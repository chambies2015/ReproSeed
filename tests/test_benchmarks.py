"""Small isolated recipe coverage; large performance runs stay outside ordinary CI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_recipe_smoke_preserves_semantics_and_import_isolation(tmp_path: Path) -> None:
    destination = tmp_path / "lab with spaces Ω"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path / "unrelated-import-context")
    env["PYTHONHOME"] = str(tmp_path / "unrelated-python-home")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "benchmarks" / "lab.py"),
            "--directory",
            str(destination),
            "--mode",
            "smoke",
            "--baseline-ref",
            "HEAD",
            "--accepted-ref",
            "HEAD",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads((destination / "comparison.json").read_text(encoding="utf-8"))
    assert evidence["measurement_version"] == 1 and evidence["passed"]
    assert len(evidence["semantic_comparisons"]) == 11
    assert all(item["equal"] for item in evidence["semantic_comparisons"])
    sides = set()
    for sample in evidence["samples"]:
        sides.add(sample["side"])
        origin = sample["measurement"]["provenance"]
        expected = destination / (sample["side"] + "-source")
        assert Path(origin["source"]) == expected
        for module in origin["modules"].values():
            assert Path(module["path"]).is_relative_to(expected / "src")
            assert len(module["sha256"]) == 64
    assert sides == {"baseline", "accepted", "new"}
    assert evidence["accepted"]["commit"] == evidence["baseline"]["commit"]
    assert evidence["accepted"]["files"] == evidence["baseline"]["files"]
    for side in sides:
        timing = next(item for item in evidence["samples"] if item["name"] == f"timing-0-{side}")
        shapes = {item["shape"] for item in timing["measurement"]["cache"]}
        assert {
            "threshold_below",
            "threshold_at",
            "threshold_above",
            "mixed",
            "dense_to_sparse",
            "sparse_protocol",
        } <= shapes
        memory = next(item for item in evidence["samples"] if item["name"] == f"memory-{side}")
        for item in memory["measurement"]["cache"]:
            assert item["model_plus_cache_index_bytes"] == (
                item["shared_preexisting_model_index_bytes"] + item["cache"] + item["index"]
            )
            assert item["encoder_reachable_bytes"] >= item["index"]
            assert item["peak_traced_bytes"] >= item["current_traced_bytes"]
        mixed = next(item for item in memory["measurement"]["encoding"] if item["shape"] == "mixed")
        assert mixed["traced"] and len(mixed["operations"]) == 24
        assert all(item["scratch_peak_above_retained_bytes"] >= 0 for item in mixed["operations"])
        if side == "new":
            assert not mixed["operations"][0]["ordinal_index_after"]
            assert mixed["operations"][2]["ordinal_index_after"]
            assert mixed["operations"][3]["key_type"] == "frozenset"
            assert mixed["operations"][3]["ordinal_index_before"]
            assert {
                entry["shape"]: entry["ordinal_index_initialized"]
                for entry in memory["measurement"]["cache"]
                if entry["shape"].startswith("threshold_")
            } == {
                "threshold_below": False,
                "threshold_at": False,
                "threshold_above": True,
            }
    for sample in evidence["samples"]:
        if sample["measurement"]["kind"] == "real":
            real = sample["measurement"]["real"]
            assert real["original_rows"] == 11
            assert real["report"]["oracle_invocations"] == 18
            assert sum(real["report"]["final_counts"].values()) == 3
            assert real["immutability"] and real["strict_reader"]
            assert real["integrity"] and real["foreign_keys"]
            assert len(real["replay"]["confirmations"]) == 3
    # The explicit historical reference is optional for smoke, so shallow CI
    # can validate recipe mechanics by archiving HEAD without fetching history.
    repeated = subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "benchmarks" / "lab.py"),
            "--directory",
            str(destination),
            "--mode",
            "smoke",
            "--baseline-ref",
            "HEAD",
            "--accepted-ref",
            "HEAD",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert repeated.returncode != 0
    unchanged = json.loads((destination / "comparison.json").read_text(encoding="utf-8"))
    assert unchanged == evidence


@pytest.mark.parametrize("sizes", [("1000000000",), ("16", "16"), ("16", "20", "24", "28")])
def test_benchmark_recipe_rejects_unbounded_workload_before_creation(
    tmp_path: Path, sizes: tuple[str, ...]
) -> None:
    destination = tmp_path / "not-created"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "benchmarks" / "lab.py"),
            "--directory",
            str(destination),
            "--sizes",
            *sizes,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert not destination.exists()
