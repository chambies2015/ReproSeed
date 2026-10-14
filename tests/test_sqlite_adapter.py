from __future__ import annotations

import hashlib
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from reproseed.sqlite_adapter import (
    DatabaseError,
    DatabaseModel,
    compact,
    snapshot,
    validate_database,
)


def create(path: Path, script: str) -> Path:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(script)
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def relational(tmp_path: Path) -> Path:
    return create(
        tmp_path / "source.sqlite3",
        """
        PRAGMA foreign_keys = ON;
        PRAGMA user_version = 17;
        PRAGMA application_id = 123456;
        CREATE TABLE owners(id INTEGER PRIMARY KEY, label TEXT NOT NULL);
        CREATE TABLE projects(id INTEGER PRIMARY KEY, owner_id INTEGER REFERENCES owners(id)
                             ON DELETE SET NULL, label TEXT NOT NULL);
        CREATE TABLE entries(id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id)
                            ON DELETE CASCADE, label TEXT NOT NULL);
        CREATE TABLE empty(id INTEGER PRIMARY KEY);
        CREATE INDEX entries_label ON entries(label);
        CREATE VIEW labels AS SELECT label FROM entries;
        INSERT INTO owners VALUES(-8, 'kept owner'), (91, 'removed owner');
        INSERT INTO projects VALUES(24, -8, 'kept project'), (51, 91, 'removed project'),
                                   (74, NULL, 'nullable project');
        INSERT INTO entries VALUES(-19, 24, 'kept entry'), (87, 51, 'removed entry'),
                                  (89, 74, 'nullable descendant');
        """,
    )


def schema(path: Path) -> list[tuple[str, str, str | None]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(
            "SELECT type, name, sql FROM sqlite_schema ORDER BY name"
        ).fetchall()


def test_snapshot_and_model_protect_source_and_include_empty_tables(
    relational: Path, tmp_path: Path
):
    before = digest(relational)
    private = tmp_path / "snapshot.sqlite3"
    snapshot(relational, private)
    model = DatabaseModel.from_database(private)
    assert model.rows == (
        ("entries", -19),
        ("entries", 87),
        ("entries", 89),
        ("owners", -8),
        ("owners", 91),
        ("projects", 24),
        ("projects", 51),
        ("projects", 74),
    )
    assert model.counts() == {"empty": 0, "entries": 3, "owners": 2, "projects": 3}
    assert digest(relational) == before
    assert schema(private) == schema(relational)


def test_dependency_closure_and_materialization_preserve_retained_values(
    relational: Path, tmp_path: Path
):
    model = DatabaseModel.from_database(relational)
    original = digest(relational)
    retained = frozenset(model.rows)
    deleted = model.deletion_closure([("owners", 91)], retained)
    assert deleted == frozenset({("owners", 91), ("projects", 51), ("entries", 87)})
    candidate = tmp_path / "candidate.sqlite3"
    model.materialize(relational, retained - deleted, candidate)
    validate_database(candidate)
    assert schema(candidate) == schema(relational)
    with closing(sqlite3.connect(candidate)) as connection:
        assert connection.execute("SELECT * FROM projects ORDER BY id").fetchall() == [
            (24, -8, "kept project"),
            (74, None, "nullable project"),
        ]
        assert connection.execute("SELECT * FROM entries ORDER BY id").fetchall() == [
            (-19, 24, "kept entry"),
            (89, 74, "nullable descendant"),
        ]
    assert digest(relational) == original
    # A later materialization always starts from pristine state, including after oracle writes.
    with closing(sqlite3.connect(candidate)) as connection:
        connection.execute("UPDATE entries SET label = 'oracle mutated'")
        connection.commit()
    next_candidate = tmp_path / "next.sqlite3"
    model.materialize(relational, retained, next_candidate)
    with closing(sqlite3.connect(next_candidate)) as connection:
        assert connection.execute("SELECT label FROM entries WHERE id = -19").fetchone() == (
            "kept entry",
        )


def test_invalid_subset_is_rejected_before_it_can_be_used(relational: Path, tmp_path: Path):
    model = DatabaseModel.from_database(relational)
    candidate = tmp_path / "invalid.sqlite3"
    with pytest.raises(DatabaseError, match="foreign_key_check"):
        model.materialize(relational, frozenset(model.rows) - {("owners", 91)}, candidate)
    assert not candidate.exists()
    assert not Path(str(candidate) + "-wal").exists()


def test_cycles_self_references_nullable_links_and_quoted_identifiers(tmp_path: Path):
    source = create(
        tmp_path / "quoted.sqlite3",
        """
        CREATE TABLE "a odd"("k""ey" INTEGER PRIMARY KEY,
                             "b ref" INTEGER REFERENCES "B odd"("ID"),
                             "own ref" INTEGER REFERENCES "a odd"("k""ey"));
        CREATE TABLE "B odd"("ID" INTEGER PRIMARY KEY,
                             "a ref" INTEGER REFERENCES "a odd"("k""ey"));
        INSERT INTO "a odd" VALUES(-20, 72, -20), (99, NULL, NULL);
        INSERT INTO "B odd" VALUES(72, -20), (83, 99);
        """,
    )
    model = DatabaseModel.from_database(source)
    rows = frozenset(model.rows)
    cycle = model.deletion_closure([("a odd", -20)], rows)
    assert cycle == frozenset({("a odd", -20), ("B odd", 72)})
    assert model.deletion_closure([("a odd", 99)], rows) == frozenset(
        {("a odd", 99), ("B odd", 83)}
    )
    destination = tmp_path / "cycle.sqlite3"
    model.materialize(source, rows - cycle, destination)
    validate_database(destination)
    assert DatabaseModel.from_database(destination).counts() == {"B odd": 1, "a odd": 1}


def test_case_insensitive_fk_metadata_and_implicit_pk_target(tmp_path: Path):
    source = create(
        tmp_path / "case.sqlite3",
        """
        CREATE TABLE Parent(ID INTEGER PRIMARY KEY);
        CREATE TABLE Child(ID INTEGER PRIMARY KEY, parent_id INT REFERENCES pArEnT);
        INSERT INTO Parent VALUES(300);
        INSERT INTO Child VALUES(900, 300);
        """,
    )
    model = DatabaseModel.from_database(source)
    assert model.deletion_closure([("Parent", 300)], frozenset(model.rows)) == frozenset(model.rows)


def test_supported_strict_and_autoincrement_metadata_survive_compaction(tmp_path: Path):
    source = create(
        tmp_path / "strict.sqlite3",
        """
        PRAGMA page_size = 8192;
        PRAGMA encoding = 'UTF-16';
        PRAGMA auto_vacuum = INCREMENTAL;
        PRAGMA user_version = 42;
        PRAGMA application_id = 123;
        CREATE TABLE parent(id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT) STRICT;
        CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INT REFERENCES parent(id)) STRICT;
        INSERT INTO parent VALUES(4, 'retained'), (98, 'remove');
        INSERT INTO child VALUES(83, 4);
        """,
    )
    before = digest(source)
    model = DatabaseModel.from_database(source)
    assert model.counts() == {"child": 1, "parent": 2}  # sqlite_sequence is not reducible.
    private = tmp_path / "private.sqlite3"
    model.materialize(source, frozenset(model.rows) - {("parent", 98)}, private)
    final = tmp_path / "final.sqlite3"
    compact(private, final)
    assert schema(final) == schema(source)
    with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(final)) as output:
        for pragma in ("user_version", "application_id", "encoding", "page_size", "auto_vacuum"):
            assert (
                output.execute(f"PRAGMA {pragma}").fetchone()
                == original.execute(f"PRAGMA {pragma}").fetchone()
            )
        assert output.execute("SELECT * FROM sqlite_sequence").fetchall() == [("parent", 98)]
        assert output.execute("PRAGMA freelist_count").fetchone() == (0,)
    assert digest(source) == before


def test_compact_removes_deleted_payload_and_unused_pages(tmp_path: Path):
    source = create(
        tmp_path / "large.sqlite3", "CREATE TABLE payloads(id INTEGER PRIMARY KEY, value TEXT);"
    )
    secret = "REMOVED_SYNTHETIC_PAYLOAD_" * 500
    with closing(sqlite3.connect(source)) as connection:
        connection.executemany(
            "INSERT INTO payloads VALUES(?, ?)", [(i, secret) for i in range(40)]
        )
        connection.execute("INSERT INTO payloads VALUES(90, 'kept')")
        connection.commit()
    model = DatabaseModel.from_database(source)
    private = tmp_path / "private.sqlite3"
    model.materialize(source, frozenset({("payloads", 90)}), private)
    final = tmp_path / "final.sqlite3"
    compact(private, final)
    assert final.stat().st_size < private.stat().st_size
    assert b"REMOVED_SYNTHETIC_PAYLOAD_" not in final.read_bytes()
    assert DatabaseModel.from_database(final).rows == (("payloads", 90),)


def test_materialize_empty_database_and_reject_unknown_identities(relational: Path, tmp_path: Path):
    model = DatabaseModel.from_database(relational)
    destination = tmp_path / "empty.sqlite3"
    model.materialize(relational, frozenset(), destination)
    assert DatabaseModel.from_database(destination).counts() == dict.fromkeys(model.counts(), 0)
    assert model.deletion_closure([("owners", -8)], frozenset()) == frozenset()
    with pytest.raises(DatabaseError, match="identities"):
        model.materialize(relational, frozenset({("owners", 3)}), tmp_path / "unknown.sqlite3")
    with pytest.raises(DatabaseError, match="identities"):
        model.counts([("missing", 0)])


@pytest.mark.parametrize(
    "script",
    [
        "CREATE TABLE t(value TEXT)",
        "CREATE TABLE t(id VARCHAR PRIMARY KEY)",
        "CREATE TABLE t(a INTEGER, b INTEGER, PRIMARY KEY(a, b))",
        "CREATE TABLE t(id INTEGER PRIMARY KEY DESC)",
        "CREATE TABLE t(id INTEGER PRIMARY KEY) WITHOUT ROWID",
        "CREATE TABLE t(id INTEGER PRIMARY KEY, doubled INTEGER GENERATED ALWAYS AS(id*2))",
        "CREATE TABLE t(id INTEGER PRIMARY KEY); CREATE TRIGGER tr AFTER DELETE ON t "
        "BEGIN INSERT INTO t VALUES(44); END",
        "CREATE TABLE p(id INTEGER PRIMARY KEY); "
        "CREATE TABLE t(id INTEGER PRIMARY KEY, parent TEXT REFERENCES p(id))",
        "CREATE TABLE p(id INTEGER PRIMARY KEY, other INTEGER UNIQUE); "
        "CREATE TABLE t(id INTEGER PRIMARY KEY, parent INTEGER REFERENCES p(other))",
        "CREATE TABLE p(id INTEGER PRIMARY KEY, other INTEGER, UNIQUE(id, other)); "
        "CREATE TABLE t(id INTEGER PRIMARY KEY, a INTEGER, b INTEGER, "
        "FOREIGN KEY(a, b) REFERENCES p(id, other))",
    ],
)
def test_unsupported_shapes_fail_without_source_modification(tmp_path: Path, script: str):
    source = create(tmp_path / "unsupported.sqlite3", script)
    before = digest(source)
    with pytest.raises(DatabaseError, match="Unsupported schema"):
        DatabaseModel.from_database(source)
    assert digest(source) == before


def test_virtual_tables_are_rejected_without_source_modification(tmp_path: Path):
    source = create(
        tmp_path / "virtual.sqlite3", "CREATE VIRTUAL TABLE text_search USING fts5(text)"
    )
    before = digest(source)
    with pytest.raises(DatabaseError, match="Unsupported schema.*(virtual|shadow)"):
        DatabaseModel.from_database(source)
    assert digest(source) == before


def test_noninteger_fk_values_are_rejected_even_when_fk_check_passes(tmp_path: Path):
    # Build legacy storage with a real value, then simulate a declared type migration.
    # SQLite's ordinary-table integrity/FK checks accept 1.0, but row edges require integers.
    legacy = create(
        tmp_path / "legacy.sqlite3",
        """
        CREATE TABLE parent(id INTEGER PRIMARY KEY);
        CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id BLOB REFERENCES parent(id));
        INSERT INTO parent VALUES(1);
        INSERT INTO child VALUES(2, 1.0);
        PRAGMA writable_schema = ON;
        UPDATE sqlite_schema SET sql = replace(sql, 'parent_id BLOB', 'parent_id INTEGER')
        WHERE name = 'child';
        """,
    )
    validate_database(legacy)
    with pytest.raises(DatabaseError, match="Noninteger foreign-key value"):
        DatabaseModel.from_database(legacy)
    source = create(
        tmp_path / "types.sqlite3",
        """
        CREATE TABLE parent(id INTEGER PRIMARY KEY);
        CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));
        INSERT INTO parent VALUES(1);
        INSERT INTO child VALUES(2, X'31');
        """,
    )
    # Model storage validation rejects a BLOB before any link can become a row edge.
    with pytest.raises(DatabaseError, match="Noninteger foreign-key value"):
        DatabaseModel.from_database(source)
    # TEXT affinity with '1' passes SQLite's parent-affinity comparison, but is unsupported.
    alternate = create(
        tmp_path / "text.sqlite3",
        """
        CREATE TABLE parent(id INTEGER PRIMARY KEY);
        CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id TEXT REFERENCES parent(id));
        INSERT INTO parent VALUES(1);
        INSERT INTO child VALUES(2, '1');
        """,
    )
    validate_database(alternate)
    with pytest.raises(DatabaseError, match="noninteger foreign key"):
        DatabaseModel.from_database(alternate)


def test_invalid_database_and_foreign_keys_are_detected(tmp_path: Path):
    corrupted = tmp_path / "not-sqlite.sqlite3"
    corrupted.write_bytes(b"this is not an SQLite database")
    with pytest.raises(DatabaseError, match="validation failed"):
        validate_database(corrupted)
    with pytest.raises(DatabaseError):
        DatabaseModel.from_database(corrupted)
    invalid = create(
        tmp_path / "bad-fk.sqlite3",
        """
        CREATE TABLE parent(id INTEGER PRIMARY KEY);
        CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));
        INSERT INTO child VALUES(3, 99);
        """,
    )
    with pytest.raises(DatabaseError, match="foreign_key_check"):
        validate_database(invalid)
    with pytest.raises(DatabaseError, match="foreign_key_check"):
        DatabaseModel.from_database(invalid)


@pytest.fixture
def wal_source(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "wal.sqlite3"
    with closing(sqlite3.connect(path)) as writer:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute("CREATE TABLE data(id INTEGER PRIMARY KEY, label TEXT)")
        writer.commit()
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.execute("INSERT INTO data VALUES(71, 'committed in WAL')")
        writer.commit()
        assert Path(str(path) + "-wal").stat().st_size > 0
        yield path


def test_backup_includes_committed_uncheckpointed_wal(wal_source: Path, tmp_path: Path):
    before_main = digest(wal_source)
    wal = Path(str(wal_source) + "-wal")
    before_wal = digest(wal)
    destination = tmp_path / "snapshot.sqlite3"
    snapshot(wal_source, destination)
    with closing(sqlite3.connect(destination)) as connection:
        assert connection.execute("SELECT * FROM data").fetchall() == [(71, "committed in WAL")]
    assert digest(wal_source) == before_main
    assert digest(wal) == before_wal


def test_snapshot_locked_database_has_a_bounded_deadline(tmp_path: Path):
    source = create(tmp_path / "locked.sqlite3", "CREATE TABLE t(id INTEGER PRIMARY KEY)")
    destination = tmp_path / "timed-out.sqlite3"
    with closing(sqlite3.connect(source)) as blocker:
        blocker.execute("BEGIN EXCLUSIVE")
        start = time.monotonic()
        with pytest.raises(DatabaseError, match="timed out"):
            snapshot(source, destination, timeout_seconds=0.08)
        assert time.monotonic() - start < 1.5
    assert not destination.exists()


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("nan")])
def test_snapshot_rejects_nonfinite_or_nonpositive_timeout(
    relational: Path, tmp_path: Path, timeout: float
):
    destination = tmp_path / "bad-timeout.sqlite3"
    with pytest.raises(DatabaseError, match="finite positive"):
        snapshot(relational, destination, timeout)
    assert not destination.exists()


def test_database_operations_refuse_existing_destinations(relational: Path, tmp_path: Path):
    original = digest(relational)
    for operation in (snapshot, compact):
        with pytest.raises(DatabaseError, match="differ"):
            operation(relational, relational)
        with pytest.raises(DatabaseError, match="sidecars"):
            operation(relational, Path(str(relational) + "-wal"))
        existing = tmp_path / f"{operation.__name__}.sqlite3"
        existing.write_bytes(b"preserve this existing file")
        with pytest.raises(DatabaseError, match="overwrite"):
            operation(relational, existing)
        assert existing.read_bytes() == b"preserve this existing file"
        sidecar_target = tmp_path / f"{operation.__name__}-sidecar.sqlite3"
        sidecar = Path(str(sidecar_target) + "-wal")
        sidecar.write_bytes(b"preserve this sidecar")
        with pytest.raises(DatabaseError, match="overwrite"):
            operation(relational, sidecar_target)
        assert sidecar.read_bytes() == b"preserve this sidecar"
    assert digest(relational) == original


def test_snapshot_invalid_or_missing_source_cleans_private_destination(tmp_path: Path):
    missing = tmp_path / "missing.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    with pytest.raises(DatabaseError, match="regular file"):
        snapshot(missing, destination)
    assert not missing.exists()
    assert not destination.exists()
    invalid = tmp_path / "invalid.sqlite3"
    invalid.write_bytes(b"invalid bytes")
    with pytest.raises(DatabaseError, match="acquisition failed"):
        snapshot(invalid, destination)
    assert not destination.exists()
