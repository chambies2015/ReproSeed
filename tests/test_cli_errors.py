"""First-use stderr privacy and human recovery guidance regressions."""

from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_config_artifacts import target
from windows_permissions import denied_directory_acl, probe_directory_creation

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


def test_owned_staging_mkdir_denial_is_attempted_once_without_launch_or_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    request: pytest.FixtureRequest,
) -> None:
    launch = tmp_path / "oracle-launches"
    config = target(
        tmp_path,
        f"from pathlib import Path\nPath({str(launch)!r}).write_text('launched')\n"
        "print('TARGET'); raise SystemExit(42)",
    )
    parent = tmp_path / "output-parent"
    parent.mkdir()
    existing = parent / "existing.txt"
    existing.write_text("preserve existing work", encoding="utf-8")
    inputs = [config, tmp_path / "source.sqlite3", tmp_path / "oracle.py", existing]
    before = [sha256(path) for path in inputs]
    owned = parent / ".reproseed-build-synthetic-denial"
    monkeypatch.setattr(
        "reproseed.artifacts.uuid.uuid4", lambda: SimpleNamespace(hex="synthetic-denial")
    )
    original_mkdir = Path.mkdir
    attempts = 0
    delegated: list[Path] = []

    def denied_mkdir(
        path: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False
    ) -> None:
        nonlocal attempts
        if path == owned:
            attempts += 1
            # A regression to retrying must fail this finite test immediately.
            assert attempts == 1, "owned staging denial was retried"
            assert mode == 0o700 and not parents and not exist_ok
            raise PermissionError(errno.EACCES, "synthetic denial", "PRIVATE\x1b/path")
        delegated.append(path)
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    launches = 0
    original_popen = subprocess.Popen

    def counted_popen(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        nonlocal launches
        launches += 1
        return original_popen(*args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "mkdir", denied_mkdir)
    monkeypatch.setattr("reproseed.oracle.subprocess.Popen", counted_popen)
    unrelated = parent / "unrelated"
    unrelated.mkdir()
    started = time.monotonic()
    exit_code = main(
        ["reduce", "--config", str(config), "--out", str(parent / "bundle"), "--allow-exec"]
    )
    elapsed = time.monotonic() - started
    output = capsys.readouterr()
    unchanged = [sha256(path) for path in inputs] == before
    no_output = not (parent / "bundle").exists()
    no_staging = not list(parent.glob(".reproseed-build-*"))
    request.node.user_properties.append(
        (
            "staging_denial",
            json.dumps(
                dict(
                    exit=exit_code,
                    attempts=attempts,
                    oracle_launches=launches,
                    seconds=elapsed,
                    inputs_unchanged=unchanged,
                    no_output=no_output,
                    no_staging=no_staging,
                )
            ),
        )
    )
    assert exit_code == 2 and attempts == 1 and elapsed < 5
    assert "file_operation_failed" in output.err and "permissions" in output.err
    assert "PRIVATE" not in output.err and str(tmp_path) not in output.err
    assert "\x1b" not in output.err and output.out == ""
    assert launches == 0 and not launch.exists()
    assert unchanged and no_output and no_staging
    assert unrelated.is_dir() and unrelated in delegated and parent in delegated


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
def test_windows_denied_output_returns_promptly_without_launch_or_overwrite(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    sentinel = tmp_path / "must-not-launch"
    config = target(
        tmp_path,
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n"
        "print('TARGET'); raise SystemExit(42)",
    )
    inputs = [config, tmp_path / "source.sqlite3", tmp_path / "oracle.py"]
    parent = tmp_path / "denied-output"
    parent.mkdir()
    existing = parent / "existing.txt"
    existing.write_text("preserve existing work", encoding="utf-8")
    inputs.append(existing)
    before = [sha256(path) for path in inputs]
    observation: dict[str, object] = {"integration": "not_run"}
    try:
        with denied_directory_acl(parent) as acl:
            observation.update(acl=acl)
            probe = probe_directory_creation(parent, cwd=tmp_path)
            observation["probe"] = probe
            assert probe["probe_removed"]
            assert probe["decision"] != "unexpected_error", json.dumps(probe)
            if probe["decision"] == "allowed":
                observation["integration"] = "capability_skipped"
                pytest.skip(
                    "real ACL-denial integration unavailable: owned WD/AD ACL edit succeeded "
                    "but current CLI context allowed mkdir(mode=0o700)"
                )
            observation["integration"] = "ran"
            started = time.monotonic()
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
            observation.update(exit=result.returncode, seconds=time.monotonic() - started)
            assert result.returncode == 2, "denied-output CLI did not return exit 2"
            assert observation["seconds"] < 8
            assert "file_operation_failed" in result.stderr
            assert "permissions" in result.stderr
            assert str(tmp_path) not in result.stderr and "\x1b" not in result.stderr
            assert result.stdout == ""
    finally:
        unchanged = [sha256(path) for path in inputs] == before
        no_output = not (parent / "bundle").exists()
        no_staging = not list(parent.glob(".reproseed-build-*"))
        observation.update(
            inputs_unchanged=unchanged,
            oracle_launches=0 if not sentinel.exists() else "observed_launch",
            no_output=no_output,
            no_staging=no_staging,
        )
        request.node.user_properties.append(("acl_integration", json.dumps(observation)))
        assert unchanged and no_output and no_staging and not sentinel.exists()


def test_directory_capability_probe_removes_successful_probe_and_distinguishes_path_error(
    tmp_path: Path,
) -> None:
    allowed = probe_directory_creation(tmp_path, cwd=tmp_path)
    assert allowed["decision"] == "allowed" and allowed["probe_removed"]
    unexpected = probe_directory_creation(tmp_path / "missing-parent", cwd=tmp_path)
    assert unexpected["decision"] == "unexpected_error" and unexpected["errno"] == errno.ENOENT
    assert not list(tmp_path.glob(".reproseed-probe-*"))


@pytest.mark.skipif(os.name != "nt", reason="controlled Windows ACL restoration")
@pytest.mark.parametrize("interruption", ["skip", "assertion", "timeout"])
def test_owned_acl_restores_original_after_test_control_flow(
    tmp_path: Path, interruption: str
) -> None:
    parent = tmp_path / "owned-permissions"
    parent.mkdir()
    failures = {
        "skip": pytest.skip.Exception("injected capability skip"),
        "assertion": AssertionError("injected assertion failure"),
        "timeout": subprocess.TimeoutExpired("synthetic owned probe", 8),
    }
    failure = failures[interruption]
    with pytest.raises(type(failure)):
        with denied_directory_acl(parent) as observation:
            raise failure
    assert observation["acl_restored"] is True
    assert probe_directory_creation(parent, cwd=tmp_path)["decision"] == "allowed"
    assert not list(tmp_path.glob("acl-*"))


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
