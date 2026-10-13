"""Independently find cycles and verify the application's actual false acceptance."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from app import validate_workflows

MARKER = "REPROSEED_APPROVAL_CYCLE"


def _cycle_lengths(dependencies: dict[int, int | None]) -> set[int]:
    """Use path positions, independently of the application's visited-set check."""
    lengths: set[int] = set()
    finished: set[int] = set()
    for start in sorted(dependencies):
        path: dict[int, int] = {}
        current: int | None = start
        while current is not None and current not in finished:
            if current in path:
                lengths.add(len(path) - path[current])
                break
            path[current] = len(path)
            current = dependencies[current]
        finished.update(path)
    return lengths


def check(database: Path) -> int:
    decisions = validate_workflows(database)
    target = False
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        workflows = connection.execute(
            'SELECT id, department_id FROM "approval workflows" ORDER BY id'
        ).fetchall()
        if set(decisions) != {row[0] for row in workflows}:
            print("Unexpected workflow result", file=sys.stderr)
            return 2
        for workflow_id, department_id in workflows:
            rows = connection.execute(
                """
                SELECT "approval steps".id, "approval steps".depends_on_id,
                       employees.department_id
                FROM "approval steps"
                JOIN employees ON employees.id = "approval steps".approver_id
                WHERE "approval steps".workflow_id = ?
                """,
                (workflow_id,),
            ).fetchall()
            rules = connection.execute(
                'SELECT minimum_approvals FROM "approval rules" WHERE workflow_id = ?',
                (workflow_id,),
            ).fetchall()
            dependencies = {step_id: dependency for step_id, dependency, _ in rows}
            eligible = (
                bool(rules)
                and len(rows) >= max(rule[0] for rule in rules)
                and all(
                    approver_department == department_id
                    and (dependency is None or dependency in dependencies)
                    for _, dependency, approver_department in rows
                )
            )
            cycles = _cycle_lengths(dependencies) if eligible else set()
            expected = eligible and not cycles
            accepted = decisions[workflow_id]
            if type(accepted) is not bool:
                print("Unexpected workflow decision type", file=sys.stderr)
                return 2
            if accepted != expected:
                # Only an eligible workflow incorrectly accepted with two-node
                # cycles qualifies; a different cycle/crash/rejection does not.
                if accepted and eligible and cycles == {2}:
                    target = True
                else:
                    print("Unexpected workflow validation discrepancy", file=sys.stderr)
                    return 2
    if target:
        print(MARKER)
        return 45
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: oracle.py DATABASE", file=sys.stderr)
        return 2
    try:
        return check(Path(sys.argv[1]))
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, RecursionError):
        print("Approval validator could not be checked", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
