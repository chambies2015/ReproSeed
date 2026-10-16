"""Assert the real export invariant, with one stable failure signature."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from app import export_entries


def test_cross_project_names(reproseed_db: Path) -> None:
    """Two projects may use the same entry name without losing either entry."""
    with closing(
        sqlite3.connect(reproseed_db.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        expected = connection.execute(
            """
            SELECT entries.id, entries.project_id, entries.name
            FROM entries
            JOIN projects ON projects.id = entries.project_id
            JOIN owners ON owners.id = projects.owner_id
            ORDER BY entries.id
            """
        ).fetchall()
    exported = export_entries(reproseed_db)
    expected_ids = {entry_id for entry_id, _, _ in expected}
    actual_ids = {entry["entry_id"] for entry in exported}
    omitted = [row for row in expected if row[0] not in actual_ids]
    # Establish the particular defect from independent source rows and actual
    # application output. Other discrepancies have a different exception type.
    if (
        actual_ids < expected_ids
        and len(actual_ids) == len(exported)
        and all(
            any(entry["name"] == name and entry["project_id"] != project_id for entry in exported)
            for _, project_id, name in omitted
        )
    ):
        # Explicit raising avoids pytest assertion expansion changing the exact
        # message as candidate values change during reduction.
        raise AssertionError("cross-project export lost an entry")
    if actual_ids != expected_ids or len(actual_ids) != len(exported):
        raise RuntimeError("unexpected export discrepancy")
