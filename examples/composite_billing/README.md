# Composite billing reconciliation

This synthetic billing application reconciles invoices against successful charges
and completed refunds. Its deliberate defect adds returned money to settlement.
An invoice for 10,000 cents with a settled 7,000-cent charge and a completed
4,000-cent refund has only 3,000 cents of net settlement. The buggy application
counts 11,000 cents and marks the invoice paid. This defect is independent of the
five earlier application examples.

The default generator creates 1,308 user rows deterministically:

| Table | Rows | Declared primary key | References |
| --- | ---: | --- | --- |
| tenants | 12 | TEXT | none |
| accounts | 36 | TEXT + TEXT | scalar tenant |
| invoices | 180 | TEXT + INTEGER | composite account |
| invoice_lines | 540 | TEXT | implicit composite invoice |
| payments | 360 | INTEGER | explicit composite invoice |
| refunds | 180 | TEXT + TEXT | scalar payment and composite account |

Accounts and invoices repeat their second key components under different tenants.
Invoice numbers are sparse integers. All primary-key components are non-NULL and
use exact declared INTEGER or TEXT types. TEXT comparisons use SQLite's default
BINARY collation. These are ordinary rowid tables; the application uses declared
keys throughout and never uses hidden rowids. The invoice-line TEXT key omits a
NOT NULL declaration but every stored key is actual non-NULL TEXT.

The scalar-keyed lines and payments reference both invoice components as one
foreign key. Payment decoys include fully populated references, `(NULL, number)`,
`(tenant, NULL)` and `(NULL, NULL)`. A reference with either component NULL does
not require a parent. Composite-keyed refunds reference a scalar payment and a
composite account. Tenant deletion therefore closes over several levels of
dependencies. Fully paid and underpaid invoices, pending payments, pending
refunds and unrelated tenants provide ordinary decoys. No stored failure flag
identifies the target.

`app.py` exposes `reconcile_invoices(database)`, returning paid decisions keyed
by `(tenant_id, invoice_no)`. Its CLI emits a JSON list containing both key
components and each boolean decision. An invoice needs retained line amounts
matching its declared total before it can be paid. Pending charges and refunds
do not contribute to settlement.

The independent oracle reads invoice, line, payment and refund contract inputs
separately and executes the application. It compares the entire decision map
with correct net settlement and independently calculated refund-addition
behavior. Only a complete map matching that particular defect, with at least
one observed false-paid invoice, emits the exact stdout line
`REPROSEED_COMPOSITE_BILLING_FALSE_PAID` and exits 47. Correct decisions return
PASS. Missing decisions, unrelated discrepancies, malformed results and other
crashes cannot emit the target marker. Counterfactual regression tests subtract
refunds in the staged application while leaving the oracle unchanged and require
PASS. Other tests make the target refund pending, inject unrelated decisions,
and crash the application.

From the repository root, with the development environment installed:

```console
uv run python examples/composite_billing/generate.py
uv run reproseed diagnose --config examples/composite_billing/reproseed.toml
uv run reproseed diagnose --config examples/composite_billing/reproseed.toml --allow-exec --format json
uv run reproseed reduce --config examples/composite_billing/reproseed.toml --out repro-bundle-billing --allow-exec
uv run reproseed inspect repro-bundle-billing
uv run reproseed inspect repro-bundle-billing --format text
uv run reproseed replay repro-bundle-billing --allow-exec
```

Choose fresh source and bundle output paths on subsequent runs. The generator
and reducer refuse to overwrite existing paths. Static diagnosis establishes
structural readiness without executing the application; executable diagnosis
requires three fresh baseline target confirmations. The finite reduction budget
is 260 invocations, including three baseline and three reserved final
confirmations. Every accepted reduction needs two confirmations unless it reuses
already confirmed candidate evidence. Full acceptance requires at most 16
retained rows, three fresh compact-fixture confirmations and three further
relocated replay confirmations. This is a heuristic target, not a claim of
global minimality.

The measurement recipe verifies retained declared values, schema, indexes,
metadata, integrity and foreign keys. It makes original source and asset paths
unavailable and runs replay from a relocated bundle in an unrelated working
directory outside the checkout. It checks source and bundle hashes before and
after reduction, inspection and replay:

```console
uv run --locked python tests/milestone_smoke.py --directory .validation/composite-billing-measurements-fresh --examples composite_billing
```

The M2b Windows/Python 3.12.15, SQLite 3.53.1 source-validation measurement
reduced 1,308 rows to eight: one tenant, account and invoice, three invoice lines,
one payment and one refund. It used 126 of 260 invocations, 23 cache hits and 22
accepted reductions, with zero invalid or unresolved attempts. It exhausted
single-row deletion closures. Reduction took 44.703 seconds on that host; this
observation is not a performance promise. The source occupied 172,032 bytes and
the compact fixture 65,536 bytes. Three fresh compact-fixture confirmations and
three further relocated replay confirmations reproduced the target. Retained
declared values, schema, indexes, metadata, integrity, foreign keys and source
and bundle hashes were preserved. See
[the milestone completion evidence](../../docs/m2b-completion.md) for the
recorded commands and broader validation.

`generate.py --small /new/path/fixture.sqlite3` creates eight genuine rows with
the same schema and accounting defect: one tenant, account and invoice; three
invoice lines; one settled payment; and one completed refund. Installed-wheel
CI uses this fixture for the complete diagnosis, reduction, default/explicit
JSON and text inspection, and relocated replay lifecycle. The default large
fixture remains the full acceptance and measurement scenario.

Copy the complete bundle outside the checkout and use the installed CLI from an
unrelated working directory:

```console
reproseed inspect /path/to/relocated-billing-bundle --format text
reproseed replay /path/to/relocated-billing-bundle --allow-exec
```

The bundle carries the application and oracle; originals are unnecessary.
Compact export may change hidden rowids while preserving declared keys and
values, so the compact fixture is reconfirmed. Reduction is not anonymization.
Review code and retained data before sharing. Disposable execution is not an
operating-system sandbox.
