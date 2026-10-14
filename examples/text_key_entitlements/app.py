"""An entitlement processor with a deliberate cross-tenant event deduplication bug."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def process_entitlements(database: Path) -> dict[int, bool]:
    """Return whether each received event applies an entitlement grant."""
    decisions: dict[int, bool] = {}
    seen: set[str] = set()
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        rows = connection.execute(
            """
            SELECT event_receipts.id, accounts.tenant_id, events.external_reference,
                   event_receipts.status, events.operation, events.account_id,
                   entitlements.account_id, entitlements.enabled
            FROM event_receipts
            JOIN events ON events.id = event_receipts.event_id
            JOIN accounts ON accounts.id = events.account_id
            LEFT JOIN entitlements ON entitlements.id = events.entitlement_id
            ORDER BY event_receipts.id
            """
        )
        for receipt, _tenant, reference, status, operation, account, owner, enabled in rows:
            if owner is not None and owner != account:
                raise ValueError("Event entitlement belongs to another account")
            if status != "pending" or operation != "grant" or enabled != 1:
                decisions[receipt] = False
                continue
            # Deliberate bug: a gateway reference is unique within its tenant.
            # A global reference suppresses an unrelated tenant's valid grant.
            deduplication_key = reference
            decisions[receipt] = deduplication_key not in seen
            seen.add(deduplication_key)
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(process_entitlements(arguments.database), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
