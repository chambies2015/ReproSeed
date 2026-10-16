"""Small semantic probes, also executed against isolated disposable mutants.

Each mutation target is a real product boundary. The probes use ordinary assertions
so the mutation worker can distinguish an observed semantic failure from setup errors.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Set
from contextlib import closing
from copy import deepcopy
from pathlib import Path

import pytest

from reproseed import sqlite_adapter
from reproseed.artifacts import sha256
from reproseed.config import Config, OracleSpec, load_config
from reproseed.oracle import Outcome, run_oracle
from reproseed.reducer import Evaluation, reduce_rows
from reproseed.report import ReportError, validate_report
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel, RowId
from reproseed.workflow import build_verified_fixture


def _database(path: Path, statements: str) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(statements)


def _case(directory: Path, body: str | None = None) -> Config:
    _database(
        directory / "source.sqlite3",
        "CREATE TABLE items(id INTEGER PRIMARY KEY, value TEXT);"
        "INSERT INTO items VALUES(-7,'synthetic'),(42,'decoy');",
    )
    if body is None:
        body = (
            "import sqlite3,sys\n"
            "with sqlite3.connect(sys.argv[1]) as db:\n"
            "    present=db.execute('SELECT count(*) FROM items').fetchone()[0]\n"
            "if present:\n    print('TARGET')\n    raise SystemExit(42)\n"
        )
    (directory / "oracle.py").write_text(body, encoding="utf-8")
    path = directory / "case.toml"
    path.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="TARGET"\nstream="stdout"\ntimeout_seconds=2.0\noutput_limit_bytes=4096\n'
        "[reduction]\nmax_invocations=40\n",
        encoding="utf-8",
    )
    return load_config(path)


def test_cache_requires_exact_membership(tmp_path: Path) -> None:
    class Model:
        rows: tuple[RowId, ...] = (("items", -7), ("items", 42), ("items", "42"))

        def deletion_closure(
            self, seeds: Iterable[RowId], retained: Set[RowId]
        ) -> frozenset[RowId]:
            return frozenset(seeds).intersection(retained)

    calls: list[frozenset[RowId]] = []

    def evaluate(candidate: frozenset[RowId]) -> Evaluation:
        calls.append(candidate)
        return Evaluation("PASS")

    result = reduce_rows(Model(), evaluate)
    for row in Model.rows:
        assert frozenset(Model.rows) - {row} in calls, (
            "equal-size candidates need distinct exact evidence"
        )
    assert len(calls) == len(set(calls)), (
        "exact repeated candidates must reuse stable PASS evidence"
    )
    assert result.retained == frozenset(Model.rows)
    assert not result.accepted


def test_composite_relationship_uses_entire_key(tmp_path: Path) -> None:
    database = tmp_path / "composite.sqlite3"
    _database(
        database,
        "CREATE TABLE parents(tenant TEXT, item INTEGER, PRIMARY KEY(tenant,item));"
        "CREATE TABLE children(id INTEGER PRIMARY KEY, tenant TEXT, item INTEGER,"
        "FOREIGN KEY(tenant,item) REFERENCES parents);"
        "INSERT INTO parents VALUES('a',42),('b',42),('a',43);"
        "INSERT INTO children VALUES(1,'a',42),(2,'b',42),(3,'a',43);",
    )
    model = DatabaseModel.from_database(database)
    rows = frozenset(model.rows)
    assert model.deletion_closure([("parents", ("a", 42))], rows) == frozenset(
        {("parents", ("a", 42)), ("children", 1)}
    ), "complete tenant/item identity must remove its child and preserve partial matches"


def test_closure_includes_transitive_descendants(tmp_path: Path) -> None:
    database = tmp_path / "chain.sqlite3"
    _database(
        database,
        "CREATE TABLE roots(id INTEGER PRIMARY KEY);"
        "CREATE TABLE children(id INTEGER PRIMARY KEY, parent INTEGER REFERENCES roots);"
        "CREATE TABLE leaves(id INTEGER PRIMARY KEY, parent INTEGER REFERENCES children);"
        "INSERT INTO roots VALUES(-7),(42);"
        "INSERT INTO children VALUES(1,-7),(2,42);"
        "INSERT INTO leaves VALUES(11,1),(12,2);",
    )
    model = DatabaseModel.from_database(database)
    assert model.deletion_closure([("roots", -7)], frozenset(model.rows)) == frozenset(
        {("roots", -7), ("children", 1), ("leaves", 11)}
    ), "required descendants must be removed transitively; unrelated descendants survive"


def test_partial_null_relationship_is_optional(tmp_path: Path) -> None:
    database = tmp_path / "nullable.sqlite3"
    _database(
        database,
        "CREATE TABLE parents(tenant TEXT, item INTEGER, PRIMARY KEY(tenant,item));"
        "CREATE TABLE children(id INTEGER PRIMARY KEY, tenant TEXT, item INTEGER,"
        "FOREIGN KEY(tenant,item) REFERENCES parents);"
        "INSERT INTO parents VALUES('',0),('a',42);"
        "INSERT INTO children VALUES(1,'a',42),(2,'a',NULL),(3,NULL,42),(4,NULL,NULL);",
    )
    try:
        model = DatabaseModel.from_database(database)
    except DatabaseError as exc:
        raise AssertionError("valid partial-NULL SQLite references must remain supported") from exc
    rows = frozenset(model.rows)
    removed = model.deletion_closure([("parents", ("a", 42))], rows)
    assert removed == frozenset({("parents", ("a", 42)), ("children", 1)}), (
        "any NULL child component means no parent dependency"
    )
    model.materialize(database, rows - removed, tmp_path / "candidate.sqlite3")


def test_each_oracle_invocation_uses_pristine_state(tmp_path: Path) -> None:
    config = _case(
        tmp_path,
        "import sqlite3,sys\n"
        "with sqlite3.connect(sys.argv[1]) as db:\n"
        "    present=db.execute('SELECT count(*) FROM items').fetchone()[0]\n"
        "    db.execute('DELETE FROM items')\n"
        "if present:\n    print('TARGET')\n    raise SystemExit(42)\n",
    )
    before = sha256(config.source)
    results = [run_oracle(config.oracle, config.source, config.assets) for _ in range(2)]
    assert [result.outcome for result in results] == [Outcome.TARGET_FAILURE] * 2, (
        "an oracle's DELETE must not become the next invocation's initial state"
    )
    assert sha256(config.source) == before, "oracle mutation must remain on disposable copies"


def test_expected_exit_without_marker_is_unresolved(tmp_path: Path) -> None:
    config = _case(tmp_path, "print('TARGET suffix'); raise SystemExit(42)\n")
    result = run_oracle(config.oracle, config.source, config.assets)
    assert result.outcome is Outcome.UNRESOLVED, (
        "matching exit alone must never establish the target"
    )
    assert result.reason == "expected failure exit without exact marker"
    assert result.executed is True


def test_final_verification_uses_three_fresh_executions(tmp_path: Path) -> None:
    config = _case(tmp_path)
    report = build_verified_fixture(config, tmp_path / "fixture.sqlite3")
    assert len(report["final_verification"]) == 3, "compact fixture needs three fresh confirmations"
    assert len(report["baseline_verification"]) == 3
    assert all(result["executed"] is True for result in report["final_verification"])


def test_accepted_reduction_has_two_charged_executions(tmp_path: Path) -> None:
    config = _case(tmp_path)
    report = build_verified_fixture(config, tmp_path / "fixture.sqlite3")
    assert report["accepted_reductions"], "the synthetic case must reach actual acceptance"
    expected = 6 + sum(
        sum(result["executed"] for result in attempt["confirmations"])
        for attempt in report["attempts"]
        if not attempt["cached"]
    )
    assert report["oracle_invocations"] == expected, (
        "each accepted pair needs two fresh charged executions, beyond baseline/final verification"
    )
    validate_report(report, config)


def _recorded_report(tmp_path: Path) -> tuple[dict, Config]:
    config = Config(
        tmp_path / "case.toml",
        tmp_path / "source.sqlite3",
        (),
        OracleSpec(("{python}", "oracle.py", "{db}"), 42, "TARGET", "stdout", 2.0, 4096),
        40,
    )

    def confirmation(target: bool = True) -> dict:
        return {
            "outcome": "TARGET_FAILURE" if target else "PASS",
            "reason": (
                "expected exit and exact failure marker"
                if target
                else "zero exit without target marker"
            ),
            "exit_code": 42 if target else 0,
            "output_bytes": 7 if target else 0,
            "duration_seconds": 0.01,
            "executed": True,
        }

    passed = {
        "number": 1,
        "retained_rows": 0,
        "removed_rows": 3,
        "outcome": "PASS",
        "reason": "zero exit without target marker",
        "cached": False,
        "confirmations": [confirmation(False)],
    }
    cached = deepcopy(passed)
    cached.update(number=3, removed_rows=2, cached=True)
    return {
        "version": 1,
        "verified": True,
        "original_counts": {"items": 3},
        "final_counts": {"items": 2},
        "oracle_invocations": 9,
        "unknown_interrupted_launches": 0,
        "budget_charged_invocations": 9,
        "interrupted_invocations": [],
        "max_invocations": 40,
        "baseline_verification": [confirmation() for _ in range(3)],
        "final_verification": [confirmation() for _ in range(3)],
        "attempts": [
            passed,
            {
                "number": 2,
                "retained_rows": 2,
                "removed_rows": 1,
                "outcome": "TARGET_FAILURE",
                "reason": "two_fresh_confirmations",
                "cached": False,
                "confirmations": [confirmation(), confirmation()],
            },
            cached,
        ],
        "accepted_reductions": [{"attempt": 2, "before": 3, "after": 2}],
        "cache_hits": 1,
        "unresolved_attempts": 0,
        "invalid_candidates": 0,
        "termination_reason": "single_row_closures_exhausted",
        "minimality": "No global minimality claim.",
    }, config


def test_reader_does_not_charge_cached_confirmation_again(tmp_path: Path) -> None:
    report, config = _recorded_report(tmp_path)
    try:
        validate_report(report, config)
    except ReportError as exc:
        raise AssertionError("cached historical PASS evidence is not a new execution") from exc


def test_reader_rejects_forged_count_chain(tmp_path: Path) -> None:
    report, config = _recorded_report(tmp_path)
    report["attempts"][0]["removed_rows"] = 4
    rejected = False
    try:
        validate_report(report, config)
    except ReportError as exc:
        rejected = "accepted reduction chain" in str(exc)
    assert rejected, "reader must reject a forged count chain even when confirmation records agree"


def test_materialization_interruption_cleans_private_output_and_preserves_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _case(tmp_path)
    model = DatabaseModel.from_database(config.source)
    before = sha256(config.source)
    destination = tmp_path / "interrupted.sqlite3"

    def interrupted(connection: sqlite3.Connection) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(sqlite_adapter, "_validate_connection", interrupted)
    with pytest.raises(KeyboardInterrupt):
        model.materialize(config.source, frozenset(), destination)
    assert not destination.exists()
    assert sha256(config.source) == before


def test_snapshot_output_failure_preserves_existing_private_path(tmp_path: Path) -> None:
    config = _case(tmp_path)
    destination = tmp_path / "existing.sqlite3"
    destination.write_bytes(b"owned synthetic sentinel")
    before = sha256(config.source)
    with pytest.raises(DatabaseError, match="overwrite"):
        sqlite_adapter.snapshot(config.source, destination)
    assert destination.read_bytes() == b"owned synthetic sentinel"
    assert sha256(config.source) == before
