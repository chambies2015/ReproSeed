# M2f generated correctness, exact caching and automated readiness

Local work date: 2026-10-16, America/Chicago. Publication is not authorized.
This report records bounded synthetic engineering evidence, not a human study,
production-readiness proof or claim of global minimality.

## Source and ownership

Started clean on `main`, HEAD `0b776c8f5002c846940e438207d582af2259bda6`,
the accepted M2e source (hosted run `38901295778`, supplied acceptance reference).
There were no preexisting working-tree changes. No staging, commit, push, Git reset,
PR, tag, release, package upload, tester contact or service change was performed.
Version remains `0.1.0`; runtime dependencies remain empty. Historical completion
reports and historical bundles were not edited.

Runtime integration had one owner; generated verification, disposable mutation checks
and lab extensions were implemented on disjoint files. The initial capture and a second
review capture were followed by final `.validation/m2f-frozen-source-03`. The canonical SHA256
of the 90 executable-validation inputs (runtime, tests, benchmarks, examples, CI,
pyproject and lockfile) is:

`1f52a74f8b571ca601a342339b0e9bc708329edff8b2dd418dfbc7cb8780ab01`

`.validation/m2f-source-freeze-03.json` contains every file hash. Completion/performance evidence
prose is completed after execution and is outside that aggregate. The benchmark
README is included and remains frozen. Final hash checks confirm those 90 input files
remain unchanged; documentation is rebuilt and content-checked separately. Git HEAD alone
does not identify this uncommitted implementation.

Static review after the initial capture tightened POSIX mutation replay quoting and
raw-model input publication before constructor failures, exact LF/CRLF preservation
in disposable substitutions, and a real lazy-map interruption lifecycle. Their recipe/test fixes are
in the final capture. The completed performance job used the initial immutable capture;
its selected runtime, example, lab and worker bytes are identical to the final capture.
It does not execute the changed generated/mutation recipes. Final nonperformance
gates use the final capture or byte-checked installed runtime.

Actual pre-M2e and accepted-M2e archives were sampled before runtime edits at 64 rows,
24 candidates, one ordinary timing repetition and separate traced samples. All eight
workers passed across the two prechange recipes. Evidence remains in
`.validation/m2f-prechange-pre-m2e-sample` and
`.validation/m2f-prechange-accepted-m2e-sample`. Archive SHA256 values:

| Implementation | Commit | Archive SHA256 |
| --- | --- | --- |
| Pre-M2e | `27be3d46c31f752f8944eb6e78d0f743f4edb9cd` | `0ea76d59e8f8dc3aa0d9de7defe119eb597204ff50c49bfe57ed3c27556c926a` |
| Accepted M2e | `0b776c8f5002c846940e438207d582af2259bda6` | `2d58a7ad873735556745a7bb6e3c607d944f9e22653d37ffb1992421f50fec13` |

Final large jobs use a newly owned local temporary root recorded in
`.validation/m2f-local-roots.json`, retained because saved replay commands reference
its captured sources. Results are also copied under ignored `.validation`. Network
share I/O affected development campaign duration; it is not silently treated as CPU
work. Final performance measurements run without concurrent validation workers.

## Runtime policy and exactness

`reducer.py` uses one cache with a fixed cardinality rule: at most 32 retained rows
use an immutable exact frozenset; larger selections use fixed-width packed membership.
The encoder borrows the model's existing rows tuple and immutable `row_universe`
property. Protocol callers without the membership property use tuple membership for
small keys. No second cache, digest identity, eviction or extra O(N) sparse membership
structure was added. Constructor shape validation is one O(N) scan, included in CPU
measurements. A dense encoding builds its ordinal dictionary privately and publishes
one completed reference. The index remains live if later candidates become sparse.
Direct non-tuple iterable inputs are materialized into an owned tuple; the measured
production path borrows an already-live model tuple, so it does not extend that lifetime.

Equal candidates have equal cardinality, choose the same form and compare equal.
Sparse equality compares complete declared identities; dense equality compares one
bit per deterministic identity. The two key types are disjoint, so a boundary crossing
cannot alias another form. Hash collisions still resolve through exact equality.
Table names, INTEGER versus TEXT, full composite tuples, empty/full selections and
leading/trailing-zero bits remain distinct and canonical. Encoding remains after
deletion closure. PASS/DATABASE_INVALID caching, UNRESOLVED noncaching, ordering,
budgets, committed search publication and final cache bypass are unchanged.

Review found and fixed an internal protocol edge case: an unsupported boolean/float
universe key could alias a valid integer candidate under Python equality. DatabaseModel
never produces those identities, so this was not a demonstrated SQLite-path defect.
Constructor and candidate checks now reject them. Tests exercise foreign identities,
all tiny subsets, threshold/history/iteration invariance, forced hash collisions,
borrowed membership and interrupted lazy construction. No source schema capability,
report/config/manifest/diagnosis/event version or public tuning flag changed.

## Generated campaign

The developer recipe uses independently authored structured schemas, parent-left
full-key SQLite joins and a separate fixed-point reference traversal. Expected edges
never come from the adapter's private graph or closure implementation. Each case
retains generator version 1, seed, ordinal, template, verification configuration,
input/config hashes, implementation origin/hash and exact replay argv. Model inputs
are written before executing the implementation, so an assertion cannot erase the
authored counterexample. Failures are retained without retries. The retained-artifact option is a stop
threshold checked between bounded workers and can overshoot by one finite batch plus
aggregate JSON growth; separate case/fixture/log/result limits keep retained work finite.
It is not a strict filesystem or process-memory maximum.

The matrix covers scalar INTEGER/TEXT and all four two-component families, ordinary
and STRICT rowid/WITHOUT ROWID templates, empty/unrelated tables, negative/sparse
integers, empty/quoted/Unicode keys, K/K identifiers, chains, separate FK groups,
shared descendants, self-links/cycles, explicit/implicit complete targets and partial
NULL references. Secondary indexes and FK actions are preserved without rewriting
retained values. Exact identities, values, schema/index/storage metadata, integrity,
FK checks and source hashes are checked on real materializations.

For representative universes of eight rows, all 256 seed subsets are enumerated.
Valid retained subsets are enumerated independently; only a separately bounded
sample is materialized. Model search predicates are synthetic and do not count as
application executions. Real lifecycle cases use the genuine billing app/oracle in
both layouts, insertion reversal, disconnected rows and bijective key/reference
renaming. Correcting its refund-sign bug must produce PASS. Transformed cases check
validity and target preservation, without requiring an identical minimal fixture.

Accepted M2e and new code run in isolated interpreters with the same generated inputs
and exact captured application assets. Ordered considered/evaluated identities,
attempts/cache decisions, acceptance chains, final identities, stop reasons and
accounting compare exactly; only `duration_seconds` is normalized. Historical
agreement is supplementary to the independent SQL/reference checks.

Frozen Python 3.12 smoke passed 82/82 implementation-case executions and all 41
comparisons. Per implementation it recorded 12,617 closure checks, 2,048 exhaustive
seed subsets, 704 valid retained subsets, 34 materializations, 152 encoding checks,
21 in-process CLI calls and 20 observed oracle subprocesses plus one generator.

Frozen Python 3.12 extended passed 2,432/2,432 implementation-case executions and
all 1,216 exact comparisons: per side 128 supported fixtures, 64 rejection variants,
1,000 models and 24 real lifecycles. Failed, timed-out and skipped cases were all zero.
Both sides recorded the same actual work:

| Work per implementation | Extended count |
| --- | ---: |
| Closure checks | 88,675 |
| Exhaustively enumerated seed subsets | 9,988 |
| Independently valid retained subsets | 3,436 |
| Actual materializations | 772 |
| Exact encoding checks | 2,432 |
| In-process CLI entry calls | 240 |
| Observed oracle subprocesses | 674 |
| Generator subprocesses | 24 |

The last two rows total 698 application subprocesses per side; verification-worker
and provenance orchestration launches are separate. The 128-fixture matrix per side was:

| Declared key | Rowid | STRICT rowid | WITHOUT ROWID | STRICT WITHOUT ROWID |
| --- | ---: | ---: | ---: | ---: |
| INTEGER | 6 | 6 | 5 | 5 |
| TEXT | 6 | 6 | 5 | 5 |
| INTEGER/INTEGER | 6 | 5 | 5 | 5 |
| INTEGER/TEXT | 6 | 5 | 5 | 5 |
| TEXT/INTEGER | 6 | 5 | 5 | 5 |
| TEXT/TEXT | 6 | 5 | 5 | 5 |

Per side, SQLite rejected four wrong-arity DDL cases. ReproSeed rejected 60 valid
SQLite variants: four each of alternate target, arity, collation, descending key,
FK storage/type, generated column, invalid FK, key storage/type, NULL key,
partial-NULL storage, partial target, trigger and virtual table. All applicable
rejection cases checked both diagnose and reduce: no oracle launch and no bundle.

All four transformations in both billing layouts passed at each noise level 0/1/2,
covering 24 conditions per implementation. Every case preserved the target, passed
strict inspection and three fresh final/relocated-replay confirmations, and classified
the corrected refund-sign implementation as PASS. The full case matrix, template IDs,
actual per-case execution counts and raw replay commands remain in the retained results
and `.validation/m2f-gate-evidence/campaign-extended-312-detailed-summary.{md,json}`.
Final retained extended files total 491,417,280 bytes (468.65 MiB), below the 512 MiB
stop threshold. No partition, retry or skipped remainder was needed. Smoke and extended
share seed 104729; their overlapping ordinals are not additional unique generated cases.

Python 3.14 smoke also passed all 82 executions and 41 comparisons, with the
same per-side counters as Python 3.12. Its SQLite version is 3.50.4.

Python 3.14 extended passed all 2,432 implementation-case executions and 1,216
comparisons, with zero failures, timeouts or skips. Its actual case counts, every
work counter above, 24-cell key/layout matrix, rejection variants/classifications
and all 24 lifecycle rows match Python 3.12 on both implementation sides. Its
retained files total 491,899,313 bytes (469.11 MiB), below the same stop threshold.
The separate detailed summary is
`.validation/m2f-gate-evidence/campaign-extended-314-detailed-summary.{md,json}`.


## Mutation sensitivity and faults

Ten finite exact-once substitutions are applied only to disposable source copies.
Substitution preserves every other byte, including LF/CRLF line endings. POSIX replay
uses shlex quoting, Windows uses its native argument convention, and raw argv is saved.
Each control and mutant runs the same targeted semantic probe in an isolated process.
Trace evidence must show the changed production line executed; a clean control must
pass. Syntax/import/setup errors are invalid mutants and unknown timeouts unresolved,
not semantic detections. Every denominator row is preserved in `mutations.json`.

| Mutant | Boundary / expected violated invariant |
| --- | --- |
| cache_row_count | Equal-sized distinct candidates require distinct evidence. |
| composite_component_lost | Dependencies use the complete ordered parent PK. |
| descendant_edge_dropped | Retained dependent descendants are removed transitively. |
| partial_null_required | Any NULL child component creates no required parent edge. |
| oracle_state_reused | Oracle mutation never becomes source/next-invocation state. |
| exit_without_marker | Expected exit requires the configured exact stream marker. |
| final_only_two | Compact fixture needs three fresh confirmations. |
| accepted_confirmation_reused | Accepted candidate needs two actual charged executions. |
| reader_charges_cached_evidence | Reused evidence does not charge another execution. |
| reader_forged_count_chain | Attempt totals agree with committed accepted counts. |

The frozen Python 3.12 and 3.14 runs each detected all ten mutants. Every clean
control passed, every changed production boundary was traced, and every mutant
failed its targeted semantic assertion. There were zero survivors, invalid mutants
or timeouts on either runtime. Each process had a 60-second deadline. Original and
captured clean source hashes remained unchanged on both runs. The table below
records the actual individual results; full changed-line/hash, test name, trace,
assertion, duration and replay argv remain in each `mutations.json`.

| Mutant / targeted probe in `tests/test_m2f_faults.py` | Python 3.12 | Python 3.14 | Actual failed assertion |
| --- | --- | --- | --- |
| `cache_row_count` / `test_cache_requires_exact_membership` | detected | detected | equal-size candidates need distinct exact evidence |
| `composite_component_lost` / `test_composite_relationship_uses_entire_key` | detected | detected | complete tenant/item identity must remove its child and preserve partial matches |
| `descendant_edge_dropped` / `test_closure_includes_transitive_descendants` | detected | detected | required descendants must be removed transitively; unrelated descendants survive |
| `partial_null_required` / `test_partial_null_relationship_is_optional` | detected | detected | valid partial-NULL SQLite references must remain supported |
| `oracle_state_reused` / `test_each_oracle_invocation_uses_pristine_state` | detected | detected | an oracle's DELETE must not become the next invocation's initial state |
| `exit_without_marker` / `test_expected_exit_without_marker_is_unresolved` | detected | detected | matching exit alone must never establish the target |
| `final_only_two` / `test_final_verification_uses_three_fresh_executions` | detected | detected | compact fixture needs three fresh confirmations |
| `accepted_confirmation_reused` / `test_accepted_reduction_has_two_charged_executions` | detected | detected | each accepted pair needs two fresh charged executions, beyond baseline/final verification |
| `reader_charges_cached_evidence` / `test_reader_does_not_charge_cached_confirmation_again` | detected | detected | cached historical PASS evidence is not a new execution |
| `reader_forged_count_chain` / `test_reader_rejects_forged_count_chain` | detected | detected | reader must reject a forged count chain even when confirmation records agree |

This finite sample establishes sensitivity to these ten deliberate defects only.
It is not exhaustive mutation coverage or evidence that all faults are detected.


Existing deterministic injection coverage remains for completed evaluation before
checkpoint publication, committed acceptance, first/second confirmations, known and
unknown invocation charges, further-interruption aborts, compaction/finalization and
publication. New cases cover sparse/packed initialization and private snapshot/output
failure. Existing event tests cover short/disk-full writes, broken progress, exclusive
creation and caps. Strict-reader tests include rehashed semantic corruption, separate
from manifest mismatch. A late interruption after completed publication may leave a
valid inspectable bundle; that is not classified as corruption. Telemetry remains
diagnostic and cannot supply execution evidence or replay authority.

In particular, `test_interrupted_private_lazy_map_publishes_a_strict_replayable_bundle`
interrupts private ordinal filling at ordinal 9 on 80 real SQLite rows. After one
completed empty-candidate PASS, the map remains unpublished, all 80 confirmed rows
remain, the report records one attempt and seven actual workflow invocations,
and strict inspection plus three fresh relocated replay confirmations pass.
`test_materialization_interruption_cleans_private_output_and_preserves_source` and
`test_snapshot_output_failure_preserves_existing_private_path` cover private-file
failures. Both full suites executed these cases; none of this deterministic injection
is labeled a real signal test.

## Measurements

All 35 main workers passed and all 16 semantic comparisons matched; nine separate
actual process-CPU workers also passed. Measurements used 10k/50k/100k rows, 24
candidates and three untraced alternating repetitions. Separate traced workers cover
nine densities/history shapes, construction, conversion scratch and search peaks.
All 18 archive/current/runtime/example/harness byte-equivalence checks matched.
Full medians/ranges, all nine shapes, source hashes and executed commands are in the
[M2f performance appendix](performance.md#m2f-current-evidence).

| 100k workload | Pre-M2e incremental bytes | M2e incremental bytes | M2f incremental bytes | M2f including model indexes |
| --- | ---: | ---: | ---: | ---: |
| Dense | 100,674,658 | 8,342,998 | 8,343,021 | 13,337,925 |
| Sparse, 16 retained | 23,650 | 8,342,998 | 23,953 | 5,018,857 |
| Mixed | 4,197,031 | 8,074,682 | 8,051,095 | 13,045,999 |
| Dense to sparse | 5,599,740 | 8,240,776 | 8,182,286 | 13,177,190 |

M2e/M2f have another 4,994,904 bytes of existing model membership/partition indexes;
pre-M2e does not. These are added once in the last column. Existing core row objects
and the 800,040-byte shared rows tuple remain separately excluded, with unchanged
production lifetime. Encoder-reachable accounting overlaps these shared objects and
must not be added to the combined total. Dense saving is 91.71% incremental or 86.75%
including added model indexes versus pre-M2e. Sparse-only saving is 99.71% incremental
or 62.37% including existing model indexes versus M2e. Both sparse totals exceed
pre-M2e; mixed/shrinking runs retain their ordinal map and also exceed pre-M2e here.

| 100k workload | Pre-M2e CPU seconds | M2e CPU seconds | M2f CPU seconds | New versus M2e |
| --- | --- | --- | --- | --- |
| Dense | 3.8125 [3.4063, 3.8438] | 4.6250 [4.5625, 4.7656] | 6.2344 [6.1406, 6.5313] | +34.8% |
| Sparse | 3.0313 [2.8438, 3.0938] | 3.1094 [3.0313, 3.1563] | 3.2031 [2.7813, 3.2969] | +3.0% |
| Mixed | 2.8438 [2.6094, 3.2344] | 3.5156 [3.4063, 3.8281] | 4.3594 [3.9219, 4.5469] | +24.0% |

These are median [minimum, maximum], three separate process-time repetitions,
including the production constructor scan and search, excluding input/model prep.
Separate elapsed medians pre/M2e/new were dense 6.3700/7.0731/8.6368 seconds,
sparse 6.6969/4.1750/4.3003 and mixed 4.5601/4.9028/6.3892. Repeated-dense elapsed
regressed 46.1% versus M2e. No general speed improvement is established.

Lazy initialization moves the 26.64 MB ordinal-construction trace peak into the first
packed conversion; it does not eliminate it. Sparse search peak fell from 39,023,260
to 30,809,685 bytes, while shrinking search peak rose from 33,831,716 to 35,235,360.
Sparse peak savings are therefore much smaller than persistent cache savings.

Scaled genuine duplicate export reduced 20,000 to 5 using 87/400 workflow executions;
mixed WITHOUT ROWID billing reduced 20,005 to 8 using 209/260. Seven workers per domain
(all three instrumented implementations, three ordinary and one new progress run)
passed strict inspection, integrity/FKs, source/bundle hashes and three fresh final and
relocated replay confirmations. Reports/candidates/accounting matched exactly.
Ordinary pre/M2e/new elapsed seconds were 24.6709/27.6598/29.3680 and
72.6625/71.6931/68.5383 respectively. Progress samples were 24.5835/68.7861.
These are one sample per condition, with progress last; no stable macro speed or
progress-overhead ratio follows.

Historical [M2e measurements](performance.md) are preserved. Current samples are
separately labeled. Cache-owned bytes include incremental keys/results/encoder and
ordinal integers; existing model membership/partition indexes are reported separately
and combined once. Shared references and their existing lifetime are explicit. Traced
initialization, per-encoding scratch, complete-search peak and untraced repeated CPU
timings are separate. Tracemalloc is Python allocation evidence, not RSS, native SQLite,
filesystem cache or child memory. No hardware-sensitive ratio is a CI assertion.

## Product, package and platform gates

The installed product gate passed using a fresh standard `venv` and offline
`pip install --no-index --no-deps` outside the checkout. Python was CPython
3.12.15, SQLite 3.53.1, on Windows 10 build 19045. The imported package came from
`C:/Users/xeonc/AppData/Local/Temp/reproseed-m2f-dxpq6lf3/product/venv/Lib/site-packages/reproseed`.
Every installed runtime Python file matched frozen source 03. `PYTHONPATH`,
`PYTHONHOME`, and `VIRTUAL_ENV` were removed from child environments; the installed
interpreter's import path contained no source-checkout directory.

| Application | Original rows | Retained rows | Reduction executions / budget | Cache hits | Accepted changes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Duplicate export | 2,430 | 5 | 54 / 400 | 11 | 13 |
| Threshold | 11 | 3 | 18 / 80 | 5 | 3 |
| Reservations | 4,248 | 9 | 131 / 400 | 24 | 21 |
| Approvals | 1,626 | 6 | 107 / 400 | 25 | 22 |
| TEXT entitlements | 970 | 10 | 180 / 240 | 31 | 30 |
| Ordinary composite billing | 1,308 | 8 | 126 / 260 | 23 | 22 |
| Mixed WITHOUT ROWID billing | 1,308 | 8 | 126 / 260 | 23 | 22 |

Charged invocations equaled known reduction executions in all seven cases; unknown
interrupted launches, unresolved attempts, and invalid candidates were all zero.
The unchanged milestone recipe checked retained values, schema/index/storage
metadata, integrity and foreign keys, and complete original-source and bundle
hashes. Each case passed static diagnosis, three executed diagnosis confirmations,
default/explicit JSON/text inspection, three fresh final confirmations, and three
fresh relocated replay confirmations with the original example and bundle paths
unavailable. Both billing cases used the full generator and exceeded 1,200 rows;
neither used the small wheel-smoke fixture. Acceptance chains and per-attempt cache
evidence are preserved separately in `application-chains.json` and the unchanged
original bundle reports.

| Genuine history | Reviewed generating commit | Historical reduction | Old reduction executions | Current source reader | Installed inspection and relocated replay |
| --- | --- | ---: | ---: | --- | --- |
| pre-M1b INTEGER | `ba40d64db748d974c36666294a1cc4500c79c25f` | 11 to 3 rows | 18 | Default JSON, explicit JSON, text; fresh replay 3/3 | Default JSON, explicit JSON, text; fresh replay 3/3 |
| M2a TEXT | `d60c79c07ae12666af9572ced69edc3b9523ce17` | 10 to 10 rows | 23 | Default JSON, explicit JSON, text; fresh replay 3/3 | Default JSON, explicit JSON, text; fresh replay 3/3 |
| M2b composite | `d70edac43c22efe3df643b821af1c51ec756a945` | 8 to 8 rows | 15 | Default JSON, explicit JSON, text; fresh replay 3/3 | Default JSON, explicit JSON, text; fresh replay 3/3 |

Historical bundles were generated from actual local Git archives with their genuine
generators. The TEXT and composite histories used their established small
compatibility generators. The current-source validation and additional installed
console validation each executed a separate fresh replay triple. Complete source,
original bundle, copied bundle, and relocated bundle hashes remained unchanged.
Original historical example/bundle paths and the supplied copied-bundle path were
unavailable during the additional installed relocated replays. Git access used
the original read-only object store with the frozen working tree and optional
locking disabled; no historical artifact was edited.

All 24 outer setup/recipe commands exited zero. The 107 recorded nested recipe
commands contain 100 zero exits and seven intentionally invoked application-target
exits: 42, 43, 44, 45, 46, 47, and 47. The unchanged recipe explicitly checked the
configured exact marker/stream and exit for those seven independent baseline
oracles; these are expected outcomes, not failed validation commands. These command
counts describe the recorded recipe layers, not every descendant OS process.
There were no recorded skips, timeouts, unexpected exits, or retries in this product
gate. Every outer and nested stderr output was empty. Correctness work ran
concurrently elsewhere, so product wall times are not isolated performance evidence.

Frozen executable-source SHA256:
`1f52a74f8b571ca601a342339b0e9bc708329edff8b2dd418dfbc7cb8780ab01`.
The concrete early product wheel was
`C:/Users/xeonc/AppData/Local/Temp/reproseed-m2f-dxpq6lf3/dist-product-early/reproseed-0.1.0-py3-none-any.whl`,
SHA256 `948f338c8d27ccefa7f66024fccc52e90a4718a7cb3ed77654e3344935a1872b`.
The complete frozen source inventory and wheel bytes remained unchanged throughout.
The product gate establishes neither hosted Linux acceptance nor publication.

Retained evidence is under
`M:/Server/ReproSeed/ReproSeed/.validation/m2f-product-gates/summary.json`,
`application-chains.json`, and the adjacent numbered stdout/stderr files and
recipe `commands.json` directories. Full synthetic application outputs and copied
historical bundles remain under the exclusive external `product` directory;
genuine historical archives and original generated bundles remain under frozen
source 03's `.validation/product-historical` directory.


The frozen Python 3.12 full suite passed with **801 passed, 6 skipped, 2 warnings**
in 626.20 seconds. Locked offline sync, Ruff lint/format and strict mypy for Windows
and Linux targets passed. The six skips are two Windows symlink-privilege limits
and four POSIX signal/mode cases. The two cleanup-injection warnings report
`taskkill exit (code 1)`; they are preserved, not suppressed. The current local
Windows permission probes passed; earlier hosted ACL capability skips remain separate.

Python 3.14's complete clean-copy suite passed with **801 passed, 6 skipped,
2 warnings** in 588.73 seconds. The same two Windows symlink and four POSIX cases
were skipped, and the same two `taskkill exit (code 1)` injection warnings appeared.
The source copy lives outside the checkout and initially contained neither Git
metadata, a venv nor validation artifacts. Installed module origins/hashes were
proved before testing. Both ordinary and clean-copy wheel/sdist builds and content
inspectors passed. The early installed-product, initial and clean-copy wheels are
byte-identical: SHA256 `948f338c8d27ccefa7f66024fccc52e90a4718a7cb3ed77654e3344935a1872b`.
The inspectors confirmed version 0.1.0, empty runtime requirements, complete expected
source/package files and absence of ignored generated inputs, caches and mutants.

All 21 final gate commands completed with exit zero. The second external consumer
passed from the clean-source wheel in a fresh external standard venv/pip installation,
with no network, editable import, PYTHONPATH or PYTHONHOME leakage. Its main threshold
journey reduced 11 to 3 rows in 18 workflow invocations, emitted 70 version-1 events
across nine phases, passed default/explicit JSON and text inspection, and replayed
with three new confirmations after relocation. The separate small installed TEXT,
ordinary composite and WITHOUT ROWID smoke cases were respectively 10 to 10 rows
with 23 invocations, 8 to 8 with 15, and 8 to 8 with 15; each passed three executed
diagnosis, final and relocated-replay confirmations. These small fixtures supplement
the seven full installed application cases above.

Its negative audit recorded 40 executed checks plus one capability skip:
`asset_symlink` could not create a synthetic symlink. Wrong exit/stream/marker,
unrelated crash, bounded timeout/output, inconsistent baseline, missing launch,
missing dependency, no-acknowledgement, tampered/sidecar/traversal, exhausted search
budget and failed-final-confirmation cases produced their expected classifications,
launch counts and publication behavior. A timeout inside this deliberate oracle
test is an expected non-target result, not an orchestration timeout. Actual owned
Windows unreadable-input and unwritable-output probes both established denial;
the CLI returned 2 in 0.375 and 0.344 seconds, launched no oracle and preserved
inputs. The output case published no bundle. ACL restoration and owned temporary
cleanup were recorded successful. Raw evidence is
`.validation/m2f-external-consumer.json`; it describes a simulated first-user
journey, not a human study.



Local runtimes are Windows 10 build 19045, CPython 3.12.15 / SQLite 3.53.1 and
CPython 3.14.7 / SQLite 3.50.4. WSL enumeration returned E_ACCESSDENIED; no Linux
runtime pass is claimed. A bounded Docker server-version probe also returned
permission denied (including denied access to its configuration); no host setup was
changed. Python launcher inventory exposed 3.14 and unsupported 3.10; the locked
uv environment supplies 3.12. No available supported 3.13 runtime was found. Python 3.14's initial registry/direct-URL offline pytest
installation attempts failed because index/download metadata was absent. The already
cached six locked pure-Python tool distributions were repacked only after verifying
every RECORD file hash/size, then installed into its owned venv with pip --no-index.
Tool provenance is in `.validation/m2f-offline-tool-wheels/provenance.json`. No network
download or runtime dependency was introduced. This is a disclosed tooling recovery,
not a weakened product test or official package publication.

Deterministic KeyboardInterrupt injection on Windows is distinct from real POSIX
signals and real Windows console Ctrl+C. The latter two have no new local execution
claim here. Permission capability skips, warnings and intermediate failures must be
read alongside their actual platform evidence.

## Intermediate failures and reproducibility

- Development generated smoke 01 completed every case but its lifecycle comparison
  failed because archived LF and current CRLF application assets differed in exact
  hashes. The harness now supplies identical captured assets to both runtimes; no
  source/hash difference was normalized away. The failed evidence remains intact.
- The first final lab attempt failed during archive acquisition because the frozen
  source lived beneath ignored `.validation` and Git reported an untracked cwd. It
  ran no benchmark worker. A fresh run supplies read-only original GIT_DIR,
  GIT_WORK_TREE pointing at the frozen source and GIT_OPTIONAL_LOCKS=0.
- The protocol universe-alias defect and raw model failure-input preservation gap
  were caught during review and repaired before the executable freeze.
- An initial semantic cache probe expected every singleton in a deterministic search
  that actually considers two-row complements. That test assumption failed (one failed,
  eleven passed), was corrected to the actual considered identities, and still detects
  the row-count mutant. The first Ruff pass found four E501 lines, subsequently fixed.
- Static review found text-mode mutation editing would normalize unrelated CRLF bytes.
  Byte-level exact-once replacement and LF/CRLF regression cases repaired the recipe
  before final mutation execution; no working runtime was mutated.
- Final pre-freeze style review found one 101-character line in the new LF/CRLF
  regression. Ruff reformatted that line before capture 03; final lint/format passed.
- A read-only diff check with `core.autocrlf=false` treated CRLF as trailing whitespace.
  The normal repository-configured `git diff --check` passed; no file was rewritten
  to satisfy the artificial override. Git's LF/CRLF conversion notices are recorded.
- Build tooling warned that its owned `.tools/uv-cache` is inside the source root.
  Distribution content inspection separately checks the actual package contents.
- The final batch had no unexpected nonzero exits or orchestration timeouts. The
  full-suite skips/warnings and the external audit's separate symlink capability
  skip are listed above; deliberate negative-case exits remain expected evidence.

Use the bounded commands in [benchmarks/README](../benchmarks/README.md),
[AGENTS](../AGENTS.md) and [contributing](../CONTRIBUTING.md). Always use fresh output
paths. Saved single-case replay commands name captured sources and recipes; retain
the original synthetic counterexample even if a later reduction succeeds. Gate logs
retain exact argv, cwd, exit, duration and log hashes. No artifact is uploaded.

The exact 21-command receipts are `.validation/m2f-final-gates/commands.json`,
with adjacent immutable logs and a successful `summary.json`. Product setup and
nested commands are recorded separately under `.validation/m2f-product-gates`.
Performance commands and source origins are in the performance appendix and raw
comparison JSON. The final documentation-inclusive clean copy, build, content check,
four-wheel byte comparison, historical-report hashes, final source inventory and
Git checks are recorded by `.validation/m2f-final-package.json`. This receipt is
created after this report is saved so its recorded report and sdist hashes do not
require a self-referential report hash. Original raw artifacts remain under the
exclusive local root; `.validation/m2f-validated-results` contains byte-identical
copies of the four campaign results and two mutation summaries.

For a fresh ordinary developer reproduction, the checked-in commands include:

```powershell
uv sync --locked --python 3.12
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy --platform linux
uv run --locked pytest --basetemp=.validation/m2f-review-pytest-NEW
uv run --locked python benchmarks/campaign.py --directory .validation/m2f-review-smoke-NEW --profile smoke --seed 104729
uv run --locked python benchmarks/campaign.py --directory .validation/m2f-review-extended-NEW --profile extended --seed 104729 --worker-seconds 600
uv run --locked python benchmarks/mutations.py --directory .validation/m2f-review-mutants-NEW
uv build --no-sources --out-dir .validation/m2f-review-dist-NEW
```

Choose unused paths for every `NEW` directory; these commands are instructions,
not an assertion that those literal paths were executed. For offline reproduction,
add `--offline` with populated locked caches. Use the resulting concrete wheel/sdist
paths with `tests/distribution_smoke.py` and the wheel with
`tests/external_consumer_smoke.py --existing-applications --audit-errors`.
Run the campaign with each available supported interpreter. Per-case results save
the exact isolated replay command against retained input/source files. The CI smoke's
explicit `--baseline-ref HEAD` permits shallow checkout mechanics; it does not claim
a second accepted historical comparator. Local extended runs used accepted M2e.

## Readiness and handoff

Human usability is **NOT TESTED/advisory**. Under Dan's updated direction it is not a
development, technical-acceptance or limited-alpha recommendation prerequisite.
Automated checks establish only their tested invariants and bounded scope. Actual
hosted Ubuntu/Python 3.12, Ubuntu/Python 3.14 and Windows/Python 3.12 results on Dan's
reviewed M2f commit remain a technical gate; this uncommitted tree cannot establish it.
Critical defects and package/replay correctness remain gates. Publication/distribution
requires Dan's separate explicit decision.

Local engineering verdict: **PASS within the tested scope; CONDITIONAL GO for
limited alpha pending the new hosted matrix**. No demonstrated unresolved critical
correctness defect remains from this work. The cache reaches both incremental memory
targets with exact identities; the disclosed CPU, mixed-cache and peak-allocation
regressions constrain the improvement claim. Generated SQL/reference checks,
old/new differential checks, all ten selected mutants, real application chains,
historical readers and offline installed consumers support this bounded verdict.

Final diff review covered canonical identity, borrowed fixed structures/lifetimes,
independent expected answers, retained failure inputs, exclusive owned outputs,
cleanup, unchanged reader/confirmation semantics and CI scope. Changes comprise
17 modified tracked files and eight intended new source/document files; generated
databases, disposable mutants, archives, packages and logs remain ignored. Main and
HEAD remain `0b776c8f5002c846940e438207d582af2259bda6`, with an empty index and
all M2f changes unstaged/uncommitted for Dan. The executable freeze is unchanged;
the final package receipt verifies all 117 project files during its clean build and
preserves historical completion hashes and historical performance text. No package
version, publication or external contact was authorized or performed.
