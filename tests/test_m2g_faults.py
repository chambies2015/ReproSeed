"""Actual one-session pytest probes used by disposable semantic mutations."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from reproseed.pytest_oracle import _execute, load_target
from reproseed.sqlite_adapter import snapshot


def _run(directory: Path, body: str) -> int:
    source = directory / "source.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO items VALUES(1)")
    (directory / "test_case.py").write_text(body, encoding="utf-8")
    target = directory / "target.toml"
    target.write_text(
        'adapter_version=1\nnodeid="test_case.py::test_case"\n'
        'exception="builtins.AssertionError"\nmessage="intended invariant"\n',
        encoding="utf-8",
    )
    private = directory / "private"
    private.mkdir()
    database = private / "db.sqlite3"
    snapshot(source, database)
    code, _reason = _execute(load_target(target), database, private)
    return code


def probe_pytest_message(directory: Path) -> None:
    code = _run(
        directory,
        'def test_case(reproseed_db):\n    raise AssertionError("different invariant")\n',
    )
    assert code == 2, "same exception with a different message must remain unresolved"


def probe_pytest_teardown(directory: Path) -> None:
    code = _run(
        directory,
        "import pytest\n"
        "@pytest.fixture\ndef dependent(reproseed_db):\n"
        "    yield reproseed_db\n    raise RuntimeError('finalizer failed')\n"
        "def test_case(dependent):\n    raise AssertionError('intended invariant')\n",
    )
    assert code == 2, "a matching call followed by failing teardown must remain unresolved"


def probe_pytest_skip(directory: Path) -> None:
    code = _run(
        directory,
        'import pytest\ndef test_case(reproseed_db):\n    pytest.skip("not executed")\n',
    )
    assert code == 2, "skip/no-call is unresolved, never a genuine pass"
