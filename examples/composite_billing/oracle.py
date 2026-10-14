"""Independently verify observed false-paid decisions caused by refunded funds."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from app import reconcile_invoices

MARKER = "REPROSEED_COMPOSITE_BILLING_FALSE_PAID"
InvoiceKey = tuple[str, int]


def check(database: Path) -> int:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        invoices = {
            (tenant, number): total
            for tenant, number, total in connection.execute(
                "SELECT tenant_id, invoice_no, total_cents FROM invoices"
            )
        }
        lines = connection.execute(
            "SELECT tenant_id, invoice_no, amount_cents FROM invoice_lines"
        ).fetchall()
        payments = {
            payment: (tenant, number, amount, state)
            for payment, tenant, number, amount, state in connection.execute(
                "SELECT id, tenant_id, invoice_no, amount_cents, state FROM payments"
            )
        }
        refunds = connection.execute(
            "SELECT payment_id, amount_cents, state FROM refunds"
        ).fetchall()
    actual = reconcile_invoices(database)
    if set(actual) != set(invoices) or any(type(value) is not bool for value in actual.values()):
        print("Unexpected invoice decision map", file=sys.stderr)
        return 2
    line_amounts: dict[InvoiceKey, int] = {}
    successful_charges: dict[InvoiceKey, int] = {}
    returned_funds: dict[InvoiceKey, int] = {}
    for tenant, number, amount in lines:
        key = (tenant, number)
        if key in invoices:
            line_amounts[key] = line_amounts.get(key, 0) + amount
    for tenant, number, amount, state in payments.values():
        key = (tenant, number)
        if state == "settled" and key in invoices:
            successful_charges[key] = successful_charges.get(key, 0) + amount
    for payment, amount, state in refunds:
        tenant, number, _charged, payment_state = payments[payment]
        key = (tenant, number)
        if state == "settled" and payment_state == "settled" and key in invoices:
            returned_funds[key] = returned_funds.get(key, 0) + amount
    intended: dict[InvoiceKey, bool] = {}
    refund_added: dict[InvoiceKey, bool] = {}
    false_paid = False
    for key, total in invoices.items():
        complete = line_amounts.get(key, 0) == total
        charges = successful_charges.get(key, 0)
        refunded = returned_funds.get(key, 0)
        net_settled = charges - refunded
        intended[key] = complete and net_settled >= total
        refund_added[key] = complete and charges + refunded >= total
        if refund_added[key] and not intended[key] and refunded > 0:
            false_paid = True
    if actual == intended:
        return 0
    if actual == refund_added and false_paid:
        print(MARKER)
        return 47
    print("Unexpected invoice reconciliation discrepancy", file=sys.stderr)
    return 2


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: oracle.py DATABASE", file=sys.stderr)
        return 2
    try:
        return check(Path(sys.argv[1]))
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        print("Invoice reconciler could not be checked", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
