"""Generate deterministic synthetic inventory reservations, never real customer data."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def generate(database: Path) -> None:
    """Create a fresh database with 4,248 rows and one overbooking scenario."""
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite an existing database: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE warehouses (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                name TEXT NOT NULL
            );
            CREATE TABLE stock_lots (
                id INTEGER PRIMARY KEY,
                warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                sku TEXT NOT NULL,
                capacity INTEGER NOT NULL CHECK (capacity >= 0)
            );
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                preferred_warehouse_id INTEGER REFERENCES warehouses(id),
                reference TEXT NOT NULL
            );
            CREATE TABLE reservations (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id),
                warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                status TEXT NOT NULL CHECK (status IN ('submitted', 'cancelled'))
            );
            CREATE TABLE reservation_lines (
                id INTEGER PRIMARY KEY,
                reservation_id INTEGER NOT NULL REFERENCES reservations(id),
                lot_id INTEGER NOT NULL REFERENCES stock_lots(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0)
            );
            CREATE INDEX lines_reservation ON reservation_lines(reservation_id);
            CREATE INDEX lines_lot ON reservation_lines(lot_id);
            PRAGMA user_version = 12;
            PRAGMA application_id = 1381190738;
            """
        )
        organizations = [(101 + i * 17, f"Synthetic tenant {i + 1}") for i in range(8)]
        warehouses = [
            (1001 + i * 19, organizations[i // 5][0], f"Synthetic warehouse {i + 1}")
            for i in range(40)
        ]
        lots = [
            (10001 + i * 23, warehouses[i // 5][0], f"SKU-{i + 1:04d}", 100) for i in range(200)
        ]
        lots[-1] = (*lots[-1][:3], 10)
        orders = []
        reservations = []
        lines = []
        for i in range(1000):
            warehouse = warehouses[i // 25]
            order_id = 20001 + i * 29
            reservation_id = 50001 + i * 31
            orders.append(
                (
                    order_id,
                    warehouse[1],
                    None if i % 7 == 0 else warehouse[0],
                    f"SYNTHETIC-{i + 1:05d}",
                )
            )
            # Earlier reservations for the final lot were cancelled. Only the last
            # two compete: their requests (6+1 and 7+1) each fit capacity 10.
            status = "cancelled" if i in (995, 996, 997) else "submitted"
            reservations.append((reservation_id, order_id, warehouse[0], status))
            quantity = 6 if i == 998 else 7 if i == 999 else 2
            lines.extend(
                [
                    (90001 + i * 74, reservation_id, lots[i // 5][0], quantity),
                    (90038 + i * 74, reservation_id, lots[i // 5][0], 1),
                ]
            )
        connection.executemany("INSERT INTO organizations VALUES (?, ?)", organizations)
        connection.executemany("INSERT INTO warehouses VALUES (?, ?, ?)", warehouses)
        connection.executemany("INSERT INTO stock_lots VALUES (?, ?, ?, ?)", lots)
        connection.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
        connection.executemany("INSERT INTO reservations VALUES (?, ?, ?, ?)", reservations)
        connection.executemany("INSERT INTO reservation_lines VALUES (?, ?, ?, ?)", lines)
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
    print(f"Created {arguments.database}: 4248 synthetic user rows across six tables.")


if __name__ == "__main__":
    main()
