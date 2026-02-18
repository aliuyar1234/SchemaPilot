#!/usr/bin/env python3
"""Validate policy-pack invariants before apply."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.shared_domain.policy_pack_tests import evaluate_policy_pack_invariants


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        default="backend/shared_domain/policy_packs.json",
        help="Policy pack JSON file path.",
    )
    parser.add_argument("--pack-id", default=None, help="Validate only one policy pack id.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / args.file
    payload = json.loads(path.read_text(encoding="utf-8"))
    packs = payload if isinstance(payload, list) else []
    failures: list[str] = []
    for pack in packs:
        if not isinstance(pack, dict):
            failures.append("pack_payload_invalid")
            continue
        pack_id = str(pack.get("id", "")).strip()
        if args.pack_id and pack_id != args.pack_id:
            continue
        for failure in evaluate_policy_pack_invariants(pack):
            failures.append(f"{pack_id}:{failure}")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("PASS CHK-POLICY-PACK-TEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
