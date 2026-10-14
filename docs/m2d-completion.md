# M2d completion evidence

Date: 2026-10-14. Verdict: **CONDITIONAL GO** for a limited developer alpha,
subject to the conditions in [alpha readiness](alpha-readiness.md). This milestone
implements onboarding and external-consumer validation; it does not publish an
alpha, change version 0.1.0, or constitute an independent outside-user study.

## Starting state and ownership

The checkout started on `main`, HEAD
`dd3db90eee65ed10e158cdcc9ef16b8a677e9852`, with empty Git status. It matched the
reviewed M2c commit supplied in the request. M2c's accepted
[hosted run 38599450878](https://github.com/chambies2015/ReproSeed/actions/runs/38599450878)
passed Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12. That is prior
M2c evidence, not hosted validation of this work. Historical completion reports
and existing ignored evidence were preserved.

All fixtures, sentinels, permission changes, environments and containers were
synthetic and tool-owned. No production database, account, credential, billable
service or intentionally malicious unrelated-resource payload was used. No stage,
commit, push, PR, tag, release or package upload was performed. Changes remain
unstaged and uncommitted for Dan; hosted M2d CI awaits his review/commit/push.

## Implemented behavior and regressions

The schema/model, reducer, oracle, workflow accounting and report validator remain
unchanged. Python 3.12+, empty runtime dependencies, existing exit meanings,
report/replay/configuration version 1 and diagnostic JSON version 1 are preserved.

- Missing/unreadable configuration is distinguished from malformed UTF-8/TOML.
  Reduction's input/schema/filesystem stderr uses the existing curated diagnostic
  cause mapping rather than echoing private paths, unknown field values or table
  identifiers. Snapshot deadlines retain `snapshot_timeout`.
- Human text adds recovery guidance; residual bundle/verification text escapes
  terminal controls. Successful command JSON and inspection defaults retain their
  existing shapes. Recorded failed baseline/final/replay classifications are not
  turned into success or majority-voted.
- A demonstrated Windows denied-output hang is fixed. `tempfile` could retry
  ACL-denied mkdirs because Windows `os.access` reported the parent writable.
  Bundle staging now starts with one exclusive UUID-named private-parent mkdir;
  denial/collision fails before snapshot/oracle execution. Existing portable
  temporary-directory cleanup operates inside the successfully owned parent.
  Cleanup does not replace an active failure/interruption with an outer rmdir
  error. Existing paths and final output ownership rules remain intact.
- Eleven new CLI regressions cover curated errors, snapshot classification, real
  controlled Windows ACL denial, collision preservation and cleanup interruption
  exit 130. Five tutorial tests synchronize complete guide files with retained
  assets and exercise true target/non-target data. Six consumer-helper regressions
  cover isolation, failure handling and owned temporary cleanup.

Independent review reproduced an interruption-masking defect in the first staging
wrapper draft; it was repaired before final validation. Real Windows ACL rejection
returns exit 2 within the regression's eight-second subprocess deadline, with no
oracle sentinel, output bundle or source-hash change. A controlled cleanup
interruption preserves exit 130, and a preexisting staging collision is preserved.
These are targeted fixes, not a new schema capability or reduction heuristic.

## Simulated first-user journey

`tests/external_consumer_smoke.py` accepts a concrete wheel. It creates a fresh
external standard-library venv and installs using that interpreter's pip:

```text
python -m venv <new external environment>
<fresh python> -m pip install --no-index --no-deps <concrete wheel>
```

The consumer removes PYTHONPATH/PYTHONHOME and virtual-environment leakage, disables
pip configuration/index reliance, and proves the imported package is in the new
installation's actual site-packages, outside the checkout. Installed console entry
points run version/help, fresh threshold generation, static and executable
diagnosis, reduction, default/explicit JSON and text inspection, relocation and
three new replay confirmations from an unrelated cwd after original paths are
unavailable. No editable/source import substitutes for a failed wheel. Finite
deadlines apply to subprocesses; consumer temporary state is removed on completion.

The example is the existing aggregate-threshold domain, not a seventh application.
Its SQL oracle reports the target only when a crate's parcel masses exceed 100;
a nonfailure control with mass zero exits 0 without a marker. The specific fixture
has 11 rows and reduces to one crate/two parcels (3 rows), with 18/80 invocations.
Three fresh baseline, compact-final and relocated-replay target results are checked.
Source/configuration/assets, supplied/relocated bundles and the wheel retain their
byte hashes; retained declared schema/values, integrity and FKs are checked.

Fresh venv/pip journeys passed on Windows and Debian-container Linux, including
spaces, Unicode café and special-character project paths. The Linux audit also ran
as UID/GID 1000 rather than root, proving real mode-bit input/output rejection.
Both installed error audits passed 40 CLI records. Windows exercised junctions and
ACL denial; its symlink privilege probe was unavailable. Linux exercised symlinks
and both permission denials; Windows junctions do not apply there.

Literal PowerShell and all three POSIX guide blocks were executed against the
reviewed/final-runtime wheels. The harness supplied concrete wheel/interpreter
locations, the text-editor file-creation step and additional failure/hash checks.
The guide's complete
generator/oracle/TOML content is required to equal the retained threshold assets.
The guide instructs checking PowerShell native exit codes; its harness additionally
enabled native-command error stopping. POSIX uses `set -eu`. Both journeys replayed
after renaming the original project. Independent developers have not attempted
these instructions yet.

First-use friction observed:

- The original README entered through checkout/uv. It now leads with the problem,
  concrete 11 -> 3 example, local-wheel guide and immediate limits.
- This host's uv-managed Python 3.12 is not registered with `py -3.12`; the literal
  attempt returned 103. The guide explains selecting an explicit supported Python
  executable. Fresh venv/pip does not require uv on the consumer side.
- Exact marker stream/line and nonzero exit, three confirmations, budgets reserving
  final checks and selecting a new output directory need explicit explanation.
  The guide supplies full files and a troubleshooting table.
- Wheel acquisition is still a trusted local-build workflow. External dependencies,
  a meaningful application oracle and pre-sharing data/code review remain user work.
  A developer-written successful simulation does not establish external usability.

Evidence is ignored under `.validation/m2d-installed-windows-evidence/`,
`.validation/m2d-linux-wheel-evidence/`, `.validation/m2d-nonroot-linux-evidence/`,
`.validation/m2d-literal-linux-evidence/`, `.validation/m2d-guide-windows/` and
`.validation/m2d-root-evidence/`. It includes actual argv/cwd/deadlines/exits,
runtime/import origins, classifications, hashes and cleanup observations.

## Error and recovery audit

The installed helper `tests/error_smoke.py` records exact exits, observed oracle
starts, checked input/bundle bytes, bounded output/privacy assertions and recovery
guidance. Permission input bytes are compared after restoring controlled ACL/mode
changes. No real secret values are used.

| Cases | Observed classification and safety |
| --- | --- |
| Missing config, malformed TOML, missing source/asset, invalid budget | Exit 2, curated input cause, no oracle launch or bundle. |
| Unsupported schema, broken FKs | Exit 2 structural rejection, source preserved, no launch. |
| Wrong exit, wrong stream, marker mismatch, unrelated crash | Executed baseline exit 1 with all three non-target observations retained; no successful reproduction claim. |
| Timeout and output limit | Three executed UNRESOLVED observations, exit 1; raw synthetic process output omitted from CLI results. |
| Launch failure | Exit 1 with nonlaunch/UNRESOLVED evidence and zero known executions. |
| Inconsistent baseline | TARGET_FAILURE, PASS and UNRESOLVED are preserved; exit 1 with no majority vote. |
| Budget 6 | Search ends by budget, preserves confirmed rows, runs three final confirmations; verified exit 0 with exactly six charged executions. |
| Existing output | Exit 2 before oracle; preexisting sentinel/data preserved. |
| Tampering, traversal and finalized WAL/SHM/journal sidecars | Exit 2 before replay; supplied bundle/sidecars preserved without repair/deletion. |
| Missing external replay dependency | Three new UNRESOLVED outcomes, exit 1; original recorded success is not a new reproduction. |
| Replay differs from historical target | Three PASS outcomes, exit 1, original bundle unchanged. |
| Failed final verification | Exit 1 after actual observations; no verified bundle published. |
| Unreadable input / unwritable output | Exit 2, zero launches, preserved input bytes, no output overwrite; actual Windows ACL and non-root POSIX probes. |
| Static diagnosis, inspect, missing execution acknowledgement | Static/inspect never execute; reduce/replay without --allow-exec exit 2 with zero launches. |
| Spaces/Unicode/special characters, explicit assets | Successful installed workflow; argv is an array rather than shell interpolation. Directories/traversal/links are rejected where applicable. |

Search interruption and final/accounting interruption remain distinct. The full
suite exercises committed search salvage, fresh compact-final/replay checks,
unknown-launch accounting and further-interruption aborts. Injected interruptions
on Windows do not establish real Windows console Ctrl+C behavior. Real POSIX SIGINT
workflow/diagnosis and process-group tests ran on Linux separately.

## Seven scenarios and historical compatibility

Full explicit installed-wheel measurements ran in fresh external directories on
Windows and Linux, rather than adding another full six-example CI reduction.
Every scenario checked semantic application decisions where applicable, retained
declared values/schema/metadata, integrity/FKs, source/bundle hashes, three baseline
and compact-final confirmations, and three new unrelated-cwd relocated replays.
There were zero unresolved/invalid trials and zero unknown launches in these runs.

| Scenario | Original -> final rows | Invocations / budget | Accepted | Cache hits | Windows reduction seconds | Linux reduction seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Duplicate export | 2,430 -> 5 | 54 / 400 | 13 | 11 | 16.938 | 3.904 |
| Aggregate threshold | 11 -> 3 | 18 / 80 | 3 | 5 | 5.063 | 0.903 |
| Reservations | 4,248 -> 9 | 131 / 400 | 21 | 24 | 36.687 | 9.410 |
| Approval cycle | 1,626 -> 6 | 107 / 400 | 22 | 25 | 36.718 | 7.060 |
| TEXT entitlements | 970 -> 10 | 180 / 240 | 30 | 31 | 63.078 | 10.885 |
| Ordinary composite billing | 1,308 -> 8 | 126 / 260 | 22 | 23 | 37.922 | 8.379 |
| WITHOUT ROWID billing | 1,308 -> 8 | 126 / 260 | 22 | 23 | 42.297 | 7.918 |

These are observations, not hardcoded generic reduction requirements or performance
claims; runs overlapped other validation. Both full billing fixtures start above
1,200 rows and retain eight, below the acceptance ceiling of 16. Per-table counts,
bytes, confirmations and hashes are retained in measurement JSON. Windows full
measurements used the final reviewed runtime. Linux explicit measurements preceded
the Windows staging/cleanup repair; final Linux full-suite and installed workflows
then exercised the repaired runtime. The key/model/search/oracle implementations
were unchanged. Large explicit measurements were not repeated just to write this
readiness document; full-suite reruns followed demonstrated code/test corrections.

The explicit compatibility recipe archived genuine reviewed source at
`ba40d64db748d974c36666294a1cc4500c79c25f` (pre-M1b INTEGER),
`d60c79c07ae12666af9572ced69edc3b9523ce17` (M2a TEXT) and
`d70edac43c22efe3df643b821af1c51ec756a945` (M2b composite). Fresh genuine bundles
were generated by those implementations, never hand-constructed to satisfy the
current reader. Current source and final reviewed installed-wheel default/explicit
JSON/text inspection and relocated three-confirmation replay passed. Original
reports, source and original/relocated bundle hashes were unchanged. Prior fixtures
were respectively 11 -> 3, 10 -> 10 and 8 -> 8. Evidence:
`.validation/m2d-*-v1-fresh/` and `.validation/m2d-final-installed-history/`.

## Platforms, commands and final gates

Clean copies were prepared from tracked/nonignored source with per-file hashes,
without initial `.venv`, `.validation` or `dist`. Windows used Windows 10 build
19045, AMD64, CPython 3.12.15 (MSC 1944), SQLite 3.53.1 and uv 0.13.0.
Linux used the cached network-disabled image
`ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim`, image identity
`b27bdf6aad179578bdd6cefb1316dbd9287cf36feaac5c167287dbe27b6a6fff`:
Debian Bookworm, Linux 6.18.33.2-microsoft-standard-WSL2, x86_64/glibc 2.36,
CPython 3.12.11 (GCC 12.2.0), SQLite 3.40.1 and uv 0.8.22. Both used Ruff 0.17.0,
pytest 9.1.1, mypy 1.20.2 and build 1.6.1. This is local Debian-container evidence,
not Ubuntu hosted verification.

Actual command families, with platform-specific resolved executables/new paths,
are recorded in ignored `commands.json` and individual logs:

```text
uv sync --locked --python 3.12
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy --platform linux
uv run --locked pytest tests/test_getting_started.py tests/test_external_consumer_smoke.py tests/test_cli_errors.py --basetemp=<new first-user temp>
uv run --locked pytest tests/test_diagnose_cli.py tests/test_diagnostics.py tests/test_bundle_snapshot.py tests/test_config_artifacts.py --basetemp=<new privacy temp>
uv run --locked pytest --basetemp=.validation/pytest
uv build --no-sources
uv run --locked python tests/distribution_smoke.py --wheel <built wheel> --sdist <built sdist>
python tests/external_consumer_smoke.py --wheel <built wheel> --existing-applications --audit-errors --evidence <new file>
<installed python> tests/milestone_smoke.py --directory <new external directory> --python <installed python> --cli <installed console>
<installed python> tests/milestone_smoke.py --directory <new external directory> --python <installed python> --cli <installed console> --examples composite_billing --without-rowid-billing-fixture
uv run --locked python tests/compatibility_smoke.py --directory <new history directory> --history <pre-m1b|m2a-text|m2b-composite>
```

| Gate | Windows | Linux |
| --- | --- | --- |
| Locked sync, Ruff lint/format, both mypy targets | PASS | PASS |
| Focused first-user/tutorial/CLI tests | 22 passed | 21 passed, 1 Windows ACL skip |
| Focused diagnostics/privacy/bundle/config | 125 passed, 4 platform/privilege skips | 128 passed, 1 Windows junction skip |
| Final full suite | **631 passed, 6 skipped, 2 warnings in 721.22 s** | **611 passed, 26 skipped in 143.14 s**, no warnings |
| Wheel/sdist build and content/metadata checks | PASS | PASS |
| Fresh standard venv/pip, installed lifecycle and small key/layout cases | PASS | PASS |
| Installed error audit and literal tutorial | PASS | PASS, including non-root audit/all three literal POSIX blocks |

Windows's six skips were two existing symlink privilege failures (WinError 1314),
real POSIX SIGINT workflow/diagnosis, executable-mode and signal-return-code tests.
Linux's 26 skips are Windows-specific junction, Job Object/taskkill/fallback/API,
readonly attribute and the new Windows ACL test. No failure was skipped, retried
in hosted configuration or changed to continue-on-error. Windows emitted two
warnings in injected invocation-accounting/cleanup boundaries:
`oracle cleanup incomplete: taskkill exit (code 1)`. Accounting assertions passed;
these warnings preserve observed cleanup uncertainty, not proof every interrupted
cleanup succeeded. Actual platform signals and deterministic injection are distinct.

Final clean-source/evidence roots are `.validation/m2d-final-windows*` and
`.validation/m2d-final-linux*`; final separate Linux wheel checks are in
`.validation/m2d-linux-wheel-evidence/`. New consumer evidence always used a new
file. Local runtimes do not establish hosted Ubuntu/Python 3.12/3.14, Linux/Python
3.14, macOS or real Windows console Ctrl+C. Those checks were not run here.

## Packaging, security and documentation

The version, package/console names and Python requirement remain unchanged.
`license-files = ["LICENSE"]` and repository/homepage/issues/documentation URLs
were added. Wheel metadata establishes MIT, included license, `>=3.12`, Markdown
README and no Requires-Dist runtime entries. `distribution_smoke.py` checks exact
intended runtime Python files against source bytes, the sole console entry point,
metadata/README/license and intended sdist docs/examples/tests. Both archives exclude
databases, sidecars, logs, caches, environments, secrets/evidence directories and
editable-install requirements. Local Twine 7.0.0 `check --strict` passed for wheel
and sdist; readme_renderer 46.0 with its Markdown engine rendered the wheel's actual
README description successfully. These extra checks used an ephemeral development
tool environment, with no project/lock/runtime dependency changes. Public
package-index display/publication and publisher authentication were not tested.
Evidence: `.validation/m2d-readme-render/`.

Metadata/venv choices follow primary references:
[writing pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/),
[packaging projects](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
and [Python 3.12 venv](https://docs.python.org/3.12/library/venv.html).
Final packaging includes this report and compares runtime bytes with the tested
wheels; aggregate evidence remains ignored, not part of either distribution.

The focused sharing review found no demonstrated remaining P0 security defect.
The fixed privacy leak is P2; the denied-output hang was a fixed P1 reliability
defect. Controlled tests reconfirm static/inspect/acknowledgement boundaries,
private verified replay payloads, explicit regular-file acquisition, traversal/link
and sidecar rejection, pristine copies and immutability. A synthetic asset edit
plus recomputed manifest hash can pass inspection, showing that integrity is relative
to a manifest, not authorship or new reproduction. Replay can then report PASS or
UNRESOLVED. No new claim of a security sandbox or comprehensive hostile-code audit
is made. SECURITY now enumerates bundle contents and pre-sharing steps, inherited
permissions/dependencies, credential-bearing literals and non-secure temporary
erasure. Known Windows startup/Job and POSIX detached-child cleanup limits remain.

README, getting-started, contributing, architecture/diagnostics, SECURITY, roadmap
and AGENTS guidance were updated. The new readiness document evaluates gates A-N
with evidence, severities, supported scope and remaining conditions. CI retains the
three existing jobs, read-only permissions, pinned actions and 15-minute bound;
the duplicated inline threshold lifecycle is replaced by the repeatable consumer
helper, preserving the small TEXT/composite/WITHOUT ROWID cases. Distribution
inspection is added. Full six/seventh reductions are not multiplied in CI.

## Intermediate failures and final review

Meaningful failed attempts remain in ignored evidence/tool logs and were not
relabeled as successes:

- uv absent from PATH; restricted default cache/WSL access and uncached backend
  network failures. The existing explicit uv/Python were located, declared build
  and locked dev requirements fetched with authorized access, then consumer/Linux
  validation ran offline. No system setting changed.
- A new test's `tests.test_config_artifacts` import worked under `python -m pytest`
  but failed clean pytest-console collection on both platforms. Its direct helper
  import and Ruff ordering were corrected; final console suites passed.
- A helper-only SQLite context left connections open on Windows; fixture unlink
  failed WinError 32. Explicit closing fixed bookkeeping. A broad input ACL denial
  also denied ACL inspection/removal; it was narrowed to read-data denial, with
  owned cleanup and failure evidence preserved.
- The error audit demonstrated the real denied-output >30-second stall described
  above; final finite CLI and installed-wheel permission checks passed after repair.
  Independent review then found cleanup-interruption masking; the guard/regression
  repaired that draft before final gates.
- An ignored recorder used a relative cache path in a clean-copy cwd, causing
  offline missing-tool/backend failures. Resolving that cache fixed the harness.
  A later Linux consumer rerun correctly rejected an already existing evidence
  filename; it was rerun with new evidence without overwriting the first result.
- Literal PowerShell first encountered unregistered `py -3.12` (exit 103); using
  the documented explicit interpreter passed. A wrapper-only output-decoding
  failure was corrected with byte capture/UTF-8; actual child commands had succeeded.
- Initial distribution inspection used an inappropriate bytes email parser for
  Unicode README content, then detected a changed script after a build. Its text
  parser was corrected and current sources rebuilt; final content checks passed.
  A rendering helper initially expected a bare h1, while the renderer adds an id
  and anchor; its HTML check was corrected and rendering passed without a README
  syntax defect.

Final diff review checked execution acknowledgement, strict JSON/exit compatibility,
private details, source/bundle protection, cleanup/ownership, finite subprocess
bounds, package exclusions, installed origins, historical compatibility and scope.
No new runtime dependency, schema family, adapter, algorithm, UI, LLM integration,
redaction or publication was introduced. Historical completion files remain intact.

The final working tree contains 13 modified tracked files and 9 new documentation/
test-support files, all unstaged; the index has no changes. Generated databases,
archives, environments, bundles, logs and retained evidence remain ignored.
Dan's review, successful hosted M2d matrix, independent first-user feedback and
an explicit distribution decision are the remaining **CONDITIONAL GO** gates.
