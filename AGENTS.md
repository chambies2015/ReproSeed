# Engineering guidance

ReproSeed M0/M1a is a local Python 3.12+ CLI with a standard-library-only runtime.
Architecture and scope are described in docs/architecture.md and docs/roadmap.md.

## Module boundaries

- config.py validates versioned TOML and explicit file selection before execution.
- sqlite_adapter.py owns read-only snapshots, schema inspection, dependency closures,
  private candidate construction, validation and compact export.
- oracle.py stages disposable copies and classifies bounded subprocess executions.
- reducer.py owns deterministic row removal and normalized candidate caching.
- workflow.py owns confirmation counts, budgets and verification sequencing.
- artifacts.py owns bundles, portable replay configuration and hash verification.
- cli.py owns argument parsing, acknowledgement and user-facing exit codes.

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
- Quote identifiers, bind values, disable FK actions only on private candidates and validate.
- Bundle assets are explicit regular files, never recursive collection or implicit secrets.
- Shells, eval and arbitrary format expressions do not belong in oracle execution.
- inspect is read-only and never executes code. reduce/replay require --allow-exec.
- Source protection is a tool behavior, not a sandbox against authorized arbitrary oracle code.

## Commands

```
uv sync --locked --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mypy --platform linux
uv run pytest --basetemp=.validation/pytest
uv build --no-sources
```

Run acceptance tests and install the wheel outside the source import context when changes
affect the workflow. Use a fresh bundle output; no overwrite shortcut exists.
See CONTRIBUTING.md for the complete validation workflow and platform limits.
