"""Independently compare observed grants with tenant-scoped delivery semantics."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from app import process_entitlements

MARKER = "REPROSEED_TEXT_KEY_ENTITLEMENTS"


def check(database: Path) -> int:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        receipt_ids = {row[0] for row in connection.execute("SELECT id FROM event_receipts")}
        # Read the contract inputs independently of the processor's query and
        # compare the complete observable decision map, including ignored rows.
        events = {
            event_id: (account_id, entitlement_id, reference, operation)
            for event_id, account_id, entitlement_id, reference, operation in connection.execute(
                "SELECT id, account_id, entitlement_id, external_reference, operation FROM events"
            )
        }
        accounts = dict(connection.execute("SELECT id, tenant_id FROM accounts"))
        entitlements = {
            entitlement_id: (owner, enabled)
            for entitlement_id, owner, enabled in connection.execute(
                "SELECT id, account_id, enabled FROM entitlements"
            )
        }
        receipts = connection.execute(
            "SELECT id, event_id, status FROM event_receipts ORDER BY id"
        ).fetchall()
    actual = process_entitlements(database)
    if set(actual) != receipt_ids or any(type(value) is not bool for value in actual.values()):
        print("Unexpected entitlement decision map", file=sys.stderr)
        return 2
    intended: dict[int, bool] = {}
    global_reference: dict[int, bool] = {}
    scoped_seen: set[tuple[int, str]] = set()
    reference_seen: set[str] = set()
    cross_tenant_suppressed = False
    for receipt_id, event_id, status in receipts:
        account_id, entitlement_id, reference, operation = events[event_id]
        tenant = accounts[account_id]
        entitlement = entitlements.get(entitlement_id)
        if entitlement is not None and entitlement[0] != account_id:
            print("Unexpected entitlement ownership", file=sys.stderr)
            return 2
        eligible = (
            status == "pending"
            and operation == "grant"
            and entitlement is not None
            and entitlement[1] == 1
        )
        scope = (tenant, reference)
        intended[receipt_id] = eligible and scope not in scoped_seen
        global_reference[receipt_id] = eligible and reference not in reference_seen
        if intended[receipt_id] and not global_reference[receipt_id]:
            cross_tenant_suppressed = True
        if eligible:
            scoped_seen.add(scope)
            reference_seen.add(reference)
    if actual == intended:
        return 0
    if actual == global_reference and cross_tenant_suppressed:
        print(MARKER)
        return 46
    print("Unexpected entitlement processing discrepancy", file=sys.stderr)
    return 2


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: oracle.py DATABASE", file=sys.stderr)
        return 2
    try:
        return check(Path(sys.argv[1]))
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        print("Entitlement processor could not be checked", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
