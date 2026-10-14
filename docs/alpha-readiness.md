# Limited public-alpha readiness

Decision date: 2026-10-14. Verdict: **CONDITIONAL GO** for the scope below.
This is an internal engineering review and simulated first-user journey, not an
independent user study or authorization to publish. The package remains version
0.1.0; no public package-index installation was established.

## Supported scope and conditions

The proposed alpha is for developers on **Windows and Linux** reducing trusted,
disposable local SQLite fixtures on Python 3.12+, with SQLite 3.37+ and the
[documented bounded schema](architecture.md#supported-schema). Ordinary/STRICT
tables and WITHOUT ROWID tables can use the supported scalar or two-component
INTEGER/TEXT keys and complete-parent-PK foreign keys. The user writes a specific
data-dependent oracle, supplies regular files explicitly, and installs external
application dependencies separately. The tested distribution path is a locally
built wheel installed into a fresh venv with pip. Recipients must review code/data
and choose their own isolation before acknowledging replay execution.

The conditional verdict requires:

1. Dan reviews the unstaged M2d.1 repair, commits/pushes it, and obtains a successful
   hosted matrix on Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12.
   M2d run 38613024891 passed both Ubuntu jobs but failed Windows's ACL-denial
   regression without establishing an effective denial precondition. It did not
   satisfy the hosted gate; accepted M2c CI does not certify the repair.
2. At least one independent developer completes the guide and relocated replay
   before widening access beyond an explicitly supervised pilot. Record confusion,
   unsuccessful steps, dependencies and sharing review; address any P0/P1 finding.
3. Dan makes an explicit distribution/version/support decision. A possible future
   alpha identifier is `0.1.0a1`; it is a recommendation, not an applied change.
   No release, package upload, tag, signing or publisher-authentication mechanism
   is implied by this review.

This scope excludes production/live databases, hostile bundles without external
isolation, automatic anonymization, a complete packaged execution environment,
global minimality, macOS alpha support, wider SQLite schemas and other adapters.
macOS was not validated; the required hosted Windows/Linux matrix remains a condition.

## Gate assessment

PASS means established within the stated local evidence and supported scope.
PARTIAL identifies a material limit or pending gate. BLOCKED means a demonstrated
unresolved blocker; NOT TESTED means no relevant execution evidence. See
[M2d completion](m2d-completion.md) for actual commands, results and intermediate
failures. The original report preserves its local observations; the
[M2d.1 completion](m2d1-completion.md) records the permission-precondition repair
and its separate deterministic and real ACL evidence. Hosted acceptance of M2d.1
remains pending Dan's new commit and push.

| Gate | Status | Evidence and limit |
| --- | --- | --- |
| A. Core reproducibility correctness | PASS | Real SQLite/subprocess acceptance, strict report checks, invocation accounting and coherent interruption regressions; compact final/replay confirmations are fresh. This verifies the supplied oracle contract, not semantic equivalence beyond it. |
| B. Supported SQLite compatibility | PASS | Scalar INTEGER/TEXT, two-component keys, grouped FKs, mixed WITHOUT ROWID layouts and explicit rejection coverage. The existing schema subset is frozen. |
| C. Source immutability | PASS | Complete source/assets and supplied/relocated bundle hashes across diagnosis, reduction, inspection and replay. Tool behavior protects originals; authorized code has the user's OS permissions. |
| D. Strict failure oracle semantics | PASS | Incorrect exit, wrong stream, mismatch, unrelated crash, timeout/output limit and inconsistent baseline remain non-target results; no majority voting or exit-only acceptance. |
| E. Bundle integrity and relocation | PASS | Default/explicit JSON and text inspection, private acquisition, sidecar/tamper/traversal rejection and three new unrelated-cwd replay outcomes with original paths unavailable. Hashes do not authenticate an author. |
| F. Installation from a wheel | PASS | Fresh external standard venv/pip --no-index --no-deps installs, console commands and site-packages origin proof. Consumer uses neither uv nor editable imports/network. |
| G. First-use instructions | PARTIAL | Complete synchronized files and literal shell workflows tested internally, including spaces/Unicode. Independent outside-user feedback remains untested. |
| H. Useful failure diagnostics | PASS | Installed negative audit checks classification, no inappropriate launch/write/success, bounded output and synthetic secret omission. Curated input causes and human recovery guidance added. The original hosted ACL test did not establish a permission denial, so its successful reduction is not denial-handling evidence; M2d.1 separates the actual permission probe from deterministic staging-denial coverage. |
| I. Security and data-sharing disclosures | PASS | Focused controlled boundary tests and practical pre-sharing checklist. Temporary data is not securely erased; included code and retained values must be reviewed. |
| J. Cross-platform execution and cleanup | PARTIAL | Clean Windows and Debian-container runtime evidence; existing POSIX real-signal and Windows injected/Job regressions remain distinct. M2d hosted Ubuntu/Python 3.12 and 3.14 passed; Windows/Python 3.12 failed an unproven ACL-denial precondition. M2d.1 hosted validation and real Windows console Ctrl+C remain unestablished. |
| K. Historical format compatibility | PASS | Genuine archived pre-M1b INTEGER, accepted M2a TEXT and M2b composite version-1 bundles inspected/replayed without rewriting historical reports. |
| L. CI, contents and distribution metadata | PARTIAL | Wheel/sdist builds, exact runtime/metadata/license/content checks and unchanged hosted matrix with repeatable small consumer smoke. M2d run 38613024891 passed both Ubuntu jobs but failed Windows; the M2d.1 hosted gate awaits Dan's repair commit/push and all three successful jobs. |
| M. External dependency limitations | PARTIAL | Missing dependency is UNRESOLVED and replay can differ despite matching hashes. Dependencies/environment remain manually supplied and documented. |
| N. Remaining public-alpha blockers | PARTIAL | No demonstrated unresolved P0 in this review. Successful hosted M2d.1 CI, independent first-user feedback and Dan's explicit distribution decision remain conditions. |

## Significant findings

Severity: P0 is an unacceptable correctness/integrity/security failure; P1 is a
material alpha usability/reliability blocker; P2 is a nonblocking improvement or
documented limitation. Absence of a finding is not a proof of universal safety.

| Finding | Severity | Actual evidence and reproduction | User impact / action | Fixed in M2d? |
| --- | --- | --- | --- | --- |
| Windows denied output stalled before reporting permissions | P1 | The original local development-console audit recorded a 30-second denied-output stall; M2d replaced tempfile acquisition under the output parent with one exclusive staging-parent mkdir. Hosted run 38613024891 instead created a verified bundle after a successful ACL edit; the original test never probed effective directory-creation denial. | Validate the actual ACL capability before the real CLI denial test, and independently inject denial at the production staging mkdir. Keep no-overwrite and interruption semantics; do not infer a permission bypass from an unmet precondition. | M2d added the production boundary and recorded local exit-2 evidence. M2d.1 repairs the test precondition and reinforces separate deterministic coverage; hosted acceptance remains pending. |
| Input error stderr exposed selected input details | P2 | Missing-source reduction echoed an absolute path; unsupported-schema errors could echo schema names. Controlled sentinel regressions now exercise missing source/asset, unknown field, schema and OSError cases. | Curate causes without raw paths/values; preserve classification and direct users to static diagnosis. | Yes: shared input-cause mapping and terminal-safe residual errors; version-1 JSON shapes and exit meanings preserved. |
| New user entered through checkout/uv instructions | P2 | Original README quickstart required checkout/uv; fresh wheel journey otherwise worked. A local `py -3.12` failed because uv-managed Python was not launcher-registered. | Lead with wheel onboarding, complete files and explicit interpreter recovery; check native exit codes. | Yes: new guide/README, executable synchronization tests and consumer recipe. |
| Independent first-user evidence absent | P1 condition | Every M2d journey was performed by project agents; no independent developer study ran. | Arrange an outside developer pilot; treat failures as feedback before widening availability. | No; subsequent human activity. |
| M2d hosted Windows gate failed | P1 condition | Reviewed M2d commit 6aaf7d77d51bb5e6277f16caa3a85e5e3e9574b6 ran in hosted run 38613024891: Ubuntu/Python 3.12 and 3.14 passed, Windows/Python 3.12 failed the ACL-denial test without proving its precondition. This failure alone does not demonstrate a product permission defect. | Dan reviews/commits/pushes M2d.1 and requires all three unchanged hosted jobs to pass. Preserve the original M2d completion report as historical local evidence. | No accepted repair run; pending authorized human commit/push and hosted validation. |
| Executable bundles are not a sandbox | P2 limitation | Static/acknowledgement/no-launch sentinels and private-payload mutation regressions pass. Review confirms subprocesses inherit permissions/environment; documented Windows startup/Job and POSIX detached-child limitations remain. | Review code and use external isolation for untrusted parties. Do not share secrets or run malicious probes on unrelated resources. | Documented; no OS sandbox promised. |
| Integrity is relative to the supplied manifest | P2 limitation | Controlled bundle edits plus recomputed hashes can pass static inspection, while new replay reports changed outcomes. | Obtain artifacts from a trusted source. Commit integrity, wheel-byte equality and package publisher authentication are distinct. | Documented; authorship authentication is outside this format. |
| Dependencies and sensitive content remain explicit responsibilities | P2 limitation | Installed missing-dependency replay produces three UNRESOLVED outcomes; retained SQLite/schema/assets/config remain in the bundle. | Review every declared file/value and disclose/install trusted dependencies. Temporary files are not securely erased. | Documented; no implicit collection or automatic redaction added. |

## Follow-up decision

The [original hosted run](https://github.com/chambies2015/ReproSeed/actions/runs/38613024891)
does not satisfy the Windows gate. M2d.1 verifies effective permissions before the
real integration assertion and tests production staging denial independently;
neither a capability skip nor a deterministic injected denial establishes real
ACL-denial behavior on a runner where directory creation remains allowed.

The tests support a narrow supervised developer pilot, with the conditions above.
They do not establish production readiness or a successful external user study.
Prioritize actual pilot blockers and sharing clarity before speculative schema or
PostgreSQL work. No publication follows automatically from **CONDITIONAL GO**.
