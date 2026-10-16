# ReproSeed

ReproSeed turns a large data-dependent SQLite failure into a small fixture that another
developer can replay. You supply a command that detects one specific failure. The local
Python CLI removes rows, preserves relational validity, and reconfirms that exact failure
before writing a bundle with the database, explicitly included code and verification evidence.

For example, the synthetic [aggregate threshold application](examples/threshold/README.md)
shrinks from **11 rows to 3**: one crate and the two parcels whose combined mass exceeds
100. The oracle still detects that condition in three fresh final confirmations. The
bundle can be moved elsewhere and replayed without the original database or project paths.
This is a measured example, not a promised reduction ratio for other applications.

## Try it locally

Start with [Getting started](docs/getting-started.md): install a locally built wheel in a
fresh Python virtual environment using `venv` and `pip`, create the complete synthetic
example, diagnose, reduce, inspect and relocate/replay it. The guide has Windows PowerShell
and Linux shell commands; its consumer workflow needs no uv, editable install or network
after obtaining the wheel. No public package-index installation is claimed.

ReproSeed remains a prototype. The [limited-alpha readiness review](docs/alpha-readiness.md)
records a conditional go, pending hosted validation, outside-user feedback and a distribution decision.
It requires Python 3.12+ and SQLite 3.37+, supports a
[bounded SQLite schema subset](docs/architecture.md#supported-schema), and runs configured
code with your OS permissions when you supply `--allow-exec`. Reduction is not
anonymization, global minimality or proof that all crashes are equivalent. External application
dependencies remain your responsibility. Read [the trust boundaries](SECURITY.md) before
executing or sharing a bundle.

The first-use sequence with the installed CLI is:

```console
reproseed diagnose --config reproseed.toml
reproseed diagnose --config reproseed.toml --allow-exec
reproseed reduce --config reproseed.toml --out bundle --allow-exec
reproseed inspect bundle --format text
reproseed replay bundle --allow-exec
```

Choose a new output directory for each reduction. Static diagnosis and inspection execute
no oracle code; executable diagnosis confirms three fresh baseline attempts. Inspection
checks hashes, fixture validity and recorded evidence; a new replay establishes new outcomes.
See [diagnostic output](docs/diagnostics.md), [contributing and validation](CONTRIBUTING.md)
and [the roadmap](docs/roadmap.md).

For a longer reduction, add `--progress` for aggregate status lines on stderr,
or `--events run.jsonl` for a new, separate diagnostic file. Both are opt-in;
stdout keeps the existing JSON summary. Event paths resolve from your working
directory, their parent must exist, and existing files are never replaced. Events
omit rows, keys, table names, paths and oracle output. They can be incomplete and
are not verification evidence or a resume file. See [progress/events](docs/progress-events.md)
and the measured [performance lab](docs/performance.md).

## Example applications

Six independent synthetic applications exercise actual data-dependent behavior:

| Application | Previously measured rows, original → retained | Failure checked |
| --- | --- | --- |
| [Duplicate export](examples/duplicate_export/README.md) | 2,430 → 5 | An exporter loses a same-name entry from a different project |
| [Aggregate threshold](examples/threshold/README.md) | 11 → 3 | A crate's combined parcel mass exceeds 100 |
| [Reservation overbooking](examples/reservation_overbook/README.md) | 4,248 → 9 | Reservations exceed available inventory |
| [Cyclic approvals](examples/approval_cycle/README.md) | 1,626 → 6 | An approval application mishandles a cycle |
| [TEXT entitlements](examples/text_key_entitlements/README.md) | 970 → 10 | Entitlements cross a tenant boundary |
| [Composite billing](examples/composite_billing/README.md) | 1,308 → 8 | Refunds are incorrectly added to settled payments |

The same billing application has a seventh execution scenario with five WITHOUT ROWID
tables and one ordinary INTEGER-keyed payments table; its previous measurement is also
1,308 → 8. These are measurements of deterministic fixtures, not hardcoded reducer targets.
The small TEXT and billing generators retain the real decisions for fast installed-wheel
checks. The demos need only Python and installed ReproSeed.

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
[M2c completion evidence](docs/m2c-completion.md) records historical local validation and its
limits. M2c was accepted at commit `dd3db90eee65ed10e158cdcc9ef16b8a677e9852` in
[hosted run 38599450878](https://github.com/chambies2015/ReproSeed/actions/runs/38599450878):
Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 all passed.
[M2d completion evidence](docs/m2d-completion.md) records the simulated consumer journey and
[limited-alpha readiness decision](docs/alpha-readiness.md). Hosted validation of M2d remains
pending Dan's review, commit and push. Historical completion reports remain unchanged.
Independent outside-user feedback precedes further speculative schema expansion;
PostgreSQL and publication remain separate future work.
