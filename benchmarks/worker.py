"""Isolated benchmark worker; invoke through ``python benchmarks/lab.py``."""

from __future__ import annotations

import argparse
import dataclasses
import gc
import hashlib
import json
import platform
import random
import shutil
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

SPARSE_BOUNDARY = 32
SHAPES = (
    "dense",
    "sparse",
    "repeated",
    "threshold_below",
    "threshold_at",
    "threshold_above",
    "mixed",
    "dense_to_sparse",
    "sparse_protocol",
)


def provenance(source):
    import reproseed.reducer as reducer
    import reproseed.sqlite_adapter as adapter

    root = source.resolve()
    origins = {}
    for module in (reducer, adapter):
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(root / "src"), (path, root)
        origins[module.__name__] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {
        "source": str(root),
        "modules": origins,
        "python": sys.version,
        "executable": sys.executable,
        "sqlite": sqlite3.sqlite_version,
        "os": platform.platform(),
    }


def size_owned(value, excluded, seen=None):
    if seen is None:
        seen = set()
    ident = id(value)
    if ident in seen or ident in excluded:
        return 0
    seen.add(ident)
    size = sys.getsizeof(value)
    if isinstance(value, Mapping):
        return size + sum(
            size_owned(k, excluded, seen) + size_owned(v, excluded, seen) for k, v in value.items()
        )
    if isinstance(value, (tuple, list, set, frozenset)):
        return size + sum(size_owned(v, excluded, seen) for v in value)
    if dataclasses.is_dataclass(value) or hasattr(value, "__dict__"):
        return size + size_owned(vars(value), excluded, seen)
    return size


def row_ids(n):
    # Four supported identity families, with deliberate per-table separation.
    return tuple(
        ("integer", i)
        if i % 4 == 0
        else ("text", f"r-{i:07}")
        if i % 4 == 1
        else ("composite", (i // 4, f"k-{i % 19}"))
        if i % 4 == 2
        else ("without_rowid", (f"tenant-{i % 13}", i))
        for i in range(n)
    )


def selection(rows, shape, index, count, full=None):
    """One bounded, shared workload definition for every archived implementation."""
    n = len(rows)
    if shape.startswith("threshold_"):
        offset = {"threshold_below": -1, "threshold_at": 0, "threshold_above": 1}[shape]
        size = min(n - 1, SPARSE_BOUNDARY + offset)
        start = index % max(1, n - size)
        return frozenset(rows[start : start + size])
    if shape == "dense_to_sparse":
        return frozenset(rows[: max(1, n // (2 ** min(index + 1, 32)))])
    if shape == "mixed":
        # Same sparse key both before and after the first packed candidate;
        # dense duplicates also cross later sparse/dense transitions.
        phase = index % 6
        offset = 0 if phase in (0, 3) else 1 if phase in (1, 5) else 2
        subset = frozenset(rows[offset : offset + min(16, max(1, n // 4))])
        return (frozenset(rows) if full is None else full) - subset if phase in (2, 4) else subset
    index = index % max(1, count // 3) if shape == "repeated" else index
    subset = frozenset(rows[index : index + min(16, max(1, n // 4))])
    return (
        subset
        if shape in {"sparse", "sparse_protocol"}
        else (frozenset(rows) if full is None else full) - subset
    )


def closure_selection(rows, shape, index, count, retained):
    # Match the established benchmark's tiny dense deletion closure; avoid
    # charging an extra synthetic full-universe allocation to every candidate.
    if shape in {"dense", "repeated"}:
        start = index % max(1, count // 3) if shape == "repeated" else index
        return frozenset(rows[start : start + min(16, max(1, len(rows) // 4))])
    if shape == "mixed" and index % 6 in (2, 4):
        return frozenset(rows[2 : 2 + min(16, max(1, len(rows) // 4))])
    return retained - selection(rows, shape, index, count, full=retained)


def encoder_for(reducer, rows, universe):
    """Use a new shared-membership interface when present, preserving old sources."""
    import inspect

    encoder_class = getattr(reducer, "_CandidateEncoding", None)
    if encoder_class is None:
        return None
    if "universe" in inspect.signature(encoder_class).parameters:
        return encoder_class(rows, universe=universe)
    return encoder_class(rows)


def cache_sample(n, shape, count, traced):
    from reproseed.reducer import BudgetExhausted, Evaluation, reduce_rows
    from reproseed.sqlite_adapter import DatabaseModel, row_sort_key

    rows = tuple(sorted(row_ids(n), key=row_sort_key))
    excluded = {id(v) for row in rows for v in (row, row[0], row[1])}
    excluded.update(id(v) for row in rows if isinstance(row[1], tuple) for v in row[1])
    base_model = None if shape == "sparse_protocol" else DatabaseModel(rows, (), {})
    universe = getattr(base_model, "row_universe", getattr(base_model, "_row_universe", None))
    partitions = getattr(base_model, "_rows_by_table", None)
    model_indexes = size_owned(universe, excluded) if universe is not None else 0
    if partitions is not None:
        model_indexes += size_owned(partitions, excluded) + sys.getsizeof(dict(partitions))
    shared = {id(rows)}
    if universe is not None and shape != "sparse_protocol":
        shared.add(id(universe))
    captured = {}
    calls = 0

    class Model:
        def __init__(self):
            self.rows = rows
            self.index = 0

        @property
        def row_universe(self):
            return None if shape == "sparse_protocol" else universe

        def deletion_closure(self, seeds, retained):
            if self.index >= count:
                raise BudgetExhausted
            index = self.index
            self.index += 1
            return closure_selection(rows, shape, index, count, retained)

    def evaluate(candidate):
        nonlocal calls
        calls += 1
        outcome = "TARGET_FAILURE" if shape == "dense_to_sparse" else "PASS"
        return Evaluation(outcome, reason="synthetic_" + outcome.lower())

    def trace(frame, event, arg):
        if event == "return" and frame.f_code is reduce_rows.__code__:
            captured["current_traced_bytes"], captured["peak_traced_bytes"] = (
                tracemalloc.get_traced_memory()
            )
            cache = frame.f_locals["cache"]
            owned_exclusions = excluded | shared
            owned_seen = set()
            captured["cache"] = size_owned(cache, owned_exclusions, owned_seen)
            encoder = frame.f_locals.get("encoding") or frame.f_locals.get("encoder")
            # Read the actual production encoder, not an imitation of its representation.
            if encoder is None:
                encoder = next(
                    (
                        v
                        for v in frame.f_locals.values()
                        if type(v).__name__ == "_CandidateEncoding"
                    ),
                    None,
                )
            captured["index"] = (
                0 if encoder is None else size_owned(encoder, owned_exclusions, owned_seen)
            )
            captured["encoder_reachable_bytes"] = (
                0 if encoder is None else size_owned(encoder, excluded)
            )
            captured["shared_preexisting_rows_tuple_bytes"] = sys.getsizeof(rows)
            captured["shared_preexisting_model_index_bytes"] = model_indexes
            captured["model_plus_cache_index_bytes"] = (
                model_indexes + captured["cache"] + captured["index"]
            )
            captured["encoder_retains_rows_tuple"] = encoder is not None and any(
                value is rows for value in vars(encoder).values()
            )
            captured["encoder_retains_model_universe"] = (
                encoder is not None
                and universe is not None
                and any(value is universe for value in vars(encoder).values())
            )
            captured["shared_reference_lifetime"] = (
                "Existing model and model.rows remain live throughout reduce_rows; "
                "shared encoder references do not extend their measured search lifetime."
            )
            captured["ordinal_index_initialized"] = (
                encoder is not None and getattr(encoder, "ordinals", None) is not None
            )
            captured["keys"] = sum(sys.getsizeof(key) for key in cache)
        return trace if frame.f_code is reduce_rows.__code__ else None

    gc.collect()
    if traced:
        tracemalloc.start()
        sys.settrace(trace)
    start = time.perf_counter()
    result = reduce_rows(Model(), evaluate)
    seconds = time.perf_counter() - start
    if traced:
        sys.settrace(None)
        tracemalloc.stop()
    return {
        "rows": n,
        "shape": shape,
        "candidate_count": count,
        "evaluations": calls,
        "cache_hits": result.cache_hits,
        "accepted_changes": len(result.accepted),
        "retained_rows": len(result.retained),
        "membership_interface": "protocol_fallback" if shape == "sparse_protocol" else "model",
        "representation_workload_boundary": SPARSE_BOUNDARY,
        "seconds": seconds,
        "traced": traced,
        **captured,
    }


def database(path, n):
    with closing(sqlite3.connect(path)) as con, con:
        con.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE parent(id INTEGER PRIMARY KEY, payload TEXT);
        CREATE TABLE text_key(id TEXT PRIMARY KEY NOT NULL,
            parent_id INTEGER REFERENCES parent(id));
        CREATE TABLE pair(tenant TEXT, id INTEGER,
            parent_id INTEGER REFERENCES parent(id), PRIMARY KEY(tenant,id));
        CREATE TABLE packed(tenant TEXT, id INTEGER,
            parent_id INTEGER REFERENCES parent(id), PRIMARY KEY(tenant,id)) WITHOUT ROWID;
        """)
        group = n // 4
        con.executemany("INSERT INTO parent VALUES (?, 'synthetic')", ((i,) for i in range(group)))
        con.executemany(
            "INSERT INTO text_key VALUES (?,?)", ((f"r-{i:07}", i) for i in range(group))
        )
        con.executemany("INSERT INTO pair VALUES ('tenant',?,?)", ((i, i) for i in range(group)))
        con.executemany(
            "INSERT INTO packed VALUES ('tenant',?,?)", ((i, i) for i in range(n - group * 3))
        )


def model_sample(path, n, directory, repetition):
    from reproseed.sqlite_adapter import DatabaseModel

    start = time.perf_counter()
    model = DatabaseModel.from_database(path)
    construction = time.perf_counter() - start
    full = frozenset(model.rows)
    chosen = frozenset(model.rows[::2])
    start = time.perf_counter()
    for _ in range(50):
        model._check_rows(chosen)
    membership = time.perf_counter() - start
    start = time.perf_counter()
    for index in range(50):
        model.deletion_closure(model.rows[index : index + 3], full)
    closure = time.perf_counter() - start
    parent_seeds = [row for row in model.rows if row[0] == "parent"]
    start = time.perf_counter()
    for index in range(50):
        model.deletion_closure(parent_seeds[index : index + 3], full)
    parent_closure = time.perf_counter() - start
    removed = model.deletion_closure(model.rows[: max(1, n // 8)], full)
    start = time.perf_counter()
    destination = directory / f"materialized-{n}-{repetition}.sqlite3"
    model.materialize(path, full - removed, destination)
    materialization = time.perf_counter() - start
    return {
        "rows": n,
        "model_seconds": construction,
        "membership_50_seconds": membership,
        "closure_50_seconds": closure,
        "parent_closure_50_seconds": parent_closure,
        "materialize_seconds": materialization,
        "retained_rows": len(full - removed),
    }


def model_memory_sample(path, n):
    from reproseed.sqlite_adapter import DatabaseModel

    gc.collect()
    tracemalloc.start()
    model = DatabaseModel.from_database(path)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    excluded = {id(value) for row in model.rows for value in (row, row[0], row[1])}
    excluded.update(
        id(value) for row in model.rows if isinstance(row[1], tuple) for value in row[1]
    )
    universe = getattr(model, "_row_universe", None)
    partition = getattr(model, "_rows_by_table", None)
    # A mappingproxy hides its backing dict's shallow capacity; an equal-size
    # dict copy gives an explicit estimate, reported separately from exact keys.
    index_bytes = size_owned(universe, excluded) if universe is not None else 0
    if partition is not None:
        index_bytes += size_owned(partition, excluded) + sys.getsizeof(dict(partition))
    return {
        "rows": n,
        "current_traced_bytes": current,
        "peak_traced_bytes": peak,
        "adapter_index_estimated_bytes": index_bytes,
    }


def encoding_sample(n, shape, count, traced=False):
    """Separate initialization, conversion and temporary Python allocations."""
    import reproseed.reducer as reducer
    from reproseed.sqlite_adapter import DatabaseModel

    rows = row_ids(n)
    full = frozenset(rows)
    model = None if shape == "sparse_protocol" else DatabaseModel(rows, (), {})
    universe = getattr(model, "row_universe", getattr(model, "_row_universe", None))
    if shape == "sparse_protocol":
        universe = None
    initialization_start = time.perf_counter()
    if traced:
        gc.collect()
        tracemalloc.start()
    encoder = encoder_for(reducer, rows, universe)
    initialization_seconds = time.perf_counter() - initialization_start
    initialization_bytes = tracemalloc.get_traced_memory() if traced else None
    if traced:
        tracemalloc.stop()
    elapsed = 0.0
    operations = []
    remembered = {}
    for i in range(count):
        candidate = selection(rows, shape, i, count, full=full)
        initialized_before = encoder is not None and getattr(encoder, "ordinals", None) is not None
        if traced:
            tracemalloc.start()
        start = time.perf_counter()
        key = candidate if encoder is None else encoder.encode(candidate)
        elapsed += time.perf_counter() - start
        allocations = tracemalloc.get_traced_memory() if traced else None
        if traced:
            tracemalloc.stop()
        # Compare actual exact equality across history, including sparse keys
        # first observed before lazy initialization. No hash-only matching.
        duplicate_group = None
        if shape == "mixed":
            duplicate_group = (0, 1, 2, 0, 2, 1)[i % 6]
        elif shape == "repeated":
            duplicate_group = i % max(1, count // 3)
        if duplicate_group is not None:
            if duplicate_group in remembered:
                assert remembered[duplicate_group] == key
            else:
                remembered[duplicate_group] = key
        operations.append(
            {
                "candidate_rows": len(candidate),
                "key_type": type(key).__name__,
                "key_shallow_bytes": sys.getsizeof(key),
                "ordinal_index_before": initialized_before,
                "ordinal_index_after": encoder is not None
                and getattr(encoder, "ordinals", None) is not None,
                "current_traced_bytes": None if allocations is None else allocations[0],
                "peak_traced_bytes": None if allocations is None else allocations[1],
                "scratch_peak_above_retained_bytes": None
                if allocations is None
                else (max(0, allocations[1] - allocations[0])),
            }
        )
        assert key is not None
    return {
        "rows": n,
        "shape": shape,
        "candidate_count": count,
        "encoding_seconds": elapsed,
        "initialization_seconds": initialization_seconds,
        "initialization_current_traced_bytes": None
        if initialization_bytes is None
        else initialization_bytes[0],
        "initialization_peak_traced_bytes": None
        if initialization_bytes is None
        else initialization_bytes[1],
        "traced": traced,
        "operations": operations,
        "encoder": "frozenset_identity" if encoder is None else type(encoder).__name__,
    }


def differential(seed):
    """Exercise the imported reducer with bounded seeded exact identity graphs."""
    from reproseed.reducer import BudgetExhausted, Evaluation, reduce_rows
    from reproseed.sqlite_adapter import DatabaseModel, row_sort_key

    rng = random.Random(seed)
    scenarios = []
    for name in (
        "scalar",
        "text",
        "composite",
        "mixed_cycles",
        "empty",
        "irreducible",
        "budget",
        "nonmonotonic",
        "invalid_unresolved",
        "cache_boundary",
    ):
        count = 0 if name == "empty" else 96 if name == "cache_boundary" else 36
        rows = (
            tuple(("scalar", index) for index in range(count))
            if name == "scalar"
            else tuple(("text", f"value-{index:03}") for index in range(count))
            if name == "text"
            else tuple(("composite", (index % 3, f"value-{index:03}")) for index in range(count))
            if name == "composite"
            else row_ids(count)
        )
        dependents = {}
        if name == "mixed_cycles":
            for row in rows:
                dependents[row] = frozenset((row, rows[rng.randrange(len(rows))]))
            dependents[rows[0]] = frozenset((rows[1],))
            dependents[rows[1]] = frozenset((rows[0],))
        model = DatabaseModel(rows, (), dependents)
        evaluated = []
        considered = []
        calls = 0
        actual_closure = model.deletion_closure
        actual_universe = getattr(model, "row_universe", getattr(model, "_row_universe", None))

        class RecordingModel:
            def __init__(
                self,
                rows=rows,
                closure=actual_closure,
                log=considered,
                universe=actual_universe,
                scenario=name,
            ):
                self.rows = rows
                self.closure = closure
                self.log = log
                self.transitions = 0
                self.universe = universe
                self.scenario = scenario

            @property
            def row_universe(self):
                return self.universe

            def deletion_closure(self, seeds, retained):
                self.transitions += 1
                if self.transitions > 500:
                    raise AssertionError("differential scenario exceeded finite transition cap")
                if self.scenario == "cache_boundary":
                    if self.transitions > 24:
                        raise BudgetExhausted
                    closure = closure_selection(
                        self.rows, "mixed", self.transitions - 1, 24, retained
                    )
                else:
                    closure = self.closure(seeds, retained)
                self.log.append(sorted(retained - closure, key=row_sort_key))
                return closure

        def evaluate(candidate, *, name=name, rows=rows, evaluated=evaluated):
            nonlocal calls
            if name == "budget" and calls >= 4:
                raise BudgetExhausted
            calls += 1
            evaluated.append(sorted(candidate, key=row_sort_key))
            if name in {"irreducible", "cache_boundary"}:
                outcome = "PASS"
            elif name == "invalid_unresolved" and len(candidate) % 5 == 0:
                outcome = "DATABASE_INVALID"
            elif name == "invalid_unresolved" and calls % 3 == 0:
                outcome = "UNRESOLVED"
            elif name == "nonmonotonic":
                outcome = "TARGET_FAILURE" if len(candidate) % 7 in (2, 5) else "PASS"
            else:
                outcome = "TARGET_FAILURE" if rows and rows[-1] in candidate else "PASS"
            confirmations = ({"outcome": outcome, "executed": outcome != "DATABASE_INVALID"},)
            return Evaluation(outcome, confirmations, "synthetic_" + outcome.lower())

        result = reduce_rows(RecordingModel(), evaluate)
        scenarios.append(
            {
                "name": name,
                "evaluated": evaluated,
                "considered": considered,
                "retained": sorted(result.retained, key=row_sort_key),
                "attempts": result.attempts,
                "accepted": result.accepted,
                "cache_hits": result.cache_hits,
                "termination_reason": result.termination_reason,
                "evaluations": calls,
            }
        )
    return {"seed": seed, "scenarios": scenarios}


def hashes(directory):
    return {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def normalize(value):
    """Only subprocess durations are volatile in semantic report comparisons."""
    if isinstance(value, Mapping):
        return {key: normalize(item) for key, item in value.items() if key != "duration_seconds"}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def real_sample(fixture, directory, observe, record_identities):
    from reproseed import workflow
    from reproseed.artifacts import acquire_bundle, create_bundle, replay_bundle
    from reproseed.config import load_config
    from reproseed.sqlite_adapter import DatabaseModel, row_sort_key

    example = directory / "example"
    shutil.copytree(fixture, example)
    original_hashes = hashes(example)
    config = load_config(example / "reproseed.toml")
    original_model = DatabaseModel.from_database(config.source)
    original_count = len(original_model.rows)
    considered = []
    evaluated = []
    real_reduce = workflow.reduce_rows

    def recording_reduce(model, evaluate, *args, **kwargs):
        class Model:
            rows = model.rows

            @property
            def row_universe(self):
                return getattr(model, "row_universe", getattr(model, "_row_universe", None))

            def deletion_closure(self, seeds, retained):
                closure = model.deletion_closure(seeds, retained)
                considered.append(sorted(retained - closure, key=row_sort_key))
                return closure

        def recording_evaluate(candidate):
            evaluated.append(sorted(candidate, key=row_sort_key))
            return evaluate(candidate)

        return real_reduce(Model(), recording_evaluate, *args, **kwargs)

    if record_identities:
        workflow.reduce_rows = recording_reduce
    observer = None
    progress_file = None
    progress_path = directory / "progress.txt"
    if observe:
        from reproseed.observation import StreamObserver

        progress_file = progress_path.open("w", encoding="utf-8")
        observer = StreamObserver(progress=progress_file)
    bundle = directory / "bundle"
    start = time.perf_counter()
    try:
        report = (
            create_bundle(config, bundle, observer=observer)
            if observer is not None
            else create_bundle(config, bundle)
        )
    finally:
        workflow.reduce_rows = real_reduce
        if progress_file is not None:
            progress_file.close()
    elapsed = time.perf_counter() - start
    assert hashes(example) == original_hashes
    bundle_hashes = hashes(bundle)
    with acquire_bundle(bundle) as acquired:
        assert normalize(acquired.report) == normalize(report)
    final_model = DatabaseModel.from_database(bundle / "fixture.sqlite3")
    with closing(
        sqlite3.connect((bundle / "fixture.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    ) as con:
        assert con.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    with tempfile.TemporaryDirectory(prefix="reproseed-lab-relocated-") as temporary:
        relocated = Path(temporary) / "relocated bundle Ω"
        shutil.copytree(bundle, relocated)
        assert hashes(relocated) == bundle_hashes
        hidden_example = directory / "example-unavailable"
        hidden_bundle = directory / "bundle-unavailable"
        example.rename(hidden_example)
        bundle.rename(hidden_bundle)
        try:
            replay = replay_bundle(relocated)
            assert replay["outcome"] == "TARGET_FAILURE"
            assert len(replay["confirmations"]) == 3
            assert hashes(relocated) == bundle_hashes
        finally:
            hidden_example.rename(example)
            hidden_bundle.rename(bundle)
    assert hashes(example) == original_hashes and hashes(bundle) == bundle_hashes
    return {
        "original_rows": original_count,
        "wall_seconds": elapsed,
        "progress": observe,
        "identities_instrumented": record_identities,
        "source_hashes": original_hashes,
        "bundle_hashes": bundle_hashes,
        "report": normalize(report),
        "strict_reader": True,
        "integrity": True,
        "foreign_keys": True,
        "replay": normalize(replay),
        "immutability": True,
        "final_identities": sorted(final_model.rows, key=row_sort_key),
        "considered": considered,
        "evaluated": evaluated,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--kind", choices=("micro", "differential", "real"), default="micro")
    parser.add_argument("--sizes", type=int, nargs="+", default=[10000, 50000, 100000])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--candidates", type=int, default=24)
    parser.add_argument("--seed", type=int, default=271828)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--observe", action="store_true")
    parser.add_argument("--record-identities", action="store_true")
    parser.add_argument("--memory-only", action="store_true")
    parser.add_argument("--timing-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 5 or not 3 <= args.candidates <= 64:
        parser.error("repetitions must be 1..5 and candidates 3..64")
    if not 1 <= len(args.sizes) <= 3 or len(set(args.sizes)) != len(args.sizes):
        parser.error("choose one to three distinct sizes")
    if any(not 16 <= n <= 100000 or n % 4 for n in args.sizes):
        parser.error("sizes must be multiples of four from 16..100000")
    if args.memory_only and args.timing_only:
        parser.error("choose memory-only or timing-only")
    args.directory.mkdir(exist_ok=False)
    sys.path.insert(0, str(args.source.resolve() / "src"))
    result = {"measurement_version": 1, "kind": args.kind, "provenance": provenance(args.source)}
    if args.kind == "differential":
        result["differential"] = differential(args.seed)
    elif args.kind == "real":
        if args.fixture is None:
            parser.error("real requires --fixture")
        result["real"] = real_sample(
            args.fixture, args.directory, args.observe, args.record_identities
        )
    else:
        result.update(cache=[], model=[], model_memory=[], encoding=[])
        for n in args.sizes:
            for shape in SHAPES:
                if not args.memory_only:
                    for _ in range(args.repetitions):
                        result["cache"].append(cache_sample(n, shape, args.candidates, False))
                        result["encoding"].append(encoding_sample(n, shape, args.candidates))
                if not args.timing_only:
                    result["cache"].append(cache_sample(n, shape, args.candidates, True))
                    result["encoding"].append(encoding_sample(n, shape, args.candidates, True))
            path = args.directory / f"model-{n}.sqlite3"
            database(path, n)
            if not args.memory_only:
                for repetition in range(args.repetitions):
                    result["model"].append(model_sample(path, n, args.directory, repetition))
            if not args.timing_only:
                result["model_memory"].append(model_memory_sample(path, n))
    output = args.directory / "measurements.json"
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"measurement_version": 1, "output": str(output)}))


if __name__ == "__main__":
    main()
