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
to a kill-on-close Job Object and polls pipes with PeekNamedPipe. Closing the job terminates
assigned descendants. Assignment occurs after process creation, so there is a startup race;
host job policies may reject assignment. Bounded taskkill /T /F plus direct process kill
provide best-effort fallback. Descendants that detach or outlive an unassigned parent can
escape. Cleanup and temporary-directory removal cannot guarantee removal of files held by
escaped processes. The runner returns within finite process/cleanup bounds rather than
waiting indefinitely for pipe EOF. Only Windows cleanup has been exercised locally here;
POSIX behavior is covered by configured CI, not a claimed hosted result.

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

Replay checks versioned manifests and hashes before execution, rejects paths escaping the
bundle and runs on fresh temporary copies. Hashes detect changes relative to the manifest;
they do not authenticate an untrusted bundle. Someone who changes both an artifact and its
manifest can supply new executable code. External executables and dependencies are not
included automatically. Source and bundled files remain unchanged by tool operations;
arbitrary oracle code is subject to the execution trust boundary above.

For a suspected vulnerability, contact the repository owner privately through an available
GitHub contact channel before sharing sensitive proof data. Do not include real databases,
credentials or personal records in public issues. There is no promised security response SLA.
