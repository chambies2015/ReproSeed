"""Counterfactual fixes and unrelated defects do not satisfy the example oracles."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
EXAMPLES = (
    ("reservation_overbook", 44, "REPROSEED_RESERVATION_OVERBOOK"),
    ("approval_cycle", 45, "REPROSEED_APPROVAL_CYCLE"),
)


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=15, check=False)


def _prepare(example: str, directory: Path) -> Path:
    directory.mkdir()
    for name in ("app.py", "oracle.py", "generate.py"):
        shutil.copy2(REPOSITORY / "examples" / example / name, directory / name)
    database = directory / "fixture.sqlite3"
    result = _run([sys.executable, str(directory / "generate.py"), str(database)], directory.parent)
    assert result.returncode == 0, result.stdout + result.stderr
    return database


def _oracle(database: Path) -> subprocess.CompletedProcess[str]:
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    result = _run(
        [sys.executable, str(database.parent / "oracle.py"), str(database)], database.parent
    )
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    return result


@pytest.mark.parametrize(("example", "expected_exit", "marker"), EXAMPLES)
def test_realistic_oracle_target_and_correct_data(
    tmp_path: Path, example: str, expected_exit: int, marker: str
) -> None:
    database = _prepare(example, tmp_path / "application")
    target = _oracle(database)
    assert target.returncode == expected_exit, target.stdout + target.stderr
    assert target.stdout.splitlines() == [marker]
    assert not target.stderr

    # Independently regenerate the bytes and prove existing outputs are protected.
    duplicate = tmp_path / "second.sqlite3"
    generated = _run(
        [sys.executable, str(database.parent / "generate.py"), str(duplicate)], tmp_path
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    assert database.read_bytes() == duplicate.read_bytes()
    protected = _run(
        [sys.executable, str(database.parent / "generate.py"), str(duplicate)], tmp_path
    )
    assert protected.returncode != 0
    assert database.read_bytes() == duplicate.read_bytes()

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        if example == "reservation_overbook":
            connection.execute("UPDATE stock_lots SET capacity = 100")
        else:
            connection.execute(
                'UPDATE "approval steps" SET depends_on_id = NULL '
                'WHERE id = (SELECT MAX(id) FROM "approval steps")'
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    correct = _oracle(database)
    assert correct.returncode == 0, correct.stdout + correct.stderr
    assert not correct.stdout
    assert not correct.stderr


@pytest.mark.parametrize(("example", "expected_exit", "marker"), EXAMPLES)
def test_realistic_oracle_stops_reproducing_when_application_bug_is_fixed(
    tmp_path: Path, example: str, expected_exit: int, marker: str
) -> None:
    database = _prepare(example, tmp_path / "application")
    original = _oracle(database)
    assert original.returncode == expected_exit
    assert original.stdout.splitlines() == [marker]
    application = database.parent / "app.py"
    source = application.read_text(encoding="utf-8")
    # Counterfactual application repairs operate on staged synthetic assets.
    # The oracle is unchanged and must recognize correct application behavior.
    if example == "reservation_overbook":
        source = source.replace(
            "decisions: dict[int, bool] = {}",
            "decisions: dict[int, bool] = {}\n    available: dict[int, int] = {}",
        ).replace(
            "capacities[lot_id] = capacity",
            "capacities[lot_id] = available.setdefault(lot_id, capacity)",
        )
        source = source.replace(
            "    return decisions",
            "            if decisions[reservation_id]:\n"
            "                for lot_id, quantity in demand.items():\n"
            "                    available[lot_id] -= quantity\n"
            "    return decisions",
        )
    else:
        source = source.replace("        completed.add(step_id)\n", "", 1).replace(
            "        visiting.remove(step_id)",
            "        visiting.remove(step_id)\n        completed.add(step_id)",
        )
    assert source != application.read_text(encoding="utf-8")
    application.write_text(source, encoding="utf-8")
    fixed = _oracle(database)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert not fixed.stdout
    assert not fixed.stderr


def test_reservation_individual_overallocation_is_an_unrelated_defect(tmp_path: Path) -> None:
    database = _prepare("reservation_overbook", tmp_path / "application")
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE reservation_lines SET quantity = 1000 "
            "WHERE id = (SELECT MIN(id) FROM reservation_lines)"
        )
    application = database.parent / "app.py"
    source = application.read_text(encoding="utf-8")
    broken = source.replace("quantity <= capacities[lot_id]", "True")
    assert broken != source
    application.write_text(broken, encoding="utf-8")
    unrelated = _oracle(database)
    assert unrelated.returncode == 2, unrelated.stdout + unrelated.stderr
    assert not unrelated.stdout
    assert "Unexpected individual reservation decision" in unrelated.stderr


def test_approval_three_node_cycle_is_an_unrelated_defect(tmp_path: Path) -> None:
    database = _prepare("approval_cycle", tmp_path / "application")
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        steps = [
            row[0]
            for row in connection.execute(
                'SELECT id FROM "approval steps" WHERE workflow_id = '
                '(SELECT MIN(id) FROM "approval workflows") ORDER BY id LIMIT 3'
            )
        ]
        connection.executemany(
            'UPDATE "approval steps" SET depends_on_id = ? WHERE id = ?',
            [(steps[(index + 1) % 3], step) for index, step in enumerate(steps)],
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    unrelated = _oracle(database)
    assert unrelated.returncode == 2, unrelated.stdout + unrelated.stderr
    assert not unrelated.stdout
    assert "Unexpected workflow validation discrepancy" in unrelated.stderr


@pytest.mark.parametrize(("example", "expected_exit", "marker"), EXAMPLES)
def test_realistic_application_crash_does_not_emit_target(
    tmp_path: Path, example: str, expected_exit: int, marker: str
) -> None:
    database = _prepare(example, tmp_path / "application")
    function = "process_reservations" if example == "reservation_overbook" else "validate_workflows"
    (database.parent / "app.py").write_text(
        f"def {function}(database):\n    raise RuntimeError('Unrelated synthetic crash')\n",
        encoding="utf-8",
    )
    crash = _oracle(database)
    assert crash.returncode not in (0, expected_exit)
    assert marker not in crash.stdout.splitlines()
    assert "Unrelated synthetic crash" in crash.stderr
