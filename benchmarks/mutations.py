"""Finite mutation sensitivity on disposable Python source snapshots.

Run with development dependencies installed:
python benchmarks/mutations.py --directory .validation/mutations-fresh
No working runtime is patched. Thirteen explicit mutations and their clean controls
run in isolated interpreters, each with a deadline and bounded retained output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import runpy
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
PROBE_PATH = Path("tests/test_m2f_faults.py")
BRIDGE_PROBE_PATH = Path("tests/test_m2g_faults.py")
VERSION = 1
OUTPUT_LIMIT = 16_384


@dataclass(frozen=True)
class Mutation:
    name: str
    file: str
    old: str
    new: str
    test: str
    boundary: str
    invariant: str
    probe: str = PROBE_PATH.as_posix()


MUTATIONS = (
    Mutation(
        "cache_row_count",
        "reducer.py",
        "key = encoding.encode(candidate)",
        "key = len(candidate)",
        "test_cache_requires_exact_membership",
        "closure-normalized cache lookup",
        "same row count does not imply equal exact membership",
    ),
    Mutation(
        "composite_component_lost",
        "sqlite_adapter.py",
        "parent_key = _identity(values[len(table.primary_keys) :])",
        "parent_key = _identity(values[len(table.primary_keys) : len(table.primary_keys) + 1])",
        "test_composite_relationship_uses_entire_key",
        "composite parent dependency identity",
        "the complete ordered composite key determines dependency identity",
    ),
    Mutation(
        "descendant_edge_dropped",
        "sqlite_adapter.py",
        "pending.extend(self._dependents.get(row, frozenset()).intersection(retained) - removed)",
        "pending.extend(())",
        "test_closure_includes_transitive_descendants",
        "transitive dependent traversal",
        "removing a parent also removes its retained dependent descendants",
    ),
    Mutation(
        "partial_null_required",
        "sqlite_adapter.py",
        'sql = f"SELECT {selected} FROM {_quote(table.name)} WHERE {populated}"',
        'sql = f"SELECT {selected} FROM {_quote(table.name)}"',
        "test_partial_null_relationship_is_optional",
        "NULL-exempt child dependency selection",
        "a partial-NULL foreign key does not require a complete parent key",
    ),
    Mutation(
        "oracle_state_reused",
        "oracle.py",
        "return _execute(spec, root, staged_database, execution, cleanup)",
        "return _execute(spec, root, database, execution, cleanup)",
        "test_each_oracle_invocation_uses_pristine_state",
        "disposable per-invocation database selection",
        "oracle writes cannot alter its source or the next invocation's initial state",
    ),
    Mutation(
        "exit_without_marker",
        "oracle.py",
        "elif exit_code == spec.expected_exit and marker:",
        "elif exit_code == spec.expected_exit:",
        "test_expected_exit_without_marker_is_unresolved",
        "exact exit/marker target classification",
        "the expected exit requires the exact marker on the configured stream",
    ),
    Mutation(
        "final_only_two",
        "workflow.py",
        "final = []\n        for confirmation in range(1, 4):",
        "final = []\n        for confirmation in range(1, 3):",
        "test_final_verification_uses_three_fresh_executions",
        "fresh compact-fixture final verification",
        "three fresh target confirmations are required for the compact fixture",
    ),
    Mutation(
        "accepted_confirmation_reused",
        "workflow.py",
        "second = counter.invoke(candidate)",
        "second = first",
        "test_accepted_reduction_has_two_charged_executions",
        "second candidate confirmation",
        "acceptance requires two actual fresh executions, each charged once",
    ),
    Mutation(
        "reader_charges_cached_evidence",
        "report.py",
        "if attempt.cached:",
        "if False and attempt.cached:",
        "test_reader_does_not_charge_cached_confirmation_again",
        "reader cached-execution accounting",
        "historical cached confirmations do not count as new executions",
    ),
    Mutation(
        "reader_forged_count_chain",
        "report.py",
        "if attempt.retained + attempt.removed != current:",
        "if False and attempt.retained + attempt.removed != current:",
        "test_reader_rejects_forged_count_chain",
        "reader accepted-count chain consistency",
        "each attempt's removed plus retained count equals the committed prior selection",
    ),
    Mutation(
        "pytest_message_ignored",
        "pytest_oracle.py",
        'and self.calls["call"][1:] == (self.target.exception, self.target.message)',
        'and self.calls["call"][1] == self.target.exception',
        "probe_pytest_message",
        "structured call exception message equality",
        "a different message is not the specified target",
        BRIDGE_PROBE_PATH.as_posix(),
    ),
    Mutation(
        "pytest_teardown_ignored",
        "pytest_oracle.py",
        'return 2, "setup-or-teardown-failed"',
        'return TARGET_EXIT, "target"',
        "probe_pytest_teardown",
        "required-phase failure must reject before target classification",
        "a failing finalizer prevents target acceptance",
        BRIDGE_PROBE_PATH.as_posix(),
    ),
    Mutation(
        "pytest_skip_passed",
        "pytest_oracle.py",
        "if self.problem is not None:\n            return 2, self.problem",
        'if self.problem == "skip-or-xfail-unsupported":\n'
        '            return 0, "passed"\n'
        "        if self.problem is not None:\n            return 2, self.problem",
        "probe_pytest_skip",
        "skip/incomplete execution rejection",
        "a skipped call is not a genuine pass",
        BRIDGE_PROBE_PATH.as_posix(),
    ),
)


def hashes(source: Path) -> dict[str, str]:
    paths = [
        *sorted((source / "src/reproseed").glob("*.py")),
        source / PROBE_PATH,
        source / BRIDGE_PROBE_PATH,
    ]
    return {path.relative_to(source).as_posix(): digest(path) for path in paths}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(source: Path, destination: Path) -> None:
    """Copy only explicit regular runtime Python sources and the selected probes."""
    paths = [
        *sorted((source / "src/reproseed").glob("*.py")),
        source / PROBE_PATH,
        source / BRIDGE_PROBE_PATH,
    ]
    if not paths or not (source / "src/reproseed/reducer.py").is_file():
        raise ValueError("source must contain the ReproSeed runtime")
    destination.mkdir()
    for path in paths:
        if not path.is_file() or path.is_symlink() or path.is_junction():
            raise ValueError("mutation snapshots require regular unlinked source files")
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def apply_mutation(source: Path, mutation: Mutation) -> dict:
    path = source / "src/reproseed" / mutation.file
    original = path.read_bytes()
    variants: dict[bytes, bytes] = {}
    for newline in ("\n", "\r\n"):
        old = mutation.old.replace("\n", newline).encode("utf-8")
        new = mutation.new.replace("\n", newline).encode("utf-8")
        variants.setdefault(old, new)
    occurrences = sum(original.count(old) for old in variants)
    if occurrences != 1:
        raise ValueError(f"{mutation.name}: expected one original boundary, found {occurrences}")
    old = next(value for value in variants if value in original)
    new = variants[old]
    modified = original.replace(old, new, 1)
    # Trace the first actually changed line, rather than an unchanged context line.
    original_lines = old.splitlines()
    modified_lines = new.splitlines()
    changed = next(
        index
        for index, (before, after) in enumerate(zip(original_lines, modified_lines, strict=False))
        if before != after
    )
    line = original[: original.index(old)].count(b"\n") + 1 + changed
    before = digest(path)
    path.write_bytes(modified)
    return {
        "occurrences": occurrences,
        "changed_file": path.relative_to(source).as_posix(),
        "changed_line": line,
        "before_sha256": before,
        "after_sha256": digest(path),
    }


def worker(source: Path, directory: Path, mutation: Mutation, line: int) -> dict:
    """Execute exactly one targeted test, tracking the altered production line."""
    directory.mkdir()
    sys.path.insert(0, str(source / "src"))
    reached = False
    changed_file = (source / "src/reproseed" / mutation.file).resolve()

    def trace(frame, event, arg):
        nonlocal reached
        if (
            event == "line"
            and frame.f_code.co_filename == str(changed_file)
            and frame.f_lineno == line
        ):
            reached = True
        return trace

    record = {"boundary_reached": False, "test": mutation.test}
    started = time.monotonic()
    try:
        namespace = runpy.run_path(str(source / mutation.probe))
        imports = {}
        for name, module in tuple(sys.modules.items()):
            if name.startswith("reproseed.") and getattr(module, "__file__", None):
                path = Path(module.__file__).resolve()
                if not path.is_relative_to((source / "src").resolve()):
                    raise RuntimeError("import escaped selected source: " + str(path))
                imports[name] = {"path": str(path), "sha256": digest(path)}
        record["imports"] = imports
        sys.settrace(trace)
        namespace[mutation.test](directory)
    except AssertionError as exc:
        record.update(
            status="assertion_failure",
            exception=type(exc).__name__,
            assertion=str(exc)[:2000],
            traceback=traceback.format_exc()[-4000:],
        )
    except BaseException as exc:
        record.update(
            status="invalid",
            exception=type(exc).__name__,
            reason=str(exc)[:2000],
            traceback=traceback.format_exc()[-4000:],
        )
    else:
        record["status"] = "passed"
    finally:
        sys.settrace(None)
    record["boundary_reached"] = reached
    record["duration_seconds"] = time.monotonic() - started
    record["case_hashes"] = {
        path.relative_to(directory).as_posix(): digest(path)
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix in {".py", ".toml", ".sqlite3"}
    }
    return record


def run_worker(
    source: Path, directory: Path, mutation: Mutation, line: int, timeout: int, recipe: Path
) -> dict:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    arguments = [
        sys.executable,
        "-I",
        "-B",
        str(recipe),
        "--worker-source",
        str(source),
        "--directory",
        str(directory),
        "--mutation",
        mutation.name,
        "--line",
        str(line),
    ]
    # Workers never write directly into parent capture buffers. Polling bounds
    # retained output and duration independently, including broken worker setup.
    stdout_path = directory.parent / (directory.name + ".stdout")
    stderr_path = directory.parent / (directory.name + ".stderr")
    stopped = None
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        with subprocess.Popen(
            arguments, cwd=directory.parent, env=env, stdout=stdout, stderr=stderr
        ) as process:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if (
                    stdout_path.stat().st_size > OUTPUT_LIMIT
                    or stderr_path.stat().st_size > OUTPUT_LIMIT
                ):
                    stopped = "output_limit"
                elif time.monotonic() >= deadline:
                    stopped = "timeout"
                if stopped:
                    process.kill()
                    process.wait(timeout=5)
                    break
                time.sleep(0.02)
    for path in (stdout_path, stderr_path):
        if path.stat().st_size > OUTPUT_LIMIT:
            with path.open("r+b") as stream:
                stream.truncate(OUTPUT_LIMIT)
    if stopped == "timeout":
        return {"status": "timeout", "timeout_seconds": timeout, "boundary_reached": None}
    if stopped == "output_limit":
        return {"status": "invalid", "reason": "worker output exceeded retained bound"}
    stdout_bytes = stdout_path.read_bytes()
    stderr_bytes = stderr_path.read_bytes()
    try:
        result = json.loads(stdout_bytes)
    except (ValueError, UnicodeError):
        return {
            "status": "invalid",
            "reason": "worker returned no valid result",
            "returncode": process.returncode,
            "stdout": stdout_bytes[-2000:].decode("utf-8", errors="replace"),
            "stderr": stderr_bytes[-2000:].decode("utf-8", errors="replace"),
        }
    if process.returncode:
        result.update(status="invalid", reason="worker exited unsuccessfully")
    result["timeout_seconds"] = timeout
    return result


def classification(control: dict, mutant: dict) -> str:
    if control.get("status") == "timeout" or mutant.get("status") == "timeout":
        return "unresolved_timeout"
    if control.get("status") != "passed" or not control.get("boundary_reached"):
        return "invalid"
    if not mutant.get("boundary_reached") or mutant.get("status") == "invalid":
        return "invalid"
    if mutant.get("status") == "assertion_failure":
        return "detected"
    if mutant.get("status") == "passed":
        return "survivor"
    return "invalid"


def _replay_command(arguments: list[str], *, platform_name: str | None = None) -> str:
    platform_name = os.name if platform_name is None else platform_name
    return subprocess.list2cmdline(arguments) if platform_name == "nt" else shlex.join(arguments)


def campaign(
    source: Path, directory: Path, *, timeout: int = 60, selected: tuple = MUTATIONS
) -> dict:
    if not 5 <= timeout <= 120:
        raise ValueError("worker timeout must be between 5 and 120 seconds")
    if not 1 <= len(selected) <= len(MUTATIONS) or len({item.name for item in selected}) != len(
        selected
    ):
        raise ValueError("select 1 to 13 distinct known mutations")
    if any(item not in MUTATIONS for item in selected):
        raise ValueError("only the finite declared mutations are accepted")
    if not directory.parent.is_dir():
        raise ValueError("output parent must already exist")
    # mkdir is the exclusive acquisition: there is no overwrite/cleanup shortcut.
    directory.mkdir()
    before = hashes(source)
    frozen = directory / "clean-source"
    snapshot(source, frozen)
    frozen_hashes = hashes(frozen)
    recipe = directory / "mutations.py"
    shutil.copyfile(Path(__file__), recipe)
    report = {
        "mutation_version": VERSION,
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "source": str(source),
        "source_hashes": before,
        "frozen_source_hashes": frozen_hashes,
        "recipe": str(recipe),
        "recipe_sha256": digest(recipe),
        "worker_timeout_seconds": timeout,
        "probe_generator": "fixed-semantic-probes-v1",
        "seed": None,
        "results": [],
    }
    for mutation in selected:
        case = directory / mutation.name
        case.mkdir()
        record = {**asdict(mutation), "classification": "invalid"}
        report["results"].append(record)
        copied = case / "mutant-source"
        snapshot(frozen, copied)
        try:
            change = apply_mutation(copied, mutation)
        except ValueError as exc:
            record["reason"] = str(exc)
        else:
            record["change"] = change
            changed_files = [
                path for path, value in hashes(copied).items() if frozen_hashes[path] != value
            ]
            record["changed_files"] = changed_files
            record["exactly_one_boundary_applied"] = (
                changed_files == [change["changed_file"]] and change["occurrences"] == 1
            )
            record["control"] = run_worker(
                frozen, case / "control-case", mutation, change["changed_line"], timeout, recipe
            )
            record["mutant"] = run_worker(
                copied, case / "mutant-case", mutation, change["changed_line"], timeout, recipe
            )
            record["classification"] = classification(record["control"], record["mutant"])
            if not record["exactly_one_boundary_applied"]:
                record["classification"] = "invalid"
            record["mutant_source_hashes"] = hashes(copied)
        record["replay_argv"] = [
            sys.executable,
            "-I",
            str(recipe),
            "--directory",
            str(case / "reproduction-new"),
            "--source",
            str(frozen),
            "--mutation",
            mutation.name,
            "--timeout",
            str(timeout),
        ]
        record["reproduce"] = _replay_command(record["replay_argv"])
        report["source_unchanged"] = hashes(source) == before
        report["frozen_source_unchanged"] = hashes(frozen) == frozen_hashes
        counts = {
            name: sum(item["classification"] == name for item in report["results"])
            for name in ("detected", "survivor", "invalid", "unresolved_timeout")
        }
        report["counts"] = {"attempted": len(report["results"]), **counts}
        (directory / "mutations.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )
    return report


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=REPOSITORY)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--mutation", choices=[mutation.name for mutation in MUTATIONS])
    parser.add_argument("--worker-source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--line", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args(arguments)
    if args.worker_source:
        mutation = next(item for item in MUTATIONS if item.name == args.mutation)
        result = worker(args.worker_source.resolve(), args.directory.resolve(), mutation, args.line)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    selected = tuple(item for item in MUTATIONS if not args.mutation or item.name == args.mutation)
    try:
        report = campaign(
            args.source.resolve(), args.directory.resolve(), timeout=args.timeout, selected=selected
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report["counts"], sort_keys=True))
    return int(
        not report["source_unchanged"]
        or not report["frozen_source_unchanged"]
        or any(item["classification"] != "detected" for item in report["results"])
    )


if __name__ == "__main__":
    raise SystemExit(main())
