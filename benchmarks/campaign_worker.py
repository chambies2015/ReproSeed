"""One finite source-isolated generated verification worker; use campaign.py."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import platform
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import campaign_cases as cases  # noqa: E402

FIXTURE_SOURCE = None


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def hashes(root):
    return {
        path.relative_to(root).as_posix(): cases.digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def normalize(value):
    # Candidate identities, confirmations, outputs and reasons remain intact.
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items() if key != "duration_seconds"}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def provenance(source):
    import reproseed.artifacts as artifacts
    import reproseed.reducer as reducer
    import reproseed.sqlite_adapter as adapter

    origins = {}
    for module in (adapter, reducer, artifacts):
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(source / "src"), (path, source)
        origins[module.__name__] = {"path": str(path), "sha256": cases.digest(path)}
    return {
        "source": str(source),
        "modules": origins,
        "python": sys.version,
        "executable": sys.executable,
        "sqlite": sqlite3.sqlite_version,
        "os": platform.platform(),
    }


def encoding_checks():
    from reproseed.reducer import _CandidateEncoding

    universe = tuple(("a", i) for i in range(96)) + (
        ("a", "1"),
        ("b", 1),
        ("pair", ("tenant-a", 7)),
        ("pair", ("tenant-b", 7)),
        ("pair", (7, "tenant-a")),
        ("pair", ("7", "tenant-a")),
    )
    first, second = _CandidateEncoding(universe), _CandidateEncoding(reversed(universe))
    selections = [frozenset(universe[:n]) for n in (0, 1, 15, 16, 17, 31, 32, 33, 64, 96, 102)]
    selections += [frozenset({universe[i]}) for i in (0, 1, 96, 97, 98, 99, 100, 101)]
    keys = []
    for selection in selections:
        before = first.encode(selection)
        # Build the other encoder's dense index before looking up tiny keys.
        second.encode(frozenset(universe))
        after = second.encode(frozenset(reversed(tuple(selection))))
        assert before == after, "canonical identity changed after dense initialization"
        for old_key, old_selection in keys:
            assert (before == old_key) == (selection == old_selection), "cache membership collision"
        keys.append((before, selection))
    try:
        first.encode(frozenset({("foreign", 1)}))
    except (KeyError, ValueError):
        pass
    else:
        raise AssertionError("foreign identity silently accepted")
    return len(selections)


def run_supported(directory, seed, ordinal, subset_cap, materialization_cap):
    from reproseed.sqlite_adapter import DatabaseModel

    spec = cases.fixture(seed, ordinal)
    write_json(directory / "input.json", spec.metadata())
    source = directory / "source.sqlite3"
    cases.build(spec, source)
    before = cases.digest(source)
    original_state = cases.schema_state(source)
    universe, original_values = cases.inventory(spec, source)
    edges = cases.sql_edges(spec, source)
    model = DatabaseModel.from_database(source)
    assert frozenset(model.rows) == universe, "declared identity inventory differs from SQL"
    rng = random.Random(seed + ordinal * 65537)
    exhaustive = cases.subsets(cases.ordered(universe), subset_cap)
    trials = exhaustive or [
        frozenset(row for row in cases.ordered(universe) if rng.randrange(3) == 0)
        for _ in range(24)
    ]
    closure_count = 0
    for seeds in trials:
        for retained in (
            universe,
            frozenset(row for row in cases.ordered(universe) if rng.randrange(4)),
        ):
            expected = cases.reference_closure(edges, seeds, retained)
            actual = model.deletion_closure(seeds, retained)
            assert actual == expected, {
                "seeds": cases.ordered(seeds),
                "retained": cases.ordered(retained),
                "expected": cases.ordered(expected),
                "actual": cases.ordered(actual),
            }
            assert seeds & retained <= actual <= retained
            assert model.deletion_closure(actual, retained) == actual, "closure is not idempotent"
            extra = frozenset(cases.ordered(universe)[:1])
            assert actual <= model.deletion_closure(seeds | extra, retained), "closure not monotone"
            closure_count += 3
    # Enumerate valid retained subsets independently. Materialization uses only
    # a bounded sample and is reported separately from combinatorial checks.
    valid = [selection for selection in exhaustive if cases.valid_retained(edges, selection)]
    materialized = [universe]
    if valid:
        materialized.extend([valid[0], valid[len(valid) // 2], valid[-1]])
    else:
        removed = cases.reference_closure(edges, cases.ordered(universe)[:1], universe)
        materialized.extend([universe - removed, frozenset()])
    materialized = list(dict.fromkeys(materialized))[:materialization_cap]
    for i, retained in enumerate(materialized):
        assert cases.valid_retained(edges, retained)
        destination = directory / f"candidate-{i}.sqlite3"
        model.materialize(source, retained, destination)
        identities, actual_values = cases.inventory(spec, destination)
        assert identities == retained, "materialized wrong declared identities"
        assert actual_values == {row: original_values[row] for row in retained}, (
            "retained values changed"
        )
        assert cases.schema_state(destination) == original_state, "schema/index/metadata changed"
    # Insertion order has identical rows/schema and must give exact identities
    # and closures; physical database hashes are deliberately not compared.
    reversed_source = directory / "reversed.sqlite3"
    cases.build(spec, reversed_source, reverse=True)
    reversed_model = DatabaseModel.from_database(reversed_source)
    assert reversed_model.rows == model.rows
    assert cases.sql_edges(spec, reversed_source) == edges
    assert cases.schema_state(reversed_source) == original_state
    assert cases.inventory(spec, reversed_source) == (universe, original_values)
    assert cases.digest(source) == before, "source database changed"
    return {
        "schema_template": spec.template,
        "layout": spec.layout,
        "key_families": list(spec.tables[0].families),
        "source_sha256": before,
        "input_sha256": cases.digest(directory / "input.json"),
        "rows": len(universe),
        "edges": len(edges),
        "closure_checks": closure_count,
        "exhaustive_seed_subsets": len(exhaustive),
        "valid_retained_subsets": len(valid),
        "materializations": len(materialized),
        "subprocess_executions": 0,
        "metamorphic_insertion_order": True,
        "encoding_checks": encoding_checks(),
        "semantic": {
            "identities": cases.ordered(universe),
            "edges": sorted([[parent, child] for parent, child in edges], key=repr),
            "valid_subsets": [cases.ordered(value) for value in valid],
        },
    }


def run_model(directory, seed, ordinal, _subset_cap, _materialization_cap):
    from reproseed.reducer import Evaluation, reduce_rows
    from reproseed.sqlite_adapter import DatabaseModel

    rng = random.Random(seed * 131 + ordinal)
    count = ordinal % 33
    family = cases.FAMILIES[ordinal % 6]
    rows = tuple(
        (
            "model",
            i * 17011 - 101
            if family == ("INTEGER",)
            else f"key-{i}-é"
            if family == ("TEXT",)
            else tuple(
                i * 101 if component == "INTEGER" else f"tenant-{i // 2}-é" for component in family
            ),
        )
        for i in range(count)
    )
    # TEXT/TEXT tuples need unique second components while reusing the first.
    if family == ("TEXT", "TEXT"):
        rows = tuple(("model", (f"tenant-{i // 2}", f"key-{i}-é")) for i in range(count))
    edges = (
        {(parent, child) for parent in rows for child in rows if rng.randrange(47) == 0}
        if ordinal % 4
        else set()
    )
    dependencies = {
        parent: frozenset(child for p, child in edges if p == parent) for parent in rows
    }
    mode = ("target", "pass", "nonmonotonic", "invalid_unresolved")[ordinal % 4]
    payload = {
        "seed": seed,
        "ordinal": ordinal,
        "rows": cases.ordered(rows),
        "edges": sorted([[parent, child] for parent, child in edges], key=repr),
        "mode": mode,
    }
    # Retain the authored counterexample before executing the implementation.
    write_json(directory / "input.json", payload)
    model = DatabaseModel(rows, (), dependencies)
    considered, evaluated = [], []

    class RecordingModel:
        rows = model.rows

        def deletion_closure(self, seeds, retained):
            expected = cases.reference_closure(edges, seeds, retained)
            actual = model.deletion_closure(seeds, retained)
            assert actual == expected
            if actual and len(actual) > 0:
                considered.append(frozenset(retained - actual))
            assert len(considered) <= 2048, "finite model search transition cap exceeded"
            return actual

    def evaluate(candidate):
        if mode == "pass":
            outcome = "PASS"
        elif mode == "nonmonotonic":
            outcome = "TARGET_FAILURE" if len(candidate) % 5 in (1, 3) else "PASS"
        elif mode == "invalid_unresolved" and len(candidate) % 5 == 0:
            outcome = "DATABASE_INVALID"
        elif mode == "invalid_unresolved" and len(candidate) % 3 == 0:
            outcome = "UNRESOLVED"
        else:
            outcome = "TARGET_FAILURE" if rows and rows[-1] in candidate else "PASS"
        result = Evaluation(
            outcome,
            tuple(
                {"outcome": outcome, "executed": True}
                for _ in range(2 if outcome == "TARGET_FAILURE" else 1)
            ),
            "model_" + outcome,
        )
        evaluated.append((candidate, result))
        return result

    result = reduce_rows(RecordingModel(), evaluate)
    assert len(considered) == len(result.attempts)
    seen, evaluations = {}, iter(evaluated)
    retained = frozenset(rows)
    acceptance = []
    for candidate, attempt in zip(considered, result.attempts, strict=True):
        expected_cached = candidate in seen
        assert attempt["cached"] is expected_cached, (
            "cache decision disagrees with exact set equality"
        )
        if expected_cached:
            evidence = seen[candidate]
        else:
            actual_candidate, evidence = next(evaluations)
            assert actual_candidate == candidate, (
                "evaluated identities differ from considered membership"
            )
            if evidence.outcome != "UNRESOLVED":
                seen[candidate] = evidence
        assert attempt["outcome"] == evidence.outcome
        assert attempt["confirmations"] == list(evidence.confirmations)
        assert attempt["retained_rows"] == len(candidate)
        assert attempt["removed_rows"] == len(retained - candidate)
        if evidence.outcome == "TARGET_FAILURE":
            assert candidate < retained
            acceptance.append(
                {"attempt": attempt["number"], "before": len(retained), "after": len(candidate)}
            )
            retained = candidate
    assert next(evaluations, None) is None
    assert result.retained == retained and result.accepted == acceptance
    assert result.cache_hits == sum(attempt["cached"] for attempt in result.attempts)
    return {
        "schema_template": f"model-{family}-{mode}",
        "input_sha256": cases.digest(directory / "input.json"),
        "closure_checks": len(considered),
        "materializations": 0,
        "subprocess_executions": 0,
        "semantic": {
            "considered": [cases.ordered(s) for s in considered],
            "evaluated": [cases.ordered(s) for s, _ in evaluated],
            "attempts": result.attempts,
            "accepted": result.accepted,
            "retained": cases.ordered(result.retained),
            "cache_hits": result.cache_hits,
            "termination_reason": result.termination_reason,
        },
    }


def cli(arguments):
    from reproseed.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


def run_unsupported(directory, seed, ordinal, _subset_cap, _materialization_cap):
    from reproseed.sqlite_adapter import DatabaseError, DatabaseModel

    variant, sql = cases.unsupported(ordinal)
    (directory / "schema.sql").write_text(sql, encoding="utf-8")
    source = directory / "source.sqlite3"
    try:
        with contextlib.closing(sqlite3.connect(source)) as con, con:
            con.executescript(sql)
    except sqlite3.Error as exc:
        return {
            "schema_template": "unsupported-" + variant,
            "classification": "sqlite_ddl_rejected",
            "sqlite_reason": str(exc),
            "subprocess_executions": 0,
            "cli_commands": 0,
            "input_sha256": cases.digest(directory / "schema.sql"),
            "semantic": {"variant": variant, "classification": "sqlite_ddl_rejected"},
        }
    before = cases.digest(source)
    try:
        DatabaseModel.from_database(source)
    except DatabaseError as exc:
        reason = str(exc)
    else:
        raise AssertionError(f"ReproSeed accepted deliberate unsupported variant: {variant}")
    sentinel = directory / "oracle-launched"
    (directory / "sentinel.py").write_text(
        "from pathlib import Path\nPath(" + repr(str(sentinel)) + ").write_text('launched')\n",
        encoding="utf-8",
    )
    config = directory / "reproseed.toml"
    config.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["sentinel.py"]\n[oracle]\n'
        'argv=["{python}","sentinel.py","{db}"]\nexpected_exit=43\nmarker="SYNTHETIC"\n'
        'stream="stdout"\ntimeout_seconds=1\noutput_limit_bytes=1024\n[reduction]\n'
        "max_invocations=20\n",
        encoding="utf-8",
    )
    code, stdout, stderr = cli(
        ["diagnose", "--config", str(config), "--allow-exec", "--format", "json"]
    )
    assert code == 2, (code, stdout, stderr)
    diagnosis = json.loads(stdout)
    assert diagnosis["actual_invocations"] == 0 and diagnosis["oracle_executed"] is False
    code, stdout, stderr = cli(
        ["reduce", "--config", str(config), "--out", str(directory / "bundle"), "--allow-exec"]
    )
    assert code == 2 and not (directory / "bundle").exists(), (code, stdout, stderr)
    assert not sentinel.exists(), "unsupported input launched an oracle"
    assert cases.digest(source) == before
    return {
        "schema_template": "unsupported-" + variant,
        "classification": "reproseed_rejected",
        "reproseed_reason": reason,
        "source_sha256": before,
        "input_sha256": cases.digest(directory / "schema.sql"),
        "config_sha256": cases.digest(config),
        "subprocess_executions": 0,
        "cli_commands": 2,
        "semantic": {
            "variant": variant,
            "classification": "reproseed_rejected",
            "diagnostic_reason": diagnosis["error"]["reason"],
        },
    }


def transform_billing(database, transformation):
    with contextlib.closing(sqlite3.connect(database)) as con, con:
        if transformation == "irrelevant":
            con.execute("CREATE TABLE disconnected(id TEXT PRIMARY KEY,payload TEXT)")
            con.executemany(
                "INSERT INTO disconnected VALUES (?,?)",
                ((f"irrelevant-{i}", "decoy") for i in range(4)),
            )
        elif transformation == "renamed":
            for table, column in (
                ("tenants", "id"),
                ("accounts", "tenant_id"),
                ("invoices", "tenant_id"),
                ("invoice_lines", "tenant_id"),
                ("payments", "tenant_id"),
                ("refunds", "tenant_id"),
            ):
                con.execute(f"UPDATE {table} SET {column}='renamed Ω/' || {column}")
            for table in ("accounts", "invoices", "refunds"):
                con.execute(f"UPDATE {table} SET account_code='account Ω/' || account_code")
            for table in ("invoices", "invoice_lines", "payments"):
                con.execute(f"UPDATE {table} SET invoice_no=-invoice_no-700000")
            con.execute("UPDATE payments SET id=-id-900000")
            con.execute("UPDATE refunds SET payment_id=-payment_id-900000")
            con.execute("UPDATE invoice_lines SET id='line Ω/' || id")
            con.execute("UPDATE refunds SET reference='refund Ω/' || reference")
        elif transformation == "insertion_order":
            tables = [
                row[0] for row in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")
            ]
            for table in tables:
                values = con.execute(f"SELECT * FROM {cases.quote(table)}").fetchall()
                con.execute(f"DELETE FROM {cases.quote(table)}")
                if values:
                    con.executemany(
                        f"INSERT INTO {cases.quote(table)} VALUES ("
                        + ",".join("?" for _ in values[0])
                        + ")",
                        reversed(values),
                    )
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def _run_lifecycle(directory, seed, ordinal, run_oracle):
    from reproseed import workflow
    from reproseed.config import load_config
    from reproseed.sqlite_adapter import DatabaseModel

    source_root = FIXTURE_SOURCE or Path(__import__("reproseed").__file__).resolve().parents[2]
    # Four independently meaningful transformations of the genuine billing app,
    # in both compatible layouts. No planted marker/flag serves as its oracle.
    transformation = ("original", "insertion_order", "irrelevant", "renamed")[ordinal % 4]
    without_rowid = bool((ordinal // 4) % 2)
    example = directory / "example"
    example.mkdir()
    for path in (source_root / "examples" / "composite_billing").iterdir():
        if path.suffix in {".py", ".toml"}:
            shutil.copyfile(path, example / path.name)
    flags = ["--small", *(["--without-rowid"] if without_rowid else [])]
    # Generator is the actual existing application generator, run in a bounded
    # subprocess before recording actual oracle process accounting separately.
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            str(example / "generate.py"),
            str(example / "fixture.sqlite3"),
            *flags,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    transform_billing(example / "fixture.sqlite3", transformation)
    # Three bounded noise levels make all 24 extended lifecycle inputs distinct.
    noise_rows = ordinal // 8
    if noise_rows:
        with contextlib.closing(sqlite3.connect(example / "fixture.sqlite3")) as con, con:
            con.execute("CREATE TABLE campaign_noise(id INTEGER PRIMARY KEY,payload TEXT)")
            con.executemany(
                "INSERT INTO campaign_noise VALUES (?,?)",
                (
                    (seed % 1000000 + i * 17011, f"seed-{seed}-case-{ordinal}-decoy-{i}")
                    for i in range(noise_rows)
                ),
            )
    before = hashes(example)
    config = load_config(example / "reproseed.toml")
    original_model = DatabaseModel.from_database(config.source)
    original_schema = cases.schema_state(config.source)
    with contextlib.closing(sqlite3.connect(config.source)) as con:
        originals = {
            name: set(con.execute(f"SELECT * FROM {cases.quote(name)}"))
            for (name,) in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
    independent = run_oracle(config.oracle, config.source, config.assets)
    assert independent.outcome.value == "TARGET_FAILURE"
    considered, evaluated = [], []
    real_reduce = workflow.reduce_rows

    def recording_reduce(model, evaluate, *args, **kwargs):
        class Model:
            rows = model.rows

            def deletion_closure(self, seeds, retained):
                closure = model.deletion_closure(seeds, retained)
                considered.append(cases.ordered(retained - closure))
                return closure

        def recording_evaluate(candidate):
            evaluated.append(cases.ordered(candidate))
            return evaluate(candidate)

        return real_reduce(Model(), recording_evaluate, *args, **kwargs)

    bundle = directory / "bundle"
    workflow.reduce_rows = recording_reduce
    real_materialize = DatabaseModel.materialize
    materializations = 0

    def recording_materialize(self, *args, **kwargs):
        nonlocal materializations
        materializations += 1
        return real_materialize(self, *args, **kwargs)

    DatabaseModel.materialize = recording_materialize
    try:
        code, stdout, stderr = cli(
            ["reduce", "--config", str(config.path), "--out", str(bundle), "--allow-exec"]
        )
    finally:
        workflow.reduce_rows = real_reduce
        DatabaseModel.materialize = real_materialize
    assert code == 0, (code, stdout, stderr)
    assert hashes(example) == before, "application source/assets mutated"
    report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    assert cases.schema_state(bundle / "fixture.sqlite3") == original_schema
    final_model = DatabaseModel.from_database(bundle / "fixture.sqlite3")
    with contextlib.closing(sqlite3.connect(bundle / "fixture.sqlite3")) as con:
        for table, rows in originals.items():
            assert set(con.execute(f"SELECT * FROM {cases.quote(table)}")) <= rows
    for field in ("baseline_verification", "final_verification"):
        assert len(report[field]) == 3 and all(
            record["outcome"] == "TARGET_FAILURE" for record in report[field]
        )
    for acceptance in report["accepted_reductions"]:
        attempt = report["attempts"][acceptance["attempt"] - 1]
        assert len(attempt["confirmations"]) == 2
    actual_executions = sum(
        record["executed"]
        for record in [
            *report["baseline_verification"],
            *report["final_verification"],
            *[
                confirmation
                for attempt in report["attempts"]
                if not attempt["cached"]
                for confirmation in attempt["confirmations"]
            ],
        ]
    )
    assert actual_executions == report["oracle_invocations"]
    for extra in ([], ["--format", "json"], ["--format", "text"]):
        code, stdout, stderr = cli(["inspect", str(bundle), *extra])
        assert code == 0, (stdout, stderr)
        if extra != ["--format", "text"]:
            assert json.loads(stdout) == report
    bundle_before = hashes(bundle)
    with tempfile.TemporaryDirectory(prefix="reproseed-campaign-relocated-") as temporary:
        relocated = Path(temporary) / "relocated Ω"
        shutil.copytree(bundle, relocated)
        example.rename(directory / "example-unavailable")
        bundle.rename(directory / "bundle-unavailable")
        try:
            code, stdout, stderr = cli(["replay", str(relocated), "--allow-exec"])
            assert code == 0, (stdout, stderr)
            replay = json.loads(stdout)
            assert replay["outcome"] == "TARGET_FAILURE" and len(replay["confirmations"]) == 3
            assert hashes(relocated) == bundle_before
        finally:
            (directory / "example-unavailable").rename(example)
            (directory / "bundle-unavailable").rename(bundle)
    assert hashes(bundle) == bundle_before and hashes(example) == before
    # Fix the actual application defect in a disposable asset copy. Its original
    # SQL/Python oracle must now classify PASS; expected-exit-only checks fail.
    corrected = directory / "corrected"
    shutil.copytree(example, corrected)
    app = corrected / "app.py"
    text = app.read_text(encoding="utf-8")
    assert text.count("settled += refunded") == 1
    app.write_text(text.replace("settled += refunded", "settled -= refunded"), encoding="utf-8")
    fixed = load_config(corrected / "reproseed.toml")
    correction = run_oracle(fixed.oracle, fixed.source, fixed.assets)
    assert correction.outcome.value == "PASS", "fixing refund sign did not remove target outcome"
    assert hashes(example) == before
    return {
        "schema_template": "real-composite-billing",
        "transformation": transformation,
        "layout": "mixed_without_rowid" if without_rowid else "rowid",
        "generator_flags": flags,
        "safe_noise_rows": noise_rows,
        "source_sha256": before["fixture.sqlite3"],
        "config_sha256": before["reproseed.toml"],
        "input_sha256": before["fixture.sqlite3"],
        "source_hashes": before,
        "original_rows": len(original_model.rows),
        "materializations": materializations,
        "cli_commands": 5,
        "subprocess_executions": actual_executions + 6,
        "generator_subprocesses": 1,
        "oracle_subprocesses": actual_executions + 5,
        "corrected_application": normalize(correction.as_dict()),
        "semantic": {
            "report": normalize(report),
            "considered": considered,
            "evaluated": evaluated,
            "retained": cases.ordered(final_model.rows),
            "replay": normalize(replay),
            "independent_oracle": normalize(independent.as_dict()),
            "corrected_application": normalize(correction.as_dict()),
            "source_hashes": before,
            "target_preserved": True,
        },
    }


def run_lifecycle(directory, seed, ordinal, _subset_cap, _materialization_cap):
    from reproseed import artifacts, oracle, workflow

    observed = []
    actual_oracle = oracle.run_oracle
    workflow_oracle, replay_oracle = workflow.run_oracle, artifacts.run_oracle

    def recording_oracle(*args, **kwargs):
        result = actual_oracle(*args, **kwargs)
        observed.append(normalize(result.as_dict()))
        return result

    workflow.run_oracle = recording_oracle
    artifacts.run_oracle = recording_oracle
    try:
        result = _run_lifecycle(directory, seed, ordinal, recording_oracle)
    finally:
        workflow.run_oracle, artifacts.run_oracle = workflow_oracle, replay_oracle
    count = sum(record["executed"] is True for record in observed)
    assert result["oracle_subprocesses"] == count, (
        "actual oracle executions disagree with accounting"
    )
    result["observed_oracle_executions"] = count
    result["semantic"]["observed_oracle_results"] = observed
    return result


RUNNERS = {
    "supported": run_supported,
    "unsupported": run_unsupported,
    "model": run_model,
    "lifecycle": run_lifecycle,
}


def main():
    global FIXTURE_SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument(
        "--fixture-source",
        type=Path,
        help="One captured examples tree shared by both runtime implementations",
    )
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--kind", required=True, choices=tuple(RUNNERS))
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--subset-cap", type=int, default=256)
    parser.add_argument("--materialization-cap", type=int, default=3)
    args = parser.parse_args()
    limits = {"supported": 256, "unsupported": 128, "model": 4000, "lifecycle": 48}
    if not (
        0 <= args.start < limits[args.kind]
        and 1 <= args.count <= 32
        and args.start + args.count <= limits[args.kind]
        and 0 <= args.seed <= 2**32 - 1
        and 1 <= args.subset_cap <= 256
        and 1 <= args.materialization_cap <= 8
    ):
        parser.error("worker inputs exceed finite case/subset/materialization bounds")
    args.directory.mkdir(exist_ok=False)
    source = args.source.resolve()
    FIXTURE_SOURCE = args.fixture_source.resolve() if args.fixture_source else None
    sys.path.insert(0, str(source / "src"))
    result = {
        "campaign_version": 1,
        "generator_version": cases.GENERATOR_VERSION,
        "provenance": provenance(source),
        "cases": [],
    }
    write_json(args.directory / "results.json", result)
    for ordinal in range(args.start, args.start + args.count):
        directory = args.directory / f"{args.kind}-{ordinal:04}"
        directory.mkdir()
        record = {"kind": args.kind, "ordinal": ordinal, "seed": args.seed, "status": "attempted"}
        record["generator_version"] = cases.GENERATOR_VERSION
        record["implementation_provenance"] = result["provenance"]
        verification = {
            "generator_version": cases.GENERATOR_VERSION,
            "kind": args.kind,
            "ordinal": ordinal,
            "seed": args.seed,
            "subset_cap": args.subset_cap,
            "materialization_cap": args.materialization_cap,
        }
        write_json(directory / "verification.json", verification)
        record["config_sha256"] = cases.digest(directory / "verification.json")
        record["schema_template"] = (
            cases.fixture(args.seed, ordinal).template
            if args.kind == "supported"
            else "unsupported-" + cases.unsupported(ordinal)[0]
            if args.kind == "unsupported"
            else "seeded-model"
            if args.kind == "model"
            else "real-composite-billing"
        )
        result["cases"].append(record)
        write_json(args.directory / "results.json", result)
        try:
            record.update(
                RUNNERS[args.kind](
                    directory, args.seed, ordinal, args.subset_cap, args.materialization_cap
                ),
                status="completed",
            )
        except Exception as exc:
            record.update(status="failed", exception=type(exc).__name__, reason=str(exc)[:4000])
            (directory / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if "input_sha256" not in record:
            for name in ("input.json", "schema.sql", "source.sqlite3", "example/fixture.sqlite3"):
                raw = directory / name
                if raw.is_file():
                    record["input_sha256"] = cases.digest(raw)
                    break
        write_json(directory / "result.json", record)
        write_json(args.directory / "results.json", result)
    result["passed"] = all(case["status"] == "completed" for case in result["cases"])
    write_json(args.directory / "results.json", result)
    print(json.dumps({"passed": result["passed"], "cases": len(result["cases"])}))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
