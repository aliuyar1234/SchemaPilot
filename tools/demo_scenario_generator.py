#!/usr/bin/env python3
"""Generate deterministic first-hour demo data bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.shared_domain.demo_scenario import generate_demo_scenario


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        default="runtime/demo/first_hour",
        help="Output folder for generated deterministic demo scenario files.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = generate_demo_scenario(output_root=args.output_root)
    payload = result.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    manifest = Path(result.manifest_path)
    if not manifest.exists():
        print("FAIL demo scenario manifest was not written.")
        return 1
    print("PASS demo scenario generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
