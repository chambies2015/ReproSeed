"""Portable CLI with explicit acknowledgement before executing configured commands."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from reproseed import __version__
from reproseed.artifacts import BundleError, acquire_bundle, create_bundle, replay_bundle
from reproseed.config import ConfigError, load_config
from reproseed.diagnostics import (
    describe_input_error,
    diagnose,
    format_diagnosis,
    serialize_diagnosis,
)
from reproseed.inspection import escape_terminal, format_inspection
from reproseed.observation import ObservationError, observation_context
from reproseed.sqlite_adapter import DatabaseError
from reproseed.workflow import VerificationError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="reproseed",
        description="Reduce SQLite fixtures while reconfirming a specified failure.",
    )
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command", required=True)
    diagnose_command = commands.add_parser(
        "diagnose", help="check fixture readiness; optionally run three baseline confirmations"
    )
    diagnose_command.add_argument(
        "--config", type=Path, required=True, help="version 1 TOML configuration"
    )
    diagnose_command.add_argument(
        "--allow-exec", action="store_true", help="execute oracle with your OS permissions"
    )
    diagnose_command.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="readable text (default) or diagnostic JSON",
    )
    reduce = commands.add_parser("reduce", help="verify, reduce, and export a new replay bundle")
    reduce.add_argument("--config", type=Path, required=True, help="version 1 TOML configuration")
    reduce.add_argument(
        "--out", type=Path, required=True, help="new output directory (must not exist)"
    )
    reduce.add_argument(
        "--allow-exec", action="store_true", help="execute oracle with your OS permissions"
    )
    reduce.add_argument(
        "--progress", action="store_true", help="write aggregate reduction progress to stderr"
    )
    reduce.add_argument(
        "--events",
        type=Path,
        help="exclusively create aggregate JSONL telemetry, relative to the caller's cwd",
    )
    inspect = commands.add_parser(
        "inspect", help="verify hashes and read report; never run the oracle"
    )
    inspect.add_argument("bundle", type=Path)
    inspect.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="report JSON (default) or a compact summary; neither executes the oracle",
    )
    replay = commands.add_parser("replay", help="verify hashes and reconfirm on three fresh copies")
    replay.add_argument("bundle", type=Path)
    replay.add_argument(
        "--allow-exec", action="store_true", help="execute oracle with your OS permissions"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command in {"reduce", "replay"} and not arguments.allow_exec:
        print(
            "reproseed: --allow-exec is required; configured code runs with your OS permissions",
            file=sys.stderr,
        )
        return 2
    try:
        if arguments.command == "diagnose":
            diagnosis = diagnose(arguments.config, allow_exec=arguments.allow_exec)
            print(
                serialize_diagnosis(diagnosis)
                if arguments.format == "json"
                else format_diagnosis(diagnosis)
            )
            return diagnosis.exit_code
        elif arguments.command == "reduce":
            config = load_config(arguments.config)
            if arguments.progress or arguments.events is not None:
                with observation_context(
                    config, arguments.out, events=arguments.events, progress=arguments.progress
                ) as observer:
                    report = create_bundle(config, arguments.out, observer=observer)
            else:
                report = create_bundle(config, arguments.out)
            summary = {
                key: report[key]
                for key in (
                    "original_counts",
                    "final_counts",
                    "oracle_invocations",
                    "termination_reason",
                    "verified",
                )
            }
            print(json.dumps(summary, indent=2, allow_nan=False))
        elif arguments.command == "inspect":
            with acquire_bundle(arguments.bundle) as acquired:
                if arguments.format == "text":
                    print(format_inspection(acquired.report, acquired.manifest))
                else:
                    print(json.dumps(acquired.report, indent=2, allow_nan=False))
        else:
            result = replay_bundle(arguments.bundle)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0 if result["outcome"] == "TARGET_FAILURE" else 1
        return 0
    except ObservationError as exc:
        print(f"reproseed: {exc}", file=sys.stderr)
        print(
            "Recovery: choose a new event file outside the bundle and inputs, with an "
            "existing writable parent; event-file parents are never created.",
            file=sys.stderr,
        )
        return 2
    except VerificationError as exc:
        print(f"reproseed: {escape_terminal(str(exc))}", file=sys.stderr)
        print(
            "Recovery: use diagnose --allow-exec to review fresh baseline outcomes, "
            "the exact exit/marker contract, dependencies and execution limits.",
            file=sys.stderr,
        )
        return 1
    except BundleError as exc:
        print(f"reproseed: {escape_terminal(str(exc))}", file=sys.stderr)
        print(
            "Recovery: check the bundle files and permissions; use a fresh output directory "
            "for reduction. Obtain an intact trusted copy if integrity validation failed.",
            file=sys.stderr,
        )
        return 2
    except (ConfigError, DatabaseError, OSError, sqlite3.Error) as exc:
        stage = "configuration"
        if isinstance(exc, DatabaseError):
            stage = (
                "snapshot"
                if str(exc) == "Snapshot acquisition timed out"
                else "database_validation"
            )
        detail = describe_input_error(exc, stage)
        print(f"reproseed: {detail.reason}: {detail.message}", file=sys.stderr)
        print(
            "Recovery: check input/output paths and permissions, and run diagnose "
            "without --allow-exec to review configuration and supported schema.",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print(
            "reproseed: interrupted; use inspect to check any output bundle before replay",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
