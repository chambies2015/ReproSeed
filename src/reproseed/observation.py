"""Opt-in aggregate telemetry; never an execution ledger or replay evidence."""

from __future__ import annotations

import json
import math
import os
import re
import stat
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import KW_ONLY, dataclass, fields
from pathlib import Path
from typing import BinaryIO, Literal, Protocol, TextIO, cast, get_args

from reproseed.config import Config

EventType = Literal[
    "started",
    "completed",
    "model_ready",
    "confirmation",
    "candidate",
    "committed",
    "search_stopped",
    "invocation",
    "aborted",
    "failed",
    "published",
    "sink_disabled",
    "truncated",
]
Phase = Literal[
    "run",
    "preparation",
    "acquisition",
    "model",
    "baseline",
    "search",
    "compaction",
    "final_verification",
    "publication",
    "observation",
]
ReasonCode = Literal[
    "single_row_closures_exhausted",
    "empty_candidate_confirmed",
    "oracle_budget_exhausted_reserved_final_verification",
    "interrupted_best_confirmed_candidate_preserved",
    "preparation_failed",
    "baseline_failed",
    "final_verification_failed",
    "publication_failed",
    "interrupted",
    "operation_failed",
    "target_confirmed",
    "zero_exit",
    "signal",
    "contradictory_marker",
    "unexpected_exit",
    "missing_marker",
    "output_limit",
    "output_read_failed",
    "timeout",
    "launch_failed",
    "conflicting_confirmations",
    "two_fresh_confirmations",
    "database_invalid",
    "events_unavailable",
    "stderr_unavailable",
    "size_limit",
    "serialization_failed",
]
ObservationOutcome = Literal["TARGET_FAILURE", "PASS", "UNRESOLVED", "DATABASE_INVALID"]

EVENT_LIMIT = 16 * 1024 * 1024
RECORD_LIMIT = 4096
TRUNCATION_RESERVE = RECORD_LIMIT
PROGRESS_INTERVAL = 0.5

_EVENTS = frozenset(get_args(EventType))
_PHASES = frozenset(get_args(Phase))
_REASONS = frozenset(get_args(ReasonCode))
_OUTCOMES = frozenset(get_args(ObservationOutcome))
_ORACLE_REASONS: dict[str, ReasonCode] = {
    "expected exit and exact failure marker": "target_confirmed",
    "zero exit without target marker": "zero_exit",
    "process terminated by signal": "signal",
    "target marker contradicts zero exit": "contradictory_marker",
    "unexpected exit code": "unexpected_exit",
    "expected failure exit without exact marker": "missing_marker",
    "combined output limit exceeded": "output_limit",
    "output read failed": "output_read_failed",
    "deadline exceeded (process or open output pipes)": "timeout",
}


def sanitize_reason(reason: str) -> ReasonCode:
    """Map fixed internal reasons; never copy exception or oracle text into telemetry."""
    if reason in _REASONS:
        return cast(ReasonCode, reason)
    return _ORACLE_REASONS.get(reason, "operation_failed")


@dataclass(frozen=True)
class Observation:
    event: EventType
    phase: Phase
    _: KW_ONLY
    original_rows: int | None = None
    candidate_rows: int | None = None
    retained_rows: int | None = None
    attempts: int | None = None
    accepted_changes: int | None = None
    cache_hits: int | None = None
    known_executions: int | None = None
    unknown_launches: int | None = None
    charged_invocations: int | None = None
    max_invocations: int | None = None
    confirmation: int | None = None
    required_confirmations: int | None = None
    outcome: ObservationOutcome | None = None
    reason: ReasonCode | None = None
    executed: bool | None = None


class Observer(Protocol):
    def emit(self, observation: Observation) -> None: ...


class _NoObserver:
    def emit(self, observation: Observation) -> None:
        pass


NO_OBSERVER: Observer = _NoObserver()


class ObservationError(ValueError):
    """The requested event file could not be safely acquired before execution."""


def _checked_event_path(config: Config, output: Path, path: Path) -> Path:
    if str(path).replace("/", "\\").startswith(("\\\\.\\", "\\\\?\\")) or (
        path.drive and not path.is_absolute()
    ):
        raise ObservationError("event file path must not use a device or drive-relative path")
    lexical = path if path.is_absolute() else Path.cwd() / path
    # Check every lexical ancestor before resolving, including paths through '..'.
    current = Path(lexical.anchor)
    for component in lexical.parts[1:]:
        if component not in {".", ".."} and (
            any(ord(char) < 32 or char in '<>:"|?*' for char in component)
            or component.endswith((".", " "))
            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", component)
        ):
            raise ObservationError("event file path must use regular portable file names")
        current /= component
        if current.is_symlink() or current.is_junction():
            raise ObservationError("event file path must not traverse symlinks or junctions")
    path = lexical.resolve()
    output = output.resolve()
    if path == output or path.is_relative_to(output) or output.is_relative_to(path):
        raise ObservationError("event file must be separate from the output bundle")
    protected = (
        config.path,
        config.source,
        *(asset.path for asset in config.assets),
        *(
            config.source.with_name(config.source.name + suffix)
            for suffix in ("-wal", "-shm", "-journal")
        ),
    )
    if any(path == item.resolve() or path.is_relative_to(item.resolve()) for item in protected):
        raise ObservationError("event file conflicts with an input or SQLite sidecar path")
    if path.exists() or path.is_symlink() or path.is_junction():
        raise ObservationError("event file already exists; choose a new file")
    if not path.parent.is_dir():
        raise ObservationError("event file parent must already be a writable directory")
    return path


def _record(observation: Observation, sequence: int, elapsed: float) -> bytes:
    if not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("non-finite observation time")
    record: dict[str, object] = {
        "event_version": 1,
        "sequence": sequence,
        "elapsed_seconds": round(elapsed, 6),
    }
    for field in fields(observation):
        value = getattr(observation, field.name)
        if field.name == "event":
            valid = value in _EVENTS
        elif field.name == "phase":
            valid = value in _PHASES
        elif field.name == "outcome":
            valid = value is None or value in _OUTCOMES
        elif field.name == "reason":
            valid = value is None or value in _REASONS
        elif field.name == "executed":
            valid = value is None or type(value) is bool
        else:
            valid = value is None or (type(value) is int and 0 <= value <= 2**63 - 1)
        if not valid:
            raise ValueError("observation contains a non-allowlisted fact")
        if value is not None or (field.name == "executed" and observation.event == "invocation"):
            record[field.name] = value
    try:
        encoded = (
            json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("cannot serialize finite observation") from exc
    if len(encoded) > RECORD_LIMIT:
        raise ValueError("observation record exceeds limit")
    return encoded


class StreamObserver:
    """Own synchronous sinks, disable failed sinks, and retain no event history."""

    def __init__(
        self,
        *,
        events: BinaryIO | None = None,
        progress: TextIO | None = None,
        warning: TextIO | None = None,
        limit: int = EVENT_LIMIT,
    ) -> None:
        if limit < 2 * RECORD_LIMIT or limit > EVENT_LIMIT:
            raise ValueError("event cap must be between 8192 bytes and 16 MiB")
        self._events = events
        self._owned_events = events
        self._progress = progress
        self._warning = warning
        self._limit = limit
        self._written = 0
        self._sequence = 0
        self._started = time.monotonic()
        self._last_progress = -math.inf
        self._last_accepted = 0
        self._warned: set[str] = set()

    def _warn(self, sink: str) -> None:
        if sink in self._warned:
            return
        self._warned.add(sink)
        warning = self._warning
        if warning is not None:
            try:
                message = f"reproseed: {sink} telemetry disabled; observations are incomplete\n"
                if warning.write(message) != len(message):
                    raise OSError("short telemetry warning write")
                warning.flush()
                return
            except (OSError, ValueError):
                self._warning = None
                if warning is self._progress:
                    self._progress = None
        if sink != "stderr" and self._events is None:
            return
        self._write_event(
            Observation(
                event="sink_disabled",
                phase="observation",
                reason="stderr_unavailable" if sink == "stderr" else "events_unavailable",
            )
        )

    def _write_event(self, observation: Observation) -> None:
        if self._events is None:
            return
        try:
            encoded = _record(observation, self._sequence + 1, time.monotonic() - self._started)
            if self._written + len(encoded) > self._limit - TRUNCATION_RESERVE:
                encoded = _record(
                    Observation(event="truncated", phase="observation", reason="size_limit"),
                    self._sequence + 1,
                    time.monotonic() - self._started,
                )
                capped = True
            else:
                capped = False
            sink = self._events
            # One unbuffered write; a short/uncertain write permanently disables this sink.
            # Detach before entering I/O. An interruption propagates, but search salvage
            # must not append after an uncertain write or reuse a sequence number.
            self._events = None
            if sink.write(encoded) != len(encoded):
                raise OSError("short event write")
            sink.flush()
            self._written += len(encoded)
            self._sequence += 1
            self._events = sink
            if capped:
                self._events = None
                self._warn("events")
        except (OSError, ValueError, UnicodeError):
            self._events = None
            self._warn("events")

    def emit(self, observation: Observation) -> None:
        self._write_event(observation)
        if self._progress is None:
            return
        now = time.monotonic()
        repetitive = observation.phase == "search" and observation.event in {
            "candidate",
            "committed",
            "invocation",
        }
        accepted = observation.accepted_changes
        if observation.event == "committed" and accepted is not None:
            repetitive = repetitive and accepted <= self._last_accepted
        if repetitive and now - self._last_progress < PROGRESS_INTERVAL:
            return
        try:
            # Reuse the allowlist for text: arbitrary strings can never reach a terminal.
            facts = json.loads(_record(observation, 0, 0.0))
            parts = [f"reproseed: {observation.phase} {observation.event}"]
            parts.extend(
                f"{key}={value}"
                for key, value in facts.items()
                if key
                not in {
                    "event_version",
                    "sequence",
                    "elapsed_seconds",
                    "event",
                    "phase",
                }
            )
            message = " ".join(parts) + "\n"
            sink = self._progress
            self._progress = None
            if sink.write(message) != len(message):
                raise OSError("short progress write")
            sink.flush()
            self._last_progress = now
            if accepted is not None:
                self._last_accepted = accepted
            self._progress = sink
        except (OSError, ValueError, UnicodeError):
            self._progress = None
            self._warn("stderr")

    def close(self) -> None:
        if self._owned_events is not None:
            try:
                self._owned_events.close()
            except OSError:
                self._events = None
                self._warn("events")
            finally:
                self._owned_events = None


@contextmanager
def observation_context(
    config: Config,
    output: Path,
    *,
    events: Path | None,
    progress: bool,
) -> Iterator[Observer]:
    if events is None and not progress:
        yield NO_OBSERVER
        return
    file: BinaryIO | None = None
    if events is not None:
        try:
            path = _checked_event_path(config, output, events)
            file = path.open("xb", buffering=0)
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                file.close()
                raise ObservationError("event file must be a regular file")
        except OSError as exc:
            if file is not None:
                try:
                    file.close()
                except OSError:
                    pass
            raise ObservationError(
                "cannot create event file exclusively; check its parent and permissions"
            ) from exc
    observer = StreamObserver(
        events=file,
        progress=sys.stderr if progress else None,
        warning=sys.stderr,
    )
    try:
        yield observer
    finally:
        observer.close()
