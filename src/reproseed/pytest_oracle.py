"""Explicit, optional pytest bridge for the version-1 exit/marker protocol.

No pytest import or test discovery happens when this module is imported or its
help is shown. Tests are trusted executable code; this is not a sandbox.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import inspect
import os
import re
import sys
import tempfile
import threading
import tomllib
from collections.abc import Callable, Generator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Never, cast

from reproseed.config import ConfigError, safe_file
from reproseed.sqlite_adapter import DatabaseError, snapshot

if TYPE_CHECKING:
    import pytest

MARKER = "REPROSEED_PYTEST_TARGET_V1"
TARGET_EXIT = 86
MAX_TARGET_BYTES = 16 * 1024
SUPPORTED_PYTEST = ">=8.3,<10"
# Ordinary local fixtures are supported. These hooks replace or reinterpret
# execution, fixture binding or reports and are outside this initial bridge.
_EXECUTION_HOOKS = {
    "pytest_fixture_setup",
    "pytest_pyfunc_call",
    "pytest_runtest_call",
    "pytest_runtest_protocol",
    "pytest_runtestloop",
    "pytest_runtest_makereport",
}
# Explicit capture fixtures work even with --capture=no. They and logging/warnings
# plugin would buffer bytes outside the containing oracle's output accounting.
_CAPTURE_FIXTURES = {
    "capsys",
    "capfd",
    "capsysbinary",
    "capfdbinary",
    "capteesys",
    "caplog",
    "recwarn",
}


class TargetError(ValueError):
    """A fixed reason code, never target content or private paths."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PytestTarget:
    root: Path
    file: Path
    nodeid: str
    exception: str
    message: str


def _string(value: object, limit: int, *, controls: bool = False) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise TargetError("invalid-target-string")
    try:
        if len(value.encode("utf-8")) > limit:
            raise TargetError("invalid-target-string")
    except UnicodeError as exc:
        raise TargetError("invalid-target-string") from exc
    if not controls and any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise TargetError("invalid-target-string")
    return value


def load_target(path: Path) -> PytestTarget:
    """Read one bounded, strict target, rooted at its own directory."""
    path = path.absolute()
    try:
        if any(part.is_symlink() or part.is_junction() for part in (path, *path.parents)):
            raise TargetError("unsafe-target-path")
        if not path.is_file():
            raise TargetError("target-not-regular-file")
        with path.open("rb") as stream:
            data = stream.read(MAX_TARGET_BYTES + 1)
        if len(data) > MAX_TARGET_BYTES:
            raise TargetError("target-too-large")
        raw = tomllib.loads(data.decode("utf-8"))
    except TargetError:
        raise
    except (OSError, ValueError, RecursionError) as exc:
        raise TargetError("target-unreadable-or-malformed") from exc
    if raw.keys() != {"adapter_version", "nodeid", "exception", "message"}:
        raise TargetError("invalid-target-fields")
    if type(raw["adapter_version"]) is not int or raw["adapter_version"] != 1:
        raise TargetError("unsupported-adapter-version")
    nodeid = _string(raw["nodeid"], 4096)
    exception = _string(raw["exception"], 512)
    message = _string(raw["message"], 4096, controls=True)
    if "." not in exception or any(not part.isidentifier() for part in exception.split(".")):
        raise TargetError("invalid-exception-name")
    name, separator, selector = nodeid.partition("::")
    selection, bracket, parameters = selector.partition("[")
    parts = selection.split("::")
    if (
        not separator
        or len(parts) not in (1, 2)
        or any(not part.isidentifier() for part in parts)
        or (bracket and not parameters.endswith("]"))
        or Path(name).suffix != ".py"
    ):
        raise TargetError("invalid-exact-nodeid")
    root = path.parent.resolve()
    try:
        test_file = safe_file(root, name)
        for directory in (test_file.parent, *test_file.parent.parents):
            if not directory.is_relative_to(root):
                break
            conftest = directory / "conftest.py"
            if conftest.exists() or conftest.is_symlink() or conftest.is_junction():
                safe_file(root, conftest.relative_to(root).as_posix())
    except (ConfigError, OSError, ValueError) as exc:
        raise TargetError("unsafe-test-path") from exc
    return PytestTarget(root, test_file, nodeid, exception, message)


def _supported_pytest(version: object) -> bool:
    if not isinstance(version, str):
        return False
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", version)
    if match is None:
        return False
    major, minor = int(match[1]), int(match[2])
    return (major == 8 and minor >= 3) or major == 9


class _Session:
    """Keep bounded structured evidence for exactly one selected pytest item."""

    def __init__(self, target: PytestTarget, database: Path) -> None:
        self.target = target
        self.database = database
        self.problem: str | None = None
        self.collected = 0
        self.starts = 0
        self.finishes = 0
        self.session_starts = 0
        self.session_finishes = 0
        self.session_exit: object = None
        self.session: pytest.Session | None = None
        self.selected_item: pytest.Item | None = None
        self.calls: dict[str, tuple[str, str | None, str | None]] = {}
        self.reports: dict[str, str] = {}
        self.fixture_function: Callable[[], Path] | None = None
        self.fixture_setups = 0
        self.pytest: ModuleType | None = None

    def pytest_plugin_registered(self, plugin: object, manager: pytest.PytestPluginManager) -> None:
        if plugin is self or getattr(plugin, "__name__", None) == "reproseed_pytest_fixtures":
            return
        module = (
            plugin.__name__
            if isinstance(plugin, ModuleType)
            else getattr(plugin, "__module__", type(plugin).__module__)
        )
        if module.startswith("_pytest.") or module == "_pytest":
            return
        filename = getattr(plugin, "__file__", None)
        if isinstance(filename, str):
            path = Path(filename)
            if path.name == "conftest.py" and path.resolve().is_relative_to(self.target.root):
                reason = None
                callers = manager.get_hookcallers(plugin) or []
                if any(caller.name in _EXECUTION_HOOKS for caller in callers):
                    reason = "execution-hook-unsupported"
                elif getattr(plugin, "pytest_plugins", None):
                    reason = "external-plugin-unsupported"
                if reason is not None:
                    self._reject(reason)
                    assert self.pytest is not None
                    raise self.pytest.UsageError(f"reproseed: {reason}")
                return
        self._reject("external-plugin-unsupported")

    def _reject(self, reason: str) -> None:
        if self.problem is None:
            self.problem = reason

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        self.session_starts += 1
        self.session = session

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        assert self.pytest is not None
        selected = [item for item in items if item.nodeid == self.target.nodeid]
        items[:] = selected
        self.collected = len(selected)
        reason: str | None = None
        if len(items) != 1 or items[0].nodeid != self.target.nodeid:
            reason = "selection-not-exact"
        elif type(items[0]) is not self.pytest.Function:
            reason = "unsupported-collector"
        else:
            item = cast("pytest.Function", items[0])
            function = item.obj
            supported_parents = {
                self.pytest.Session,
                self.pytest.Dir,
                self.pytest.Package,
                self.pytest.Module,
                self.pytest.Class,
            }
            if any(type(parent) not in supported_parents for parent in item.listchain()[:-1]):
                reason = "unsupported-collector"
            elif (
                not (inspect.isfunction(function) or inspect.ismethod(function))
                or inspect.iscoroutinefunction(function)
                or inspect.isasyncgenfunction(function)
                or inspect.isgeneratorfunction(function)
            ):
                reason = "unsupported-test-function"
            elif "reproseed_db" not in item.fixturenames:
                reason = "database-fixture-required"
            elif _CAPTURE_FIXTURES.intersection(item.fixturenames):
                reason = "capture-fixture-unsupported"
            elif any(
                next(item.iter_markers(name), None) is not None
                for name in ("skip", "skipif", "xfail", "flaky", "rerun", "xdist_group")
            ):
                reason = "skip-xfail-or-rerun-unsupported"
        if self.problem is not None:
            reason = self.problem
        if reason is not None:
            self._reject(reason)
            items.clear()  # Collection may import code, but no setup/call may follow rejection.
        else:
            self.selected_item = items[0]

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if not report.passed:
            self._reject("collection-incomplete")

    def pytest_runtestloop(self, session: pytest.Session) -> None:
        if (
            len(session.items) != 1
            or session.items[0].nodeid != self.target.nodeid
            or session.items[0] is not self.selected_item
        ):
            self._reject("selection-not-exact")
            assert self.pytest is not None
            raise self.pytest.UsageError("reproseed: selection-not-exact")

    def pytest_runtest_logstart(self, nodeid: str) -> None:
        self.starts += 1
        if nodeid != self.target.nodeid or self.starts != 1:
            self._reject("unexpected-test-execution")
            assert self.pytest is not None
            raise self.pytest.UsageError("reproseed: unexpected-test-execution")

    def pytest_runtest_logfinish(self, nodeid: str) -> None:
        self.finishes += 1
        if nodeid != self.target.nodeid or self.finishes != 1:
            self._reject("unexpected-test-execution")

    def pytest_pyfunc_call(self, pyfuncitem: pytest.Function) -> None:
        # Pytest's own Python-function implementation is trylast. This check
        # therefore runs before the function body, after every fixture wrapper.
        if pyfuncitem.funcargs.get("reproseed_db") is not self.database:
            self._reject("reserved-fixture-overridden")
            assert self.pytest is not None
            raise self.pytest.UsageError("reproseed: reserved-fixture-overridden")

    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]) -> None:
        phase = call.when
        if item.nodeid != self.target.nodeid or phase not in {"setup", "call", "teardown"}:
            self._reject("unexpected-phase")
            return
        if phase in self.calls:
            self._reject("duplicate-phase")
            return
        if call.excinfo is None:
            self.calls[phase] = ("passed", None, None)
            return
        value = call.excinfo.value
        if isinstance(value, BaseExceptionGroup):
            self._reject("exception-group-unsupported")
        try:
            signature = f"{type(value).__module__}.{type(value).__qualname__}"
            message = str(value)
        except Exception:
            self._reject("exception-signature-unavailable")
            signature, message = None, None
        self.calls[phase] = ("failed", signature, message)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        phase = report.when
        if (
            report.nodeid != self.target.nodeid
            or phase not in {"setup", "call", "teardown"}
            or phase in self.reports
        ):
            self._reject("unexpected-or-duplicate-report")
            return
        if hasattr(report, "wasxfail") or report.outcome not in {"passed", "failed"}:
            self._reject("skip-or-xfail-unsupported")
        self.reports[phase] = report.outcome

    def pytest_fixture_setup(
        self, fixturedef: pytest.FixtureDef[object], request: pytest.FixtureRequest
    ) -> object:
        if fixturedef.argname in _CAPTURE_FIXTURES:
            self._reject("capture-fixture-unsupported")
            assert self.pytest is not None
            raise self.pytest.UsageError("reproseed: capture-fixture-unsupported")
        if fixturedef.argname == "reproseed_db":
            if fixturedef.func is not self.fixture_function:
                self._reject("reserved-fixture-overridden")
                assert self.pytest is not None
                raise self.pytest.UsageError("reproseed: reserved-fixture-overridden")
            self.fixture_setups += 1
        return None

    def pytest_internalerror(self) -> None:
        self._reject("pytest-internal-error")

    def pytest_keyboard_interrupt(self) -> None:
        self._reject("interrupted")

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        self.session_finishes += 1
        self.session_exit = exitstatus
        if session.testscollected != 1:
            self._reject("selection-not-exact")

    def classify(self, exit_code: object) -> tuple[int, str]:
        if self.problem == "interrupted":
            return 130, "interrupted"
        if self.problem is not None:
            return 2, self.problem
        if (
            not isinstance(exit_code, int)
            or isinstance(exit_code, bool)
            or exit_code not in (0, 1)
            or exit_code != self.session_exit
        ):
            return 2, "inconsistent-session-exit"
        if (
            self.collected != 1
            or self.starts != 1
            or self.finishes != 1
            or self.session_starts != 1
            or self.session_finishes != 1
            or self.fixture_setups != 1
            or self.calls.keys() != {"setup", "call", "teardown"}
            or self.reports.keys() != {"setup", "call", "teardown"}
        ):
            return 2, "incomplete-session"
        if any(self.calls[phase][0] != self.reports[phase] for phase in self.calls):
            return 2, "contradictory-phase-report"
        if self.reports["setup"] != "passed" or self.reports["teardown"] != "passed":
            return 2, "setup-or-teardown-failed"
        if self.session is not None and (
            self.session.testscollected != 1
            or self.session.testsfailed != exit_code
            or self.session.shouldfail
            or self.session.shouldstop
        ):
            return 2, "inconsistent-final-session"
        if self.reports["call"] == "passed" and exit_code == 0:
            return 0, "passed"
        if (
            self.reports["call"] == "failed"
            and exit_code == 1
            and self.calls["call"][1:] == (self.target.exception, self.target.message)
        ):
            return TARGET_EXIT, "target"
        return 2, "different-call-failure"


class _ForwardOutput:
    """Discard pytest rendering while streaming bounded output-volume records.

    OS descriptors cover Python prints, os.write and ordinary subprocess output.
    Public pytest.main can render raw configuration errors even without its
    terminal plugin. No rendering is forwarded. Fixed records account for at
    least the observed byte volume, preserving the outer runner's output bound
    and preventing printed protocol markers. This is not a sandbox or a general
    sanitizer for arbitrary trusted code.
    """

    def __init__(self) -> None:
        self.complete = False
        self.failed = False
        self.saved: tuple[int, int] | None = None
        self.reader = -1
        self.thread: threading.Thread | None = None

    def _forward(self) -> None:
        assert self.saved is not None
        try:
            while chunk := os.read(self.reader, 4096):
                record = b"reproseed-pytest: output-accounted\n"
                payload = record * ((len(chunk) + len(record) - 1) // len(record))
                while payload:
                    payload = payload[os.write(self.saved[1], payload) :]
            self.complete = True
        except OSError:
            self.failed = True
        finally:
            os.close(self.reader)

    def __enter__(self) -> _ForwardOutput:
        sys.stdout.flush()
        sys.stderr.flush()
        self.saved = os.dup(1), os.dup(2)
        self.reader, writer = os.pipe()
        self.thread = threading.Thread(target=self._forward, daemon=True)
        self.thread.start()
        try:
            os.dup2(writer, 1)
            os.dup2(writer, 2)
        finally:
            os.close(writer)
        return self

    def __exit__(self, *exception: object) -> None:
        assert self.saved is not None and self.thread is not None
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            os.dup2(self.saved[0], 1)
            os.dup2(self.saved[1], 2)
        self.thread.join(timeout=1.0)
        if not self.thread.is_alive():
            for descriptor in self.saved:
                os.close(descriptor)


@contextmanager
def _environment(root: Path) -> Iterator[None]:
    inherited = {key: value for key, value in os.environ.items() if key.startswith("PYTEST_")}
    previous_path = sys.path.copy()
    previous_bytecode = sys.dont_write_bytecode
    previous_bytecode_environment = os.environ.get("PYTHONDONTWRITEBYTECODE")
    previous_directory = Path.cwd()
    try:
        for key in inherited:
            os.environ.pop(key, None)
        os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(root))
        os.chdir(root)
        yield
    finally:
        for key in tuple(os.environ):
            if key.startswith("PYTEST_"):
                os.environ.pop(key, None)
        os.environ.update(inherited)
        if previous_bytecode_environment is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = previous_bytecode_environment
        sys.path[:] = previous_path
        sys.dont_write_bytecode = previous_bytecode
        os.chdir(previous_directory)


def _execute(target: PytestTarget, database: Path, private: Path) -> tuple[int, str]:
    try:
        version = importlib.metadata.version("pytest")
    except importlib.metadata.PackageNotFoundError:
        return 2, "pytest-not-installed"
    if not _supported_pytest(version):
        return 2, "pytest-version-unsupported"
    with _environment(target.root), _ForwardOutput() as output:
        try:
            import pytest

            if pytest.__version__ != version:
                return 2, "pytest-version-inconsistent"

            class BoundSession(_Session):
                @pytest.hookimpl(wrapper=True, tryfirst=True)
                def pytest_fixture_setup(
                    self, fixturedef: pytest.FixtureDef[object], request: pytest.FixtureRequest
                ) -> Generator[None, object, object]:
                    super().pytest_fixture_setup(fixturedef, request)
                    result = yield
                    if fixturedef.argname == "reproseed_db" and result is not self.database:
                        self._reject("reserved-fixture-overridden")
                        raise pytest.UsageError("reproseed: reserved-fixture-overridden")
                    return result

            session = BoundSession(target, database)
            session.pytest = pytest

            def reproseed_database() -> Path:
                return database

            fixtures = ModuleType("reproseed_pytest_fixtures")
            fixtures.reproseed_db = pytest.fixture(name="reproseed_db")(reproseed_database)  # type: ignore[attr-defined]
            session.fixture_function = reproseed_database
            config = private / "pytest.ini"
            config.write_text("[pytest]\n", encoding="utf-8")
            exit_code = pytest.main(
                [
                    "-c",
                    str(config),
                    "--rootdir",
                    str(target.root),
                    "--confcutdir",
                    str(target.root),
                    "--import-mode=importlib",
                    "--basetemp",
                    str(private / "pytest-temp"),
                    "--capture=no",
                    "-p",
                    "no:terminal",
                    "-p",
                    "no:cacheprovider",
                    "-p",
                    "no:logging",
                    "-p",
                    "no:warnings",
                    "-o",
                    "addopts=",
                    "./" + target.file.relative_to(target.root).as_posix(),
                ],
                plugins=[session, fixtures],
            )
            result = session.classify(exit_code)
        except KeyboardInterrupt:
            result = 130, "interrupted"
        except Exception:
            result = 2, "pytest-execution-error"
    if not output.complete or output.failed:
        return 2, "output-forwarding-incomplete"
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise TargetError("invalid-arguments")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(description="Run one explicit pytest failure contract (pytest is optional).")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--allow-exec", action="store_true")
    try:
        args = parser.parse_args(argv)
        if not args.allow_exec:
            raise TargetError("execution-not-acknowledged")
        target = load_target(args.target)
        with tempfile.TemporaryDirectory(prefix="reproseed-pytest-") as directory:
            private = Path(directory)
            database = private / "db.sqlite3"
            snapshot(args.db, database)
            code, reason = _execute(target, database, private)
    except KeyboardInterrupt:
        code, reason = 130, "interrupted"
    except TargetError as exc:
        code, reason = 2, exc.reason
    except (DatabaseError, OSError):
        code, reason = 2, "private-database-or-workspace-failed"
    if code == TARGET_EXIT:
        print(MARKER, flush=True)
    else:
        print(f"reproseed-pytest: {reason}", file=sys.stderr, flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
