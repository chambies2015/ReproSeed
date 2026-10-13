"""Focused diagnostic accounting, curated input causes and safe display regressions."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from reproseed.config import Asset, OracleSpec
from reproseed.diagnostics import diagnose, format_diagnosis, serialize_diagnosis
from reproseed.oracle import OracleInterrupted, OracleInvocation, OracleResult, Outcome
from reproseed.sqlite_adapter import DatabaseError
from reproseed.workflow import InvocationCounter


def _config(tmp_path: Path, schema: str = "CREATE TABLE items(id INTEGER PRIMARY KEY)") -> Path:
    with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as database:
        database.executescript(schema)
    (tmp_path / "oracle.py").write_text("private initial bytes", encoding="utf-8")
    config = tmp_path / "case.toml"
    config.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=["oracle.py"]\n'
        '[oracle]\nargv=["{python}","oracle.py","{db}"]\nexpected_exit=42\n'
        'marker="CONFIGURATION_SECRET"\nstream="stdout"\ntimeout_seconds=1.0\n'
        "output_limit_bytes=4096\n[reduction]\nmax_invocations=10\n",
        encoding="utf-8",
    )
    return config


def _target() -> OracleResult:
    return OracleResult(
        Outcome.TARGET_FAILURE, "expected exit and exact failure marker", 42, 21, 0.01
    )


@pytest.mark.parametrize("executed", [False, True, None])
def test_interruption_preserves_existing_counter_launch_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executed: bool | None
) -> None:
    config = _config(tmp_path)

    def interrupt(*args: object) -> OracleResult:
        raise OracleInterrupted(executed)

    monkeypatch.setattr("reproseed.workflow.run_oracle", interrupt)
    diagnosis = diagnose(config, allow_exec=True)
    document = diagnosis.as_dict()
    assert diagnosis.exit_code == 130
    assert document["interrupted"] is True
    assert document["accounting_complete"] is True
    assert document["actual_invocations"] == int(executed is True)
    assert document["unknown_interrupted_launches"] == int(executed is None)
    assert document["budget_charged_invocations"] == int(executed is not False)
    assert document["oracle_executed"] is executed
    assert document["baseline_confirmed"] is False
    assert document["baseline_results"] == []
    assert document["interrupted_invocations"] == [
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": executed}
    ]
    assert "Baseline reproduction: not established" in format_diagnosis(diagnosis)
    assert json.loads(serialize_diagnosis(diagnosis)) == document


@pytest.mark.parametrize("publish_first", [False, True])
def test_further_interrupt_exposes_incomplete_accounting_without_claiming_nonlaunch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, publish_first: bool
) -> None:
    config = _config(tmp_path)
    original = InvocationCounter._publish_accounting

    def interrupt_oracle(*args: object) -> OracleResult:
        raise OracleInterrupted(True)

    def interrupt_publication(counter: InvocationCounter, accounting: object) -> None:
        if publish_first:
            original(counter, accounting)
        raise KeyboardInterrupt

    monkeypatch.setattr("reproseed.workflow.run_oracle", interrupt_oracle)
    monkeypatch.setattr(InvocationCounter, "_publish_accounting", interrupt_publication)
    diagnosis = diagnose(config, allow_exec=True)
    assert diagnosis.exit_code == 130
    assert diagnosis.accounting_complete is False
    assert diagnosis.oracle_executed is (True if publish_first else None)
    assert diagnosis.actual_invocations == int(publish_first)
    assert diagnosis.baseline_confirmed is False
    assert "prevented complete invocation accounting" in format_diagnosis(diagnosis)


def test_result_publication_interruption_keeps_known_charge_without_inventing_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)

    def interrupt_result(result: OracleResult) -> dict[str, object]:
        raise KeyboardInterrupt

    monkeypatch.setattr("reproseed.workflow.run_oracle", lambda *args: _target())
    monkeypatch.setattr(OracleResult, "as_dict", interrupt_result)
    diagnosis = diagnose(config, allow_exec=True)
    assert diagnosis.exit_code == 130
    assert diagnosis.actual_invocations == diagnosis.unreported_invocations == 1
    assert diagnosis.baseline_results == diagnosis.interrupted_invocations == ()
    assert diagnosis.baseline_confirmed is False
    assert "unavailable result metadata: 1" in format_diagnosis(diagnosis)


@pytest.mark.parametrize("executed", [False, True, None])
def test_cleanup_abort_after_recording_preserves_complete_launch_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executed: bool | None
) -> None:
    config = _config(tmp_path)

    def abort_cleanup(*args: object) -> OracleResult:
        raise OracleInterrupted(executed, abort=True)

    monkeypatch.setattr("reproseed.workflow.run_oracle", abort_cleanup)
    diagnosis = diagnose(config, allow_exec=True)
    assert diagnosis.exit_code == 130
    assert diagnosis.accounting_complete is True
    assert diagnosis.actual_invocations == int(executed is True)
    assert diagnosis.unknown_interrupted_launches == int(executed is None)
    assert diagnosis.oracle_executed is executed
    assert diagnosis.interrupted_invocations == (
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": executed},
    )
    assert diagnosis.baseline_confirmed is False
    text = format_diagnosis(diagnosis)
    assert "prevented complete invocation accounting" not in text
    if executed is True:
        assert "Oracle: executed" in text
        assert "confirmed launch" in text


def test_assets_are_frozen_once_before_baseline_invocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    observed: list[str] = []

    def invoke(
        spec: OracleSpec, database: Path, assets: tuple[Asset, ...], state: OracleInvocation
    ) -> OracleResult:
        observed.append(assets[0].path.read_text(encoding="utf-8"))
        assert assets[0].path != tmp_path / "oracle.py"
        assert database != tmp_path / "source.sqlite3"
        (tmp_path / "oracle.py").write_text("external replacement bytes", encoding="utf-8")
        return _target()

    monkeypatch.setattr("reproseed.workflow.run_oracle", invoke)
    diagnosis = diagnose(config, allow_exec=True)
    assert diagnosis.exit_code == 0
    assert observed == ["private initial bytes"] * 3
    assert diagnosis.actual_invocations == 3
    assert diagnosis.baseline_confirmed is True
    assert all(
        result["reason_code"] == "target_contract_matched" for result in diagnosis.baseline_results
    )
    serialized = serialize_diagnosis(diagnosis)
    assert str(tmp_path) not in serialized
    assert "CONFIGURATION_SECRET" not in serialized
    assert "oracle.py" not in serialized


@pytest.mark.parametrize(
    "schema,reason",
    [
        ("CREATE TABLE items(id TEXT PRIMARY KEY)", "unsupported_primary_key"),
        (
            "CREATE TABLE items(id INTEGER PRIMARY KEY);"
            "CREATE TRIGGER changed AFTER INSERT ON items BEGIN SELECT 1; END;",
            "unsupported_trigger",
        ),
        (
            "CREATE TABLE parent(id INTEGER PRIMARY KEY);"
            "CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));"
            "INSERT INTO child VALUES(1,99);",
            "foreign_key_violation",
        ),
    ],
)
def test_curated_database_errors_do_not_execute_or_expose_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema: str, reason: str
) -> None:
    config = _config(tmp_path, schema)

    def unexpected(*args: object) -> OracleResult:
        pytest.fail("invalid database cannot execute an oracle")

    monkeypatch.setattr("reproseed.workflow.run_oracle", unexpected)
    diagnosis = diagnose(config, allow_exec=True)
    assert diagnosis.exit_code == 2
    assert diagnosis.error is not None and diagnosis.error.reason == reason
    assert diagnosis.actual_invocations == 0
    assert diagnosis.structurally_suitable is False
    assert diagnosis.integrity_valid is True
    assert diagnosis.foreign_keys_valid is (False if reason == "foreign_key_violation" else True)
    assert str(tmp_path) not in serialize_diagnosis(diagnosis)


@pytest.mark.parametrize(
    "table",
    [
        "foreign_key_check failed",
        "integrity_check failed",
        "triggers",
        "WITHOUT ROWID",
        "noninteger foreign key",
    ],
)
def test_schema_identifiers_cannot_reclassify_the_validator_failure(
    tmp_path: Path, table: str
) -> None:
    quoted = '"' + table.replace('"', '""') + '"'
    config = _config(tmp_path, f"CREATE TABLE {quoted}(id TEXT PRIMARY KEY)")
    diagnosis = diagnose(config, allow_exec=True)
    assert diagnosis.exit_code == 2
    assert diagnosis.error is not None and diagnosis.error.reason == "unsupported_primary_key"
    assert diagnosis.schema_supported is False
    assert diagnosis.integrity_valid is True
    assert diagnosis.foreign_keys_valid is True
    assert diagnosis.actual_invocations == 0


def test_snapshot_error_path_tokens_cannot_claim_database_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)

    def fail_snapshot(*args: object) -> None:
        raise DatabaseError(
            "Snapshot acquisition failed: private/path/"
            "foreign_key_check failed/integrity_check failed"
        )

    monkeypatch.setattr("reproseed.diagnostics.snapshot", fail_snapshot)
    diagnosis = diagnose(config, allow_exec=True)
    assert diagnosis.exit_code == 2
    assert diagnosis.error is not None and diagnosis.error.reason == "database_operation_failed"
    assert diagnosis.snapshot_acquired is False
    assert (
        diagnosis.integrity_valid
        is diagnosis.foreign_keys_valid
        is diagnosis.schema_supported
        is None
    )
    assert diagnosis.actual_invocations == 0
    assert "private/path" not in serialize_diagnosis(diagnosis)


def test_old_sqlite_does_not_classify_uninspected_schema_as_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("reproseed.sqlite_adapter.sqlite3.sqlite_version_info", (3, 36, 0))
    diagnosis = diagnose(config)
    assert diagnosis.exit_code == 2
    assert diagnosis.error is not None and diagnosis.error.reason == "unsupported_sqlite_version"
    assert diagnosis.schema_supported is None
    assert diagnosis.structurally_suitable is False


def test_table_name_controls_are_escaped_in_text(tmp_path: Path) -> None:
    table = 'stock\x1b[31m\u202e\u2028"items'
    quoted = '"' + table.replace('"', '""') + '"'
    config = _config(tmp_path, f"CREATE TABLE {quoted}(id INTEGER PRIMARY KEY)")
    diagnosis = diagnose(config)
    assert diagnosis.exit_code == 0
    assert diagnosis.as_dict()["table_counts"] == {table: 0}
    text = format_diagnosis(diagnosis)
    assert "\x1b" not in text and "\u202e" not in text and "\u2028" not in text
    assert "\\u001b" in text and "\\u202e" in text and "\\u2028" in text
    assert "Oracle: not executed" in text
    assert "Baseline reproduction: not established" in text


def test_input_asset_path_never_collides_with_private_snapshot(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (tmp_path / "pristine.sqlite3").write_text("a deliberately named supporting file")
    config.write_text(config.read_text().replace('["oracle.py"]', '["pristine.sqlite3"]'))
    diagnosis = diagnose(config)
    assert diagnosis.exit_code == 0
    assert diagnosis.assets_validated is True
    assert (tmp_path / "pristine.sqlite3").read_text() == "a deliberately named supporting file"
