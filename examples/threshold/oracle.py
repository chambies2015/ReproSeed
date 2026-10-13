"""Detect a crate whose combined parcel mass exceeds the configured limit."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

MARKER = "REPROSEED_WEIGHT_THRESHOLD"


def check(database: Path) -> int:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        overloaded = connection.execute(
            """
            SELECT crates.crate_id
            FROM crates JOIN parcels ON parcels.crate_id = crates.crate_id
            GROUP BY crates.crate_id
            HAVING SUM(parcels.mass) > 100
            """
        ).fetchone()
    if overloaded is not None:
        print(MARKER)
        return 43
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: oracle.py DATABASE", file=sys.stderr)
        return 2
    try:
        return check(Path(sys.argv[1]))
    except (OSError, sqlite3.Error) as error:
        print(f"Threshold could not be checked: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
