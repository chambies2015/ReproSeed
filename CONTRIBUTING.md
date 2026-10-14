# Contributing

Install Python 3.12+ and uv. Runtime dependencies are standard library only. Development
tools are resolved in uv.lock; do not hand-edit it. Use synthetic data exclusively.

```
uv sync --locked --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mypy --platform linux
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run pytest --basetemp=.validation/pytest
uv run pytest tests/test_text_keys.py tests/test_diagnose_cli.py tests/test_diagnostics.py tests/test_realistic_acceptance.py --basetemp=.validation/pytest-focused
uv run --locked python tests/milestone_smoke.py --directory .validation/m2a-measurements-fresh
uv run --locked python tests/compatibility_smoke.py --directory .validation/pre-m1b-v1-fresh
uv build --no-sources
```

Create the `.validation` parent explicitly before pytest, including in a fresh checkout.
The disposable `.validation/pytest` directory is reserved for pytest to remove and recreate;
keep environments, caches and retained evidence elsewhere. This explicit temporary root
avoids restricted global temp-root enumeration on some Windows environments. Use a fresh
base-directory name if another test process is using that directory.
Required acceptance tests use real database files and subprocesses. A symlink test requires
Windows Developer Mode or symlink privileges; POSIX signal tests run only on POSIX. Record
skips and environment failures honestly. CI covers Linux Python 3.12/3.14 and Windows 3.12;
configuration alone is not evidence of a successful hosted run.

After building, install dist/reproseed-0.1.0-py3-none-any.whl into a fresh virtual environment
with `uv pip install --python <fresh-interpreter> --no-deps <wheel-path>`. Change directory
outside the repository and run that environment's `reproseed --help`. Copy one synthetic
example into that external working directory, generate its fixture, reduce, inspect with
default JSON, explicit JSON and text, relocate and replay it. Do not let an editable source
installation hide a broken wheel. The compatibility recipe requires a new tool-owned
scratch directory under `.validation`; it generates a genuine version-1 bundle from the
reviewed pre-M1b source before checking the current reader and replay.

The installed-wheel threshold smoke also exercises default-text static diagnosis and
JSON static/executable diagnosis. Use `tests/milestone_smoke.py --directory <new-directory>
--python <installed-interpreter> --cli <installed-console>` for all five measured examples.
Run it outside the checkout with an isolated wheel installation. It records counts, actual
invocations, budget, cache/acceptance summaries, elapsed reduction time, file sizes and
source/bundle hash equality. It checks retained values/schema/metadata and replays relocated
bundles after original example paths are made unavailable. Large reductions belong in the
acceptance suite and explicit measurement recipe, not repeated in small formatting tests.

M2a validation also requires `tests/test_text_keys.py` and the
`examples/text_key_entitlements/` acceptance application. Exercise static and executable
diagnosis, reduction, default/explicit JSON and text inspection, and three-confirmation
relocated replay with the installed wheel outside the checkout. Retain source/assets/bundle
hash equality and declared-value/schema checks; do not assert hidden-rowid equality after
TEXT-key compaction. Record text/integer example counts, per-table counts, actual invocations
and finite budget, cache hits, acceptances, invalid/unresolved trials, runtime and fixture sizes.
Keep large measurement runs explicit rather than multiplying them across small smoke tests.

For rejection fixtures, prove diagnosis and reduction never launch the oracle, publish no
verified bundle and preserve source hashes. Cover exact TEXT/BINARY keys, nullable-schema
non-NULL snapshots, wrong storage, malformed text, unsupported collations/FK declarations,
mixed-family dependencies, empty/Unicode/quoted/NUL keys and cycles using real SQLite files.
Ordinary integer ordering and cancellation/accounting regressions must continue to pass.

Use a clean copy prepared with CI's explicit `.validation` parent; run full tests, builds
and the installed-wheel workflow without editable imports. Inspect wheel/sdist contents
for generated databases, bundles, caches and retained evidence. Record actual Python/SQLite
versions and actual Windows/Linux runs; mypy's Linux target alone is not Linux execution.
Preserve the read-only hosted matrix, pinned actions and all three existing platform jobs.

Diagnostic regressions use real subprocesses for outcome/limit/mutation contracts, focused
interruption injection for launch-accounting boundaries, and a separate POSIX SIGINT test.
Record these separately by platform; Windows injection is not console Ctrl+C coverage.

Cancellation regressions inject one-shot exceptions at meaningful search publication and
invocation-accounting boundaries. Retain deterministic coverage for pending acceptance,
cache hits, completed evaluations and the first/second confirmations. A salvaged result
must pass the unchanged report validator and agree with actual fixture counts. Exercise
real SQLite and subprocesses through final verification, both inspection formats and
relocated replay. A bounded POSIX signal smoke complements this coverage where supported;
an injected exception on Windows does not establish Windows console-signal behavior.

Windows process-tree regressions use parent/child readiness handshakes and retain process
handles to observe termination separately from disposable-directory deletion. Test teardown
records observations before assertions and recovers only its own synthetic processes and
files. Keep finite stability probes as recorded validation batches, never hosted retries.
Cleanup waits/retries share a 1.5-second allowance; tests must preserve the total bound.
The descendant-pipe and live-tree timeout harnesses trigger a test-only monotonic deadline
jump after both processes are ready (and after parent exit for the open-pipe case). The
clock offset then stays fixed so cleanup consumes its real shared allowance. Actual
1.8-second/four-second total assertions remain; the separate 0.15-second timeout test uses
real elapsed time. Linux retains immediate evidence before a read-only process-identity
observation of at most 0.2 seconds, included in those total bounds. Windows completion
assertions remain immediate. Deterministic tests cover disappearing Job members,
failed assignment, remaining budget, deletion obstruction and further interruption. The
[M1b.1.2 report](docs/m1b1-2-completion.md) separates natural failures, injected boundaries,
Windows API denials and actual platform execution.

Keep source acquisition, candidate state and oracle state separate. Preserve values and
schema. Add meaningful regression cases for contracts changed by a patch. Do not weaken
acceptance assertions or silently skip failures. Read AGENTS.md before implementation and
SECURITY.md before executing external oracle code. Publishing and later roadmap milestones
are outside M2a. Leave milestone work unstaged and uncommitted for Dan's review; do not
push, open a PR, tag, release or publish packages. M1b.2's accepted hosted evidence is
commit `c9cf32ced7f0428385d1daad912d5aa01fec6967`, run `38476866662`, all three jobs
successful. Historical completion reports stay unchanged; M2a hosted evidence remains pending.
