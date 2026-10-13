"""Cancellation at invocation transfers must preserve established launch evidence."""

from __future__ import annotations

import inspect
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from types import FrameType

import pytest

from reproseed.artifacts import sha256
from reproseed.cli import main
from reproseed.config import Asset, Config, OracleSpec
from reproseed.oracle import OracleInterrupted, OracleInvocation, OracleResult, Outcome, run_oracle
from reproseed.reducer import AbortReduction, BudgetExhausted
from reproseed.report import validate_report
from reproseed.workflow import InvocationCounter, build_verified_fixture


@contextmanager
def interrupt_before_statement(function: object, statement: str) -> Iterator[None]:
    """One-shot probe at the process-handle to launch-evidence boundary."""
    lines, start = inspect.getsourcelines(function)
    target_line = start + next(
        index for index, line in enumerate(lines) if line.strip() == statement
    )
    fired = False

    def trace(frame: FrameType, event: str, argument: object) -> object:
        nonlocal fired
        if event == "line" and frame.f_lineno == target_line and frame.f_code == function.__code__:
            fired = True
            sys.settrace(None)
            raise KeyboardInterrupt
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        yield
    finally:
        sys.settrace(previous)
    assert fired, "the intended launch boundary was not reached"


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        tmp_path / "case.toml",
        tmp_path / "source.sqlite3",
        (),
        OracleSpec(("unused",), 42, "TARGET", "stdout", 1.0, 4096),
        8,
    )


def target_result() -> OracleResult:
    return OracleResult(
        Outcome.TARGET_FAILURE, "expected exit and exact failure marker", 42, 7, 0.01
    )


@pytest.mark.parametrize("publish_first", [False, True])
def test_completed_accounting_publication_cannot_lose_or_duplicate_known_charge(
    config: Config, monkeypatch: pytest.MonkeyPatch, publish_first: bool
) -> None:
    monkeypatch.setattr("reproseed.workflow.run_oracle", lambda *args: target_result())
    counter = InvocationCounter(config)
    original_publish = counter._publish_accounting
    fired = False

    def interrupt(accounting: object) -> None:
        nonlocal fired
        if not fired:
            fired = True
            if publish_first:
                original_publish(accounting)
            raise KeyboardInterrupt
        original_publish(accounting)

    monkeypatch.setattr(counter, "_publish_accounting", interrupt)
    with pytest.raises(KeyboardInterrupt):
        counter.invoke(config.source)
    assert fired
    assert counter.count == 1
    assert counter.unknown_launches == 0
    assert counter.charged == 1
    assert counter.interrupted_invocations == [
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": True}
    ]


@pytest.mark.parametrize("executed", [False, True, None])
def test_interrupted_record_and_charge_publish_together(
    config: Config, monkeypatch: pytest.MonkeyPatch, executed: bool | None
) -> None:
    def interrupt(*args: object) -> OracleResult:
        raise OracleInterrupted(executed)

    monkeypatch.setattr("reproseed.workflow.run_oracle", interrupt)
    counter = InvocationCounter(config)
    with pytest.raises(OracleInterrupted):
        counter.invoke(config.source)
    assert counter.interrupted_invocations == [
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": executed}
    ]
    assert counter.count == (executed is True)
    assert counter.unknown_launches == (executed is None)
    assert counter.charged == (executed is not False)


def test_further_oracle_cleanup_interrupt_aborts_after_one_known_charge(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(*args: object) -> OracleResult:
        raise OracleInterrupted(True, abort=True)

    monkeypatch.setattr("reproseed.workflow.run_oracle", interrupt)
    counter = InvocationCounter(config)
    with pytest.raises(AbortReduction):
        counter.invoke(config.source)
    assert counter.count == counter.charged == 1
    assert counter.unknown_launches == 0
    assert counter.interrupted_invocations == [
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": True}
    ]


def test_second_interrupt_in_real_oracle_cleanup_aborts_and_preserves_launch(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reproseed import oracle

    with closing(sqlite3.connect(config.source)) as database:
        database.execute("CREATE TABLE records (id INTEGER PRIMARY KEY)")
    config = replace(config, oracle=replace(config.oracle, argv=("{python}", "-c", "pass")))
    original = oracle._kill_tree
    calls = 0

    def interrupt_cleanup(*args: object) -> None:
        nonlocal calls
        calls += 1
        original(*args)
        raise KeyboardInterrupt

    monkeypatch.setattr(oracle, "_kill_tree", interrupt_cleanup)
    counter = InvocationCounter(config)
    with interrupt_before_statement(oracle._execute, "execution.executed = True"):
        with pytest.raises(AbortReduction):
            counter.invoke(config.source)
    assert calls == 1
    assert counter.count == counter.charged == 1
    assert counter.unknown_launches == 0
    assert counter.interrupted_invocations == [
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": True}
    ]


@pytest.mark.parametrize("executed", [False, True, None])
@pytest.mark.parametrize("publish_first", [False, True])
def test_further_cancellation_during_interrupted_accounting_aborts_with_coherent_snapshot(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    executed: bool | None,
    publish_first: bool,
) -> None:
    def interrupt_oracle(*args: object) -> OracleResult:
        raise OracleInterrupted(executed)

    monkeypatch.setattr("reproseed.workflow.run_oracle", interrupt_oracle)
    counter = InvocationCounter(config)
    original_publish = counter._publish_accounting

    def interrupt_publication(accounting: object) -> None:
        if publish_first:
            original_publish(accounting)
        raise KeyboardInterrupt

    monkeypatch.setattr(counter, "_publish_accounting", interrupt_publication)
    with pytest.raises(AbortReduction):
        counter.invoke(config.source)
    # This second interruption aborts recovery. No partially recorded charge or
    # interruption is exposed, and an aborted workflow cannot publish a bundle.
    assert counter.count == (publish_first and executed is True)
    assert counter.unknown_launches == (publish_first and executed is None)
    assert len(counter.interrupted_invocations) == int(publish_first)
    assert counter.charged == (publish_first and executed is not False)


@pytest.mark.parametrize("confirmation", [1, 2])
def test_completed_real_oracle_result_lost_during_return_transfer_is_charged(
    config: Config,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    confirmation: int,
) -> None:
    with closing(sqlite3.connect(config.source)) as database:
        database.executescript(
            "CREATE TABLE things(id INTEGER PRIMARY KEY);INSERT INTO things VALUES(1);"
        )
    config = replace(
        config,
        oracle=replace(
            config.oracle, argv=("{python}", "-c", "print('TARGET'); raise SystemExit(42)")
        ),
    )
    calls = 0

    def lost_return(
        spec: OracleSpec,
        database: Path,
        assets: tuple[Asset, ...],
        invocation: OracleInvocation | None = None,
    ) -> OracleResult:
        nonlocal calls
        calls += 1
        result = run_oracle(spec, database, assets, invocation)
        assert result.outcome == Outcome.TARGET_FAILURE
        if calls == 3 + confirmation:
            # The process completed, but no result reaches InvocationCounter.
            raise KeyboardInterrupt
        return result

    monkeypatch.setattr("reproseed.workflow.run_oracle", lost_return)
    destination = tmp_path / "final.sqlite3"
    report = build_verified_fixture(config, destination)
    assert calls == 6 + confirmation
    assert report["oracle_invocations"] == calls
    assert report["unknown_interrupted_launches"] == 0
    assert report["budget_charged_invocations"] == calls <= config.max_invocations
    assert report["accepted_reductions"] == []
    assert report["original_counts"] == report["final_counts"] == {"things": 1}
    assert report["interrupted_invocations"] == [
        {"outcome": "UNRESOLVED", "reason": "interrupted", "executed": True}
    ]
    assert report["termination_reason"] == "interrupted_best_confirmed_candidate_preserved"
    assert len(report["baseline_verification"]) == len(report["final_verification"]) == 3
    validate_report(report, config)
    with closing(sqlite3.connect(destination)) as database:
        assert database.execute("SELECT id FROM things").fetchall() == [(1,)]


def test_returned_process_handle_establishes_known_launch_before_evidence_assignment(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reproseed.oracle import _execute

    config.source.write_bytes(b"synthetic staged input")
    config = replace(
        config,
        oracle=replace(config.oracle, argv=("{python}", "-c", "import time;time.sleep(30)")),
    )
    counter = InvocationCounter(config)
    with (
        interrupt_before_statement(_execute, "execution.executed = True"),
        pytest.raises(OracleInterrupted) as error,
    ):
        counter.invoke(config.source)
    assert error.value.executed is True
    assert counter.count == counter.charged == 1
    assert counter.unknown_launches == 0


def test_budget_check_does_not_launch_or_charge_again(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def invoke(*args: object) -> OracleResult:
        nonlocal calls
        calls += 1
        return target_result()

    monkeypatch.setattr("reproseed.workflow.run_oracle", invoke)
    counter = InvocationCounter(config)
    for _ in range(config.max_invocations):
        counter.invoke(config.source)
    with pytest.raises(BudgetExhausted):
        counter.invoke(config.source)
    assert calls == counter.count == counter.charged == config.max_invocations
    assert not counter.interrupted_invocations


@pytest.mark.parametrize("publish_first", [False, True])
def test_further_interrupt_during_counter_recovery_aborts_real_cli_bundle(
    config: Config,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    publish_first: bool,
) -> None:
    with closing(sqlite3.connect(config.source)) as database:
        database.executescript(
            "CREATE TABLE things(id INTEGER PRIMARY KEY);INSERT INTO things VALUES(1);"
        )
    config.path.write_text(
        'version=1\nsource="source.sqlite3"\ninclude=[]\n'
        '[oracle]\nargv=["{python}","-c","print(\'TARGET\'); raise SystemExit(42)"]\n'
        'expected_exit=42\nmarker="TARGET"\nstream="stdout"\n'
        "timeout_seconds=2.0\noutput_limit_bytes=4096\n[reduction]\nmax_invocations=8\n",
        encoding="utf-8",
    )
    original_hashes = {path: sha256(path) for path in (config.path, config.source)}
    calls = 0
    publications = 0
    original_publish = InvocationCounter._publish_accounting

    def interrupted_oracle(*args: object) -> OracleResult:
        nonlocal calls
        calls += 1
        result = run_oracle(*args)
        assert result.outcome == Outcome.TARGET_FAILURE
        if calls == 4:
            raise OracleInterrupted(True)
        return result

    def interrupted_publication(counter: InvocationCounter, accounting: object) -> None:
        nonlocal publications
        publications += 1
        if publications == 4:
            if publish_first:
                original_publish(counter, accounting)
            raise KeyboardInterrupt
        original_publish(counter, accounting)

    monkeypatch.setattr("reproseed.workflow.run_oracle", interrupted_oracle)
    monkeypatch.setattr(InvocationCounter, "_publish_accounting", interrupted_publication)
    bundle = tmp_path / "bundle"
    assert (
        main(["reduce", "--config", str(config.path), "--out", str(bundle), "--allow-exec"]) == 130
    )
    output = capsys.readouterr()
    assert "interrupted before a verified bundle could be completed" in output.err
    assert not output.out
    assert calls == 4  # Three real baseline confirmations, then one interrupted trial.
    assert not bundle.exists()
    assert {path: sha256(path) for path in original_hashes} == original_hashes
