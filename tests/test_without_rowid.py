"""Bounded WITHOUT ROWID identities, mixed-layout relationships and execution safety."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

import pytest

from reproseed.cli import main
from reproseed.diagnostics import diagnose, serialize_diagnosis
from reproseed.reducer import Evaluation, reduce_rows
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel, RowId, compact, validate_database


def _create(path: Path, schema: str) -> Path:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(schema)
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _state(path: Path) -> tuple[list[tuple[object, ...]], dict[str, set[tuple[object, ...]]]]:
    with closing(sqlite3.connect(path)) as connection:
        schema = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
        ).fetchall()
        values = {
            row[1]: set(connection.execute(f"SELECT * FROM {_quote(row[1])}"))
            for row in schema
            if row[0] == "table" and not row[1].startswith("sqlite_")
        }
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    return schema, values


FAMILIES = [
    ("INTEGER",),
    ("TEXT",),
    ("INTEGER", "INTEGER"),
    ("INTEGER", "TEXT"),
    ("TEXT", "INTEGER"),
    ("TEXT", "TEXT"),
]


@pytest.mark.parametrize("families", FAMILIES)
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_supported_declared_keys_and_auxiliary_pk_storage_preserve_exact_values(
    tmp_path: Path, families: tuple[str, ...], strict: bool, empty: bool
) -> None:
    table_name = 'items "odd'
    first_name = 'key "first'
    second_name = "key second"
    first = _quote(first_name)
    second = _quote(second_name)
    table = _quote(table_name)
    # The key order deliberately differs from the physical column order.
    columns = f"payload BLOB,{first} {families[0]},note TEXT"
    if len(families) == 2:
        columns = f"{second} {families[1]}," + columns
    keys = first if len(families) == 1 else f"{first},{second}"
    suffix = " WITHOUT ROWID, STRICT" if strict else " WITHOUT ROWID"
    source = _create(
        tmp_path / "source.sqlite3",
        "PRAGMA encoding='UTF-16'; PRAGMA page_size=8192;"
        "PRAGMA user_version=731; PRAGMA application_id=9917;"
        f"CREATE TABLE {table}({columns},PRIMARY KEY({keys})){suffix};"
        f"CREATE INDEX extra_payload ON {table}(payload);"
        f"CREATE UNIQUE INDEX extra_note ON {table}(note);",
    )
    integers = [-9001, -8, 0, 42, 100009]
    texts = ["", "Item-A", "item-a", "42", "雪-🙂", "nul\0key", "'quote\"; DELETE"]
    component_values = [integers if family == "INTEGER" else texts for family in families]
    key_values = (
        [(key,) for key in component_values[0]]
        if len(families) == 1
        else [(a, b) for a in component_values[0] for b in component_values[1]]
    )
    with closing(sqlite3.connect(source)) as connection:
        if not empty:
            connection.executemany(
                f"INSERT INTO {table}({keys},payload,note) VALUES("
                + ",".join("?" for _ in range(len(families) + 2))
                + ")",
                [(*values, b"\0\xff unchanged payload", None) for values in reversed(key_values)],
            )
            connection.commit()
        primary_index = next(
            index for index in connection.execute(f"PRAGMA index_list({table})") if index[3] == "pk"
        )
        index_columns = connection.execute(
            f"PRAGMA index_xinfo({_quote(primary_index[1])})"
        ).fetchall()
        assert sum(column[5] == 1 for column in index_columns) == len(families)
        # WITHOUT ROWID indexes store ordinary table columns as auxiliary entries.
        assert any(column[5] == 0 and column[2] == "payload" for column in index_columns)
        assert [column[2] for column in index_columns if column[5] == 1] == (
            [first_name] if len(families) == 1 else [first_name, second_name]
        )
        with pytest.raises(sqlite3.OperationalError, match="no such column"):
            connection.execute(f"SELECT rowid FROM {table}")
    before = _digest(source)
    original_state = _state(source)
    model = DatabaseModel.from_database(source)
    expected_keys = (
        [] if empty else [values[0] if len(values) == 1 else values for values in key_values]
    )
    assert model.rows == tuple((table_name, key) for key in sorted(expected_keys))
    assert model.counts() == {table_name: len(expected_keys)}
    assert model._tables[0].without_rowid is True
    assert model._tables[0].primary_keys == (
        (first_name,) if len(families) == 1 else (first_name, second_name)
    )
    retained = frozenset() if empty else frozenset({model.rows[0], model.rows[-1]})
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(source, retained, candidate)
    final = tmp_path / "compact.sqlite3"
    compact(candidate, final)
    for path in (candidate, final):
        validate_database(path)
        assert frozenset(DatabaseModel.from_database(path).rows) == retained
        schema, values = _state(path)
        assert schema == original_state[0]
        assert values[table_name] <= original_state[1][table_name]
        assert len(values[table_name]) == len(retained)
        with closing(sqlite3.connect(path)) as result, closing(sqlite3.connect(source)) as original:
            assert next(
                row[4] for row in result.execute("PRAGMA table_list") if row[1] == table_name
            )
            for pragma in ("encoding", "page_size", "user_version", "application_id"):
                assert (
                    result.execute(f"PRAGMA {pragma}").fetchone()
                    == original.execute(f"PRAGMA {pragma}").fetchone()
                )
    assert _digest(source) == before


def test_integer_primary_key_storage_layout_is_distinct_without_changing_identity(
    tmp_path: Path,
) -> None:
    source = _create(
        tmp_path / "integer.sqlite3",
        "CREATE TABLE ordinary(id INTEGER PRIMARY KEY,payload TEXT);"
        "CREATE TABLE clustered(id INTEGER PRIMARY KEY,payload TEXT) WITHOUT ROWID;"
        "INSERT INTO ordinary VALUES(-8,'same'),(91000,NULL);"
        "INSERT INTO clustered VALUES(-8,'same'),(91000,NULL);",
    )
    model = DatabaseModel.from_database(source)
    assert model.rows == (
        ("clustered", -8),
        ("clustered", 91000),
        ("ordinary", -8),
        ("ordinary", 91000),
    )
    assert {table.name: table.without_rowid for table in model._tables} == {
        "clustered": True,
        "ordinary": False,
    }
    with closing(sqlite3.connect(source)) as connection:
        assert connection.execute("PRAGMA index_list(ordinary)").fetchall() == []
        assert connection.execute("PRAGMA index_list(clustered)").fetchone()[3] == "pk"
        assert connection.execute("SELECT rowid,id FROM ordinary ORDER BY id").fetchall() == [
            (-8, -8),
            (91000, 91000),
        ]


@pytest.mark.parametrize("families", FAMILIES)
@pytest.mark.parametrize("explicit_target", [False, True])
def test_without_rowid_foreign_keys_follow_every_declared_parent_key_family(
    tmp_path: Path, families: tuple[str, ...], explicit_target: bool
) -> None:
    names = ("a",) if len(families) == 1 else ("a", "b")
    parent_columns = ",".join(
        f"{name} {family}" for name, family in zip(names, families, strict=True)
    )
    key_columns = ",".join(names)
    target = f"parent({key_columns})" if explicit_target else "parent"
    source = _create(
        tmp_path / "families.sqlite3",
        f"CREATE TABLE parent({parent_columns},PRIMARY KEY({key_columns})) WITHOUT ROWID;"
        f"CREATE TABLE children(id TEXT PRIMARY KEY,{parent_columns},"
        f"FOREIGN KEY({key_columns}) REFERENCES {target}) WITHOUT ROWID;",
    )
    key = tuple(-91 if family == "INTEGER" else "雪-🙂" for family in families)
    alternate = tuple(100009 if family == "INTEGER" else "" for family in families)
    other_first = (alternate[0], *key[1:])
    parent_keys = [key, other_first]
    child_values = [("exact", *key), ("other-first", *other_first), ("null-first", None, *key[1:])]
    if len(families) == 2:
        parent_keys.append((key[0], alternate[1]))
        child_values.extend([("other-second", key[0], alternate[1]), ("null-second", key[0], None)])
    with closing(sqlite3.connect(source)) as connection:
        connection.executemany(
            "INSERT INTO parent VALUES(" + ",".join("?" for _ in names) + ")", parent_keys
        )
        connection.executemany(
            "INSERT INTO children VALUES(" + ",".join("?" for _ in range(len(names) + 1)) + ")",
            child_values,
        )
        connection.commit()
        direct = connection.execute(
            "SELECT children.id FROM children JOIN parent ON "
            + " AND ".join(f"children.{name}=parent.{name} COLLATE BINARY" for name in names)
            + " WHERE "
            + " AND ".join(f"parent.{name}=?" for name in names),
            key,
        ).fetchall()
    assert direct == [("exact",)]
    before = _digest(source)
    model = DatabaseModel.from_database(source)
    rows = frozenset(model.rows)
    parent_identity = ("parent", key[0] if len(key) == 1 else key)
    removed = model.deletion_closure([parent_identity], rows)
    assert removed == frozenset({parent_identity, ("children", "exact")})
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(source, rows - removed, candidate)
    validate_database(candidate)
    assert frozenset(DatabaseModel.from_database(candidate).rows) == rows - removed
    assert _digest(source) == before


@pytest.fixture
def mixed_source(tmp_path: Path) -> Path:
    return _create(
        tmp_path / "mixed.sqlite3",
        """
        PRAGMA user_version=71;
        PRAGMA application_id=8819;
        CREATE TABLE tenants(id TEXT PRIMARY KEY) WITHOUT ROWID;
        CREATE TABLE owners(id INTEGER PRIMARY KEY);
        CREATE TABLE invoices(number INTEGER,tenant TEXT REFERENCES tenants(id),
            owner INT REFERENCES owners,payload BLOB,PRIMARY KEY(tenant,number)) WITHOUT ROWID;
        CREATE TABLE plans(tenant TEXT,name TEXT,PRIMARY KEY(tenant,name)) WITHOUT ROWID;
        CREATE TABLE payments(id INTEGER PRIMARY KEY,tenant TEXT,number INT,
            plan_tenant TEXT,plan_name TEXT,payload BLOB,
            FOREIGN KEY(tenant,number) REFERENCES invoices ON DELETE SET NULL,
            FOREIGN KEY(plan_tenant,plan_name) REFERENCES plans(tenant,name) ON DELETE CASCADE);
        CREATE TABLE events(id INTEGER PRIMARY KEY,tenant TEXT,number INT,owner INT,
            FOREIGN KEY(tenant,number) REFERENCES invoices(tenant,number),
            FOREIGN KEY(owner) REFERENCES owners(id)) WITHOUT ROWID;
        CREATE TABLE lines(tenant TEXT,line INTEGER,number INTEGER,payment INT,
            PRIMARY KEY(tenant,line),FOREIGN KEY(tenant,number) REFERENCES invoices,
            FOREIGN KEY(payment) REFERENCES payments(id)) WITHOUT ROWID;
        CREATE TABLE links(id TEXT PRIMARY KEY,tenant TEXT,number INT,other_tenant TEXT,
            other_number INT,FOREIGN KEY(tenant,number) REFERENCES invoices,
            FOREIGN KEY(other_tenant,other_number) REFERENCES invoices) WITHOUT ROWID;
        CREATE TABLE receipts(id TEXT PRIMARY KEY,event INT REFERENCES events(id)) WITHOUT ROWID;
        CREATE INDEX invoices_payload ON invoices(payload);
        CREATE VIEW labels AS SELECT tenant,number FROM invoices;
        INSERT INTO tenants VALUES('a'),('b');
        INSERT INTO owners VALUES(-8),(910);
        INSERT INTO invoices VALUES(42,'a',-8,X'00ff'),(42,'b',910,X'0102'),(43,'a',-8,X'0304');
        INSERT INTO plans VALUES('a','basic'),('b','basic');
        INSERT INTO payments VALUES(1,'a',42,'a','basic',X'00ff'),
            (2,'b',42,'b','basic',X'0102'),(3,'a',43,NULL,NULL,X'0304'),
            (4,NULL,NULL,NULL,NULL,X'04'),(5,NULL,42,NULL,NULL,X'05'),
            (6,'a',NULL,NULL,NULL,X'06');
        INSERT INTO events VALUES(701,'a',42,-8),(702,'b',42,910),
            (703,'a',43,-8),(704,NULL,42,NULL);
        INSERT INTO lines VALUES('a',8,42,1),('b',8,42,2),('a',9,43,3);
        INSERT INTO links VALUES('both','a',42,'b',42),('alternate','a',43,'a',42);
        INSERT INTO receipts VALUES('a-receipt',701),('b-receipt',702);
        """,
    )


def test_mixed_layout_grouped_fks_remove_exact_descendants_and_preserve_null_references(
    mixed_source: Path, tmp_path: Path
) -> None:
    before = _digest(mixed_source)
    original = _state(mixed_source)
    model = DatabaseModel.from_database(mixed_source)
    rows = frozenset(model.rows)
    removed = frozenset(
        {
            ("invoices", ("a", 42)),
            ("payments", 1),
            ("events", 701),
            ("lines", ("a", 8)),
            ("links", "both"),
            ("links", "alternate"),
            ("receipts", "a-receipt"),
        }
    )
    assert model.deletion_closure([("invoices", ("a", 42))], rows) == removed
    assert model.deletion_closure([("plans", ("a", "basic"))], rows) == frozenset(
        {("plans", ("a", "basic")), ("payments", 1), ("lines", ("a", 8))}
    )
    assert model.deletion_closure([("tenants", "b")], rows) == frozenset(
        {
            ("tenants", "b"),
            ("invoices", ("b", 42)),
            ("payments", 2),
            ("events", 702),
            ("lines", ("b", 8)),
            ("links", "both"),
            ("receipts", "b-receipt"),
        }
    )
    assert model.deletion_closure([("owners", 910)], rows) == (
        model.deletion_closure([("tenants", "b")], rows) - {("tenants", "b")}
    ) | {("owners", 910)}
    for key in (4, 5, 6):
        assert model.deletion_closure([("payments", key)], rows) == frozenset({("payments", key)})
    assert model.deletion_closure([("events", 704)], rows) == frozenset({("events", 704)})
    with closing(sqlite3.connect(mixed_source)) as connection:
        # Independent SQLite joins compare the complete declared tuple.
        for table, key_column, expected in (("payments", "id", [1]), ("events", "id", [701])):
            actual = connection.execute(
                f"SELECT c.{key_column} FROM {table} c JOIN invoices p "
                "ON c.tenant=p.tenant COLLATE BINARY AND c.number=p.number "
                "WHERE p.tenant=? AND p.number=?",
                ("a", 42),
            ).fetchall()
            assert actual == [(key,) for key in expected]
    selected = rows - removed
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(mixed_source, selected, candidate)
    final = tmp_path / "compact.sqlite3"
    compact(candidate, final)
    for path in (candidate, final):
        schema, values = _state(path)
        assert schema == original[0]
        assert frozenset(DatabaseModel.from_database(path).rows) == selected
        for table, retained in values.items():
            assert retained <= original[1][table]
            assert len(retained) == model.counts(selected)[table]
        assert values["payments"] == {
            (2, "b", 42, "b", "basic", b"\x01\x02"),
            (3, "a", 43, None, None, b"\x03\x04"),
            (4, None, None, None, None, b"\x04"),
            (5, None, 42, None, None, b"\x05"),
            (6, "a", None, None, None, b"\x06"),
        }
    with closing(sqlite3.connect(candidate)) as connection:
        connection.execute("UPDATE invoices SET payload=X'ffee'")
        connection.commit()
    fresh = tmp_path / "fresh.sqlite3"
    model.materialize(mixed_source, selected, fresh)
    assert _state(fresh) == _state(final)
    assert _digest(mixed_source) == before


def test_mixed_layout_cycles_self_references_and_normalized_reduction_cache(tmp_path: Path) -> None:
    source = _create(
        tmp_path / "cycles.sqlite3",
        "CREATE TABLE nodes(a TEXT,b INTEGER,peer_a TEXT,peer_b INT,PRIMARY KEY(a,b),"
        "FOREIGN KEY(peer_a,peer_b) REFERENCES nodes) WITHOUT ROWID;"
        "CREATE TABLE lefts(id TEXT PRIMARY KEY,right_id INT REFERENCES rights) WITHOUT ROWID;"
        "CREATE TABLE rights(id INTEGER PRIMARY KEY,left_id TEXT REFERENCES lefts);"
        "CREATE TABLE descendants(id INTEGER PRIMARY KEY,left_id TEXT REFERENCES lefts)"
        " WITHOUT ROWID;"
        "INSERT INTO nodes VALUES('a',42,'b',42),('b',42,'a',42),"
        "('self',-8,'self',-8),('partial',91,NULL,42),('decoy',91,NULL,NULL);"
        "INSERT INTO lefts VALUES('cycle',900),('decoy',NULL);"
        "INSERT INTO rights VALUES(900,'cycle'),(-8,NULL);"
        "INSERT INTO descendants VALUES(91000,'cycle'),(-8,NULL);",
    )
    before = _digest(source)
    model = DatabaseModel.from_database(source)
    rows = frozenset(model.rows)
    essential = frozenset({("lefts", "cycle"), ("rights", 900), ("descendants", 91000)})
    assert model.deletion_closure([("lefts", "cycle")], rows) == essential
    assert model.deletion_closure([("rights", 900)], rows) == essential
    assert model.deletion_closure([("nodes", ("a", 42))], rows) == frozenset(
        {("nodes", ("a", 42)), ("nodes", ("b", 42))}
    )
    assert model.deletion_closure([("nodes", ("self", -8))], rows) == frozenset(
        {("nodes", ("self", -8))}
    )
    calls: list[frozenset[RowId]] = []

    def evaluate(selected: frozenset[RowId]) -> Evaluation:
        calls.append(selected)
        candidate = tmp_path / f"trial-{len(calls)}.sqlite3"
        model.materialize(source, selected, candidate)
        validate_database(candidate)
        return Evaluation("TARGET_FAILURE" if essential <= selected else "PASS")

    result = reduce_rows(model, evaluate)
    assert result.retained == essential
    assert len(calls) == len(set(calls))
    assert result.cache_hits > 0
    assert _digest(source) == before


@pytest.mark.parametrize(
    "sql,exception,match",
    [
        ("CREATE TABLE t(value TEXT) WITHOUT ROWID", sqlite3.OperationalError, "PRIMARY KEY"),
        (
            "CREATE TABLE t(id INTEGER PRIMARY KEY AUTOINCREMENT) WITHOUT ROWID",
            sqlite3.OperationalError,
            "AUTOINCREMENT",
        ),
        (
            "CREATE TABLE t(id INTEGER PRIMARY KEY) WITHOUT ROWID; INSERT INTO t VALUES(NULL)",
            sqlite3.IntegrityError,
            "NOT NULL",
        ),
        (
            "CREATE TABLE t(a TEXT,b INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;"
            "INSERT INTO t VALUES('key',NULL)",
            sqlite3.IntegrityError,
            "NOT NULL",
        ),
    ],
)
def test_sqlite_itself_rejects_illegal_without_rowid_schemas_and_null_keys(
    tmp_path: Path, sql: str, exception: type[Exception], match: str
) -> None:
    # These fail at engine creation/insertion, before a ReproSeed model exists.
    with closing(sqlite3.connect(tmp_path / "engine.sqlite3")) as connection:
        with pytest.raises(exception, match=match):
            connection.executescript(sql)


def _config(root: Path, source: Path, program: str | None = None) -> Path:
    sentinel = root / "must-not-launch"
    (root / "oracle.py").write_text(
        program
        or "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('launched')\n"
        "print('PRIVATE_ORACLE_MARKER'); raise SystemExit(42)\n",
        encoding="utf-8",
    )
    config = root / "case.toml"
    config.write_text(
        f'version=1\nsource="{source.name}"\ninclude=["oracle.py"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="PRIVATE_ORACLE_MARKER"\nstream="stdout"\ntimeout_seconds=3.0\n'
        "output_limit_bytes=4096\n[reduction]\nmax_invocations=80\n",
        encoding="utf-8",
    )
    return config


def _reject_safely(
    tmp_path: Path,
    source: Path,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = _digest(source)
    with pytest.raises(DatabaseError) as failure:
        DatabaseModel.from_database(source)
    assert "PRIVATE-KEY" not in str(failure.value)
    config = _config(tmp_path, source)
    assets_before = _digest(tmp_path / "oracle.py")

    def unexpected(*args: object) -> None:
        pytest.fail("unsupported WITHOUT ROWID schemas must reject before oracle execution")

    monkeypatch.setattr("reproseed.workflow.run_oracle", unexpected)
    for allow_exec in (False, True):
        result = diagnose(config, allow_exec=allow_exec)
        assert result.exit_code == 2
        assert result.error is not None and result.error.reason == reason
        assert result.structurally_suitable is False
        assert result.actual_invocations == 0
        assert result.oracle_executed is False
        serialized = serialize_diagnosis(result)
        assert json.loads(serialized)["diagnostic_version"] == 1
        for private in (str(tmp_path), "private_items", "PRIVATE-KEY", "PRIVATE_ORACLE_MARKER"):
            assert private not in serialized
    output = tmp_path / "must-not-publish"
    assert main(["reduce", "--config", str(config), "--out", str(output), "--allow-exec"]) == 2
    error = capsys.readouterr().err
    assert "Traceback" not in error
    assert "PRIVATE-KEY" not in error
    assert not output.exists()
    assert not (tmp_path / "must-not-launch").exists()
    assert _digest(source) == before
    assert _digest(tmp_path / "oracle.py") == assets_before


UNSUPPORTED = [
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,c TEXT,PRIMARY KEY(a,b,c)) WITHOUT ROWID",
        "unsupported_composite_primary_key_arity",
        id="three-components",
    ),
    *[
        pytest.param(
            f"CREATE TABLE private_items(id {kind} PRIMARY KEY) WITHOUT ROWID",
            "unsupported_primary_key",
            id=f"scalar-{kind.lower()}",
        )
        for kind in ("REAL", "BLOB", "NUMERIC", "INT", "VARCHAR")
    ],
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b REAL,PRIMARY KEY(a,b)) WITHOUT ROWID",
        "unsupported_primary_key",
        id="composite-real",
    ),
    *[
        pytest.param(
            f"CREATE TABLE private_items(id {kind} PRIMARY KEY DESC) WITHOUT ROWID",
            "unsupported_primary_key_order",
            id=f"descending-{kind.lower()}",
        )
        for kind in ("INTEGER", "TEXT")
    ],
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a,b DESC)) WITHOUT ROWID",
        "unsupported_composite_primary_key_order",
        id="descending-composite",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY COLLATE NOCASE) WITHOUT ROWID",
        "unsupported_text_key_collation",
        id="scalar-nocase",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT COLLATE RTRIM,PRIMARY KEY(id COLLATE BINARY))"
        " WITHOUT ROWID",
        "unsupported_text_key_collation",
        id="scalar-column-rtrim",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a COLLATE NOCASE,b))"
        " WITHOUT ROWID",
        "unsupported_composite_key_collation",
        id="composite-nocase",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT COLLATE NOCASE,b INTEGER,"
        "PRIMARY KEY(a COLLATE BINARY,b)) WITHOUT ROWID",
        "unsupported_composite_key_collation",
        id="composite-column-nocase",
    ),
    pytest.param(
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY) WITHOUT ROWID;"
        "INSERT INTO private_items VALUES('PRIVATE-KEY')",
        "unsupported_primary_key_value",
        id="scalar-integer-wrong-storage",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY) WITHOUT ROWID;"
        "INSERT INTO private_items VALUES(X'505249564154452d4b4559')",
        "unsupported_primary_key_value",
        id="scalar-text-blob-storage",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;"
        "INSERT INTO private_items VALUES('PRIVATE-KEY',42.5)",
        "unsupported_composite_primary_key_value",
        id="composite-real-storage",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY) WITHOUT ROWID;"
        "INSERT INTO private_items VALUES(CAST(X'80ff' AS TEXT))",
        "unsupported_text_encoding",
        id="malformed-text-key",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;"
        "CREATE TABLE private_items(id TEXT PRIMARY KEY,a TEXT REFERENCES parent) WITHOUT ROWID",
        "unsupported_composite_foreign_key_cardinality",
        id="one-component-fk",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;"
        "CREATE TABLE private_items(id TEXT PRIMARY KEY,a TEXT,b INT,c TEXT,"
        "FOREIGN KEY(a,b,c) REFERENCES parent) WITHOUT ROWID",
        "unsupported_composite_foreign_key_cardinality",
        id="three-component-fk",
    ),
    pytest.param(
        "CREATE TABLE parent(id TEXT PRIMARY KEY,alternate TEXT UNIQUE) WITHOUT ROWID;"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,"
        "parent TEXT REFERENCES parent(alternate))",
        "unsupported_foreign_key_target",
        id="non-pk-unique-fk",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT,b INT,"
        "FOREIGN KEY(b,a) REFERENCES parent(b,a)) WITHOUT ROWID",
        "unsupported_foreign_key_target",
        id="reordered-composite-target",
    ),
    pytest.param(
        "CREATE TABLE parent(id TEXT PRIMARY KEY) WITHOUT ROWID;"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,parent INTEGER REFERENCES parent)"
        " WITHOUT ROWID",
        "unsupported_foreign_key_type",
        id="cross-affinity-scalar",
    ),
    pytest.param(
        "CREATE TABLE parent(a INTEGER,b TEXT,PRIMARY KEY(a,b)) WITHOUT ROWID;"
        "CREATE TABLE private_items(id TEXT PRIMARY KEY,a TEXT,b TEXT,"
        "FOREIGN KEY(a,b) REFERENCES parent) WITHOUT ROWID",
        "unsupported_composite_foreign_key_type",
        id="cross-affinity-composite",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;"
        "CREATE TABLE private_items(id TEXT PRIMARY KEY,a TEXT,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent) WITHOUT ROWID;"
        "INSERT INTO private_items VALUES('PRIVATE-KEY',NULL,'wrong-storage')",
        "unsupported_composite_foreign_key_value",
        id="partial-null-wrong-storage",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;"
        "CREATE TABLE private_items(id TEXT PRIMARY KEY,a TEXT,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent) WITHOUT ROWID;"
        "INSERT INTO private_items VALUES('PRIVATE-KEY',CAST(X'80ff' AS TEXT),NULL)",
        "unsupported_text_encoding",
        id="partial-null-malformed-text",
    ),
    pytest.param(
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,derived INTEGER GENERATED ALWAYS AS(id))"
        " WITHOUT ROWID",
        "unsupported_generated_column",
        id="generated-column",
    ),
    pytest.param(
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY) WITHOUT ROWID;"
        "CREATE TRIGGER private_trigger AFTER DELETE ON private_items BEGIN SELECT 1; END",
        "unsupported_trigger",
        id="trigger",
    ),
    pytest.param(
        "CREATE TABLE private_items(id TEXT PRIMARY KEY) WITHOUT ROWID;"
        "CREATE VIRTUAL TABLE text_search USING fts5(text)",
        "unsupported_virtual_table",
        id="virtual-table",
    ),
]


@pytest.mark.parametrize("schema,reason", UNSUPPORTED)
def test_sqlite_created_unsupported_shapes_reject_before_oracle_and_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    schema: str,
    reason: str,
) -> None:
    source = _create(tmp_path / "unsupported.sqlite3", schema)
    _reject_safely(tmp_path, source, reason, monkeypatch, capsys)


def test_unavailable_custom_collation_rejects_without_private_details_or_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "custom.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.create_collation("private_custom", lambda a, b: (a > b) - (a < b))
        connection.execute(
            "CREATE TABLE private_items(id TEXT PRIMARY KEY COLLATE private_custom) WITHOUT ROWID"
        )
    _reject_safely(tmp_path, source, "unsupported_unavailable_collation", monkeypatch, capsys)


def test_malformed_sqlite_input_rejects_without_oracle_or_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "malformed.sqlite3"
    source.write_bytes(b"synthetic malformed SQLite PRIVATE-KEY")
    before = _digest(source)
    config = _config(tmp_path, source)

    def unexpected(*args: object) -> None:
        pytest.fail("malformed SQLite cannot execute configured code")

    monkeypatch.setattr("reproseed.workflow.run_oracle", unexpected)
    result = diagnose(config, allow_exec=True)
    assert result.exit_code == 2
    assert result.actual_invocations == 0
    assert result.oracle_executed is False
    assert str(tmp_path) not in serialize_diagnosis(result)
    bundle = tmp_path / "bundle"
    assert main(["reduce", "--config", str(config), "--out", str(bundle), "--allow-exec"]) == 2
    assert "PRIVATE-KEY" not in capsys.readouterr().err
    assert not bundle.exists()
    assert not (tmp_path / "must-not-launch").exists()
    assert _digest(source) == before


def test_static_diagnosis_uses_supported_mixed_model_without_executing(
    mixed_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _digest(mixed_source)
    config = _config(tmp_path, mixed_source)

    def unexpected(*args: object) -> None:
        pytest.fail("static diagnosis cannot execute an oracle")

    monkeypatch.setattr("reproseed.workflow.run_oracle", unexpected)
    result = diagnose(config)
    assert result.exit_code == 0
    assert result.schema_supported is True
    assert result.table_counts == DatabaseModel.from_database(mixed_source).counts()
    assert result.baseline_confirmed is False
    assert result.actual_invocations == 0
    assert result.oracle_executed is False
    assert not (tmp_path / "must-not-launch").exists()
    assert _digest(mixed_source) == before


def _cli(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "reproseed", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return result


def _files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _digest(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_real_cli_diagnosis_reduction_inspection_and_relocated_replay(tmp_path: Path) -> None:
    root = tmp_path / "original"
    root.mkdir()
    source = _create(
        root / "source.sqlite3",
        "CREATE TABLE parents(id TEXT PRIMARY KEY,payload BLOB) WITHOUT ROWID;"
        "CREATE TABLE children(id INTEGER PRIMARY KEY,parent TEXT REFERENCES parents);"
        "INSERT INTO parents VALUES('雪-🙂',X'00ff'),('decoy',NULL);"
        "INSERT INTO children VALUES(-8,'雪-🙂'),(910,'decoy');",
    )
    original_state = _state(source)
    config = _config(
        root,
        source,
        "import sqlite3,sys\n"
        "from contextlib import closing\n"
        "with closing(sqlite3.connect(sys.argv[1])) as c:\n"
        "    assert c.execute('PRAGMA integrity_check').fetchall() == [('ok',)]\n"
        "    assert c.execute('PRAGMA foreign_key_check').fetchall() == []\n"
        "    target = c.execute('SELECT 1 FROM children WHERE id=?',(-8,)).fetchone()\n"
        "    c.execute('DELETE FROM children'); c.commit()\n"
        "if target:\n"
        "    print('PRIVATE_ORACLE_MARKER'); raise SystemExit(42)\n",
    )
    source_files = _files(root)
    static = json.loads(
        _cli(["diagnose", "--config", str(config), "--format", "json"], tmp_path).stdout
    )
    assert static["schema_supported"] is True
    assert static["oracle_executed"] is False
    assert static["baseline_confirmed"] is False
    baseline = json.loads(
        _cli(
            ["diagnose", "--config", str(config), "--allow-exec", "--format", "json"], tmp_path
        ).stdout
    )
    assert baseline["baseline_confirmed"] is True
    assert baseline["actual_invocations"] == 3
    bundle = tmp_path / "bundle"
    _cli(["reduce", "--config", str(config), "--out", str(bundle), "--allow-exec"], tmp_path)
    assert _files(root) == source_files
    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    assert report["version"] == 1 and report["verified"] is True
    assert report["final_counts"] == {"children": 1, "parents": 1}
    for field in ("baseline_verification", "final_verification"):
        assert len(report[field]) == 3
        assert all(
            result["outcome"] == "TARGET_FAILURE" and result["executed"] for result in report[field]
        )
    assert report["invalid_candidates"] == report["unresolved_attempts"] == 0
    fixture_state = _state(bundle / "fixture.sqlite3")
    assert fixture_state[0] == original_state[0]
    assert fixture_state[1] == {"parents": {("雪-🙂", b"\0\xff")}, "children": {(-8, "雪-🙂")}}
    bundle_files = _files(bundle)
    default = _cli(["inspect", str(bundle)], tmp_path)
    explicit = _cli(["inspect", str(bundle), "--format", "json"], tmp_path)
    assert json.loads(default.stdout) == report
    assert explicit.stdout == default.stdout
    assert (
        "Recorded final confirmations: 3/3 TARGET_FAILURE"
        in _cli(["inspect", str(bundle), "--format", "text"], tmp_path).stdout
    )
    assert _files(bundle) == bundle_files
    with tempfile.TemporaryDirectory(prefix="reproseed-without-rowid-replay-") as temporary:
        relocation = Path(temporary)
        relocated = relocation / "bundle"
        shutil.copytree(bundle, relocated)
        root.rename(tmp_path / "original-unavailable")
        bundle.rename(tmp_path / "bundle-unavailable")
        unrelated = relocation / "unrelated"
        unrelated.mkdir()
        result = json.loads(_cli(["replay", str(relocated), "--allow-exec"], unrelated).stdout)
        assert result["outcome"] == "TARGET_FAILURE"
        assert len(result["confirmations"]) == 3
        assert all(attempt["outcome"] == "TARGET_FAILURE" for attempt in result["confirmations"])
        assert _files(relocated) == bundle_files
    assert _files(tmp_path / "original-unavailable") == source_files
