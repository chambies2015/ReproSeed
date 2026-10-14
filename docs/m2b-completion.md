# M2b completion evidence

## Scope and starting state

Work started on `main` at `d60c79c07ae12666af9572ced69edc3b9523ce17`, with
a clean working tree and empty index. This is the accepted M2a.1 commit;
[hosted run 38572680512](https://github.com/chambies2015/ReproSeed/actions/runs/38572680512)
passed Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12.
Historical completion reports remain unchanged. M2b hosted acceptance requires
Dan's subsequent commit and push. No staging, commit, push, PR, tag, release or
package publication was performed. All fixtures and scratch directories are
synthetic and tool-owned; generated evidence stays ignored under `.validation`.

## Design and supported shape

The shared adapter accepts ordinary and STRICT rowid tables with exactly two
ascending declared PK components, each exact INTEGER or TEXT (case and harmless
surrounding whitespace ignored). Existing INTEGER rowid aliases and TEXT/BINARY
scalar keys remain supported. Families come from schema metadata, including
empty tables. Every actual parent PK component must be non-NULL and have the
declared integer/text SQLite storage class; TEXT must decode safely.

Scalar identities remain `int | str`; composite identities use ordered
two-component tuples. Row identities are `(table, key)`. Explicit sort tokens
preserve scalar ordering and compare composite components in PK order, with
exact types, equality and hashable candidate-cache identities. No hidden rowids,
case folding or value coercion substitute for declared keys.

`table_xinfo` determines PK ordinals; `index_list` identifies the unique,
nonpartial declared PK index; `index_xinfo` checks its ordered actual key
columns, ascending order and BINARY comparisons, excluding auxiliary rowid
entries. Isolated empty-schema index probes also establish each TEXT column's
default BINARY collation. No CREATE TABLE regular-expression parser was added.

FK rows are grouped by constraint id and sequence. Explicit references must
name the full parent PK in matching order; omitted targets reference that full
PK implicitly. The parent determines each child component's declaration and
storage policy: integer affinity plus actual integer storage, or exact TEXT
plus actual text storage. Any NULL child component creates no dependency edge;
all populated groups use the full tuple. Reverse-edge lookup and visited-set
closure traversal support multiple constraints, scalar/composite children,
chains, self-references and cycles.

Candidate deletion quotes every PK identifier and binds every component in PK
order with BINARY equality. FK actions are disabled only on private candidates;
all excluded declared rows are deleted explicitly, then integrity and FKs are
validated. Retained values, indexes and schema remain exact subsets of pristine
state. VACUUM INTO may change hidden rowids, so three fresh confirmations of
the compact fixture remain required. The heuristic, budget reservation,
two-confirmation acceptances, invocation accounting and interruption
checkpoints are unchanged. Config, report, manifest and diagnostic formats
remain version 1; reports continue to store counts rather than row identities.

Three-or-more-component PKs, unsupported declared component types, NULL/wrong
storage, non-BINARY composite comparisons, descending composite order,
unsupported PK index metadata, reordered/non-PK UNIQUE FK targets, mismatched
FK cardinality and cross-affinity references are rejected. WITHOUT ROWID,
triggers, generated/hidden columns, virtual/shadow tables and previous excluded
shapes remain rejected. Curated diagnostic causes disclose no keys, rows,
arbitrary SQL, oracle output or absolute paths. Static diagnosis never launches
the oracle, and reduction rejects unsupported schemas before publication.

## Regression and application evidence

The new regression file uses real SQLite files for all four component families,
ordinary/STRICT/empty/nullable declarations, quoted identifiers, sparse and
negative integers, empty/Unicode/NUL text, PK ordinal order, exact deletion and
compaction, complete FK groups, partial NULLs, cycles, multi-level descendants
and normalized caches. Metadata boundary injections supplement real metadata
checks. Rejection tests assert no oracle launch, no bundle, source hash equality
and privacy-safe static/executable diagnosis. Existing categorical composite
rejection fixtures were replaced with genuinely unsupported shapes.

Before implementation, the 16 supported-PK regressions run against the archived
accepted M2a.1 source all failed at its one-column schema rejection. The
archive and command log are retained under `.validation/m2b-before`.

The billing application executes a deliberate refund-sign bug: it adds refunds
to settled charges. Its independent oracle recomputes net settlement, checks
actual application decisions and recognizes only the specified false-paid
behavior. Correcting subtraction yields PASS; unrelated crashes, decisions,
malformed decision maps and pending refunds do not produce the target marker.
The full generator has 1,308 rows; the small installed-wheel fixture has eight
genuine rows across six relational tables.

Initial full billing measurement on Windows/Python 3.12.15/SQLite 3.53.1:

| Table | Original | Retained |
| --- | ---: | ---: |
| tenants | 12 | 1 |
| accounts | 36 | 1 |
| invoices | 180 | 1 |
| invoice_lines | 540 | 3 |
| payments | 360 | 1 |
| refunds | 180 | 1 |
| Total | 1,308 | 8 |

The run charged 126/260 invocations, accepted 22 reductions, reused 23 cached
candidates, and recorded zero invalid or unresolved attempts. Search ended at
`single_row_closures_exhausted`. Source/final sizes were 172,032/65,536 bytes;
reduction took 44.703 seconds. Three baseline, three final and three relocated
replay confirmations were TARGET_FAILURE; separate executable diagnosis also
confirmed three fresh targets. Retained values/schema/metadata and FK validity
passed. Source and bundle hashes were equal before/after the complete workflow.
Detailed evidence: `.validation/m2b-composite-example-first/measurements.json`.

Source fixture SHA256:
`bf0f870a8c6d092829003fd5f98ca45e8b71b614209c15d180123440e23ed6f6`.
Final fixture SHA256:
`64f539818d456b9377a10dffcd232d46b86cb7791814409614e7738089e2d887`.

## Validation ledger

All 167 current focused adapter/TEXT/composite cases passed on Windows: a
captured 164-case run plus the three final additions. The new file contains 91
composite cases. Eight billing-focused semantic/acceptance cases passed; all 20
realistic semantic-oracle cases passed after the test-helper correction below.
Nine further recorded real-SQLite probes rejected NULL in both PK positions
across all four families and an empty custom default TEXT collation overridden
by a BINARY PK index. Probe evidence is `.validation/m2b-review-probes.json`.

Clean copies were prepared from the tracked and nonignored new files, with
per-file SHA256 records and `.validation`, `.venv` and `dist` absent initially.
Both pipelines explicitly created the CI pytest temporary-directory parent.
Only synthetic disposable files were used. Dependency lockfiles, action pins,
read-only CI permissions and the Ubuntu 3.12/3.14 and Windows 3.12 matrix remain
unchanged. CI's installed-wheel step now adds the small genuine composite case,
with bounded execution and no retries, continue-on-error or new broad skips.

Linux clean-copy validation used a cached, network-disabled disposable Docker
image `ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim` (image id
`b27bdf6aad17`). Runtime: Linux 6.18.33.2-microsoft-standard-WSL2, x86_64,
glibc 2.36; CPython 3.12.11, GCC 12.2.0; SQLite 3.40.1; uv 0.8.22; Ruff
0.17.0; pytest 9.1.1; mypy 1.20.2; build 1.6.1. Locked sync, Ruff lint/format, mypy,
mypy's Linux target, full pytest, wheel/sdist builds, distribution checks and
installed-wheel workflows passed. The suite reported **506 passed, 25 skipped
in 95.45 seconds** (recorder wall time 96.125 seconds).

Every Linux skip was an existing Windows-specific test: junction semantics,
owned Job integration, taskkill fallback, Windows Job API/ownership/failure
branches and readonly-file attributes. Linux ran its real POSIX signal and
process-group tests. Windows's deterministic injected interruption coverage
does not establish real Windows console Ctrl+C behavior. The Linux run was
local container execution, not a hosted Ubuntu run.

The Linux wheel's CLI was exercised outside `/source` in fresh virtual
environments. An isolated import assertion confirmed `reproseed` came from
the installation's `site-packages`. CI's exact script passed threshold,
ten-row TEXT and eight-row composite diagnosis/reduction/default JSON/explicit
JSON/text inspection/relocated replay. A separate installed-wheel run completed
all six full examples with unchanged observed row counts and invocation counts.
No editable source import substituted for the installed package. Logs,
commands, source-copy hashes, distributions and measurements are retained in
`.validation/m2b-linux-evidence/results`.

Windows clean-copy validation used Windows 10 build 19045, AMD64; CPython
3.12.15, MSC 1944; SQLite 3.53.1; uv 0.13.0
(`4ecd0eff2`, 2026-10-09); Ruff 0.17.0; pytest 9.1.1; mypy 1.20.2; build 1.6.1.
Locked sync, Ruff lint/format, mypy, the additional Linux target and full pytest
passed. The suite reported **525 passed, 6 skipped, 2 warnings in 720.82
seconds** (recorder wall time 722.984 seconds). The clean-copy wheel and sdist
build also passed. Logs and source-copy hashes are retained in
`.validation/m2b-windows-evidence`.

The six Windows skips were the two symlink cases lacking the required host
privilege (WinError 1314), real POSIX SIGINT workflow/diagnostic delivery,
POSIX executable mode and POSIX signal return codes. These same cross-platform
paths ran on Linux where applicable; Windows junction and Job/fallback tests
ran locally. Two existing interrupted invocation-accounting tests emitted
`oracle cleanup incomplete: taskkill exit (code 1)` warnings, while their
launch-accounting assertions passed. This is recorded cleanup uncertainty,
not a claim that every interrupted process cleanup succeeded. No new skips,
timeouts, hosted retries or weaker test assertions were introduced.

The Windows wheel passed CI's exact external installation script in 64.406
seconds: threshold, ten-row TEXT and eight-row composite static/executable
diagnosis, reduction, JSON/text inspection and relocated replay. An isolated
origin assertion confirmed the installed `site-packages` implementation.
Final test-helper supplementation passed all 20 affected oracle cases in
74.17 seconds (recorder wall time 76.531 seconds), along with final lint/format
and a fresh wheel/sdist build. That supplementary evidence is retained in
`.validation/m2b-windows-final-evidence`.

Windows's additional full installed-wheel run completed all six examples in
313.422 seconds, with the same row and invocation counts as the source table
below, all semantic/value/schema/FK/hash checks and all baseline/final/replay
confirmations. Individual reduction seconds were 23.250, 6.984, 45.125,
51.406, 74.562 and 52.734. Measurements are retained in
`.validation/m2b-windows-evidence/installed-measurements/measurements.json`.

Both platform distribution inspections found 17 wheel entries and 84 sdist
entries, no runtime `Requires-Dist`, and exact runtime-source bytes. Archives
contained no generated SQLite databases/sidecars, bundles, `.validation`,
environment/tool caches, `.git`, bytecode or `__pycache__`. The new example,
tests and intended completion documentation are included in the source
distribution. Final documentation-only updates are copied into the clean
snapshots and rebuilt/rechecked after the full runtime validation. Final
package evidence is retained alongside each platform's validation evidence.

## Complete application measurements

These are observations of the full Windows source workflows, not engine rules.
All six passed deterministic generation, shared-model static diagnosis,
three-confirmation executable diagnosis, exact semantic application checks,
retained declared values/schema/index/database metadata, integrity/FK checks,
source/assets/bundle hash equality, default/explicit JSON and text inspection,
and three additional relocated replay confirmations from unrelated temporary
working directories with the original example and bundle paths unavailable.
Every reduction had three fresh baseline and three compact-final targets.
Actual and charged counts agreed; unknown launches were zero. Every example
had zero invalid and unresolved candidates and ended at
`single_row_closures_exhausted`.

| Application | Original -> final | Calls / budget | Cache hits | Accepted | Reduction seconds | Source -> final bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Duplicate export | 2,430 -> 5 | 54 / 400 | 11 | 13 | 39.344 | 147,456 -> 20,480 |
| Aggregate threshold | 11 -> 3 | 18 / 80 | 5 | 3 | 11.390 | 12,288 -> 12,288 |
| Reservation overbooking | 4,248 -> 9 | 131 / 400 | 24 | 21 | 98.593 | 196,608 -> 36,864 |
| Approval cycle | 1,626 -> 6 | 107 / 400 | 25 | 22 | 27.672 | 94,208 -> 32,768 |
| TEXT entitlements | 970 -> 10 | 180 / 240 | 31 | 30 | 65.625 | 282,624 -> 57,344 |
| Composite billing | 1,308 -> 8 | 126 / 260 | 23 | 22 | 39.047 | 172,032 -> 65,536 |

Billing's per-table counts match the initial table above. Its final source and
fixture hashes also match the initial hashes above. Each measurement records
every source and bundle file hash, original/final table counts, runtime, budget,
confirmations and complete report. Evidence:
`.validation/m2b-source-measurements/measurements.json` and per-example
`measurement.json`, `reduction.json`, inspection and replay records.

The Linux installed-wheel full examples independently reached the same counts,
budgets, cache hits and acceptances. Their reduction durations were 5.495,
1.182, 11.995, 10.577, 14.163 and 8.946 seconds respectively in the table's
order. Per-platform hashes are checked within each run; database bytes need
not match across SQLite versions to preserve exact retained declared values.

## Genuine historical bundle compatibility

The explicit historical recipe archived reviewed pre-M1b commit
`ba40d64db748d974c36666294a1cc4500c79c25f`, generated a genuine old version-1
INTEGER threshold bundle with that implementation (11 -> 3 rows, 18 old
executions), then inspected and replayed it with the current reader. A separate
recipe archived accepted M2a.1 commit `d60c79c07ae12666af9572ced69edc3b9523ce17`
and used its unmodified implementation to generate a genuine TEXT bundle
(small fixture 10 -> 10 rows, 23 old executions). Both passed default and
explicit JSON equality with their original reports, text inspection and three
new relocated replay targets from unrelated external working directories.
Archive/commit provenance and all original source/bundle hashes are retained
in `.validation/m2b-pre-m1b-v1` and `.validation/m2b-m2a-text-v1`.

In addition, the genuinely preserved pre-M2b M2a TEXT artifact at
`.validation/m2a-source-measurements/text_key_entitlements/bundle-unavailable`
was validated against its original October 13 measurement, rather than relying
solely on regenerated historical source. That original fixture was 970 -> 10
rows with 180 recorded executions. Original measurement mtime was
`2026-10-13T22:33:01Z`; its SHA256 was
`8ea1e123a5d43531f65f7e9b9fbd7120402f8581759b74eb2f206c1985127871`.
Every original source and bundle hash matched the captured prior measurement.
The current reader's default/explicit JSON equaled the original report and
text inspection passed. Three new copied, relocated replay confirmations were
TARGET_FAILURE with exit 46. The original source, bundle, report and measurement
were neither renamed nor written. Evidence:
`.validation/m2b-preserved-m2a-text/validation-result.json` and companion logs.
Hash/consistency checks do not authenticate historical executions; these new
replays establish only their freshly observed outcomes.

The final installed Linux wheel also inspected and replayed verified byte
copies of the genuine pre-M1b INTEGER and preserved October 13 M2a TEXT
bundles. Both default JSON outputs matched the original reports, text
inspection passed, and each replay returned three fresh TARGET_FAILURE
confirmations. Original and copied bundle hashes remained unchanged. Direct
mounting of the original Windows fixture files hit host permission restrictions;
explicit captured manifest files were copied byte-for-byte to fresh tool-owned
payloads instead, without changing the original files or their permissions.
Evidence: `.validation/m2b-linux-evidence/results/final-linux-historical.json`
and `historical-payloads/capture.json` under that evidence directory's parent.

## Performance review

An ignored benchmark compared accepted archived scalar code with current code
on 4,248 reservation rows. Median milliseconds (three warm-cache repeats):

| Operation | Accepted scalar | M2b scalar |
| --- | ---: | ---: |
| Model, including integrity/storage/FKs | 24.064 | 37.428 |
| Dependency discovery | 14.947 | 18.912 |
| Sorting | 1.353 | 8.659 |
| Closure | 2.334 | 4.568 |
| Materialization, including backup/checks | 691.313 | 743.499 |

Closure's implementation is unchanged; concurrent filesystem/process activity
affects these small measurements. An interleaved, fixed-input in-memory sort
probe with GC disabled during timing confirmed identical scalar ordering and
an actual token-allocation constant cost: 1.194 versus 6.394 ms, a 5.35x ratio
but 5.199 ms absolute difference for 4,248 rows. This is recorded rather than
hidden; the unchanged application reductions still use the same invocation
counts. The extra allocations do not introduce pairwise identity comparisons.

Composite scaling used 1,000/4,000/16,000 parents plus equally many scalar
children referencing complete tuples. Model medians were 11.071/38.590/174.602
ms; dependency discovery 4.401/16.646/111.994 ms; materialization
331.271/310.263/465.457 ms. SQL query plans confirmed composite deletion uses
the declared PK autoindex. Complete typed tuples directly index reverse-edge
maps; components are bounded at two, sorting remains O(N log N), and no new
per-child scan of all parent rows was introduced. These local three-repeat
observations are not a universal complexity or performance guarantee.
All benchmark candidates passed identity, source hash and integrity/FK checks.
Evidence: `.validation/m2b-performance/measurements.json` and
`isolated-scalar-sort.json`.

## Review, discovered issues and limitations

Independent implementation review and real-SQLite probes found no demonstrated
runtime defect. Review covered grouped FK edges, missing/spurious descendant
removal, typed equality, case folding/coercion, hidden rowids, PK component
order, quoted/bound SQL, NULL parent identities, diagnosis/reduction agreement,
scalar ordering, budget/confirmation/accounting invariants and excluded shapes.
Existing cancellation, cleanup and accounting tests remain in the full suite.

A test-helper review found that changing `settled += refunded` to
`settled -= refunded` preserves file length and can leave a same-second cached
`.pyc` valid. The realistic-oracle subprocess helper now disables bytecode
writes and explicitly uses UTF-8, so counterfactual tests exercise the edited
source. All 20 semantic-oracle tests passed afterward. This changes test
execution hygiene, not the generic reducer or billing application behavior.
The clean snapshots were already captured; final supplemental validation
copies this helper and reruns its affected tests before final packaging.

Temporary harness issues were corrected without runtime edits: Linux's empty
tmpfs destination already existed, so copying into that known empty mount used
`dirs_exist_ok`; a manual probe cleanup needed `closing` for its own SQLite
connection. A supplemental Linux lint run after pytest scanned deliberately
broken counterfactual application copies under its scratch directory, because
that isolated copy had no Git context for ignore discovery. The harness was
reordered to lint/format before generating test fixtures, matching CI. Source
lint/format and all 20 final oracle tests then passed (4.25 seconds in pytest;
5.542 seconds recorder wall time). No test or production rule was weakened.
The corrected actual runs, not these failed harness preparations, provide the
platform evidence above.

A direct root build initially tried the unavailable package network for its
isolated backend requirements. The completed package builds use cached offline
resolution, as the clean validation recorders already did; no lockfile or
dependency policy changed to work around the environment.

No Linux/Python 3.14 run or real Windows console Ctrl+C run was performed
locally. Hosted M2b validation remains pending Dan's commit/push. Arbitrary
arity, descending composites, WITHOUT ROWID, broader SQLite affinities or
collations, M2c and PostgreSQL remain outside scope. Tuple sorting's measured
constant overhead is a known performance tradeoff. This is not a
production-ready release, anonymization mechanism or proof of global minimality.

## Final Git state

Branch remains `main`; HEAD remains
`d60c79c07ae12666af9572ced69edc3b9523ce17`. The index is empty, and
`git diff --check` passes. Seventeen tracked files are modified and seven
new files are untracked. All changes remain unstaged and uncommitted for Dan.
No historical completion report or prior bundle was modified.

```text
 M .github/workflows/ci.yml
 M AGENTS.md
 M CONTRIBUTING.md
 M README.md
 M SECURITY.md
 M docs/architecture.md
 M docs/diagnostics.md
 M docs/roadmap.md
 M src/reproseed/diagnostics.py
 M src/reproseed/reducer.py
 M src/reproseed/sqlite_adapter.py
 M tests/compatibility_smoke.py
 M tests/milestone_smoke.py
 M tests/test_realistic_acceptance.py
 M tests/test_realistic_oracles.py
 M tests/test_sqlite_adapter.py
 M tests/test_text_keys.py
?? docs/m2b-completion.md
?? examples/composite_billing/
?? tests/test_composite_keys.py
```

Hosted M2b acceptance remains pending Dan's subsequent commit and push. Local
Windows and Linux evidence above does not substitute for that hosted gate.
