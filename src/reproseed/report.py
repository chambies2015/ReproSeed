"""Validate the evidence recorded by the existing version-one report writer.

Version one records confirmations, not a complete execution ledger. Cached
records repeat historical confirmations. An interrupted evaluation can lose its
first completed confirmation, or both if interrupted before the reducer records
the returned evaluation. These gaps are bounded below; they are not filled with
invented records. Consistent metadata does not prove a historical execution.
Unknown fields are rejected at every record level; extensions need a new version.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from reproseed.config import Config


class ReportError(ValueError):
    """Recorded bundle evidence is malformed or internally contradictory."""


_REPORT_FIELDS = {
    "version",
    "verified",
    "original_counts",
    "final_counts",
    "oracle_invocations",
    "unknown_interrupted_launches",
    "budget_charged_invocations",
    "interrupted_invocations",
    "max_invocations",
    "baseline_verification",
    "final_verification",
    "attempts",
    "accepted_reductions",
    "cache_hits",
    "unresolved_attempts",
    "invalid_candidates",
    "termination_reason",
    "minimality",
}
_RESULT_FIELDS = {"outcome", "reason", "exit_code", "output_bytes", "duration_seconds", "executed"}
_ATTEMPT_FIELDS = {
    "number",
    "retained_rows",
    "removed_rows",
    "outcome",
    "reason",
    "cached",
    "confirmations",
}
_TERMINATIONS = {
    "single_row_closures_exhausted",
    "empty_candidate_confirmed",
    "oracle_budget_exhausted_reserved_final_verification",
    "interrupted_best_confirmed_candidate_preserved",
}
_TARGET_REASON = "expected exit and exact failure marker"
_PASS_REASON = "zero exit without target marker"
_UNRESOLVED_REASONS = {
    "launch_error",
    "staging_error",
    "combined output limit exceeded",
    "output read failed",
    "deadline exceeded (process or open output pipes)",
    "process terminated by signal",
    "target marker contradicts zero exit",
    "unexpected exit code",
    "expected failure exit without exact marker",
}


def _fields(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ReportError(f"report {label} has missing or unknown fields")
    return cast(dict[str, object], value)


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ReportError(f"report {label} must be an integer at least {minimum}")
    return value


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ReportError(f"report {label} must be a boolean")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReportError(f"report {label} must be a nonempty string")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ReportError(f"report {label} must be an array")
    return cast(list[object], value)


def _counts(value: object, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ReportError(f"report {label} must map table names to counts")
    if any(not isinstance(name, str) for name in value):
        raise ReportError(f"report {label} table names must be strings")
    # SQLite permits a quoted empty table name; the existing adapter preserves it.
    return {name: _integer(count, f"{label} count") for name, count in value.items()}


@dataclass(frozen=True)
class _Confirmation:
    outcome: str
    reason: str
    exit_code: int | None
    output_bytes: int
    duration_seconds: float
    executed: bool


def _confirmation(value: object, config: Config, label: str) -> _Confirmation:
    record = _fields(value, _RESULT_FIELDS, label)
    outcome = _string(record["outcome"], f"{label} outcome")
    reason = _string(record["reason"], f"{label} reason")
    executed = _boolean(record["executed"], f"{label} executed")
    exit_value = record["exit_code"]
    if exit_value is not None and type(exit_value) is not int:
        raise ReportError(f"report {label} exit_code must be an integer or null")
    exit_code = exit_value
    output = _integer(record["output_bytes"], f"{label} output_bytes")
    duration = record["duration_seconds"]
    try:
        finite_duration = type(duration) in (int, float) and math.isfinite(cast(float, duration))
    except OverflowError:
        finite_duration = False
    if not finite_duration or cast(float, duration) < 0:
        raise ReportError(f"report {label} duration_seconds must be finite and nonnegative")
    if outcome == "TARGET_FAILURE":
        valid = (
            executed
            and exit_code == config.oracle.expected_exit
            and reason == _TARGET_REASON
            and output >= len(config.oracle.marker.encode("utf-8"))
        )
    elif outcome == "PASS":
        valid = executed and exit_code == 0 and reason == _PASS_REASON
    elif outcome == "UNRESOLVED":
        valid = reason in _UNRESOLVED_REASONS
        if reason in {"launch_error", "staging_error"}:
            valid = valid and not executed and exit_code is None and output == 0
        else:
            valid = valid and executed
        if reason == "process terminated by signal":
            valid = valid and exit_code is not None and exit_code < 0
        elif reason == "target marker contradicts zero exit":
            valid = valid and exit_code == 0
        elif reason == "unexpected exit code":
            valid = (
                valid
                and exit_code not in (0, config.oracle.expected_exit)
                and (exit_code is None or exit_code > 0)
            )
        elif reason == "expected failure exit without exact marker":
            valid = valid and exit_code == config.oracle.expected_exit
        elif reason == "combined output limit exceeded":
            valid = valid and output > config.oracle.output_limit_bytes
    else:
        valid = False
    if not valid:
        raise ReportError(f"report {label} has inconsistent oracle outcome evidence")
    if outcome != "UNRESOLVED" and output > config.oracle.output_limit_bytes:
        raise ReportError(f"report {label} successful output exceeds the oracle limit")
    return _Confirmation(outcome, reason, exit_code, output, float(cast(float, duration)), executed)


def _mandatory(value: object, config: Config, label: str) -> None:
    records = _list(value, label)
    if len(records) != 3:
        raise ReportError(f"report {label} requires exactly three confirmations")
    for item in records:
        result = _confirmation(item, config, label)
        if result.outcome != "TARGET_FAILURE" or not result.executed:
            raise ReportError(
                f"report {label} requires three executed TARGET_FAILURE confirmations"
            )


@dataclass(frozen=True)
class _Attempt:
    retained: int
    removed: int
    outcome: str
    reason: str
    cached: bool
    confirmations: tuple[_Confirmation, ...]


def _attempt(value: object, number: int, config: Config) -> _Attempt:
    label = f"attempt {number}"
    record = _fields(value, _ATTEMPT_FIELDS, label)
    if _integer(record["number"], f"{label} number", 1) != number:
        raise ReportError("report attempt numbers must be consecutive starting at one")
    retained = _integer(record["retained_rows"], f"{label} retained_rows")
    removed = _integer(record["removed_rows"], f"{label} removed_rows", 1)
    outcome = _string(record["outcome"], f"{label} outcome")
    reason = _string(record["reason"], f"{label} reason")
    cached = _boolean(record["cached"], f"{label} cached")
    confirmations = tuple(
        _confirmation(item, config, label)
        for item in _list(record["confirmations"], f"{label} confirmations")
    )
    outcomes = tuple(result.outcome for result in confirmations)
    if outcome == "TARGET_FAILURE":
        valid = (
            outcomes == ("TARGET_FAILURE", "TARGET_FAILURE") and reason == "two_fresh_confirmations"
        )
    elif outcome == "PASS":
        valid = outcomes == ("PASS",) and reason == confirmations[0].reason
    elif outcome == "DATABASE_INVALID":
        valid = not confirmations and len(reason) <= 500
    elif outcome == "UNRESOLVED":
        valid = not cached and (
            (not confirmations and reason == "interrupted_during_evaluation")
            or (outcomes == ("UNRESOLVED",) and reason == confirmations[0].reason)
            or (
                len(outcomes) == 2
                and outcomes[0] == "TARGET_FAILURE"
                and outcomes[1] in {"PASS", "UNRESOLVED"}
                and reason == "conflicting_confirmations"
            )
        )
    else:
        valid = False
    if not valid:
        raise ReportError(f"report {label} has inconsistent confirmation evidence")
    return _Attempt(retained, removed, outcome, reason, cached, confirmations)


def validate_report(value: object, config: Config) -> None:
    """Check v1 structure, count chains, recorded evidence and bounded accounting.

    The configuration supplies the expected exit, output limit and execution
    budget. Fixture structure and actual table counts are checked separately by
    bundle acquisition. This function never executes the oracle.
    """
    report = _fields(value, _REPORT_FIELDS, "root")
    if _integer(report["version"], "version", 1) != 1:
        raise ReportError("unsupported report version")
    if not _boolean(report["verified"], "verified"):
        raise ReportError("bundle report does not declare a verified fixture")
    original = _counts(report["original_counts"], "original_counts")
    final = _counts(report["final_counts"], "final_counts")
    if original.keys() != final.keys() or any(
        final[name] > count for name, count in original.items()
    ):
        raise ReportError("report final counts must use the original tables and cannot increase")
    _string(report["minimality"], "minimality")
    termination = _string(report["termination_reason"], "termination_reason")
    if termination not in _TERMINATIONS:
        raise ReportError("report has unsupported termination_reason")
    interrupted = termination == "interrupted_best_confirmed_candidate_preserved"
    _mandatory(report["baseline_verification"], config, "baseline_verification")
    _mandatory(report["final_verification"], config, "final_verification")
    attempts = tuple(
        _attempt(item, index, config)
        for index, item in enumerate(_list(report["attempts"], "attempts"), 1)
    )
    accepted: dict[int, tuple[int, int]] = {}
    last_reference = 0
    for item in _list(report["accepted_reductions"], "accepted_reductions"):
        record = _fields(item, {"attempt", "before", "after"}, "accepted reduction")
        reference = _integer(record["attempt"], "accepted attempt", 1)
        before = _integer(record["before"], "accepted before", 1)
        after = _integer(record["after"], "accepted after")
        if not last_reference < reference <= len(attempts) or after >= before:
            raise ReportError(
                "report accepted reductions require valid ordered references and decreasing counts"
            )
        accepted[reference] = before, after
        last_reference = reference
    current = sum(original.values())
    known_executions = 6
    cache_evidence: set[tuple[int, str, str, tuple[_Confirmation, ...]]] = set()
    for number, attempt in enumerate(attempts, 1):
        if attempt.retained + attempt.removed != current:
            raise ReportError("report attempt counts do not match the accepted reduction chain")
        evidence = attempt.retained, attempt.outcome, attempt.reason, attempt.confirmations
        if attempt.cached:
            if evidence not in cache_evidence:
                raise ReportError("report cache hit has no matching prior uncached evidence")
        else:
            known_executions += sum(result.executed for result in attempt.confirmations)
            if attempt.outcome != "UNRESOLVED":
                cache_evidence.add(evidence)
        if attempt.reason == "interrupted_during_evaluation":
            if not interrupted or number != len(attempts):
                raise ReportError("report interrupted evaluation must end an interrupted search")
        if number in accepted:
            if attempt.outcome != "TARGET_FAILURE" or accepted[number] != (
                current,
                attempt.retained,
            ):
                raise ReportError("report accepted reduction disagrees with its confirmed attempt")
            current = attempt.retained
        elif attempt.outcome == "TARGET_FAILURE" and not (interrupted and number == len(attempts)):
            raise ReportError("report confirmed reduction is missing its accepted reference")
    if current != sum(final.values()):
        raise ReportError("report accepted reduction chain does not reach the final total")
    if termination == "empty_candidate_confirmed" and current != 0:
        raise ReportError("report empty termination requires an empty final fixture")
    if termination == "single_row_closures_exhausted" and current == 0:
        raise ReportError("report empty fixture requires its empty termination reason")
    for field, actual in (
        ("cache_hits", sum(attempt.cached for attempt in attempts)),
        ("unresolved_attempts", sum(attempt.outcome == "UNRESOLVED" for attempt in attempts)),
        ("invalid_candidates", sum(attempt.outcome == "DATABASE_INVALID" for attempt in attempts)),
    ):
        if _integer(report[field], field) != actual:
            raise ReportError(f"report {field} disagrees with recorded attempts")
    interruption_records = _list(report["interrupted_invocations"], "interrupted_invocations")
    if interruption_records and (not interrupted or len(interruption_records) > 1):
        raise ReportError("report interrupted invocations require an interrupted search")
    unknown_launches = 0
    for item in interruption_records:
        record = _fields(item, {"outcome", "reason", "executed"}, "interrupted invocation")
        executed = record["executed"]
        if (
            record["outcome"] != "UNRESOLVED"
            or record["reason"] != "interrupted"
            or (executed is not None and type(executed) is not bool)
        ):
            raise ReportError("report has invalid interrupted-invocation evidence")
        known_executions += executed is True
        unknown_launches += executed is None
    invocations = _integer(report["oracle_invocations"], "oracle_invocations")
    unknown = _integer(report["unknown_interrupted_launches"], "unknown_interrupted_launches")
    charged = _integer(report["budget_charged_invocations"], "budget_charged_invocations")
    limit = _integer(report["max_invocations"], "max_invocations", 6)
    if unknown != unknown_launches or charged != invocations + unknown or charged > limit:
        raise ReportError("report known executions, unknown launches and charged budget disagree")
    if limit != config.max_invocations:
        raise ReportError("report max_invocations disagrees with replay configuration")
    # A callback interruption loses at most its first completed confirmation.
    # Outside that callback, a returned evaluation may be lost before recording.
    allowance = (1 if interruption_records else 2) if interrupted else 0
    if not known_executions <= invocations <= known_executions + allowance:
        raise ReportError("report execution total contradicts available confirmation evidence")
    if (
        termination == "oracle_budget_exhausted_reserved_final_verification"
        and charged + 2 <= limit
    ):
        raise ReportError("report budget exhaustion contradicts its reserved verification capacity")
