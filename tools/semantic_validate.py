#!/usr/bin/env python3
"""Validate semantic manifest JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.shared_domain.semantic import semantic_manifest_checksum, validate_semantic_manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to semantic manifest JSON file.")
    parser.add_argument(
        "--workspace-id",
        dest="workspace_id",
        default=None,
        help="Optional expected workspace ID for strict validation.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    manifest_path = Path(args.manifest).resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"FAIL semantic manifest file not found: {manifest_path.as_posix()}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"FAIL semantic manifest JSON parse error: {exc}")
        return 1

    if not isinstance(payload, dict):
        print("FAIL semantic manifest must be a JSON object.")
        return 1
    try:
        normalized = validate_semantic_manifest(payload, expected_workspace_id=args.workspace_id)
    except ValueError as exc:
        print(f"FAIL semantic manifest validation: {exc}")
        return 1
    checksum = semantic_manifest_checksum(normalized)
    print("PASS semantic manifest validation")
    print(json.dumps({"checksum": checksum}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
