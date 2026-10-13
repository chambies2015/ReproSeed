# Cyclic approval workflow

This synthetic purchase-approval validator should reject workflows containing
dependency cycles. Its deliberate depth-first search bug marks a step completed
before following that step's dependency. On a back edge, the completed-step fast
path returns before checking the active path. A genuine two-step cycle is therefore
accepted. A separate direct-self-dependency check still rejects self loops.

The generator creates 1,626 user rows: six `"team departments"`, 60 employees,
120 `"approval workflows"`, 1,320 `"approval steps"` and 120 `"approval rules"`.
The unrelated `"approval activity"` table is empty. Quoted table identifiers,
negative and sparse integer primary keys and nullable references all remain inside
ReproSeed's supported SQLite subset.

Employees belong to departments. Workflows reference a department and an optional
requester; steps reference their workflow, approver and optional predecessor step;
rules reference their workflow and an optional reviewer. The self-reference is a
single-column integer foreign key declared deferred so the generator can insert
both ends of a cycle in one transaction. Activity rows, if present, could reference
a workflow and employee. No triggers or unsupported schema features are used.

Most workflows have ordinary eleven-step approval chains. The final workflow has
a nine-step chain plus two steps that depend on each other. Both cycle steps use
the workflow's department and approver, and its rule requires at least one step.
The application cannot accept a workflow with no rule or no eligible steps, so
the failure requires enough surrounding domain context to remain meaningful.

`app.py` exposes `validate_workflows(database)`, returning actual readiness
decisions. The oracle independently follows predecessor paths and records path
positions to detect cycles. It emits `REPROSEED_APPROVAL_CYCLE` on stdout and exits
45 only when the application incorrectly accepts an otherwise eligible workflow
with a two-node cycle. An accepted three-node cycle, unrelated rejection or crash
does not satisfy that exact target. Breaking the two-node cycle or repairing the
application's visited-set ordering makes the unchanged oracle pass.

From the repository root, with the development environment installed:

```console
uv run python examples/approval_cycle/generate.py
uv run reproseed diagnose --config examples/approval_cycle/reproseed.toml
uv run reproseed diagnose --config examples/approval_cycle/reproseed.toml --allow-exec --format json
uv run reproseed reduce --config examples/approval_cycle/reproseed.toml --out repro-bundle-approval --allow-exec
uv run reproseed inspect repro-bundle-approval
uv run reproseed inspect repro-bundle-approval --format text
uv run reproseed replay repro-bundle-approval --allow-exec
```

Use fresh source/output paths for another run; existing files are never
overwritten. Static diagnosis executes no oracle and confirms no failure.
Executable diagnosis requires three fresh target confirmations and does not
promise that a later reduction will succeed.

The M1b.2 Windows/Python 3.12.15, SQLite 3.53.1 validation reduced 1,626 rows to
six within the 400-invocation budget. It used 107 oracle executions, 25 cache hits
and 22 accepted reductions, with zero unresolved or invalid trials. It exhausted
single-row deletion closures. The retained counts were:

| Table | Original | Retained |
| --- | ---: | ---: |
| team departments | 6 | 1 |
| employees | 60 | 1 |
| approval workflows | 120 | 1 |
| approval steps | 1,320 | 2 |
| approval rules | 120 | 1 |
| approval activity | 0 | 0 |

The two unchanged step rows still reference one another, and foreign-key checks
pass. Deleting either step closes over the other, exercising cycle-aware removal
without application-specific reducer logic. The source occupied 94,208 bytes; the
compact fixture occupied 32,768 bytes. An additional local run took 62.269 seconds
while other fixture acceptance runs used the same host; this is an observation
rather than a benchmark. The completion report records the acceptance run, three
final confirmations and three relocated replay confirmations with hash checks.

Copy the entire completed bundle to a new directory outside this checkout. With
ReproSeed installed, use an unrelated working directory:

```console
reproseed inspect /path/to/relocated-approval-bundle --format text
reproseed replay /path/to/relocated-approval-bundle --allow-exec
```

Replay uses the bundle's verified scripts and fixture; original example paths
are unnecessary. These demos need only Python and ReproSeed, while arbitrary
application dependencies are not packaged automatically. Retained values and
schema remain present: reduction is not anonymization or proof of global
minimality. Review artifacts before sharing; subprocess staging is not a sandbox.
