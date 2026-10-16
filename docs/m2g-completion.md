# M2g: exact pytest oracle bridge and complete workflow

Local work: 2026-10-16, America/Chicago. This report is completed from actual
validation results. M2g hosted acceptance awaits Dan's reviewed commit/push.
No publication or version change is authorized. Independent human usability is
NOT TESTED/advisory.

Starting state: clean `main`, HEAD `e14eaffbf4e3ddfc64df522b2660e0e9e8760039`.
Accepted M2f [hosted run 38945054973](https://github.com/chambies2015/ReproSeed/actions/runs/38945054973)
was inspected once: Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12
all succeeded. The latest-three-run listing showed it as the newest run; these
accepted results do not validate M2g. Historical completion reports remain unchanged.

Changes remain unstaged and uncommitted. No staging, commit, push, reset/clean,
branch/PR/tag, publication, tester contact or machine service/permission change
was performed. Version remains `0.1.0`; mandatory dependencies remain empty.

## Final source provenance

The final executable/documentation input capture is
`.validation/m2g-source-freeze-07.json`, recording 128 individual SHA256 values.
Its canonical sorted JSON path/hash aggregate is:

`a627857427337019b465ee1b86935c2f2936ca3836cb8d14d27ce61ccedd616a`

The retained local capture is
`C:\Users\xeonc\AppData\Local\Temp\reproseed-m2g-c98v9zzo\frozen-source-07`.
The root is also recorded in `.validation/m2g-local-roots.json`. Retain this owned
scratch root because evidence/reproduction commands refer to it. Completion prose
in this file is deliberately excluded from the aggregate, finished after execution
and included in the final rebuilt/content-checked source distribution. Git HEAD
alone does not identify an uncommitted implementation.

Earlier captures 01–06 and failed/interrupted checks are retained. The installed
test helper needed a package-only `-S` bootstrap. Later concrete probes found
implicit warning capture, malformed dependency metadata, child bytecode pollution
and filenames interpreted as pytest arguments. The
final capture contains their fixes and regression tests. All actual final bridge
checks, thirteen mutations and final external consumers use capture 07/the byte-equal
installed wheel. Runtime module bytes were compared against both the wheel and the
capture before version-specific test runs.

The single extended generated campaign and established non-pytest application/
historical checks used capture 03. The 03→07 audit records exactly four changed
files: this integration's bridge, its test module and two prose guides. The 57
selected non-pytest runtime/example/recipe/probe inputs are identical, and no
established runtime module references the bridge. The generated campaign's recorded
adapter/reducer/artifact provenance is unchanged. This is an explicit bounded
carryover of unchanged executed paths, not a claim that all fourteen modules or
the complete captures have equal hashes. The bridge consumers and mutations were
rerun on 07; the extended campaign was not repeated for a larger denominator.

## Bridge architecture and classification

`pytest_oracle.py` is the only added runtime module. Existing configuration,
oracle runner, SQLite model/adapter, reducer, budgets, confirmations, cache policy,
workflow, artifacts, report, diagnosis, inspection and event modules are unchanged.
There is no second reducer, automatic plugin entry point or format migration.

The optional module parses a strict four-field adapter-version-1 target. Reads are
bounded to 16 KiB; nodeid/exception/message have bounded UTF-8 lengths. It rejects
unknown/missing fields, malformed TOML/UTF-8, unsafe paths, unsupported versions and
types without echoing input values. It does not import the named exception class.
The target's directory anchors the run root and portable regular test path.
Test/conftest path links/junctions are rejected. The actual collected nodeid must
be an exact single ordinary synchronous Python function/method or explicit case.
Selection is checked again after collection before setup, including object identity,
and unexpected/duplicate execution aborts before another item's setup.

Pytest loads only after acknowledgement and compatible installed-version validation.
Each oracle process makes one `pytest.main` call. Supported released versions are
`>=8.3,<10`; actual versions exercised are locked **9.1.1** and separately obtained
**8.3.5**. A missing or non-string/malformed/unsupported version fails before test,
conftest or fake pytest module sentinels execute.

| Observed session | Bridge outcome |
| --- | --- |
| Exactly one intended call, exact qualified exception/message, successful setup/teardown, complete reports, consistent final one-failure session | 86, exact `REPROSEED_PYTEST_TARGET_V1` on stdout |
| Exactly one genuine passing setup/call/teardown and consistent completed success | 0, no marker |
| Different exception/message, setup/finalizer failure, extra failure, incomplete/duplicate/contradictory report, unfamiliar exit, collection/internal/session error or unsupported integration | 2, no marker |
| Observed interruption where clean return is possible | 130, no marker |

The observer compares actual call exception objects, phase reports and final session
state after pytest returns. It never forwards pytest's exit as a target signal.
A matching call followed by a failing finalizer is unresolved. Skips/xfail/XPASS,
exception groups, async/generator tests, reruns, xdist and custom collectors are
unsupported. Exact signature agreement establishes the configured contract, not
arbitrary semantic equivalence.

An additional read-only-source SQLite backup backs the reserved `reproseed_db` Path.
The selected test must request it directly or through a fixture dependency.
Ordinary local conftest fixtures are supported. Fixture overrides and registered
interception hooks for fixture setup, Python/runtest calls, protocol/loop or report
construction are rejected, including aliased hook names. The effective bound Path
is checked before the Python function body. Actual semantic use remains the author's
responsibility. Test writes never become the source, later candidate or compact export.

The bridge clears inherited `PYTEST_*` controls, disables third-party autoload,
uses an owned empty ini and explicit root/confcutdir, and rejects explicit conftest
plugin integration. Parent configuration/conftest cannot select unrelated tests.
Terminal/global capture/cache/logging/warnings plugins are disabled as appropriate;
explicit stdout/stderr/log/warning capture fixtures are rejected in dependency
closures and dynamic requests. Remaining output is discarded in bounded 4 KiB
reads while fixed records emit at least its volume to the outer runner. This prevents
printed markers and raw pytest diagnostics from entering the protocol while preserving
timeout/output enforcement. It is not a general sanitizer or memory/OS sandbox.
Arbitrary trusted code can redirect output, allocate memory and access OS resources.
Temp/cache/bytecode state stays disposable; subprocesses are never reused. Ordinary
Python children inherit bytecode suppression, and the original environment is
restored. Portable filenames beginning `-` or `@` are passed as literal file paths,
not pytest options or argument-file directives.

## Real application and counterfactuals

`examples/pytest_duplicate_export/prepare.py` copies only named assets from the
existing duplicate-export example plus its test/target/config. It runs the unchanged
deterministic generator. The ordinary oracle/example is intact. The pytest test
queries expected entries independently, invokes the real exporter and raises the
stable explicit AssertionError only after observing an omitted entry with a same-name
entry in a different project. Other export discrepancies have a different exception.

The full case has 2,430 user rows (6 owners, 24 projects, 2,400 entries), an explicit
400-invocation budget, 10-second oracle timeout and 65,536-byte output bound.
The small case uses 10 genuine generated rows. Both compact to five retained rows
(one owner, two projects, two entries), within the eight-row acceptance bound.
No production default or reducer ordering was changed to achieve this result.

All executable diagnosis/baseline/final/replay checks require three fresh target
confirmations; every accepted reduction has two actual confirmations. Static
diagnosis launches no tests. The lifecycle exercises progress/events, default and
explicit JSON plus text inspection, renamed original case/bundle paths and replay
from an unrelated directory. Hashes, schema, retained declared values, integrity/FKs
and final counts are checked. Correcting only the exporter's known key in a separate
owned case makes the same unchanged test genuinely pass (bridge exit 0). Verified
original bundles are never patched in place.

Final07 installed-wheel measurements:

| Pytest / case | Original → retained | Reduction executions / budget | Wall seconds |
| --- | --- | --- | --- |
| 9.1.1 small | 10 → 5 | 25 / 400 | 24.235 |
| 9.1.1 full | 2,430 → 5 | 54 / 400 | 49.172 |
| 8.3.5 small | 10 → 5 | 25 / 400 | 18.031 |

The full search recorded 46 attempts, 13 accepted reductions, 11 cache hits and
zero unresolved/invalid candidates. Termination was `single_row_closures_exhausted`,
which is not a global-minimality proof. The 54 executions include reduction baseline
and final verification; separate executable diagnosis and relocated replay each
add three actual confirmations. Startup probes and the fixed-app execution are
separate consumer commands, not invented report invocations.

Every six-file source hash and eight-file bundle hash remains equal before/after
the operations and relocation. Concrete full-case SHA256 values:

| Payload | SHA256 |
| --- | --- |
| Original generated database | `a1f219e3495878679289eef047a6eba8e91d483797eaa5977c5b5f4f785cda69` |
| Compact fixture, including after relocated replay | `8b9b80e6a6a2e3ae387dee0f3b93da7a5d9dba34b0fada3b8c06c571e1958e4a` |
| Exporter, identical source→bundle | `24a55f35d1d1264027c4141f82621fb2e3ae7b14e92716e00cd97225ee371e99` |
| Test, identical source→bundle | `dfe7c01819d18c81b7d6764c9cdeabcb0f6b85dba3301895882301ea73a76091` |
| Target, identical source→bundle | `590d6345a25828f6ba6f455088cf51c6c2e36b23ac3dc67dabc6b4d3cec23176` |
| Final07 full bundle manifest | `fb0f4db537e1d756aa7cddc5a0567ffd1ec6a89576e69242ff209824da01514d` |

Full inventories and each actual outcome/command are retained in
`.validation/m2g-pytest-consumers-frozen07.json` and
`.validation/m2g-pytest8-consumers-frozen07.json`. Earlier 03/04 consumer successes
remain separately labeled and are not substituted for final07 execution.

Three fresh samples per startup condition gave these medians in seconds:

| Condition | No-op Python | Pytest import | Complete bridge | Import minus no-op |
| --- | --- | --- | --- | --- |
| 9.1.1 small | 0.078 | 0.703 | 0.968 | 0.625 |
| 9.1.1 full | 0.047 | 0.547 | 0.953 | 0.500 |
| 8.3.5 small | 0.047 | 0.375 | 0.578 | 0.328 |

These observations ran alongside validation jobs and include filesystem/scheduling
noise. The import delta estimates startup; complete bridge time also includes
SQLite snapshot, collection and the actual test. This is not a stable performance
ratio or a CI timing assertion. No startup cost is hidden by process reuse.

## Adversarial coverage and demonstrated repairs

`tests/test_pytest_oracle.py` contains 153 cases, combining real SQLite/fresh
subprocess sessions with impossible-state hook stubs. The executed boundaries include:

| Category | Actual checks |
| --- | --- |
| Exact selection/signature | Matching failure, genuine pass, different type/message/other node, parametrized exact case versus family, module/class/missing selector, custom collector ancestry and late collection-item insertion |
| Full phases/session | Setup/teardown-only lookalikes, target plus finalizer error, pass plus teardown error, syntax/import/collection error, internal/session error, final failure-count drift, KeyboardInterrupt and unknown/duplicate/missing/contradictory report/exit states |
| Unsupported outcomes | Skip/skipif, xfail, strict/non-strict XPASS, exception groups, async/generator/custom collection, rerun integration and external plugin declarations |
| Optional dependency/acknowledgement | Actual wheel-only absence, supported/unsupported versions and missing metadata Version before sentinels; help/import/static diagnose/inspect with pytest unavailable; unacknowledged execution |
| Environment/binding | Autoload entry-point sentinel, inherited addopts/plugins, parent ini/conftest, local fixture dependencies, reserved override and result-interception hooks/aliases, direct/indirect/dynamic capture fixtures |
| State/output | Direct and repeated outer DB/asset writes stay disposable; fake markers in passing/wrong-failure tests; actual reached infinite/noisy/warning-flood cases hit outer bounds; wrong expected exit/marker stream; private signature/path/test-output sentinels absent from public output/progress/events |
| Files/config | Traversal, unsafe/oversized/unknown-field target, selected test/conftest links, target links and actual Windows junction rejection |

Three symbolic-link creation tests capability-skip on this Windows account with
WinError 1314. The Windows junction test actually runs and passes. Injected
KeyboardInterrupt is distinct from real POSIX signals and real Windows console
Ctrl+C; no new local real-signal pass is claimed.

Review demonstrated and repaired: custom collector ancestry escaping an item-only
check; final session failure counts drifting after reports; fixture hook ordering/
interception; explicit capture fixtures despite `--capture=no`; default warning
capture bypassing the byte bound; and missing dependency Version causing a raw
traceback. Each has a permanent regression. Raw private diagnostics and emitted
test markers cannot substitute for structured call evidence.

## Mutation sensitivity and generated correctness

The disposable recipe preserves all ten M2f probes and adds three bridge probes.
All thirteen clean controls passed, all thirteen mutants were detected by semantic
assertions, and all 26 control/mutant changed-boundary traces were reached.
Denominator: **13 attempted, 13 detected, 0 survivors, 0 invalid, 0 timeouts**.
The final 07 run took 39.004 wall seconds. Working and frozen input hashes remained
unchanged. No syntax/import/setup breakage was credited as a detection.

| Bridge mutation | Real-session control and detecting assertion |
| --- | --- |
| Compare exception type while ignoring message | Different actual assertion message must remain unresolved |
| Change required-phase failure rejection into TARGET | Matching call plus failed fixture finalizer must remain unresolved |
| Return PASS on a skipped-call problem | A real skipped call is unresolved, never a genuine pass |

Full raw controls, mutant results, exact source replacement, changed-line traces,
hashes and replay argv are in `.validation/m2g-mutations-final07.json` and the retained
owned mutation directory. Earlier ten probes are unchanged. The generated smoke
seed 104729 passed all 41 comparisons/82 implementation cases: 8 supported, 8 deliberate
unsupported, 24 model and 1 lifecycle per implementation. Its 16 expected rejections
are separate from driver failures. The one extended campaign uses the unchanged
128/64/1,000/24 profile per implementation. It passed **2,432/2,432 implementation
cases and 1,216/1,216 exact comparisons**, with 128 expected schema rejections and
zero failed, skipped or timed-out cases. Per implementation it recorded 88,675
closure checks, 9,988 exhaustive seed subsets, 772 materializations, 240 CLI calls,
24 generator subprocesses and 674 actual oracle subprocesses. These counters are
distinct; model/reference checks are not presented as pytest/oracle executions.
Summed worker elapsed time was 675.281 seconds with concurrent milestone jobs,
not an isolated performance comparison. Recorded adapter/reducer/artifact origin
hashes matched in all 7,296 extended provenance checks (not a full sys.modules trace).
The complete raw extended JSON is 156,533,095 bytes; its compact summary, selected
input equality audit and fresh generic-CLI no-eager-bridge import probe are retained
separately. All frozen03 hashes remain unchanged after the one campaign.

## Packaging, consumers, platforms and limits

The wheel remains dependency-free with only the console-script entry point and no
pytest11 plugin. The bridge and pytest invoked with `-m` are external execution
dependencies outside the version-1 bundle manifest. Such bundles need an M2g-capable
build and compatible pytest; they are not Python-only and an older ReproSeed cannot
supply this module. Installed dependency inventories are retained in new developer
evidence only, never inserted into old report/configuration/manifest/event formats.

The six official locked wheels were downloaded with normal pip setup and verified
against every corresponding `uv.lock` SHA256. `tests/pytest_wheelhouse.py` was also
executed successfully against its six exact URLs/hashes. The separately downloaded
pytest 8.3.5 wheel SHA256 is
`c69214aa47deac29fad6c2a4f590b9c4a9fdb16a403176fe154b79c0b4d4d820`;
its owned wheelhouse/provenance reuses the five verified locked dependencies.
Neither setup changes the project lockfile. Actual consumer installs/lifecycles
use offline pip and fresh standard venvs outside the checkout, without editable,
PYTHONPATH/PYTHONHOME or source-checkout imports. Parent orchestration legitimately
uses the frozen test helpers; every consumer's ReproSeed import is proven to be its
own installed site-packages. Wheel-only consumer A tests ordinary commands/examples
plus bridge help/acknowledgement/missing/static behavior. Consumer B installs
supported pytest explicitly and performs the full workflow and fixed-app counterfactual.

The exact thirteen-command PowerShell block in `docs/pytest-oracles.md` also passed
as one script against the installed wheel in a fresh external mini repository.
PowerShell 7.6.5 selected system Python 3.14.7 / SQLite 3.50.4, and pytest 9.1.1
was installed from the verified offline wheelhouse. All commands completed in
65.938 seconds: static/executable diagnosis, reduction with events/progress,
default/JSON/text inspection, relocation and replay. The small fixture reduced
10→5 rows in 25 invocations; baseline/final/replay each confirmed three times.
All fourteen explicitly staged input files stayed unchanged. Evidence and the
exact executed block are in `.validation/m2g-powershell-guide-frozen07.json`.
Two setup-only Python launcher lookup failures are retained separately; neither
executed the guide block. The POSIX block has not been locally executed.

Builds use hatchling 1.32.4 in a separate owned standard venv with offline build-only
wheels (packaging 26.3, pathspec 1.1.1, pluggy 1.7.0, tomlkit 0.15.2 and
trove-classifiers 2026.9.21.13). These do not enter runtime/consumer dependencies.
The actual command is `uv build <frozen-source> --offline --no-sources
--no-build-isolation --python <owned-build-venv> --out-dir <owned-output>`.
The separate prepared environment supplies the unchanged build-system requirements.
Wheel/sdist content checks verify exact runtime bytes, empty requirements, license,
entry point, documentation/examples/tests and exclusion of databases/caches/generated
outputs/mutants/third-party distributions.

Local execution is Windows 10 build 19045 with Python 3.12.15 / SQLite 3.53.1;
the additional bridge version/platform run uses Python 3.14.7 / SQLite 3.50.4.
Docker server access and WSL enumeration were denied. They were not bypassed and
host setup/permissions were not changed; local Linux and literal POSIX execution
are **NOT TESTED**. The documented POSIX equivalent awaits actual hosted execution.
The required Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 matrix,
pinned actions, read-only permissions and strict failure behavior remain. CI adds
only exact locked-wheel acquisition and the bounded small bridge wheel smoke.
Hosted M2g acceptance awaits Dan's commit/push and that commit's actual CI results.
No macOS, independent human usability, global minimality or publication claim follows.

## Intermediate evidence retained

- Default uv cache access failed; locked sync passed using the owned repository
  cache. Default network setup was restricted; approved explicit dependency setup
  downloaded only the selected wheels. A first temp-wheelhouse write was denied;
  setup succeeded in owned `.validation` without changing permissions.
- The first online build could not reach the index; an offline network-share build
  scan was stopped through its tool session. Final builds run on the small local
  frozen copy with separately prepared offline build requirements.
- Early evolving bridge tests recorded 14 failures/50 passes/2 skips/2 setup errors;
  initial plugin identification and overly long automatic parameter IDs were fixed.
  A later prefreeze run recorded 1 failed/124 passed/3 skipped, exposing fixture hook
  ordering. The failures and focused repairs are retained and are not final passes.
- Frozen03 pytest8/3.12 and pytest9/3.14 each recorded 1 failed/141 passed/3 skipped
  because the test's `-S` helper exposed site-packages. The package-only helper fix
  passed all six affected cases on both versions; frozen04 then recorded
  142 passed/3 skipped on both environments.
- Frozen04 review probes independently demonstrated warning capture and malformed
  dependency Version diagnostics. Final07 includes their narrow fixes and four
  additional tests. Later direct-mode probes found Python-child bytecode creation
  and literal filenames interpreted as pytest arguments; final07 includes the
  narrow environment/literal-path fixes and four further positive regressions.
  Frozen05's full suite passed 947 tests with nine skips and two warnings in 532.08 s
  before these last fixes. The superseded full03 suite was intentionally interrupted at
  roughly 68% after replacement; it is not a complete-suite pass. All earlier
  consumer successes and startup measurements remain separately labeled. The
  superseded full06 run was also stopped for replacement by final07; neither partial
  run is relabeled as a complete-suite pass.

No failed or incomplete intermediate is relabeled as a pass. Final gate results,
consumer measurements and hashes below refer to their identified completed runs.

## Established application and historical gates

All seven installed-wheel scenarios passed diagnosis, reduction, default/explicit
JSON and text inspection, retained-value/schema/integrity/FK checks and three fresh
relocated replay confirmations with original paths unavailable. Source and bundle
hashes remained unchanged. The installed runtime was external site-packages.

| Scenario | Original → retained | Executions / budget |
| --- | --- | --- |
| Ordinary duplicate export | 2,430 → 5 | 54 / 400 |
| Threshold | 11 → 3 | 18 / 80 |
| Reservation overbook | 4,248 → 9 | 131 / 400 |
| Approval cycle | 1,626 → 6 | 107 / 400 |
| TEXT entitlements | 970 → 10 | 180 / 240 |
| Composite billing | 1,308 → 8 | 126 / 260 |
| Mixed WITHOUT ROWID billing | 1,308 → 8 | 126 / 260 |

These are actual observations, not engine constants. Both billing layouts exceed
the 1,200-row acceptance minimum and retain fewer than sixteen rows. Evidence is
`.validation/m2g-established-six-final.json` and
`.validation/m2g-without-rowid-final.json`.

The unchanged compatibility recipe archived actual reviewed commits, generated
genuine historical version-1 bundles and used the current reader for default/
explicit JSON/text inspection and relocated replay. All three new replay
confirmations passed per bundle; hashes and historical reports remained unchanged.

| History | Generation commit | Original → retained |
| --- | --- | --- |
| pre-M1b INTEGER | `ba40d64db748d974c36666294a1cc4500c79c25f` | 11 → 3 |
| M2a TEXT | `d60c79c07ae12666af9572ced69edc3b9523ce17` | 10 → 10 |
| M2b composite | `d70edac43c22efe3df643b821af1c51ec756a945` | 8 → 8 |

Generation archive hashes, original asset/bundle hashes and new replay outcomes
are in `.validation/m2g-historical-final.json` and the retained generated cases.
The reader/legacy runtime inputs are identical in captures 03 and 07 as described
above; historical artifacts were not rewritten to accommodate this bridge.

## Final automated gates

The locked sync with Python 3.12 passed using the owned cache. Final07 Ruff lint and
format checks passed (116 Python files); strict mypy passed natively and with
`--platform linux` (14 source files). The final complete suite on Windows /
Python 3.12.15 / locked pytest 9.1.1 passed **951 tests, 9 skips, 2 warnings in
512.29 seconds**. The skips are five unavailable symbolic-link privileges and
four POSIX-only signal/mode cases. Two existing invocation-accounting interruption
tests emitted `oracle cleanup incomplete: taskkill exit (code 1)` warnings; they
passed. The complete log is `.validation/m2g-pytest-full312-frozen07.log`.
Both final focused installed-wheel runs passed:

| Windows environment | Final bridge suite |
| --- | --- |
| Python 3.12.15 / pytest 8.3.5 | 150 passed, 3 symlink capability skips, 89.97 s |
| Python 3.14.7 / pytest 9.1.1 | 150 passed, 3 symlink capability skips, 129.36 s |

All fourteen installed module bytes match the final07 wheel/capture, and the
post-run check confirms all 128 frozen file hashes unchanged. The final wheel SHA256 is
`aa7e564baadccd78b9dda2365b392058147679d64fb927799f15426b94cb00a7`.
The final completed-prose sdist hash/content inventory is retained separately in
`.validation/m2g-distribution-final-handoff.json` to avoid a self-referential hash
inside the report packaged by that sdist.

The final diff review covered exact call matching, acknowledgement/import order,
fixture binding, parent configuration isolation, diagnostic/output bounds,
source protection and completed teardown/session checks. Demonstrated defects
were repaired and regression-tested. Established runtime modules, packaging
requirements, version and historical completion reports are unchanged. All work
remains unstaged/uncommitted on the starting HEAD for Dan's review. Local Linux,
literal POSIX use and independent human feedback remain NOT TESTED; hosted M2g
acceptance requires Dan's reviewed commit/push and its new CI results.
