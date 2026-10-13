"""Search publication boundaries, independent of bytecode/source-line numbering."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Set
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any

import pytest

from reproseed import reducer
from reproseed.config import Config, OracleSpec
from reproseed.oracle import OracleResult, Outcome
from reproseed.report import validate_report
from reproseed.sqlite_adapter import RowId


@dataclass
class Model:
    rows: tuple[RowId, ...] = (("items", 1), ("items", 2))
    component: bool = False

    def deletion_closure(self, seeds: Iterable[RowId], retained: Set[RowId]) -> frozenset[RowId]:
        return frozenset(retained if self.component else seeds)


def evidence(outcome: str) -> dict[str, object]:
    target = outcome == "TARGET_FAILURE"
    return OracleResult(
        Outcome(outcome),
        "expected exit and exact failure marker" if target else "zero exit without target marker",
        42 if target else 0,
        7 if target else 0,
        0.01,
    ).as_dict()


def assert_valid(
    result: reducer.SearchResult,
    executions: list[dict[str, object]],
    tmp_path: Path,
    *,
    original_rows: int = 2,
) -> None:
    current = original_rows
    for acceptance in result.accepted:
        assert acceptance["before"] == current
        current = int(str(acceptance["after"]))
        attempt = result.attempts[int(str(acceptance["attempt"])) - 1]
        assert len(attempt["confirmations"]) == 2  # type: ignore[arg-type]
    assert current == len(result.retained)
    assert result.cache_hits == sum(a["cached"] is True for a in result.attempts)
    report = {
        "version": 1,
        "verified": True,
        "original_counts": {"items": original_rows},
        "final_counts": {"items": len(result.retained)},
        "oracle_invocations": 6 + len(executions),
        "unknown_interrupted_launches": 0,
        "budget_charged_invocations": 6 + len(executions),
        "interrupted_invocations": [],
        "max_invocations": 100,
        "baseline_verification": [evidence("TARGET_FAILURE") for _ in range(3)],
        "final_verification": [evidence("TARGET_FAILURE") for _ in range(3)],
        "attempts": result.attempts,
        "accepted_reductions": result.accepted,
        "cache_hits": result.cache_hits,
        "invalid_candidates": sum(a["outcome"] == "DATABASE_INVALID" for a in result.attempts),
        "unresolved_attempts": sum(a["outcome"] == "UNRESOLVED" for a in result.attempts),
        "termination_reason": result.termination_reason,
        "minimality": "No global minimality claim; synthetic unit evidence.",
    }
    config = Config(
        tmp_path / "case.toml",
        tmp_path / "source.sqlite3",
        (),
        OracleSpec(("unused",), 42, "TARGET", "stdout", 1.0, 4096),
        100,
    )
    validate_report(report, config)


@pytest.mark.parametrize("boundary", ["attempt_tail", "acceptance_tail", "prepared", "published"])
def test_acceptance_publishes_rows_and_evidence_together(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, boundary: str
) -> None:
    executions: list[dict[str, object]] = []
    injected = False
    original = reducer._commit_progress

    def evaluate(candidate: frozenset[RowId]) -> reducer.Evaluation:
        outcome = "TARGET_FAILURE" if candidate else "PASS"
        confirmations = tuple(evidence(outcome) for _ in range(2 if candidate else 1))
        executions.extend(confirmations)
        return reducer.Evaluation(
            outcome,
            confirmations,
            "two_fresh_confirmations" if candidate else "zero exit without target marker",
        )

    def prepare(*args: Any, **kwargs: Any) -> reducer._Checkpoint:
        nonlocal injected
        checkpoint = original(*args, **kwargs)
        if boundary == "prepared" and checkpoint.accepted_count:
            injected = True
            raise KeyboardInterrupt
        return checkpoint

    def trace(frame: FrameType, event: str, argument: object) -> Any:
        nonlocal injected
        if event != "line" or injected:
            return trace
        values = frame.f_locals
        if frame.f_code is original.__code__:
            checkpoint = values["checkpoint"]
            pending_attempt = len(values["attempts"]) > checkpoint.attempt_count
            pending_acceptance = len(values["accepted"]) > checkpoint.accepted_count
            trigger = values["result"].outcome == "TARGET_FAILURE" and (
                (boundary == "attempt_tail" and pending_attempt and not pending_acceptance)
                or (boundary == "acceptance_tail" and pending_acceptance)
            )
        elif frame.f_code is reducer.reduce_rows.__code__:
            checkpoint = values.get("checkpoint")
            trigger = (
                boundary == "published"
                and checkpoint is not None
                and checkpoint.accepted_count == 1
            )
        else:
            trigger = False
        if trigger:
            injected = True
            sys.settrace(None)
            raise KeyboardInterrupt
        return trace

    monkeypatch.setattr(reducer, "_commit_progress", prepare)
    previous_trace = sys.gettrace()
    try:
        sys.settrace(trace)
        result = reducer.reduce_rows(Model(), evaluate)
    finally:
        sys.settrace(previous_trace)
    assert injected
    assert result.termination_reason == "interrupted_best_confirmed_candidate_preserved"
    assert len(result.retained) == (1 if boundary == "published" else 2)
    assert len(result.accepted) == (1 if boundary == "published" else 0)
    assert_valid(result, executions, tmp_path)


@pytest.mark.parametrize("boundary", ["before_prepare", "prepared", "published"])
def test_cached_attempt_counts_only_after_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, boundary: str
) -> None:
    executions: list[dict[str, object]] = []
    injected = False
    original = reducer._commit_progress

    def evaluate(candidate: frozenset[RowId]) -> reducer.Evaluation:
        assert not candidate
        confirmation = evidence("PASS")
        executions.append(confirmation)
        return reducer.Evaluation("PASS", (confirmation,), "zero exit without target marker")

    def prepare(*args: Any, **kwargs: Any) -> reducer._Checkpoint:
        nonlocal injected
        cached = args[6]
        if cached and boundary == "before_prepare":
            injected = True
            raise KeyboardInterrupt
        checkpoint = original(*args, **kwargs)
        if cached and boundary == "prepared":
            injected = True
            raise KeyboardInterrupt
        return checkpoint

    def trace(frame: FrameType, event: str, argument: object) -> Any:
        nonlocal injected
        if event == "line" and frame.f_code is reducer.reduce_rows.__code__:
            checkpoint = frame.f_locals.get("checkpoint")
            if boundary == "published" and checkpoint is not None and checkpoint.attempt_count == 2:
                injected = True
                sys.settrace(None)
                raise KeyboardInterrupt
        return trace

    monkeypatch.setattr(reducer, "_commit_progress", prepare)
    previous_trace = sys.gettrace()
    try:
        sys.settrace(trace)
        result = reducer.reduce_rows(Model(component=True), evaluate)
    finally:
        sys.settrace(previous_trace)
    assert injected
    assert len(executions) == 1
    assert result.cache_hits == (1 if boundary == "published" else 0)
    assert len(result.attempts) == (2 if boundary == "published" else 1)
    assert not result.accepted
    assert result.termination_reason == "interrupted_best_confirmed_candidate_preserved"
    assert_valid(result, executions, tmp_path)


@pytest.mark.parametrize("outcome", ["PASS", "DATABASE_INVALID", "UNRESOLVED", "TARGET_FAILURE"])
def test_completed_evaluation_before_attempt_does_not_change_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: str
) -> None:
    executions: list[dict[str, object]] = []
    injected = False

    def evaluate(candidate: frozenset[RowId]) -> reducer.Evaluation:
        if outcome == "DATABASE_INVALID":
            return reducer.Evaluation(outcome, reason="invalid synthetic candidate")
        confirmations = tuple(
            evidence("TARGET_FAILURE" if outcome == "TARGET_FAILURE" else "PASS")
            for _ in range(2 if outcome == "TARGET_FAILURE" else 1)
        )
        executions.extend(confirmations)
        if outcome == "UNRESOLVED":
            confirmations[0].update(
                outcome="UNRESOLVED", reason="unexpected exit code", exit_code=43
            )
        return reducer.Evaluation(
            outcome,
            confirmations,
            "unexpected exit code"
            if outcome == "UNRESOLVED"
            else "two_fresh_confirmations"
            if outcome == "TARGET_FAILURE"
            else "zero exit without target marker",
        )

    def prepare(*args: Any, **kwargs: Any) -> reducer._Checkpoint:
        nonlocal injected
        assert args[5].outcome == outcome
        injected = True
        raise KeyboardInterrupt

    monkeypatch.setattr(reducer, "_commit_progress", prepare)
    result = reducer.reduce_rows(Model(), evaluate)
    assert injected
    assert result.retained == frozenset(Model().rows)
    assert not result.attempts
    assert not result.accepted
    assert result.termination_reason == "interrupted_best_confirmed_candidate_preserved"
    assert_valid(result, executions, tmp_path)
