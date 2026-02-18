#!/usr/bin/env python3
"""Validate pack registry integrity and referenced artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default="packs/registry.json",
        help="Path to registry file.",
    )
    return parser.parse_args()


def validate_pack_registry(root: Path, *, registry_path: str) -> list[str]:
    registry_file = root / registry_path
    if not registry_file.exists():
        return [f"missing registry file: {registry_file.as_posix()}"]
    try:
        payload = json.loads(registry_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid registry json: {exc}"]
    if not isinstance(payload, dict):
        return ["registry payload must be an object"]
    errors: list[str] = []
    version = payload.get("registry_version")
    if version != "v1":
        errors.append(f"registry_version must be v1, got {version!r}")
    for section in ("policy_packs", "semantic_packs", "connector_examples"):
        entries = payload.get(section, [])
        if not isinstance(entries, list):
            errors.append(f"{section} must be a list")
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(f"{section}[{index}] must be an object")
                continue
            errors.extend(_validate_registry_entry(root=root, section=section, entry=entry))
    return errors


def _validate_registry_entry(*, root: Path, section: str, entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pack_id = str(entry.get("pack_id", "")).strip()
    version = str(entry.get("version", "")).strip()
    path = str(entry.get("path", "")).strip()
    if not pack_id:
        errors.append(f"{section}: missing pack_id")
    if not version:
        errors.append(f"{section}: missing version for {pack_id or '<unknown>'}")
    if not path:
        errors.append(f"{section}: missing path for {pack_id or '<unknown>'}")
        return errors
    target = root / path
    if not target.exists():
        errors.append(f"{section}: missing artifact {target.as_posix()}")
    return errors


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    errors = validate_pack_registry(root, registry_path=args.registry)
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("PASS CHK-PACK-REGISTRY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
