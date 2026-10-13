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

Cancellation regressions inject one-shot exceptions at meaningful search publication and
invocation-accounting boundaries. Retain deterministic coverage for pending acceptance,
cache hits, completed evaluations and the first/second confirmations. A salvaged result
must pass the unchanged report validator and agree with actual fixture counts. Exercise
real SQLite and subprocesses through final verification, both inspection formats and
relocated replay. A bounded POSIX signal smoke complements this coverage where supported;
an injected exception on Windows does not establish Windows console-signal behavior.

Keep source acquisition, candidate state and oracle state separate. Preserve values and
schema. Add meaningful regression cases for contracts changed by a patch. Do not weaken
acceptance assertions or silently skip failures. Read AGENTS.md before implementation and
SECURITY.md before executing external oracle code. Publishing and later roadmap milestones
are outside M1b.1.1.
