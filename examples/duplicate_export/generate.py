"""Generate only synthetic data for the deliberately broken exporter demo."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def generate(database: Path) -> None:
    """Create a fresh, deterministic fixture containing 2,430 user rows."""
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite an existing database: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE owners (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL REFERENCES owners(id),
                name TEXT NOT NULL
            );
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                name TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX entries_project ON entries(project_id);
            PRAGMA user_version = 1;
            """
        )
        connection.executemany(
            "INSERT INTO owners VALUES (?, ?)",
            [(owner_id, f"Synthetic owner {owner_id}") for owner_id in range(1, 7)],
        )
        connection.executemany(
            "INSERT INTO projects VALUES (?, ?, ?)",
            [
                (project_id, (project_id - 1) // 4 + 1, f"Synthetic project {project_id}")
                for project_id in range(1, 25)
            ],
        )
        entries = [
            (
                entry_id,
                (entry_id - 1) // 100 + 1,
                f"entry-{entry_id:04d}",
                f"Synthetic payload {entry_id}",
            )
            for entry_id in range(1, 2401)
        ]
        # Both projects belong to owner 6. The exporter must retain both records.
        entries[-2] = (2399, 23, "shared-export-name", "First colliding payload")
        entries[-1] = (2400, 24, "shared-export-name", "Second colliding payload")
        connection.executemany("INSERT INTO entries VALUES (?, ?, ?, ?)", entries)


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
    print(f"Created {arguments.database}: 6 owners, 24 projects, 2400 entries (2430 rows).")


if __name__ == "__main__":
    main()
