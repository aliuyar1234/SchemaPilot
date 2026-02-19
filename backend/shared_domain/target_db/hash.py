"""Deterministic hash helpers for target-db profile drift detection."""

from __future__ import annotations

import hashlib
import json


def target_db_profile_hash(
    *,
    workspace_id: str,
    name: str,
    db_type: str,
    mode: str,
    connection: dict[str, object],
    credential_refs: dict[str, object],
) -> str:
    """Canonical hash for target-db profile desired config."""
    payload = {
        "workspace_id": workspace_id,
        "name": name.strip(),
        "db_type": db_type.strip().lower(),
        "mode": mode.strip().lower(),
        "connection": dict(connection),
        "credential_refs": dict(credential_refs),
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
