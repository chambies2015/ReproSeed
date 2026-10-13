# Duplicate export demo

The application in `app.py` exports entries into a dictionary keyed by name
globally. Two entries with the same name in different projects collide, so one
entry disappears. `oracle.py` calls that application, compares exported IDs
with database IDs, and emits `REPROSEED_DUPLICATE_EXPORT` with exit code 42
only when an omitted entry has a retained name match from a different project.
Other export discrepancies return a different failure.

The deterministic generator creates 6 owners, 24 projects, and 2,400 entries:
2,430 synthetic rows in total. Ordinary names are unique. The final two entries
share a name and belong to two projects owned by the same owner. A useful
reproduction needs one owner, two projects, and those two entries.

From the repository root after installing the development environment:

```console
uv run python examples/duplicate_export/generate.py
uv run reproseed reduce --config examples/duplicate_export/reproseed.toml --out duplicate-bundle --allow-exec
uv run reproseed inspect duplicate-bundle
uv run reproseed replay duplicate-bundle --allow-exec
```

The generator refuses to overwrite an existing fixture. Use an unused output
path or deliberately remove your previous synthetic fixture before regenerating.
The config resolves the fixture and supporting files relative to its own
directory. The output directory must not already exist.

You can inspect the application's original export with
`uv run python examples/duplicate_export/app.py examples/duplicate_export/fixture.sqlite3`.
The oracle itself returns 42 on this failure; successful ReproSeed reduction
and replay commands return 0. ReproSeed requires `--allow-exec` because the
configured code runs with your operating-system permissions.

The bundle includes the application and oracle. It can be moved elsewhere and
replayed with Python and an installed ReproSeed CLI. This is reduction, not
anonymization: retained values, schema, and included code remain in the bundle.
The result is a confirmed small reproduction, with no global minimality claim.
