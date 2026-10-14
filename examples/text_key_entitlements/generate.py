"""Generate deterministic synthetic entitlements, never real tenant data."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def text_id(family: str, ordinal: int) -> str:
    """Use sparse, stable UUID-like identifiers unrelated to hidden rowids."""
    return f"{family}-00000000-0000-4000-8000-{1009 + ordinal * 7919:012x}"


def generate(database: Path, *, small: bool = False) -> None:
    """Create 970 rows by default, or ten essential rows for installed-wheel smoke."""
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite an existing database: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE tenants (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE accounts (
                id TEXT PRIMARY KEY NOT NULL,
                tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                name TEXT NOT NULL
            );
            CREATE TABLE entitlements (
                id TEXT NOT NULL,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                issuer_tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                feature TEXT NOT NULL,
                enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                PRIMARY KEY (id)
            );
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                entitlement_id TEXT REFERENCES entitlements(id),
                external_reference TEXT NOT NULL,
                operation TEXT NOT NULL CHECK (operation IN ('grant', 'preview'))
            );
            CREATE TABLE event_receipts (
                id INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(id),
                status TEXT NOT NULL CHECK (status IN ('pending', 'discarded'))
            );
            CREATE INDEX accounts_tenant ON accounts(tenant_id);
            CREATE INDEX entitlements_account ON entitlements(account_id);
            CREATE INDEX events_account ON events(account_id);
            CREATE INDEX events_entitlement ON events(entitlement_id);
            CREATE INDEX receipts_event ON event_receipts(event_id);
            PRAGMA user_version = 21;
            PRAGMA application_id = 1381190738;
            """
        )
        tenant_count, account_count, entitlement_count, event_count = (
            (2, 2, 2, 2) if small else (10, 40, 120, 400)
        )
        tenants = [(101 + i * 17, f"Synthetic tenant {i + 1}") for i in range(tenant_count)]
        accounts_per_tenant = account_count // tenant_count
        accounts = [
            (
                text_id("account", i),
                tenants[i // accounts_per_tenant][0],
                f"Synthetic account {i + 1}",
            )
            for i in range(account_count)
        ]
        entitlements_per_account = entitlement_count // account_count
        entitlements = [
            (
                text_id("entitlement", i),
                accounts[i // entitlements_per_account][0],
                accounts[i // entitlements_per_account][1],
                f"FEATURE-{i % entitlements_per_account + 1}",
                1,
            )
            for i in range(entitlement_count)
        ]
        events = []
        receipts = []
        for i in range(event_count):
            account_index = i // (event_count // account_count)
            # The final two events use distinct tenants but the same upstream
            # reference. This is ordinary event content, never a failure flag.
            target_pair = i >= event_count - 2
            if target_pair:
                account_index = account_count - 1 if i == event_count - 1 else 0
            entitlement_index = (
                account_index * entitlements_per_account + i % entitlements_per_account
            )
            event_id = text_id("event", i)
            events.append(
                (
                    event_id,
                    accounts[account_index][0],
                    entitlements[entitlement_index][0] if target_pair or i % 13 != 0 else None,
                    "gateway-delivery-7f36" if target_pair else f"gateway-delivery-{i * 37:06x}",
                    "grant" if target_pair or i % 19 != 0 else "preview",
                )
            )
            receipts.append(
                (90001 + i * 31, event_id, "pending" if target_pair or i % 17 != 0 else "discarded")
            )
        connection.executemany("INSERT INTO tenants VALUES (?, ?)", tenants)
        connection.executemany("INSERT INTO accounts VALUES (?, ?, ?)", accounts)
        connection.executemany("INSERT INTO entitlements VALUES (?, ?, ?, ?, ?)", entitlements)
        connection.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", events)
        connection.executemany("INSERT INTO event_receipts VALUES (?, ?, ?)", receipts)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Synthetic generator produced invalid foreign keys")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database", nargs="?", type=Path, default=Path(__file__).parent / "fixture.sqlite3"
    )
    parser.add_argument(
        "--small", action="store_true", help="Ten-row installed-wheel smoke fixture."
    )
    arguments = parser.parse_args()
    generate(arguments.database, small=arguments.small)
    rows = 10 if arguments.small else 970
    print(f"Created {arguments.database}: {rows} synthetic user rows across five tables.")


if __name__ == "__main__":
    main()
