"""Immutable evidence bundle storage helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from backend.shared_domain.artifact_crypto import (
    decrypt_payload,
    encrypt_payload,
    load_artifact_crypto_config,
)
from backend.shared_domain.errors import NotFoundError

EVIDENCE_URI_PREFIX = "evidence://"


@dataclass(frozen=True)
class StoredEvidenceBundle:
    """Metadata for a stored evidence bundle."""

    evidence_id: str
    workspace_id: str
    evidence_bundle_uri: str
    content_hash: str
    path: str


def store_evidence_bundle(
    *,
    workspace_id: str,
    payload: dict[str, object],
    storage_root: str,
    bundle_type: str = "generic",
    evidence_id: str | None = None,
) -> StoredEvidenceBundle:
    """Write evidence immutably and return a stable URI + hash."""
    canonical_payload = _canonical_json(payload)
    content_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    safe_bundle_type = bundle_type.strip().lower().replace(" ", "_") or "generic"
    bundle_id = evidence_id or f"{safe_bundle_type}_{content_hash[:24]}"
    bundle_root = Path(storage_root) / "evidence_store" / workspace_id
    bundle_root.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_root / f"{bundle_id}.json"

    envelope: dict[str, object] = {
        "evidence_id": bundle_id,
        "workspace_id": workspace_id,
        "bundle_type": safe_bundle_type,
        "content_hash": content_hash,
    }
    envelope.update(
        encrypt_payload(
            payload=payload,
            config=load_artifact_crypto_config(),
        )
    )
    envelope_json = json.dumps(envelope, indent=2, sort_keys=True)
    if bundle_path.exists():
        existing_json = bundle_path.read_text(encoding="utf-8")
        if existing_json != envelope_json:
            raise ValueError(
                "Evidence bundle immutability violation: existing bundle content differs."
            )
    else:
        bundle_path.write_text(envelope_json, encoding="utf-8")

    return StoredEvidenceBundle(
        evidence_id=bundle_id,
        workspace_id=workspace_id,
        evidence_bundle_uri=build_evidence_uri(workspace_id=workspace_id, evidence_id=bundle_id),
        content_hash=content_hash,
        path=bundle_path.as_posix(),
    )


def load_evidence_bundle(
    *, workspace_id: str, evidence_id: str, storage_root: str
) -> dict[str, object]:
    """Load one evidence bundle envelope from storage."""
    bundle_path = Path(storage_root) / "evidence_store" / workspace_id / f"{evidence_id}.json"
    if not bundle_path.exists():
        raise NotFoundError(
            "Evidence bundle not found.",
            details={"workspace_id": workspace_id, "evidence_id": evidence_id},
        )
    raw = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Evidence bundle content is invalid.")
    payload = decrypt_payload(envelope=raw, config=load_artifact_crypto_config())
    normalized = {str(key): value for key, value in raw.items() if key != "payload"}
    normalized["payload"] = payload
    return normalized


def resolve_evidence_uri(uri: str, *, storage_root: str) -> dict[str, object]:
    """Resolve evidence URI to workspace/evidence IDs and on-disk path."""
    workspace_id, evidence_id = parse_evidence_uri(uri)
    path = Path(storage_root) / "evidence_store" / workspace_id / f"{evidence_id}.json"
    return {
        "workspace_id": workspace_id,
        "evidence_id": evidence_id,
        "path": path.as_posix(),
    }


def build_evidence_uri(*, workspace_id: str, evidence_id: str) -> str:
    """Build canonical evidence URI."""
    return f"{EVIDENCE_URI_PREFIX}{workspace_id}/{evidence_id}"


def parse_evidence_uri(uri: str) -> tuple[str, str]:
    """Parse evidence URI into workspace and evidence IDs."""
    if not uri.startswith(EVIDENCE_URI_PREFIX):
        raise ValueError("Evidence URI must start with evidence://.")
    remainder = uri.removeprefix(EVIDENCE_URI_PREFIX).strip("/")
    parts = remainder.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Evidence URI must be evidence://<workspace_id>/<evidence_id>.")
    return parts[0], parts[1]


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
