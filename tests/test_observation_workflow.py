"""Observation sees committed facts and preserves real cancellation/verification contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_cancellation_workflow import _case as cancellation_case
from test_cancellation_workflow import _files, _verified_lifecycle

from reproseed import reducer, workflow
from reproseed.artifacts import create_bundle, validate_bundle
from reproseed.cli import main
from reproseed.config import Config, load_config
from reproseed.observation import Observation
from reproseed.oracle import OracleInterrupted
from reproseed.sqlite_adapter import RowId


def _case(root: Path, **kwargs: Any) -> Config:
    config = cancellation_case(root, **kwargs)
    # These tests reach lifecycle boundaries, rather than calibrating deadlines.
    # Keep a finite bound with headroom for Windows process startup and pipe EOF.
    text = config.path.read_text(encoding="utf-8")
    assert "timeout_seconds=2.0" in text
    config.path.write_text(
        text.replace("timeout_seconds=2.0", "timeout_seconds=5.0"), encoding="utf-8"
    )
    return load_config(config.path)


class Collector:
    def __init__(self) -> None:
        self.events: list[Observation] = []

    def emit(self, observation: Observation) -> None:
        self.events.append(observation)


@pytest.mark.parametrize("flags", [[], ["--progress"], ["--events"], ["--progress", "--events"]])
def test_cli_observation_modes_keep_json_and_source_bytes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    config = _case(tmp_path / "source")
    before = _files(config.path.parent)
    bundle = tmp_path / "bundle"
    events = tmp_path / "events.jsonl"
    arguments = ["reduce", "--config", str(config.path), "--out", str(bundle), "--allow-exec"]
    for flag in flags:
        arguments.append(flag)
        if flag == "--events":
            arguments.append(str(events))
    assert main(arguments) == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert set(summary) == {
        "original_counts",
        "final_counts",
        "oracle_invocations",
        "termination_reason",
        "verified",
    }
    assert bool(captured.err) == ("--progress" in flags)
    assert _files(config.path.parent) == before
    _, report = validate_bundle(bundle)
    if "--events" in flags:
        records = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
        assert records[-1]["event"] == "completed"
        assert records[-1]["phase"] == "run"
        assert records[-1]["known_executions"] == report["oracle_invocations"]
        stopped = next(record for record in records if record["event"] == "search_stopped")
        assert stopped["retained_rows"] == sum(report["final_counts"].values())
        assert stopped["attempts"] == len(report["attempts"])
        assert stopped["accepted_changes"] == len(report["accepted_reductions"])
        assert stopped["cache_hits"] == report["cache_hits"]
        assert stopped["charged_invocations"] + 3 == report["budget_charged_invocations"]
        assert all(record["event_version"] == 1 for record in records)
        assert [record["sequence"] for record in records] == list(range(1, len(records) + 1))
        serialized = events.read_text(encoding="utf-8")
        for secret in (str(config.path), "synthetic-1", 'TARGET"', "oracle.py", "items"):
            assert secret not in serialized
        assert not (bundle / events.name).exists()


def test_published_committed_counters_match_every_report_prefix(tmp_path: Path) -> None:
    config = _case(tmp_path / "source", rows=4)
    collector = Collector()
    report = create_bundle(config, tmp_path / "bundle", collector)
    committed = [event for event in collector.events if event.event == "committed"]
    assert len(committed) == len(report["attempts"])
    retained = sum(report["original_counts"].values())
    accepted = hits = 0
    for number, (event, attempt) in enumerate(zip(committed, report["attempts"], strict=True), 1):
        if attempt["outcome"] == "TARGET_FAILURE":
            retained = attempt["retained_rows"]
            accepted += 1
        hits += int(attempt["cached"])
        assert (event.attempts, event.retained_rows, event.accepted_changes, event.cache_hits) == (
            number,
            retained,
            accepted,
            hits,
        )
    invocations = [event for event in collector.events if event.event == "invocation"]
    assert len(invocations) == report["oracle_invocations"]
    assert all(event.executed is True for event in invocations)
    assert [event.known_executions for event in invocations] == list(range(1, len(invocations) + 1))
    assert collector.events[-1].event == "completed"
    assert next(i for i, e in enumerate(collector.events) if e.event == "published") > max(
        i for i, e in enumerate(collector.events) if e.phase == "final_verification"
    )


@pytest.mark.parametrize("boundary", ["candidate", "committed"])
def test_observer_search_interrupt_preserves_strict_replayable_selection(
    tmp_path: Path, boundary: str
) -> None:
    config = _case(tmp_path / "source", rows=2)
    source = _files(config.path.parent)

    class Interrupted(Collector):
        interrupted = False

        def emit(self, observation: Observation) -> None:
            super().emit(observation)
            if observation.event == boundary and not self.interrupted:
                self.interrupted = True
                raise KeyboardInterrupt

    observer = Interrupted()
    bundle = tmp_path / "bundle"
    report = create_bundle(config, bundle, observer)
    assert observer.interrupted
    assert report["termination_reason"] == "interrupted_best_confirmed_candidate_preserved"
    _verified_lifecycle(config, bundle, report, source, invocations=report["oracle_invocations"])


@pytest.mark.parametrize("boundary", ["encoding", "completed_evaluation", "acceptance_prepared"])
def test_new_search_boundaries_with_observation_keep_confirmed_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    config = _case(tmp_path / "source", rows=2)
    source = _files(config.path.parent)
    observer = Collector()
    interrupted = False
    if boundary == "encoding":
        original_encode = reducer._CandidateEncoding.encode

        def encoding(self: Any, candidate: Any) -> Any:
            nonlocal interrupted
            encoded = original_encode(self, candidate)
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return encoded

        monkeypatch.setattr(reducer._CandidateEncoding, "encode", encoding)
    else:
        original_commit = reducer._commit_progress

        def commit(*args: Any, **kwargs: Any) -> Any:
            nonlocal interrupted
            result = args[5]
            if boundary == "completed_evaluation" and not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            pending = original_commit(*args, **kwargs)
            if boundary == "acceptance_prepared" and result.outcome == "TARGET_FAILURE":
                interrupted = True
                raise KeyboardInterrupt
            return pending

        monkeypatch.setattr(reducer, "_commit_progress", commit)
    bundle = tmp_path / "bundle"
    report = create_bundle(config, bundle, observer)
    assert interrupted
    assert not report["accepted_reductions"]
    assert report["final_counts"] == {"items": 2}
    _verified_lifecycle(config, bundle, report, source, invocations=report["oracle_invocations"])


def test_interrupted_private_lazy_map_publishes_a_strict_replayable_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _case(tmp_path / "source", rows=80)
    source = _files(config.path.parent)
    original = reducer._CandidateEncoding._packed_ordinals
    captured: list[reducer._CandidateEncoding] = []
    interrupted = False

    def initialize(self: reducer._CandidateEncoding) -> dict[RowId, int]:
        captured.append(self)
        assert self.ordinals is None
        previous = sys.gettrace()

        def trace(frame: Any, event: str, argument: object) -> Any:
            nonlocal interrupted
            if (
                event == "line"
                and frame.f_code is original.__code__
                and frame.f_locals.get("ordinal") == 9
                and not interrupted
            ):
                interrupted = True
                raise KeyboardInterrupt
            return trace

        try:
            sys.settrace(trace)
            return original(self)
        finally:
            sys.settrace(previous)

    monkeypatch.setattr(reducer._CandidateEncoding, "_packed_ordinals", initialize)
    bundle = tmp_path / "bundle"
    report = create_bundle(config, bundle, Collector())
    assert interrupted and len(captured) == 1 and captured[0].ordinals is None
    assert report["final_counts"] == {"items": 80}
    assert report["termination_reason"] == "interrupted_best_confirmed_candidate_preserved"
    assert not report["accepted_reductions"] and len(report["attempts"]) == 1
    assert report["attempts"][0]["outcome"] == "PASS"
    assert report["oracle_invocations"] == 7 and report["cache_hits"] == 0
    _verified_lifecycle(config, bundle, report, source, invocations=7)


@pytest.mark.parametrize("phase", ["baseline", "compaction", "final_verification", "publication"])
def test_observer_interrupt_before_verification_or_publication_aborts(
    tmp_path: Path, phase: str
) -> None:
    config = _case(tmp_path / "source")
    before = _files(config.path.parent)
    bundle = tmp_path / "bundle"

    class Interrupt(Collector):
        def emit(self, observation: Observation) -> None:
            super().emit(observation)
            if observation.phase == phase and observation.event == "started":
                raise KeyboardInterrupt

    observer = Interrupt()
    with pytest.raises(KeyboardInterrupt):
        create_bundle(config, bundle, observer)
    assert not bundle.exists()
    assert _files(config.path.parent) == before
    assert observer.events[-1].event == "aborted"
    assert not any(event.event == "published" for event in observer.events)


def test_unknown_interrupted_launch_is_distinct_from_completed_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _case(tmp_path / "source")
    original = workflow.run_oracle
    calls = 0

    def interrupt(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OracleInterrupted(None)
        return original(*args, **kwargs)

    monkeypatch.setattr(workflow, "run_oracle", interrupt)
    observer = Collector()
    bundle = tmp_path / "bundle"
    report = create_bundle(config, bundle, observer)
    validate_bundle(bundle)
    uncertain = [e for e in observer.events if e.event == "invocation" and e.executed is None]
    assert len(uncertain) == 1
    assert uncertain[0].reason == "interrupted"
    assert uncertain[0].known_executions == 3
    assert uncertain[0].charged_invocations == 4
    assert report["unknown_interrupted_launches"] == 1
    assert report["oracle_invocations"] == 6
    assert observer.events[-1].charged_invocations == 7


@pytest.mark.parametrize("event", ["published", "completed"])
def test_late_notification_interrupt_leaves_only_fully_valid_bundle(
    tmp_path: Path, event: str
) -> None:
    config = _case(tmp_path / "source")
    before = _files(config.path.parent)
    bundle = tmp_path / "bundle"

    class Interrupt(Collector):
        def emit(self, observation: Observation) -> None:
            super().emit(observation)
            if observation.event == event and observation.phase in {"publication", "run"}:
                raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        create_bundle(config, bundle, Interrupt())
    _, report = validate_bundle(bundle)
    assert report["verified"] is True
    assert len(report["final_verification"]) == 3
    assert _files(config.path.parent) == before


def test_second_interrupt_during_accounted_unknown_notification_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _case(tmp_path / "source")
    original = workflow.run_oracle
    calls = 0

    def interrupt(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OracleInterrupted(None)
        return original(*args, **kwargs)

    class Interrupt(Collector):
        def emit(self, observation: Observation) -> None:
            super().emit(observation)
            if observation.event == "invocation" and observation.reason == "interrupted":
                raise KeyboardInterrupt

    monkeypatch.setattr(workflow, "run_oracle", interrupt)
    observer = Interrupt()
    bundle = tmp_path / "bundle"
    with pytest.raises(reducer.AbortReduction):
        create_bundle(config, bundle, observer)
    assert not bundle.exists()
    assert calls == 4
    assert not any(event.event == "published" for event in observer.events)
