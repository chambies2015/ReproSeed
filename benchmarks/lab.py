"""Run bounded source-isolated comparisons; generated data stays in a new directory.

Example: python benchmarks/lab.py --directory .validation/performance-fresh --mode all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tarfile
from contextlib import closing
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
BASELINE = "27be3d46c31f752f8944eb6e78d0f743f4edb9cd"


def command(arguments, cwd, *, timeout=1200):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def snapshot(source, destination):
    """Capture only project Python/TOML sources, never generated databases or logs."""
    destination.mkdir()
    for name in ("src", "examples"):
        for path in sorted((source / name).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".toml"}:
                if path.is_symlink() or path.is_junction():
                    raise ValueError("benchmark source snapshot refuses linked files")
                target = destination / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    return source_hashes(destination)


def source_hashes(source):
    return {
        p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for tree in (source / "src", source / "examples")
        for p in sorted(tree.rglob("*"))
        if p.is_file() and p.suffix in {".py", ".toml"}
    }


def archive_baseline(source, destination, ref):
    destination.mkdir()
    commit = command(["git", "rev-parse", ref + "^{commit}"], source, timeout=30)
    if commit.returncode:
        raise RuntimeError(commit.stderr)
    archive = destination / "source.tar"
    saved = command(
        ["git", "archive", "--format=tar", "--output=" + str(archive), commit.stdout.strip()],
        source,
        timeout=60,
    )
    if saved.returncode:
        raise RuntimeError(saved.stderr)
    with tarfile.open(archive) as packed:
        packed.extractall(destination, filter="data")
    return {
        "commit": commit.stdout.strip(),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": source_hashes(destination),
    }


def prepare_fixture(source, destination, example, minimum_rows):
    """Scale two existing applications using additional complete semantic decoys."""
    destination.mkdir()
    for path in (source / "examples" / example).iterdir():
        if path.suffix in {".py", ".toml"}:
            shutil.copyfile(path, destination / path.name)
    database = destination / "fixture.sqlite3"
    flags = ["--without-rowid"] if example == "composite_billing" else []
    process = command(
        [sys.executable, str(destination / "generate.py"), str(database), *flags],
        destination,
        timeout=60,
    )
    if process.returncode:
        raise RuntimeError(process.stderr)
    with closing(sqlite3.connect(database)) as con, con:
        con.execute("PRAGMA foreign_keys=ON")
        if example == "duplicate_export":
            extra = max(0, minimum_rows - 2430)
            con.executemany(
                "INSERT INTO entries VALUES (?,1,?,?)",
                (
                    (2401 + i, f"lab-safe-{i:07}", "Synthetic performance decoy")
                    for i in range(extra)
                ),
            )
        elif example == "composite_billing":
            units = max(0, math.ceil((minimum_rows - 1308) / 7))
            for i in range(units):
                invoice = 1000000 + i
                payment = 1000000 + i * 2
                con.execute(
                    "INSERT INTO invoices VALUES ('tenant-001',?,'account-01',10000)", (invoice,)
                )
                con.executemany(
                    "INSERT INTO invoice_lines VALUES (?,'tenant-001',?,?,?)",
                    (
                        (f"lab-line-{i}-{part}", invoice, "Synthetic performance decoy", amount)
                        for part, amount in enumerate((4000, 3000, 3000))
                    ),
                )
                con.execute(
                    "INSERT INTO payments VALUES (?,'tenant-001',?,4000,'settled')",
                    (payment, invoice),
                )
                con.execute(
                    "INSERT INTO payments VALUES (?,NULL,NULL,1000,'pending')", (payment + 1,)
                )
                con.execute(
                    "INSERT INTO refunds VALUES ('tenant-001',?,'account-01',?,2000,'pending')",
                    (f"lab-refund-{i}", payment),
                )
        assert con.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    return {
        "example": example,
        "minimum_rows": minimum_rows,
        "sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "layout": "mixed_without_rowid" if example == "composite_billing" else "scalar_rowid",
    }


def run_worker(source, directory, kind, extra=()):
    args = [
        sys.executable,
        "-I",
        str(Path(__file__).with_name("worker.py")),
        "--source",
        str(source),
        "--directory",
        str(directory),
        "--kind",
        kind,
        *map(str, extra),
    ]
    try:
        process = command(args, directory.parent)
    except subprocess.TimeoutExpired as exc:
        return {"status": "failed", "reason": "deadline", "timeout_seconds": exc.timeout}
    record = {
        "status": "passed" if process.returncode == 0 else "failed",
        "returncode": process.returncode,
        "stdout": process.stdout[-4000:],
        "stderr": process.stderr[-4000:],
        "directory": str(directory),
    }
    if process.returncode == 0:
        record["measurement"] = json.loads(
            (directory / "measurements.json").read_text(encoding="utf-8")
        )
    return record


def semantic_real(value):
    return {
        key: value[key]
        for key in (
            "original_rows",
            "source_hashes",
            "report",
            "final_identities",
            "considered",
            "evaluated",
            "strict_reader",
            "integrity",
            "foreign_keys",
            "replay",
            "immutability",
        )
    }


def summarize(samples):
    """Keep all raw samples; report medians/ranges without speed assertions."""
    times = {}
    memory = {}
    for sample in samples:
        if sample["status"] != "passed":
            continue
        side = sample["side"]
        measurement = sample["measurement"]
        for entry in measurement.get("cache", []):
            label = f"{entry['rows']}/{entry['shape']}/{side}"
            if entry["traced"]:
                memory[label] = {**entry, "cache_plus_index_bytes": entry["cache"] + entry["index"]}
            else:
                times.setdefault(label + "/search_seconds", []).append(entry["seconds"])
        for entry in measurement.get("encoding", []):
            label = f"{entry['rows']}/{entry['shape']}/{side}/encoding_seconds"
            times.setdefault(label, []).append(entry["encoding_seconds"])
        for entry in measurement.get("model", []):
            for name in (
                "model_seconds",
                "membership_50_seconds",
                "closure_50_seconds",
                "parent_closure_50_seconds",
                "materialize_seconds",
            ):
                times.setdefault(f"{entry['rows']}/{side}/{name}", []).append(entry[name])
        for entry in measurement.get("model_memory", []):
            memory[f"model/{entry['rows']}/{side}"] = entry
    return {
        "timings": {
            label: {
                "median": statistics.median(values),
                "minimum": min(values),
                "maximum": max(values),
                "samples": len(values),
            }
            for label, values in sorted(times.items())
        },
        "memory": memory,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=REPOSITORY)
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument(
        "--mode", choices=("all", "micro", "differential", "real", "smoke"), default="all"
    )
    parser.add_argument("--sizes", type=int, nargs="+", default=[10000, 50000, 100000])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--candidates", type=int, default=24)
    parser.add_argument("--real-rows", type=int, default=20000)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 5 or not 3 <= args.candidates <= 64:
        parser.error("repetitions must be 1..5 and candidates 3..64")
    if not 20000 <= args.real_rows <= 50000:
        parser.error("real-rows must be 20000..50000")
    if any(not 16 <= n <= 100000 or n % 4 for n in args.sizes):
        parser.error("sizes must be multiples of four from 16..100000")
    source = args.source.resolve()
    output = args.directory.resolve()
    output.mkdir(exist_ok=False)
    baseline = output / "baseline-source"
    baseline_evidence = archive_baseline(source, baseline, args.baseline_ref)
    current = output / "new-source"
    new_files = snapshot(source, current)
    head = command(["git", "rev-parse", "HEAD"], source, timeout=30)
    status = command(["git", "status", "--short"], source, timeout=30)
    evidence = {
        "measurement_version": 1,
        "baseline": baseline_evidence,
        "new": {"head": head.stdout.strip(), "status": status.stdout, "files": new_files},
        "recipe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "worker_sha256": hashlib.sha256(
            Path(__file__).with_name("worker.py").read_bytes()
        ).hexdigest(),
        "limits": {
            "sizes": [64] if args.mode == "smoke" else args.sizes,
            "candidate_count": args.candidates,
            "repetitions": 1 if args.mode == "smoke" else args.repetitions,
            "real_rows": args.real_rows,
            "worker_deadline_seconds": 1200,
        },
        "samples": [],
        "semantic_comparisons": [],
        "measurement_notes": [
            "Timing and tracemalloc samples are separate processes.",
            "Tracemalloc is Python allocations, not RSS/native SQLite/children.",
            "Cache owned sizes exclude pre-existing row identities; "
            "ordinal dict/int overhead included.",
            "Run with competing validation workers stopped; contention is operator-reported.",
        ],
    }

    def sample(side, name, kind, extra=()):
        result = run_worker(baseline if side == "baseline" else current, output / name, kind, extra)
        result.update(side=side, name=name)
        evidence["samples"].append(result)
        write_json(output / "comparison.json", evidence)
        print(f"{name}: {result['status']}", flush=True)
        return result

    if args.mode in {"all", "micro", "smoke"}:
        sizes = [64] if args.mode == "smoke" else args.sizes
        repetitions = 1 if args.mode == "smoke" else args.repetitions
        extra = ["--sizes", *sizes, "--candidates", args.candidates]
        for repetition in range(repetitions):
            for side in ("baseline", "new") if repetition % 2 == 0 else ("new", "baseline"):
                sample(side, f"timing-{repetition}-{side}", "micro", [*extra, "--timing-only"])
        for side in ("new", "baseline"):
            sample(side, f"memory-{side}", "micro", [*extra, "--memory-only"])
    if args.mode in {"all", "differential", "smoke"}:
        for seed in (271828, 314159, 161803):
            pair = [
                sample(side, f"differential-{seed}-{side}", "differential", ["--seed", seed])
                for side in ("baseline", "new")
            ]
            equal = (
                all(item["status"] == "passed" for item in pair)
                and pair[0]["measurement"]["differential"] == pair[1]["measurement"]["differential"]
            )
            evidence["semantic_comparisons"].append(
                {"kind": "seeded_graph", "seed": seed, "equal": equal}
            )
    if args.mode in {"all", "real", "smoke"}:
        examples = (
            ("threshold",) if args.mode == "smoke" else ("duplicate_export", "composite_billing")
        )
        for ordinal, example in enumerate(examples):
            fixture = output / f"fixture-{example}"
            prepare_fixture(
                current, fixture, example, 0 if args.mode == "smoke" else args.real_rows
            )
            pair = {}
            order = ("baseline", "new") if ordinal % 2 == 0 else ("new", "baseline")
            for side in order:
                pair[side] = sample(
                    side,
                    f"real-{example}-{side}",
                    "real",
                    ["--fixture", fixture, "--record-identities"],
                )
            equal = all(item["status"] == "passed" for item in pair.values()) and semantic_real(
                pair["baseline"]["measurement"]["real"]
            ) == semantic_real(pair["new"]["measurement"]["real"])
            evidence["semantic_comparisons"].append(
                {"kind": "real", "example": example, "equal": equal}
            )
            ordinary = {}
            for side in reversed(order):
                ordinary[side] = sample(
                    side, f"ordinary-{example}-{side}", "real", ["--fixture", fixture]
                )
            ordinary_equal = all(
                item["status"] == "passed" for item in ordinary.values()
            ) and semantic_real(ordinary["baseline"]["measurement"]["real"]) == semantic_real(
                ordinary["new"]["measurement"]["real"]
            )
            evidence["semantic_comparisons"].append(
                {"kind": "ordinary_real", "example": example, "equal": ordinary_equal}
            )
            enabled = sample(
                "new", f"real-{example}-progress", "real", ["--fixture", fixture, "--observe"]
            )
            progress_equal = enabled["status"] == ordinary["new"][
                "status"
            ] == "passed" and semantic_real(enabled["measurement"]["real"]) == semantic_real(
                ordinary["new"]["measurement"]["real"]
            )
            evidence["semantic_comparisons"].append(
                {"kind": "progress", "example": example, "equal": progress_equal}
            )
    evidence["summary"] = summarize(evidence["samples"])
    evidence["passed"] = all(item["status"] == "passed" for item in evidence["samples"]) and all(
        item["equal"] for item in evidence["semantic_comparisons"]
    )
    write_json(output / "comparison.json", evidence)
    raise SystemExit(0 if evidence["passed"] else 1)


if __name__ == "__main__":
    main()
