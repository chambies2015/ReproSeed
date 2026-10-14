# M2c completion evidence

Validation date: 2026-10-14. This is a bounded SQLite adapter expansion of the
local standard-library-only Python CLI. Hosted M2c validation remains pending
Dan's subsequent commit and push; no release or package publication is authorized.

## Starting state and ownership

The starting checkout was `main`, HEAD
`d70edac43c22efe3df643b821af1c51ec756a945`, with an empty Git status.
It matches accepted M2b [hosted run 38592071692](https://github.com/chambies2015/ReproSeed/actions/runs/38592071692),
which passed Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12.
The explicit M2c request supersedes the older M2b-only instruction. No existing
user changes were present. Historical completion reports and accepted history
were preserved. Every database used here was generated synthetic data in a
new tool-owned scratch directory. No stage, commit, push, PR, tag or publication
was performed.

## Supported identities and storage layouts

WITHOUT ROWID supports one exact declared INTEGER or TEXT component, or exactly
two components: INTEGER+INTEGER, INTEGER+TEXT, TEXT+INTEGER and TEXT+TEXT.
All WITHOUT ROWID PK index components must be ascending. Ordinary rowid-table
support is preserved, including scalar INTEGER rowid aliases, scalar TEXT's
existing ordering policy and ascending two-component keys. Mixed storage layouts,
empty tables and supported STRICT combinations share one adapter and lifecycle.

`_Table.without_rowid` comes from `PRAGMA main.table_list`. `table_xinfo` PK
ordinals establish the declared key order. A WITHOUT ROWID scalar INTEGER PK
requires a unique nonpartial declared PK index; it is never a rowid alias.
`index_list` locates that index, and `index_xinfo` entries with key flag 1 must
match the declared columns and order. Auxiliary nonkey data columns are excluded
from key arity. The existing composite checks apply to both storage layouts.
PK index comparisons are BINARY; every TEXT key also requires BINARY on its
column default, established through the existing empty SQLite schema probe.
All actual PK components must be non-NULL integer/text storage matching their
metadata, and TEXT must decode safely.

`ScalarKey = int | str`, the two-component `CompositeKey`, and `(table, key)`
RowId equality remain unchanged. Storage layout adds no identity component.
Ordering, hashable candidate caches, reduction heuristics, invocation accounting,
cancellation checkpoints and all version-1 serialized formats remain unchanged.

Rejected SQLite-created schemas include three-or-more PK components, REAL/BLOB/
NUMERIC/INT/VARCHAR PK declarations, unsupported collations, descending WITHOUT
ROWID or composite keys, wrong storage or malformed key text, unavailable custom
collations, non-PK UNIQUE/reordered FK targets, incorrect FK arity, cross-affinity
FK declarations, generated/hidden columns, triggers and virtual/shadow tables.
SQLite itself rejects WITHOUT ROWID with no declared PK, AUTOINCREMENT, and NULL
PK inserts; tests distinguish engine rejection from adapter rejection without
manufacturing impossible schema states.

SQLite's [WITHOUT ROWID documentation](https://www.sqlite.org/withoutrowid.html)
explains the absent hidden rowid, INTEGER PK alias behavior, last_insert_rowid
updates, rowid-based incremental BLOB I/O and update-hook notifications. ReproSeed
uses none of those as row identity. [PRAGMA documentation](https://www.sqlite.org/pragma.html)
establishes the metadata interpretation; [foreign-key documentation](https://www.sqlite.org/foreignkeys.html)
establishes parent-driven comparison and NULL rules; [CREATE TABLE documentation](https://www.sqlite.org/lang_createtable.html)
describes declared PK restrictions.

## Relationships and preservation

Each FK declaration id remains one ordered group targeting the complete parent
PK, implicitly or explicitly in PK order. Parent component families determine
child declaration/storage policy independently of the child's own key or layout.
Any NULL child component creates no required parent or reverse edge; non-NULL
components still undergo type/storage/decoding validation. Full tuple equality
prevents removal of unrelated rows sharing only one component. Independent FKs,
both mixed-layout directions, cycles and self-references use the existing graph.
Child-column collations do not override the validated parent's FK comparison.

Candidate acquisition and deletion use quoted declared PK columns and bound
values. FK actions are disabled only on private candidates, then re-enabled;
integrity and FK consistency are checked before oracle execution. Retained values
are not rewritten by ON DELETE actions. Backup and VACUUM INTO preserve declared
schema, indexes and metadata. WITHOUT ROWID has no hidden rowid to preserve;
ordinary TEXT/composite tables can acquire different hidden rowids during VACUUM.
Three fresh confirmations still verify the compact artifact.

## Schema, lifecycle and rejection regressions

`tests/test_without_rowid.py` adds 76 real SQLite cases: six key shapes across
empty/populated and ordinary/STRICT variants, reversed physical/PK column order,
auxiliary index columns, secondary indexes, UTF-16 metadata, negative/sparse
integers, quoted/empty/Unicode/NUL text, nullable data, all-family implicit/explicit
FKs, mixed-layout chains, multiple FKs, partial NULL references, cycles, self-links,
deterministic caching, materialization and compaction. SQLite joins independently
check exact dependencies. Source hashes, complete retained values, schema/indexes,
metadata, integrity and FK checks are asserted.

Unsupported fixtures exercise static and executable diagnosis plus reduction,
with zero launches, no published output, unchanged source/assets, and curated
causes that omit sensitive values and paths. Engine-rejection cases remain
separate. A real mutating subprocess exercises static/executable diagnosis,
reduction, default/explicit JSON and text inspection, pristine confirmation copies
and relocated replay outside the checkout. Old categorical WITHOUT ROWID rejects
were replaced by specific unsupported schemas with their safety assertions intact.

Focused Windows legacy scalar/composite/adapter/diagnosis validation passed
213 tests with one existing POSIX SIGINT skip in 220.82 seconds. The 76 new cases
passed in focused parts; 28 application-oracle/generator cases passed in two
recorded runs. The clean-copy full-suite results below provide the final single
suite runs. Novel independent probes also passed declared columns named `rowid`
and `_rowid_`, quoted names, ASCII FK identifier folding, child NOCASE versus
parent BINARY comparisons, exact closures, bound deletion, compaction and unchanged
source hashes. Evidence: `.validation/wr-audit-novel/`.

## Full applications and billing variant

Source-import measurements ran on Windows 10 build 19045, CPython 3.12.15,
SQLite 3.53.1. These results are observations, not hardcoded reducer requirements.

| Application | Original -> final | Invocations / budget | Accepted | Cache hits | Reduction seconds | Source / final bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Duplicate export | 2,430 -> 5 | 54 / 400 | 13 | 11 | 17.766 | 147,456 / 20,480 |
| Threshold | 11 -> 3 | 18 / 80 | 3 | 5 | 8.297 | 12,288 / 12,288 |
| Reservations | 4,248 -> 9 | 131 / 400 | 21 | 24 | 38.172 | 196,608 / 36,864 |
| Approval cycle | 1,626 -> 6 | 107 / 400 | 22 | 25 | 27.922 | 94,208 / 32,768 |
| TEXT entitlements | 970 -> 10 | 180 / 240 | 30 | 31 | 53.062 | 282,624 / 57,344 |
| Ordinary composite billing | 1,308 -> 8 | 126 / 260 | 22 | 23 | 38.109 | 172,032 / 65,536 |
| Mixed-layout billing | 1,308 -> 8 | 126 / 260 | 22 | 23 | 44.375 | 147,456 / 45,056 |

Every run had zero invalid/unresolved candidates and unknown launches, terminated
with `single_row_closures_exhausted`, and passed three baseline, three compact-final
and three fresh relocated replay target confirmations. Static/executable diagnosis,
default/explicit JSON/text inspection, independent application decisions, retained
values/schema/indexes/metadata, integrity/FKs and source/bundle immutability passed.

Both billing layouts retained tenants 12 -> 1, accounts 36 -> 1, invoices 180 -> 1,
invoice_lines 540 -> 3, payments 360 -> 1 and refunds 180 -> 1. The variant puts all
tables except ordinary INTEGER payments in WITHOUT ROWID storage. The unchanged
independent application/oracle detects refunds incorrectly added to settled money,
using exit 47 and its exact configured marker. No oracle-directed row flags were
added. Archived M2b and current default full/small generator bytes matched exactly.
The 126 reduction launches include its three baseline and three final attempts.
Each explicit billing recipe additionally runs one independent oracle preflight,
three diagnosis baselines and three relocated replays: 133 oracle launches in
that complete recipe. Those seven separate checks do not charge the reduction's
260-invocation budget. Direct application decision probes are not oracle launches.

Ordinary/variant fresh oracle time was 34.357/39.765 seconds; estimated other
reduction work was 3.752/4.610 seconds. Runs overlapped validation activity, so the
6.266-second wall-time difference is not an isolated storage performance result.
Declared data, retained rows, search decisions and invocation totals agree.
The alternate source/final fixtures are smaller because their storage structures
differ. Full variant acceptance remains an explicit recipe, avoiding another large
reduction in every hosted job. CI adds its genuine eight-row wheel smoke.

Exact source commands:

```text
.venv/Scripts/python.exe tests/milestone_smoke.py --directory .validation/m2c-six-applications-fresh
.venv/Scripts/python.exe tests/milestone_smoke.py --directory .validation/m2c-without-rowid-billing-fresh --examples composite_billing --without-rowid-billing-fixture
```

Evidence includes per-table counts, all source/bundle SHA256 maps, timings and
actual outcomes in those directories' `measurements.json` and
`.validation/m2c-billing-validation-ledger.json`. Example before/after hash evidence:

| Captured asset | SHA256 (unchanged across its inspection/replay operations) |
| --- | --- |
| Ordinary billing source | `bf0f870a8c6d092829003fd5f98ca45e8b71b614209c15d180123440e23ed6f6` |
| Ordinary compact fixture | `64f539818d456b9377a10dffcd232d46b86cb7791814409614e7738089e2d887` |
| Alternate billing source | `0a23220a11cb335ad8b9a3265788ada1e76d7eddccd9e97ca7d9a7c416a6290b` |
| Alternate compact fixture | `b6e02dca67ac0b1534a4e1957125f9085f22bf0975cda1237789fca5753278c3` |
| Alternate manifest | `b3c8c4970fd2cbf3f42800d55391267be0331d0f18c51ed5b9859a909c290c5a` |
| Alternate report | `3d41dbbe9df88b08cbfb22f5f576a6d5012e2a0b2be5ac8157cf7b98cceabaef` |

The hash assertion is equality before and after operations on each supplied asset;
source and reduced-fixture hashes are expected to differ.

## Genuine historical bundle compatibility

The recipe archived each reviewed commit and executed its own source/generator
with an explicit import-location assertion, creating genuine version-1 evidence:

| History | Archived commit | Original -> final | Historical executions | New replay |
| --- | --- | ---: | ---: | --- |
| Pre-M1b INTEGER | `ba40d64db748d974c36666294a1cc4500c79c25f` | 11 -> 3 | 18 | 3 TARGET_FAILURE |
| Accepted M2a TEXT | `d60c79c07ae12666af9572ced69edc3b9523ce17` | 10 -> 10 | 23 | 3 TARGET_FAILURE |
| Accepted M2b composite | `d70edac43c22efe3df643b821af1c51ec756a945` | 8 -> 8 | 15 | 3 TARGET_FAILURE |

Default/explicit JSON preserved the original report exactly; text inspection and
relocated replay passed with unchanged source/bundle hashes. No historical report
was hand-created, migrated or rewritten. Commands used
`tests/compatibility_smoke.py --directory <new-directory>` with default history,
`--history m2a-text` and `--history m2b-composite`. Evidence:
`.validation/m2c-pre-m1b-v1-fresh/`, `.validation/m2c-m2a-text-v1-fresh/`,
`.validation/m2c-m2b-composite-v1-fresh/`; each retains `generation.json` and
`compatibility-result.json`, including actual archived source hashes.

The current Linux-built pure-Python wheel also inspected and replayed all three
genuine historical bundles from an external Windows virtual environment. An
isolated `-I` assertion confirmed `Lib/site-packages/reproseed/__init__.py`.
Only each captured manifest and explicit artifacts were copied, their historical
hashes were checked, and original tool-owned source/bundle paths were unavailable
during operations. Default/explicit JSON matched the original reports exactly;
text inspection and three executed TARGET_FAILURE replay results passed for every
history. Original and copied bundle/source hashes stayed unchanged. Evidence:
`.validation/m2c-installed-history/result.json`, including wheel hash, exact
commands, runtime, hashes and per-history outcomes.

## Clean-copy platform and installed-wheel validation

Clean copies contain only tracked/nonignored source files, with per-file SHA256
records and no initial `.validation`, `.venv` or `dist`. They explicitly prepare
the CI test temporary parent. Windows and Linux pipelines perform locked sync,
Ruff lint/format, mypy, the additional Linux static target, full pytest, wheel/sdist
builds, distribution inspection, the exact CI external wheel lifecycle, isolated
site-packages import verification and explicit installed full-six/alternate
measurements. Command logs and hashes are retained in
`.validation/m2c-windows-evidence/` and `.validation/m2c-linux-evidence/results/`.

Linux used the cached network-disabled disposable image
`ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim`, image SHA256
`b27bdf6aad179578bdd6cefb1316dbd9287cf36feaac5c167287dbe27b6a6fff`.
Runtime: Linux 6.18.33.2-microsoft-standard-WSL2, x86_64/glibc 2.36, CPython 3.12.11
(GCC 12.2.0), SQLite 3.40.1, uv 0.8.22, Ruff 0.17.0, pytest 9.1.1, mypy 1.20.2
and build 1.6.1. All listed pipeline stages passed. Full pytest:
**590 passed, 25 skipped in 111.17 seconds** (recorder wall time 111.787 seconds),
with no warnings. All skips are existing Windows-specific junction, Job Object,
taskkill/fallback/API ownership and readonly-attribute cases. Real POSIX SIGINT,
process groups and executable-mode tests ran here; injected Windows interruptions
are distinct evidence. This local Linux run is not a hosted Ubuntu gate.

Linux distribution inspection verified no runtime dependency metadata, exact
packaged source bytes and exclusion of databases, sidecars, logs, environments,
caches and validation evidence. The exact CI external wheel workflow passed
threshold, ten-row TEXT, eight-row ordinary composite and eight-row mixed-layout
cases in 15.421 seconds. The separate external wheel import came from
`/tmp/.../origin-installation/lib/python3.12/site-packages/reproseed/__init__.py`.
All six full installed applications reproduced the source row/invocation counts
in 51.732 seconds; full alternate billing passed in 11.308 seconds. Its reduction
alone took 9.125 seconds versus 8.463 seconds ordinary, again an observation under
concurrent activity. All installed cases passed diagnosis, inspections, independent
application assertions, retained schema/values/FKs, pristine confirmations and
three fresh relocated replays with unchanged hashes. No editable source import
substituted for the wheel.

Windows used Windows 10 build 19045, AMD64, CPython 3.12.15 (MSC 1944),
SQLite 3.53.1, uv 0.13.0 (`4ecd0eff2`, 2026-10-09), Ruff 0.17.0, pytest 9.1.1,
mypy 1.20.2 and build 1.6.1. Locked sync, lint/format, both static mypy targets,
full pytest, builds, package-content checks, the exact CI installed-wheel workflow
and isolated import origin passed. Full pytest: **609 passed, 6 skipped,
1 warning in 646.64 seconds** (recorder wall time 648.171 seconds).
The six existing skips were two host symlink privilege failures (WinError 1314),
POSIX SIGINT workflow/diagnosis, executable mode and signal return-code cases.
These POSIX cases and symlink paths ran on Linux. No new skip/xfail shortcut was
introduced. Existing deterministic interruption, Job Object and fallback cleanup
tests ran on Windows; this does not establish real console Ctrl+C behavior.

The warning was
`test_second_interrupt_in_real_oracle_cleanup_aborts_and_preserves_launch`:
`oracle cleanup incomplete: taskkill exit (code 128)`. Its interruption/accounting
assertions passed, and the runtime oracle module is unchanged. This is recorded
cleanup uncertainty, not a claim that every interrupted cleanup succeeded.
Windows's exact CI external-wheel workflow passed in 44.437 seconds, including
all four small lifecycles. Isolated import origin was the OS-temp environment's
`origin-installation/Lib/site-packages/reproseed/__init__.py`. Windows's additional
full installed-six measurements passed in 169.469 seconds; the full alternate
billing run passed in 33.625 seconds. Counts, invocations, accepted reductions,
cache hits and zero invalid/unresolved candidates matched the source measurements
and Linux installed results. All retained values/schema/metadata/layouts/FKs and
source/bundle hashes passed, with fresh compact-final and relocated confirmations.

The frozen-source Windows and Linux distribution builds predated this completion
report. Final packaging rebuilds the current checkout after recording these
results, includes `docs/m2c-completion.md` in the sdist, compares every runtime
module to the already tested wheels, and rechecks metadata/content exclusions.
Final build/content evidence is retained in `.validation/m2c-final-packaging/`.

## Scalar sorting measurement and final review

The current and accepted M2b `row_sort_key` source is byte-identical (SHA256
`3068e65e424ffc9e3e963e06432b57113db79af7d6d4372894235d7d04cec25a`). An interleaved
benchmark used the same fixed shuffled 4,248 reservation identities, 15 alternate
ordering repeats of 20 sorts, with GC disabled only during timing. Windows 3.12.15
median time was M2b 9.206 ms versus current 10.457 ms. Samples overlapped broadly
(6.234-15.994 versus 5.948-15.494 ms) during concurrent validation. Identical source
and ordering establish no new sorting implementation or allocation mechanism;
these noisy timings do not establish a new M2c cost. M2b's recorded scalar token
cost remains documented. No generalized sort refactor was introduced. Evidence:
`.validation/m2c-scalar-sort/measurements.json` with source/archive hashes.

Independent final code and test reviews found no demonstrated adapter, identity,
FK, compaction, oracle/accounting, version-1 reader, scalar/composite cache or CI
defect. The final diff retains quoted/bound SQL, parent-driven comparisons, exact
declared values, coherent cancellation progress and compact-final confirmations.
No unsupported broader key family or storage-page identity was admitted.

## Intermediate attempts, limitations and final Git state

The default uv executable was absent from PATH; the repository's `.tools/bin/uv.exe`
was located. Default cache access was denied in the restricted session; locked
sync succeeded with a tool-owned cache and the existing 3.12 interpreter. Read-only
WSL enumeration and restricted Docker access were denied; approved local Docker
access enabled the requested disposable Linux execution. No system setting changed.

Initial root Ruff checks identified two overlong adapter lines and formatting
differences; formatting corrected them before behavioral validation.
A first clean-copy Windows lint run captured new tests before formatting finished;
it failed on long lines. The corrected frozen file was recopied, and all subsequent
lint/format checks passed. The initial focused lifecycle test loaded an obsolete
replay-field assertion while its correction was being written; its corrected rerun
passed. Two Linux harness attempts stopped before tests: copying into Docker's
precreated `/source` directory, then uv attempting index refresh despite networking
being disabled. The scratch-only harness now allows the empty destination and uses
explicit offline cache resolution. These were recorded harness/test-authoring
failures, not suppressed application failures or CI retry logic.
An independent ad hoc probe also first failed with a Python command-quoting
SyntaxError; its corrected quoted-identifier/storage-layout probe passed.

Linux/Python 3.14, hosted M2c jobs and real Windows console Ctrl+C were not run here.
Static mypy's Linux target is not runtime testing. Existing platform-specific skips
and actual warnings are documented with final full-suite results. Only authorized
synthetic subprocesses ran; source protection is tool behavior, not an OS sandbox.
This bounded subset is not all SQLite WITHOUT ROWID schemas, anonymization, global
minimality or a production-readiness claim. PostgreSQL, LLM integration, web UI,
release and publication remain outside M2c. A separate public-alpha readiness and
usability review is proposed next.

All milestone changes remain unstaged and uncommitted for Dan. Final branch/HEAD
remain `main` / `d70edac43c22efe3df643b821af1c51ec756a945`; the cached diff is empty.
Final Git status contains 18 modified files and two new files:

```text
 M .github/workflows/ci.yml
 M AGENTS.md
 M CONTRIBUTING.md
 M README.md
 M SECURITY.md
 M docs/architecture.md
 M docs/diagnostics.md
 M docs/roadmap.md
 M examples/composite_billing/README.md
 M examples/composite_billing/generate.py
 M src/reproseed/diagnostics.py
 M src/reproseed/sqlite_adapter.py
 M tests/compatibility_smoke.py
 M tests/milestone_smoke.py
 M tests/test_composite_keys.py
 M tests/test_realistic_oracles.py
 M tests/test_sqlite_adapter.py
 M tests/test_text_keys.py
?? docs/m2c-completion.md
?? tests/test_without_rowid.py
```

`tests/test_realistic_acceptance.py`, lockfiles, runtime version and dependencies,
historical completion reports, oracles/applications and the hosted matrix/action
pins/permissions are unchanged. Generated archives, databases, bundles, environments,
logs and package evidence stay ignored. Only the small alternate installed-wheel
CI workflow is added; a separate full variant remains explicit. Final diff checks
and independent review passed. Hosted M2c acceptance still requires Dan's subsequent
commit/push.
