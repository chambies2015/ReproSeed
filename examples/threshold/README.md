# Aggregate threshold example

This second target uses `crates` and `parcels`, non-contiguous integer keys,
and a different failure condition. The oracle checks whether a crate's total
parcel mass exceeds 100. It emits `REPROSEED_WEIGHT_THRESHOLD` and exits 43
only when that aggregate condition holds.

The deterministic synthetic fixture contains 3 crates and 8 parcels. Two
parcels weigh 61 and 44 in the same crate. Neither is sufficient alone, so
the intended small reproduction retains that crate and both parcels.

From the repository root after installing the development environment:

```console
uv run python examples/threshold/generate.py
uv run reproseed reduce --config examples/threshold/reproseed.toml --out threshold-bundle --allow-exec
uv run reproseed inspect threshold-bundle
uv run reproseed replay threshold-bundle --allow-exec
```

The generator and reducer refuse to overwrite existing output paths. The
oracle is included explicitly, so the bundle needs only Python and an
installed ReproSeed CLI to replay after relocation. Retained values and code
are still present; reduction does not anonymize them. The same general
reduction engine handles this example and the duplicate export showcase.
