"""Generate deterministic synthetic billing records, never real customer data."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def generate(database: Path, *, small: bool = False) -> None:
    """Create 1,308 user rows, or eight genuine rows for installed-wheel smoke."""
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite an existing database: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE tenants (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL
            );
            CREATE TABLE accounts (
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                account_code TEXT NOT NULL,
                name TEXT NOT NULL,
                PRIMARY KEY (tenant_id, account_code)
            );
            CREATE TABLE invoices (
                tenant_id TEXT NOT NULL,
                invoice_no INTEGER NOT NULL,
                account_code TEXT NOT NULL,
                total_cents INTEGER NOT NULL CHECK (total_cents > 0),
                PRIMARY KEY (tenant_id, invoice_no),
                FOREIGN KEY (tenant_id, account_code)
                    REFERENCES accounts(tenant_id, account_code)
            );
            CREATE TABLE invoice_lines (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                invoice_no INTEGER,
                description TEXT NOT NULL,
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                FOREIGN KEY (tenant_id, invoice_no) REFERENCES invoices
            );
            CREATE TABLE payments (
                id INTEGER PRIMARY KEY,
                tenant_id TEXT,
                invoice_no INTEGER,
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                state TEXT NOT NULL CHECK (state IN ('settled', 'pending')),
                FOREIGN KEY (tenant_id, invoice_no) REFERENCES invoices(tenant_id, invoice_no)
            );
            CREATE TABLE refunds (
                tenant_id TEXT NOT NULL,
                reference TEXT NOT NULL,
                account_code TEXT NOT NULL,
                payment_id INTEGER NOT NULL REFERENCES payments(id),
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                state TEXT NOT NULL CHECK (state IN ('settled', 'pending')),
                PRIMARY KEY (tenant_id, reference),
                FOREIGN KEY (tenant_id, account_code)
                    REFERENCES accounts(tenant_id, account_code)
            );
            CREATE INDEX invoices_account ON invoices(tenant_id, account_code);
            CREATE INDEX lines_invoice ON invoice_lines(tenant_id, invoice_no);
            CREATE INDEX payments_invoice ON payments(tenant_id, invoice_no);
            CREATE INDEX refunds_payment ON refunds(payment_id);
            PRAGMA user_version = 22;
            PRAGMA application_id = 1381190738;
            """
        )
        tenants = [
            (f"tenant-{ordinal:03}", f"Synthetic tenant {ordinal}")
            for ordinal in ([12] if small else range(1, 13))
        ]
        accounts = [
            (tenant, f"account-{ordinal:02}", f"Synthetic account {ordinal}")
            for tenant, _name in tenants
            for ordinal in ([3] if small else range(1, 4))
        ]
        invoices = []
        lines = []
        payments = []
        refunds = []
        for index in [179] if small else range(180):
            tenant = f"tenant-{index // 15 + 1:03}"
            invoice_no = 101 + (index % 15) * 37
            account = f"account-{index % 15 // 5 + 1:02}"
            target = index == 179
            invoices.append((tenant, invoice_no, account, 10000))
            for ordinal, amount in enumerate((4000, 3000, 3000), start=1):
                lines.append(
                    (f"line-{index:04}-{ordinal}", tenant, invoice_no, f"Service {ordinal}", amount)
                )
            # Decoys contain fully paid, underpaid, pending, and refunded charges.
            # Only the final invoice crosses the paid threshold by adding refunds.
            payment_id = 10001 + index * 31
            settled = 7000 if target else (4000 if index % 4 == 0 else 12000)
            payments.append((payment_id, tenant, invoice_no, settled, "settled"))
            if not small:
                # Nullable composite references follow SQLite's any-NULL rule.
                # These unattached pending payments also share ordinary key values.
                nullable = (index % 13) % 4
                foreign_tenant = None if nullable in (1, 3) else tenant
                foreign_number = None if nullable in (2, 3) else invoice_no
                payments.append((payment_id + 1, foreign_tenant, foreign_number, 1000, "pending"))
            refunds.append(
                (
                    tenant,
                    f"refund-{index % 15:02}",
                    account,
                    payment_id,
                    4000 if target else 2000,
                    "settled" if target or index % 4 != 0 else "pending",
                )
            )
        connection.executemany("INSERT INTO tenants VALUES (?, ?)", tenants)
        connection.executemany("INSERT INTO accounts VALUES (?, ?, ?)", accounts)
        connection.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?)", invoices)
        connection.executemany("INSERT INTO invoice_lines VALUES (?, ?, ?, ?, ?)", lines)
        connection.executemany("INSERT INTO payments VALUES (?, ?, ?, ?, ?)", payments)
        connection.executemany("INSERT INTO refunds VALUES (?, ?, ?, ?, ?, ?)", refunds)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Synthetic generator produced invalid foreign keys")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database", nargs="?", type=Path, default=Path(__file__).parent / "fixture.sqlite3"
    )
    parser.add_argument(
        "--small", action="store_true", help="Eight-row installed-wheel smoke fixture."
    )
    arguments = parser.parse_args()
    generate(arguments.database, small=arguments.small)
    rows = 8 if arguments.small else 1308
    print(f"Created {arguments.database}: {rows} synthetic user rows across six tables.")


if __name__ == "__main__":
    main()
