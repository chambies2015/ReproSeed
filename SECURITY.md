# Trust boundaries

ReproSeed runs the exact command selected in configuration. reduce and replay require
--allow-exec because that command executes with your OS permissions and inherited
environment. shell=False prevents shell interpretation; it does not make code safe.
Inspect assets and argv before running an unfamiliar bundle. Temporary working directories
and disposable database copies are state hygiene, not operating-system isolation.

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
classification, reason, exit code, byte count and duration. Environment variables and
credentials are never serialized by ReproSeed.

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

Reduction is not anonymization or sanitization. Retained values, schema, included code,
markers and diagnostic reasons can disclose sensitive information. Private search snapshots
and candidates contain source data. They are temporary, not securely erased. Final VACUUM
INTO compaction removes unused pages from the exported fixture, but this does not certify
that retained data is safe to share. Review every artifact before distributing a bundle.

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

For a suspected vulnerability, contact the repository owner privately through an available
GitHub contact channel before sharing sensitive proof data. Do not include real databases,
credentials or personal records in public issues. There is no promised security response SLA.
