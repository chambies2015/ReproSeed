"""Generate a separate synthetic aggregate-threshold fixture."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def generate(database: Path) -> None:
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite an existing database: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE crates (
                crate_id INTEGER PRIMARY KEY,
                label TEXT NOT NULL
            );
            CREATE TABLE parcels (
                parcel_id INTEGER PRIMARY KEY,
                crate_id INTEGER NOT NULL REFERENCES crates(crate_id),
                mass INTEGER NOT NULL CHECK (mass >= 0)
            );
            PRAGMA user_version = 7;
            """
        )
        connection.executemany(
            "INSERT INTO crates VALUES (?, ?)",
            [
                (-7, "Synthetic light crate A"),
                (12, "Synthetic light crate B"),
                (99, "Synthetic overloaded crate"),
            ],
        )
        connection.executemany(
            "INSERT INTO parcels VALUES (?, ?, ?)",
            [
                (-30, -7, 5),
                (2, -7, 8),
                (9, 12, 11),
                (50, 12, 13),
                (71, 99, 61),
                (400, 99, 44),
                (910, 12, 2),
                (1001, -7, 9),
            ],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "fixture.sqlite3",
        help="New database path; existing files are never overwritten.",
    )
    arguments = parser.parse_args()
    generate(arguments.database)
    print(f"Created {arguments.database}: 3 crates and 8 parcels (11 rows).")


if __name__ == "__main__":
    main()
