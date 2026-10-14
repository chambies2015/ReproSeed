"""Read-only acquisition and row-subset construction for the supported SQLite shape."""

from __future__ import annotations

import math
import sqlite3
import time
from collections import defaultdict
from collections.abc import Iterable, Set
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Key = int | str
KeyFamily = Literal["INTEGER", "TEXT"]
RowId = tuple[str, Key]


class DatabaseError(ValueError):
    """An invalid database, unsupported schema, or failed private database operation."""


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _identifier_key(identifier: str) -> str:
    # SQLite folds ASCII identifiers; Python casefold would also merge distinct Unicode names.
    return identifier.translate(
        str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    )


def _readonly(path: Path, *, timeout_seconds: float = 5.0) -> sqlite3.Connection:
    if not path.is_file():
        raise DatabaseError(f"Database is not a regular file: {path}")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout_seconds)


def _sidecars(path: Path) -> tuple[Path, ...]:
    return tuple(path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal"))


def _reserve_destination(source: Path, destination: Path) -> None:
    canonical_source = source.resolve()
    protected = {
        path.resolve()
        for path in (canonical_source, *_sidecars(canonical_source), *_sidecars(source))
    }
    if destination.resolve() in protected:
        raise DatabaseError("Database destination must differ from its source and SQLite sidecars")
    for path in (destination, *_sidecars(destination)):
        if path.exists() or path.is_symlink():
            raise DatabaseError(f"Refusing to overwrite an existing database path: {path}")
    try:
        with destination.open("xb"):
            pass
    except OSError as exc:
        raise DatabaseError(f"Cannot create database destination: {destination}: {exc}") from exc


def _remove_failed_destination(destination: Path) -> None:
    # These paths were absent before the private operation. Never remove source files.
    for path in (destination, *_sidecars(destination)):
        path.unlink(missing_ok=True)


def snapshot(source: Path, destination: Path, timeout_seconds: float = 5.0) -> None:
    """Acquire a consistent backup, including committed WAL, without issuing source writes.

    Backup work is incremental and both lock retries and repeated restarts share one deadline.
    SQLite's read-only WAL handling may still use its normal shared-memory sidecar.
    """
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise DatabaseError("Snapshot timeout must be a finite positive number")
    deadline = time.monotonic() + timeout_seconds

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() >= deadline:
            raise DatabaseError("Snapshot acquisition timed out")

    # Zero busy timeout keeps each backup step responsive to the progress deadline.
    try:
        with closing(_readonly(source, timeout_seconds=0.0)) as original:
            _reserve_destination(source, destination)
            try:
                with closing(sqlite3.connect(destination, timeout=0.0)) as target:
                    original.backup(target, pages=64, progress=progress, sleep=0.01)
            except BaseException:
                _remove_failed_destination(destination)
                raise
    except (sqlite3.Error, OSError) as exc:
        raise DatabaseError(f"Snapshot acquisition failed: {exc}") from exc


def _validate_integrity(connection: sqlite3.Connection) -> None:
    try:
        results = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as exc:
        if "no such collation sequence" in str(exc):
            raise DatabaseError("Unsupported schema: unavailable collation metadata") from exc
        raise
    if results != [("ok",)]:
        raise DatabaseError(f"Database integrity_check failed ({len(results)} reported problems)")


def _validate_foreign_keys(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise DatabaseError("Database foreign_key_check failed: foreign-key violations exist")


def _validate_connection(connection: sqlite3.Connection) -> None:
    _validate_integrity(connection)
    _validate_foreign_keys(connection)


def validate_database(path: Path) -> None:
    """Perform full structural and foreign-key checks through a read-only connection."""
    try:
        with closing(_readonly(path)) as connection:
            _validate_connection(connection)
    except (sqlite3.Error, OSError) as exc:
        raise DatabaseError(f"Database validation failed: {exc}") from exc


def compact(source: Path, destination: Path) -> None:
    """VACUUM INTO a new fixture from private pre-oracle state, removing unused pages."""
    try:
        with closing(_readonly(source)) as connection:
            _validate_connection(connection)
            _reserve_destination(source, destination)
            try:
                connection.execute("VACUUM INTO ?", (str(destination.resolve()),))
                validate_database(destination)
            except BaseException:
                _remove_failed_destination(destination)
                raise
    except (sqlite3.Error, OSError) as exc:
        raise DatabaseError(f"Database compaction failed: {exc}") from exc


@dataclass(frozen=True)
class _Table:
    name: str
    primary_key: str
    key_family: KeyFamily
    column_types: dict[str, str]


@dataclass(frozen=True)
class DatabaseModel:
    """Stable row identities and reverse foreign-key edges from pristine private state."""

    rows: tuple[RowId, ...]
    _tables: tuple[_Table, ...]
    _dependents: dict[RowId, frozenset[RowId]]

    @classmethod
    def from_database(cls, path: Path) -> DatabaseModel:
        try:
            with closing(_readonly(path)) as connection:
                _validate_integrity(connection)
                tables = _read_tables(connection)
                rows: list[RowId] = []
                for table in tables:
                    _validate_key_storage(connection, table, table.primary_key, primary=True)
                    sql = (
                        f"SELECT {_quote(table.primary_key)} FROM {_quote(table.name)} "
                        "ORDER BY 1 COLLATE BINARY"
                    )
                    for (value,) in _key_rows(connection, sql):
                        if not isinstance(value, int | str):
                            raise DatabaseError("Invalid primary-key value")
                        rows.append((table.name, value))
                dependents = _read_dependencies(connection, tables)
                _validate_foreign_keys(connection)
                return cls(tuple(rows), tables, dependents)
        except UnicodeError as exc:
            raise DatabaseError("Unsupported schema: malformed TEXT encoding") from exc
        except (sqlite3.Error, OSError) as exc:
            if "Could not decode" in str(exc):
                raise DatabaseError("Unsupported schema: malformed TEXT encoding") from exc
            raise DatabaseError(f"Database modeling failed: {exc}") from exc

    def counts(self, retained: Iterable[RowId] | None = None) -> dict[str, int]:
        selected = set(self.rows if retained is None else retained)
        self._check_rows(selected)
        counts = dict.fromkeys((table.name for table in self._tables), 0)
        for table, _key in selected:
            counts[table] += 1
        return counts

    def _check_rows(self, selected: Set[RowId]) -> None:
        if not selected <= set(self.rows):
            raise DatabaseError("Row identities do not belong to this pristine database model")

    def deletion_closure(self, seeds: Iterable[RowId], retained: Set[RowId]) -> frozenset[RowId]:
        """Include retained dependents recursively, terminating self-references and cycles."""
        self._check_rows(retained)
        seed_set = set(seeds)
        self._check_rows(seed_set)
        pending = list(seed_set.intersection(retained))
        removed: set[RowId] = set()
        while pending:
            row = pending.pop()
            if row in removed:
                continue
            removed.add(row)
            pending.extend(self._dependents.get(row, frozenset()).intersection(retained) - removed)
        return frozenset(removed)

    def materialize(self, pristine: Path, retained: Set[RowId], destination: Path) -> None:
        """Construct and validate a private subset; DELETE actions never alter retained values."""
        self._check_rows(retained)
        snapshot(pristine, destination)
        try:
            with closing(sqlite3.connect(destination)) as connection:
                # This must happen outside the DELETE transaction. All deletions are explicit.
                connection.execute("PRAGMA foreign_keys = OFF")
                with connection:
                    for table in self._tables:
                        sql = (
                            f"DELETE FROM {_quote(table.name)} "
                            f"WHERE {_quote(table.primary_key)} COLLATE BINARY = ?"
                        )
                        deleted = (
                            (key,)
                            for name, key in self.rows
                            if name == table.name and (name, key) not in retained
                        )
                        connection.executemany(sql, deleted)
                connection.execute("PRAGMA foreign_keys = ON")
                if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
                    raise DatabaseError("Cannot enable foreign-key validation on candidate")
                _validate_connection(connection)
        except BaseException as exc:
            _remove_failed_destination(destination)
            if isinstance(exc, sqlite3.Error | OSError):
                raise DatabaseError(f"Candidate construction failed: {exc}") from exc
            raise


def _read_tables(connection: sqlite3.Connection) -> tuple[_Table, ...]:
    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise DatabaseError("SQLite 3.37 or newer is required for reliable table metadata")
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE type = 'trigger' LIMIT 1").fetchone():
        raise DatabaseError("Unsupported schema: triggers are not supported")
    tables: list[_Table] = []
    for entry in sorted(connection.execute("PRAGMA main.table_list"), key=lambda row: row[1]):
        _schema, name, kind, _ncol, without_rowid, _strict = entry[:6]
        if name.startswith("sqlite_") or kind == "view":
            continue
        if kind != "table":
            raise DatabaseError(f"Unsupported schema: {kind} table {name!r}")
        if without_rowid:
            raise DatabaseError(f"Unsupported schema: WITHOUT ROWID table {name!r}")
        columns = connection.execute(f"PRAGMA main.table_xinfo({_quote(name)})").fetchall()
        if any(column[6] != 0 for column in columns):
            raise DatabaseError(f"Unsupported schema: generated or hidden columns in {name!r}")
        primary = [column for column in columns if column[5] != 0]
        if len(primary) != 1 or primary[0][2].strip().upper() not in {"INTEGER", "TEXT"}:
            raise DatabaseError(
                f"Unsupported schema: {name!r} requires one INTEGER or TEXT PRIMARY KEY"
            )
        family: KeyFamily = "TEXT" if primary[0][2].strip().upper() == "TEXT" else "INTEGER"
        # INTEGER PRIMARY KEY DESC is not a rowid alias and can contain NULL/noninteger keys.
        indexes = connection.execute(f"PRAGMA main.index_list({_quote(name)})").fetchall()
        primary_indexes = [index for index in indexes if index[3] == "pk"]
        if family == "INTEGER" and primary_indexes:
            raise DatabaseError(
                f"Unsupported schema: non-rowid-alias INTEGER primary key in {name!r}"
            )
        if family == "TEXT":
            if len(primary_indexes) != 1:
                raise DatabaseError("Unsupported schema: TEXT primary-key index metadata")
            index = primary_indexes[0]
            if index[2] != 1 or index[4] != 0:
                raise DatabaseError("Unsupported schema: TEXT primary-key index metadata")
            _binary_key_index(connection, index[1], primary[0][0], primary[0][1])
            _binary_column_collation(connection, name, primary[0][1])
        types = {column[1]: column[2] for column in columns}
        tables.append(_Table(name, primary[0][1], family, types))
    return tuple(tables)


def _binary_key_index(
    connection: sqlite3.Connection, index: str, column_id: int, column_name: str
) -> None:
    keys = [
        entry
        for entry in connection.execute(f"PRAGMA main.index_xinfo({_quote(index)})")
        if entry[5] == 1
    ]
    if (
        len(keys) != 1
        or keys[0][1] != column_id
        or keys[0][2] != column_name
        or not isinstance(keys[0][4], str)
        or keys[0][4].upper() != "BINARY"
    ):
        raise DatabaseError("Unsupported schema: TEXT key collation must be BINARY")


def _binary_column_collation(
    connection: sqlite3.Connection, table_name: str, primary_key: str
) -> None:
    # A table-level PK can override its column's collation. SQLite FK equality uses the
    # column default, so a BINARY PK index alone is insufficient. Ask SQLite to derive
    # that default in an empty, isolated schema probe; never parse CREATE TABLE SQL.
    declaration = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = ?", (table_name,)
    ).fetchone()
    if declaration is None or not isinstance(declaration[0], str):
        raise DatabaseError("Unsupported schema: TEXT primary-key collation metadata")
    probe_name = "reproseed_column_collation"
    while _identifier_key(probe_name) == _identifier_key(table_name):
        probe_name += "_"
    try:
        with closing(sqlite3.connect(":memory:")) as probe:
            probe.execute(declaration[0])
            probe.execute(
                f"CREATE INDEX {_quote(probe_name)} ON {_quote(table_name)}({_quote(primary_key)})"
            )
            columns = probe.execute(f"PRAGMA table_xinfo({_quote(table_name)})").fetchall()
            column_id = next(column[0] for column in columns if column[1] == primary_key)
            _binary_key_index(probe, probe_name, column_id, primary_key)
    except sqlite3.Error as exc:
        raise DatabaseError("Unsupported schema: TEXT primary-key collation metadata") from exc


def _key_rows(connection: sqlite3.Connection, sql: str) -> list[tuple[object, ...]]:
    try:
        return connection.execute(sql).fetchall()
    except (sqlite3.Error, UnicodeError) as exc:
        if isinstance(exc, UnicodeError) or "Could not decode" in str(exc):
            raise DatabaseError("Unsupported schema: malformed TEXT encoding") from exc
        raise


def _validate_key_storage(
    connection: sqlite3.Connection,
    table: _Table,
    column: str,
    *,
    primary: bool,
    family: KeyFamily | None = None,
) -> None:
    family = table.key_family if family is None else family
    identifier = _quote(column)
    if (
        primary
        and family == "TEXT"
        and connection.execute(
            f"SELECT 1 FROM {_quote(table.name)} WHERE {identifier} IS NULL LIMIT 1"
        ).fetchone()
    ):
        raise DatabaseError("Unsupported schema: NULL TEXT primary-key value")
    storage = "text" if family == "TEXT" else "integer"
    if connection.execute(
        f"SELECT 1 FROM {_quote(table.name)} "
        f"WHERE {identifier} IS NOT NULL AND typeof({identifier}) != ? LIMIT 1",
        (storage,),
    ).fetchone():
        role = "primary-key" if primary else "foreign-key"
        prefix = "Nontext" if family == "TEXT" else "Noninteger"
        raise DatabaseError(f"{prefix} {role} value in {table.name!r}")


def _read_dependencies(
    connection: sqlite3.Connection, tables: tuple[_Table, ...]
) -> dict[RowId, frozenset[RowId]]:
    by_name = {_identifier_key(table.name): table for table in tables}
    edges: dict[RowId, set[RowId]] = defaultdict(set)
    for table in tables:
        groups: dict[int, list[tuple[object, ...]]] = defaultdict(list)
        for foreign_key in connection.execute(
            f"PRAGMA main.foreign_key_list({_quote(table.name)})"
        ):
            groups[foreign_key[0]].append(foreign_key)
        columns = {_identifier_key(name): name for name in table.column_types}
        for group in groups.values():
            if len(group) != 1:
                raise DatabaseError(f"Unsupported schema: composite foreign key in {table.name!r}")
            _fk_id, _seq, parent_name, source_column, target_column, *_actions = group[0]
            if not isinstance(parent_name, str) or not isinstance(source_column, str):
                raise DatabaseError(f"Invalid foreign-key metadata in {table.name!r}")
            parent = by_name.get(_identifier_key(parent_name))
            if parent is None:
                raise DatabaseError(f"Unsupported schema: foreign-key parent {parent_name!r}")
            if target_column is not None and (
                not isinstance(target_column, str)
                or _identifier_key(target_column) != _identifier_key(parent.primary_key)
            ):
                raise DatabaseError(
                    f"Unsupported schema: foreign key must target {parent.name!r} PK"
                )
            actual_column = columns.get(_identifier_key(source_column))
            if actual_column is None:
                raise DatabaseError(f"Invalid foreign-key metadata in {table.name!r}")
            declared_type = table.column_types[actual_column].strip().upper()
            if parent.key_family == "INTEGER" and "INT" not in declared_type:
                raise DatabaseError(f"Unsupported schema: noninteger foreign key in {table.name!r}")
            if parent.key_family == "TEXT" and declared_type != "TEXT":
                raise DatabaseError(f"Unsupported schema: nontext foreign key in {table.name!r}")
            _validate_key_storage(
                connection, table, actual_column, primary=False, family=parent.key_family
            )
            sql = (
                f"SELECT {_quote(table.primary_key)}, {_quote(actual_column)} "
                f"FROM {_quote(table.name)} WHERE {_quote(actual_column)} IS NOT NULL"
            )
            for child_key, parent_key in _key_rows(connection, sql):
                if not isinstance(child_key, int | str) or not isinstance(parent_key, int | str):
                    raise DatabaseError("Invalid foreign-key value")
                edges[(parent.name, parent_key)].add((table.name, child_key))
    return {row: frozenset(children) for row, children in edges.items()}
