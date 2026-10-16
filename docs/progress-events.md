# Reduction progress and events

Reduction remains quiet until its existing stdout JSON summary by default. Opt in to
simple stderr lines, a separate diagnostic JSON Lines file, or both:

```console
reproseed reduce --config case.toml --out bundle --allow-exec --progress
reproseed reduce --config case.toml --out bundle --allow-exec --events run.jsonl
reproseed reduce --config case.toml --out bundle --allow-exec --progress --events run.jsonl
```

Neither option grants execution permission. Both are reduction-only. Stdout keeps the
existing summary shape. `--events` resolves against the caller's current working
directory; source and asset paths keep their configuration-relative interpretation.
The event file is never automatically copied into the bundle.

The lines describe preparation, private source acquisition, model construction, baseline
confirmations, search, compaction, final confirmations and publication. Candidate size
describes pending work; retained rows and accepted changes describe a published search
checkpoint. Cache hits reuse historical confirmation evidence and do not count as new
executions. Known executions and conservatively charged invocations remain distinct from
unknown interrupted launches. There is no estimated completion percentage or ETA.

Repetitive search display is limited to one line per half second. Accepted changes,
phase transitions and final status bypass that limit. Events are streamed independently
of the display limit, without retaining a second in-memory history. No heartbeat thread
is used while an oracle blocks. The synchronous writes can still experience OS stalls.

## Separate version-1 diagnostic format

Each complete line is one finite UTF-8 JSON object. Mandatory fields are:

| Field | Meaning |
| --- | --- |
| `event_version` | Exactly `1`; independent of report/config/manifest/diagnosis versions |
| `sequence` | Consecutive run-local positive integer, beginning at one |
| `elapsed_seconds` | Nonnegative monotonic seconds since observer construction, rounded to six decimals |
| `event` | Allowlisted lifecycle event |
| `phase` | Allowlisted phase |

Events are `started`, `completed`, `model_ready`, `confirmation`, `candidate`,
`committed`, `search_stopped`, `invocation`, `aborted`, `failed`, `published`,
`sink_disabled` and `truncated`. Phases are `run`, `preparation`, `acquisition`,
`model`, `baseline`, `search`, `compaction`, `final_verification`, `publication`
and `observation`.

Optional integer facts are `original_rows`, `candidate_rows`, `retained_rows`, `attempts`,
`accepted_changes`, `cache_hits`, `known_executions`, `unknown_launches`,
`charged_invocations`, `max_invocations`, `confirmation` and `required_confirmations`.
They are aggregate nonnegative integers bounded by 2^63 - 1. Optional `outcome` is
`TARGET_FAILURE`, `PASS`, `UNRESOLVED` or `DATABASE_INVALID`. `reason` is a fixed
sanitized code, including the established search stop codes; arbitrary exceptions and
oracle text are never copied into it. `executed` is boolean or null; invocation events
always include it, with null denoting launch uncertainty. Other events omit absent facts.

For example, the following illustrates the shape; timestamps and counts depend on the run:

```jsonl
{"event_version":1,"sequence":1,"elapsed_seconds":0.000021,"event":"started","phase":"run"}
{"event_version":1,"sequence":2,"elapsed_seconds":0.000088,"event":"started","phase":"preparation"}
```

Keys, row contents, table names, membership encodings, argv, failure markers, absolute
paths, environment values, credentials and raw stdout/stderr are excluded. The format
does not perform anonymization: review the bundle's retained fixture and explicit assets
separately before sharing them.

Telemetry is diagnostic and may be incomplete. It is not `report.json`, a replay artifact,
authenticated historical evidence, an execution ledger or a resume checkpoint. An event
that starts a phase does not establish its completion. Only successful final confirmation
and bundle publication allow published/completed observations. Hash validation and old
events do not establish a fresh reproduction; execute replay for new outcomes.

## Ownership, bounds and failures

The log is created exclusively before any configured oracle executes. Existing empty
files, directories, links and device names are rejected. Its parent must already exist
and allow creation; parents are never made automatically. The path must be separate
from configuration/source/assets, source SQLite sidecars and the intended output bundle.
Lexical ancestors are checked for symlinks/junctions before resolution, including paths
that traverse `..`. This follows the supported local path policy and does not promise
immunity to hostile concurrent filesystem replacement.

Initial acquisition failure returns CLI exit 2 without execution. An aborted run may
leave its owned partial event file for diagnosis. Each record is limited to 4096 bytes;
the total file cap is 16 MiB. The writer reserves 4096 bytes for one complete `truncated`
event with `reason="size_limit"`, then stops logging. The display can continue.

An I/O or serialization failure disables only that sink and issues at most one warning
through an available channel. A failed stderr sink can be recorded as `sink_disabled`
in an available event file. File writes are unbuffered; after an uncertain partial or
short write, no more records are appended. Such a file can end with an incomplete JSON
line. These conditions cannot change oracle outcomes or promote pending search state.
KeyboardInterrupt, second-interruption aborts and arbitrary implementation errors are
not converted into harmless logging failures.

The handled search boundary includes candidate/committed notifications inside the
reducer. Its `search_stopped` notification is the handoff to finalization: interruption
there or during compaction/final confirmation may abort without a bundle. Publication
notifications follow the completed exclusive publication. An interruption during a
late `published` or run `completed` notification can therefore return interruption status
while leaving an already complete, independently inspectable verified bundle.
