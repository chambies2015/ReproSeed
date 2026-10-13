# Inventory reservation overbooking

This synthetic inventory processor decides whether submitted reservations can be
accepted against stock lots. Its deliberate defect compares each reservation with
the lot's original capacity and never debits quantities accepted earlier. Two
requests of 7 and 8 units therefore both succeed against a ten-unit lot.

The generator creates 4,248 user rows deterministically. Eight organizations own
40 warehouses, which contain 200 stock lots. The fixture also contains 1,000
orders, 1,000 reservations and 2,000 reservation lines. Integer primary keys are
sparse. Orders belong to organizations and may name a preferred warehouse;
reservations reference both orders and warehouses; lines reference reservations
and stock lots. These multiple parent relationships exercise recursive dependent
removal. Several orders have a NULL preferred warehouse.

Each ordinary lot has capacity 100 and five small reservations totaling fifteen
units. The final lot has capacity ten. Its first three reservations are cancelled;
its final two submitted reservations contain quantities `6 + 1` and `7 + 1`.
There are no planted failure flags. Other tenants and lots remain ordinary decoys.

`app.py` exposes `process_reservations(database)`, returning actual acceptance
decisions. It groups a reservation's lines by lot before checking individual
capacity, so this is an aggregate accounting defect across reservations. The
independent oracle reads demands separately, calls the processor, and totals only
quantities the processor actually accepted. It emits the exact stdout line
`REPROSEED_RESERVATION_OVERBOOK` with exit 44 only when multiple individually
acceptable reservations collectively exceed a lot's capacity. Missing decisions,
individual over-allocation, needless rejection and application crashes do not
satisfy that target. A correct processor that debits stock and rejects the later
request passes the same oracle.

From the repository root, with the development environment installed:

```console
uv run python examples/reservation_overbook/generate.py
uv run reproseed diagnose --config examples/reservation_overbook/reproseed.toml
uv run reproseed diagnose --config examples/reservation_overbook/reproseed.toml --allow-exec --format json
uv run reproseed reduce --config examples/reservation_overbook/reproseed.toml --out repro-bundle-reservation --allow-exec
uv run reproseed inspect repro-bundle-reservation
uv run reproseed inspect repro-bundle-reservation --format text
uv run reproseed replay repro-bundle-reservation --allow-exec
```

Use a new source/output path on later runs; the generator and reducer refuse to
overwrite existing paths. Without `--allow-exec`, diagnosis checks structure and
assets without executing the application or establishing reproduction. Executable
diagnosis requires three fresh target confirmations; success does not guarantee a
later reduction will succeed.

The M1b.2 Windows/Python 3.12.15, SQLite 3.53.1 validation reduced 4,248 rows to
nine within the configured 400-invocation budget. It used 131 oracle executions,
24 cache hits and 21 accepted reductions, with zero unresolved or invalid trials.
It exhausted single-row deletion closures. The retained counts were:

| Table | Original | Retained |
| --- | ---: | ---: |
| organizations | 8 | 1 |
| warehouses | 40 | 1 |
| stock_lots | 200 | 1 |
| orders | 1,000 | 2 |
| reservations | 1,000 | 2 |
| reservation_lines | 2,000 | 2 |

The retained lines request six and seven units against the same ten-unit lot.
Every retained value and schema declaration stayed unchanged. The source occupied
196,608 bytes; the compact fixture occupied 36,864 bytes. An additional local run
took 68.726 seconds while other fixture acceptance runs used the same host; that
is an observation rather than a benchmark or performance promise. The completion
report records the acceptance run, three final confirmations and three relocated
replay confirmations with source/bundle hash checks.

Copy the entire completed bundle to a fresh directory outside this checkout.
With ReproSeed installed, replay it from an unrelated working directory:

```console
reproseed inspect /path/to/relocated-reservation-bundle --format text
reproseed replay /path/to/relocated-reservation-bundle --allow-exec
```

Both included scripts are staged from the verified bundle payload; the original
example paths are unnecessary. These demos need only Python and ReproSeed.
Arbitrary application dependencies are not packaged automatically. Reduction is
not anonymization, and the result has no proof of global minimality. Review code
and retained data before sharing; subprocess staging is not an OS sandbox.
