"""Baseline, reduction, and independent final verification orchestration."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from reproseed.config import Config
from reproseed.observation import NO_OBSERVER, Observation, Observer, Phase, sanitize_reason
from reproseed.oracle import OracleInterrupted, OracleInvocation, OracleResult, Outcome, run_oracle
from reproseed.reducer import AbortReduction, BudgetExhausted, Evaluation, reduce_rows
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel, RowId, compact, snapshot


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
    observer: Observer = NO_OBSERVER
    phase: Phase = "search"
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
        except KeyboardInterrupt as exc:
            # This recovery is attempted once. A further interrupt propagates;
            # it cannot turn an incomplete finalization into a verified bundle.
            try:
                if isinstance(exc, OracleInterrupted):
                    invocation.executed = exc.executed
                self._record(invocation, interrupted=True)
                self.observer.emit(
                    Observation(
                        "invocation",
                        self.phase,
                        outcome="UNRESOLVED",
                        reason="interrupted",
                        executed=invocation.executed,
                        known_executions=self.count,
                        unknown_launches=self.unknown_launches,
                        charged_invocations=self.charged,
                    )
                )
            except KeyboardInterrupt:
                raise AbortReduction from None
            if isinstance(exc, OracleInterrupted) and exc.abort:
                raise AbortReduction from exc
            raise
        # Notification follows coherent accounting, outside interruption recovery.
        self.observer.emit(
            Observation(
                "invocation",
                self.phase,
                outcome=result.outcome.value,
                executed=result.executed,
                known_executions=self.count,
                unknown_launches=self.unknown_launches,
                charged_invocations=self.charged,
            )
        )
        return result


def build_verified_fixture(
    config: Config, destination: Path, observer: Observer = NO_OBSERVER
) -> dict[str, object]:
    counter = InvocationCounter(config, observer)
    with tempfile.TemporaryDirectory(prefix="reproseed-search-") as temporary:
        working = Path(temporary)
        pristine = working / "pristine.sqlite3"
        observer.emit(Observation("started", "acquisition"))
        snapshot(config.source, pristine)
        observer.emit(Observation("completed", "acquisition"))
        observer.emit(Observation("started", "model"))
        model = DatabaseModel.from_database(pristine)
        observer.emit(
            Observation(
                "model_ready",
                "model",
                original_rows=len(model.rows),
                retained_rows=len(model.rows),
                max_invocations=config.max_invocations,
            )
        )
        counter.phase = "baseline"
        observer.emit(Observation("started", "baseline", required_confirmations=3))
        baseline = []
        for confirmation in range(1, 4):
            result = counter.invoke(pristine)
            baseline.append(result.as_dict())
            observer.emit(
                Observation(
                    "confirmation",
                    "baseline",
                    confirmation=confirmation,
                    required_confirmations=3,
                    outcome=result.outcome.value,
                    known_executions=counter.count,
                    charged_invocations=counter.charged,
                )
            )
        if any(result["outcome"] != Outcome.TARGET_FAILURE.value for result in baseline):
            observer.emit(Observation("failed", "baseline", reason="baseline_failed"))
            outcomes = [str(result["outcome"]) + ":" + str(result["reason"]) for result in baseline]
            raise VerificationError(
                "baseline failed three fresh confirmations: " + ", ".join(outcomes)
            )
        observer.emit(Observation("completed", "baseline", required_confirmations=3))
        counter.phase = "search"

        def evaluate(retained: frozenset[RowId]) -> Evaluation:
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

        observer.emit(Observation("started", "search", retained_rows=len(model.rows)))
        search = reduce_rows(model, evaluate, observer=observer)
        observer.emit(
            Observation(
                "search_stopped",
                "search",
                retained_rows=len(search.retained),
                attempts=len(search.attempts),
                accepted_changes=len(search.accepted),
                cache_hits=search.cache_hits,
                reason=sanitize_reason(search.termination_reason),
                known_executions=counter.count,
                unknown_launches=counter.unknown_launches,
                charged_invocations=counter.charged,
            )
        )
        observer.emit(Observation("started", "compaction", retained_rows=len(search.retained)))
        best = working / "best.sqlite3"
        model.materialize(pristine, search.retained, best)
        compact(best, destination)
        observer.emit(Observation("completed", "compaction", retained_rows=len(search.retained)))
        counter.phase = "final_verification"
        observer.emit(Observation("started", "final_verification", required_confirmations=3))
        final = []
        for confirmation in range(1, 4):
            result = counter.invoke(destination)
            final.append(result.as_dict())
            observer.emit(
                Observation(
                    "confirmation",
                    "final_verification",
                    confirmation=confirmation,
                    required_confirmations=3,
                    outcome=result.outcome.value,
                    known_executions=counter.count,
                    charged_invocations=counter.charged,
                )
            )
        if any(result["outcome"] != Outcome.TARGET_FAILURE.value for result in final):
            observer.emit(
                Observation("failed", "final_verification", reason="final_verification_failed")
            )
            raise VerificationError(
                "final artifact failed three fresh confirmations; bundle not published"
            )
        observer.emit(Observation("completed", "final_verification", required_confirmations=3))
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
