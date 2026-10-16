"""Fail-closed bridge regressions with real SQLite and fresh pytest subprocesses."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

import reproseed
from reproseed import pytest_oracle as bridge_module
from reproseed.cli import main
from reproseed.config import Asset, OracleSpec
from reproseed.oracle import OracleResult, Outcome, run_oracle

MARKER = "REPROSEED_PYTEST_TARGET_V1"
MESSAGE = "specific cross-project invariant"
TARGET = f"raise AssertionError({MESSAGE!r})"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


def _contract(
    root: Path,
    *,
    nodeid: str = "test_subject.py::test_target",
    exception: str = "builtins.AssertionError",
    message: str = MESSAGE,
) -> Path:
    target = root / "pytest-target.toml"
    _write(
        target,
        "adapter_version = 1\n"
        f"nodeid = {json.dumps(nodeid)}\n"
        f"exception = {json.dumps(exception)}\n"
        f"message = {json.dumps(message)}\n",
    )
    return target


def _case(tmp_path: Path, program: str, *, nodeid: str = "test_subject.py::test_target") -> Path:
    root = tmp_path / "payload"
    root.mkdir()
    with closing(sqlite3.connect(root / "source.sqlite3")) as database:
        database.executescript(
            "CREATE TABLE items(id INTEGER PRIMARY KEY); INSERT INTO items VALUES(7)"
        )
    _write(root / "test_subject.py", program)
    _contract(root, nodeid=nodeid)
    return root


def _package_bootstrap() -> str:
    """Expose only ReproSeed to -S, including when it lives beside pytest in a wheel venv."""
    package = Path(reproseed.__file__).resolve()
    return (
        "import importlib.util; "
        "reproseed_spec=importlib.util.spec_from_file_location("
        f"'reproseed', {str(package)!r}, submodule_search_locations=[{str(package.parent)!r}]); "
        "assert reproseed_spec is not None and reproseed_spec.loader is not None; "
        "reproseed_package=importlib.util.module_from_spec(reproseed_spec); "
        "sys.modules['reproseed']=reproseed_package; "
        "reproseed_spec.loader.exec_module(reproseed_package)"
    )


def _bridge(
    root: Path,
    *,
    allow: bool = True,
    env: dict[str, str] | None = None,
    bootstrap: str | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        "--target",
        str(root / "pytest-target.toml"),
        "--db",
        str(root / "source.sqlite3"),
    ]
    if allow:
        arguments.append("--allow-exec")
    command = [sys.executable, "-m", "reproseed.pytest_oracle", *arguments]
    if bootstrap is not None:
        command = [
            sys.executable,
            "-S",
            "-c",
            "import sys,runpy; "
            + _package_bootstrap()
            + "; assert importlib.util.find_spec('pytest') is None; "
            + bootstrap
            + "; runpy.run_module('reproseed.pytest_oracle', run_name='__main__')",
            *arguments,
        ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        environment.update(env)
    return subprocess.run(
        command,
        cwd=root.parent,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )


def _outcome(result: subprocess.CompletedProcess[str], expected: int) -> None:
    assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
    assert (MARKER in result.stdout.splitlines()) is (expected == 86), result.stdout
    assert MARKER not in result.stderr.splitlines(), result.stderr


def _outer(
    root: Path,
    *,
    timeout: float = 8,
    limit: int = 65536,
    expected_exit: int = 86,
    stream: str = "stdout",
) -> OracleResult:
    assert stream in {"stdout", "stderr"}
    spec = OracleSpec(
        argv=(
            "{python}",
            "-m",
            "reproseed.pytest_oracle",
            "--target",
            "pytest-target.toml",
            "--db",
            "{db}",
            "--allow-exec",
        ),
        expected_exit=expected_exit,
        marker=MARKER,
        stream=stream,  # type: ignore[arg-type]
        timeout_seconds=timeout,
        output_limit_bytes=limit,
    )
    assets = tuple(
        Asset(path.relative_to(root).as_posix(), path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "source.sqlite3"
    )
    return run_oracle(spec, root / "source.sqlite3", assets)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (TARGET, 86),
        ("assert reproseed_db.is_file()", 0),
        (f"raise ValueError({MESSAGE!r})", 2),
        ("raise AssertionError('different invariant')", 2),
        ("import pytest; pytest.skip('not executed')", 2),
        ("import pytest; pytest.xfail('known limitation')", 2),
        (f"raise ExceptionGroup('group', [AssertionError({MESSAGE!r})])", 2),
        ("raise KeyboardInterrupt()", 130),
    ],
)
def test_exact_call_contract_with_real_pytest(tmp_path: Path, body: str, expected: int) -> None:
    root = _case(tmp_path, f"def test_target(reproseed_db):\n    {body}\n")
    before = _digest(root / "source.sqlite3")
    _outcome(_bridge(root), expected)
    assert _digest(root / "source.sqlite3") == before


@pytest.mark.parametrize(
    ("phase", "call", "finalizer"),
    [
        ("setup", "pass", False),
        ("teardown", "pass", False),
        ("teardown", TARGET, False),
        ("teardown", TARGET, True),
    ],
)
def test_matching_signature_in_fixture_phases_is_unresolved(
    tmp_path: Path, phase: str, call: str, finalizer: bool
) -> None:
    fixture = "import pytest\n@pytest.fixture\ndef local_fixture(reproseed_db, request):\n"
    if phase == "setup":
        fixture += f"    {TARGET}\n    yield\n"
    elif finalizer:
        fixture += (
            f"    def finish():\n        {TARGET}\n"
            "    request.addfinalizer(finish)\n    return reproseed_db\n"
        )
    else:
        fixture += f"    yield reproseed_db\n    {TARGET}\n"
    root = _case(tmp_path, fixture + f"def test_target(local_fixture):\n    {call}\n")
    _outcome(_bridge(root), 2)


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("call", ["pass", TARGET])
def test_xfail_and_xpass_are_unresolved(tmp_path: Path, strict: bool, call: str) -> None:
    root = _case(
        tmp_path,
        f"import pytest\n@pytest.mark.xfail(strict={strict!r})\n"
        f"def test_target(reproseed_db):\n    {call}\n",
    )
    _outcome(_bridge(root), 2)


def test_only_selected_test_executes_and_fixture_dependency_is_supported(tmp_path: Path) -> None:
    root = _case(
        tmp_path,
        "import pytest\n"
        "@pytest.fixture\n"
        "def indirect(reproseed_db):\n    return reproseed_db\n"
        "def test_target(indirect):\n    assert indirect.is_file()\n"
        f"def test_other(reproseed_db):\n    {TARGET}\n",
    )
    _outcome(_bridge(root), 0)


def test_reserved_fixture_must_be_requested(tmp_path: Path) -> None:
    root = _case(tmp_path, f"def test_target():\n    {TARGET}\n")
    _outcome(_bridge(root), 2)


def test_reserved_fixture_override_is_rejected_before_test_call(tmp_path: Path) -> None:
    sentinel = tmp_path / "test-ran"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    Path({str(sentinel)!r}).touch()\n    {TARGET}\n",
    )
    _write(
        root / "conftest.py",
        "import pytest\n@pytest.fixture\ndef reproseed_db():\n    return 'ambiguous override'\n",
    )
    _outcome(_bridge(root), 2)
    assert not sentinel.exists()


@pytest.mark.parametrize("tryfirst", [False, True])
def test_fixture_hook_cannot_rebind_the_database_to_supplied_source(
    tmp_path: Path, tryfirst: bool
) -> None:
    imported = tmp_path / "fixture-conftest-imported"
    hook_ran = tmp_path / "fixture-hook-ran"
    call_ran = tmp_path / "rebound-call-ran"
    root = _case(
        tmp_path,
        "from pathlib import Path\nimport sqlite3\n"
        "def test_target(reproseed_db):\n"
        f"    Path({str(call_ran)!r}).touch()\n"
        "    with sqlite3.connect(reproseed_db) as database:\n"
        "        database.execute('DELETE FROM items')\n"
        f"    {TARGET}\n",
    )
    before = _digest(root / "source.sqlite3")
    _write(
        root / "conftest.py",
        "from pathlib import Path\nimport pytest\n"
        f"Path({str(imported)!r}).touch()\n"
        f"@pytest.hookimpl(hookwrapper=True, tryfirst={tryfirst!r})\n"
        "def pytest_fixture_setup(fixturedef, request):\n"
        "    outcome = yield\n"
        "    if fixturedef.argname == 'reproseed_db':\n"
        f"        Path({str(hook_ran)!r}).touch()\n"
        "        outcome.force_result(Path(__file__).with_name('source.sqlite3'))\n",
    )
    _outcome(_bridge(root), 2)
    assert imported.exists()
    assert not hook_ran.exists()
    assert not call_ran.exists()
    assert _digest(root / "source.sqlite3") == before


@pytest.mark.parametrize(
    "hook",
    [
        "pytest_pyfunc_call",
        "pytest_runtest_call",
        "pytest_runtest_protocol",
        "pytest_runtestloop",
        "pytest_runtest_makereport",
    ],
)
def test_execution_interception_hooks_cannot_substitute_a_target_failure(
    tmp_path: Path, hook: str
) -> None:
    imported = tmp_path / "intercepting-conftest-imported"
    hook_ran = tmp_path / "intercepting-hook-ran"
    call_ran = tmp_path / "actual-test-call-ran"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    Path({str(call_ran)!r}).touch()\n",
    )
    _write(
        root / "conftest.py",
        "from pathlib import Path\n"
        f"Path({str(imported)!r}).touch()\n"
        f"def {hook}():\n    Path({str(hook_ran)!r}).touch()\n    {TARGET}\n",
    )
    _outcome(_bridge(root), 2)
    assert imported.exists()
    assert not hook_ran.exists()
    assert not call_ran.exists()


def test_execution_hook_alias_is_rejected_by_its_registered_hook_name(tmp_path: Path) -> None:
    imported = tmp_path / "aliased-conftest-imported"
    hook_ran = tmp_path / "aliased-hook-ran"
    call_ran = tmp_path / "aliased-test-call-ran"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    Path({str(call_ran)!r}).touch()\n",
    )
    _write(
        root / "conftest.py",
        "from pathlib import Path\nimport pytest\n"
        f"Path({str(imported)!r}).touch()\n"
        "@pytest.hookimpl(specname='pytest_fixture_setup')\n"
        f"def pytest_alias():\n    Path({str(hook_ran)!r}).touch()\n    {TARGET}\n",
    )
    result = _bridge(root)
    _outcome(result, 2)
    assert "execution-hook-unsupported" in result.stderr
    assert imported.exists()
    assert not hook_ran.exists()
    assert not call_ran.exists()


@pytest.mark.parametrize(
    "capture", ["capsys", "capfd", "capsysbinary", "capfdbinary", "capteesys", "caplog", "recwarn"]
)
def test_buffering_capture_fixtures_are_rejected_before_setup(tmp_path: Path, capture: str) -> None:
    setup_ran = tmp_path / "capture-test-setup-ran"
    call_ran = tmp_path / "capture-test-call-ran"
    root = _case(
        tmp_path,
        "from pathlib import Path\nimport pytest\n"
        "@pytest.fixture(autouse=True)\n"
        f"def setup_probe():\n    Path({str(setup_ran)!r}).touch()\n"
        f"def test_target(reproseed_db, {capture}):\n"
        f"    Path({str(call_ran)!r}).touch()\n"
        f"    print('finite captured output' * 8192)\n    {TARGET}\n",
    )
    result = _bridge(root)
    _outcome(result, 2)
    assert "capture-fixture-unsupported" in result.stderr
    assert not setup_ran.exists()
    assert not call_ran.exists()


def test_buffering_fixture_through_local_dependency_is_rejected_before_setup(
    tmp_path: Path,
) -> None:
    setup_ran = tmp_path / "indirect-capture-setup-ran"
    call_ran = tmp_path / "indirect-capture-call-ran"
    root = _case(
        tmp_path,
        "from pathlib import Path\nimport pytest\n"
        "@pytest.fixture\n"
        "def local_capture(capfd):\n"
        f"    Path({str(setup_ran)!r}).touch()\n    return capfd\n"
        "def test_target(reproseed_db, local_capture):\n"
        f"    Path({str(call_ran)!r}).touch()\n    {TARGET}\n",
    )
    result = _bridge(root)
    _outcome(result, 2)
    assert "capture-fixture-unsupported" in result.stderr
    assert not setup_ran.exists()
    assert not call_ran.exists()


def test_dynamic_capture_request_is_rejected_before_buffering_starts(tmp_path: Path) -> None:
    before_request = tmp_path / "dynamic-capture-request-reached"
    after_request = tmp_path / "dynamic-capture-enabled"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        "def test_target(reproseed_db, request):\n"
        f"    Path({str(before_request)!r}).touch()\n"
        "    request.getfixturevalue('capfd')\n"
        f"    Path({str(after_request)!r}).touch()\n"
        f"    print('finite captured output' * 8192)\n    {TARGET}\n",
    )
    result = _bridge(root)
    _outcome(result, 2)
    assert "capture-fixture-unsupported" in result.stderr
    assert before_request.exists()
    assert not after_request.exists()


@pytest.mark.parametrize("custom", ["collector", "module", "rerun", "async"])
def test_unsupported_test_integrations_do_not_execute_call(tmp_path: Path, custom: str) -> None:
    sentinel = tmp_path / "unsupported-call-ran"
    program = (
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    Path({str(sentinel)!r}).touch()\n    {TARGET}\n"
    )
    if custom == "rerun":
        program = "import pytest\n@pytest.mark.flaky(reruns=2)\n" + program.replace(
            "from pathlib import Path\n", ""
        )
        program = "from pathlib import Path\n" + program
    elif custom == "async":
        program = program.replace("def test_target", "async def test_target")
    root = _case(tmp_path, program)
    if custom == "collector":
        _write(
            root / "conftest.py",
            "import pytest\n"
            "class CustomFunction(pytest.Function):\n    pass\n"
            "def pytest_pycollect_makeitem(collector, name, obj):\n"
            "    if name == 'test_target':\n"
            "        return CustomFunction.from_parent(collector, name=name)\n",
        )
    elif custom == "module":
        _write(
            root / "conftest.py",
            "import pytest\n"
            "class CustomModule(pytest.Module):\n    pass\n"
            "def pytest_pycollect_makemodule(module_path, parent):\n"
            "    return CustomModule.from_parent(parent, path=module_path)\n",
        )
    _outcome(_bridge(root), 2)
    assert not sentinel.exists()


@pytest.mark.parametrize(
    "program",
    [
        "def test_target(:\n    pass\n",
        "raise ImportError('PRIVATE_IMPORT_SECRET')\n",
        "import definitely_absent_reproseed_test_module\n",
    ],
)
def test_collection_failures_are_curated(tmp_path: Path, program: str) -> None:
    root = _case(tmp_path, program)
    result = _bridge(root)
    _outcome(result, 2)
    assert "PRIVATE_IMPORT_SECRET" not in result.stdout + result.stderr
    assert str(root) not in result.stdout + result.stderr


def test_conftest_syntax_errors_are_curated(tmp_path: Path) -> None:
    root = _case(tmp_path, f"def test_target(reproseed_db):\n    {TARGET}\n")
    _write(root / "conftest.py", "def PRIVATE_CONFTEST_SECRET(:\n    pass\n")
    result = _bridge(root)
    _outcome(result, 2)
    assert "PRIVATE_CONFTEST_SECRET" not in result.stdout + result.stderr
    assert str(root) not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "nodeid",
    ["test_subject.py::test_missing", "test_subject.py", "test_subject.py::TestMany"],
)
def test_missing_or_multi_item_selectors_do_not_run_setup(tmp_path: Path, nodeid: str) -> None:
    sentinel = tmp_path / "setup-ran"
    root = _case(
        tmp_path,
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.fixture(autouse=True)\n"
        f"def setup():\n    Path({str(sentinel)!r}).touch()\n"
        "def test_one(reproseed_db):\n    pass\n"
        "class TestMany:\n"
        "    def test_one(self, reproseed_db):\n        pass\n"
        "    def test_two(self, reproseed_db):\n        pass\n",
        nodeid=nodeid,
    )
    _outcome(_bridge(root), 2)
    assert not sentinel.exists()


@pytest.mark.parametrize("change", ["prepend-other", "append-other", "duplicate-target"])
def test_late_selection_changes_are_rejected_before_any_setup(tmp_path: Path, change: str) -> None:
    collection_ran = tmp_path / "late-collection-hook-ran"
    setup_ran = tmp_path / "late-selection-setup-ran"
    other_ran = tmp_path / "unexpected-other-ran"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    {TARGET}\n"
        f"def test_other(reproseed_db):\n    Path({str(other_ran)!r}).touch()\n",
    )
    modification = {
        "prepend-other": "items.insert(0, other)",
        "append-other": "items.append(other)",
        "duplicate-target": "items.append(items[0])",
    }[change]
    _write(
        root / "conftest.py",
        "import pytest\nfrom pathlib import Path\ncollected = []\n"
        "def pytest_itemcollected(item):\n    collected.append(item)\n"
        "@pytest.hookimpl(trylast=True)\n"
        "def pytest_collection_modifyitems(items):\n"
        "    other = next(item for item in collected if item.name == 'test_other')\n"
        f"    {modification}\n    Path({str(collection_ran)!r}).touch()\n"
        "@pytest.fixture(autouse=True)\n"
        f"def setup_probe():\n    Path({str(setup_ran)!r}).touch()\n",
    )
    _outcome(_bridge(root), 2)
    assert collection_ran.exists()
    assert not setup_ran.exists()
    assert not other_ran.exists()


@pytest.mark.parametrize(
    ("selector", "expected"),
    [("[chosen]", 86), ("[other]", 0), ("", 2), ("[missing]", 2)],
)
def test_exact_parametrized_case_is_required(tmp_path: Path, selector: str, expected: int) -> None:
    root = _case(
        tmp_path,
        "import pytest\n@pytest.mark.parametrize('value', [1, 2], ids=['chosen', 'other'])\n"
        f"def test_target(reproseed_db, value):\n    if value == 1:\n        {TARGET}\n",
        nodeid="test_subject.py::test_target" + selector,
    )
    _outcome(_bridge(root), expected)


def test_spaces_unicode_and_quoted_parameter_id(tmp_path: Path) -> None:
    root = _case(tmp_path, "")
    name = "safe tests/test 雪.py"
    parameter = 'a "quoted" id'
    _write(
        root / name,
        "import pytest\n"
        f"@pytest.mark.parametrize('value', [1], ids=[{parameter!r}])\n"
        f"def test_target(reproseed_db, value):\n    {TARGET}\n",
    )
    _contract(root, nodeid=f"{name}::test_target[{parameter}]")
    _outcome(_bridge(root), 86)


@pytest.mark.parametrize("filename", ["@test_subject.py", "-ptest_subject.py"])
def test_safe_leading_argument_characters_are_literal_file_paths(
    tmp_path: Path, filename: str
) -> None:
    called = tmp_path / "literal-file-test-called"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    Path({str(called)!r}).touch()\n    {TARGET}\n",
    )
    (root / "test_subject.py").rename(root / filename)
    _contract(root, nodeid=f"{filename}::test_target")
    _outcome(_bridge(root), 86)
    assert called.exists()


def test_methods_are_supported(tmp_path: Path) -> None:
    root = _case(
        tmp_path,
        f"class TestExport:\n    def test_target(self, reproseed_db):\n        {TARGET}\n",
        nodeid="test_subject.py::TestExport::test_target",
    )
    _outcome(_bridge(root), 86)


@pytest.mark.parametrize("exact_type", [False, True])
def test_exception_type_is_exact_module_and_qualname(tmp_path: Path, exact_type: bool) -> None:
    root = _case(
        tmp_path,
        "class Failures:\n    class Specific(AssertionError):\n        pass\n"
        f"def test_target(reproseed_db):\n    raise Failures.Specific({MESSAGE!r})\n",
    )
    if exact_type:
        _contract(root, exception="test_subject.Failures.Specific")
    _outcome(_bridge(root), 86 if exact_type else 2)


def test_configured_exception_class_is_never_imported_to_validate_its_name(tmp_path: Path) -> None:
    imported = tmp_path / "exception-module-imported"
    root = _case(tmp_path, f"def test_target(reproseed_db):\n    {TARGET}\n")
    _write(
        root / "private_exception_module.py",
        "from pathlib import Path\n"
        f"Path({str(imported)!r}).touch()\n"
        "class Specific(Exception):\n    pass\n",
    )
    _contract(root, exception="private_exception_module.Specific")
    _outcome(_bridge(root), 2)
    assert not imported.exists()


def test_unacknowledged_execution_does_not_import_test_or_conftest(tmp_path: Path) -> None:
    sentinel = tmp_path / "import-ran"
    program = f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n"
    root = _case(tmp_path, program + "def test_target(reproseed_db):\n    pass\n")
    _write(root / "conftest.py", program)
    _outcome(_bridge(root, allow=False), 2)
    assert not sentinel.exists()


@pytest.mark.parametrize("version", [None, "7.4.4", "10.0.0", "invalid"])
def test_missing_or_unsupported_pytest_precedes_payload_import(
    tmp_path: Path, version: str | None
) -> None:
    sentinel = tmp_path / "import-ran"
    program = f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n"
    root = _case(tmp_path, program + "def test_target(reproseed_db):\n    pass\n")
    _write(root / "conftest.py", program)
    bootstrap = "pass"
    if version is not None:
        dependency = tmp_path / "unsupported-dependency"
        _write(
            dependency / "pytest-0.dist-info" / "METADATA",
            f"Metadata-Version: 2.1\nName: pytest\nVersion: {version}\n",
        )
        _write(
            dependency / "pytest.py",
            f"__version__ = {version!r}\n"
            "def main(*args, **kwargs):\n    raise AssertionError('unsupported pytest executed')\n",
        )
        bootstrap = f"sys.path.insert(0, {str(dependency)!r})"
    result = _bridge(root, bootstrap=bootstrap)
    _outcome(result, 2)
    assert ("pytest-not-installed" if version is None else "pytest-version-unsupported") in (
        result.stdout + result.stderr
    )
    assert not sentinel.exists()
    assert "Traceback" not in result.stdout + result.stderr
    assert str(root) not in result.stdout + result.stderr


def test_pytest_metadata_without_version_is_rejected_before_payload_import(tmp_path: Path) -> None:
    test_imported = tmp_path / "missing-version-test-imported"
    conftest_imported = tmp_path / "missing-version-conftest-imported"
    dependency_imported = tmp_path / "missing-version-pytest-imported"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"Path({str(test_imported)!r}).touch()\n"
        "def test_target(reproseed_db):\n    pass\n",
    )
    _write(
        root / "conftest.py",
        f"from pathlib import Path\nPath({str(conftest_imported)!r}).touch()\n",
    )
    dependency = tmp_path / "missing-version-dependency"
    _write(
        dependency / "pytest-unknown.dist-info" / "METADATA",
        "Metadata-Version: 2.1\nName: pytest\n",
    )
    _write(
        dependency / "pytest.py",
        f"from pathlib import Path\nPath({str(dependency_imported)!r}).touch()\n",
    )
    result = _bridge(
        root,
        bootstrap=f"sys.path.insert(0, {str(dependency)!r}); import importlib.metadata; "
        "assert importlib.metadata.version('pytest') is None",
    )
    _outcome(result, 2)
    assert "pytest-version-unsupported" in result.stderr
    assert not test_imported.exists()
    assert not conftest_imported.exists()
    assert not dependency_imported.exists()
    assert "Traceback" not in result.stdout + result.stderr
    assert str(root) not in result.stdout + result.stderr
    assert str(dependency) not in result.stdout + result.stderr


def test_help_without_site_packages_does_not_import_pytest(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "import sys,runpy; "
            + _package_bootstrap()
            + "; assert importlib.util.find_spec('pytest') is None; "
            "runpy.run_module('reproseed.pytest_oracle', run_name='__main__')",
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--allow-exec" in result.stdout


def test_inherited_plugin_and_argument_injection_is_disabled(tmp_path: Path) -> None:
    sentinel = tmp_path / "injected-plugin-ran"
    injection = tmp_path / "injection"
    _write(
        injection / "injected_plugin.py",
        f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
    )
    _write(
        injection / "reproseed_injection-1.0.dist-info" / "METADATA",
        "Metadata-Version: 2.1\nName: reproseed-injection\nVersion: 1.0\n",
    )
    _write(
        injection / "reproseed_injection-1.0.dist-info" / "entry_points.txt",
        "[pytest11]\nreproseed_injection = injected_plugin\n",
    )
    root = _case(
        tmp_path,
        "import os\ndef test_target(reproseed_db):\n"
        "    assert os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'\n"
        f"    {TARGET}\n",
    )
    env = {
        "PYTEST_ADDOPTS": "--definitely-invalid-option -p injected_plugin",
        "PYTEST_PLUGINS": "injected_plugin",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "0",
        "PYTHONPATH": os.pathsep.join([str(injection), os.environ.get("PYTHONPATH", "")]),
    }
    _outcome(_bridge(root, env=env), 86)
    assert not sentinel.exists()


def test_ancestor_configuration_is_excluded_and_local_conftest_works(tmp_path: Path) -> None:
    ancestor = tmp_path / "ancestor-loaded"
    _write(tmp_path / "pytest.ini", "[pytest]\naddopts = --invalid-parent-option\n")
    _write(
        tmp_path / "conftest.py",
        f"from pathlib import Path\nPath({str(ancestor)!r}).touch()\n"
        "raise AssertionError('ancestor conftest must not import')\n",
    )
    root = _case(
        tmp_path,
        "def test_target(reproseed_db, included_fixture):\n"
        f"    assert included_fixture == 'local'\n    {TARGET}\n",
    )
    _write(
        root / "conftest.py",
        "import pytest\n@pytest.fixture\ndef included_fixture():\n    return 'local'\n",
    )
    _outcome(_bridge(root), 86)
    assert not ancestor.exists()
    assert not list(root.rglob("__pycache__"))
    assert not list(root.rglob(".pytest_cache"))


def test_direct_bridge_disables_bytecode_for_ordinary_python_children(tmp_path: Path) -> None:
    root = _case(
        tmp_path,
        "import subprocess, sys\n"
        "def test_target(reproseed_db):\n"
        "    subprocess.run([sys.executable, '-c', "
        "\"import app; assert app.VALUE == 'pristine'\"], check=True)\n"
        f"    {TARGET}\n",
    )
    _write(root / "app.py", "VALUE = 'pristine'\n")
    before = {path.name: _digest(path) for path in root.iterdir() if path.is_file()}
    assert len(before) == 4
    environment = os.environ.copy()
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "reproseed.pytest_oracle",
            "--target",
            str(root / "pytest-target.toml"),
            "--db",
            str(root / "source.sqlite3"),
            "--allow-exec",
        ],
        cwd=root.parent,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    _outcome(result, 86)
    assert not list(root.rglob("__pycache__"))
    assert not list(root.rglob("*.pyc"))
    assert {path.name: _digest(path) for path in root.iterdir() if path.is_file()} == before


def test_environment_restores_an_originally_missing_bytecode_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    original_bytecode = sys.dont_write_bytecode
    with bridge_module._environment(tmp_path):
        assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"
        assert sys.dont_write_bytecode is True
    assert "PYTHONDONTWRITEBYTECODE" not in os.environ
    assert sys.dont_write_bytecode is original_bytecode


def test_conftest_external_plugin_declaration_is_rejected_before_plugin_import(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "external-plugin-imported"
    root = _case(tmp_path, f"def test_target(reproseed_db):\n    {TARGET}\n")
    _write(root / "conftest.py", "pytest_plugins = ['external_fixture_plugin']\n")
    _write(
        root / "external_fixture_plugin.py",
        f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
    )
    _outcome(_bridge(root), 2)
    assert not sentinel.exists()


def test_linked_conftest_is_rejected_before_import(tmp_path: Path) -> None:
    root = _case(tmp_path, f"def test_target(reproseed_db):\n    {TARGET}\n")
    sentinel = tmp_path / "linked-conftest-imported"
    outside = tmp_path / "outside-conftest.py"
    _write(outside, f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
    try:
        (root / "conftest.py").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"test-owned symbolic links unavailable: {error}")
    _outcome(_bridge(root), 2)
    assert not sentinel.exists()


@pytest.mark.parametrize("call", ["pass", "raise ValueError('unrelated')"])
def test_fake_marker_from_test_cannot_be_the_bridge_protocol(tmp_path: Path, call: str) -> None:
    root = _case(
        tmp_path,
        f"def test_target(reproseed_db):\n    print({MARKER!r})\n    {call}\n",
    )
    _outcome(_bridge(root), 0 if call == "pass" else 2)
    result = _outer(root)
    assert result.outcome is (Outcome.PASS if call == "pass" else Outcome.UNRESOLVED)


def test_outer_contract_still_requires_expected_exit_and_marker_stream(tmp_path: Path) -> None:
    root = _case(tmp_path, f"def test_target(reproseed_db):\n    {TARGET}\n")
    assert _outer(root).outcome is Outcome.TARGET_FAILURE
    wrong_exit = _outer(root, expected_exit=85)
    assert wrong_exit.outcome is Outcome.UNRESOLVED
    assert wrong_exit.exit_code == 86
    wrong_stream = _outer(root, stream="stderr")
    assert wrong_stream.outcome is Outcome.UNRESOLVED
    assert wrong_stream.exit_code == 86


def test_supplied_database_is_not_mutated_by_direct_bridge(tmp_path: Path) -> None:
    root = _case(
        tmp_path,
        "import sqlite3\nfrom contextlib import closing\n"
        "def test_target(reproseed_db):\n"
        "    with closing(sqlite3.connect(reproseed_db)) as database:\n"
        "        assert database.execute('SELECT id FROM items').fetchall() == [(7,)]\n"
        "        database.execute('DELETE FROM items')\n        database.commit()\n"
        f"    {TARGET}\n",
    )
    before = _digest(root / "source.sqlite3")
    for _ in range(2):
        _outcome(_bridge(root), 86)
        assert _digest(root / "source.sqlite3") == before


def test_outer_fresh_confirmations_discard_database_and_asset_mutation(tmp_path: Path) -> None:
    root = _case(
        tmp_path,
        "import sqlite3\nfrom contextlib import closing\nfrom pathlib import Path\n"
        "def test_target(reproseed_db):\n"
        "    asset = Path(__file__).with_name('support.txt')\n"
        "    assert asset.read_text() == 'pristine-support'\n"
        "    with closing(sqlite3.connect(reproseed_db)) as database:\n"
        "        assert database.execute('SELECT id FROM items').fetchall() == [(7,)]\n"
        "        database.execute('DELETE FROM items')\n        database.commit()\n"
        "    asset.write_text('mutated')\n"
        f"    {TARGET}\n",
    )
    _write(root / "support.txt", "pristine-support")
    before = {path.name: _digest(path) for path in root.iterdir()}
    for _ in range(3):
        result = _outer(root)
        assert result.outcome is Outcome.TARGET_FAILURE, result
    assert {path.name: _digest(path) for path in root.iterdir()} == before


@pytest.mark.parametrize("kind", ["timeout", "output"])
def test_outer_execution_bounds_reach_actual_test(tmp_path: Path, kind: str) -> None:
    ready = tmp_path / "test-entered"
    body = "import time\n    while True:\n        time.sleep(0.01)"
    if kind == "output":
        body = "import sys; sys.stdout.write('noisy-output' * 100000); sys.stdout.flush()"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    Path({str(ready)!r}).touch()\n    {body}\n",
    )
    result = _outer(root, timeout=3, limit=4096)
    assert ready.exists(), result
    assert result.outcome is Outcome.UNRESOLVED
    assert result.reason == (
        "deadline exceeded (process or open output pipes)"
        if kind == "timeout"
        else "combined output limit exceeded"
    )
    assert result.duration_seconds < 8


def test_warning_flood_reaches_outer_output_limit(tmp_path: Path) -> None:
    ready = tmp_path / "warning-flood-entered"
    root = _case(
        tmp_path,
        "from pathlib import Path\nimport warnings\n"
        "def test_target(reproseed_db):\n"
        f"    Path({str(ready)!r}).touch()\n"
        "    warnings.simplefilter('always')\n"
        "    for _ in range(1000):\n"
        "        warnings.warn('finite warning ' + 'x' * 2048, UserWarning)\n"
        f"    {TARGET}\n",
    )
    result = _outer(root, limit=4096)
    assert ready.exists(), result
    assert result.outcome is Outcome.UNRESOLVED
    assert result.reason == "combined output limit exceeded"


def test_single_warning_within_output_limit_can_confirm_target(tmp_path: Path) -> None:
    root = _case(
        tmp_path,
        "import warnings\n"
        "def test_target(reproseed_db):\n"
        "    warnings.simplefilter('always')\n"
        "    warnings.warn('one finite warning', UserWarning)\n"
        f"    {TARGET}\n",
    )
    result = _outer(root, limit=65536)
    assert result.outcome is Outcome.TARGET_FAILURE, result
    assert len(MARKER) < result.output_bytes < 65536


@pytest.mark.parametrize(
    "nodeid",
    [
        "../outside.py::test_target",
        "/absolute.py::test_target",
        "nested/../test_subject.py::test_target",
        "test_subject.py::*",
        "test_subject.py::test_target\x00",
        "C:/absolute.py::test_target",
    ],
)
def test_unsafe_selectors_do_not_import_payload(tmp_path: Path, nodeid: str) -> None:
    sentinel = tmp_path / "import-ran"
    root = _case(
        tmp_path,
        f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
        nodeid=nodeid,
    )
    _outcome(_bridge(root), 2)
    assert not sentinel.exists()


@pytest.mark.parametrize(
    "change",
    [
        'adapter_version = 2\nnodeid="test_subject.py::test_target"\n'
        'exception="builtins.AssertionError"\nmessage="specific"\n',
        'adapter_version = true\nnodeid="test_subject.py::test_target"\n'
        'exception="builtins.AssertionError"\nmessage="specific"\n',
        'adapter_version = 1\nnodeid="test_subject.py::test_target"\n'
        'exception="builtins.AssertionError"\nmessage=""\n',
        'adapter_version = 1\nnodeid="test_subject.py::test_target"\n'
        'exception="AssertionError"\nmessage="specific"\n',
        'adapter_version = 1\nnodeid="test_subject.py::test_target"\n'
        'exception="builtins.AssertionError"\nmessage="specific"\nunknown=true\n',
        'adapter_version = 1\nnodeid="test_subject.py::test_target"\n',
        "adapter_version = 1\nadapter_version = 1\n",
        "# oversized\n" + " " * (1024 * 1024 + 1),
    ],
    ids=[
        "version",
        "boolean-version",
        "empty-message",
        "unqualified-type",
        "unknown-field",
        "missing-field",
        "duplicate-field",
        "oversized",
    ],
)
def test_invalid_target_contract_is_bounded_and_curated(tmp_path: Path, change: str) -> None:
    sentinel = tmp_path / "import-ran"
    root = _case(
        tmp_path,
        f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
    )
    _write(root / "pytest-target.toml", change)
    result = _bridge(root)
    _outcome(result, 2)
    assert not sentinel.exists()
    assert "Traceback" not in result.stdout + result.stderr
    assert str(root) not in result.stdout + result.stderr


def test_test_file_symlink_is_rejected_before_import(tmp_path: Path) -> None:
    sentinel = tmp_path / "import-ran"
    root = _case(tmp_path, "")
    outside = tmp_path / "outside.py"
    _write(outside, f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n")
    (root / "test_subject.py").unlink()
    try:
        (root / "test_subject.py").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"test-owned symbolic links unavailable: {error}")
    _outcome(_bridge(root), 2)
    assert not sentinel.exists()


def test_target_file_symlink_is_rejected(tmp_path: Path) -> None:
    root = _case(tmp_path, f"def test_target(reproseed_db):\n    {TARGET}\n")
    target = root / "pytest-target.toml"
    outside = tmp_path / "outside-target.toml"
    target.replace(outside)
    try:
        target.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"test-owned symbolic links unavailable: {error}")
    _outcome(_bridge(root), 2)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction protection")
def test_test_directory_junction_is_rejected_before_import(tmp_path: Path) -> None:
    root = _case(tmp_path, "")
    outside = tmp_path / "outside-tests"
    outside.mkdir()
    sentinel = tmp_path / "junction-import-ran"
    _write(
        outside / "test_outside.py",
        f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
    )
    junction = root / "linked-tests"
    creation = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if creation.returncode:
        pytest.skip("test-owned junction creation unavailable")
    try:
        assert junction.is_junction()
        _contract(root, nodeid="linked-tests/test_outside.py::test_target")
        _outcome(_bridge(root), 2)
        assert not sentinel.exists()
    finally:
        junction.rmdir()


def test_expected_signature_and_private_paths_are_not_reported(tmp_path: Path) -> None:
    secret = "PRIVATE_SIGNATURE_SECRET_104729"
    root = _case(
        tmp_path,
        f"def test_target(reproseed_db):\n    raise AssertionError({secret!r})\n",
    )
    _contract(root, message=secret)
    result = _bridge(root)
    _outcome(result, 86)
    assert secret not in result.stdout + result.stderr
    assert str(root) not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr


def test_static_commands_without_pytest_and_public_output_excludes_test_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = tmp_path / "test-imported"
    secret = "PRIVATE_TEST_STDOUT_104729"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).touch()\n"
        f"def test_target(reproseed_db):\n    print({secret!r})\n    {TARGET}\n",
    )
    config = root / "reproseed.toml"
    _write(
        config,
        'version=1\nsource="source.sqlite3"\ninclude=["test_subject.py","pytest-target.toml"]\n'
        '[oracle]\nargv=["{python}","-m","reproseed.pytest_oracle","--target",'
        '"pytest-target.toml","--db","{db}","--allow-exec"]\nexpected_exit=86\n'
        f'marker="{MARKER}"\nstream="stdout"\ntimeout_seconds=8\noutput_limit_bytes=65536\n'
        "[reduction]\nmax_invocations=6\n",
    )

    def without_pytest(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-S",
                "-c",
                "import sys,runpy,importlib.util; "
                + _package_bootstrap()
                + "; assert importlib.util.find_spec('pytest') is None; "
                "runpy.run_module('reproseed', run_name='__main__')",
                *arguments,
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )

    static = without_pytest("diagnose", "--config", str(config), "--format", "json")
    assert static.returncode == 0, static.stderr
    document = json.loads(static.stdout)
    assert document["structurally_suitable"] is True
    assert document["oracle_executed"] is False
    assert not sentinel.exists()
    bundle = tmp_path / "bundle"
    events = tmp_path / "events.jsonl"
    assert (
        main(
            [
                "reduce",
                "--config",
                str(config),
                "--out",
                str(bundle),
                "--allow-exec",
                "--progress",
                "--events",
                str(events),
            ]
        )
        == 0
    )
    public = capsys.readouterr()
    assert secret not in public.out + public.err + events.read_text(encoding="utf-8")
    assert sentinel.exists()
    sentinel.unlink()
    before = {
        path.relative_to(bundle): _digest(path) for path in bundle.rglob("*") if path.is_file()
    }
    for format_name in ("json", "text"):
        inspected = without_pytest("inspect", str(bundle), "--format", format_name)
        assert inspected.returncode == 0, inspected.stderr
        assert secret not in inspected.stdout + inspected.stderr
        assert not sentinel.exists()
    assert {
        path.relative_to(bundle): _digest(path) for path in bundle.rglob("*") if path.is_file()
    } == before


def test_conftest_session_failure_is_not_target(tmp_path: Path) -> None:
    root = _case(tmp_path, f"def test_target(reproseed_db):\n    {TARGET}\n")
    _write(
        root / "conftest.py",
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    raise RuntimeError('PRIVATE_SESSION_SECRET')\n",
    )
    result = _bridge(root)
    _outcome(result, 2)
    assert "PRIVATE_SESSION_SECRET" not in result.stdout + result.stderr
    assert str(root) not in result.stdout + result.stderr


def test_pytest_internal_error_is_curated_and_never_runs_test(tmp_path: Path) -> None:
    call_ran = tmp_path / "call-after-internal-error"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    Path({str(call_ran)!r}).touch()\n    {TARGET}\n",
    )
    _write(
        root / "conftest.py",
        "def pytest_collection_modifyitems(items):\n"
        "    raise RuntimeError('PRIVATE_INTERNAL_ERROR_SECRET')\n",
    )
    result = _bridge(root)
    _outcome(result, 2)
    assert not call_ran.exists()
    assert "PRIVATE_INTERNAL_ERROR_SECRET" not in result.stdout + result.stderr
    assert str(root) not in result.stdout + result.stderr


def test_unexpected_session_failure_count_rejects_completed_target(tmp_path: Path) -> None:
    sentinel = tmp_path / "target-call-ran"
    root = _case(
        tmp_path,
        "from pathlib import Path\n"
        f"def test_target(reproseed_db):\n    Path({str(sentinel)!r}).touch()\n    {TARGET}\n",
    )
    _write(
        root / "conftest.py",
        "def pytest_sessionfinish(session):\n    session.testsfailed += 1\n",
    )
    _outcome(_bridge(root), 2)
    assert sentinel.exists()


def _complete_session(tmp_path: Path) -> bridge_module._Session:
    """A valid structured control used to isolate deliberately impossible states."""
    target = bridge_module.PytestTarget(
        root=tmp_path,
        file=tmp_path / "test_subject.py",
        nodeid="test_subject.py::test_target",
        exception="builtins.AssertionError",
        message=MESSAGE,
    )
    session = bridge_module._Session(target, tmp_path / "db.sqlite3")
    session.pytest = pytest
    session.collected = session.starts = session.finishes = 1
    session.session_starts = session.session_finishes = session.fixture_setups = 1
    session.session_exit = 1
    session.session = SimpleNamespace(  # type: ignore[assignment]
        testscollected=1, testsfailed=1, shouldfail=False, shouldstop=False
    )
    session.calls = {
        "setup": ("passed", None, None),
        "call": ("failed", "builtins.AssertionError", MESSAGE),
        "teardown": ("passed", None, None),
    }
    session.reports = {"setup": "passed", "call": "failed", "teardown": "passed"}
    assert session.classify(1) == (86, "target")
    return session


@pytest.mark.parametrize("exit_code", [None, True, "1", 0, 2, 3, 4, 5, 6, 86, -1])
def test_unexpected_or_inconsistent_public_exit_is_unresolved(
    tmp_path: Path, exit_code: object
) -> None:
    session = _complete_session(tmp_path)
    assert session.classify(exit_code)[0] == 2


@pytest.mark.parametrize(
    "field",
    [
        "collected",
        "starts",
        "finishes",
        "session_starts",
        "session_finishes",
        "fixture_setups",
    ],
)
@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_duplicate_execution_evidence_is_unresolved(
    tmp_path: Path, field: str, count: int
) -> None:
    session = _complete_session(tmp_path)
    setattr(session, field, count)
    assert session.classify(1)[0] == 2


@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
@pytest.mark.parametrize("missing", ["calls", "reports"])
def test_missing_phase_evidence_is_unresolved(tmp_path: Path, phase: str, missing: str) -> None:
    session = _complete_session(tmp_path)
    getattr(session, missing).pop(phase)
    assert session.classify(1)[0] == 2


@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
def test_contradictory_phase_report_is_unresolved(tmp_path: Path, phase: str) -> None:
    session = _complete_session(tmp_path)
    session.reports[phase] = "failed" if phase != "call" else "passed"
    assert session.classify(1)[0] == 2


@pytest.mark.parametrize("phase", ["setup", "call", "teardown", "unexpected"])
def test_duplicate_or_unknown_hook_reports_are_rejected(tmp_path: Path, phase: str) -> None:
    session = _complete_session(tmp_path)
    report = SimpleNamespace(nodeid=session.target.nodeid, when=phase, outcome="passed")
    session.pytest_runtest_logreport(report)  # type: ignore[arg-type]
    assert session.classify(1)[0] == 2


@pytest.mark.parametrize("phase", ["setup", "call", "teardown", "unexpected"])
def test_duplicate_or_unknown_call_hooks_are_rejected(tmp_path: Path, phase: str) -> None:
    session = _complete_session(tmp_path)
    item = SimpleNamespace(nodeid=session.target.nodeid)
    call = SimpleNamespace(when=phase, excinfo=None)
    session.pytest_runtest_makereport(item, call)  # type: ignore[arg-type]
    assert session.classify(1)[0] == 2


@pytest.mark.parametrize("hook", ["pytest_internalerror", "pytest_keyboard_interrupt"])
def test_internal_and_interrupt_hooks_are_fail_closed(tmp_path: Path, hook: str) -> None:
    session = _complete_session(tmp_path)
    getattr(session, hook)()
    assert session.classify(1)[0] == (130 if hook == "pytest_keyboard_interrupt" else 2)


def test_no_call_skip_with_exit_zero_is_not_pass(tmp_path: Path) -> None:
    session = _complete_session(tmp_path)
    session.calls.pop("call")
    session.reports.pop("call")
    session.session_exit = 0
    assert session.session is not None
    session.session.testsfailed = 0
    assert session.classify(0)[0] == 2


def test_genuine_pass_requires_successful_teardown_and_consistent_exit(tmp_path: Path) -> None:
    session = _complete_session(tmp_path)
    session.calls["call"] = ("passed", None, None)
    session.reports["call"] = "passed"
    session.session_exit = 0
    assert session.session is not None
    session.session.testsfailed = 0
    assert session.classify(0) == (0, "passed")
    session.calls["teardown"] = ("failed", "builtins.AssertionError", MESSAGE)
    session.reports["teardown"] = "failed"
    session.session_exit = 1
    session.session.testsfailed = 1
    assert session.classify(1)[0] == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [("testscollected", 2), ("testsfailed", 2), ("shouldfail", True), ("shouldstop", True)],
)
def test_final_session_public_state_must_be_consistent(
    tmp_path: Path, field: str, value: object
) -> None:
    session = _complete_session(tmp_path)
    assert session.session is not None
    setattr(session.session, field, value)
    assert session.classify(1)[0] == 2
