"""Deterministic dependency-aware chunk removal, independent of the oracle business logic."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Set
from dataclasses import dataclass
from typing import Protocol

from reproseed.sqlite_adapter import RowId


class BudgetExhausted(Exception):
    """Search must stop while preserving capacity for final verification."""


class ReductionModel(Protocol):
    @property
    def rows(self) -> tuple[RowId, ...]: ...

    def deletion_closure(
        self, seeds: Iterable[RowId], retained: Set[RowId]
    ) -> frozenset[RowId]: ...


@dataclass(frozen=True)
class Evaluation:
    outcome: str
    confirmations: tuple[dict[str, object], ...] = ()
    reason: str = ""


@dataclass
class SearchResult:
    retained: frozenset[RowId]
    attempts: list[dict[str, object]]
    accepted: list[dict[str, object]]
    cache_hits: int
    termination_reason: str


def reduce_rows(
    model: ReductionModel, evaluate: Callable[[frozenset[RowId]], Evaluation]
) -> SearchResult:
    retained = frozenset(model.rows)
    attempts: list[dict[str, object]] = []
    accepted: list[dict[str, object]] = []
    cache: dict[frozenset[RowId], Evaluation] = {}
    cache_hits = 0
    groups = 1
    reason = "single_row_closures_exhausted"
    try:
        while retained:
            ordered = sorted(retained)
            width = (len(ordered) + groups - 1) // groups
            changed = False
            for offset in range(0, len(ordered), width):
                closure = model.deletion_closure(ordered[offset : offset + width], retained)
                candidate = retained - closure
                if not closure or len(candidate) >= len(retained):
                    continue
                cached = candidate in cache
                if cached:
                    result = cache[candidate]
                    cache_hits += 1
                else:
                    try:
                        result = evaluate(candidate)
                    except KeyboardInterrupt:
                        attempts.append(
                            {
                                "number": len(attempts) + 1,
                                "retained_rows": len(candidate),
                                "removed_rows": len(closure),
                                "outcome": "UNRESOLVED",
                                "reason": "interrupted_during_evaluation",
                                "cached": False,
                                "confirmations": [],
                            }
                        )
                        raise
                    # Unresolved trials are never evidence of a verified failure, nor a stable pass.
                    if result.outcome != "UNRESOLVED":
                        cache[candidate] = result
                attempt: dict[str, object] = {
                    "number": len(attempts) + 1,
                    "retained_rows": len(candidate),
                    "removed_rows": len(closure),
                    "outcome": result.outcome,
                    "reason": result.reason,
                    "cached": cached,
                    "confirmations": list(result.confirmations),
                }
                attempts.append(attempt)
                if result.outcome == "TARGET_FAILURE":
                    accepted.append(
                        {"attempt": len(attempts), "before": len(retained), "after": len(candidate)}
                    )
                    retained = candidate
                    groups = max(1, groups - 1)
                    changed = True
                    break
            if changed:
                continue
            if groups >= len(ordered):
                break
            groups = min(len(ordered), groups * 2)
        if not retained:
            reason = "empty_candidate_confirmed"
    except BudgetExhausted:
        reason = "oracle_budget_exhausted_reserved_final_verification"
    except KeyboardInterrupt:
        reason = "interrupted_best_confirmed_candidate_preserved"
    return SearchResult(retained, attempts, accepted, cache_hits, reason)
