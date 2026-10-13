"""An approval validator with a deliberately flawed depth-first cycle check."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def _has_cycle(dependencies: dict[int, int | None]) -> bool:
    completed: set[int] = set()
    visiting: set[int] = set()

    def visit(step_id: int) -> bool:
        if step_id in completed:
            return False
        if step_id in visiting:
            return True
        # Deliberate bug: "completed" should be set only after following the
        # dependency. A back edge now exits above before checking "visiting".
        completed.add(step_id)
        visiting.add(step_id)
        dependency = dependencies[step_id]
        cyclic = dependency is not None and visit(dependency)
        visiting.remove(step_id)
        return cyclic

    # A direct self-dependency is rejected by a separate input check.
    return any(dependency == step for step, dependency in dependencies.items()) or any(
        visit(step) for step in sorted(dependencies)
    )


def validate_workflows(database: Path) -> dict[int, bool]:
    """Return whether each workflow is ready to accept approval requests."""
    decisions: dict[int, bool] = {}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        workflows = connection.execute(
            'SELECT id, department_id FROM "approval workflows" ORDER BY id'
        ).fetchall()
        for workflow_id, department_id in workflows:
            steps = connection.execute(
                """
                SELECT "approval steps".id, "approval steps".depends_on_id,
                       employees.department_id
                FROM "approval steps"
                JOIN employees ON employees.id = "approval steps".approver_id
                WHERE "approval steps".workflow_id = ?
                ORDER BY "approval steps".id
                """,
                (workflow_id,),
            ).fetchall()
            minimum = connection.execute(
                'SELECT MAX(minimum_approvals) FROM "approval rules" WHERE workflow_id = ?',
                (workflow_id,),
            ).fetchone()[0]
            dependencies = {step_id: dependency for step_id, dependency, _ in steps}
            context_valid = all(
                approver_department == department_id
                and (dependency is None or dependency in dependencies)
                for _, dependency, approver_department in steps
            )
            decisions[workflow_id] = (
                minimum is not None
                and len(steps) >= minimum
                and context_valid
                and not _has_cycle(dependencies)
            )
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(validate_workflows(arguments.database), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
