# M2e implementation and validation

Work started on clean `main` at reviewed commit
`27be3d46c31f752f8944eb6e78d0f743f4edb9cd`. Accepted M2d.1 hosted evidence is
run `38623620343`; its Windows ACL-denial case was capability-skipped, separate
from local actual-denial and deterministic staging-denial evidence. Historical
completion reports are preserved. This work remains unstaged and uncommitted.

The implementation adds reduction-only `--progress` and `--events`, exact packed
candidate-cache identities, immutable model membership/per-table indexes, and a
bounded source-isolated performance/differential lab. Python >=3.12, package version
0.1.0, empty runtime dependencies, SQLite schema scope, search ordering, budgets,
confirmation counts and report/config/manifest/replay/diagnosis version 1 remain.

## Observation and cancellation

`Observation`/`Observer` provide a small typed callback with a no-op default.
Display/file logic lives outside the reducer. Events show acquisition, modeling,
three baseline confirmations, pending candidate sizes, committed search facts,
stop reason, compaction, three final confirmations, publication and final status.
Invocation observations follow coherent accounting; accepted-state observations
follow checkpoint publication. A cache hit reuses historical evidence and does
not add an execution. Unknown interrupted launches remain separate.

Events use finite UTF-8 JSONL with independent `event_version=1`, monotonic elapsed
time, consecutive sequence numbers and whitelisted aggregate fields. File acquisition
is exclusive before oracle execution, rejects existing/linked/device/protected paths,
requires an existing parent and keeps logs outside the output bundle. Record and file
bounds are 4096 bytes/16 MiB, with a reserved truncation record. The writer retains
no complete stream. Short, failed or interrupted writes permanently detach that sink;
warnings use an available channel. Only intended sink I/O/serialization failures are
handled. Interruptions, aborts and implementation errors propagate.

Search callbacks inside the reducer preserve the committed confirmed selection.
The search-stopped notification hands off to finalization; interruption there may
abort. Baseline/compaction/final-verification/publication-start interruption does
not publish incomplete evidence. Late published/completed notification interruption
can leave a fully verified, inspectable bundle, so the CLI cancellation message now
directs users to inspect any output before replay. Second accounting-recovery
interruption still aborts. See [event contract](progress-events.md).

## Cache and adapter

Stable ordinals sort the validated declared RowIds with the existing order. Every
candidate is encoded after dependency closure into exactly ceil(universe-size/8)
bytes using bytearray bit updates; leading/trailing zeros and empty/full sets have
canonical identities within that invocation. Equality compares the complete bytes
after dictionary hashing, so a hash collision cannot merge candidates. Typed INTEGER,
TEXT, full composite keys and table separation remain exact. No digest-only identity,
old frozenset-key cache, eviction, cross-run state or search heuristic was added.
UNRESOLVED remains noncacheable; baseline/final verification bypasses the cache.

The frozen model retains an immutable row-universe set and read-only per-table row
tuples. The existing three-argument constructor remains valid. Membership checks no
longer rebuild the universe and materialization traverses each table's own rows in
the original order. Bound DELETEs, pristine backups, FK-action policy, validation,
storage layout and compact-fixture confirmations remain unchanged.

The prechange observations were verified in source and measured before edits; they
were optimization hypotheses, not correctness defects. The final lab records both
savings and costs, including ordinal/index ownership, scratch allocations in the
Python peak, sparse workloads and conversion overhead. See [performance evidence](performance.md).

## Validation evidence

The source-isolated final lab passed **24 workers and nine semantic comparisons**.
It used three alternating untraced microbenchmark repetitions per side, separate
allocation runs, and separately instrumented/ordinary real runs. All requested
10k/50k/100k sizes ran. Runtime/recipe/source hashes still matched after the run.

| 100k-row observation | Archived baseline | M2e |
| --- | ---: | ---: |
| 24 dense cache entries, including ordinal index | 100,673,393 bytes | 8,341,893 bytes |
| Dense reducer peak traced Python allocations | 105,936,248 bytes | 39,022,427 bytes |
| Sparse cache plus ordinal index | 22,385 bytes | 8,341,885 bytes |
| Dense complete cache-search median | 3.4372 s | 3.8428 s |
| 50 membership checks, median | 0.7356 s | 0.0587 s |
| Validated materialization, median | 0.5158 s | 0.4635 s |

Dense cache storage fell 91.7%, including ordinal overhead. Additional adapter
indexes estimate 4,994,904 bytes at 100k rows. Sparse cache storage grew 372.7 times;
the dense complete-search median increased about 12%. Small materialization and
model-construction results also include regressions. These changes meet the
dense-storage target, not a universal memory/speed claim. Full median/range tables,
encoding/tracing overhead and measurement definitions are in [performance](performance.md).

| Larger real comparison | Source -> retained | Invocations | Accepted / cache hits | Attempts |
| --- | ---: | ---: | ---: | ---: |
| Existing duplicate export, scaled scalar fixture | 20,000 -> 5 | 87 | 25 / 25 | 81 |
| Existing billing, scaled mixed WITHOUT ROWID fixture | 20,005 -> 8 | 209 | 38 / 26 | 191 |

Both archived/new pairs matched ordered considered/evaluated identities, normalized
cache decisions, complete attempts/confirmations, acceptance chains, final identities,
stop reason and invocation accounting. Only `duration_seconds` was normalized in
reports/replay. The unchanged strict reader accepted every bundle, integrity/FKs
passed, source/assets and original/relocated bundle hashes were unchanged, and three
fresh relocated replay confirmations passed with original paths unavailable.
Three seeded nine-scenario graph comparisons also matched. Unknown launches were
zero in these ordinary measurements; separate injected tests cover uncertainty.

Ordinary baseline/new/text-progress times were 23.352/27.451/22.645 seconds scalar
and 59.184/59.106/67.368 seconds billing. These are single samples with order/cache
noise, not stable overhead estimates. Semantic recording timings are kept separate.
No competing validation worker ran during this final performance run.

Preliminary exploratory checks exposed integration races while optional observer
parameters were still being wired; those runs are not final-snapshot evidence.
The first integrated focused run then passed 81 tests and failed one compaction
boundary test: its third baseline invocation actually returned UNRESOLVED after
the new synthetic fixture's two-second deadline. Verification correctly refused
the bundle before the intended interruption. Only the new observation-workflow
fixtures now use a finite five-second deadline; all fresh-confirmation and deadline-
specific assertions remain. The preliminary clean suite result was **2 failed,
720 passed, 6 skipped, 2 existing cleanup warnings**. It also exposed a one-second
valid-bundle setup timeout in the six malformed-bundle cases; only that setup now
explicitly selects five seconds through an optional fixture parameter. Default
malformed-configuration cases and dedicated timeout classifications are unchanged.
The first clean-copy benchmark smoke also exposed a
validation-harness Git worktree/prefix error. The final harness uses the clean copy
as `GIT_WORK_TREE`, original project metadata through `GIT_DIR`, and disables optional
Git locks. No runtime repair or performance-source change was needed for these
fixture/harness issues. They remain recorded as failed preliminary checks.

The repaired final coherent gate passed **88 focused tests** in 142.81 seconds,
then **722 passed, 6 skipped, 2 warnings** in 772.31 seconds in a fresh clean
copy with a non-editable site-packages installation. The small source-isolated
benchmark smoke and all six malformed-bundle setup/rejection cases passed.
The clean copy's captured source bytes were unchanged; current runtime/test/recipe
hashes matched that snapshot after validation. Exact commands, JUnit results,
source manifests and `result.json` are under `.validation/m2e-final-checks-fresh/`.
Evidence-only documentation was completed afterward and included in final package
content inspection; runtime/test/recipe files stayed frozen.

| Gate | Actual Windows result |
| --- | --- |
| Locked synchronization using existing owned offline cache | PASS |
| Ruff lint/format, strict mypy Windows and Linux targets | PASS |
| Focused cache/observation/recipe/malformed-bundle regressions | 88 passed |
| Complete clean-copy, non-editable suite | 722 passed, 6 skipped, 2 existing warnings |
| Final performance lab | 24 workers passed, 9 semantic comparisons equal |
| Offline external standard venv/pip consumer and negative audit | PASS; 40 audit cases, one symlink capability skip |
| Seven full installed application scenarios | PASS; reference row/invocation observations retained |
| Genuine historical INTEGER/TEXT/composite source and installed readers/replays | PASS |
| Wheel/sdist build, exact runtime/metadata/source-content checks | PASS |
| Actual Linux runtime / new hosted matrix | Not run here; denied capability / Dan's later commit and push |

The six final suite skips are two unavailable symlink-creation privileges
(WinError 1314), POSIX workflow SIGINT, POSIX diagnosis SIGINT, executable-mode
semantics and POSIX signal return codes. Windows owned ACL-denial integration
ran; it was not capability-skipped locally. No blanket platform skip was added.
Both warnings are existing deterministic accounting/cleanup injections:
`test_second_interrupt_in_real_oracle_cleanup_aborts_and_preserves_launch` and
`test_returned_process_handle_establishes_known_launch_before_evidence_assignment`,
each `oracle cleanup incomplete: taskkill exit (code 1)`. Their accounting
assertions passed; the warnings do not establish completed cleanup. Windows
injected KeyboardInterrupt is distinct from real console Ctrl+C and POSIX SIGINT.

Build also emits uv's generic warning that the owned cache is inside the source
directory. Explicit package inclusion/content checks establish that no cache,
environment, generated database, sidecar, bundle, log, JSONL or profile entered
the actual distributions. Version 0.1.0, Python >=3.12, empty runtime dependencies,
MIT metadata/license and the single console entry point are unchanged. All 13
runtime module bytes are checked against the source. The final wheel is compared
with the wheel used by installed consumer/application/history validation.

## Installed consumer, established applications and history

The fresh offline standard venv/pip consumer passed, with site-packages import
origin outside the checkout, no editable import or consumer uv dependency, no
PYTHONPATH/PYTHONHOME leakage, and spaces/Unicode paths. Progress and events ran
on the genuine threshold tutorial; stdout stayed the existing JSON shape, the
70-record event stream completed with report-consistent counters, and no event
file entered the bundle. Static/executable diagnosis, default/explicit JSON and
text inspection, and three fresh relocated replay confirmations all passed with
original project/bundle paths unavailable. Temporary state was removed and wheel
bytes were unchanged.

The existing installed error audit passed 40 cases; synthetic symlink creation
was capability-skipped. Both actual owned input-read and output-create denials
were observed: exit 2, zero oracle starts, unchanged input bytes and restored owned
ACLs. This is separate local evidence, not a claim that the prior hosted Windows
actual-denial case executed. No new ACL investigation or repair scope was added.

All seven full installed-wheel scenarios reconfirmed the reference row and
invocation observations:

| Scenario | Original -> retained | Invocations / budget | Accepted / cache hits | Reduction seconds |
| --- | ---: | ---: | ---: | ---: |
| Duplicate export | 2,430 -> 5 | 54 / 400 | 13 / 11 | 11.500 |
| Threshold | 11 -> 3 | 18 / 80 | 3 / 5 | 4.375 |
| Reservations | 4,248 -> 9 | 131 / 400 | 21 / 24 | 29.719 |
| Approval cycle | 1,626 -> 6 | 107 / 400 | 22 / 25 | 25.687 |
| TEXT entitlements | 970 -> 10 | 180 / 240 | 30 / 31 | 47.906 |
| Ordinary composite billing | 1,308 -> 8 | 126 / 260 | 22 / 23 | 42.375 |
| Mixed WITHOUT ROWID billing | 1,308 -> 8 | 126 / 260 | 22 / 23 | 37.500 |

These are single correctness-gate measurements; some overlapped the final focused
test worker, so they are not isolated performance comparisons. The separate lab
above ran without competing validation. Every scenario preserved source/assets,
original/relocated bundle hashes, declared schema/storage metadata and retained
values; integrity/FK checks and three fresh final/replay confirmations passed.
Invalid candidates, unresolved attempts and unknown interrupted launches were
zero in these seven ordinary measurements.
Both full billing layouts started above 1,200 rows and retained at most 16. Small
wheel smoke fixtures were not substituted for these measurements.

Genuine historical bundles were generated from fresh archives of the original
reviewed sources. The current source reader and separately installed wheel both
performed default/explicit JSON and text inspection and three fresh relocated
replay confirmations. Supplied historical reports were not rewritten or migrated.

| History | Archived commit | Prior rows | Prior invocations | New replay |
| --- | --- | ---: | ---: | --- |
| pre-M1b INTEGER | `ba40d64db748d974c36666294a1cc4500c79c25f` | 11 -> 3 | 18 | 3 TARGET_FAILURE |
| accepted M2a TEXT | `d60c79c07ae12666af9572ced69edc3b9523ce17` | 10 -> 10 | 23 | 3 TARGET_FAILURE |
| accepted M2b composite | `d70edac43c22efe3df643b821af1c51ec756a945` | 8 -> 8 | 15 | 3 TARGET_FAILURE |

Owned evidence is under `.validation/m2e-gate-fresh/` (consumer JSON, seven
measurements and installed historical logs), the three fresh
`.validation/m2e-history-*-fresh/` trees, and the separate performance/final-check
trees. Source, original bundle and relocated bundle byte hashes remained equal
within each lifecycle; matching hashes do not authenticate historical execution.

Actual aggregate text from the installed synthetic threshold run:

```text
reproseed: model model_ready original_rows=11 retained_rows=11 max_invocations=80
reproseed: search search_stopped retained_rows=3 attempts=14 accepted_changes=3 cache_hits=5 known_executions=15 unknown_launches=0 charged_invocations=15 reason=single_row_closures_exhausted
reproseed: publication published
reproseed: run completed original_rows=11 retained_rows=3 attempts=14 accepted_changes=3 cache_hits=5 known_executions=18 unknown_launches=0 charged_invocations=18
```

The last two complete records of its 70-record diagnostic file (earlier lines
omitted here) were:

```jsonl
{"event_version":1,"sequence":69,"elapsed_seconds":4.688,"event":"published","phase":"publication"}
{"event_version":1,"sequence":70,"elapsed_seconds":4.688,"event":"completed","phase":"run","original_rows":11,"retained_rows":3,"attempts":14,"accepted_changes":3,"cache_hits":5,"known_executions":18,"unknown_launches":0,"charged_invocations":18}
```

Search charged 15 invocations; the three fresh compact confirmations brought the
completed total to 18. These lines contain no keys, row values, table names, paths,
markers or process output and remain unauthenticated diagnostic observations.

## Reproduction and remaining gate

Use the commands in AGENTS.md, [contributing](../CONTRIBUTING.md) and
[benchmarks/README.md](../benchmarks/README.md), always with fresh scratch/output
paths. The principal command families actually exercised were:

```text
uv sync --locked --python 3.12
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy --platform linux
uv run --locked pytest tests/test_compact_cache.py tests/test_observation.py tests/test_observation_workflow.py tests/test_benchmarks.py tests/test_config_artifacts.py::test_replay_rejects_invalid_bundle_before_launch --basetemp=.validation/m2e-focused-new
uv sync --locked --no-editable --python 3.12
<clean installed Python> -m pytest --basetemp=.validation/m2e-full-new
uv run --locked python benchmarks/lab.py --directory .validation/m2e-performance-new --mode all --sizes 10000 50000 100000 --repetitions 3 --candidates 24 --real-rows 20000
uv build --no-sources
uv run --locked python tests/distribution_smoke.py --wheel dist/reproseed-0.1.0-py3-none-any.whl --sdist dist/reproseed-0.1.0.tar.gz
uv run --locked python tests/external_consumer_smoke.py --wheel dist/reproseed-0.1.0-py3-none-any.whl --existing-applications --audit-errors --evidence .validation/m2e-consumer-new.json
<installed Python> tests/milestone_smoke.py --directory .validation/m2e-six-new --python <installed Python> --cli <installed console>
<installed Python> tests/milestone_smoke.py --directory .validation/m2e-without-rowid-new --python <installed Python> --cli <installed console> --examples composite_billing --without-rowid-billing-fixture
uv run --locked python tests/compatibility_smoke.py --directory .validation/m2e-pre-m1b-new --history pre-m1b
uv run --locked python tests/compatibility_smoke.py --directory .validation/m2e-m2a-new --history m2a-text
uv run --locked python tests/compatibility_smoke.py --directory .validation/m2e-m2b-new --history m2b-composite
```

Run clean-copy commands from the fresh copy, not the original checkout. Our copy
contained regular tracked/nonignored project files and initially no `.git`, `.venv`,
`dist` or `.validation`; an explicit validation parent was created. A read-only
original `GIT_DIR`, `GIT_WORK_TREE=<clean copy>` and `GIT_OPTIONAL_LOCKS=0` allowed the
small recipe to archive genuine HEAD without changing import origin. The fresh
non-editable installation's origin was asserted beneath its site-packages.

For installed full scenarios, create a fresh standard venv outside the checkout
using `python -m venv <outside-venv>` and install the absolute wheel with that
interpreter's `-m pip install --no-index --no-deps <absolute-wheel>`. Remove
PYTHONPATH/PYTHONHOME/development-venv leakage, run from an unrelated directory,
and pass that interpreter/console to milestone_smoke. The consumer recipe already
automates those installation/isolation steps for the tutorial and genuine small
key/layout cases. Installed historical bundles additionally ran default/explicit
JSON and text inspection and `replay --allow-exec` from owned relocated copies.

The actual local uv executable was `.tools/bin/uv.exe`, with
`--cache-dir .tools/uv-cache --offline`; the default cache was inaccessible, so
we used the existing owned cache rather than requesting broader access. Exact
argv, exits, durations and logs are retained in the two gate `commands.json`
files. The expanded local suite/build/consumer gate exceeded 15 minutes; that
consumer included `--audit-errors`, which CI does not run, so this is not a
prediction of a same-command hosted duration. CI now has a finite 20-minute
allowance for the expanded checks; its OS/Python
matrix, pinned actions, read-only permissions, assertions and no-retry policy
are preserved. Large benchmark runs remain outside CI.

The local Windows runtime is CPython 3.12.15, SQLite 3.53.1, Windows 10
build 19045. Docker API access and WSL enumeration were denied by this environment;
Linux runtime execution is unavailable here. A Linux mypy target is not runtime
execution. No system-service, privilege, ACL-policy or security-software change was
attempted to acquire that optional capability. Existing permission tests remain
limited to their own disposable paths.

Progress writes are synchronous and can experience OS stalls. Telemetry can be
partial and is neither a ledger nor authenticated reproduction evidence. Packed
caching is not a whole-process memory bound; sparse workloads can cost more. RSS,
native SQLite and child-process memory are outside tracemalloc measurements. No
production readiness or global minimality is claimed. Real Windows console Ctrl+C,
new hosted Ubuntu/Python 3.12/3.14 and Windows/Python 3.12 validation, independent
human feedback and Dan's distribution decision remain outstanding.

Public-alpha readiness stays **CONDITIONAL GO**. No staging, commit, push, PR, tag,
version change, package upload, release, tester contact or repository setting change
is authorized or performed. M2e hosted acceptance awaits Dan's reviewed commit/push.

## Final review and Git handoff

Review covered exact byte equality and universe isolation, unchanged search/evaluation
order, typed boundaries, invocation/checkpoint publication, unknown-launch and second-
interruption accounting, observer failure isolation, partial writes/cap/privacy,
source/bundle immutability, actual installed origins, test assertions and package
contents. Fixture deadline setup fixes and the finite CI allowance are disclosed
above. No failing assertion was removed, report reader loosened, CI retry added,
or new SQLite family, runtime dependency, plugin framework or search heuristic added.

Final branch remains `main`, HEAD
`27be3d46c31f752f8944eb6e78d0f743f4edb9cd`. All implementation, tests and documentation
are unstaged/uncommitted, with no staged files. Intended status groups are:

```text
 M .github/workflows/ci.yml
 M AGENTS.md
 M CONTRIBUTING.md
 M README.md
 M SECURITY.md
 M docs/alpha-readiness.md
 M docs/architecture.md
 M docs/getting-started.md
 M docs/roadmap.md
 M pyproject.toml
 M src/reproseed/artifacts.py
 M src/reproseed/cli.py
 M src/reproseed/reducer.py
 M src/reproseed/sqlite_adapter.py
 M src/reproseed/workflow.py
 M tests/distribution_smoke.py
 M tests/external_consumer_smoke.py
 M tests/test_cancellation_workflow.py
 M tests/test_config_artifacts.py
 M tests/test_invocation_accounting.py
?? benchmarks/
?? docs/m2e-completion.md
?? docs/performance.md
?? docs/progress-events.md
?? src/reproseed/observation.py
?? tests/test_benchmarks.py
?? tests/test_compact_cache.py
?? tests/test_observation.py
?? tests/test_observation_workflow.py
```

Historical completion reports, application generators/oracles, report/config/diagnosis
formats, oracle orchestration, package version and lockfile are preserved. Generated
state remains ignored. Dan can review this tree, then make the separate commit/push
and distribution decision; agent validation does not satisfy independent user feedback.
