# ReproSeed performance lab

This standard-library recipe compares actual archived Python sources with an isolated
snapshot of the current `src/` and synthetic `examples/`. It never imports both versions
into one process. Each `-I` worker inserts exactly its selected `source/src`, asserts the
resolved reducer/adapter origins, and records source-file SHA256 hashes, Python, SQLite,
OS and executable. The parent records the archived commit, archive SHA256, current HEAD,
working status and all captured source-file hashes. Uncommitted source is captured;
HEAD alone is not its content identity.

Run from the checkout with development dependencies installed. Every destination must be
new and have an existing parent. Generated data, traces and JSON belong under ignored
`.validation/`; they are excluded from distributions.

```sh
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run --locked python benchmarks/lab.py --directory .validation/m2e-performance-fresh --mode all
```

The default baseline is reviewed M2d.1 commit
`27be3d46c31f752f8944eb6e78d0f743f4edb9cd`, not a reimplementation. Fetch that object through
your normal repository workflow if it is absent; the recipe does not use the network.
`--baseline-ref REF` explicitly selects another available commit and records it. Source
snapshots and all samples remain in the new output directory; `comparison.json` has
`measurement_version=1`. Failed samples are retained, never automatically retried.
The command exits nonzero on a worker failure or semantic mismatch.

The complete run contains:

- Cache/model workloads at 10,000, 50,000 and 100,000 rows; 24 candidates; three untraced
  timing repetitions with alternating baseline/new order, followed by separate traced
  allocation samples. All four supported INTEGER/TEXT/composite/mixed WITHOUT ROWID
  identity shapes occur. Cache cases use 24 dense distinct selections, 24 sparse
  selections, and eight dense selections repeated three times. Dense candidates omit
  16 rows; sparse candidates retain 16. These deliberately different cases expose the
  fixed ordinal-index tradeoff.
- Actual production `reduce_rows` cache inspection at return, excluding shared,
  pre-existing row identity objects but including cache containers, keys, result metadata,
  the encoder object, ordinal dictionary and ordinal integers. It measures peak traced
  Python allocations before the recursive storage-measurement traversal. Scratch space
  is reflected in aggregate peak, not separately attributed to the encoder. Model
  allocation samples include construction and estimate extra membership/partition index
  storage, including per-table tuples and a mappingproxy backing-dictionary estimate.
- Model construction, 50 membership validations, 50 three-leaf closures, 50 three-parent
  closures and one real validated materialization per size/repetition. Each parent has
  one child in each of three tables; cycles/self-links are separate correctness cases.
  Materialization still includes snapshot/SQLite validation and actual DELETE work.
- Three finite seeded graph comparisons with scalar/TEXT/composite identities, mixed
  graph cycles/self-links, empty and irreducible selections, budget exhaustion,
  nonmonotonic targets, invalid candidates and unresolved evaluations. Comparisons retain
  complete ordered considered/evaluated identities, cache decisions, attempt outcomes,
  acceptance chains, committed identities and stop reasons.
- Two scaled existing applications, each starting with at least 20,000 source rows.
  Duplicate export receives unique harmless entries; mixed WITHOUT ROWID billing
  receives complete safe invoice/line/payment/refund decoys. The genuine existing
  semantic oracles and their unchanged explicit 400/260 invocation budgets are used.
  Each domain runs an instrumented baseline/new semantic pair, then separate ordinary
  baseline/new timings, then ordinary new-code timing with text progress enabled.
  Instrumented runs record full candidate identities outside the public telemetry.
  Every run uses the unchanged strict bundle reader, integrity/FK checks, three fresh
  final confirmations and three fresh relocated replay confirmations while original
  source/assets/bundle paths are unavailable. Source and original/relocated bundle
  hashes must remain unchanged. Report comparison removes only `duration_seconds`.

Use an otherwise idle host. The recipe never starts parallel workers; it cannot prevent
other desktop, antivirus, OS or network-filesystem activity. Real timings use one sample
per condition and progress runs occur last, so they reveal bounded observations with
cache/order noise rather than a stable overhead ratio. They are not included in the
three-sample microbenchmark medians. Timing samples do not enable tracemalloc, cProfile
or candidate-identity recording. Cache `encoding_seconds` times only conversion of an
already-constructed candidate: the baseline directly uses that frozenset, while new code
calls the production encoder. It excludes baseline hashing, and baseline assignment can release the previous full-set
reference; do not use those baseline conversion-loop numbers for an encoding speed ratio.
Use complete untraced `search_seconds` samples to assess overall cache-work tradeoffs.

Other bounded modes and controls:

```sh
uv run --locked python benchmarks/lab.py --directory .validation/m2e-micro-fresh --mode micro --sizes 10000 50000 100000 --repetitions 3 --candidates 24
uv run --locked python benchmarks/lab.py --directory .validation/m2e-differential-fresh --mode differential
uv run --locked python benchmarks/lab.py --directory .validation/m2e-real-fresh --mode real --real-rows 20000
uv run --locked python benchmarks/lab.py --directory .validation/m2e-small-fresh --mode smoke --baseline-ref HEAD
```

`smoke` uses 64 model/cache rows and the 11-row threshold application, and can archive
HEAD in a shallow checkout. That checks recipe mechanics and provenance, without
claiming a historical performance comparison. `tests/test_benchmarks.py` exercises it,
including Unicode/space paths, import-environment contamination, bounded arguments and
refusal to reuse an output directory. A clean-copy validator may supply read-only
`GIT_DIR`/`GIT_WORK_TREE` for the original project's archive while current source imports
come only from its copied source snapshot. Ordinary CI has no speed-ratio assertion.

Limits are explicit: sizes are multiples of four from 16 through 100,000, candidate
count 3..64, timing repetitions 1..5, and requested large fixture rows 20,000..50,000
(billing rounds upward by at most six rows). Each worker has a 1,200-second deadline;
oracles retain the application configuration's five-second deadline and output limit.
The lab does not exhaust RAM/disk to find host limits. An omitted size is unmeasured;
a failed worker remains a failed sample in `comparison.json`.

For an optional separate profile, choose new owned outputs and a source snapshot from
a completed run:

```sh
uv run --locked python -I -m cProfile -o .validation/m2e-cache-profile.prof benchmarks/worker.py --source .validation/m2e-performance-fresh/new-source --directory .validation/m2e-profile-fresh --sizes 10000 --timing-only
```

Profiled/traced durations must not be substituted for ordinary timings. Tracemalloc
tracks Python allocations, not process RSS, SQLite native memory, filesystem cache or
oracle child-process memory. Storage estimates are implementation/runtime specific.
Do not sum overlapping phase timers or present these measurements as a whole-process
memory cap, global-minimality proof, human-feedback gate or universal speed claim.
See [measured observations](../docs/performance.md).
