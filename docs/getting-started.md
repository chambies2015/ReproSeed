# Getting started with ReproSeed

For an existing failing pytest test, use the separate [pytest oracle guide](pytest-oracles.md)
and its complete duplicate-export preparation recipe. It requires optional separately
installed pytest and an exact nodeid/exception/message contract. The tutorial below
retains its ordinary dependency-free oracle and synchronized files.

ReproSeed reduces a disposable SQLite fixture while preserving one specified
data-dependent failure. The output is a small database, explicitly selected
application/oracle files, a portable replay configuration and recorded evidence.
Another developer can inspect the bundle and run three new confirmations after
moving it away from your original project.

This walkthrough uses the existing aggregate-threshold example: three crates and
eight parcels, including two parcels of mass 61 and 44 in one crate. The oracle
queries their combined mass; it reports the target only when a crate exceeds 100.
The measured result is 11 rows → 3, retaining that crate and those two parcels.
It is a synthetic invariant violation, not an unconditional crash script.

## Prerequisites and scope

Use Python 3.12 or newer with its `sqlite3` module linked to SQLite 3.37 or newer.
The SQLite library inside Python matters; a separate `sqlite3` command is unnecessary.
The example has no external dependencies. ReproSeed itself has only standard-library
runtime dependencies. For your own application, install any required executables or
libraries in the execution environment yourself; the bundle is not a container.

Supported tables have declared exact INTEGER or TEXT primary keys, or exactly two
ascending INTEGER/TEXT primary-key components. TEXT comparisons must use BINARY.
Supported ordinary/STRICT and WITHOUT ROWID layouts can be mixed, with foreign keys
targeting each parent's complete primary key in order. There are additional metadata
and storage checks. Missing/wider primary keys, unsupported collations, triggers,
virtual tables and generated columns are rejected. Read the
[complete supported subset](architecture.md#supported-schema) before preparing your
own fixture; do not rewrite an unsupported schema and assume it preserves your bug.

Use synthetic or disposable local data. Reduction keeps retained values and source
code; it does not anonymize them. Read [SECURITY.md](../SECURITY.md) before executing
or sharing a bundle. `--allow-exec` acknowledges execution with your OS permissions
and inherited environment. Disposable copies are not an OS sandbox.

## Obtain and install a local wheel

Obtain `reproseed-0.1.0-py3-none-any.whl` from a trusted local build. A maintainer can
build it using [the contributing workflow](../CONTRIBUTING.md). Keep the concrete
wheel outside the tutorial project. There is no verified public package-index
installation in this milestone; these instructions install that local file, not a
future `pip install reproseed` release. No network is needed after the wheel is built.

Create a fresh directory and environment outside the source checkout. The following
commands deliberately use a path with a space and Unicode. If you already have that
tutorial directory, choose another new name; do not overwrite an earlier experiment.
The environment need not be activated: use its interpreter and console script directly.

### Windows PowerShell

Replace the wheel path with the file you obtained. `py -3.12` selects Python 3.12;
an explicit path to another supported interpreter also works. If the launcher says
"No suitable Python runtime found", it may not know about a separately managed
Python. Replace `py -3.12` with `& 'C:\path\to\python.exe'` using your supported
interpreter's real path; the virtual environment and pip steps remain the same.

```powershell
$ErrorActionPreference = 'Stop'
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
$Wheel = 'C:\Downloads\reproseed-0.1.0-py3-none-any.whl'
$TutorialRoot = Join-Path $env:TEMP 'ReproSeed tutorial café'
New-Item -ItemType Directory -Path $TutorialRoot
py -3.12 -m venv (Join-Path $TutorialRoot 'venv')
$Python = Join-Path $TutorialRoot 'venv\Scripts\python.exe'
$ReproSeed = Join-Path $TutorialRoot 'venv\Scripts\reproseed.exe'
& $Python -m pip install --no-index --no-deps $Wheel
& $Python -c "import sys, sqlite3, reproseed; print(sys.version); print('SQLite', sqlite3.sqlite_version); print(reproseed.__file__)"
& $ReproSeed --version
& $ReproSeed --help
New-Item -ItemType Directory -Path (Join-Path $TutorialRoot 'project')
Set-Location (Join-Path $TutorialRoot 'project')
```

Check each native command's exit code (`$LASTEXITCODE`); PowerShell's
`$ErrorActionPreference` alone does not stop every native command on failure.
The printed import path must be under this new environment's `Lib\site-packages`,
not `src\reproseed` in a checkout. A newly created `venv` includes pip by default.

### Linux POSIX shell

Replace the wheel path. Use a supported interpreter with `venv`/`ensurepip` available;
some Linux distributions provide them in a separate Python venv package.

```sh
set -eu
unset PYTHONPATH PYTHONHOME
Wheel='/home/me/Downloads/reproseed-0.1.0-py3-none-any.whl'
TutorialRoot=$(mktemp -d "${TMPDIR:-/tmp}/ReproSeed tutorial café.XXXXXX")
python3.12 -m venv "$TutorialRoot/venv"
Python="$TutorialRoot/venv/bin/python"
ReproSeed="$TutorialRoot/venv/bin/reproseed"
"$Python" -m pip install --no-index --no-deps "$Wheel"
"$Python" -c "import sys, sqlite3, reproseed; print(sys.version); print('SQLite', sqlite3.sqlite_version); print(reproseed.__file__)"
"$ReproSeed" --version
"$ReproSeed" --help
mkdir "$TutorialRoot/project"
cd "$TutorialRoot/project"
```

The import path must be in the new environment's `site-packages`. Both recipes remove
`PYTHONPATH`/`PYTHONHOME` from this shell session to avoid an existing source/development
installation changing imports.
The [external-consumer smoke](../tests/external_consumer_smoke.py) removes those variables
and verifies the installed import origin rather than silently falling back to the checkout.

## Create the three complete files

Save the following files in `project` using a text editor, with exactly these filenames
and UTF-8 encoding. The retained executable versions are
[generate.py](../examples/threshold/generate.py),
[oracle.py](../examples/threshold/oracle.py) and
[reproseed.toml](../examples/threshold/reproseed.toml).
[Tutorial regressions](../tests/test_getting_started.py) require these blocks to agree
with those files. There is no source-checkout import in any of them.

### `generate.py`

<!-- tutorial-file: generate.py -->
```python
"""Generate a separate synthetic aggregate-threshold fixture."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def generate(database: Path) -> None:
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite an existing database: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE crates (
                crate_id INTEGER PRIMARY KEY,
                label TEXT NOT NULL
            );
            CREATE TABLE parcels (
                parcel_id INTEGER PRIMARY KEY,
                crate_id INTEGER NOT NULL REFERENCES crates(crate_id),
                mass INTEGER NOT NULL CHECK (mass >= 0)
            );
            PRAGMA user_version = 7;
            """
        )
        connection.executemany(
            "INSERT INTO crates VALUES (?, ?)",
            [
                (-7, "Synthetic light crate A"),
                (12, "Synthetic light crate B"),
                (99, "Synthetic overloaded crate"),
            ],
        )
        connection.executemany(
            "INSERT INTO parcels VALUES (?, ?, ?)",
            [
                (-30, -7, 5),
                (2, -7, 8),
                (9, 12, 11),
                (50, 12, 13),
                (71, 99, 61),
                (400, 99, 44),
                (910, 12, 2),
                (1001, -7, 9),
            ],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "fixture.sqlite3",
        help="New database path; existing files are never overwritten.",
    )
    arguments = parser.parse_args()
    generate(arguments.database)
    print(f"Created {arguments.database}: 3 crates and 8 parcels (11 rows).")


if __name__ == "__main__":
    main()
```

The generator refuses an existing database path. It does not need to be included in
the bundle: replay consumes the reduced fixture, rather than regenerating the original.

### `oracle.py`

<!-- tutorial-file: oracle.py -->
```python
"""Detect a crate whose combined parcel mass exceeds the configured limit."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

MARKER = "REPROSEED_WEIGHT_THRESHOLD"


def check(database: Path) -> int:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        overloaded = connection.execute(
            """
            SELECT crates.crate_id
            FROM crates JOIN parcels ON parcels.crate_id = crates.crate_id
            GROUP BY crates.crate_id
            HAVING SUM(parcels.mass) > 100
            """
        ).fetchone()
    if overloaded is not None:
        print(MARKER)
        return 43
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: oracle.py DATABASE", file=sys.stderr)
        return 2
    try:
        return check(Path(sys.argv[1]))
    except (OSError, sqlite3.Error) as error:
        print(f"Threshold could not be checked: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

A failure oracle is your application's test command. This example checks a precise SQL
condition; for an application bug, invoke the actual application and check its specific
incorrect behavior before printing the marker. Do not catch every exception and translate
it to the target. An unrelated crash must remain distinguishable.

### `reproseed.toml`

<!-- tutorial-file: reproseed.toml -->
```toml
version = 1
source = "fixture.sqlite3"
include = ["oracle.py"]

[oracle]
argv = ["{python}", "oracle.py", "{db}"]
expected_exit = 43
marker = "REPROSEED_WEIGHT_THRESHOLD"
stream = "stdout"
timeout_seconds = 5.0
output_limit_bytes = 65536

[reduction]
max_invocations = 80
```

All fields are required. Paths resolve relative to this configuration, not the shell's
working directory. `include` selects only regular files under that root. Use portable
`/` separators for nested assets; directories, traversal, symlinks and junctions are
rejected. ReproSeed never recursively collects a project. Quote TOML strings normally;
forward slashes avoid backslash escaping when specifying an absolute Windows source path.

`argv` is an argument array, not a shell command. `{python}` and `{db}` must occupy whole
arguments: they become the current interpreter and a fresh disposable database path.
There is no shell expansion, interpolation of arbitrary expressions or automatic
installation of dependencies. Include every needed application file explicitly.

The exact exit code **and** exact whole-line marker on the selected stream must match.
Exit 43 without the marker, a marker on stderr, a different exception, timeout or excessive
output is `UNRESOLVED`. Exit 0 without the marker is `PASS`; only the configured target is
`TARGET_FAILURE`. A substring match is insufficient. This prevents a different crash
from becoming a smaller but irrelevant reproducer.

## Generate, diagnose, reduce and inspect

Long reductions can opt into `--progress` (aggregate lines on stderr) and
`--events run.jsonl` (a new file relative to your current working directory).
Append `--progress --events run.jsonl` to the reduction command below to try both.
Keep the event file outside the bundle and choose a new name for each run; its
parent must already exist. Neither option grants execution permission. Default
output and the tutorial assets remain the same. These optional diagnostics omit
fixture values and keys and can be incomplete; they are not replay artifacts or
a verification ledger. See [the event contract](progress-events.md).

Run these commands in `project`, using the variables from the installation section.
All should exit 0. Static diagnosis confirms structure, assets, integrity and foreign
keys; it executes no oracle and makes no reproduction claim. The acknowledged diagnosis
runs three fresh attempts, all of which must be `TARGET_FAILURE`.

### Windows PowerShell

```powershell
& $Python .\generate.py
& $ReproSeed diagnose --config .\reproseed.toml
& $ReproSeed diagnose --config .\reproseed.toml --format json
& $ReproSeed diagnose --config .\reproseed.toml --allow-exec --format json
& $ReproSeed reduce --config .\reproseed.toml --out .\bundle --allow-exec
& $ReproSeed inspect .\bundle
& $ReproSeed inspect .\bundle --format json
& $ReproSeed inspect .\bundle --format text
```

### Linux POSIX shell

```sh
"$Python" ./generate.py
"$ReproSeed" diagnose --config ./reproseed.toml
"$ReproSeed" diagnose --config ./reproseed.toml --format json
"$ReproSeed" diagnose --config ./reproseed.toml --allow-exec --format json
"$ReproSeed" reduce --config ./reproseed.toml --out ./bundle --allow-exec
"$ReproSeed" inspect ./bundle
"$ReproSeed" inspect ./bundle --format json
"$ReproSeed" inspect ./bundle --format text
```

Reduction independently confirms the baseline three times. Each accepted smaller
candidate needs two fresh confirmations, and the compact exported fixture needs three.
Every invocation gets pristine database/assets; oracle writes cannot contaminate the
next candidate through ReproSeed's supplied paths. The tool opens the source read-only.

The budget of 80 counts actual reduction invocations, including baseline, search and
final verification. Separate diagnosis does not consume that reduction budget. Three
invocations are reserved for final verification. Budget exhaustion can produce a verified
bundle from the best confirmed selection, with the termination reason recorded; it
does not prove minimality. Budgets must be 6–100,000; a budget of 6 allows only baseline
and final confirmation, so no search occurs. Use a new `--out` path for every run.

The reduction's small JSON summary has `verified: true` and original/final table counts.
The text inspection should show 11 original → 3 retained, 1 crate and 2 parcels, plus
three recorded baseline and final target confirmations. Default and explicit JSON
inspection return the same version-1 report shape. Inspection checks hashes, consistency
and fixture validity now; it never executes the oracle. Recorded confirmations are
historical claims. [Diagnostic JSON](diagnostics.md) is independently versioned.

The bundle contains `fixture.sqlite3`, `oracle.py`, `replay.toml`, `report.json`,
`manifest.json` and a generated `README.md`. Retained values, schema/table names, included
code, the marker and configured limits remain visible. External dependencies are not
automatically included.

## Relocate and replay

Copy the completed bundle, rename the original project so its old configuration/source
paths no longer exist, and replay from another working directory. Keep the virtual
environment in `TutorialRoot`; it is independent of the renamed project.

### Windows PowerShell

```powershell
$SharedBundle = Join-Path $TutorialRoot 'shared bundle café'
Copy-Item -LiteralPath .\bundle -Destination $SharedBundle -Recurse
Set-Location $TutorialRoot
Move-Item -LiteralPath (Join-Path $TutorialRoot 'project') -Destination (Join-Path $TutorialRoot 'original project unavailable')
New-Item -ItemType Directory -Path (Join-Path $TutorialRoot 'unrelated cwd')
Set-Location (Join-Path $TutorialRoot 'unrelated cwd')
& $ReproSeed inspect $SharedBundle --format text
& $ReproSeed replay $SharedBundle --allow-exec
```

### Linux POSIX shell

```sh
SharedBundle="$TutorialRoot/shared bundle café"
cp -R ./bundle "$SharedBundle"
cd "$TutorialRoot"
mv ./project './original project unavailable'
mkdir './unrelated cwd'
cd './unrelated cwd'
"$ReproSeed" inspect "$SharedBundle" --format text
"$ReproSeed" replay "$SharedBundle" --allow-exec
```

Successful replay exits 0 and prints `outcome: TARGET_FAILURE` with exactly three new
`TARGET_FAILURE` confirmations. These executions use one verified private payload and
three fresh disposable copies; they do not use the original project or modify the
supplied bundle through tool operations. Replaying again produces new observations.
The [consumer regression recipe](../tests/external_consumer_smoke.py) checks source,
asset and supplied-bundle byte hashes across this entire lifecycle, including relocation.

## Troubleshooting and recovery

The CLI exit differs from the oracle's exit 43: 0 is successful verification/inspection
or static checks; 1 is a baseline/final/replay target that was not established; 2 is an
input, usage, schema, filesystem or bundle error; 130 is interrupted verification.
The oracle's `PASS` means the failure did not occur, so a PASS baseline/replay is not
a successful reproduction.

| Symptom | Meaning and next step |
| --- | --- |
| Missing config, source or included file | Check the filename and config-relative paths. Save the full files and generate the fixture first. Static diagnosis can check these before executing. |
| Malformed TOML or invalid budget | Use the complete version-1 example; unknown fields/types are rejected. Keep finite limits and a budget of at least 6. |
| Permission denied | Use a readable disposable input and a writable new output location. ReproSeed does not need administrator/root access; avoid widening permissions on unrelated data. |
| Unsupported schema | Check the exact supported subset. SQLite supporting a declaration does not mean ReproSeed supports it. No oracle should launch after structural rejection. |
| Broken foreign keys | Repair the synthetic/disposable fixture using application knowledge, then diagnose again. Do not disable checks to force acceptance. |
| Baseline includes PASS | The target is absent or inconsistent. Run the application's own test on the fixture and establish the intended condition before reducing. Three target results are required, with no majority vote. |
| Unexpected exit, missing marker or wrong stream | Confirm the exact nonzero exit and one exact marker line on stdout. Do not broaden the marker to make an unrelated crash pass. |
| Launch error or missing replay dependency | Check the configured executable and environment. Explicitly included files travel in the bundle; arbitrary executables/libraries do not. Install trusted dependencies separately and repeat diagnosis/replay. |
| Timeout or output limit | The result is UNRESOLVED. Fix a hanging/noisy test, or deliberately adjust the finite timeout/combined-output limit if needed; a timeout is not the target. |
| Search budget exhausted | Inspect the termination reason and counts. A verified result still has three final confirmations. Use a fresh output and a larger finite budget if more search is worthwhile. |
| Interrupted search | One handled search interruption stops search and attempts final verification of committed progress; a verified bundle may still exit 0 and records interruption. Baseline/finalization or a further interruption may exit 130 without a bundle. |
| Final verification failed | No verified bundle is published. Check instability or behavior affected by compaction; use fresh inputs/output when repeating. |
| Output already exists | Select a new directory. Existing user files are not overwritten. |
| Bundle hash/integrity error or unexpected SQLite sidecar | Obtain a fresh intact bundle from a trusted source. Do not edit manifest hashes to manufacture trust, or delete/merge finalized sidecars as a repair shortcut. |
| Replay differs from the recorded failure | Exit 1 and the new classifications are evidence of the difference. Check trusted external dependencies and environment; matching hashes do not guarantee identical behavior everywhere. |

For invalid inputs, `diagnose --format json` provides curated causes without paths,
argv, marker values, row values or raw process output. Read the stage/cause and
[diagnostic format](diagnostics.md). Table names remain visible. Keep actual failed
observations when reporting a problem; do not describe static readiness as reproduction.

## Before sharing and remaining limits

Review retained database content, included source/configuration files, filenames and
literal strings. Check for credentials and personal data, state required external
dependencies, and make sure the recipient understands execution permissions. See the
practical [pre-sharing checklist](../SECURITY.md#before-sharing-a-bundle).
Inspect never executes bundled code. Run unfamiliar code only with external isolation
that you configure; hashes match a manifest but do not authenticate its author.

ReproSeed preserves supported declared schema/retained values, not a complete execution
environment. Ordinary TEXT/composite tables' hidden rowids may change during compaction;
WITHOUT ROWID tables have none. There is no global-minimality proof, automatic redaction,
secure erasure of temporary data or claim of semantic equivalence beyond your oracle.
Process cleanup is bounded with documented Windows/POSIX limitations in SECURITY.md.

The tested journey is a developer-run simulation, not an independent outside-user study.
See [alpha readiness](alpha-readiness.md) and [M2d completion evidence](m2d-completion.md)
for the actual platforms, commands, package checks, limitations and outstanding gates.
