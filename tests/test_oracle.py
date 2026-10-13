from __future__ import annotations

import _thread
import hashlib
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

from reproseed.config import Asset, OracleSpec
from reproseed.oracle import OracleInterrupted, Outcome, run_oracle


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "original.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO records VALUES (7)")
    return database


def _spec(
    code: str,
    *,
    stream: str = "stdout",
    timeout: float = 3.0,
    limit: int = 65536,
) -> OracleSpec:
    return OracleSpec(
        argv=("{python}", "-c", code),
        expected_exit=19,
        marker="specific failure",
        stream="stderr" if stream == "stderr" else "stdout",
        timeout_seconds=timeout,
        output_limit_bytes=limit,
    )


@pytest.mark.parametrize(
    ("code", "outcome"),
    [
        ("print('specific failure'); raise SystemExit(19)", Outcome.TARGET_FAILURE),
        ("print('healthy')", Outcome.PASS),
        ("print('specific failure')", Outcome.UNRESOLVED),
        ("print('specific failure'); raise SystemExit(20)", Outcome.UNRESOLVED),
        ("raise SystemExit(19)", Outcome.UNRESOLVED),
        ("print('other crash'); raise SystemExit(7)", Outcome.UNRESOLVED),
        ("print('prefix specific failure'); raise SystemExit(19)", Outcome.UNRESOLVED),
        ("print('specific failure suffix'); raise SystemExit(19)", Outcome.UNRESOLVED),
        ("print(' specific failure'); raise SystemExit(19)", Outcome.UNRESOLVED),
        ("print('specific failure '); raise SystemExit(19)", Outcome.UNRESOLVED),
        (
            "import sys; sys.stdout.write('specific failure'); raise SystemExit(19)",
            Outcome.TARGET_FAILURE,
        ),
        (
            "import os; os.write(1, b'specific failure\\r\\n'); raise SystemExit(19)",
            Outcome.TARGET_FAILURE,
        ),
    ],
)
def test_outcome_requires_exact_contract(tmp_path: Path, code: str, outcome: Outcome) -> None:
    result = run_oracle(_spec(code), _database(tmp_path), ())
    assert result.outcome == outcome
    assert result.executed
    assert result.duration_seconds >= 0
    assert len(result.reason) < 100
    assert "healthy" not in result.as_dict().values()
    assert set(result.as_dict()) == {
        "outcome",
        "reason",
        "exit_code",
        "output_bytes",
        "duration_seconds",
        "executed",
    }


def test_marker_is_only_recognized_on_configured_stream(tmp_path: Path) -> None:
    database = _database(tmp_path)
    code = "import sys; print('specific failure', file=sys.stderr); raise SystemExit(19)"
    assert run_oracle(_spec(code), database, ()).outcome == Outcome.UNRESOLVED
    assert run_oracle(_spec(code, stream="stderr"), database, ()).outcome == Outcome.TARGET_FAILURE
    code = "import sys; print('specific failure', file=sys.stderr)"
    assert run_oracle(_spec(code), database, ()).outcome == Outcome.PASS


def test_partial_reads_and_overlong_lines_do_not_create_a_marker(tmp_path: Path) -> None:
    code = (
        "import os, time; "
        "os.write(1, b'x' * 9000 + b'specific failure\\n'); "
        "os.write(1, b'specific '); time.sleep(0.05); "
        "os.write(1, b'failure\\n'); raise SystemExit(19)"
    )
    result = run_oracle(_spec(code), _database(tmp_path), ())
    assert result.outcome == Outcome.TARGET_FAILURE
    assert result.output_bytes == 9034


def test_each_invocation_stages_database_and_nested_assets(tmp_path: Path) -> None:
    database = _database(tmp_path)
    script = tmp_path / "oracle.py"
    script.write_text(
        "import pathlib, sqlite3, sys\n"
        "db = pathlib.Path(sys.argv[1])\n"
        "assert db.name == 'db.sqlite3'\n"
        "assert pathlib.Path('data/input.txt').read_text() == 'synthetic'\n"
        "with sqlite3.connect(db) as connection:\n"
        "    assert connection.execute('SELECT id FROM records').fetchall() == [(7,)]\n"
        "    connection.execute('DELETE FROM records')\n"
        "pathlib.Path(__file__).write_text('changed')\n"
        "pathlib.Path('data/input.txt').write_text('changed')\n"
        "print('specific failure')\n"
        "raise SystemExit(19)\n",
        encoding="utf-8",
    )
    asset = tmp_path / "input.txt"
    asset.write_text("synthetic", encoding="utf-8")
    originals = {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (database, script, asset)
    }
    spec = OracleSpec(
        argv=("{python}", "scripts/check.py", "{db}"),
        expected_exit=19,
        marker="specific failure",
        stream="stdout",
        timeout_seconds=3,
        output_limit_bytes=65536,
    )
    assets = (Asset("scripts/check.py", script), Asset("data/input.txt", asset))
    for _ in range(2):
        assert run_oracle(spec, database, assets).outcome == Outcome.TARGET_FAILURE
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals} == originals


def test_timeout_is_bounded(tmp_path: Path) -> None:
    started = time.monotonic()
    result = run_oracle(_spec("import time; time.sleep(30)", timeout=0.15), _database(tmp_path), ())
    assert result.outcome == Outcome.UNRESOLVED
    assert "deadline" in result.reason
    assert time.monotonic() - started < 4


def test_output_limit_combines_both_streams_and_is_bounded(tmp_path: Path) -> None:
    code = (
        "import os; "
        "os.write(1, b'x' * 800); os.write(2, b'y' * 800); "
        "print('specific failure'); raise SystemExit(19)"
    )
    result = run_oracle(_spec(code, limit=1000), _database(tmp_path), ())
    assert result.outcome == Outcome.UNRESOLVED
    assert "output limit" in result.reason
    assert result.output_bytes > 1000
    started = time.monotonic()
    code = "import os\nwhile True:\n    os.write(1, b'x' * 8192)\n"
    result = run_oracle(_spec(code, limit=4096), tmp_path / "original.sqlite3", ())
    assert result.outcome == Outcome.UNRESOLVED
    assert "output limit" in result.reason
    assert time.monotonic() - started < 4


def test_output_at_exact_limit_is_permitted(tmp_path: Path) -> None:
    code = "import os; os.write(1, b'specific failure\\n'); raise SystemExit(19)"
    result = run_oracle(_spec(code, limit=17), _database(tmp_path), ())
    assert result.outcome == Outcome.TARGET_FAILURE
    assert result.output_bytes == 17


def test_launch_and_staging_failures_are_unresolved_and_do_not_count(tmp_path: Path) -> None:
    spec = OracleSpec(
        argv=(str(tmp_path / "does-not-exist"),),
        expected_exit=19,
        marker="specific failure",
        stream="stdout",
        timeout_seconds=1,
        output_limit_bytes=1000,
    )
    result = run_oracle(spec, _database(tmp_path), ())
    assert result.outcome == Outcome.UNRESOLVED
    assert result.reason == "launch_error"
    assert result.exit_code is None
    assert result.output_bytes == 0
    assert not result.executed
    missing = run_oracle(spec, tmp_path / "missing.sqlite3", ())
    assert missing.outcome == Outcome.UNRESOLVED
    assert missing.reason == "staging_error"
    assert not missing.executed


def test_missing_dependency_in_launched_script_is_unresolved(tmp_path: Path) -> None:
    result = run_oracle(
        _spec("import reproseed_synthetic_dependency_that_does_not_exist"),
        _database(tmp_path),
        (),
    )
    assert result.outcome == Outcome.UNRESOLVED
    assert result.executed
    assert result.exit_code != 19
    assert "Traceback" not in result.reason


def test_descendant_holding_output_pipes_cannot_extend_deadline(tmp_path: Path) -> None:
    # The child has its own finite exit as a fallback on Windows, where
    # taskkill cannot reliably find descendants after the parent has exited.
    code = (
        "import subprocess, sys; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)']); "
        "print('specific failure'); raise SystemExit(19)"
    )
    started = time.monotonic()
    result = run_oracle(_spec(code, timeout=0.2), _database(tmp_path), ())
    assert result.outcome == Outcome.UNRESOLVED
    assert "open output pipes" in result.reason
    assert time.monotonic() - started < 1.8


def test_timeout_cleans_up_live_parent_and_child(tmp_path: Path) -> None:
    probe = tmp_path / "child-survived.txt"
    child_code = (
        f"import pathlib, time; time.sleep(2); pathlib.Path({str(probe)!r}).write_text('survived')"
    )
    code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); time.sleep(30)"
    )
    result = run_oracle(_spec(code, timeout=0.4), _database(tmp_path), ())
    assert result.outcome == Outcome.UNRESOLVED
    time.sleep(2.1)
    assert not probe.exists()


def test_cancellation_cleans_up_process_tree_and_propagates(tmp_path: Path) -> None:
    ready = tmp_path / "ready.txt"
    probe = tmp_path / "child-survived.txt"
    child_code = (
        f"import pathlib, time; time.sleep(2); pathlib.Path({str(probe)!r}).write_text('survived')"
    )
    code = (
        "import os, pathlib, subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        f"pathlib.Path({str(ready)!r}).write_text(os.getcwd()); time.sleep(30)"
    )
    cancel = threading.Event()

    def interrupt_when_ready() -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not cancel.wait(0.01):
            if ready.exists():
                _thread.interrupt_main()
                return

    interrupter = threading.Thread(target=interrupt_when_ready, daemon=True)
    interrupter.start()
    try:
        with pytest.raises(OracleInterrupted) as interrupted:
            run_oracle(_spec(code, timeout=8), _database(tmp_path), ())
    finally:
        cancel.set()
        interrupter.join(timeout=1)
    assert ready.exists()
    assert interrupted.value.executed is True
    assert not Path(ready.read_text()).exists()
    time.sleep(2.1)
    assert not probe.exists()


def test_cancellation_before_launch_reports_no_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)

    def interrupt_copy(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("reproseed.oracle.shutil.copyfile", interrupt_copy)
    with pytest.raises(OracleInterrupted) as interrupted:
        run_oracle(_spec("raise SystemExit(19)"), database, ())
    assert interrupted.value.executed is False


def test_interruption_inside_process_constructor_reports_unknown_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)

    def interrupt_constructor(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("reproseed.oracle.subprocess.Popen", interrupt_constructor)
    with pytest.raises(OracleInterrupted) as interrupted:
        run_oracle(_spec("raise SystemExit(19)"), database, ())
    assert interrupted.value.executed is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal return codes")
def test_signal_termination_is_unresolved(tmp_path: Path) -> None:
    code = (
        "import os, signal; print('specific failure', flush=True); "
        "os.kill(os.getpid(), signal.SIGTERM)"
    )
    result = run_oracle(_spec(code), _database(tmp_path), ())
    assert result.outcome == Outcome.UNRESOLVED
    assert result.exit_code is not None and result.exit_code < 0
    assert result.reason == "process terminated by signal"


def test_stdin_is_closed(tmp_path: Path) -> None:
    code = (
        "import sys; assert sys.stdin.read() == ''; print('specific failure'); raise SystemExit(19)"
    )
    assert run_oracle(_spec(code), _database(tmp_path), ()).outcome == Outcome.TARGET_FAILURE


def test_invocations_do_not_require_the_repository_working_directory(tmp_path: Path) -> None:
    spec = _spec("import os, sys; assert os.getcwd() != sys.argv[1]")
    portable = OracleSpec(
        argv=(*spec.argv, str(Path.cwd())),
        expected_exit=spec.expected_exit,
        marker=spec.marker,
        stream=spec.stream,
        timeout_seconds=spec.timeout_seconds,
        output_limit_bytes=spec.output_limit_bytes,
    )
    assert run_oracle(portable, _database(tmp_path), ()).outcome == Outcome.PASS
    assert portable.argv[0] != sys.executable
