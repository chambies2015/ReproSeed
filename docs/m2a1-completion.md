# M2a.1 completion evidence

## Scope and starting state

Work began on `main` at reviewed commit
`eb8108dece9055dc9180826f42de03363cb64cbe` with a clean working tree and empty
index. M2a had been implemented locally and pushed. This patch repairs the
bundle-path-security test setup and adds evidence for its timing boundary.
Runtime implementation, version-1 formats, five applications, CI matrix,
action SHAs and permissions are unchanged. M2b remains planned.

All inputs are synthetic. Scratch directories and retained command evidence
are tool-owned ignored `.validation/m2a1-*` paths. No reset, staging, commit,
push, PR, tag, release or package publication was performed. Dan must review,
commit and push; hosted M2a.1 acceptance remains pending that commit's CI run.

## Retrieved hosted failure evidence

[M2a run 38564568013](https://github.com/chambies2015/ReproSeed/actions/runs/38564568013)
passed Ubuntu/Python 3.12 and Ubuntu/Python 3.14. Its
[Windows job 115853833714](https://github.com/chambies2015/ReproSeed/actions/runs/38564568013/job/115853833714)
failed with `419 passed, 4 skipped, 1 warning, 2 errors in 324.44s`.
The build and installed-wheel steps were skipped. The GitHub job logs and
job/step metadata were retrieved directly. Relevant signatures are retained
in `.validation/m2a1-hosted-signatures.txt`, excluding environment contents,
credentials and raw arbitrary oracle output.

The runner was Windows Server 2025 Datacenter `10.0.26100`, image
`windows-2025-vs2026`, image version `20260925.250.1`, with CPython 3.12.10.
Both errors occurred before their link-security assertions, in the shared
one-row real mutating-oracle fixture with a one-second timeout and six-invocation
budget:

- `tests/test_bundle_snapshot.py::test_bundle_symlink_rejected`:
  `VerificationError: final artifact failed three fresh confirmations; bundle not published`.
- `tests/test_bundle_snapshot.py::test_bundle_junction_rejected`:
  `VerificationError: baseline failed three fresh confirmations: UNRESOLVED:deadline exceeded (process or open output pipes), TARGET_FAILURE:expected exit and exact failure marker, TARGET_FAILURE:expected exit and exact failure marker`.

The junction failure is confirmed as a first-baseline deadline classification.
The symlink error establishes three successful baseline confirmations, completed
compaction and three returned final results with at least one non-target result.
The retrieved logs contain no final-result values. Their actual classifications,
positions, launch/execution timing and cleanup timing cannot be recovered from
this historical evidence. A deadline is a hypothesis for that separate failure,
not a demonstrated cause. No evidence identifies a TEXT-key or production oracle
implementation defect. The warning was separately attributed to
`test_second_interrupt_in_real_oracle_cleanup_aborts_and_preserves_launch`:
`oracle cleanup incomplete: taskkill exit (code 128)`; it was not attributed to
either bundle fixture setup.

## Timing boundary and repair

Review covered `build_verified_fixture`, `InvocationCounter`, `run_oracle`,
`_execute`, Windows Job assignment/tree termination and the shared cleanup
allowance. The execution clock begins before process launch. Launch, Windows
Job setup, pipe-reader startup and waiting for process completion/pipe EOF
consume the configured deadline. Initial private staging is outside that
execution clock. Cleanup waits, reader shutdown and directory-deletion retries
share a separate real monotonic 1.5-second allowance. Synchronous OS calls
cannot be preempted by that allowance. Result duration includes execution/tree
cleanup; test-only wall measurements additionally include staging/removal.

The fixture's deadline is now five seconds. It still creates a genuine bundle
through `create_bundle`, executes the real mutating oracle, requires exact exit
42 and whole-line `TARGET` on stdout, and spends exactly six launches on three
baseline plus three final confirmations. This finite allowance is appropriate
for path-security setup; evidence below records its observed headroom and limits.
Production deadlines and cleanup contracts are unchanged.

`tests/test_bundle_snapshot.py` now checks six distinct disposable directories,
real database/asset mutations, pristine exported database/assets, all six target
outcomes, complete accounting and unchanged input hashes. Setup failure adds
synthetic phase/position, classification, fixed reason, exit/byte counts, result
duration, invocation wall duration and launch-accounting metadata. It exposes
no raw oracle output, argv or environment and introduces no production feature.
Symlink/junction rejection covers both validation and replay, forbids payload
reads/execution through the link and checks the supplied bundle's hashes.

Six readiness-driven regression cases expire a live real subprocess separately
at each baseline/final confirmation position. One latched test-only clock offset
crosses the configured deadline; cleanup continues at the real clock rate.
Every deadline stays `UNRESOLVED`; the other confirmations remain observed
targets. No majority vote, fewer confirmations, retries, mocks replacing oracle
execution, xfails or new skips were added. Failed publication preserves input
hashes and pre-existing output. A separate unexpected-exit case checks actionable
diagnostics without disclosing printed arbitrary output. Existing real
0.15-second slow-oracle and Windows process-tree tests remain unchanged.

## Validation results

### Finite timing investigation

The exact hosted Python version was exercised locally: Windows 10 build 19045,
CPython 3.12.10 (MSC 1943 AMD64), SQLite 3.47.1, pytest 9.1.1. This is not the
hosted Windows Server image. `tests/bundle_timing_probe.py` is a rerunnable
standard-library evidence recipe, separate from pytest collection and hosted CI.
It records every real invocation's classification, execution flag, phase,
launch/observed-completion timing, wall duration, Job assignment, cleanup timing,
warnings and hash preservation without capturing raw oracle output/environment.

Five bundles were generated for each combination below. Each row represents
30/30 real TARGET_FAILURE results and five verified bundles. No natural timeout
or final-verification failure was reproduced with the old one-second timeout.

| Fixture deadline / scheduling | Maximum baseline wall seconds | Maximum final wall seconds | Targets / attempts |
| --- | ---: | ---: | ---: |
| 1 second / ordinary | 0.172 | 0.188 | 30 / 30 |
| 1 second / concurrent load | 0.578 | 0.578 | 30 / 30 |
| 5 seconds / ordinary | 0.407 | 0.312 | 30 / 30 |
| 5 seconds / concurrent load | 0.781 | 0.656 | 30 / 30 |

Each concurrent batch started two workers making 40 finite Python import/SQLite
subprocess launches apiece plus a concurrent `tests/test_oracle.py` run. All
three background processes remained active at each bundle's completion; all
background exits were zero. Maximum new-five-second loaded launch time was
0.266 seconds and observed completion was 0.766 seconds. These timings include
scheduling effects and observations, not isolated CPU execution measurements.
The largest invocation wall time was 0.781 seconds including staging/removal.
Five seconds supplies over six times that observed wall duration and four
additional seconds beyond the deadline implicated by the hosted baseline. It
is a finite testing allowance, not a guarantee about every hosted schedule.

All 120 natural invocations acquired an owned Job, removed their disposable
directory and emitted no cleanup warnings. Maximum measured directory removal
was 0.031 seconds. Tree cleanup measured zero elapsed clock ticks: local
`GetTickCount64()` monotonic resolution is 0.015625 seconds, so this does not
prove instantaneous cleanup. The existing real cleanup deadlines are preserved.
All source/assets and bundles validated after creation retained their hashes.

Separate readiness-driven one-second probes recorded the actual implicated
outcomes: baseline `UNRESOLVED(deadline), TARGET_FAILURE, TARGET_FAILURE`, and
final `TARGET_FAILURE, TARGET_FAILURE, TARGET_FAILURE, UNRESOLVED(deadline),
TARGET_FAILURE, TARGET_FAILURE`. Both rejected publication and preserved inputs.
These are deterministic synthetic boundary observations. They do not identify
the lost hosted final classifications. Injected result durations include the
clock offset; real wall fields use the untouched clock. Forced-case completion
observations can include termination during cleanup rather than natural exit.

Evidence is retained in
`.validation/m2a1-timing-{old1s,new5s}-{ordinary,load}/evidence.json`,
`.validation/m2a1-timing-injected-{baseline,final}/evidence.json`,
`.validation/m2a1-timing-summary.json` and
`.validation/m2a1-timing-environment.json`.

### Finite Windows security stability batch

All 20 predetermined runs completed with exit zero, no failure/setup error and
no timeout. Each run generated both genuine bundles successfully (12 actual
target confirmations), passed real junction rejection and skipped symlink
creation for existing WinError 1314 privilege unavailability. This establishes
stable symlink-test setup locally; symlink rejection itself runs on Linux and
remains pending a suitably privileged Windows runner. No skip was introduced.
Every result, including skips, is retained in
`.validation/m2a1-security-stability/evidence.json` and `security-01.xml` through
`security-20.xml`. The finite batch supplements the full suites below.

| Run | Junction | Symlink | Exit | Wall seconds |
| ---: | --- | --- | ---: | ---: |
| 1 | pass | privilege skip | 0 | 7.485 |
| 2 | pass | privilege skip | 0 | 5.719 |
| 3 | pass | privilege skip | 0 | 5.953 |
| 4 | pass | privilege skip | 0 | 4.312 |
| 5 | pass | privilege skip | 0 | 4.844 |
| 6 | pass | privilege skip | 0 | 4.922 |
| 7 | pass | privilege skip | 0 | 5.250 |
| 8 | pass | privilege skip | 0 | 5.782 |
| 9 | pass | privilege skip | 0 | 5.859 |
| 10 | pass | privilege skip | 0 | 4.563 |
| 11 | pass | privilege skip | 0 | 5.171 |
| 12 | pass | privilege skip | 0 | 4.719 |
| 13 | pass | privilege skip | 0 | 5.360 |
| 14 | pass | privilege skip | 0 | 5.593 |
| 15 | pass | privilege skip | 0 | 5.250 |
| 16 | pass | privilege skip | 0 | 4.828 |
| 17 | pass | privilege skip | 0 | 5.047 |
| 18 | pass | privilege skip | 0 | 4.328 |
| 19 | pass | privilege skip | 0 | 5.078 |
| 20 | pass | privilege skip | 0 | 4.750 |

### Full validation and applications

Fresh clean copies selected explicit tracked/current regular source files,
recorded SHA256 maps and started without `.validation`, `.venv` or `dist`.
Both pipelines explicitly prepared `.validation` before running the full suite,
as CI does. Windows used the exact local CPython 3.12.10 interpreter above,
uv 0.13.0 and cached locked dependencies offline. Linux used a new disposable
cached Docker container with container-native source files: Linux
`6.18.33.2-microsoft-standard-WSL2` x86_64/glibc 2.36, CPython 3.12.11 (GCC
12.2.0), SQLite 3.40.1 and uv 0.8.22. Both used Ruff 0.17.0, pytest 9.1.1 and
mypy 1.20.2. No existing container or unrelated data was modified.

| Check | Windows | Actual Linux |
| --- | --- | --- |
| Locked sync, Ruff lint/format, mypy, mypy Linux target | pass | pass |
| Full clean-copy pytest | 426 passed, 6 skipped, 2 warnings; 477.98 seconds | 407 passed, 25 skipped; 114.37 seconds |
| Wheel and source-distribution builds/contents | pass | pass |
| Exact existing CI installed-wheel recipe outside checkout | pass | pass |
| Genuine historical version-1 read/replay compatibility | pass | pass |

Windows skips were the two existing unavailable-symlink-privilege cases plus
four POSIX-only cases. Linux skips were 25 Windows-specific branches; Linux
symlink rejection and POSIX real-signal tests actually ran. Windows interruption
injection coverage is separate from real console Ctrl+C, which was not run.
The two Windows warnings were `oracle cleanup incomplete: taskkill exit (code 1)`
in `test_second_interrupt_in_real_oracle_cleanup_aborts_and_preserves_launch`
and `test_returned_process_handle_establishes_known_launch_before_evidence_assignment`.
Both tests passed; these warnings remain recorded, unsuppressed, and are not
attributed to the repaired fixture. The focused fixture run separately passed
35 tests with one privilege skip in 34.33 seconds, and the final two-link check
passed the junction case with one privilege skip in 3.63 seconds. The broader
Windows deadline/classification/cleanup/accounting run passed 117 tests with
two skips and two warnings in 60.08 seconds.

The explicit timing helper received a small supplemental observer correction
after the initial clean-copy snapshots: fallback `taskkill` launches are
distinguished from the oracle launch. All original natural observations used
assigned Jobs, so those measurements are unaffected. The final helper was copied
into Windows's clean source before build, checked on both platforms and included
in rebuilt distributions; collected tests and runtime bytes did not change.
The initial Linux supplemental `ruff check .` after pytest traversed generated
synthetic `.validation/pytest` snippets without Git metadata and exited one.
That harness failure remains in the logs. Fresh explicit source checks and exact
helper checks passed. Attempts to execute supplemental commands after an owned
container had auto-removed also timed out at the harness layer; they did not run
or retry the test suite. Completion-document edits made after testing are
documentation only and included in the final handoff build.

Raw Windows command records/logs are in `.validation/m2a1-windows-evidence/`;
Linux main records/logs and immutable copy hashes are in
`.validation/m2a1-linux-evidence/results/`, supplemental checks/distributions in
`supplemental/`, targeted helper checks in `helper-targeted/`, and their index in
`.validation/m2a1-linux-evidence/summary.json`. The root deadline/classification
run is in `.validation/m2a1-deadline-oracle.log`. The additional Windows focused
TEXT-key/diagnostics/application run passed 96 tests with one POSIX-only skip
in 170.06 seconds; its log is `.validation/m2a1-text-diagnostics.log`.

Fresh genuine pre-M1b bundles were generated from archived reviewed source
commit `ba40d64db748d974c36666294a1cc4500c79c25f`, rather than fabricated reports.
Windows's explicit source recipe and Linux's current installed wheel each
validated default/explicit JSON and text inspection, then relocated and replayed
the historical bundle with original paths unavailable. Both recorded 11 -> 3
rows, 18 old reduction executions and three new target replay confirmations,
with source/bundle hashes unchanged. Windows evidence is
`.validation/m2a1-pre-m1b-v1-fresh/compatibility-result.json` and
`.validation/m2a1-compatibility.log`; Linux archive/hash/result evidence is indexed
in its summary and retained historical files.

Both external installed-wheel batches passed all five full examples with
`PYTHONPATH`/`PYTHONHOME` removed. `python -I` proved imports beneath each fresh
installation's `site-packages`. The exact CI recipe separately exercised the
threshold and compact TEXT workflows without an editable source installation.
Default/explicit JSON and text inspection, static/executable diagnosis, genuine
application-level reduction and relocated replay all passed. The five full
applications also ran in both full acceptance suites.

| Application | Observed rows | Executions / budget | Cache hits / acceptances | Windows reduction seconds | Linux reduction seconds | Source / final bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Duplicate export | 2,430 -> 5 | 54 / 400 | 11 / 13 | 16.250 | 4.330 | 147,456 / 20,480 |
| Threshold | 11 -> 3 | 18 / 80 | 5 / 3 | 3.734 | 1.166 | 12,288 / 12,288 |
| Reservations | 4,248 -> 9 | 131 / 400 | 24 / 21 | 29.313 | 14.721 | 196,608 / 36,864 |
| Approvals | 1,626 -> 6 | 107 / 400 | 25 / 22 | 24.843 | 12.015 | 94,208 / 32,768 |
| TEXT entitlements | 970 -> 10 | 180 / 240 | 31 / 30 | 37.594 | 22.084 | 282,624 / 57,344 |

Every application had zero invalid/unresolved trials, no unknown launches,
three baseline/final/relocated-replay target confirmations, exact retained
declared values and preserved schema/metadata, integrity and FK validity. These
are repeated observations, not engine constants or global-minimality claims.
Each platform's `installed-measurements/measurements.json` retains actual
per-table counts, all source/assets/bundle hash maps and every confirmation.
Original example paths were made unavailable before replay; all original
source/assets and relocated bundle bytes remained unchanged. TEXT hidden-rowid
equality was not substituted for declared-key preservation.

Representative actual Windows commands (the recorder retains full argv/exits;
the bootstrap project environment is Python 3.12.15/SQLite 3.53.1, while the
Windows oracle/test/wheel execution above uses explicit Python 3.12.10):

```powershell
.tools/bin/uv.exe sync --locked --python 3.12 --offline
.venv/Scripts/python.exe .validation/m2a1_validate.py prepare --root . --destination .validation/m2a1-clean-windows --evidence .validation/m2a1-windows-evidence
$env:M2A1_PYTHON='M:/Server/ReproSeed/ReproSeed/.validation/m1b1-2-python/cpython-3.12.10-windows-x86_64-none/python.exe'
.venv/Scripts/python.exe .validation/m2a1_validate.py pipeline --root .validation/m2a1-clean-windows --evidence .validation/m2a1-windows-evidence --uv .tools/bin/uv.exe
.validation/m2a1-win31210/Scripts/python.exe -m pytest tests/test_bundle_snapshot.py tests/test_oracle.py tests/test_oracle_cleanup.py tests/test_invocation_accounting.py --basetemp=.validation/pytest-m2a1-deadline-oracle
.validation/m2a1-win31210/Scripts/python.exe -m pytest tests/test_text_keys.py tests/test_diagnose_cli.py tests/test_diagnostics.py tests/test_realistic_acceptance.py --basetemp=.validation/pytest-m2a1-text-diagnostics
.validation/m2a1-win31210/Scripts/python.exe tests/compatibility_smoke.py --directory .validation/m2a1-pre-m1b-v1-fresh
.validation/m2a1-win31210/Scripts/python.exe tests/bundle_timing_probe.py --directory .validation/m2a1-timing-old1s-ordinary --timeout 1.0 --repetitions 5
.validation/m2a1-win31210/Scripts/python.exe tests/bundle_timing_probe.py --directory .validation/m2a1-timing-old1s-load --timeout 1.0 --repetitions 5 --load
.validation/m2a1-win31210/Scripts/python.exe tests/bundle_timing_probe.py --directory .validation/m2a1-timing-new5s-ordinary --timeout 5.0 --repetitions 5
.validation/m2a1-win31210/Scripts/python.exe tests/bundle_timing_probe.py --directory .validation/m2a1-timing-new5s-load --timeout 5.0 --repetitions 5 --load
.validation/m2a1-win31210/Scripts/python.exe tests/bundle_timing_probe.py --directory .validation/m2a1-timing-injected-baseline --timeout 1.0 --repetitions 1 --inject baseline
.validation/m2a1-win31210/Scripts/python.exe tests/bundle_timing_probe.py --directory .validation/m2a1-timing-injected-final --timeout 1.0 --repetitions 1 --inject final
.validation/m2a1-win31210/Scripts/python.exe tests/bundle_timing_probe.py --directory .validation/m2a1-security-stability --security-runs 20
```

Both clean pipelines ran locked sync, `uv run --locked ruff check .`,
`uv run --locked ruff format --check .`, `uv run --locked mypy`,
`uv run --locked mypy --platform linux`, the explicit validation-parent command,
`uv run --locked pytest --basetemp=.validation/pytest`, and
`uv build --no-sources`, before installing/exercising the wheel externally.
Linux additionally generated genuine historical source/bundle evidence and
validated it using the installed wheel. No hosted workflow was changed.

## Final review and limitations

Final handoff wheel/sdist builds passed with `uv build --no-sources --offline`.
The source/distribution byte comparison passed; its result is retained in
`.validation/m2a1-final-dist/content-check.json`. The wheel contains 17 files
and has no runtime dependencies; the sdist contains 77 files. Explicit
inventories exclude generated databases, sidecars, bundles, caches, environments,
logs and validation evidence. Every runtime module byte matches both exercised
wheels; every selected source file matches its final sdist member, including
the final tests, probe, roadmap and this report. No artifact is published.

Final handoff commands:

```powershell
.tools/bin/uv.exe build --no-sources --offline --out-dir .validation/m2a1-final-dist
.venv/Scripts/python.exe .validation/m2a1_package_check.py
git -c core.autocrlf=false diff --check
git status --short
git diff --cached --name-only
```

Production modules, cleanup/deadline tests, invocation/accounting tests,
historical completion reports and CI configuration remain unchanged. The
final diff contains only `tests/test_bundle_snapshot.py`,
`tests/bundle_timing_probe.py`, `docs/roadmap.md` and this report. No retries,
xfails, hidden output assertions, removed confirmations or new skips were added.
Schema/key/FK semantics, deterministic reduction/cache/checkpoints, read-only
WAL snapshots, compact-fixture confirmation and version-1 validation remain
covered by the unchanged regression suites and actual integration runs.

Local five-second stability and controlled boundary tests do not establish
success on the hosted Windows Server 2025 scheduler. Historical final-result
classifications remain unavailable. Native Ubuntu, local Python 3.14 and
Windows console Ctrl+C were not run for this patch. Linux's actual Docker/WSL2
execution is distinct from a new hosted Ubuntu result. Windows symlink rejection
still needs privileges; the real fixture and junction rejection ran locally,
and actual Linux symlink rejection passed. Hosted M2a.1 acceptance is pending
Dan's new commit and GitHub CI run. M2b is not implemented.

Final branch/HEAD remain `main` /
`eb8108dece9055dc9180826f42de03363cb64cbe`; the index is empty. All four files
remain unstaged/uncommitted for Dan. Final `git status --short`:

```text
 M docs/roadmap.md
 M tests/test_bundle_snapshot.py
?? docs/m2a1-completion.md
?? tests/bundle_timing_probe.py
```
