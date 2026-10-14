"""Keep complete tutorial files synchronized and prove the oracle depends on data."""

from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
EXAMPLE = REPOSITORY / "examples" / "threshold"
GUIDE = REPOSITORY / "docs" / "getting-started.md"


@pytest.mark.parametrize("filename", ["generate.py", "oracle.py", "reproseed.toml"])
def test_complete_tutorial_files_match_retained_assets(filename: str) -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    pattern = rf"<!-- tutorial-file: {re.escape(filename)} -->\n```\w+\n(.*?)\n```"
    matches = re.findall(pattern, guide, re.DOTALL)
    assert len(matches) == 1, f"Expected one complete documented {filename}"
    assert matches[0] + "\n" == (EXAMPLE / filename).read_text(encoding="utf-8")


@pytest.mark.parametrize("removed_parcel", [71, 400])
def test_documented_oracle_checks_the_specific_aggregate(
    tmp_path: Path, removed_parcel: int
) -> None:
    project = tmp_path / "first use café"
    project.mkdir()
    for filename in ("generate.py", "oracle.py", "reproseed.toml"):
        shutil.copyfile(EXAMPLE / filename, project / filename)
    database = project / "fixture.sqlite3"
    generated = subprocess.run(
        [sys.executable, str(project / "generate.py")],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert generated.returncode == 0
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM crates").fetchone() == (3,)
        assert connection.execute("SELECT COUNT(*) FROM parcels").fetchone() == (8,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    original_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    result = subprocess.run(
        [sys.executable, str(project / "oracle.py"), str(database)],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 43
    assert result.stdout == "REPROSEED_WEIGHT_THRESHOLD\n"
    assert result.stderr == ""
    assert hashlib.sha256(database.read_bytes()).hexdigest() == original_hash

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("DELETE FROM parcels WHERE parcel_id = ?", (removed_parcel,))
    modified_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    without_target = subprocess.run(
        [sys.executable, str(project / "oracle.py"), str(database)],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert without_target.returncode == 0
    assert without_target.stdout == ""
    assert without_target.stderr == ""
    assert hashlib.sha256(database.read_bytes()).hexdigest() == modified_hash
