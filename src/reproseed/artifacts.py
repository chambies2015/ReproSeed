"""Versioned, hashed bundles with immutable fixture replay."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import shutil
import sqlite3
import sys
import tempfile
import tomllib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from reproseed import __version__
from reproseed.config import (
    RESERVED,
    Asset,
    Config,
    ConfigError,
    load_config,
    relative_name,
    safe_file,
)
from reproseed.observation import NO_OBSERVER, Observation, Observer
from reproseed.oracle import Outcome, run_oracle
from reproseed.report import ReportError, validate_report
from reproseed.sqlite_adapter import DatabaseError, DatabaseModel
from reproseed.workflow import build_verified_fixture


class BundleError(ValueError):
    """A bundle cannot be safely inspected or replayed."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    try:
        encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except (ValueError, TypeError, RecursionError) as exc:
        raise BundleError("cannot serialize finite JSON metadata") from exc
    path.write_text(encoded, encoding="utf-8")


def replay_toml(config: Config) -> str:
    def quote(value: object) -> str:
        # TOML does not accept JSON's UTF-16 surrogate-pair escapes.
        return json.dumps(value, ensure_ascii=False, allow_nan=False)

    return (
        'version = 1\nsource = "fixture.sqlite3"\n'
        f"include = {quote([asset.relative for asset in config.assets])}\n\n"
        "[oracle]\n"
        f"argv = {quote(list(config.oracle.argv))}\n"
        f"expected_exit = {config.oracle.expected_exit}\n"
        f"marker = {quote(config.oracle.marker)}\n"
        f"stream = {quote(config.oracle.stream)}\n"
        f"timeout_seconds = {config.oracle.timeout_seconds}\n"
        f"output_limit_bytes = {config.oracle.output_limit_bytes}\n\n"
        "[reduction]\n"
        f"max_invocations = {config.max_invocations}\n"
    )


def check_output(config: Config, output: Path) -> Path:
    # Check before resolve too: a broken symlink is still an existing output.
    if output.exists() or output.is_symlink() or output.is_junction():
        raise BundleError("output already exists; choose a new bundle directory")
    output = output.resolve()
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = config.source.with_name(config.source.name + suffix)
        if output == sidecar or output.is_relative_to(sidecar):
            raise BundleError("output conflicts with a source SQLite sidecar path")
    for input_path in (config.path, config.source, *(asset.path for asset in config.assets)):
        if input_path == output or input_path.is_relative_to(output):
            raise BundleError("output conflicts with an input file or directory")
    return output


@contextmanager
def _build_directory(parent: Path) -> Iterator[Path]:
    # tempfile retries Windows PermissionError when os.access claims a directory
    # is writable; that ACL-blind check can cause a long denied-mkdir loop.
    # One exclusive mkdir propagates denial immediately and never owns collisions.
    owned = parent / (".reproseed-build-" + uuid.uuid4().hex)
    owned.mkdir(mode=0o700)
    try:
        # Keep TemporaryDirectory's portable readonly-file cleanup within our
        # successfully created private parent, rather than the unchecked output parent.
        with tempfile.TemporaryDirectory(prefix="payload-", dir=owned) as temporary:
            yield Path(temporary)
    finally:
        already_failing = sys.exc_info()[0] is not None
        try:
            owned.rmdir()
        except OSError:
            # An inner cleanup failure/interruption can leave its child behind.
            # Preserve that original exception, including CLI interruption semantics.
            if not already_failing:
                raise


def create_bundle(
    config: Config, output: Path, observer: Observer = NO_OBSERVER
) -> dict[str, object]:
    observer.emit(Observation("started", "run"))
    try:
        report = _create_bundle(config, output, observer)
    except KeyboardInterrupt:
        observer.emit(Observation("aborted", "run", reason="interrupted"))
        raise
    except (ValueError, OSError, sqlite3.Error):
        observer.emit(Observation("failed", "run", reason="operation_failed"))
        raise
    observer.emit(
        Observation(
            "completed",
            "run",
            original_rows=sum(cast(dict[str, int], report["original_counts"]).values()),
            retained_rows=sum(cast(dict[str, int], report["final_counts"]).values()),
            attempts=len(cast(list[object], report["attempts"])),
            accepted_changes=len(cast(list[object], report["accepted_reductions"])),
            cache_hits=cast(int, report["cache_hits"]),
            known_executions=cast(int, report["oracle_invocations"]),
            charged_invocations=cast(int, report["budget_charged_invocations"]),
            unknown_launches=cast(int, report["unknown_interrupted_launches"]),
        )
    )
    return report


def _create_bundle(config: Config, output: Path, observer: Observer) -> dict[str, object]:
    observer.emit(Observation("started", "preparation"))
    output = check_output(config, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with _build_directory(output.parent) as staging:
        staged_assets: list[Asset] = []
        for asset in config.assets:
            destination = staging / asset.relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset.path, destination)
            staged_assets.append(Asset(asset.relative, destination))
        staged = replace(config, assets=tuple(staged_assets))
        observer.emit(Observation("completed", "preparation"))
        report = build_verified_fixture(staged, staging / "fixture.sqlite3", observer=observer)
        observer.emit(Observation("started", "publication"))
        (staging / "replay.toml").write_text(replay_toml(staged), encoding="utf-8")
        write_json(staging / "report.json", report)
        (staging / "README.md").write_text(
            "# Verified ReproSeed fixture\n\n"
            "Replay: `reproseed replay /path/to/this/bundle --allow-exec`.\n"
            "Inspect without executing code: `reproseed inspect /path/to/this/bundle`.\n\n"
            "Three fresh invocations of the compact artifact satisfied the configured oracle.\n"
            "The result is not proven globally minimal. Reduction is not anonymization.\n"
            "Retained data, schema, assets, and markers may contain sensitive information.\n"
            "Hashes detect edits relative to the manifest; they do not authenticate a bundle.\n"
            "The oracle executes with your OS permissions. Temporary copies are not a sandbox.\n"
            "{python} uses your current ReproSeed interpreter. Other executables and application\n"
            "dependencies in replay.toml must be supplied externally. Only the bundled demos\n"
            "are self-contained apart from Python and ReproSeed. See report.json for evidence.\n",
            encoding="utf-8",
        )
        names = {"fixture.sqlite3", "replay.toml", "report.json", "README.md"} | {
            asset.relative for asset in staged_assets
        }
        manifest = {
            "version": 1,
            "tool": "reproseed",
            "tool_version": __version__,
            "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
            "hash_algorithm": "sha256",
            "artifacts": {name: sha256(staging / name) for name in sorted(names)},
        }
        write_json(staging / "manifest.json", manifest)
        validate_bundle(staging)
        # Exclusive mkdir prevents overwriting even an empty directory created concurrently.
        output.mkdir(exist_ok=False)
        try:
            for path in staging.iterdir():
                if path.name != "manifest.json":
                    shutil.move(str(path), output / path.name)
            shutil.move(str(staging / "manifest.json"), output / "manifest.json")
        except BaseException:
            # Only this newly created directory is ours. Never remove a pre-existing bundle.
            shutil.rmtree(output)
            raise
        observer.emit(Observation("published", "publication"))
    return report


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError("duplicate JSON key")
        result[key] = value
    return result


JSON_LIMIT = 64 * 1024 * 1024
JSON_DEPTH_LIMIT = 64


def _bounded_read(path: Path, limit: int, label: str) -> bytes:
    with path.open("rb") as file:
        data = file.read(limit + 1)
    if len(data) > limit:
        raise BundleError(f"{label} exceeds {limit} bytes")
    return data


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise BundleError("JSON numbers must be finite")
    return result


def _reject_constant(value: str) -> object:
    raise BundleError("JSON numbers must be finite")


def _check_json_depth(value: object) -> None:
    pending: list[tuple[Iterator[object], int]] = [(iter((value,)), 1)]
    while pending:
        nodes, depth = pending[-1]
        try:
            node = next(nodes)
        except StopIteration:
            pending.pop()
            continue
        if isinstance(node, (dict, list)):
            if depth > JSON_DEPTH_LIMIT:
                raise BundleError(f"JSON nesting exceeds {JSON_DEPTH_LIMIT} levels")
            children = node.values() if isinstance(node, dict) else node
            pending.append((iter(children), depth + 1))


def read_json(path: Path) -> dict[str, object]:
    try:
        data = _bounded_read(path, JSON_LIMIT, "JSON file")
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=_finite_float,
            parse_constant=_reject_constant,
        )
        _check_json_depth(value)
    except BundleError:
        raise
    except (OSError, ValueError, RecursionError) as exc:
        raise BundleError(
            "cannot parse JSON metadata: malformed UTF-8/JSON or excessive nesting"
        ) from exc
    if not isinstance(value, dict):
        raise BundleError("JSON metadata must contain an object")
    return cast(dict[str, object], value)


def _manifest(root: Path) -> tuple[dict[str, object], dict[str, str]]:
    manifest = read_json(safe_file(root, "manifest.json"))
    if set(manifest) != {
        "version",
        "tool",
        "tool_version",
        "runtime",
        "hash_algorithm",
        "artifacts",
    }:
        raise BundleError("manifest has missing or unknown fields")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise BundleError("unsupported manifest version")
    if manifest["tool"] != "reproseed" or manifest["hash_algorithm"] != "sha256":
        raise BundleError("unsupported manifest tool or hash algorithm")
    runtime = manifest["runtime"]
    if (
        not isinstance(manifest["tool_version"], str)
        or not isinstance(runtime, dict)
        or set(runtime) != {"python", "sqlite"}
        or any(not isinstance(v, str) for v in runtime.values())
    ):
        raise BundleError("invalid tool/runtime metadata")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict):
        raise BundleError("manifest.artifacts must map names to SHA256 digests")
    required = {"fixture.sqlite3", "replay.toml", "report.json", "README.md"}
    if not required.issubset(artifacts):
        raise BundleError("manifest is missing required artifacts")
    folded: set[str] = set()
    reserved = {name.casefold() for name in RESERVED}
    for name, digest in artifacts.items():
        relative_name(name)
        key = name.casefold()
        if (
            key in folded
            or any(key.startswith(n + "/") or n.startswith(key + "/") for n in folded)
            or (name not in required and name.split("/")[0].casefold() in reserved)
        ):
            raise BundleError("manifest has reserved, duplicate or conflicting artifact names")
        folded.add(key)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise BundleError(f"invalid digest for {name!r}")
    return manifest, cast(dict[str, str], artifacts)


def _reject_sidecars(root: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = root / ("fixture.sqlite3" + suffix)
        if sidecar.exists() or sidecar.is_symlink() or sidecar.is_junction():
            raise BundleError(
                "static bundle fixture must not have SQLite WAL, SHM or journal sidecars"
            )


def _copy_payload(root: Path, destination: Path, artifacts: dict[str, str]) -> None:
    """Copy only declared regular files; mode bits preserve POSIX executable assets."""
    for name in artifacts:
        source = safe_file(root, name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in {"report.json", "replay.toml"}:
            limit = JSON_LIMIT if name == "report.json" else 1024 * 1024
            target.write_bytes(_bounded_read(source, limit, name))
        else:
            shutil.copy2(source, target)


@dataclass(frozen=True)
class VerifiedBundle:
    """Verified private payload; paths are usable only inside acquire_bundle's context."""

    root: Path
    config: Config
    report: dict[str, object]
    manifest: dict[str, object]


@contextmanager
def acquire_bundle(bundle: Path) -> Iterator[VerifiedBundle]:
    """Capture metadata, copy/hash payload, then validate without opening original SQLite."""
    if bundle.is_symlink() or bundle.is_junction() or not bundle.is_dir():
        raise BundleError("bundle must be a regular directory, without a symlink or junction")
    root = bundle.resolve()
    try:
        manifest, artifacts = _manifest(root)
        _reject_sidecars(root)
        with tempfile.TemporaryDirectory(prefix="reproseed-bundle-") as temporary:
            private = Path(temporary)
            payload = private / "payload"
            payload.mkdir()
            _copy_payload(root, payload, artifacts)
            _reject_sidecars(root)
            for name, digest in artifacts.items():
                if sha256(payload / name) != digest:
                    raise BundleError(f"artifact hash mismatch: {name!r}")
            replay_path = payload / "replay.toml"
            try:
                replay = tomllib.loads(
                    _bounded_read(replay_path, 1024 * 1024, "replay configuration").decode("utf-8")
                )
            except BundleError:
                raise
            except (ValueError, RecursionError) as exc:
                raise BundleError(
                    "invalid replay configuration: malformed UTF-8/TOML or numeric input"
                ) from exc
            if replay.get("source") != "fixture.sqlite3":
                raise BundleError("replay source must be the bundled fixture.sqlite3")
            config = load_config(replay_path)
            required = {"fixture.sqlite3", "replay.toml", "report.json", "README.md"}
            if set(artifacts) != required | {asset.relative for asset in config.assets}:
                raise BundleError("manifest files do not match replay assets and required files")
            report = read_json(payload / "report.json")
            validate_report(report, config)
            # SQLite may create SHM even on a read-only WAL connection. Open only a
            # separate disposable validation copy, leaving the hashed payload pristine.
            check = private / "check"
            check.mkdir()
            fixture = check / "fixture.sqlite3"
            shutil.copyfile(config.source, fixture)
            if DatabaseModel.from_database(fixture).counts() != report["final_counts"]:
                raise BundleError("fixture table counts disagree with report.final_counts")
            yield VerifiedBundle(payload, config, report, manifest)
    except ConfigError as exc:
        raise BundleError("invalid replay configuration or unsafe bundle artifact path") from exc
    except ReportError as exc:
        raise BundleError(str(exc)) from exc
    except DatabaseError as exc:
        raise BundleError(
            "fixture failed supported-schema, integrity or foreign-key validation"
        ) from exc
    except OSError as exc:
        raise BundleError(
            "cannot read or copy bundle files; check declared files and permissions"
        ) from exc
    except (UnicodeError, tomllib.TOMLDecodeError, RecursionError) as exc:
        raise BundleError(
            "invalid replay metadata: malformed UTF-8/TOML or excessive nesting"
        ) from exc


def validate_bundle(bundle: Path) -> tuple[Config, dict[str, object]]:
    """Inspection compatibility API. Replay must retain acquire_bundle's private lifetime."""
    with acquire_bundle(bundle) as acquired:
        root = bundle.resolve()
        config = replace(
            acquired.config,
            path=root / "replay.toml",
            source=root / "fixture.sqlite3",
            assets=tuple(Asset(a.relative, root / a.relative) for a in acquired.config.assets),
        )
        return config, acquired.report


def replay_bundle(bundle: Path) -> dict[str, object]:
    with acquire_bundle(bundle) as acquired:
        config = acquired.config
        results = [
            run_oracle(config.oracle, config.source, config.assets).as_dict() for _ in range(3)
        ]
    outcomes = {result["outcome"] for result in results}
    if outcomes == {Outcome.TARGET_FAILURE.value}:
        outcome = Outcome.TARGET_FAILURE.value
    elif outcomes == {Outcome.PASS.value}:
        outcome = Outcome.PASS.value
    else:
        outcome = Outcome.UNRESOLVED.value
    return {"outcome": outcome, "confirmations": results}
