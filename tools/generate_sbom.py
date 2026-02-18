#!/usr/bin/env python3
"""Generate deterministic CycloneDX-like SBOM JSON for release gating."""

from __future__ import annotations

import argparse
import json
from importlib import metadata
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runtime/supply_chain/sbom.json")
    return parser.parse_args()


def build_sbom() -> dict[str, object]:
    components: list[dict[str, str]] = []
    for dist in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = str(dist.metadata.get("Name", "")).strip()
        version = str(dist.version).strip()
        if not name:
            continue
        components.append(
            {
                "name": name,
                "version": version,
                "type": "library",
                "purl": f"pkg:pypi/{name}@{version}",
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": components,
    }


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(build_sbom(), indent=2, sort_keys=True), encoding="utf-8")
    try:
        display = output_path.relative_to(root).as_posix()
    except ValueError:
        display = output_path.as_posix()
    print(display)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
