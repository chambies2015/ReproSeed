# Limited public-alpha readiness

Decision updated: 2026-10-16. Verdict: **CONDITIONAL GO** pending the M2f technical
gate below. Dan directs continued development using thorough automated testing.
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

The technical gates and separate publication decision are:

1. Dan reviews the unstaged M2f changes, commits/pushes them, and obtains a successful
   hosted matrix on Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12.
   Accepted M2e commit `0b776c8f5002c846940e438207d582af2259bda6`, hosted run
   `38901295778`, establishes the prior gate, not the new source. M2d.1's Windows
   ACL-denial test was capability-skipped, separate from local actual-denial and
   deterministic staging-denial evidence. Historical completion reports are preserved.
2. Resolve demonstrated critical correctness defects and pass the bounded automated
   verification, package and portable-replay checks on the final source. Human
   usability is **NOT TESTED** and advisory; independent developers are unavailable.
   Recruiting testers is not a development, technical-acceptance or limited-alpha
   recommendation prerequisite. Agent tests are not an independent human study.
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
and its separate deterministic and real ACL evidence. M2d.1's accepted hosted run
is preserved in historical reports. Accepted M2e's hosted gate is recorded above;
M2f's hosted gate remains pending Dan's commit and push. Automated verification
establishes only the tested invariants and bounded scope. See [M2f evidence](m2f-completion.md).

M2f's local frozen-source gates passed on Windows with Python 3.12.15 and 3.14.7:
each full suite recorded 801 passed, six platform/capability skips and two disclosed
cleanup-injection warnings. Each runtime completed 2,432 extended generated
implementation cases with 1,216 exact comparisons and detected all ten selected
semantic mutants. Seven full installed application scenarios, the larger scalar
and mixed-layout fixtures, three genuine historical bundle families, clean builds
and offline external consumers passed. The separate consumer error audit executed
40 checks and capability-skipped one synthetic symlink. These local results do not
establish the pending hosted matrix or real Windows console Ctrl+C behavior.

| Gate | Status | Evidence and limit |
| --- | --- | --- |
| A. Core reproducibility correctness | PASS | Real SQLite/subprocess acceptance, strict report checks, invocation accounting and coherent interruption regressions; compact final/replay confirmations are fresh. This verifies the supplied oracle contract, not semantic equivalence beyond it. |
| B. Supported SQLite compatibility | PASS | Scalar INTEGER/TEXT, two-component keys, grouped FKs, mixed WITHOUT ROWID layouts and explicit rejection coverage. The existing schema subset is frozen. |
| C. Source immutability | PASS | Complete source/assets and supplied/relocated bundle hashes across diagnosis, reduction, inspection and replay. Tool behavior protects originals; authorized code has the user's OS permissions. |
| D. Strict failure oracle semantics | PASS | Incorrect exit, wrong stream, mismatch, unrelated crash, timeout/output limit and inconsistent baseline remain non-target results; no majority voting or exit-only acceptance. |
| E. Bundle integrity and relocation | PASS | Default/explicit JSON and text inspection, private acquisition, sidecar/tamper/traversal rejection and three new unrelated-cwd replay outcomes with original paths unavailable. Hashes do not authenticate an author. |
| F. Installation from a wheel | PASS | Fresh external standard venv/pip --no-index --no-deps installs, console commands and site-packages origin proof. Consumer uses neither uv nor editable imports/network. |
| G. Human usability | NOT TESTED | Complete synchronized files and literal shell workflows tested internally, including spaces/Unicode; independent human feedback remains advisory and does not block engineering acceptance. |
| H. Useful failure diagnostics | PASS | Installed negative audit checks classification, no inappropriate launch/write/success, bounded output and synthetic secret omission. Curated input causes and human recovery guidance added. The original hosted ACL test did not establish a permission denial, so its successful reduction is not denial-handling evidence; M2d.1 separates the actual permission probe from deterministic staging-denial coverage. |
| I. Security and data-sharing disclosures | PASS | Focused controlled boundary tests and practical pre-sharing checklist. Temporary data is not securely erased; included code and retained values must be reviewed. |
| J. Cross-platform execution and cleanup | PARTIAL | Accepted M2e hosted evidence remains distinct from M2f. The prior M2d.1 hosted Windows ACL case was capability-skipped. M2f needs its new hosted matrix; real Windows console Ctrl+C remains unestablished. |
| K. Historical format compatibility | PASS | Genuine archived pre-M1b INTEGER, accepted M2a TEXT and M2b composite version-1 bundles inspected/replayed without rewriting historical reports. |
| L. CI, contents and distribution metadata | PARTIAL | Accepted M2e hosted run 38901295778; M2f requires Dan's reviewed commit/push and its actual successful hosted matrix, with pinned actions and wheel checks preserved. |
| M. External dependency limitations | PARTIAL | Missing dependency is UNRESOLVED and replay can differ despite matching hashes. Dependencies/environment remain manually supplied and documented. |
| N. Remaining technical and publication gates | PARTIAL | Actual hosted M2f CI and resolution of critical defects remain technical conditions. Dan's explicit distribution decision is separate; no package publication is authorized. |

## Significant findings

Severity: P0 is an unacceptable correctness/integrity/security failure; P1 is a
material alpha usability/reliability blocker; P2 is a nonblocking improvement or
documented limitation. Absence of a finding is not a proof of universal safety.

| Finding | Severity | Actual evidence and reproduction | User impact / action | Fixed in M2d? |
| --- | --- | --- | --- | --- |
| Windows denied output stalled before reporting permissions | P1 | The original local audit recorded a 30-second stall; M2d replaced tempfile acquisition with one exclusive staging-parent mkdir. Hosted run 38613024891 created a verified bundle without an effective denial precondition. | Probe actual permission capability and retain independent staging-denial injection. Do not infer a permission bypass from a permitted operation. | M2d.1 accepted in run 38623620343; its hosted Windows actual-denial test was capability-skipped, distinct from local actual-denial and deterministic evidence. |
| Input error stderr exposed selected input details | P2 | Missing-source reduction echoed an absolute path; unsupported-schema errors could echo schema names. Controlled sentinel regressions now exercise missing source/asset, unknown field, schema and OSError cases. | Curate causes without raw paths/values; preserve classification and direct users to static diagnosis. | Yes: shared input-cause mapping and terminal-safe residual errors; version-1 JSON shapes and exit meanings preserved. |
| New user entered through checkout/uv instructions | P2 | Original README quickstart required checkout/uv; fresh wheel journey otherwise worked. A local `py -3.12` failed because uv-managed Python was not launcher-registered. | Lead with wheel onboarding, complete files and explicit interpreter recovery; check native exit codes. | Yes: new guide/README, executable synchronization tests and consumer recipe. |
| Independent first-user evidence absent | Advisory / NOT TESTED | Every automated journey was performed by project agents; no independent developer study ran. | Record human usability as untested; continue bounded engineering verification without a recruitment gate. | Not a technical-acceptance prerequisite under Dan's M2f direction. |
| M2d hosted Windows gate failed | Prior condition | M2d run 38613024891 failed the unproven ACL-denial precondition. This alone did not demonstrate a product permission defect. | Preserve historical completion evidence and distinguish an actual denial from a capability skip. | Closed by accepted M2d.1 run 38623620343 with the Windows actual-denial case capability-skipped. Accepted M2e and pending M2f have separate gates. |
| Executable bundles are not a sandbox | P2 limitation | Static/acknowledgement/no-launch sentinels and private-payload mutation regressions pass. Review confirms subprocesses inherit permissions/environment; documented Windows startup/Job and POSIX detached-child limitations remain. | Review code and use external isolation for untrusted parties. Do not share secrets or run malicious probes on unrelated resources. | Documented; no OS sandbox promised. |
| Integrity is relative to the supplied manifest | P2 limitation | Controlled bundle edits plus recomputed hashes can pass static inspection, while new replay reports changed outcomes. | Obtain artifacts from a trusted source. Commit integrity, wheel-byte equality and package publisher authentication are distinct. | Documented; authorship authentication is outside this format. |
| Dependencies and sensitive content remain explicit responsibilities | P2 limitation | Installed missing-dependency replay produces three UNRESOLVED outcomes; retained SQLite/schema/assets/config remain in the bundle. | Review every declared file/value and disclose/install trusted dependencies. Temporary files are not securely erased. | Documented; no implicit collection or automatic redaction added. |

## Follow-up decision

The [original hosted run](https://github.com/chambies2015/ReproSeed/actions/runs/38613024891)
does not satisfy the Windows gate. M2d.1 verifies effective permissions before the
real integration assertion and tests production staging denial independently;
neither a capability skip nor a deterministic injected denial establishes real
ACL-denial behavior on a runner where directory creation remains allowed.

The tests support a bounded technical recommendation when actual technical gates
pass. They do not establish production readiness or a successful external user study.
Human feedback may improve later usability work without blocking implementation or
technical acceptance. Publication remains Dan's separate explicit decision; no
publication follows automatically from a technical GO recommendation.
