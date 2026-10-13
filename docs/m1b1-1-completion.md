# M1b.1.1 completion evidence

This follow-up repairs cancellation consistency before M1b.2. Changes remain
unstaged and uncommitted for Dan. Validation results below are local patch
evidence; hosted run 38455095031 validated the earlier M1b.1 commit only.

## Starting state and before-fix evidence

The checkout started clean on `main` at
`e2606aae3d33bd18bda8ba29aef56bd9aff14c29`. The reviewed reducer blob was
`7e085f5b6fec34da023085607da6b0e58342f062`. No reset or cleanup of user work
was performed. All fixtures and scratch evidence were synthetic/tool-owned.

On Windows Python 3.12.15, `.venv\Scripts\python.exe
.validation/m1b1-1-before.py` reproduced both defects using one-shot tracing
against the unchanged reviewed source. After acceptance append and before
retained assignment (reviewed line 98), the result retained two rows while its
accepted chain reached one. After cache-hit increment and before attempt
construction (line 84), it reported one cache hit and zero cached attempts.
Both results reported `interrupted_best_confirmed_candidate_preserved`.
Scratch evidence is `.validation/m1b1-1-before.json`. These were deterministic
exceptions, not OS signal tests, and used local Python 3.12 rather than the
independent review's Python 3.13.5.

The integration probe `.validation/cancellation_integration_before.py` loaded
the immutable reviewed reducer from Git, then ran real SQLite and oracle
subprocess workflows. The strict writer rejected acceptance with `report
accepted reduction chain does not reach the final total` and cache bookkeeping
with `report cache_hits disagrees with recorded attempts`. Each source hash
stayed unchanged and neither output bundle was published. Results are in
`.validation/cancellation-integration-before.json`.

The adjacent accounting audit demonstrated additional gaps: interruption after
a completed oracle returned but before charging lost one known execution;
interruption after an interruption record append but before charging lost a
known charge or an unknown-launch charge. Before repair,
`.venv\Scripts\python.exe -m pytest tests/test_invocation_accounting.py -q
--basetemp=.validation/pytest-accounting-before` yielded three failures and one
pass. The nonlaunch case correctly remained uncharged.

The repeatable immutable-source command `.venv\Scripts\python.exe
.validation/probe-accounting-before.py` confirmed those charge losses. The
separate `.validation/probe-accounting-launch-before.py` ran an actual process
and interrupted the reviewed oracle after `Popen` returned but before
`execution.executed = True`; the old oracle reported an unknown launch despite
having a handle. The probe itself bounded-killed/reaped that process. The repair
puts the handle within the oracle's cleanup region and records known execution.

An intermediate repair review also found that a second interruption during
counter recovery could fall through the reducer's ordinary search catch and
salvage incomplete accounting. A real-subprocess probe printed seven actual
calls, six serialized known executions, and strict-reader acceptance. Its
initial tool-owned temporary cleanup failed because the probe had left its
SQLite connection open; that probe error was corrected and is separate from
the captured accounting result. The final patch raises `AbortReduction`, a
`KeyboardInterrupt` subtype, for interrupted accounting recovery. Both reducer
handlers explicitly bypass salvage for it. Two real CLI regressions interrupt
before/after accounting publication and establish exit 130, exactly four actual
calls, no final confirmations or bundle, and unchanged source/configuration.

## Repair and limits

`reducer.py` uses a frozen checkpoint containing the retained selection and
committed attempt/acceptance prefix lengths. Progress preparation appends a
provisional attempt and, for a confirmed failure, acceptance metadata. The
caller publishes one checkpoint reference. Cancellation before that publication
returns the old selection and discards provisional tails; cancellation after it
returns the newer selection and complete evidence. Cache hits are counted from
committed attempts; workflow invalid/unresolved summaries already use the same
records. Preparation is constant cost in history length, without copying the
accumulated history each step. Return-time truncation/folding is linear once.
Ordinary ordering, chunk heuristics and normalized candidate caching remain.

Invocation accounting has its own immutable snapshot containing known/unknown
charges, last invocation identity and an interruption chain. One publication
records both charge and interruption evidence; identity prevents charging a
completed invocation twice during recovery. A caller-owned `OracleInvocation`
holds launch evidence across `run_oracle` result transfer. The optional fourth
argument preserves ordinary three-argument callers. A returned process handle
establishes a known launch and is covered by cleanup even if interruption
precedes the next launch-state assignment; an interrupted constructor without a
returned handle remains genuinely unknown and conservatively charged.

Search cancellation stops further search and finalizes the checkpoint through
compact export and three fresh confirmations on the exported fixture. Baseline,
finalization or final-confirmation cancellation may abort with CLI 130 and no
verified bundle. A further interruption in counter recovery bypasses search
salvage and aborts; an interruption in finalization propagates. If
unresolved-attempt preparation itself is interrupted within the
search catch, its provisional tail can instead be discarded. No recovery loops
retry indefinitely. Private output cleanup remains best effort.

The report format and strict reader are unchanged. Version 1 still permits the
documented bounded omission of completed candidate confirmations during
cancellation; those known executions remain charged. It does not reconstruct
missing confirmations or invent an outcome. Reduction is not anonymization;
there is no global-minimality claim. Tests target explicit publication and
transfer boundaries, not every possible asynchronous exception, forced process
termination, power loss or hostile interference. Python explains the broader
limits of asynchronous exceptions in its
[signal-handler exception note](https://docs.python.org/3.12/library/signal.html#note-on-signal-handlers-and-exceptions).

## Validation

Local validation ran on 2026-10-13. Windows reported
`Windows-10-10.0.19045-SP0`, Python 3.12.15 (MSC 1944 AMD64), SQLite 3.53.1 and
uv 0.13.0. Linux used the existing cached Docker image
`ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim`: Debian/glibc 2.36,
WSL2 kernel 6.18.33.2, Python 3.12.11 (GCC 12.2.0), SQLite 3.40.1 and uv
0.8.22. Docker Desktop was 4.86.0, client/engine 29.7.2. This is actual Linux
runtime evidence, distinct from `mypy --platform linux` static checking.

| Check | Windows | Linux |
| --- | --- | --- |
| Locked dependency sync | Passed, cached offline clean copy | Passed, clean copy |
| Ruff lint / format | Passed; 40 formatted files | Passed; 40 formatted files |
| mypy / mypy Linux platform | Passed; 11 source files each | Passed; 11 source files each |
| Full clean-copy pytest | 272 passed, 5 skipped; 211.24 s | 276 passed, 1 skipped; 311.31 s |
| Wheel / source-distribution build | Passed | Passed |
| External installed-wheel workflow | Passed | Passed |

Windows skips were two symlink tests because this host lacked creation
privilege (WinError 1314), POSIX executable-mode semantics, POSIX signal return
codes, and the new actual POSIX SIGINT workflow. Linux skipped only Windows
junction semantics. All remaining tests ran; no broad skip or assertion was
weakened. The Windows injected exceptions exercised actual SQLite and oracle
subprocesses but do not establish Windows console Ctrl+C behavior.

Focused after-fix commands included:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_reducer.py tests/test_reducer_cancellation.py -q --basetemp=.validation/pytest-reducer-final
.tools/bin/uv.exe --cache-dir .validation/uv-cache run --locked pytest tests/test_cancellation_workflow.py --basetemp=.validation/cancellation-workflow-final -q
.venv\Scripts\python.exe -m pytest tests/test_invocation_accounting.py tests/test_reducer_cancellation.py tests/test_cancellation_workflow.py tests/test_report_validation.py -q --basetemp=.validation/pytest-accounting-abort-after
```

Results were respectively 15 passed; 17 passed/1 POSIX skip; and 126 passed/1
POSIX skip. The final full suites also include the two added counter-recovery
abort cases. Final boundary coverage uses checkpoint/log state or helper
publication, without fixed line numbers. The process-handle test derives the
launch-evidence statement from source. Only the before-fix reproduction records
the reviewed line numbers.

Initial checkout synchronization succeeded with:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.validation\uv-cache'
.tools\bin\uv.exe sync --locked --python 3.12
```

Clean copies were made from explicitly enumerated tracked and nonignored new
regular files; `.validation`, `.venv` and `dist` were absent initially. The
ignored helper `.validation/m1b1_1_validate.py` extracted the unchanged CI test
preparation and wheel blocks into LF scripts. The Windows commands were:

```powershell
.venv\Scripts\python.exe .validation/m1b1_1_validate.py prepare
.venv\Scripts\python.exe .validation/m1b1_1_validate.py windows
```

The initial clean Windows copy's online sync failed reaching PyPI while
resolving Hatchling. Logs remain in
`.validation/m1b1-1-win312-evidence/sync-online-failed.log` and
`commands-online-failed.json`. A fresh final copy used the existing cache with
`UV_OFFLINE=1`, `UV_CACHE_DIR` set to the repository's tool-owned cache,
`PYTHONUTF8=1`, and `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV` removed. It ran:

```text
uv sync --locked --python 3.12
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy --platform linux
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run --locked pytest --basetemp=.validation/pytest
uv build --no-sources
```

`uv` resolved to the repository `.tools/bin/uv.exe`; the repaired CI test block
ran with Git Bash. Final Windows command argv, working directories, exits and
logs are under `.validation/m1b1-1-win312-final-evidence/commands.json`. Both
copies asserted the validation parent absent before executing CI's explicit
mkdir. The CI matrix, action pins, permissions, full tests and installed-wheel
block are unchanged.

Linux dispatch used this command after sandbox engine access was denied before
any container ran; automatic review allowed access to the existing engine:

```powershell
docker run --rm --mount 'type=bind,source=M:\Server\ReproSeed\ReproSeed\.validation\m1b1-1-clean-linux312-final,target=/work' --mount 'type=bind,source=M:\Server\ReproSeed\ReproSeed\.validation\m1b1-1-linux312-final-evidence,target=/evidence' --workdir /work ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim bash /evidence/validate.sh
```

The script ran the same locked sync, lint, format, both mypy commands, exact CI
preparation/test block, build and wheel block with `UV_PYTHON_DOWNLOADS=never`,
`UV_CACHE_DIR=/evidence/uv-cache`, `PYTHONUTF8=1`, `RUNNER_TEMP=/tmp/m1b1-1-runner`.
Exact script and dispatch results are in
`.validation/m1b1-1-linux312-final-evidence/validate.sh` and `docker-dispatch.json`.

## Interrupted bundles and ordinary demos

Each successful cancellation workflow checked strict report validation and
actual fixture counts, retained values/schema, SQLite integrity and foreign
keys, baseline/final confirmations, committed summaries and budget totals.
Default JSON equalled explicit JSON; text accepted and distinguished recorded
verification from execution. Relocated replay ran outside the repository with
the original source/assets/bundle paths unavailable and established three new
executed TARGET_FAILURE confirmations. Source and every bundle-file hash
remained unchanged.

| Search boundary | Original → final rows | Committed attempts / acceptances | Known executions |
| --- | --- | --- | --- |
| Acceptance prepared before checkpoint publication | 2 → 2 | 1 / 0 | 9 |
| Cached attempt prepared before publication | 2 → 2 | 1 / 0; cache hits 0 | 7 |
| Completed PASS evaluation before attempt publication | 2 → 2 | 0 / 0 | 7 |
| Complete acceptance checkpoint already published | 2 → 1 | 2 / 1 | 9 |
| First / second confirmation, no prior acceptance | 2 → 2 | 1 / 0 | 7 / 8 |
| First / second confirmation after prior acceptance | 4 → 2 | 4 / 1; cache hits 1 | 10 / 11 |
| Actual Linux SIGINT at pending acceptance | 2 → 2 | 1 / 0; cache hits 0 | 9 |

These real lifecycle cases had zero unknown launches; separate deterministic
accounting tests cover known nonlaunch, known execution and unknown constructor
states, conservative charging and no duplicate charging. Budget-six, empty,
irreducible and uninterrupted controls also pass full lifecycles. Abort tests
cover baseline, compact export, final confirmation, a second interruption during
graceful finalization, and interrupted counter recovery. Pre-existing output
returns exit 2 before any oracle executes and retains every file unchanged.

Linux's actual SIGINT smoke used a child `READY acceptance_before_publication`
stdout handshake, then `os.kill(child_pid, SIGINT)`, bounded waits and cleanup.
It did not use randomized signals or a sleep race. Per-case reports, new replay
confirmations and source hashes are retained in each clean copy's pytest
`lifecycle-evidence.json`; Linux additionally preserves them under its evidence
directory's `cancellation-lifecycles/` and `cancellation-results.json`.
`.validation/cancellation-workflow-summary.json` summarizes focused Windows
evidence.

Both normal demos ran as full-suite acceptance tests on both platforms. Actual
observations, not engine constants:

| Target | Original counts | Final counts | Known / charged executions | Cache hits |
| --- | --- | --- | --- | --- |
| Duplicate export | entries 2400, owners 6, projects 24 (2430) | entries 2, owners 1, projects 2 (5) | 54 / 54 | 11 |
| Aggregate threshold | crates 3, parcels 8 (11) | crates 1, parcels 2 (3) | 18 / 18 | 5 |

Acceptance verified schema, user_version, unchanged retained values, integrity,
foreign keys, original database/asset hashes, fresh final verification, replay
and bundle immutability. The duplicate replay used an outside-repository
relocation; the installed-wheel threshold workflow also relocated its bundle.
An additional Windows read-only inspection of both preserved demo bundles ran
default/explicit JSON and text and compared all bundle hashes. Exact command
was `.venv\Scripts\python.exe .validation/m1b1_1_demo_inspection.py`; results and
text are under the final Windows evidence directory. Each platform's
`acceptance-results.json`, `duplicate-report.json` and `threshold-report.json`
retain actual counts and invocation totals.

## Genuine compatibility and distributions

The existing recipe generated genuine pre-M1b version-1 bytes from archived
commit `ba40d64db748d974c36666294a1cc4500c79c25f`, without hand-constructing a
report or migrating it. Final repaired-runtime validation used a fresh directory:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.validation\uv-cache'
$env:UV_OFFLINE = '1'
.tools\bin\uv.exe run --locked python tests/compatibility_smoke.py --directory .validation/m1b1-1-compat-final
```

It passed original-report equality for default/explicit JSON, text inspection,
three new relocated TARGET_FAILURE replay confirmations, and unchanged source
and all bundle hashes. Its historical reduction was 11 → 3 rows with 18
executions; replay added three confirmations without rewriting that report.
`.validation/m1b1-1-compat-final/compatibility-result.json` records results.
An earlier generate/validate phase pair also passed; attempting to validate that
already-relocated scratch directory again returned FileNotFoundError because
the recipe had intentionally moved its bundle. The fresh final recipe above
completed successfully; no old bundle was overwritten.

Both clean-copy builds generate a wheel and source distribution. Windows's
unchanged CI wheel block passed installation with no index/dependencies into a
fresh OS-temp environment outside the entire repository, `--help`, actual
threshold generation/reduction, default/explicit JSON and text inspection,
relocated three-confirmation replay, and unchanged bundle hashes. A separate
isolated import-origin check resolved ReproSeed under that environment's
`Lib/site-packages`, not source. Linux's same CI recipe passed with its temporary
environment under `/tmp`, including 11 → 3 rows / 18 reduction executions and
three fresh relocated replay confirmations. Its isolated import resolved to
`/tmp/m1b1-1-origin/lib/python3.12/site-packages/reproseed/__init__.py`.
Both platforms installed with `--no-deps`; the CI wheel installation also used
`--no-index`. Linux's `validation-result.json`, `complete.log`, `build.log`,
`wheel-ci.log`, `origin-install.log` and `origin.log` preserve those checks.

The final root-source distribution build includes this completed report:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.validation\uv-cache'
.tools\bin\uv.exe build --no-sources --offline --out-dir .validation/m1b1-1-final-dist
.venv\Scripts\python.exe .validation/m1b1_1_distributions.py
```

Content verification checks all 11 wheel modules against current source and
both tested Windows/Linux wheels, no `Requires-Dist` runtime dependencies,
source-distribution inclusion of current completion/CI/compatibility recipe and
new regression files, and absence of generated databases, bundles, bytecode,
Git state, environments or validation caches. Evidence is
`.validation/m1b1-1-final-dist/contents-check.json`. These package files were
built locally and were not published.

## Limits and final review

No new hosted run, Ubuntu/Python 3.14 execution, or Windows console-signal test
was run for this patch. Linux used the available Debian/Python 3.12 runtime and
uv 0.8.22, not the hosted image/tool version. Historical M1b.1 hosted run
38455095031 is recorded separately in the roadmap and is not evidence for this
patch. Ordinary runtime dependencies remain standard library only. Supported
schema scope, source acquisition, portable bundle format, private replay
acquisition, CLI meanings and strict reader are preserved.

The final review checked source/tests/docs for scope creep, weakened assertions,
accidental generated files, inaccurate interruption guarantees and validator
bypasses. No M1b.2 features, retries, continue-on-error or broad skips were
added. Existing test changes only adapt stubs to the optional caller-owned
invocation state. `report.py`, CLI, CI, project/lock files and historical reports
are unchanged. Current source and test files match both full-suite clean copies.
`git diff --check` passes. All changes are unstaged and uncommitted; no commit,
push, PR, tag, release or package publication was performed. HEAD remains the
starting commit on `main`. `git diff --name-only --cached` is empty.

Final `git status --short`:

```text
 M AGENTS.md
 M CONTRIBUTING.md
 M README.md
 M SECURITY.md
 M docs/architecture.md
 M docs/roadmap.md
 M src/reproseed/oracle.py
 M src/reproseed/reducer.py
 M src/reproseed/workflow.py
 M tests/test_inspection.py
 M tests/test_report_validation.py
?? docs/m1b1-1-completion.md
?? tests/test_cancellation_workflow.py
?? tests/test_invocation_accounting.py
?? tests/test_reducer_cancellation.py
```
