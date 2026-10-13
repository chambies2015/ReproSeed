"""Baseline, reduction, and independent final verification orchestration."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from reproseed.config import Config
from reproseed.oracle import OracleInterrupted, OracleInvocation, OracleResult, Outcome, run_oracle
from reproseed.reducer import AbortReduction, BudgetExhausted, Evaluation, reduce_rows
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel, compact, snapshot


class VerificationError(ValueError):
    """The configured failure could not be established; no verified bundle is produced."""


@dataclass(frozen=True)
class _InterruptedInvocation:
    invocation: OracleInvocation
    executed: bool | None
    previous: _InterruptedInvocation | None


@dataclass(frozen=True)
class _Accounting:
    count: int = 0
    unknown_launches: int = 0
    last: OracleInvocation | None = None
    interrupted: _InterruptedInvocation | None = None


@dataclass
class InvocationCounter:
    config: Config
    _accounting: _Accounting = field(default_factory=_Accounting, init=False)

    @property
    def count(self) -> int:
        return self._accounting.count

    @property
    def unknown_launches(self) -> int:
        return self._accounting.unknown_launches

    @property
    def interrupted_invocations(self) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        node = self._accounting.interrupted
        while node is not None:
            records.append(
                {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": node.executed}
            )
            node = node.previous
        records.reverse()
        return records

    @property
    def charged(self) -> int:
        return self.count + self.unknown_launches

    def _publish_accounting(self, accounting: _Accounting) -> None:
        # One reference publishes charge and interruption evidence together.
        self._accounting = accounting

    def _record(self, invocation: OracleInvocation, *, interrupted: bool) -> None:
        previous = self._accounting
        new_charge = previous.last is not invocation
        known = previous.count + (new_charge and invocation.executed is True)
        unknown = previous.unknown_launches + (new_charge and invocation.executed is None)
        history = previous.interrupted
        if interrupted and (history is None or history.invocation is not invocation):
            history = _InterruptedInvocation(invocation, invocation.executed, history)
        self._publish_accounting(_Accounting(known, unknown, invocation, history))

    def invoke(self, database: Path) -> OracleResult:
        if self.charged >= self.config.max_invocations:
            raise BudgetExhausted
        invocation = OracleInvocation()
        try:
            result = run_oracle(self.config.oracle, database, self.config.assets, invocation)
            invocation.executed = result.executed
            self._record(invocation, interrupted=False)
            return result
        except KeyboardInterrupt as exc:
            # This recovery is attempted once. A further interrupt propagates;
            # it cannot turn an incomplete finalization into a verified bundle.
            try:
                if isinstance(exc, OracleInterrupted):
                    invocation.executed = exc.executed
                self._record(invocation, interrupted=True)
            except KeyboardInterrupt:
                raise AbortReduction from None
            raise


def build_verified_fixture(config: Config, destination: Path) -> dict[str, object]:
    counter = InvocationCounter(config)
    with tempfile.TemporaryDirectory(prefix="reproseed-search-") as temporary:
        working = Path(temporary)
        pristine = working / "pristine.sqlite3"
        snapshot(config.source, pristine)
        model = DatabaseModel.from_database(pristine)
        baseline = [counter.invoke(pristine).as_dict() for _ in range(3)]
        if any(result["outcome"] != Outcome.TARGET_FAILURE.value for result in baseline):
            outcomes = [str(result["outcome"]) + ":" + str(result["reason"]) for result in baseline]
            raise VerificationError(
                "baseline failed three fresh confirmations: " + ", ".join(outcomes)
            )

        def evaluate(retained: frozenset[tuple[str, int]]) -> Evaluation:
            if counter.charged + 2 > config.max_invocations - 3:
                raise BudgetExhausted
            with tempfile.TemporaryDirectory(prefix="trial-", dir=working) as trial:
                candidate = Path(trial) / "candidate.sqlite3"
                try:
                    model.materialize(pristine, retained, candidate)
                except DatabaseError as exc:
                    return Evaluation("DATABASE_INVALID", reason=str(exc)[:500])
                first = counter.invoke(candidate)
                confirmations = [first.as_dict()]
                if first.outcome != Outcome.TARGET_FAILURE:
                    return Evaluation(first.outcome.value, tuple(confirmations), first.reason)
                second = counter.invoke(candidate)
                confirmations.append(second.as_dict())
                if second.outcome != Outcome.TARGET_FAILURE:
                    return Evaluation(
                        "UNRESOLVED", tuple(confirmations), "conflicting_confirmations"
                    )
                return Evaluation("TARGET_FAILURE", tuple(confirmations), "two_fresh_confirmations")

        search = reduce_rows(model, evaluate)
        best = working / "best.sqlite3"
        model.materialize(pristine, search.retained, best)
        compact(best, destination)
        final = [counter.invoke(destination).as_dict() for _ in range(3)]
        if any(result["outcome"] != Outcome.TARGET_FAILURE.value for result in final):
            raise VerificationError(
                "final artifact failed three fresh confirmations; bundle not published"
            )
        return {
            "version": 1,
            "verified": True,
            "original_counts": model.counts(),
            "final_counts": model.counts(search.retained),
            "oracle_invocations": counter.count,
            "unknown_interrupted_launches": counter.unknown_launches,
            "budget_charged_invocations": counter.charged,
            "interrupted_invocations": counter.interrupted_invocations,
            "max_invocations": config.max_invocations,
            "baseline_verification": baseline,
            "final_verification": final,
            "attempts": search.attempts,
            "accepted_reductions": search.accepted,
            "cache_hits": search.cache_hits,
            "unresolved_attempts": sum(a["outcome"] == "UNRESOLVED" for a in search.attempts),
            "invalid_candidates": sum(a["outcome"] == "DATABASE_INVALID" for a in search.attempts),
            "termination_reason": search.termination_reason,
            "minimality": (
                "No global minimality claim; exhausted closures may include unresolved trials."
            ),
        }
