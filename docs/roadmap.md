# Roadmap

## M0/M1a — current prototype

Python project foundation, strict configuration and execution acknowledgement; SQLite
supported-shape introspection and read-only WAL-aware snapshots; deterministic relational
row reduction; exact failure oracle and repeat confirmations; compact hashed replay bundles;
synthetic duplicate-export acceptance case and independent aggregate-threshold target.
No global minimality or anonymization claim.

## M1a.1 — clean-checkout CI repair

Prepare the ignored validation parent explicitly before pytest and document that setup
for fresh checkouts. Reconfirm the existing slice with clean-copy tests, both synthetic
targets, distribution builds and installed-wheel replay. See [repair evidence](m1a1-completion.md).
The hosted gate was satisfied by [run 38435813594](https://github.com/chambies2015/ReproSeed/actions/runs/38435813594)
on reviewed commit `ba40d64db748d974c36666294a1cc4500c79c25f`: Ubuntu/Python 3.12,
Ubuntu/Python 3.14 and Windows/Python 3.12 all passed tests, distribution builds and the
installed-wheel workflow. This accepted M1a.1 run does not validate later M1b.1 changes.
Historical completion reports retain the observations available when they were written.

## M1b.1 — evidence-checked bundles and readable inspection

Validate the existing version-1 report structure and checkable evidence relationships.
Bound actual JSON/configuration reads and reject non-finite values. Acquire, hash and validate
one private bundle payload; check fixture structure and final counts on a separate private
database copy; execute replay only from verified private bytes. Reject finalized SQLite
sidecars without modifying supplied files. Add opt-in compact text inspection while preserving
the default JSON shape, execution acknowledgement and confirmation counts. Test genuine
pre-M1b version-1 compatibility. See [M1b.1 evidence](m1b1-completion.md).

Hashes and metadata consistency establish neither authorship nor historical execution.
Inspection does not execute the oracle. The hosted gate was satisfied by
[run 38455095031](https://github.com/chambies2015/ReproSeed/actions/runs/38455095031) on reviewed
commit `e2606aae3d33bd18bda8ba29aef56bd9aff14c29`: Ubuntu/Python 3.12, Ubuntu/Python 3.14 and
Windows/Python 3.12 passed tests, distribution builds and installed-wheel workflows.
This accepted M1b.1 run does not validate the later cancellation repair. Historical reports
retain the observations available when they were written.

## M1b.1.1 — interruption-consistent search progress

Repair interrupted acceptance and cached-attempt publication so the retained selection,
accepted-reduction chain and summaries describe one committed search state. Audit adjacent
invocation accounting without weakening the version-1 reader or changing reduction ordering.
Add deterministic boundary coverage and real SQLite/subprocess interrupted-bundle workflows,
including inspection and relocated replay. See [cancellation repair evidence](m1b1-1-completion.md)
for the tested boundaries, platform results and remaining limits. Hosted
[run 38460548154](https://github.com/chambies2015/ReproSeed/actions/runs/38460548154) on reviewed
commit `b2bcc51f691d7c5dfe30345199f884dd7e7bb97e` passed both Ubuntu jobs (Python 3.12/3.14),
but Windows/Python 3.12 failed cancellation directory cleanup in job `115514293016`;
its later build and installed-wheel steps were skipped. This was not a successful hosted gate.

## M1b.1.2 — hosted Windows cancellation cleanup repair

Observe owned process completion before removing disposable oracle state, with one bounded
cleanup allowance, explicit resource ownership and persistent-obstruction warnings. Strengthen
readiness and separate process-termination/directory-removal evidence; retain deterministic
accounting/cleanup tests and finite Windows stability probes. See
[M1b.1.2 completion evidence](m1b1-2-completion.md). The hosted gate was accepted on commit
`5e72f68fc5133d9f343537ba7472ca0a0b186289` in
[run 38471526956](https://github.com/chambies2015/ReproSeed/actions/runs/38471526956): Ubuntu
Python 3.12, Ubuntu Python 3.14 and Windows Python 3.12 all succeeded. The historical report
retains the local observations available when it was written; this acceptance records the
later hosted result without rewriting that history.

## M1b.2 — demanding synthetic fixtures and targeted diagnostics

Add realistic reservation-overbooking and two-node approval-cycle applications with
independent semantic oracles, large relational decoy fixtures and relocated-replay evidence.
Add static configuration/schema readiness and optional three-confirmation executable
diagnosis, with terminal-safe text and separately versioned diagnostic JSON. Preserve the
adapter subset, ordinary reducer ordering, process protections and bundle/report version 1.
See [completion evidence](m1b2-completion.md). M1b.2 was accepted on commit
`c9cf32ced7f0428385d1daad912d5aa01fec6967` in
[run 38476866662](https://github.com/chambies2015/ReproSeed/actions/runs/38476866662):
Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 all succeeded. The historical
completion report retains the observations available when it was written. This closes M1b.
Its accepted application measurements are duplicate export 2,430 -> 5 rows, aggregate
threshold 11 -> 3, reservations 4,248 -> 9 and approval cycles 1,626 -> 6. These are observed
results for those fixtures, not reducer rules or claims of global minimality.

## M2a — single-column TEXT keys

Add exact declared TEXT PRIMARY KEY to ordinary/STRICT rowid tables using BINARY collation
established through SQLite index metadata. Require actual non-NULL TEXT PK values and
matching parent-family FK declaration/storage policy, including mixed INTEGER/TEXT tables,
nullable references, self-references and cycles. Preserve retained declared values, existing
integer ordering, reduction/oracle accounting and every version-1 serialized contract.
Hidden rowids of TEXT-keyed tables may change during compaction; final verification must
reconfirm the exported fixture. VARCHAR/CHAR, arbitrary collations, composite keys,
WITHOUT ROWID and other previously unsupported shapes remain outside this milestone.

The string-ID entitlement application exercises a separate tenant-scoping defect and
multi-level mixed-key dependencies. Extend schema rejection, reduction, diagnostic,
inspection/replay and installed-wheel coverage together. Preserve historical version-1
bundles and all four integer application acceptance cases. See [M2a completion evidence](m2a-completion.md)
for actual local checks and measurements. The implementation was completed locally and
pushed as `eb8108dece9055dc9180826f42de03363cb64cbe`. Hosted
[run 38564568013](https://github.com/chambies2015/ReproSeed/actions/runs/38564568013)
passed both Ubuntu jobs (Python 3.12/3.14), but Windows/Python 3.12 failed two bundle
path-security fixture setups in job `115853833714`; build and installed-wheel steps
were skipped. That run did not complete M2a's hosted gate; M2a.1 below records its accepted
repair. Historical completion reports
retain their original local observations. M2a is a prototype milestone, not a
production-ready or alpha release.

## M2a.1 — Windows bundle-fixture reliability repair

Investigate the shared one-second fixture deadline, retain real mutating subprocesses
and six strict baseline/final confirmations, and strengthen synthetic setup diagnostics
and separate deadline regressions. See [M2a.1 completion evidence](m2a1-completion.md)
for actual timing probes, finite Windows stability results and platform validation.
The repair was accepted at commit `d60c79c07ae12666af9572ced69edc3b9523ce17` in
[hosted run 38572680512](https://github.com/chambies2015/ReproSeed/actions/runs/38572680512):
Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 passed. This closes the
M2a hosted gate. The historical completion reports preserve their original local evidence.
TEXT entitlements reduced 970 -> 10 rows; together with the four established application
results, this is an observation for a fixture rather than a generic reducer requirement.

## M2b — bounded two-column composite keys

Support ordinary/STRICT rowid tables with exactly two ascending declared PK components,
each exact INTEGER or TEXT. Ordered metadata and actual non-NULL storage define complete
tuple identities. Preserve scalar ordering, BINARY text index/default comparisons and
parent-driven child storage rules. Composite FKs are grouped constraints targeting the
full parent PK in order, explicitly or implicitly; any NULL child component creates no edge.
Scalar/composite children and parents, multiple FKs, cycles and mixed families share the
existing lifecycle and version-1 formats. Retained declared values survive compaction;
hidden rowids are outside the preservation contract.

The independent composite billing application detects refunds incorrectly added to settled
payments, using a full 1,308-row fixture and an eight-row wheel smoke. Reconfirm all five prior
applications, genuine pre-M1b INTEGER and accepted M2a TEXT bundles, full schema rejection,
invocation/interruption accounting, inspection and relocated replay. See
[M2b completion evidence](m2b-completion.md) for its historical local checks and limits.
M2b was accepted at commit `d70edac43c22efe3df643b821af1c51ec756a945` in
[hosted run 38592071692](https://github.com/chambies2015/ReproSeed/actions/runs/38592071692):
Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 all passed.

Three-or-more-column PKs, descending composite components, arbitrary collations,
cross-affinity coercions, alternate/reordered FK targets and WITHOUT ROWID remain rejected.
M2b does not constitute a production-ready release.

## M2c — bounded SQLite WITHOUT ROWID support

Extend the existing adapter to ordinary/STRICT WITHOUT ROWID tables with one exact
INTEGER/TEXT PK component or two exact INTEGER/TEXT components. All WITHOUT ROWID PK
components must be ascending and TEXT comparisons BINARY. table_list identifies storage
layout; table_xinfo orders declared components and index_list/index_xinfo establish the
declared PK, excluding auxiliary nonkey storage columns. Scalar INTEGER there is a declared
indexed key, not a rowid alias. Retain the exact existing `(table, key)` identity, candidate
cache and deterministic ordering contracts.

Mixed-layout scalar/composite FK groups use the full parent PK and its component families.
Any NULL child component creates no edge, while remaining components still undergo
storage validation. Cycles, independent constraints and descendant closures share the
existing reduction path. Private materialization and VACUUM INTO preserve exact retained
declared values, storage declarations and schema; three fresh compact confirmations remain
mandatory. Diagnosis, configuration, bundle/report/replay and diagnostic JSON stay version 1.

The composite billing generator's explicit `--without-rowid` mode exercises five WITHOUT
ROWID tables and ordinary INTEGER-keyed payments using the same defect and independent
oracle. Reconfirm all six existing applications plus a full alternate-layout reduction
starting with at least 1,200 rows, and use the genuine small variant for hosted wheel smoke.
Generate genuine prior M2b composite evidence from its archived accepted source alongside
the existing INTEGER/TEXT compatibility checks. Record actual counts, execution/budget/cache
summaries, hashes, preserved values/schema/FKs, timing and file sizes. Preserve the hosted
matrix and standard-library runtime. See [M2c completion evidence](m2c-completion.md) for
actual validation and limits. M2c was accepted at commit
`dd3db90eee65ed10e158cdcc9ef16b8a677e9852` in
[hosted run 38599450878](https://github.com/chambies2015/ReproSeed/actions/runs/38599450878):
Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 passed.
The historical completion report retains the evidence available when written.

Three-or-more-component keys, descending WITHOUT ROWID/composite keys, arbitrary collations,
coercive affinity matching, non-PK UNIQUE/reordered FK targets, generated/hidden columns,
virtual/shadow tables and triggers remain rejected. SQLite itself rejects WITHOUT ROWID
without a PK, AUTOINCREMENT and NULL PK inserts; these are separate from adapter rejection.
PostgreSQL, LLM integration, web UI and package publication are outside M2c. Milestone work
stays unstaged and uncommitted for Dan.

## M2d — public-alpha readiness and first-user onboarding

Freeze the accepted SQLite and version-1 correctness contracts. Verify installation from
a locally built wheel with standard venv/pip outside the checkout and no consumer network
or uv requirement. Keep complete [getting-started examples](getting-started.md) synchronized
with executable tutorial assets; audit realistic mistakes, recovery, safe diagnostics,
package contents and bundle sharing. Preserve the six applications and alternate billing
layout, historical INTEGER/TEXT/composite bundles and the existing hosted matrix.
See [readiness gates](alpha-readiness.md) and [M2d completion evidence](m2d-completion.md).
M2d was pushed as reviewed commit `6aaf7d77d51bb5e6277f16caa3a85e5e3e9574b6`.
[Hosted run 38613024891](https://github.com/chambies2015/ReproSeed/actions/runs/38613024891)
passed Ubuntu/Python 3.12 and Ubuntu/Python 3.14, but Windows/Python 3.12 failed the
denied-output ACL regression in job `116020933305`. The ACL-edit command succeeded,
but the test did not establish an effective directory-creation denial; the CLI
created a verified bundle instead. This does not independently establish a product
permission bypass, and the hosted gate was not accepted. The original M2d completion
report preserves its local observations. This milestone changes no version and
publishes no package, release or tag.

## M2d.1 — effective-permission preconditions and staging-denial coverage

Repair the Windows integration test to probe actual child-directory creation under
its temporary, test-owned ACL before expecting product denial. A successful ACL
edit or ACL readback is supplementary evidence, not proof of an effective denial.
Run the real CLI denial assertions only when the bounded subprocess probe observes
an appropriate permission error; record a narrowly scoped capability skip when
creation remains allowed. Restore the original owned ACL on every exit path.

Independently inject PermissionError at the production private staging-parent
mkdir, retaining the real bundle/CLI path, and establish one attempted creation,
curated exit 2, no oracle launches, no bundle, no overwrite and unchanged inputs.
Keep real ACL integration separate from deterministic boundary coverage, along
with collision and interruption regressions, finite stability results and the
complete product/installed-wheel/compatibility checks. See
[M2d.1 completion evidence](m2d1-completion.md) for the actual repair and validation.
Changes remain unstaged and uncommitted for Dan; acceptance requires his subsequent
review, commit and push, followed by success in all three unchanged hosted jobs.
Public-alpha readiness remains **CONDITIONAL GO** pending successful hosted M2d.1
CI, independent developer feedback and Dan's explicit distribution decision.

## Next — limited-alpha decision and outside-user feedback

Resolve the readiness conditions, then Dan decides the supported alpha scope and a
distribution channel. Invite independent developers to attempt the documented workflow
and record task completion, confusion, dependency gaps and useful reproducer sharing.
The internal first-user simulation is not that study. Prioritize observed correctness
or onboarding blockers before speculative SQLite expansion or a broader adapter.
Any future alpha release identifier and publication need a separate explicit decision.

## M3 — PostgreSQL

Consider an adapter only after the limited-alpha decision and outside-user feedback,
with SQLite contracts and replay evidence stable. Revisit snapshot,
dependency, server permissions and reproducibility semantics for PostgreSQL.

## Later

Related-file and request-sequence reduction may follow. Web servers/frontends/dashboards,
LLM integrations/embeddings/paid services, automatic anonymization, attachment reduction,
parallel/distributed workers and package publishing are outside this milestone.
