#!/usr/bin/env python3
"""Create deterministic release artifact signatures for supply-chain gate."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runtime/supply_chain/signature.json")
    parser.add_argument(
        "--artifacts",
        nargs="*",
        default=[
            "MANIFEST.sha256",
            "runtime/release_gate/report.json",
            "runtime/supply_chain/sbom.json",
        ],
    )
    parser.add_argument(
        "--key",
        default=None,
        help="Signing key (defaults to SCHEMAPILOT_RELEASE_SIGNING_KEY env).",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    key = (args.key or __import__("os").environ.get("SCHEMAPILOT_RELEASE_SIGNING_KEY", "")).strip()
    if not key:
        key = "local-dev-release-key"
    artifact_hashes: dict[str, str] = {}
    for artifact in args.artifacts:
        path = root / artifact
        if not path.exists():
            continue
        artifact_hashes[artifact] = _sha256(path)
    canonical = json.dumps(artifact_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    payload = {
        "algorithm": "HMAC-SHA256",
        "artifacts": artifact_hashes,
        "signature": signature,
        "key_id": "schemapilot-release-v1",
    }
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    try:
        display = output_path.relative_to(root).as_posix()
    except ValueError:
        display = output_path.as_posix()
    print(display)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
