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
