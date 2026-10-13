"""Algorithm invariants on a real cyclic SQLite model."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from reproseed.reducer import BudgetExhausted, Evaluation, reduce_rows
from reproseed.sqlite_adapter import DatabaseModel, RowId


def cyclic_model(tmp_path: Path) -> DatabaseModel:
    path = tmp_path / "cycle.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.executescript(
            "CREATE TABLE vertices(id INTEGER PRIMARY KEY, peer INTEGER REFERENCES vertices(id));"
            "INSERT INTO vertices VALUES(1,2),(2,1),(99,NULL);"
        )
    return DatabaseModel.from_database(path)


def test_deterministic_progress_and_normalized_closure_cache(tmp_path: Path) -> None:
    model = cyclic_model(tmp_path)
    calls: list[frozenset[RowId]] = []

    def evaluate(retained: frozenset[RowId]) -> Evaluation:
        calls.append(retained)
        return Evaluation("TARGET_FAILURE" if ("vertices", 1) in retained else "PASS")

    first = reduce_rows(model, evaluate)
    first_calls = calls.copy()
    calls.clear()
    second = reduce_rows(model, evaluate)
    assert calls == first_calls
    assert first == second
    assert len(first.retained) == 2
    assert first.cache_hits >= 2
    assert len(first_calls) == len(set(first_calls))
    assert all(a["before"] > a["after"] for a in first.accepted)


def test_unresolved_is_not_cached_as_failure_or_pass(tmp_path: Path) -> None:
    model = cyclic_model(tmp_path)
    calls: list[frozenset[RowId]] = []

    def evaluate(retained: frozenset[RowId]) -> Evaluation:
        calls.append(retained)
        return Evaluation("UNRESOLVED")

    result = reduce_rows(model, evaluate)
    assert result.retained == frozenset(model.rows)
    assert result.cache_hits == 0
    assert len(calls) > len(set(calls))
    assert all(a["outcome"] == "UNRESOLVED" for a in result.attempts)


def test_budget_and_interruption_preserve_best_confirmed(tmp_path: Path) -> None:
    model = cyclic_model(tmp_path)
    calls = 0

    def evaluate(retained: frozenset[RowId]) -> Evaluation:
        nonlocal calls
        calls += 1
        if calls == 1:
            return Evaluation("UNRESOLVED")
        if calls == 2:
            return Evaluation("TARGET_FAILURE")
        raise BudgetExhausted

    result = reduce_rows(model, evaluate)
    assert len(result.retained) == 1
    assert result.termination_reason.startswith("oracle_budget_exhausted")

    def interrupted(retained: frozenset[RowId]) -> Evaluation:
        raise KeyboardInterrupt

    result = reduce_rows(model, interrupted)
    assert result.retained == frozenset(model.rows)
    assert result.termination_reason.startswith("interrupted")


def test_empty_and_irreducible_models(tmp_path: Path) -> None:
    model = cyclic_model(tmp_path)
    empty = reduce_rows(model, lambda retained: Evaluation("TARGET_FAILURE"))
    assert not empty.retained
    assert empty.termination_reason == "empty_candidate_confirmed"
    unchanged = reduce_rows(model, lambda retained: Evaluation("PASS"))
    assert unchanged.retained == frozenset(model.rows)
    assert unchanged.termination_reason == "single_row_closures_exhausted"
