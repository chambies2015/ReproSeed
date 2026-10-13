# Contributing

Install Python 3.12+ and uv. Runtime dependencies are standard library only. Development
tools are resolved in uv.lock; do not hand-edit it. Use synthetic data exclusively.

```
uv sync --locked --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mypy --platform linux
uv run pytest --basetemp=.validation/pytest
uv build --no-sources
```

The explicit pytest temporary root avoids restricted global temp-root enumeration on some
Windows environments. Use a fresh name if another test process is using that directory.
Required acceptance tests use real database files and subprocesses. A symlink test requires
Windows Developer Mode or symlink privileges; POSIX signal tests run only on POSIX. Record
skips and environment failures honestly. CI covers Linux Python 3.12/3.14 and Windows 3.12;
configuration alone is not evidence of a successful hosted run.

After building, install dist/reproseed-0.1.0-py3-none-any.whl into a fresh virtual environment
with `uv pip install --python <fresh-interpreter> --no-deps <wheel-path>`. Change directory
outside the repository and run that environment's `reproseed --help`. Copy one synthetic
example into that external working directory, generate its fixture, reduce, inspect,
relocate and replay it. Do not let an editable source installation hide a broken wheel.

Keep source acquisition, candidate state and oracle state separate. Preserve values and
schema. Add meaningful regression cases for contracts changed by a patch. Do not weaken
acceptance assertions or silently skip failures. Read AGENTS.md before implementation and
SECURITY.md before executing external oracle code. Publishing and later roadmap milestones
are outside M0/M1a.
