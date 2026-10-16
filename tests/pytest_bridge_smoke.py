"""Verify offline installed-wheel consumers of the explicitly invoked pytest bridge.

Consumer A has only the ReproSeed wheel. Consumer B additionally installs a
specific pytest version from an explicit owned wheelhouse. Lifecycle commands
run outside the source checkout, in standard venvs, without source imports.
Use --full for the additional 2,430-row acceptance case; default smoke is small.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
import tomllib
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from external_consumer_smoke import (
    Commands,
    consumer_environment,
    exercise_consumer,
    hashes,
    require,
    target_confirmations,
    validate_import_origin,
)
from milestone_smoke import database_state, retained_values_preserved

REPOSITORY = Path(__file__).resolve().parents[1]
PREPARE = REPOSITORY / "examples" / "pytest_duplicate_export" / "prepare.py"
MARKER = "REPROSEED_PYTEST_TARGET_V1"
RUNTIME_PROBE = (
    "import importlib.metadata,importlib.util,json,os,platform,site,sqlite3,sys,reproseed; "
    "print(json.dumps({'python':sys.version,'sqlite':sqlite3.sqlite_version,"
    "'platform':platform.platform(),'reproseed_module':reproseed.__file__,"
    "'version':importlib.metadata.version('reproseed'),'prefix':sys.prefix,"
    "'site_packages':site.getsitepackages(),'path':[os.path.abspath(p) for p in sys.path],"
    "'pytest_available':importlib.util.find_spec('pytest') is not None,"
    "'dependencies':sorted([{'name':d.metadata['Name'],'version':d.version} "
    "for d in importlib.metadata.distributions()], key=lambda d:d['name'].casefold()),"
    "'mandatory_dependencies':importlib.metadata.distribution('reproseed').requires or []}))"
)


def installed_runtime(
    commands: Commands, outside: Path, installation: Path, wheel: Path
) -> tuple[Path, Path, dict[str, Any]]:
    commands.run([sys.executable, "-m", "venv", str(installation)], outside, timeout=90)
    binary = installation / ("Scripts" if os.name == "nt" else "bin")
    python = binary / ("python.exe" if os.name == "nt" else "python")
    cli = binary / ("reproseed.exe" if os.name == "nt" else "reproseed")
    commands.run(
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
        outside,
        timeout=90,
    )
    runtime = commands.document([str(python), "-c", RUNTIME_PROBE], outside)
    validate_import_origin(runtime, installation)
    require(runtime["mandatory_dependencies"] == [], "The wheel gained mandatory dependencies")
    require(runtime["pytest_available"] is False, "A fresh wheel-only venv unexpectedly has pytest")
    return python, cli, runtime


def prepare_case(commands: Commands, python: Path, outside: Path, *, full: bool) -> Path:
    case = outside / ("full pytest case café" if full else "small pytest case café")
    argv = [str(python), str(PREPARE), "--directory", str(case)]
    if not full:
        argv.append("--small")
    commands.run(argv, outside)
    # Preparation is the sole explicit source-asset copy. Every subsequent
    # execution uses this new case or an installed module, never source imports.
    return case


def bridge_argv(python: Path, case: Path) -> list[str]:
    return [
        str(python),
        "-m",
        "reproseed.pytest_oracle",
        "--target",
        str(case / "pytest-target.toml"),
        "--db",
        str(case / "fixture.sqlite3"),
        "--allow-exec",
    ]


def wheel_only(wheel: Path, outside: Path, evidence: dict[str, Any]) -> None:
    outside.mkdir()
    ordinary: dict[str, Any] = {}
    evidence["ordinary_workflow"] = ordinary
    # Reuse the established real threshold tutorial rather than substituting
    # --help for proof that ordinary no-pytest workflows still function.
    exercise_consumer(wheel, outside, ordinary, audit=False, existing_applications=False)
    runtime = ordinary["runtime"]
    installation = Path(runtime["prefix"])
    binary = installation / ("Scripts" if os.name == "nt" else "bin")
    python = binary / ("python.exe" if os.name == "nt" else "python")
    cli = binary / ("reproseed.exe" if os.name == "nt" else "reproseed")
    commands = Commands(evidence, consumer_environment())
    probe = commands.document([str(python), "-c", RUNTIME_PROBE], outside)
    validate_import_origin(probe, installation)
    require(probe["pytest_available"] is False, "Wheel-only consumer unexpectedly contains pytest")
    require(probe["mandatory_dependencies"] == [], "ReproSeed has mandatory runtime dependencies")
    evidence["runtime"] = probe
    commands.run([str(python), "-m", "reproseed.pytest_oracle", "--help"], outside)
    case = prepare_case(commands, python, outside, full=False)
    conftest_sentinel = case / "conftest-imported"
    test_sentinel = case / "test-imported"
    (case / "conftest.py").write_text(
        "from pathlib import Path\n"
        "Path(__file__).with_name('conftest-imported').write_text('executed')\n",
        encoding="utf-8",
    )
    test_path = case / "test_export.py"
    test_path.write_text(
        test_path.read_text(encoding="utf-8").replace(
            "import sqlite3\n",
            "import sqlite3\n"
            "from pathlib import Path as SentinelPath\n"
            "SentinelPath(__file__).with_name('test-imported').write_text('executed')\n",
            1,
        ),
        encoding="utf-8",
    )
    before = hashes(case)
    static = commands.document(
        [str(cli), "diagnose", "--config", str(case / "reproseed.toml"), "--format", "json"],
        outside,
    )
    require(
        static["structurally_suitable"] is True
        and static["actual_invocations"] == 0
        and static["baseline_results"] == [],
        "Static diagnosis without pytest did not remain structural",
    )
    commands.run(bridge_argv(python, case)[:-1], outside, expected_exit=2)
    missing = commands.run(bridge_argv(python, case), outside, expected_exit=2)
    require(MARKER not in missing, "Missing pytest emitted the target marker")
    require(
        not conftest_sentinel.exists() and not test_sentinel.exists() and hashes(case) == before,
        "Help, unacknowledged execution, missing pytest or static diagnose imported case code",
    )
    evidence.update(
        missing_pytest_exit=2,
        unacknowledged_exit=2,
        no_test_or_conftest_imports=True,
        static_diagnosis=static,
        source_hashes_before_and_after=before,
    )


def measure_startup(commands: Commands, python: Path, case: Path, outside: Path) -> dict[str, Any]:
    measurements: dict[str, list[float]] = {"python_noop": [], "pytest_import": [], "bridge": []}
    for name, argv, expected in (
        ("python_noop", [str(python), "-c", "pass"], 0),
        ("pytest_import", [str(python), "-c", "import pytest"], 0),
        ("bridge", bridge_argv(python, case), 86),
    ):
        for _ in range(3):
            started = time.monotonic()
            output = commands.run(argv, outside, expected_exit=expected)
            measurements[name].append(time.monotonic() - started)
            if name == "bridge":
                require(output.splitlines() == [MARKER], "Direct bridge target marker differed")
    medians = {name: statistics.median(values) for name, values in measurements.items()}
    return {
        "fresh_subprocess_wall_seconds": measurements,
        "median_seconds": medians,
        "pytest_import_minus_noop_seconds": medians["pytest_import"] - medians["python_noop"],
        "bridge_minus_noop_seconds": medians["bridge"] - medians["python_noop"],
        "limit": "Import delta estimates startup; bridge delta also includes SQLite and the test.",
    }


def exercise_pytest_case(
    commands: Commands,
    python: Path,
    cli: Path,
    outside: Path,
    *,
    full: bool,
) -> dict[str, Any]:
    case = prepare_case(commands, python, outside, full=full)
    source = case / "fixture.sqlite3"
    config = case / "reproseed.toml"
    original = database_state(source)
    original_rows = sum(original.counts.values())
    require(original_rows == (2430 if full else 10), "Prepared generator row count differed")
    require(not full or original_rows >= 2000, "Full acceptance needs at least 2,000 user rows")
    before = hashes(case)
    startup = measure_startup(commands, python, case, outside)
    diagnoses = {}
    for execute in (False, True):
        argv = [str(cli), "diagnose", "--config", str(config), "--format", "json"]
        if execute:
            argv.append("--allow-exec")
        diagnosis = commands.document(argv, outside, timeout=90)
        require(
            diagnosis["structurally_suitable"] is True
            and diagnosis["table_counts"] == original.counts
            and diagnosis["actual_invocations"] == (3 if execute else 0)
            and diagnosis["baseline_confirmed"] is execute
            and diagnosis["error"] is None,
            "Pytest-case static or executable diagnosis was inconsistent",
        )
        if execute:
            target_confirmations(diagnosis["baseline_results"], 86)
        else:
            require(diagnosis["baseline_results"] == [], "Static diagnosis executed pytest")
        diagnoses["baseline" if execute else "static"] = diagnosis
    bundle = outside / ("full pytest bundle" if full else "small pytest bundle")
    events = outside / ("full-events.jsonl" if full else "small-events.jsonl")
    started = time.monotonic()
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
        timeout=600 if full else 240,
    )
    reduction_seconds = time.monotonic() - started
    reduction_record = commands.records[-1]
    require(reduction["verified"] is True, "Pytest-driven reduction did not verify a bundle")
    require(bool(reduction_record["stderr"]), "Requested progress did not produce stderr")
    event_records = [json.loads(line) for line in events.read_text("utf-8").splitlines()]
    require(
        bool(event_records)
        and all(record["event_version"] == 1 for record in event_records)
        and [record["sequence"] for record in event_records]
        == list(range(1, len(event_records) + 1))
        and event_records[-1]["event"] == "completed"
        and event_records[-1]["known_executions"] == reduction["oracle_invocations"],
        "Progress event sequence or final invocation accounting differed",
    )
    report = commands.document([str(cli), "inspect", str(bundle)], outside)
    require(
        report
        == commands.document([str(cli), "inspect", str(bundle), "--format", "json"], outside),
        "Default and explicit JSON inspection differed",
    )
    text = commands.run([str(cli), "inspect", str(bundle), "--format", "text"], outside)
    final = database_state(bundle / "fixture.sqlite3")
    retained_values_preserved(original, final)
    final_rows = sum(final.counts.values())
    require(5 <= final_rows <= 8, "The real export collision did not reduce to at most eight rows")
    require(
        f"Rows: {original_rows} original -> {final_rows} retained" in text
        and "Recorded final confirmations: 3/3 TARGET_FAILURE" in text,
        "Text inspection omitted verified retained-row evidence",
    )
    max_invocations = tomllib.loads(config.read_text("utf-8"))["reduction"]["max_invocations"]
    require(
        report["original_counts"] == original.counts
        and report["final_counts"] == final.counts
        and 6 <= report["oracle_invocations"] <= max_invocations,
        "Report row counts or explicit invocation budget differed",
    )
    for field in ("baseline_verification", "final_verification"):
        target_confirmations(report[field], 86)
    for accepted in report["accepted_reductions"]:
        confirmations = report["attempts"][accepted["attempt"] - 1]["confirmations"]
        require(
            len(confirmations) == 2
            and all(
                result["outcome"] == "TARGET_FAILURE"
                and result["executed"] is True
                and result["exit_code"] == 86
                for result in confirmations
            ),
            "An accepted reduction lacked two target confirmations",
        )
    fresh = [
        *report["baseline_verification"],
        *report["final_verification"],
        *[
            result
            for attempt in report["attempts"]
            if not attempt["cached"]
            for result in attempt["confirmations"]
        ],
    ]
    require(
        sum(result["executed"] is True for result in fresh) == report["oracle_invocations"],
        "Report fresh invocation count differed from its evidence",
    )
    bundle_before = hashes(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text("utf-8"))
    require(
        manifest["artifacts"]
        == {name: digest for name, digest in bundle_before.items() if name != "manifest.json"},
        "Bundle manifest did not hash the complete explicit payload",
    )
    require(hashes(case) == before, "Diagnosis, bridge execution or reduction changed originals")
    relocated = outside / ("full relocated bundle café" if full else "small relocated bundle café")
    shutil.copytree(bundle, relocated)
    unavailable_case = case.with_name(case.name + " unavailable")
    unavailable_bundle = bundle.with_name(bundle.name + " unavailable")
    case.rename(unavailable_case)
    bundle.rename(unavailable_bundle)
    require(
        not case.exists() and not source.exists() and not config.exists() and not bundle.exists(),
        "Original case and bundle paths remained available during replay",
    )
    unrelated = outside / ("full unrelated cwd" if full else "small unrelated cwd")
    unrelated.mkdir()
    replay = commands.document(
        [str(cli), "replay", str(relocated), "--allow-exec"], unrelated, timeout=90
    )
    require(replay["outcome"] == "TARGET_FAILURE", "Relocated replay did not reproduce the target")
    target_confirmations(replay["confirmations"], 86)
    require(
        hashes(unavailable_case) == before
        and hashes(unavailable_bundle) == bundle_before
        and hashes(relocated) == bundle_before,
        "Relocated replay changed source or supplied bundle bytes",
    )
    # Apply the actual application correction only in a separate owned copy.
    fixed = outside / ("full corrected app case" if full else "small corrected app case")
    shutil.copytree(unavailable_case, fixed)
    app = fixed / "app.py"
    broken_key = 'exported_by_name = {row["name"]: dict(row) for row in rows}'
    fixed_key = 'exported_by_name = {(row["project_id"], row["name"]): dict(row) for row in rows}'
    application = app.read_text("utf-8")
    require(
        application.count(broken_key) == 1, "The counterfactual did not locate the known defect"
    )
    app.write_text(application.replace(broken_key, fixed_key), encoding="utf-8")
    fixed_before = hashes(fixed)
    fixed_output = commands.run(bridge_argv(python, fixed), unrelated)
    require(MARKER not in fixed_output, "The corrected application's genuine PASS emitted a marker")
    require(hashes(fixed) == fixed_before, "Direct PASS execution changed its supplied case")
    require(
        hashes(unavailable_case) == before and hashes(relocated) == bundle_before,
        "Counterfactual changed verified originals",
    )
    return {
        "full": full,
        "original_counts": original.counts,
        "final_counts": final.counts,
        "original_rows": original_rows,
        "final_rows": final_rows,
        "oracle_invocations": report["oracle_invocations"],
        "max_invocations": max_invocations,
        "reduction_wall_seconds": reduction_seconds,
        "fresh_oracle_duration_seconds": sum(result["duration_seconds"] for result in fresh),
        "startup": startup,
        "diagnoses": diagnoses,
        "report": report,
        "progress_events": event_records,
        "relocated_replay": replay,
        "counterfactual": {"actual_exporter_key_corrected": True, "bridge_exit": 0},
        "source_hashes_before_and_after": before,
        "bundle_hashes_before_and_after": bundle_before,
        "original_paths_unavailable_during_replay": True,
        "schema_metadata_and_retained_values_preserved": True,
        "integrity_and_foreign_keys_valid": True,
    }


def with_pytest(
    wheel: Path,
    wheelhouse: Path,
    pytest_version: str,
    outside: Path,
    evidence: dict[str, Any],
    *,
    full: bool,
) -> None:
    outside.mkdir()
    commands = Commands(evidence, consumer_environment())
    installation = outside / "fresh pytest installation café"
    python, cli, wheel_only_runtime = installed_runtime(commands, outside, installation, wheel)
    evidence["runtime_before_pytest"] = wheel_only_runtime
    commands.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--only-binary=:all:",
            "--find-links",
            str(wheelhouse),
            f"pytest=={pytest_version}",
        ],
        outside,
        timeout=90,
    )
    commands.run([str(python), "-m", "pip", "check"], outside)
    runtime = commands.document([str(python), "-c", RUNTIME_PROBE], outside)
    validate_import_origin(runtime, installation)
    require(
        runtime["pytest_available"] is True
        and any(
            dependency["name"] == "pytest" and dependency["version"] == pytest_version
            for dependency in runtime["dependencies"]
        ),
        "The requested explicit pytest dependency was not installed",
    )
    evidence["runtime"] = runtime
    commands.run([str(python), "-m", "reproseed.pytest_oracle", "--help"], outside)
    evidence["small"] = exercise_pytest_case(commands, python, cli, outside, full=False)
    if full:
        evidence["full"] = exercise_pytest_case(commands, python, cli, outside, full=True)


def run_smoke(
    wheel: Path,
    wheelhouse: Path,
    pytest_version: str,
    evidence: dict[str, Any],
    *,
    full: bool,
    directory: Path | None = None,
) -> None:
    wheel = wheel.resolve(strict=True)
    wheelhouse = wheelhouse.resolve(strict=True)
    require(wheel.is_file() and wheel.suffix == ".whl", "--wheel must name one built wheel")
    require(wheelhouse.is_dir(), "--wheelhouse must name the explicit dependency-wheel directory")
    dependency_wheels = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(wheelhouse.glob("*.whl"))
        if path.is_file()
    }
    require(bool(dependency_wheels), "The explicit dependency wheelhouse is empty")
    evidence.update(
        evidence_version=1,
        recipe="offline installed-wheel pytest bridge consumers",
        wheel=str(wheel),
        wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
        wheelhouse=str(wheelhouse),
        dependency_wheel_sha256=dependency_wheels,
        requested_pytest_version=pytest_version,
        full_requested=full,
        consumer_reproseed_source_imports=False,
        orchestration_helpers_from_checkout=True,
        editable_install=False,
        network_during_lifecycle=False,
        independent_human_usability="NOT TESTED; developer simulation only",
        status="running",
    )
    if directory is not None:
        directory = directory.absolute()
        require(
            not directory.resolve().is_relative_to(REPOSITORY.resolve()),
            "An explicit consumer directory must be outside the checkout",
        )
        directory.mkdir(parents=True, exist_ok=False)
    temporary_root = (
        tempfile.TemporaryDirectory(prefix="reproseed pytest consumers café ")
        if directory is None
        else nullcontext(str(directory))
    )
    with temporary_root as temporary:
        outside = Path(temporary).resolve()
        require(
            not outside.is_relative_to(REPOSITORY.resolve()),
            "Consumer scratch space must be outside the checkout",
        )
        evidence["consumer_directory"] = str(outside)
        no_pytest: dict[str, Any] = {}
        pytest_consumer: dict[str, Any] = {}
        evidence.update(consumer_a=no_pytest, consumer_b=pytest_consumer)
        wheel_only(wheel, outside / "consumer A wheel only", no_pytest)
        with_pytest(
            wheel,
            wheelhouse,
            pytest_version,
            outside / "consumer B with pytest",
            pytest_consumer,
            full=full,
        )
    evidence["status"] = "passed"
    evidence["temporary_state_cleaned"] = directory is None and not outside.exists()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--wheelhouse", required=True, type=Path)
    parser.add_argument("--pytest-version", default="9.1.1")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--directory",
        type=Path,
        help="Optional new external scratch directory, retained for review",
    )
    parser.add_argument("--full", action="store_true")
    arguments = parser.parse_args()
    evidence_path = arguments.evidence.resolve() if arguments.evidence else None
    if evidence_path is not None:
        require(not evidence_path.exists(), "Evidence output must be a fresh path")
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = {}
    try:
        run_smoke(
            arguments.wheel,
            arguments.wheelhouse,
            arguments.pytest_version,
            evidence,
            full=arguments.full,
            directory=arguments.directory,
        )
    except Exception as error:
        evidence.update(status="failed", error=str(error))
        raise
    except KeyboardInterrupt:
        evidence.update(status="interrupted")
        raise
    finally:
        output = json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if evidence_path is not None:
            with evidence_path.open("x", encoding="utf-8") as stream:
                stream.write(output)
        print(output, end="")


if __name__ == "__main__":
    main()
