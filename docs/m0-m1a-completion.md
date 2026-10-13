# M0/M1a completion report

Date: October 13, 2026. Implementation and local validation ran on Windows.

## Starting state and ownership

The existing checkout was M:\Server\ReproSeed\ReproSeed, on an unborn main branch.
`git status --branch --short` showed `No commits yet on main...origin/main [gone]`;
`git rev-parse HEAD` confirmed there was no starting commit. origin was
https://github.com/chambies2015/ReproSeed.git. The working directory contained only .git;
there were no tracked or untracked user files to preserve and no inherited AGENTS.md.

Available initially: PowerShell, Git, ripgrep, Python 3.14.7 and Python 3.10.
uv was absent from PATH. uv 0.13.0 was installed into ignored .tools, then it installed
Python 3.12.15 and created .venv. Validation used Python 3.12.15 and SQLite 3.53.1.
No unrelated databases, credentials, personal files or other projects were inspected.
Every database used was generated synthetic data.

## Implemented

- Installable src-layout package, argparse CLI, MIT license, locked uv development tools,
  pytest/Ruff/mypy configuration, documentation and read-only GitHub Actions permissions.
- Strict version 1 TOML; explicit regular-file assets, config-relative paths, whole-argument
  {python}/{db} placeholders, bounded settings and --allow-exec acknowledgement.
- Read-only WAL-aware backup with a five-second deadline; schema metadata inspection,
  integer identities and reverse FK edges; recursive dependent-child deletion with cycles.
- Validated pristine candidates, disposable oracle copies, exact exit/marker classification,
  bounded capture, finite deadline, cancellation and process-tree cleanup.
- Deterministic chunk reduction, normalized candidate cache, two-confirmation acceptance,
  three-confirmation baseline/final checks and reserved final execution capacity.
- Compact pre-oracle fixture export, versioned manifest/report, SHA256 checks, safe paths,
  read-only inspect, fresh-copy replay and refusal to overwrite existing outputs.
- A real duplicate-name export bug with separate oracle and a different aggregate-threshold
  target; real subprocess acceptance, database/schema/value/hash and relocation checks.
- CI matrix for Ubuntu Python 3.12/3.14 and Windows Python 3.12, quality checks, tests,
  wheel/sdist build and installed-wheel reduce/inspect/relocated replay outside checkout.

## Decisions and scope

Runtime dependencies remain empty. The build backend is Hatchling. Small typed modules
separate configuration, SQLite, oracle, reducer, orchestration and artifacts; no plugin
framework was added. Foreign-key closure explicitly removes dependent rows irrespective
of ON DELETE actions. Retained values and schema are preserved. Final VACUUM INTO removes
unused pages before verification/hashing; no original or candidate-history databases ship.

SQLite >=3.37 is required for reliable table_list metadata. INTEGER PKs must alias rowid;
descending non-alias forms are rejected. STRICT and AUTOINCREMENT work. FK columns have
integer affinity and actual non-null stored integer values. Views/indexes and relevant
metadata are preserved. These precise restrictions implement the initial supported shape;
custom functions/collations and arbitrary schemas are not automatically accommodated.

Only whole-argument placeholders are supported. Portable expected oracle exits are 1–255.
Replay reconfirms three times. A possible two-confirmation trial is reserved before search,
so one remaining search slot may be unused. Hashes cover content, not author authenticity.
Configuration is capped at 1 MiB and manifest/report JSON at 64 MiB; staging is validated
before publication. Reports omit row values and raw output.

Windows required stdlib ctypes Job Object and PeekNamedPipe handling after real tests found
that blocking pipe reads could overrun the deadline. Job assignment can race startup or be
rejected by host policy; bounded taskkill/direct kill remain best-effort fallback. POSIX uses
a new session/process-group kill; detached descendants can escape. These are cleanup tools,
not OS isolation. Staging cancellation counts no execution; confirmed launch cancellation
counts one. An interrupted Popen construction has unknown launch state, recorded separately
and charged conservatively against the budget. No uncertainty is counted as verified failure.

Read-only WAL connections may use SQLite's normal shared-memory sidecar. Source protection
describes tool operations; an arbitrary authorized oracle retains the account's permissions.
Reduction is not anonymization and no global minimality claim is made. No later milestone,
publishing, GitHub administration or runtime service integration was implemented.

## Actual validation

Commands below were run from the checkout unless stated otherwise. `.tools\bin\uv.exe`
was the uv executable. Later uv commands used UV_CACHE_DIR=.validation\uv-cache because
the default global cache was restricted. Required dependency downloads received tool approval.

| Exact command | Actual result |
| --- | --- |
| `.tools\bin\uv.exe sync --locked --python 3.12` | Passed; 15 locked packages resolved, editable package installed |
| `.tools\bin\uv.exe run ruff check .` | All checks passed |
| `.tools\bin\uv.exe run ruff format --check .` | Passed; 27 files already formatted |
| `.tools\bin\uv.exe run mypy` | No issues in 9 package source files |
| `.tools\bin\uv.exe run mypy --platform linux` | No issues in 9 source files; static platform analysis only |
| `.venv\Scripts\python.exe -m pytest --basetemp=.validation/all-tests -q` | 106 passed, 3 skipped in 83.30 seconds |
| `.venv\Scripts\python.exe -m pytest tests/test_acceptance.py --basetemp=.validation/acceptance-agent -v` | 2 passed in 22.19 seconds |
| `.venv\Scripts\python.exe -m pytest tests/test_sqlite_adapter.py -q --basetemp=.test-tmp/sqlite-agent-final --tb=short` | 29 passed in 24.51 seconds |
| `.venv\Scripts\python.exe -m pytest tests/test_oracle.py -q --basetemp=.tmp/oracle-tests-4 --tb=short` | 27 passed, 1 POSIX-only skip in 15.53 seconds |
| `.venv\Scripts\python.exe -m pytest tests/test_config_artifacts.py --basetemp=.validation/artifact-final -q` | After final publication validation: 44 passed, 2 explicit skips in 28.83 seconds |
| `.tools\bin\uv.exe build --no-sources --offline --cache-dir .validation/uv-cache` | Wheel and source distribution built successfully |
| `.tools\bin\uv.exe venv .validation/installed --python .venv/Scripts/python.exe --cache-dir .validation/uv-cache` | Fresh non-editable test environment created |
| `.tools\bin\uv.exe pip install --python .validation/installed/Scripts/python.exe --no-index --no-deps dist/reproseed-0.1.0-py3-none-any.whl --cache-dir .validation/uv-cache` | Built wheel installed with no runtime dependencies |
| `.tools\bin\uv.exe pip install --python .validation/installed/Scripts/python.exe --no-index --no-deps --reinstall-package reproseed dist/reproseed-0.1.0-py3-none-any.whl --cache-dir .validation/uv-cache` | Latest rebuilt wheel reinstalled before final installed smoke |
| `.venv\Scripts\python.exe .validation/installed_smoke.py` | Installed CLI help, baseline, reduction, inspect and relocated replay passed from outside checkout; import came from installed site-packages |

The ignored installed_smoke.py script and wheel-smoke-evidence.json retain local evidence;
the equivalent portable installed-wheel recipe is committed inline in CI. Distribution
contents were inspected: package code and metadata only in the wheel; source/docs/tests/
examples/CI in sdist; no generated databases, bundles, environments or cache content.
The final sdist had 36 members including this report. uv warned about a cache inside the
source root; explicit sdist selection and member inspection confirmed its exclusion.

The full suite's three skips were explicit: this Windows account cannot create symlinks
(WinError 1314); executable-mode semantics require POSIX; signal return-code semantics require
POSIX. Source hardlink rejection did execute successfully. No required acceptance test was
skipped. The Windows descendant-pipe deadline, tree cleanup and cancellation cases passed.

Tests also exercised baseline pass/wrong/inconsistent outcomes, wrong marker/exit combinations,
timeouts/output limits/launch errors, oracle mutations, nullable/self/cyclic/chain FKs,
quoted/sparse/negative identifiers, unsupported and invalid databases, committed uncheckpointed
WAL, bounded snapshot locking, deterministic caching, budgets, irreducible/empty cases,
file/sidecar conflicts, malformed/tampered bundles and missing dependencies.

Early attempts exposed and resolved environment/tooling failures: sandbox network prevented
initial uv/editable downloads; the global uv cache and default pytest temp-root scan were
restricted. Approved downloads and workspace-local cache/basetemp fixed them. The first
oracle cleanup tests failed on Windows and drove the Job/pipe fix. A reducer unit test did
not reach its intended budget branch because the equivalent candidate was cached; its input
was changed to exercise an unresolved, uncached trial, keeping budget assertions intact.
The first installed smoke evidence script tried to hash an imported __pycache__ directory;
it was corrected to compare regular files and rerun successfully. These failed attempts
are not counted as successful checks.

## Demo and independent replay evidence

| Target | Original user rows | Final rows | Reduction oracle executions | Final verification | Search termination |
| --- | --- | --- | --- | --- | --- |
| Duplicate export | 6 owners + 24 projects + 2400 entries = 2430 | 1 owner + 2 projects + 2 entries = 5 | 54 | 3/3 TARGET_FAILURE | single_row_closures_exhausted |
| Weight threshold | 3 crates + 8 parcels = 11 | 1 crate + 2 parcels = 3 | 18 | 3/3 TARGET_FAILURE | single_row_closures_exhausted |

The duplicate run recorded 46 candidate attempts, 13 accepted reductions and 11 normalized
cache hits; zero unresolved trials and zero database-invalid candidates. Its 54 executions
include baseline and final verification. Replay uses three additional actual oracle executions;
the direct acceptance/smoke baseline invocation is separate from reduction's budget.

Acceptance verified exact declared schema, retained values as source-row subsets, user_version,
integrity_check and foreign_key_check. A relocated bundle was copied to an OS temporary
directory outside the repository, and original example/bundle paths were renamed before
replay from an unrelated cwd. All three replay confirmations were TARGET_FAILURE. Every
bundled regular file's SHA256 remained identical. The installed-wheel smoke independently
repeated this entire workflow without an editable source import.

Duplicate source SHA256 before/after both reduction and replay:
`a1f219e3495878679289eef047a6eba8e91d483797eaa5977c5b5f4f785cda69`.

Duplicate compact fixture SHA256 before/after relocated replay:
`8b9b80e6a6a2e3ae387dee0f3b93da7a5d9dba34b0fada3b8c06c571e1958e4a`.

Threshold compact fixture SHA256:
`471fdf89e2deae73c964d37de7175e05629dee27145a8373414af1e01e7d58b1`.

The exact README quickstart also ran successfully using the local uv executable:

```
uv sync --locked --python 3.12
uv run python examples/duplicate_export/generate.py
uv run reproseed reduce --config examples/duplicate_export/reproseed.toml --out ./repro-bundle --allow-exec
uv run reproseed inspect ./repro-bundle
uv run reproseed replay ./repro-bundle --allow-exec
```

It reproduced 2430 -> 5 rows with 54 reduction executions and 3/3 TARGET_FAILURE replay.
The generated source and repro-bundle are intentionally ignored, available locally for review.

## Review, unrun checks and final Git state

Independent code review found and fixed Unicode TOML surrogate serialization, malformed
UTF-8/NUL validation, source aliases and sidecar conflicts, executable-mode preservation,
and interrupted-launch accounting. The untracked implementation was reviewed for scope,
filesystem operations, source protection, claims and missing tests. Ordinary git diff is
empty on this unborn checkout because all implementation files are new and unstaged.

Linux runtime tests and hosted GitHub Actions were not run. The workflow pins verified
official full commits: checkout v7.0.1 at 3d3c42e5aac5ba805825da76410c181273ba90b1 and
setup-uv v10.3.0 at 1c37ad07a6a961277cf70c0d37d6f313000f5884. Their release/commit and
action.yml sources were checked; the inline wheel-test Python parsed locally. This does
not establish a passing hosted CI run. Local Python 3.14 tests were not run after installing
the requested Python 3.12 environment. Production concurrency, malicious OS-level isolation,
sanitization and global minimality are neither supported nor claimed.

Final Git state: main remains unborn; 35 reviewable new files, all untracked. `git status
--short` lists .github/, .gitignore, AGENTS.md, CONTRIBUTING.md, LICENSE, README.md, SECURITY.md,
docs/, examples/, pyproject.toml, src/, tests/ and uv.lock. `git diff --cached --stat` is empty.
Generated SQLite fixtures, bundles, logs, build outputs, tools/environments and caches are
ignored. Nothing was staged, committed, pushed, tagged, released or published, and no PR
was created. All requested changes remain available for Dan to review and commit.
