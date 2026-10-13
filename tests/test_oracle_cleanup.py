"""Deterministic cleanup ordering, deadline and owned Windows API boundaries."""

from __future__ import annotations

import errno
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import reproseed.oracle as oracle


class _Clock:
    now = 100.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert 0 < seconds <= 0.01
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    value = _Clock()
    monkeypatch.setattr(oracle.time, "monotonic", value.monotonic)
    monkeypatch.setattr(oracle.time, "sleep", value.sleep)
    return value


def _locked() -> OSError:
    error = PermissionError(errno.EACCES, "synthetic lock")
    error.winerror = 32
    return error


def test_transient_deletion_failure_retries_only_exact_owned_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    calls: list[Path] = []
    original = oracle.shutil.rmtree

    def remove(path: Path, **kwargs: object) -> None:
        calls.append(path)
        if len(calls) == 1:
            raise _locked()
        original(path, **kwargs)

    monkeypatch.setattr(oracle.shutil, "rmtree", remove)
    cleanup = oracle._Cleanup()
    oracle._remove_owned_directory(root, cleanup)
    assert calls == [root, root]
    assert not root.exists()
    assert clock.now == pytest.approx(100.01)
    assert cleanup.deadline == 101.5


def test_permanent_lock_exhausts_remaining_allowance_without_claiming_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    calls: list[Path] = []

    def remove(path: Path, **kwargs: object) -> None:
        calls.append(path)
        raise _locked()

    monkeypatch.setattr(oracle.shutil, "rmtree", remove)
    cleanup = oracle._Cleanup()
    cleanup.begin()
    clock.now += 1.48  # tree/reader cleanup already consumed this allowance
    with pytest.warns(RuntimeWarning, match="removal.*code 32"):
        oracle._remove_owned_directory(root, cleanup)
    assert 2 <= len(calls) <= 4
    assert set(calls) == {root}
    assert root.exists()
    assert clock.now == pytest.approx(101.5)
    assert cleanup.deadline == 101.5


def test_nontransient_deletion_error_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    calls = 0

    def remove(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise OSError(errno.EIO, "synthetic disk error")

    monkeypatch.setattr(oracle.shutil, "rmtree", remove)
    with pytest.warns(RuntimeWarning, match="removal"):
        oracle._remove_owned_directory(root, oracle._Cleanup())
    assert calls == 1
    assert root.exists()
    assert clock.now == 100


def test_deletion_does_not_follow_replaced_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(Path, "is_junction", lambda self: True)
    monkeypatch.setattr(oracle.shutil, "rmtree", lambda *args, **kwargs: calls.append(args))
    with pytest.warns(RuntimeWarning, match="replaced by a link"):
        oracle._remove_owned_directory(tmp_path, oracle._Cleanup())
    assert not calls


def test_successful_directory_cleanup_has_no_sleep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    monkeypatch.setattr(oracle.time, "sleep", lambda seconds: pytest.fail("unconditional sleep"))
    oracle._remove_owned_directory(root, oracle._Cleanup())
    assert not root.exists()


@pytest.mark.parametrize("further", [False, True])
def test_deletion_obstruction_preserves_cancellation_and_stops_further_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: _Clock, further: bool
) -> None:
    from reproseed.config import OracleSpec

    root = tmp_path / "owned"
    root.mkdir()
    monkeypatch.setattr(oracle.tempfile, "mkdtemp", lambda **kwargs: str(root))

    def interrupt_copy(*args: object) -> None:
        raise KeyboardInterrupt

    calls = 0

    def remove(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if further:
            raise KeyboardInterrupt
        raise _locked()

    monkeypatch.setattr(oracle.shutil, "copyfile", interrupt_copy)
    monkeypatch.setattr(oracle.shutil, "rmtree", remove)
    spec = OracleSpec(("unused",), 19, "marker", "stdout", 1, 4096)
    if further:
        with pytest.raises(oracle.OracleInterrupted) as interrupted:
            oracle.run_oracle(spec, tmp_path / "source", ())
        assert calls == 1
        assert clock.now == 100
    else:
        with (
            pytest.warns(RuntimeWarning, match="removal"),
            pytest.raises(oracle.OracleInterrupted) as interrupted,
        ):
            oracle.run_oracle(spec, tmp_path / "source", ())
        assert clock.now == pytest.approx(101.5)
    assert interrupted.value.executed is False
    assert interrupted.value.abort is further
    assert root.exists()


def test_readonly_callback_never_retries_unknown_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def remove(path: Path, *, onexc: object) -> None:
        def unsupported(*args: object) -> None:
            pytest.fail("must not retry scandir/open as deletion")

        onexc(unsupported, str(path), _locked())

    monkeypatch.setattr(oracle.shutil, "rmtree", remove)
    with pytest.warns(RuntimeWarning, match="removal"):
        oracle._remove_owned_directory(tmp_path, oracle._Cleanup(deadline=0))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job API branches")
@pytest.mark.parametrize("failure", ["create", "configure", "open", "assign", "interrupt"])
def test_job_assignment_failure_closes_only_acquired_handles(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    closed: list[int] = []

    def assign(*args: object) -> bool:
        if failure == "interrupt":
            raise KeyboardInterrupt
        return failure != "assign"

    kernel = SimpleNamespace(
        CreateJobObjectW=lambda *args: 0 if failure == "create" else 99,
        SetInformationJobObject=lambda *args: failure != "configure",
        OpenProcess=lambda *args: 0 if failure == "open" else 101,
        AssignProcessToJobObject=assign,
        CloseHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(oracle, "_kernel", kernel)
    owner = oracle._Cleanup()
    if failure == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            oracle._windows_job(17, owner)
    else:
        assert oracle._windows_job(17, owner) is None
    assert owner.job is None
    assert closed == (
        [] if failure == "create" else [99] if failure in {"configure", "open"} else [101, 99]
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job API branches")
@pytest.mark.parametrize("partial", [False, True])
def test_job_observes_members_after_termination_request_with_shared_deadline(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock, partial: bool
) -> None:
    import ctypes

    events: list[object] = []
    queries = 0

    def query(handle: int, kind: int, buffer: object, size: int, result: object) -> bool:
        nonlocal queries
        queries += 1
        events.append("query")
        counts = (ctypes.c_ulong * 2).from_buffer(buffer)
        counts[:] = [2, 1 if partial and queries == 1 else 2]
        (ctypes.c_size_t * counts[1]).from_buffer(buffer, 8)[:] = [10, 11][: counts[1]]
        return True

    def membership(handle: int, job: int, member: object) -> bool:
        assert job == 99
        member._obj.value = True
        return True

    def wait(handle: int, milliseconds: int) -> int:
        events.append(("wait", handle, milliseconds))
        clock.now += 0.4
        return 0

    kernel = SimpleNamespace(
        TerminateJobObject=lambda *args: events.append("terminate") or True,
        QueryInformationJobObject=query,
        OpenProcess=lambda rights, inherit, pid: pid + 1000,
        IsProcessInJob=membership,
        WaitForSingleObject=wait,
        CloseHandle=lambda handle: events.append(("close", handle)),
    )
    monkeypatch.setattr(oracle, "_kernel", kernel)
    job = oracle._WindowsJob(99)
    job.stop(101.5)
    job.close()
    job.close()
    assert events[0] == "query"
    assert events[1 + partial] == "terminate"
    assert queries == 2 + partial
    waits = [event for event in events if isinstance(event, tuple) and event[0] == "wait"]
    assert waits[0][1:] == (1010, 1500)
    assert waits[1][1] == 1011
    assert 1099 <= waits[1][2] <= 1100
    assert [event for event in events if isinstance(event, tuple) and event[0] == "close"] == [
        ("close", 1010),
        ("close", 1011),
        ("close", 99),
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows fallback branches")
@pytest.mark.parametrize("failure", [None, OSError, subprocess.TimeoutExpired])
def test_unavailable_job_fallback_spends_one_shared_budget(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock, failure: type[Exception] | None
) -> None:
    events: list[object] = []

    def taskkill(argv: list[str], **kwargs: object) -> object:
        assert argv == ["taskkill", "/PID", "17", "/T", "/F"]
        events.append(("taskkill", kwargs["timeout"]))
        clock.now += 1.25
        if failure is OSError:
            raise OSError("unavailable")
        if failure is subprocess.TimeoutExpired:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return SimpleNamespace(returncode=0)

    def wait(*, timeout: float) -> None:
        events.append(("parent_wait", timeout))

    process = SimpleNamespace(
        pid=17, _handle=101, poll=lambda: None, kill=lambda: events.append("kill"), wait=wait
    )
    monkeypatch.setattr(oracle.subprocess, "run", taskkill)
    monkeypatch.setattr(
        oracle, "_kernel", SimpleNamespace(WaitForSingleObject=lambda handle, timeout: 0)
    )
    cleanup = oracle._Cleanup()
    oracle._kill_tree(process, None, cleanup)
    assert events == [("taskkill", 1.5), "kill", ("parent_wait", 0.25)]
    assert cleanup.deadline == 101.5


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job API failure branches")
@pytest.mark.parametrize("failure", ["terminate", "query", "wait", "membership", "departed"])
def test_job_failure_branches_release_handles_and_report_actual_error(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import ctypes

    closed: list[int] = []
    waits: list[int] = []

    def query(handle: int, kind: int, buffer: object, size: int, result: object) -> bool:
        if failure == "query":
            return False
        (ctypes.c_ulong * 2).from_buffer(buffer)[:] = [1, 1]
        (ctypes.c_size_t * 1).from_buffer(buffer, 8)[0] = 10
        return True

    def membership(handle: int, job: int, member: object) -> bool:
        member._obj.value = failure != "departed"
        return failure != "membership"

    kernel = SimpleNamespace(
        TerminateJobObject=lambda *args: failure != "terminate",
        QueryInformationJobObject=query,
        OpenProcess=lambda *args: 1010,
        IsProcessInJob=membership,
        WaitForSingleObject=lambda handle, timeout: waits.append(handle) or 0xFFFFFFFF,
        CloseHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(oracle, "_kernel", kernel)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)
    job = oracle._WindowsJob(99)
    if failure == "departed":
        job.stop(oracle.time.monotonic() + 1.5)
        assert not waits  # a reused PID outside the owned Job is not observed
    else:
        with pytest.warns(RuntimeWarning, match="code 5"):
            job.stop(oracle.time.monotonic() + 1.5)
    job.close()
    assert closed == ([99] if failure == "query" else [1010, 99])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job interruption ownership")
def test_job_handle_is_closed_once_when_member_wait_is_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []

    def interrupt(deadline: float) -> None:
        raise KeyboardInterrupt

    job = SimpleNamespace(stop=interrupt, close=lambda: closed.append(99))
    with pytest.raises(KeyboardInterrupt):
        oracle._kill_tree(SimpleNamespace(pid=17), job, oracle._Cleanup())
    assert closed == [99]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job list exit boundary")
def test_disappeared_member_is_still_waited_and_new_member_is_captured(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    import ctypes

    requested = False
    opened: list[int] = []
    waited: list[int] = []
    closed: list[int] = []

    def query(handle: int, kind: int, buffer: object, size: int, result: object) -> bool:
        # Member 10 disappears at termination without signaling yet, while 11
        # joined during the initial snapshot. Both need process-handle waits.
        (ctypes.c_ulong * 2).from_buffer(buffer)[:] = [1, 1]
        (ctypes.c_size_t * 1).from_buffer(buffer, 8)[0] = 11 if requested else 10
        return True

    def terminate(*args: object) -> bool:
        nonlocal requested
        assert opened == [10]
        requested = True
        return True

    def open_process(rights: int, inherit: bool, pid: int) -> int:
        opened.append(pid)
        return pid + 1000

    def membership(handle: int, job: int, member: object) -> bool:
        member._obj.value = True
        return True

    kernel = SimpleNamespace(
        TerminateJobObject=terminate,
        QueryInformationJobObject=query,
        OpenProcess=open_process,
        IsProcessInJob=membership,
        WaitForSingleObject=lambda handle, timeout: waited.append(handle) or 0,
        CloseHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(oracle, "_kernel", kernel)
    job = oracle._WindowsJob(99)
    job.stop(101.5)
    job.close()
    assert opened == [10, 11]
    assert waited == [1010, 1011]
    assert closed == [1010, 1011, 99]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job ownership transfer")
def test_assigned_job_is_owned_before_return_transfer(monkeypatch: pytest.MonkeyPatch) -> None:
    from test_invocation_accounting import interrupt_before_statement

    closed: list[int] = []
    kernel = SimpleNamespace(
        CreateJobObjectW=lambda *args: 99,
        SetInformationJobObject=lambda *args: True,
        OpenProcess=lambda *args: 101,
        AssignProcessToJobObject=lambda *args: True,
        CloseHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(oracle, "_kernel", kernel)
    owner = oracle._Cleanup()
    with interrupt_before_statement(oracle._windows_job, "return job"):
        with pytest.raises(KeyboardInterrupt):
            oracle._windows_job(17, owner)
    assert owner.job is None
    assert closed == [101, 99]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job caller exception context")
def test_callers_handled_exception_does_not_release_successfully_assigned_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    kernel = SimpleNamespace(
        CreateJobObjectW=lambda *args: 99,
        SetInformationJobObject=lambda *args: True,
        OpenProcess=lambda *args: 101,
        AssignProcessToJobObject=lambda *args: True,
        CloseHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(oracle, "_kernel", kernel)
    owner = oracle._Cleanup()
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        job = oracle._windows_job(17, owner)
    assert job is owner.job and job.handle == 99
    assert closed == [101]
    job.close()
    assert closed == [101, 99]


def test_callers_handled_cancellation_is_not_a_further_cleanup_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reproseed.config import OracleSpec

    root = tmp_path / "owned"
    root.mkdir()
    monkeypatch.setattr(oracle.tempfile, "mkdtemp", lambda **kwargs: str(root))

    source = tmp_path / "source"
    source.write_bytes(b"synthetic")

    def execute(
        spec: object, root: object, db: object, execution: object, cleanup: object
    ) -> object:
        execution.executed = True
        return oracle.OracleResult(oracle.Outcome.PASS, "zero exit without target marker", 0, 0, 0)

    def interrupt_removal(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(oracle, "_execute", execute)
    monkeypatch.setattr(oracle.shutil, "rmtree", interrupt_removal)
    spec = OracleSpec(("unused",), 19, "marker", "stdout", 1, 4096)
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        with pytest.raises(oracle.OracleInterrupted) as interrupted:
            oracle.run_oracle(spec, source, ())
    assert not interrupted.value.abort
    assert interrupted.value.executed is True
    assert root.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows readonly file attribute")
def test_readonly_leaf_disappearance_does_not_abandon_remaining_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    leaf = root / "readonly"
    leaf.write_bytes(b"synthetic")
    leaf.chmod(0o444)
    (root / "other").write_bytes(b"retained until cleanup")
    unlink = oracle.os.unlink
    rmtree = oracle.shutil.rmtree

    def disappear(path: object, **kwargs: object) -> None:
        unlink(path, **kwargs)
        if Path(path) == leaf:
            raise FileNotFoundError("synthetic race after readonly reset")

    def remove(path: Path, *, onexc: object) -> None:
        onexc(oracle.os.unlink, str(leaf), PermissionError("synthetic readonly"))
        rmtree(path)

    monkeypatch.setattr(oracle.os, "unlink", disappear)
    monkeypatch.setattr(oracle.shutil, "rmtree", remove)
    oracle._remove_owned_directory(root, oracle._Cleanup())
    assert not root.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job PID acquisition boundary")
def test_failed_handle_acquisition_does_not_suppress_second_snapshot(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    import ctypes

    attempts: list[int] = []
    waited: list[int] = []
    closed: list[int] = []

    def open_process(rights: int, inherit: bool, pid: int) -> int:
        attempts.append(pid)
        return 0 if len(attempts) == 1 else 1010

    def membership(handle: int, job: int, member: object) -> bool:
        member._obj.value = True
        return True

    kernel = SimpleNamespace(
        TerminateJobObject=lambda *args: True,
        OpenProcess=open_process,
        IsProcessInJob=membership,
        WaitForSingleObject=lambda handle, timeout: waited.append(handle) or 0,
        CloseHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(oracle, "_kernel", kernel)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 87)
    job = oracle._WindowsJob(99)
    monkeypatch.setattr(job, "_pids", lambda deadline: (10,))
    job.stop(101.5)
    job.close()
    assert attempts == [10, 10]
    assert waited == [1010]
    assert closed == [1010, 99]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows readonly file attribute")
def test_readonly_staged_file_is_removed(tmp_path: Path) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    asset = root / "asset"
    asset.write_bytes(b"synthetic")
    asset.chmod(0o444)
    oracle._remove_owned_directory(root, oracle._Cleanup())
    assert not root.exists()
