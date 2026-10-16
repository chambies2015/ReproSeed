# ReproSeed performance lab

M2f extends this recipe with three isolated implementations: actual pre-M2e source
(`27be3d46c31f752f8944eb6e78d0f743f4edb9cd`), accepted M2e source
(`0b776c8f5002c846940e438207d582af2259bda6`) and the captured current source.
`--accepted-ref` selects the second archive explicitly. Small shallow-checkout
mechanics runs use both `--baseline-ref HEAD --accepted-ref HEAD`; these are not
historical performance evidence. All historical [M2e observations](../docs/performance.md)
remain labeled with their original source and runtime.

The extended workloads add 31/32/33 retained identities, mixed sparse/dense candidates,
duplicates before and after ordinal initialization, dense-to-sparse shrinkage and a
protocol caller without the model membership interface. The current policy uses exact
frozensets up to 32 rows and packed bytes above 32, with lazy ordinal construction.
Existing model membership and row tuples are shared and remain live through search.
Storage fields distinguish incremental cache/encoder ownership, reachable shared
references, existing model indexes and their combined cost. A dense invocation retains
its ordinal map when later selections become sparse; sparse-only savings must not be
applied to that mixed lifetime. Per-encoding traced samples distinguish initialization,
retained allocations and scratch peaks; ordinary repetitions remain untraced.

## Generated correctness and mutation sensitivity

These are developer recipes, not public ReproSeed commands. They require only the
standard library after development tools are installed, except mutation probes import
the installed pytest development dependency. Each output parent must exist and the
output directory must be new. No retry or overwrite option is provided.

```sh
uv run --locked python benchmarks/campaign.py --directory .validation/m2f-smoke-fresh --profile smoke --seed 104729
uv run --locked python benchmarks/campaign.py --directory .validation/m2f-extended-fresh --profile extended --seed 104729
uv run --locked python benchmarks/mutations.py --directory .validation/m2f-mutations-fresh
```

Smoke selects eight supported fixtures, eight deliberate unsupported/invalid variants,
24 seeded model searches and one real billing lifecycle per implementation. Extended
selects 128 supported fixtures, 64 deliberate variants, 1,000 model searches and 24 real
billing lifecycles per implementation. Accepted M2e and the frozen new sources run in
separate isolated interpreters on identical generated inputs. Source/import hashes,
generator version, template, seed, input/config hashes and exact single-case replay argv
are recorded in `results.json`; raw synthetic inputs and failures remain beside it.
`--case supported:0` (or `unsupported`, `model`, `lifecycle`) replays one ordinal with
the same `--seed`. Use each saved `replay_command` to select the captured sources and
recipe rather than silently regenerating a case against different code.

The four layouts are ordinary/STRICT rowid and ordinary/STRICT WITHOUT ROWID. All six
scalar/composite INTEGER/TEXT key shapes occur, along with independent FK groups,
partial NULLs, cycles, self-links, tenant partial identifiers, empty/unrelated tables,
quoted/Unicode keys and indexes/actions. Authored structured templates drive full-key
SQLite joins with the parent on the left; a separate fixed-point scan supplies expected
closures. No expected edge comes from adapter internals. Values, schema/index metadata,
integrity and FKs are checked after actual materialization. Tiny universes enumerate seed
subsets and independently enumerate valid retained subsets; only a bounded sample is
materialized. Counters distinguish these from CLI commands and oracle subprocesses.
Valid SQLite schemas outside ReproSeed's policy and SQLite DDL rejections are separate
classifications. Diagnose/reduce rejection cases assert zero launches and no bundle.

The finite controls reject excessive counts, seeds, subsets, materializations, deadlines
and artifact-stop-threshold values before fixture allocation. `--artifact-limit-mib` is
checked between bounded workers; retained files may exceed it by one finite batch plus
growth of aggregate result JSON. Finite case/fixture counts and log/result sizes bound
retained work; the threshold is not a strict process-memory or filesystem maximum.
Worker logs and results have explicit limits, workers have deadlines, and the driver
preserves failed/skipped cases.
Defaults allow 256 tiny subsets, three materializations per fixture and 180 seconds per
batch worker. Large campaigns stay outside ordinary CI. The CI smoke can archive HEAD
in a shallow checkout; that checks mechanics without claiming historical equivalence.

Metamorphic evidence states its invariant: insertion reversal preserves exact rows/schema
and search inputs; disconnected rows, bijective key/reference renaming and compatible
storage variants preserve fixture validity and target outcome. They need not select the
same minimal fixture. Correcting the genuine billing defect must remove the outcome.
The real application oracle is reused; model predicates are explicitly synthetic and do
not count as real CLI/subprocess lifecycles. Agreement with M2e supplements the independent
SQL checks and cannot establish the absence of shared defects.

The mutation recipe makes ten disposable source copies and applies one exact production
boundary substitution per mutant. Its clean control and mutant execute the same targeted
probe in isolated interpreters. Line tracing proves the changed boundary was reached;
only a semantic assertion after a successful clean control counts as detection. Syntax,
import/setup errors are invalid; unknown timeouts are unresolved; survivors stay visible.
`mutations.json` records each boundary, invariant, test, hashes, assertion, classification,
timeout and replay command. `--mutation NAME` selects one finite mutant; `--timeout`
is bounded to 5..120 seconds. Working runtime hashes are rechecked after the campaign.
Mutated copies, generated fixtures and logs remain ignored and are excluded from packages.

Automated evidence establishes bounded tested invariants. Human usability remains
NOT TESTED/advisory. Neither recipe authorizes publication or replaces the actual hosted
M2f gate. See [M2f completion](../docs/m2f-completion.md) for actual counts and limits.

## Measurement mechanics

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
  timing repetitions in recorded three-way rotating/reversed order, followed by separate traced
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
  Each domain runs an instrumented three-way semantic comparison, then separate ordinary
  timings for all three sources, then ordinary new-code timing with text progress enabled.
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
uv run --locked python benchmarks/lab.py --directory .validation/m2f-small-fresh --mode smoke --baseline-ref HEAD --accepted-ref HEAD
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
