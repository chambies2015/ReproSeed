# Tenant-scoped entitlement delivery

This synthetic entitlement processor applies grants from received gateway events.
Its deliberate defect treats an external event reference as globally unique.
References are unique within a tenant, so the same reference used by another
tenant must apply independently. The buggy processor suppresses that valid grant.
This is independent of the existing export, stock and approval defects.

The default generator creates 970 user rows deterministically across five tables:

| Table | Rows | Declared primary key |
| --- | ---: | --- |
| tenants | 10 | INTEGER |
| accounts | 40 | TEXT, inline, NOT NULL |
| entitlements | 120 | TEXT, table-level, NOT NULL |
| events | 400 | TEXT, inline |
| event_receipts | 400 | INTEGER |

Sparse UUID-like string IDs are actual TEXT values with BINARY primary-key
collation. Every event key is non-NULL, including in the ordinary rowid schema
that permits NULL primary-key values. Accounts reference integer tenants;
entitlements reference both text accounts and integer issuer tenants; events
reference text accounts and nullable text entitlements; integer receipts reference
text events. Deleting a tenant therefore closes over several dependency levels.
Unrelated tenants, previews, discarded receipts and events without an entitlement
provide ordinary decoys. The final two pending grant events belong to different
tenants and carry the same gateway reference. There is no failure flag.

`app.py` exposes `process_entitlements(database)`, returning the actual decision
for each receipt. The independent oracle reads its contract inputs separately,
executes the processor, and compares the complete map with tenant-scoped behavior.
It emits the exact stdout line `REPROSEED_TEXT_KEY_ENTITLEMENTS` with exit 46 only
when the complete result matches global-reference deduplication and suppresses a
valid grant in another tenant. Correct scoped behavior returns PASS. Missing or
malformed decisions, unrelated suppression, ownership errors and crashes cannot
emit the target marker. Regression tests repair the application while leaving the
oracle unchanged, and exercise an intentional same-tenant duplicate.

From the repository root, with the development environment installed:

```console
uv run python examples/text_key_entitlements/generate.py
uv run reproseed diagnose --config examples/text_key_entitlements/reproseed.toml
uv run reproseed diagnose --config examples/text_key_entitlements/reproseed.toml --allow-exec --format json
uv run reproseed reduce --config examples/text_key_entitlements/reproseed.toml --out repro-bundle-entitlements --allow-exec
uv run reproseed inspect repro-bundle-entitlements
uv run reproseed inspect repro-bundle-entitlements --format text
uv run reproseed replay repro-bundle-entitlements --allow-exec
```

Choose fresh source and output paths on later runs. The generator and reducer
refuse to overwrite existing paths. Static diagnosis executes no application and
establishes structural readiness; executable diagnosis requires three fresh target
confirmations. The finite reduction budget is 240 invocations, including three
baseline and three reserved final confirmations. Every accepted reduction needs
two fresh confirmations unless it reuses already confirmed candidate evidence.
The full acceptance target is at most 12 retained rows from the 970-row source.

The M2a Windows/Python 3.12.15, SQLite 3.53.1 source-validation run reduced
970 rows to ten: two rows in each table. It used 180 of 240 oracle invocations,
31 cache hits and 30 accepted reductions, with zero unresolved or invalid trials.
It exhausted single-row deletion closures. Reduction took 43.094 seconds on that
host; this observation is not a performance promise. The source occupied 282,624
bytes and the compact fixture occupied 57,344 bytes. Three fresh compact-fixture
confirmations and three further relocated replay confirmations reproduced the
target. Declared values, schema, indexes, metadata and source/asset/bundle hashes
were preserved. See [the completion evidence](../../docs/m2a-completion.md) for
the recorded commands, hashes and additional validation.

The measurement recipe records counts, elapsed time, budget, cache and attempt
summaries, hashes and fresh confirmation outcomes:

```console
uv run --locked python tests/milestone_smoke.py --directory .validation/text-key-measurements-fresh --examples text_key_entitlements
```

It verifies all retained declared column values, schema, indexes, metadata,
integrity and foreign keys. It then makes original paths unavailable and runs
three replay confirmations from a relocated bundle outside the checkout. M2a
preserves declared values and primary keys; compact export may change implicit
hidden rowids, which this application never uses.

`generate.py --small /new/path/fixture.sqlite3` creates a ten-row fixture with the
same schema and defect for installed-wheel smoke. Full acceptance and measured
reduction use the default large fixture. CI exercises TEXT diagnosis, reduction,
default/explicit JSON and text inspection, and relocated replay using an isolated
installed wheel without repeating a large benchmark.

Copy the complete bundle outside the checkout and use the installed CLI from an
unrelated working directory:

```console
reproseed inspect /path/to/relocated-entitlement-bundle --format text
reproseed replay /path/to/relocated-entitlement-bundle --allow-exec
```

The verified bundle includes both application and oracle; original assets and
source paths are unnecessary. Only Python and ReproSeed are required. Retained
content can still be sensitive: reduction is not anonymization and proves no
global minimum. Review the code and data before sharing. Disposable subprocess
state is not an operating-system sandbox.
