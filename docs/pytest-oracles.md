# A specifically failing pytest test as an oracle

M2g adds an optional, explicitly invoked bridge. A normal ReproSeed installation has
no mandatory dependencies; install supported pytest separately in the interpreter
used for the oracle. The bridge supports released pytest **8.3 through 9.x** (`>=8.3,<10`),
using public `pytest.main`, fixture, collection and report hooks. The concrete tested
versions and platforms belong in [M2g completion](m2g-completion.md). No pytest11 entry
point is registered. Installing ReproSeed alone does not change ordinary pytest sessions.

Select exactly one ordinary synchronous Python function/method or one parametrized
case. A target file is separate from the unchanged version-1 ReproSeed configuration:

```toml
adapter_version = 1
nodeid = "test_export.py::test_cross_project_names"
exception = "builtins.AssertionError"
message = "cross-project export lost an entry"
```

The four fields are required and unknown fields are rejected. Reads are bounded to
16 KiB; strings and selector lengths are bounded. The exception is its observed
module plus qualname, compared without importing the named class. Messages must be
exact and nonempty. Pytest assertion expansion can vary with the data: use a stable,
specific explicit exception at the intended invariant, such as
`raise AssertionError("cross-project export lost an entry")`. Establish that invariant
from the application result first. A matching signature establishes this configured
contract; it does not prove arbitrary semantic equivalence.

Paths use portable `/` separators, and the test file must be a regular file inside
the target file's directory. That directory is the run root. Traversal, links,
junctions, globs, directory/module/class selections and ambiguous parameter families
are rejected. A literal quoted TOML selector such as
`nodeid = 'tests/test_export.py::test_case[owner with spaces]'` selects that exact
case; the actual collected nodeid must match. Safe file paths support spaces and
Unicode. Collection imports Python and is execution, even when selection is rejected
before test setup.

The bridge passes the selected file as a literal relative file argument, including
when its portable name begins with `-` or `@`; it cannot become a pytest option or
argument-file directive.

The test must request `reproseed_db`, directly or through another fixture. It is a
`pathlib.Path` to an additional owned snapshot of the supplied candidate. Local
overrides of this reserved fixture are rejected. Tests may write this disposable
database; those writes never become later candidates or the exported fixture.
Requesting the fixture proves binding, while meaningful use is the test author's duty.

Use the existing oracle protocol without changes to the generic runner:

```toml
version = 1
source = "fixture.sqlite3"
include = ["app.py", "test_export.py", "pytest-target.toml"]

[oracle]
argv = ["{python}", "-m", "reproseed.pytest_oracle", "--target", "pytest-target.toml", "--db", "{db}", "--allow-exec"]
expected_exit = 86
marker = "REPROSEED_PYTEST_TARGET_V1"
stream = "stdout"
timeout_seconds = 10.0
output_limit_bytes = 65536

[reduction]
max_invocations = 400
```

Only explicitly included files enter the bundle. Include every necessary test,
application, local conftest and target file; there is no recursive project discovery.
The containing `reduce`/`replay`/executable `diagnose` also requires `--allow-exec`.
Bridge help, imports, static diagnosis and inspection do not import pytest or tests.
Missing/unsupported pytest produces a curated unresolved result before test or
conftest import. There is no dependency installation or network access by the bridge.

| Bridge result | Exit | Required state |
| --- | --- | --- |
| TARGET | 86 and the exact marker on stdout | Exactly one intended item executed once; setup and teardown passed; the actual call failed with the exact exception/message; complete consistent reports and final failed-session exit; no additional error |
| PASS | 0, no marker | The selected item genuinely passed setup, call and teardown, with a consistent successful completed session |
| UNRESOLVED | 2, no marker | Wrong signature, setup/finalizer failure, collection/internal/session error, missing or duplicate reports, unsupported behavior, invalid target or dependency |
| Interrupted | 130, no marker | An observed interruption where the bridge can return cleanly; the outer runner may instead enforce its finite deadline |

Pytest's nonzero exit alone is insufficient. A matching call followed by a failed
finalizer is unresolved. Skips, skip markers, xfail/XPASS (strict or non-strict),
exception groups, async/generator tests, reruns, xdist, external plugins and custom
collectors are unsupported. These do not establish a genuine PASS or target.

Each fresh oracle subprocess calls `pytest.main` once. Third-party plugin autoload
is disabled for that process, inherited `PYTEST_*` controls are cleared, and an
owned empty ini plus explicit root/confcutdir prevents parent config/conftest discovery.
Included local conftest fixtures work; explicit `pytest_plugins` integration is rejected.
Local conftest hooks that intercept fixture setup, Python calls, runtest calls/protocol/
loop or report construction are also unsupported; ordinary fixture definitions work.
The normal terminal reporter, pytest output capture and cache provider are disabled.
The logging and warnings plugins are disabled as well. Explicit pytest capture fixtures (`capsys`,
`capfd`, their binary variants, `capteesys`, `caplog` and `recwarn`) are unsupported, including
through a fixture dependency, so their buffers cannot hide noisy output from the
outer limit. Arbitrary trusted Python can still allocate memory or redirect output
itself; this is not a general memory/resource sandbox.
Bytecode is disabled in the bridge and through the environment inherited by ordinary
Python children; the caller's environment is restored afterwards. Pytest temporary
files use owned disposable space.

Remaining pytest/test stdout/stderr, including ordinary child-process output, is
discarded in bounded streaming chunks. Fixed output-volume records emit at least
the observed volume to stderr, preserving the outer runner's combined byte limit
while preventing test-printed markers and pytest error rendering from becoming
protocol/diagnostic content. There is no unbounded StringIO. The bridge emits only
fixed status/reason codes; it does not print target messages, tracebacks or private
paths as its own diagnostics. Trusted
tests may themselves print arbitrary data: this is not a test-output sanitizer.

The generic runner supplies timeout, output and process cleanup boundaries. Direct
bridge invocations protect the supplied database through a snapshot but must be
bounded by the caller if a test can hang. Config/plugin isolation and private copies
are state hygiene, not an OS sandbox; tests and conftest run with your permissions.
See [SECURITY](../SECURITY.md).

## Run the real duplicate-export recipe

The [preparation script](../examples/pytest_duplicate_export/prepare.py) explicitly
copies the existing duplicate-export exporter and unchanged deterministic generator
into a new case. The test independently queries expected entries and compares the
real exporter result. It raises the target only for an entry lost to a same-name
entry from another project. Correcting the exporter in a separate case makes that
same test pass. The ordinary non-pytest example remains available.

Obtain an M2g-capable wheel, the example preparation files and a trusted wheelhouse
containing supported pytest and its dependencies. Setup may use normal package tools;
the lifecycle below installs and runs offline. Use fresh case, event and bundle paths.
The installed consumer recipe exercises the corresponding command argument arrays
in clean environments outside the checkout. Its actual versions and platforms are
recorded in the completion report. The POSIX form below is provided for Linux
validation; unavailable local Linux runtimes are not evidence that it ran.

PowerShell, from the repository with a supported Python command named `python`:

```powershell
python -m venv pytest-consumer
& ./pytest-consumer/Scripts/python.exe -m pip install --no-index --no-deps ./dist/reproseed-0.1.0-py3-none-any.whl
& ./pytest-consumer/Scripts/python.exe -m pip install --no-index --find-links ./pytest-wheels pytest==9.1.1
& ./pytest-consumer/Scripts/python.exe ./examples/pytest_duplicate_export/prepare.py --directory ./pytest-case --small
& ./pytest-consumer/Scripts/reproseed.exe diagnose --config ./pytest-case/reproseed.toml
& ./pytest-consumer/Scripts/reproseed.exe diagnose --config ./pytest-case/reproseed.toml --allow-exec
& ./pytest-consumer/Scripts/reproseed.exe reduce --config ./pytest-case/reproseed.toml --out ./pytest-bundle --allow-exec --progress --events ./pytest-events.jsonl
& ./pytest-consumer/Scripts/reproseed.exe inspect ./pytest-bundle
& ./pytest-consumer/Scripts/reproseed.exe inspect ./pytest-bundle --format json
& ./pytest-consumer/Scripts/reproseed.exe inspect ./pytest-bundle --format text
Move-Item -LiteralPath ./pytest-bundle -Destination ./pytest-relocated
Move-Item -LiteralPath ./pytest-case -Destination ./pytest-case-unavailable
& ./pytest-consumer/Scripts/reproseed.exe replay ./pytest-relocated --allow-exec
```

POSIX form for the retained hosted Linux matrix, awaiting actual M2g Linux execution:

```sh
python3 -m venv pytest-consumer
pytest-consumer/bin/python -m pip install --no-index --no-deps dist/reproseed-0.1.0-py3-none-any.whl
pytest-consumer/bin/python -m pip install --no-index --find-links pytest-wheels pytest==9.1.1
pytest-consumer/bin/python examples/pytest_duplicate_export/prepare.py --directory pytest-case --small
pytest-consumer/bin/reproseed diagnose --config pytest-case/reproseed.toml
pytest-consumer/bin/reproseed diagnose --config pytest-case/reproseed.toml --allow-exec
pytest-consumer/bin/reproseed reduce --config pytest-case/reproseed.toml --out pytest-bundle --allow-exec --progress --events pytest-events.jsonl
pytest-consumer/bin/reproseed inspect pytest-bundle
pytest-consumer/bin/reproseed inspect pytest-bundle --format json
pytest-consumer/bin/reproseed inspect pytest-bundle --format text
mv pytest-bundle pytest-relocated
mv pytest-case pytest-case-unavailable
pytest-consumer/bin/reproseed replay pytest-relocated --allow-exec
```

Omit `--small` for the full 2,430-row fixture. Limits above are explicit example
choices; production defaults are unchanged. Every baseline/final/replay still needs
three fresh confirmations, every accepted reduction two. Pytest starts afresh for
each invocation and adds measurable startup cost. No global minimality is claimed.

The module invoked with `-m` and installed pytest are **external execution
dependencies**, absent from the version-1 bundle manifest. Replay needs an
M2g-capable ReproSeed build and compatible separately installed pytest; this bundle
is not Python-only and older ReproSeed cannot supply this new bridge. Manifest hashes
do not authenticate installed dependencies. Old bundle families remain readable and
replayable by current code with their own execution requirements.

For repeatable developer verification, explicitly acquire the locked dependency
wheels with `python tests/pytest_wheelhouse.py --directory pytest-wheels`, then run
`python tests/pytest_bridge_smoke.py --wheel dist/reproseed-0.1.0-py3-none-any.whl --wheelhouse pytest-wheels --full --evidence .validation/m2g-consumers-new.json`.
The smoke creates clean external standard venvs, proves site-packages imports,
removes source path leakage, verifies both dependency-free and pytest consumers,
and retains hash/count/invocation/counterfactual observations. The optional full
case stays outside ordinary CI. Automated journeys are not independent human feedback.

The implementation follows pytest's public [Python invocation API](https://docs.pytest.org/en/stable/how-to/usage.html#calling-pytest-from-python-code),
[hook/report reference](https://docs.pytest.org/en/stable/reference/reference.html),
[exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html),
[plugin-loading controls](https://docs.pytest.org/en/stable/how-to/plugins.html) and
[plugin authoring guidance](https://docs.pytest.org/en/stable/how-to/writing_plugins.html).
The bridge's stricter acceptance contract is defined above; pytest's ordinary failed
session exit also covers failures that cannot be this configured target.
