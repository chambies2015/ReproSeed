"""Exercise a concrete wheel as a simulated first user, using only venv and pip.

The consumer never imports this checkout. All transient files live in a newly
created OS temporary directory outside it and are removed on success or failure.
An optional new --evidence file retains actual commands and synthetic results.
This is a developer simulation, not evidence from an independent user study.
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
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
TUTORIAL = REPOSITORY / "examples" / "threshold"
TUTORIAL_ASSETS = ("generate.py", "oracle.py", "reproseed.toml")


class SmokeError(RuntimeError):
    """A consumer action failed; never fall back to the checkout."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def consumer_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "_OLD_VIRTUAL_PATH"):
        environment.pop(name, None)
    environment.update(
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        PIP_CONFIG_FILE=os.devnull,
        PIP_NO_INPUT="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    return environment


def hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


class Commands:
    def __init__(self, evidence: dict[str, Any], environment: dict[str, str]) -> None:
        self.records: list[dict[str, Any]] = []
        evidence["commands"] = self.records
        self.environment = environment

    def run(
        self, argv: list[str], cwd: Path, *, timeout: float = 45, expected_exit: int = 0
    ) -> str:
        started = time.monotonic()
        record: dict[str, Any] = {
            "argv": argv,
            "cwd": str(cwd),
            "timeout_seconds": timeout,
            "expected_exit": expected_exit,
        }
        self.records.append(record)
        try:
            result = subprocess.run(
                argv,
                cwd=cwd,
                env=self.environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            record.update(error=str(error), elapsed_seconds=time.monotonic() - started)
            raise SmokeError(f"Consumer command could not complete: {argv!r}: {error}") from error
        record.update(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=time.monotonic() - started,
        )
        require(
            result.returncode == expected_exit,
            f"Consumer command {argv!r} exited {result.returncode}, expected {expected_exit}: "
            f"{result.stdout}\n{result.stderr}",
        )
        return result.stdout

    def document(self, argv: list[str], cwd: Path, *, timeout: float = 45) -> dict[str, Any]:
        output = self.run(argv, cwd, timeout=timeout)
        try:
            result = json.loads(output)
        except json.JSONDecodeError as error:
            raise SmokeError(f"Consumer command returned invalid JSON: {argv!r}") from error
        require(isinstance(result, dict), f"Consumer command returned non-object JSON: {argv!r}")
        return result


def validate_import_origin(runtime: dict[str, Any], installation: Path) -> None:
    origin = Path(runtime["reproseed_module"]).resolve()
    # On Windows getsitepackages() also lists the venv root. That root alone
    # does not establish an installed wheel's site-packages origin.
    site_directories = [
        Path(name).resolve()
        for name in runtime["site_packages"]
        if Path(name).name.casefold() == "site-packages"
    ]
    require(
        origin.is_relative_to(installation.resolve())
        and not origin.is_relative_to(REPOSITORY.resolve())
        and any(origin.is_relative_to(directory) for directory in site_directories),
        f"ReproSeed import did not originate in the fresh installation's site-packages: {origin}",
    )
    require(
        Path(runtime["prefix"]).resolve() == installation.resolve(),
        "The consumer interpreter did not use the fresh virtual environment",
    )
    require(
        all(
            not Path(name).resolve().is_relative_to(REPOSITORY.resolve())
            for name in runtime["path"]
        ),
        "The consumer import path contains the source checkout",
    )


def target_confirmations(records: list[dict[str, Any]], expected_exit: int) -> None:
    require(len(records) == 3, "Expected exactly three fresh target confirmations")
    require(
        all(
            record["outcome"] == "TARGET_FAILURE"
            and record["executed"] is True
            and record["exit_code"] == expected_exit
            for record in records
        ),
        "A fresh confirmation did not reproduce the exact target",
    )


def database_rows(database: Path) -> tuple[list[tuple[Any, ...]], dict[str, set[tuple[Any, ...]]]]:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        require(
            connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
            "Fixture integrity check did not pass",
        )
        require(
            connection.execute("PRAGMA foreign_key_check").fetchall() == [],
            "Fixture foreign-key check did not pass",
        )
        schema = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' "
            "ORDER BY type,name"
        ).fetchall()
        rows = {
            table: set(connection.execute(f'SELECT * FROM "{table}"'))
            for table in ("crates", "parcels")
        }
    return schema, rows


def exercise_consumer(
    wheel: Path,
    outside: Path,
    evidence: dict[str, Any],
    *,
    audit: bool,
    existing_applications: bool,
) -> None:
    environment = consumer_environment()
    commands = Commands(evidence, environment)
    evidence["environment"] = {
        "PYTHONPATH_removed": "PYTHONPATH" not in environment,
        "PYTHONHOME_removed": "PYTHONHOME" not in environment,
        "consumer_directory": str(outside),
        "consumer_outside_checkout": True,
        "network_required": False,
    }
    installation = outside / "fresh installation café"
    commands.run([sys.executable, "-m", "venv", str(installation)], outside, timeout=90)
    bin_directory = installation / ("Scripts" if os.name == "nt" else "bin")
    # Retain POSIX interpreter symlinks: resolving them discards venv selection.
    python = bin_directory / ("python.exe" if os.name == "nt" else "python")
    cli = bin_directory / ("reproseed.exe" if os.name == "nt" else "reproseed")
    commands.run(
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
        outside,
        timeout=90,
    )
    runtime = commands.document(
        [
            str(python),
            "-c",
            "import importlib.metadata,json,os,platform,site,sqlite3,sys,reproseed; "
            "print(json.dumps({'python':sys.version,'sqlite':sqlite3.sqlite_version,"
            "'platform':platform.platform(),'reproseed_module':reproseed.__file__,"
            "'version':importlib.metadata.version('reproseed'),'prefix':sys.prefix,"
            "'site_packages':site.getsitepackages(),"
            "'path':[os.path.abspath(p) for p in sys.path]}))",
        ],
        outside,
    )
    validate_import_origin(runtime, installation)
    evidence["runtime"] = runtime
    require(
        commands.run([str(cli), "--version"], outside).strip() == runtime["version"],
        "Installed console version differs from installed metadata",
    )
    require(
        "diagnose" in commands.run([str(cli), "--help"], outside),
        "Installed console help lacks the documented diagnostic command",
    )
    project = outside / "ReproSeed tutorial café [first use]"
    project.mkdir()
    for name in TUTORIAL_ASSETS:
        shutil.copy2(TUTORIAL / name, project / name)
    evidence["tutorial_assets"] = hashes(project)
    source = project / "fixture.sqlite3"
    config = project / "reproseed.toml"
    contract = tomllib.loads(config.read_text(encoding="utf-8"))
    oracle = contract["oracle"]
    commands.run([str(python), str(project / "generate.py"), str(source)], outside)
    original_schema, original_rows = database_rows(source)
    source_before = hashes(project)
    require(
        {table: len(rows) for table, rows in original_rows.items()} == {"crates": 3, "parcels": 8},
        "Tutorial generator did not produce the documented 11 rows",
    )
    # Establish that the oracle depends on the SQLite data, with a fresh nonfailure copy.
    oracle_argv = [str(python), str(project / "oracle.py")]
    require(
        commands.run(
            [*oracle_argv, str(source)], outside, expected_exit=oracle["expected_exit"]
        ).splitlines()
        == [oracle["marker"]],
        "Tutorial oracle did not emit the exact whole-line target marker",
    )
    nonfailure = outside / "nonfailure.sqlite3"
    shutil.copy2(source, nonfailure)
    with closing(sqlite3.connect(nonfailure)) as connection, connection:
        connection.execute("UPDATE parcels SET mass=0")
    require(
        commands.run([*oracle_argv, str(nonfailure)], outside) == "",
        "Tutorial oracle emitted a failure for a nonfailing data set",
    )
    static_text = commands.run([str(cli), "diagnose", "--config", str(config)], outside)
    require(
        "Oracle: not executed" in static_text and "not established" in static_text,
        "Static diagnostic text did not distinguish structure from reproduction",
    )
    diagnoses = {}
    for execute in (False, True):
        argv = [str(cli), "diagnose", "--config", str(config), "--format", "json"]
        if execute:
            argv.append("--allow-exec")
        diagnosis = commands.document(argv, outside)
        require(
            diagnosis["diagnostic_version"] == 1
            and diagnosis["structurally_suitable"] is True
            and diagnosis["table_counts"] == {"crates": 3, "parcels": 8}
            and diagnosis["total_rows"] == 11
            and diagnosis["oracle_executed"] is execute
            and diagnosis["baseline_confirmed"] is execute
            and diagnosis["actual_invocations"] == (3 if execute else 0)
            and diagnosis["unknown_interrupted_launches"] == 0
            and diagnosis["error"] is None,
            "Diagnostic did not match the documented static/executable contract",
        )
        if execute:
            target_confirmations(diagnosis["baseline_results"], oracle["expected_exit"])
        else:
            require(diagnosis["baseline_results"] == [], "Static diagnosis executed an oracle")
        diagnoses["baseline" if execute else "static"] = diagnosis
    bundle = outside / "new bundle café"
    events = outside / "reduction events café.jsonl"
    reduction = commands.document(
        [
            str(cli),
            "reduce",
            "--config",
            str(config),
            "--out",
            str(bundle),
            "--allow-exec",
            "--progress",
            "--events",
            str(events),
        ],
        outside,
        timeout=120,
    )
    require(reduction["verified"] is True, "Reduction did not publish a verified bundle")
    require(
        "ReproSeed" in str(commands.records[-1]["stderr"])
        or "reproseed" in str(commands.records[-1]["stderr"]),
        "Opt-in progress was not written to stderr",
    )
    event_records = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    require(
        bool(event_records)
        and all(record["event_version"] == 1 for record in event_records)
        and [record["sequence"] for record in event_records]
        == list(range(1, len(event_records) + 1))
        and event_records[-1]["event"] == "completed"
        and event_records[-1]["phase"] == "run"
        and event_records[-1]["known_executions"] == reduction["oracle_invocations"],
        "Installed progress event stream did not complete with consistent accounting",
    )
    require(not (bundle / events.name).exists(), "External event file was included in bundle")
    evidence["progress_events"] = event_records
    require(hashes(project) == source_before, "Diagnosis or reduction changed original input files")
    bundle_before = hashes(bundle)
    report = commands.document([str(cli), "inspect", str(bundle)], outside)
    require(
        report
        == commands.document([str(cli), "inspect", str(bundle), "--format", "json"], outside),
        "Default and explicit JSON inspection disagree",
    )
    inspection = commands.run([str(cli), "inspect", str(bundle), "--format", "text"], outside)
    require(
        "Rows: 11 original -> 3 retained" in inspection
        and "Recorded final confirmations: 3/3 TARGET_FAILURE" in inspection
        and "New replay: not performed by inspect" in inspection,
        "Text inspection did not explain recorded evidence and retained counts",
    )
    require(
        report["original_counts"] == {"crates": 3, "parcels": 8}
        and report["final_counts"] == {"crates": 1, "parcels": 2}
        and report["verified"] is True
        and 6 <= report["oracle_invocations"] <= contract["reduction"]["max_invocations"],
        "Reduction report did not preserve tutorial counts or the invocation bound",
    )
    target_confirmations(report["baseline_verification"], oracle["expected_exit"])
    target_confirmations(report["final_verification"], oracle["expected_exit"])
    final_schema, final_rows = database_rows(bundle / "fixture.sqlite3")
    require(
        final_schema == original_schema
        and all(rows <= original_rows[table] for table, rows in final_rows.items()),
        "Reduction changed the declared schema or retained values",
    )
    require(hashes(bundle) == bundle_before, "Inspection changed supplied bundle files")
    relocated = outside / "relocated bundle café"
    shutil.copytree(bundle, relocated)
    unavailable_project = outside / "original project unavailable"
    unavailable_bundle = outside / "original bundle unavailable"
    project.rename(unavailable_project)
    bundle.rename(unavailable_bundle)
    require(
        not project.exists()
        and not config.exists()
        and not source.exists()
        and not bundle.exists(),
        "Original project/configuration/source/bundle paths remain available",
    )
    unrelated = outside / "unrelated working directory"
    unrelated.mkdir()
    replay = commands.document([str(cli), "replay", str(relocated), "--allow-exec"], unrelated)
    require(replay["outcome"] == "TARGET_FAILURE", "Relocated replay did not reproduce the target")
    target_confirmations(replay["confirmations"], oracle["expected_exit"])
    require(
        hashes(unavailable_project) == source_before
        and hashes(unavailable_bundle) == bundle_before
        and hashes(relocated) == bundle_before,
        "Replay changed source or supplied bundle files",
    )
    evidence["workflow"] = {
        "diagnoses": diagnoses,
        "reduction": reduction,
        "replay": replay,
        "source_hashes_before_and_after": source_before,
        "bundle_hashes_before_and_after": bundle_before,
        "source_and_bundle_unchanged": True,
        "schema_and_retained_values_preserved": True,
        "integrity_and_foreign_keys_valid": True,
        "nonfailure_oracle_exit": 0,
    }
    if audit:
        evidence["error_audit"] = commands.document(
            [
                str(python),
                str(REPOSITORY / "tests" / "error_smoke.py"),
                "--python",
                str(python),
                "--cli",
                str(cli),
                "--directory",
                str(outside / "error audit"),
            ],
            unrelated,
            timeout=180,
        )
    if existing_applications:
        # Preserve existing hosted wheel coverage without repeating large reductions.
        small_applications = (
            ("text-key", ["--examples", "text_key_entitlements", "--small-text-fixture"]),
            ("composite-key", ["--examples", "composite_billing", "--small-composite-fixture"]),
            (
                "without-rowid",
                [
                    "--examples",
                    "composite_billing",
                    "--small-composite-fixture",
                    "--without-rowid-billing-fixture",
                ],
            ),
        )
        measurements = {}
        for label, flags in small_applications:
            directory = outside / f"{label} installed-wheel smoke"
            commands.run(
                [
                    str(python),
                    str(REPOSITORY / "tests" / "milestone_smoke.py"),
                    "--directory",
                    str(directory),
                    "--python",
                    str(python),
                    "--cli",
                    str(cli),
                    *flags,
                ],
                unrelated,
                timeout=180,
            )
            measurements[label] = json.loads((directory / "measurements.json").read_text("utf-8"))
        evidence["existing_application_measurements"] = measurements


def run_smoke(
    wheel: Path,
    evidence: dict[str, Any],
    *,
    audit: bool = False,
    existing_applications: bool = False,
) -> None:
    wheel = wheel.resolve(strict=True)
    require(wheel.is_file() and wheel.suffix == ".whl", "--wheel must name a concrete built wheel")
    wheel_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
    evidence.update(
        evidence_version=1,
        study="simulated first-user journey",
        wheel=str(wheel),
        wheel_sha256=wheel_hash,
        status="running",
    )
    with tempfile.TemporaryDirectory(prefix="reproseed consumer café ") as temporary:
        outside = Path(temporary).resolve()
        require(
            not outside.is_relative_to(REPOSITORY.resolve()),
            "Consumer temporary directory is inside the source checkout; use an external TMPDIR",
        )
        try:
            exercise_consumer(
                wheel, outside, evidence, audit=audit, existing_applications=existing_applications
            )
        finally:
            # The context manager removes only this newly acquired, tool-owned root.
            evidence["consumer_temporary_directory"] = str(outside)
    require(not outside.exists(), "Consumer temporary state was not cleaned up")
    require(
        hashlib.sha256(wheel.read_bytes()).hexdigest() == wheel_hash,
        "Installation changed the wheel",
    )
    evidence.update(status="passed", temporary_state_cleaned=True, wheel_unchanged=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel", type=Path, required=True, help="Concrete already-built .whl path"
    )
    parser.add_argument(
        "--evidence", type=Path, help="New local JSON file; never overwrites existing evidence"
    )
    parser.add_argument(
        "--audit-errors", action="store_true", help="Also exercise installed negative-path audit"
    )
    parser.add_argument(
        "--existing-applications",
        action="store_true",
        help="Retain small TEXT/composite/WITHOUT ROWID installed-wheel workflows for CI",
    )
    arguments = parser.parse_args()
    evidence: dict[str, Any] = {}
    if arguments.evidence is not None and arguments.evidence.exists():
        parser.error("--evidence must be a new file")
    try:
        run_smoke(
            arguments.wheel,
            evidence,
            audit=arguments.audit_errors,
            existing_applications=arguments.existing_applications,
        )
        exit_code = 0
    except (OSError, SmokeError) as error:
        evidence.update(status="failed", error=str(error))
        temporary = evidence.get("consumer_temporary_directory")
        if temporary is not None:
            evidence["temporary_state_cleaned"] = not Path(temporary).exists()
        print(f"External consumer smoke failed: {error}", file=sys.stderr)
        exit_code = 1
    output = json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.evidence is not None:
        with arguments.evidence.open("x", encoding="utf-8") as destination:
            destination.write(output)
    print(output, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
