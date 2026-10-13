"""A reservation processor with a deliberate aggregate stock accounting defect."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path


def process_reservations(database: Path) -> dict[int, bool]:
    """Return acceptance decisions for submitted inventory reservations."""
    decisions: dict[int, bool] = {}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        reservations = connection.execute(
            """
            SELECT reservations.id, reservations.warehouse_id, orders.organization_id,
                   warehouses.organization_id
            FROM reservations
            JOIN orders ON orders.id = reservations.order_id
            JOIN warehouses ON warehouses.id = reservations.warehouse_id
            WHERE reservations.status = 'submitted'
            ORDER BY reservations.id
            """
        ).fetchall()
        for reservation_id, warehouse_id, order_tenant, warehouse_tenant in reservations:
            if order_tenant != warehouse_tenant:
                raise ValueError("Reservation warehouse belongs to another tenant")
            demand: dict[int, int] = defaultdict(int)
            capacities: dict[int, int] = {}
            for lot_id, quantity, lot_warehouse, capacity in connection.execute(
                """
                SELECT stock_lots.id, reservation_lines.quantity,
                       stock_lots.warehouse_id, stock_lots.capacity
                FROM reservation_lines
                JOIN stock_lots ON stock_lots.id = reservation_lines.lot_id
                WHERE reservation_lines.reservation_id = ?
                ORDER BY reservation_lines.id
                """,
                (reservation_id,),
            ):
                if lot_warehouse != warehouse_id:
                    raise ValueError("Reservation line uses stock from another warehouse")
                demand[lot_id] += quantity
                capacities[lot_id] = capacity
            # Deliberate bug: compare each reservation with the original capacity.
            # Successful earlier reservations never debit the available stock.
            decisions[reservation_id] = bool(demand) and all(
                quantity <= capacities[lot_id] for lot_id, quantity in demand.items()
            )
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(process_reservations(arguments.database), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
