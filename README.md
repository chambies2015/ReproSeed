# ReproSeed

Smaller fixture. Same specified failure. Independently replayable evidence.

ReproSeed is an M0/M1a prototype of a local Python CLI. It reduces a disposable SQLite
fixture to a relationally valid row subset while reconfirming the explicit exit/marker
contract supplied by the user. It exports a compact fixture, replay assets and evidence.
It does not infer semantic crash equivalence. Reduction is not anonymization, and the
result is not proven globally minimal.

## Quickstart

With [uv](https://docs.astral.sh/uv/) installed, run from this checkout:

```
uv sync --locked --python 3.12
uv run python examples/duplicate_export/generate.py
uv run reproseed reduce --config examples/duplicate_export/reproseed.toml --out ./repro-bundle --allow-exec
uv run reproseed inspect ./repro-bundle
uv run reproseed replay ./repro-bundle --allow-exec
```

The deterministic example has 2,430 user rows. A deliberately buggy exporter keys entries
by name globally, losing one of two same-name entries in different projects. The separate
oracle exercises the exporter and verifies that particular omission before emitting its
marker. The intended essential case has one owner, two projects and two entries. An
independent numeric-threshold example lives in examples/threshold/.

Choose a new output directory for every reduction. Copy/move the completed bundle elsewhere
and replay using the installed CLI; original fixture and example files are unnecessary.
Only Python and ReproSeed are needed for these demos. Arbitrary applications may require
external executables/dependencies, which ReproSeed does not package automatically.

## Configuration

All fields below are required. Unknown/malformed fields are rejected before execution.
Source and supporting file paths resolve relative to the configuration file, not your cwd.

```toml
version = 1
source = "fixture.sqlite3"
include = ["app.py", "oracle.py"]

[oracle]
argv = ["{python}", "oracle.py", "{db}"]
expected_exit = 42
marker = "REPROSEED_DUPLICATE_EXPORT"
stream = "stdout"
timeout_seconds = 5.0
output_limit_bytes = 65536

[reduction]
max_invocations = 400
```

argv is an argument array, never a shell string. {python} and {db} must occupy whole
arguments; they resolve to ReproSeed's interpreter and the invocation's disposable database.
Other formatting expressions are rejected. Relative scripts run from a fresh staged cwd.
Include explicitly named regular files under the configuration root, using portable `/`
separators; no traversal, symlinks/junctions, directory collection or implicit repository copy.
Source may be an absolute path or a path relative to the configuration. Expected exits are
1–255, timeouts 0.01–3600 seconds, combined output limits 1–16,777,216 bytes and invocation
budgets 6–100,000. The marker must be a nonempty exact single UTF-8 line (up to 4096 bytes).

TARGET_FAILURE requires the expected normal nonzero exit and exact whole-line marker on
the configured stream. PASS is zero without that marker. Every other outcome is UNRESOLVED,
including a different crash, timeout or contradictory output. Baseline and compact final
artifact require three fresh confirmations each; a reduced candidate requires two. Final
verification is reserved within the budget and never uses search caches.

## Support and limits

SQLite >=3.37; ordinary rowid tables with one exact INTEGER PRIMARY KEY alias; single
integer-affinity FK columns referencing those PKs with actual integer/null stored values.
Sparse/negative IDs, nullable references, cycles, self-references, unrelated/empty tables,
quoted identifiers, STRICT and AUTOINCREMENT are supported. Composite/missing PKs,
non-alias descending PKs, unsupported FK targets/types, WITHOUT ROWID, virtual tables,
triggers and generated columns fail explicitly. See docs/architecture.md for exact semantics.

The tool opens source read-only and uses SQLite backup, including committed WAL, without
checkpointing or source writes. Use a disposable local fixture; live production databases
are outside the workflow. Removal closes over dependent children recursively and never
uses ON DELETE actions to rewrite retained values. Every candidate gets integrity/FK checks.
Final VACUUM INTO removes unused pages; retained content may still be sensitive.

--allow-exec acknowledges that configured code runs with your OS permissions and inherited
environment. Temporary directories are not a sandbox. Read [SECURITY.md](SECURITY.md) before
executing/sharing bundles. Hashes detect edits relative to a manifest, not malicious authors.
Windows Job Object assignment has startup/host-policy limitations; POSIX detached children
can escape process-group cleanup. Deadlines and bounded cleanup prevent indefinite pipe waits.

CLI exits: 0 verified success/inspection, 1 failure not confirmed, 2 usage/config/schema/bundle
error, 130 interrupted before verification completed. The oracle's expected exit is separate.
inspect never executes the oracle. Reports contain bounded classification metadata, not row
values or raw output. No original database or candidate history is exported.

## Development and troubleshooting

```
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --basetemp=.validation/pytest
uv build --no-sources
```

If baseline fails, check marker stream, exact line, exit code and dependencies first. A timeout
or noisy command is unresolved; adjust explicit finite bounds when appropriate. Schema
rejections identify the unsupported shape. Existing outputs are never overwritten. Hash
mismatches require a fresh trusted bundle; editing manifest hashes does not establish trust.
See [CONTRIBUTING.md](CONTRIBUTING.md), [architecture](docs/architecture.md),
[roadmap](docs/roadmap.md) and [completion evidence](docs/m0-m1a-completion.md).
