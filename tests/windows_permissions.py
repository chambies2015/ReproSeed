"""Bounded, privacy-safe observations of a test-owned Windows ACL boundary."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path


def _acl_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    # Do not put the account, ACL readback or private paths into failure output.
    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=5)
    except subprocess.TimeoutExpired:
        raise RuntimeError("owned ACL operation timed out") from None
    except OSError as exc:
        raise RuntimeError(f"owned ACL operation failed (errno={exc.errno})") from None
    if result.returncode != 0:
        raise RuntimeError(f"owned ACL operation exited {result.returncode}")
    return result


_DACL_PROGRAM = """
import ctypes, sys
from pathlib import Path
api = ctypes.WinDLL('advapi32', use_last_error=True)
api.GetFileSecurityW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_void_p,
                               ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
api.GetFileSecurityW.restype = ctypes.c_int
api.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ulong)]
api.GetSecurityDescriptorControl.restype = ctypes.c_int
api.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int)]
api.GetSecurityDescriptorDacl.restype = ctypes.c_int
api.SetFileSecurityW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_void_p]
api.SetFileSecurityW.restype = ctypes.c_int
api.SetNamedSecurityInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
api.SetNamedSecurityInfoW.restype = ctypes.c_ulong
action, target, snapshot = sys.argv[1:]
if action == 'snapshot':
    needed = ctypes.c_ulong()
    ok = api.GetFileSecurityW(target, 4, None, 0, ctypes.byref(needed))
    if ok or ctypes.get_last_error() != 122 or not 0 < needed.value <= 65536:
        raise SystemExit(ctypes.get_last_error() or 1)
    buffer = ctypes.create_string_buffer(needed.value)
    if not api.GetFileSecurityW(target, 4, buffer, len(buffer), ctypes.byref(needed)):
        raise SystemExit(ctypes.get_last_error() or 1)
    Path(snapshot).write_bytes(buffer.raw[:needed.value])
elif action in ('restore', 'restore_inheritance'):
    data = Path(snapshot).read_bytes()
    if not 0 < len(data) <= 65536:
        raise SystemExit(1)
    buffer = ctypes.create_string_buffer(data)
    control, revision = ctypes.c_ushort(), ctypes.c_ulong()
    if not api.GetSecurityDescriptorControl(buffer, ctypes.byref(control), ctypes.byref(revision)):
        raise SystemExit(ctypes.get_last_error() or 1)
    if action == 'restore' and not control.value & 0x0400:
        # Preserve non-auto-inherited metadata, including pytest's inherited
        # ACEs with no AI control flag. SetNamedSecurityInfo would re-inherit.
        if not api.SetFileSecurityW(target, 4, buffer):
            raise SystemExit(ctypes.get_last_error() or 1)
    else:
        present, defaulted, dacl = ctypes.c_int(), ctypes.c_int(), ctypes.c_void_p()
        if not api.GetSecurityDescriptorDacl(buffer, ctypes.byref(present), ctypes.byref(dacl),
                                         ctypes.byref(defaulted)):
            raise SystemExit(ctypes.get_last_error() or 1)
        flags = 4 | (0x80000000 if control.value & 0x1000 else 0x20000000)
        status = api.SetNamedSecurityInfoW(target, 1, flags, None, None, dacl, None)
        if status:
            raise SystemExit(status)
else:
    raise SystemExit(1)
"""


def _dacl_operation(action: str, parent: Path, snapshot: Path) -> None:
    # SECURITY_INFORMATION=4 addresses only the DACL, never owner/group/SACL,
    # and restoration retains the original protected/unprotected inheritance.
    # A subprocess gives synchronous Windows calls the same five-second bound.
    _acl_command([sys.executable, "-c", _DACL_PROGRAM, action, str(parent), str(snapshot)])


@contextmanager
def denied_directory_acl(
    parent: Path, permissions: str = "(WD,AD)", *, propagate_children: bool = False
) -> Iterator[dict[str, object]]:
    """Target the owned parent; inherited ACEs may also affect its owned children."""
    identity = _acl_command(["whoami"]).stdout.strip()
    if not identity:
        raise RuntimeError("current Windows identity was unavailable")
    identifier = uuid.uuid4().hex
    saved = parent.parent / ("acl-original-" + identifier + ".txt")
    readback = parent.parent / ("acl-readback-" + identifier + ".txt")
    descriptor = parent.parent / ("acl-descriptor-" + identifier + ".bin")
    _acl_command(["icacls", str(parent), "/save", str(saved)])
    original = saved.read_bytes()
    _dacl_operation("snapshot", parent, descriptor)
    observation: dict[str, object] = {"acl_saved": True, "acl_restored": False}
    try:
        # Establish exact restoration support before applying any deny. Failure
        # is a helper error, never a capability skip or a privilege adjustment.
        _dacl_operation("restore", parent, descriptor)
        _acl_command(["icacls", str(parent), "/save", str(readback)])
        if readback.read_bytes() != original:
            raise RuntimeError("owned directory DACL restoration preflight did not match")
        observation["acl_restore_preflight"] = True
        readback.unlink()
        _acl_command(["icacls", str(parent), "/deny", identity + ":" + permissions])
        observation["acl_edit_exit"] = 0
        _acl_command(["icacls", str(parent)])
        observation["acl_readback_exit"] = 0
        yield observation
    finally:
        active_error = sys.exc_info()[1]
        try:
            # /remove:d could remove original denies and /deny can alter explicit
            # grants. Restore the complete captured DACL, preserving its metadata.
            # No backup/restore privilege changes or recursive icacls calls occur.
            if propagate_children:
                # An inherited deny can remain on children when exact parent
                # metadata requires SetFileSecurity. Restore their inherited
                # rights through this sole owned parent first; never target a
                # child's ACL directly. Then restore exact parent metadata.
                _dacl_operation("restore_inheritance", parent, descriptor)
                observation["children_inheritance_restore_exit"] = 0
            _dacl_operation("restore", parent, descriptor)
            readback.unlink(missing_ok=True)
            _acl_command(["icacls", str(parent), "/save", str(readback)])
            observation["acl_restored"] = readback.read_bytes() == original
            if not observation["acl_restored"]:
                raise RuntimeError("owned directory DACL did not match its original snapshot")
            for private_snapshot in (saved, readback, descriptor):
                private_snapshot.unlink()
        except Exception as cleanup_error:
            observation["acl_restore_failed"] = True
            if isinstance(active_error, (Exception, KeyboardInterrupt)):
                active_error.add_note(
                    "owned directory DACL restoration failed "
                    f"({type(cleanup_error).__name__}); private snapshots retained"
                )
            else:
                # pytest.skip is a BaseException. A would-be capability skip must
                # become an error when the actual original ACL could not be restored.
                raise


def probe_directory_creation(
    parent: Path,
    *,
    python: str = sys.executable,
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Try the production mkdir mode in the CLI's interpreter/token/cwd context."""
    child = parent / (".reproseed-probe-" + uuid.uuid4().hex)
    program = """
import errno, json, sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    p.mkdir(mode=0o700)
except OSError as exc:
    denied = (isinstance(exc, PermissionError) and exc.errno == errno.EACCES
              and getattr(exc, 'winerror', None) == 5)
    print(json.dumps({'decision': 'denied' if denied else 'unexpected_error',
                      'errno': exc.errno, 'winerror': getattr(exc, 'winerror', None)}))
else:
    p.rmdir()
    print(json.dumps({'decision': 'allowed', 'errno': None, 'winerror': None}))
"""
    started = time.monotonic()
    try:
        result = subprocess.run(
            [python, "-c", program, str(child)],
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("directory capability probe timed out") from None
    except OSError as exc:
        raise RuntimeError(f"directory capability probe failed (errno={exc.errno})") from None
    # A process/path/cleanup error must never become a capability skip.
    if result.returncode != 0 or result.stderr:
        raise RuntimeError(f"directory capability probe failed (exit={result.returncode})")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("decision") not in {
        "denied",
        "allowed",
        "unexpected_error",
    }:
        raise RuntimeError("invalid directory capability probe result")
    value["exit"] = result.returncode
    value["seconds"] = time.monotonic() - started
    value["probe_removed"] = not child.exists()
    return value
