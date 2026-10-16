"""Deterministic dependency-aware chunk removal, independent of the oracle business logic."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Set
from dataclasses import dataclass
from typing import Protocol, cast

from reproseed.observation import (
    NO_OBSERVER,
    Observation,
    ObservationOutcome,
    Observer,
    sanitize_reason,
)
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
    cache_hits: int = 0


class _CandidateEncoding:
    """Exact packed membership within one immutable, deterministically ordered universe."""

    def __init__(self, rows: Iterable[RowId]) -> None:
        # Keep the existing RowId objects, rather than copying or stringifying keys.
        # Duplicates in a protocol caller's rows still describe one row identity.
        self.ordinals = dict.fromkeys(rows, 0)
        for ordinal, row in enumerate(sorted(self.ordinals, key=row_sort_key)):
            self.ordinals[row] = ordinal
        self.byte_count = (len(self.ordinals) + 7) // 8

    def encode(self, retained: Set[RowId]) -> bytes:
        # Fixed width preserves leading/trailing zero bits. Each identity owns one
        # bit, so byte equality is set equality within this invocation's universe.
        membership = bytearray(self.byte_count)
        for row in retained:
            ordinal = self.ordinals[row]
            membership[ordinal // 8] |= 1 << (ordinal % 8)
        return bytes(membership)


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
        return _Checkpoint(
            candidate, number, checkpoint.accepted_count + 1, checkpoint.cache_hits + int(cached)
        )
    return _Checkpoint(
        checkpoint.retained, number, checkpoint.accepted_count, checkpoint.cache_hits + int(cached)
    )


def reduce_rows(
    model: ReductionModel,
    evaluate: Callable[[frozenset[RowId]], Evaluation],
    observer: Observer = NO_OBSERVER,
) -> SearchResult:
    checkpoint = _Checkpoint(frozenset(model.rows))
    attempts: list[dict[str, object]] = []
    accepted: list[dict[str, object]] = []
    cache: dict[bytes, Evaluation] = {}
    groups = 1
    reason = "single_row_closures_exhausted"
    try:
        encoding = _CandidateEncoding(model.rows)
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
                observer.emit(
                    Observation(
                        "candidate",
                        "search",
                        candidate_rows=len(candidate),
                        retained_rows=len(checkpoint.retained),
                        attempts=checkpoint.attempt_count,
                        accepted_changes=checkpoint.accepted_count,
                        cache_hits=checkpoint.cache_hits,
                    )
                )
                # Closure-normalized membership remains the cache identity.
                key = encoding.encode(candidate)
                cached = key in cache
                if cached:
                    result = cache[key]
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
                        cache[key] = result
                checkpoint = _commit_progress(
                    checkpoint, attempts, accepted, candidate, len(closure), result, cached
                )
                observer.emit(
                    Observation(
                        "committed",
                        "search",
                        candidate_rows=len(candidate),
                        retained_rows=len(checkpoint.retained),
                        attempts=checkpoint.attempt_count,
                        accepted_changes=checkpoint.accepted_count,
                        cache_hits=checkpoint.cache_hits,
                        outcome=cast(ObservationOutcome, result.outcome),
                        reason=(
                            "database_invalid"
                            if result.outcome == "DATABASE_INVALID"
                            else sanitize_reason(result.reason)
                        ),
                    )
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
