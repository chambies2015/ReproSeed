"""Version-one evidence checks against synthetic records and real bundles."""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from reproseed.artifacts import BundleError, create_bundle, sha256, validate_bundle
from reproseed.config import Config, OracleSpec, load_config
from reproseed.oracle import OracleInterrupted, OracleResult, Outcome
from reproseed.report import ReportError, validate_report
from reproseed.workflow import build_verified_fixture


@pytest.fixture
def report_config(tmp_path: Path) -> Config:
    return Config(
        tmp_path / "case.toml",
        tmp_path / "source.sqlite3",
        (),
        OracleSpec(("{python}", "oracle.py", "{db}"), 42, "TARGET", "stdout", 1.0, 4096),
        20,
    )


def confirmation(outcome: str = "TARGET_FAILURE") -> dict[str, Any]:
    return {
        "outcome": outcome,
        "reason": (
            "expected exit and exact failure marker"
            if outcome == "TARGET_FAILURE"
            else "zero exit without target marker"
        ),
        "exit_code": 42 if outcome == "TARGET_FAILURE" else 0,
        "output_bytes": 7 if outcome == "TARGET_FAILURE" else 0,
        "duration_seconds": 0.01,
        "executed": True,
    }


@pytest.fixture
def valid_report() -> dict[str, Any]:
    passed = {
        "number": 1,
        "retained_rows": 0,
        "removed_rows": 3,
        "outcome": "PASS",
        "reason": "zero exit without target marker",
        "cached": False,
        "confirmations": [confirmation("PASS")],
    }
    cached = deepcopy(passed)
    cached.update(number=3, removed_rows=2, cached=True)
    return {
        "version": 1,
        "verified": True,
        "original_counts": {"things": 3},
        "final_counts": {"things": 2},
        "oracle_invocations": 9,
        "unknown_interrupted_launches": 0,
        "budget_charged_invocations": 9,
        "interrupted_invocations": [],
        "max_invocations": 20,
        "baseline_verification": [confirmation() for _ in range(3)],
        "final_verification": [confirmation() for _ in range(3)],
        "attempts": [
            passed,
            {
                "number": 2,
                "retained_rows": 2,
                "removed_rows": 1,
                "outcome": "TARGET_FAILURE",
                "reason": "two_fresh_confirmations",
                "cached": False,
                "confirmations": [confirmation(), confirmation()],
            },
            cached,
        ],
        "accepted_reductions": [{"attempt": 2, "before": 3, "after": 2}],
        "cache_hits": 1,
        "unresolved_attempts": 0,
        "invalid_candidates": 0,
        "termination_reason": "single_row_closures_exhausted",
        "minimality": (
            "No global minimality claim; exhausted closures may include unresolved trials."
        ),
    }


def replace_field(report: dict[str, Any], path: tuple[str | int, ...], value: Any) -> None:
    record: Any = report
    for part in path[:-1]:
        record = record[part]
    record[path[-1]] = value


def test_current_report_and_cached_confirmations_are_valid(
    valid_report: dict[str, Any], report_config: Config
) -> None:
    # The cached PASS repeats executed=True; it is evidence, not a new launch.
    validate_report(valid_report, report_config)


@pytest.mark.parametrize(
    "path,value",
    [
        (("version",), True),
        (("version",), 2),
        (("verified",), 1),
        (("verified",), False),
        (("original_counts", "things"), -1),
        (("original_counts", "things"), True),
        (("final_counts", "things"), 4),
        (("final_counts", "things"), 1.5),
        (("final_counts",), {"other": 2}),
        (("oracle_invocations",), True),
        (("oracle_invocations",), -1),
        (("oracle_invocations",), 10),
        (("unknown_interrupted_launches",), 1),
        (("budget_charged_invocations",), 10),
        (("max_invocations",), 19),
        (("max_invocations",), True),
        (("baseline_verification",), []),
        (("final_verification",), [confirmation(), confirmation()]),
        (("baseline_verification", 0), confirmation("PASS")),
        (("final_verification", 0, "outcome"), "UNRESOLVED"),
        (("baseline_verification", 0, "executed"), False),
        (("final_verification", 0, "executed"), 1),
        (("final_verification", 0, "exit_code"), 43),
        (("final_verification", 0, "exit_code"), True),
        (("final_verification", 0, "output_bytes"), True),
        (("final_verification", 0, "output_bytes"), 0),
        (("final_verification", 0, "output_bytes"), 5),
        (("final_verification", 0, "duration_seconds"), -0.01),
        (("final_verification", 0, "duration_seconds"), math.nan),
        (("final_verification", 0, "duration_seconds"), math.inf),
        (("final_verification", 0, "duration_seconds"), -math.inf),
        (("final_verification", 0, "duration_seconds"), True),
        (("final_verification", 0, "duration_seconds"), 10**400),
        (("attempts", 1, "confirmations"), [confirmation()]),
        (("attempts", 1, "confirmations", 1), confirmation("PASS")),
        (("attempts", 1, "confirmations", 0, "executed"), False),
        (("attempts", 1, "number"), True),
        (("attempts", 1, "number"), 3),
        (("attempts", 1, "removed_rows"), 2),
        (("attempts", 1, "retained_rows"), -1),
        (("attempts", 1, "cached"), 0),
        (("attempts", 2, "confirmations", 0, "duration_seconds"), 0.2),
        (("accepted_reductions", 0, "attempt"), 99),
        (("accepted_reductions", 0, "attempt"), True),
        (("accepted_reductions", 0, "before"), 2),
        (("accepted_reductions", 0, "after"), 3),
        (("accepted_reductions",), []),
        (("cache_hits",), 2),
        (("unresolved_attempts",), 1),
        (("invalid_candidates",), 1),
        (("termination_reason",), "done"),
        (("termination_reason",), "empty_candidate_confirmed"),
        (("termination_reason",), "oracle_budget_exhausted_reserved_final_verification"),
        (
            ("interrupted_invocations",),
            [{"outcome": "UNRESOLVED", "reason": "interrupted", "executed": True}],
        ),
    ],
)
def test_inconsistent_report_is_rejected(
    valid_report: dict[str, Any], report_config: Config, path: tuple[str | int, ...], value: Any
) -> None:
    replace_field(valid_report, path, value)
    with pytest.raises(ReportError):
        validate_report(valid_report, report_config)


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("baseline_verification", 0),
        ("attempts", 0),
        ("accepted_reductions", 0),
    ],
)
def test_unknown_fields_rejected_at_record_levels(
    valid_report: dict[str, Any], report_config: Config, path: tuple[str | int, ...]
) -> None:
    record: Any = valid_report
    for part in path:
        record = record[part]
    record["future_field"] = 1
    with pytest.raises(ReportError, match="unknown fields"):
        validate_report(valid_report, report_config)


def test_budget_exhaustion_can_leave_one_search_slot_unused(
    valid_report: dict[str, Any], report_config: Config
) -> None:
    from dataclasses import replace

    valid_report["max_invocations"] = 10
    valid_report["termination_reason"] = "oracle_budget_exhausted_reserved_final_verification"
    validate_report(valid_report, replace(report_config, max_invocations=10))


def test_database_invalid_and_cached_invalid_have_no_execution_charge(
    valid_report: dict[str, Any], report_config: Config
) -> None:
    for index in (0, 2):
        valid_report["attempts"][index].update(
            outcome="DATABASE_INVALID", reason="candidate failed integrity check", confirmations=[]
        )
    valid_report.update(oracle_invocations=8, budget_charged_invocations=8, invalid_candidates=2)
    validate_report(valid_report, report_config)


@pytest.mark.parametrize("executed", [False, True, None])
@pytest.mark.parametrize("completed_first", [False, True])
def test_interrupted_writer_output_keeps_known_and_unknown_launches_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executed: bool | None, completed_first: bool
) -> None:
    with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as database:
        database.executescript(
            "CREATE TABLE things(id INTEGER PRIMARY KEY);INSERT INTO things VALUES(1);"
        )
    config = Config(
        tmp_path / "case.toml",
        tmp_path / "source.sqlite3",
        (),
        OracleSpec(("unused",), 42, "TARGET", "stdout", 1.0, 4096),
        20,
    )
    calls = 0

    def invoke(*args: object) -> OracleResult:
        nonlocal calls
        calls += 1
        if calls == (5 if completed_first else 4):
            raise OracleInterrupted(executed)
        return OracleResult(
            Outcome.TARGET_FAILURE, "expected exit and exact failure marker", 42, 7, 0.01
        )

    monkeypatch.setattr("reproseed.workflow.run_oracle", invoke)
    report = build_verified_fixture(config, tmp_path / "final.sqlite3")
    assert report["oracle_invocations"] == 6 + completed_first + (executed is True)
    assert report["unknown_interrupted_launches"] == (executed is None)
    assert report["termination_reason"] == "interrupted_best_confirmed_candidate_preserved"
    validate_report(report, config)


@pytest.mark.parametrize("missing_confirmations", [0, 1, 2])
def test_interrupted_reducer_boundary_allows_bounded_unrecorded_confirmations(
    valid_report: dict[str, Any], report_config: Config, missing_confirmations: int
) -> None:
    valid_report.update(
        termination_reason="interrupted_best_confirmed_candidate_preserved",
        oracle_invocations=9 + missing_confirmations,
        budget_charged_invocations=9 + missing_confirmations,
    )
    validate_report(valid_report, report_config)
    valid_report.update(oracle_invocations=12, budget_charged_invocations=12)
    with pytest.raises(ReportError, match="execution total"):
        validate_report(valid_report, report_config)


def test_unknown_launch_does_not_substitute_for_known_confirmation(
    valid_report: dict[str, Any], report_config: Config
) -> None:
    valid_report.update(
        termination_reason="interrupted_best_confirmed_candidate_preserved",
        interrupted_invocations=[
            {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": None}
        ],
        unknown_interrupted_launches=1,
        oracle_invocations=8,
        budget_charged_invocations=9,
    )
    with pytest.raises(ReportError, match="execution total"):
        validate_report(valid_report, report_config)


@pytest.mark.parametrize(
    "table_name,rows,retain_one", [("", 1, False), ("things", 0, False), ("things", 1, True)]
)
def test_empty_and_irreducible_genuine_writer_reports_remain_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    table_name: str,
    rows: int,
    retain_one: bool,
) -> None:
    quoted = '"' + table_name.replace('"', '""') + '"'
    with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as database:
        database.execute(f"CREATE TABLE {quoted}(id INTEGER PRIMARY KEY)")
        if rows:
            database.execute(f"INSERT INTO {quoted} VALUES(1)")
            database.commit()
    config = Config(
        tmp_path / "case.toml",
        tmp_path / "source.sqlite3",
        (),
        OracleSpec(("unused",), 42, "TARGET", "stdout", 1.0, 4096),
        20,
    )

    def invoke(spec: OracleSpec, path: Path, assets: object) -> OracleResult:
        with closing(sqlite3.connect(path)) as database:
            empty = database.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0] == 0
        if empty and retain_one:
            return OracleResult(Outcome.PASS, "zero exit without target marker", 0, 0, 0.01)
        return OracleResult(
            Outcome.TARGET_FAILURE, "expected exit and exact failure marker", 42, 7, 0.01
        )

    monkeypatch.setattr("reproseed.workflow.run_oracle", invoke)
    report = build_verified_fixture(config, tmp_path / "final.sqlite3")
    assert report["original_counts"] == {table_name: rows}
    assert report["final_counts"] == {table_name: int(retain_one)}
    validate_report(report, config)


def test_unicode_marker_without_newline_uses_its_utf8_byte_length(tmp_path: Path) -> None:
    with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as database:
        database.execute("CREATE TABLE things(id INTEGER PRIMARY KEY)")
    marker = "T😀"
    config = Config(
        tmp_path / "case.toml",
        tmp_path / "source.sqlite3",
        (),
        OracleSpec(
            (
                "{python}",
                "-c",
                f"import sys;sys.stdout.buffer.write({marker!r}.encode('utf8'));sys.exit(42)",
            ),
            42,
            marker,
            "stdout",
            1.0,
            4096,
        ),
        6,
    )
    report = build_verified_fixture(config, tmp_path / "final.sqlite3")
    assert report["baseline_verification"][0]["output_bytes"] == len(marker.encode("utf-8"))
    validate_report(report, config)
    report["final_verification"][0]["output_bytes"] = len(marker)
    with pytest.raises(ReportError, match="oracle outcome evidence"):
        validate_report(report, config)


@pytest.mark.parametrize(
    "reason,exit_code,output_bytes,valid",
    [
        ("unexpected exit code", -9, 0, False),
        ("unexpected exit code", 43, 0, True),
        ("unexpected exit code", None, 0, True),
        ("combined output limit exceeded", 42, 4096, False),
        ("combined output limit exceeded", 42, 4097, True),
    ],
)
def test_unresolved_reason_agrees_with_exit_and_output_evidence(
    valid_report: dict[str, Any],
    report_config: Config,
    reason: str,
    exit_code: int | None,
    output_bytes: int,
    valid: bool,
) -> None:
    result = confirmation()
    result.update(
        outcome="UNRESOLVED", reason=reason, exit_code=exit_code, output_bytes=output_bytes
    )
    valid_report["attempts"][2].update(
        outcome="UNRESOLVED", reason=reason, cached=False, confirmations=[result]
    )
    valid_report.update(
        cache_hits=0, unresolved_attempts=1, oracle_invocations=10, budget_charged_invocations=10
    )
    if valid:
        validate_report(valid_report, report_config)
    else:
        with pytest.raises(ReportError, match="oracle outcome evidence"):
            validate_report(valid_report, report_config)


def test_rehashed_shallow_report_is_rejected(tmp_path: Path) -> None:
    with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as database:
        database.execute("CREATE TABLE things(id INTEGER PRIMARY KEY)")
    (tmp_path / "oracle.py").write_text("print('TARGET'); raise SystemExit(42)", encoding="utf-8")
    config = tmp_path / "case.toml"
    config.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="TARGET"\nstream="stdout"\ntimeout_seconds=1.0\noutput_limit_bytes=4096\n'
        "[reduction]\nmax_invocations=6\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle"
    create_bundle(load_config(config), bundle)
    report = bundle / "report.json"
    report.write_text('{"version":1,"verified":true}', encoding="utf-8")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["report.json"] = sha256(report)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BundleError, match="report"):
        validate_bundle(bundle)
