"""Check the exporter for the particular cross-project omission failure."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from app import export_entries

MARKER = "REPROSEED_DUPLICATE_EXPORT"


def check(database: Path) -> int:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        expected = connection.execute(
            """
            SELECT entries.id, entries.name, entries.project_id
            FROM entries
            JOIN projects ON projects.id = entries.project_id
            JOIN owners ON owners.id = projects.owner_id
            ORDER BY entries.id
            """
        ).fetchall()
    exported = export_entries(database)
    exported_by_id = {entry["entry_id"]: entry for entry in exported}
    expected_ids = {entry_id for entry_id, _, _ in expected}
    omitted = [row for row in expected if row[0] not in exported_by_id]
    if not omitted and set(exported_by_id) == expected_ids:
        return 0
    # Establish this bug from the application's output and real source rows.
    # A different export discrepancy does not satisfy this failure contract.
    collision_explains_omissions = omitted and all(
        any(item["name"] == name and item["project_id"] != project_id for item in exported)
        for _, name, project_id in omitted
    )
    if collision_explains_omissions and set(exported_by_id) < expected_ids:
        print(MARKER)
        return 42
    print("Unexpected export discrepancy", file=sys.stderr)
    return 2


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: oracle.py DATABASE", file=sys.stderr)
        return 2
    try:
        return check(Path(sys.argv[1]))
    except (OSError, sqlite3.Error, KeyError) as error:
        print(f"Exporter could not be checked: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
