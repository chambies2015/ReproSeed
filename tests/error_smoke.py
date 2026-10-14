"""Bounded installed-CLI mistake and sharing audit using only synthetic owned files.

Run with --python, --cli and a fresh external --directory. No ReproSeed imports occur.
The caller supplies an already installed wheel and may retain the returned JSON evidence;
the temporary audit tree is removed even on failure. This is a simulated user audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from windows_permissions import denied_directory_acl, probe_directory_creation

PRIVATE = "PRIVATE_SYNTHETIC_VALUE_6be52"
MARKER = "PRIVATE_SYNTHETIC_MARKER_6be52"
ORACLE = """import sqlite3, sys, time
from pathlib import Path
database, mode, ledger, dependency = sys.argv[1:]
ledger = Path(ledger)
count = int(ledger.read_text()) + 1 if ledger.exists() else 1
ledger.write_text(str(count))
print("PRIVATE_SYNTHETIC_VALUE_6be52")
with sqlite3.connect(database) as db:
    total = db.execute("SELECT coalesce(sum(quantity), 0) FROM items").fetchone()[0]
if mode == "timeout":
    time.sleep(10)
elif mode == "output":
    sys.stdout.write("PRIVATE_SYNTHETIC_VALUE_6be52" * 1000)
elif mode == "crash":
    raise RuntimeError("PRIVATE_SYNTHETIC_VALUE_6be52")
elif mode == "inconsistent":
    if count == 2:
        raise SystemExit(0)
    if count == 3:
        raise SystemExit(9)
elif mode == "final_failure" and count > 3:
    raise SystemExit(0)
elif mode == "dependency" and not Path(dependency).exists():
    raise SystemExit(9)
if total > 20:
    marker = "WRONG_MARKER" if mode == "mismatch" else "PRIVATE_SYNTHETIC_MARKER_6be52"
    print(marker, file=sys.stderr if mode == "wrong_stream" else sys.stdout)
    raise SystemExit(43 if mode == "wrong_exit" else 42)
"""


def hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def probe_input_read(python: Path, path: Path, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    """Observe the installed interpreter's byte-read result without exposing data."""
    program = """
import errno, json, sys
from pathlib import Path
try:
    with Path(sys.argv[1]).open('rb') as selected:
        selected.read(1)
except OSError as exc:
    denied = (isinstance(exc, PermissionError) and exc.errno == errno.EACCES
              and getattr(exc, 'winerror', None) in (None, 5))
    print(json.dumps({'decision': 'denied' if denied else 'unexpected_error',
                      'errno': exc.errno, 'winerror': getattr(exc, 'winerror', None),
                      'permission_error': isinstance(exc, PermissionError)}))
else:
    print(json.dumps({'decision': 'allowed', 'errno': None, 'winerror': None}))
"""
    try:
        result = subprocess.run(
            [str(python), "-c", program, str(path)],
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("input capability probe timed out") from None
    except OSError as exc:
        raise RuntimeError(f"input capability probe failed (errno={exc.errno})") from None
    if result.returncode != 0 or result.stderr:
        raise RuntimeError(f"input capability probe failed (exit={result.returncode})")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("decision") not in {
        "denied",
        "allowed",
        "unexpected_error",
    }:
        raise RuntimeError("invalid input capability probe result")
    value["exit"] = result.returncode
    return value


class Audit:
    def __init__(self, python: Path, cli: Path, directory: Path) -> None:
        self.python = python
        self.cli = cli
        self.root = directory
        self.env = dict(os.environ)
        self.env.pop("PYTHONPATH", None)
        self.env.pop("PYTHONHOME", None)
        self.env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        self.records: list[dict[str, Any]] = []
        self.skips: list[dict[str, str]] = []
        self.permission_observations: list[dict[str, Any]] = []
        self.cwd = self.root / "unrelated cwd Î© & spaces"
        self.cwd.mkdir()

    def run(
        self,
        name: str,
        args: list[str],
        expected: int,
        *,
        watch: tuple[Path, ...] = (),
        recovery: str,
    ) -> dict[str, Any] | None:
        before = [hashes(path) for path in watch]
        starts_before = sum(int(path.read_text()) for path in self.root.glob("*-launches.txt"))
        command = [str(self.cli), *args]
        process = subprocess.run(
            command,
            cwd=self.cwd,
            env=self.env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert process.returncode == expected, (
            name,
            process.returncode,
            process.stdout,
            process.stderr,
        )
        assert PRIVATE not in process.stdout + process.stderr, name
        assert MARKER not in process.stdout + process.stderr, name
        assert "\x1b" not in process.stdout + process.stderr, name
        assert [hashes(path) for path in watch] == before, f"{name}: input/bundle changed"
        observed_starts = (
            sum(int(path.read_text()) for path in self.root.glob("*-launches.txt")) - starts_before
        )
        self.records.append(
            {
                "case": name,
                "command": command,
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "watched_files_unchanged": True,
                "watched_roots": [str(path) for path in watch],
                "observed_oracle_starts": observed_starts,
                "private_literals_absent": True,
                "recovery": recovery,
            }
        )
        return json.loads(process.stdout) if process.stdout.startswith("{") else None

    def case(self, name: str, *, mode: str = "target", budget: int = 6) -> tuple[Path, Path]:
        project = self.root / name
        project.mkdir()
        source = project / "PRIVATE_source.sqlite3"
        with closing(sqlite3.connect(source)) as database, database:
            database.executescript("CREATE TABLE items(id INTEGER PRIMARY KEY, quantity INTEGER);")
            database.executemany(
                "INSERT INTO items VALUES(?, ?)", enumerate([9, 10, 11, *([-1] * 8)], 1)
            )
        (project / "oracle.py").write_text(ORACLE, encoding="utf-8")
        ledger = self.root / (name + "-launches.txt")
        dependency = self.root / "external synthetic dependency.txt"
        argv = ["{python}", "oracle.py", "{db}", mode, str(ledger), str(dependency)]
        config = project / "case.toml"
        config.write_text(
            'version=1\nsource="PRIVATE_source.sqlite3"\ninclude=["oracle.py"]\n'
            f"[oracle]\nargv={json.dumps(argv, ensure_ascii=False)}\nexpected_exit=42\n"
            f'marker="{MARKER}"\nstream="stdout"\n'
            f"timeout_seconds={1.0 if mode == 'timeout' else 3.0}\n"
            f"output_limit_bytes=4096\n[reduction]\nmax_invocations={budget}\n",
            encoding="utf-8",
        )
        return config, ledger

    @staticmethod
    def launches(ledger: Path) -> int:
        return int(ledger.read_text()) if ledger.exists() else 0

    def diagnosis(self, name: str, config: Path, expected: int) -> dict[str, Any]:
        result = self.run(
            name,
            ["diagnose", "--config", str(config), "--allow-exec", "--format", "json"],
            expected,
            watch=(config.parent,),
            recovery=(
                "Correct the reported input, contract, dependency or execution "
                "limit; rerun diagnosis."
            ),
        )
        assert result is not None and result["diagnostic_version"] == 1, name
        assert str(config.parent) not in json.dumps(result), name
        return result

    def execute(self) -> dict[str, Any]:
        invalid = {
            "missing_config": "configuration_unavailable",
            "malformed_toml": "malformed_configuration",
            "missing_source": "source_unavailable",
            "missing_asset": "asset_unavailable",
            "unsupported_schema": "unsupported_primary_key",
            "broken_foreign_keys": "foreign_key_violation",
            "invalid_budget": "invalid_execution_limit",
            "asset_traversal": "unsafe_asset_path",
            "asset_directory": "asset_unavailable",
        }
        for name, reason in invalid.items():
            config, ledger = self.case(name)
            if name == "missing_config":
                config.unlink()
            elif name == "malformed_toml":
                config.write_text('version = "unterminated', encoding="utf-8")
            elif name == "missing_source":
                (config.parent / "PRIVATE_source.sqlite3").unlink()
            elif name == "missing_asset":
                (config.parent / "oracle.py").unlink()
            elif name == "unsupported_schema":
                with closing(sqlite3.connect(config.parent / "PRIVATE_source.sqlite3")) as db, db:
                    db.execute("CREATE TABLE unsupported(id VARCHAR PRIMARY KEY)")
            elif name == "broken_foreign_keys":
                with closing(sqlite3.connect(config.parent / "PRIVATE_source.sqlite3")) as db, db:
                    db.executescript(
                        "CREATE TABLE children(id INTEGER PRIMARY KEY, "
                        "parent INTEGER REFERENCES items(id));"
                        "INSERT INTO children VALUES(1,999);"
                    )
            elif name == "invalid_budget":
                config.write_text(
                    config.read_text().replace("max_invocations=6", "max_invocations=5")
                )
            elif name == "asset_traversal":
                config.write_text(
                    config.read_text().replace('include=["oracle.py"]', 'include=["../oracle.py"]')
                )
            elif name == "asset_directory":
                (config.parent / "assets").mkdir()
                config.write_text(
                    config.read_text().replace('include=["oracle.py"]', 'include=["assets"]')
                )
            diagnosis = self.diagnosis(name, config, 2)
            assert diagnosis["error"]["reason"] == reason, (name, diagnosis)
            assert diagnosis["actual_invocations"] == self.launches(ledger) == 0
            assert diagnosis["oracle_executed"] is False
            assert diagnosis["baseline_results"] == [] and diagnosis["baseline_confirmed"] is False
            self.records[-1]["classification"] = "input_or_structural_rejection"
            self.records[-1]["actual_launches"] = 0
            if name in {"missing_source", "malformed_toml", "missing_config", "unsupported_schema"}:
                self.run(
                    name + "_reduce",
                    [
                        "reduce",
                        "--config",
                        str(config),
                        "--out",
                        str(self.root / (name + "-bundle")),
                        "--allow-exec",
                    ],
                    2,
                    watch=(config.parent,),
                    recovery="Correct input; run static diagnosis before allowing execution.",
                )
                assert "PRIVATE_source" not in self.records[-1]["stderr"]
                assert self.launches(ledger) == 0

        modes = {
            "wrong_exit": (["UNRESOLVED"] * 3, "unexpected_exit"),
            "wrong_stream": (["UNRESOLVED"] * 3, "missing_exact_marker"),
            "mismatch": (["UNRESOLVED"] * 3, "missing_exact_marker"),
            "crash": (["UNRESOLVED"] * 3, "unexpected_exit"),
            "timeout": (["UNRESOLVED"] * 3, "timeout"),
            "output": (["UNRESOLVED"] * 3, "output_limit"),
            "inconsistent": (["TARGET_FAILURE", "PASS", "UNRESOLVED"], None),
            "launch_failure": (["UNRESOLVED"], "launch_error"),
        }
        for mode, (outcomes, reason) in modes.items():
            config, ledger = self.case(mode, mode=mode)
            if mode == "launch_failure":
                config.write_text(
                    config.read_text().replace(
                        '"{python}"', '"reproseed-missing-synthetic-executable"'
                    )
                )
            result = self.diagnosis(mode, config, 1)
            assert [item["outcome"] for item in result["baseline_results"]] == outcomes, mode
            if reason is not None:
                assert all(item["reason_code"] == reason for item in result["baseline_results"]), (
                    mode
                )
            assert result["baseline_confirmed"] is False
            launches = 0 if mode == "launch_failure" else 3
            assert result["actual_invocations"] == self.launches(ledger) == launches
            self.records[-1].update(
                classification="baseline_did_not_reproduce", actual_launches=launches
            )

        config, ledger = self.case("budget six Î© & spaces")
        project = config.parent
        bundle = self.root / "budget bundle Î© & spaces"
        self.run(
            "static_no_execution",
            ["diagnose", "--config", str(config), "--format", "json"],
            0,
            watch=(project,),
            recovery="Static suitability requires executable diagnosis to establish reproduction.",
        )
        assert self.launches(ledger) == 0
        self.run(
            "reduce_requires_acknowledgement",
            ["reduce", "--config", str(config), "--out", str(bundle)],
            2,
            watch=(project,),
            recovery="Review configured code before explicitly adding --allow-exec.",
        )
        assert self.launches(ledger) == 0 and not bundle.exists()
        summary = self.run(
            "exhausted_search_budget",
            ["reduce", "--config", str(config), "--out", str(bundle), "--allow-exec"],
            0,
            watch=(project,),
            recovery=(
                "Budget stopped search; final verification still passed. Increase "
                "budget in a new run for further reduction."
            ),
        )
        assert summary is not None and summary["verified"] is True
        assert (
            summary["termination_reason"] == "oracle_budget_exhausted_reserved_final_verification"
        )
        assert summary["oracle_invocations"] == self.launches(ledger) == 6
        assert summary["original_counts"] == summary["final_counts"] == {"items": 11}
        self.records[-1].update(
            classification="search_budget_exhausted_verified", actual_launches=6
        )
        self.run(
            "existing_output",
            ["reduce", "--config", str(config), "--out", str(bundle), "--allow-exec"],
            2,
            watch=(project, bundle),
            recovery="Choose a new output directory; existing user files are never replaced.",
        )
        assert self.launches(ledger) == 6
        self.run(
            "inspect_never_executes",
            ["inspect", str(bundle)],
            0,
            watch=(bundle,),
            recovery=(
                "Inspection validates recorded evidence and structure; only "
                "replay establishes new outcomes."
            ),
        )
        assert self.launches(ledger) == 6
        self.run(
            "replay_requires_acknowledgement",
            ["replay", str(bundle)],
            2,
            watch=(bundle,),
            recovery=(
                "Review bundle code/data and execution permissions before adding --allow-exec."
            ),
        )
        assert self.launches(ledger) == 6

        tampered = self.root / "tampered bundle"
        shutil.copytree(bundle, tampered)
        with (tampered / "oracle.py").open("a", encoding="utf-8") as asset:
            asset.write("\n# edited\n")
        self.run(
            "tampered_bundle",
            ["replay", str(tampered), "--allow-exec"],
            2,
            watch=(tampered,),
            recovery=(
                "Obtain an intact trusted copy; editing a manifest does not "
                "authenticate its author."
            ),
        )
        assert self.launches(ledger) == 6
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = bundle / ("fixture.sqlite3" + suffix)
            sidecar.touch()
            self.run(
                "finalized_sidecar" + suffix,
                ["inspect", str(bundle)],
                2,
                watch=(bundle,),
                recovery=(
                    "Create a proper finalized bundle; inspection does not remove "
                    "or incorporate sidecars."
                ),
            )
            assert sidecar.exists() and self.launches(ledger) == 6
            sidecar.unlink()

        manifest = tampered / "manifest.json"
        captured = json.loads(manifest.read_text())
        captured["artifacts"]["oracle.py"] = hashlib.sha256(
            (tampered / "oracle.py").read_bytes()
        ).hexdigest()
        manifest.write_text(json.dumps(captured), encoding="utf-8")
        self.run(
            "edited_manifest_can_be_consistent",
            ["inspect", str(tampered)],
            0,
            watch=(tampered,),
            recovery=(
                "Consistent hashes do not authenticate authorship or historical "
                "executions; review before replay."
            ),
        )
        assert self.launches(ledger) == 6
        (tampered / "oracle.py").write_text(
            ORACLE.replace("total > 20", "total > 1000"), encoding="utf-8"
        )
        captured["artifacts"]["oracle.py"] = hashlib.sha256(
            (tampered / "oracle.py").read_bytes()
        ).hexdigest()
        manifest.write_text(json.dumps(captured), encoding="utf-8")
        differing = self.run(
            "replay_differing_outcome",
            ["replay", str(tampered), "--allow-exec"],
            1,
            watch=(tampered,),
            recovery=(
                "Replay observed a different outcome; investigate environment or "
                "oracle differences. Recorded history is not a current "
                "reproduction."
            ),
        )
        assert differing is not None and differing["outcome"] == "PASS"
        assert [item["outcome"] for item in differing["confirmations"]] == ["PASS"] * 3
        assert self.launches(ledger) == 9

        captured["artifacts"]["../outside.txt"] = "0" * 64
        manifest.write_text(json.dumps(captured), encoding="utf-8")
        self.run(
            "manifest_traversal",
            ["inspect", str(tampered)],
            2,
            watch=(tampered,),
            recovery="Reject unsafe bundles and request a newly constructed safe bundle.",
        )
        assert self.launches(ledger) == 9

        dependency = self.root / "external synthetic dependency.txt"
        dependency.write_text("available", encoding="utf-8")
        dependency_config, dependency_ledger = self.case("external_dependency", mode="dependency")
        dependency_bundle = self.root / "external dependency bundle"
        self.run(
            "dependency_bundle_creation",
            [
                "reduce",
                "--config",
                str(dependency_config),
                "--out",
                str(dependency_bundle),
                "--allow-exec",
            ],
            0,
            watch=(dependency_config.parent,),
            recovery=(
                "Supply external dependencies separately; they are not collected automatically."
            ),
        )
        assert self.launches(dependency_ledger) == 6
        dependency.unlink()
        replay = self.run(
            "missing_external_dependency",
            ["replay", str(dependency_bundle), "--allow-exec"],
            1,
            watch=(dependency_bundle,),
            recovery="Install/supply required external dependencies and rerun replay.",
        )
        assert replay is not None and replay["outcome"] == "UNRESOLVED"
        assert len(replay["confirmations"]) == 3
        assert all(item["outcome"] == "UNRESOLVED" for item in replay["confirmations"])
        assert self.launches(dependency_ledger) == 9

        final_config, final_ledger = self.case("final_failure", mode="final_failure")
        failed_bundle = self.root / "must not publish"
        self.run(
            "final_verification_failure",
            ["reduce", "--config", str(final_config), "--out", str(failed_bundle), "--allow-exec"],
            1,
            watch=(final_config.parent,),
            recovery=(
                "No verified bundle was published. Investigate nondeterminism before retrying."
            ),
        )
        assert self.launches(final_ledger) == 6 and not failed_bundle.exists()
        self.permission_cases()
        self.link_cases()
        return {
            "simulated_user_audit": True,
            "platform": sys.platform,
            "python": sys.version,
            "records": self.records,
            "skips": self.skips,
            "permission_observations": self.permission_observations,
        }

    def permission_cases(self) -> None:
        config, ledger = self.case("permissions")
        input_bytes_before = hashes(config.parent)
        output_parent = config.parent if os.name == "nt" else self.root / "denied output"
        if os.name != "nt":
            output_parent.mkdir()
        if os.name == "nt":
            # Explicitly target only this owned parent, restoring it before the
            # second boundary. Inherited ACEs also affect its owned child files.
            input_observation: dict[str, Any] = {"case": "unreadable_input"}
            self.permission_observations.append(input_observation)
            with denied_directory_acl(
                config.parent, permissions="(OI)(CI)(RD)", propagate_children=True
            ) as acl_observation:
                input_observation["acl"] = acl_observation
                input_probe = probe_input_read(self.python, config, self.cwd, self.env)
                input_observation["probe"] = input_probe
                if input_probe["decision"] == "unexpected_error":
                    raise RuntimeError("unexpected input capability probe error")
                if input_probe["decision"] == "allowed":
                    self.skips.append(
                        {
                            "case": "unreadable_input",
                            "reason": (
                                "Input bytes remained readable after the owned directory ACL edit; "
                                "real Windows input-denial integration was unavailable."
                            ),
                        }
                    )
                    input_observation["cli_executed"] = False
                else:
                    started = time.monotonic()
                    result = self.run(
                        "unreadable_input",
                        ["diagnose", "--config", str(config), "--allow-exec", "--format", "json"],
                        2,
                        recovery=(
                            "Restore appropriate input read permissions; choose an accessible path."
                        ),
                    )
                    # Bytes cannot be checked until the inherited read deny has
                    # been restored. Keep that evidence unknown if restoration
                    # or the post-context hash check fails.
                    self.records[-1]["watched_files_unchanged"] = None
                    assert result is not None
                    assert result["error"]["reason"] == "configuration_unavailable"
                    assert result["actual_invocations"] == 0 and result["oracle_executed"] is False
                    assert result["baseline_results"] == []
                    input_observation.update(
                        cli_executed=True,
                        cli_exit=self.records[-1]["exit_code"],
                        cli_elapsed_seconds=time.monotonic() - started,
                    )
                assert self.launches(ledger) == 0
            assert hashes(config.parent) == input_bytes_before
            input_observation.update(
                actual_launches=self.launches(ledger),
                input_files_unchanged=True,
                child_readability_restored=True,
            )
            if input_observation["cli_executed"]:
                self.records[-1]["watched_files_unchanged"] = True
                self.records[-1]["watched_roots"] = [str(config.parent)]

            output_observation: dict[str, Any] = {"case": "unwritable_output"}
            self.permission_observations.append(output_observation)
            with denied_directory_acl(output_parent) as acl_observation:
                output_probe = probe_directory_creation(
                    output_parent, python=str(self.python), cwd=self.cwd, env=self.env
                )
                output_observation["probe"] = output_probe
                output_observation["acl"] = acl_observation
                if output_probe["decision"] == "unexpected_error":
                    raise RuntimeError("unexpected directory capability probe error")
                if output_probe["decision"] == "allowed":
                    self.skips.append(
                        {
                            "case": "unwritable_output",
                            "reason": (
                                "Child-directory creation was allowed after the owned ACL edit; "
                                "real Windows output-denial integration was unavailable."
                            ),
                        }
                    )
                    output_observation["cli_executed"] = False
                else:
                    started = time.monotonic()
                    self.run(
                        "unwritable_output",
                        [
                            "reduce",
                            "--config",
                            str(config),
                            "--out",
                            str(output_parent / "bundle"),
                            "--allow-exec",
                        ],
                        2,
                        watch=(config.parent,),
                        recovery=(
                            "Restore output directory creation permissions; "
                            "choose an accessible path."
                        ),
                    )
                    output_observation.update(
                        cli_executed=True,
                        cli_exit=self.records[-1]["exit_code"],
                        cli_elapsed_seconds=time.monotonic() - started,
                    )
                    assert "file_operation_failed" in self.records[-1]["stderr"]
                    assert "permissions" in self.records[-1]["stderr"]
                    assert self.records[-1]["stdout"] == ""
                assert self.launches(ledger) == 0
                assert hashes(config.parent) == input_bytes_before
                assert not (output_parent / "bundle").exists()
                assert not list(output_parent.glob(".reproseed-build-*"))
                assert not list(output_parent.glob(".reproseed-probe-*"))
            output_observation.update(
                actual_launches=self.launches(ledger),
                input_files_unchanged=hashes(config.parent) == input_bytes_before,
                output_unpublished=not (output_parent / "bundle").exists(),
            )
        else:
            for name, path, probe, arguments in (
                (
                    "unreadable_input",
                    config,
                    "open(sys.argv[1], 'rb')",
                    ["diagnose", "--config", str(config), "--allow-exec", "--format", "json"],
                ),
                (
                    "unwritable_output",
                    output_parent,
                    "Path(sys.argv[1], 'probe').mkdir()",
                    [
                        "reduce",
                        "--config",
                        str(config),
                        "--out",
                        str(output_parent / "bundle"),
                        "--allow-exec",
                    ],
                ),
            ):
                original = path.stat().st_mode
                try:
                    path.chmod(0 if path.is_file() else 0o500)
                    tested = subprocess.run(
                        [
                            str(self.python),
                            "-c",
                            "import sys; from pathlib import Path; " + probe,
                            str(path),
                        ],
                        capture_output=True,
                        timeout=5,
                    )
                    if tested.returncode == 0:
                        self.skips.append(
                            {
                                "case": name,
                                "reason": (
                                    "Current account bypasses mode-bit denial; "
                                    "installed permission rejection not "
                                    "established."
                                ),
                            }
                        )
                    else:
                        self.run(
                            name,
                            arguments,
                            2,
                            recovery=(
                                "Restore input read or output creation "
                                "permissions; choose an accessible path."
                            ),
                        )
                        assert self.launches(ledger) == 0
                finally:
                    path.chmod(original)
                assert hashes(config.parent) == input_bytes_before

    def link_cases(self) -> None:
        config, ledger = self.case("linked_asset")
        linked = config.parent / "linked.py"
        try:
            linked.symlink_to(config.parent / "oracle.py")
        except OSError:
            self.skips.append(
                {
                    "case": "asset_symlink",
                    "reason": "Host does not permit creation of a synthetic symlink.",
                }
            )
        else:
            config.write_text(
                config.read_text().replace('include=["oracle.py"]', 'include=["linked.py"]')
            )
            result = self.diagnosis("asset_symlink", config, 2)
            assert result["error"]["reason"] == "linked_asset" and self.launches(ledger) == 0
        if os.name == "nt":
            config, ledger = self.case("junction_asset")
            target = self.root / "owned junction target"
            target.mkdir()
            sentinel = target / "sentinel.txt"
            sentinel.write_text("tool-owned", encoding="utf-8")
            junction = config.parent / "linked"
            made = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                capture_output=True,
                timeout=5,
            )
            if made.returncode:
                self.skips.append(
                    {
                        "case": "asset_junction",
                        "reason": "Host did not permit creation of the owned junction.",
                    }
                )
            else:
                config.write_text(
                    config.read_text().replace(
                        'include=["oracle.py"]', 'include=["linked/sentinel.txt"]'
                    )
                )
                result = self.diagnosis("asset_junction", config, 2)
                assert result["error"]["reason"] == "linked_asset" and self.launches(ledger) == 0
                assert sentinel.read_text() == "tool-owned"
        else:
            self.skips.append(
                {
                    "case": "asset_junction",
                    "reason": "Windows junctions are not a POSIX filesystem feature.",
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    audit: Audit | None = None
    try:
        # POSIX venv Python is often a symlink; resolving it discards venv selection.
        audit = Audit(args.python.absolute(), args.cli.absolute(), root)
        result = audit.execute()
    except BaseException:
        print(
            json.dumps(
                {
                    "completed": False,
                    "records": [] if audit is None else audit.records,
                    "skips": [] if audit is None else audit.skips,
                    "permission_observations": []
                    if audit is None
                    else audit.permission_observations,
                },
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise
    finally:
        already_failing = sys.exc_info()[0] is not None
        try:
            shutil.rmtree(root)
        except OSError:
            if not already_failing:
                raise
            print(
                "error-smoke: owned-state cleanup also failed; preserving the audit error",
                file=sys.stderr,
            )
    result["owned_temporary_state_removed"] = not root.exists()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
