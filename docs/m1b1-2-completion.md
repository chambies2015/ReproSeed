# M1b.1.2 — Windows cancellation cleanup

## Starting state and hosted failure

Started on `main` at reviewed commit `b2bcc51f691d7c5dfe30345199f884dd7e7bb97e`.
`git status --short` was empty and the diff against that commit was empty. No
user changes needed preservation or relocation. Work remains in this checkout;
no reset, staging, commit, push, PR, tag, release or package publication is authorized.

M1b.1.1 [run 38460548154](https://github.com/chambies2015/ReproSeed/actions/runs/38460548154)
passed Ubuntu/Python 3.12 and Ubuntu/Python 3.14. Windows job
[115514293016](https://github.com/chambies2015/ReproSeed/actions/runs/38460548154/job/115514293016)
failed; its build and installed-wheel steps were skipped. This was not an accepted
hosted gate. The GitHub connector recovered the raw job log, job status metadata
and concise excerpt under `.validation/m1b1-2-evidence/hosted-*`. The initial
`gh run view 38460548154 --job 115514293016 --log` attempt returned exit 4 because
the local CLI was unauthenticated; the connector retrieval succeeded.

Relevant recovered excerpt (timestamp prefixes omitted):

```text
Microsoft Windows Server 2025
10.0.26100
Using CPython 3.12.10 interpreter
collected 277 items
assert ready.exists()
assert interrupted.value.executed is True
> assert not Path(ready.read_text()).exists()
WindowsPath('C:/Users/RUNNER~1/AppData/Local/Temp/reproseed-oracle-qc0uu3ej').exists
tests\test_oracle.py:266: AssertionError
1 failed, 273 passed, 3 skipped in 70.34s
```

The hosted log establishes surviving disposable-directory state after cancellation
and known execution. It does not establish whether a child survived or the exact
resource preventing deletion; the later sentinel assertion was not reached.

## Investigation: observations and limits

The original code closed its kill-on-close Job, waited only for the Popen parent,
closed pipes, joined readers briefly, then used TemporaryDirectory with
`ignore_cleanup_errors=True`. Termination requests are asynchronous. This sequence
did not observe termination of the resource-holding descendants before deletion.

Natural original-test reproduction on Windows 10 build 19045 / CPython 3.12.15:
15 of 20 iterations passed, five failed the original directory assertion (3, 6,
7, 8, 12). This was a finite batch, not retry-until-green. Original source/test bytes
were obtained with `git show` into isolated tool-owned scratch, without resetting
the checkout. Every iteration's stdout, stderr, exit and elapsed time remain in
`.validation/oracle-baseline-cleanup/results.json`.

Two instrumented original-source batches used readiness, exact Job membership,
process handle signals and deletion-error observation. The first batch observed
the actual code parent and the child's virtualenv launcher: two passed its stronger
assertions, 18 failed, and 11 directories survived. Those results remain under
`.validation/oracle-instrumented-original/`. The corrected second batch observed
both actual interpreters from their readiness PIDs: all 20 failed immediate
process-termination assertions and 10 directories survived. Every probe proved
both ready interpreters belonged to this invocation's Job. After original cleanup
returned, the outer Popen launcher had exited but both actual interpreters were
still unsignaled. Every deletion attempted encountered WinError 32
(sharing violation); retained directories also encountered WinError 145
(directory not empty). Corrected evidence is under
`.validation/oracle-instrumented-original-ready/`, including all phase observations,
Win32 codes and elapsed times.

The phase logs also show both tool-owned readers stopping before directory removal;
the original source closes its pipes before that removal. They do not establish a
reader leak as the cause. An unsignaled process object means termination is not
complete; these observations do not distinguish ongoing thread execution from
pending process/I/O teardown. Sharing violations observed during that interval,
successful later owned cleanup and deterministic transient/permanent-error tests
are kept separate from assumptions about an external permission or security lock.

This demonstrates a local descendant-completion/resource-release race and silent
best-effort deletion failure. It supports the hosted failure hypothesis, but does
not prove the hosted runner had the identical obstacle. It does not demonstrate
a CPython direct-parent wait bug: Windows virtualenv launchers and the interpreters
running the synthetic code have different PIDs. Hosted CPython's `poll()` observes
the direct process handle before caching its code. The harness therefore records
actual interpreter readiness PIDs and launcher PIDs separately.

An isolated API probe on CPython 3.14.7 showed successful own-Job assignment and
termination, with ActiveProcesses already zero while a Popen handle remained open.
It disproved the initial assumption that that particular retained handle necessarily
prevents zero on this runtime; no completion design depends on that assumption.
Probe source/output are in `.validation/m1b1-2-evidence/job-api-probe*`.

Three early strengthened-test draft runs each reported 2 failed, 30 passed,
1 skipped. They exposed insufficient startup time for two-process readiness,
the denied fallback described below, and missed exiting Job members in the first
repair draft. A later run reported 8 failed, 24 passed, 1 skipped because a new
handshake assertion exposed child-launcher/actual-child PID mismatch; its readiness
failures were harness defects. All draft observations are preserved in
`.validation/oracle-strengthened-*`. After fixing that handshake, the same supported
tree assertions passed: 32 passed, 1 POSIX-only skip on Windows 3.12.15.

## Repair and ownership

One `_Cleanup` object starts a monotonic 1.5-second allowance when cleanup begins.
Tree termination/completion, parent wait, reader joins and actual transient
deletion retries consume its remaining time; none resets the deadline. This
allowance bounds waits and retries, not synchronous OS calls that an external
filesystem or kernel can stall. It is independent of the configured runtime/pipe
deadline and does not impose a full delay on successful calls.

For the supported assigned Windows tree:

1. Enumerate member IDs and acquire observation handles before termination. Confirm
   each handle belongs to this exact invocation's Job. Retain identities even if
   the Job list later drops exiting members. Failed OpenProcess acquisition does
   not suppress a second snapshot of that PID.
2. Request TerminateJobObject on that owned Job only. Capture a second snapshot to
   include members associated during the first snapshot. Grow incomplete process
   lists, including successful API results with fewer returned than assigned IDs.
3. Wait on captured member process handles with remaining time, then release every
   acquired observation handle in `finally`. Process signals establish termination;
   Job signaling and ActiveProcesses reference-lifetime counts do not supply it.
4. Close the Job once through an idempotent owner, retaining kill-on-close fallback.
   Ownership is recorded before return transfer; exceptional assignment/transfer
   paths close their acquired handles. Popen retains ownership of its own handle.
5. Wait/reap the parent, stop/join readers and close tool-owned pipes, then remove
   only the exact mkdtemp root. A successful delete returns immediately. Only actual
   Windows access/sharing/lock/nonempty failures retry, at most 10 ms per remaining
   allowance interval. Persistent obstruction warns with an operation/error code.

The directory remover refuses a replaced symlink/junction root; Python 3.12 rmtree
does not traverse nested symlink/junction targets. Readonly attribute recovery is
restricted to Windows deletion primitives and non-reparse entries; no general
callback, recursive collection or unrelated path cleanup was added. Nested
disappearance does not silently abandon another surviving file/root. Source files
and bundle payloads are never deletion targets.

No inherited/parent Job is opened, terminated or reconfigured. Job assignment can
still fail or race process creation. Fallback retains bounded `taskkill /PID` on
the invocation's exact Popen PID, `/T /F`, then direct parent kill/wait. Detached or
unassigned descendants can escape. In this restricted desktop environment,
taskkill returned 1 with Access denied in approximately 0.032 seconds; the parent
was stopped, a child/locked directory could remain, and warnings/independent
observations recorded that limitation. The new unavailable-Job integration requires
complete cleanup on taskkill success, and bounded cancellation plus explicit
obstruction evidence on denied fallback. It does not relax the original supported
Job cancellation test. Evidence is `.validation/oracle-fallback-diagnostic/` and
the fallback test's `fallback-attempts.json` / `cleanup-observations.json`.

Initial cancellation keeps known/unknown launch evidence. A further interruption
during cleanup carries an internal abort flag; InvocationCounter publishes its
existing charge/interruption evidence once, then raises AbortReduction instead of
salvaging search. The flag is not serialized. Existing accounting-recovery abort
behavior, confirmation counts, exact marker classification and strict version-1
validation are unchanged. Cleanup obstruction never substitutes another oracle
outcome or replaces OracleInterrupted with a secondary filesystem exception.

Final ownership review also replaced thread-wide `sys.exception()` inference with
explicit handlers for this invocation's own exceptional exits. A caller's already
handled exception must not close a newly assigned Job or turn the first cleanup
interrupt into a second one. Separate deterministic caller-context tests cover both.

## Regression coverage and validation

Real tree tests cover cancellation after both interpreters are ready, inherited
and closed pipes, descendant cwd/open staged database, parent exit before child
completion, normal completion with a remaining child, timeout, output limit,
successful exact-Job membership and unavailable assignment. Process termination
and directory removal are separately recorded before any assertion can prevent
teardown. Every helper has bounded waits and recovery for only its own observed
process identities and verified temporary root, after product observations.

Teardown never reopens an unobserved metadata PID for termination; a departed PID
could have been reused. Failed readiness uses the synthetic child's finite watchdog
when no identity was acquired. A watcher-timeout assertion runs after owned cleanup.

Early drafts increased the pipe-holding startup cutoff from 0.2 to 0.8 seconds
and the live-tree timeout cutoff from 0.4 to 0.8 seconds while retaining their
actual total `<1.8s` / `<4s` assertions. Further finite-probe failures demonstrated
that an elapsed startup cutoff could still precede the handshake under concurrent
validation load. The final tests instead inject a monotonic deadline jump only
after both actual processes are proven ready; the pipe-holding case also observes
parent termination while the child remains live. A latched nine-second offset to
an eight-second startup guard triggers deadline classification, then stays fixed
through cleanup so the 1.5-second allowance still advances in real elapsed time.
Only oracle_module.time is proxied; the helper clock and total bounds remain real.
These two cases combine deterministic deadline injection with real process/resource
integration, not natural elapsed-timeout evidence. The separate real 0.15-second
single-process timeout test and real output-limit/cancellation cases are unchanged.
No production sleep, broader timeout policy or hosted retry was added.

Deterministic tests cover shared remaining time, successful fast deletion,
transient/permanent obstruction, error and permission branches, readonly deletion,
link refusal, process-list disappearance/new arrivals/partial lists, failed handle
acquisition, exact membership/PID reuse, Job create/configure/open/assign failures,
handle release on interruption and further cleanup cancellation. Tests also verify
one known accounting charge and AbortReduction after a second real-launch cleanup
interruption. Final root focused validation on Windows 3.12.15 passed 48 tests
(29 cleanup primitives, 19 accounting tests); the restricted taskkill fallback
reported two expected warnings. The existing accounting/reducer/lifecycle run
passed 45 with one POSIX-only skip before adding the two new accounting cases.

The subsequent caller-context changes passed 50 focused tests (31 cleanup, 19
accounting), and the final two caller-context tests passed after refining their
injection. These are intermediate root checks; final clean-copy results below
identify the complete source snapshots actually exercised.

The first clean-copy Linux suite reported 288 passed, 24 skipped, one failed in
308.45 seconds. The new normal-completion test observed parent terminated, child
still pending and directory already absent at 0.618833 seconds; TARGET_FAILURE
and its `<1.8s` bound had passed. POSIX SIGKILL is asynchronous and Linux unlink
does not require all process references to disappear. That new immediate assertion
exceeded the existing POSIX cleanup contract. The final harness preserves this
immediate process/directory evidence in `cleanup-immediate-observations.json`, then
performs a Linux-only read-only condition observation for at most 0.2 seconds on
the same process identity, accepting absence/zombie state as terminated. It still
fails a live process at the deadline and checks the original total wall bound
after observation. Windows keeps immediate process/dir assertions. No unconditional
sleep or new POSIX process supervisor was added. The failed Linux batch is retained;
its build/wheel steps did not run after failure.

## Finite Windows probe record

The original-test column uses CPython 3.12.15 and the reviewed source/test. The
two instrumented columns report directory state independently of process state;
the corrected batch observed both actual interpreter handles unsignaled in every
iteration, including the ten with successful directory removal. Their elapsed
times were 0.437–0.641 seconds from launch through cancellation return. Complete
individual phase/error/timing records are retained in the scratch locations above.

The first repaired batch used exact CPython 3.12.10. Each iteration ran eight
real-process cases: seven supported Job cases plus unavailable-Job fallback. All
140 supported cases proved both interpreter signals and absent directories; all
20 fallback cases recorded denied taskkill, incomplete cleanup warnings and bounded
own-harness recovery. Eight tests passing does not claim successful fallback
cleanup. Source/test hashes stayed unchanged through this finite batch. The final
review changed caller-context ownership and teardown identity handling; a separate
fresh final batch below validates those final bytes. Neither batch is a CI retry.

The next batch, after caller-context and teardown review, had 19 passing
iterations and one failure in iteration 15's timeout readiness handshake. Its
child-ready and tree-launched `.tmp` files had not completed atomic rename when
the 0.4-second invocation deadline expired; no interpreter identity was acquired.
The oracle correctly returned UNRESOLVED and cleanup/return took 1.312 seconds.
The old observation helper's `Path('')` fallback incorrectly labeled an unknown
directory as present; that particular raw record means directory identity was
unknown, not a proved private-directory leftover. The helper now records `null`
for unknown directory state. All other seven cases in iteration 15 and all eight
cases in the other 19 iterations passed. The complete batch remains under
`.validation/oracle-repaired-31210-final/`. The final readiness-budget batch uses
the targeted 0.8-second handshake allowance with the unchanged four-second bound;
its fresh results are recorded separately below. That 0.8-second-cutoff batch also
finished 19 passing iterations and one pipe-case readiness failure in iteration 6
at 1.469 seconds, with unknown directory identity explicitly null. All other cases
passed; the complete batch is `.validation/oracle-repaired-31210-ready-budget/`.
This second setup cutoff motivated the structural test-only deadline hook above,
rather than another startup-timeout increase. Its final fresh finite batch is
`.validation/oracle-repaired-31210-boundary/`, with the injected boundary labeled
in each affected case's evidence.

| Iteration | Original test | Earlier instrumented directory retained | Corrected instrumented directory retained | First repaired batch (8 cases), seconds |
| --- | --- | --- | --- | --- |
| 1 | PASS | no | no | PASS, 7.015 |
| 2 | PASS | no | yes | PASS, 6.265 |
| 3 | FAIL | no | yes | PASS, 6.547 |
| 4 | PASS | no | yes | PASS, 8.172 |
| 5 | PASS | yes | no | PASS, 7.328 |
| 6 | FAIL | yes | no | PASS, 7.032 |
| 7 | FAIL | yes | yes | PASS, 7.484 |
| 8 | FAIL | no | yes | PASS, 8.110 |
| 9 | PASS | yes | no | PASS, 7.657 |
| 10 | PASS | no | no | PASS, 7.766 |
| 11 | PASS | no | no | PASS, 6.781 |
| 12 | FAIL | yes | no | PASS, 7.203 |
| 13 | PASS | no | no | PASS, 7.312 |
| 14 | PASS | yes | no | PASS, 6.719 |
| 15 | PASS | yes | yes | PASS, 6.860 |
| 16 | PASS | yes | no | PASS, 7.500 |
| 17 | PASS | yes | yes | PASS, 8.391 |
| 18 | PASS | no | yes | PASS, 8.391 |
| 19 | PASS | yes | yes | PASS, 7.531 |
| 20 | PASS | yes | yes | PASS, 7.141 |

The exact repeat runner is retained as `.validation/oracle_repeated_probe.py`;
its results include command argv, runtime, initial/final source hashes, every
pytest stdout/stderr/exit and per-case process/directory/fallback observations.

All subsequent iterations, including the two failed readiness probes:

| Iteration | Caller-review batch | Elapsed-cutoff batch | Final structural-boundary batch |
| --- | --- | --- | --- |
| 1 | PASS, 6.782s | PASS, 7.937s | PASS, 6.032s |
| 2 | PASS, 6.719s | PASS, 7.812s | PASS, 6.922s |
| 3 | PASS, 6.781s | PASS, 7.000s | PASS, 6.000s |
| 4 | PASS, 6.859s | PASS, 7.406s | PASS, 6.312s |
| 5 | PASS, 6.484s | PASS, 8.813s | PASS, 6.562s |
| 6 | PASS, 7.703s | FAIL readiness, 10.360s | PASS, 6.250s |
| 7 | PASS, 6.891s | PASS, 8.375s | PASS, 6.171s |
| 8 | PASS, 7.000s | PASS, 9.812s | PASS, 8.469s |
| 9 | PASS, 7.250s | PASS, 8.782s | PASS, 7.016s |
| 10 | PASS, 8.531s | PASS, 9.797s | PASS, 6.828s |
| 11 | PASS, 8.265s | PASS, 9.609s | PASS, 6.954s |
| 12 | PASS, 8.094s | PASS, 8.016s | PASS, 7.594s |
| 13 | PASS, 7.281s | PASS, 7.859s | PASS, 8.484s |
| 14 | PASS, 7.844s | PASS, 8.265s | PASS, 10.172s |
| 15 | FAIL readiness, 8.140s | PASS, 8.188s | PASS, 8.500s |
| 16 | PASS, 7.360s | PASS, 8.047s | PASS, 6.750s |
| 17 | PASS, 7.250s | PASS, 8.078s | PASS, 6.907s |
| 18 | PASS, 7.797s | PASS, 7.969s | PASS, 7.157s |
| 19 | PASS, 8.312s | PASS, 8.125s | PASS, 6.687s |
| 20 | PASS, 7.188s | PASS, 9.359s | PASS, 6.656s |

The final batch passed 160 cases in 20 independent pytest runs, with unchanged
source/test hashes throughout. It separately proved immediate termination of
both actual process handles and directory removal in all 140 supported Job cases.
The 20 unavailable-Job cases retained the documented taskkill access-denial
limitation before bounded harness recovery. Forty of the 160 cases explicitly
record deterministic timeout-boundary injection (20 after ready live-tree,
20 after parent exit with live child pipes); the other cases retain their real
trigger/clock behavior. Exact final repeat command:

```text
.venv\Scripts\python.exe .validation/oracle_repeated_probe.py --directory .validation/oracle-repaired-31210-boundary
```

## Validation commands and runtimes

The repository's `.tools/bin/uv.exe` is uv 0.13.0. Root locked sync passed; final
fresh Windows copies select the isolated downloaded CPython 3.12.10 interpreter
at `.validation/m1b1-2-python/cpython-3.12.10-windows-x86_64-none/python.exe`.
Initial sandbox network retrieval failed, then approved tool access downloaded
that tool-owned runtime. No system Python or service was reconfigured. Windows
is 10 build 19045, not hosted Server 2025 build 26100. Exact local Python:
`3.12.10 (main, May 30 2025, 05:39:07) [MSC v.1943 64 bit (AMD64)]`, SQLite 3.47.1.
Initial root probes used CPython 3.12.15 / MSC 1944 / SQLite 3.53.1.

Linux uses the cached `ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim`
Docker image, network disabled, CPython 3.12.11 / GCC 12.2.0 / SQLite 3.40.1,
glibc 2.36 on Linux 6.18.33.2-microsoft-standard-WSL2. The direct WSL inventory
was denied in the sandbox; approved access to the existing Docker engine worked.
Linux uv is 0.8.22, not the hosted 0.13.0 tool version. No Linux/Python 3.14
execution or Windows console Ctrl+C integration was performed for this repair.
Windows uses `_thread.interrupt_main` against real subprocesses, not a console
control event. Linux's existing real SIGINT lifecycle test is separately recorded.

Fresh copies omit `.validation`, `.venv`, distributions and ignored caches;
`copy.json` records file SHA256 values and verifies those directories absent.
They run the unchanged CI preparation and full test block with Git Bash on
Windows / Bash on Linux. Development dependencies use locked cached resolution
(`UV_OFFLINE=1`), `PYTHONUTF8=1`, and remove `PYTHONPATH`, `PYTHONHOME`,
`VIRTUAL_ENV`. Exact argv, cwd, durations, exits and logs are preserved under
`.validation/m1b1-2-evidence/{win31210,linux312,win31210-final,linux312-final}/`.

```text
uv sync --locked --python <isolated 3.12.10 interpreter>  # Windows
uv sync --locked --python 3.12                         # Linux
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy --platform linux
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run --locked pytest --basetemp=.validation/pytest
uv build --no-sources
```

The retained `.validation/m1b1_2_validate.py` creates Windows copies and runs
their checks, the unchanged extracted installed-wheel CI block, import-origin
checks and acceptance/lifecycle evidence preservation. Linux's retained
`linux312-final/validate.sh`, `commands.tsv` and `docker-dispatch.log` record
the equivalent container commands. Full distribution/wheel validation is local;
packages are not published. The first Windows snapshot passed 308 tests with
five skips/two warnings in 187.14 seconds, then built both distributions and
passed the external installed-wheel workflow. The first Linux snapshot failed
the new immediate POSIX observation described above; all its results are retained.

Root focused commands actually executed included:

```text
.venv\Scripts\python.exe -m pytest tests/test_invocation_accounting.py tests/test_reducer_cancellation.py tests/test_cancellation_workflow.py --basetemp=.validation/m1b1-2-accounting
.venv\Scripts\python.exe -m pytest tests/test_oracle_cleanup.py tests/test_invocation_accounting.py --basetemp=.validation/m1b1-2-boundaries-reviewed
.venv\Scripts\python.exe -m pytest tests/test_oracle_cleanup.py -k callers --basetemp=.validation/m1b1-2-caller-context
```

The final genuine compatibility recipe uses a fresh directory; it archives
reviewed pre-M1b commit `ba40d64db748d974c36666294a1cc4500c79c25f` to generate
real historical version-1 bytes, then reads/replays with current code. Its exact
command is in `compatibility-final-command.json`; historical reports are not
hand-constructed or migrated. It passed: 11 → 3 rows / 18 historical executions,
default and explicit JSON equal the original report, text inspection succeeds,
three new relocated TARGET_FAILURE confirmations, unchanged source and every
bundle-file hash. Final output is `.validation/m1b1-2-compat-final/compatibility-result.json`.

## Interrupted lifecycles, demos and immutability

Both complete product snapshots exercised the existing real SQLite/subprocess
interrupted-bundle lifecycles, strict report validation, fixture counts, retained
values/schema, integrity/FKs, three baseline/final confirmations, default/explicit
JSON equality, text inspection and relocated three-confirmation replay. Source
and all bundle-file hashes stayed unchanged. There were 12 preserved lifecycle
records on Windows and 13 on Linux, including Linux's real SIGINT pending-
acceptance handshake. Recorded outcomes from the completed snapshots:

| Boundary/control | Original → final rows | Attempts / accepted changes | Known executions | New replay confirmations |
| --- | --- | --- | --- | --- |
| First / second candidate confirmation, no prior acceptance | 2 → 2 | 1 / 0 | 7 / 8 | 3 each |
| First / second confirmation after prior acceptance | 4 → 2 | 4 / 1 | 10 / 11 | 3 each |
| Pending acceptance before checkpoint publication | 2 → 2 | 1 / 0 | 9 | 3 |
| Pending cached attempt before publication | 2 → 2 | 1 / 0 | 7 | 3 |
| Completed PASS before attempt publication | 2 → 2 | 0 / 0 | 7 | 3 |
| Published acceptance interrupted afterward | 2 → 1 | 2 / 1 | 9 | 3 |
| Budget-six control | 2 → 2 | 0 / 0 | 6 | 3 |
| Empty control | 0 → 0 | 0 / 0 | 6 | 3 |
| Irreducible control | 1 → 1 | 1 / 0 | 7 | 3 |
| Uninterrupted control | 2 → 1 | 3 / 1 | 9 | 3 |
| Actual Linux SIGINT at pending acceptance | 2 → 2 | 1 / 0 | 9 | 3 |

These lifecycle records have no unknown launches. Separate deterministic accounting
tests preserve known nonlaunch, known execution, unknown construction, conservative
charging, coherent recovery and no double charge. The new further-cleanup cases
record one known execution before AbortReduction. Existing abort tests still cover
baseline, compaction, final confirmation, accounting recovery and further graceful-
finalization interruption. No failed confirmation publishes a verified bundle;
pre-existing output remains untouched. Per-case `lifecycle-evidence.json` copies
and `cancellation-results.json` preserve actual reports, source hashes and replay
results under each platform's evidence directory.

Both normal demos passed on Windows 3.12.10 and Linux 3.12.11. Counts are observations,
not reducer constants:

| Target | Original counts | Final counts | Known / charged reduction executions |
| --- | --- | --- | --- |
| Duplicate export | entries 2400, owners 6, projects 24 (2430) | entries 2, owners 1, projects 2 (5) | 54 / 54 |
| Aggregate threshold | crates 3, parcels 8 (11) | crates 1, parcels 2 (3) | 18 / 18 |

The duplicate fixture exceeds 2,000 original rows and finishes below eight.
Acceptance checks preserved retained values, declared schema and metadata,
integrity/FKs, original database/assets hashes, fresh final verification and
bundle immutability through replay. The duplicate acceptance replay relocates
outside the repository; the installed-wheel threshold workflow relocates its
bundle and makes original example paths unavailable. Extra default/explicit JSON
and text inspection accepts both demo bundles and leaves every file hash unchanged.
`acceptance-results.json`, `duplicate-report.json` and `threshold-report.json`
retain the counts, reports and hash maps.

The unchanged CI installed-wheel block installs with `--no-index --no-deps`
into a fresh OS-temp environment outside the source checkout, runs help, actual
threshold generation/reduce, all three inspection modes and relocated replay.
An independent `python -I` import-origin check resolves ReproSeed in that
environment's `site-packages`. Wheel metadata retains no runtime Requires-Dist;
the runtime remains standard-library-only.

## Complete platform runs

Every full run is retained, including the failed initial Linux harness snapshot.
The last snapshot names identify the final structural deadline hooks. Production
source equality across post-factory-review snapshots is separately recorded in
`.validation/m1b1-2-evidence/production-source-snapshot-equality.json`.

| Evidence directory suffix | Full-suite result | Pytest elapsed | Build / installed wheel |
| --- | --- | --- | --- |
| win31210 | 308 passed, 5 skipped, 2 warnings | 187.14s | passed / passed |
| linux312 | 288 passed, 24 skipped, 1 failed (new immediate POSIX assertion) | 308.45s | not run after failure |
| win31210-final | 310 passed, 5 skipped, 2 warnings | 184.23s | passed / passed |
| linux312-final | 290 passed, 25 skipped | 290.26s | passed / passed |
| win31210-ready-final | 310 passed, 5 skipped, 2 warnings | 213.91s | passed / passed |
| linux312-ready-final | 290 passed, 25 skipped | 318.92s | passed / passed |
| win31210-boundary-final | 310 passed, 5 skipped, 2 warnings | 209.99s | passed / passed |
| linux312-boundary-final | 290 passed, 25 skipped | 338.98s | passed / passed |

Windows's five skips are two symlink privilege failures (WinError 1314), POSIX
real SIGINT lifecycle, POSIX executable-file semantics and POSIX signal return
codes. Its two warnings are intentional real-launch accounting interruption
cases that occur before Job assignment and encounter denied taskkill fallback.
Linux's 25 skips are the Windows junction/Job/fallback/API-specific cases; Linux
executes the symlink, executable-mode and actual SIGINT tests. No supported
cancellation or directory assertion is skipped or xfailed. All successful full
pipelines run locked sync, lint, format, both mypy targets, distribution build,
the unchanged installed-wheel block and independent external import-origin check.

The last Windows installed-wheel workflow took 23.593 seconds and passed; the
Python import resolved in the external installation, not this checkout. Its
demo/lifecycle/inspection results agree with the observations above. Source and
test file hashes in its `copy.json` identify the final files exercised.

The last Linux installed-wheel workflow took six seconds and passed; isolated
imports resolved under `/tmp/m1b1-2-origin/lib/python3.12/site-packages/reproseed/`.
Its 13 lifecycle records include the real SIGINT case, each with three executed
final and three new replay confirmations, zero unknown launches and known counts
equal to charges. The last Windows snapshot has the corresponding 12 lifecycle
records. Both last snapshots reconfirmed the normal demo counts and all immutability
checks. All final source and test SHA256 values are captured in their `copy.json`.

The root final wheel/source-distribution content check compares all 11 wheel
modules to current source and both last tested wheels; checks absence of runtime
Requires-Dist; compares current source/test hashes to both tested manifests;
checks the sdist contains the current completion report, historical reports,
CI/compatibility recipes and regressions; and rejects generated databases,
sidecars, bytecode, Git state, environments or validation caches. Final commands:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.validation\uv-cache'
.tools\bin\uv.exe build --no-sources --offline --out-dir .validation/m1b1-2-final-dist
.venv\Scripts\python.exe .validation/m1b1_2_distributions.py
```

Package/content-check results are retained under `.validation/m1b1-2-final-dist/`;
these are local distribution artifacts, not published packages.

## Final handoff and limits

The local repair addresses the demonstrated missing descendant-completion boundary;
the hosted log's exact obstacle remains an inference. Hosted validation of these
unpushed changes is pending Dan's review, commit and push. Earlier hosted runs and
the local matrices above are not a hosted pass of this repair. Windows Server 2025
behavior and Windows console Ctrl+C remain unexercised here. The exact hosted
CPython version was exercised locally, on a different Windows OS build.

Unavailable assignment, denied taskkill, escaped descendants, persistent external
locks and stalled synchronous OS calls retain documented best-effort limits.
The finite supported-tree probes establish the boundaries actually observed; they
do not promise cleanup under every asynchronous exception or hostile interference.
The final review checked shared deadlines/no per-step reset, member/Job ownership,
handle leaks/double close, known/unknown execution charging, abort-before-salvage,
owned-only deletion, readiness/assertion preservation and claims by platform.

CI matrix, action pins, permissions, full-suite and installed-wheel blocks are
unchanged. No retries, continue-on-error, new CLI diagnostics, adapters, schema
support, search strategy, serialized report format or M1b.2 fixture was added.
Reducer, report validator, inspection, bundle acquisition, lock/project files and
historical reports are unchanged. New diagnostics are confined to test/evidence
scratch and sanitized cleanup warnings. All source/runtime changes use the
standard library.

HEAD remains `b2bcc51f691d7c5dfe30345199f884dd7e7bb97e` on `main`.
`git diff --check` passes and `git diff --name-only --cached` is empty. Changes
are unstaged and uncommitted. No commit, push, PR, tag, release or package publication
was performed. Final `git status --short`:

```text
 M CONTRIBUTING.md
 M SECURITY.md
 M docs/architecture.md
 M docs/roadmap.md
 M src/reproseed/oracle.py
 M src/reproseed/workflow.py
 M tests/test_invocation_accounting.py
 M tests/test_oracle.py
?? docs/m1b1-2-completion.md
?? tests/test_oracle_cleanup.py
```

## Primary references

- [TerminateProcess completion semantics](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess)
- [TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject)
- [Job Objects and signaling](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Job process ID lists](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list)
- [ActiveProcesses lifetime semantics](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information)
- [Python TemporaryDirectory cleanup](https://docs.python.org/3.12/library/tempfile.html)
- [Hosted CPython 3.12.10 subprocess source](https://github.com/python/cpython/blob/v3.12.10/Lib/subprocess.py#L1426-L1456)
