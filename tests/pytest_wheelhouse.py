"""Acquire only the locked pytest wheels for later offline consumer verification.

This explicit development setup command uses the network; lifecycle recipes do not.
Every wheel is checked against uv.lock before it becomes an installation input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {"pytest", "colorama", "iniconfig", "packaging", "pluggy", "pygments"}
MAX_BYTES = 8 * 1024 * 1024


def acquire(directory: Path) -> list[dict[str, str]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = [item for item in lock["package"] if item["name"] in PACKAGES]
    if {item["name"] for item in packages} != PACKAGES:
        raise ValueError("locked pytest dependencies are incomplete")
    directory.mkdir()
    records = []
    for item in packages:
        wheels = [wheel for wheel in item["wheels"] if wheel["url"].endswith("-none-any.whl")]
        if len(wheels) != 1:
            raise ValueError("expected one locked portable wheel")
        wheel = wheels[0]
        url = wheel["url"]
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(MAX_BYTES + 1)
        actual = hashlib.sha256(data).hexdigest()
        if len(data) > MAX_BYTES or "sha256:" + actual != wheel["hash"]:
            raise ValueError("locked dependency wheel hash or bound mismatch")
        name = url.rsplit("/", 1)[-1]
        with (directory / name).open("xb") as stream:
            stream.write(data)
        records.append(
            {
                "package": item["name"],
                "version": item["version"],
                "url": url,
                "filename": name,
                "sha256": actual,
            }
        )
    (directory / "provenance.json").write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(acquire(args.directory), indent=2))


if __name__ == "__main__":
    main()
