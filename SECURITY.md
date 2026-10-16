# Trust boundaries

The optional [pytest bridge](docs/pytest-oracles.md) runs only when explicitly selected
and acknowledged. Its target file is bounded and strict; exact structured exception
type/message and complete successful setup/teardown are required. Missing/unsupported
pytest fails before importing target/conftest code. Static diagnosis and inspection
do not import pytest. Collection itself executes code. The reserved `reproseed_db`
fixture uses an additional owned snapshot and rejects local overrides.

Controlled root/config/conftest boundaries and disabled third-party autoload avoid
inheriting an unrelated pytest ecosystem. Explicit external plugins, reruns, xdist,
custom collectors and skip/xfail behavior are unsupported. Output rendering/capture
is disabled; remaining pytest/test output is discarded in bounded streaming chunks
while fixed output-volume records keep excessive output visible to the outer byte
limit. Bridge diagnostics use fixed reasons. This is not a general output sanitizer:
trusted code retains OS access and can bypass normal output mechanisms. Included
tests/application/target/conftest files remain explicit assets. Installed ReproSeed
and pytest invoked via `-m` are external dependencies outside manifest authentication.

ReproSeed runs the exact command selected in configuration. reduce, replay and executable diagnose require
--allow-exec because that command executes with your OS permissions and inherited
environment. shell=False prevents shell interpretation; it does not make code safe.
Inspect assets and argv before running an unfamiliar bundle. Temporary working directories
and disposable database copies are state hygiene, not operating-system isolation.

`diagnose` without `--allow-exec` never launches configured code. It validates a private
source snapshot with the same restricted schema and integrity/FK checks as reduction.
Static success does not establish reproduction. Executable diagnosis requires three fresh
target confirmations, preserves actual failed classifications and interrupted-launch
uncertainty, and creates no replay bundle. Assets are frozen privately before confirmations
and copied afresh with the database for each attempt. Diagnostic JSON/text omit absolute
paths, argv and marker values, rows, raw process output and inherited environment values.
Table names and fixed diagnostic causes remain visible; text escapes terminal controls.

The shared schema model supports exact INTEGER rowid-alias, exact TEXT/BINARY primary
keys and exactly two ascending INTEGER/TEXT PK components in ordinary rowid tables.
WITHOUT ROWID tables support one or two exact INTEGER/TEXT components with a validated
ascending declared PK index, including scalar INTEGER whose key is not a rowid alias.
Storage layout comes from SQLite metadata and never becomes a substitute row identity.
Each composite component must
have its exact non-NULL integer/text storage, with BINARY TEXT index/default comparisons.
Every TEXT PK must be a non-NULL stored TEXT value that decodes to a Python string;
ordinary SQLite declarations that permit NULL are accepted only for snapshots with valid
actual keys. TEXT references require stored TEXT or NULL in exact declared TEXT columns.
INTEGER references retain integer-affinity declarations and stored integer or NULL values.
The referenced parent's component families determine this check. Composite FK constraints
are one ordered group, explicitly or implicitly targeting the complete declared parent PK.
Any NULL child component means no required parent and no dependency edge; NULL parent PK
components are rejected. Non-NULL child components are validated even when another FK
component is NULL. These checks apply to mixed rowid/WITHOUT ROWID dependencies in either
direction. Unsupported cardinality, reordered/non-PK targets and descending composite or
WITHOUT ROWID PK components are rejected before launch, including in empty-table declarations.
Unsupported collations, malformed
text and cross-affinity declarations are rejected; keys are never normalized to force support.

ReproSeed itself opens the source read-only, snapshots with the SQLite backup API and
issues no source writes, checkpoint, VACUUM or journal-mode changes. A read-only WAL
connection can use SQLite's normal shared-memory sidecar. An arbitrary oracle can still
reach other files, networks or credentials accessible to the account. Run untrusted code
in an external OS sandbox or restricted account that you configure yourself.

Use a disposable local fixture. Concurrently changing production databases are outside
the supported workflow. Snapshot acquisition has a five-second deadline. Normal SQLite
locking and filesystem behavior still apply. Backup includes committed uncheckpointed WAL
contents; immutable mode is deliberately not used.

## Execution and cleanup

The per-invocation deadline includes process runtime and pipe EOF. Combined stdout/stderr
capture has a byte limit; no arbitrary output is retained or serialized. Diagnostics contain
classification, reason, exit code, byte count and duration. Inherited environment
values are not automatically serialized. Explicitly selected
assets and argv literals may contain credentials and must be reviewed before sharing.

On POSIX, processes start in a fresh session; cleanup kills their process group. A process
that deliberately detaches can escape this group. On Windows, the runner attempts assignment
to a kill-on-close Job Object and polls pipes with PeekNamedPipe. Cleanup captures member
process handles before requesting Job termination, captures new members afterward, and waits
for process signals before releasing those handles and closing the owned Job. Waiting only
for the launcher does not establish descendant completion. Assignment occurs after process
creation, so there is a startup race;
host job policies may reject assignment. Bounded taskkill /T /F plus direct process kill
provide best-effort fallback. Descendants that detach or outlive an unassigned parent can
escape. Cleanup and temporary-directory removal cannot guarantee removal of files held by
escaped processes. The runner returns within finite process/cleanup bounds rather than
waiting indefinitely for pipe EOF.

Tree waits, reader shutdown and actual transient Windows deletion retries share one
monotonic 1.5-second cleanup allowance. Successful cleanup has no unconditional delay.
Removal uses only the invocation's exact disposable root and does not traverse symlinks
or junction targets. A persistent lock, denied API operation or exhausted allowance emits
a cleanup warning; it does not replace cancellation or redefine the oracle outcome.
Synchronous OS calls themselves cannot be preempted by this allowance. A further interruption
during cleanup aborts salvage after recording known launch evidence once. See the
[M1b.1.2 completion report](docs/m1b1-2-completion.md) for exercised boundaries and limits.

Platform execution evidence belongs in the milestone
completion reports. The accepted M1a.1 hosted run covers Ubuntu/Python 3.12 and 3.14 and
Windows/Python 3.12 at its reviewed commit; it does not validate later working changes.

A handled first search interruption stops reduction and preserves a coherent confirmed
selection. Publication still requires compaction and three fresh TARGET_FAILURE confirmations
of the exact exported fixture. Cancellation before baseline verification or during finalization
can abort without publishing. A second interruption during invocation-accounting recovery
aborts through CLI exit 130, preserving the boundary between unfinished accounting and a
verified report; further interruptions are not swallowed indefinitely. Tool-owned partial
output is cleaned up where possible, and pre-existing output is never replaced.
Deterministic boundary injection tests this recovery behavior; real-signal coverage is reported
separately with its platform in the [cancellation repair evidence](docs/m1b1-1-completion.md).
[Python's signal exception note](https://docs.python.org/3.12/library/signal.html#note-on-signal-handlers-and-exceptions)
explains why KeyboardInterrupt can arrive between operations. This is no guarantee against
every asynchronous exception, forced termination, power loss or hostile process interference.

## Data and bundle sharing

Reduction's optional `--progress` and `--events` expose allowlisted aggregate
counts, lifecycle/outcome labels and fixed reason codes. They omit keys, row data,
table names, paths, command arguments, markers, environment and process output.
The JSONL file is exclusively created before oracle execution, outside the bundle;
it is not included automatically. It is bounded to 16 MiB and reserves a truncation
record. Sinks retain no complete in-memory history. Partial writes permanently
disable that sink; other sink failures similarly preserve accounting and search
state. Aborts can leave an owned partial log. Logs are unauthenticated diagnostics,
not a complete execution ledger, proof of reproduction or a resume point.
Synchronous writes can still stall at the OS level; path checks do not promise
hostile-filesystem race immunity. See [progress/events](docs/progress-events.md).

Candidate caches use bounded exact sparse identity sets (at most 32 rows) or exact
fixed-width membership bytes with lazy deterministic ordinals
scoped to one model. Hash-table lookup checks complete key equality; no fingerprint
substitutes for identity. This reduces dense cache ownership but does not impose a
process memory limit: models, selections, attempt evidence, SQLite and subprocesses
consume additional memory.

Reduction is not anonymization or sanitization. Retained values, schema, included code,
markers and diagnostic reasons can disclose sensitive information. Private search snapshots
and candidates contain source data. They are temporary, not securely erased. Final VACUUM
INTO compaction removes unused pages from the exported fixture, but this does not certify
that retained data is safe to share. Review every artifact before distributing a bundle.
Ordinary TEXT-keyed and composite-keyed tables do not alias their declared keys to SQLite's
hidden rowid. VACUUM INTO may change those hidden rowids. WITHOUT ROWID tables have no
hidden rowid and use declared PK storage identity; their INTEGER PK does not alias a rowid.
ReproSeed does not rely on last_insert_rowid, rowid-based incremental BLOB I/O or update
hooks for these tables. Declared retained values, keys and original storage declarations
are preserved; ordinary hidden rowid identity is outside M2c's preservation contract.
Publication still requires three
fresh target confirmations of the exact compact fixture, including any rowid-sensitive
application behavior.

Only explicitly named regular files under the configuration root are included. Traversal,
symlinks, junctions and recursive directory collection are rejected. This avoids implicit
collection; an explicitly selected file can still contain secrets. Reports omit row values
and raw process output. The bundle omits original/candidate database history.

Inspection and replay capture bounded manifest metadata and validate safe declared artifact
names, then copy only those files into one tool-owned private payload. They verify the copied
bytes against the captured hashes and validate the copied report/configuration before any
oracle execution. SQLite schema, integrity, foreign keys and reported final row counts are
checked on a separate private database copy. Finalized bundles with any
`fixture.sqlite3-wal`, `fixture.sqlite3-shm` or `fixture.sqlite3-journal` beside the fixture
are rejected, including empty sidecars, without deleting or incorporating those files.
This static-bundle policy does not change WAL-aware snapshotting of normal reduction sources.

Replay sources every fresh disposable database and asset copy from this verified private
payload. After acquisition it does not reread the original bundle configuration or assets;
oracle writes cannot contaminate subsequent confirmations or pristine payload bytes through
the paths supplied by ReproSeed. Inspection never runs the oracle, needs no `--allow-exec`,
and opens only private database copies for SQLite checks. Default/explicit JSON inspection
retains the existing report shape; text inspection escapes terminal controls in displayed
strings and distinguishes checks performed now from recorded confirmations.

Hashes establish that copied contents match a supplied manifest. Evidence checks establish
structural consistency of recorded metadata, with version-1 interruption accounting limits.
Fixture checks establish structure and final counts. None of these establish that a new
replay reproduced the target, authenticate authorship, or prove a claimed historical
execution happened. A person who changes both artifacts and manifest can supply new code
and consistent records. Only an explicitly acknowledged replay executes new confirmations.

Private acquisition prevents drift from the copied, hashed payload used for execution. It
does not provide complete hostile-filesystem race immunity, operating-system isolation, or
protection against someone with arbitrary access to the user's process or private temporary
directories. External executables and dependencies are not included automatically. Supplied
source and bundle files remain unchanged by tool operations; arbitrary oracle code remains
subject to the execution trust boundary above.

## Before sharing a bundle

A finalized bundle contains `fixture.sqlite3`, the explicitly included application/oracle
files, `replay.toml`, `report.json`, `manifest.json` and a generated `README.md`. The replay
configuration retains the selected argv, exact marker and included filenames. Reports retain
table names, counts and bounded execution evidence; the database retains selected values and
schema. Relative asset names, source-code literals and external argv paths can disclose
information even when no row values appear in CLI output. Files outside the explicit include
list are not recursively collected, and external dependencies are not packaged automatically.

Before distributing this directory:

- Run `reproseed inspect <bundle> --format text` to review current integrity/structure checks
  and recorded evidence. Inspection does not execute application code or certify safe data.
- Open the retained SQLite fixture with a trusted read-only viewer and review every retained
  table, value, schema declaration and name for information that should not be shared.
- Review all included source/configuration files, exact markers, filenames and argv literals.
  Confirm that credentials, personal data and private system paths are absent or deliberately
  approved for sharing. ReproSeed performs no automatic redaction or anonymization.
- State the required interpreter, external executables/dependencies and any expected local
  files. Reconfirm a relocated copy using `reproseed replay <bundle> --allow-exec` in an
  appropriate environment before asking someone else to reproduce it.
- Treat received bundles as executable code. Review their contents and trust their origin
  before acknowledging execution; use external OS isolation or a restricted account for
  untrusted code. Bundled code executes with the launching user's OS permissions.

A valid manifest establishes matching bytes relative to the supplied hashes. Someone who
changes an asset and its manifest entry can produce a consistent bundle; that does not
authenticate a publisher or the recorded history. A verified historical bundle may still
fail a fresh replay when external dependencies or application behavior differ. Source,
candidate and replay temporary files are not securely erased.

The [M2d readiness assessment](docs/alpha-readiness.md) records the controlled synthetic
sharing/error audit and its platform limits. It is an internal simulated first-user review,
not an independent external-user study or a claim of complete security coverage.

For a suspected vulnerability, contact the repository owner privately through an available
GitHub contact channel before sharing sensitive proof data. Do not include real databases,
credentials or personal records in public issues. There is no promised security response SLA.
