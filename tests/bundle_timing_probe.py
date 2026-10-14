"""Finite synthetic bundle timing and Windows path-security validation batches.

Run with the project interpreter and a new tool-owned --directory. Timing uses
the real public bundle builder, a one-row INTEGER fixture and a mutating oracle.
Only classifications, counts, timing and cleanup observations are retained.
The optional deadline injection is a readiness-triggered clock jump confined to
the oracle module; reported wall timings continue to use the untouched clock.
This recipe is evidence collection, never test retries or hosted CI behavior.
"""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import subprocess
import sys
import time
import warnings
import xml.etree.ElementTree as ET
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from reproseed import oracle, workflow
from reproseed.artifacts import create_bundle, sha256, validate_bundle
from reproseed.config import load_config
from reproseed.workflow import VerificationError

REPOSITORY = Path(__file__).resolve().parents[1]
REAL_CLOCK = time.monotonic
SECURITY_TESTS = [
    "tests/test_bundle_snapshot.py::test_bundle_symlink_rejected",
    "tests/test_bundle_snapshot.py::test_bundle_junction_rejected",
]


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def synthetic_case(directory: Path, timeout: float) -> Path:
    directory.mkdir()
    with closing(sqlite3.connect(directory / "source.sqlite3")) as connection:
        connection.executescript(
            "CREATE TABLE things(id INTEGER PRIMARY KEY, value TEXT);"
            "INSERT INTO things VALUES(1,'pristine');"
        )
    (directory / "data.txt").write_text("pristine", encoding="utf-8")
    (directory / "oracle.py").write_text(
        "import sqlite3,sys,time,threading\nfrom pathlib import Path\n"
        "if len(sys.argv)>2:\n"
        " ready=Path(sys.argv[2]); ready.write_text('ready')\n"
        " limit=time.monotonic()+30\n"
        " while not ready.with_suffix('.release').exists() and time.monotonic()<limit:\n"
        "  threading.Event().wait(0.01)\n"
        "c=sqlite3.connect(sys.argv[1])\n"
        "assert c.execute('SELECT value FROM things').fetchone()==('pristine',)\n"
        "assert Path('data.txt').read_text()=='pristine'\n"
        "c.execute(\"UPDATE things SET value='mutated'\"); c.commit(); c.close()\n"
        "Path('data.txt').write_text('mutated')\n"
        "print('TARGET'); raise SystemExit(42)\n",
        encoding="utf-8",
    )
    config = directory / "case.toml"
    config.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py","data.txt"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="TARGET"\nstream="stdout"\n'
        f"timeout_seconds={timeout}\noutput_limit_bytes=4096\n"
        "[reduction]\nmax_invocations=6\n",
        encoding="utf-8",
    )
    return config


def measure_bundle(directory: Path, timeout: float, injection: str) -> dict[str, Any]:
    config_path = synthetic_case(directory, timeout)
    inputs = [directory / name for name in ("source.sqlite3", "data.txt", "oracle.py", "case.toml")]
    before = [sha256(path) for path in inputs]
    records: list[dict[str, Any]] = []
    real_run = workflow.run_oracle
    real_popen = subprocess.Popen
    real_kill = oracle._kill_tree
    real_remove = oracle._remove_owned_directory
    current: dict[str, Any] = {}
    invocation_started = 0.0
    ready = directory / "deadline.ready"
    clock_offset = 0.0
    inject_number = {"none": 0, "baseline": 1, "final": 4}[injection]

    def probe_clock() -> float:
        nonlocal clock_offset
        if len(records) + 1 == inject_number and ready.exists() and not clock_offset:
            clock_offset = timeout + 0.5
            current["injected_after_child_readiness"] = True
        return REAL_CLOCK() + clock_offset

    def observed_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        started = REAL_CLOCK()
        process = real_popen(*args, **kwargs)
        # A fallback taskkill launch is distinct from the oracle's process.
        if "process_launch_seconds" in current:
            current["cleanup_subprocess_launches"] = (
                current.get("cleanup_subprocess_launches", 0) + 1
            )
            return process
        current["process_launch_seconds"] = REAL_CLOCK() - started
        current["launch_observed_after_seconds"] = REAL_CLOCK() - invocation_started
        real_poll = process.poll

        def observed_poll() -> int | None:
            result = real_poll()
            if result is not None and "completion_observed_after_seconds" not in current:
                current["completion_observed_after_seconds"] = REAL_CLOCK() - invocation_started
            return result

        process.poll = observed_poll  # type: ignore[method-assign]
        return process

    def observed_kill(*args: Any, **kwargs: Any) -> None:
        current["owned_job_assigned"] = args[1] is not None
        started = REAL_CLOCK()
        try:
            real_kill(*args, **kwargs)
        finally:
            current["tree_cleanup_seconds"] = REAL_CLOCK() - started

    def observed_remove(root: Path, *args: Any, **kwargs: Any) -> None:
        started = REAL_CLOCK()
        try:
            real_remove(root, *args, **kwargs)
        finally:
            current["directory_cleanup_seconds"] = REAL_CLOCK() - started
            current["disposable_root_removed"] = not root.exists()

    def observed_run(*args: Any, **kwargs: Any) -> oracle.OracleResult:
        nonlocal current, invocation_started, clock_offset
        number = len(records) + 1
        current = {"invocation": number, "phase": "baseline" if number <= 3 else "final"}
        invocation_started = REAL_CLOCK()
        clock_offset = 0.0
        if number == inject_number:
            args = (replace(args[0], argv=(*args[0].argv, str(ready))), *args[1:])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = real_run(*args, **kwargs)
        current.update(result.as_dict())
        current["wall_seconds_including_staging_and_cleanup"] = REAL_CLOCK() - invocation_started
        current["cleanup_warnings"] = [
            str(item.message)
            for item in caught
            if str(item.message).startswith("oracle cleanup incomplete:")
        ]
        records.append(current)
        clock_offset = 0.0
        return result

    result: dict[str, Any] = {"timeout_seconds": timeout, "injection": injection}
    started = REAL_CLOCK()
    with (
        patch.object(workflow, "run_oracle", observed_run),
        patch.object(oracle.subprocess, "Popen", observed_popen),
        patch.object(oracle, "_kill_tree", observed_kill),
        patch.object(oracle, "_remove_owned_directory", observed_remove),
        patch.object(oracle, "time", SimpleNamespace(monotonic=probe_clock, sleep=time.sleep)),
    ):
        try:
            report = create_bundle(load_config(config_path), directory / "bundle")
        except VerificationError as error:
            result.update(status="verification_rejected", error=str(error))
        else:
            result.update(status="verified", oracle_invocations=report["oracle_invocations"])
    result.update(
        bundle_wall_seconds=REAL_CLOCK() - started,
        invocations=records,
        source_and_assets_unchanged=before == [sha256(path) for path in inputs],
        bundle_published=(directory / "bundle").exists(),
    )
    if result["bundle_published"]:
        bundle = directory / "bundle"
        payload = {path.name: sha256(path) for path in bundle.iterdir() if path.is_file()}
        validate_bundle(bundle)
        result["bundle_unchanged_by_validation"] = payload == {
            path.name: sha256(path) for path in bundle.iterdir() if path.is_file()
        }
    return result


def load_worker() -> None:
    """A fixed number of ordinary Python imports, SQLite queries and launches."""
    code = (
        "import hashlib,json,sqlite3; "
        "c=sqlite3.connect(':memory:'); "
        "c.executescript('CREATE TABLE t(id INTEGER PRIMARY KEY,value TEXT);'); "
        "c.executemany('INSERT INTO t(value) VALUES(?)',[(str(i),) for i in range(1000)]); "
        "assert c.execute('SELECT count(*) FROM t').fetchone()==(1000,); "
        "hashlib.sha256(json.dumps(list(range(10000))).encode()).digest(); c.close()"
    )
    for _ in range(40):
        subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )


def start_load(directory: Path) -> list[tuple[str, subprocess.Popen[bytes], float]]:
    commands = [
        (
            f"process_worker_{number}",
            [sys.executable, str(Path(__file__).resolve()), "--load-worker"],
        )
        for number in (1, 2)
    ]
    commands.append(
        (
            "concurrent_oracle_tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_oracle.py",
                "--basetemp=" + str(directory / "load-pytest"),
                "-q",
            ],
        )
    )
    return [
        (
            name,
            subprocess.Popen(
                command, cwd=REPOSITORY, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ),
            REAL_CLOCK(),
        )
        for name, command in commands
    ]


def security_batch(directory: Path, count: int, evidence: dict[str, Any]) -> int:
    failed = False
    for number in range(1, count + 1):
        report = directory / f"security-{number:02}.xml"
        started = REAL_CLOCK()
        code = None
        timed_out = False
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *SECURITY_TESTS,
                    "--basetemp=" + str(directory / f"pytest-{number:02}"),
                    "--junitxml=" + str(report),
                    "-q",
                ],
                cwd=REPOSITORY,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            )
            code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
        cases = []
        for case in ET.parse(report).iter("testcase") if report.exists() else ():
            status = "passed"
            for candidate in ("error", "failure", "skipped"):
                if case.find(candidate) is not None:
                    status = candidate
                    break
            cases.append({"name": case.attrib["name"], "result": status})
        record = {
            "run": number,
            "exit_code": code,
            "timed_out": timed_out,
            "wall_seconds": REAL_CLOCK() - started,
            "tests": cases,
        }
        evidence["runs"].append(record)
        write_evidence(directory / "evidence.json", evidence)
        print(json.dumps(record), flush=True)
        failed |= code != 0 or timed_out
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--timeout", type=float, choices=(1.0, 5.0), default=5.0)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--inject", choices=("none", "baseline", "final"), default="none")
    parser.add_argument("--security-runs", type=int, default=0)
    parser.add_argument("--load-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.load_worker:
        load_worker()
        return 0
    if args.directory is None:
        parser.error("--directory is required")
    if not 1 <= args.repetitions <= 100 or not 0 <= args.security_runs <= 100:
        parser.error("finite repetition counts must be between 1 and 100")
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    evidence: dict[str, Any] = {
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "os": platform.platform(),
        "deadline_seconds": args.timeout,
        "load": args.load,
        "injection": args.inject,
        "clock": "real wall; result duration includes the injected offset when enabled",
        "runs": [],
    }
    write_evidence(directory / "evidence.json", evidence)
    if args.security_runs:
        return security_batch(directory, args.security_runs, evidence)
    background = start_load(directory) if args.load else []
    failed = False
    try:
        for number in range(1, args.repetitions + 1):
            record = measure_bundle(directory / f"case-{number:02}", args.timeout, args.inject)
            record["run"] = number
            record["background_processes_active"] = sum(
                process.poll() is None for _, process, _ in background
            )
            evidence["runs"].append(record)
            write_evidence(directory / "evidence.json", evidence)
            print(
                json.dumps(
                    {
                        "run": number,
                        "status": record["status"],
                        "outcomes": [item["outcome"] for item in record["invocations"]],
                        "wall_seconds": record["bundle_wall_seconds"],
                    }
                ),
                flush=True,
            )
            expected = "verified" if args.inject == "none" else "verification_rejected"
            failed |= record["status"] != expected or not record["source_and_assets_unchanged"]
    finally:
        evidence["load_results"] = []
        for name, process, started in background:
            try:
                code = process.wait(timeout=max(0.1, 180 - (REAL_CLOCK() - started)))
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=15)
                failed = True
            evidence["load_results"].append(
                {"name": name, "exit_code": code, "wall_seconds": REAL_CLOCK() - started}
            )
            failed |= code != 0
        write_evidence(directory / "evidence.json", evidence)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
