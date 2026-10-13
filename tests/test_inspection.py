"""Read-only CLI inspection against synthetic, real-file bundles."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import unicodedata
from contextlib import closing
from pathlib import Path

import pytest

from reproseed.artifacts import create_bundle, sha256
from reproseed.cli import main
from reproseed.config import Asset, OracleSpec, load_config
from reproseed.inspection import escape_terminal
from reproseed.oracle import OracleInterrupted, OracleResult, run_oracle


def _bundle(
    directory: Path,
    *,
    rows: int = 1,
    budget: int = 40,
    table: str = "things",
    oracle: str = "print('TARGET'); raise SystemExit(42)",
) -> tuple[Path, dict[str, object]]:
    quoted = '"' + table.replace('"', '""') + '"'
    with closing(sqlite3.connect(directory / "source.sqlite3")) as database:
        database.execute(f"CREATE TABLE {quoted}(id INTEGER PRIMARY KEY, value TEXT)")
        database.executemany(
            f"INSERT INTO {quoted} VALUES(?,?)",
            [(number, "synthetic row value omitted from summary") for number in range(rows)],
        )
        database.commit()
    (directory / "oracle.py").write_text(oracle, encoding="utf-8")
    config = directory / "case.toml"
    config.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="TARGET"\nstream="stdout"\ntimeout_seconds=2.0\noutput_limit_bytes=4096\n'
        f"[reduction]\nmax_invocations={budget}\n",
        encoding="utf-8",
    )
    bundle = directory / "bundle"
    return bundle, create_bundle(load_config(config), bundle)


def _contents(bundle: Path) -> dict[str, str]:
    return {
        file.relative_to(bundle).as_posix(): sha256(file)
        for file in bundle.rglob("*")
        if file.is_file()
    }


def test_default_and_explicit_json_preserve_report_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle, report = _bundle(tmp_path)
    assert main(["inspect", str(bundle)]) == 0
    default = capsys.readouterr()
    assert not default.err
    assert json.loads(default.out) == report
    assert main(["inspect", str(bundle), "--format", "json"]) == 0
    explicit = capsys.readouterr()
    assert not explicit.err
    assert explicit.out == default.out


@pytest.mark.parametrize("case", ["normal", "zero", "budget", "unresolved", "irreducible"])
def test_text_summarizes_real_validated_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    oracle = "print('TARGET'); raise SystemExit(42)"
    if case in {"unresolved", "irreducible"}:
        oracle = (
            "import sqlite3,sys\n"
            "c=sqlite3.connect(sys.argv[1])\n"
            "rows=c.execute('SELECT count(*) FROM things').fetchone()[0]\nc.close()\n"
            "if rows:\n    print('TARGET')\n    raise SystemExit(42)\n"
            f"raise SystemExit({43 if case == 'unresolved' else 0})\n"
        )
    bundle, report = _bundle(
        tmp_path,
        rows=0 if case == "zero" else 1,
        budget=6 if case == "budget" else 40,
        oracle=oracle,
    )
    assert main(["inspect", str(bundle), "--format", "text"]) == 0
    result = capsys.readouterr()
    assert not result.err
    text = result.out
    assert "bundle format 1 / report format 1" in text
    assert "Recorded tool: reproseed " in text
    assert "Recorded runtime: Python " in text
    assert "SQLite " in text
    assert "Artifact integrity: checked now" in text
    assert "Recorded evidence: structure and consistency checked now" in text
    assert "Fixture structure/counts: checked now" in text
    assert "Recorded baseline confirmations: 3/3 TARGET_FAILURE" in text
    assert "Recorded final confirmations: 3/3 TARGET_FAILURE" in text
    assert "New replay: not performed by inspect (oracle not executed)" in text
    assert "do not authenticate historical executions" in text
    assert "Reduction is not anonymization or proof of global minimality." in text
    assert f"Recorded oracle executions: {report['oracle_invocations']}" in text
    assert (
        f"Budget charged: {report['budget_charged_invocations']}/{report['max_invocations']}"
        in text
    )
    assert f"Cache hits: {report['cache_hits']} (reused evidence; no new executions)" in text
    assert f"{report['unresolved_attempts']} unresolved trials" in text
    assert f"{report['invalid_candidates']} invalid candidates" in text
    assert "synthetic row value" not in text
    assert 'confirmations": [' not in text
    if case == "normal":
        assert '"things": 1 -> 0' in text
        assert "Rows: 1 original -> 0 retained (100.0% removed)" in text
        assert "1 accepted reductions" in text
        assert "No rows remain" in text
    elif case == "zero":
        assert '"things": 0 -> 0' in text
        assert "n/a; original fixture has zero rows" in text
    elif case == "budget":
        assert '"things": 1 -> 1' in text
        assert "0.0% removed" in text
        assert "Oracle budget stopped the search" in text
        assert "final verification capacity was reserved" in text
    elif case == "unresolved":
        assert "1 unresolved trials" in text
        assert "Single-row deletion closures exhausted; unresolved trials may remain" in text
    else:
        assert '"things": 1 -> 1' in text
        assert "Single-row deletion closures exhausted" in text


def test_controls_in_table_and_runtime_strings_are_escaped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    table = 'table\nFAKE\r\t\x1b[31m\x7f\x85\u2028\u2029\u202e\u2066"end'
    bundle, _ = _bundle(tmp_path, table=table)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tool_version"] = "0.1.0\x1b[2J\nFAKE"
    manifest["runtime"]["python"] += "\u202eFAKE"
    manifest["runtime"]["sqlite"] += "\x85FAKE"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert main(["inspect", str(bundle), "--format", "text"]) == 0
    result = capsys.readouterr()
    assert not result.err
    assert escape_terminal(json.dumps(table, ensure_ascii=False)) in result.out
    assert "0.1.0\\u001b[2J\\u000aFAKE" in result.out
    assert "\\u202eFAKE" in result.out
    assert "\\u0085FAKE" in result.out
    assert all(
        character == "\n" or unicodedata.category(character) not in {"Cc", "Cf", "Zl", "Zp"}
        for character in result.out
    )
    assert not any(line.startswith("FAKE") for line in result.out.splitlines())


def test_text_separates_cached_evidence_from_new_executions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oracle = (
        "import sqlite3,sys\n"
        "c=sqlite3.connect(sys.argv[1])\n"
        "rows=c.execute('SELECT count(*) FROM things').fetchone()[0]\nc.close()\n"
        "if rows:\n    print('TARGET')\n    raise SystemExit(42)\n"
        "raise SystemExit(0)\n"
    )
    bundle, report = _bundle(tmp_path, rows=3, oracle=oracle)
    assert isinstance(report["cache_hits"], int) and report["cache_hits"] > 0
    attempts = report["attempts"]
    assert isinstance(attempts, list)
    recorded_executions = 6 + sum(
        sum(record["executed"] is True for record in attempt["confirmations"])
        for attempt in attempts
        if not attempt["cached"]
    )
    assert report["oracle_invocations"] == recorded_executions
    assert main(["inspect", str(bundle), "--format", "text"]) == 0
    text = capsys.readouterr().out
    assert f"Recorded oracle executions: {recorded_executions}" in text
    assert f"Cache hits: {report['cache_hits']} (reused evidence; no new executions)" in text


def test_text_distinguishes_unknown_interrupted_launch_from_known_executions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def interrupted(spec: OracleSpec, database: Path, assets: tuple[Asset, ...]) -> OracleResult:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OracleInterrupted(None)
        return run_oracle(spec, database, assets)

    monkeypatch.setattr("reproseed.workflow.run_oracle", interrupted)
    bundle, report = _bundle(tmp_path)
    assert report["oracle_invocations"] == 6
    assert report["budget_charged_invocations"] == 7
    assert main(["inspect", str(bundle), "--format", "text"]) == 0
    text = capsys.readouterr().out
    assert "Recorded oracle executions: 6" in text
    assert "Budget charged: 7/40 (1 unknown interrupted launches)" in text
    assert "Search interrupted; the best confirmed candidate was preserved" in text


def test_inspect_never_executes_sentinel_oracle_and_preserves_every_file(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel.txt"
    oracle = (
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('executed')\n"
        "print('RAW_ORACLE_OUTPUT_NOT_FOR_INSPECTION')\n"
        "print('TARGET'); raise SystemExit(42)\n"
    )
    bundle, report = _bundle(tmp_path, oracle=oracle, budget=6)
    assert sentinel.read_text() == "executed"
    sentinel.unlink()
    before = _contents(bundle)
    source_before = sha256(tmp_path / "source.sqlite3")
    for extra in ([], ["--format", "json"], ["--format", "text"]):
        completed = subprocess.run(
            [sys.executable, "-m", "reproseed", "inspect", str(bundle), *extra],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert not completed.stderr
        assert not sentinel.exists()
        assert _contents(bundle) == before
        assert sha256(tmp_path / "source.sqlite3") == source_before
        assert "RAW_ORACLE_OUTPUT_NOT_FOR_INSPECTION" not in completed.stdout
        assert "synthetic row value" not in completed.stdout
        if extra != ["--format", "text"]:
            assert json.loads(completed.stdout) == report


@pytest.mark.parametrize("inspection_format", ["json", "text"])
def test_invalid_bundle_has_existing_error_category_and_no_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], inspection_format: str
) -> None:
    bundle, _ = _bundle(tmp_path)
    (bundle / "report.json").write_text("corrupted", encoding="utf-8")
    assert main(["inspect", str(bundle), "--format", inspection_format]) == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert "reproseed:" in result.err
    assert "artifact hash mismatch" in result.err
