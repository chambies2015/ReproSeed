# M1b.2 completion evidence

Starting checkout: `main`, commit `5e72f68fc5133d9f343537ba7472ca0a0b186289`, clean
`git status --short`. The accepted M1b.1.2 hosted run is
[38471526956](https://github.com/chambies2015/ReproSeed/actions/runs/38471526956).
The GitHub connector returned success for Ubuntu/Python 3.12, Ubuntu/Python 3.14
and Windows/Python 3.12. Historical completion reports retain their original local
observations. No reset, staging, commit, push, PR, tag, release or package publication
is authorized or performed for this milestone.

Implemented: optional baseline diagnosis using the existing validation/execution
foundation; reservation-overbooking and cyclic-approval applications with independent
semantic oracles; diagnostic integration/accounting tests; realistic acceptance and
a reusable four-example measurement recipe; installed-wheel diagnostic smoke; updated
developer workflow and M2 boundary documentation. No schema expansion, reducer ordering
change, fixture-specific engine logic or runtime dependency was added.

Hosted M1b.2 CI remains pending Dan's review, commit and push.

## Implementation and diagnostic contract

`diagnostics.py` calls unchanged strict configuration parsing, safe explicit-file checks,
read-only WAL-aware snapshot acquisition, `DatabaseModel.from_database`, `InvocationCounter`
and `run_oracle`. There is no alternate schema acceptance, process orchestration, failure
classification or reducer. Assets are frozen under a separate private `assets/` directory
before confirmations, including in static mode. Each executable attempt gets fresh database
and asset copies through the existing runner. Diagnosis never creates a replay bundle.

The default readable text distinguishes checks performed now from an untested baseline.
`--allow-exec` requests exactly three attempts unless interruption or a hard nonlaunch
prevents completion. Completed PASS/UNRESOLVED outcomes remain visible and do not supply
target confirmations. All three must match the exact configured nonzero exit and whole
UTF-8 marker line on its configured stream. Diagnosis does not predict later reduction
success. Static exit 0 establishes structural readiness only; executable exit 0 establishes
three target outcomes now; failed baseline is 1; invalid input is 2; interruption is 130.

The separate `diagnostic_version = 1` document leaves report.json/replay.toml version 1
unchanged. It includes current checks, sorted table counts, limits and a minimal oracle
contract; ordered actual outcomes/reasons/codes, exit, executed flag, duration and bounded
output counts; known/unknown launch charges and interruption completeness. No missing
result, majority result or uncertain execution is invented. Full field meanings are in
[diagnostics.md](diagnostics.md).

Invalid input gets a machine-readable curated cause with no raw exception path/value.
Table names, original argv and marker values cannot inject error labels. Text escapes
terminal/control/direction characters in schema metadata. JSON/text omit absolute paths,
raw process output, row values and inherited environment values. The contract summarizes
marker length, argument count, stream and expected exit without echoing secrets in argv or
markers. A completed launch with a lost result remains charged; unknown interrupted launch
is conservatively charged; a further interruption during accounting recovery is incomplete
and aborts. A further cleanup interruption after committed accounting retains that complete
accounting. No search salvage or report publication exists in diagnosis.

## Captured diagnostic examples

Actual static diagnosis of the generated threshold fixture, default text, exit 0:

```text
ReproSeed diagnosis (diagnostic format 1)
SQLite snapshot: acquired
Schema: supported
Integrity validation: passed
Foreign-key validation: passed
Explicit assets: validated and privately copied
User tables: 2
Rows: 11
Tables (user rows):
  "crates": 3
  "parcels": 8
Structurally suitable for reduction: yes
Oracle contract: exit 43 and an exact whole UTF-8 marker line on stdout
A matching exit code alone does not establish the target failure.
Limits: 5s per attempt; 65536 combined output bytes; 80 configured reduction invocations
Oracle: not executed
Actual invocations: 0; unknown interrupted launches: 0
Baseline reproduction: not established
Next step: use --allow-exec to verify the configured failure.
Readiness checks do not guarantee a subsequent reduction will succeed.
```

The same static check in JSON, exit 0 (complete captured document):

```json
{
  "diagnostic_version": 1,
  "mode": "static",
  "snapshot_acquired": true,
  "schema_supported": true,
  "integrity_valid": true,
  "foreign_keys_valid": true,
  "assets_validated": true,
  "structurally_suitable": true,
  "table_counts": {
    "crates": 3,
    "parcels": 8
  },
  "total_rows": 11,
  "oracle_contract": {
    "expected_exit": 43,
    "stream": "stdout",
    "marker_matching": "exact_whole_utf8_line",
    "marker_utf8_bytes": 26,
    "argv_argument_count": 3
  },
  "limits": {
    "timeout_seconds": 5.0,
    "output_limit_bytes": 65536,
    "max_invocations": 80
  },
  "required_baseline_confirmations": 3,
  "oracle_executed": false,
  "baseline_confirmed": false,
  "baseline_results": [],
  "actual_invocations": 0,
  "unknown_interrupted_launches": 0,
  "budget_charged_invocations": 0,
  "interrupted_invocations": [],
  "unreported_invocations": 0,
  "accounting_complete": true,
  "interrupted": false,
  "error": null
}
```

Executable diagnosis of that fixture returned exit 0 with three executed
TARGET_FAILURE/target_contract_matched results, exit 43 and 28 combined output
bytes each. Actual duration records are retained in diagnose-baseline.json.

## Realistic application defects

Reservation schema: organizations → warehouses → stock_lots; organizations/nullable
preferred warehouses → orders; orders/warehouses → reservations; reservations/lots →
reservation_lines. The six tables have sparse integer keys, multiple FK parents, nullable
references, eight synthetic tenants, forty warehouses, two hundred lots and decoy/cancelled
reservations. Each submitted reservation's total demand is checked against original lot
capacity, but previously accepted demand is never deducted. On the last capacity-10 lot,
requests of 7 and 8 both fit individually and are both accepted, overbooking stock. The
independent oracle invokes the processor and totals its actual accepted quantities. It
rejects individual over-allocation, needless rejection, invalid decision shapes and crashes
as different failures. The final subset retains demands 6 and 7, still overbooking the
unchanged capacity 10 with nine relationally valid rows.

Approval schema: quoted `team departments` → employees; departments/nullable requester →
`approval workflows`; workflows/approvers/self-dependent steps → `approval steps`;
workflows/nullable reviewer → `approval rules`; unrelated empty `approval activity`.
There are negative/sparse keys, nullable references, 120 workflows with decoy chains,
and a genuine two-node self-FK cycle committed using a deferred constraint. The depth-first
validator puts steps into its completed set before traversing dependencies, so a back edge
misses the visiting-set cycle check. The independent oracle uses path positions to detect
cycle lengths, then checks actual workflow acceptance. Only a false acceptance with eligible
two-node cycles matches; a three-node defect or other discrepancy exits without the marker.
The six-row final fixture retains one department, approver, workflow, rule and both cycle
steps; requester/reviewer references survive unchanged and activity stays empty.

Counterfactual tests repair each application in a disposable copy and prove that the
unchanged oracle returns PASS. Correct source data also returns PASS. Tests preserve the
planted target while adding a different defect and require a non-target result, so an
unrelated failure cannot hide behind a legitimate marker. No row or special flag directly
instructs an oracle to report TARGET_FAILURE. Both generators are deterministic and refuse
existing database outputs. All data, applications and coordination files are synthetic.

## Four-example measurements

Source-run evidence is `.validation/m1b2-source-measurements/measurements.json`, generated by:

```powershell
.venv\Scripts\python.exe tests/milestone_smoke.py --directory .validation/m1b2-source-measurements
```

Actual reduction totals include baseline, uncached search executions and final verification;
separate original-oracle, executable-diagnose and replay runs are outside those budgets.
Cache hits reuse evidence rather than add executions. These measured counts are observations,
not hardcoded execution expectations in the acceptance tests.

| Example | Original → final rows | Executions / budget | Cache hits | Accepted | Wall seconds | Source → final bytes |
| --- | --- | --- | --- | --- | --- | --- |
| Duplicate export | 2430 → 5 | 54 / 400 | 11 | 13 | 18.828 | 147456 → 20480 |
| Aggregate threshold | 11 → 3 | 18 / 80 | 5 | 3 | 7.829 | 12288 → 12288 |
| Reservation overbooking | 4248 → 9 | 131 / 400 | 24 | 21 | 65.657 | 196608 → 36864 |
| Approval cycle | 1626 → 6 | 107 / 400 | 25 | 22 | 30.000 | 94208 → 32768 |

| Example / table | Original | Final |
| --- | --- | --- |
| Duplicate / entries | 2400 | 2 |
| Duplicate / owners | 6 | 1 |
| Duplicate / projects | 24 | 2 |
| Threshold / crates | 3 | 1 |
| Threshold / parcels | 8 | 2 |
| Reservation / orders | 1000 | 2 |
| Reservation / organizations | 8 | 1 |
| Reservation / reservation_lines | 2000 | 2 |
| Reservation / reservations | 1000 | 2 |
| Reservation / stock_lots | 200 | 1 |
| Reservation / warehouses | 40 | 1 |
| Approval / approval activity | 0 | 0 |
| Approval / approval rules | 120 | 1 |
| Approval / approval steps | 1320 | 2 |
| Approval / approval workflows | 120 | 1 |
| Approval / employees | 60 | 1 |
| Approval / team departments | 6 | 1 |

All four source runs had zero invalid candidates, unresolved attempts and unknown launches.
All terminated with `single_row_closures_exhausted`. All four independently reproduced on
the original; passed static diagnosis and three executable diagnostic confirmations;
preserved three baseline and three final TARGET_FAILURE confirmations in their reports;
passed default JSON, explicit JSON and text inspection; and passed three new relocated
replay TARGET_FAILURE confirmations outside the checkout after original example/bundle
paths were made unavailable. Reservation and approval meet their ≤12/≤10 row goals; the
existing duplicate/threshold goals remain satisfied. Exhausted closures do not prove global
minimality. The generic reducer, closures, caches and ordering were not changed.

These Windows source measurements used Python 3.12.15 and SQLite 3.53.1, on shared hardware
while other validation processes ran. They are observed elapsed times, not controlled
benchmarks. Summed fresh oracle result durations were 16.153s, 5.736s, 55.955s and 26.299s
respectively. The wall-time remainder estimates were 2.675s, 2.093s, 9.702s and 3.701s.
They include unprofiled CLI/startup, asset staging, temporary-directory removal, candidate
materialization, cache/search and publication overhead; they do not isolate those costs.
The measured execution intervals dominate these runs, but this does not establish whether
interpreter launch, application SQL or cleanup is the largest individual cost. Neither new
fixture exceeded its budget. There is no demonstrated engine defect requiring optimization.

## Source and bundle immutability

The measurement harness hashes every original example file before execution and again
after diagnosis/reduction/replay. It hashes every declared bundle file before inspection,
after all three inspection formats and after relocated replay. Equality assertions passed
for all four. Original example and first-bundle paths are renamed before replay; the replay
cwd and copied bundle are outside the checkout. It compares every retained row tuple with
the original set, declared schema SQL and relevant table/index/FK/database metadata, and
requires actual SQLite integrity/FK checks. Separate application execution verifies the
retained relational cause for each new fixture.

Captured fixture SHA256 values from those runs:

| Example | Source | Final |
| --- | --- | --- |
| Duplicate | `a1f219e3495878679289eef047a6eba8e91d483797eaa5977c5b5f4f785cda69` | `8b9b80e6a6a2e3ae387dee0f3b93da7a5d9dba34b0fada3b8c06c571e1958e4a` |
| Threshold | `c523f93be27a6ef7768c9c6a443b911dca37d6caabe4bd920f5f8084dd4e8cf2` | `471fdf89e2deae73c964d37de7175e05629dee27145a8373414af1e01e7d58b1` |
| Reservation | `a457404c3dad432083656cd935c3a32ae10fa19ca42af351058aea9e785d4985` | `fe9af650fa04a887961e8a5210b59c87bbf2f505f35983551a29a22d46b8067e` |
| Approval | `74b3cf3c4251ba779037bf0b756b1cb9b90f76070b3eee103736bc2e1ef43d54` | `037e3b906423538b570be87a7dfd02e93e4e96cfac5f631528b41fb8e3dffd4d` |

Full source/bundle SHA256 maps and confirmation records remain in each example's
`measurement.json`. Generated fixtures and bundles stay ignored, outside distributed
package contents. Hash equality proves unchanged bytes relative to these captured hashes;
it does not authenticate authorship or historical execution.

## Regressions and review findings

New real SQLite/subprocess tests cover static sentinel nonlaunch without acknowledgement;
explicit three-attempt execution; cwd independence; JSON/text agreement; positive stdout
and stderr contracts; zero/PASS; wrong expected exit; missing marker; wrong stream;
unrelated crash; marker with unrelated/zero exit; failed launch; timeout; output overflow;
deterministically inconsistent TARGET_FAILURE/PASS/UNRESOLVED observations; unsupported PK;
invalid FKs; missing/traversal assets; malformed TOML; pristine database/asset mutations;
terminal-control table names; committed WAL counts without source/WAL writes; lost-result
launch accounting; owned-directory removal; and a separate actual POSIX SIGINT lifecycle.
Focused tests additionally exercise known nonlaunch/launch/unknown interrupted launch,
first/second accounting interruption, cleanup-abort accounting, frozen asset acquisition,
curated privacy-safe causes and snapshot/asset namespace separation.

Review found and fixed a new diagnostic cause-mapping defect: substring searches could
interpret validator keywords in an untrusted table name or path as a different failed
check. Mapping now uses stage-aware fixed message boundaries; real named-table and
snapshot-path regressions prevent false integrity/FK claims or misleading advice. Review
also distinguished an accounting-recovery abort from a cleanup abort after completed
counter publication, with regressions for all three launch states.

One early focused batch had an output-limit test fail under contention: its 0.15s deadline
could expire before the synthetic writer started, correctly producing UNRESOLVED/timeout
instead of UNRESOLVED/output-limit. Only that test's deadline was changed to a finite 3s;
the real timeout test retains 0.15s. The corrected selected run passed 12 tests. This was
a test setup defect, not a manufactured target or softened oracle contract. No skips,
assertions, generic engine protections or hosted retry policy were removed.

The first Linux four-example installed-wheel recipe failed before any example: its
interpreter path normalization resolved the virtual-environment symlink to global Python,
which could not import the installed wheel. The recipe now preserves lexical absolute
interpreter/console paths. Its exercise logic and runtime engine are unchanged. The full
Linux suite and CI threshold wheel smoke had already passed; the corrected installed
recipe is verified separately. An early local validation recorder also had a relative
path error when launching its extracted CI wheel block; the final recorder uses absolute
paths. These failed attempts remain in local evidence rather than being hidden as passes.

## Local validation

Clean copies contain only explicitly enumerated tracked/current untracked project files,
with SHA256 manifests and `.validation`, `.venv` and `dist` absent initially. They run the
CI setup that creates `.validation` before pytest. Locked sync, Ruff lint/format, both mypy
targets, the full suite, wheel/sdist builds and the extracted CI installed-wheel block all
passed on the final Windows and Linux copies. All runtime module bytes match the reviewed
working source. The only subsequent test-recipe change preserves interpreter symlinks;
its installed-mode path was verified on both platforms rather than repeating unchanged
large acceptance tests. Final documentation is included in the final local distribution.

| Platform | Actual runtime | Full pytest result | Pytest elapsed |
| --- | --- | --- | --- |
| Windows 10, build 19045 | CPython 3.12.15, SQLite 3.53.1 | 366 passed, 6 skipped, 2 warnings | 363.32s |
| Linux kernel 6.18.33.2 Microsoft WSL2, glibc 2.36 | CPython 3.12.11, SQLite 3.40.1 | 347 passed, 25 skipped | 78.13s |

Both used pytest 9.1.1, Ruff 0.17.0 and mypy 1.20.2. Windows uv was 0.13.0
(`4ecd0eff2`, 2026-10-09); the cached Linux image used uv 0.8.22. Both consumed the same
unchanged uv.lock. Linux used `ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim`, copied
the project to a tool-owned `/tmp` directory, and ran tests/build/replay with `--network none`.
The first offline sync stopped because a locked development package was absent. A separate
locked dependency-cache fill downloaded public development packages, after which offline
sync and tests passed. No tests, applications or oracles depended on a network service.

Windows skips were two missing symlink privileges (WinError 1314), existing real POSIX
SIGINT reduction, POSIX executable-mode semantics, new real POSIX diagnostic SIGINT and
POSIX signal return codes. Its two warnings are existing intentional launch/accounting
interruptions before Job assignment: taskkill fallback returned code 1. Both warning cases
passed their launch accounting assertions. Linux skips are Windows junction/Job/API/fallback
and readonly-attribute cases. Linux executed symlink/executable-mode and both actual SIGINT
lifecycle cases. Deterministically injected KeyboardInterrupt accounting/publication cases
ran on both; Windows injection is not Windows console-signal coverage. No failure was hidden
with new skips or retry-until-green behavior.

Focused checks included the first CLI batch (22 passed, one POSIX skip), corrected selected
CLI batch (12 passed), final diagnostic unit batch (22 passed), realistic oracle negatives
(8 passed), and realistic acceptance (2 passed in 148.97s). The early combined focused batch
had 41 passes, one skip and the output-deadline setup failure documented above; its corrected
cases and both final full suites passed. The final combined diagnostic-focused run passed
46 tests with one POSIX skip in 25.73s, recorded in
`.validation/m1b2-final-diagnostic-focused.log`.

Final clean-copy commands (Windows prep/recording uses the project-local uv executable):

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

Exact dispatched argv, exits and elapsed times are captured in
`.validation/m1b2-evidence/windows-final/commands.json` and
`.validation/m1b2-evidence/linux-final/results/commands.json`; corresponding logs record
versions, pytest skips/warnings, build contents and extracted CI wheel execution. Source
copy manifests preserve what each full suite exercised. Current runtime/test hashes and
the corrected harness are compared with both final copies in the final package check.
Earlier failed environmental/harness attempts are retained separately in these records.

## Builds, installed wheels and compatibility

The unchanged three-entry hosted matrix is preserved. Its threshold installed-wheel block
now checks default-text static diagnosis plus static/executable JSON diagnosis before
reduce/default-JSON/explicit-JSON/text inspection/relocated replay. New diagnostic subprocess
calls have finite 60-second outer bounds. The extracted CI block passed outside the source
context on both platforms; Windows took 19.781s, corrected Linux 6.593s.

The explicit installed-wheel recipe runs all four examples using a separate wheel
installation and its console entry point, with PYTHONPATH/PYTHONHOME removed. Import-origin
assertions show packages under the outside installation's site-packages, rather than this
checkout. Both recipes confirm original independent oracles, static/executable diagnoses,
reductions, all inspection forms, final confirmations, three relocated replays and exact
source/bundle hash equality. Entire recipe elapsed: Windows 75.625s; Linux 32.441s.

| Example | Installed Windows reduction seconds | Installed Linux reduction seconds | Rows / reduction executions |
| --- | --- | --- | --- |
| Duplicate export | 10.031 | 4.231 | 2430 → 5 / 54 |
| Threshold | 3.250 | 1.410 | 11 → 3 / 18 |
| Reservation | 24.406 | 10.827 | 4248 → 9 / 131 |
| Approval | 18.891 | 8.123 | 1626 → 6 / 107 |

Counts, budget, cache hits, accepted reductions, zero invalid/unresolved trials and
`single_row_closures_exhausted` termination agree with the source table above on both
platforms. Measurements are observations on this hardware, not promises for other runtime,
filesystem or scheduling conditions. Full installed evidence lives in each final platform's
`installed-measurements/measurements.json`, including fresh oracle durations, sizes,
per-table counts, source/bundle SHA256 maps and exact final/replay results.

Wheel and sdist content inspection checks all runtime module bytes, no runtime Requires-Dist,
and no generated databases, sidecars, bundles, bytecode, validation directories, Git state,
environments or caches. Only explicit package source/examples/tests/docs are distributed.
The wheel includes diagnostics.py; the sdist includes both new application examples,
diagnostic documentation/tests and completion evidence. Builds are local artifacts only.

The genuine compatibility recipe archives reviewed pre-M1b commit
`ba40d64db748d974c36666294a1cc4500c79c25f`, uses its source and synthetic threshold example
to produce a real version-1 bundle, then invokes the current reader. Windows's complete
recipe and Linux's current-reader validation both passed: 11 → 3 rows, 18 old reduction
executions, unchanged default/explicit report JSON, text inspection, three new TARGET_FAILURE
replay confirmations and unchanged source/bundle bytes. No fixture migration or report
reinterpretation is involved.

```powershell
.tools\bin\uv.exe run --locked --offline python tests/compatibility_smoke.py --directory .validation/m1b2-pre-m1b-v1-fresh
```

The original attempt to mount separately generated Windows legacy files into Linux was
blocked by their private Windows ACLs, including sandboxed and elevated reads. A new genuine
generation exported only ten explicitly enumerated synthetic files during the same owning
tool invocation. Linux checked each exported SHA256 before extraction and ran the unchanged
recipe's `--phase validate` against those bytes. Original private artifacts were preserved;
no ACL was weakened, bundle rewritten or hash recomputed to accept altered contents. Results:
`.validation/m1b2-pre-m1b-v1-fresh/compatibility-result.json` and
`.validation/m1b2-evidence/linux-final/compatibility-result.json`.

## Remaining limits and final handoff

M2 is not implemented. The restricted SQLite subset, external executable/dependency
requirements, exact exit/stream/whole-line marker contract, lack of anonymization and lack
of a global-minimality proof remain. Structural readiness does not establish reproduction;
baseline readiness does not guarantee search/final verification. Inspection/hash consistency
does not authenticate authorship or historical execution. Temporary directories and
process-tree cleanup are not an OS sandbox against authorized arbitrary code, hostile
filesystem races, detached descendants or externally stalled synchronous OS calls.

Actual Linux SIGINT coverage is distinct from injected Windows cancellation. Windows
console Ctrl+C, Windows Server 2025, local Python 3.14 runtime and hosted M1b.2 CI were not
run. The preserved hosted matrix still requires Dan's commit/push before new CI evidence
exists. No billable inference, production database, real user data or package publishing
was used. Generated validation artifacts remain ignored and previous artifacts are preserved.

Final review checked scoped changes, independent semantic oracles, value/schema preservation,
bounded execution/cleanup, fresh mutation-free confirmations, version-1 compatibility,
privacy-safe errors, terminal escaping, honest uncertainty and no fixture-specific reducer
logic. config.py, sqlite_adapter.py, oracle.py, reducer.py, workflow.py, artifacts.py,
report.py and inspection.py remain unchanged. Historical completion reports remain unchanged.

`main` remains at `5e72f68fc5133d9f343537ba7472ca0a0b186289`; no staged changes.
Final local distributions are under `.validation/m1b2-ready-dist/`; the corresponding
`content-check.json` records byte comparisons with both exercised wheels and current
runtime/test source, explicit sdist contents and exclusion checks. Handoff build recipe:

```powershell
.tools\bin\uv.exe build --no-sources --offline --out-dir .validation/m1b2-ready-dist
.venv\Scripts\python.exe .validation/m1b2_package_check.py
git diff --check
```

Final `git status --short` (all work unstaged/uncommitted):

```text
 M .github/workflows/ci.yml
 M AGENTS.md
 M CONTRIBUTING.md
 M README.md
 M SECURITY.md
 M docs/architecture.md
 M docs/roadmap.md
 M src/reproseed/cli.py
?? docs/diagnostics.md
?? docs/m1b2-completion.md
?? examples/approval_cycle/
?? examples/reservation_overbook/
?? src/reproseed/diagnostics.py
?? tests/milestone_smoke.py
?? tests/test_diagnose_cli.py
?? tests/test_diagnostics.py
?? tests/test_realistic_acceptance.py
?? tests/test_realistic_oracles.py
```
