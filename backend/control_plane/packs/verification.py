"""Policy-pack signature verification helpers for control-plane enforcement."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.control_plane.packs.compat import evaluate_policy_pack_entry_compatibility

SIGNED_PACK_SECTION = "policy_packs"
SIGNATURE_ALGORITHM = "hmac-sha256"


@dataclass(frozen=True)
class PackVerificationResult:
    """Deterministic verification result for one pack entry."""

    workspace_profile: str
    pack_id: str
    enforcement: str
    verified: bool
    registry_path: str
    matrix_path: str
    compatibility_checked: bool
    compatibility_ok: bool
    requires_migration: bool
    compatibility_errors: tuple[str, ...]
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "workspace_profile": self.workspace_profile,
            "pack_id": self.pack_id,
            "enforcement": self.enforcement,
            "verified": self.verified,
            "registry_path": self.registry_path,
            "matrix_path": self.matrix_path,
            "compatibility_checked": self.compatibility_checked,
            "compatibility_ok": self.compatibility_ok,
            "requires_migration": self.requires_migration,
            "compatibility_errors": list(self.compatibility_errors),
            "errors": list(self.errors),
        }


def verify_policy_pack_entry(
    *,
    workspace_profile: str,
    pack_id: str,
    registry_path: str,
    matrix_path: str,
    signing_key: str,
    enforce_non_enterprise: bool,
    repo_root: Path,
) -> PackVerificationResult:
    """Verify one policy pack entry from registry using signed metadata."""

    normalized_profile = workspace_profile.strip().lower() or "unknown"
    enforce = normalized_profile == "enterprise" or enforce_non_enterprise
    enforcement = "enforce" if enforce else "warn"
    errors: list[str] = []
    compatibility_errors: list[str] = []
    compatibility_checked = False
    compatibility_ok = True
    requires_migration = False
    resolved_registry_path = (repo_root / registry_path).resolve()
    artifact_root = resolved_registry_path.parent
    payload = _load_registry_payload(resolved_registry_path, errors)
    entry: dict[str, Any] | None = None
    if payload is not None:
        raw_entries = payload.get(SIGNED_PACK_SECTION, [])
        entries = raw_entries if isinstance(raw_entries, list) else []
        entry = next(
            (
                row
                for row in entries
                if isinstance(row, dict) and str(row.get("pack_id", "")).strip() == pack_id
            ),
            None,
        )
        if entry is None:
            errors.append(f"missing_registry_entry:{pack_id}")
    if entry is not None:
        signature_errors = _verify_registry_entry(
            entry=entry,
            repo_root=repo_root,
            artifact_root=artifact_root,
            signing_key=signing_key,
        )
        errors.extend(signature_errors)
        if not signature_errors:
            compatibility = evaluate_policy_pack_entry_compatibility(
                entry=entry,
                matrix_path=matrix_path,
                repo_root=repo_root,
            )
            compatibility_checked = compatibility.checked
            compatibility_ok = compatibility.compatible
            requires_migration = compatibility.requires_migration
            compatibility_errors = list(compatibility.errors)
            errors.extend(compatibility_errors)
    return PackVerificationResult(
        workspace_profile=normalized_profile,
        pack_id=pack_id,
        enforcement=enforcement,
        verified=not errors,
        registry_path=registry_path,
        matrix_path=matrix_path,
        compatibility_checked=compatibility_checked,
        compatibility_ok=compatibility_ok,
        requires_migration=requires_migration,
        compatibility_errors=tuple(sorted(set(compatibility_errors))),
        errors=tuple(sorted(errors)),
    )


def _load_registry_payload(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        errors.append(f"missing_registry_file:{path.as_posix()}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append(f"invalid_registry_json:{path.as_posix()}")
        return None
    if not isinstance(payload, dict):
        errors.append("invalid_registry_payload")
        return None
    if str(payload.get("registry_version", "")).strip() != "v1":
        errors.append("unsupported_registry_version")
    return payload


def _verify_registry_entry(
    *,
    entry: dict[str, Any],
    repo_root: Path,
    artifact_root: Path,
    signing_key: str,
) -> list[str]:
    errors: list[str] = []
    path = str(entry.get("path", "")).strip()
    version = str(entry.get("version", "")).strip()
    schema_version = str(entry.get("schema_version", "")).strip() or "v1"
    semantic_schema_version = (
        str(entry.get("semantic_schema_version", "")).strip() or schema_version
    )
    compat_range = str(entry.get("compat_range", "")).strip()
    migration_available = bool(entry.get("migration_available", False))
    pack_id = str(entry.get("pack_id", "")).strip()
    if not path:
        errors.append(f"missing_path:{pack_id or '<unknown>'}")
        return errors
    artifact = _resolve_artifact_path(repo_root=repo_root, artifact_root=artifact_root, path=path)
    if not artifact.exists():
        errors.append(f"missing_artifact:{path}")
        return errors
    signature = entry.get("signature")
    if not isinstance(signature, dict):
        errors.append(f"missing_signature:{pack_id or '<unknown>'}")
        return errors
    algorithm = str(signature.get("algorithm", "")).strip().lower()
    key_id = str(signature.get("key_id", "")).strip()
    provided = str(signature.get("value", "")).strip()
    if algorithm != SIGNATURE_ALGORITHM:
        errors.append(f"unsupported_signature_algorithm:{algorithm or '<empty>'}")
    if not key_id:
        errors.append("missing_signature_key_id")
    if not provided:
        errors.append("missing_signature_value")
    if not signing_key.strip():
        errors.append("missing_signing_key")
        return errors
    if errors:
        return errors
    expected = _compute_signature(
        artifact=artifact,
        pack_id=pack_id,
        path=path,
        version=version,
        schema_version=schema_version,
        semantic_schema_version=semantic_schema_version,
        compat_range=compat_range,
        migration_available=migration_available,
        signing_key=signing_key,
    )
    if not hmac.compare_digest(provided, expected):
        errors.append(f"signature_mismatch:{pack_id}")
    return errors


def _compute_signature(
    *,
    artifact: Path,
    pack_id: str,
    path: str,
    version: str,
    schema_version: str,
    semantic_schema_version: str,
    compat_range: str,
    migration_available: bool,
    signing_key: str,
) -> str:
    artifact_checksum = hashlib.sha256(_artifact_canonical_bytes(artifact)).hexdigest()
    signature_payload = {
        "artifact_checksum": artifact_checksum,
        "compat_range": compat_range,
        "migration_available": migration_available,
        "pack_id": pack_id,
        "path": path,
        "schema_version": schema_version,
        "semantic_schema_version": semantic_schema_version,
        "section": SIGNED_PACK_SECTION,
        "version": version,
    }
    canonical = json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(signing_key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def _artifact_canonical_bytes(path: Path) -> bytes:
    if path.suffix.lower() != ".json":
        return path.read_bytes()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return path.read_bytes()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def _resolve_artifact_path(*, repo_root: Path, artifact_root: Path, path: str) -> Path:
    entry_path = Path(path)
    if entry_path.is_absolute():
        return entry_path.resolve()
    primary = (artifact_root / entry_path).resolve()
    if primary.exists():
        return primary
    fallback = (repo_root / entry_path).resolve()
    if fallback.exists():
        return fallback
    return primary
