"""Real SQLite composite identities, complete FK groups and rejection safety."""

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
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel, RowId, compact, validate_database


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
    "families", [("INTEGER", "INTEGER"), ("INTEGER", "TEXT"), ("TEXT", "INTEGER"), ("TEXT", "TEXT")]
)
@pytest.mark.parametrize("shape", ["ordinary", "not-null", "strict", "whitespace-types"])
def test_all_composite_families_preserve_exact_values_and_order(
    tmp_path: Path, families: tuple[str, str], shape: str
) -> None:
    types = families if shape != "whitespace-types" else tuple(f'" {t.lower()} "' for t in families)
    nullability = " NOT NULL" if shape == "not-null" else ""
    suffix = " STRICT" if shape == "strict" else ""
    source = _create(
        tmp_path / "composite.sqlite3",
        f'CREATE TABLE "items odd"("first" {types[0]}{nullability}, '
        f'"seco""nd" {types[1]}{nullability}, payload BLOB, '
        'PRIMARY KEY("first", "seco""nd"))' + suffix,
    )
    integers = [-910, -8, 0, 42, 100009]
    texts = ["", "Item-A", "item-a", "42", "雪-🙂", "nul\0key", "'quote\"; DELETE FROM items"]
    first_values = integers if families[0] == "INTEGER" else texts
    second_values = integers if families[1] == "INTEGER" else texts
    keys = [(a, b) for a in first_values for b in second_values]
    with closing(sqlite3.connect(source)) as connection:
        connection.executemany(
            'INSERT INTO "items odd" VALUES(?, ?, ?)',
            [(a, b, b"\0\xff retained payload") for a, b in reversed(keys)],
        )
        connection.commit()
    before = _digest(source)
    model = DatabaseModel.from_database(source)
    assert model.rows == tuple(("items odd", key) for key in sorted(keys))
    assert model.counts() == {"items odd": len(keys)}
    retained = frozenset({model.rows[0], model.rows[-1]})
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(source, retained, candidate)
    validate_database(candidate)
    assert frozenset(DatabaseModel.from_database(candidate).rows) == retained
    assert _schema(candidate) == _schema(source)
    with closing(sqlite3.connect(candidate)) as connection:
        assert connection.execute('SELECT * FROM "items odd" ORDER BY 1,2').fetchall() == [
            (*key, b"\0\xff retained payload") for _, key in sorted(retained)
        ]
    assert _digest(source) == before


@pytest.mark.parametrize(
    "families", [("INTEGER", "INTEGER"), ("INTEGER", "TEXT"), ("TEXT", "INTEGER"), ("TEXT", "TEXT")]
)
@pytest.mark.parametrize("suffix", ["", " STRICT"])
def test_empty_composite_metadata_and_compaction(
    tmp_path: Path, families: tuple[str, str], suffix: str
) -> None:
    source = _create(
        tmp_path / "empty.sqlite3",
        f"CREATE TABLE empty(a {families[0]}, b {families[1]}, PRIMARY KEY(b,a)){suffix};"
        "CREATE TABLE scalar(id INTEGER PRIMARY KEY); INSERT INTO scalar VALUES(-71),(8000);",
    )
    model = DatabaseModel.from_database(source)
    assert model.rows == (("scalar", -71), ("scalar", 8000))
    assert model.counts() == {"empty": 0, "scalar": 2}
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(source, frozenset(), candidate)
    final = tmp_path / "compact.sqlite3"
    compact(candidate, final)
    assert DatabaseModel.from_database(final).counts() == {"empty": 0, "scalar": 0}
    assert _schema(final) == _schema(source)


def test_primary_key_order_comes_from_ordinals_and_hidden_rowids_are_not_identities(
    tmp_path: Path,
) -> None:
    source = _create(
        tmp_path / "ordinals.sqlite3",
        "PRAGMA encoding='UTF-16'; PRAGMA page_size=8192;"
        "CREATE TABLE items(sequence INTEGER, tenant TEXT, payload TEXT, "
        "PRIMARY KEY(tenant,sequence));"
        "INSERT INTO items(rowid,sequence,tenant,payload) VALUES"
        "(991,42,'雪-🙂','keep'),(-88,42,'other','remove'),(20000,-8,'雪-🙂','remove');",
    )
    model = DatabaseModel.from_database(source)
    assert model.rows == (
        ("items", ("other", 42)),
        ("items", ("雪-🙂", -8)),
        ("items", ("雪-🙂", 42)),
    )
    before = _digest(source)
    selected = frozenset({("items", ("雪-🙂", 42))})
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(source, selected, candidate)
    final = tmp_path / "compact.sqlite3"
    compact(candidate, final)
    assert frozenset(DatabaseModel.from_database(final).rows) == selected
    with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(final)) as result:
        assert result.execute("SELECT sequence,tenant,payload FROM items").fetchall() == [
            (42, "雪-🙂", "keep")
        ]
        # A compact rowid table may acquire a different hidden rowid. Only the
        # declared pair is used to reconstruct identity and retain exact values.
        for pragma in ("encoding", "page_size"):
            assert (
                result.execute(f"PRAGMA {pragma}").fetchone()
                == original.execute(f"PRAGMA {pragma}").fetchone()
            )
    assert _digest(source) == before


@pytest.fixture
def relational_source(tmp_path: Path) -> Path:
    return _create(
        tmp_path / "relational.sqlite3",
        """
        PRAGMA user_version=91;
        PRAGMA application_id=8182;
        CREATE TABLE tenants(id TEXT PRIMARY KEY);
        CREATE TABLE owners(id INTEGER PRIMARY KEY);
        CREATE TABLE invoices(tenant TEXT, number INTEGER, owner INT REFERENCES owners(id),
            payload BLOB, PRIMARY KEY(tenant,number));
        CREATE TABLE plans(tenant TEXT, name TEXT, PRIMARY KEY(tenant,name));
        CREATE TABLE payments(id INTEGER PRIMARY KEY, tenant TEXT, number INT,
            plan_tenant TEXT, plan_name TEXT, payload BLOB,
            FOREIGN KEY(tenant,number) REFERENCES invoices(tenant,number) ON DELETE SET NULL,
            FOREIGN KEY(plan_tenant,plan_name) REFERENCES plans ON DELETE CASCADE);
        CREATE TABLE events(id TEXT PRIMARY KEY, tenant TEXT, number BIGINT, owner INT,
            FOREIGN KEY(tenant,number) REFERENCES invoices,
            FOREIGN KEY(owner) REFERENCES owners(id));
        CREATE TABLE lines(tenant TEXT, number INTEGER, line INTEGER, scalar INTEGER,
            PRIMARY KEY(tenant,line),
            FOREIGN KEY(tenant,number) REFERENCES invoices(tenant,number),
            FOREIGN KEY(scalar) REFERENCES payments(id));
        CREATE TABLE links(id INTEGER PRIMARY KEY, tenant TEXT, number INTEGER,
            alternate_tenant TEXT, alternate_number INT,
            FOREIGN KEY(tenant,number) REFERENCES invoices,
            FOREIGN KEY(alternate_tenant,alternate_number) REFERENCES invoices);
        CREATE TABLE receipts(id TEXT PRIMARY KEY, event TEXT REFERENCES events(id));
        CREATE INDEX payment_payload ON payments(payload);
        CREATE VIEW invoice_labels AS SELECT tenant,number FROM invoices;
        INSERT INTO tenants VALUES('a'),('b');
        INSERT INTO owners VALUES(-8),(910);
        INSERT INTO invoices VALUES('a',42,-8,X'00ff'),('b',42,910,X'0102'),
            ('a',43,-8,X'0304');
        INSERT INTO plans VALUES('a','basic'),('b','basic');
        INSERT INTO payments VALUES(1,'a',42,'a','basic',X'00ff'),
            (2,'b',42,'b','basic',X'0102'),(3,'a',43,NULL,NULL,X'0304'),
            (4,NULL,NULL,NULL,NULL,X'04'),(5,NULL,42,NULL,NULL,X'05'),
            (6,'a',NULL,NULL,NULL,X'06');
        INSERT INTO events VALUES('a-event','a',42,-8),('b-event','b',42,910),
            ('alternate-event','a',43,-8),('nullable-event',NULL,42,NULL);
        INSERT INTO lines VALUES('a',42,8,1),('b',42,8,2),('a',43,9,3);
        INSERT INTO links VALUES(701,'a',42,'b',42),(702,'a',43,'a',42);
        INSERT INTO receipts VALUES('a-receipt','a-event'),('b-receipt','b-event');
        """,
    )


def test_complete_composite_foreign_keys_do_not_cross_tenants_or_invoice_numbers(
    relational_source: Path,
) -> None:
    model = DatabaseModel.from_database(relational_source)
    rows = frozenset(model.rows)
    expected_a = frozenset(
        {
            ("invoices", ("a", 42)),
            ("payments", 1),
            ("events", "a-event"),
            ("lines", ("a", 8)),
            ("links", 701),
            ("links", 702),
            ("receipts", "a-receipt"),
        }
    )
    assert model.deletion_closure([("invoices", ("a", 42))], rows) == expected_a
    assert model.deletion_closure([("invoices", ("b", 42))], rows) == frozenset(
        {
            ("invoices", ("b", 42)),
            ("payments", 2),
            ("events", "b-event"),
            ("lines", ("b", 8)),
            ("links", 701),
            ("receipts", "b-receipt"),
        }
    )
    assert model.deletion_closure([("invoices", ("a", 43))], rows) == frozenset(
        {
            ("invoices", ("a", 43)),
            ("payments", 3),
            ("events", "alternate-event"),
            ("lines", ("a", 9)),
            ("links", 702),
        }
    )
    # Independently query full parent equality, including both group components.
    with closing(sqlite3.connect(relational_source)) as connection:
        direct = connection.execute(
            "SELECT p.id FROM payments AS p JOIN invoices AS i "
            "ON i.tenant = p.tenant COLLATE BINARY AND i.number = p.number "
            "WHERE i.tenant = ? AND i.number = ?",
            ("a", 42),
        ).fetchall()
    assert direct == [(1,)]
    assert all(("payments", key) not in expected_a for key in (2, 3, 4, 5, 6))


def test_parent_family_controls_composite_pk_children_and_multiple_foreign_keys(
    relational_source: Path,
) -> None:
    model = DatabaseModel.from_database(relational_source)
    rows = frozenset(model.rows)
    assert model.deletion_closure([("plans", ("a", "basic"))], rows) == frozenset(
        {("plans", ("a", "basic")), ("payments", 1), ("lines", ("a", 8))}
    )
    assert model.deletion_closure([("owners", 910)], rows) == frozenset(
        {
            ("owners", 910),
            ("invoices", ("b", 42)),
            ("payments", 2),
            ("events", "b-event"),
            ("lines", ("b", 8)),
            ("links", 701),
            ("receipts", "b-receipt"),
        }
    )
    # Each partially NULL group is exempt from the parent relationship.
    for key in (4, 5, 6):
        assert model.deletion_closure([("payments", key)], rows) == frozenset({("payments", key)})
    assert model.deletion_closure([("events", "nullable-event")], rows) == frozenset(
        {("events", "nullable-event")}
    )


@pytest.mark.parametrize(
    "families", [("INTEGER", "INTEGER"), ("INTEGER", "TEXT"), ("TEXT", "INTEGER"), ("TEXT", "TEXT")]
)
@pytest.mark.parametrize("target", ["parent", "parent(a,b)"])
def test_every_parent_component_family_has_full_explicit_and_implicit_fk_edges(
    tmp_path: Path, families: tuple[str, str], target: str
) -> None:
    source = _create(
        tmp_path / "families.sqlite3",
        f"CREATE TABLE parent(a {families[0]},b {families[1]},PRIMARY KEY(a,b));"
        f"CREATE TABLE child(id TEXT PRIMARY KEY,a {families[0]},b {families[1]},"
        f"FOREIGN KEY(a,b) REFERENCES {target});",
    )
    first = -91 if families[0] == "INTEGER" else "雪-🙂"
    alternate_first = 91000 if families[0] == "INTEGER" else "other"
    second = 42 if families[1] == "INTEGER" else ""
    alternate_second = -8 if families[1] == "INTEGER" else "42"
    with closing(sqlite3.connect(source)) as connection:
        connection.executemany(
            "INSERT INTO parent VALUES(?,?)",
            [(first, second), (alternate_first, second), (first, alternate_second)],
        )
        connection.executemany(
            "INSERT INTO child VALUES(?,?,?)",
            [
                ("exact", first, second),
                ("same-second", alternate_first, second),
                ("same-first", first, alternate_second),
                ("null-first", None, second),
                ("null-second", first, None),
                ("both-null", None, None),
            ],
        )
        connection.commit()
    model = DatabaseModel.from_database(source)
    rows = frozenset(model.rows)
    assert model.deletion_closure([("parent", (first, second))], rows) == frozenset(
        {("parent", (first, second)), ("child", "exact")}
    )
    retained = rows - model.deletion_closure([("parent", (first, second))], rows)
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(source, retained, candidate)
    validate_database(candidate)
    assert frozenset(DatabaseModel.from_database(candidate).rows) == retained


def test_materialization_compaction_schema_values_and_pristine_source(
    relational_source: Path,
    tmp_path: Path,
) -> None:
    before = _digest(relational_source)
    model = DatabaseModel.from_database(relational_source)
    rows = frozenset(model.rows)
    removed = model.deletion_closure([("invoices", ("a", 42))], rows)
    selected = rows - removed
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(relational_source, selected, candidate)
    final = tmp_path / "final.sqlite3"
    compact(candidate, final)
    validate_database(final)
    assert frozenset(DatabaseModel.from_database(final).rows) == selected
    assert _schema(final) == _schema(relational_source)
    with (
        closing(sqlite3.connect(relational_source)) as original,
        closing(sqlite3.connect(final)) as result,
    ):
        tables = original.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        ).fetchall()
        for (table,) in tables:
            old = set(original.execute(f'SELECT * FROM "{table}"'))
            new = set(result.execute(f'SELECT * FROM "{table}"'))
            assert new <= old
            assert len(new) == model.counts(selected)[table]
        assert result.execute("SELECT * FROM payments ORDER BY id").fetchall() == [
            (2, "b", 42, "b", "basic", b"\x01\x02"),
            (3, "a", 43, None, None, b"\x03\x04"),
            (4, None, None, None, None, b"\x04"),
            (5, None, 42, None, None, b"\x05"),
            (6, "a", None, None, None, b"\x06"),
        ]
        for pragma in ("user_version", "application_id"):
            assert (
                result.execute(f"PRAGMA {pragma}").fetchone()
                == original.execute(f"PRAGMA {pragma}").fetchone()
            )
    # Oracle mutation cannot seed a later materialization.
    with closing(sqlite3.connect(candidate)) as connection:
        connection.execute("UPDATE invoices SET payload=X'ffee'")
        connection.commit()
    later = tmp_path / "later.sqlite3"
    model.materialize(relational_source, selected, later)
    with closing(sqlite3.connect(later)) as connection:
        assert connection.execute(
            "SELECT payload FROM invoices WHERE tenant=? AND number=?", ("b", 42)
        ).fetchone() == (b"\x01\x02",)
    assert _digest(relational_source) == before


def test_composite_binary_parent_matching_and_ascii_identifier_matching(tmp_path: Path) -> None:
    source = _create(
        tmp_path / "names.sqlite3",
        'CREATE TABLE "Parent odd"("Ten""ant" TEXT, "Number" INTEGER, '
        'PRIMARY KEY("Ten""ant","Number"));'
        "CREATE TABLE children(id TEXT PRIMARY KEY, tenant TEXT COLLATE NOCASE, number INT,"
        'FOREIGN KEY(tenant,number) REFERENCES "pArEnT odd"("tEn""AnT","nUmBeR"));'
        "INSERT INTO \"Parent odd\" VALUES('Item-A',42),('item-a',42);"
        "INSERT INTO children VALUES('42','Item-A',42),('other','item-a',42);",
    )
    model = DatabaseModel.from_database(source)
    rows = frozenset(model.rows)
    assert model.deletion_closure([("Parent odd", ("Item-A", 42))], rows) == frozenset(
        {("Parent odd", ("Item-A", 42)), ("children", "42")}
    )
    assert model.deletion_closure([("Parent odd", ("item-a", 42))], rows) == frozenset(
        {("Parent odd", ("item-a", 42)), ("children", "other")}
    )


def test_composite_cycles_self_references_and_normalized_candidate_cache(tmp_path: Path) -> None:
    source = _create(
        tmp_path / "cycles.sqlite3",
        "CREATE TABLE nodes(tenant TEXT,number INTEGER,peer_tenant TEXT,peer_number INT,"
        "PRIMARY KEY(tenant,number), FOREIGN KEY(peer_tenant,peer_number) REFERENCES nodes);"
        "CREATE TABLE scalar(id INTEGER PRIMARY KEY,node_tenant TEXT,node_number INT,"
        "FOREIGN KEY(node_tenant,node_number) REFERENCES nodes);"
        "CREATE TABLE text_scalar(id TEXT PRIMARY KEY);"
        "INSERT INTO nodes VALUES('a',42,'b',42),('b',42,'a',42),('a',43,'a',43),"
        "('decoy',-8,NULL,NULL);"
        "INSERT INTO scalar VALUES(900,'a',42),(100001,NULL,NULL);"
        "INSERT INTO text_scalar VALUES('42'),('Item-A');",
    )
    model = DatabaseModel.from_database(source)
    rows = frozenset(model.rows)
    essential = frozenset({("nodes", ("a", 42)), ("nodes", ("b", 42)), ("scalar", 900)})
    assert model.deletion_closure([("nodes", ("a", 42))], rows) == essential
    assert model.deletion_closure([("nodes", ("a", 43))], rows) == frozenset({("nodes", ("a", 43))})
    calls: list[frozenset[RowId]] = []
    run = 0

    def evaluate(retained: frozenset[RowId]) -> Evaluation:
        calls.append(retained)
        candidate = tmp_path / f"trial-{run}-{len(calls)}.sqlite3"
        model.materialize(source, retained, candidate)
        assert frozenset(DatabaseModel.from_database(candidate).rows) == retained
        return Evaluation("TARGET_FAILURE" if essential <= retained else "PASS")

    first = reduce_rows(model, evaluate)
    first_calls = calls.copy()
    calls.clear()
    run += 1
    second = reduce_rows(model, evaluate)
    assert first == second
    assert calls == first_calls
    assert len(calls) == len(set(calls))
    assert first.retained == essential
    assert first.cache_hits > 0
    assert all(attempt["before"] > attempt["after"] for attempt in first.accepted)


def test_composite_identity_does_not_coerce_fold_or_drop_components(tmp_path: Path) -> None:
    source = _create(
        tmp_path / "identities.sqlite3",
        "CREATE TABLE items(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "INSERT INTO items VALUES('42',42),('Item-A',42),('Item-A',43);",
    )
    model = DatabaseModel.from_database(source)
    for index, unknown in enumerate(
        (
            ("items", (42, 42)),
            ("items", ("item-a", 42)),
            ("items", ("42", "42")),
            ("items", 42),
            ("items", ("Item-A", 44)),
        )
    ):
        destination = tmp_path / f"unknown-{index}.sqlite3"
        with pytest.raises(DatabaseError, match="identities"):
            model.materialize(source, frozenset({unknown}), destination)
        assert not destination.exists()
    assert len(set(model.rows)) == 3


def test_typed_sorting_preserves_legacy_scalar_order(tmp_path: Path) -> None:
    from reproseed.sqlite_adapter import row_sort_key

    source = _create(
        tmp_path / "legacy-order.sqlite3",
        "CREATE TABLE integers(id INTEGER PRIMARY KEY);"
        "CREATE TABLE strings(id TEXT PRIMARY KEY);"
        "INSERT INTO integers VALUES(100009),(-91),(42),(0);"
        "INSERT INTO strings VALUES('item-a'),('Item-A'),('42'),('雪-🙂'),('');",
    )
    model = DatabaseModel.from_database(source)
    # Legacy sorted identities compare table names first and each table has a
    # fixed scalar family. The typed comparator preserves the entire sequence.
    assert sorted(model.rows, key=row_sort_key) == sorted(model.rows)


def _config(root: Path, source: Path, sentinel: Path) -> Path:
    (root / "oracle.py").write_text(
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
    reasons: str | tuple[str, ...],
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
        pytest.fail("unsupported composite schemas must reject before any oracle launch")

    monkeypatch.setattr("reproseed.workflow.run_oracle", unexpected)
    for allow_exec in (False, True):
        result = diagnose(config, allow_exec=allow_exec)
        assert result.exit_code == 2
        assert result.error is not None
        assert result.error.reason in ((reasons,) if isinstance(reasons, str) else reasons)
        assert result.schema_supported is (
            None if result.error.reason == "integrity_failure" else False
        )
        assert result.structurally_suitable is False
        assert result.actual_invocations == 0
        assert result.oracle_executed is False
        serialized = serialize_diagnosis(result)
        assert json.loads(serialized)["diagnostic_version"] == 1
        for private in (str(root), "private_items", "PRIVATE-KEY", "PRIVATE_ORACLE_MARKER"):
            assert private not in serialized
    bundle = root / "must-not-publish"
    assert main(["reduce", "--config", str(config), "--out", str(bundle), "--allow-exec"]) == 2
    assert "Traceback" not in capsys.readouterr().err
    assert not bundle.exists()
    assert not sentinel.exists()
    assert _digest(source) == before
    assert _digest(root / "oracle.py") == assets_before


UNSUPPORTED_SCHEMAS = [
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,c TEXT,PRIMARY KEY(a,b,c))",
        "unsupported_composite_primary_key_arity",
        id="three-column-pk-empty",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "INSERT INTO private_items VALUES(NULL,42)",
        "unsupported_null_composite_primary_key",
        id="null-first",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "INSERT INTO private_items VALUES('PRIVATE-KEY',NULL)",
        "unsupported_null_composite_primary_key",
        id="null-second",
    ),
    pytest.param(
        "CREATE TABLE private_items(a INTEGER,b TEXT,PRIMARY KEY(a,b));"
        "INSERT INTO private_items VALUES('PRIVATE-KEY','other')",
        "unsupported_composite_primary_key_value",
        id="text-in-integer-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(a INTEGER,b TEXT,PRIMARY KEY(a,b));"
        "INSERT INTO private_items VALUES(42.5,'PRIVATE-KEY')",
        "unsupported_composite_primary_key_value",
        id="real-in-integer-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "INSERT INTO private_items VALUES(X'505249564154452d4b4559',42)",
        "unsupported_composite_primary_key_value",
        id="blob-in-text-pk",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT COLLATE NOCASE,b INTEGER,PRIMARY KEY(a,b))",
        "unsupported_composite_key_collation",
        id="nocase-first-empty",
    ),
    pytest.param(
        "CREATE TABLE private_items(a INTEGER,b TEXT COLLATE RTRIM,PRIMARY KEY(a,b))",
        "unsupported_composite_key_collation",
        id="rtrim-second-empty",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT COLLATE NOCASE,b INTEGER,"
        "PRIMARY KEY(a COLLATE BINARY,b))",
        "unsupported_composite_key_collation",
        id="nocase-column-binary-pk-empty",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a COLLATE NOCASE,b))",
        "unsupported_composite_key_collation",
        id="nocase-index-empty",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a DESC,b))",
        "unsupported_composite_primary_key_order",
        id="descending-first-empty",
    ),
    pytest.param(
        "CREATE TABLE private_items(a INTEGER,b TEXT,PRIMARY KEY(a,b DESC))",
        "unsupported_composite_primary_key_order",
        id="descending-second-empty",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,c TEXT,PRIMARY KEY(a,b,c)) WITHOUT ROWID",
        "unsupported_composite_primary_key_arity",
        id="without-rowid-three-components",
    ),
    *[
        pytest.param(
            f"CREATE TABLE private_items(a {kind},b TEXT,PRIMARY KEY(a,b))",
            "unsupported_primary_key",
            id=f"unsupported-{kind.lower()}-empty",
        )
        for kind in ("REAL", "BLOB", "NUMERIC", "INT", "VARCHAR", "CHAR")
    ],
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER)", "unsupported_primary_key", id="missing-pk"
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,c INTEGER GENERATED ALWAYS AS(b),"
        "PRIMARY KEY(a,b))",
        "unsupported_generated_column",
        id="generated",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TRIGGER private_trigger AFTER DELETE ON private_items BEGIN SELECT 1; END",
        "unsupported_trigger",
        id="trigger",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT REFERENCES parent)",
        "unsupported_composite_foreign_key_cardinality",
        id="one-fk-component",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT,b INT,c TEXT,"
        "FOREIGN KEY(a,b,c) REFERENCES parent)",
        "unsupported_composite_foreign_key_cardinality",
        id="three-fk-components",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,x TEXT,y INTEGER,PRIMARY KEY(a,b),UNIQUE(x,y));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent(x,y))",
        "unsupported_foreign_key_target",
        id="non-pk-unique-pair",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,b INT,a TEXT,"
        "FOREIGN KEY(b,a) REFERENCES parent(b,a))",
        "unsupported_foreign_key_target",
        id="reordered-parent-columns",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a INTEGER,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent)",
        "unsupported_composite_foreign_key_type",
        id="integer-fk-to-text-component-empty",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT,b TEXT,"
        "FOREIGN KEY(a,b) REFERENCES parent)",
        "unsupported_composite_foreign_key_type",
        id="text-fk-to-integer-component-empty",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a VARCHAR,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent)",
        "unsupported_composite_foreign_key_type",
        id="varchar-fk-component-empty",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent);"
        "INSERT INTO parent VALUES('PRIVATE-KEY',42);"
        "INSERT INTO private_items VALUES(1,'PRIVATE-KEY','wrong')",
        "unsupported_composite_foreign_key_value",
        id="text-in-integer-fk",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent);"
        "INSERT INTO parent VALUES('PRIVATE-KEY',42);"
        "INSERT INTO private_items VALUES(1,X'505249564154452d4b4559',42)",
        "unsupported_composite_foreign_key_value",
        id="blob-in-text-fk",
    ),
    pytest.param(
        "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "INSERT INTO private_items VALUES(CAST(X'80ff' AS TEXT),42)",
        "unsupported_text_encoding",
        id="invalid-utf8-pk",
    ),
    pytest.param(
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent);"
        "INSERT INTO private_items VALUES(1,CAST(X'80ff' AS TEXT),42)",
        "unsupported_text_encoding",
        id="invalid-utf8-fk",
    ),
]


@pytest.mark.parametrize("schema,reason", UNSUPPORTED_SCHEMAS)
def test_unsupported_composite_shapes_reject_before_execution_or_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    schema: str,
    reason: str,
) -> None:
    source = _create(tmp_path / "unsupported.sqlite3", schema)
    _assert_rejection_safety(tmp_path, source, reason, monkeypatch, capsys)


def test_custom_composite_collation_rejects_empty_schema_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "custom.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.create_collation("private_custom", lambda a, b: (a > b) - (a < b))
        connection.execute(
            "CREATE TABLE private_items(a TEXT,b INTEGER,PRIMARY KEY(a COLLATE private_custom,b))"
        )
    _assert_rejection_safety(
        tmp_path, source, "unsupported_unavailable_collation", monkeypatch, capsys
    )


@pytest.mark.parametrize(
    "component,value",
    [("a", "1.0"), ("a", "42.5"), ("b", "42"), ("b", "42.5")],
)
def test_migrated_composite_pk_storage_is_never_coerced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    component: str,
    value: str,
) -> None:
    declaration = "a BLOB,b TEXT" if component == "a" else "a INTEGER,b BLOB"
    values = f"{value},'PRIVATE-KEY'" if component == "a" else f"91,{value}"
    new_declaration = "a INTEGER" if component == "a" else "b TEXT"
    source = _create(
        tmp_path / "migrated.sqlite3",
        f"CREATE TABLE private_items({declaration},PRIMARY KEY(a,b));"
        f"INSERT INTO private_items VALUES({values});"
        "PRAGMA writable_schema=ON;"
        f"UPDATE sqlite_schema SET sql=replace(sql,'{component} BLOB','{new_declaration}') "
        "WHERE name='private_items';",
    )
    # SQLite 3.50+ may reject old storage under a migrated declaration during
    # integrity validation; older engines reach the explicit component check.
    _assert_rejection_safety(
        tmp_path,
        source,
        ("unsupported_composite_primary_key_value", "integrity_failure"),
        monkeypatch,
        capsys,
    )


@pytest.mark.parametrize("component,value", [("a", "42"), ("b", "1.0")])
def test_migrated_composite_fk_storage_is_never_parent_affinity_coercion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    component: str,
    value: str,
) -> None:
    declaration = "a BLOB,b INT" if component == "a" else "a TEXT,b BLOB"
    values = f"{value},1" if component == "a" else f"'42',{value}"
    new_declaration = "a TEXT" if component == "a" else "b INT"
    source = _create(
        tmp_path / "migrated-fk.sqlite3",
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        f"CREATE TABLE private_items(id INTEGER PRIMARY KEY,{declaration},"
        "FOREIGN KEY(a,b) REFERENCES parent);"
        "INSERT INTO parent VALUES('42',1);"
        f"INSERT INTO private_items VALUES(9,{values});"
        "PRAGMA writable_schema=ON;"
        f"UPDATE sqlite_schema SET sql=replace(sql,'{component} BLOB','{new_declaration}') "
        "WHERE name='private_items';",
    )
    _assert_rejection_safety(
        tmp_path,
        source,
        ("unsupported_composite_foreign_key_value", "integrity_failure"),
        monkeypatch,
        capsys,
    )


@pytest.mark.parametrize(
    "values,reason",
    [
        ("NULL,'PRIVATE-KEY'", "unsupported_composite_foreign_key_value"),
        ("CAST(X'80ff' AS TEXT),NULL", "unsupported_text_encoding"),
    ],
)
def test_partial_null_fk_still_rejects_unsupported_storage_and_text_encoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    values: str,
    reason: str,
) -> None:
    source = _create(
        tmp_path / "partial-null.sqlite3",
        "CREATE TABLE parent(a TEXT,b INTEGER,PRIMARY KEY(a,b));"
        "CREATE TABLE private_items(id INTEGER PRIMARY KEY,a TEXT,b INT,"
        "FOREIGN KEY(a,b) REFERENCES parent);"
        f"INSERT INTO private_items VALUES(1,{values});",
    )
    _assert_rejection_safety(tmp_path, source, reason, monkeypatch, capsys)


@pytest.mark.parametrize(
    "metadata",
    [
        "missing-index",
        "duplicate-index",
        "nonunique-index",
        "partial-index",
        "missing-key-column",
        "expression-key",
        "wrong-column-id",
        "reordered-key-columns",
    ],
)
def test_composite_pk_index_metadata_is_required_even_when_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    metadata: str,
) -> None:
    source = _create(
        tmp_path / "metadata.sqlite3",
        "CREATE TABLE private_items(a TEXT,b INTEGER,payload TEXT,PRIMARY KEY(a,b));",
    )

    class MetadataConnection(sqlite3.Connection):
        def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
            cursor = super().execute(sql, parameters)
            list_query = sql.startswith("PRAGMA main.index_list(")
            keys_query = sql.startswith("PRAGMA main.index_xinfo(")
            if not (list_query or keys_query):
                return cursor
            rows = [list(row) for row in cursor.fetchall()]
            if list_query:
                if metadata == "missing-index":
                    rows = []
                elif metadata == "duplicate-index":
                    rows.append(rows[0].copy())
                elif metadata == "nonunique-index":
                    rows[0][2] = 0
                elif metadata == "partial-index":
                    rows[0][4] = 1
            if keys_query:
                if metadata == "missing-key-column":
                    rows = [row for row in rows if row[0] != 1]
                elif metadata == "expression-key":
                    rows[0][1:3] = [-2, None]
                elif metadata == "wrong-column-id":
                    rows[0][1] = 2
                elif metadata == "reordered-key-columns":
                    rows[0][1:3], rows[1][1:3] = rows[1][1:3], rows[0][1:3]
            if not rows:
                return super().execute("SELECT NULL WHERE 0")
            # Retain real SQLite data/schema/integrity and alter only the
            # metadata boundary to cover malformed/unavailable index replies.
            query = " UNION ALL ".join("SELECT " + ",".join("?" for _ in row) for row in rows)
            return super().execute(query, tuple(value for row in rows for value in row))

    def readonly(path: Path, *, timeout_seconds: float = 5.0) -> sqlite3.Connection:
        return sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=timeout_seconds,
            factory=MetadataConnection,
        )

    monkeypatch.setattr("reproseed.sqlite_adapter._readonly", readonly)
    _assert_rejection_safety(
        tmp_path,
        source,
        "unsupported_composite_primary_key_metadata",
        monkeypatch,
        capsys,
    )


def test_supported_composite_static_diagnosis_shares_model_and_never_launches(
    relational_source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _digest(relational_source)
    config = _config(tmp_path, relational_source, tmp_path / "sentinel")

    def unexpected(*args: object) -> None:
        pytest.fail("static diagnosis cannot launch an oracle")

    monkeypatch.setattr("reproseed.workflow.run_oracle", unexpected)
    result = diagnose(config)
    assert result.exit_code == 0
    assert result.schema_supported is True
    assert result.structurally_suitable is True
    assert result.table_counts == DatabaseModel.from_database(relational_source).counts()
    assert result.actual_invocations == 0
    assert result.oracle_executed is False
    assert result.baseline_confirmed is False
    assert _digest(relational_source) == before
