"""Deterministic cancellation boundaries with real SQLite and oracle subprocesses."""

from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import FrameType
from typing import Any

import pytest

from reproseed import reducer, workflow
from reproseed.artifacts import create_bundle, sha256, validate_bundle
from reproseed.cli import main
from reproseed.config import Asset, Config, OracleSpec, load_config
from reproseed.oracle import OracleInterrupted, OracleInvocation, OracleResult, Outcome, run_oracle
from reproseed.report import validate_report
from reproseed.sqlite_adapter import DatabaseModel

REPOSITORY = Path(__file__).resolve().parents[1]
INTERRUPTED = "interrupted_best_confirmed_candidate_preserved"


def _files(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): sha256(path)
        for path in directory.rglob("*")
        if path.is_file()
    }


def _case(
    root: Path, *, rows: int = 2, cycle: bool = False, empty_fails: bool = False, budget: int = 40
) -> Config:
    root.mkdir()
    with closing(sqlite3.connect(root / "source.sqlite3")) as database:
        if cycle:
            database.executescript(
                "CREATE TABLE items(id INTEGER PRIMARY KEY, peer INTEGER REFERENCES items(id));"
                "INSERT INTO items VALUES(1,2),(2,1);"
            )
        else:
            database.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, value TEXT)")
            database.executemany(
                "INSERT INTO items VALUES(?,?)", [(i, f"synthetic-{i}") for i in range(1, rows + 1)]
            )
            database.commit()
    (root / "oracle.py").write_text(
        "import sqlite3,sys\n"
        "with sqlite3.connect(sys.argv[1]) as db:\n"
        "    count=db.execute('SELECT count(*) FROM items').fetchone()[0]\n"
        f"if count or {empty_fails!r}:\n"
        "    print('TARGET')\n"
        "    raise SystemExit(42)\n",
        encoding="utf-8",
    )
    path = root / "case.toml"
    path.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="TARGET"\nstream="stdout"\ntimeout_seconds=2.0\noutput_limit_bytes=4096\n'
        f"[reduction]\nmax_invocations={budget}\n",
        encoding="utf-8",
    )
    return load_config(path)


def _cli(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "reproseed", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return result


def _verified_lifecycle(
    config: Config,
    bundle: Path,
    report: dict[str, Any],
    source_files: dict[str, str],
    *,
    invocations: int,
) -> None:
    """Check all salvaged evidence, then independently inspect and relocate/replay."""
    original = DatabaseModel.from_database(config.source)
    fixture = DatabaseModel.from_database(bundle / "fixture.sqlite3")
    assert fixture.counts() == report["final_counts"]
    assert original.counts() == report["original_counts"]
    with closing(sqlite3.connect(config.source)) as source_db:
        with closing(sqlite3.connect(bundle / "fixture.sqlite3")) as fixture_db:
            schema_sql = "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
            assert (
                fixture_db.execute(schema_sql).fetchall()
                == source_db.execute(schema_sql).fetchall()
            )
            assert set(fixture_db.execute("SELECT * FROM items")) <= set(
                source_db.execute("SELECT * FROM items")
            )
            assert fixture_db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert fixture_db.execute("PRAGMA foreign_key_check").fetchall() == []
    replay_config, acquired_report = validate_bundle(bundle)
    assert acquired_report == report
    validate_report(report, replay_config)
    current = sum(report["original_counts"].values())
    for accepted in report["accepted_reductions"]:
        assert accepted["before"] == current
        evidence = report["attempts"][accepted["attempt"] - 1]
        assert evidence["outcome"] == "TARGET_FAILURE"
        assert len(evidence["confirmations"]) == 2
        assert all(r["outcome"] == "TARGET_FAILURE" for r in evidence["confirmations"])
        current = accepted["after"]
    assert current == sum(report["final_counts"].values())
    for field, predicate in (
        ("cache_hits", lambda attempt: attempt["cached"]),
        ("invalid_candidates", lambda attempt: attempt["outcome"] == "DATABASE_INVALID"),
        ("unresolved_attempts", lambda attempt: attempt["outcome"] == "UNRESOLVED"),
    ):
        assert report[field] == sum(predicate(a) for a in report["attempts"])
    for field in ("baseline_verification", "final_verification"):
        assert len(report[field]) == 3
        assert all(r["outcome"] == "TARGET_FAILURE" and r["executed"] for r in report[field])
    assert report["oracle_invocations"] == invocations
    assert report["unknown_interrupted_launches"] == 0
    assert report["budget_charged_invocations"] == invocations <= config.max_invocations
    assert _files(config.path.parent) == source_files
    bundle_files = _files(bundle)
    default = _cli(["inspect", str(bundle)], bundle.parent)
    explicit = _cli(["inspect", str(bundle), "--format", "json"], bundle.parent)
    assert json.loads(default.stdout) == report
    assert explicit.stdout == default.stdout
    text = _cli(["inspect", str(bundle), "--format", "text"], bundle.parent)
    assert "Recorded baseline confirmations: 3/3 TARGET_FAILURE" in text.stdout
    assert "Recorded final confirmations: 3/3 TARGET_FAILURE" in text.stdout
    assert "New replay: not performed by inspect" in text.stdout
    if report["termination_reason"] == INTERRUPTED:
        assert "Search interrupted; the best confirmed candidate was preserved" in text.stdout
    assert _files(bundle) == bundle_files
    with tempfile.TemporaryDirectory(prefix="reproseed-interrupted-relocation-") as temporary:
        root = Path(temporary)
        assert not root.is_relative_to(REPOSITORY)
        relocated = root / "relocated"
        shutil.copytree(bundle, relocated)
        unavailable_source = config.path.parent.with_name(config.path.parent.name + "-unavailable")
        unavailable_bundle = bundle.with_name(bundle.name + "-unavailable")
        config.path.parent.rename(unavailable_source)
        bundle.rename(unavailable_bundle)
        unrelated = root / "unrelated"
        unrelated.mkdir()
        before_replay = _files(relocated)
        replay = json.loads(_cli(["replay", str(relocated), "--allow-exec"], unrelated).stdout)
        assert replay["outcome"] == "TARGET_FAILURE"
        assert len(replay["confirmations"]) == 3
        assert all(
            r["outcome"] == "TARGET_FAILURE" and r["executed"] for r in replay["confirmations"]
        )
        assert _files(relocated) == before_replay
    assert _files(unavailable_source) == source_files
    assert _files(unavailable_bundle) == bundle_files
    (bundle.parent / "lifecycle-evidence.json").write_text(
        json.dumps({"report": report, "replay": replay, "source_sha256": source_files}, indent=2),
        encoding="utf-8",
    )


def _track_real_invocations(monkeypatch: pytest.MonkeyPatch) -> list[OracleResult]:
    results: list[OracleResult] = []

    def tracked(
        spec: OracleSpec,
        database: Path,
        assets: tuple[Asset, ...],
        invocation: OracleInvocation | None = None,
    ) -> OracleResult:
        result = run_oracle(spec, database, assets, invocation)
        results.append(result)
        return result

    monkeypatch.setattr(workflow, "run_oracle", tracked)
    return results


def _pending_attempt(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    for value in (*args, *kwargs.values()):
        if isinstance(value, list) and value and isinstance(value[-1], dict):
            if "cached" in value[-1]:
                return value[-1]
        if isinstance(value, dict) and "cached" in value:
            return value
    raise AssertionError("progress publication did not expose a pending attempt")


@pytest.mark.parametrize("boundary", ["acceptance", "cache", "completed_evaluation"])
def test_interrupted_pending_progress_real_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    config = _case(tmp_path / "source", cycle=boundary == "cache")
    source_files = _files(config.path.parent)
    results = _track_real_invocations(monkeypatch)
    original = reducer._commit_progress
    injected = False

    def interrupt(*args: Any, **kwargs: Any) -> Any:
        nonlocal injected
        pending = original(*args, **kwargs)
        attempt = _pending_attempt(args, kwargs)
        selected = (
            attempt["outcome"] == "TARGET_FAILURE"
            if boundary == "acceptance"
            else attempt["cached"]
            if boundary == "cache"
            else not attempt["cached"] and attempt["outcome"] == "PASS"
        )
        if selected and not injected:
            injected = True
            raise KeyboardInterrupt
        return pending

    monkeypatch.setattr(reducer, "_commit_progress", interrupt)
    bundle = tmp_path / "bundle"
    report = create_bundle(config, bundle)
    assert injected
    assert report["termination_reason"] == INTERRUPTED
    assert report["final_counts"] == {"items": 2}
    assert report["accepted_reductions"] == []
    assert report["cache_hits"] == 0
    assert len(results) == (9 if boundary == "acceptance" else 7)
    _verified_lifecycle(config, bundle, report, source_files, invocations=len(results))


def test_interruption_after_complete_progress_preserves_new_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _case(tmp_path / "source")
    source_files = _files(config.path.parent)
    results = _track_real_invocations(monkeypatch)
    injected = False

    def trace(frame: FrameType, event: str, arg: Any) -> Any:
        nonlocal injected
        checkpoint = frame.f_locals.get("checkpoint")
        if (
            frame.f_code is reducer.reduce_rows.__code__
            and event == "line"
            and checkpoint is not None
            and checkpoint.accepted_count == 1
            and not injected
        ):
            injected = True
            sys.settrace(None)
            raise KeyboardInterrupt
        return trace

    old_trace = sys.gettrace()
    sys.settrace(trace)
    try:
        bundle = tmp_path / "bundle"
        report = create_bundle(config, bundle)
    finally:
        sys.settrace(old_trace)
    assert injected
    assert report["termination_reason"] == INTERRUPTED
    assert report["final_counts"] == {"items": 1}
    assert report["accepted_reductions"] == [{"attempt": 2, "before": 2, "after": 1}]
    _verified_lifecycle(config, bundle, report, source_files, invocations=len(results))


@pytest.mark.parametrize("confirmation", [1, 2])
@pytest.mark.parametrize("previous_acceptance", [False, True])
def test_first_and_second_candidate_confirmation_preserve_committed_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    confirmation: int,
    previous_acceptance: bool,
) -> None:
    config = _case(
        tmp_path / "source",
        rows=4 if previous_acceptance else 2,
        empty_fails=not previous_acceptance,
    )
    source_files = _files(config.path.parent)
    results: list[OracleResult] = []
    interrupt_call = (6 if previous_acceptance else 3) + confirmation

    def interrupt(
        spec: OracleSpec,
        database: Path,
        assets: tuple[Asset, ...],
        invocation: OracleInvocation | None = None,
    ) -> OracleResult:
        result = run_oracle(spec, database, assets, invocation)
        results.append(result)
        if len(results) == interrupt_call:
            assert result.outcome == Outcome.TARGET_FAILURE
            raise OracleInterrupted(True)
        return result

    monkeypatch.setattr(workflow, "run_oracle", interrupt)
    bundle = tmp_path / "bundle"
    report = create_bundle(config, bundle)
    assert report["termination_reason"] == INTERRUPTED
    assert report["final_counts"] == {"items": 2}
    assert len(report["accepted_reductions"]) == int(previous_acceptance)
    assert report["interrupted_invocations"] == [
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": True}
    ]
    assert len(results) == interrupt_call + 3
    _verified_lifecycle(config, bundle, report, source_files, invocations=len(results))


@pytest.mark.parametrize("case", ["budget", "empty", "irreducible", "normal"])
def test_ordinary_real_workflows_keep_confirmation_and_budget_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    config = _case(
        tmp_path / "source",
        rows=0 if case == "empty" else 1 if case == "irreducible" else 2,
        empty_fails=case == "empty",
        budget=6 if case == "budget" else 40,
    )
    source_files = _files(config.path.parent)
    results = _track_real_invocations(monkeypatch)
    bundle = tmp_path / "bundle"
    report = create_bundle(config, bundle)
    assert report["final_counts"] == {
        "items": 0 if case == "empty" else 2 if case == "budget" else 1
    }
    if case == "budget":
        assert report["termination_reason"] == "oracle_budget_exhausted_reserved_final_verification"
        assert len(results) == 6
    elif case == "empty":
        assert report["termination_reason"] == "empty_candidate_confirmed"
        assert len(results) == 6
    else:
        assert report["termination_reason"] == "single_row_closures_exhausted"
    _verified_lifecycle(config, bundle, report, source_files, invocations=len(results))


@pytest.mark.parametrize(
    "boundary", ["baseline", "finalization", "final_confirmation", "second_interrupt"]
)
def test_cli_aborts_incomplete_verification_and_cleans_tool_owned_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    boundary: str,
) -> None:
    config = _case(tmp_path / "source")
    source_files = _files(config.path.parent)
    results: list[OracleResult] = []
    interrupt_call = 1 if boundary == "baseline" else 7

    def interrupt(
        spec: OracleSpec,
        database: Path,
        assets: tuple[Asset, ...],
        invocation: OracleInvocation | None = None,
    ) -> OracleResult:
        result = run_oracle(spec, database, assets, invocation)
        results.append(result)
        if boundary != "finalization" and len(results) == interrupt_call:
            raise OracleInterrupted(True)
        return result

    monkeypatch.setattr(workflow, "run_oracle", interrupt)
    if boundary == "finalization":
        original_compact = workflow.compact

        def interrupted_compact(source: Path, destination: Path) -> None:
            original_compact(source, destination)
            assert destination.is_file()
            raise KeyboardInterrupt

        monkeypatch.setattr(workflow, "compact", interrupted_compact)
    if boundary == "second_interrupt":
        original_progress = reducer._commit_progress

        def interrupted_progress(*args: Any, **kwargs: Any) -> Any:
            pending = original_progress(*args, **kwargs)
            if _pending_attempt(args, kwargs)["outcome"] == "TARGET_FAILURE":
                raise KeyboardInterrupt
            return pending

        monkeypatch.setattr(reducer, "_commit_progress", interrupted_progress)
    bundle = tmp_path / "bundle"
    code = main(["reduce", "--config", str(config.path), "--out", str(bundle), "--allow-exec"])
    captured = capsys.readouterr()
    assert code == 130
    assert not captured.out
    assert "interrupted before a verified bundle could be completed" in captured.err
    assert len(results) == (1 if boundary == "baseline" else 6 if boundary == "finalization" else 7)
    assert all(result.executed for result in results)
    assert not bundle.exists()
    assert not list(tmp_path.glob(".reproseed-build-*"))
    assert _files(config.path.parent) == source_files


def test_cli_preserves_preexisting_output_before_any_oracle_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _case(tmp_path / "source")
    source_files = _files(config.path.parent)
    results = _track_real_invocations(monkeypatch)
    bundle = tmp_path / "preexisting"
    bundle.mkdir()
    (bundle / "user-work.txt").write_bytes(b"existing user work\x00\xff")
    existing = _files(bundle)
    assert main(["reduce", "--config", str(config.path), "--out", str(bundle), "--allow-exec"]) == 2
    assert "output already exists" in capsys.readouterr().err
    assert not results
    assert _files(bundle) == existing
    assert _files(config.path.parent) == source_files


@pytest.mark.skipif(os.name != "posix", reason="real SIGINT workflow smoke requires POSIX signals")
def test_real_sigint_at_pending_acceptance_finalizes_verified_bundle(tmp_path: Path) -> None:
    config = _case(tmp_path / "source")
    source_files = _files(config.path.parent)
    bundle = tmp_path / "bundle"
    driver = (
        "import signal,sys,threading\n"
        "from reproseed import reducer\n"
        "from reproseed.cli import main\n"
        "signal.signal(signal.SIGINT, signal.default_int_handler)\n"
        "original=reducer._commit_progress\n"
        "def pause(*args, **kwargs):\n"
        "    pending=original(*args,**kwargs)\n"
        "    attempts=next(a for a in args if isinstance(a,list) and a "
        "and isinstance(a[-1],dict) and 'cached' in a[-1])\n"
        "    if attempts[-1]['outcome']=='TARGET_FAILURE':\n"
        "        print('READY acceptance_before_publication',flush=True)\n"
        "        if not threading.Event().wait(20):\n"
        "            raise RuntimeError('signal handshake deadline exceeded')\n"
        "    return pending\n"
        "reducer._commit_progress=pause\n"
        "raise SystemExit(main(['reduce','--config',sys.argv[1],"
        "'--out',sys.argv[2],'--allow-exec']))\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", driver, str(config.path), str(bundle)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        ready = executor.submit(process.stdout.readline).result(timeout=15)
        assert ready == "READY acceptance_before_publication\n"
        os.kill(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stdout + stderr
        assert json.loads(stdout)["termination_reason"] == INTERRUPTED
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
        executor.shutdown(wait=True)
    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] == INTERRUPTED
    assert report["final_counts"] == {"items": 2}
    assert report["accepted_reductions"] == []
    _verified_lifecycle(config, bundle, report, source_files, invocations=9)
