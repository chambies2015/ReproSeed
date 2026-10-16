"""Bounded, reproducible generated SQLite correctness campaign (developer recipe).

Run from any directory with an installed development interpreter, without network.
Every destination must be new. Failures and original synthetic inputs are retained.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
ACCEPTED_M2E = "0b776c8f5002c846940e438207d582af2259bda6"
PROFILES = {
    "smoke": {"supported": 8, "unsupported": 8, "model": 24, "lifecycle": 1},
    "extended": {"supported": 128, "unsupported": 64, "model": 1000, "lifecycle": 24},
}
MAXIMUMS = {"supported": 256, "unsupported": 128, "model": 4000, "lifecycle": 48}
OUTPUT_LIMIT = 262144


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bytes_used(root):
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def run_worker(argv, directory, timeout):
    """Keep finite worker output on disk, checking its cap while it runs."""
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    log = directory.parent / (directory.name + ".log")
    started = time.monotonic()
    status, reason = None, None
    with log.open("xb") as stream:
        process = subprocess.Popen(
            argv, cwd=directory.parent, env=environment, stdout=stream, stderr=subprocess.STDOUT
        )
        try:
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    status, reason = "timed_out", "finite_worker_deadline"
                    process.kill()
                    break
                if log.stat().st_size > OUTPUT_LIMIT:
                    status, reason = "failed", "worker_output_limit"
                    process.kill()
                    break
                time.sleep(0.025)
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    status = status or ("completed" if process.returncode == 0 else "failed")
    if log.stat().st_size > OUTPUT_LIMIT:
        status, reason = "failed", "worker_output_limit"
        with log.open("r+b") as stream:
            stream.truncate(OUTPUT_LIMIT)
    with log.open("rb") as stream:
        output = stream.read(OUTPUT_LIMIT).decode("utf-8", errors="replace")
    result = {
        "status": status,
        "reason": reason,
        "returncode": process.returncode,
        "timeout_seconds": timeout,
        "elapsed_seconds": time.monotonic() - started,
        "output_tail": output[-4000:],
        "directory": str(directory),
    }
    path = directory / "results.json"
    if path.is_file() and path.stat().st_size <= 32 * 1024 * 1024:
        try:
            with path.open("rb") as stream:
                payload = stream.read(32 * 1024 * 1024 + 1)
            if len(payload) > 32 * 1024 * 1024:
                raise ValueError("worker result exceeds 32 MiB")
            result["measurement"] = json.loads(payload)
        except (ValueError, UnicodeError) as exc:
            result.update(status="failed", reason="invalid_worker_result", parse_error=str(exc))
    return result


def replay_argv(recipe, current, baseline, output, seed, kind, ordinal, args):
    return [
        sys.executable,
        "-I",
        str(recipe / "campaign.py"),
        "--source",
        str(current),
        "--baseline-source",
        str(baseline),
        "--directory",
        str(output / f"replay-{kind}-{ordinal}"),
        "--seed",
        str(seed),
        "--case",
        f"{kind}:{ordinal}",
        "--subset-cap",
        str(args.subset_cap),
        "--materialization-cap",
        str(args.materialization_cap),
        "--worker-seconds",
        str(args.worker_seconds),
    ]


def summarize(evidence):
    counts = collections.Counter()
    work = collections.Counter()
    attempted = 0
    for sample in evidence["samples"]:
        records = sample.get("measurement", {}).get("cases", [])
        actual = {record["ordinal"]: record for record in records}
        for ordinal in sample["ordinals"]:
            record = actual.get(ordinal)
            # A killed batch may have generated only its first case. Untouched
            # scheduled ordinals are skipped, never invented attempted failures.
            status = record["status"] if record else "skipped"
            attempted += int(record is not None)
            if status == "attempted" and sample["status"] == "timed_out":
                status = "timed_out"
            if status == "attempted":
                status = "failed"
            counts[f"{sample['side']}/{sample['kind']}/{status}"] += 1
            if record is None:
                continue
            if record.get("classification") in {"sqlite_ddl_rejected", "reproseed_rejected"}:
                counts[f"{sample['side']}/{sample['kind']}/rejected"] += 1
            for name in (
                "closure_checks",
                "exhaustive_seed_subsets",
                "valid_retained_subsets",
                "materializations",
                "subprocess_executions",
                "cli_commands",
                "oracle_subprocesses",
                "generator_subprocesses",
                "encoding_checks",
            ):
                if type(record.get(name)) is int:
                    work[f"{sample['side']}/{name}"] += record[name]
    return {
        "case_status_counts": dict(sorted(counts.items())),
        "work_counts": dict(sorted(work.items())),
        "attempted": attempted,
        "completed": sum(value for key, value in counts.items() if key.endswith("/completed")),
        "failed": sum(value for key, value in counts.items() if key.endswith("/failed")),
        "timed_out": sum(value for key, value in counts.items() if key.endswith("/timed_out")),
        "skipped": sum(value for key, value in counts.items() if key.endswith("/skipped")),
        "rejected": sum(value for key, value in counts.items() if key.endswith("/rejected")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=REPOSITORY)
    parser.add_argument("--baseline-ref", default=ACCEPTED_M2E)
    parser.add_argument(
        "--baseline-source",
        type=Path,
        help="Previously captured accepted source for exact offline single-case replay",
    )
    parser.add_argument("--profile", choices=tuple(PROFILES), default="smoke")
    parser.add_argument("--seed", type=int, default=104729)
    parser.add_argument("--case", help="Replay exactly KIND:ORDINAL with the same seed and bounds")
    parser.add_argument("--supported-cases", type=int)
    parser.add_argument("--unsupported-cases", type=int)
    parser.add_argument("--model-cases", type=int)
    parser.add_argument("--lifecycle-cases", type=int)
    parser.add_argument("--subset-cap", type=int, default=256)
    parser.add_argument("--materialization-cap", type=int, default=3)
    parser.add_argument("--worker-seconds", type=float, default=180)
    parser.add_argument("--artifact-limit-mib", type=int, default=512)
    args = parser.parse_args()
    counts = {
        kind: getattr(args, kind + "_cases")
        if getattr(args, kind + "_cases") is not None
        else count
        for kind, count in PROFILES[args.profile].items()
    }
    if any(not 0 <= count <= MAXIMUMS[kind] for kind, count in counts.items()):
        parser.error("case counts exceed finite supported/unsupported/model/lifecycle bounds")
    if not (
        0 <= args.seed <= 2**32 - 1
        and 1 <= args.subset_cap <= 256
        and 1 <= args.materialization_cap <= 8
        and 1 <= args.worker_seconds <= 600
        and 16 <= args.artifact_limit_mib <= 1024
    ):
        parser.error(
            "seed, subsets, materializations, worker deadline or artifact cap exceed bounds"
        )
    selected = {kind: list(range(count)) for kind, count in counts.items()}
    if args.case:
        try:
            kind, raw = args.case.split(":")
            ordinal = int(raw)
            if kind not in MAXIMUMS or not 0 <= ordinal < MAXIMUMS[kind]:
                raise ValueError
        except ValueError:
            parser.error("case must be bounded KIND:ORDINAL")
        selected = {kind: [ordinal]}
    if not any(selected.values()):
        parser.error("at least one case is required")
    source, output = args.source.resolve(), args.directory.resolve()
    if output.is_relative_to(source / "src") or output.is_relative_to(source / "examples"):
        parser.error("output must be outside the source and example trees")
    output.mkdir(exist_ok=False)
    recipe = output / "recipe"
    recipe.mkdir()
    for name in ("campaign.py", "campaign_cases.py", "campaign_worker.py", "lab.py"):
        shutil.copyfile(Path(__file__).with_name(name), recipe / name)
    evidence = {
        "campaign_version": 1,
        "generator_version": 1,
        "profile": args.profile,
        "seed": args.seed,
        "selected": selected,
        "recipe_hashes": {path.name: file_hash(path) for path in recipe.iterdir()},
        "limits": {
            "worker_seconds": args.worker_seconds,
            "worker_output_bytes": OUTPUT_LIMIT,
            "subset_cap": args.subset_cap,
            "materialization_cap": args.materialization_cap,
            "artifact_limit_bytes": args.artifact_limit_mib * 1024 * 1024,
            "artifact_limit_policy": (
                "Stop threshold checked between bounded workers; retained files may exceed it "
                "by one finite batch plus aggregate result JSON growth. Case/fixture/log/result "
                "bounds keep retained work finite; this is not a strict filesystem/process maximum."
            ),
            "max_fixture_rows": 16,
            "max_tiny_universe": 8,
            "max_model_transitions_per_case": 2048,
        },
        "samples": [],
        "comparisons": [],
        "passed": False,
        "notes": [
            "Only subprocess duration_seconds is normalized for semantic comparisons.",
            "Model evaluation is synthetic; it is not a real oracle subprocess.",
            "Extended logical cases are run once per captured implementation.",
            "All synthetic inputs and failed attempts are retained; there are no retries.",
            "Valid SQLite schemas rejected by ReproSeed are classified separately "
            "from DDL rejection.",
        ],
    }
    result_path = output / "results.json"
    write_json(result_path, evidence)
    try:
        current, baseline = output / "new-source", output / "m2e-source"
        new_files = lab.snapshot(source, current)
        if args.baseline_source is None:
            accepted = lab.archive_baseline(source, baseline, args.baseline_ref)
        else:
            accepted = {
                "captured_source": str(args.baseline_source.resolve()),
                "files": lab.snapshot(args.baseline_source.resolve(), baseline),
            }
        evidence["implementations"] = {"new": {"files": new_files}, "m2e": accepted}
        for command, label in (
            (["git", "rev-parse", "HEAD"], "head"),
            (["git", "status", "--short"], "status"),
        ):
            process = lab.command(command, source, timeout=30)
            evidence["implementations"]["new"][label] = (
                process.stdout.strip() if not process.returncode else None
            )
        write_json(result_path, evidence)
        stopped = False
        for kind, ordinals in selected.items():
            batch_size = 1 if kind == "lifecycle" else 8 if kind == "supported" else 32
            for offset in range(0, len(ordinals), batch_size):
                batch = ordinals[offset : offset + batch_size]
                pair = {}
                for side, captured in (("m2e", baseline), ("new", current)):
                    name = f"{kind}-{batch[0]:04}-{side}"
                    destination = output / name
                    if stopped or bytes_used(output) > evidence["limits"]["artifact_limit_bytes"]:
                        stopped = True
                        sample = {
                            "status": "skipped",
                            "reason": "artifact_limit",
                            "directory": str(destination),
                        }
                    else:
                        argv = [
                            sys.executable,
                            "-I",
                            "-B",
                            str(recipe / "campaign_worker.py"),
                            "--source",
                            str(captured),
                            "--fixture-source",
                            str(current),
                            "--directory",
                            str(destination),
                            "--kind",
                            kind,
                            "--seed",
                            str(args.seed),
                            "--start",
                            str(batch[0]),
                            "--count",
                            str(len(batch)),
                            "--subset-cap",
                            str(args.subset_cap),
                            "--materialization-cap",
                            str(args.materialization_cap),
                        ]
                        sample = run_worker(argv, destination, args.worker_seconds)
                    sample.update(side=side, kind=kind, ordinals=batch)
                    for record in sample.get("measurement", {}).get("cases", []):
                        replay = replay_argv(
                            recipe,
                            current,
                            baseline,
                            output,
                            args.seed,
                            kind,
                            record["ordinal"],
                            args,
                        )
                        record["replay_argv"] = replay
                        record["replay_command"] = (
                            subprocess.list2cmdline(replay)
                            if os.name == "nt"
                            else shlex.join(replay)
                        )
                        write_json(
                            destination / f"{kind}-{record['ordinal']:04}" / "result.json", record
                        )
                    evidence["samples"].append(sample)
                    pair[side] = sample
                    evidence["summary"] = summarize(evidence)
                    write_json(result_path, evidence)
                    print(f"{name}: {sample['status']}", flush=True)
                first = {
                    record["ordinal"]: record
                    for record in pair["m2e"].get("measurement", {}).get("cases", [])
                }
                second = {
                    record["ordinal"]: record
                    for record in pair["new"].get("measurement", {}).get("cases", [])
                }
                for ordinal in batch:
                    old, new = first.get(ordinal), second.get(ordinal)
                    equal = (
                        old is not None
                        and new is not None
                        and old["status"] == new["status"] == "completed"
                        and old["semantic"] == new["semantic"]
                    )
                    evidence["comparisons"].append(
                        {"kind": kind, "ordinal": ordinal, "equal": equal}
                    )
                write_json(result_path, evidence)
        evidence["source_snapshots_unchanged"] = (
            lab.source_hashes(current) == new_files
            and lab.source_hashes(baseline) == accepted["files"]
        )
        evidence["artifact_bytes"] = bytes_used(output)
        evidence["summary"] = summarize(evidence)
        evidence["passed"] = (
            all(sample["status"] == "completed" for sample in evidence["samples"])
            and all(comparison["equal"] for comparison in evidence["comparisons"])
            and evidence["source_snapshots_unchanged"]
        )
    except Exception as exc:
        evidence["setup_or_driver_failure"] = {
            "type": type(exc).__name__,
            "reason": str(exc)[:4000],
        }
    finally:
        write_json(result_path, evidence)
    raise SystemExit(0 if evidence["passed"] else 1)


if __name__ == "__main__":
    main()
