"""Finite mutation-recipe mechanics and honest semantic classifications."""

from __future__ import annotations

import json
import os
import runpy
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "benchmarks/mutations.py"


def test_isolated_mutation_recipe_detects_semantics_and_preserves_sources(tmp_path: Path) -> None:
    destination = tmp_path / "isolated mutation with spaces Ω"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path / "unrelated-import-path")
    env["PYTHONHOME"] = str(tmp_path / "unrelated-python-home")
    arguments = [
        sys.executable,
        "-I",
        str(RECIPE),
        "--source",
        str(ROOT),
        "--directory",
        str(destination),
        "--mutation",
        "cache_row_count",
    ]
    result = subprocess.run(
        arguments,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads((destination / "mutations.json").read_text(encoding="utf-8"))
    assert evidence["counts"] == {
        "attempted": 1,
        "detected": 1,
        "survivor": 0,
        "invalid": 0,
        "unresolved_timeout": 0,
    }
    assert evidence["source_unchanged"] and evidence["frozen_source_unchanged"]
    assert evidence["source_hashes"] == evidence["frozen_source_hashes"]
    mutant = evidence["results"][0]
    assert mutant["exactly_one_boundary_applied"]
    assert mutant["change"]["occurrences"] == 1
    assert mutant["change"]["before_sha256"] != mutant["change"]["after_sha256"]
    assert mutant["changed_files"] == ["src/reproseed/reducer.py"]
    assert mutant["control"]["status"] == "passed"
    assert mutant["mutant"]["status"] == "assertion_failure"
    assert mutant["control"]["boundary_reached"] and mutant["mutant"]["boundary_reached"]
    assert "equal-size candidates" in mutant["mutant"]["assertion"]
    replay = mutant["replay_argv"]
    assert replay[0] == sys.executable
    assert replay[replay.index("--source") + 1] == str(destination / "clean-source")
    for side, expected_source in (
        ("control", destination / "clean-source"),
        ("mutant", destination / "cache_row_count/mutant-source"),
    ):
        for imported in mutant[side]["imports"].values():
            assert Path(imported["path"]).is_relative_to(expected_source / "src")
            assert len(imported["sha256"]) == 64
    repeated = subprocess.run(
        arguments,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert repeated.returncode == 2
    assert json.loads((destination / "mutations.json").read_text(encoding="utf-8")) == evidence


def test_posix_replay_quoting_preserves_apostrophes_dollars_and_spaces() -> None:
    recipe = runpy.run_path(str(RECIPE))
    arguments = [
        "/tmp/Python's $HOME/python interpreter",
        "-I",
        "/tmp/recipe's $USER/mutations.py",
        "--source",
        "/tmp/source's $PATH with spaces",
        "--directory",
        "/tmp/output's $SHELL/reproduction new",
    ]
    command = recipe["_replay_command"](arguments, platform_name="posix")
    assert shlex.split(command) == arguments


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_multiline_mutation_preserves_every_byte_outside_its_boundary(
    tmp_path: Path, newline: str
) -> None:
    recipe = runpy.run_path(str(RECIPE))
    mutation = next(item for item in recipe["MUTATIONS"] if item.name == "final_only_two")
    path = tmp_path / "src/reproseed/workflow.py"
    path.parent.mkdir(parents=True)
    old = mutation.old.replace("\n", newline).encode("utf-8")
    new = mutation.new.replace("\n", newline).encode("utf-8")
    original = (
        ("# untouched Ω prefix" + newline + "def verify():" + newline + "        ").encode("utf-8")
        + old
        + (newline + "            pass" + newline + "# untouched é suffix" + newline).encode(
            "utf-8"
        )
    )
    path.write_bytes(original)
    record = recipe["apply_mutation"](tmp_path, mutation)
    assert record["occurrences"] == 1 and record["changed_line"] == 4
    assert path.read_bytes() == original.replace(old, new, 1)


def test_every_finite_mutation_changes_exactly_one_boundary_on_a_private_copy(
    tmp_path: Path,
) -> None:
    recipe = runpy.run_path(str(RECIPE))
    before = recipe["hashes"](ROOT)
    for mutation in recipe["MUTATIONS"]:
        copied = tmp_path / mutation.name
        recipe["snapshot"](ROOT, copied)
        record = recipe["apply_mutation"](copied, mutation)
        assert record["occurrences"] == 1
        changed = {
            path for path, value in recipe["hashes"](copied).items() if before[path] != value
        }
        assert changed == {record["changed_file"]}
        assert record["changed_line"] >= 1
    assert recipe["hashes"](ROOT) == before


@pytest.mark.parametrize("timeout", [-1, 0, 4, 121, 1000000])
def test_recipe_rejects_excessive_deadlines_before_output_creation(
    tmp_path: Path, timeout: int
) -> None:
    recipe = runpy.run_path(str(RECIPE))
    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="timeout"):
        recipe["campaign"](ROOT, destination, timeout=timeout)
    assert not destination.exists()


@pytest.mark.parametrize(
    "control,mutant,expected",
    [
        (
            {"status": "passed", "boundary_reached": True},
            {"status": "assertion_failure", "boundary_reached": True},
            "detected",
        ),
        (
            {"status": "passed", "boundary_reached": True},
            {"status": "passed", "boundary_reached": True},
            "survivor",
        ),
        (
            {"status": "passed", "boundary_reached": True},
            {"status": "invalid", "boundary_reached": True},
            "invalid",
        ),
        (
            {"status": "passed", "boundary_reached": True},
            {"status": "assertion_failure", "boundary_reached": False},
            "invalid",
        ),
        (
            {"status": "assertion_failure", "boundary_reached": True},
            {"status": "assertion_failure", "boundary_reached": True},
            "invalid",
        ),
        (
            {"status": "passed", "boundary_reached": True},
            {"status": "timeout", "boundary_reached": None},
            "unresolved_timeout",
        ),
        (
            {"status": "timeout", "boundary_reached": None},
            {"status": "assertion_failure", "boundary_reached": True},
            "unresolved_timeout",
        ),
    ],
)
def test_setup_failures_and_unknown_timeouts_are_not_semantic_detections(
    control: dict, mutant: dict, expected: str
) -> None:
    recipe = runpy.run_path(str(RECIPE))
    assert recipe["classification"](control, mutant) == expected
