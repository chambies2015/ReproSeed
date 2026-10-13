# M1b.1 completion report

Date: October 13, 2026. Evidence-checked bundles and opt-in human-readable inspection.
Hosted CI for these working changes remains pending Dan's commit and push.

## Starting state and ownership

Repository: `M:\Server\ReproSeed\ReproSeed`, branch `main`, HEAD
`ba40d64db748d974c36666294a1cc4500c79c25f`. Initial `git status --porcelain=v1` was
empty; HEAD exactly matched the reviewed pre-M1b implementation. Existing ignored local
validation evidence was preserved. No reset, staging, commit, push, PR, tag, release or
package publication was performed. Historical completion reports are unchanged.

The M1a.1 hosted gate was satisfied by
[run 38435813594](https://github.com/chambies2015/ReproSeed/actions/runs/38435813594)
on that reviewed commit, as recorded in the accepted milestone request: Ubuntu/Python 3.12,
Ubuntu/Python 3.14 and Windows/Python 3.12 all passed tests, builds and installed-wheel
workflows. That historical run is not validation of this implementation. The matrix,
pinned actions, locked dependencies and repaired clean-checkout preparation are retained.

## Implementation and evidence boundary

`report.py` provides typed version-1 validation with explicit required field sets at every
record level. Unknown fields require a deliberately versioned extension rather than silent
acceptance. Booleans and integers are distinguished. Counts are nonnegative, table sets
agree, final counts do not increase, attempt numbers/references are valid, and strictly
decreasing accepted reductions connect original and final totals. Empty table names remain
supported because the existing SQLite adapter/writer supports them.

Baseline and final evidence require exactly three executed TARGET_FAILURE records with
the configured exit, compatible reason and enough output bytes for the UTF-8 marker.
Accepted attempts require two confirming records. PASS, unrelated failures, contradictory
confirmations, false execution flags and incomplete evidence cannot establish acceptance.
Outcome/reason relationships, finite nonnegative durations, cache/unresolved/invalid
summaries and charged budget/configuration relationships are checked.

The report format and writer are unchanged. Cached confirmations repeat historical evidence
and are excluded from new execution totals; cached records need compatible prior uncached
records. Version 1 lacks candidate row identities, so matching cache evidence cannot prove
that two candidates had identical retained rows. It also lacks a complete interruption
ledger: a second-invocation interruption can omit the first completed confirmation, and an
interruption after evaluation returns but before recording can omit both. The validator
checks bounded accounting allowances (up to one omitted known execution with an invocation
interruption record, otherwise up to two for an interrupted search), rather than fabricating
records. Known executions and unknown interrupted launches remain separate. Contradictory
records are rejected, including inconsistent chains that could result from interruption
between separate reducer bookkeeping assignments.

Bundle checking and replay distinguish four claims:

1. Copied contents match the captured manifest's hashes.
2. Recorded evidence is structurally consistent within version-1 limitations.
3. The private fixture has supported structure, valid integrity/foreign keys and the reported
   final table counts.
4. Only a newly executed replay can establish new reproduction outcomes.

The first three do not establish the fourth. Neither hashes nor consistent metadata
authenticate authorship or prove a claimed historical execution actually occurred. Original
row identities/values and original database structure cannot be reconstructed from this
report. No anonymization or global-minimality claim is made.

## Verified private payload

`acquire_bundle` is an explicit context manager shared by inspection and replay. It captures
bounded manifest metadata, validates safe declared names, rejects finalized SQLite sidecars,
copies only declared regular files, and verifies the copied bytes against captured hashes.
Copied report/configuration are parsed and checked; configuration must name exactly the
fixture and declared assets. A separate disposable database copy receives supported-schema,
integrity, foreign-key and actual-count checks. SQLite never opens the original bundle
database for these checks or the pristine hashed payload for validation.

Replay retains that private lifetime and sources every fresh database/asset copy from it.
It never reacquires configuration or assets from originals after acquisition. Oracle writes
cannot contaminate pristine bytes or later confirmations through the tool-supplied paths.
Temporary directories are cleaned up by their contexts; POSIX executable asset modes are
preserved. `validate_bundle` retains its inspection tuple API; execution uses the acquisition
context rather than the returned original-path metadata.

Any `fixture.sqlite3-wal`, `fixture.sqlite3-shm` or `fixture.sqlite3-journal` beside a finalized
fixture, including empty files, causes rejection without deletion or incorporation. Normal
reduction-source WAL snapshots are unchanged. Traversal, symlink, junction, reserved-path,
case-insensitive duplicate and file/directory conflict defenses remain enforced. Undeclared
files are never acquired.

This prevents replay drifting away from the copied, hashed payload. It does not authenticate
the manifest, provide an OS sandbox, or guarantee complete hostile-filesystem race immunity.
An actor with arbitrary process/private-directory access remains outside this state-hygiene
boundary. Authorized oracle code still runs with the user's OS permissions.

JSON uses standard-library duplicate-key/non-finite hooks, bounded actual reads (64 MiB),
and a 64-level nesting limit. Depth checking uses an iterator stack. Replay/configuration
reads are bounded at 1 MiB. NaN, Infinity, negative Infinity and float overflow are rejected;
JSON writes use `allow_nan=False`. Malformed UTF-8/JSON/TOML, excessive nesting and oversized
integer parsing return actionable errors without exposing document contents. Review found
and fixed the standard-library TOML parser's plain ValueError for a 5,000-digit integer.

## Shallow-report regression and compatibility

The first focused test used a genuine generated synthetic bundle, replaced its report with
only `{"version":1,"verified":true}`, and deliberately updated the manifest's report hash.
Before integration:

```text
.venv/Scripts/python.exe -m pytest tests/test_report_validation.py --basetemp=.validation/report-before -q
FAILED test_rehashed_shallow_report_is_rejected
E Failed: DID NOT RAISE BundleError
1 failed in 0.92s
```

After integration that test passes. A separate clone of the genuine reviewed bundle gives
the same before/after CLI evidence: archived reviewed inspection returned 0 and the shallow
JSON; the final reader returned 2, no stdout, and `report root has missing or unknown fields`.
The recomputed hash isolates semantic validation from hash-mismatch rejection. This gap did
not establish that every historical bundle was invalid or that hashes authenticate authors.

`tests/compatibility_smoke.py` is a small reproducible standard-library source recipe. It
archives the exact reviewed commit, explicitly selects its source with an import-origin
assertion, generates the threshold fixture and a genuine version-1 bundle, then invokes the
current CLI. Commands actually run:

```text
.venv/Scripts/python.exe tests/compatibility_smoke.py --directory .validation/pre-m1b-v1 --phase generate
.venv/Scripts/python.exe tests/compatibility_smoke.py --directory .validation/pre-m1b-v1 --phase validate
```

The reviewed writer reduced 11 to 3 rows using 18 executions. Both JSON forms equal the
original report, text inspection succeeds, and relocated replay produces three executed
TARGET_FAILURE confirmations with original paths unavailable. All bundle and source/example
file hashes remain unchanged. The final reader was checked again against the retained
relocated artifact after the last reason-validation changes; it passed both JSON forms,
text and three new confirmations. No existing bundle was migrated or rewritten.

Actual final-reader text from that artifact:

```text
ReproSeed bundle format 1 / report format 1
Recorded tool: reproseed 0.1.0
Recorded runtime: Python 3.12.15; SQLite 3.53.1
Artifact integrity: checked now (SHA256; 5 declared files)
Recorded evidence: structure and consistency checked now
Fixture structure/counts: checked now
Rows: 11 original -> 3 retained (72.7% removed)
Tables (original -> retained):
  "crates": 3 -> 1
  "parcels": 8 -> 2
Recorded oracle executions: 18
Budget charged: 18/80 (0 unknown interrupted launches)
Cache hits: 5 (reused evidence; no new executions)
Search: 3 accepted reductions; 0 unresolved trials; 0 invalid candidates
Recorded baseline confirmations: 3/3 TARGET_FAILURE
Recorded final confirmations: 3/3 TARGET_FAILURE
Search termination: Single-row deletion closures exhausted; unresolved trials may remain.
New replay: not performed by inspect (oracle not executed)
Hashes and consistent recorded evidence do not authenticate historical executions.
Reduction is not anonymization or proof of global minimality.
```

Formatting is separate from parsing/validation. Default and explicit JSON retain the report
shape with no extra stdout status. Text derives real counts/percentages, handles zero original
rows, separates cache hits from executions and unknown launches, summarizes termination, and
escapes Unicode controls/line separators in displayed table/runtime strings. It does not
display row values, environment variables, raw process output or the full attempt history.
Sentinel subprocess tests establish that inspect executes no oracle and needs no --allow-exec.

## Validation commands and actual results

Explicit tracked and new source files were copied to fresh tool-owned source directories;
no existing environments, caches, databases or bundles were collected. Copy manifests record
`.validation`, `.venv` and `dist` absent at creation. Windows used `.tools/bin/uv.exe` 0.13.0
and `UV_CACHE_DIR` inside tool-owned scratch. A fresh online sync failed because the restricted
host could not reach PyPI; `uv sync --locked --python 3.12 --offline` then installed all locked
packages from the existing cache. Subsequent Windows commands used `UV_OFFLINE=1`. Root
locked sync also succeeded. No lockfile, dependency version or runtime dependency changed.

Linux ran in the already installed Docker Desktop 4.86.0 / Engine 29.7.2 with the cached
`ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim` image. Only disposable source/evidence
directories were mounted. It is Debian bookworm under WSL2, not an Ubuntu hosted runner.
Direct WSL enumeration and unapproved Docker access were denied; approved existing-engine
access succeeded. No runtime/service was installed or reconfigured.

Commands inside the validation copies:

```sh
uv sync --locked --python 3.12  # Windows initial fresh install added --offline
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy --platform linux
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run --locked pytest --basetemp=.validation/pytest
uv build --no-sources
```

The first preparation/test entry and installed-wheel script were extracted from CI and run
with Bash. Final Windows tests also ran the exact preparation and pytest commands directly.
The final Linux copy used extracted LF scripts from a fresh source-only directory, with
absence of `.validation` checked immediately before preparation. The earlier Linux suite
passed 225 tests with one skip, but CRLF extraction produced a carriage-return basetemp name
and its evidence-preservation helper stopped before building. Scripts were corrected to LF
and the final implementation rerun in a new clean copy. A scratch driver import guard was
also corrected before that final run. These were evidence-harness issues, not relaxed tests.

Final runtime results:

| Actual runtime | Python / SQLite | Final full suite |
| --- | --- | --- |
| Windows 10 build 19045 | 3.12.15 / 3.53.1 | 227 passed, 4 skipped; 153.53 seconds |
| Debian bookworm container, WSL2 kernel 6.18.33.2 | 3.12.11 / 3.40.1 | 230 passed, 1 skipped; 231.19 seconds |

Both runtime copies passed locked sync, Ruff lint/format and both mypy modes. Windows's four
skips are two symlink-privilege cases (WinError 1314), POSIX executable semantics and POSIX
signal return codes. Linux skips only the Windows junction case; its symlink, executable and
signal tests actually run. Focused report validation finished with 81 passing cases; snapshot
and existing bundle checks passed 71 with three Windows skips before the extra TOML regression;
inspection's 12 real-file cases passed. The final full suites include the final added cases.

The installed-wheel recipe retains help, reduction, inspection, relocation and replay and now
exercises explicit JSON/text plus default JSON and every bundle file's unchanged hash. Windows
ran the updated recipe in OS temporary storage outside the repository; Linux uses container
temporary storage outside `/work`. Both use fresh pip-enabled environments, install wheels
with `--no-index --no-deps`, remove inherited PYTHONPATH/PYTHONHOME, and execute from unrelated
working directories. Separate `-I` import-origin checks establish `site-packages` imports in
the fresh installations. Threshold reduction produces 11 to 3 rows with 18 executions;
relocated replay produces three executed TARGET_FAILURE confirmations.

Windows and Linux both built the wheel and source distribution successfully. The final
source build additionally includes this completion report; its command/result and distribution
content inspection are recorded below.

Root driver commands actually run (the files are retained in ignored scratch):

```text
.venv/Scripts/python.exe .validation/m1b1_validate.py prepare
.venv/Scripts/python.exe .validation/m1b1_validate.py windows
.venv/Scripts/python.exe .validation/m1b1_final_win.py
.venv/Scripts/python.exe .validation/m1b1_external_wheel.py
```

The final Linux dispatch was:

```powershell
docker run --rm --mount 'type=bind,source=M:\Server\ReproSeed\ReproSeed\.validation\m1b1-clean-linux312-final,target=/work' --mount 'type=bind,source=M:\Server\ReproSeed\ReproSeed\.validation\m1b1-linux312-final-evidence,target=/evidence' --workdir /work ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim bash /evidence/validate.sh
```

Final source-distribution build and inspection commands returned 0:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.validation\uv-cache'
.tools\bin\uv.exe build --no-sources --offline --out-dir .validation/m1b1-final-dist
.venv\Scripts\python.exe .validation/m1b1_distributions.py
```

Distribution inspection checks all eleven wheel modules against current source bytes and
the tested Windows/Linux wheels; all match. Wheel metadata has no `Requires-Dist`. The
source distribution contains the current completion report, CI, compatibility recipe and
new modules, with no databases, bundles, environments, bytecode or caches. uv warned that its
cache directory was inside the source directory; explicit distribution-content checks
confirmed no cache was packaged. After finalizing this report the same offline build and
content inspection were rerun, so the final source archive contains this final report.

Evidence/command drivers and logs are retained under ignored scratch:

- `.validation/m1b1-win312-evidence/`: original/final command JSON, lint/format/mypy/full-suite
  logs, build, extracted CI wheel recipe, external OS-temp recipe/import-origin logs and
  acceptance reports/results.
- `.validation/m1b1-linux312-final-evidence/`: copy/absence proof, actual Linux versions,
  exact `validate.sh`, sync/static/full-suite/build/wheel/import logs and acceptance results.
- `.validation/pre-m1b-v1/`: reviewed source archive, unchanged genuine bundle, compatibility
  recipe results, old/new shallow-report evidence, final-reader replay and actual text output.
- `.validation/m1b1_validate.py`, `m1b1_final_win.py`, `m1b1_external_wheel.py` and
  `m1b1_preserve.py`: local scratch drivers, not product code or committed generated assets.
- `.validation/m1b1-final-dist/`: final wheel/source distribution and `contents-check.json`;
  `.validation/m1b1_distributions.py` records the explicit package-content assertions.

## Acceptance and immutability

Final reports from actual acceptance runs contain:

| Target | Original table counts | Final table counts | Executions including baseline/search/final | Cache hits |
| --- | --- | --- | --- | --- |
| Duplicate export | 6 owners + 24 projects + 2,400 entries = 2,430 | 1 owner + 2 projects + 2 entries = 5 | 54 | 11 |
| Aggregate threshold | 3 crates + 8 parcels = 11 | 1 crate + 2 parcels = 3 | 18 | 5 |

These are observed outputs, not constants in the engine. Both have three baseline and three
fresh final confirmations; each replay adds three new confirmations. Duplicate export stays
within the required eight-row maximum. The acceptance tests assert preserved retained values,
declared schema/indexes/user versions, integrity and FK validity, unchanged source/selected
asset hashes, and every original bundle file unchanged by inspection/replay. Original paths
are made unavailable for relocation. The independent threshold target preserves masses 61
and 44, together exceeding 100. Search ends with exhausted single-row closures in both cases;
this establishes no global minimum.

Deterministic copy-boundary tests replace a synthetic original asset after manifest capture:
changed copied bytes fail hashes before any execution. Replacements after successful private
acquisition, including original configuration/assets, cannot redirect replay. A real mutating
oracle changes its staged database and supporting asset; three later invocations still see
pristine data, and all private payload/original bundle hashes remain unchanged. Unexpected
sidecars are preserved on rejection, and undeclared files are never copied. Incorrect but
correctly hashed final counts are rejected against the real SQLite fixture.

## Review, limitations and handoff

Diff review covered scope, evidence wording, typed boundaries, malformed-input errors,
confirmation/cache/interruption semantics, snapshot races, source immutability, test strength
and generated files. It found and fixed oversized TOML integer handling, a marker-byte-count
contradiction, and unresolved reason contradictions (negative unexpected exits and a claimed
output-limit result below its limit). No existing acceptance assertion was weakened.

README, architecture, SECURITY, AGENTS and roadmap describe the new contract. M1b.2 is split
out for demanding synthetic fixtures/targeted diagnostics and was not implemented. Reducer,
workflow/oracle algorithms, supported schema, exits, acknowledgement, tool version and
standard-library-only runtime remain unchanged. External dependencies/environment are still
not a captured universal replay environment. Temporary data is not securely erased.

Unrun here: Windows/Python 3.14, Linux/Python 3.14 and actual Ubuntu hosted jobs for this patch.
Static Linux mypy is distinct from the Linux runtime tests above. No new hosted run was
observed or triggered; Dan's review/commit/push is the remaining hosted gate.

Final `git diff --check` passed; `git diff --cached --stat` is empty. Branch and HEAD remain
the starting `main` and reviewed commit. Final Git status:

```text
 M .github/workflows/ci.yml
 M AGENTS.md
 M README.md
 M SECURITY.md
 M docs/architecture.md
 M docs/roadmap.md
 M src/reproseed/artifacts.py
 M src/reproseed/cli.py
 M src/reproseed/config.py
?? docs/m1b1-completion.md
?? src/reproseed/inspection.py
?? src/reproseed/report.py
?? tests/compatibility_smoke.py
?? tests/test_bundle_snapshot.py
?? tests/test_inspection.py
?? tests/test_report_validation.py
```

All changes remain unstaged and uncommitted. Generated validation evidence and distributions
remain ignored; no user bundle or source was removed or repaired.
