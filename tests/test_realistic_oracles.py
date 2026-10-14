"""Counterfactual fixes and unrelated defects do not satisfy the example oracles."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
EXAMPLES = (
    ("reservation_overbook", 44, "REPROSEED_RESERVATION_OVERBOOK", False),
    ("approval_cycle", 45, "REPROSEED_APPROVAL_CYCLE", False),
    ("text_key_entitlements", 46, "REPROSEED_TEXT_KEY_ENTITLEMENTS", False),
    ("composite_billing", 47, "REPROSEED_COMPOSITE_BILLING_FALSE_PAID", False),
    ("composite_billing", 47, "REPROSEED_COMPOSITE_BILLING_FALSE_PAID", True),
)


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    # Counterfactual fixes can preserve source size and occur within one second.
    # Read staged application source afresh instead of reusing timestamp-based bytecode.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )


def _prepare(example: str, directory: Path, *, without_rowid: bool = False) -> Path:
    directory.mkdir()
    for name in ("app.py", "oracle.py", "generate.py"):
        shutil.copy2(REPOSITORY / "examples" / example / name, directory / name)
    database = directory / "fixture.sqlite3"
    flags = ["--without-rowid"] if without_rowid else []
    result = _run(
        [sys.executable, str(directory / "generate.py"), str(database), *flags], directory.parent
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return database


def _oracle(database: Path) -> subprocess.CompletedProcess[str]:
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    result = _run(
        [sys.executable, str(database.parent / "oracle.py"), str(database)], database.parent
    )
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    return result


@pytest.mark.parametrize(("example", "expected_exit", "marker", "without_rowid"), EXAMPLES)
def test_realistic_oracle_target_and_correct_data(
    tmp_path: Path, example: str, expected_exit: int, marker: str, without_rowid: bool
) -> None:
    database = _prepare(example, tmp_path / "application", without_rowid=without_rowid)
    target = _oracle(database)
    assert target.returncode == expected_exit, target.stdout + target.stderr
    assert target.stdout.splitlines() == [marker]
    assert not target.stderr

    # Independently regenerate the bytes and prove existing outputs are protected.
    duplicate = tmp_path / "second.sqlite3"
    flags = ["--without-rowid"] if without_rowid else []
    generated = _run(
        [sys.executable, str(database.parent / "generate.py"), str(duplicate), *flags], tmp_path
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    assert database.read_bytes() == duplicate.read_bytes()
    protected = _run(
        [sys.executable, str(database.parent / "generate.py"), str(duplicate), *flags], tmp_path
    )
    assert protected.returncode != 0
    assert database.read_bytes() == duplicate.read_bytes()

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        if example == "reservation_overbook":
            connection.execute("UPDATE stock_lots SET capacity = 100")
        elif example == "approval_cycle":
            connection.execute(
                'UPDATE "approval steps" SET depends_on_id = NULL '
                'WHERE id = (SELECT MAX(id) FROM "approval steps")'
            )
        elif example == "text_key_entitlements":
            connection.execute(
                "UPDATE events SET external_reference = 'independent-gateway-reference' "
                "WHERE id = (SELECT MAX(id) FROM events)"
            )
        else:
            connection.execute("UPDATE refunds SET state = 'pending'")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    correct = _oracle(database)
    assert correct.returncode == 0, correct.stdout + correct.stderr
    assert not correct.stdout
    assert not correct.stderr


@pytest.mark.parametrize(("example", "expected_exit", "marker", "without_rowid"), EXAMPLES)
def test_realistic_oracle_stops_reproducing_when_application_bug_is_fixed(
    tmp_path: Path, example: str, expected_exit: int, marker: str, without_rowid: bool
) -> None:
    database = _prepare(example, tmp_path / "application", without_rowid=without_rowid)
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
    elif example == "approval_cycle":
        source = source.replace("        completed.add(step_id)\n", "", 1).replace(
            "        visiting.remove(step_id)",
            "        visiting.remove(step_id)\n        completed.add(step_id)",
        )
    elif example == "text_key_entitlements":
        source = source.replace("seen: set[str] = set()", "seen: set[tuple[int, str]] = set()")
        source = source.replace(
            "deduplication_key = reference", "deduplication_key = (_tenant, reference)"
        )
    else:
        source = source.replace("settled += refunded", "settled -= refunded")
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


def test_text_entitlement_same_tenant_duplicate_is_correctly_suppressed(tmp_path: Path) -> None:
    database = _prepare("text_key_entitlements", tmp_path / "application")
    with closing(sqlite3.connect(database)) as connection, connection:
        # Give the second duplicate the first event's account and entitlement.
        # Both now belong to the same tenant, where suppression is intentional.
        first, last = connection.execute(
            "SELECT id, account_id, entitlement_id FROM events "
            "WHERE external_reference = 'gateway-delivery-7f36' ORDER BY id"
        ).fetchall()
        connection.execute(
            "UPDATE events SET account_id = ?, entitlement_id = ? WHERE id = ?",
            (first[1], first[2], last[0]),
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    correct = _oracle(database)
    assert correct.returncode == 0, correct.stdout + correct.stderr
    assert not correct.stdout
    assert not correct.stderr


def test_text_entitlement_unrelated_missing_grants_do_not_emit_target(tmp_path: Path) -> None:
    database = _prepare("text_key_entitlements", tmp_path / "application")
    application = database.parent / "app.py"
    source = application.read_text(encoding="utf-8")
    broken = source.replace(
        "decisions[receipt] = deduplication_key not in seen", "decisions[receipt] = False"
    )
    assert broken != source
    application.write_text(broken, encoding="utf-8")
    unrelated = _oracle(database)
    assert unrelated.returncode == 2, unrelated.stdout + unrelated.stderr
    assert not unrelated.stdout
    assert "Unexpected entitlement processing discrepancy" in unrelated.stderr


@pytest.mark.parametrize(("example", "expected_exit", "marker", "without_rowid"), EXAMPLES)
def test_realistic_application_crash_does_not_emit_target(
    tmp_path: Path, example: str, expected_exit: int, marker: str, without_rowid: bool
) -> None:
    database = _prepare(example, tmp_path / "application", without_rowid=without_rowid)
    function = {
        "reservation_overbook": "process_reservations",
        "approval_cycle": "validate_workflows",
        "text_key_entitlements": "process_entitlements",
        "composite_billing": "reconcile_invoices",
    }[example]
    (database.parent / "app.py").write_text(
        f"def {function}(database):\n    raise RuntimeError('Unrelated synthetic crash')\n",
        encoding="utf-8",
    )
    crash = _oracle(database)
    assert crash.returncode not in (0, expected_exit)
    assert marker not in crash.stdout.splitlines()
    assert "Unrelated synthetic crash" in crash.stderr


@pytest.mark.parametrize("without_rowid", [False, True])
def test_composite_billing_unrelated_decisions_do_not_emit_target(
    tmp_path: Path, without_rowid: bool
) -> None:
    database = _prepare("composite_billing", tmp_path / "application", without_rowid=without_rowid)
    application = database.parent / "app.py"
    source = application.read_text(encoding="utf-8")
    broken = source.replace(
        "decisions[key] = line_totals.get(key, 0) == total and settlement.get(key, 0) >= total",
        "decisions[key] = True",
    )
    assert broken != source
    application.write_text(broken, encoding="utf-8")
    unrelated = _oracle(database)
    assert unrelated.returncode == 2, unrelated.stdout + unrelated.stderr
    assert not unrelated.stdout
    assert "Unexpected invoice reconciliation discrepancy" in unrelated.stderr


@pytest.mark.parametrize("without_rowid", [False, True])
def test_composite_billing_pending_refund_is_not_settled_money(
    tmp_path: Path, without_rowid: bool
) -> None:
    database = _prepare("composite_billing", tmp_path / "application", without_rowid=without_rowid)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE refunds SET state = 'pending' "
            "WHERE tenant_id = 'tenant-012' AND reference = 'refund-14'"
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    correct = _oracle(database)
    assert correct.returncode == 0, correct.stdout + correct.stderr
    assert not correct.stdout
    assert not correct.stderr


@pytest.mark.parametrize("without_rowid", [False, True])
def test_composite_billing_malformed_decision_map_is_not_target(
    tmp_path: Path, without_rowid: bool
) -> None:
    database = _prepare("composite_billing", tmp_path / "application", without_rowid=without_rowid)
    application = database.parent / "app.py"
    source = application.read_text(encoding="utf-8")
    broken = source.replace("    return decisions", "    return {}")
    assert broken != source
    application.write_text(broken, encoding="utf-8")
    unrelated = _oracle(database)
    assert unrelated.returncode == 2, unrelated.stdout + unrelated.stderr
    assert not unrelated.stdout
    assert "Unexpected invoice decision map" in unrelated.stderr


@pytest.mark.parametrize("without_rowid", [False, True])
def test_composite_billing_small_fixture_has_real_refund_accounting(
    tmp_path: Path, without_rowid: bool
) -> None:
    application = tmp_path / "application"
    application.mkdir()
    for name in ("app.py", "oracle.py", "generate.py"):
        shutil.copy2(REPOSITORY / "examples" / "composite_billing" / name, application / name)
    database = application / "fixture.sqlite3"
    flags = ["--without-rowid"] if without_rowid else []
    generated = _run(
        [sys.executable, str(application / "generate.py"), str(database), "--small", *flags],
        tmp_path,
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    with closing(sqlite3.connect(database)) as connection:
        tables = ("tenants", "accounts", "invoices", "invoice_lines", "payments", "refunds")
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
        assert counts == {
            "tenants": 1,
            "accounts": 1,
            "invoices": 1,
            "invoice_lines": 3,
            "payments": 1,
            "refunds": 1,
        }
        assert sum(counts.values()) == 8
        assert {
            row[1]: bool(row[4])
            for row in connection.execute("PRAGMA table_list")
            if row[0] == "main" and row[1] in tables
        } == {table: without_rowid and table != "payments" for table in tables}
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        total = connection.execute("SELECT total_cents FROM invoices").fetchone()[0]
        charged = connection.execute(
            "SELECT SUM(amount_cents) FROM payments WHERE state = 'settled'"
        ).fetchone()[0]
        refunded = connection.execute(
            "SELECT SUM(amount_cents) FROM refunds WHERE state = 'settled'"
        ).fetchone()[0]
        assert charged - refunded < total <= charged + refunded
    target = _oracle(database)
    assert target.returncode == 47, target.stdout + target.stderr
    assert target.stdout.splitlines() == ["REPROSEED_COMPOSITE_BILLING_FALSE_PAID"]
    assert not target.stderr


def test_composite_billing_storage_variant_preserves_declared_data_and_indexes(
    tmp_path: Path,
) -> None:
    ordinary = _prepare("composite_billing", tmp_path / "application")
    alternate = tmp_path / "without-rowid.sqlite3"
    generated = _run(
        [sys.executable, str(ordinary.parent / "generate.py"), str(alternate), "--without-rowid"],
        tmp_path,
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    with (
        closing(sqlite3.connect(ordinary)) as rowid_connection,
        closing(sqlite3.connect(alternate)) as without_rowid_connection,
    ):
        schema_query = (
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
        ordinary_schema = rowid_connection.execute(schema_query).fetchall()
        alternate_schema = without_rowid_connection.execute(schema_query).fetchall()
        assert [
            (kind, name, table, sql.replace(" WITHOUT ROWID", ""))
            for kind, name, table, sql in alternate_schema
        ] == ordinary_schema
        tables = [name for kind, name, _table, _sql in ordinary_schema if kind == "table"]
        assert len(tables) == 6
        for table in tables:
            query = f'SELECT * FROM "{table}"'
            assert set(without_rowid_connection.execute(query)) == set(
                rowid_connection.execute(query)
            )
        for metadata in ("user_version", "application_id"):
            assert without_rowid_connection.execute(f"PRAGMA {metadata}").fetchone() == (
                rowid_connection.execute(f"PRAGMA {metadata}").fetchone()
            )
        assert without_rowid_connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert without_rowid_connection.execute("PRAGMA foreign_key_check").fetchall() == []
