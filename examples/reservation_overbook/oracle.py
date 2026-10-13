"""Independently verify that the processor actually accepted too much stock."""

from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from app import process_reservations

MARKER = "REPROSEED_RESERVATION_OVERBOOK"


def check(database: Path) -> int:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        submitted = {
            row[0]
            for row in connection.execute("SELECT id FROM reservations WHERE status = 'submitted'")
        }
        rows = connection.execute(
            """
            SELECT reservation_lines.reservation_id, reservation_lines.lot_id,
                   reservation_lines.quantity, stock_lots.capacity
            FROM reservation_lines
            JOIN reservations ON reservations.id = reservation_lines.reservation_id
            JOIN stock_lots ON stock_lots.id = reservation_lines.lot_id
            WHERE reservations.status = 'submitted'
            ORDER BY reservation_lines.id
            """
        ).fetchall()
    decisions = process_reservations(database)
    if set(decisions) != submitted or any(
        type(accepted) is not bool for accepted in decisions.values()
    ):
        print("Unexpected reservation result", file=sys.stderr)
        return 2
    demands: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    capacities: dict[int, int] = {}
    for reservation_id, lot_id, quantity, capacity in rows:
        demands[reservation_id][lot_id] += quantity
        capacities[lot_id] = capacity
    accepted_totals: dict[int, int] = defaultdict(int)
    accepted_reservations: dict[int, set[int]] = defaultdict(set)
    for reservation_id in sorted(decisions):
        accepted = decisions[reservation_id]
        individually_fits = bool(demands[reservation_id]) and all(
            quantity <= capacities[lot_id] for lot_id, quantity in demands[reservation_id].items()
        )
        fits_remaining = bool(demands[reservation_id]) and all(
            quantity <= capacities[lot_id] - accepted_totals[lot_id]
            for lot_id, quantity in demands[reservation_id].items()
        )
        # A correct processor may reject a request after previous acceptances
        # consume stock. Individual over-allocation or a needless rejection is
        # a different defect, rather than this aggregate accounting failure.
        if (accepted and not individually_fits) or (not accepted and fits_remaining):
            print("Unexpected individual reservation decision", file=sys.stderr)
            return 2
        if accepted:
            for lot_id, quantity in demands[reservation_id].items():
                accepted_totals[lot_id] += quantity
                accepted_reservations[lot_id].add(reservation_id)
    if any(
        total > capacities[lot_id] and len(accepted_reservations[lot_id]) >= 2
        for lot_id, total in accepted_totals.items()
    ):
        print(MARKER)
        return 44
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: oracle.py DATABASE", file=sys.stderr)
        return 2
    try:
        return check(Path(sys.argv[1]))
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        print("Reservation processor could not be checked", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
