# ReproSeed

Smaller fixture. Same specified failure. Independently replayable evidence.

ReproSeed is an M2c prototype of a local Python CLI. It reduces a disposable SQLite
fixture to a relationally valid row subset while reconfirming the explicit exit/marker
contract supplied by the user. It exports a compact fixture, replay assets and evidence.
It does not infer semantic crash equivalence. Reduction is not anonymization, and the
result is not proven globally minimal.

## Quickstart

With [uv](https://docs.astral.sh/uv/) installed, run from this checkout:

```
uv sync --locked --python 3.12
uv run python examples/duplicate_export/generate.py
uv run reproseed diagnose --config examples/duplicate_export/reproseed.toml
uv run reproseed diagnose --config examples/duplicate_export/reproseed.toml --allow-exec
uv run reproseed reduce --config examples/duplicate_export/reproseed.toml --out ./repro-bundle --allow-exec
uv run reproseed inspect ./repro-bundle
uv run reproseed inspect ./repro-bundle --format text
uv run reproseed replay ./repro-bundle --allow-exec
```

The deterministic example has 2,430 user rows. A deliberately buggy exporter keys entries
by name globally, losing one of two same-name entries in different projects. The separate
oracle exercises the exporter and verifies that particular omission before emitting its
marker. The intended essential case has one owner, two projects and two entries. An
independent numeric-threshold example lives in examples/threshold/. More demanding examples
exercise [inventory reservations](examples/reservation_overbook/README.md) and
[cyclic approvals](examples/approval_cycle/README.md).
The [text-key entitlement example](examples/text_key_entitlements/README.md) exercises
a separate tenant-scoping defect with mixed INTEGER/TEXT keys and several FK levels.
The [composite billing example](examples/composite_billing/README.md) uses two-column
invoice/account keys and detects an invoice falsely marked paid when refunds are added
to settled payments. Its full fixture has 1,308 rows; `generate.py --small` retains the
same application defect in eight rows for installed-wheel validation.
Its explicit `--without-rowid` generator mode uses the same data and oracle with five
WITHOUT ROWID tables and an ordinary INTEGER-keyed payments table.

Choose a new output directory for every reduction. Copy/move the completed bundle elsewhere
and replay using the installed CLI; original fixture and example files are unnecessary.
Only Python and ReproSeed are needed for these demos. Arbitrary applications may require
external executables/dependencies, which ReproSeed does not package automatically.

For your own application, prepare a disposable SQLite fixture and write an oracle that
exercises the actual defect, emitting one exact marker and the configured exit only for
that specific failure. List its supporting files explicitly in version-1 configuration.
Run static diagnosis, then acknowledge execution to confirm the baseline. Reduce into a
new directory and inspect the result. Review retained data and included code before sharing
the bundle; the recipient reconfirms with `replay --allow-exec` using the installed CLI.

## Diagnosing a fixture

```
uv run reproseed diagnose --config examples/threshold/reproseed.toml
uv run reproseed diagnose --config examples/threshold/reproseed.toml --format json
uv run reproseed diagnose --config examples/threshold/reproseed.toml --allow-exec
uv run reproseed diagnose --config examples/threshold/reproseed.toml --allow-exec --format json
```

Generate the example first with `uv run python examples/threshold/generate.py`.
The default text output checks configuration, explicit assets, a private consistent SQLite
snapshot, the reducer's supported schema subset, integrity and foreign keys. It gives actual
per-table counts and the oracle contract/limits. Without `--allow-exec`, no application or
oracle launches. Static exit 0 means structural readiness; it does not confirm a failure.

With `--allow-exec`, diagnosis runs three fresh baseline attempts, unless an interruption
or hard nonlaunch blocks completion. Every completed classification is shown, including
PASS and UNRESOLVED. All three must be TARGET_FAILURE; a matching exit alone is insufficient.
Each attempt gets pristine database and supporting-file copies. Diagnosis produces no bundle
and writes no evidence beside the source. It omits argv, marker values, paths, raw process
output, rows and environment data from its output. Readiness does not guarantee that a later
reduction or final verification will succeed. See the [diagnostic format](docs/diagnostics.md).

Diagnostic exits: 0 static checks passed or requested baseline confirmed; 1 executed-mode
baseline not established; 2 invalid configuration/schema/input; 130 interrupted.

## Inspecting a bundle

`reproseed inspect ./bundle` and `reproseed inspect ./bundle --format json` return the
existing version-1 JSON report. `--format text` selects a compact summary of table counts,
reduction, recorded confirmations, executions, cache hits, budget and search termination.
Neither inspection format needs `--allow-exec` or runs application/oracle code.

Inspection acquires one private copy of the declared payload, checks its hashes and recorded
evidence, and checks SQLite structure, foreign keys and final table counts on another private
database copy. These are checks performed now. Historical confirmation records are claims
whose structure and consistency are checked; inspecting them does not reproduce the target.
Only a new `replay --allow-exec` runs three fresh confirmations of the copied payload.

Actual text inspection of the synthetic threshold bundle generated by the reviewed pre-M1b
implementation, with this reader:

```text
ReproSeed bundle format 1 / report format 1
Recorded tool: reproseed 0.1.0
Recorded runtime: Python 3.12.15; SQLite 3.53.1
Artifact integrity: checked now (SHA256; 5 declared files)
Recorded evidence: structure and consistency checked now
Fixture structure/counts: checked now
Rows: 11 original -> 3 retained (72.7% removed)
Tables (original -> retained):
  "crates": 3 -> 1
  "parcels": 8 -> 2
Recorded oracle executions: 18
Budget charged: 18/80 (0 unknown interrupted launches)
Cache hits: 5 (reused evidence; no new executions)
Search: 3 accepted reductions; 0 unresolved trials; 0 invalid candidates
Recorded baseline confirmations: 3/3 TARGET_FAILURE
Recorded final confirmations: 3/3 TARGET_FAILURE
Search termination: Single-row deletion closures exhausted; unresolved trials may remain.
New replay: not performed by inspect (oracle not executed)
Hashes and consistent recorded evidence do not authenticate historical executions.
Reduction is not anonymization or proof of global minimality.
```

Finalized bundles must not have `fixture.sqlite3-wal`, `fixture.sqlite3-shm` or
`fixture.sqlite3-journal` beside their fixture, including empty sidecars. Such bundles are
rejected without deleting or incorporating those files. A normal reduction source can use
committed WAL; its read-only snapshot contract remains separate.

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

A handled first interruption during search stops further reduction and preserves coherent
confirmed progress. ReproSeed then compacts that selection and requires three fresh target
confirmations of the exact exported fixture before publishing. The report records interrupted
search; this can still exit successfully. Interruption before baseline verification, during
finalization or final verification, or again during graceful finalization may abort with exit
130 and no verified bundle. A second interruption during invocation-accounting recovery
aborts with exit 130. Existing outputs and supplied files are preserved.

## Support and limits

SQLite >=3.37; ordinary and STRICT rowid tables with one exact INTEGER PRIMARY KEY alias,
one exact declared TEXT/BINARY primary key, or exactly two ascending declared PRIMARY KEY
columns. WITHOUT ROWID tables support one exact INTEGER or TEXT component and the same
four two-component combinations: INTEGER+INTEGER, INTEGER+TEXT, TEXT+INTEGER and TEXT+TEXT.
Every WITHOUT ROWID PK component must be ascending in its declared PK index. Mixed storage
layouts and supported STRICT combinations share the same lifecycle. Type-name case and
surrounding whitespace are ignored. Every parent PK component must be non-NULL and stored
as its declared SQLite integer/text family; text must decode safely to Python str. Nullable
ordinary non-STRICT PK declarations are accepted only when every actual component is valid.
Empty tables still undergo metadata checks. TEXT comparisons require BINARY on both the
PK index and the column's default collation.

WITHOUT ROWID tables have no hidden rowid. Their INTEGER PRIMARY KEY is a declared integer
key rather than a rowid alias; ReproSeed validates its declared PK index. SQLite requires
a PK and enforces NOT NULL on every component, and rejects AUTOINCREMENT. Inserts do not
update `last_insert_rowid()`, rowid-based incremental BLOB I/O does not apply, and update
hooks do not report their changes. ReproSeed does not rely on those behaviors. See
[SQLite's WITHOUT ROWID differences](https://www.sqlite.org/withoutrowid.html#differences_from_ordinary_rowid_tables).

Scalar and two-column FKs must reference the full supported parent PK, either implicitly
or with explicit columns in PK order. The parent's component families select child-column
policy independently of the child's own PK: INTEGER parents require integer-affinity
declarations and integer/null storage; TEXT parents require exact TEXT declarations and
text/null storage. Composite FKs form one complete tuple edge. If any child component is
NULL, no parent is required and no edge is invented. Mixed tables, multiple FKs, cycles,
self-references, negative/sparse integers, empty strings, Unicode, quoted identifiers and
ordinary INTEGER rowid-alias AUTOINCREMENT remain supported. SQLite applies parent affinity/collation to FK
comparisons; ReproSeed rejects cross-affinity declarations instead of coercing keys. See
[the architecture](docs/architecture.md) and [SQLite FK rules](https://www.sqlite.org/foreignkeys.html).

Three-or-more-column or missing PKs, PK types other than exact INTEGER/TEXT,
descending composite or WITHOUT ROWID PK components, non-alias scalar INTEGER PKs in
ordinary rowid tables, NULL/wrong-storage parent keys, VARCHAR/CHAR TEXT keys/references,
NOCASE/RTRIM/custom TEXT collations, reordered or
non-PK UNIQUE FK targets, mismatched FK cardinality, virtual/shadow tables,
triggers and generated/hidden columns fail explicitly. This is a bounded schema subset.

The tool opens source read-only and uses SQLite backup, including committed WAL, without
checkpointing or source writes. Use a disposable local fixture; live production databases
are outside the workflow. Removal closes over dependent children recursively and never
uses ON DELETE actions to rewrite retained values. Every candidate gets integrity/FK checks.
Final VACUUM INTO removes unused pages; retained content may still be sensitive. It can
change hidden rowids in ordinary TEXT-keyed and composite-keyed tables. WITHOUT ROWID
tables use their declared PK as storage identity and have no hidden rowid to preserve.
ReproSeed preserves retained declared column values and keys; three final confirmations of the compact fixture
remain the authority for whether the configured failure reproduces.

--allow-exec acknowledges that configured code runs with your OS permissions and inherited
environment. Temporary directories are not a sandbox. Read [SECURITY.md](SECURITY.md) before
executing/sharing bundles. Hashes detect edits relative to a manifest, not malicious authors.
Replay uses the verified private payload for all three fresh database and asset copies.
Later changes to the supplied bundle cannot redirect these confirmations to different bytes.
This does not authenticate the manifest or provide complete hostile-filesystem race immunity.
Windows Job Object assignment has startup/host-policy limitations; POSIX detached children
can escape process-group cleanup. Deadlines and bounded cleanup prevent indefinite pipe waits.

CLI exits: 0 verified success/inspection/static diagnosis, 1 failure not confirmed, 2 usage/config/schema/bundle
error, 130 interrupted before verification completed. The oracle's expected exit is separate.
inspect never executes the oracle. Reports contain bounded classification metadata, not row
values or raw output. No original database or candidate history is exported. A consistent
report and matching hashes do not authenticate its author or prove its historical executions.

## Development and troubleshooting

```
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run pytest --basetemp=.validation/pytest
uv build --no-sources
```

If baseline fails, check marker stream, exact line, exit code and dependencies first. A timeout
or noisy command is unresolved; adjust explicit finite bounds when appropriate. Schema
rejections identify the unsupported shape. Existing outputs are never overwritten. Hash
mismatches require a fresh trusted bundle; editing manifest hashes does not establish trust.
See [CONTRIBUTING.md](CONTRIBUTING.md), [architecture](docs/architecture.md),
[roadmap](docs/roadmap.md), [historical completion evidence](docs/m0-m1a-completion.md)
and [M1b.1 evidence](docs/m1b1-completion.md).
The [M1b.1.1 cancellation repair evidence](docs/m1b1-1-completion.md) distinguishes injected
boundary tests from platform-specific real-signal tests and records their limits.
See [M1b.2 completion evidence](docs/m1b2-completion.md) for its fixtures, diagnostics and
local validation. M1b.2 was accepted at commit `c9cf32ced7f0428385d1daad912d5aa01fec6967` in
[hosted run 38476866662](https://github.com/chambies2015/ReproSeed/actions/runs/38476866662):
Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 all succeeded. Historical
completion reports retain the observations available when they were written.
See [M2a completion evidence](docs/m2a-completion.md) and
[M2a.1 repair evidence](docs/m2a1-completion.md) for their historical local results and limits.
M2a.1 was accepted at commit `d60c79c07ae12666af9572ced69edc3b9523ce17` in
[hosted run 38572680512](https://github.com/chambies2015/ReproSeed/actions/runs/38572680512):
Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 all passed.
[M2b completion evidence](docs/m2b-completion.md) records its historical local checks.
M2b was accepted at commit `d70edac43c22efe3df643b821af1c51ec756a945` in
[hosted run 38592071692](https://github.com/chambies2015/ReproSeed/actions/runs/38592071692):
Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 all passed.
[M2c completion evidence](docs/m2c-completion.md) records actual local validation and its
limits; hosted M2c acceptance requires Dan's subsequent review, commit and push.
Historical reports remain unchanged. A separate public-alpha readiness and usability review
is proposed after M2c. PostgreSQL and package publication are outside this milestone.
