"""An invoice reconciler with a deliberate refund-sign accounting bug."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

InvoiceKey = tuple[str, int]


def reconcile_invoices(database: Path) -> dict[InvoiceKey, bool]:
    """Return whether each invoice has matching lines and sufficient settlement."""
    decisions: dict[InvoiceKey, bool] = {}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        line_totals = {
            (tenant, number): amount
            for tenant, number, amount in connection.execute(
                "SELECT tenant_id, invoice_no, SUM(amount_cents) FROM invoice_lines "
                "GROUP BY tenant_id, invoice_no"
            )
        }
        settlement: dict[InvoiceKey, int] = {}
        for tenant, number, amount, refunded in connection.execute(
            """
            SELECT payments.tenant_id, payments.invoice_no, payments.amount_cents,
                   COALESCE(refund_totals.amount, 0)
            FROM payments
            LEFT JOIN (
                SELECT payment_id, SUM(amount_cents) AS amount FROM refunds
                WHERE state = 'settled' GROUP BY payment_id
            ) AS refund_totals ON refund_totals.payment_id = payments.id
            WHERE payments.state = 'settled'
            """
        ):
            if tenant is None or number is None:
                continue
            settled = amount
            # Deliberate bug: returned funds reduce settlement of a charge.
            # Adding a refund can falsely mark an underpaid invoice as paid.
            settled += refunded
            key = (tenant, number)
            settlement[key] = settlement.get(key, 0) + settled
        for tenant, number, total in connection.execute(
            "SELECT tenant_id, invoice_no, total_cents FROM invoices ORDER BY tenant_id, invoice_no"
        ):
            key = (tenant, number)
            decisions[key] = line_totals.get(key, 0) == total and settlement.get(key, 0) >= total
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()
    decisions = reconcile_invoices(arguments.database)
    print(
        json.dumps(
            [
                {"tenant_id": tenant, "invoice_no": number, "paid": paid}
                for (tenant, number), paid in decisions.items()
            ],
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
