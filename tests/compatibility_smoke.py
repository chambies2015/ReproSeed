"""Generate a genuine reviewed version-1 bundle, then check the current CLI.

Run with --phase generate/validate separately to retain a pre-change bundle while
implementing the new reader. Scratch output must be a new .validation directory.
This is an explicit integration recipe, not an automatically collected pytest test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
REVIEWED_COMMIT = "ba40d64db748d974c36666294a1cc4500c79c25f"


def run(arguments: list[str], cwd: Path) -> str:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    result = subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {result.stdout}\n{result.stderr}"
        )
    return result.stdout


def cli(source: Path, arguments: list[str], cwd: Path) -> str:
    # The explicit first search path and assertion prevent an editable install
    # from silently replacing the reviewed implementation used by this recipe.
    bootstrap = (
        "import sys; from pathlib import Path; "
        f"root = Path({str(source)!r}).resolve(); sys.path.insert(0, str(root)); "
        "import reproseed; "
        "assert Path(reproseed.__file__).resolve().is_relative_to(root); "
        "from reproseed.cli import main; raise SystemExit(main(sys.argv[1:]))"
    )
    return run([sys.executable, "-c", bootstrap, *arguments], cwd)


def hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def generate(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory / "reviewed-source.zip"
    with archive.open("xb") as output:
        subprocess.run(
            ["git", "archive", "--format=zip", REVIEWED_COMMIT],
            cwd=REPOSITORY,
            stdout=output,
            check=True,
            timeout=60,
        )
    reviewed = directory / "reviewed"
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if entry.filename.startswith(("src/reproseed/", "examples/threshold/")):
                destination = reviewed / entry.filename
                assert destination.resolve().is_relative_to(reviewed.resolve())
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(source.read(entry))
    example = directory / "example"
    shutil.copytree(reviewed / "examples" / "threshold", example)
    run([sys.executable, str(example / "generate.py")], directory)
    source_before = hashes(example)
    cli(
        reviewed / "src",
        [
            "reduce",
            "--config",
            str(example / "reproseed.toml"),
            "--out",
            str(directory / "bundle"),
            "--allow-exec",
        ],
        directory,
    )
    assert hashes(example) == source_before, "reviewed reduction changed original example files"
    print(f"Generated version-1 bundle with reviewed commit {REVIEWED_COMMIT} at {directory}")


def validate(directory: Path) -> None:
    bundle = directory / "bundle"
    original_report = json.loads((bundle / "report.json").read_text(encoding="utf-8"))
    bundle_before = hashes(bundle)
    example = directory / "example"
    source_before = hashes(example)
    default_json = cli(REPOSITORY / "src", ["inspect", str(bundle)], directory)
    explicit_json = cli(REPOSITORY / "src", ["inspect", str(bundle), "--format", "json"], directory)
    assert json.loads(default_json) == json.loads(explicit_json) == original_report
    text = cli(REPOSITORY / "src", ["inspect", str(bundle), "--format", "text"], directory)
    (directory / "text-inspection.txt").write_text(text, encoding="utf-8")
    assert hashes(bundle) == bundle_before, "inspection changed original bundle files"
    relocated = directory / "relocated-bundle"
    bundle.rename(relocated)
    unavailable = directory / "example-unavailable"
    example.rename(unavailable)
    replay = json.loads(
        cli(REPOSITORY / "src", ["replay", str(relocated), "--allow-exec"], directory)
    )
    assert replay["outcome"] == "TARGET_FAILURE"
    assert len(replay["confirmations"]) == 3
    assert all(record["executed"] for record in replay["confirmations"])
    assert hashes(relocated) == bundle_before, "replay changed original bundle files"
    assert hashes(unavailable) == source_before, "current CLI changed original example files"
    result = {
        "reviewed_commit": REVIEWED_COMMIT,
        "original_rows": sum(original_report["original_counts"].values()),
        "final_rows": sum(original_report["final_counts"].values()),
        "old_reduction_executions": original_report["oracle_invocations"],
        "new_replay_confirmations": len(replay["confirmations"]),
        "json_compatible": True,
        "source_and_bundle_unchanged": True,
    }
    (directory / "compatibility-result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(text, end="")
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--phase", choices=("all", "generate", "validate"), default="all")
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    scratch = (REPOSITORY / ".validation").resolve()
    if directory == scratch or not directory.is_relative_to(scratch):
        parser.error("--directory must name a tool-owned subdirectory of .validation")
    if arguments.phase in {"all", "generate"}:
        generate(directory)
    if arguments.phase in {"all", "validate"}:
        validate(directory)


if __name__ == "__main__":
    main()
