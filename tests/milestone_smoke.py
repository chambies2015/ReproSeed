"""Measure real synthetic workflows, including an optional installed-wheel CLI.

Use a new --directory for every run. This recipe keeps evidence there and replays
each bundle from an OS temporary directory outside the checkout after making the
original fixture, assets, and bundle paths unavailable. It uses no network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
EXAMPLES = {
    "duplicate_export": (2430, 8),
    "threshold": (11, 3),
    "reservation_overbook": (3500, 12),
    "approval_cycle": (1500, 10),
    "text_key_entitlements": (800, 12),
    "composite_billing": (1200, 16),
}


def hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


@dataclass
class DatabaseState:
    schema: list[tuple[Any, ...]]
    metadata: dict[str, Any]
    rows: dict[str, set[tuple[Any, ...]]]

    @property
    def counts(self) -> dict[str, int]:
        return {table: len(rows) for table, rows in self.rows.items()}


def database_state(database: Path) -> DatabaseState:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        schema = [
            row
            for row in connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name"
            )
            if not row[1].startswith("sqlite_")
        ]
        tables = [row[1] for row in schema if row[0] == "table"]
        rows = {table: set(connection.execute(f"SELECT * FROM {quote(table)}")) for table in tables}
        metadata = {
            "user_version": connection.execute("PRAGMA user_version").fetchone()[0],
            "application_id": connection.execute("PRAGMA application_id").fetchone()[0],
            "storage_layouts": {
                row[1]: {"without_rowid": bool(row[4]), "strict": bool(row[5])}
                for row in connection.execute("PRAGMA table_list")
                if row[0] == "main" and row[1] in tables
            },
            "tables": {
                table: {
                    "columns": connection.execute(f"PRAGMA table_xinfo({quote(table)})").fetchall(),
                    "foreign_keys": connection.execute(
                        f"PRAGMA foreign_key_list({quote(table)})"
                    ).fetchall(),
                    "indexes": connection.execute(f"PRAGMA index_list({quote(table)})").fetchall(),
                    "index_columns": {
                        index[1]: connection.execute(
                            f"PRAGMA index_xinfo({quote(index[1])})"
                        ).fetchall()
                        for index in connection.execute(f"PRAGMA index_list({quote(table)})")
                    },
                }
                for table in tables
            },
        }
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    return DatabaseState(schema, metadata, rows)


def retained_values_preserved(original: DatabaseState, final: DatabaseState) -> None:
    assert final.schema == original.schema
    assert final.metadata == original.metadata
    assert final.rows.keys() == original.rows.keys()
    for table, rows in final.rows.items():
        assert rows <= original.rows[table], f"Retained values changed in {table}"


def specific_application_failure(
    example: str, source_root: Path, database: Path, python: Path, directory: Path
) -> None:
    """Check actual app decisions and relational causes without trusting its oracle."""
    if example not in {
        "reservation_overbook",
        "approval_cycle",
        "text_key_entitlements",
        "composite_billing",
    }:
        return
    decisions = json.loads(
        succeeded(run([str(python), str(source_root / "app.py"), str(database)], directory))
    )
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        if example == "reservation_overbook":
            demands = connection.execute(
                """
                SELECT reservations.id, stock_lots.id, stock_lots.capacity,
                       SUM(reservation_lines.quantity)
                FROM reservations
                JOIN reservation_lines ON reservation_lines.reservation_id = reservations.id
                JOIN stock_lots ON stock_lots.id = reservation_lines.lot_id
                WHERE reservations.status = 'submitted'
                GROUP BY reservations.id, stock_lots.id
                """
            ).fetchall()
            per_lot: dict[int, list[tuple[int, int, int]]] = {}
            for reservation, lot, capacity, quantity in demands:
                assert decisions[str(reservation)] is True
                assert quantity <= capacity
                per_lot.setdefault(lot, []).append((reservation, capacity, quantity))
            assert any(
                len(requests) >= 2 and sum(request[2] for request in requests) > requests[0][1]
                for requests in per_lot.values()
            ), "No individually valid accepted reservations actually overbook stock"
        elif example == "approval_cycle":
            cycles = connection.execute(
                """
                SELECT a.id, b.id, a.workflow_id, b.workflow_id
                FROM "approval steps" a
                JOIN "approval steps" b ON a.depends_on_id = b.id AND b.depends_on_id = a.id
                WHERE a.id <> b.id
                """
            ).fetchall()
            assert len(cycles) == 2, "The retained failure must be one genuine two-node cycle"
            assert len({row[2] for row in cycles}) == 1
            assert all(row[2] == row[3] and decisions[str(row[2])] is True for row in cycles)
            assert connection.execute('SELECT COUNT(*) FROM "approval activity"').fetchone() == (0,)
        elif example == "text_key_entitlements":
            grants = connection.execute(
                """
                SELECT event_receipts.id, accounts.tenant_id, events.external_reference,
                       events.account_id, entitlements.account_id
                FROM event_receipts
                JOIN events ON events.id = event_receipts.event_id
                JOIN accounts ON accounts.id = events.account_id
                JOIN entitlements ON entitlements.id = events.entitlement_id
                WHERE event_receipts.status = 'pending' AND events.operation = 'grant'
                      AND entitlements.enabled = 1
                ORDER BY event_receipts.id
                """
            ).fetchall()
            scoped_seen: set[tuple[int, str]] = set()
            accepted_tenants: dict[str, set[int]] = {}
            suppressed = False
            for receipt, tenant, reference, account, owner in grants:
                assert account == owner
                actual = decisions[str(receipt)]
                if (tenant, reference) not in scoped_seen and actual is False:
                    assert accepted_tenants.get(reference, set()) - {tenant}
                    suppressed = True
                if actual is True:
                    accepted_tenants.setdefault(reference, set()).add(tenant)
                scoped_seen.add((tenant, reference))
            assert suppressed, "No valid grant was suppressed by another tenant's event reference"
        else:
            paid = {
                (decision["tenant_id"], decision["invoice_no"]): decision["paid"]
                for decision in decisions
            }
            invoices = connection.execute(
                """
                SELECT invoices.tenant_id, invoices.invoice_no, invoices.total_cents,
                       COALESCE((SELECT SUM(amount_cents) FROM invoice_lines
                                 WHERE invoice_lines.tenant_id = invoices.tenant_id
                                   AND invoice_lines.invoice_no = invoices.invoice_no), 0),
                       COALESCE((SELECT SUM(amount_cents) FROM payments
                                 WHERE payments.tenant_id = invoices.tenant_id
                                   AND payments.invoice_no = invoices.invoice_no
                                   AND payments.state = 'settled'), 0),
                       COALESCE((SELECT SUM(refunds.amount_cents) FROM refunds
                                 JOIN payments ON payments.id = refunds.payment_id
                                 WHERE payments.tenant_id = invoices.tenant_id
                                   AND payments.invoice_no = invoices.invoice_no
                                   AND payments.state = 'settled'
                                   AND refunds.state = 'settled'), 0)
                FROM invoices
                """
            ).fetchall()
            assert any(
                paid[(tenant, number)] is True
                and total > 0
                and lines == total
                and refunds > 0
                and settled - refunds < total <= settled + refunds
                for tenant, number, total, lines, settled, refunds in invoices
            ), "No invoice was falsely marked paid by adding settled refunds"


def run(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=300,
        check=False,
    )


def succeeded(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return result.stdout


def _diagnose(
    cli: list[str], config: Path, directory: Path, counts: dict[str, int], execute: bool
) -> dict[str, Any]:
    arguments = ["diagnose", "--config", str(config)]
    if execute:
        arguments.append("--allow-exec")
    output = succeeded(run([*cli, *arguments, "--format", "json"], directory))
    result = json.loads(output)
    label = "baseline" if execute else "static"
    (directory / f"diagnose-{label}.json").write_text(output, encoding="utf-8")
    assert result["diagnostic_version"] == 1
    assert result["snapshot_acquired"] is True
    assert result["schema_supported"] is True
    assert result["structurally_suitable"] is True
    assert result["table_counts"] == counts
    assert result["total_rows"] == sum(counts.values())
    assert result["oracle_executed"] is execute
    assert result["baseline_confirmed"] is execute
    assert result["actual_invocations"] == (3 if execute else 0)
    assert result["unknown_interrupted_launches"] == 0
    assert result["error"] is None
    if execute:
        assert len(result["baseline_results"]) == 3
        assert all(
            record["outcome"] == "TARGET_FAILURE" and record["executed"] is True
            for record in result["baseline_results"]
        )
    else:
        assert result["baseline_results"] == []
        # The text command exercises the default format without a second baseline run.
        text = succeeded(run([*cli, *arguments], directory))
        (directory / "diagnose-static.txt").write_text(text, encoding="utf-8")
        assert "Oracle: not executed" in text
        assert "Baseline reproduction: not established" in text
        for table, count in counts.items():
            assert f"{json.dumps(table)}: {count}" in text
    return result


def exercise_example(
    example: str,
    directory: Path,
    *,
    python: Path = Path(sys.executable),
    cli: list[str] | None = None,
    small_text_fixture: bool = False,
    small_composite_fixture: bool = False,
    without_rowid_billing_fixture: bool = False,
) -> dict[str, Any]:
    """Run one complete real workflow; raise on any contract or row-target failure."""
    directory.mkdir(parents=True, exist_ok=False)
    directory = directory.resolve()
    command = cli if cli is not None else [str(python), "-m", "reproseed"]
    source_root = directory / "example"
    source_root.mkdir()
    for asset in (REPOSITORY / "examples" / example).iterdir():
        if asset.suffix in {".py", ".toml"}:
            shutil.copy2(asset, source_root / asset.name)
    source = source_root / "fixture.sqlite3"
    config = source_root / "reproseed.toml"
    small = (small_text_fixture and example == "text_key_entitlements") or (
        small_composite_fixture and example == "composite_billing"
    )
    generator_flags = ["--small"] if small else []
    without_rowid = without_rowid_billing_fixture and example == "composite_billing"
    if without_rowid:
        generator_flags.append("--without-rowid")
    succeeded(
        run(
            [str(python), str(source_root / "generate.py"), str(source), *generator_flags],
            directory,
        )
    )
    original = database_state(source)
    original_rows = sum(original.counts.values())
    minimum_rows, maximum_rows = EXAMPLES[example]
    if small:
        minimum_rows = maximum_rows = 8 if example == "composite_billing" else 10
    assert original_rows >= minimum_rows
    if example in {"duplicate_export", "threshold"}:
        assert original_rows == minimum_rows
    if example == "duplicate_export":
        assert original.counts == {"entries": 2400, "owners": 6, "projects": 24}
    if example == "composite_billing":
        assert original.metadata["storage_layouts"] == {
            table: {"without_rowid": without_rowid and table != "payments", "strict": False}
            for table in original.rows
        }
    deterministic = directory / "deterministic.sqlite3"
    succeeded(
        run(
            [str(python), str(source_root / "generate.py"), str(deterministic), *generator_flags],
            directory,
        )
    )
    assert deterministic.read_bytes() == source.read_bytes(), "Generator is not deterministic"
    deterministic.unlink()
    source_before = hashes(source_root)
    raw_config = tomllib.loads(config.read_text(encoding="utf-8"))
    oracle = raw_config["oracle"]
    independent = run([str(python), str(source_root / "oracle.py"), str(source)], directory)
    assert independent.returncode == oracle["expected_exit"], independent.stderr
    assert independent.stdout.splitlines() == [oracle["marker"]]
    assert independent.stderr == ""
    (directory / "independent-oracle.json").write_text(
        json.dumps(
            {"exit_code": independent.returncode, "marker": oracle["marker"], "stream": "stdout"},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    static = _diagnose(command, config, directory, original.counts, False)
    baseline = _diagnose(command, config, directory, original.counts, True)
    assert hashes(source_root) == source_before
    bundle = directory / "bundle"
    started = time.monotonic()
    reduction_output = succeeded(
        run(
            [*command, "reduce", "--config", str(config), "--out", str(bundle), "--allow-exec"],
            directory,
        )
    )
    reduction_seconds = time.monotonic() - started
    (directory / "reduction.json").write_text(reduction_output, encoding="utf-8")
    assert hashes(source_root) == source_before
    final = database_state(bundle / "fixture.sqlite3")
    retained_values_preserved(original, final)
    specific_application_failure(
        example, source_root, bundle / "fixture.sqlite3", python, directory
    )
    final_rows = sum(final.counts.values())
    assert 0 < final_rows <= maximum_rows
    if example == "threshold":
        assert final.counts == {"crates": 1, "parcels": 2}
    elif example == "duplicate_export":
        assert final_rows >= 5
        assert final.counts["owners"] >= 1
        assert final.counts["projects"] >= 2
        assert final.counts["entries"] >= 2
    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    assert report["original_counts"] == original.counts
    assert report["final_counts"] == final.counts
    assert report["max_invocations"] == raw_config["reduction"]["max_invocations"]
    assert 6 <= report["oracle_invocations"] <= report["max_invocations"]
    for field in ("baseline_verification", "final_verification"):
        assert len(report[field]) == 3
        assert all(
            record["outcome"] == "TARGET_FAILURE"
            and record["exit_code"] == oracle["expected_exit"]
            and record["executed"] is True
            for record in report[field]
        )
    assert report["cache_hits"] == sum(attempt["cached"] for attempt in report["attempts"])
    assert report["unresolved_attempts"] == sum(
        attempt["outcome"] == "UNRESOLVED" for attempt in report["attempts"]
    )
    assert report["invalid_candidates"] == sum(
        attempt["outcome"] == "DATABASE_INVALID" for attempt in report["attempts"]
    )
    fresh_results = [
        *report["baseline_verification"],
        *report["final_verification"],
        *[
            result
            for attempt in report["attempts"]
            if not attempt["cached"]
            for result in attempt["confirmations"]
        ],
    ]
    assert sum(result["executed"] for result in fresh_results) == report["oracle_invocations"]
    oracle_seconds = sum(result["duration_seconds"] for result in fresh_results)
    bundle_before = hashes(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"] == {
        name: digest for name, digest in bundle_before.items() if name != "manifest.json"
    }
    for format_name, arguments in (
        ("default", []),
        ("json", ["--format", "json"]),
        ("text", ["--format", "text"]),
    ):
        output = succeeded(run([*command, "inspect", str(bundle), *arguments], directory))
        suffix = "txt" if format_name == "text" else "json"
        (directory / f"inspect-{format_name}.{suffix}").write_text(output, encoding="utf-8")
        if format_name == "text":
            assert f"Rows: {original_rows} original -> {final_rows} retained" in output
            assert "Recorded final confirmations: 3/3 TARGET_FAILURE" in output
            assert "New replay: not performed by inspect" in output
        else:
            assert json.loads(output) == report
    assert hashes(bundle) == bundle_before
    source_size = source.stat().st_size
    final_size = (bundle / "fixture.sqlite3").stat().st_size
    unavailable_source = directory / "example-unavailable"
    unavailable_bundle = directory / "bundle-unavailable"
    with tempfile.TemporaryDirectory(prefix="reproseed-milestone-relocated-") as temporary:
        outside = Path(temporary).resolve()
        assert not outside.is_relative_to(REPOSITORY.resolve())
        relocated = outside / "bundle"
        shutil.copytree(bundle, relocated)
        source_root.rename(unavailable_source)
        bundle.rename(unavailable_bundle)
        assert not source_root.exists() and not bundle.exists()
        working = outside / "unrelated-cwd"
        working.mkdir()
        replay_output = succeeded(
            run([*command, "replay", str(relocated), "--allow-exec"], working)
        )
        replay = json.loads(replay_output)
        (directory / "replay.json").write_text(replay_output, encoding="utf-8")
        assert replay["outcome"] == "TARGET_FAILURE"
        assert len(replay["confirmations"]) == 3
        assert all(
            record["outcome"] == "TARGET_FAILURE"
            and record["executed"] is True
            and record["exit_code"] == oracle["expected_exit"]
            for record in replay["confirmations"]
        )
        assert hashes(relocated) == bundle_before
    assert hashes(unavailable_source) == source_before
    assert hashes(unavailable_bundle) == bundle_before
    measurement = {
        "example": example,
        "without_rowid_billing_fixture": without_rowid,
        "generator_flags": generator_flags,
        "original_counts": original.counts,
        "final_counts": final.counts,
        "original_rows": original_rows,
        "final_rows": final_rows,
        "oracle_invocations": report["oracle_invocations"],
        "max_invocations": report["max_invocations"],
        "budget_charged_invocations": report["budget_charged_invocations"],
        "unknown_interrupted_launches": report["unknown_interrupted_launches"],
        "cache_hits": report["cache_hits"],
        "accepted_reductions": len(report["accepted_reductions"]),
        "unresolved_attempts": report["unresolved_attempts"],
        "invalid_candidates": report["invalid_candidates"],
        "termination_reason": report["termination_reason"],
        "reduction_wall_seconds": reduction_seconds,
        "fresh_oracle_duration_seconds": oracle_seconds,
        "reduction_other_seconds_estimate": reduction_seconds - oracle_seconds,
        "source_bytes": source_size,
        "final_fixture_bytes": final_size,
        "runtime": manifest["runtime"],
        "static_diagnosis": static,
        "baseline_diagnosis": baseline,
        "final_confirmations": report["final_verification"],
        "relocated_replay_confirmations": replay["confirmations"],
        "source_hashes_before_and_after": source_before,
        "bundle_hashes_before_and_after": bundle_before,
        "source_and_bundle_unchanged": True,
        "schema_metadata_and_retained_values_preserved": True,
        "integrity_and_foreign_keys_valid": True,
    }
    (directory / "measurement.json").write_text(
        json.dumps(measurement, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return measurement


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument(
        "--cli", type=Path, help="Installed console script; uses --python's runtime"
    )
    parser.add_argument("--examples", nargs="+", choices=tuple(EXAMPLES), default=list(EXAMPLES))
    parser.add_argument(
        "--small-text-fixture",
        action="store_true",
        help="Use ten TEXT rows for installed-wheel smoke; full acceptance uses 970 rows.",
    )
    parser.add_argument(
        "--small-composite-fixture",
        action="store_true",
        help="Use eight genuine billing rows for installed-wheel smoke; full fixture has 1308.",
    )
    parser.add_argument(
        "--without-rowid-billing-fixture",
        action="store_true",
        help="Use the mixed-layout WITHOUT ROWID variant of composite_billing.",
    )
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    # POSIX virtual-environment interpreters commonly symlink to a global Python.
    # Keep their lexical paths: resolving the link discards the selected venv.
    python = arguments.python.absolute()
    cli = [str(arguments.cli.absolute())] if arguments.cli else [str(python), "-m", "reproseed"]
    runtime_code = (
        "import json, platform, sqlite3, sys, reproseed; "
        "print(json.dumps({'python':sys.version,'sqlite':sqlite3.sqlite_version,"
        "'os':platform.platform(),'reproseed_module':reproseed.__file__}))"
    )
    runtime = json.loads(succeeded(run([str(python), "-c", runtime_code], directory)))
    if arguments.cli:
        assert not Path(runtime["reproseed_module"]).resolve().is_relative_to(REPOSITORY.resolve())
    succeeded(run([*cli, "--help"], directory))
    measurements = [
        exercise_example(
            example,
            directory / example,
            python=python,
            cli=cli,
            small_text_fixture=arguments.small_text_fixture,
            small_composite_fixture=arguments.small_composite_fixture,
            without_rowid_billing_fixture=arguments.without_rowid_billing_fixture,
        )
        for example in arguments.examples
    ]
    result = {"runtime": runtime, "examples": measurements}
    output = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    (directory / "measurements.json").write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
