"""Run the user's explicit failure contract against disposable staged files.

The temporary directory protects fixture state; it is not an OS sandbox. Pipe
readers retain only enough bytes to compare one exact marker line, and the
deadline covers both the process and descendants that keep its pipes open.
"""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Protocol

from reproseed.config import Asset, OracleSpec


class _Job(Protocol):
    def stop(self, deadline: float) -> None: ...

    def close(self) -> None: ...


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
    _kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel.TerminateJobObject.restype = wintypes.BOOL
    _kernel.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    _kernel.QueryInformationJobObject.restype = wintypes.BOOL
    _kernel.IsProcessInJob.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.BOOL),
    ]
    _kernel.IsProcessInJob.restype = wintypes.BOOL
    _kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel.WaitForSingleObject.restype = wintypes.DWORD
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

    class _WindowsJob:
        """Own exactly one invocation's Job; process signals establish exit.

        ActiveProcesses has process-reference lifetime semantics. Neither
        that count nor a Job handle wait establishes process termination.
        """

        def __init__(self, handle: int) -> None:
            self.handle: int | None = handle

        def close(self) -> None:
            handle, self.handle = self.handle, None
            if handle is not None:
                _kernel.CloseHandle(handle)

        def stop(self, deadline: float) -> None:
            assert self.handle is not None
            owned: list[int] = []
            members: list[int] = []
            seen: set[int] = set()

            def capture_members() -> None:
                for pid in self._pids(deadline):
                    if pid in seen:
                        continue
                    if time.monotonic() >= deadline:
                        _cleanup_warning("Job member capture deadline", None)
                        return
                    process_handle = _kernel.OpenProcess(0x100000 | 0x1000, False, pid)
                    if not process_handle:
                        error = ctypes.get_last_error()
                        if error != 87:  # ERROR_INVALID_PARAMETER: already gone
                            _cleanup_warning("Job member observation", error)
                        continue
                    owned.append(process_handle)
                    seen.add(pid)  # the retained handle now prevents PID reuse
                    member = wintypes.BOOL()
                    if not _kernel.IsProcessInJob(
                        process_handle, self.handle, ctypes.byref(member)
                    ):
                        _cleanup_warning("Job membership observation", ctypes.get_last_error())
                    elif member.value:
                        # PID reuse cannot make us wait on an unrelated process.
                        members.append(process_handle)

            try:
                # Capture identities BEFORE termination: exiting members can
                # disappear from the Job list before their objects signal.
                capture_members()
                if not _kernel.TerminateJobObject(self.handle, 1):
                    _cleanup_warning("Job termination", ctypes.get_last_error())
                    return  # close() still supplies kill-on-close fallback
                # Also cover members associated during the first snapshot.
                capture_members()
                for process_handle in members:
                    milliseconds = int(max(0.0, deadline - time.monotonic()) * 1000)
                    status = _kernel.WaitForSingleObject(process_handle, milliseconds)
                    if status != 0:  # WAIT_OBJECT_0 means the process exited
                        _cleanup_warning(
                            "Job member wait",
                            ctypes.get_last_error() if status == 0xFFFFFFFF else status,
                        )
            finally:
                for process_handle in owned:
                    _kernel.CloseHandle(process_handle)

        def _pids(self, deadline: float) -> tuple[int, ...]:
            capacity = 64
            while time.monotonic() < deadline:
                # ULONG_PTR list follows two DWORD counts (8-byte header).
                buffer = ctypes.create_string_buffer(8 + capacity * ctypes.sizeof(ctypes.c_size_t))
                if _kernel.QueryInformationJobObject(
                    self.handle, 3, buffer, ctypes.sizeof(buffer), None
                ):
                    assigned = wintypes.DWORD.from_buffer(buffer).value
                    count = wintypes.DWORD.from_buffer(buffer, 4).value
                    if count < assigned:
                        if capacity >= 65536:
                            _cleanup_warning("Job member enumeration capacity", None)
                            return ()
                        capacity *= 2
                        continue
                    pids = (ctypes.c_size_t * count).from_buffer(buffer, 8)
                    return tuple(pids)
                error = ctypes.get_last_error()
                if error != 234 or capacity >= 65536:  # ERROR_MORE_DATA
                    _cleanup_warning("Job member enumeration", error)
                    return ()
                capacity *= 2
            _cleanup_warning("Job member enumeration deadline", None)
            return ()

    def _windows_job(pid: int, owner: _Cleanup | None = None) -> _WindowsJob | None:
        """Try to keep the process tree in a kill-on-close Windows Job."""
        handle = _kernel.CreateJobObjectW(None, None)
        if not handle:
            return None
        job = _WindowsJob(handle)
        if owner is not None:
            owner.job = job
        assigned = False
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            configured = _kernel.SetInformationJobObject(
                handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            )
            if configured:
                process_handle = _kernel.OpenProcess(0x0100 | 0x0001, False, pid)
                if process_handle:
                    try:
                        assigned = bool(_kernel.AssignProcessToJobObject(handle, process_handle))
                    finally:
                        _kernel.CloseHandle(process_handle)
            if assigned:
                return job
            return None
        except BaseException:
            job.close()
            if owner is not None:
                owner.job = None
            raise
        finally:
            if not assigned:
                job.close()
                if owner is not None:
                    owner.job = None


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

    def __init__(self, executed: bool | None, *, abort: bool = False) -> None:
        super().__init__("oracle invocation interrupted")
        self.executed = executed
        self.abort = abort


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


_CLEANUP_SECONDS = 1.5


@dataclass
class _Cleanup:
    deadline: float | None = None
    abort: bool = False
    job: _Job | None = None

    def begin(self) -> float:
        if self.deadline is None:
            self.deadline = time.monotonic() + _CLEANUP_SECONDS
        return self.deadline

    def remaining(self) -> float:
        return max(0.0, self.begin() - time.monotonic())


def _cleanup_warning(operation: str, error: int | None) -> None:
    # No raw oracle output, staged values or inherited environment. Warnings
    # configured as errors must not replace cancellation or its launch evidence.
    try:
        warnings.warn(
            f"oracle cleanup incomplete: {operation} (code {error})", RuntimeWarning, stacklevel=2
        )
    except RuntimeWarning:
        pass


def _remove_owned_directory(root: Path, cleanup: _Cleanup) -> None:
    def reset_readonly(function: Callable[[str], object], path: str, error: BaseException) -> None:
        target = Path(path)
        if isinstance(error, FileNotFoundError):
            return
        if sys.platform == "win32" and isinstance(error, PermissionError):
            try:
                metadata = target.lstat()
            except FileNotFoundError:
                return
            if (
                function in {os.unlink, os.rmdir}
                and not metadata.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                and not metadata.st_mode & stat.S_IWRITE
            ):
                target.chmod(metadata.st_mode | stat.S_IWRITE)
                try:
                    function(path)
                except FileNotFoundError:
                    pass
                return
        raise error

    cleanup.begin()
    while True:
        try:
            # rmtree does not traverse nested symlinks or Windows junctions.
            # Refuse a replaced root as well; never resolve it to another tree.
            if root.is_symlink() or root.is_junction():
                _cleanup_warning("temporary directory replaced by a link", None)
                return
            shutil.rmtree(root, onexc=reset_readonly)
            return
        except FileNotFoundError:
            if root.exists():
                _cleanup_warning("temporary directory removal left its root", 2)
            return
        except OSError as error:
            # Windows access/sharing/lock/nonempty errors can be transient
            # after termination. Other failures do not warrant a retry.
            transient = getattr(error, "winerror", None) in {5, 32, 33, 145}
            remaining = cleanup.remaining()
            if not transient or remaining <= 0:
                _cleanup_warning(
                    "temporary directory removal", getattr(error, "winerror", error.errno)
                )
                return
            time.sleep(min(0.01, remaining))


def _kill_tree(process: subprocess.Popen[bytes], job: _Job | None, cleanup: _Cleanup) -> None:
    """Bounded cleanup, including a POSIX group whose leader already exited.

    Windows terminates and observes an owned Job when assignment succeeds, and taskkill
    otherwise. Assignment races, host Job restrictions and detached processes
    mean cleanup is still best effort, not an isolation guarantee.
    """
    deadline = cleanup.begin()
    if sys.platform == "win32":
        if job is not None:
            try:
                job.stop(deadline)
            finally:
                job.close()
        elif process.poll() is None:
            try:
                result = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    timeout=cleanup.remaining(),
                    check=False,
                )
                if result.returncode:
                    _cleanup_warning("taskkill exit", result.returncode)
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
        process.wait(timeout=cleanup.remaining())
    except subprocess.TimeoutExpired:
        _cleanup_warning("parent wait deadline", None)


@dataclass
class OracleInvocation:
    """Caller-owned launch evidence, including interrupted result transfer.

    None is reserved for the process-construction interval where no returned
    process handle establishes whether a launch occurred.
    """

    executed: bool | None = False


def _execute(
    spec: OracleSpec, root: Path, database: Path, execution: OracleInvocation, cleanup: _Cleanup
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
    process: subprocess.Popen[bytes] | None = None
    readers: tuple[threading.Thread, ...] = ()
    forced_reason: str | None = None
    interrupted = False
    try:
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
        if sys.platform == "win32":
            _windows_job(process.pid, cleanup)
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
    except KeyboardInterrupt:
        interrupted = True
        raise
    finally:
        capture.stop.set()
        # Also reap descendants after a normal exit: they may have closed the
        # pipes but still be running. Do not reuse their test database state.
        try:
            try:
                if process is not None:
                    # A returned handle establishes launch even if cancellation
                    # preceded the assignment above.
                    execution.executed = True
                    _kill_tree(process, cleanup.job, cleanup)
            finally:
                try:
                    for reader in readers:
                        if reader.ident is not None:
                            reader.join(timeout=cleanup.remaining())
                            if reader.is_alive():
                                _cleanup_warning("pipe reader deadline", None)
                finally:
                    if process is not None:
                        for pipe in (process.stdout, process.stderr):
                            if pipe is not None:
                                try:
                                    pipe.close()
                                except OSError as error:
                                    _cleanup_warning("pipe close", error.errno)
        except KeyboardInterrupt:
            cleanup.abort = cleanup.abort or interrupted
            raise

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


def run_oracle(
    spec: OracleSpec,
    database: Path,
    assets: tuple[Asset, ...],
    invocation: OracleInvocation | None = None,
) -> OracleResult:
    """Stage pristine files, then execute one bounded oracle invocation."""
    started = time.monotonic()
    execution = invocation if invocation is not None else OracleInvocation()
    cleanup = _Cleanup()
    root: Path | None = None
    interrupted = False
    try:
        try:
            root = Path(tempfile.mkdtemp(prefix="reproseed-oracle-"))
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
            return _execute(spec, root, staged_database, execution, cleanup)
        except KeyboardInterrupt:
            interrupted = True
            raise
        finally:
            try:
                if root is not None:
                    _remove_owned_directory(root, cleanup)
            except KeyboardInterrupt:
                cleanup.abort = cleanup.abort or interrupted
                raise
    except KeyboardInterrupt as error:
        raise OracleInterrupted(execution.executed, abort=cleanup.abort) from error
