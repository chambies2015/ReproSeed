"""Diagnostic CLI regressions with real SQLite inputs and bounded subprocesses."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest

from reproseed.artifacts import sha256
from reproseed.cli import main
from reproseed.oracle import OracleInterrupted, OracleResult, run_oracle


def _case(
    root: Path,
    program: str,
    *,
    expected_exit: int = 42,
    stream: str = "stdout",
    timeout: float = 3.0,
    output_limit: int = 4096,
    argv: list[str] | None = None,
    schema: str = "CREATE TABLE items(id INTEGER PRIMARY KEY, quantity INTEGER);"
    "INSERT INTO items VALUES(17,6),(91,7);",
) -> Path:
    root.mkdir()
    with closing(sqlite3.connect(root / "source.sqlite3")) as database:
        database.executescript(schema)
    (root / "oracle.py").write_text(program, encoding="utf-8")
    (root / "support.txt").write_text("pristine-support", encoding="utf-8")
    command = argv or ["{python}", "oracle.py", "{db}"]
    config = root / "reproseed.toml"
    config.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py","support.txt"]\n'
        f"[oracle]\nargv={json.dumps(command)}\nexpected_exit={expected_exit}\n"
        f'marker="TARGET_DIAGNOSIS"\nstream="{stream}"\ntimeout_seconds={timeout}\n'
        f"output_limit_bytes={output_limit}\n[reduction]\nmax_invocations=20\n",
        encoding="utf-8",
    )
    return config


def _cli(config: Path, cwd: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reproseed", "diagnose", "--config", str(config), *options],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )


def _hashes(root: Path) -> dict[str, str]:
    return {path.name: sha256(path) for path in root.iterdir() if path.is_file()}


TARGET = "print('TARGET_DIAGNOSIS'); raise SystemExit(42)\n"


def test_static_never_launches_and_text_json_agree_from_unrelated_cwd(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel"
    config = _case(
        tmp_path / "case",
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('launched')\n" + TARGET,
    )
    before = _hashes(config.parent)
    result = _cli(config, tmp_path, "--format", "json")
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["diagnostic_version"] == 1
    assert document["mode"] == "static"
    assert document["snapshot_acquired"] is True
    assert document["schema_supported"] is True
    assert document["structurally_suitable"] is True
    assert document["table_counts"] == {"items": 2}
    assert document["total_rows"] == 2
    assert document["oracle_executed"] is False
    assert document["baseline_confirmed"] is False
    assert document["actual_invocations"] == 0
    assert document["baseline_results"] == []
    text = _cli(config, tmp_path)
    assert text.returncode == 0, text.stderr
    assert "not executed" in text.stdout.lower()
    assert "not established" in text.stdout.lower()
    assert "items" in text.stdout
    assert "--allow-exec" in text.stdout
    assert str(config.parent) not in result.stdout + text.stdout
    assert not sentinel.exists()
    assert _hashes(config.parent) == before
    executable = _cli(config, tmp_path, "--allow-exec", "--format", "json")
    assert executable.returncode == 0, executable.stderr
    evidence = json.loads(executable.stdout)
    assert evidence["table_counts"] == document["table_counts"]
    assert evidence["oracle_executed"] is True
    assert evidence["baseline_confirmed"] is True
    assert evidence["actual_invocations"] == 3
    assert sentinel.read_text() == "launched"
    assert _hashes(config.parent) == before


@pytest.mark.parametrize(
    ("program", "expected_exit", "stream", "outcome", "reason", "exit_code"),
    [
        (TARGET, 42, "stdout", "TARGET_FAILURE", "expected exit and exact failure marker", 42),
        (
            "import sys; print('TARGET_DIAGNOSIS',file=sys.stderr); raise SystemExit(42)",
            42,
            "stderr",
            "TARGET_FAILURE",
            "expected exit and exact failure marker",
            42,
        ),
        ("raise SystemExit(0)", 42, "stdout", "PASS", "zero exit without target marker", 0),
        (TARGET, 43, "stdout", "UNRESOLVED", "unexpected exit code", 42),
        (
            "raise SystemExit(42)",
            42,
            "stdout",
            "UNRESOLVED",
            "expected failure exit without exact marker",
            42,
        ),
        (
            "import sys; print('TARGET_DIAGNOSIS',file=sys.stderr); raise SystemExit(42)",
            42,
            "stdout",
            "UNRESOLVED",
            "expected failure exit without exact marker",
            42,
        ),
        (
            "raise RuntimeError('PRIVATE_CRASH_DETAIL')",
            42,
            "stdout",
            "UNRESOLVED",
            "unexpected exit code",
            1,
        ),
        (
            "print('TARGET_DIAGNOSIS'); raise SystemExit(44)",
            42,
            "stdout",
            "UNRESOLVED",
            "unexpected exit code",
            44,
        ),
        (
            "print('TARGET_DIAGNOSIS')",
            42,
            "stdout",
            "UNRESOLVED",
            "target marker contradicts zero exit",
            0,
        ),
    ],
)
def test_actual_contract_classifications_and_text(
    tmp_path: Path,
    program: str,
    expected_exit: int,
    stream: str,
    outcome: str,
    reason: str,
    exit_code: int,
) -> None:
    config = _case(tmp_path / "case", program, expected_exit=expected_exit, stream=stream)
    static = _cli(config, tmp_path, "--format", "json")
    assert static.returncode == 0
    assert json.loads(static.stdout)["baseline_confirmed"] is False
    result = _cli(config, tmp_path, "--allow-exec", "--format", "json")
    assert result.returncode == (0 if outcome == "TARGET_FAILURE" else 1), result.stderr
    document = json.loads(result.stdout)
    assert document["actual_invocations"] == document["budget_charged_invocations"] == 3
    assert document["unknown_interrupted_launches"] == 0
    assert document["baseline_confirmed"] is (outcome == "TARGET_FAILURE")
    assert len(document["baseline_results"]) == 3
    for confirmation in document["baseline_results"]:
        assert confirmation["outcome"] == outcome
        assert confirmation["reason"] == reason
        assert confirmation["exit_code"] == exit_code
        assert confirmation["executed"] is True
        assert confirmation["duration_seconds"] >= 0
        assert confirmation["output_bytes"] >= 0
    assert "PRIVATE_CRASH_DETAIL" not in result.stdout + result.stderr
    text = _cli(config, tmp_path, "--allow-exec")
    assert text.returncode == result.returncode
    assert outcome in text.stdout
    assert reason in text.stdout
    assert "exit" in text.stdout.lower() and "marker" in text.stdout.lower()


def test_correct_application_source_is_pass(tmp_path: Path) -> None:
    program = (
        "import sqlite3,sys\n"
        "with sqlite3.connect(sys.argv[1]) as db:\n"
        "    values=[r[0] for r in db.execute('SELECT quantity FROM items')]\n"
        "    accepted=sum(values) <= 20\n"
        "    if not accepted:\n"
        "        print('TARGET_DIAGNOSIS'); raise SystemExit(42)\n"
    )
    config = _case(tmp_path / "case", program)
    result = _cli(config, tmp_path, "--allow-exec", "--format", "json")
    assert result.returncode == 1
    assert [r["outcome"] for r in json.loads(result.stdout)["baseline_results"]] == ["PASS"] * 3


def test_static_diagnosis_counts_committed_wal_without_source_writes(tmp_path: Path) -> None:
    config = _case(tmp_path / "case", TARGET)
    source = config.parent / "source.sqlite3"
    with closing(sqlite3.connect(source)) as database:
        assert database.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        database.execute("PRAGMA wal_autocheckpoint=0")
        database.execute("INSERT INTO items VALUES(200,3)")
        database.commit()
        wal = source.with_name(source.name + "-wal")
        before = (sha256(source), sha256(wal))
        result = _cli(config, tmp_path, "--format", "json")
        assert result.returncode == 0, result.stdout + result.stderr
        document = json.loads(result.stdout)
        assert document["table_counts"] == {"items": 3}
        assert document["total_rows"] == 3
        assert document["oracle_executed"] is False
        assert (sha256(source), sha256(wal)) == before


@pytest.mark.parametrize(("kind", "reason"), [("timeout", "deadline"), ("output", "output limit")])
def test_timeout_and_output_bounds(tmp_path: Path, kind: str, reason: str) -> None:
    program = (
        "import threading; threading.Event().wait(10)"
        if kind == "timeout"
        else "import os; os.write(1,b'PRIVATE_OUTPUT'*1000); raise SystemExit(42)"
    )
    config = _case(
        tmp_path / "case", program, timeout=0.15 if kind == "timeout" else 3.0, output_limit=64
    )
    result = _cli(config, tmp_path, "--allow-exec", "--format", "json")
    assert result.returncode == 1, result.stderr
    document = json.loads(result.stdout)
    assert document["actual_invocations"] == 3
    assert all(r["outcome"] == "UNRESOLVED" for r in document["baseline_results"])
    assert all(reason in r["reason"] for r in document["baseline_results"])
    assert "PRIVATE_OUTPUT" not in result.stdout + result.stderr


def test_launch_failure_is_known_nonlaunch(tmp_path: Path) -> None:
    config = _case(tmp_path / "case", TARGET, argv=["reproseed-missing-synthetic-executable"])
    result = _cli(config, tmp_path, "--allow-exec", "--format", "json")
    assert result.returncode == 1, result.stderr
    document = json.loads(result.stdout)
    assert document["actual_invocations"] == document["budget_charged_invocations"] == 0
    assert document["oracle_executed"] is False
    assert document["baseline_confirmed"] is False
    assert document["baseline_results"]
    assert all(r["executed"] is False for r in document["baseline_results"])
    assert all(r["outcome"] == "UNRESOLVED" for r in document["baseline_results"])


def test_deterministic_inconsistent_baseline_preserves_all_observations(tmp_path: Path) -> None:
    state = tmp_path / "test-owned-launch-count"
    program = (
        "from pathlib import Path\n"
        f"state=Path({str(state)!r})\n"
        "count=int(state.read_text())+1 if state.exists() else 1\n"
        "state.write_text(str(count))\n"
        "if count == 1:\n    print('TARGET_DIAGNOSIS'); raise SystemExit(42)\n"
        "if count == 2:\n    raise SystemExit(0)\n"
        "raise SystemExit(9)\n"
    )
    config = _case(tmp_path / "case", program)
    result = _cli(config, tmp_path, "--allow-exec", "--format", "json")
    assert result.returncode == 1
    document = json.loads(result.stdout)
    assert [r["outcome"] for r in document["baseline_results"]] == [
        "TARGET_FAILURE",
        "PASS",
        "UNRESOLVED",
    ]
    assert document["baseline_confirmed"] is False
    assert document["actual_invocations"] == 3
    assert state.read_text() == "3"


@pytest.mark.parametrize("invalid", ["schema", "foreign_keys", "asset", "config", "traversal"])
def test_invalid_input_never_launches_and_returns_json(tmp_path: Path, invalid: str) -> None:
    sentinel = tmp_path / "must-not-launch"
    schema = (
        "CREATE TABLE items(id TEXT PRIMARY KEY);"
        if invalid == "schema"
        else "CREATE TABLE items(id INTEGER PRIMARY KEY);"
        "CREATE TABLE children(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES items(id));"
        "INSERT INTO children VALUES(4,999);"
        if invalid == "foreign_keys"
        else "CREATE TABLE items(id INTEGER PRIMARY KEY);"
    )
    config = _case(
        tmp_path / "case",
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n" + TARGET,
        schema=schema,
    )
    if invalid == "asset":
        (config.parent / "support.txt").unlink()
    elif invalid == "config":
        config.write_text("version=1\nversion=2\n", encoding="utf-8")
    elif invalid == "traversal":
        config.write_text(config.read_text().replace("support.txt", "../support.txt"))
    before = _hashes(config.parent)
    result = _cli(config, tmp_path, "--allow-exec", "--format", "json")
    assert result.returncode == 2, result.stdout + result.stderr
    document = json.loads(result.stdout)
    assert document["structurally_suitable"] is False
    assert document["baseline_results"] == []
    assert document["actual_invocations"] == 0
    assert document["oracle_executed"] is False
    assert document["error"] is not None
    assert str(config.parent) not in result.stdout
    assert not sentinel.exists()
    assert _hashes(config.parent) == before


def test_fresh_confirmations_discard_database_and_asset_mutations(tmp_path: Path) -> None:
    ledger = tmp_path / "invocations.jsonl"
    program = (
        "import json,sqlite3,sys\nfrom pathlib import Path\n"
        "database=Path(sys.argv[1]); support=Path('support.txt')\n"
        "assert support.read_text() == 'pristine-support'\n"
        "with sqlite3.connect(database) as db:\n"
        "    assert db.execute('SELECT count(*) FROM items').fetchone()[0] == 2\n"
        "    db.execute('DELETE FROM items'); db.commit()\n"
        "support.write_text('MUTATED_SUPPORT')\n"
        f"with Path({str(ledger)!r}).open('a') as log:\n"
        "    log.write(json.dumps(str(database.parent))+'\\n')\n" + TARGET
    )
    config = _case(tmp_path / "case", program)
    before = _hashes(config.parent)
    result = _cli(config, tmp_path, "--allow-exec", "--format", "json")
    assert result.returncode == 0, result.stdout + result.stderr
    document = json.loads(result.stdout)
    assert document["actual_invocations"] == 3
    assert document["baseline_confirmed"] is True
    roots = [Path(json.loads(line)) for line in ledger.read_text().splitlines()]
    assert len(set(roots)) == 3
    assert all(not root.exists() for root in roots)
    assert _hashes(config.parent) == before
    assert "MUTATED_SUPPORT" not in result.stdout


def test_text_escapes_table_controls(tmp_path: Path) -> None:
    name = 'inventory\x1b[31m\n\u202e"lots'
    quoted = '"' + name.replace('"', '""') + '"'
    config = _case(
        tmp_path / "case", TARGET, schema=f"CREATE TABLE {quoted}(id INTEGER PRIMARY KEY)"
    )
    result = _cli(config, tmp_path)
    assert result.returncode == 0
    assert "\x1b" not in result.stdout
    assert "\u202e" not in result.stdout
    assert "\\u001b" in result.stdout and "\\u202e" in result.stdout
    document = json.loads(_cli(config, tmp_path, "--format", "json").stdout)
    assert document["table_counts"] == {name: 0}


def test_completed_launch_interruption_is_charged_and_cleanup_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "owned-root"
    program = (
        "from pathlib import Path\nimport sys\n"
        f"Path({str(ledger)!r}).write_text(str(Path(sys.argv[1]).parent))\n" + TARGET
    )
    config = _case(tmp_path / "case", program)
    before = _hashes(config.parent)

    def lost_return(*args: object) -> OracleResult:
        result = run_oracle(*args)
        assert result.executed is True
        raise OracleInterrupted(True)

    monkeypatch.setattr("reproseed.workflow.run_oracle", lost_return)
    assert main(["diagnose", "--config", str(config), "--allow-exec", "--format", "json"]) == 130
    output = capsys.readouterr()
    document = json.loads(output.out)
    assert document["interrupted"] is True
    assert document["baseline_confirmed"] is False
    assert document["actual_invocations"] == document["budget_charged_invocations"] == 1
    assert document["unknown_interrupted_launches"] == 0
    assert document["interrupted_invocations"] == [
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": True}
    ]
    assert not Path(ledger.read_text()).exists()
    assert _hashes(config.parent) == before


@pytest.mark.skipif(os.name != "posix", reason="real SIGINT delivery requires POSIX")
def test_real_posix_diagnose_sigint_returns_partial_accounting_and_cleans(tmp_path: Path) -> None:
    readiness = tmp_path / "ready"
    program = (
        "import sys,threading\nfrom pathlib import Path\n"
        f"Path({str(readiness)!r}).write_text(str(Path(sys.argv[1]).parent))\n"
        "threading.Event().wait(15)\n"
    )
    config = _case(tmp_path / "case", program, timeout=20.0)
    before = _hashes(config.parent)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "reproseed",
            "diagnose",
            "--config",
            str(config),
            "--allow-exec",
            "--format",
            "json",
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 8
        while not readiness.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.01)
        assert readiness.exists(), "synthetic oracle never reached launch handshake"
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=8)
        assert process.returncode == 130, stdout + stderr
        document = json.loads(stdout)
        assert document["interrupted"] is True
        assert document["actual_invocations"] == 1
        assert document["budget_charged_invocations"] == 1
        assert document["baseline_confirmed"] is False
        assert document["interrupted_invocations"][0]["executed"] is True
        assert not Path(readiness.read_text()).exists()
        assert _hashes(config.parent) == before
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=8)
