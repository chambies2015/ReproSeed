"""Generate synthetic approval workflows with one deliberate two-step cycle."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def generate(database: Path) -> None:
    """Create a fresh deterministic fixture containing 1,626 user rows."""
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite an existing database: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE "team departments" (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                department_id INTEGER NOT NULL REFERENCES "team departments"(id),
                name TEXT NOT NULL
            );
            CREATE TABLE "approval workflows" (
                id INTEGER PRIMARY KEY,
                department_id INTEGER NOT NULL REFERENCES "team departments"(id),
                requester_id INTEGER REFERENCES employees(id),
                title TEXT NOT NULL
            );
            CREATE TABLE "approval steps" (
                id INTEGER PRIMARY KEY,
                workflow_id INTEGER NOT NULL REFERENCES "approval workflows"(id),
                approver_id INTEGER NOT NULL REFERENCES employees(id),
                depends_on_id INTEGER REFERENCES "approval steps"(id)
                    DEFERRABLE INITIALLY DEFERRED,
                label TEXT NOT NULL
            );
            CREATE TABLE "approval rules" (
                id INTEGER PRIMARY KEY,
                workflow_id INTEGER NOT NULL REFERENCES "approval workflows"(id),
                reviewer_id INTEGER REFERENCES employees(id),
                minimum_approvals INTEGER NOT NULL CHECK (minimum_approvals > 0)
            );
            CREATE TABLE "approval activity" (
                id INTEGER PRIMARY KEY,
                workflow_id INTEGER REFERENCES "approval workflows"(id),
                employee_id INTEGER REFERENCES employees(id),
                message TEXT NOT NULL
            );
            CREATE INDEX steps_workflow ON "approval steps"(workflow_id);
            PRAGMA user_version = 13;
            PRAGMA application_id = 1381190738;
            """
        )
        departments = [(-503 + i * 101, f"Synthetic department {i + 1}") for i in range(6)]
        employees = [
            (-10007 + i * 173, departments[i // 10][0], f"Synthetic approver {i + 1}")
            for i in range(60)
        ]
        workflows = []
        steps = []
        rules = []
        for i in range(120):
            department_id = departments[i // 20][0]
            approver_id = employees[(i // 20) * 10 + i % 10][0]
            workflow_id = -25001 + i * 421
            workflows.append(
                (
                    workflow_id,
                    department_id,
                    None if i % 9 == 0 else approver_id,
                    f"Synthetic purchase approval {i + 1}",
                )
            )
            rules.append((80001 + i * 43, workflow_id, None if i % 3 == 0 else approver_id, 1))
            step_ids = [100001 + (i * 11 + j) * 47 for j in range(11)]
            for j, step_id in enumerate(step_ids):
                dependency = None if j == 0 else step_ids[j - 1]
                if i == 119 and j in (9, 10):
                    dependency = step_ids[10 if j == 9 else 9]
                steps.append((step_id, workflow_id, approver_id, dependency, f"Review {j + 1}"))
        connection.executemany('INSERT INTO "team departments" VALUES (?, ?)', departments)
        connection.executemany("INSERT INTO employees VALUES (?, ?, ?)", employees)
        connection.executemany('INSERT INTO "approval workflows" VALUES (?, ?, ?, ?)', workflows)
        connection.executemany('INSERT INTO "approval rules" VALUES (?, ?, ?, ?)', rules)
        connection.executemany('INSERT INTO "approval steps" VALUES (?, ?, ?, ?, ?)', steps)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Synthetic generator produced invalid foreign keys")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "fixture.sqlite3",
        help="New database path; existing files are never overwritten.",
    )
    arguments = parser.parse_args()
    generate(arguments.database)
    print(f"Created {arguments.database}: 1626 synthetic user rows; approval activity is empty.")


if __name__ == "__main__":
    main()
