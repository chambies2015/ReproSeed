"""First-use stderr privacy and human recovery guidance regressions."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_config_artifacts import target

from reproseed.artifacts import sha256
from reproseed.cli import main
from reproseed.config import ConfigError, load_config
from reproseed.diagnostics import diagnose, format_diagnosis, serialize_diagnosis
from reproseed.sqlite_adapter import DatabaseError


def test_missing_configuration_is_unavailable_not_malformed(tmp_path: Path) -> None:
    path = tmp_path / "missing-config.toml"
    with pytest.raises(ConfigError, match="configuration file is missing"):
        load_config(path)
    diagnosis = diagnose(path)
    assert diagnosis.exit_code == 2
    assert diagnosis.error is not None
    assert diagnosis.error.reason == "configuration_unavailable"
    assert str(tmp_path) not in serialize_diagnosis(diagnosis)
    assert "check the path and permissions" in format_diagnosis(diagnosis)


@pytest.mark.parametrize("kind", ["source", "asset", "unknown_field", "schema"])
def test_reduce_input_error_omits_private_paths_and_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    private = "PRIVATE_SYNTHETIC_ERROR_VALUE"
    config = target(tmp_path, "raise AssertionError('must not execute')")
    text = config.read_text()
    if kind == "source":
        text = text.replace('source="source.sqlite3"', f'source="{private}.sqlite3"')
    elif kind == "asset":
        text = text.replace('include=["oracle.py"]', f'include=["{private}.py"]')
    elif kind == "unknown_field":
        text = text.replace("version=1", f"version=1\n{private}=1")
    else:
        import sqlite3

        with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as database:
            database.execute(f'CREATE TABLE "{private}"(id VARCHAR PRIMARY KEY)')
    config.write_text(text, encoding="utf-8")
    assert (
        main(["reduce", "--config", str(config), "--out", str(tmp_path / "bundle"), "--allow-exec"])
        == 2
    )
    output = capsys.readouterr()
    assert private not in output.err and str(tmp_path) not in output.err
    assert output.out == ""
    assert "Recovery:" in output.err and "diagnose" in output.err
    assert not (tmp_path / "bundle").exists()


def test_os_error_is_curated_and_does_not_echo_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = target(tmp_path)

    def denied(*args: object) -> None:
        raise PermissionError(13, "synthetic denial", "PRIVATE\x1b[31m/path")

    monkeypatch.setattr("reproseed.cli.create_bundle", denied)
    assert (
        main(["reduce", "--config", str(config), "--out", str(tmp_path / "bundle"), "--allow-exec"])
        == 2
    )
    output = capsys.readouterr()
    assert "file_operation_failed" in output.err
    assert "PRIVATE" not in output.err and "\x1b" not in output.err
    assert "permissions" in output.err


def test_non_target_diagnosis_has_text_recovery_without_json_shape_change(tmp_path: Path) -> None:
    diagnosis = diagnose(target(tmp_path, "raise SystemExit(0)"), allow_exec=True)
    before = diagnosis.as_dict()
    assert diagnosis.exit_code == 1
    assert "Recovery: run the configured application on a disposable copy" in format_diagnosis(
        diagnosis
    )
    assert diagnosis.as_dict() == before


def test_snapshot_deadline_keeps_specific_cli_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = target(tmp_path)

    def deadline(*args: object) -> None:
        raise DatabaseError("Snapshot acquisition timed out")

    monkeypatch.setattr("reproseed.cli.create_bundle", deadline)
    assert (
        main(["reduce", "--config", str(config), "--out", str(tmp_path / "bundle"), "--allow-exec"])
        == 2
    )
    assert "snapshot_timeout" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "nt", reason="controlled Windows ACL denial")
def test_windows_denied_output_returns_promptly_without_launch_or_overwrite(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-launch"
    config = target(
        tmp_path,
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n"
        "print('TARGET'); raise SystemExit(42)",
    )
    before = sha256(tmp_path / "source.sqlite3")
    parent = tmp_path / "denied-output"
    parent.mkdir()
    identity = subprocess.run(
        ["whoami"], capture_output=True, text=True, check=True, timeout=5
    ).stdout.strip()
    try:
        subprocess.run(
            ["icacls", str(parent), "/deny", identity + ":(WD,AD)"],
            check=True,
            capture_output=True,
            timeout=5,
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "reproseed",
                "reduce",
                "--config",
                str(config),
                "--out",
                str(parent / "bundle"),
                "--allow-exec",
            ],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
            timeout=8,
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "file_operation_failed" in result.stderr
        assert "permissions" in result.stderr
        assert result.stdout == "" and not sentinel.exists()
        assert sha256(tmp_path / "source.sqlite3") == before
        assert not (parent / "bundle").exists()
        assert not list(parent.glob(".reproseed-build-*"))
    finally:
        subprocess.run(
            ["icacls", str(parent), "/remove:d", identity],
            check=True,
            capture_output=True,
            timeout=5,
        )


def test_staging_cleanup_interruption_keeps_cli_130_and_source_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = target(tmp_path, budget=6)
    before = sha256(tmp_path / "source.sqlite3")

    def interrupted_cleanup(*args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "reproseed.artifacts.tempfile.TemporaryDirectory.cleanup", interrupted_cleanup
    )
    try:
        assert (
            main(
                [
                    "reduce",
                    "--config",
                    str(config),
                    "--out",
                    str(tmp_path / "bundle"),
                    "--allow-exec",
                ]
            )
            == 130
        )
        assert "interrupted" in capsys.readouterr().err
        assert sha256(tmp_path / "source.sqlite3") == before
        assert not (tmp_path / "bundle").exists()
    finally:
        monkeypatch.undo()
        # All matching roots were allocated by this test's attempted reduction.
        for owned in tmp_path.glob(".reproseed-build-*"):
            shutil.rmtree(owned)


def test_staging_name_collision_preserves_existing_files_without_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    launch = tmp_path / "must-not-launch"
    config = target(
        tmp_path,
        f"from pathlib import Path\nPath({str(launch)!r}).write_text('bad')\n"
        "print('TARGET'); raise SystemExit(42)",
    )
    colliding = tmp_path / ".reproseed-build-synthetic-collision"
    colliding.mkdir()
    retained = colliding / "user-file.txt"
    retained.write_text("preserve existing work", encoding="utf-8")
    before = (sha256(retained), sha256(tmp_path / "source.sqlite3"))
    monkeypatch.setattr(
        "reproseed.artifacts.uuid.uuid4", lambda: SimpleNamespace(hex="synthetic-collision")
    )
    assert (
        main(["reduce", "--config", str(config), "--out", str(tmp_path / "bundle"), "--allow-exec"])
        == 2
    )
    assert "file_operation_failed" in capsys.readouterr().err
    assert (sha256(retained), sha256(tmp_path / "source.sqlite3")) == before
    assert not launch.exists() and not (tmp_path / "bundle").exists()
