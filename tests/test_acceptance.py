"""Real-subprocess acceptance checks for two distinct synthetic targets."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): _sha256(path)
        for path in directory.rglob("*")
        if path.is_file()
    }


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _cli(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, "-m", "reproseed", *arguments], cwd)


def _succeeded(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def _prepare(example: str, directory: Path) -> Path:
    directory.mkdir()
    for asset in (REPOSITORY / "examples" / example).iterdir():
        if asset.suffix in {".py", ".toml"}:
            shutil.copy2(asset, directory / asset.name)
    database = directory / "fixture.sqlite3"
    _succeeded(_run([sys.executable, str(directory / "generate.py"), str(database)], directory))
    return database


def _database_state(
    database: Path,
) -> tuple[list[tuple[Any, ...]], dict[str, set[tuple[Any, ...]]], int]:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        schema = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = [str(row[1]) for row in schema if row[0] == "table"]
        rows = {
            table: set(connection.execute('SELECT * FROM "' + table.replace('"', '""') + '"'))
            for table in tables
        }
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    return schema, rows, user_version


def _retained_values_preserved(
    original: tuple[list[tuple[Any, ...]], dict[str, set[tuple[Any, ...]]], int],
    final: tuple[list[tuple[Any, ...]], dict[str, set[tuple[Any, ...]]], int],
) -> None:
    assert final[0] == original[0]
    assert final[2] == original[2]
    assert final[1].keys() == original[1].keys()
    for table, rows in final[1].items():
        assert rows <= original[1][table], f"Retained values changed in {table}"


def test_duplicate_export_complete_relocated_acceptance(tmp_path: Path) -> None:
    source_root = tmp_path / "original-example"
    source = _prepare("duplicate_export", source_root)
    original_state = _database_state(source)
    original_counts = {table: len(rows) for table, rows in original_state[1].items()}
    assert original_counts == {"entries": 2400, "owners": 6, "projects": 24}
    assert sum(original_counts.values()) >= 2000
    source_hash = _sha256(source)
    asset_hashes = {name: _sha256(source_root / name) for name in ("app.py", "oracle.py")}
    baseline = _run([sys.executable, str(source_root / "oracle.py"), str(source)], tmp_path)
    assert baseline.returncode == 42, baseline.stdout + baseline.stderr
    assert baseline.stdout.splitlines() == ["REPROSEED_DUPLICATE_EXPORT"]

    bundle = tmp_path / "first-bundle"
    _succeeded(
        _cli(
            [
                "reduce",
                "--config",
                str(source_root / "reproseed.toml"),
                "--out",
                str(bundle),
                "--allow-exec",
            ],
            tmp_path,
        )
    )
    assert _sha256(source) == source_hash
    assert {name: _sha256(source_root / name) for name in asset_hashes} == asset_hashes
    final_state = _database_state(bundle / "fixture.sqlite3")
    _retained_values_preserved(original_state, final_state)
    final_counts = {table: len(rows) for table, rows in final_state[1].items()}
    assert 5 <= sum(final_counts.values()) <= 8
    assert final_counts["owners"] >= 1
    assert final_counts["projects"] >= 2
    assert final_counts["entries"] >= 2
    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    assert report["original_counts"] == original_counts
    assert report["final_counts"] == final_counts
    assert 6 <= report["oracle_invocations"] <= 400
    assert len(report["final_verification"]) == 3

    before_inspect = _files(bundle)
    _succeeded(_cli(["inspect", str(bundle)], tmp_path))
    assert _files(bundle) == before_inspect

    # Use the OS temporary root even when pytest's --basetemp is inside the
    # repository. Make the old fixture and asset paths unavailable before replay.
    with tempfile.TemporaryDirectory(prefix="reproseed-relocated-acceptance-") as temporary:
        relocation_root = Path(temporary)
        relocated = relocation_root / "bundle"
        assert not relocated.is_relative_to(REPOSITORY)
        shutil.copytree(bundle, relocated)
        source_root.rename(tmp_path / "original-example-unavailable")
        bundle.rename(tmp_path / "first-bundle-unavailable")
        unrelated_cwd = relocation_root / "unrelated-working-directory"
        unrelated_cwd.mkdir()
        before_replay = _files(relocated)
        _succeeded(_cli(["replay", str(relocated), "--allow-exec"], unrelated_cwd))
        assert _files(relocated) == before_replay
        assert _sha256(relocated / "fixture.sqlite3") == before_replay["fixture.sqlite3"]
    assert _sha256(tmp_path / "original-example-unavailable" / "fixture.sqlite3") == source_hash


def test_different_schema_and_aggregate_target(tmp_path: Path) -> None:
    source_root = tmp_path / "threshold-example"
    source = _prepare("threshold", source_root)
    source_hash = _sha256(source)
    original_state = _database_state(source)
    assert sum(len(rows) for rows in original_state[1].values()) == 11
    baseline = _run([sys.executable, str(source_root / "oracle.py"), str(source)], tmp_path)
    assert baseline.returncode == 43, baseline.stdout + baseline.stderr
    assert baseline.stdout.splitlines() == ["REPROSEED_WEIGHT_THRESHOLD"]
    bundle = tmp_path / "threshold-bundle"
    _succeeded(
        _cli(
            [
                "reduce",
                "--config",
                str(source_root / "reproseed.toml"),
                "--out",
                str(bundle),
                "--allow-exec",
            ],
            tmp_path,
        )
    )
    final_state = _database_state(bundle / "fixture.sqlite3")
    _retained_values_preserved(original_state, final_state)
    assert {table: len(rows) for table, rows in final_state[1].items()} == {
        "crates": 1,
        "parcels": 2,
    }
    assert _sha256(source) == source_hash
    source_root.rename(tmp_path / "threshold-example-unavailable")
    before_replay = _files(bundle)
    _succeeded(_cli(["replay", str(bundle), "--allow-exec"], tmp_path))
    assert _files(bundle) == before_replay
