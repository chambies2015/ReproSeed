# M2c architecture

The contract is: smaller fixture, same specified failure, independently replayable evidence.
"Same" is the configured exit/marker contract. ReproSeed does not infer semantic equivalence
between arbitrary crashes. The runtime uses Python 3.12+ standard-library modules only.

## Lifecycle

1. Parse strict version 1 TOML. Resolve source/assets against the configuration directory.
   Validate fields, portable names and explicit assets before launching code.
2. Open the source using mode=ro and acquire a private backup, including committed WAL.
   Incremental backup callbacks enforce a five-second deadline for lock retries/restarts.
3. Validate structural integrity, inspect schema/storage metadata and construct
   stable `(table, declared primary key)` identities plus reverse FK edges. Each table's
   metadata selects its ordered integer/text key component families; stored values never
   select the families. Composite foreign-key groups become complete tuple edges.
   Check foreign-key consistency after schema/storage acceptance so unsupported key
   declarations and values produce their specific errors before relational validation.
4. Confirm baseline three times, each using fresh staged database/assets. Abort on any
   outcome other than TARGET_FAILURE.
5. Remove deterministic chunks, then refine down to single-row seeds. Compute recursive
   dependent-child closure before candidate construction; a visited set terminates cycles.
6. Build each candidate from pristine snapshot state. Explicitly delete all excluded rows
   with FK actions disabled outside the transaction. Re-enable and validate integrity/FKs.
   Database-invalid candidates are recorded separately and do not execute the oracle.
7. Run disposable copies. Two fresh TARGET_FAILURE results are required for acceptance;
   conflicting confirmations are UNRESOLVED. Strictly fewer retained rows are required.
8. Materialize the best confirmed subset, compact with VACUUM INTO, validate, then execute
   three fresh copies of that exact final file, bypassing candidate caches.
9. Only on successful final verification, write replay configuration, report and SHA256
   manifest. Publish to an exclusively created directory without replacing existing files.

The oracle always receives a fresh db.sqlite3 and explicit supporting assets in its own cwd.
It may write these private copies. Such writes never become later candidate or export state.
Assets are frozen into the bundle-building directory before search, then restaged per trial.
The source is never checkpointed, vacuumed or changed by ReproSeed SQL. SQLite can use a
normal WAL shared-memory sidecar. An arbitrary oracle is not constrained by this tool policy.

## Supported schema

SQLite >=3.37 is required for table_list metadata. Supported user tables are ordinary or
STRICT rowid or WITHOUT ROWID tables with these bounded declared primary-key shapes:

| Family | Declaration and metadata | Actual stored values |
| --- | --- | --- |
| INTEGER | Exact declared INTEGER; ordinary rowid tables require a rowid alias, established by absence of a separate PK index; WITHOUT ROWID requires a declared ascending PK index | Non-NULL SQLite integers; negative, sparse and zero keys supported |
| TEXT | Exact declared TEXT; single-column PK index established by index_list/index_xinfo, with BINARY comparison | Non-NULL SQLite TEXT that decodes correctly to Python strings |
| Two-column composite | Exactly two ascending PK components, each exact declared INTEGER or TEXT; a unique nonpartial declared PK index matches their order and BINARY comparisons | Every INTEGER component is non-NULL SQLite integer; every TEXT component is non-NULL SQLite text that decodes safely |

Type-name case and surrounding whitespace are ignored; VARCHAR/CHAR and other text-affinity
spellings are outside M2c. INTEGER+INTEGER, INTEGER+TEXT, TEXT+INTEGER and TEXT+TEXT
composite shapes are supported. Inline and table-level single-column TEXT PKs are supported, with
or without explicit NOT NULL. An ordinary non-STRICT SQLite PK can permit NULL; this schema
is accepted only when every snapshot PK component is non-NULL and has the required storage.
This stricter identity policy applies even though SQLite may allow NULL in ordinary
composite PKs. STRICT tables are supported,
as is AUTOINCREMENT on an ordinary INTEGER rowid alias. Empty tables, empty strings, Unicode,
SQL quotes, embedded NULs and case-sensitive distinct text keys are supported. Identifiers
are quoted, including embedded quotes. See SQLite's [CREATE TABLE rules](https://www.sqlite.org/lang_createtable.html).

TEXT equality uses exact string identity, with no coercion, case folding or Unicode
normalization. The declared PK index and its key-column collation are checked using SQLite
[index_list and index_xinfo metadata](https://www.sqlite.org/pragma.html#pragma_index_xinfo).
An empty isolated in-memory schema probe derives the column's default collation through
a plain index, since a table-level PK can override the column collation. Both must be BINARY;
the adapter delegates this to SQLite instead of parsing CREATE TABLE with regular expressions.
Composite metadata follows table_xinfo PK ordinals, locates the declared PK through
index_list, and checks ordered key entries from index_xinfo. Entries whose key flag is zero
are auxiliary storage columns, not PK components; this includes ordinary rowid entries and
WITHOUT ROWID nonkey data columns. Unique/nonpartial origin, column identity, component count, ascending
order and comparison collations are checked even for empty tables. INTEGER composite
components are not rowid aliases; scalar INTEGER in an ordinary rowid table retains its
separate alias requirement. Every WITHOUT ROWID scalar/composite PK component must be
ascending; ordinary scalar TEXT handling retains its existing comparison policy.
NOCASE, RTRIM, custom collations, descending composite or WITHOUT ROWID components and unsupported PK index
metadata are rejected explicitly.
This restriction makes exact text dependency identities agree with the supported BINARY
comparison semantics; it does not approximate arbitrary SQLite comparisons. SQLite describes
its [storage classes, affinity and collations](https://www.sqlite.org/datatype3.html).

`PRAGMA table_list` supplies each table's WITHOUT ROWID storage flag. This metadata is
part of the table model; it does not change `(table, key)` equality, sort order or candidate
cache identities. A WITHOUT ROWID scalar INTEGER PK must have a unique nonpartial declared
PK index, unlike the ordinary rowid alias. Its PK components still come from table_xinfo
ordinals, and only index_xinfo key entries determine identity. Empty tables undergo the
same checks. See [SQLite table metadata](https://www.sqlite.org/pragma.html#pragma_table_list).

WITHOUT ROWID has no hidden rowid, and INTEGER PRIMARY KEY has integer affinity without
rowid-alias behavior. SQLite requires a declared PK and enforces NOT NULL on every
component; missing PKs, AUTOINCREMENT and NULL PK inserts fail in SQLite itself. Inserts
do not update last_insert_rowid(), rowid-based incremental BLOB I/O cannot open these rows,
and sqlite3_update_hook does not report their changes. ReproSeed relies on declared values
and metadata throughout. These engine restrictions are distinct from ReproSeed rejecting
SQLite-created schemas outside the bounded supported shapes. See
[SQLite's WITHOUT ROWID differences](https://www.sqlite.org/withoutrowid.html#differences_from_ordinary_rowid_tables).

Foreign keys must reference the complete supported parent's declared PK, explicitly in
the parent's PK order or implicitly by omitting the target column list. foreign_key_list
rows are grouped by constraint id and ordered by component sequence. Cardinality and
all targets are checked as one constraint; a two-column FK is never two scalar edges.
The parent component family determines the policy, independently of the child table's PK:
INTEGER parents require integer-affinity child columns (declared type contains INT) and
actual integer or NULL values; TEXT parents require exact declared TEXT child columns and
actual TEXT or NULL values that decode correctly. Scalar-keyed children may reference
composite parents, and composite-keyed children may reference scalar or composite parents.
Multiple scalar/composite FKs, self-references, mixed-family chains and cycles are supported,
including either FK direction between rowid and WITHOUT ROWID tables.
If any child FK component is NULL, SQLite requires no parent; ReproSeed creates no edge for
that group. This includes both fully NULL and partially NULL tuples. Non-NULL child
components still undergo their declaration/storage checks even when another component is
NULL. Independent FK ids remain separate groups. Otherwise the complete
typed tuple identifies the parent, keeping tenant-scoped keys distinct. Reverse edges are
indexed by declared parent identity; visited-set closure traversal terminates cycles.
SQLite [uses the parent's affinity and collation for FK equality](https://www.sqlite.org/foreignkeys.html#fk_basics);
M2c conservatively rejects cross-affinity declarations and unsupported parent collations
rather than changing values or constructing incomplete dependency edges. A parent removal
also removes every dependent child recursively, irrespective of ON DELETE actions. Retained
values are never changed to NULL or rewritten by cascading actions.

Missing or three-or-more-column PKs, BLOB/REAL/NUMERIC/other declared PK components,
NULL or wrong-storage PK components,
descending INTEGER PRIMARY KEY forms that do not alias rowid, unsupported FK declarations,
non-PK UNIQUE FK targets, reordered explicit targets, mismatched FK cardinality,
descending composite or WITHOUT ROWID PK components, virtual/shadow tables,
triggers and generated/hidden columns fail explicitly. Malformed text and unavailable custom
collations produce handled database errors. Internal SQLite tables are excluded from row
reduction. Declared table/index/view SQL and relevant metadata are preserved,
including user_version, application_id, page size, encoding, auto_vacuum and sqlite_sequence.
Views/indexes are preserved, not silently dropped. Application dependencies such as custom
SQLite functions/collations may cause validation or private construction to fail and are not
automatically loaded. Arbitrary SQLite schemas are deferred.

Scalar keys retain `int | str`; composite keys are `tuple[int | str, int | str]` in declared
PK order. Row identities are `(table, key)`, for example `("invoices", ("tenant-a", 42))`.
This differs from `("invoices", ("tenant-b", 42))`; text `"42"` never becomes integer `42`.
A table has fixed metadata-established component families, including when empty.
Explicit deterministic sort tokens preserve scalar numeric/text ordering and compare
composite components in declared order without mixed-type TypeError. Candidate-cache
identities remain exact, hashable retained identity sets. Reports record counts
and confirmation evidence, not individual retained identities; configuration, bundle,
report, replay and diagnostic formats remain version 1.

Candidate deletion quotes each PK column and binds each component in PK order, using
explicit BINARY comparisons where needed. A composite deletion combines both predicates
with AND; it cannot remove another tenant's row sharing an invoice number. All excluded
rows are removed from a pristine private snapshot with FK actions disabled only there,
then integrity and foreign keys are checked again. Retained values/schema are not rewritten.

M2c preserves retained declared column values and keys. Ordinary TEXT and composite PKs
are separate from hidden rowids, which [SQLite may change during VACUUM](https://www.sqlite.org/rowidtable.html).
WITHOUT ROWID tables have no hidden rowid: their declared PK supplies storage identity.
Backup/private deletion/VACUUM INTO preserve the original storage declaration, indexes and
metadata; no alternate reconstruction or deletion through SELECT rowid is needed.
The reducer never substitutes hidden rowids for declared keys. Three fresh final confirmations
of the exact VACUUM INTO output remain authoritative for the compact fixture's failure;
rowid-sensitive application behavior is not presumed to survive compaction.

## Oracle outcomes

| Outcome | Contract |
| --- | --- |
| TARGET_FAILURE | Normal exit with configured nonzero code AND exact UTF-8 whole-line marker on configured stream |
| PASS | Exit zero without marker on the configured stream |
| UNRESOLVED | Wrong failure/exit, missing marker on failure, zero with marker, conflicting confirmations, signal, timeout, launch/staging/read failure or output limit |

Markers are compared as UTF-8 bytes, accepting LF/CRLF and a final complete line without a
newline. Substrings or surrounding extra characters do not match. Output on the unselected
stream does not satisfy the contract. Combined output byte limits cover both streams. No raw
output/row values are stored. No majority vote occurs. --allow-exec acknowledges execution;
it is not a sandbox. See SECURITY.md for platform cleanup and data-sharing boundaries.

Oracle cleanup uses one monotonic 1.5-second allowance for tree completion waits,
reader shutdown and retries of actual transient Windows directory-deletion failures.
For an assigned Windows Job, it captures member process handles before requesting
termination, captures newly associated members afterward and waits for process signals.
Exiting members can disappear from the Job list before their process objects signal;
waiting only for the launcher is insufficient. Membership checks use only this invocation's
Job, and every acquired observation handle and the Job handle is released once. Neither
Job-handle signaling nor an ActiveProcesses count supplies the process completion condition.
Readers stop and join,
pipes close, and only the exact disposable directory is removed. Successful cleanup does
not sleep; exceptional obstruction warns without changing the failure contract. The
allowance bounds waits/retries, not an externally stalled synchronous OS call. See
[M1b.1.2 evidence](m1b1-2-completion.md) for natural failures and deterministic boundaries.

## Search, budgets and uncertainty

Chunks begin with the whole universe; unsuccessful chunks refine toward individual seeds.
Stable table/key ordering and dependency closures make the search deterministic for stable
oracle outcomes. Equivalent retained identity sets are cached within a run. Only confirmed
TARGET_FAILURE, PASS and database-invalid results are reusable; UNRESOLVED is not cached.
No result from a cache replaces final verification. Budgets count actual process executions,
including baseline and confirmations; three executions are reserved for final verification.
Each search trial reserves room for two possible confirmations before beginning. Thus a
single remaining search slot can remain unused. Empty fixtures and irreducible fixtures
are valid results if final verification succeeds. Budget exhaustion or search interruption
preserves the best confirmed subset, then attempts final verification.

The reducer publishes progress through one frozen checkpoint containing the retained rows
and the committed lengths of append-only attempt and acceptance logs. A progress transition
appends complete records provisionally, then replaces the checkpoint reference. A handled
KeyboardInterrupt returns only the prefixes named by that checkpoint;
provisional tails do not become report history. Before publication the previous confirmed
selection survives, and after publication the newer selection and its acceptance evidence
survive together. Cache hits are derived from the returned committed attempts, as are the
workflow's invalid/unresolved summaries. Each transition appends small records and replaces
one checkpoint; it does not copy the accumulated history on every attempt. Evaluation and
oracle effects remain separate from this publication, and actual executions are not undone
when a pending search record is abandoned. Search ordering and normalized caching are unchanged.

Reports include original/final table counts, actual executions, attempt classifications,
confirmation records, accepted size changes, cache hits and a precise termination reason.
An exhausted single-row closure pass is not proof of global minimality, especially with
unresolved trials. Baseline/final failures publish no verified bundle. Reproducibility still
depends on external executables, interpreter, dependencies and environment; those are not
captured as a universal execution environment.

## Diagnosis

`diagnose --config ...` is a separate readiness entry point with default readable text and
opt-in JSON. `diagnostics.py` loads the same strict version-1 configuration, checks and copies
explicit assets privately, acquires a WAL-aware read-only-source snapshot and calls
`DatabaseModel.from_database` unchanged. It does not implement a second schema validator or
invoke reduction. Static checks return actual table counts and structural suitability;
oracle execution and baseline reproduction remain explicitly untested.

`--allow-exec` uses the existing `InvocationCounter` and `run_oracle` for exactly three fresh
baseline attempts unless interruption or hard nonlaunch prevents completion. Executed PASS
and UNRESOLVED attempts do not short-circuit the three observations or count as confirmations.
The privately frozen database/assets are restaged per invocation; application mutations
cannot become later baseline inputs. All three TARGET_FAILURE outcomes establish only the
baseline now, with no promise of successful search or final verification.

The [diagnostic document](diagnostics.md) has its own `diagnostic_version = 1`; report.json
and replay.toml remain version 1 unchanged. Diagnostic metadata describes actual completed
outcomes, known executions, known nonlaunches and uncertain interrupted launches. A further
interruption during counter recovery sets accounting completeness false and exits 130.
Missing result metadata is never invented. JSON remains parseable for invalid inputs and
handled interruption; curated cause codes avoid echoing source paths or configuration
secrets. Text escapes terminal controls and explains why an exit code alone is insufficient.
No bundle or evidence file is created beside user inputs. Database checks run in the order
integrity, schema/storage/dependency acceptance, then foreign-key consistency. A schema
rejection after a completed integrity check leaves FK validity untested. Unavailable custom
collation or malformed-text errors can prevent that check from establishing a result;
diagnosis conservatively leaves integrity validity untested for those causes.

Version-1 evidence validation checks required typed fields and nested records, supported
outcomes/termination reasons, nonnegative finite durations, table-name/count consistency,
sequential attempt references and the strictly decreasing accepted-reduction chain. Baseline
and final records each require exactly three executed TARGET_FAILURE confirmations with the
configured exit code; accepted candidates require two such confirmations. Actual booleans
and integers are distinguished, so `true` is not a count or version. Unknown fields are
rejected at the report, oracle-result, attempt, accepted-reduction and interrupted-record
levels. Report and replay budget metadata must agree, and charged budget cannot exceed its
configured limit. Evidence validation is separate from text formatting.

Cached attempts can repeat earlier confirmation records, including their `executed` flags;
those records are reused evidence, not additional subprocess executions. Validation requires
matching prior uncached evidence, but version 1 lacks candidate identity sets, so matching
counts/records do not establish identical retained row identities. Interrupted records
distinguish known executions, known nonlaunches and unknown launches. Charged budget is known
executions plus unknown launches. Cancellation during evaluation can discard the first
completed confirmation; cancellation after an evaluation returns but before it is recorded
can omit both. Validation checks the corresponding bounded accounting interval. Version 1
cannot always reconstruct an exact execution ledger; it preserves uncertainty without
inventing missing executions or treating historical records as independently observed.

## Bundles and CLI exits

Version 1 bundles contain fixture.sqlite3, replay.toml, explicit assets, report.json,
README.md and manifest.json. Manifest SHA256 hashes cover all required artifacts except
the manifest itself. Runtime/tool versions are recorded. The writer retains this version-1
format; display-only row totals and percentages are derived during text inspection.

Bundle construction first creates one exclusive private staging parent beside the intended
output. A denied mkdir propagates before snapshotting or oracle execution. This avoids
Windows tempfile retrying ACL-denied mkdirs when its os.access check claims the parent is
writable. Existing portable temporary-directory cleanup runs inside that owned parent;
cleanup must preserve an active interruption/error rather than replace it with a directory
removal error. Publication still uses exclusive output creation and never owns a preexisting
output or staging-name collision. Interrupted cleanup can leave private temporary data;
temporary state is not securely erased.

Inspection and replay share a private acquisition lifecycle:

1. Read bounded manifest metadata, validate its version/shape and declared portable artifact
   names, and reject traversal, symlinks, junctions and reserved-path conflicts.
2. Reject `fixture.sqlite3-wal`, `fixture.sqlite3-shm` and `fixture.sqlite3-journal` alongside
   the finalized fixture, including empty sidecars. Do not incorporate or delete these files.
3. Copy only the declared payload to a tool-owned temporary directory, preserving supported
   POSIX executable-file behavior, and compare copied bytes with the captured manifest hashes.
4. Parse the copied replay configuration and report. Require known versions, an exact asset
   list and consistent recorded evidence. No oracle executes before all checks succeed.
5. Make a separate private database copy for supported-schema inspection, integrity and
   foreign-key checks, and comparison of actual table counts with report `final_counts`.
6. Inspect this validated data, or run three replay confirmations with fresh disposable
   databases and asset copies sourced from the verified private payload. Keep its lifetime
   explicit and clean up tool-owned temporary directories afterward.

Once acquisition succeeds, replay does not reread original configuration, assets or fixture.
Oracle mutations of one invocation cannot change pristine payload bytes or later trials.
The original bundle database is not opened for SQLite checks that could create sidecars.
A normal reduction source with committed WAL remains supported by its separate snapshot
contract; a finalized bundle is a static artifact.

JSON uses standard-library hooks: duplicate keys and non-finite numbers are rejected, actual
reads are bounded at 64 MiB, and nesting beyond 64 levels is rejected. Replay configuration
actual reads are bounded at 1 MiB. Malformed UTF-8/JSON, unsupported versions and wrongly typed
metadata produce actionable bundle errors. JSON writes reject non-finite serialization.

`inspect ./bundle` and `inspect ./bundle --format json` retain the report's existing JSON
shape. `--format text` summarizes validated counts, budget, recorded confirmations and search
termination without listing the attempt history. It escapes terminal controls in displayed
strings, exposes no row values or raw process output, and explicitly says no oracle executed.
Inspection needs no execution acknowledgement and leaves supplied bundle files unchanged.

Keep four different claims separate: copied bytes match the captured manifest; recorded
evidence is structurally consistent; the fixture is structurally valid and agrees with final
counts; and a new replay reproduced the configured target in this invocation. The first three
do not establish the fourth. Neither hashes nor consistent metadata authenticate an author
or prove that a historical execution occurred. Private acquisition prevents execution from
drifting away from copied, hashed bytes; it is neither an OS sandbox nor complete immunity
to hostile-filesystem races or arbitrary access to the process/private temporary directory.
Other application dependencies remain external; the demos need Python and installed ReproSeed.

CLI codes differ from the oracle's expected failure code: 0 means verified reduction,
successful inspection or TARGET_FAILURE replay; 1 means baseline/final verification failed
or replay was PASS/UNRESOLVED; 2 means usage/configuration/schema/filesystem/bundle error;
130 means interrupted before completing verification. An interrupted search can still
return 0 if its preserved fixture passes final verification; report.json records interruption.

M2d curates input/configuration/schema/filesystem stderr through the diagnostic cause
mapper and adds human recovery guidance. Missing/unreadable configuration is distinguished
from malformed TOML, and snapshot timeouts retain their specific cause. Residual bundle and
verification text escapes terminal controls. Successful command JSON, report/replay version
1 and diagnostic JSON version 1 retain their existing shapes and exit meanings.

## Cancellation boundaries

One handled search interruption stops further search and recovers the checkpoint's coherent
confirmed selection. The workflow materializes that selection from pristine snapshot state,
compacts it and confirms three fresh copies of the exact exported fixture. No cached or partial
confirmation supplies final evidence. A bundle accepted by the strict reader is published only
after all three final outcomes establish TARGET_FAILURE. Before a verified baseline, during
compaction/finalization or during final verification, interruption may abort with no verified
bundle. A second interruption during counter recovery propagates through the reducer's
search handler and aborts with CLI exit 130; an uncharged invocation cannot be salvaged into
a verified bundle. A further interruption during graceful finalization also propagates and
may abort. If another interruption arrives while the reducer prepares its unresolved
attempt record, the outer search handler can discard that provisional record and return the
same coherent checkpoint. Neither path retries indefinitely. Pre-existing output is preserved
and tool-owned partial output is removed where possible.

Cancellation during staging does not count as an execution. Cancellation after a confirmed
launch counts once. If cancellation interrupts Popen construction itself, launch is unknown;
the report separates unknown_interrupted_launches from actual oracle_invocations and charges
each unknown launch conservatively against the budget. Interruption records are unresolved.
The oracle updates an optional caller-owned invocation state with known nonlaunch, unknown
construction or confirmed execution before returning; existing three-argument callers still
work. A returned process handle establishes execution and enters bounded cleanup even if an
interruption precedes the normal executed-state assignment. The counter uses the shared state
if interruption occurs after oracle completion but before its return value is transferred.
It publishes count, unknown-launch charge and interruption evidence together through one
immutable accounting reference, including the invocation identity to prevent charging the
same execution twice.

A further interruption during oracle cleanup carries an abort flag alongside the existing
launch evidence. The counter records that invocation once, then raises AbortReduction to
bypass search salvage. This flag is internal and adds no version-1 report field.
Normal accounting transitions replace a small state object; interruption evidence uses a
linked history materialized only when requested, avoiding repeated history copies. The search
checkpoint cannot roll back this accounting. Version 1 still has the bounded
omitted-confirmation limitations described above; no full execution ledger is invented.

Regression coverage injects one-shot exceptions at publication and accounting boundaries,
including the first and second candidate confirmations. Real SQLite/subprocess workflow tests
exercise acceptance and cache-hit interruption through finalization, default JSON/text
inspection and relocated three-confirmation replay, with source and bundle immutability
checks. A bounded POSIX signal subprocess smoke is separate from deterministic injection;
the [M1b.1.1 completion report](m1b1-1-completion.md) records actual platforms, versions and skips.
[Python's signal exception note](https://docs.python.org/3.12/library/signal.html#note-on-signal-handlers-and-exceptions)
explains that KeyboardInterrupt can arrive between operations. These tested boundaries do
not establish immunity to every asynchronous exception, forced termination, power loss or
hostile process interference. Bounded process cleanup retains the platform caveats in SECURITY.md.

## Primary references

- [SQLite backup API](https://www.sqlite.org/backup.html)
- [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html)
- [SQLite PRAGMAs](https://www.sqlite.org/pragma.html)
- [SQLite CREATE TABLE and primary keys](https://www.sqlite.org/lang_createtable.html)
- [SQLite WITHOUT ROWID differences](https://www.sqlite.org/withoutrowid.html)
- [SQLite rowid tables and hidden rowid stability](https://www.sqlite.org/rowidtable.html)
- [SQLite datatype affinity, storage classes and collations](https://www.sqlite.org/datatype3.html)
- [Python 3.12 sqlite3](https://docs.python.org/3.12/library/sqlite3.html)
- [Python 3.12 subprocess](https://docs.python.org/3.12/library/subprocess.html)
- [Python 3.12 signal exceptions](https://docs.python.org/3.12/library/signal.html#note-on-signal-handlers-and-exceptions)
- [Python 3.12 JSON](https://docs.python.org/3.12/library/json.html)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Windows PeekNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe)
