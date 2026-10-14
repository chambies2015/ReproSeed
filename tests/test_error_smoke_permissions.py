"""Installed-audit capability decisions cannot silently become denial success."""

from __future__ import annotations

import errno
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import error_smoke
import pytest
from windows_permissions import denied_directory_acl


def test_input_probe_uses_actual_read_and_distinguishes_missing_file(tmp_path: Path) -> None:
    selected = tmp_path / "private-input.bin"
    before = b"PRIVATE_SYNTHETIC_READ_PROBE_CONTENT"
    selected.write_bytes(before)
    allowed = error_smoke.probe_input_read(
        Path(sys.executable), selected, tmp_path, dict(os.environ)
    )
    assert allowed == {"decision": "allowed", "errno": None, "winerror": None, "exit": 0}
    assert selected.read_bytes() == before
    missing = error_smoke.probe_input_read(
        Path(sys.executable), tmp_path / "missing.bin", tmp_path, dict(os.environ)
    )
    assert missing["decision"] == "unexpected_error" and missing["errno"] == errno.ENOENT
    assert str(tmp_path) not in str(missing) and "PRIVATE" not in str(allowed)


def test_allowed_windows_audit_probes_restore_one_directory_without_executing_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = error_smoke.Audit(Path(sys.executable), tmp_path / "unused-cli", tmp_path)
    ownership: list[tuple[Path, str, bool]] = []
    restored: list[bool] = []

    @contextmanager
    def owned_acl(
        parent: Path, permissions: str = "(WD,AD)", *, propagate_children: bool = False
    ) -> Iterator[dict[str, object]]:
        ownership.append((parent, permissions, propagate_children))
        evidence: dict[str, object] = {"acl_restored": False}
        try:
            yield evidence
        finally:
            evidence["acl_restored"] = True
            restored.append(True)

    def must_not_execute(*args: object, **kwargs: object) -> None:
        raise AssertionError("allowed capability must not execute a denial CLI assertion")

    monkeypatch.setattr(error_smoke, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(error_smoke, "denied_directory_acl", owned_acl)
    monkeypatch.setattr(audit, "run", must_not_execute)
    audit.permission_cases()
    owned = tmp_path / "permissions"
    assert ownership == [(owned, "(OI)(CI)(RD)", True), (owned, "(WD,AD)", False)]
    assert restored == [True, True]
    assert {skip["case"] for skip in audit.skips} == {"unreadable_input", "unwritable_output"}
    assert all(
        observation["probe"]["decision"] == "allowed"
        for observation in audit.permission_observations
    )
    assert all(observation["acl"]["acl_restored"] for observation in audit.permission_observations)
    assert all(observation["actual_launches"] == 0 for observation in audit.permission_observations)
    assert not (owned / "bundle").exists() and not list(owned.glob(".reproseed-*"))


def test_unexpected_windows_audit_probe_fails_after_owned_acl_restoration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = error_smoke.Audit(Path(sys.executable), tmp_path / "unused-cli", tmp_path)
    restored: list[bool] = []

    @contextmanager
    def owned_acl(
        parent: Path, permissions: str, *, propagate_children: bool = False
    ) -> Iterator[dict[str, object]]:
        try:
            yield {"acl_restored": False}
        finally:
            restored.append(True)

    monkeypatch.setattr(error_smoke, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(error_smoke, "denied_directory_acl", owned_acl)
    monkeypatch.setattr(
        error_smoke,
        "probe_input_read",
        lambda *args: {"decision": "unexpected_error", "errno": errno.EINVAL, "winerror": 87},
    )
    with pytest.raises(RuntimeError, match="unexpected input capability probe error"):
        audit.permission_cases()
    assert restored == [True] and audit.records == [] and audit.skips == []
    assert not (tmp_path / "permissions" / "bundle").exists()


@pytest.mark.skipif(os.name != "nt", reason="owned Windows inherited input-read denial")
def test_inherited_input_denial_restores_owned_child_reads_and_bytes(tmp_path: Path) -> None:
    owned = tmp_path / "owned-inputs"
    owned.mkdir()
    files = [owned / name for name in ("source.sqlite3", "case.toml", "oracle.py")]
    for index, path in enumerate(files):
        path.write_bytes(f"synthetic content {index}".encode())
    before = error_smoke.hashes(owned)
    environment = dict(os.environ)
    try:
        with denied_directory_acl(
            owned, permissions="(OI)(CI)(RD)", propagate_children=True
        ) as acl:
            probes = [
                error_smoke.probe_input_read(Path(sys.executable), path, tmp_path, environment)
                for path in files
            ]
            assert all(probe["decision"] in {"allowed", "denied"} for probe in probes)
            if all(probe["decision"] == "allowed" for probe in probes):
                pytest.skip(
                    "real inherited input-read denial unavailable in current process context"
                )
            assert all(probe["decision"] == "denied" for probe in probes)
            assert all(probe["errno"] == errno.EACCES for probe in probes)
    finally:
        assert error_smoke.hashes(owned) == before
        assert all(
            error_smoke.probe_input_read(Path(sys.executable), path, tmp_path, environment)[
                "decision"
            ]
            == "allowed"
            for path in files
        )
        assert not list(tmp_path.glob("acl-*"))
    assert acl["acl_restored"] and acl["children_inheritance_restore_exit"] == 0
