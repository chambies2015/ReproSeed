from __future__ import annotations

import _thread
import hashlib
import json
import os
import shutil
import signal
import sqlite3
import sys
import tempfile
import threading
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace, TracebackType

import pytest

from reproseed import oracle as oracle_module
from reproseed.config import Asset, OracleSpec
from reproseed.oracle import OracleInterrupted, Outcome, run_oracle


def _deadline_after_readiness(monkeypatch: pytest.MonkeyPatch) -> threading.Event:
    """Inject deadline expiry at a proven process boundary, with real cleanup time.

    A latched offset changes only the oracle's clock; all later cleanup reads
    advance at the real rate and share its normal allowance. Harness observations
    and total wall bounds keep the untouched clock. Real elapsed timeout coverage
    remains separate in test_timeout_is_bounded.
    """
    expired = threading.Event()
    monotonic = time.monotonic
    monkeypatch.setattr(
        oracle_module,
        "time",
        SimpleNamespace(
            monotonic=lambda: monotonic() + (9.0 if expired.is_set() else 0.0),
            sleep=time.sleep,
        ),
    )
    return expired


class _ObservedProcess:
    """Observe a synthetic process without confusing a reused PID with an exit."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.handle: int | None = None
        self.start_identity: str | None = None
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.kernel.OpenProcess.restype = wintypes.HANDLE
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.WaitForSingleObject.restype = wintypes.DWORD
            self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            self.kernel.TerminateProcess.restype = wintypes.BOOL
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle.restype = wintypes.BOOL
            # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE.
            self.handle = self.kernel.OpenProcess(0x100000 | 0x1000 | 0x0001, False, pid)
            if not self.handle:
                raise OSError(ctypes.get_last_error(), "could not observe synthetic process")
        elif sys.platform.startswith("linux"):
            stat = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
            self.start_identity = stat[19]

    def running(self) -> bool:
        if self.handle is not None:
            state = self.kernel.WaitForSingleObject(self.handle, 0)
            assert state in {0, 258}, f"unexpected process wait status: {state}"
            return state == 258
        # Linux orphaned descendants can remain zombies until adopted/reaped.
        # A zombie has terminated and released its cwd, files and pipe handles.
        stat = Path(f"/proc/{self.pid}/stat")
        try:
            if self.start_identity is not None:
                fields = stat.read_text().rsplit(") ", 1)[1].split()
                if fields[19] != self.start_identity or fields[0] == "Z":
                    return False
            os.kill(self.pid, 0)
        except (FileNotFoundError, ProcessLookupError):
            return False
        return True

    def terminate(self) -> None:
        if not self.running():
            return
        if self.handle is not None:
            assert self.kernel.TerminateProcess(self.handle, 99)
        else:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close(self) -> None:
        if self.handle is not None:
            assert self.kernel.CloseHandle(self.handle)
            self.handle = None


class _OwnedTree:
    """Readiness, process evidence and bounded teardown for only this test's tree.

    Child readiness follows opening the staged database. Parent readiness follows
    child readiness. The watcher opens process handles before releasing the parent
    or interrupting the test, so termination and directory removal are independent
    observations. The finite child watchdog also protects a failed harness startup.
    """

    def __init__(self, tmp_path: Path, *, pipes: bool = True) -> None:
        self.ready = tmp_path / "tree-ready.json"
        self.launched = tmp_path / "tree-launched.json"
        self.child_ready = tmp_path / "child-ready.json"
        self.release = tmp_path / "release-parent"
        self.processes: list[_ObservedProcess] = []
        self.metadata: dict[str, object] = {}
        self.errors: list[BaseException] = []
        self.stop = threading.Event()
        self.watcher: threading.Thread | None = None
        self.ready_seen = threading.Event()
        self.started = time.monotonic()
        child = (
            "import json, os, pathlib, time\n"
            "staged = open('db.sqlite3', 'rb')\n"
            f"ready = pathlib.Path({str(self.child_ready)!r})\n"
            "temporary = ready.with_suffix('.tmp')\n"
            "temporary.write_text(json.dumps({'pid': os.getpid(), 'cwd': os.getcwd()}))\n"
            "temporary.replace(ready)\n"
            "time.sleep(20)\n"
        )
        streams = "" if pipes else ", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL"
        self.prefix = (
            "import json, os, pathlib, subprocess, sys, time\n"
            f"child_ready = pathlib.Path({str(self.child_ready)!r})\n"
            f"ready = pathlib.Path({str(self.ready)!r})\n"
            f"launched = pathlib.Path({str(self.launched)!r})\n"
            f"release = pathlib.Path({str(self.release)!r})\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child!r}]{streams})\n"
            "metadata = {'parent': os.getpid(), 'child': child.pid, 'cwd': os.getcwd()}\n"
            "temporary = launched.with_suffix('.tmp')\n"
            "temporary.write_text(json.dumps(metadata))\n"
            "temporary.replace(launched)\n"
            "deadline = time.monotonic() + 8\n"
            "while not child_ready.exists() and time.monotonic() < deadline:\n"
            "    time.sleep(0.005)\n"
            "assert child_ready.exists(), 'child readiness deadline'\n"
            # Windows virtualenv launchers can give Popen and the running child
            # different PIDs; observe the interpreter that opened the file.
            "metadata['child_launcher'] = metadata['child']\n"
            "metadata['child'] = json.loads(child_ready.read_text())['pid']\n"
            "temporary = launched.with_suffix('.tmp')\n"
            "temporary.write_text(json.dumps(metadata))\n"
            "temporary.replace(launched)\n"
            "temporary = ready.with_suffix('.tmp')\n"
            "temporary.write_text(json.dumps(metadata))\n"
            "temporary.replace(ready)\n"
            "deadline = time.monotonic() + 8\n"
            "while not release.exists() and time.monotonic() < deadline:\n"
            "    time.sleep(0.005)\n"
            "assert release.exists(), 'parent release deadline'\n"
        )

    def __enter__(self) -> _OwnedTree:
        return self

    def watch(self, action: Callable[[], None]) -> None:
        def observe() -> None:
            try:
                deadline = time.monotonic() + 5
                while not self.stop.wait(0.005) and time.monotonic() < deadline:
                    if self.ready.exists():
                        self.metadata = json.loads(self.ready.read_text())
                        child_metadata = json.loads(self.child_ready.read_text())
                        assert child_metadata["pid"] == self.metadata["child"]
                        assert child_metadata["cwd"] == self.metadata["cwd"]
                        for name in ("parent", "child"):
                            self.processes.append(_ObservedProcess(int(self.metadata[name])))
                        assert all(process.running() for process in self.processes)
                        self.ready_seen.set()
                        action()
                        return
                if not self.stop.is_set():
                    raise AssertionError("process-tree readiness deadline")
            except BaseException as error:
                self.errors.append(error)

        self.watcher = threading.Thread(target=observe, daemon=True)
        self.watcher.start()

    def release_parent(self) -> None:
        self.release.touch()

    def observations(self) -> dict[str, object]:
        # Capture all evidence before any assertion can short-circuit teardown.
        directory = self.metadata.get("cwd")
        root = Path(str(directory)) if directory is not None else None
        evidence = {
            "ready": self.ready_seen.is_set(),
            "pids": [process.pid for process in self.processes],
            "staged_directory": directory,
            "elapsed_seconds": round(time.monotonic() - self.started, 6),
            "watcher_errors": [repr(error) for error in self.errors],
            "running": [process.running() for process in self.processes],
            "directory_exists": root.exists() if root is not None else None,
            "deadline_boundary": self.metadata.get("deadline_boundary"),
        }
        if sys.platform.startswith("linux"):
            immediate = self.ready.parent / "cleanup-immediate-observations.json"
            if not immediate.exists():
                immediate.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            # POSIX cleanup requests group SIGKILL. Delivery/exit can lag the
            # caller's return, and Linux can unlink a cwd/open file immediately.
            # Observe the same captured identities within one small allowance;
            # never kill anything here or substitute a fixed sentinel sleep.
            deadline = time.monotonic() + 0.2
            while any(process.running() for process in self.processes):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.stop.wait(min(0.005, remaining))
            evidence["running"] = [process.running() for process in self.processes]
            evidence["elapsed_seconds"] = round(time.monotonic() - self.started, 6)
            evidence["directory_exists"] = root.exists() if root is not None else None
        (self.ready.parent / "cleanup-observations.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        return evidence

    def assert_cleaned(self) -> None:
        evidence = self.observations()
        assert evidence["ready"], evidence
        assert not self.errors, evidence
        assert evidence["running"] == [False, False], evidence
        assert not evidence["directory_exists"], evidence

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop.set()
        if self.watcher is not None:
            self.watcher.join(timeout=1)
        try:
            # Product assertions/observations have already run. Recovery only
            # terminates observed test processes; it cannot make assertions pass.
            # Do not reopen a late PID from metadata: its original process may
            # have gone. Unobserved children retain their finite own watchdog.
            for process in reversed(self.processes):
                process.terminate()
            deadline = time.monotonic() + 2
            while any(process.running() for process in self.processes):
                if time.monotonic() >= deadline:
                    raise AssertionError("synthetic-process teardown deadline")
                time.sleep(0.005)
        finally:
            for process in self.processes:
                process.close()
            if self.launched.exists():
                metadata = json.loads(self.launched.read_text())
                root = Path(metadata["cwd"])
                assert root.parent == Path(tempfile.gettempdir())
                assert root.name.startswith("reproseed-oracle-")
                assert not root.is_symlink() and not root.is_junction()
                try:
                    shutil.rmtree(root)
                except FileNotFoundError:
                    pass
        if self.watcher is not None:
            assert not self.watcher.is_alive(), "synthetic readiness watcher teardown deadline"


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


def test_descendant_holding_output_pipes_cannot_extend_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expired = _deadline_after_readiness(monkeypatch)
    with _OwnedTree(tmp_path) as tree:

        def expire_after_parent_exit() -> None:
            tree.release_parent()
            deadline = time.monotonic() + 1
            while tree.processes[0].running():
                remaining = deadline - time.monotonic()
                assert remaining > 0, "ready parent exit deadline"
                tree.stop.wait(min(0.005, remaining))
            assert tree.processes[1].running()
            tree.metadata["deadline_boundary"] = "ready child retains pipes after parent exit"
            expired.set()

        tree.watch(expire_after_parent_exit)
        code = tree.prefix + "print('specific failure'); raise SystemExit(19)\n"
        started = time.monotonic()
        # The real startup guard bounds a broken handshake. Trigger the timeout
        # only after the intended parent-exited/child-ready condition is proven.
        result = run_oracle(_spec(code, timeout=8), _database(tmp_path), ())
        assert expired.is_set()
        assert result.outcome == Outcome.UNRESOLVED
        assert "open output pipes" in result.reason
        tree.assert_cleaned()
        assert time.monotonic() - started < 1.8


def test_timeout_cleans_up_live_parent_and_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expired = _deadline_after_readiness(monkeypatch)
    with _OwnedTree(tmp_path) as tree:

        def expire_with_live_tree() -> None:
            assert all(process.running() for process in tree.processes)
            tree.metadata["deadline_boundary"] = "ready parent and child remain live"
            expired.set()

        tree.watch(expire_with_live_tree)
        code = tree.prefix + "time.sleep(30)\n"
        started = time.monotonic()
        result = run_oracle(_spec(code, timeout=8), _database(tmp_path), ())
        assert expired.is_set()
        assert result.outcome == Outcome.UNRESOLVED
        assert "deadline" in result.reason
        tree.assert_cleaned()
        assert time.monotonic() - started < 4


@pytest.mark.parametrize("pipes", [True, False], ids=["inherited-pipes", "closed-pipes"])
def test_cancellation_cleans_up_process_tree_and_propagates(tmp_path: Path, pipes: bool) -> None:
    with _OwnedTree(tmp_path, pipes=pipes) as tree:
        tree.watch(_thread.interrupt_main)
        code = tree.prefix + "time.sleep(30)\n"
        started = time.monotonic()
        with pytest.raises(OracleInterrupted) as interrupted:
            run_oracle(_spec(code, timeout=8), _database(tmp_path), ())
        assert tree.ready.exists()
        assert interrupted.value.executed is True
        tree.assert_cleaned()
        assert time.monotonic() - started < 4


def test_normal_completion_cleans_descendant_with_closed_output_pipes(tmp_path: Path) -> None:
    with _OwnedTree(tmp_path, pipes=False) as tree:
        tree.watch(tree.release_parent)
        code = tree.prefix + "print('specific failure'); raise SystemExit(19)\n"
        started = time.monotonic()
        result = run_oracle(_spec(code), _database(tmp_path), ())
        assert result.outcome == Outcome.TARGET_FAILURE
        tree.assert_cleaned()
        assert time.monotonic() - started < 1.8


def test_output_limit_cleans_up_live_parent_and_child(tmp_path: Path) -> None:
    with _OwnedTree(tmp_path) as tree:
        tree.watch(tree.release_parent)
        code = tree.prefix + "while True:\n    os.write(1, b'x' * 8192)\n"
        started = time.monotonic()
        result = run_oracle(_spec(code, limit=4096), _database(tmp_path), ())
        assert result.outcome == Outcome.UNRESOLVED
        assert "output limit" in result.reason
        tree.assert_cleaned()
        assert time.monotonic() - started < 4


@pytest.mark.skipif(sys.platform != "win32", reason="Windows owned Job integration")
def test_windows_successful_job_assignment_contains_ready_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ctypes
    from ctypes import wintypes

    assigned = []
    original = oracle_module._windows_job

    def record_job(pid: int, *args: object) -> object:
        job = original(pid, *args)
        assigned.append(job)
        return job

    monkeypatch.setattr(oracle_module, "_windows_job", record_job)
    with _OwnedTree(tmp_path) as tree:

        def check_membership_and_interrupt() -> None:
            try:
                assert len(assigned) == 1 and assigned[0] is not None
                handle = assigned[0].handle
                assert handle is not None
                kernel = tree.processes[0].kernel
                kernel.IsProcessInJob.argtypes = [
                    wintypes.HANDLE,
                    wintypes.HANDLE,
                    ctypes.POINTER(wintypes.BOOL),
                ]
                kernel.IsProcessInJob.restype = wintypes.BOOL
                for process in tree.processes:
                    member = wintypes.BOOL()
                    assert kernel.IsProcessInJob(process.handle, handle, ctypes.byref(member))
                    assert member.value, "ready process is outside this invocation's Job"
            finally:
                _thread.interrupt_main()

        tree.watch(check_membership_and_interrupt)
        with pytest.raises(OracleInterrupted) as interrupted:
            run_oracle(_spec(tree.prefix + "time.sleep(30)\n", timeout=8), _database(tmp_path), ())
        assert interrupted.value.executed is True
        tree.assert_cleaned()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows bounded taskkill fallback")
def test_windows_unavailable_job_attempts_bounded_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oracle_module, "_windows_job", lambda *args: None)
    original_run = oracle_module.subprocess.run
    original_kill = oracle_module._kill_tree
    attempts: list[dict[str, object]] = []
    cleanup_pids: list[int] = []

    def record_owned_cleanup(process: object, *args: object) -> None:
        # A Windows virtualenv redirector can have a different PID from the
        # interpreter that writes readiness. Record the actual owned Popen PID.
        cleanup_pids.append(process.pid)
        original_kill(process, *args)
        assert process.poll() is not None

    def record_fallback(command: list[str], **kwargs: object) -> object:
        try:
            result = original_run(command, **kwargs)
        except (OSError, oracle_module.subprocess.TimeoutExpired) as error:
            attempts.append({"command": command, "error": type(error).__name__})
            raise
        attempts.append({"command": command, "returncode": result.returncode})
        return result

    monkeypatch.setattr(oracle_module.subprocess, "run", record_fallback)
    monkeypatch.setattr(oracle_module, "_kill_tree", record_owned_cleanup)
    with _OwnedTree(tmp_path) as tree:
        tree.watch(_thread.interrupt_main)
        started = time.monotonic()
        with warnings.catch_warnings(record=True) as warnings_seen:
            warnings.simplefilter("always")
            with pytest.raises(OracleInterrupted) as interrupted:
                run_oracle(
                    _spec(tree.prefix + "time.sleep(30)\n", timeout=8), _database(tmp_path), ()
                )
        assert interrupted.value.executed is True
        evidence = tree.observations()
        (tmp_path / "fallback-attempts.json").write_text(json.dumps(attempts, indent=2))
        assert len(attempts) == 1
        assert attempts[0]["command"] == [
            "taskkill",
            "/PID",
            str(cleanup_pids[0]),
            "/T",
            "/F",
        ]
        assert evidence["ready"] and not tree.errors, evidence
        if attempts[0].get("returncode") == 0:
            tree.assert_cleaned()
        elif evidence["directory_exists"]:
            # Host policy can deny taskkill. Preserve the observed limitation,
            # cancellation, and warning instead of claiming tree cleanup worked.
            assert any("oracle cleanup incomplete" in str(item.message) for item in warnings_seen)
        assert time.monotonic() - started < 4


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
