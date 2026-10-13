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
Inspection does not execute the oracle. Hosted validation of M1b.1 remains pending Dan's
commit and push unless a run on that implementation is observed.

## M1b.2 — demanding synthetic fixtures and targeted diagnostics

Add additional demanding synthetic fixtures and focused diagnostics within the existing
adapter and oracle contracts. Use observed failures to choose the work; do not expand schema
support, add new algorithms or change delivery surfaces as part of M1b.1.

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
