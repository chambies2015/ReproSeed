"""Real SQLite TEXT identities, parent-driven relationships and rejection safety."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from reproseed.cli import main
from reproseed.diagnostics import diagnose, serialize_diagnosis
from reproseed.reducer import Evaluation, reduce_rows
from reproseed.sqlite_adapter import (
    DatabaseError,
    DatabaseModel,
    RowId,
    compact,
    snapshot,
    validate_database,
)


def _create(path: Path, script: str) -> Path:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(script)
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema(path: Path) -> list[tuple[str, str, str | None]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(
            "SELECT type, name, sql FROM sqlite_schema ORDER BY name"
        ).fetchall()


@pytest.mark.parametrize(
    "declaration,suffix",
    [
        ("id TEXT PRIMARY KEY", ""),
        ("id TEXT, PRIMARY KEY(id)", ""),
        ("id TEXT PRIMARY KEY NOT NULL", ""),
        ("id text PRIMARY KEY", ""),
        ('id " TeXt " PRIMARY KEY', ""),
        ("id TEXT COLLATE BINARY PRIMARY KEY", ""),
        ("id TEXT, PRIMARY KEY(id COLLATE BINARY DESC)", ""),
        ("id TEXT PRIMARY KEY", " STRICT"),
    ],
)
def test_text_primary_key_declarations_and_exact_key_values(
    tmp_path: Path, declaration: str, suffix: str
) -> None:
    source = _create(tmp_path / "text.sqlite3", f"CREATE TABLE items({declaration}){suffix}")
    keys = ["", "Item-A", "item-a", "'quoted\"", "雪-🙂", "nul\0key", "42"]
    with closing(sqlite3.connect(source)) as connection:
        connection.executemany("INSERT INTO items VALUES(?)", [(key,) for key in keys])
        connection.commit()
    before = _digest(source)
    private = tmp_path / "snapshot.sqlite3"
    snapshot(source, private)
    model = DatabaseModel.from_database(private)
    assert model.rows == tuple(("items", key) for key in sorted(keys))
    assert model.counts() == {"items": len(keys)}
    assert ("items", 42) not in model.rows
    assert ("items", "Item-A") in model.rows and ("items", "item-a") in model.rows
    selected = frozenset({("items", "Item-A"), ("items", "nul\0key"), ("items", "雪-🙂")})
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(private, selected, candidate)
    validate_database(candidate)
    assert frozenset(DatabaseModel.from_database(candidate).rows) == selected
    assert _schema(candidate) == _schema(source)
    assert _digest(source) == before


def test_empty_text_table_is_selected_from_metadata_and_can_be_compacted(tmp_path: Path) -> None:
    source = _create(
        tmp_path / "empty.sqlite3",
        "CREATE TABLE text_keys(id TEXT PRIMARY KEY);"
        "CREATE TABLE int_keys(id INTEGER PRIMARY KEY); INSERT INTO int_keys VALUES(-91),(800);",
    )
    model = DatabaseModel.from_database(source)
    assert model.rows == (("int_keys", -91), ("int_keys", 800))
    assert model.counts() == {"int_keys": 2, "text_keys": 0}
    private = tmp_path / "candidate.sqlite3"
    model.materialize(source, frozenset(), private)
    final = tmp_path / "compact.sqlite3"
    compact(private, final)
    assert DatabaseModel.from_database(final).counts() == {"int_keys": 0, "text_keys": 0}
    assert _schema(final) == _schema(source)


@pytest.fixture
def mixed_source(tmp_path: Path) -> Path:
    source = _create(
        tmp_path / "mixed.sqlite3",
        """
        PRAGMA user_version = 27;
        PRAGMA application_id = 8102;
        CREATE TABLE "accounts odd"("k""ey" TEXT PRIMARY KEY, label TEXT NOT NULL);
        CREATE TABLE owners(id INTEGER PRIMARY KEY, label TEXT NOT NULL);
        CREATE TABLE records(id TEXT PRIMARY KEY,
            account TEXT REFERENCES "accounts odd"("k""ey") ON DELETE SET NULL,
            owner INT REFERENCES owners(id) ON DELETE CASCADE,
            alternate TEXT REFERENCES "accounts odd"("k""ey"), payload BLOB);
        CREATE TABLE children(id INTEGER PRIMARY KEY,
            record TEXT REFERENCES records(id) ON DELETE SET NULL, label TEXT);
        CREATE INDEX record_payload ON records(payload);
        CREATE VIEW record_labels AS SELECT id FROM records;
        INSERT INTO "accounts odd" VALUES('Item-A', 'retained'), ('item-a', 'removed');
        INSERT INTO owners VALUES(-8, 'retained owner'), (910, 'removed owner');
        """,
    )
    with closing(sqlite3.connect(source)) as connection:
        connection.executemany(
            "INSERT INTO records VALUES(?, ?, ?, ?, ?)",
            [
                ("row\0keep", "Item-A", -8, None, b"\x00\xff retained"),
                ("row'remove", "item-a", 910, "item-a", b"removed"),
                ("nullable", None, None, None, b"nullable payload"),
            ],
        )
        connection.executemany(
            "INSERT INTO children VALUES(?, ?, ?)",
            [(27, "row\0keep", "retained child"), (901, "row'remove", "removed child")],
        )
        connection.commit()
    return source


def test_dependencies_use_the_referenced_parents_key_family(mixed_source: Path) -> None:
    model = DatabaseModel.from_database(mixed_source)
    retained = frozenset(model.rows)
    assert model.deletion_closure([("accounts odd", "item-a")], retained) == frozenset(
        {("accounts odd", "item-a"), ("records", "row'remove"), ("children", 901)}
    )
    assert model.deletion_closure([("owners", 910)], retained) == frozenset(
        {("owners", 910), ("records", "row'remove"), ("children", 901)}
    )
    assert model.deletion_closure([("accounts odd", "Item-A")], retained) == frozenset(
        {("accounts odd", "Item-A"), ("records", "row\0keep"), ("children", 27)}
    )
    assert model.deletion_closure([("records", "nullable")], retained) == frozenset(
        {("records", "nullable")}
    )


def test_mixed_materialization_and_compaction_preserve_all_retained_values(
    mixed_source: Path, tmp_path: Path
) -> None:
    before = _digest(mixed_source)
    model = DatabaseModel.from_database(mixed_source)
    removed = model.deletion_closure([("accounts odd", "item-a")], frozenset(model.rows))
    retained = frozenset(model.rows) - removed
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(mixed_source, retained, candidate)
    final = tmp_path / "compact.sqlite3"
    compact(candidate, final)
    validate_database(final)
    assert frozenset(DatabaseModel.from_database(final).rows) == retained
    assert _schema(final) == _schema(mixed_source)
    with closing(sqlite3.connect(final)) as connection:
        assert connection.execute("SELECT * FROM records ORDER BY id").fetchall() == [
            ("nullable", None, None, None, b"nullable payload"),
            ("row\0keep", "Item-A", -8, None, b"\x00\xff retained"),
        ]
        assert connection.execute("SELECT * FROM children").fetchall() == [
            (27, "row\0keep", "retained child")
        ]
        assert connection.execute("PRAGMA user_version").fetchone() == (27,)
        assert connection.execute("PRAGMA application_id").fetchone() == (8102,)
    # An oracle-mutated materialization cannot become the next candidate's source.
    with closing(sqlite3.connect(candidate)) as connection:
        connection.execute("UPDATE records SET payload = X'1234'")
        connection.commit()
    later = tmp_path / "later.sqlite3"
    model.materialize(mixed_source, retained, later)
    with closing(sqlite3.connect(later)) as connection:
        assert connection.execute(
            "SELECT payload FROM records WHERE id = ?", ("row\0keep",)
        ).fetchone() == (b"\x00\xff retained",)
    assert _digest(mixed_source) == before


def test_text_foreign_key_identifier_matching_is_ascii_only_and_target_may_be_implicit(
    tmp_path: Path,
) -> None:
    source = _create(
        tmp_path / "names.sqlite3",
        """
        CREATE TABLE Parent(ID TEXT PRIMARY KEY);
        CREATE TABLE Child(ID INTEGER PRIMARY KEY, Parent_ID TEXT REFERENCES pArEnT);
        CREATE TABLE "Ä"(id TEXT PRIMARY KEY);
        CREATE TABLE "ä"(id TEXT PRIMARY KEY, parent TEXT REFERENCES "Ä");
        INSERT INTO Parent VALUES('Exact-Key');
        INSERT INTO Child VALUES(700, 'Exact-Key');
        INSERT INTO "Ä" VALUES('42');
        INSERT INTO "ä" VALUES('42', '42');
        """,
    )
    model = DatabaseModel.from_database(source)
    selected = frozenset(model.rows)
    assert model.deletion_closure([("Parent", "Exact-Key")], selected) == frozenset(
        {("Parent", "Exact-Key"), ("Child", 700)}
    )
    assert model.deletion_closure([("Ä", "42")], selected) == frozenset({("Ä", "42"), ("ä", "42")})
    assert model.deletion_closure([("ä", "42")], selected) == frozenset({("ä", "42")})


def test_text_fk_matching_uses_binary_parent_even_when_child_column_uses_nocase(
    tmp_path: Path,
) -> None:
    source = _create(
        tmp_path / "child-collation.sqlite3",
        "CREATE TABLE parents(id TEXT PRIMARY KEY);"
        "CREATE TABLE children(id INTEGER PRIMARY KEY,"
        "parent TEXT COLLATE NOCASE REFERENCES parents(id));"
        "INSERT INTO parents VALUES('Item-A'),('item-a');"
        "INSERT INTO children VALUES(1,'Item-A'),(2,'item-a');",
    )
    model = DatabaseModel.from_database(source)
    rows = frozenset(model.rows)
    assert model.deletion_closure([("parents", "Item-A")], rows) == frozenset(
        {("parents", "Item-A"), ("children", 1)}
    )
    assert model.deletion_closure([("parents", "item-a")], rows) == frozenset(
        {("parents", "item-a"), ("children", 2)}
    )


def test_text_keys_and_database_encoding_survive_compaction(tmp_path: Path) -> None:
    source = _create(
        tmp_path / "utf16.sqlite3",
        "PRAGMA encoding='UTF-16'; PRAGMA page_size=8192;"
        "CREATE TABLE items(id TEXT PRIMARY KEY, value TEXT NOT NULL);"
        "INSERT INTO items VALUES('雪-🙂','retained'),('remove','removed');",
    )
    before = _digest(source)
    model = DatabaseModel.from_database(source)
    candidate = tmp_path / "candidate.sqlite3"
    selected = frozenset({("items", "雪-🙂")})
    model.materialize(source, selected, candidate)
    final = tmp_path / "final.sqlite3"
    compact(candidate, final)
    assert DatabaseModel.from_database(final).rows == (("items", "雪-🙂"),)
    with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(final)) as result:
        assert result.execute("SELECT * FROM items").fetchall() == [("雪-🙂", "retained")]
        for pragma in ("encoding", "page_size"):
            assert (
                result.execute(f"PRAGMA {pragma}").fetchone()
                == original.execute(f"PRAGMA {pragma}").fetchone()
            )
    assert _digest(source) == before


def test_mixed_cycles_self_references_and_normalized_candidate_cache(tmp_path: Path) -> None:
    source = _create(
        tmp_path / "cycles.sqlite3",
        "CREATE TABLE text_nodes(id TEXT PRIMARY KEY, peer TEXT REFERENCES text_nodes(id),"
        "number INTEGER REFERENCES numbers(id));"
        "CREATE TABLE numbers(id INTEGER PRIMARY KEY, text_node TEXT REFERENCES text_nodes(id));"
        "INSERT INTO text_nodes VALUES('A','A',42),('a',NULL,NULL),('42',NULL,NULL);"
        "INSERT INTO numbers VALUES(42,'A'),(900,NULL);",
    )
    model = DatabaseModel.from_database(source)
    rows = frozenset(model.rows)
    assert model.deletion_closure([("text_nodes", "A")], rows) == frozenset(
        {("text_nodes", "A"), ("numbers", 42)}
    )
    calls: list[frozenset[RowId]] = []

    def evaluate(retained: frozenset[RowId]) -> Evaluation:
        calls.append(retained)
        candidate = tmp_path / f"trial-{len(calls)}.sqlite3"
        model.materialize(source, retained, candidate)
        assert frozenset(DatabaseModel.from_database(candidate).rows) == retained
        return Evaluation("TARGET_FAILURE" if ("text_nodes", "A") in retained else "PASS")

    first = reduce_rows(model, evaluate)
    first_calls = calls.copy()
    calls.clear()
    # Fresh trial paths make the second deterministic run independent of its predecessor.
    for path in tmp_path.glob("trial-*.sqlite3"):
        path.unlink()
    second = reduce_rows(model, evaluate)
    assert first == second
    assert calls == first_calls
    assert len(calls) == len(set(calls))
    assert first.retained == frozenset({("text_nodes", "A"), ("numbers", 42)})
    assert first.cache_hits > 0
    assert all(attempt["before"] > attempt["after"] for attempt in first.accepted)


def test_unknown_text_identity_is_not_coerced_or_case_folded(tmp_path: Path) -> None:
    source = _create(
        tmp_path / "identity.sqlite3",
        "CREATE TABLE items(id TEXT PRIMARY KEY); INSERT INTO items VALUES('42'),('Item-A');",
    )
    model = DatabaseModel.from_database(source)
    for unknown in (("items", 42), ("items", "item-a")):
        with pytest.raises(DatabaseError, match="identities"):
            model.materialize(source, frozenset({unknown}), tmp_path / "unknown.sqlite3")
        assert not (tmp_path / "unknown.sqlite3").exists()


UNSUPPORTED_SCHEMAS = [
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY); INSERT INTO private_items VALUES(NULL);",
        "unsupported_null_text_primary_key",
        id="null-text-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY COLLATE NOCASE)",
        "unsupported_text_key_collation",
        id="nocase-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT COLLATE RTRIM, PRIMARY KEY(id))",
        "unsupported_text_key_collation",
        id="rtrim-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT COLLATE NOCASE, PRIMARY KEY(id COLLATE BINARY))",
        "unsupported_text_key_collation",
        id="nocase-column-binary-index-empty",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT COLLATE NOCASE, PRIMARY KEY(id COLLATE BINARY));"
        "INSERT INTO private_items VALUES('PRIVATE-KEY'),('private-key');",
        "unsupported_text_key_collation",
        id="nocase-column-binary-index-populated",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY);"
        "INSERT INTO private_items VALUES(X'505249564154452d4b4559');",
        "unsupported_primary_key_value",
        id="blob-text-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(id VARCHAR PRIMARY KEY)",
        "unsupported_primary_key",
        id="varchar-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(id CHAR PRIMARY KEY)",
        "unsupported_primary_key",
        id="char-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(id BLOB PRIMARY KEY)",
        "unsupported_primary_key",
        id="blob-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(id REAL PRIMARY KEY)",
        "unsupported_primary_key",
        id="real-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b TEXT,c TEXT,PRIMARY KEY(a,b,c))",
        "unsupported_composite_primary_key_arity",
        id="three-column-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY COLLATE NOCASE) WITHOUT ROWID",
        "unsupported_text_key_collation",
        id="without-rowid-nocase",
    ),
    pytest.param("CREATE TABLE private_items(id TEXT)", "unsupported_primary_key", id="missing-pk"),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY, derived TEXT GENERATED ALWAYS AS(id))",
        "unsupported_generated_column",
        id="generated-column",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY);"
        "CREATE TRIGGER private_trigger AFTER DELETE ON private_items BEGIN SELECT 1; END;",
        "unsupported_trigger",
        id="trigger",
    ),
    pytest.param(
        "CREATE VIRTUAL TABLE private_items USING fts5(value)",
        None,
        id="virtual-table",
    ),
    pytest.param(
        "CREATE TABLE parent(id TEXT PRIMARY KEY,other TEXT UNIQUE);"
        "CREATE TABLE private_items(id TEXT PRIMARY KEY,parent TEXT REFERENCES parent(other))",
        "unsupported_foreign_key_target",
        id="unique-fk-target",
    ),
    pytest.param(
        "CREATE TABLE parent(id TEXT PRIMARY KEY,other TEXT,UNIQUE(id,other));"
        "CREATE TABLE private_items(id TEXT PRIMARY KEY,a TEXT,b TEXT,"
        "FOREIGN KEY(a,b) REFERENCES parent(id,other))",
        "unsupported_foreign_key_target",
        id="composite-fk-to-non-primary-unique-columns",
    ),
    pytest.param(
        "CREATE TABLE parent(id TEXT PRIMARY KEY COLLATE NOCASE);"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,parent TEXT REFERENCES parent(id))",
        "unsupported_text_key_collation",
        id="unsupported-parent-collation",
    ),
    pytest.param(
        "CREATE TABLE parent(id TEXT PRIMARY KEY);"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,parent INTEGER REFERENCES parent(id));"
        "INSERT INTO parent VALUES('42'); INSERT INTO private_items VALUES(1,42);",
        "unsupported_foreign_key_type",
        id="integer-fk-to-text-parent",
    ),
    pytest.param(
        "CREATE TABLE parent(id INTEGER PRIMARY KEY);"
        "CREATE TABLE private_items(id TEXT PRIMARY KEY,parent TEXT REFERENCES parent(id));"
        "INSERT INTO parent VALUES(42); INSERT INTO private_items VALUES('private-key','42');",
        "unsupported_foreign_key_type",
        id="text-fk-to-integer-parent",
    ),
    pytest.param(
        "CREATE TABLE parent(id TEXT PRIMARY KEY);"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,parent VARCHAR REFERENCES parent(id))",
        "unsupported_foreign_key_type",
        id="varchar-fk",
    ),
    pytest.param(
        "CREATE TABLE parent(id TEXT PRIMARY KEY);"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,parent TEXT REFERENCES parent(id));"
        "INSERT INTO parent VALUES('PRIVATE-KEY');"
        "INSERT INTO private_items VALUES(1,X'505249564154452d4b4559');",
        "unsupported_foreign_key_value",
        id="blob-text-fk",
    ),
]


def _config(root: Path, source: Path, sentinel: Path) -> Path:
    oracle = root / "oracle.py"
    oracle.write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('launched')\n"
        "print('PRIVATE_ORACLE_MARKER'); raise SystemExit(42)\n",
        encoding="utf-8",
    )
    config = root / "case.toml"
    config.write_text(
        f'version=1\nsource="{source.name}"\ninclude=["oracle.py"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="PRIVATE_ORACLE_MARKER"\nstream="stdout"\ntimeout_seconds=2.0\n'
        "output_limit_bytes=4096\n[reduction]\nmax_invocations=12\n",
        encoding="utf-8",
    )
    return config


def _assert_rejection_safety(
    root: Path,
    source: Path,
    reason: str | tuple[str, ...] | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = _digest(source)
    with pytest.raises(DatabaseError):
        DatabaseModel.from_database(source)
    sentinel = root / "must-not-launch"
    config = _config(root, source, sentinel)
    assets_before = _digest(root / "oracle.py")

    def unexpected(*args: object) -> None:
        pytest.fail("unsupported schemas must reject before any oracle launch")

    monkeypatch.setattr("reproseed.workflow.run_oracle", unexpected)
    for allow_exec in (False, True):
        diagnosis = diagnose(config, allow_exec=allow_exec)
        assert diagnosis.exit_code == 2
        assert diagnosis.error is not None
        if reason is not None:
            expected = (reason,) if isinstance(reason, str) else reason
            assert diagnosis.error.reason in expected
        assert diagnosis.schema_supported is (
            None if diagnosis.error.reason == "integrity_failure" else False
        )
        assert diagnosis.structurally_suitable is False
        assert diagnosis.actual_invocations == 0
        assert diagnosis.oracle_executed is False
        serialized = serialize_diagnosis(diagnosis)
        assert json.loads(serialized)["diagnostic_version"] == 1
        for private in (str(root), "private_items", "PRIVATE-KEY", "PRIVATE_ORACLE_MARKER"):
            assert private not in serialized
    bundle = root / "must-not-publish"
    assert main(["reduce", "--config", str(config), "--out", str(bundle), "--allow-exec"]) == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert not bundle.exists()
    assert not sentinel.exists()
    assert _digest(source) == before
    assert _digest(root / "oracle.py") == assets_before


@pytest.mark.parametrize("schema,reason", UNSUPPORTED_SCHEMAS)
def test_unsupported_text_key_shapes_never_execute_or_modify_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    schema: str,
    reason: str | None,
) -> None:
    source = _create(tmp_path / "unsupported.sqlite3", schema)
    _assert_rejection_safety(tmp_path, source, reason, monkeypatch, capsys)


def test_custom_primary_key_collation_rejects_empty_source_without_uncaught_sqlite_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "custom.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.create_collation(
            "private_custom", lambda left, right: (left > right) - (left < right)
        )
        connection.executescript(
            "CREATE TABLE private_items(id TEXT PRIMARY KEY COLLATE private_custom)"
        )
    _assert_rejection_safety(
        tmp_path, source, "unsupported_unavailable_collation", monkeypatch, capsys
    )
    diagnosis = diagnose(tmp_path / "case.toml")
    assert diagnosis.integrity_valid is None
    assert diagnosis.foreign_keys_valid is None


@pytest.mark.parametrize("value", ["42", "42.5"])
def test_nontext_stored_fk_is_rejected_when_sqlite_parent_affinity_accepts_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    # Model a legacy type migration: SQLite parent TEXT affinity considers 42 equal to '42'.
    # The snapshot's declaration is supported, but its stored child value is not TEXT.
    source = _create(
        tmp_path / "legacy.sqlite3",
        "CREATE TABLE parent(id TEXT PRIMARY KEY);"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,parent BLOB REFERENCES parent(id));"
        f"INSERT INTO parent VALUES('{value}'); INSERT INTO private_items VALUES(1,{value});"
        "PRAGMA writable_schema=ON;"
        "UPDATE sqlite_schema SET sql=replace(sql,'parent BLOB','parent TEXT')"
        "WHERE name='private_items';",
    )
    # Newer SQLite rejects this migrated numeric storage during integrity_check; older
    # SQLite permits structural validation and reaches the explicit TEXT storage check.
    _assert_rejection_safety(
        tmp_path,
        source,
        ("unsupported_foreign_key_value", "integrity_failure"),
        monkeypatch,
        capsys,
    )


@pytest.mark.parametrize("value", ["42", "42.5"])
def test_nontext_stored_pk_is_rejected_without_coercion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    source = _create(
        tmp_path / "legacy-pk.sqlite3",
        "CREATE TABLE private_items(id BLOB PRIMARY KEY);"
        f"INSERT INTO private_items VALUES({value});"
        "PRAGMA writable_schema=ON;"
        "UPDATE sqlite_schema SET sql=replace(sql,'id BLOB','id TEXT') WHERE name='private_items';",
    )
    _assert_rejection_safety(
        tmp_path,
        source,
        ("unsupported_primary_key_value", "integrity_failure"),
        monkeypatch,
        capsys,
    )


def test_malformed_utf8_text_primary_key_has_curated_error_and_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _create(
        tmp_path / "encoding.sqlite3",
        "CREATE TABLE private_items(id TEXT PRIMARY KEY);"
        "INSERT INTO private_items VALUES(CAST(X'80ff' AS TEXT));",
    )
    validate_database(source)
    _assert_rejection_safety(tmp_path, source, "unsupported_text_encoding", monkeypatch, capsys)


def test_malformed_utf8_text_foreign_key_has_curated_error_before_fk_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _create(
        tmp_path / "fk-encoding.sqlite3",
        "CREATE TABLE parent(id TEXT PRIMARY KEY);"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,parent TEXT REFERENCES parent(id));"
        "INSERT INTO parent VALUES('private-key');"
        "INSERT INTO private_items VALUES(1,CAST(X'80ff' AS TEXT));",
    )
    _assert_rejection_safety(tmp_path, source, "unsupported_text_encoding", monkeypatch, capsys)


def test_valid_text_shape_static_diagnosis_uses_the_same_model_and_no_oracle(
    mixed_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _digest(mixed_source)
    config = _config(tmp_path, mixed_source, tmp_path / "sentinel")

    def unexpected(*args: object) -> None:
        pytest.fail("static diagnosis cannot launch the oracle")

    monkeypatch.setattr("reproseed.workflow.run_oracle", unexpected)
    diagnosis = diagnose(config)
    assert diagnosis.exit_code == 0
    assert diagnosis.schema_supported is True
    assert diagnosis.structurally_suitable is True
    assert diagnosis.table_counts == DatabaseModel.from_database(mixed_source).counts()
    assert diagnosis.actual_invocations == 0
    assert diagnosis.baseline_confirmed is False
    assert diagnosis.oracle_executed is False
    assert _digest(mixed_source) == before
