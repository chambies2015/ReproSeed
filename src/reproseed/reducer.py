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


_CacheKey = bytes | frozenset[RowId]
_SPARSE_LIMIT = 32


def _supported_identity(row: RowId) -> bool:
    # bool/float compare equal to integers in Python, but are not SQLite identities.
    if type(row) is not tuple or len(row) != 2 or type(row[0]) is not str:
        return False
    key = row[1]
    if type(key) in (int, str):
        return True
    return (
        type(key) is tuple
        and len(key) == 2
        and all(type(component) in (int, str) for component in key)
    )


class _CandidateEncoding:
    """Bounded exact sparse keys and lazy packed membership in one immutable universe."""

    def __init__(self, rows: Iterable[RowId], *, universe: frozenset[RowId] | None = None) -> None:
        # Production borrows both objects from the live immutable model. Protocol
        # callers without its membership index use tuple membership on the small
        # sparse path; no additional O(N) membership structure is retained.
        self.rows = rows if isinstance(rows, tuple) else tuple(rows)
        if any(not _supported_identity(row) for row in self.rows):
            raise ValueError("Unsupported row identity in candidate universe")
        self.universe = universe
        self.ordinals: dict[RowId, int] | None = None

    def _packed_ordinals(self) -> dict[RowId, int]:
        if self.ordinals is None:
            # Build privately. An interruption leaves the previous coherent state;
            # neither encoding nor later evaluation can observe a partial map.
            ordinals = dict.fromkeys(self.rows, 0)
            for ordinal, row in enumerate(sorted(ordinals, key=row_sort_key)):
                ordinals[row] = ordinal
            self.ordinals = ordinals
        return self.ordinals

    def encode(self, retained: Set[RowId]) -> _CacheKey:
        if len(retained) <= _SPARSE_LIMIT:
            universe = self.rows if self.universe is None else self.universe
            for row in retained:
                if not _supported_identity(row):
                    raise ValueError("Unsupported row identity in candidate")
                if row not in universe:
                    raise KeyError(row)
            return frozenset(retained)
        ordinals = self._packed_ordinals()
        # Fixed width preserves leading/trailing zero bits. Each identity owns one
        # bit; bytes and sparse frozensets are disjoint key types. Cardinality alone
        # selects the representation, independent of insertion/initialization order.
        membership = bytearray((len(ordinals) + 7) // 8)
        for row in retained:
            if not _supported_identity(row):
                raise ValueError("Unsupported row identity in candidate")
            ordinal = ordinals[row]
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
    cache: dict[_CacheKey, Evaluation] = {}
    groups = 1
    reason = "single_row_closures_exhausted"
    try:
        encoding = _CandidateEncoding(model.rows, universe=getattr(model, "row_universe", None))
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
