# Performance observations

M2e meets the dense-cache storage target in this run. At 100,000 rows and 24 dense
candidates, actual cache-owned storage including the ordinal index fell **91.7%**,
from 100,673,393 to 8,341,893 bytes. This trades memory for encoding CPU work:
complete cache-search time increased in the dense case, sparse cache storage increased,
and real end-to-end samples show substantial host/order noise. No general speedup or
whole-process memory limit is claimed.

## Reproduction and provenance

Measured on 2026-10-15 (America/Chicago), using Windows 10 build 19045, CPython
3.12.15 (64-bit, MSC v.1944) and SQLite 3.53.1. Root validation workers were stopped
during the final lab. Ordinary desktop/OS/antivirus and storage activity were not
measured or controlled. Docker and WSL execution were denied on this host; these are
Windows measurements. No Linux performance result is claimed.

```sh
uv run --locked python benchmarks/lab.py --directory .validation/m2e-performance-fresh --mode all --sizes 10000 50000 100000 --repetitions 3 --candidates 24 --real-rows 20000
```

The local invocation used `.venv/Scripts/python.exe -I` with the same arguments and
new output `.validation/m2e-performance-final-fresh`. See
[the recipe](../benchmarks/README.md) for bounded modes, small CI smoke, tracing and
optional separate profiling. All 24 final worker samples passed, all nine semantic
comparisons were equal, and no requested size was omitted. Raw samples, failed-sample
fields and per-file source hashes are retained in ignored `comparison.json`.

Baseline was an actual immutable `git archive` of reviewed M2d.1 commit
`27be3d46c31f752f8944eb6e78d0f743f4edb9cd`, captured before optimized paths changed.
Its archive SHA256 is
`0ea76d59e8f8dc3aa0d9de7defe119eb597204ff50c49bfe57ed3c27556c926a`.
Before implementation, the archive also produced the initial 10k/50k/100k measurements
and an ordinary threshold reduction: 11 to three rows, 18 invocations, 4.935 seconds.
The initial samples were single observations; the tables below use the final alternating
three-sample timing run.

New source was copied from the frozen uncommitted M2e tree; its Git HEAD is still the
baseline commit and does not identify its uncommitted content. The SHA256 of the
canonical JSON mapping of captured `src/` and `examples/` paths to file hashes is
`7295287a054e82ed6d3f0d0ac2db7e55882e638170b67c2d5a7f94a36a97280a`.
Workers run in separate `-I` interpreters, insert only the selected source root, assert
reducer/adapter import origins beneath that root, and record actual imported-file hashes.
The recipe/worker SHA256 values are also recorded. Historical and new code are never
loaded into one interpreter.

| Imported file | Archived baseline SHA256 | New SHA256 |
| --- | --- | --- |
| `reproseed.reducer` | `c934e8b268960b05a3d67e8be072941aca823d9bce75c15ee053739efae76ed8` | `761c71afc0c9eb27d806711e78dd7fb31510390afb599cc32a1830956cfe3343` |
| `reproseed.sqlite_adapter` | `91addb9db5d281981bcefd38b88b778e4fc29a5d409ab76700428033af40c35d` | `58d15d201c7bbe136013431bab8372745c7bc5305f6f8351d2f2cecb58ffce77` |

## Cache storage and allocations

The production reducer is inspected at return, after closure normalization and actual
cache insertion/hit decisions. Shared pre-existing row identities are excluded from
cache-owned storage; dictionary/key/result metadata, the encoder and ordinal integers
are included. Dense candidates omit 16 rows. Sparse candidates retain 16. Repeated
workloads have eight distinct dense candidates visited three times, producing eight
evaluations and 16 cache hits; distinct workloads produce 24 evaluations and no hits.

| Rows | Dense baseline cache bytes | New cache bytes | New ordinal index bytes | New total bytes | Lower storage |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 12,593,393 | 36,089 | 568,268 | 604,357 | 95.2% |
| 50,000 | 50,341,745 | 155,705 | 4,014,780 | 4,170,485 | 91.7% |
| 100,000 | 100,673,393 | 305,705 | 8,036,188 | 8,341,893 | 91.7% |

| Rows | Workload | Baseline cache bytes | New cache plus index bytes | Change |
| ---: | --- | ---: | ---: | --- |
| 10,000 | sparse | 22,385 | 603,965 | 27.0× larger |
| 10,000 | repeated | 4,197,825 | 580,309 | 86.2% lower |
| 50,000 | sparse | 22,385 | 4,170,477 | 186.3× larger |
| 50,000 | repeated | 16,780,737 | 4,066,821 | 75.8% lower |
| 100,000 | sparse | 22,385 | 8,341,885 | 372.7× larger |
| 100,000 | repeated | 33,557,953 | 8,138,229 | 75.7% lower |

The sparse result is unfavorable: a fixed universe index and fixed-width key do not
pay for themselves with only 24 tiny selections. The implementation is justified by
exactness and substantially smaller dense retained-candidate caches, rather than a claim
that every candidate distribution uses less memory. Cache eviction, adaptive policy,
persistent reuse and a hard memory cap remain outside this milestone.

| 100,000-row workload | Baseline peak traced bytes | New peak traced bytes |
| --- | ---: | ---: |
| dense | 105,936,248 | 39,022,427 |
| sparse | 30,808,636 | 39,022,411 |
| repeated | 64,353,708 | 38,946,309 |

Tracing starts after shared input identities are built and includes reducer/encoder
scratch allocations. Peaks are captured before recursive storage inspection so that
its temporary visited-set allocations do not inflate the peak. Peak scratch is not
separately attributed to the encoder. Tracemalloc tracks Python allocation blocks,
not RSS, native SQLite memory, filesystem cache or oracle-child memory; see the
[Python tracemalloc documentation](https://docs.python.org/3.12/library/tracemalloc.html).
At 100k dense rows, allocation-observation runs took 14.414 seconds baseline and 14.508
seconds new, versus untraced medians 3.437 and 3.843 seconds. Those slower samples
include tracing and storage inspection and are not used for speed claims.

## Untraced cache and adapter timings

All following micro times are seconds, shown as **median [minimum, maximum]**, with
exactly three finite samples per side and alternating run order. Timing and traced
allocation samples use separate processes. No phase totals are summed.

| Rows | Cache workload | Baseline complete search | New complete search |
| ---: | --- | ---: | ---: |
| 10,000 | dense | 0.1261 [0.1222, 0.1469] | 0.1914 [0.1836, 0.4371] |
| 10,000 | sparse | 0.1478 [0.1358, 0.1783] | 0.2068 [0.1365, 0.2570] |
| 10,000 | repeated | 0.1622 [0.1228, 0.1640] | 0.2751 [0.1814, 1.0057] |
| 50,000 | dense | 1.2693 [1.1299, 1.3668] | 2.0351 [1.8648, 2.1071] |
| 50,000 | sparse | 1.1155 [1.0899, 1.4133] | 1.1539 [0.9967, 1.2348] |
| 50,000 | repeated | 1.1701 [1.0918, 1.5610] | 1.7791 [1.3645, 1.9189] |
| 100,000 | dense | 3.4372 [2.7519, 3.6040] | 3.8428 [3.8290, 4.4100] |
| 100,000 | sparse | 3.3482 [2.5551, 3.4092] | 3.0126 [2.8418, 3.4674] |
| 100,000 | repeated | 4.4970 [3.6678, 6.8415] | 4.4558 [4.1056, 4.9102] |

The 100k dense search median increased about 12%; the sparse/repeated whole-search
results were mixed and have overlapping ranges. Additional packed encoding work is
a measured CPU tradeoff for the resident-cache reduction. The new production encoder
alone took the following time to encode 24 already-built candidates at 100k rows:

| Workload | New encoding seconds |
| --- | ---: |
| dense | 1.4544 [1.4225, 1.5456] |
| sparse | 0.0001 [0.0001, 0.0002] |
| repeated | 1.3773 [1.3588, 1.6945] |

The archived reducer directly uses the existing frozenset, so it has no corresponding
packed-conversion call. Raw baseline conversion-loop numbers include release of the
previous full-set reference during assignment and exclude hashing; they are deliberately
not used for a conversion speed ratio. Complete production-search timings above include
actual normalized cache work for each implementation.

| Rows | Adapter phase | Baseline seconds | New seconds |
| ---: | --- | ---: | ---: |
| 10,000 | Model construction | 0.0394 [0.0368, 0.0411] | 0.0422 [0.0398, 0.1072] |
| 10,000 | 50 membership checks | 0.0252 [0.0243, 0.0369] | 0.0053 [0.0045, 0.0100] |
| 10,000 | 50 leaf closures | 0.0506 [0.0461, 0.0713] | 0.0096 [0.0086, 0.0473] |
| 10,000 | 50 parent closures | 0.0836 [0.0491, 0.0858] | 0.0090 [0.0089, 0.0241] |
| 10,000 | Validated materialization | 0.2300 [0.2085, 0.2736] | 0.2602 [0.2304, 0.2877] |
| 50,000 | Model construction | 0.1710 [0.1590, 0.1822] | 0.1518 [0.1504, 0.1687] |
| 50,000 | 50 membership checks | 0.4248 [0.4056, 0.4507] | 0.0253 [0.0238, 0.0282] |
| 50,000 | 50 leaf closures | 0.6081 [0.5128, 1.4139] | 0.0770 [0.0448, 0.0892] |
| 50,000 | 50 parent closures | 0.4939 [0.4473, 1.3568] | 0.0464 [0.0442, 0.0750] |
| 50,000 | Validated materialization | 0.3964 [0.3158, 0.4483] | 0.3496 [0.3243, 0.3654] |
| 100,000 | Model construction | 0.3235 [0.3149, 0.3364] | 0.3418 [0.3399, 0.3998] |
| 100,000 | 50 membership checks | 0.7356 [0.6770, 0.7928] | 0.0587 [0.0531, 0.1597] |
| 100,000 | 50 leaf closures | 1.5479 [1.5095, 1.6604] | 0.2533 [0.2349, 0.3450] |
| 100,000 | 50 parent closures | 1.5378 [1.3921, 1.7318] | 0.2617 [0.2449, 0.3641] |
| 100,000 | Validated materialization | 0.5158 [0.4850, 0.6616] | 0.4635 [0.4477, 0.5263] |

The model has four supported key/layout tables with three children per parent.
Closures use three seeds each; leaf and parent timings are distinct. Counts and
materialization still validate membership. New per-instance membership indexes remove
rebuilding the row-universe set, and table partitions preserve original per-table
deletion order while avoiding repeated whole-universe scans. At 100k rows, membership
checks and closures improved in this run; model construction was slightly slower.
Materialization improved at 50k/100k and regressed at 10k. These are workload observations
with visible noise, not hardware-independent guarantees.

| Rows | Additional adapter-index estimate bytes | Baseline model resident traced bytes | New model resident traced bytes |
| ---: | ---: | ---: | ---: |
| 10,000 | 604,888 | 3,872,656 | 4,477,360 |
| 50,000 | 2,497,752 | 18,286,960 | 20,784,528 |
| 100,000 | 4,994,904 | 36,507,584 | 41,502,360 |

The adapter estimate includes the membership frozenset, per-table tuples and references,
and a mappingproxy backing-dictionary estimate. It is separate from the ordinal index
in the cache table. At 100k rows, model-construction traced peaks were 43,234,235 bytes
baseline and 43,614,011 new. Adding both the new cache/ordinal storage and this extra
adapter-index estimate still gives about 13.34 MB versus 100.67 MB baseline dense cache
alone; shared model/retained-state/native allocations are not thereby eliminated.

## Larger real applications and differential correctness

The scalar case extends the genuine duplicate-export generator with unique safe entries.
The mixed WITHOUT ROWID billing case adds complete safe invoice/line/payment/refund
units to its genuine generator; original default fixtures and semantic oracles are
unchanged. All runs keep explicit application budgets (400 scalar, 260 billing),
five-second subprocess deadlines, three baseline/final confirmations, two confirmations
per accepted reduction and three fresh relocated replay confirmations.

| Application | Source rows | Final rows | Known/charged invocations | Unknown launches | Accepted changes | Cache hits | Attempts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Duplicate export, scalar | 20,000 | 5 | 87/87 | 0 | 25 | 25 | 81 |
| Billing, mixed WITHOUT ROWID | 20,005 | 8 | 209/209 | 0 | 38 | 26 | 191 |

Both archived/new instrumented pairs compare exact ordered considered/evaluated candidate
identities, complete attempts including normalized cache decisions, outcomes and
confirmations, acceptance chains, committed final identities, stop reasons and invocation
accounting. Entire reports and replay results compare equal after removing only
`duration_seconds`. All report structures passed the unchanged strict reader.

All three seeded graph runs (271828, 314159, 161803), nine scenarios each, also compared
equal. They cover scalar/TEXT/composite identities, cycles/self-links, empty and
irreducible selections, exhausted budgets, nonmonotonic predicates, invalid candidates
and unresolved trials. Real SQLite/materialization/subprocess paths are exercised by
every application run rather than inferred from those model/evaluator cases.

| Application | Ordinary baseline seconds | Ordinary new seconds | New with text progress seconds |
| --- | ---: | ---: | ---: |
| Duplicate export | 23.352 | 27.451 | 22.645 |
| Mixed-layout billing | 59.184 | 59.106 | 67.368 |

These ordinary runs do not record candidate identity histories. Each condition has one
sample; ordering is reversed between the two domains and progress runs occur last.
Progress-enabled samples preserve the same complete report/accounting/final identities.
Their signed differences are not stable estimates of progress overhead: filesystem
warmth and desktop noise can dominate the cost. The scalar ordinary new sample was
slower than baseline; a progress sample being faster does not imply negative overhead.

| Application | Instrumented baseline seconds | Instrumented new seconds |
| --- | ---: | ---: |
| Duplicate export | 27.127 | 23.507 |
| Mixed-layout billing | 60.213 | 59.394 |

Instrumented timings include sorting/retaining exact candidate identities, so they are
semantic-comparison evidence and are excluded from ordinary speed conclusions. Every
large run passed supported-schema/integrity/FK checks, preserved source/assets and
original/relocated bundle hashes, and replayed outside the checkout while original paths
were unavailable. All hashes and confirmations remain in the raw measurement JSON.

## Limits and remaining gate

These are bounded synthetic workloads on one Windows host. They do not describe RSS,
children/native allocations, arbitrary schemas, arbitrary candidate densities or all
hardware. Fixed-width cache keys still require a per-run ordinal index; retained sets,
sorting, closures and materialization consume additional memory. There is no eviction
or hard whole-process limit. Profiling instructions use
[cProfile](https://docs.python.org/3.12/library/profile.html) in separate runs; profiled
or traced times must not replace ordinary timings.

Large runs stay outside ordinary CI. The small recipe test checks isolated imports,
semantic equality, Unicode/space paths, import-environment contamination, output
immutability and bounded inputs without a hardware-sensitive ratio assertion.
The seven established scenarios, genuine historical bundle compatibility and package/
external-consumer validation are recorded separately in
[M2e completion evidence](m2e-completion.md). Agent measurements do not satisfy independent
human feedback. Readiness remains CONDITIONAL GO pending the new hosted gate, independent
feedback and Dan's distribution decision; no publication is authorized.


## M2f current evidence

The sections above preserve historical M2e measurements and the readiness conditions
that applied when they were recorded. Under Dan's M2f direction, human usability is
NOT TESTED/advisory and does not block engineering acceptance. Actual hosted M2f CI
and Dan's separate distribution decision remain outstanding.

## M2f three-way performance evidence

This is a new Windows observation, separate from the historical M2e measurements. The final run used Python 3.12.15 (MSC v.1944, 64-bit AMD64), SQLite 3.53.1, and Windows 10 build 19045. No project validation worker ran concurrently. OS/desktop activity remained uncontrolled; a few small read-only result/provenance inspections ran during the lab.

The lab completed **35/35 workers**, with **16/16 exact semantic comparisons**; the separate process-CPU supplement completed **9/9 workers**. No final-run sample failed, timed out, or was skipped. The 35 workers comprise nine untraced micro workers, three separate traced memory workers, nine seeded differential workers, and fourteen genuine SQLite/subprocess application workers. CPU samples are separate instrumented runs. Micro and differential workers use bounded synthetic evaluation functions; only the fourteen macro workers execute genuine application oracles.

The measured source capture has executable aggregate `e82ae1a6d0236bd3b1dc20911c9a4ea8ba6b1a3ad54e581c91086e867e501185`. All 18 byte-equivalence checks passed: archived/current source snapshots remained unchanged; measured runtime/examples match the initial frozen and final working files; lab/worker match; all CPU worker source hashes match the main comparison. Later campaign/test edits are outside these measured inputs. The final full-repository freeze is recorded separately by the completion report.

### Sources and raw evidence

| Implementation | Commit/input | Archive SHA256 |
| --- | --- | --- |
| Pre-M2e | 27be3d46c31f752f8944eb6e78d0f743f4edb9cd | 0ea76d59e8f8dc3aa0d9de7defe119eb597204ff50c49bfe57ed3c27556c926a |
| Accepted M2e | 0b776c8f5002c846940e438207d582af2259bda6 | 2d58a7ad873735556745a7bb6e3c607d944f9e22653d37ffb1992421f50fec13 |
| M2f | Uncommitted snapshot from 0b776c8f5002c846940e438207d582af2259bda6 | Source-file hashes in comparison.json |

Every isolated `-I` worker asserted reducer/adapter origins beneath its selected source root and recorded their SHA256, executable, Python, SQLite and OS. The parent captured every `src/` and `examples/` Python/TOML hash. The supplemental wrapper SHA256 is `439e5177cf090f34aa6f54903f3b1e9e68b1f2d255983b37e1803c9dac72ca31`; the frozen common worker SHA256 is `ddadca3e1047ae30856ea9c5528ab7d607f4fef4944184860576b7e485b7fe8d`.

| Evidence | Ignored mirror | Bytes | SHA256 |
| --- | --- | --- | --- |
| Main comparison | `M:\Server\ReproSeed\ReproSeed\.validation\m2f-performance-results.json` | 211,924,673 | c34fab825f3768b78e1cc30f993126ecd341bbc32e7d1478a4e18c93513740ff |
| Process CPU | `M:\Server\ReproSeed\ReproSeed\.validation\m2f-performance-cpu-results.json` | 391,065 | e21b3847ee922d8aab911e6ce7b076c0bfb2eca534224ba9117a7201e8a182fa |
| CPU wrapper | `M:\Server\ReproSeed\ReproSeed\.validation\m2f-performance-cpu.py` | 8,979 | 439e5177cf090f34aa6f54903f3b1e9e68b1f2d255983b37e1803c9dac72ca31 |

Local originals remain at `C:\Users\xeonc\AppData\Local\Temp\reproseed-m2f-dxpq6lf3\performance-02\comparison.json` and `C:\Users\xeonc\AppData\Local\Temp\reproseed-m2f-dxpq6lf3\cpu-samples\cpu-results.json`. Compact extraction: `.validation/m2f-performance-summary.json`; constructor/scratch extraction: `.validation/m2f-performance-encoding-summary.json`. Nothing was relocated or deleted.

### Persistent Python object ownership

All numbers below are bytes. Each pair is **incremental cache + encoder / combined model-index estimate + cache + encoder**. Recursive `sys.getsizeof` accounting includes cache containers, keys, evaluation metadata, encoder, ordinal dictionary and ordinal integers. It excludes pre-existing RowId objects, declared key values and the shared `model.rows` tuple. The existing immutable model membership/partition structures are counted once in the combined estimate; mappingproxy backing-dictionary capacity is estimated with an equal-size dictionary. These are Python object-accounting measurements, not RSS or a whole-process memory limit.

| Universe / workload | Pre-M2e | Accepted M2e | M2f |
| --- | --- | --- | --- |
| 10,000 / dense | 12,594,658 / 12,594,658 | 605,622 / 1,210,510 | 605,637 / 1,210,525 |
| 10,000 / sparse | 23,650 / 23,650 | 605,222 / 1,210,110 | 24,137 / 629,025 |
| 50,000 / dense | 50,343,010 / 50,343,010 | 4,171,630 / 6,669,382 | 4,171,645 / 6,669,397 |
| 50,000 / sparse | 23,650 / 23,650 | 4,171,614 / 6,669,366 | 23,993 / 2,521,745 |
| 100,000 / dense | 100,674,658 / 100,674,658 | 8,342,998 / 13,337,902 | 8,343,021 / 13,337,925 |
| 100,000 / sparse | 23,650 / 23,650 | 8,342,998 / 13,337,902 | 23,953 / 5,018,857 |

| Universe | Existing M2e/M2f model indexes | Existing rows tuple, separately excluded |
| --- | --- | --- |
| 10,000 | 604,888 | 80,040 |
| 50,000 | 2,497,752 | 400,040 |
| 100,000 | 4,994,904 | 800,040 |

The encoder borrows existing rows/universe references from a model that stays live throughout reduction. It does not extend their production search lifetime. Protocol fallback has no synthetic model membership/partition index and creates no new full-universe membership set. Its tuple membership cost is not a promise of constant-time lookup.

Reachable encoder storage is a separate diagnostic view: it traverses the encoder plus borrowed existing rows tuple and model universe (while excluding the already shared RowId objects). It overlaps the model-index accounting and encoder ownership above. **Do not add reachable encoder bytes to the combined model-index/cache total**; doing so double-counts shared objects and owned encoder structures.

| 100k M2f workload | Incremental encoder bytes | Encoder-reachable bytes | Borrows rows tuple | Borrows model universe |
| --- | --- | --- | --- | --- |
| dense | 8,036,051 | 13,030,611 | True | True |
| sparse | 303 | 4,994,863 | True | True |
| mixed | 8,036,051 | 13,030,611 | True | True |
| sparse_protocol | 303 | 800,343 | True | False |

At 100,000 rows, the dense incremental saving versus pre-M2e is **91.71%**; including the existing M2f model indexes yields **86.75%**. Sparse-only incremental saving versus accepted M2e is **99.71%**; combined model-index saving is **62.37%**. Sparse cache storage remains slightly above pre-M2e because of the small encoder object. Dense storage is essentially unchanged from M2e.

### All nine 100,000-row workloads

| Workload | Pre-M2e incremental / combined | M2e incremental / combined | M2f incremental / combined |
| --- | --- | --- | --- |
| dense (99,984 retained) | 100,674,658 / 100,674,658 | 8,342,998 / 13,337,902 | 8,343,021 / 13,337,925 |
| sparse (16 retained) | 23,650 / 23,650 | 8,342,998 / 13,337,902 | 23,953 / 5,018,857 |
| repeated dense (8 distinct/24) | 33,558,338 / 33,558,338 | 8,138,470 / 13,133,374 | 8,138,493 / 13,133,397 |
| threshold below (31) | 60,514 / 60,514 | 8,342,998 / 13,337,902 | 60,817 / 5,055,721 |
| threshold at (32) | 60,514 / 60,514 | 8,342,998 / 13,337,902 | 60,817 / 5,055,721 |
| threshold above (33) | 60,514 / 60,514 | 8,342,998 / 13,337,902 | 8,343,021 / 13,337,925 |
| mixed (3 distinct/24) | 4,197,031 / 4,197,031 | 8,074,682 / 13,069,586 | 8,051,095 / 13,045,999 |
| dense to sparse (16 accepted; 1 final) | 5,599,740 / 5,599,740 | 8,240,776 / 13,235,680 | 8,182,286 / 13,177,190 |
| sparse protocol fallback (16) | 23,650 / 23,650 | 8,342,998 / 8,342,998 | 23,953 / 23,953 |

The threshold cliff is visible: 31/32 identities stay sparse; 33 initializes the ordinal map. Mixed duplicates repeat sparse keys before and after initialization and dense keys between small selections. A mixed or shrinking run retains its ordinal index after packed encoding. Its memory is substantially above pre-M2e for these few-key workloads; sparse-only savings do not carry over automatically.

Traced Python allocation peaks during production search are measured after shared input/model preparation. They include sorting/candidate/search scratch, and exclude native SQLite allocations, children and RSS. Each sample is a separate process from untraced timing.

| 100k workload | Pre-M2e peak bytes | M2e peak bytes | M2f peak bytes |
| --- | --- | --- | --- |
| dense (99,984 retained) | 105,937,584 | 39,023,260 | 39,023,252 |
| sparse (16 retained) | 30,809,525 | 39,023,260 | 30,809,685 |
| repeated dense (8 distinct/24) | 64,354,212 | 38,946,781 | 38,946,773 |
| threshold below (31) | 30,832,565 | 39,024,796 | 30,832,725 |
| threshold at (32) | 30,832,565 | 39,024,796 | 30,832,725 |
| threshold above (33) | 30,832,565 | 39,024,796 | 39,024,788 |
| mixed (3 distinct/24) | 34,993,185 | 38,883,273 | 38,859,655 |
| dense to sparse (16 accepted; 1 final) | 25,795,784 | 33,831,716 | 35,235,360 |
| sparse protocol fallback (16) | 30,809,525 | 39,023,260 | 30,809,685 |

Sparse persistent ownership drops strongly while sorting/candidate scratch still dominates its search peak. The new shrinking-workload peak is higher than accepted M2e; lazy initialization moves a large allocation into the active search. No whole-process memory-cap claim follows.

### Complete-search elapsed time

Seconds are median [minimum, maximum], three untraced repetitions per implementation, with finite alternating source orders. All are complete production `reduce_rows` calls on the benchmark model. They include encoder construction and search; shared input preparation is excluded. Traced timings are not included.

| 100k workload | Pre-M2e | Accepted M2e | M2f | M2f versus M2e median |
| --- | --- | --- | --- | --- |
| dense (99,984 retained) | 6.3700 [4.8831, 6.5090] | 7.0731 [5.8924, 8.1176] | 8.6368 [7.1698, 9.4172] | +22.11% |
| sparse (16 retained) | 6.6969 [3.8514, 6.8761] | 4.1750 [3.8090, 4.2039] | 4.3003 [4.0009, 4.6296] | +3.00% |
| repeated dense (8 distinct/24) | 6.8355 [4.2361, 10.7077] | 6.0932 [5.9651, 6.1279] | 8.9003 [7.2314, 9.4175] | +46.07% |
| threshold below (31) | 6.0442 [3.3949, 9.9027] | 4.8230 [4.2325, 9.8496] | 4.1397 [4.0336, 5.0398] | -14.17% |
| threshold at (32) | 5.6293 [3.2931, 8.0692] | 5.0268 [4.3370, 8.1647] | 4.2597 [3.8791, 5.2584] | -15.26% |
| threshold above (33) | 5.1560 [3.9070, 5.7209] | 5.8876 [4.7507, 7.8543] | 5.8764 [4.6321, 7.5828] | -0.19% |
| mixed (3 distinct/24) | 4.5601 [4.5599, 5.9267] | 4.9028 [4.6793, 8.6949] | 6.3892 [5.1330, 7.6731] | +30.32% |
| dense to sparse (16 accepted; 1 final) | 1.6346 [1.6120, 2.0747] | 1.9578 [1.5190, 2.8101] | 2.0238 [1.8681, 2.8876] | +3.37% |
| sparse protocol fallback (16) | 5.2733 [3.9606, 5.3521] | 4.5397 [4.1430, 6.7618] | 4.3751 [3.9305, 5.4645] | -3.63% |

These measurements show regressions as well as savings. The new implementation does not establish a general speed improvement. Its constructor validates the universe, and candidate identity validation remains active during encoding.

### Separate actual process CPU time

Seconds are median [minimum, maximum], three separate alternating repetitions. The wrapper records `time.process_time()` alongside the frozen worker's existing `perf_counter()` calls and asserts exactly two search points. This brackets production `reduce_rows` and includes its constructor scan while excluding row/model/input preparation. It asserts expected evaluations/cache hits (dense 24/0; sparse 24/0; mixed 3/21). Production files are unchanged.

| 100k workload | Pre-M2e CPU | M2e CPU | M2f CPU | M2f versus M2e median |
| --- | --- | --- | --- | --- |
| dense | 3.812500 [3.406250, 3.843750] | 4.625000 [4.562500, 4.765625] | 6.234375 [6.140625, 6.531250] | +34.80% |
| sparse | 3.031250 [2.843750, 3.093750] | 3.109375 [3.031250, 3.156250] | 3.203125 [2.781250, 3.296875] | +3.02% |
| mixed | 2.843750 [2.609375, 3.234375] | 3.515625 [3.406250, 3.828125] | 4.359375 [3.921875, 4.546875] | +24.00% |

The same wrapper asserts fifty encoding clock points: constructor-helper start/end and 24 conversion start/end pairs. Constructor-helper scope includes interface inspection plus the actual constructor; first packed conversion includes lazy index construction. Candidate preparation is outside conversion timing.

| 100k workload / CPU scope | Pre-M2e | Accepted M2e | M2f |
| --- | --- | --- | --- |
| dense / initialization helper | 0.000000 [0.000000, 0.000000] | 0.343750 [0.328125, 0.359375] | 0.046875 [0.046875, 0.062500] |
| dense / 24 conversions | 0.046875 [0.031250, 0.062500] | 1.671875 [1.546875, 1.828125] | 3.171875 [3.000000, 3.187500] |
| sparse / initialization helper | 0.000000 [0.000000, 0.000000] | 0.312500 [0.312500, 0.328125] | 0.046875 [0.046875, 0.062500] |
| sparse / 24 conversions | 0.000000 [0.000000, 0.000000] | 0.000000 [0.000000, 0.000000] | 0.000000 [0.000000, 0.000000] |
| mixed / initialization helper | 0.000000 [0.000000, 0.000000] | 0.296875 [0.281250, 0.406250] | 0.046875 [0.046875, 0.062500] |
| mixed / 24 conversions | 0.000000 [0.000000, 0.015625] | 0.546875 [0.453125, 0.609375] | 1.109375 [1.109375, 1.421875] |

Short sparse conversion windows quantized to zero on this Windows process clock; that does not make the work free. Baseline direct assignment can release a previous full-set reference, so conversion-only baseline numbers are not an encoding speed ratio. Complete-search CPU is the fairer cache-work comparison.

### Separate per-encoding allocation traces

The frozen helper traces initialization separately, then each conversion independently after candidate preparation. Scratch is the operation's traced peak minus its traced current allocation after conversion; it is not a whole-process scratch bound. Persistent structures already measured in earlier trace intervals remain represented by the ownership tables above. Clock/helper bookkeeping remains visible even when pre-M2e has no encoder.

| 100k implementation / workload | Init current / peak bytes | Maximum conversion peak bytes | Maximum transient above retained bytes | First packed operation (zero-based) |
| --- | --- | --- | --- | --- |
| Pre-M2e / all three shapes | 24 / 24 | 48 | 0 | none |
| Accepted M2e / all three shapes | 8,243,956 / 26,643,024 | 25,114 | 12,557 | 0 |
| M2f / dense | 1,624 / 4,824 | 26,642,760 | 18,386,407 | 0 |
| M2f / sparse | 1,624 / 4,824 | 504 | 480 | none |
| M2f / mixed | 1,624 / 4,824 | 26,642,792 | 18,386,463 | 2 |

The 26.64 MB ordinal-construction peak is deferred into the first packed conversion rather than eliminated. Sparse-only avoids it; mixed construction occurs at operation 2 and remains live afterward. Duplicate sparse keys retain exact equality across that initialization boundary.

### Scaled genuine applications

Each domain ran all three instrumented implementations, all three ordinary timing implementations, and a new progress-enabled run. Exact old/new semantics matched. Every run passed the unchanged strict reader, integrity/FK checks, source/bundle hash preservation, three fresh baseline and final confirmations, and three fresh relocated replay confirmations while original source/assets/bundle paths were unavailable.

| Domain | Workers | Rows | Workflow oracle calls / budget | Attempts | Accepted changes | Cache hits |
| --- | --- | --- | --- | --- | --- | --- |
| Duplicate export | 7 | 20,000 -> 5 | 87 / 400 | 81 | 25 | 25 |
| Mixed WITHOUT ROWID billing | 7 | 20,005 -> 8 | 209 / 260 | 191 | 38 | 26 |

Workflow calls include baseline/final confirmations; replay adds three fresh executions per worker. Across fourteen macros, reports record 2,072 workflow oracle invocations plus 42 fresh replay confirmations. These are genuine application oracles, separate from synthetic model/cache microbenchmarks.

| Domain | Pre ordinary seconds | M2e ordinary seconds | M2f ordinary seconds | M2f progress seconds |
| --- | --- | --- | --- | --- |
| Duplicate export | 24.6709 | 27.6598 | 29.3680 | 24.5835 |
| Mixed WITHOUT ROWID billing | 72.6625 | 71.6931 | 68.5383 | 68.7861 |

These ordinary/progress measurements have **one sample per condition**, with progress last. They are bounded observations, not medians or a stable speed/progress-overhead ratio. Instrumented runs record candidate identities and are not ordinary timing samples.

### Actual commands and retained failure

The commands below were actually executed. Their output destinations already exist; a rerun must select new owned output paths.

```powershell
$env:GIT_DIR = 'M:\Server\ReproSeed\ReproSeed\.git'
$env:GIT_WORK_TREE = 'M:\Server\ReproSeed\ReproSeed\.validation\m2f-frozen-source'
.\.venv\Scripts\python.exe -I .validation/m2f-frozen-source/benchmarks/lab.py --source M:/Server/ReproSeed/ReproSeed/.validation/m2f-frozen-source --directory C:/Users/xeonc/AppData/Local/Temp/reproseed-m2f-dxpq6lf3/performance-02 --mode all --sizes 10000 50000 100000 --repetitions 3 --candidates 24 --real-rows 20000
.\.venv\Scripts\python.exe -I C:/Users/xeonc/AppData/Local/Temp/reproseed-m2f-dxpq6lf3/cpu_measure.py --comparison-root C:/Users/xeonc/AppData/Local/Temp/reproseed-m2f-dxpq6lf3/performance-02 --output-root C:/Users/xeonc/AppData/Local/Temp/reproseed-m2f-dxpq6lf3/cpu-samples
```

Main output acquisition: `2026-10-16T13:51:05.255822+00:00`; main completion observed `2026-10-16 14:35:56 UTC`. CPU controller: `2026-10-16T14:35:58.359204+00:00` through `2026-10-16T14:38:30.976595+00:00`.

The initial command at 13:50:40 UTC used the frozen directory without an explicit Git work-tree context and failed before launching any worker: `git archive: fatal: current working directory is untracked`. Its partial owned output remains at `C:\Users\xeonc\AppData\Local\Temp\reproseed-m2f-dxpq6lf3\performance`. The final run used a fresh `performance-02` output and explicit read-only Git context; no failed sample was retried or removed from its denominator.
