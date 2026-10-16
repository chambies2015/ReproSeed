"""Small independent generated correctness checks; extended work is opt-in."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from reproseed.sqlite_adapter import DatabaseModel

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generated_sql_cases", ROOT / "benchmarks/campaign_cases.py"
)
assert SPEC is not None and SPEC.loader is not None
generated = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generated
SPEC.loader.exec_module(generated)


def load_recipe(name: str):
    spec = importlib.util.spec_from_file_location(
        "generated_" + name, ROOT / "benchmarks" / (name + ".py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("ordinal", [0, 1, 2, 3, 4, 5, 12, 17, 24, 29, 42, 47])
def test_generated_sql_relationships_and_materialization(tmp_path: Path, ordinal: int) -> None:
    spec = generated.fixture(104729, ordinal)
    source = tmp_path / "source.sqlite3"
    generated.build(spec, source)
    before = generated.digest(source)
    universe, values = generated.inventory(spec, source)
    edges = generated.sql_edges(spec, source)
    model = DatabaseModel.from_database(source)
    assert frozenset(model.rows) == universe
    assert ("K", "same") in universe and ("K", "same") in universe
    # Composite first-component matches must not remove another tenant's child.
    # SQL joins use the entire declared key and explicit any-NULL FK behavior.
    for row in generated.ordered(universe):
        expected = generated.reference_closure(edges, [row], universe)
        actual = model.deletion_closure([row], universe)
        assert actual == expected
        assert row in actual and actual <= universe
        assert model.deletion_closure(actual, universe) == actual
    seeds = generated.ordered(universe)[2:4]
    retained = universe - generated.reference_closure(edges, seeds, universe)
    destination = tmp_path / "materialized.sqlite3"
    model.materialize(source, retained, destination)
    assert generated.inventory(spec, destination) == (
        retained,
        {row: values[row] for row in retained},
    )
    assert generated.schema_state(destination) == generated.schema_state(source)
    assert generated.digest(source) == before


def test_tiny_generated_exhaustive_closure_matches_sql_reference(tmp_path: Path) -> None:
    spec = generated.fixture(271828, 17)
    source = tmp_path / "tiny.sqlite3"
    generated.build(spec, source)
    universe, _ = generated.inventory(spec, source)
    assert len(universe) == 8
    edges = generated.sql_edges(spec, source)
    model = DatabaseModel.from_database(source)
    subsets = generated.subsets(generated.ordered(universe), 256)
    assert len(subsets) == 256
    for seeds in subsets:
        actual = model.deletion_closure(seeds, universe)
        assert actual == generated.reference_closure(edges, seeds, universe)
        assert seeds <= actual <= universe
        assert model.deletion_closure(actual, universe) == actual
        for extra in generated.ordered(universe)[:2]:
            assert actual <= model.deletion_closure(seeds | {extra}, universe)
    # A smaller cap never silently turns a partial sample into "exhaustive".
    assert generated.subsets(generated.ordered(universe), 255) == []


@pytest.mark.parametrize("boundary", ["constructor", "search"])
def test_generated_model_failure_retains_original_raw_counterexample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    worker = load_recipe("campaign_worker")

    def broken(*args: object, **kwargs: object) -> None:
        raise AssertionError("injected model implementation failure")

    target = (
        "reproseed.sqlite_adapter.DatabaseModel"
        if boundary == "constructor"
        else "reproseed.reducer.reduce_rows"
    )
    monkeypatch.setattr(target, broken)
    with pytest.raises(AssertionError, match="injected model implementation failure"):
        worker.run_model(tmp_path, 104729, 17, 256, 3)
    raw = json.loads((tmp_path / "input.json").read_text(encoding="utf-8"))
    assert raw["ordinal"] == 17 and raw["seed"] == 104729
    assert len(raw["rows"]) == 17 and raw["edges"] and raw["mode"] == "pass"


def test_generated_worker_bounds_a_completed_burst_of_output(tmp_path: Path) -> None:
    recipe = load_recipe("campaign")
    output = tmp_path / "owned-worker"
    result = recipe.run_worker(
        [sys.executable, "-I", "-c", "import sys; sys.stdout.buffer.write(b'x'*1048576)"],
        output,
        timeout=20,
    )
    assert result["status"] == "failed" and result["reason"] == "worker_output_limit"
    assert (tmp_path / "owned-worker.log").stat().st_size == recipe.OUTPUT_LIMIT
    assert len(result["output_tail"]) <= 4000


def run_campaign(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(directory.parent / "unrelated import context")
    environment["PYTHONHOME"] = str(directory.parent / "unrelated python home")
    return subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "benchmarks/campaign.py"),
            "--directory",
            str(directory),
            *arguments,
        ],
        cwd=directory.parent,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )


def test_generated_recipe_single_case_preserves_replay_and_provenance(tmp_path: Path) -> None:
    output = tmp_path / "generated with spaces Ω"
    result = run_campaign(
        output,
        "--baseline-ref",
        "HEAD",
        "--case",
        "supported:4",
        "--seed",
        "271828",
        "--subset-cap",
        "256",
        "--materialization-cap",
        "2",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert evidence["passed"] and evidence["source_snapshots_unchanged"]
    assert evidence["selected"] == {"supported": [4]}
    assert evidence["summary"]["completed"] == 2
    assert evidence["summary"]["failed"] == evidence["summary"]["timed_out"] == 0
    for sample in evidence["samples"]:
        source = output / ("new-source" if sample["side"] == "new" else "m2e-source")
        provenance = sample["measurement"]["provenance"]
        assert Path(provenance["source"]) == source
        for module in provenance["modules"].values():
            assert Path(module["path"]).is_relative_to(source / "src")
            assert len(module["sha256"]) == 64
        record = sample["measurement"]["cases"][0]
        assert record["exhaustive_seed_subsets"] == 256
        assert record["materializations"] == 2 and record["subprocess_executions"] == 0
        assert record["seed"] == 271828 and record["schema_template"]
        assert "--case supported:4" in record["replay_command"]
        assert record["replay_argv"][record["replay_argv"].index("--seed") + 1] == "271828"
        assert len(record["input_sha256"]) == 64
    # The retained sources/recipe make replay independent of later checkout edits.
    replay = evidence["samples"][0]["measurement"]["cases"][0]["replay_argv"]
    replayed = subprocess.run(
        replay,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    assert replayed.returncode == 0, replayed.stdout + replayed.stderr
    original = (output / "results.json").read_bytes()
    repeated = run_campaign(output, "--baseline-ref", "HEAD", "--case", "supported:4")
    assert repeated.returncode != 0
    assert (output / "results.json").read_bytes() == original


@pytest.mark.parametrize(
    "arguments",
    [
        ("--supported-cases", "1000000000"),
        ("--model-cases", "4001"),
        ("--seed", "-1"),
        ("--subset-cap", "257"),
        ("--materialization-cap", "9"),
        ("--worker-seconds", "inf"),
        ("--worker-seconds", "nan"),
        ("--artifact-limit-mib", "1000000"),
        ("--case", "model:4000"),
    ],
)
def test_generated_recipe_rejects_excessive_inputs_before_creation(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    output = tmp_path / "not-created"
    result = run_campaign(output, *arguments)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not output.exists()
