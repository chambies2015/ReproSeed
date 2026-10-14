"""Guard smoke isolation and fail-closed behavior without repeating reductions."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import external_consumer_smoke as smoke
import pytest


def test_consumer_environment_removes_development_import_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "_OLD_VIRTUAL_PATH"):
        monkeypatch.setenv(name, "source checkout sentinel")
    environment = smoke.consumer_environment()
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "_OLD_VIRTUAL_PATH"} & environment.keys()
    assert environment["PYTHONUTF8"] == "1"
    assert environment["PIP_NO_INPUT"] == "1"


def test_import_origin_requires_fresh_site_packages_without_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smoke, "REPOSITORY", tmp_path / "source checkout")
    installation = tmp_path / "fresh venv"
    site_packages = installation / "Lib" / "site-packages"
    runtime: dict[str, Any] = {
        "reproseed_module": str(site_packages / "reproseed" / "__init__.py"),
        "site_packages": [str(site_packages)],
        "prefix": str(installation),
        "path": [str(site_packages), str(tmp_path)],
    }
    smoke.validate_import_origin(runtime, installation)
    runtime["reproseed_module"] = str(smoke.REPOSITORY / "src" / "reproseed" / "__init__.py")
    with pytest.raises(smoke.SmokeError, match="fresh installation's site-packages"):
        smoke.validate_import_origin(runtime, installation)
    runtime["reproseed_module"] = str(site_packages / "reproseed" / "__init__.py")
    runtime["site_packages"].append(str(installation))
    runtime["reproseed_module"] = str(installation / "reproseed" / "__init__.py")
    with pytest.raises(smoke.SmokeError, match="fresh installation's site-packages"):
        smoke.validate_import_origin(runtime, installation)
    runtime["reproseed_module"] = str(site_packages / "reproseed" / "__init__.py")
    runtime["path"].append(str(smoke.REPOSITORY / "src"))
    with pytest.raises(smoke.SmokeError, match="source checkout"):
        smoke.validate_import_origin(runtime, installation)


def test_failed_command_records_actual_exit_without_source_fallback(tmp_path: Path) -> None:
    evidence: dict[str, Any] = {}
    commands = smoke.Commands(evidence, smoke.consumer_environment())
    with pytest.raises(smoke.SmokeError, match="exited 9, expected 0"):
        commands.run([sys.executable, "-c", "raise SystemExit(9)"], tmp_path)
    assert len(evidence["commands"]) == 1
    assert evidence["commands"][0]["exit_code"] == 9
    assert evidence["commands"][0]["timeout_seconds"] == 45


def test_command_deadline_fails_clearly_and_preserves_attempt_evidence(tmp_path: Path) -> None:
    evidence: dict[str, Any] = {}
    commands = smoke.Commands(evidence, smoke.consumer_environment())
    with pytest.raises(smoke.SmokeError, match="could not complete"):
        commands.run([sys.executable, "-c", "import time; time.sleep(5)"], tmp_path, timeout=0.05)
    assert len(evidence["commands"]) == 1
    assert "error" in evidence["commands"][0]
    assert "exit_code" not in evidence["commands"][0]


def test_consumer_refuses_checkout_temporary_root_and_removes_owned_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "synthetic.whl"
    wheel.write_bytes(b"Only path validation is exercised; this wheel is never installed.")
    monkeypatch.setattr(smoke, "REPOSITORY", tmp_path)
    # Force a hostile development TMPDIR; the smoke must reject this rather than
    # claim an external consumer test. Preserve all pre-existing files.
    monkeypatch.setattr(smoke.tempfile, "tempdir", str(tmp_path))
    evidence: dict[str, Any] = {}
    with pytest.raises(smoke.SmokeError, match="inside the source checkout"):
        smoke.run_smoke(wheel, evidence)
    assert list(tmp_path.iterdir()) == [wheel]
    assert "commands" not in evidence


def test_consumer_failure_removes_only_newly_acquired_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "synthetic.whl"
    wheel.write_bytes(b"Only cleanup is exercised; this wheel is never installed.")
    monkeypatch.setattr(smoke.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(smoke, "REPOSITORY", tmp_path / "separate checkout")
    observed: list[Path] = []

    def fail_consumer(
        selected_wheel: Path,
        outside: Path,
        evidence: dict[str, Any],
        *,
        audit: bool,
        existing_applications: bool,
    ) -> None:
        assert selected_wheel == wheel
        observed.append(outside)
        (outside / "synthetic state").write_text("created by test", encoding="utf-8")
        raise smoke.SmokeError("injected consumer failure")

    monkeypatch.setattr(smoke, "exercise_consumer", fail_consumer)
    evidence: dict[str, Any] = {}
    with pytest.raises(smoke.SmokeError, match="injected consumer failure"):
        smoke.run_smoke(wheel, evidence)
    assert observed and not observed[0].exists()
    assert wheel.read_bytes() == b"Only cleanup is exercised; this wheel is never installed."
    assert list(tmp_path.iterdir()) == [wheel]
