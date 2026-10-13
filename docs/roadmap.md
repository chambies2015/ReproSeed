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
Hosted validation remains a gate: the original run failed during temporary-directory setup,
and the repaired commit must pass all three CI matrix entries after Dan commits and pushes.
Local validation does not complete that hosted gate.

## M1b — review-driven hardening

Review the working vertical slice, improve reports and diagnostics, strengthen platform
cleanup and uncertainty evidence, and add realistic synthetic fixtures. Address review
findings before expanding adapters or delivery surfaces.

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
