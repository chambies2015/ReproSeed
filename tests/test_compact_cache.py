"""Exact per-run cache identities and immutable model indexes."""

from __future__ import annotations

import hashlib
import itertools
import random
import sqlite3
import sys
from collections.abc import Iterable, Set
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any

import pytest

from reproseed import reducer, sqlite_adapter
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel, RowId, row_sort_key


@dataclass(frozen=True)
class Model:
    rows: tuple[RowId, ...] = (("items", 1), ("items", 2), ("items", 3))

    def deletion_closure(self, seeds: Iterable[RowId], retained: Set[RowId]) -> frozenset[RowId]:
        return frozenset(seeds).intersection(retained)


def test_canonical_encoding_preserves_exact_typed_declared_identities() -> None:
    rows: tuple[RowId, ...] = (
        ("scalar", 42),
        ("scalar", "42"),
        ("other", 42),
        ("composite", ("a", 42)),
        ("composite", ("b", 42)),
        ("composite", (42, "a")),
        ("composite", ("42", "a")),
        ("text", "\x00\u00e9"),
    )
    first = reducer._CandidateEncoding(rows)
    second = reducer._CandidateEncoding(tuple(reversed(rows)))
    assert first.ordinals == second.ordinals
    assert tuple(sorted(first.ordinals, key=first.ordinals.__getitem__)) == tuple(
        sorted(rows, key=row_sort_key)
    )
    seen: dict[bytes, frozenset[RowId]] = {}
    for width in range(len(rows) + 1):
        for subset in itertools.combinations(rows, width):
            candidate = frozenset(subset)
            key = first.encode(candidate)
            assert isinstance(key, bytes)
            assert key == second.encode(candidate)
            assert key not in seen
            seen[key] = candidate
    assert len(seen) == 2 ** len(rows)


@pytest.mark.parametrize("size", [0, 1, 7, 8, 9, 15, 16, 17, 100])
def test_empty_full_sparse_dense_and_unused_bits(size: int) -> None:
    rows = tuple(("items", key) for key in range(size))
    encoding = reducer._CandidateEncoding(rows)
    width = (size + 7) // 8
    assert encoding.byte_count == width
    assert encoding.encode(frozenset()) == bytes(width)
    full = encoding.encode(frozenset(rows))
    assert len(full) == width
    if size % 8:
        assert full[-1] == (1 << (size % 8)) - 1
    generator = random.Random(709)
    for _ in range(50):
        candidate = frozenset(row for row in rows if generator.randrange(4))
        key = encoding.encode(candidate)
        decoded = frozenset(
            row
            for row, ordinal in encoding.ordinals.items()
            if key[ordinal // 8] & (1 << (ordinal % 8))
        )
        assert decoded == candidate
        assert len(key) == width
    for ordinal in (0, 7, 8, size - 1):
        if 0 <= ordinal < size:
            key = encoding.encode(frozenset({rows[ordinal]}))
            assert key == bytes(ordinal // 8) + bytes([1 << (ordinal % 8)]) + bytes(
                width - ordinal // 8 - 1
            )


def test_duplicate_universe_entries_do_not_create_extra_ordinals() -> None:
    rows = Model().rows
    encoding = reducer._CandidateEncoding(rows + rows)
    assert len(encoding.ordinals) == len(rows)
    assert encoding.encode(frozenset(rows)) == b"\x07"
    with pytest.raises(KeyError):
        encoding.encode(frozenset({("items", 99)}))


@pytest.mark.parametrize("outcome", ["PASS", "DATABASE_INVALID", "UNRESOLVED"])
def test_normalized_keys_follow_closure_and_unresolved_remains_uncached(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    class Component(Model):
        def deletion_closure(
            self, seeds: Iterable[RowId], retained: Set[RowId]
        ) -> frozenset[RowId]:
            return frozenset(retained)

    encoded: list[frozenset[RowId]] = []
    original = reducer._CandidateEncoding.encode

    def record(self: reducer._CandidateEncoding, candidate: Set[RowId]) -> bytes:
        encoded.append(frozenset(candidate))
        return original(self, candidate)

    monkeypatch.setattr(reducer._CandidateEncoding, "encode", record)
    calls: list[frozenset[RowId]] = []

    def evaluate(candidate: frozenset[RowId]) -> reducer.Evaluation:
        calls.append(candidate)
        return reducer.Evaluation(outcome)

    result = reducer.reduce_rows(Component(), evaluate)
    assert encoded and all(candidate == frozenset() for candidate in encoded)
    assert all(candidate == frozenset() for candidate in calls)
    if outcome == "UNRESOLVED":
        assert len(calls) == len(result.attempts)
        assert result.cache_hits == 0
    else:
        assert len(calls) == 1
        assert result.cache_hits == len(result.attempts) - 1
    assert not result.accepted


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_encoding_interruption_preserves_committed_acceptance(
    monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    original = reducer._CandidateEncoding.encode
    encodings = 0
    evaluations: list[frozenset[RowId]] = []

    def interrupted(self: reducer._CandidateEncoding, candidate: Set[RowId]) -> bytes:
        nonlocal encodings
        encodings += 1
        if encodings == 3 and boundary == "before":
            raise KeyboardInterrupt
        key = original(self, candidate)
        if encodings == 3 and boundary == "after":
            raise KeyboardInterrupt
        return key

    def evaluate(candidate: frozenset[RowId]) -> reducer.Evaluation:
        evaluations.append(candidate)
        return reducer.Evaluation("TARGET_FAILURE" if candidate else "PASS")

    monkeypatch.setattr(reducer._CandidateEncoding, "encode", interrupted)
    result = reducer.reduce_rows(Model(), evaluate)
    assert encodings == 3
    assert evaluations == [frozenset(), frozenset({("items", 3)})]
    assert result.retained == frozenset({("items", 3)})
    assert len(result.attempts) == 2
    assert result.accepted == [{"attempt": 2, "before": 3, "after": 1}]
    assert result.cache_hits == 0
    assert result.termination_reason == "interrupted_best_confirmed_candidate_preserved"


def test_ordinal_construction_interruption_preserves_original_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupted(self: reducer._CandidateEncoding, rows: Iterable[RowId]) -> None:
        raise KeyboardInterrupt

    def evaluate(candidate: frozenset[RowId]) -> reducer.Evaluation:
        pytest.fail("encoding setup must finish before evaluation")

    monkeypatch.setattr(reducer._CandidateEncoding, "__init__", interrupted)
    result = reducer.reduce_rows(Model(), evaluate)
    assert result.retained == frozenset(Model().rows)
    assert not result.attempts
    assert not result.accepted
    assert result.termination_reason == "interrupted_best_confirmed_candidate_preserved"


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_cache_insertion_interruption_does_not_promote_completed_evaluation(
    monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    original = reducer._CandidateEncoding.encode
    injected = False
    evaluations: list[frozenset[RowId]] = []

    class InterruptingKey(bytes):
        hashes = 0

        def __hash__(self) -> int:
            nonlocal injected
            self.hashes += 1
            if self.hashes == 2:
                injected = True
                raise KeyboardInterrupt
            return super().__hash__()

    def encode(self: reducer._CandidateEncoding, candidate: Set[RowId]) -> bytes:
        key = original(self, candidate)
        return InterruptingKey(key) if candidate and boundary == "before" else key

    def evaluate(candidate: frozenset[RowId]) -> reducer.Evaluation:
        evaluations.append(candidate)
        return reducer.Evaluation("TARGET_FAILURE" if candidate else "PASS")

    def trace(frame: FrameType, event: str, argument: object) -> Any:
        nonlocal injected
        if event == "line" and frame.f_code is reducer.reduce_rows.__code__:
            cache = frame.f_locals.get("cache", {})
            if boundary == "after" and len(cache) == 2:
                injected = True
                sys.settrace(None)
                raise KeyboardInterrupt
        return trace

    monkeypatch.setattr(reducer._CandidateEncoding, "encode", encode)
    previous = sys.gettrace()
    try:
        sys.settrace(trace)
        result = reducer.reduce_rows(Model(), evaluate)
    finally:
        sys.settrace(previous)
    assert injected
    assert len(evaluations) == 2
    assert result.retained == frozenset(Model().rows)
    assert len(result.attempts) == 1
    assert not result.accepted
    assert result.cache_hits == 0
    assert result.termination_reason == "interrupted_best_confirmed_candidate_preserved"


def test_run_local_indexes_do_not_reuse_a_replaced_database(tmp_path: Path) -> None:
    source = tmp_path / "reused.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.executescript(
            "CREATE TABLE items(id INTEGER PRIMARY KEY); INSERT INTO items VALUES(1)"
        )
    first = DatabaseModel.from_database(source)
    with closing(sqlite3.connect(source)) as connection:
        connection.executescript("DELETE FROM items; INSERT INTO items VALUES(2)")
    second = DatabaseModel.from_database(source)
    assert first.rows == (("items", 1),)
    assert second.rows == (("items", 2),)
    calls: list[frozenset[RowId]] = []

    def evaluate(candidate: frozenset[RowId]) -> reducer.Evaluation:
        calls.append(candidate)
        return reducer.Evaluation("PASS")

    for model in (first, second):
        result = reducer.reduce_rows(model, evaluate)
        assert result.retained == frozenset(model.rows)
        assert result.cache_hits == 0
    assert calls == [frozenset(), frozenset()]
    with pytest.raises(DatabaseError):
        first.deletion_closure(second.rows, frozenset(first.rows))
    with pytest.raises(DatabaseError):
        second.counts(first.rows)


def test_adapter_indexes_preserve_constructor_order_and_explicit_deletions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.executescript(
            "CREATE TABLE a(id TEXT PRIMARY KEY);"
            "CREATE TABLE b(tenant TEXT, id INTEGER, PRIMARY KEY(tenant,id)) WITHOUT ROWID;"
            "CREATE TABLE empty(id INTEGER PRIMARY KEY);"
            "INSERT INTO a VALUES('one'),('two'),('three');"
            "INSERT INTO b VALUES('a',1),('b',1),('a',2);"
        )
    validated = DatabaseModel.from_database(source)
    rows: tuple[RowId, ...] = (
        ("b", ("b", 1)),
        ("a", "three"),
        ("b", ("a", 2)),
        ("a", "one"),
        ("b", ("a", 1)),
        ("a", "two"),
    )
    model = DatabaseModel(rows, validated._tables, validated._dependents)
    assert model.rows == rows
    assert model._row_universe == frozenset(rows)
    assert model._rows_by_table["a"] == (("a", "three"), ("a", "one"), ("a", "two"))
    assert model._rows_by_table["empty"] == ()
    with pytest.raises(TypeError):
        model._rows_by_table["a"] = ()  # type: ignore[index]
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    deleted: list[str] = []
    connect = sqlite3.connect

    def traced(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(
            lambda sql: deleted.append(sql) if sql.startswith("DELETE FROM ") else None
        )
        return connection

    monkeypatch.setattr(sqlite_adapter.sqlite3, "connect", traced)
    candidate = tmp_path / "candidate.sqlite3"
    retained = frozenset({("a", "two"), ("b", ("a", 1))})
    model.materialize(source, retained, candidate)
    assert deleted == [
        'DELETE FROM "a" WHERE "id" COLLATE BINARY = \'three\'',
        'DELETE FROM "a" WHERE "id" COLLATE BINARY = \'one\'',
        'DELETE FROM "b" WHERE "tenant" COLLATE BINARY = \'b\' AND "id" COLLATE BINARY = 1',
        'DELETE FROM "b" WHERE "tenant" COLLATE BINARY = \'a\' AND "id" COLLATE BINARY = 2',
    ]
    assert DatabaseModel.from_database(candidate).rows == tuple(sorted(retained, key=row_sort_key))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
