"""Readiness checks and optional fresh baseline confirmations, without reduction."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from reproseed.config import Asset, Config, ConfigError, load_config, safe_file
from reproseed.inspection import escape_terminal
from reproseed.oracle import OracleInterrupted, Outcome
from reproseed.reducer import AbortReduction
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel, snapshot
from reproseed.workflow import InvocationCounter

_REASON_CODES = {
    "expected exit and exact failure marker": "target_contract_matched",
    "zero exit without target marker": "clean_non_target_exit",
    "unexpected exit code": "unexpected_exit",
    "expected failure exit without exact marker": "missing_exact_marker",
    "target marker contradicts zero exit": "marker_zero_exit_contradiction",
    "process terminated by signal": "process_signal",
    "deadline exceeded (process or open output pipes)": "timeout",
    "combined output limit exceeded": "output_limit",
    "output read failed": "output_read_error",
    "launch_error": "launch_error",
    "staging_error": "staging_error",
}


@dataclass(frozen=True)
class DiagnosticError:
    stage: str
    reason: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"stage": self.stage, "reason": self.reason, "message": self.message}


@dataclass(frozen=True)
class Diagnosis:
    """Version-1 diagnostic facts; no report or replay-bundle evidence is written."""

    mode: Literal["static", "baseline"]
    snapshot_acquired: bool
    schema_supported: bool | None
    structurally_suitable: bool
    assets_validated: bool
    table_counts: dict[str, int]
    config: Config | None = field(repr=False)
    baseline_results: tuple[dict[str, object], ...] = ()
    actual_invocations: int = 0
    unknown_interrupted_launches: int = 0
    interrupted_invocations: tuple[dict[str, object], ...] = ()
    unreported_invocations: int = 0
    accounting_complete: bool = True
    interrupted: bool = False
    error: DiagnosticError | None = None

    @property
    def baseline_confirmed(self) -> bool:
        return (
            self.mode == "baseline"
            and self.structurally_suitable
            and not self.interrupted
            and self.error is None
            and len(self.baseline_results) == 3
            and all(result["outcome"] == Outcome.TARGET_FAILURE for result in self.baseline_results)
        )

    @property
    def oracle_executed(self) -> bool | None:
        if self.actual_invocations:
            return True
        return None if self.unknown_interrupted_launches or not self.accounting_complete else False

    @property
    def exit_code(self) -> int:
        if self.interrupted:
            return 130
        if self.error is not None:
            return 2
        return 0 if self.mode == "static" or self.baseline_confirmed else 1

    @property
    def integrity_valid(self) -> bool | None:
        # The shared model checks integrity, schema/key policy, then foreign keys.
        if self.error is not None and self.error.reason in {
            "unsupported_unavailable_collation",
            "unsupported_text_encoding",
        }:
            return None
        if (
            self.structurally_suitable
            or self.schema_supported is False
            or (self.error is not None and self.error.reason == "foreign_key_violation")
        ):
            return True
        return (
            False if self.error is not None and self.error.reason == "integrity_failure" else None
        )

    @property
    def foreign_keys_valid(self) -> bool | None:
        if self.structurally_suitable:
            return True
        return (
            False
            if self.error is not None and self.error.reason == "foreign_key_violation"
            else None
        )

    def as_dict(self) -> dict[str, object]:
        contract: dict[str, object] | None = None
        limits: dict[str, object] | None = None
        if self.config is not None:
            spec = self.config.oracle
            contract = {
                "expected_exit": spec.expected_exit,
                "stream": spec.stream,
                "marker_matching": "exact_whole_utf8_line",
                "marker_utf8_bytes": len(spec.marker.encode("utf-8")),
                "argv_argument_count": len(spec.argv),
            }
            limits = {
                "timeout_seconds": spec.timeout_seconds,
                "output_limit_bytes": spec.output_limit_bytes,
                "max_invocations": self.config.max_invocations,
            }
        return {
            "diagnostic_version": 1,
            "mode": self.mode,
            "snapshot_acquired": self.snapshot_acquired,
            "schema_supported": self.schema_supported,
            "integrity_valid": self.integrity_valid,
            "foreign_keys_valid": self.foreign_keys_valid,
            "assets_validated": self.assets_validated,
            "structurally_suitable": self.structurally_suitable,
            "table_counts": dict(sorted(self.table_counts.items())),
            "total_rows": sum(self.table_counts.values()),
            "oracle_contract": contract,
            "limits": limits,
            "required_baseline_confirmations": 3,
            "oracle_executed": self.oracle_executed,
            "baseline_confirmed": self.baseline_confirmed,
            "baseline_results": list(self.baseline_results),
            "actual_invocations": self.actual_invocations,
            "unknown_interrupted_launches": self.unknown_interrupted_launches,
            "budget_charged_invocations": (
                self.actual_invocations + self.unknown_interrupted_launches
            ),
            "interrupted_invocations": list(self.interrupted_invocations),
            "unreported_invocations": self.unreported_invocations,
            "accounting_complete": self.accounting_complete,
            "interrupted": self.interrupted,
            "error": None if self.error is None else self.error.as_dict(),
        }


def _input_error(error: Exception, stage: str) -> DiagnosticError:
    """Curate causes from existing validators without publishing their file paths/values."""
    message = str(error)
    if isinstance(error, ConfigError):
        if message.startswith("source database is not a regular file"):
            reason, detail = "source_unavailable", "The source database is not a regular file."
        elif message.startswith("expected a regular file inside configuration root"):
            reason, detail = "asset_unavailable", "An explicitly included asset is unavailable."
        elif message.startswith(("unsafe relative path", "nonportable file path", "file paths")):
            reason, detail = (
                "unsafe_asset_path",
                "Included files need safe portable relative paths.",
            )
        elif message.startswith("symlinks and junctions"):
            reason, detail = "linked_asset", "Included assets cannot use symlinks or junctions."
        elif message.startswith(("reserved or duplicate", "conflicting asset", "include must")):
            reason, detail = "invalid_asset_selection", "The explicit asset selection is invalid."
        elif message.startswith("configuration exceeds"):
            reason, detail = "configuration_limit", "Configuration exceeds the 1 MiB read limit."
        elif message.startswith("cannot read TOML"):
            reason, detail = "malformed_configuration", "Cannot read valid bounded UTF-8 TOML."
        elif message.startswith(("argv", "oracle.argv")):
            reason, detail = (
                "invalid_oracle_argv",
                "Oracle argv or its whole-argument placeholders are invalid.",
            )
        elif message.startswith("oracle.marker"):
            reason, detail = (
                "invalid_oracle_marker",
                "The exact oracle marker must be one bounded UTF-8 line.",
            )
        elif message.startswith("oracle.stream"):
            reason, detail = (
                "invalid_oracle_stream",
                "The configured marker stream must be stdout or stderr.",
            )
        elif message.startswith(("oracle.timeout", "oracle.output_limit", "reduction.max")):
            reason, detail = (
                "invalid_execution_limit",
                "Configured execution limits are outside permitted bounds.",
            )
        elif message.startswith("oracle.expected_exit"):
            reason, detail = (
                "invalid_expected_exit",
                "The expected oracle exit must be an integer from 1 to 255.",
            )
        elif message.startswith("version"):
            reason, detail = "unsupported_configuration_version", "Configuration version must be 1."
        else:
            reason, detail = (
                "invalid_configuration",
                "Configuration has missing, unknown or invalid fields.",
            )
    elif isinstance(error, DatabaseError):
        if stage == "snapshot" and message == "Snapshot acquisition timed out":
            reason, detail = (
                "snapshot_timeout",
                "The read-only snapshot acquisition deadline expired.",
            )
        elif stage == "database_validation" and message == (
            "Database foreign_key_check failed: foreign-key violations exist"
        ):
            reason, detail = "foreign_key_violation", "Database foreign-key validation failed."
        elif stage == "database_validation" and message.startswith(
            "Database integrity_check failed ("
        ):
            reason, detail = "integrity_failure", "Database integrity validation failed."
        elif stage == "database_validation" and (
            message.startswith("Unsupported schema: ")
            or message.startswith("Noninteger primary-key value in ")
            or message.startswith("Noninteger foreign-key value in ")
            or message.startswith("Nontext primary-key value in ")
            or message.startswith("Nontext foreign-key value in ")
        ):
            restrictions = (
                (
                    "Unsupported schema: triggers are not supported",
                    "unsupported_trigger",
                    "Triggers are outside the supported schema subset.",
                ),
                (
                    "Unsupported schema: WITHOUT ROWID table ",
                    "unsupported_without_rowid",
                    "WITHOUT ROWID tables are unsupported.",
                ),
                (
                    "Unsupported schema: generated or hidden columns in ",
                    "unsupported_generated_column",
                    "Generated or hidden columns are unsupported.",
                ),
                (
                    "Unsupported schema: composite foreign key in ",
                    "unsupported_composite_foreign_key",
                    "Composite foreign keys are unsupported.",
                ),
                (
                    "Unsupported schema: foreign key must target ",
                    "unsupported_foreign_key_target",
                    "Foreign keys must reference a supported INTEGER or TEXT primary key.",
                ),
                (
                    "Unsupported schema: foreign-key parent ",
                    "unsupported_foreign_key_parent",
                    "A foreign-key parent is outside the supported schema subset.",
                ),
                (
                    "Unsupported schema: noninteger foreign key in ",
                    "unsupported_foreign_key_type",
                    "Foreign-key columns must have integer affinity.",
                ),
                (
                    "Unsupported schema: nontext foreign key in ",
                    "unsupported_foreign_key_type",
                    "Foreign keys to TEXT parents need exactly declared TEXT columns.",
                ),
                (
                    "Unsupported schema: NULL TEXT primary-key value",
                    "unsupported_null_text_primary_key",
                    "TEXT primary keys must contain no NULL values in the snapshot.",
                ),
                (
                    "Unsupported schema: TEXT key collation",
                    "unsupported_text_key_collation",
                    "TEXT primary-key columns and indexes must use BINARY collation.",
                ),
                (
                    "Unsupported schema: TEXT primary-key collation metadata",
                    "unsupported_text_key_collation",
                    "TEXT primary-key collation metadata must establish BINARY comparisons.",
                ),
                (
                    "Unsupported schema: unavailable collation metadata",
                    "unsupported_unavailable_collation",
                    "The database requires an unavailable collation; TEXT keys need BINARY.",
                ),
                (
                    "Unsupported schema: malformed TEXT encoding",
                    "unsupported_text_encoding",
                    "TEXT keys and schema metadata must decode as valid Unicode strings.",
                ),
                (
                    "Nontext primary-key value in ",
                    "unsupported_primary_key_value",
                    "TEXT primary-key values must have actual SQLite TEXT storage class.",
                ),
                (
                    "Nontext foreign-key value in ",
                    "unsupported_foreign_key_value",
                    "Non-null foreign keys to TEXT parents must have SQLite TEXT storage class.",
                ),
                (
                    "Noninteger foreign-key value in ",
                    "unsupported_foreign_key_value",
                    "Non-null foreign-key values must be stored integers.",
                ),
                (
                    "Unsupported schema: non-rowid-alias INTEGER primary key in ",
                    "unsupported_primary_key",
                    "Each table needs one rowid-alias INTEGER PRIMARY KEY.",
                ),
                (
                    "Unsupported schema: virtual table ",
                    "unsupported_virtual_table",
                    "Virtual tables are outside the supported schema subset.",
                ),
                (
                    "Unsupported schema: shadow table ",
                    "unsupported_shadow_table",
                    "Shadow tables are outside the supported schema subset.",
                ),
                (
                    "Noninteger primary-key value in ",
                    "unsupported_primary_key_value",
                    "Primary-key values must be stored integers.",
                ),
            )
            reason, detail = (
                "unsupported_schema",
                "Database schema is outside the supported SQLite subset.",
            )
            if message.endswith(" requires one INTEGER or TEXT PRIMARY KEY"):
                reason, detail = (
                    "unsupported_primary_key",
                    "Each table needs one rowid-alias INTEGER or BINARY TEXT PRIMARY KEY.",
                )
            for prefix, code, explanation in restrictions:
                if message.startswith(prefix):
                    reason, detail = code, explanation
                    break
        elif stage == "database_validation" and message == (
            "SQLite 3.37 or newer is required for reliable table metadata"
        ):
            reason, detail = "unsupported_sqlite_version", "SQLite 3.37 or newer is required."
        else:
            reason, detail = (
                "database_operation_failed",
                "The private SQLite acquisition or validation failed.",
            )
    else:
        reason, detail = (
            "file_operation_failed",
            "An input file or private staging operation failed.",
        )
    return DiagnosticError(stage, reason, detail)


def diagnose(config_path: Path, *, allow_exec: bool = False) -> Diagnosis:
    """Validate pristine inputs, optionally confirming the configured target three times."""
    mode: Literal["static", "baseline"] = "baseline" if allow_exec else "static"
    config: Config | None = None
    counter: InvocationCounter | None = None
    counts: dict[str, int] = {}
    results: list[dict[str, object]] = []
    acquired = False
    suitable = False
    assets_validated = False
    schema_supported: bool | None = None
    interrupted = False
    accounting_complete = True
    error: DiagnosticError | None = None
    stage = "configuration"
    try:
        config = load_config(config_path)
        with tempfile.TemporaryDirectory(prefix="reproseed-diagnose-") as temporary:
            working = Path(temporary)
            stage = "assets"
            assets: list[Asset] = []
            for asset in config.assets:
                source = safe_file(config.path.parent, asset.relative)
                destination = working / "assets" / asset.relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                assets.append(Asset(asset.relative, destination))
            assets_validated = True
            staged = replace(config, assets=tuple(assets))
            counter = InvocationCounter(staged)
            pristine = working / "pristine.sqlite3"
            stage = "snapshot"
            snapshot(config.source, pristine)
            acquired = True
            stage = "database_validation"
            model = DatabaseModel.from_database(pristine)
            schema_supported = True
            counts = model.counts()
            suitable = True
            if allow_exec:
                stage = "baseline"
                for _ in range(3):
                    result = counter.invoke(pristine)
                    metadata = result.as_dict()
                    metadata["reason_code"] = _REASON_CODES.get(
                        result.reason, "unrecognized_reason"
                    )
                    results.append(metadata)
                    # An unavailable command or asset blocks execution; failures
                    # returned by an executed application still get all three attempts.
                    if not result.executed:
                        break
    except KeyboardInterrupt as exc:
        interrupted = True
        if isinstance(exc, AbortReduction):
            # A cleanup abort is raised after the counter commits launch
            # evidence. An accounting-recovery abort instead has no cause.
            accounting_complete = (
                isinstance(exc.__cause__, OracleInterrupted) and exc.__cause__.abort
            )
    except (ConfigError, DatabaseError, OSError, sqlite3.Error) as exc:
        error = _input_error(exc, stage)
        if (
            error.reason.startswith("unsupported_")
            and error.reason != "unsupported_sqlite_version"
            and stage == "database_validation"
        ):
            schema_supported = False
    actual = 0 if counter is None else counter.count
    unknown = 0 if counter is None else counter.unknown_launches
    interruptions = [] if counter is None else counter.interrupted_invocations
    represented = sum(result["executed"] is True for result in results + interruptions)
    return Diagnosis(
        mode=mode,
        snapshot_acquired=acquired,
        schema_supported=schema_supported,
        structurally_suitable=suitable,
        assets_validated=assets_validated,
        table_counts=counts,
        config=config,
        baseline_results=tuple(results),
        actual_invocations=actual,
        unknown_interrupted_launches=unknown,
        interrupted_invocations=tuple(interruptions),
        unreported_invocations=max(0, actual - represented),
        accounting_complete=accounting_complete,
        interrupted=interrupted,
        error=error,
    )


def serialize_diagnosis(diagnosis: Diagnosis) -> str:
    """Serialize only curated facts; original paths, argv and marker values stay private."""
    return json.dumps(diagnosis.as_dict(), indent=2, allow_nan=False)


def format_diagnosis(diagnosis: Diagnosis) -> str:
    """Explain current checks and actual outcomes with terminal-safe strings."""
    lines = [
        "ReproSeed diagnosis (diagnostic format 1)",
        f"SQLite snapshot: {'acquired' if diagnosis.snapshot_acquired else 'not acquired'}",
        "Schema: "
        + {True: "supported", False: "unsupported", None: "not established"}[
            diagnosis.schema_supported
        ],
        "Integrity validation: "
        + {True: "passed", False: "failed", None: "not established"}[diagnosis.integrity_valid],
        "Foreign-key validation: "
        + {True: "passed", False: "failed", None: "not established"}[diagnosis.foreign_keys_valid],
        "Explicit assets: "
        + ("validated and privately copied" if diagnosis.assets_validated else "not validated"),
    ]
    if diagnosis.structurally_suitable:
        lines.extend(
            [
                f"User tables: {len(diagnosis.table_counts)}",
                f"Rows: {sum(diagnosis.table_counts.values())}",
                "Tables (user rows):",
            ]
        )
        lines.extend(
            f"  {escape_terminal(json.dumps(table, ensure_ascii=False))}: {count}"
            for table, count in sorted(diagnosis.table_counts.items())
        )
        if not diagnosis.table_counts:
            lines.append("  (no user tables)")
    lines.append(
        "Structurally suitable for reduction: "
        + ("yes" if diagnosis.structurally_suitable else "not established")
    )
    if diagnosis.config is not None:
        spec = diagnosis.config.oracle
        lines.extend(
            [
                f"Oracle contract: exit {spec.expected_exit} and an exact whole UTF-8 marker line "
                f"on {spec.stream}",
                "A matching exit code alone does not establish the target failure.",
                f"Limits: {spec.timeout_seconds:g}s per attempt; "
                f"{spec.output_limit_bytes} combined output bytes; "
                f"{diagnosis.config.max_invocations} configured reduction invocations",
            ]
        )
    lines.append(
        "Oracle: "
        + {True: "executed", False: "not executed", None: "launch uncertain"}[
            diagnosis.oracle_executed
        ]
    )
    for index, result in enumerate(diagnosis.baseline_results, 1):
        lines.append(
            f"Baseline {index}/3: {escape_terminal(str(result['outcome']))} "
            f"({escape_terminal(str(result['reason']))}); exit {result['exit_code']}; "
            f"executed {str(result['executed']).lower()}; {result['output_bytes']} output bytes; "
            f"{result['duration_seconds']}s"
        )
    for result in diagnosis.interrupted_invocations:
        executed = result["executed"]
        launch = (
            "confirmed launch"
            if executed is True
            else "no launch"
            if executed is False
            else "unknown launch"
        )
        lines.append(f"Interrupted attempt: UNRESOLVED (interrupted); {launch}")
    if diagnosis.unreported_invocations:
        lines.append(
            "Confirmed invocations with unavailable result metadata: "
            f"{diagnosis.unreported_invocations}"
        )
    lines.extend(
        [
            f"Actual invocations: {diagnosis.actual_invocations}; unknown interrupted launches: "
            f"{diagnosis.unknown_interrupted_launches}",
            "Baseline reproduction: "
            + (
                "confirmed (3/3 TARGET_FAILURE)"
                if diagnosis.baseline_confirmed
                else "not established"
            ),
        ]
    )
    if diagnosis.interrupted:
        lines.append("Diagnosis interrupted before completion.")
    if not diagnosis.accounting_complete:
        lines.append("A further interruption prevented complete invocation accounting.")
    if diagnosis.error is not None:
        lines.append(
            f"Input error ({escape_terminal(diagnosis.error.stage)}/"
            f"{escape_terminal(diagnosis.error.reason)}): "
            f"{escape_terminal(diagnosis.error.message)}"
        )
    elif diagnosis.mode == "static" and not diagnosis.interrupted:
        lines.append("Next step: use --allow-exec to verify the configured failure.")
    lines.append("Readiness checks do not guarantee a subsequent reduction will succeed.")
    return "\n".join(lines)
