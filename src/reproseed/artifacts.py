"""Versioned, hashed bundles with immutable fixture replay."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import sqlite3
import tempfile
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import cast

from reproseed import __version__
from reproseed.config import Asset, Config, ConfigError, load_config, relative_name, safe_file
from reproseed.oracle import Outcome, run_oracle
from reproseed.sqlite_adapter import validate_database
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
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def replay_toml(config: Config) -> str:
    def quote(value: object) -> str:
        # TOML does not accept JSON's UTF-16 surrogate-pair escapes.
        return json.dumps(value, ensure_ascii=False)

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


def create_bundle(config: Config, output: Path) -> dict[str, object]:
    output = check_output(config, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reproseed-build-", dir=output.parent) as temporary:
        staging = Path(temporary)
        staged_assets: list[Asset] = []
        for asset in config.assets:
            destination = staging / asset.relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset.path, destination)
            staged_assets.append(Asset(asset.relative, destination))
        staged = replace(config, assets=tuple(staged_assets))
        report = build_verified_fixture(staged, staging / "fixture.sqlite3")
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
    return report


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, object]:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise BundleError(f"JSON file exceeds 64 MiB: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, ValueError) as exc:
        raise BundleError(f"cannot parse {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise BundleError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], value)


def validate_bundle(bundle: Path) -> tuple[Config, dict[str, object]]:
    if bundle.is_symlink() or bundle.is_junction() or not bundle.is_dir():
        raise BundleError("bundle must be a regular directory, without a symlink or junction")
    root = bundle.resolve()
    try:
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
        for name, digest in artifacts.items():
            relative_name(name)
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise BundleError(f"invalid digest for {name}")
            if sha256(safe_file(root, name)) != digest:
                raise BundleError(f"artifact hash mismatch: {name}")
        required = {"fixture.sqlite3", "replay.toml", "report.json", "README.md"}
        if not required.issubset(artifacts):
            raise BundleError("manifest is missing required artifacts")
        replay_path = safe_file(root, "replay.toml")
        if replay_path.stat().st_size > 1024 * 1024:
            raise BundleError("replay configuration exceeds 1 MiB")
        with replay_path.open("rb") as file:
            replay = tomllib.load(file)
        if replay.get("source") != "fixture.sqlite3":
            raise BundleError("replay source must be the bundled fixture.sqlite3")
        config = load_config(replay_path)
        if set(artifacts) != required | {asset.relative for asset in config.assets}:
            raise BundleError("manifest files do not match replay assets and required files")
        report = read_json(safe_file(root, "report.json"))
        if type(report.get("version")) is not int or report["version"] != 1:
            raise BundleError("unsupported report version")
        if report.get("verified") is not True:
            raise BundleError("bundle report does not declare a verified fixture")
        return config, report
    except (ConfigError, OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise BundleError(str(exc)) from exc


def replay_bundle(bundle: Path) -> dict[str, object]:
    config, _ = validate_bundle(bundle)
    with tempfile.TemporaryDirectory(prefix="reproseed-replay-") as temporary:
        fixture = Path(temporary) / "fixture.sqlite3"
        shutil.copyfile(config.source, fixture)
        validate_database(fixture)
        results = [run_oracle(config.oracle, fixture, config.assets).as_dict() for _ in range(3)]
    outcomes = {result["outcome"] for result in results}
    if outcomes == {Outcome.TARGET_FAILURE.value}:
        outcome = Outcome.TARGET_FAILURE.value
    elif outcomes == {Outcome.PASS.value}:
        outcome = Outcome.PASS.value
    else:
        outcome = Outcome.UNRESOLVED.value
    return {"outcome": outcome, "confirmations": results}
