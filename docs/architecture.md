# M0/M1a architecture

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

## Bundles and CLI exits

Version 1 bundles contain fixture.sqlite3, replay.toml, explicit assets, report.json,
README.md and manifest.json. Manifest SHA256 hashes cover all required artifacts except
the manifest itself. Runtime/tool versions are recorded. Replay requires required files,
known manifest/report versions, matching asset lists, safe paths and hashes before running
three fresh trials. inspect validates/reads without executing code. Hashes are integrity
checks, not authentication. Other application dependencies remain external; the supplied
demos need only Python and installed ReproSeed.

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
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Windows PeekNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe)
