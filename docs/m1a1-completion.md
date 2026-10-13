# M1a.1 completion report

Date: October 13, 2026. This milestone repairs clean-checkout test setup and validates the
existing M0/M1a slice. Hosted validation of the repair remains pending Dan's commit/push.

## Starting state and ownership

The checkout was `M:\Server\ReproSeed\ReproSeed`, branch `main`, HEAD
`045897ec16aff8f982ce8fd63a1af4e1de885fbc`, matching the reviewed commit. Initial
`git status --porcelain=v1` was empty. Dan's committed and pushed implementation was
preserved. No reset, cleanup, staging, commit, push, PR, tag or package publication was used.
The historical `docs/m0-m1a-completion.md` remains unchanged.

## Hosted failure and root cause

GitHub connector access confirmed [run 38432780006](https://github.com/chambies2015/ReproSeed/actions/runs/38432780006)
was push/main, attempt 1, on the reviewed HEAD, and completed with failure. It started at
2026-10-13 16:43:02 UTC and was updated at 16:44:35 UTC.

| Job | Original test result |
| --- | --- |
| [Ubuntu Python 3.12, 115418983529](https://github.com/chambies2015/ReproSeed/actions/runs/38432780006/job/115418983529) | 109 setup errors, 2.10 seconds |
| [Ubuntu Python 3.14, 115418983128](https://github.com/chambies2015/ReproSeed/actions/runs/38432780006/job/115418983128) | 109 setup errors, 1.00 second |
| [Windows Python 3.12, 115418983545](https://github.com/chambies2015/ReproSeed/actions/runs/38432780006/job/115418983545) | 107 setup errors, 2 skips, 2.08 seconds |

All failed the test step after successful lint, formatting and mypy. Build and installed-wheel
steps were skipped. Pytest tries to create the specified base directory without creating its
parent. The checkout had no generated `.validation` parent. The logs report `FileNotFoundError`
for `/home/runner/work/ReproSeed/ReproSeed/.validation/pytest` or
`D:\a\ReproSeed\ReproSeed\.validation\pytest`. Functional bodies using `tmp_path` were not reached.

## Before-fix reproduction and repair

An explicit source-only copy of the original working tree was made at
`.validation/m1a1-before`; `.validation`, `.venv`, `dist` and `repro-bundle` were absent inside
the copy. After `uv sync --locked --python 3.12`, `Test-Path .validation` returned `False`.
This representative command returned exit 1 with one setup error, before its body ran:

```text
uv run --locked pytest tests/test_config_artifacts.py::test_allow_exec_before_any_oracle_launch --basetemp=.validation/pytest --tb=short
FileNotFoundError: [WinError 3] ... m1a1-before\.validation\pytest
```

The repair changes only the test step's setup, immediately before its existing invocation:

```sh
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run --locked pytest --basetemp=.validation/pytest
```

Python supplies the portable, idempotent directory creation under the workflow's existing
Bash shell on both platforms. `.validation/` was already ignored. Pytest owns only the
disposable `.validation/pytest` subtree; environments, caches and retained evidence stay
outside that subtree. No generated directory is committed.

Changed files: `.github/workflows/ci.yml`, `AGENTS.md`, `CONTRIBUTING.md`, `README.md`,
`docs/roadmap.md` and this report. The three matrix entries, pinned action SHAs, read-only
permissions, locked installation, complete checks, build and installed-wheel recipe remain
intact. Product code, tests, lockfile, dependencies and the historical report are unchanged.

## Clean-copy setup and commands

The retained `.validation/m1a1_copy.py` helper copied the 35 explicitly tracked files from
the current working tree with `shutil.copy2`, including the repair. It did not use an archive
of committed HEAD or recursively collect user files. Separate fresh copies were made at
`.validation/m1a1-clean312`, `.validation/m1a1-clean314` and `.validation/m1a1-clean-linux`.
At creation, each had no `.validation`, `.venv`, `dist` or demo bundle. The report was written
after those copies; no executable source changed afterward.

The Windows executable was `.tools/bin/uv.exe` version 0.13.0. Each copy installed its own
locked development environment. `UV_CACHE_DIR` pointed to the external existing
`M:\Server\ReproSeed\ReproSeed\.validation\uv-cache`; inherited `PYTHONPATH`, `PYTHONHOME`
and `VIRTUAL_ENV` were removed for validation. No existing project environment or fixture
was copied. Network-restricted sync attempts failed; approved downloads then completed the
same locked sync successfully. No dependency version was changed.

Commands run inside each Windows copy, using its selected interpreter:

```sh
uv sync --locked --python 3.12  # clean312; clean314 used --python 3.14
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy --platform linux
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run --locked pytest --basetemp=.validation/pytest
uv run --locked python -c "from pathlib import Path; Path('.validation').mkdir(exist_ok=True)"
uv run --locked pytest --basetemp=.validation/pytest
uv build --no-sources
```

The preparation and pytest lines were extracted from the patched workflow and run in Git
Bash. Evidence confirmed `.validation` remained absent after sync/static checks and immediately
before the first preparation. The second entry-point execution used existing generated state.

Linux used the already installed Docker Desktop engine and cached
`ghcr.io/astral-sh/uv:0.8.22-python3.12-bookworm-slim` image, with only the disposable source
and evidence directories mounted. No service or runtime was installed or reconfigured.
This is Debian bookworm under WSL2, not an Ubuntu hosted runner; its uv is 0.8.22 rather than
CI's 0.13.0. It ran `uv sync --locked`, the same checks, repaired test entry point twice,
build and wheel recipe. It also reproduced the missing-parent error with the duplicate-export
acceptance test alone before preparation. Static Linux mypy is recorded separately from
actual Linux runtime tests.

## Actual results

| Actual runtime | Python | SQLite | First full suite | Repeated entry point |
| --- | --- | --- | --- | --- |
| Windows | 3.12.15 | 3.53.1 | 106 passed, 3 skipped; 136.49 seconds | 106 passed, 3 skipped; 134.95 seconds |
| Windows | 3.14.7 | 3.50.4 | 106 passed, 3 skipped; 146.99 seconds | 106 passed, 3 skipped; 135.28 seconds |
| Linux, Debian bookworm container | 3.12.11 | 3.40.1 | 109 passed, no skips; 214.14 seconds | 109 passed, no skips; 124.78 seconds |

All three runtimes passed locked sync, Ruff lint/format and both mypy modes. Windows installed
15 locked packages; Linux installed 14 because colorama is Windows-only. All collected the
complete 109-test suite. Both synthetic acceptance tests passed in every full run. Linux
executed the POSIX cases. Windows's three existing skips were symlink creation without
privilege (`WinError 1314`), POSIX executable-mode semantics and POSIX signal return codes.
No test was added, weakened or newly skipped. No additional product defect was uncovered.

All built wheel and source distribution with `uv build --no-sources`. The unchanged inline
CI installed-wheel heredoc was extracted verbatim and run with `RUNNER_TEMP` pointing to
fresh OS/container temporary storage outside each source copy. It created a fresh pip-enabled
venv, installed the wheel with `--no-index --no-deps`, ran CLI help, generated threshold,
reduced 11 -> 3 rows with 18 executions, inspected, relocated, renamed original example paths
unavailable, and replayed with three TARGET_FAILURE confirmations and unchanged fixture hash.
These checks exercised the full existing recipe, beyond CLI help.

Supplemental import-origin checks installed the wheel into separate fresh temporary venvs
and imported outside the source tree with `PYTHONPATH`/`PYTHONHOME` removed (Windows 3.12 also
used `-I`). Logged package paths were inside the installation's `site-packages`, never source
or an editable installation. No runtime dependencies were installed.

Evidence and exact scripts/commands/logs are retained outside pytest's disposable base:

- `.validation/m1a1-win312-evidence/`: `before-entry.json`, `commands.json`, extracted
  `test-entry.sh`, `pytest-first.log`, `pytest-second.log`, `build.log`, `wheel-recipe.sh`,
  `wheel-ci-recipe.log`, and `wheel-origin.log`.
- `.validation/m1a1-win314-evidence/`: static/test/build scripts and logs,
  `actual-ci-wheel-recipe.sh`/`.log`, `wheel-origin.py`/`.log`, both runs' acceptance reports,
  and supplemental relocated acceptance replay evidence for both targets.
- `.validation/m1a1-linux-evidence/`: preflight, locked-sync/static-check logs, before-fix
  reproduction and absence proof, preparation, both pytest logs, build, extracted
  `installed-wheel-ci.sh`, wheel recipe/origin logs and saved acceptance reports.

Distribution contents were inspected: the wheel contains only nine package modules and
five metadata/license entries, with no `Requires-Dist`; source distributions contain explicit
source/tests/examples/docs/CI files and no databases, bundles, environments or caches. The
packaged workflow matches the patched source byte-for-byte. After writing this report, the
Windows 3.12 copy received it for a final `uv build --no-sources --offline` and content
inspection, so that source distribution also includes the new completion evidence. An extra
online rebuild attempt first failed to reach PyPI's Hatchling metadata in the network-restricted
tool environment; using the already populated dependency cache resolved that environment
failure. An early inspection ran before that extra build finished and used an inappropriate
cross-runtime archive-hash expectation; the final check instead compares the rebuilt wheel's
member contents to its own previously validated wheel and checks the completed source archive.

The Linux evidence-preservation helper initially matched both a numeric test directory and
pytest's `current` symlink. Its untracked glob was narrowed before preserving reports and
continuing the second run; the successful first run was retained. This was an evidence
harness issue, not a test/product failure. No timeout or assertion was relaxed.

## Synthetic acceptance evidence

Both targets were independently regenerated from explicitly selected synthetic assets in
fresh `.validation/m1a1-acceptance-f9a92d8facd0447aa9a2292aafa0a6ce`, using Windows Python
3.12.15 / SQLite 3.53.1. Exact commands, stdout/stderr, schema, retained rows and hashes are
in `acceptance-evidence.json` and the per-target JSON files there. Driver command:

```powershell
.venv\Scripts\python.exe .validation\m1a1-acceptance-f9a92d8facd0447aa9a2292aafa0a6ce\run_acceptance.py
```

| Target | Original counts | Final counts | Reduction oracle invocations | Final / relocated replay |
| --- | --- | --- | --- | --- |
| Duplicate export | 6 owners + 24 projects + 2,400 entries = 2,430 | 1 owner + 2 projects + 2 entries = 5 | 54 | 3/3 and 3/3 TARGET_FAILURE |
| Aggregate threshold | 3 crates + 8 parcels = 11 | 1 crate + 2 parcels = 3 | 18 | 3/3 and 3/3 TARGET_FAILURE |

The counts were read from actual reports, not added to reducer logic. Duplicate export
requires exit 42 and the exact stdout marker `REPROSEED_DUPLICATE_EXPORT`; threshold requires
exit 43 and `REPROSEED_WEIGHT_THRESHOLD` when a crate's total parcel mass exceeds 100.
The retained parcels have masses 61 and 44 in crate 99; neither alone exceeds the limit.
Both also confirmed baseline three times. Invocation totals include baseline/search/final;
each replay performed three additional executions. Both terminated with
`single_row_closures_exhausted`, without a global-minimality claim.

Schema declarations/indexes and user versions 1/7 matched the originals; every retained row
was a source-row subset, `PRAGMA integrity_check` was `ok`, and `foreign_key_check` was empty.
Quiescent source database and explicitly selected asset hashes were unchanged. Inspection
changed no bundle contents. Bundles were copied to OS temporary directories outside the
repository; original isolated example and bundle paths were then renamed unavailable before
replay from unrelated working directories. Every bundled regular-file hash remained unchanged.

The first local acceptance driver stopped because a direct baseline created `__pycache__`,
expanding its recursive source inventory. The evidence harness was corrected to compare
explicit selected assets/database and restarted in fresh scratch. No product defect or
assertion weakening was involved; failed scratch was preserved.

## Remaining gate and handoff

The original failed hosted run was neither rerun nor represented as validation of the repair.
All three hosted matrix entries must pass on a commit containing this patch. This remains
pending Dan's review, commit and push because this task leaves changes uncommitted/unpushed.
M1b and later features were not started. Reduction remains neither anonymization nor a proof
of global minimality; arbitrary authorized oracle execution retains the existing OS trust
boundary and process-cleanup limitations.

Unrun platforms: Linux Python 3.14 was unavailable in the existing cached runtimes and was
not manufactured by installing a new service/image. No actual Ubuntu hosted runner or repaired
GitHub run was executed. The Debian container pass and static mypy cannot establish those
hosted results. Windows 3.14 is additional local coverage, not an added matrix entry.

Final `git diff --check` passed. Diff review found only the preparation command and necessary
documentation/evidence changes, no test weakening or accidental generated files. HEAD and
branch remain the starting committed `main`; `git diff --cached --stat` is empty.
`git status --short` lists exactly:

```text
 M .github/workflows/ci.yml
 M AGENTS.md
 M CONTRIBUTING.md
 M README.md
 M docs/roadmap.md
?? docs/m1a1-completion.md
```

All five tracked modifications and the new report are unstaged and uncommitted. Useful local
scratch evidence/builds remain ignored under `.validation`; no user work was removed or
overwritten. Nothing was pushed, tagged, published or submitted as a PR.
