# Engineering guidance

ReproSeed M2e is a local Python 3.12+ CLI with a standard-library-only runtime.
Architecture and scope are described in docs/architecture.md and docs/roadmap.md.

## Module boundaries

- config.py validates versioned TOML and explicit file selection before execution.
- sqlite_adapter.py owns read-only snapshots, schema inspection, dependency closures,
  private candidate construction, validation and compact export.
- oracle.py stages disposable copies and classifies bounded subprocess executions.
- reducer.py owns deterministic row removal, normalized candidate caching and coherent
  committed search progress.
- workflow.py owns confirmation counts, budgets and verification sequencing.
- artifacts.py owns private bundle acquisition, portable replay configuration and hash verification.
- report.py owns typed version-1 evidence checks.
- inspection.py displays validated data and does not parse bundles or execute code.
- diagnostics.py reuses configuration, snapshot/model validation and invocation accounting
  for readiness checks and optional baseline execution; it never reduces or creates bundles.
- cli.py owns argument parsing, acknowledgement and user-facing exit codes.
- observation.py owns opt-in aggregate progress/event sinks, exclusive event-file
  acquisition, bounds and isolated sink failures. Telemetry is not a ledger,
  report, bundle asset or resume checkpoint.

Keep these interfaces small and typed. Do not add speculative plugin infrastructure.
Use synthetic fixtures and real SQLite/subprocess integration tests. Preserve user work.

## Invariants

- Never modify the user's source database.
- Never substitute a different crash for the specified failure.
- Never reuse oracle-mutated state as the next candidate or final fixture.
- Unsupported schemas fail explicitly rather than being silently altered.
- Unknown or untested behavior is not reported as verified.
- Reduction is not anonymization.
- No claims of global minimality without an actual proof.
- Tests and reports must reflect commands actually run.
- Never accept an exit code without the configured exact marker on the configured stream.
- Baseline/final verification needs three fresh confirmations; accepted reductions need two.
- Reserve final verification capacity. Do not publish a verified bundle on failed confirmation.
- Publish retained rows, acceptance evidence and attempt history as one coherent search state.
- Derive cache/invalid/unresolved summaries from committed attempt records.
- Cache exact normalized membership bytes only within one immutable row universe;
  deterministic ordinals preserve typed declared identities and table separation.
- Emit accepted/retained telemetry after checkpoint publication. Observer I/O
  failures disable only their sink; interrupts and implementation bugs propagate.
- Search cancellation preserves a committed confirmed selection; it never promotes partial
  confirmations or rolls back actual oracle executions.
- A handled search interruption stops search and attempts compact-fixture final verification.
  Baseline/finalization interruption or a further interruption may abort without a bundle.
- A second interruption during invocation accounting recovery must bypass search salvage and
  abort rather than publish incomplete execution accounting.
- Quote identifiers, bind values, disable FK actions only on private candidates and validate.
- Model declared INTEGER rowid-alias or exact TEXT/BINARY primary keys from SQLite metadata.
  TEXT keys must be actual TEXT and non-NULL; do not coerce, fold case or infer types from rows.
- Model exactly two ascending declared INTEGER/TEXT PK components in table_xinfo PK order,
  validate the unique nonpartial PK index/key columns and BINARY comparison metadata even
  for empty tables, and require actual non-NULL integer/text component storage.
- Read storage layout from table_list. WITHOUT ROWID supports one or two exact INTEGER/TEXT
  PK components; require its declared PK index even for scalar INTEGER and validate ascending
  key entries from index_xinfo, ignoring auxiliary nonkey columns when checking PK arity.
  INTEGER PRIMARY KEY there is not a rowid alias. Never depend on hidden rowids,
  last_insert_rowid, incremental BLOB I/O or update hooks for these tables.
- Treat each FK declaration id as one ordered group targeting the complete parent PK.
  Composite dependency identity is the full tuple; any NULL child component means no edge.
  Reject wrong arity, reordered/non-PK targets and unsupported declaration/storage families.
- Select FK declaration/storage policy from the referenced parent's key family, not the
  child's own primary key. Reject unsupported affinity/collation rather than approximating it.
- Preserve retained declared values and schema, including WITHOUT ROWID storage layout.
  Hidden rowids of ordinary TEXT/composite-keyed tables may change during VACUUM INTO and
  are never replacement row identities. WITHOUT ROWID tables have no hidden rowid.
  Reconfirm the compact fixture.
- Bundle assets are explicit regular files, never recursive collection or implicit secrets.
- Acquire bundle staging with bounded exclusive creation before oracle execution; denied
  output permissions fail promptly, collisions preserve existing paths, and cleanup errors
  do not replace an active interruption or failure.
- Inspect/replay validate copied payload bytes against the captured manifest before execution.
- Replay sources every fresh invocation from one verified private payload, never originals.
- Finalized bundle SQLite sidecars are rejected without deletion or incorporation.
- Check bundle schema, integrity, foreign keys and final counts on a separate private copy.
- Hash integrity, recorded consistency and fixture validity do not establish a new reproduction
  or authenticate historical claims; only an executed replay establishes its new outcomes.
- Preserve version-1 cached evidence and unknown-launch accounting without inventing a full ledger.
- Bound actual JSON/configuration reads; reject duplicate keys, non-finite numbers and unsafe depth.
- JSON inspection preserves the version-1 report shape; text inspection escapes terminal controls.
- Shells, eval and arbitrary format expressions do not belong in oracle execution.
- inspect is read-only and never executes code. reduce/replay require --allow-exec.
- diagnose is static by default; only --allow-exec runs three fresh baseline attempts.
  Static success establishes structural suitability, never reproduction. Preserve every
  observed PASS/UNRESOLVED result and interrupted launch uncertainty without majority voting.
- Diagnostic JSON is independently versioned; preserve report/replay version 1 unchanged.
- Source protection is a tool behavior, not a sandbox against authorized arbitrary oracle code.

## Commands

```
uv sync --locked --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mypy --platform linux
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run pytest --basetemp=.validation/pytest
uv run pytest tests/test_without_rowid.py tests/test_composite_keys.py tests/test_text_keys.py tests/test_diagnose_cli.py tests/test_diagnostics.py tests/test_realistic_acceptance.py --basetemp=.validation/pytest-focused
uv run pytest tests/test_compact_cache.py tests/test_observation.py tests/test_observation_workflow.py tests/test_benchmarks.py tests/test_config_artifacts.py::test_replay_rejects_invalid_bundle_before_launch --basetemp=.validation/m2e-focused-fresh
uv run --locked python benchmarks/lab.py --directory .validation/m2e-performance-fresh --mode all
uv run --locked python tests/milestone_smoke.py --directory .validation/m2c-measurements-fresh
uv run --locked python tests/milestone_smoke.py --directory .validation/m2c-without-rowid-measurements-fresh --examples composite_billing --without-rowid-billing-fixture
uv run --locked python tests/compatibility_smoke.py --directory .validation/pre-m1b-v1-fresh
uv run --locked python tests/compatibility_smoke.py --directory .validation/m2a-text-v1-fresh --history m2a-text
uv run --locked python tests/compatibility_smoke.py --directory .validation/m2b-composite-v1-fresh --history m2b-composite
uv build --no-sources
uv run --locked python tests/distribution_smoke.py --wheel dist/reproseed-0.1.0-py3-none-any.whl --sdist dist/reproseed-0.1.0.tar.gz
uv run --locked python tests/external_consumer_smoke.py --wheel dist/reproseed-0.1.0-py3-none-any.whl
```

Run acceptance tests and install the wheel outside the source import context when changes
affect the workflow. Use a fresh bundle output; no overwrite shortcut exists.
Exercise scalar/composite key model/reducer regressions, all six established applications,
the mixed-layout WITHOUT ROWID composite billing variant and installed-wheel TEXT/composite/
WITHOUT ROWID diagnosis, reduction, inspection and relocated replay. Use the genuine small
generators only for wheel smoke; full billing acceptance in both layouts starts with at
least 1,200 rows and targets at most 16 retained.
The explicit compatibility recipe archives the reviewed pre-M1b commit and uses its source
to generate a genuine version-1 synthetic bundle before the current reader inspects/replays it.
The m2a-text history mode separately archives accepted d60c79c07ae12666af9572ced69edc3b9523ce17
and generates a genuine prior TEXT-key bundle. The m2b-composite history mode archives
accepted d70edac43c22efe3df643b821af1c51ec756a945 to generate a genuine prior composite bundle.
Scratch directories must be new; generated
archives, databases and bundles stay ignored. Do not modify historical bundles or reports.
Exercise default/explicit JSON and text inspection in installed-wheel validation.
Use deterministic interruption injection at state transitions, plus real SQLite/subprocess
bundle inspection and relocated replay. Keep real-signal coverage distinct from injected
KeyboardInterrupt coverage and record the platform on which each actually ran.
See CONTRIBUTING.md for the complete validation workflow and platform limits.

Accepted M1b.2 evidence is commit c9cf32ced7f0428385d1daad912d5aa01fec6967 and hosted
run 38476866662. Accepted M2a.1 is commit d60c79c07ae12666af9572ced69edc3b9523ce17 and
hosted run 38572680512. Accepted M2b is commit d70edac43c22efe3df643b821af1c51ec756a945 and hosted
run 38592071692. Accepted M2c is commit dd3db90eee65ed10e158cdcc9ef16b8a677e9852 and
hosted run 38599450878. All four passed Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python
3.12. Preserve historical completion reports. M2e changes stay unstaged and uncommitted
for Dan; hosted validation requires his subsequent commit and push. External-consumer
validation uses a fresh standard venv/pip installation outside the checkout, with no network,
editable imports or PYTHONPATH/PYTHONHOME leakage. Keep tutorial files synchronized with
docs/getting-started.md. Readiness review does not authorize publication; independent outside-user
feedback follows the limited-alpha decision. Do not implement PostgreSQL, LLM
integration or web UI, or publish a release/package, in this milestone.

Accepted M2d.1 is commit 27be3d46c31f752f8944eb6e78d0f743f4edb9cd and hosted
run 38623620343. Its hosted Windows ACL-denial case was capability-skipped,
distinct from local actual-denial and deterministic staging-denial evidence.
M2e authorizes observation, exact lower-memory caching and a bounded performance lab;
it does not authorize publication or replace independent human feedback. Keep all
M2e changes unstaged/uncommitted. See benchmarks/README.md for isolated baseline
comparisons and docs/m2e-completion.md for actual validation and limits.
