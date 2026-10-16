"""Inspect concrete wheel/sdist contents without installing or publishing them."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def inspect_distributions(wheel: Path, sdist: Path) -> dict[str, object]:
    project = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    prefix = f"reproseed-{version}"
    dist_info = prefix + ".dist-info"
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
        runtime = {
            "reproseed/" + path.name: path.read_bytes()
            for path in (REPOSITORY / "src/reproseed").glob("*.py")
        }
        assert set(wheel_names) == set(runtime) | {
            f"{dist_info}/{name}"
            for name in ("METADATA", "WHEEL", "RECORD", "entry_points.txt", "licenses/LICENSE")
        }, wheel_names
        for name, content in runtime.items():
            assert archive.read(name) == content, name
        assert (
            archive.read(f"{dist_info}/licenses/LICENSE") == (REPOSITORY / "LICENSE").read_bytes()
        )
        metadata = Parser().parsestr(archive.read(f"{dist_info}/METADATA").decode("utf-8"))
        assert metadata["Name"] == "reproseed"
        assert metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.12"
        assert metadata["License-Expression"] == "MIT"
        assert metadata.get_all("License-File") == ["LICENSE"]
        assert metadata.get_all("Requires-Dist", []) == []
        assert metadata["Description-Content-Type"] == "text/markdown"
        assert (
            metadata.get_payload().strip()
            == (REPOSITORY / "README.md").read_text(encoding="utf-8").strip()
        )
        assert set(metadata.get_all("Project-URL", [])) == {
            f"{name}, {url}" for name, url in project["urls"].items()
        }
        entry_points = archive.read(f"{dist_info}/entry_points.txt").decode("utf-8")
        assert entry_points == "[console_scripts]\nreproseed = reproseed.cli:main\n"
    with tarfile.open(sdist) as archive:
        sdist_names = archive.getnames()
        members = {member.name: member for member in archive.getmembers()}
        assert all(member.isfile() for member in members.values()), (
            "sdist contains nonregular files"
        )
        for directory in ("src", "tests", "examples", "docs", "benchmarks", ".github"):
            for path in (REPOSITORY / directory).rglob("*"):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                relative = path.relative_to(REPOSITORY).as_posix()
                if path.suffix not in {".py", ".md", ".toml", ".yml", ".yaml"}:
                    continue
                name = f"{prefix}/{relative}"
                assert name in members, name
                extracted = archive.extractfile(members[name])
                assert extracted is not None
                assert extracted.read() == path.read_bytes(), name
        for name in ("README.md", "LICENSE", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md"):
            extracted = archive.extractfile(f"{prefix}/{name}")
            assert extracted is not None
            assert extracted.read() == (REPOSITORY / name).read_bytes(), name
    forbidden = {
        ".validation",
        ".venv",
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tools",
        ".env",
        "node_modules",
    }
    for name in wheel_names + sdist_names:
        assert not forbidden.intersection(name.split("/")), name
        assert not name.endswith(
            (
                ".sqlite3",
                ".sqlite",
                ".db",
                ".pyc",
                "-wal",
                "-shm",
                "-journal",
                ".log",
                ".jsonl",
                ".prof",
            )
        ), name
    return {
        "checks_passed": True,
        "version": version,
        "runtime_dependencies": [],
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "sdist_sha256": hashlib.sha256(sdist.read_bytes()).hexdigest(),
        "wheel_files": wheel_names,
        "sdist_files": sdist_names,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--sdist", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(inspect_distributions(arguments.wheel, arguments.sdist), indent=2))


if __name__ == "__main__":
    main()
