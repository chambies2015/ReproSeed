"""Baseline, reduction, and independent final verification orchestration."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from reproseed.config import Config
from reproseed.oracle import OracleInterrupted, OracleResult, Outcome, run_oracle
from reproseed.reducer import BudgetExhausted, Evaluation, reduce_rows
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel, compact, snapshot


class VerificationError(ValueError):
    """The configured failure could not be established; no verified bundle is produced."""


@dataclass
class InvocationCounter:
    config: Config
    count: int = 0
    unknown_launches: int = 0
    interrupted_invocations: list[dict[str, object]] = field(default_factory=list)

    @property
    def charged(self) -> int:
        return self.count + self.unknown_launches

    def invoke(self, database: Path) -> OracleResult:
        if self.charged >= self.config.max_invocations:
            raise BudgetExhausted
        try:
            result = run_oracle(self.config.oracle, database, self.config.assets)
        except OracleInterrupted as exc:
            self.interrupted_invocations.append(
                {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": exc.executed}
            )
            if exc.executed is True:
                self.count += 1
            elif exc.executed is None:
                self.unknown_launches += 1
            raise
        if result.executed:
            self.count += 1
        return result


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
