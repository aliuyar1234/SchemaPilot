#!/usr/bin/env python3
"""Rotate local artifact encryption key for evidence bundle envelopes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from backend.shared_domain.artifact_crypto import (
    ArtifactCryptoConfig,
    decrypt_payload,
    encrypt_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", default="runtime/storage")
    parser.add_argument("--workspace-id", default=None)
    return parser.parse_args()


def rotate(*, storage_root: str, workspace_id: str | None) -> dict[str, object]:
    root = Path(storage_root) / "evidence_store"
    old_key = os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY", "schemapilot-artifact-key")
    old_key_id = os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY_ID", "v1")
    new_key = os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_NEW_KEY", "")
    new_key_id = os.getenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_NEW_KEY_ID", "")
    if not new_key or not new_key_id:
        raise ValueError("missing_new_artifact_encryption_key")
    source_config = ArtifactCryptoConfig(enabled=True, key_id=old_key_id, key_material=old_key)
    target_config = ArtifactCryptoConfig(enabled=True, key_id=new_key_id, key_material=new_key)
    rotated = 0
    scanned = 0
    for path in sorted(root.rglob("*.json")):
        if workspace_id and path.parent.name != workspace_id:
            continue
        scanned += 1
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        decrypted = decrypt_payload(envelope=payload, config=source_config)
        payload.pop("payload", None)
        payload.pop("ciphertext", None)
        payload.pop("encrypted", None)
        payload.pop("key_id", None)
        payload.update(encrypt_payload(payload=decrypted, config=target_config))
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        rotated += 1
    return {"status": "rotated", "scanned": scanned, "rotated": rotated}


def main() -> int:
    args = parse_args()
    report = rotate(storage_root=args.storage_root, workspace_id=args.workspace_id)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
