"""Configuration and bundle boundaries, exercised with real files and processes."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from reproseed.artifacts import BundleError, create_bundle, replay_bundle, sha256, validate_bundle
from reproseed.cli import main
from reproseed.config import ConfigError, load_config
from reproseed.workflow import VerificationError


def target(
    tmp_path: Path, body: str = "print('TARGET'); raise SystemExit(42)", budget: int = 40
) -> Path:
    with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as database:
        database.executescript(
            "CREATE TABLE things(id INTEGER PRIMARY KEY, value TEXT);"
            "INSERT INTO things VALUES(-7,'retained');"
        )
    (tmp_path / "oracle.py").write_text(body, encoding="utf-8")
    config = tmp_path / "case.toml"
    config.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="TARGET"\nstream="stdout"\ntimeout_seconds=1.0\noutput_limit_bytes=4096\n'
        f"[reduction]\nmax_invocations={budget}\n",
        encoding="utf-8",
    )
    return config


@pytest.mark.parametrize(
    "old,new",
    [
        ("version=1", "version=2"),
        ("version=1", "version=true"),
        ('source="source.sqlite3"', 'source="bad\\u0000name"'),
        ("version=1", "version=1\nunknown=1"),
        ("expected_exit=42", "expected_exit=0"),
        ("expected_exit=42", "expected_exit=true"),
        ('marker="TARGET"', 'marker=""'),
        ('stream="stdout"', 'stream="both"'),
        ("timeout_seconds=1.0", "timeout_seconds=inf"),
        ("timeout_seconds=1.0", "timeout_seconds=-1"),
        ("output_limit_bytes=4096", "output_limit_bytes=0"),
        ("max_invocations=40", "max_invocations=5"),
        ('"{db}"', '"prefix{db}"'),
        ('"{db}"', '"{db.__class__}"'),
        ('argv=["{python}","oracle.py","{db}"]', 'argv="python oracle.py"'),
        ('include=["oracle.py"]', 'include=["../oracle.py"]'),
        ('include=["oracle.py"]', 'include=["oracle.py","ORACLE.py"]'),
        ('include=["oracle.py"]', 'include=["fixture.sqlite3"]'),
        ('include=["oracle.py"]', 'include=["fixture.sqlite3-wal"]'),
        ('include=["oracle.py"]', 'include=["db.sqlite3-wal"]'),
        ('include=["oracle.py"]', 'include=["source.sqlite3"]'),
        ('include=["oracle.py"]', 'include=["."]'),
        ('include=["oracle.py"]', 'include=["oracle.py/"]'),
    ],
)
def test_malformed_config(tmp_path: Path, old: str, new: str) -> None:
    config = target(tmp_path)
    config.write_text(config.read_text().replace(old, new), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config)


def test_paths_use_config_root_and_nested_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = target(tmp_path)
    (tmp_path / "nested").mkdir()
    (tmp_path / "oracle.py").rename(tmp_path / "nested" / "oracle.py")
    config.write_text(config.read_text().replace('"oracle.py"', '"nested/oracle.py"'))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    loaded = load_config(config)
    assert loaded.source == tmp_path / "source.sqlite3"
    report = create_bundle(loaded, elsewhere / "bundle")
    assert report["final_counts"] == {"things": 0}
    assert replay_bundle(elsewhere / "bundle")["outcome"] == "TARGET_FAILURE"


def test_symlink_asset_rejected(tmp_path: Path) -> None:
    config = target(tmp_path)
    link = tmp_path / "link.py"
    try:
        link.symlink_to(tmp_path / "oracle.py")
    except OSError as exc:
        pytest.skip(f"host cannot create symlinks: {exc}")
    config.write_text(config.read_text().replace('include=["oracle.py"]', 'include=["link.py"]'))
    with pytest.raises(ConfigError, match="symlinks"):
        load_config(config)


def test_allow_exec_before_any_oracle_launch(tmp_path: Path) -> None:
    config = target(tmp_path, "raise AssertionError('must not execute')")
    assert main(["reduce", "--config", str(config), "--out", str(tmp_path / "bundle")]) == 2
    assert main(["replay", str(tmp_path / "missing")]) == 2
    assert not (tmp_path / "bundle").exists()


@pytest.mark.parametrize(
    "body", ["raise SystemExit(0)", "raise SystemExit(42)", "print('TARGET'); raise SystemExit(43)"]
)
def test_bad_baseline_never_publishes(tmp_path: Path, body: str) -> None:
    config = target(tmp_path, body)
    before = sha256(tmp_path / "source.sqlite3")
    with pytest.raises(VerificationError, match="baseline"):
        create_bundle(load_config(config), tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()
    assert sha256(tmp_path / "source.sqlite3") == before


def test_baseline_inconsistency_is_not_majority_vote(tmp_path: Path) -> None:
    state = tmp_path / "count.txt"
    body = (
        "from pathlib import Path\n"
        f"p=Path({str(state)!r})\n"
        "n=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\n"
        "print('TARGET')\nraise SystemExit(0 if n==1 else 42)\n"
    )
    config = target(tmp_path, body)
    with pytest.raises(VerificationError, match="baseline"):
        create_bundle(load_config(config), tmp_path / "bundle")
    assert state.read_text() == "3"


def test_mutating_oracle_and_budget_preserve_preoracle_fixture(tmp_path: Path) -> None:
    config = target(
        tmp_path,
        "import sqlite3,sys\n"
        "c=sqlite3.connect(sys.argv[1])\n"
        "assert c.execute('SELECT value FROM things').fetchone()==('retained',)\n"
        "c.execute(\"UPDATE things SET value='mutation'\");c.commit();c.close()\n"
        "print('TARGET');raise SystemExit(42)",
        budget=6,
    )
    before = sha256(tmp_path / "source.sqlite3")
    report = create_bundle(load_config(config), tmp_path / "bundle")
    assert report["oracle_invocations"] == 6
    assert report["termination_reason"] == "oracle_budget_exhausted_reserved_final_verification"
    with closing(sqlite3.connect(tmp_path / "bundle" / "fixture.sqlite3")) as database:
        assert database.execute("SELECT value FROM things").fetchone() == ("retained",)
    assert sha256(tmp_path / "source.sqlite3") == before
    bundled = sha256(tmp_path / "bundle" / "fixture.sqlite3")
    assert replay_bundle(tmp_path / "bundle")["outcome"] == "TARGET_FAILURE"
    assert sha256(tmp_path / "bundle" / "fixture.sqlite3") == bundled


def test_conflicting_reduction_confirmations_not_accepted(tmp_path: Path) -> None:
    state = tmp_path / "count.txt"
    body = (
        "from pathlib import Path\nimport sqlite3,sys\n"
        f"p=Path({str(state)!r})\n"
        "n=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\n"
        "c=sqlite3.connect(sys.argv[1])\n"
        "empty=c.execute('SELECT count(*) FROM things').fetchone()[0]==0\n"
        "c.close()\nprint('TARGET')\nraise SystemExit(0 if empty and n==4 else 42)\n"
    )
    config = target(tmp_path, body)
    report = create_bundle(load_config(config), tmp_path / "bundle")
    assert report["final_counts"] == {"things": 1}
    assert report["unresolved_attempts"] == 1
    assert report["oracle_invocations"] == 8


def test_final_verification_bypasses_cache_and_does_not_publish_failure(tmp_path: Path) -> None:
    state = tmp_path / "count.txt"
    body = (
        "from pathlib import Path\n"
        f"p=Path({str(state)!r})\n"
        "n=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\n"
        "print('TARGET');raise SystemExit(0 if n>=5 else 42)\n"
    )
    config = target(tmp_path, body)
    with pytest.raises(VerificationError, match="final artifact"):
        create_bundle(load_config(config), tmp_path / "bundle")
    assert state.read_text() == "8"
    assert not (tmp_path / "bundle").exists()


def test_output_existing_source_and_asset_conflicts(tmp_path: Path) -> None:
    config = load_config(target(tmp_path))
    for output in (config.source, config.assets[0].path, tmp_path):
        with pytest.raises(BundleError):
            create_bundle(config, output)
    existing = tmp_path / "exists"
    existing.mkdir()
    with pytest.raises(BundleError):
        create_bundle(config, existing)
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = config.source.with_name(config.source.name + suffix)
        with pytest.raises(BundleError, match="sidecar"):
            create_bundle(config, sidecar)
        with pytest.raises(BundleError, match="sidecar"):
            create_bundle(config, sidecar / "nested")
        assert not sidecar.exists()


@pytest.mark.parametrize(
    "change", ["tamper", "version", "missing", "escape", "malformed", "report"]
)
def test_replay_rejects_invalid_bundle_before_launch(tmp_path: Path, change: str) -> None:
    config = target(tmp_path)
    bundle = tmp_path / "bundle"
    create_bundle(load_config(config), bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if change == "tamper":
        (bundle / "oracle.py").write_text("raise AssertionError('tampered')")
    elif change == "version":
        manifest["version"] = 2
    elif change == "missing":
        del manifest["artifacts"]["fixture.sqlite3"]
    elif change == "escape":
        manifest["artifacts"]["../outside"] = "0" * 64
    elif change == "report":
        (bundle / "report.json").write_text('{"version":2,"verified":true}')
        manifest["artifacts"]["report.json"] = sha256(bundle / "report.json")
    elif change == "malformed":
        manifest_path.write_text("[bad json")
    if change != "malformed":
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError):
        replay_bundle(bundle)


def test_inspect_does_not_execute_and_missing_dependency_is_unresolved(tmp_path: Path) -> None:
    config = target(tmp_path)
    bundle = tmp_path / "bundle"
    create_bundle(load_config(config), bundle)
    replay = bundle / "replay.toml"
    replay.write_text(replay.read_text().replace('"{python}"', '"reproseed-no-such-executable"'))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["artifacts"]["replay.toml"] = sha256(replay)
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    validate_bundle(bundle)
    assert main(["inspect", str(bundle)]) == 0
    result = replay_bundle(bundle)
    assert result["outcome"] == "UNRESOLVED"
    assert all(r["reason"] == "launch_error" for r in result["confirmations"])
    completed = subprocess.run(
        [sys.executable, "-m", "reproseed", "replay", str(bundle), "--allow-exec"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 1


def test_non_bmp_unicode_bundle_roundtrip(tmp_path: Path) -> None:
    config = target(
        tmp_path,
        "import sys\nsys.stdout.buffer.write('TARGET😀\\n'.encode('utf8'))\nraise SystemExit(42)",
    )
    (tmp_path / "oracle.py").rename(tmp_path / "oracle😀.py")
    config.write_text(
        config.read_text()
        .replace("oracle.py", "oracle😀.py")
        .replace('marker="TARGET"', 'marker="TARGET😀"'),
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle"
    create_bundle(load_config(config), bundle)
    assert replay_bundle(bundle)["outcome"] == "TARGET_FAILURE"


def test_invalid_utf8_config_and_replay_are_actionable(tmp_path: Path) -> None:
    config = target(tmp_path)
    config.write_bytes(b"\xff")
    with pytest.raises(ConfigError, match="TOML"):
        load_config(config)
    config.unlink()
    (tmp_path / "source.sqlite3").unlink()
    config = target(tmp_path)
    bundle = tmp_path / "bundle"
    create_bundle(load_config(config), bundle)
    (bundle / "replay.toml").write_bytes(b"\xff")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["artifacts"]["replay.toml"] = sha256(bundle / "replay.toml")
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(BundleError):
        validate_bundle(bundle)


def test_source_sidecar_asset_rejected(tmp_path: Path) -> None:
    config = target(tmp_path)
    (tmp_path / "source.sqlite3-wal").write_bytes(b"synthetic sidecar")
    config.write_text(
        config.read_text().replace('include=["oracle.py"]', 'include=["source.sqlite3-wal"]')
    )
    with pytest.raises(ConfigError, match="sidecars"):
        load_config(config)


def test_source_hardlink_asset_rejected(tmp_path: Path) -> None:
    config = target(tmp_path)
    try:
        os.link(tmp_path / "source.sqlite3", tmp_path / "alias.bin")
    except OSError as exc:
        pytest.skip(f"host cannot create hardlinks: {exc}")
    config.write_text(config.read_text().replace('include=["oracle.py"]', 'include=["alias.bin"]'))
    with pytest.raises(ConfigError, match="source"):
        load_config(config)


@pytest.mark.skipif(os.name != "posix", reason="POSIX executable mode semantics")
def test_direct_executable_asset_mode_preserved(tmp_path: Path) -> None:
    config = target(tmp_path)
    script = tmp_path / "oracle.sh"
    script.write_text("#!/bin/sh\nprintf 'TARGET\\n'\nexit 42\n")
    script.chmod(0o755)
    config.write_text(
        config.read_text()
        .replace('include=["oracle.py"]', 'include=["oracle.sh"]')
        .replace('["{python}","oracle.py","{db}"]', '["./oracle.sh","{db}"]')
    )
    bundle = tmp_path / "bundle"
    create_bundle(load_config(config), bundle)
    assert (bundle / "oracle.sh").stat().st_mode & 0o111
    assert replay_bundle(bundle)["outcome"] == "TARGET_FAILURE"
