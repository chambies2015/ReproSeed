"""Strict, versioned configuration and explicit local asset selection."""

from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast


class ConfigError(ValueError):
    """Configuration is malformed or outside the M1a contract."""


@dataclass(frozen=True)
class Asset:
    relative: str
    path: Path


@dataclass(frozen=True)
class OracleSpec:
    argv: tuple[str, ...]
    expected_exit: int
    marker: str
    stream: Literal["stdout", "stderr"]
    timeout_seconds: float
    output_limit_bytes: int


@dataclass(frozen=True)
class Config:
    path: Path
    source: Path
    assets: tuple[Asset, ...]
    oracle: OracleSpec
    max_invocations: int


RESERVED = {
    "fixture.sqlite3",
    "replay.toml",
    "manifest.json",
    "report.json",
    "README.md",
    "db.sqlite3",
}
RESERVED |= {
    database + suffix
    for database in ("fixture.sqlite3", "db.sqlite3")
    for suffix in ("-wal", "-shm", "-journal")
}


def relative_name(value: object) -> str:
    """Require a portable, unambiguous, traversal-free relative file name."""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ConfigError("file paths must be nonempty relative paths using '/' separators")
    parts = value.split("/")
    if PurePosixPath(value).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ConfigError(f"unsafe relative path: {value!r}")
    for part in parts:
        if (
            any(ord(c) < 32 or c in '<>"|?*' for c in part)
            or part.endswith((".", " "))
            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
        ):
            raise ConfigError(f"nonportable file path: {value!r}")
    return value


def safe_file(root: Path, name: object) -> Path:
    relative = relative_name(name)
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink() or path.is_junction():
            raise ConfigError(f"symlinks and junctions are not permitted: {relative}")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ConfigError(f"expected a regular file inside configuration root: {relative}")
    return path


def _fields(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a table")
    fields = cast(dict[str, object], value)
    missing, unknown = expected - fields.keys(), fields.keys() - expected
    if missing or unknown:
        raise ConfigError(
            f"{label}: missing fields {sorted(missing)}; unknown fields {sorted(unknown)}"
        )
    return fields


def _integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConfigError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def load_config(path: Path) -> Config:
    path = path.resolve()
    try:
        if path.stat().st_size > 1024 * 1024:
            raise ConfigError("configuration exceeds 1 MiB")
        with path.open("rb") as file:
            raw = tomllib.load(file)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read TOML configuration: {exc}") from exc
    root = _fields(raw, {"version", "source", "include", "oracle", "reduction"}, "configuration")
    _integer(root["version"], 1, 1, "version")
    source_value = root["source"]
    if not isinstance(source_value, str) or not source_value or "\x00" in source_value:
        raise ConfigError("source must be a nonempty database path")
    source = (path.parent / source_value).resolve()
    if not source.is_file():
        raise ConfigError(f"source database is not a regular file: {source}")
    include = root["include"]
    if not isinstance(include, list):
        raise ConfigError("include must be an explicit array of relative regular-file names")
    assets: list[Asset] = []
    names: set[str] = set()
    source_paths = (
        source,
        *(source.with_name(source.name + suffix) for suffix in ("-wal", "-shm", "-journal")),
    )
    for item in include:
        name = relative_name(item)
        folded = name.casefold()
        if name.split("/")[0].casefold() in {n.casefold() for n in RESERVED} or folded in names:
            raise ConfigError(f"reserved or duplicate asset name: {name}")
        if any(folded.startswith(n + "/") or n.startswith(folded + "/") for n in names):
            raise ConfigError(f"conflicting asset file/directory names: {name}")
        asset_path = safe_file(path.parent, name)
        if any(
            asset_path.resolve() == protected
            or (protected.exists() and asset_path.samefile(protected))
            for protected in (*source_paths, path)
        ):
            raise ConfigError("include must not collect the source, its sidecars or configuration")
        names.add(folded)
        assets.append(Asset(name, asset_path))
    oracle = _fields(
        root["oracle"],
        {"argv", "expected_exit", "marker", "stream", "timeout_seconds", "output_limit_bytes"},
        "oracle",
    )
    argv = oracle["argv"]
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a for a in argv):
        raise ConfigError("oracle.argv must be a nonempty array of nonempty strings")
    for arg in argv:
        if "\x00" in arg or (("{" in arg or "}" in arg) and arg not in {"{python}", "{db}"}):
            raise ConfigError("argv placeholders must be whole arguments: {python} or {db}")
    marker = oracle["marker"]
    if not isinstance(marker, str) or not marker.strip() or any(c in marker for c in "\r\n\x00"):
        raise ConfigError("oracle.marker must be a nonempty exact single line")
    if len(marker.encode("utf-8")) > 4096:
        raise ConfigError("oracle.marker exceeds 4096 UTF-8 bytes")
    stream = oracle["stream"]
    if stream not in ("stdout", "stderr"):
        raise ConfigError("oracle.stream must be stdout or stderr")
    timeout = oracle["timeout_seconds"]
    if (
        type(timeout) not in (int, float)
        or not math.isfinite(cast(float, timeout))
        or not 0.01 <= cast(float, timeout) <= 3600
    ):
        raise ConfigError("oracle.timeout_seconds must be finite and between 0.01 and 3600")
    reduction = _fields(root["reduction"], {"max_invocations"}, "reduction")
    return Config(
        path,
        source,
        tuple(assets),
        OracleSpec(
            tuple(argv),
            _integer(oracle["expected_exit"], 1, 255, "oracle.expected_exit"),
            marker,
            stream,
            float(cast(float, timeout)),
            _integer(oracle["output_limit_bytes"], 1, 16777216, "oracle.output_limit_bytes"),
        ),
        _integer(reduction["max_invocations"], 6, 100000, "reduction.max_invocations"),
    )
