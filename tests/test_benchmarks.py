"""Small isolated recipe coverage; large performance runs stay outside ordinary CI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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
    assert len(evidence["semantic_comparisons"]) == 6
    assert all(item["equal"] for item in evidence["semantic_comparisons"])
    sides = set()
    for sample in evidence["samples"]:
        sides.add(sample["side"])
        origin = sample["measurement"]["provenance"]
        expected = destination / (
            "baseline-source" if sample["side"] == "baseline" else "new-source"
        )
        assert Path(origin["source"]) == expected
        for module in origin["modules"].values():
            assert Path(module["path"]).is_relative_to(expected / "src")
            assert len(module["sha256"]) == 64
    assert sides == {"baseline", "new"}
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
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert repeated.returncode != 0
    unchanged = json.loads((destination / "comparison.json").read_text(encoding="utf-8"))
    assert unchanged == evidence


def test_benchmark_recipe_rejects_unbounded_workload_before_creation(tmp_path: Path) -> None:
    destination = tmp_path / "not-created"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "benchmarks" / "lab.py"),
            "--directory",
            str(destination),
            "--sizes",
            "1000000000",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert not destination.exists()
