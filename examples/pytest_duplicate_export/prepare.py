"""Prepare a fresh pytest case from explicitly named duplicate-export assets.

This recipe reuses the original application and deterministic generator. It does
not maintain a second exporter. Existing destinations are never overwritten.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPLICATION = HERE.parent / "duplicate_export"
APPLICATION_ASSETS = ("app.py", "generate.py")
PYTEST_ASSETS = ("test_export.py", "pytest-target.toml", "reproseed.toml")


def prepare(directory: Path, *, small: bool = False) -> None:
    """Copy the named files and generate a new synthetic database."""
    directory.mkdir(parents=True, exist_ok=False)
    for root, names in ((APPLICATION, APPLICATION_ASSETS), (HERE, PYTEST_ASSETS)):
        for name in names:
            shutil.copy2(root / name, directory / name)
    database = directory / "fixture.sqlite3"
    subprocess.run([sys.executable, str(directory / "generate.py"), str(database)], check=True)
    if small:
        # These are unchanged rows from the genuine generator, including its two
        # cross-project collisions and two ordinary entries. Trim only this new
        # private fixture, preserving schema and valid dependency relationships.
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("DELETE FROM entries WHERE id NOT IN (1, 101, 2399, 2400)")
            connection.execute("DELETE FROM projects WHERE id NOT IN (1, 2, 23, 24)")
            connection.execute("DELETE FROM owners WHERE id NOT IN (1, 6)")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("The prepared synthetic fixture has invalid dependencies")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path, help="A new case directory")
    parser.add_argument(
        "--small", action="store_true", help="Keep ten genuine generated rows for bounded smoke"
    )
    arguments = parser.parse_args()
    prepare(arguments.directory.resolve(), small=arguments.small)
    print(f"Prepared {'10' if arguments.small else '2430'} synthetic rows in a fresh case.")


if __name__ == "__main__":
    main()
