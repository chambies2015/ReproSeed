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
[M1b.1.2 completion evidence](m1b1-2-completion.md). Hosted validation of the uncommitted repair
remains pending Dan's review, commit and push; local success and earlier runs do not establish it.

## M1b.2 — demanding synthetic fixtures and targeted diagnostics

Add additional demanding synthetic fixtures and focused diagnostics within the existing
adapter and oracle contracts. Use observed failures to choose the work; do not expand schema
support, add new algorithms or change delivery surfaces as part of M1b.1, M1b.1.1 or M1b.1.2.

## M2 — broader SQLite support

Extend schema support deliberately, with preserved-value semantics and rejection tests.
Improve reduction strategies and investigate more precise local minimality evidence.

## M3 — PostgreSQL

Add an adapter only after SQLite contracts and replay evidence are stable. Revisit snapshot,
dependency, server permissions and reproducibility semantics for PostgreSQL.

## Later

Related-file and request-sequence reduction may follow. Web servers/frontends/dashboards,
LLM integrations/embeddings/paid services, automatic anonymization, attachment reduction,
parallel/distributed workers and package publishing are outside this milestone.
