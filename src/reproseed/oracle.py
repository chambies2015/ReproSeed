"""Run the user's explicit failure contract against disposable staged files.

The temporary directory protects fixture state; it is not an OS sandbox. Pipe
readers retain only enough bytes to compare one exact marker line, and the
deadline covers both the process and descendants that keep its pipes open.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from reproseed.config import Asset, OracleSpec

if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel.SetInformationJobObject.restype = wintypes.BOOL
    _kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel.OpenProcess.restype = wintypes.HANDLE
    _kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel.CloseHandle.restype = wintypes.BOOL
    _kernel.PeekNamedPipe.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    _kernel.PeekNamedPipe.restype = wintypes.BOOL

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64),
            ("job_time", ctypes.c_int64),
            ("flags", wintypes.DWORD),
            ("minimum_working_set", ctypes.c_size_t),
            ("maximum_working_set", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority_class", wintypes.DWORD),
            ("scheduling_class", wintypes.DWORD),
        ]

    class _IOCounters(ctypes.Structure):
        _fields_ = [
            ("read_operations", ctypes.c_uint64),
            ("write_operations", ctypes.c_uint64),
            ("other_operations", ctypes.c_uint64),
            ("read_bytes", ctypes.c_uint64),
            ("write_bytes", ctypes.c_uint64),
            ("other_bytes", ctypes.c_uint64),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", _BasicLimits),
            ("io", _IOCounters),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    def _windows_job(pid: int) -> Callable[[], None] | None:
        """Try to keep the process tree in a kill-on-close Windows Job."""
        handle = _kernel.CreateJobObjectW(None, None)
        if not handle:
            return None
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configured = _kernel.SetInformationJobObject(
            handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        )
        process_handle = _kernel.OpenProcess(0x0100 | 0x0001, False, pid)
        assigned = False
        if process_handle:
            try:
                assigned = bool(
                    configured and _kernel.AssignProcessToJobObject(handle, process_handle)
                )
            finally:
                _kernel.CloseHandle(process_handle)
        if not assigned:
            _kernel.CloseHandle(handle)
            return None

        def close() -> None:
            _kernel.CloseHandle(handle)

        return close


def _read_pipe(pipe: BinaryIO) -> bytes | None:
    if sys.platform == "win32":
        available = wintypes.DWORD()
        handle = msvcrt.get_osfhandle(pipe.fileno())
        if not _kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
            error = ctypes.get_last_error()
            if error in {109, 233}:  # ERROR_BROKEN_PIPE, ERROR_PIPE_NOT_CONNECTED
                return b""
            raise OSError(error, "pipe read failed")
        if not available.value:
            return None
        return os.read(pipe.fileno(), min(8192, available.value))
    return os.read(pipe.fileno(), 8192)


class Outcome(StrEnum):
    TARGET_FAILURE = "TARGET_FAILURE"
    PASS = "PASS"
    UNRESOLVED = "UNRESOLVED"


class OracleInterrupted(KeyboardInterrupt):
    """Carry launch evidence to the invocation-budget owner on cancellation.

    None means interruption occurred inside Popen construction: whether the
    oracle actually launched cannot be established from the returned state.
    """

    def __init__(self, executed: bool | None) -> None:
        super().__init__("oracle invocation interrupted")
        self.executed = executed


@dataclass(frozen=True)
class OracleResult:
    outcome: Outcome
    reason: str
    exit_code: int | None
    output_bytes: int
    duration_seconds: float
    executed: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "output_bytes": self.output_bytes,
            "duration_seconds": round(self.duration_seconds, 6),
            "executed": self.executed,
        }


class _LineMatcher:
    """Compare complete UTF-8 byte lines without retaining arbitrary output."""

    def __init__(self, marker: str) -> None:
        self.expected = marker.encode("utf-8")
        self.pending = bytearray()
        self.overlong = False
        self.found = False

    def _finish(self) -> None:
        if not self.overlong and bytes(self.pending).removesuffix(b"\r") == self.expected:
            self.found = True
        self.pending.clear()
        self.overlong = False

    def feed(self, data: bytes) -> None:
        segments = data.split(b"\n")
        for index, segment in enumerate(segments):
            if not self.overlong:
                if len(self.pending) + len(segment) <= len(self.expected) + 1:
                    self.pending.extend(segment)
                else:
                    self.pending.clear()
                    self.overlong = True
            if index != len(segments) - 1:
                self._finish()

    def finish(self) -> None:
        self._finish()


class _Capture:
    def __init__(self, spec: OracleSpec) -> None:
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.done = (threading.Event(), threading.Event())
        self.matcher = _LineMatcher(spec.marker)
        self.marker_stream = 0 if spec.stream == "stdout" else 1
        self.limit = spec.output_limit_bytes
        self.output_bytes = 0
        self.exceeded = False
        self.read_error = False

    def reader(self, pipe: BinaryIO, stream: int) -> None:
        try:
            while not self.stop.is_set():
                data = _read_pipe(pipe)
                if data is None:
                    self.stop.wait(0.005)
                    continue
                if not data:
                    with self.lock:
                        if stream == self.marker_stream:
                            self.matcher.finish()
                    return
                with self.lock:
                    self.output_bytes += len(data)
                    if self.output_bytes > self.limit:
                        self.exceeded = True
                        self.stop.set()
                    if stream == self.marker_stream:
                        self.matcher.feed(data)
        except (OSError, ValueError):
            if not self.stop.is_set():
                with self.lock:
                    self.read_error = True
        finally:
            self.done[stream].set()


def _kill_tree(process: subprocess.Popen[bytes], close_job: Callable[[], None] | None) -> None:
    """Bounded cleanup, including a POSIX group whose leader already exited.

    Windows uses a kill-on-close Job when assignment succeeds, and taskkill
    otherwise. Assignment races, host Job restrictions and detached processes
    mean cleanup is still best effort, not an isolation guarantee.
    """
    if sys.platform == "win32":
        if close_job is not None:
            close_job()
        elif process.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    timeout=1.0,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass


@dataclass
class _ExecutionState:
    executed: bool | None = False


def _execute(
    spec: OracleSpec, root: Path, database: Path, execution: _ExecutionState
) -> OracleResult:
    started = time.monotonic()
    argv = tuple(
        sys.executable if arg == "{python}" else str(database) if arg == "{db}" else arg
        for arg in spec.argv
    )
    capture = _Capture(spec)
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        execution.executed = None
        process = subprocess.Popen(
            argv,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            shell=False,
            start_new_session=os.name == "posix",
            creationflags=creation_flags,
        )
        execution.executed = True
    except (OSError, ValueError):
        execution.executed = False
        return OracleResult(
            Outcome.UNRESOLVED,
            "launch_error",
            None,
            0,
            time.monotonic() - started,
            executed=False,
        )

    close_job: Callable[[], None] | None = None
    readers: tuple[threading.Thread, ...] = ()
    forced_reason: str | None = None
    try:
        if sys.platform == "win32":
            close_job = _windows_job(process.pid)
        assert process.stdout is not None
        assert process.stderr is not None
        readers = tuple(
            threading.Thread(target=capture.reader, args=(pipe, index), daemon=True)
            for index, pipe in enumerate((process.stdout, process.stderr))
        )
        for reader in readers:
            reader.start()
        deadline = started + spec.timeout_seconds
        while True:
            with capture.lock:
                exceeded = capture.exceeded
                read_error = capture.read_error
            if exceeded:
                forced_reason = "combined output limit exceeded"
                break
            if read_error:
                forced_reason = "output read failed"
                break
            if process.poll() is not None and all(done.is_set() for done in capture.done):
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                forced_reason = "deadline exceeded (process or open output pipes)"
                break
            capture.stop.wait(min(0.01, remaining))
    finally:
        capture.stop.set()
        # Also reap descendants after a normal exit: they may have closed the
        # pipes but still be running. Do not reuse their test database state.
        _kill_tree(process, close_job)
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
        for reader in readers:
            if reader.ident is not None:
                reader.join(timeout=0.1)

    exit_code = process.poll()
    with capture.lock:
        output_bytes = capture.output_bytes
        marker = capture.matcher.found
        if capture.exceeded:
            forced_reason = "combined output limit exceeded"
        elif capture.read_error and forced_reason is None:
            forced_reason = "output read failed"
    if forced_reason is not None:
        outcome = Outcome.UNRESOLVED
        reason = forced_reason
    elif exit_code == spec.expected_exit and marker:
        outcome = Outcome.TARGET_FAILURE
        reason = "expected exit and exact failure marker"
    elif exit_code == 0 and not marker:
        outcome = Outcome.PASS
        reason = "zero exit without target marker"
    elif exit_code is not None and exit_code < 0:
        outcome = Outcome.UNRESOLVED
        reason = "process terminated by signal"
    elif exit_code == 0:
        outcome = Outcome.UNRESOLVED
        reason = "target marker contradicts zero exit"
    elif exit_code != spec.expected_exit:
        outcome = Outcome.UNRESOLVED
        reason = "unexpected exit code"
    else:
        outcome = Outcome.UNRESOLVED
        reason = "expected failure exit without exact marker"
    return OracleResult(outcome, reason, exit_code, output_bytes, time.monotonic() - started)


def run_oracle(spec: OracleSpec, database: Path, assets: tuple[Asset, ...]) -> OracleResult:
    """Stage pristine files, then execute one bounded oracle invocation."""
    started = time.monotonic()
    execution = _ExecutionState()
    # A misbehaving Windows descendant can retain an open file. Cleanup must
    # remain best effort rather than mask the bounded invocation result.
    try:
        with tempfile.TemporaryDirectory(
            prefix="reproseed-oracle-", ignore_cleanup_errors=True
        ) as temp:
            root = Path(temp)
            staged_database = root / "db.sqlite3"
            try:
                shutil.copyfile(database, staged_database)
                for asset in assets:
                    target = root / asset.relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(asset.path, target)
            except OSError:
                return OracleResult(
                    Outcome.UNRESOLVED,
                    "staging_error",
                    None,
                    0,
                    time.monotonic() - started,
                    executed=False,
                )
            return _execute(spec, root, staged_database, execution)
    except KeyboardInterrupt as error:
        raise OracleInterrupted(execution.executed) from error
