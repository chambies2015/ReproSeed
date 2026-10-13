# M1b.1 architecture

The contract is: smaller fixture, same specified failure, independently replayable evidence.
"Same" is the configured exit/marker contract. ReproSeed does not infer semantic equivalence
between arbitrary crashes. The runtime uses Python 3.12+ standard-library modules only.

## Lifecycle

1. Parse strict version 1 TOML. Resolve source/assets against the configuration directory.
   Validate fields, portable names and explicit assets before launching code.
2. Open the source using mode=ro and acquire a private backup, including committed WAL.
   Incremental backup callbacks enforce a five-second deadline for lock retries/restarts.
3. Validate structural integrity and foreign keys, inspect schema metadata and construct
   stable `(table, declared integer primary key)` identities plus reverse FK edges.
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

SQLite >=3.37 is required for table_list metadata. Supported user tables are ordinary rowid
tables with exactly one declared INTEGER PRIMARY KEY that aliases rowid. STRICT and
AUTOINCREMENT tables are supported. Primary keys may be negative, sparse or zero. Tables
can be empty or unrelated. Identifiers are quoted, including embedded quotes.

Foreign keys must be single columns with integer affinity (declared type contains INT),
referencing the supported parent's declared PK explicitly or implicitly. Non-null actual
stored FK values must be integers, even when SQLite comparison/coercion would accept another
storage type. Nullable references, self-references and cycles are supported. A parent removal
also removes every dependent child recursively, irrespective of ON DELETE actions. Retained
values are never changed to NULL or rewritten by cascading actions.

Missing/composite/noninteger PKs, descending INTEGER PRIMARY KEY forms that do not alias
rowid, unsupported FK types/targets/composites, WITHOUT ROWID tables, virtual/shadow tables,
triggers and generated/hidden columns fail explicitly. Internal SQLite tables are excluded
from row reduction. Declared table/index/view SQL and relevant metadata are preserved,
including user_version, application_id, page size, encoding, auto_vacuum and sqlite_sequence.
Views/indexes are preserved, not silently dropped. Application dependencies such as custom
SQLite functions/collations may cause validation or private construction to fail and are not
automatically loaded. Arbitrary SQLite schemas are deferred.

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

Reports include original/final table counts, actual executions, attempt classifications,
confirmation records, accepted size changes, cache hits and a precise termination reason.
An exhausted single-row closure pass is not proof of global minimality, especially with
unresolved trials. Baseline/final failures publish no verified bundle. Reproducibility still
depends on external executables, interpreter, dependencies and environment; those are not
captured as a universal execution environment.

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

Cancellation during staging does not count as an execution. Cancellation after a confirmed
launch counts once. If cancellation interrupts Popen construction itself, launch is unknown;
the report separates unknown_interrupted_launches from actual oracle_invocations and charges
each unknown launch conservatively against the budget. Interruption records are unresolved.

## Primary references

- [SQLite backup API](https://www.sqlite.org/backup.html)
- [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html)
- [SQLite PRAGMAs](https://www.sqlite.org/pragma.html)
- [Python 3.12 sqlite3](https://docs.python.org/3.12/library/sqlite3.html)
- [Python 3.12 subprocess](https://docs.python.org/3.12/library/subprocess.html)
- [Python 3.12 JSON](https://docs.python.org/3.12/library/json.html)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Windows PeekNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe)
