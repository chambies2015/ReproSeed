# M2d.1 completion evidence

Date: 2026-10-14. This repair separates effective Windows permissions from ACL-edit
success and reinforces the production staging boundary. Public-alpha readiness
remains **CONDITIONAL GO**, pending all three hosted M2d.1 jobs, independent
developer feedback and Dan's distribution decision. No package is published.

## Starting state and ownership

The checkout started clean on `main` at reviewed HEAD
`6aaf7d77d51bb5e6277f16caa3a85e5e3e9574b6`. All new fixtures, ACL targets and
validation directories are synthetic and tool-owned. Existing work and historical
completion reports are preserved. Changes stay unstaged and uncommitted for Dan.

## Exact hosted failure

M2d [run 38613024891](https://github.com/chambies2015/ReproSeed/actions/runs/38613024891)
passed Ubuntu/Python 3.12 and 3.14. Windows
[job 116020933305](https://github.com/chambies2015/ReproSeed/actions/runs/38613024891/job/116020933305)
failed on Windows Server 2025 Datacenter build 26100, runner 2.337.0,
`windows-2025-vs2026` image `20261007.264.1`, CPython 3.12.10.

Sanitized excerpt of the retrieved job log:

```text
collected 637 items
test_windows_denied_output_returns_promptly_without_launch_or_overwrite
assert result.returncode == 2
AssertionError: assert 0 == 2
original_counts: {"things": 1}
final_counts: {"things": 0}
oracle_invocations: 8
termination_reason: empty_candidate_confirmed
verified: true
1 failed, 632 passed, 4 skipped, 1 warning in 152.36s
```

The warning belongs to the existing
`test_second_interrupt_in_real_oracle_cleanup_aborts_and_preserves_launch` in
`test_invocation_accounting.py`: `taskkill exit (code 128)`. The Windows build,
package-content and installed-wheel steps did not run. This is a failed hosted
gate, not evidence that every product test failed.

The original test checked successful `icacls /deny current-identity:(WD,AD)`
execution but never attempted the required directory creation before invoking
ReproSeed. The successful reduction shows that this process could create its
bundle; it does not establish why Windows allowed creation or prove a permission
bypass. The earlier M2d local denied-output evidence remains historical evidence
on its recorded runtime, not validation of this hosted permission precondition.

## Implementation and permission observations

No product-code change was justified by the hosted failure. The existing M2d
`_build_directory` already attempts one exclusive private-parent
`mkdir(mode=0o700)` before copying assets, acquiring the snapshot or launching an
oracle. PermissionError reaches the curated CLI exit-2 path immediately. The
repair changes test preconditions, test-owned ACL acquisition/restoration and
installed-consumer audit evidence. SQLite/key/FK models, reducer ordering/cache,
oracle classification/accounting/cancellation, confirmation requirements,
version-1 formats, package version 0.1.0 and runtime dependencies are unchanged.

The deterministic regression invokes public CLI `main` with a genuine synthetic
SQLite/configuration/oracle fixture. Its Path.mkdir wrapper denies only the exact
UUID-selected staging-parent path, counts the operation and fails immediately if
retried; every unrelated mkdir delegates to the real implementation. It checks
one attempted creation, exit 2 with curated permission guidance, zero Popen/oracle
launches, no output or staging leak, unchanged source/configuration/assets/existing
file hashes and successful unrelated-directory creation. This exercises production
staging rather than replacing create_bundle. Existing collision/no-overwrite,
cleanup interruption exit 130, input-error and successful confirmation coverage
remain separate.

The real Windows integration now runs an eight-second subprocess capability probe
using the CLI interpreter, execution context and exact `Path.mkdir(mode=0o700)`
operation on a fresh UUID-named child. PermissionError with errno 13 / winerror 5
establishes denial; successful creation is followed by removal and a narrowly
explained capability skip; other numeric filesystem errors or process/cleanup
failures fail the test. Effective denial then permits the real subprocess CLI
assertions: bounded exit 2, curated stderr, no launch/bundle/staging leak and
unchanged inputs and preexisting files. Allowed creation never runs an impossible
denial assertion or becomes denial-handling evidence. Python's Windows mode-0o700
security-descriptor handling makes the exact mode relevant; it does not explain
the original runner's behavior.
([CPython 3.12.10 mkdir](https://github.com/python/cpython/blob/v3.12.10/Modules/posixmodule.c#L5005),
[Python os.mkdir](https://docs.python.org/3.12/library/os.html#os.mkdir))

`tests/windows_permissions.py` captures a private saved DACL and a bounded
GetFileSecurityW descriptor, preflights restoration and compares the entire saved
parent DACL before adding a deny. ACL commands and descriptor operations have
five-second subprocess bounds; API descriptor captures are limited to 64 KiB.
ACL readback is supplementary evidence. Each context restores and compares the original parent
DACL in finally, including skip/assertion/timeout paths, then removes its private
snapshots. A failed restoration cannot turn a would-be skip into accepted
coverage; active failure/interruption evidence is retained. No owner/group/SACL,
token, privilege, account or unrelated ACL is changed. A successful `/remove:d`
alone would be insufficient: `/deny` can remove matching explicit grants, while
`/remove:d` can remove preexisting denies.
([Microsoft icacls](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls),
[security-information flags](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-information))

Restoration distinguishes observed descriptor metadata. SetNamedSecurityInfoW
with the original protection flag preserves tested auto-inherited parent DACLs;
on the tested non-auto-inherited layout it changed inheritance metadata. The
helper uses DACL-only SetFileSecurityW for that case and requires exact preflight
and final parent readback. Microsoft marks SetFileSecurityW obsolete and documents
that it does not propagate directory security to children. This narrowly tested
fallback is not a general Windows ACL-management recommendation.
([SetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow),
[descriptor control](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control),
[SetFileSecurityW](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setfilesecurityw))

The installed error audit retains both Windows input and output categories using
one explicitly owned synthetic fixture directory. It applies inherited RD denial,
probes actual config-byte reads, restores, then separately applies WD/AD denial
and probes child creation before reduction. Actual PermissionError/errno 13 with
winerror absent or 5 is accepted for byte-open denial; the observed byte-open error
had no winerror. Unexpected errors fail, and allowed operations are recorded as
unavailable real coverage. The inherited-input context alone requests restoration
propagation through the owned parent before exact parent-metadata restoration;
no file ACL is explicitly targeted. SetNamedSecurityInfoW supports propagation
to existing children. API exit 0 is recorded separately from post-restoration
readability and byte-hash checks; exact child DACL metadata is not claimed.
([automatic ACE propagation](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces))

Independent local studies used Windows 10 build 19045 / Python 3.12.15. The original
WD/AD edit succeeded and both default-mode and mode-0o700 child probes were denied
with errno 13 / winerror 5, in 0.234 s and 0.219 s. The local token summary found
no Administrators/high/system group, enabled SeChangeNotifyPrivilege and no
backup/restore privilege in the selected rows. These are local observations only.
The failed hosted runner supplied no resulting ACL, token/storage evidence or
same-operation probe, so its reason for allowing creation remains unknown. No
elevation or privilege-bypass explanation is inferred.

Preliminary harness obstructions were retained, rejected and recovered rather
than folded into the final stability batch:

| Investigation | Observation and recovery |
| --- | --- |
| Initial, instrumented and completed ACL studies | Bounded icacls /restore failed; instrumented/completed return code was 1300. Original captured parent DACLs matched exactly after owned deny removal. This code does not identify the underlying privilege operation or explain the hosted failure. |
| Early API/protection and inherited-only delta prototypes | Exact preflight/final parent readback failed, including the pytest layout. Rejected synthetic parents were recreated from normal inheritance with their fixed synthetic bytes preserved. |
| Modern-API metadata variants | Full-flags and DACL-only variants changed a non-auto-inherited parent to auto-inherited metadata; protected construction also changed metadata. Captured originals were recovered exactly with DACL-only SetFileSecurityW. Separate prepared auto-inherited/explicit-grant studies matched their captured originals. |
| Two early audit probes before helper stabilization | One observed an unexpected read result with unretained numeric codes followed by a parent-DACL mismatch; another context did not yield. No CLI/oracle ran, no capability skip was recorded, and the exact owned scratch trees were removed. Post-failure source-hash verification was not established. |
| Stabilized byte-open classifier | PermissionError/errno 13 with absent winerror was incorrectly classified unexpected by a winerror-5-only rule. Parent restoration succeeded; no CLI ran. The byte-open rule was corrected using the actual exception and numeric errno. |
| Parent-only inherited-input restoration | Real diagnosis returned exit 2 with zero launches, but the subsequent hash read failed: inherited child RD denial remained despite exact parent restoration. The optional parent-targeted propagation repair restored child reads before exact parent restoration. |

Four focused audit/probe tests passed locally, including real denial of all three
owned child reads, restored readability, identical bytes and snapshot cleanup.
The completed native source-CLI audit then observed input denial (errno 13,
winerror absent), diagnosis exit 2 in 0.594 s, and output denial (errno 13 /
winerror 5), reduction exit 2 in 0.500 s. Both had zero launches, unchanged
source/configuration/asset hashes, exact restored parent DACLs, no capability
skips and no published bundle or staging/probe leakage. This source-CLI audit is
distinct from installed-wheel validation below. The later evidence-only field
rename records `children_inheritance_restore_exit=0` for API success and
`child_readability_restored=true` only after actual read/hash checks.

Privacy-safe investigation evidence is ignored under `.validation/m2d1-hosted/`
and `.validation/m2d1-agent-permission-*.json`. It omits account identities, full
token contents, raw ACL/descriptor payloads and private paths. Preliminary studies,
deterministic injection, real local ACL integration and the finite stability batch
establish different properties. None establishes the original hosted permission
context or universal ACL enforcement/restoration across Windows filesystems.
Hosted acceptance requires Dan's subsequent reviewed commit and push.

## Finite Windows stability batch

The fixed batch ran exactly 20 iterations, each in a new owned pytest directory,
with a 60-second outer deadline. Each iteration ran the deterministic staging
denial and real Windows ACL integration once. No retry-until-green rule, sleep,
xfail or unconditional Windows skip was used. The total batch took 116.718 s.

Every row below had pytest exit 0; an actual mode-0o700 probe denial with errno
13 / winerror 5; real ACL integration executed (no capability skip); real CLI
exit 2; deterministic CLI exit 2 with exactly one staging mkdir attempt; zero
oracle starts in both tests; unchanged source/configuration/assets/existing-file
hashes; no output bundle or leaked staging/probe directory; and exact original
parent-DACL restoration. No unexpected failure or cleanup obstruction occurred
in this batch. Preliminary rejected harness experiments above are separate.

Times are measured seconds, rounded to three decimals; 0.000 reflects clock
resolution/rounding rather than a zero-cost claim. The retained JSON and 20
JUnit/log pairs contain each probe's numeric codes, probe duration, CLI outcomes,
launch counts, byte/ownership checks and restoration flags:
`.validation/m2d1-stability/results.json` and `iteration-01` through `iteration-20`.

| Iteration | Actual probe | Real CLI s | Injected CLI s | Entire iteration s |
| --- | --- | --- | --- | --- |
| 1 | denied | 0.609 | 0.016 | 7.360 |
| 2 | denied | 0.797 | 0.016 | 6.578 |
| 3 | denied | 0.719 | 0.016 | 6.687 |
| 4 | denied | 0.453 | 0.000 | 5.406 |
| 5 | denied | 0.672 | 0.016 | 5.969 |
| 6 | denied | 1.453 | 0.015 | 8.344 |
| 7 | denied | 0.672 | 0.016 | 6.656 |
| 8 | denied | 0.578 | 0.015 | 5.422 |
| 9 | denied | 0.547 | 0.000 | 5.156 |
| 10 | denied | 0.469 | 0.000 | 6.375 |
| 11 | denied | 1.078 | 0.016 | 8.343 |
| 12 | denied | 0.485 | 0.000 | 5.031 |
| 13 | denied | 0.469 | 0.016 | 4.547 |
| 14 | denied | 0.766 | 0.015 | 5.328 |
| 15 | denied | 0.656 | 0.016 | 6.234 |
| 16 | denied | 0.484 | 0.000 | 4.719 |
| 17 | denied | 0.469 | 0.016 | 4.625 |
| 18 | denied | 0.406 | 0.000 | 4.297 |
| 19 | denied | 0.531 | 0.015 | 4.891 |
| 20 | denied | 0.469 | 0.016 | 4.750 |

## Platforms and validation procedure

Windows execution used Windows 10 build 19045, AMD64, CPython 3.12.15
(MSC 1944), SQLite 3.53.1 and uv 0.13.0. Linux execution used the cached,
network-disabled Debian Bookworm container
`ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim`, image
`sha256:b27bdf6aad179578bdd6cefb1316dbd9287cf36feaac5c167287dbe27b6a6fff`,
WSL2 kernel 6.18.33.2-microsoft-standard-WSL2, x86_64/glibc 2.36,
CPython 3.12.11 (GCC 12.2.0), SQLite 3.40.1 and uv 0.8.22. Both used
pytest 9.1.1, Ruff 0.17.0, mypy 1.20.2 and build 1.6.1. These are local
Windows/Debian results, not new native Ubuntu, Windows Server or Python 3.14
validation. Real Windows console Ctrl+C was not exercised.

Clean copies contained 97 regular tracked/nonignored source files with per-file
hashes and no initial `.venv`, `.validation`, `dist` or `.git`. CI's explicit
`.validation` parent was created before pytest. Cached locked dependencies were
used offline; Linux mounted inputs/cache read-only and copied them privately.
Permission-helper changes made during investigation were separately recorded
and refreshed before final-source checks. Source/runtime bytes stayed unchanged
during executed validation; final evidence-only documentation is packaged separately.

Actual command families (resolved executable paths, exact exits and durations
are in the ignored `commands.json` and logs):

```text
uv sync --locked --python 3.12
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy --platform linux
uv run --locked pytest tests/test_cli_errors.py tests/test_error_smoke_permissions.py --basetemp=<fresh>
uv run --locked pytest --basetemp=<fresh>
uv build --no-sources
uv run --locked python tests/distribution_smoke.py --wheel <wheel> --sdist <sdist>
python tests/external_consumer_smoke.py --wheel <wheel> --existing-applications --audit-errors --evidence <fresh>
<installed python> tests/milestone_smoke.py --directory <new external directory> --python <installed python> --cli <installed console>
<installed python> tests/milestone_smoke.py --directory <new external directory> --python <installed python> --cli <installed console> --examples composite_billing --without-rowid-billing-fixture
uv run --locked python tests/compatibility_smoke.py --directory <fresh> --history <pre-m1b|m2a-text|m2b-composite>
```

The final Linux clean-copy suite passed **616 tests, 30 skipped, no warnings in
154.47 s**; focused permission coverage passed **15 tests, 5 Windows skips**.
The prior 645-test copy passed 616 tests/29 skips in 124.28 s before the additional
Windows inherited-read restoration test. The final 646-test copy includes it.
All 30 final skips are Windows junction, Job Object/taskkill/API, readonly-file
and ACL integration/restoration cases. Real POSIX workflow SIGINT, diagnosis
SIGINT and signal-return-code tests ran; Windows deterministic interruption
coverage is a different category.

Locked sync, Ruff lint/format, both mypy targets, final build and distribution
inspection passed on Linux. The final external offline consumer passed its
installed key/layout workflows and error audit. UID 0's audit executed 38 cases
and honestly skipped two mode-bit permission denials plus Windows junctions.
A separate fresh UID/GID 1000 container consumer executed 40 audit cases,
including both real permission rejections (exit 2, zero starts, unchanged watched
bytes); only Windows junctions were skipped. Its temporary state was removed.
All 97 clean-copy source hashes were preserved; final helper/tests matched the
root source. Initial/final Linux wheel bytes were identical, SHA256
`bd76338248bc29791812cbfd4a4647c1e21a32408e4a5edbe415cd6e07b9ce0e`.

Linux evidence: `.validation/m2d1-linux-evidence/results/` (seven measurements)
and `.validation/m2d1-final-linux-evidence/results/` (final suite, consumers,
skips, source/wheel comparisons and final summary).

## Historical compatibility and installed consumers

Windows generated genuine version-1 bundles from fresh Git archives of the
reviewed prior sources, then validated them with the current reader. A separate
fresh standard venv/pip installation of the current wheel repeated default JSON,
explicit JSON and text inspection and three fresh relocated replay confirmations
for each bundle, while original source/bundle paths were unavailable. Source,
original bundle, relocated payload and historical report hashes remained equal.
No old report was rewritten or manually constructed.

| History | Archived commit | Prior reduction | New replay |
| --- | --- | --- | --- |
| pre-M1b INTEGER threshold | `ba40d64db748d974c36666294a1cc4500c79c25f` | 11 -> 3 | 3 TARGET_FAILURE confirmations |
| accepted M2a TEXT | `d60c79c07ae12666af9572ced69edc3b9523ce17` | 10 -> 10 | 3 TARGET_FAILURE confirmations |
| accepted M2b composite | `d70edac43c22efe3df643b821af1c51ec756a945` | 8 -> 8 | 3 TARGET_FAILURE confirmations |

Evidence: `.validation/m2d1-history-evidence/`, the three fresh
`.validation/m2d1-*-v1-fresh/` directories and
`.validation/m2d1-installed-history/result.json` (installed-wheel origin,
inspection/replay, source and supplied-bundle byte hashes).

Consumers use a fresh standard venv outside the checkout and that interpreter's
`pip install --no-index --no-deps`, with Python path/home/development-environment
leakage removed. Import-origin checks establish installed site-packages; no
editable imports, consumer uv requirement or consumer network are used. The
documented threshold journey and small genuine TEXT/composite/WITHOUT ROWID
lifecycles exercise static and three-confirmation executable diagnosis,
reduction, default/explicit JSON and text inspection and three-confirmation
relocated replay. Spaces/Unicode paths, input/bundle byte equality and disposal
of temporary consumer state are checked. Full application measurements use
separate real large fixtures, including both 1,308-row billing layouts.

Build/content checks compare all 12 runtime files with source, validate exact
wheel metadata/license/entry point, no runtime dependencies, Python >=3.12,
version 0.1.0 and the intended sdist files. Generated databases, bundles, sidecars,
caches, logs, environments, credentials and retained evidence are excluded.
The unchanged read-only CI matrix, pinned actions and installed-wheel checks
remain intact; no retry, continue-on-error or publication step was added.

## Seven full application scenarios

Separate fresh installed-wheel runs passed all seven scenarios on Windows and
Debian. Every scenario preserved source/asset/original/relocated-bundle byte
hashes, declared schema/storage layout and retained values; integrity and foreign
keys were valid. Static/executable diagnosis, reduction, all inspection formats
and relocated replay ran outside source imports with original paths unavailable.
Each final fixture and relocated replay had three fresh TARGET_FAILURE
confirmations. Invalid candidates, unresolved trials and unknown interrupted
launches were zero for these measurements. Results below are observed for these
fixtures, not global-minimality proofs or new reducer rules.

| Scenario | Original -> final rows | Invocations / budget | Accepted / cache hits | Windows reduction s | Debian reduction s |
| --- | --- | --- | --- | --- | --- |
| duplicate export | 2,430 -> 5 | 54 / 400 | 13 / 11 | 16.781 | 4.472 |
| threshold | 11 -> 3 | 18 / 80 | 3 / 5 | 5.313 | 1.121 |
| reservation overbook | 4,248 -> 9 | 131 / 400 | 21 / 24 | 51.719 | 10.432 |
| approval cycle | 1,626 -> 6 | 107 / 400 | 22 / 25 | 31.547 | 7.937 |
| TEXT entitlements | 970 -> 10 | 180 / 240 | 30 / 31 | 52.265 | 12.854 |
| ordinary composite billing | 1,308 -> 8 | 126 / 260 | 22 / 23 | 40.594 | 9.994 |
| mixed WITHOUT ROWID billing | 1,308 -> 8 | 126 / 260 | 22 / 23 | 37.781 | 9.579 |

Both full billing fixtures exceed 1,200 rows and retain at most 16. Measurement
JSON includes per-table counts, actual/budget invocation evidence, cache and
acceptance summaries, file sizes, exact source/bundle SHA256 maps, schema/value/FK
checks and new replay outcomes. Windows evidence is
`.validation/m2d1-windows-evidence/measurements-six/` and `measurements-without-rowid/`;
Debian evidence is the corresponding directories under
`.validation/m2d1-linux-evidence/results/`. The small wheel smoke is a separate
installation check and was not substituted for these full measurements.

Windows's installed consumer passed 40 error-audit cases, including both genuine
input/output permission rejections. Input probe observed PermissionError/errno 13
with no winerror; diagnosis returned 2 in 0.594 s. Directory creation observed
errno 13 / winerror 5; reduction returned 2 in 0.547 s. Both observed zero starts,
unchanged bytes and restored original parent DACLs; input child readability was
checked after restoration. No permission capability skip occurred. The sole
audit skip was unavailable synthetic symlink creation; Windows junction tests ran.
Temporary consumer state was removed and wheel bytes preserved. Evidence:
`.validation/m2d1-windows-evidence/consumer.json`.

## Final Windows gates and package equality

The final 646-test Windows suite passed **640 tests, 6 skipped, 2 warnings in
719.93 s**. Final focused permission tests passed **20 tests in 26.81 s**,
including actual output denial, inherited-input recovery and restoration after
skip/assertion/timeout. The earlier 645-test suite passed 639 tests/6 skips/2
warnings in 716.93 s before the final inherited-input test was collected; final
source checks reran the full suite after that addition and helper repair. This
was validation after changed tests, not a retry of a failed unchanged suite.

Windows's six skips are two existing symlink privilege failures (WinError 1314),
POSIX workflow SIGINT, POSIX diagnosis SIGINT, executable-mode semantics and
POSIX signal return codes. Real ACL integration ran and was not capability-skipped.
The two warnings are the existing injected interruption/accounting boundaries:
`test_second_interrupt_in_real_oracle_cleanup_aborts_and_preserves_launch` and
`test_returned_process_handle_establishes_known_launch_before_evidence_assignment`,
both `oracle cleanup incomplete: taskkill exit (code 1)`. Their accounting
assertions passed; these warnings retain observed cleanup uncertainty and are
not a claim that every interrupted cleanup completed. The original hosted
warning's code 128 is separate historical evidence.

| Final gate | Windows 10 / Python 3.12.15 | Debian / Python 3.12.11 |
| --- | --- | --- |
| Locked synchronization, Ruff lint/format, both mypy targets | PASS | PASS |
| Focused permission regressions | 20 passed | 15 passed, 5 Windows skips |
| Full final suite | 640 passed, 6 skipped, 2 existing warnings | 616 passed, 30 Windows skips, no warnings |
| Wheel/sdist and exact content/metadata inspection | PASS | PASS |
| Fresh external offline standard venv/pip consumer | PASS | PASS |
| Installed small TEXT/composite/WITHOUT ROWID lifecycles | PASS | PASS |
| Real installed input/output permission rejection | Both observed, exit 2 / zero starts | Both observed in separate non-root run |
| Seven full installed-wheel scenarios and byte/schema/FK checks | PASS | PASS |
| Genuine historical INTEGER/TEXT/composite compatibility | Source reader and installed wheel PASS | Not separately rerun on Linux |

Windows final rebuild wheel bytes matched the consumer/measurement wheel,
SHA256 `e06de9072221f860f0338b0d2169f9d5867e31fdcc2d8a1d2935911e05f6675e`.
Within-platform byte equality and all 12 source-runtime comparisons establish
that the earlier installed measurements exercised the final wheel. Cross-platform
archive byte equality is not claimed. Final evidence/report and comment-only
wording are included in a separate fresh root build/content inspection after
these checks; runtime bytes remain the same tested bytes.

Windows command/log evidence is `.validation/m2d1-windows-evidence/` and
`.validation/m2d1-windows-final-checks/`; final source packaging and hash/status
review are under `.validation/m2d1-final-package/` and
`.validation/m2d1-final-review.json`.

## Review, remaining limits and handoff

Final review checked permission assumptions, explicit target ownership and
automatic inherited effects, original-DACL restoration on every exit, honest
capability skips, real production staging injection, no-oracle/no-overwrite
assertions, private output, finite bounds, version/packaging stability and final
evidence wording. A field that had described API success as child restoration
was corrected to an exit-status field; actual child readability is recorded only
after successful reads/hashes. Comments now distinguish the sole explicitly
targeted parent from effects on its owned children. No additional product defect
was demonstrated and no product runtime code changed.

This does not replicate the original Windows Server runner's security context
or explain its permitted creation. New native Ubuntu/Python 3.12/3.14 and Windows
Server evidence requires the next hosted commit. Restoration support on arbitrary
filesystems, real Windows console Ctrl+C, macOS and independent outside-user
feedback remain unestablished. Existing Windows process-start/Job and POSIX
detached-child limitations remain; authorized oracle code inherits OS access and
environment. Reduction is not anonymization, temporary data is not securely
erased and matching manifests do not authenticate historical claims. Only the
executed fresh replays establish their new outcomes.

Final branch remains `main`, HEAD
`6aaf7d77d51bb5e6277f16caa3a85e5e3e9574b6`. Git status has these seven unstaged
or untracked files and no staged change:

```text
 M docs/alpha-readiness.md
 M docs/roadmap.md
 M tests/error_smoke.py
 M tests/test_cli_errors.py
?? docs/m2d1-completion.md
?? tests/test_error_smoke_permissions.py
?? tests/windows_permissions.py
```

Historical completion reports, source runtime, SECURITY.md, onboarding/tutorial
assets, pyproject.toml, uv.lock and CI are preserved. No reset, clean, stage,
commit, push, tag, release, package upload or alpha publication occurred. All
generated state remains ignored. Changes are ready for Dan's review; hosted
acceptance and **CONDITIONAL GO** conditions still require his subsequent commit
and push with all three jobs passing, independent developer feedback and his
explicit distribution decision.
