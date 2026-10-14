"""Private payload acquisition and bounded metadata, using real files and subprocesses."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from reproseed import artifacts, oracle, workflow
from reproseed.artifacts import (
    BundleError,
    VerifiedBundle,
    acquire_bundle,
    create_bundle,
    read_json,
    replay_bundle,
    sha256,
    validate_bundle,
    write_json,
)
from reproseed.config import Asset, Config, ConfigError, OracleSpec, load_config
from reproseed.oracle import OracleInvocation, OracleResult, Outcome
from reproseed.workflow import VerificationError


def _case(tmp_path: Path, *, extra_oracle: str = "") -> Config:
    with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as connection:
        connection.executescript(
            "CREATE TABLE things(id INTEGER PRIMARY KEY, value TEXT);"
            "INSERT INTO things VALUES(1,'pristine');"
        )
    (tmp_path / "data.txt").write_text("pristine", encoding="utf-8")
    (tmp_path / "oracle.py").write_text(
        "import sqlite3,sys\nfrom pathlib import Path\n"
        "c=sqlite3.connect(sys.argv[1])\n"
        "assert c.execute('SELECT value FROM things').fetchone()==('pristine',)\n"
        "assert Path('data.txt').read_text()=='pristine'\n"
        "c.execute(\"UPDATE things SET value='mutated'\"); c.commit(); c.close()\n"
        "Path('data.txt').write_text('mutated')\n"
        + extra_oracle
        + "print('TARGET'); raise SystemExit(42)\n",
        encoding="utf-8",
    )
    config = tmp_path / "case.toml"
    config.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py","data.txt"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        # This fixture checks payload/path security, not a one-second deadline.
        'marker="TARGET"\nstream="stdout"\ntimeout_seconds=5.0\noutput_limit_bytes=4096\n'
        "[reduction]\nmax_invocations=6\n",
        encoding="utf-8",
    )
    return load_config(config)


def _build_with_evidence(
    config: Config,
    destination: Path,
    monkeypatch: pytest.MonkeyPatch,
    observations: list[dict[str, object]],
) -> dict[str, object]:
    """Expose bounded synthetic setup results, including failed final confirmations."""
    invoke = workflow.run_oracle

    def observed(
        spec: OracleSpec,
        database: Path,
        assets: tuple[Asset, ...],
        invocation: OracleInvocation,
    ) -> OracleResult:
        started = time.monotonic()
        result = invoke(spec, database, assets, invocation)
        observations.append(
            {
                "phase": "baseline" if len(observations) < 3 else "final",
                "confirmation": len(observations) % 3 + 1,
                **result.as_dict(),
                "wall_seconds": round(time.monotonic() - started, 6),
                "launch_accounting": invocation.executed,
            }
        )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "run_oracle", observed)
        try:
            return create_bundle(config, destination)
        except VerificationError as exc:
            # No argv, environment or raw output: only synthetic result metadata.
            raise VerificationError(
                f"{exc}; synthetic invocation evidence: {json.dumps(observations, sort_keys=True)}"
            ) from exc


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = _case(tmp_path)
    inputs = (config.path, config.source, *(asset.path for asset in config.assets))
    before = {path.name: sha256(path) for path in inputs}
    execute = oracle._execute
    staged: list[Path] = []

    def fresh(
        spec: OracleSpec,
        root: Path,
        database: Path,
        invocation: OracleInvocation,
        cleanup: oracle._Cleanup,
    ) -> OracleResult:
        assert root not in staged
        staged.append(root)
        result = execute(spec, root, database, invocation, cleanup)
        if result.outcome == Outcome.TARGET_FAILURE:
            # The real script first asserted pristine copies, then mutated both.
            with closing(sqlite3.connect(database)) as connection:
                assert connection.execute("SELECT value FROM things").fetchone() == ("mutated",)
            assert (root / "data.txt").read_text(encoding="utf-8") == "mutated"
        return result

    destination = tmp_path / "bundle"
    observations: list[dict[str, object]] = []
    with monkeypatch.context() as patch:
        patch.setattr(oracle, "_execute", fresh)
        report = _build_with_evidence(config, destination, patch, observations)
    assert len(observations) == len(staged) == 6
    assert all(
        result["outcome"] == "TARGET_FAILURE"
        and result["exit_code"] == 42
        and result["executed"] is True
        and result["launch_accounting"] is True
        for result in observations
    ), observations
    assert report["oracle_invocations"] == report["budget_charged_invocations"] == 6
    assert report["max_invocations"] == 6
    assert report["unknown_interrupted_launches"] == 0
    for name in ("baseline_verification", "final_verification"):
        confirmations = report[name]
        assert isinstance(confirmations, list) and len(confirmations) == 3
        assert all(result["outcome"] == "TARGET_FAILURE" for result in confirmations)
    assert {path.name: sha256(path) for path in inputs} == before
    assert not any(root.exists() for root in staged)
    assert (destination / "data.txt").read_text(encoding="utf-8") == "pristine"
    with closing(sqlite3.connect(destination / "fixture.sqlite3")) as connection:
        assert connection.execute("SELECT value FROM things").fetchone() == ("pristine",)
    return destination


def contents(bundle: Path) -> dict[str, str]:
    return {str(p.relative_to(bundle)): sha256(p) for p in bundle.rglob("*") if p.is_file()}


def rehash(bundle: Path, name: str) -> None:
    manifest = read_json(bundle / "manifest.json")
    manifest["artifacts"][name] = sha256(bundle / name)  # type: ignore[index]
    write_json(bundle / "manifest.json", manifest)


def test_change_between_manifest_capture_and_copy_never_executes(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = artifacts._copy_payload

    def changed(root: Path, destination: Path, names: dict[str, str]) -> None:
        (root / "oracle.py").write_text("raise AssertionError('must not execute')")
        copy(root, destination, names)

    monkeypatch.setattr(artifacts, "_copy_payload", changed)
    monkeypatch.setattr(artifacts, "run_oracle", lambda *args: pytest.fail("oracle executed"))
    with pytest.raises(BundleError, match="hash mismatch"):
        replay_bundle(bundle)


def test_replay_uses_private_payload_after_originals_change(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquire = artifacts.acquire_bundle
    changed_files: dict[str, str] = {}

    @contextmanager
    def changed(original: Path) -> Iterator[VerifiedBundle]:
        with acquire(original) as acquired:
            (original / "oracle.py").write_text("raise AssertionError('original re-read')")
            replay = original / "replay.toml"
            replay.write_text(replay.read_text().replace('"{python}"', '"missing-executable"'))
            (original / "data.txt").write_text("original replaced")
            changed_files.update(contents(original))
            yield acquired

    monkeypatch.setattr(artifacts, "acquire_bundle", changed)
    result = replay_bundle(bundle)
    assert result["outcome"] == "TARGET_FAILURE"
    assert len(result["confirmations"]) == 3  # type: ignore[arg-type]
    assert contents(bundle) == changed_files


def test_oracle_mutations_do_not_contaminate_verified_payload_or_bundle(bundle: Path) -> None:
    before = contents(bundle)
    with acquire_bundle(bundle) as acquired:
        private_before = contents(acquired.root)
        for _ in range(3):
            result = artifacts.run_oracle(
                acquired.config.oracle, acquired.config.source, acquired.config.assets
            )
            assert result.outcome == "TARGET_FAILURE"
            assert contents(acquired.root) == private_before
        temporary_root = acquired.root.parent
    assert not temporary_root.exists()
    validate_bundle(bundle)
    assert contents(bundle) == before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_static_bundle_sidecars_rejected_and_preserved(bundle: Path, suffix: str) -> None:
    sidecar = bundle / ("fixture.sqlite3" + suffix)
    sidecar.write_bytes(b"synthetic unexpected state")
    before = contents(bundle)
    with pytest.raises(BundleError, match="sidecars"):
        validate_bundle(bundle)
    with pytest.raises(BundleError, match="sidecars"):
        replay_bundle(bundle)
    assert contents(bundle) == before


def test_rehashed_final_counts_must_match_fixture(bundle: Path) -> None:
    report = read_json(bundle / "report.json")
    # A complete, internally consistent budget-limited report, but the fixture has one row.
    report["original_counts"] = {"things": 2}
    report["final_counts"] = {"things": 2}
    write_json(bundle / "report.json", report)
    rehash(bundle, "report.json")
    with pytest.raises(BundleError, match="fixture table counts"):
        validate_bundle(bundle)


def test_inspection_validates_only_a_private_database(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = artifacts.DatabaseModel.from_database
    checked: list[Path] = []

    def private(path: Path) -> artifacts.DatabaseModel:
        assert not path.is_relative_to(bundle)
        assert path.parent.name == "check"
        checked.append(path)
        return model(path)

    monkeypatch.setattr(artifacts.DatabaseModel, "from_database", private)
    before = contents(bundle)
    validate_bundle(bundle)
    assert len(checked) == 1
    assert contents(bundle) == before


def test_bundle_symlink_rejected(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "link"
    try:
        link.symlink_to(bundle, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create symlinks: {exc}")
    _assert_link_rejected(bundle, link, "symlink", monkeypatch)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_bundle_junction_rejected(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "junction"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(bundle)], capture_output=True, check=False
    )
    assert completed.returncode == 0
    assert link.is_junction()
    _assert_link_rejected(bundle, link, "junction", monkeypatch)


def _assert_link_rejected(
    bundle: Path, link: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = contents(bundle)
    monkeypatch.setattr(artifacts, "_manifest", lambda *args: pytest.fail("link was followed"))
    monkeypatch.setattr(artifacts, "run_oracle", lambda *args: pytest.fail("oracle executed"))
    with pytest.raises(BundleError, match=kind):
        validate_bundle(link)
    with pytest.raises(BundleError, match=kind):
        replay_bundle(link)
    assert contents(bundle) == before
    assert link.exists()


@pytest.mark.parametrize(
    "phase,confirmation", [(phase, n) for phase in ("baseline", "final") for n in (1, 2, 3)]
)
def test_one_deadline_confirmation_never_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str, confirmation: int
) -> None:
    """Expire a live real subprocess at a readiness handshake, not a sleep race."""
    ready = tmp_path / "ready"
    state = tmp_path / "invocations"
    slow = confirmation if phase == "baseline" else 3 + confirmation
    config = _case(
        tmp_path,
        extra_oracle=(
            "import time\n"
            f"state=Path({str(state)!r})\n"
            "number=int(state.read_text())+1 if state.exists() else 1\n"
            "state.write_text(str(number))\n"
            f"if number=={slow}:\n"
            f"    Path({str(ready)!r}).write_text('ready')\n"
            "    time.sleep(30)\n"
        ),
    )
    inputs = (config.path, config.source, *(asset.path for asset in config.assets))
    before = {path.name: sha256(path) for path in inputs}
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "keep.txt").write_text("synthetic user work", encoding="utf-8")
    existing_before = contents(existing)
    destination = tmp_path / "bundle"
    original_clock = time.monotonic
    offset = 0.0

    def clock() -> float:
        nonlocal offset
        if not offset and ready.exists():
            # Latch once: later cleanup reads advance at the unchanged real rate.
            offset = config.oracle.timeout_seconds + 1.0
        return original_clock() + offset

    monkeypatch.setattr(oracle, "time", SimpleNamespace(monotonic=clock, sleep=time.sleep))
    observations: list[dict[str, object]] = []
    with pytest.raises(VerificationError, match=phase) as failure:
        _build_with_evidence(config, destination, monkeypatch, observations)
    assert offset and ready.read_text() == "ready"
    assert len(observations) == (3 if phase == "baseline" else 6)
    assert state.read_text() == str(len(observations))
    for number, result in enumerate(observations, 1):
        assert result["executed"] is True and result["launch_accounting"] is True
        if number == slow:
            assert result["outcome"] == "UNRESOLVED"
            assert result["reason"] == "deadline exceeded (process or open output pipes)"
        else:
            assert result["outcome"] == "TARGET_FAILURE" and result["exit_code"] == 42
    assert '"outcome": "UNRESOLVED"' in str(failure.value)
    assert '"launch_accounting": true' in str(failure.value)
    assert not destination.exists()
    assert not list(tmp_path.glob(".reproseed-build-*"))
    assert {path.name: sha256(path) for path in inputs} == before
    with pytest.raises(BundleError, match="output already exists"):
        create_bundle(config, existing)
    assert contents(existing) == existing_before


def test_setup_failure_reports_classifications_without_raw_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _case(
        tmp_path,
        extra_oracle="print('synthetic raw output must stay private'); raise SystemExit(41)\n",
    )
    observations: list[dict[str, object]] = []
    with pytest.raises(VerificationError) as failure:
        _build_with_evidence(config, tmp_path / "bundle", monkeypatch, observations)
    message = str(failure.value)
    assert len(observations) == 3
    assert '"phase": "baseline"' in message
    assert '"reason": "unexpected exit code"' in message
    assert '"exit_code": 41' in message
    assert '"wall_seconds":' in message and '"duration_seconds":' in message
    assert '"launch_accounting": true' in message
    assert "synthetic raw output must stay private" not in message


@pytest.mark.parametrize(
    "document",
    [
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":-Infinity}',
        b'{"a":1e999}',
        b'{"a":-1e999}',
        b'{"a":"\xff"}',
        b'{"a":',
        b"[]",
        b'{"a":' + b"[" * 70 + b"0" + b"]" * 70 + b"}",
        b'{"a":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}",
    ],
)
def test_bad_json_is_actionable(tmp_path: Path, document: bytes) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(document)
    with pytest.raises(BundleError):
        read_json(path)


def test_actual_read_size_is_bounded_despite_small_stat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b'{"long":"' + b"x" * 65 + b'"}')
    stat = Path.stat

    def stale_stat(file: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = stat(file, follow_symlinks=follow_symlinks)
        if file == path:
            fields = list(result)
            fields[6] = 0
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(Path, "stat", stale_stat)
    monkeypatch.setattr(artifacts, "JSON_LIMIT", 64)
    with pytest.raises(BundleError, match="exceeds 64 bytes"):
        read_json(path)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
def test_writer_rejects_nonfinite_numbers(tmp_path: Path, number: float) -> None:
    path = tmp_path / "bad.json"
    with pytest.raises(BundleError, match="serialize finite"):
        write_json(path, {"value": number})
    assert not path.exists()


def test_config_actual_read_limit(tmp_path: Path) -> None:
    path = tmp_path / "oversized.toml"
    path.write_bytes(b"#" * (1024 * 1024 + 1))
    with pytest.raises(ConfigError, match="exceeds 1 MiB"):
        load_config(path)


def test_large_toml_integer_is_an_actionable_error(bundle: Path, tmp_path: Path) -> None:
    from reproseed.cli import main

    path = tmp_path / "large-integer.toml"
    path.write_text("version=" + "9" * 5000)
    with pytest.raises(ConfigError, match="cannot read TOML"):
        load_config(path)
    (bundle / "replay.toml").write_text(path.read_text())
    rehash(bundle, "replay.toml")
    assert main(["inspect", str(bundle)]) == 2
    assert main(["replay", str(bundle), "--allow-exec"]) == 2


def test_malformed_bundle_metadata_returns_existing_error_category(bundle: Path) -> None:
    from reproseed.cli import main

    (bundle / "manifest.json").write_bytes(b'{"bad":"\xff"}')
    assert main(["inspect", str(bundle)]) == 2


def test_undeclared_file_is_not_acquired(bundle: Path) -> None:
    (bundle / "undeclared.txt").write_text("synthetic secret")
    before = contents(bundle)
    with acquire_bundle(bundle) as acquired:
        assert not (acquired.root / "undeclared.txt").exists()
    assert contents(bundle) == before
