"""Independent, bounded SQLite fixture descriptions for the M2f developer campaign.

This module does not import ReproSeed. Relationships are obtained by SQLite joins
using the authored FK descriptions, rather than adapter metadata or private graphs.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import random
import sqlite3
from contextlib import closing

GENERATOR_VERSION = 1
FAMILIES = (
    ("INTEGER",),
    ("TEXT",),
    ("INTEGER", "INTEGER"),
    ("INTEGER", "TEXT"),
    ("TEXT", "INTEGER"),
    ("TEXT", "TEXT"),
)
LAYOUTS = ("rowid", "strict", "without_rowid", "strict_without_rowid")


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(table, values):
    return table, values[0] if len(values) == 1 else tuple(values)


def ordered(rows):
    # All generated PK components are exact integers/text. Do not rely on the
    # production sort helper when authoring expected identity inventories.
    def order(row):
        key = row[1] if isinstance(row[1], tuple) else (row[1],)
        return row[0], tuple((0, value) if type(value) is int else (1, value) for value in key)

    return sorted(rows, key=order)


@dataclasses.dataclass
class ForeignKey:
    columns: tuple[str, ...]
    parent: str
    implicit: bool = False
    action: str = "NO ACTION"


@dataclasses.dataclass
class Table:
    name: str
    families: tuple[str, ...]
    columns: list[tuple[str, str]]
    rows: list[tuple]
    foreign_keys: list[ForeignKey] = dataclasses.field(default_factory=list)

    @property
    def primary(self):
        return tuple(f"k{i}" for i in range(len(self.families)))


@dataclasses.dataclass
class Fixture:
    template: str
    layout: str
    tables: list[Table]
    seed: int
    ordinal: int

    def metadata(self):
        return {"generator_version": GENERATOR_VERSION, **dataclasses.asdict(self)}


def keys(families, count, salt):
    # Reused components detect accidental prefix-only composite joins; scalar
    # keys include negative/sparse integers and empty, quoted and Unicode text.
    integers = (-991 - salt * 1000, 31 + salt * 1000, 700003 + salt * 1000, 47 + salt * 1000)
    texts = ("", "quote\"/'é", "ASCII", "ΑSCII")
    if len(families) == 1:
        return [(integers[i],) if families[0] == "INTEGER" else (texts[i],) for i in range(count)]
    first = integers if families[0] == "INTEGER" else texts
    second = integers if families[1] == "INTEGER" else texts
    pairs = ((0, 1), (1, 1), (0, 2), (1, 2))
    return [(first[a], second[b]) for a, b in pairs[:count]]


def fixture(seed, ordinal):
    if not 0 <= ordinal < 256:
        raise ValueError("supported fixture ordinal must be 0..255")
    rng = random.Random(seed * 1009 + ordinal)
    family = FAMILIES[ordinal % len(FAMILIES)]
    layout = LAYOUTS[(ordinal // len(FAMILIES)) % len(LAYOUTS)]
    tiny = ordinal < 24 or ordinal % 7 == 0
    count = 2 if tiny else 4
    # The first 24 cover every key/layout combination with <= eight rows.
    parent = Table('parent "α"', family, [], [])
    child = Table("child", FAMILIES[(ordinal + 3) % 6], [], [])
    leaf = Table("leaf", ("INTEGER",), [], [])
    unrelated = Table("unrelated", ("TEXT",), [], [("untouched", "independent")])
    empty = Table("empty Ω", FAMILIES[(ordinal + 1) % 6], [], [])
    # SQLite identifier folding is ASCII-only: K and Kelvin sign are distinct
    # table names even though Python casefold would merge them.
    ascii_name = Table("K", ("TEXT",), [], [("same", "ASCII identifier")])
    unicode_name = Table("K", ("TEXT",), [], [("same", "Unicode identifier")])
    tables = [parent, child, leaf, unrelated, empty, ascii_name, unicode_name]
    by_name = {table.name: table for table in tables}
    pkeys, ckeys = keys(parent.families, count, ordinal), keys(child.families, count, ordinal + 1)

    def reference(table, prefix, target, implicit, action):
        columns = tuple(prefix + str(i) for i in range(len(target.families)))
        table.columns.extend(zip(columns, target.families, strict=True))
        table.foreign_keys.append(ForeignKey(columns, target.name, implicit, action))

    reference(child, "parent", parent, ordinal % 2 == 0, "CASCADE")
    reference(leaf, "child", child, ordinal % 2 != 0, "SET NULL")
    reference(leaf, "parent", parent, False, "SET DEFAULT")
    # Every broad fixture contains a self link and an explicit cycle; nullable
    # FK components remain stored and must survive candidate construction.
    if not tiny:
        reference(parent, "self", parent, False, "NO ACTION")
        reference(parent, "cycle", child, True, "CASCADE")
    for i, key in enumerate(pkeys):
        extra = () if tiny else (*pkeys[(i + 1) % count], *ckeys[i])
        parent.rows.append((*key, f"parent-{i}", *extra))
    for i, key in enumerate(ckeys):
        target = list(pkeys[i])
        if not tiny and i == count - 1:
            target[-1] = None
        child.rows.append((*key, f"child-{i}", *target))
    leaf.rows.append((-7007, "shared descendant", *ckeys[0], *pkeys[1]))
    if not tiny:
        # Different FK parent families in one child, two declaration groups and
        # a diamond ensure policy cannot be selected from the child's own PK.
        for i in (1, 2):
            leaf.rows.append((i * 100001, f"leaf-{i}", *ckeys[i], *pkeys[(i + 1) % count]))
    if ordinal % 31 == 30:
        for table in tables:
            table.rows = []
    for table in tables:
        rng.shuffle(table.rows)
        for fk in table.foreign_keys:
            assert fk.parent in by_name
    return Fixture(
        f"relational-{family}-{layout}-{'tiny' if tiny else 'cycle'}", layout, tables, seed, ordinal
    )


def build(spec, path, *, reverse=False):
    """Execute independently authored declarations; no inferred adapter metadata."""
    if path.exists():
        raise FileExistsError(path)
    suffix = {
        "rowid": "",
        "strict": " STRICT",
        "without_rowid": " WITHOUT ROWID",
        "strict_without_rowid": " STRICT, WITHOUT ROWID",
    }[spec.layout]
    by_name = {table.name: table for table in spec.tables}
    with closing(sqlite3.connect(path)) as con, con:
        for table in spec.tables:
            declarations = [
                f"{quote(column)} {family} NOT NULL"
                for column, family in zip(table.primary, table.families, strict=True)
            ]
            declarations.append('"payload" TEXT NOT NULL')
            declarations.extend(f"{quote(name)} {family}" for name, family in table.columns)
            declarations.append("PRIMARY KEY(" + ",".join(map(quote, table.primary)) + ")")
            for fk in table.foreign_keys:
                target = (
                    ""
                    if fk.implicit
                    else "(" + ",".join(map(quote, by_name[fk.parent].primary)) + ")"
                )
                declarations.append(
                    "FOREIGN KEY(" + ",".join(map(quote, fk.columns)) + ") "
                    f"REFERENCES {quote(fk.parent)}{target} "
                    f"ON DELETE {fk.action} ON UPDATE CASCADE"
                )
            con.execute(
                f"CREATE TABLE {quote(table.name)} (" + ",".join(declarations) + ")" + suffix
            )
            con.execute(
                f"CREATE INDEX {quote('payload-' + table.name)} ON {quote(table.name)}(payload)"
            )
        for table in spec.tables:
            width = len(table.families) + 1 + len(table.columns)
            rows = list(reversed(table.rows)) if reverse else table.rows
            con.executemany(
                f"INSERT INTO {quote(table.name)} VALUES ("
                + ",".join("?" for _ in range(width))
                + ")",
                rows,
            )
        con.execute("PRAGMA user_version=1616")
        con.execute("PRAGMA application_id=1381190738")
        assert con.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def inventory(spec, path):
    """SQLite is the source of declared identities and full retained row values."""
    identities, values = set(), {}
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        for table in spec.tables:
            for row in con.execute(f"SELECT * FROM {quote(table.name)}"):
                row_id = identity(table.name, row[: len(table.families)])
                identities.add(row_id)
                values[row_id] = row
    return frozenset(identities), values


def sql_edges(spec, path):
    """Parent-left SQL equality applies SQLite's parent affinity/collation.

    Complete keys and explicit any-NULL exclusion are authored from the schema
    template; this does not use PRAGMA FK parsing or ReproSeed's graph/closure.
    """
    by_name = {table.name: table for table in spec.tables}
    edges = set()
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        for child in spec.tables:
            for fk in child.foreign_keys:
                parent = by_name[fk.parent]
                selected = ",".join("p." + quote(column) for column in parent.primary)
                selected += "," + ",".join("c." + quote(column) for column in child.primary)
                equality = " AND ".join(
                    f"p.{quote(p)} = c.{quote(c)}"
                    for p, c in zip(parent.primary, fk.columns, strict=True)
                )
                populated = " AND ".join(f"c.{quote(c)} IS NOT NULL" for c in fk.columns)
                for row in con.execute(
                    f"SELECT {selected} FROM {quote(parent.name)} p "
                    f"JOIN {quote(child.name)} c ON {equality} WHERE {populated}"
                ):
                    split = len(parent.primary)
                    edges.add(
                        (identity(parent.name, row[:split]), identity(child.name, row[split:]))
                    )
    return edges


def reference_closure(edges, seeds, retained):
    # A deliberately simple fixed-point scan, not the adapter's adjacency DFS.
    removed = set(seeds) & set(retained)
    while True:
        expanded = removed | {
            child for parent, child in edges if parent in removed and child in retained
        }
        if expanded == removed:
            return frozenset(removed)
        removed = expanded


def valid_retained(edges, retained):
    return all(child not in retained or parent in retained for parent, child in edges)


def subsets(rows, cap):
    """Enumerate all subsets only when the whole space fits the explicit cap."""
    rows = tuple(rows)
    if len(rows) > 8 or 2 ** len(rows) > cap:
        return []
    return [
        frozenset(group)
        for width in range(len(rows) + 1)
        for group in itertools.combinations(rows, width)
    ]


def schema_state(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        assert con.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        schema = con.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        tables = [row[1] for row in schema if row[0] == "table"]
        metadata = {
            table: {
                "columns": con.execute(f"PRAGMA table_xinfo({quote(table)})").fetchall(),
                "fks": con.execute(f"PRAGMA foreign_key_list({quote(table)})").fetchall(),
                "indexes": con.execute(f"PRAGMA index_list({quote(table)})").fetchall(),
            }
            for table in tables
        }
        for value in metadata.values():
            value["index_keys"] = {
                index[1]: con.execute(f"PRAGMA index_xinfo({quote(index[1])})").fetchall()
                for index in value["indexes"]
            }
        layouts = sorted(
            row[1:]
            for row in con.execute("PRAGMA table_list")
            if row[0] == "main" and row[1] in tables
        )
        return {
            "schema": schema,
            "metadata": metadata,
            "layouts": layouts,
            "user_version": con.execute("PRAGMA user_version").fetchone()[0],
            "application_id": con.execute("PRAGMA application_id").fetchone()[0],
        }


UNSUPPORTED = (
    ("arity", "CREATE TABLE bad(a INTEGER,b TEXT,c INTEGER,PRIMARY KEY(a,b,c));"),
    ("key-type", "CREATE TABLE bad(id REAL PRIMARY KEY); INSERT INTO bad VALUES(1.5);"),
    ("collation", "CREATE TABLE bad(id TEXT PRIMARY KEY COLLATE NOCASE);"),
    ("key-storage", "CREATE TABLE bad(id TEXT PRIMARY KEY); INSERT INTO bad VALUES(X'4142');"),
    ("null-key", "CREATE TABLE bad(id TEXT PRIMARY KEY); INSERT INTO bad VALUES(NULL);"),
    (
        "invalid-fk",
        "CREATE TABLE p(id INTEGER PRIMARY KEY); CREATE TABLE bad(id INTEGER "
        "PRIMARY KEY,p INTEGER REFERENCES p); INSERT INTO bad VALUES(1,404);",
    ),
    (
        "alternate-target",
        "CREATE TABLE p(id INTEGER PRIMARY KEY,other INTEGER UNIQUE); "
        "CREATE TABLE bad(id INTEGER PRIMARY KEY,p INTEGER REFERENCES p(other));",
    ),
    ("generated", "CREATE TABLE bad(id INTEGER PRIMARY KEY,g INTEGER GENERATED ALWAYS AS (id+1));"),
    (
        "trigger",
        "CREATE TABLE bad(id INTEGER PRIMARY KEY); CREATE TRIGGER change AFTER INSERT "
        "ON bad BEGIN UPDATE bad SET id=id WHERE id=new.id; END;",
    ),
    ("virtual", "CREATE VIRTUAL TABLE bad USING fts5(content);"),
    ("descending", "CREATE TABLE bad(a TEXT,b INTEGER,PRIMARY KEY(a DESC,b));"),
    (
        "fk-type",
        "CREATE TABLE p(id TEXT PRIMARY KEY); CREATE TABLE bad(id INTEGER PRIMARY KEY,"
        "p BLOB REFERENCES p);",
    ),
    (
        "partial-target",
        "CREATE TABLE p(a TEXT,b INTEGER,PRIMARY KEY(a,b)); CREATE TABLE bad("
        "id INTEGER PRIMARY KEY,a TEXT REFERENCES p(a));",
    ),
    (
        "fk-storage",
        "CREATE TABLE p(id INTEGER PRIMARY KEY); CREATE TABLE bad(id INTEGER PRIMARY "
        "KEY,p INTEGER REFERENCES p); INSERT INTO bad VALUES(1,'not-integer');",
    ),
    (
        "partial-null-storage",
        "CREATE TABLE p(a TEXT,b INTEGER,PRIMARY KEY(a,b)); CREATE TABLE "
        "bad(id INTEGER PRIMARY KEY,a TEXT,b INTEGER,FOREIGN KEY(a,b) REFERENCES p); "
        "INSERT INTO bad VALUES(1,X'4142',NULL);",
    ),
    (
        "ddl-arity",
        "CREATE TABLE p(a TEXT,b INTEGER,PRIMARY KEY(a,b)); CREATE TABLE bad("
        "id INTEGER PRIMARY KEY,a TEXT,FOREIGN KEY(a) REFERENCES p(a,b));",
    ),
)


def unsupported(ordinal):
    if not 0 <= ordinal < 128:
        raise ValueError("unsupported variant ordinal must be 0..127")
    name, sql = UNSUPPORTED[ordinal % len(UNSUPPORTED)]
    # Different declaration identifiers exercise quoting and Unicode while each
    # variant still introduces exactly the one stated unsupported feature.
    replacement = quote(("bad", "bad Ω", 'bad "quoted"', "Bad_ASCII")[ordinal // 16 % 4])
    return name, sql.replace("bad", replacement)
