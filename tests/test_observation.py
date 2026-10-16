"""Opt-in telemetry safety, bounded sinks, and real CLI reductions."""

from __future__ import annotations

import io
import json
import math
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from test_config_artifacts import target

from reproseed import observation
from reproseed.artifacts import create_bundle, sha256, validate_bundle
from reproseed.cli import main
from reproseed.config import load_config
from reproseed.observation import (
    NO_OBSERVER,
    Observation,
    ObservationError,
    StreamObserver,
    observation_context,
    sanitize_reason,
)
from reproseed.reducer import AbortReduction


def records(stream: io.BytesIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.mark.parametrize(
    "progress,events", [(False, False), (True, False), (False, True), (True, True)]
)
def test_cli_observation_modes_preserve_stdout_and_inputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], progress: bool, events: bool
) -> None:
    config = target(tmp_path)
    private = "PRIVATE_SYNTHETIC_DATA\x1b[31m\x00secret"
    with closing(sqlite3.connect(tmp_path / "source.sqlite3")) as database:
        database.execute("UPDATE things SET value=?", (private,))
        database.commit()
    inputs = [config, tmp_path / "source.sqlite3", tmp_path / "oracle.py"]
    before = [sha256(path) for path in inputs]
    bundle = tmp_path / "bundle"
    log = tmp_path / "run.jsonl"
    args = ["reduce", "--config", str(config), "--out", str(bundle), "--allow-exec"]
    if progress:
        args.append("--progress")
    if events:
        args.extend(["--events", str(log)])
    assert main(args) == 0
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert set(summary) == {
        "original_counts",
        "final_counts",
        "oracle_invocations",
        "termination_reason",
        "verified",
    }
    assert summary["verified"] is True
    assert bool(output.err) is progress
    assert private not in output.err and "\x1b" not in output.err
    assert [sha256(path) for path in inputs] == before
    assert not (bundle / log.name).exists()
    validate_bundle(bundle)
    if events:
        raw = log.read_text(encoding="utf-8")
        assert "PRIVATE" not in raw and str(tmp_path) not in raw and "oracle.py" not in raw
        data = [json.loads(line) for line in raw.splitlines()]
        assert [item["sequence"] for item in data] == list(range(1, len(data) + 1))
        assert all(item["event_version"] == 1 for item in data)
        assert all(math.isfinite(item["elapsed_seconds"]) for item in data)
        final = next(item for item in reversed(data) if item["event"] == "completed")
        assert final["known_executions"] == summary["oracle_invocations"]
        assert final["retained_rows"] == sum(summary["final_counts"].values())


@pytest.mark.parametrize(
    "flags", [["--progress"], ["--events", "run.jsonl"], ["--progress", "--events", "run.jsonl"]]
)
def test_observation_does_not_authorize_execution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    config = target(tmp_path, "raise AssertionError('must not execute')")
    assert main(["reduce", "--config", str(config), "--out", str(tmp_path / "bundle"), *flags]) == 2
    assert "--allow-exec is required" in capsys.readouterr().err
    assert not (tmp_path / "bundle").exists()


def test_event_path_is_caller_relative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config(target(tmp_path))
    caller = tmp_path / "caller with spaces \u96ea"
    caller.mkdir()
    monkeypatch.chdir(caller)
    with observation_context(
        config, tmp_path / "bundle", events=Path("run.jsonl"), progress=False
    ) as sink:
        sink.emit(Observation("started", "preparation"))
    assert (caller / "run.jsonl").is_file()
    assert not (tmp_path / "run.jsonl").exists()


@pytest.mark.parametrize(
    "kind",
    [
        "existing",
        "directory",
        "missing_parent",
        "config",
        "source",
        "asset",
        "sidecar",
        "bundle",
        "inside_bundle",
        "device",
    ],
)
def test_unsafe_event_paths_fail_before_oracle_execution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    launched = tmp_path / "launched"
    config = target(
        tmp_path,
        f"from pathlib import Path\nPath({str(launched)!r}).touch()\n"
        "print('TARGET'); raise SystemExit(42)",
    )
    bundle = tmp_path / "bundle"
    paths = {
        "existing": tmp_path / "existing.jsonl",
        "directory": tmp_path / "directory",
        "missing_parent": tmp_path / "missing" / "run.jsonl",
        "config": config,
        "source": tmp_path / "source.sqlite3",
        "asset": tmp_path / "oracle.py",
        "sidecar": tmp_path / "source.sqlite3-wal",
        "bundle": bundle,
        "inside_bundle": bundle / "run.jsonl",
        "device": tmp_path / "NUL.jsonl",
    }
    path = paths[kind]
    if kind == "existing":
        path.write_bytes(b"")
    elif kind == "directory":
        path.mkdir()
    inputs = [config, tmp_path / "source.sqlite3", tmp_path / "oracle.py"]
    before = [sha256(item) for item in inputs]
    assert (
        main(
            [
                "reduce",
                "--config",
                str(config),
                "--out",
                str(bundle),
                "--allow-exec",
                "--events",
                str(path),
            ]
        )
        == 2
    )
    assert "Recovery:" in capsys.readouterr().err
    assert not launched.exists() and not bundle.exists()
    assert [sha256(item) for item in inputs] == before
    if kind == "existing":
        assert path.read_bytes() == b""
    assert not (tmp_path / "missing").exists()


def test_initial_event_creation_denial_does_not_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = target(tmp_path)
    path = tmp_path / "run.jsonl"
    original = Path.open

    def denied(self: Path, *args: object, **kwargs: object) -> object:
        if self == path:
            raise PermissionError("synthetic denied event file")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    monkeypatch.setattr(
        "reproseed.cli.create_bundle", lambda *args, **kwargs: pytest.fail("executed")
    )
    assert (
        main(
            [
                "reduce",
                "--config",
                str(config),
                "--out",
                str(tmp_path / "bundle"),
                "--allow-exec",
                "--events",
                str(path),
            ]
        )
        == 2
    )
    assert "check its parent and permissions" in capsys.readouterr().err
    assert not path.exists()


@pytest.mark.parametrize("device", [r"\\.\pipe\reproseed-synthetic", r"\\?\C:\reproseed-synthetic"])
def test_windows_device_namespaces_are_rejected_before_path_probes(
    tmp_path: Path, device: str
) -> None:
    config = load_config(target(tmp_path))
    with pytest.raises(ObservationError, match="device"):
        with observation_context(config, tmp_path / "bundle", events=Path(device), progress=False):
            pytest.fail("device path acquired")


@pytest.mark.parametrize("junction", [False, True])
def test_link_or_junction_ancestor_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, junction: bool
) -> None:
    config = load_config(target(tmp_path))
    parent = tmp_path / "linked"
    parent.mkdir()
    name = "is_junction" if junction else "is_symlink"
    original = getattr(Path, name)
    monkeypatch.setattr(Path, name, lambda self: self == parent or original(self))
    with pytest.raises(ObservationError, match="symlinks or junctions"):
        with observation_context(
            config, tmp_path / "bundle", events=parent / "run.jsonl", progress=False
        ):
            pytest.fail("unsafe context acquired")
    assert not (parent / "run.jsonl").exists()


class FailingBytes(io.BytesIO):
    def __init__(self, failure: str) -> None:
        super().__init__()
        self.failure = failure
        self.writes = 0

    def write(self, data: bytes) -> int:
        self.writes += 1
        if self.failure == "short":
            return super().write(data[:5])
        if self.failure == "disk_full":
            raise OSError(28, "synthetic disk full")
        if self.failure == "interrupt":
            raise KeyboardInterrupt
        if self.failure == "partial_interrupt":
            super().write(data[:5])
            raise KeyboardInterrupt
        if self.failure == "abort":
            raise AbortReduction
        raise RuntimeError("implementation bug")


@pytest.mark.parametrize("failure", ["short", "disk_full"])
def test_file_failure_disables_only_file_and_never_appends_after_partial_write(
    failure: str,
) -> None:
    file = FailingBytes(failure)
    text = io.StringIO()
    observer = StreamObserver(events=file, progress=text, warning=text)
    for _ in range(3):
        observer.emit(Observation("completed", "baseline"))
    assert file.writes == 1
    assert text.getvalue().count("events telemetry disabled") == 1
    assert text.getvalue().count("baseline completed") == 3
    if failure == "short":
        assert len(file.getvalue()) == 5


class BrokenText(io.StringIO):
    def write(self, data: str) -> int:
        raise BrokenPipeError("synthetic broken stderr")


class ShortText(io.StringIO):
    def write(self, data: str) -> int:
        return super().write(data[:2])


def test_broken_progress_preserves_events_and_records_incompleteness_once() -> None:
    file = io.BytesIO()
    text = BrokenText()
    observer = StreamObserver(events=file, progress=text, warning=text)
    observer.emit(Observation("started", "preparation"))
    observer.emit(Observation("completed", "run"))
    data = records(file)
    assert [item["event"] for item in data] == ["started", "sink_disabled", "completed"]
    assert data[1]["reason"] == "stderr_unavailable"


def test_short_progress_write_disables_stderr_and_preserves_events() -> None:
    file, text = io.BytesIO(), ShortText()
    observer = StreamObserver(events=file, progress=text, warning=text)
    observer.emit(Observation("started", "preparation"))
    partial = text.getvalue()
    observer.emit(Observation("completed", "run"))
    assert text.getvalue() == partial
    assert [item["event"] for item in records(file)] == ["started", "sink_disabled", "completed"]


@pytest.mark.parametrize("error", [TypeError, ValueError])
def test_serialization_failure_disables_sink_without_swallowing_arbitrary_errors(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    file, warnings = io.BytesIO(), io.StringIO()

    def failed(*args: object, **kwargs: object) -> str:
        raise error("synthetic serialization failure")

    monkeypatch.setattr(observation.json, "dumps", failed)
    observer = StreamObserver(events=file, warning=warnings)
    observer.emit(Observation("started", "run"))
    observer.emit(Observation("completed", "run"))
    assert file.getvalue() == b""
    assert warnings.getvalue().count("events telemetry disabled") == 1


def test_event_cap_reserves_complete_truncation_record_and_stops_writing() -> None:
    file = io.BytesIO()
    warnings = io.StringIO()
    observer = StreamObserver(events=file, warning=warnings, limit=8192)
    for count in range(200):
        observer.emit(Observation("committed", "search", attempts=count))
    data = records(file)
    assert len(file.getvalue()) <= 8192
    assert data[-1]["event"] == "truncated" and data[-1]["reason"] == "size_limit"
    assert sum(item["event"] == "truncated" for item in data) == 1
    assert warnings.getvalue().count("events telemetry disabled") == 1


@pytest.mark.parametrize(
    "failure,error",
    [("interrupt", KeyboardInterrupt), ("abort", AbortReduction), ("bug", RuntimeError)],
)
def test_observer_does_not_swallow_interruptions_or_implementation_bugs(
    failure: str, error: type[BaseException]
) -> None:
    observer = StreamObserver(events=FailingBytes(failure), warning=io.StringIO())
    with pytest.raises(error):
        observer.emit(Observation("started", "search"))


def test_partial_write_interruption_cannot_append_during_search_salvage() -> None:
    file = FailingBytes("partial_interrupt")
    observer = StreamObserver(events=file, warning=io.StringIO())
    with pytest.raises(KeyboardInterrupt):
        observer.emit(Observation("candidate", "search"))
    observer.emit(Observation("search_stopped", "search", reason="interrupted"))
    assert file.writes == 1
    assert len(file.getvalue()) == 5


@pytest.mark.parametrize("failure", ["disk_full", "short", "stderr"])
def test_sink_failure_preserves_real_workflow_outcomes_and_accounting(
    tmp_path: Path, failure: str
) -> None:
    config = load_config(target(tmp_path))
    before = sha256(config.source)
    original = create_bundle(config, tmp_path / "plain")
    file = io.BytesIO() if failure == "stderr" else FailingBytes(failure)
    text = BrokenText() if failure == "stderr" else io.StringIO()
    observer = StreamObserver(events=file, progress=text, warning=text)
    observed = create_bundle(config, tmp_path / "observed", observer)

    def stable(value: object) -> object:
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key != "duration_seconds"}
        if isinstance(value, (list, tuple)):
            return [stable(item) for item in value]
        return value

    assert stable(original) == stable(observed)
    assert sha256(config.source) == before
    validate_bundle(tmp_path / "plain")
    validate_bundle(tmp_path / "observed")


def test_allowlist_refuses_control_strings_and_nonfinite_counts() -> None:
    file, text = io.BytesIO(), io.StringIO()
    observer = StreamObserver(events=file, progress=text, warning=text)
    observer.emit(
        replace(
            Observation("started", "search"), reason=cast(observation.ReasonCode, "PRIVATE\x1b[31m")
        )
    )
    assert file.getvalue() == b""
    assert "PRIVATE" not in text.getvalue() and "\x1b" not in text.getvalue()
    assert sanitize_reason("PRIVATE\x00arbitrary exception") == "operation_failed"
    assert sanitize_reason("expected exit and exact failure marker") == "target_confirmed"
    for value in (-1, math.nan, math.inf, True):
        with pytest.raises(ValueError):
            observation._record(
                replace(Observation("completed", "run"), retained_rows=cast(int, value)), 1, 0.0
            )


def test_progress_rate_limits_search_but_keeps_transitions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observation.time, "monotonic", lambda: 12.0)
    file, text = io.BytesIO(), io.StringIO()
    observer = StreamObserver(events=file, progress=text)
    for count in range(20):
        observer.emit(Observation("committed", "search", attempts=count))
    observer.emit(Observation("search_stopped", "search", attempts=20))
    assert len(text.getvalue().splitlines()) == 2
    assert len(records(file)) == 21


def test_accepted_commit_bypasses_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observation.time, "monotonic", lambda: 12.0)
    text = io.StringIO()
    observer = StreamObserver(progress=text)
    observer.emit(Observation("candidate", "search", candidate_rows=2))
    observer.emit(Observation("committed", "search", retained_rows=2, accepted_changes=1))
    observer.emit(Observation("committed", "search", retained_rows=1, accepted_changes=2))
    assert len(text.getvalue().splitlines()) == 3


def test_invocation_unknown_launch_is_distinct_and_noop_context_creates_nothing(
    tmp_path: Path,
) -> None:
    file = io.BytesIO()
    observer = StreamObserver(events=file)
    observer.emit(
        Observation(
            "invocation",
            "search",
            executed=None,
            known_executions=1,
            unknown_launches=1,
            charged_invocations=2,
        )
    )
    assert records(file)[0]["executed"] is None
    config = load_config(target(tmp_path))
    with observation_context(config, tmp_path / "bundle", events=None, progress=False) as sink:
        assert sink is NO_OBSERVER
        sink.emit(Observation("started", "run"))
