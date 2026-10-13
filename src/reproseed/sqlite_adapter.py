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

RowId = tuple[str, int]


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


def _validate_connection(connection: sqlite3.Connection) -> None:
    results = connection.execute("PRAGMA integrity_check").fetchall()
    if results != [("ok",)]:
        raise DatabaseError(f"Database integrity_check failed ({len(results)} reported problems)")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise DatabaseError("Database foreign_key_check failed: foreign-key violations exist")


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
                _validate_connection(connection)
                tables = _read_tables(connection)
                rows: list[RowId] = []
                for table in tables:
                    sql = f"SELECT {_quote(table.primary_key)} FROM {_quote(table.name)} ORDER BY 1"
                    for (value,) in connection.execute(sql):
                        if not isinstance(value, int):
                            raise DatabaseError(f"Noninteger primary-key value in {table.name!r}")
                        rows.append((table.name, value))
                dependents = _read_dependencies(connection, tables)
                return cls(tuple(rows), tables, dependents)
        except (sqlite3.Error, OSError) as exc:
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
                            f"WHERE {_quote(table.primary_key)} = ?"
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
        if len(primary) != 1 or primary[0][2].strip().upper() != "INTEGER":
            raise DatabaseError(f"Unsupported schema: {name!r} requires one INTEGER PRIMARY KEY")
        # INTEGER PRIMARY KEY DESC is not a rowid alias and can contain NULL/noninteger keys.
        indexes = connection.execute(f"PRAGMA main.index_list({_quote(name)})")
        if any(index[3] == "pk" for index in indexes):
            raise DatabaseError(
                f"Unsupported schema: non-rowid-alias INTEGER primary key in {name!r}"
            )
        types = {column[1]: column[2] for column in columns}
        tables.append(_Table(name, primary[0][1], types))
    return tuple(tables)


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
            if actual_column is None or "INT" not in table.column_types[actual_column].upper():
                raise DatabaseError(f"Unsupported schema: noninteger foreign key in {table.name!r}")
            sql = (
                f"SELECT {_quote(table.primary_key)}, {_quote(actual_column)} "
                f"FROM {_quote(table.name)} WHERE {_quote(actual_column)} IS NOT NULL"
            )
            for child_key, parent_key in connection.execute(sql):
                if not isinstance(parent_key, int):
                    raise DatabaseError(f"Noninteger foreign-key value in {table.name!r}")
                edges[(parent.name, parent_key)].add((table.name, child_key))
    return {row: frozenset(children) for row, children in edges.items()}
