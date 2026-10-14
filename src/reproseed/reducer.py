"""Deterministic dependency-aware chunk removal, independent of the oracle business logic."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Set
from dataclasses import dataclass
from typing import Protocol

from reproseed.sqlite_adapter import RowId, row_sort_key


class BudgetExhausted(Exception):
    """Search must stop while preserving capacity for final verification."""


class AbortReduction(KeyboardInterrupt):
    """A further cancellation prevented invocation accounting recovery."""


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


@dataclass(frozen=True)
class _Checkpoint:
    retained: frozenset[RowId]
    attempt_count: int = 0
    accepted_count: int = 0


def _commit_progress(
    checkpoint: _Checkpoint,
    attempts: list[dict[str, object]],
    accepted: list[dict[str, object]],
    candidate: frozenset[RowId],
    removed_rows: int,
    result: Evaluation,
    cached: bool,
) -> _Checkpoint:
    """Prepare append-only progress; the caller publishes the returned checkpoint."""
    number = checkpoint.attempt_count + 1
    attempts.append(
        {
            "number": number,
            "retained_rows": len(candidate),
            "removed_rows": removed_rows,
            "outcome": result.outcome,
            "reason": result.reason,
            "cached": cached,
            "confirmations": list(result.confirmations),
        }
    )
    if result.outcome == "TARGET_FAILURE":
        accepted.append(
            {"attempt": number, "before": len(checkpoint.retained), "after": len(candidate)}
        )
        return _Checkpoint(candidate, number, checkpoint.accepted_count + 1)
    return _Checkpoint(checkpoint.retained, number, checkpoint.accepted_count)


def reduce_rows(
    model: ReductionModel, evaluate: Callable[[frozenset[RowId]], Evaluation]
) -> SearchResult:
    checkpoint = _Checkpoint(frozenset(model.rows))
    attempts: list[dict[str, object]] = []
    accepted: list[dict[str, object]] = []
    cache: dict[frozenset[RowId], Evaluation] = {}
    groups = 1
    reason = "single_row_closures_exhausted"
    try:
        while checkpoint.retained:
            retained = checkpoint.retained
            ordered = sorted(retained, key=row_sort_key)
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
                else:
                    try:
                        result = evaluate(candidate)
                    except AbortReduction:
                        raise
                    except KeyboardInterrupt:
                        checkpoint = _commit_progress(
                            checkpoint,
                            attempts,
                            accepted,
                            candidate,
                            len(closure),
                            Evaluation("UNRESOLVED", reason="interrupted_during_evaluation"),
                            False,
                        )
                        raise
                    # Unresolved trials are never evidence of a verified failure, nor a stable pass.
                    if result.outcome != "UNRESOLVED":
                        cache[candidate] = result
                checkpoint = _commit_progress(
                    checkpoint, attempts, accepted, candidate, len(closure), result, cached
                )
                if result.outcome == "TARGET_FAILURE":
                    groups = max(1, groups - 1)
                    changed = True
                    break
            if changed:
                continue
            if groups >= len(ordered):
                break
            groups = min(len(ordered), groups * 2)
        if not checkpoint.retained:
            reason = "empty_candidate_confirmed"
    except BudgetExhausted:
        reason = "oracle_budget_exhausted_reserved_final_verification"
    except AbortReduction:
        raise
    except KeyboardInterrupt:
        reason = "interrupted_best_confirmed_candidate_preserved"
    # A cancelled preparation may have appended a provisional tail. One reference
    # publication decides both the retained rows and the visible history prefixes.
    # Normal transitions are O(1) in history size; truncate/fold only on return.
    del attempts[checkpoint.attempt_count :]
    del accepted[checkpoint.accepted_count :]
    cache_hits = sum(attempt["cached"] is True for attempt in attempts)
    return SearchResult(checkpoint.retained, attempts, accepted, cache_hits, reason)
