# M2a completion evidence

## Starting state and scope

Work began on `main`, at accepted commit
`c9cf32ced7f0428385d1daad912d5aa01fec6967`, with a clean index and working tree.
M1b.2 hosted run [38476866662](https://github.com/chambies2015/ReproSeed/actions/runs/38476866662)
passed Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12, as supplied
in the accepted milestone request. Historical completion reports are preserved.

M2a implements single-column TEXT primary keys and matching foreign keys in the
existing SQLite adapter. No runtime dependency, configuration/bundle/report version,
diagnostic version, oracle contract, confirmation count, reduction heuristic or
invocation accounting format changed. No staging, commit, push, PR, tag, release or
package publication was performed. Hosted M2a validation remains pending Dan's
subsequent review, commit and push.

## Supported shape and safety decisions

Ordinary rowid tables have exactly one supported primary key: the existing exact
INTEGER rowid alias, or exact declared TEXT, ignoring type-name case and surrounding
whitespace. Inline and table-level declarations, ordinary and STRICT tables, empty
tables, empty-string/Unicode/quoted/NUL-containing text keys, sparse integer keys,
and mixed databases are supported. Every TEXT PK must have actual SQLite TEXT
storage class, decode into a Python string, and be non-NULL in the snapshot. Ordinary
SQLite TEXT PK declarations without NOT NULL are accepted only when their actual
values meet those rules. ReproSeed does not rewrite the declaration or stored values.

Both the TEXT PK index and the column's default collation must be BINARY.
`index_list` establishes the actual single, unique, nonpartial PK index;
`index_xinfo` establishes its key column and collation. A table-level PK can override
its column collation. An isolated in-memory metadata probe executes the original
CREATE TABLE declaration without rows, creates an index that inherits the PK column's
default, and inspects that index with SQLite. This rejects a NOCASE column whose PK
index overrides it with BINARY, including empty tables. Source schema/data are never
modified, and CREATE TABLE text is not parsed with regular expressions. Identity
ordering/deletion SQL explicitly uses BINARY as an additional safeguard.

FK policy comes from the referenced parent. TEXT parents require exactly declared
TEXT child columns and non-NULL actual TEXT/string values; INTEGER parents retain
the existing integer-affinity declaration and actual integer storage policy. NULL
FKs are allowed. The child's own PK family is independent. Parent PK targets may be
explicit or implicit; identifier matching folds only ASCII as SQLite does, while
key values are never folded or coerced. The dependency graph uses exact declared
keys and terminates across multiple FKs, self-references and mixed-family cycles.
Child column collations do not replace the supported parent's BINARY equality.

VARCHAR/CHAR and other text-affinity PK/FK spellings, cross-affinity FK declarations,
NOCASE/RTRIM/custom TEXT-key collations, NULL/nontext TEXT PKs, wrong FK storage,
composite/missing PKs, composite FKs, FK targets on non-PK UNIQUE columns,
non-alias INTEGER PKs, BLOB/REAL PKs, WITHOUT ROWID, virtual/shadow tables,
generated/hidden columns and triggers remain unsupported. Integrity failures can
precede stored-type errors: newer SQLite detects some deliberately migrated legacy
storage that older SQLite lets reach the explicit storage check. Both paths reject
the input before oracle execution; precise BLOB storage regressions pin the curated
wrong-type diagnostic causes independently of that version difference.

Malformed key text and unavailable collation metadata become actionable DatabaseError
and curated diagnostic causes without echoing keys, source paths or SQLite row text.
Model validation now checks integrity, schema/storage/dependency policy, then FK
consistency. FK validity remains unknown on schema rejection. Unavailable-collation
and malformed-text errors conservatively leave integrity unknown when its completion
cannot be established. Diagnostic JSON stays version 1 with its existing shape.

TEXT keys identify rows through their declared values, never hidden rowids. VACUUM
may change hidden rowids for tables without an INTEGER PK alias. M2a preserves
retained declared values, keys, schema, indexes and relevant metadata; it does not
promise hidden-rowid identity. Three fresh confirmations of the actual compact
fixture remain the authority for final reproduction. Failed final confirmation
does not publish a verified bundle.

SQLite references: [rowid tables](https://www.sqlite.org/rowidtable.html),
[foreign-key comparisons](https://www.sqlite.org/foreignkeys.html),
[PRAGMA metadata](https://www.sqlite.org/pragma.html),
[CREATE TABLE and NULL PK behavior](https://www.sqlite.org/lang_createtable.html),
[storage classes and affinity](https://www.sqlite.org/datatype3.html).

## Interfaces and regression coverage

`Key = int | str`, `KeyFamily = Literal["INTEGER", "TEXT"]`, and
`RowId = tuple[str, Key]` extend the internal identity contract. `_Table` records the
family from schema metadata, even for empty tables. The workflow evaluator uses the
shared RowId alias. Existing frozenset cache identities preserve exact values;
table-first tuple sorting never compares an integer with a string from another
table, and one validated family per table prevents mixed-family comparisons within
a table. Existing INTEGER ordering and the reducer implementation are unchanged.

The adapter adds PK index/default-column collation checks, storage-class checks and
handled decoding errors around key reads. Materialization still starts from a fresh
private snapshot, binds every excluded key in an explicitly quoted DELETE, disables
FK actions only for that private transaction, and validates the result. No ON DELETE
action rewrites retained values. The existing artifact fixture validator already
calls the expanded shared model, so inspect/replay need no format or reader fork.

`tests/test_text_keys.py` adds 47 real SQLite cases covering declarations, nullable
PK schemas, STRICT/empty tables, exact string identity, Unicode/NUL/quotes, UTF-16
database compaction, mixed parent-family links, multiple FKs, nullable references,
cycles/self-links, ASCII-only identifier matching, dependency closure, deterministic
caching, strict accepted decreases, value/schema/metadata preservation, fresh
materialization after oracle mutations, collation overrides, NULLs, storage classes,
malformed PK/FK text, unsupported declarations and before-launch rejection. Negative
CLI cases assert zero oracle launches, unchanged source/config/assets, no bundle and
privacy-safe diagnostics. Existing categorical TEXT rejection fixtures now use
genuinely unsupported VARCHAR while retaining their rejection assertions.

The new independent application tests cover its particular semantic failure,
same-tenant duplicates, removed preconditions, a corrected processor returning PASS,
and unrelated discrepancies/errors that cannot emit the target marker. Existing
interruption, accounting, cleanup, source snapshot, report and bundle regressions
remain in the full suites.

## Synthetic entitlement application measurements

`examples/text_key_entitlements` processes grants and deliberately deduplicates a
gateway event reference globally. The intended reference scope is its tenant. Its
oracle executes the processor and independently compares the complete observable
decision map against tenant-scoped behavior. It emits the exact target marker only
when that map exactly matches the global-dedup defect and suppresses a valid grant
in another tenant. There is no bug flag or fixture-specific reducer logic.

The generator creates 970 synthetic rows in five tables: tenants use INTEGER PKs;
accounts, entitlements and events use sparse TEXT IDs; event_receipts use INTEGER
PKs. The relationships include TEXT -> TEXT, TEXT-PK children -> INTEGER parents,
INTEGER-PK children -> TEXT parents, nullable FKs and multiple dependency levels.
The finite reduction budget is 240 invocations. A separate ten-row generator mode
keeps installed-wheel CI smoke small; full pytest and measurement runs use 970 rows.

Actual Windows source run, Python 3.12.15 / SQLite 3.53.1:

| Table | Source rows | Final rows |
| --- | ---: | ---: |
| accounts | 40 | 2 |
| entitlements | 120 | 2 |
| event_receipts | 400 | 2 |
| events | 400 | 2 |
| tenants | 10 | 2 |
| Total | 970 | 10 |

Reduction used 180/240 invocations, 31 cache hits and 30 accepted reductions, with
zero unresolved/invalid candidates or unknown launches. Search terminated with
`single_row_closures_exhausted`. Observed reduction wall time was 43.094 seconds;
fixture bytes decreased from 282,624 to 57,344. Static diagnosis launched nothing;
executable diagnosis, reduction baseline, final compact verification and additional
relocated replay each recorded three TARGET_FAILURE confirmations. Diagnosis and
replay executions are separate from the recorded reduction budget. This is an
observed result, not a proof of global minimality or a timing guarantee.

Evidence: `.validation/m2a-source-measurements/measurements.json` and its per-example
diagnostic/report/replay files. The recipe checks retained declared rows are exact
subsets, original CREATE declarations and index_xinfo/other metadata match, integrity
and FKs pass, and complete source/assets/bundle SHA256 maps match before/after.
Replay occurs outside the checkout after original source/assets/bundle paths have
been made unavailable. Source SHA256:
`9feec820e4fb47907721203f9b5e642247f51d6a7ff97bdc820e8b79b1283632`;
compact fixture SHA256:
`6effd98b45c75846456fff6957d9114aa0a59fa9106495944cb0ed148b4d0a7a`.

The compact TEXT smoke also passed: 10 -> 10 rows, 23/240 invocations, five cache
hits, no accepted reductions, 5.922 seconds and 57,344 bytes before/after. It executes
the real diagnostic/reduction/inspection/relocated-replay workflow rather than a
mock. Its budget is unchanged from the full example.

## Integer and historical version-1 compatibility

Fresh source runs preserved all four established integer application counts:

| Application | Rows | Executions/budget | Cache hits | Accepted | Seconds | Source/final bytes |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Duplicate export | 2,430 -> 5 | 54/400 | 11 | 13 | 11.078 | 147,456 / 20,480 |
| Aggregate threshold | 11 -> 3 | 18/80 | 5 | 3 | 5.578 | 12,288 / 12,288 |
| Reservations | 4,248 -> 9 | 131/400 | 24 | 21 | 28.250 | 196,608 / 36,864 |
| Approval cycle | 1,626 -> 6 | 107/400 | 25 | 22 | 29.750 | 94,208 / 32,768 |

All had zero unresolved/invalid candidates or unknown launches, exhausted single-row
closures, and passed three baseline/final/additional relocated replay confirmations,
static/executable diagnosis, default/explicit JSON and text inspection, retained
values/schema/metadata and source/assets/bundle hash checks. Timings reflect actual
local scheduling, including concurrent validation work. Full evidence and per-table
counts are in `.validation/m2a-integer-measurements/measurements.json`.

Source -> compact fixture SHA256 from those runs:

| Application | Source | Compact fixture |
| --- | --- | --- |
| Duplicate export | `a1f219e3495878679289eef047a6eba8e91d483797eaa5977c5b5f4f785cda69` | `8b9b80e6a6a2e3ae387dee0f3b93da7a5d9dba34b0fada3b8c06c571e1958e4a` |
| Threshold | `c523f93be27a6ef7768c9c6a443b911dca37d6caabe4bd920f5f8084dd4e8cf2` | `471fdf89e2deae73c964d37de7175e05629dee27145a8373414af1e01e7d58b1` |
| Reservations | `a457404c3dad432083656cd935c3a32ae10fa19ca42af351058aea9e785d4985` | `fe9af650fa04a887961e8a5210b59c87bbf2f505f35983551a29a22d46b8067e` |
| Approval cycle | `74b3cf3c4251ba779037bf0b756b1cb9b90f76070b3eee103736bc2e1ef43d54` | `037e3b906423538b570be87a7dfd02e93e4e96cfac5f631528b41fb8e3dffd4d` |

The genuine historical recipe archives reviewed pre-M1b commit
`ba40d64db748d974c36666294a1cc4500c79c25f` and executes that implementation against
its synthetic threshold source to produce a real version-1 bundle. Windows's current
reader accepted default/explicit JSON exactly equal to its report, text inspection,
strict evidence relationships and three fresh relocated TARGET_FAILURE replays.
The old reduction observed 11 -> 3 rows with 18 executions; source/assets/bundle
bytes remained unchanged. Evidence:
`.validation/m2a-pre-m1b-v1-fresh/compatibility-result.json`. No migration, rewritten
hashes or invented historical execution records were used.

## Validation and package evidence

Fresh clean copies were prepared from tracked and nonignored requested source files,
with hashes captured before execution and no .venv, .validation or dist copied in.
Both explicitly ran the CI preparation that creates .validation before pytest.
Source hashes for the exercised code, tests, examples and existing documentation
remain equal to the final working files; the completion report was added afterward.

| Check | Windows 10 build 19045 | Linux WSL2 Docker / glibc 2.36 |
| --- | --- | --- |
| Python / SQLite | 3.12.15 / 3.53.1 | 3.12.11 / 3.40.1 |
| uv / Ruff / mypy / pytest | 0.13.0 / 0.17.0 / 1.20.2 / 9.1.1 | Same tool versions |
| Locked dependency sync | Passed, Python 3.12 selected | Passed, Python 3.12 selected |
| Ruff lint and formatting | Passed | Passed |
| mypy and mypy --platform linux | Passed | Passed |
| Full clean-copy pytest | 419 passed, 6 skipped, 2 warnings; 395.91s | 400 passed, 25 skipped; 97.73s |
| Wheel and sdist build | Passed | Passed |
| Package content inspection | Passed | Passed |
| Extracted CI installed-wheel smoke | Passed; 26.547s | Passed; 8.792s |
| Full installed five-example recipe | Passed; 99.422s | Passed; 41.847s |
| Genuine historical v1 generation/inspection/replay | Passed separately on Windows | Passed independently in Linux |

All 425 collected cases ran or received explicit platform/privilege skips. Windows
skips were two symlink tests (WinError 1314), POSIX executable mode, POSIX signal
return codes and the two real SIGINT workflows. Linux skips were 25 Windows-only
junction/Job Object/taskkill/readonly-file branches. Linux actually executed the
POSIX signals; deterministic Windows KeyboardInterrupt injection is distinct from
Windows console Ctrl+C coverage. Windows recorded two `taskkill exit (code 1)`
cleanup warnings in existing invocation-accounting interruption/launch-evidence
tests, which passed; the warnings remain in the full log. No warning is concealed
as a successful cleanup claim.

The focused Windows command below passed 122 cases with one POSIX SIGINT skip in
136.43 seconds. All 47 new TEXT cases passed on both actual SQLite versions. The
independent application-oracle suite also passed all 13 cases. During implementation,
obsolete categorical TEXT rejection expectations were corrected to VARCHAR, specific
storage diagnostics replaced a former generic FK failure expectation, and legacy
storage-migration tests were adapted to SQLite's actual earlier integrity rejection.
The final checks above passed after those corrections.

Representative actual commands (Windows uses the project-local uv executable and
workspace UV_CACHE_DIR; the recorder logs every command and exit):

```powershell
.tools/bin/uv.exe sync --locked --python 3.12 --offline
.venv/Scripts/python.exe -m pytest tests/test_text_keys.py tests/test_sqlite_adapter.py tests/test_diagnostics.py tests/test_diagnose_cli.py --basetemp=.validation/pytest-text-agent-final
.venv/Scripts/python.exe tests/milestone_smoke.py --directory .validation/m2a-source-measurements --examples text_key_entitlements
.venv/Scripts/python.exe tests/milestone_smoke.py --directory .validation/m2a-integer-measurements --examples duplicate_export threshold reservation_overbook approval_cycle
.venv/Scripts/python.exe tests/compatibility_smoke.py --directory .validation/m2a-pre-m1b-v1-fresh
.venv/Scripts/python.exe .validation/m2a_validate.py pipeline --root .validation/m2a-clean-windows --evidence .validation/m2a-windows-evidence --uv .tools/bin/uv.exe
```

Both clean pipelines ran `uv run --locked ruff check .`, `uv run --locked ruff format
--check .`, `uv run --locked mypy`, `uv run --locked mypy --platform linux`, the CI
parent preparation, `uv run --locked pytest --basetemp=.validation/pytest` and
`uv build --no-sources`. Windows used cached locked dependencies offline; the isolated
Linux container installed its locked development dependencies, then performed all
application/replay work locally. Only a disposable owned container was used and it
was removed afterward. No existing application container or unrelated data was changed.
The Linux historical archive's reviewed commit and SHA256 are captured separately in
`.validation/m2a-linux-evidence/historical-archive.json`.

Raw results and runtime details are in `.validation/m2a-windows-evidence/commands.json`
and platform logs, `.validation/m2a-linux-evidence/summary.json` and its command/log
files. Native Ubuntu, Linux Python 3.14, local Windows Python 3.14 and Windows console
Ctrl+C were not run. Actual Linux coverage used Python 3.12.11 in the available local
Docker runtime; it is not a claim of Ubuntu or Python 3.14 execution. The unchanged
hosted Ubuntu 3.12/3.14 and Windows 3.12 matrix, read-only permissions, pinned actions,
full tests and wheel workflow still need the later M2a commit/push gate.

Installed interpreters were freshly created, wheels installed with no dependencies,
and `python -I` verified imports beneath that environment's site-packages. Both the
CI threshold/compact-TEXT smoke and all five full examples ran outside the source
checkout using the installed console, with PYTHONPATH/PYTHONHOME removed. Default
JSON, explicit JSON and text inspection, static/executable diagnosis, relocated replay
and source/bundle immutability passed. Three baseline/final/new replay confirmations
and all table counts, budgets/cache/acceptance summaries agree with the source runs.

| Application | Installed Windows reduction seconds | Installed Linux reduction seconds | Rows / reduction executions |
| --- | ---: | ---: | --- |
| Duplicate export | 9.078 | 3.566 | 2,430 -> 5 / 54 |
| Threshold | 2.843 | 1.061 | 11 -> 3 / 18 |
| Reservations | 22.328 | 10.854 | 4,248 -> 9 / 131 |
| Approval cycle | 18.078 | 6.678 | 1,626 -> 6 / 107 |
| TEXT entitlements | 27.812 | 11.605 | 970 -> 10 / 180 |

These are filesystem/platform/scheduling observations, not performance guarantees.
The TEXT example's 31 cache hits, 30 accepted reductions, zero invalid/unresolved
trials and 282,624 -> 57,344 bytes agree on both platforms. Linux's independently
generated SQLite source hash was
`aad905adefcca180ba980b3ee44d4f937f6aee2515731dd6c3b57fb5913aad1b`, and its final
hash was `b5f9c6908fa1f74db0e1d00f30c73c318f790265d7ecc2182493dafb910c7bc9`.
Windows hashes match its source run listed above. Database file bytes can differ
between SQLite versions while retained declared values remain exact subsets within
each run. Each platform's `installed-measurements/measurements.json` contains actual
per-table counts, full source/assets/bundle SHA256 maps and all confirmation outcomes.
Linux's genuine historical-v1 recipe independently passed 11 -> 3 rows, 18 historical
reduction executions, all inspection forms and three new TARGET_FAILURE replays,
with unchanged source/bundle bytes and no report reinterpretation.

Final handoff builds live in `.validation/m2a-final-dist/`. The wheel/sdist inspection
checks every runtime module byte against both exercised wheels and both clean-copy
source hashes, every explicitly selected source file against the final sdist, and
zero runtime Requires-Dist entries. Generated databases, sidecars, bundles, logs,
bytecode, validation evidence, environments, Git state and caches are excluded. The
sdist includes the new example, tests, docs and this completion report. The final
`content-check.json` records inventories, source and distribution SHA256 values.
The local builder warned that the workspace UV cache could enter the distribution;
the inspected explicit inventories confirm that .validation and its cache are absent.
No artifact was published. Final handoff commands:

```powershell
.tools/bin/uv.exe build --no-sources --offline --out-dir .validation/m2a-final-dist
.venv/Scripts/python.exe .validation/m2a_package_check.py
git -c core.autocrlf=false diff --check
```

## Limits and final review

This is an M2a prototype. It does not support all string-keyed SQLite schemas,
arbitrary collations, composite keys or WITHOUT ROWID. Hidden rowids can change.
Retained data remains potentially sensitive; reduction is not anonymization.
Neither global minimality nor production readiness is claimed. Structural diagnosis,
hash integrity and consistent recorded evidence do not independently establish a
new reproduction or authenticate historical claims. Oracle execution and process
cleanup retain the existing platform and trust-boundary limits in SECURITY.md.

Final review covers exact identities, no coercion/case folding, both column/index
collations, parent-family dependency closures, pristine materialization, bound/quoted
SQL, retained values, unsupported rejection, integer ordering, fresh confirmations,
unchanged accounting/cancellation/process cleanup, unchanged formats and scope.
Historical reports remain unchanged. Generated databases, bundles, archives, caches,
logs and measurement evidence stay in ignored tool-owned validation directories.
M2b is proposed in the roadmap, with no M2b implementation in this change.

`main` remains at `c9cf32ced7f0428385d1daad912d5aa01fec6967`. The index is empty;
all changes are unstaged/uncommitted for Dan. Final `git status --short`:

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
 M src/reproseed/sqlite_adapter.py
 M src/reproseed/workflow.py
 M tests/milestone_smoke.py
 M tests/test_diagnose_cli.py
 M tests/test_diagnostics.py
 M tests/test_realistic_acceptance.py
 M tests/test_realistic_oracles.py
 M tests/test_sqlite_adapter.py
?? docs/m2a-completion.md
?? examples/text_key_entitlements/
?? tests/test_text_keys.py
```
