# Pytest duplicate-export integration

This recipe copies the existing `duplicate_export/app.py` and deterministic
`generate.py` by name into a fresh case. It keeps the original non-pytest example
intact and maintains no second exporter. The test independently compares the real
exported entry IDs with SQLite source rows. Only a missing entry explained by an
equal name in a different project raises the configured, stable
`AssertionError("cross-project export lost an entry")`.

Install an M2g-capable ReproSeed build and a supported pytest separately in the
same interpreter (the locked verification point is pytest 9.1.1). Neither package
is installed by the example. Run commands offline after this preparation. From
the repository root, with that interpreter activated:

```sh
python examples/pytest_duplicate_export/prepare.py --directory .validation/pytest-case
python -m reproseed diagnose --config .validation/pytest-case/reproseed.toml
python -m reproseed diagnose --config .validation/pytest-case/reproseed.toml --allow-exec
python -m reproseed reduce --config .validation/pytest-case/reproseed.toml --out .validation/pytest-bundle --allow-exec --progress --events .validation/pytest-events.jsonl
python -m reproseed inspect .validation/pytest-bundle
python -m reproseed inspect .validation/pytest-bundle --format text
python -m reproseed replay .validation/pytest-bundle --allow-exec
```

These argument arrays also work in PowerShell. Choose fresh case, bundle and event
paths each time. Add `--small` only to `prepare.py` for a ten-row CI smoke case;
the full deterministic fixture contains 2,430 user rows. Both include the genuine
cross-project name collision, which needs one owner, two projects and two entries.
The finite 400-invocation budget and ten-second per-invocation timeout account for
pytest startup; production defaults are unchanged. The reducer still needs three
fresh baseline/final confirmations and two confirmations per accepted reduction.

The exact nodeid, exception type and message are a deliberate contract. Setup and
teardown must pass, and skip/xfail, collection errors, other failures and pytest
infrastructure errors are unresolved. A test's dependence on `reproseed_db` binds
the disposable SQLite path; the test author must actually use its data correctly.
Static diagnosis validates the normal configuration and SQLite model without
importing this test or pytest. The bridge itself requires `--allow-exec`.

Only `app.py`, `test_export.py` and `pytest-target.toml` enter the bundle as explicit
assets. Replaying elsewhere requires an installed M2g-capable ReproSeed build plus
the supported pytest dependency in the oracle interpreter. Those installed
dependencies are external to the version-1 manifest; the manifest authenticates
their bundled payload bytes, not the installed interpreter or dependency versions.
Tests and local fixtures execute with normal OS permissions. Plugin isolation is
not a sandbox, and reduction is not anonymization.

The installed-wheel recipe `tests/pytest_bridge_smoke.py` measures a complete small
workflow, renamed original paths, relocated replay, input/bundle hashes and a
separate fixed-exporter counterfactual. Its `--full` option additionally starts
from all 2,430 rows and requires at most eight retained rows. The correction is
made only in another owned case, never in a verified bundle.
