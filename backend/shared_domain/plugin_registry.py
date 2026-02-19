"""Deterministic plugin registry signing and verification helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

DEFAULT_PLUGIN_REGISTRY_PATH = "plugins/registry.json"
DEFAULT_PLUGIN_SIGNING_KEY = "schemapilot-plugin-signing-key-dev-v1"
DEFAULT_PLUGIN_KEY_ID = "local-dev-v1"
PLUGIN_SIGNATURE_ALGORITHM = "hmac-sha256"
ALLOWED_CONNECTOR_TIERS = {"recommended", "community"}


def validate_plugin_registry(
    root: Path,
    *,
    registry_path: str = DEFAULT_PLUGIN_REGISTRY_PATH,
    signing_key: str = DEFAULT_PLUGIN_SIGNING_KEY,
) -> list[str]:
    """Validate plugin registry metadata including signatures."""

    payload, errors = _load_registry(root=root, registry_path=registry_path)
    if payload is None:
        return errors
    entries_raw = payload.get("plugins", [])
    if not isinstance(entries_raw, list):
        errors.append("plugins must be a list")
        return errors
    seen: set[str] = set()
    for index, raw_entry in enumerate(entries_raw):
        prefix = f"plugins[{index}]"
        if not isinstance(raw_entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = str(raw_entry.get("name", "")).strip()
        entrypoint = str(raw_entry.get("entrypoint", "")).strip()
        if not name:
            errors.append(f"{prefix}.name is required")
        if not entrypoint:
            errors.append(f"{prefix}.entrypoint is required")
        tier = str(raw_entry.get("tier", "community")).strip().lower() or "community"
        if tier not in ALLOWED_CONNECTOR_TIERS:
            errors.append(
                f"{prefix}.tier must be one of {sorted(ALLOWED_CONNECTOR_TIERS)}, got {tier!r}"
            )
        if name:
            if name in seen:
                errors.append(f"duplicate plugin name: {name}")
            seen.add(name)
        if not name or not entrypoint:
            continue
        errors.extend(
            verify_plugin_registry_entry(
                plugin_name=name,
                runtime_entrypoint=entrypoint,
                registry_entry=raw_entry,
                signing_key=signing_key,
            )
        )
    return sorted(set(errors))


def sign_plugin_registry(
    root: Path,
    *,
    registry_path: str = DEFAULT_PLUGIN_REGISTRY_PATH,
    signing_key: str = DEFAULT_PLUGIN_SIGNING_KEY,
    key_id: str = DEFAULT_PLUGIN_KEY_ID,
) -> list[str]:
    """Write deterministic plugin hash/signature metadata to registry."""

    payload, errors = _load_registry(root=root, registry_path=registry_path)
    if payload is None:
        return errors
    entries_raw = payload.get("plugins", [])
    if not isinstance(entries_raw, list):
        return ["plugins must be a list"]
    seen: set[str] = set()
    for index, raw_entry in enumerate(entries_raw):
        prefix = f"plugins[{index}]"
        if not isinstance(raw_entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = str(raw_entry.get("name", "")).strip()
        entrypoint = str(raw_entry.get("entrypoint", "")).strip()
        if not name:
            errors.append(f"{prefix}.name is required")
            continue
        if not entrypoint:
            errors.append(f"{prefix}.entrypoint is required")
            continue
        tier = str(raw_entry.get("tier", "community")).strip().lower() or "community"
        if tier not in ALLOWED_CONNECTOR_TIERS:
            errors.append(
                f"{prefix}.tier must be one of {sorted(ALLOWED_CONNECTOR_TIERS)}, got {tier!r}"
            )
            continue
        if name in seen:
            errors.append(f"duplicate plugin name: {name}")
            continue
        seen.add(name)
        raw_entry["tier"] = tier
        plugin_hash = _render_hash(_compute_entrypoint_hash(entrypoint))
        raw_entry["hash"] = plugin_hash
        raw_entry["signature"] = {
            "algorithm": PLUGIN_SIGNATURE_ALGORITHM,
            "key_id": key_id,
            "value": _compute_signature(
                plugin_name=name,
                entrypoint=entrypoint,
                plugin_hash=plugin_hash,
                signing_key=signing_key,
            ),
        }
    if errors:
        return sorted(set(errors))
    registry_file = _resolve_registry_path(root=root, registry_path=registry_path)
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(_canonical_json(payload, indent=2), encoding="utf-8")
    return []


def load_plugin_registry_entries(
    root: Path,
    *,
    registry_path: str = DEFAULT_PLUGIN_REGISTRY_PATH,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Load plugin registry entries keyed by plugin name."""

    payload, errors = _load_registry(root=root, registry_path=registry_path)
    if payload is None:
        return {}, errors
    entries_raw = payload.get("plugins", [])
    if not isinstance(entries_raw, list):
        return {}, ["plugins must be a list"]
    entries: dict[str, dict[str, object]] = {}
    for index, raw_entry in enumerate(entries_raw):
        prefix = f"plugins[{index}]"
        if not isinstance(raw_entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = str(raw_entry.get("name", "")).strip()
        if not name:
            errors.append(f"{prefix}.name is required")
            continue
        tier = str(raw_entry.get("tier", "community")).strip().lower() or "community"
        if tier not in ALLOWED_CONNECTOR_TIERS:
            errors.append(
                f"{prefix}.tier must be one of {sorted(ALLOWED_CONNECTOR_TIERS)}, got {tier!r}"
            )
            continue
        raw_entry = dict(raw_entry)
        raw_entry["tier"] = tier
        if name in entries:
            errors.append(f"duplicate plugin name: {name}")
            continue
        entries[name] = dict(raw_entry)
    return entries, sorted(set(errors))


def verify_plugin_registry_entry(
    *,
    plugin_name: str,
    runtime_entrypoint: str,
    registry_entry: dict[str, Any] | None,
    signing_key: str,
) -> list[str]:
    """Verify a loaded plugin against registry hash/signature metadata."""

    errors: list[str] = []
    if registry_entry is None:
        return [f"missing_registry_entry:{plugin_name}"]
    registry_name = str(registry_entry.get("name", "")).strip()
    if registry_name != plugin_name:
        errors.append(f"registry_name_mismatch:{plugin_name}")
    declared_entrypoint = str(registry_entry.get("entrypoint", "")).strip()
    if not declared_entrypoint:
        errors.append(f"missing_entrypoint:{plugin_name}")
    elif declared_entrypoint != runtime_entrypoint:
        errors.append(f"entrypoint_mismatch:{plugin_name}")

    provided_hash = _normalize_hash(str(registry_entry.get("hash", "")).strip())
    if provided_hash is None:
        errors.append(f"missing_or_invalid_hash:{plugin_name}")
    expected_hash_raw = _compute_entrypoint_hash(runtime_entrypoint)
    expected_hash = _render_hash(expected_hash_raw)
    if provided_hash is not None and provided_hash != expected_hash_raw:
        errors.append(f"hash_mismatch:{plugin_name}")

    signature = registry_entry.get("signature")
    if not isinstance(signature, dict):
        errors.append(f"missing_signature:{plugin_name}")
        return sorted(set(errors))
    algorithm = str(signature.get("algorithm", "")).strip().lower()
    key_id = str(signature.get("key_id", "")).strip()
    value = str(signature.get("value", "")).strip()
    if algorithm != PLUGIN_SIGNATURE_ALGORITHM:
        errors.append(f"unsupported_signature_algorithm:{algorithm or '<empty>'}")
    if not key_id:
        errors.append(f"missing_signature_key_id:{plugin_name}")
    if not value:
        errors.append(f"missing_signature_value:{plugin_name}")
    if not signing_key.strip():
        errors.append("missing_signing_key")
        return sorted(set(errors))
    if errors:
        return sorted(set(errors))
    expected_signature = _compute_signature(
        plugin_name=plugin_name,
        entrypoint=runtime_entrypoint,
        plugin_hash=expected_hash,
        signing_key=signing_key,
    )
    if not hmac.compare_digest(value, expected_signature):
        errors.append(f"signature_mismatch:{plugin_name}")
    return sorted(set(errors))


def _resolve_registry_path(*, root: Path, registry_path: str) -> Path:
    candidate = Path(registry_path)
    if not candidate.is_absolute():
        candidate = root / registry_path
    return candidate.resolve()


def _load_registry(*, root: Path, registry_path: str) -> tuple[dict[str, Any] | None, list[str]]:
    registry_file = _resolve_registry_path(root=root, registry_path=registry_path)
    if not registry_file.exists():
        return None, [f"missing plugin registry file: {registry_file.as_posix()}"]
    try:
        payload = json.loads(registry_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid plugin registry json: {exc}"]
    if not isinstance(payload, dict):
        return None, ["plugin registry payload must be an object"]
    version = str(payload.get("registry_version", "")).strip()
    errors: list[str] = []
    if version != "v1":
        errors.append(f"registry_version must be v1, got {version!r}")
    return payload, errors


def _compute_entrypoint_hash(entrypoint: str) -> str:
    return hashlib.sha256(entrypoint.strip().encode("utf-8")).hexdigest()


def _normalize_hash(value: str) -> str | None:
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("sha256:"):
        normalized = normalized.removeprefix("sha256:")
    if len(normalized) != 64:
        return None
    if any(ch not in "0123456789abcdef" for ch in normalized):
        return None
    return normalized


def _render_hash(raw_hash: str) -> str:
    return f"sha256:{raw_hash}"


def _compute_signature(
    *,
    plugin_name: str,
    entrypoint: str,
    plugin_hash: str,
    signing_key: str,
) -> str:
    payload = {
        "entrypoint": entrypoint,
        "hash": plugin_hash,
        "name": plugin_name,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(signing_key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def _canonical_json(payload: object, *, indent: int) -> str:
    return json.dumps(payload, indent=indent, sort_keys=True) + "\n"
