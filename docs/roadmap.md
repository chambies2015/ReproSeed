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
[M2b completion evidence](m2b-completion.md) for actual checks and limits. Work stays
unstaged/uncommitted for Dan; hosted M2b acceptance requires his subsequent commit/push.

Three-or-more-column PKs, descending composite components, arbitrary collations,
cross-affinity coercions, alternate/reordered FK targets and WITHOUT ROWID remain rejected.
M2b does not constitute a production-ready release.

## M2c — future SQLite scope review

Review M2b's actual supported shapes, rejection evidence and performance before selecting
another bounded SQLite addition. Wider arity, descending keys, WITHOUT ROWID or comparison
extensions require explicit identity, preservation and FK contracts plus independent
regressions; none is implemented or promised here. PostgreSQL remains later work.

## M3 — PostgreSQL

Add an adapter only after SQLite contracts and replay evidence are stable. Revisit snapshot,
dependency, server permissions and reproducibility semantics for PostgreSQL.

## Later

Related-file and request-sequence reduction may follow. Web servers/frontends/dashboards,
LLM integrations/embeddings/paid services, automatic anonymization, attachment reduction,
parallel/distributed workers and package publishing are outside this milestone.
