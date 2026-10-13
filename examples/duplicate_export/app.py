"""A tiny exporter with a deliberate cross-project name collision bug."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


def export_entries(database: Path) -> list[dict[str, Any]]:
    """Return exported entries, incorrectly treating names as globally unique."""
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT entries.id AS entry_id, entries.name AS name, entries.payload AS payload,
                   projects.id AS project_id, projects.name AS project_name,
                   owners.id AS owner_id, owners.name AS owner_name
            FROM entries
            JOIN projects ON projects.id = entries.project_id
            JOIN owners ON owners.id = projects.owner_id
            ORDER BY entries.id
            """
        )
        # Deliberate application bug: later projects overwrite earlier entries.
        exported_by_name = {row["name"]: dict(row) for row in rows}
    return list(exported_by_name.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(export_entries(arguments.database), indent=2))


if __name__ == "__main__":
    main()
