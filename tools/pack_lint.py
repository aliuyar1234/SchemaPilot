#!/usr/bin/env python3
"""Validate pack registry, signatures, and schema compatibility metadata."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any, TypedDict

from backend.shared_domain.semantic_schema_versions import default_compat_range

DEFAULT_REGISTRY_PATH = "packs/registry.json"
DEFAULT_MATRIX_PATH = "packs/compatibility_matrix.json"
DEFAULT_SIGNING_KEY = "schemapilot-pack-signing-key-dev-v1"
DEFAULT_KEY_ID = "local-dev-v1"
SIGNATURE_ALGORITHM = "hmac-sha256"
SIGNED_SECTIONS = ("policy_packs", "semantic_packs", "template_packs")
VERSION_PATTERN = re.compile(r"^v[0-9]+$")
COMPARATOR_PATTERN = re.compile(r"^(>=|<=|>|<|==)?\s*([0-9]+(?:\.[0-9]+){0,2})$")


class EntryFields(TypedDict):
    errors: list[str]
    pack_id: str
    version: str
    path: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help="Path to registry file.",
    )
    parser.add_argument(
        "--matrix",
        default=DEFAULT_MATRIX_PATH,
        help="Path to compatibility matrix file.",
    )
    parser.add_argument(
        "--signing-key",
        default=os.getenv("SCHEMAPILOT_PACK_SIGNING_KEY", DEFAULT_SIGNING_KEY),
        help="Signing key used for HMAC verification/signing.",
    )
    parser.add_argument(
        "--key-id",
        default=DEFAULT_KEY_ID,
        help="Signer key identifier written into signature metadata.",
    )
    parser.add_argument(
        "--write-signatures",
        action="store_true",
        help="Write deterministic signatures for signed pack sections.",
    )
    return parser.parse_args()


def validate_pack_registry(
    root: Path,
    *,
    registry_path: str,
    matrix_path: str = DEFAULT_MATRIX_PATH,
    signing_key: str = DEFAULT_SIGNING_KEY,
) -> list[str]:
    payload, errors = _load_registry(root=root, registry_path=registry_path)
    artifact_root = _resolve_registry_artifact_root(root=root, registry_path=registry_path)
    matrix, matrix_errors = load_compatibility_matrix(root, matrix_path=matrix_path)
    errors.extend(matrix_errors)
    if payload is None or matrix is None:
        return errors

    sections = _extract_sections(payload)
    for section, entries in sections.items():
        if not isinstance(entries, list):
            errors.append(f"{section} must be a list")
            continue
        for index, raw_entry in enumerate(entries):
            if not isinstance(raw_entry, dict):
                errors.append(f"{section}[{index}] must be an object")
                continue
            entry_errors = _validate_registry_entry(
                root=root,
                artifact_root=artifact_root,
                matrix=matrix,
                section=section,
                entry=raw_entry,
                signing_key=signing_key,
            )
            errors.extend(entry_errors)
    return errors


def sign_pack_registry(
    root: Path,
    *,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    matrix_path: str = DEFAULT_MATRIX_PATH,
    signing_key: str = DEFAULT_SIGNING_KEY,
    key_id: str = DEFAULT_KEY_ID,
) -> list[str]:
    payload, errors = _load_registry(root=root, registry_path=registry_path)
    artifact_root = _resolve_registry_artifact_root(root=root, registry_path=registry_path)
    matrix, matrix_errors = load_compatibility_matrix(root, matrix_path=matrix_path)
    errors.extend(matrix_errors)
    if payload is None or matrix is None:
        return errors

    for section in SIGNED_SECTIONS:
        entries = payload.get(section, [])
        if not isinstance(entries, list):
            errors.append(f"{section} must be a list")
            continue
        current_schema = _section_current_version(matrix, section=section)
        runtime_version = str(matrix.get("runtime_version", "")).strip() or "0.1.0"
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                errors.append(f"{section}: entry must be an object")
                continue
            fields = _extract_entry_fields(raw_entry)
            if fields["errors"]:
                errors.extend([f"{section}: {message}" for message in fields["errors"]])
                continue
            path = str(fields["path"])
            target = _resolve_artifact_path(
                root=root,
                artifact_root=artifact_root,
                path=path,
            )
            if not target.exists():
                errors.append(f"{section}: missing artifact {target.as_posix()}")
                continue
            schema_version = _infer_schema_version(
                entry=raw_entry,
                target=target,
                default_version=_section_current_version(matrix, section=section),
            )
            if not _version_supported(matrix, section=section, schema_version=schema_version):
                errors.append(
                    f"{section}: schema_version {schema_version!r} is not supported for "
                    f"{fields['pack_id']}"
                )
                continue
            raw_entry["schema_version"] = schema_version
            raw_entry["semantic_schema_version"] = schema_version
            compat_range = _normalize_compat_range(
                value=str(raw_entry.get("compat_range", "")).strip(),
                runtime_version=runtime_version,
            )
            if compat_range is None:
                errors.append(f"{section}: invalid compat_range for {fields['pack_id']}")
                continue
            raw_entry["compat_range"] = compat_range
            raw_entry["migration_available"] = (
                schema_version != current_schema
                and _has_migration_path(
                    matrix,
                    section=section,
                    from_schema_version=schema_version,
                    to_schema_version=current_schema,
                )
            )
            raw_entry["signature"] = {
                "algorithm": SIGNATURE_ALGORITHM,
                "key_id": key_id,
                "value": _compute_signature(
                    root=root,
                    artifact_root=artifact_root,
                    section=section,
                    entry=raw_entry,
                    signing_key=signing_key,
                ),
            }

    if errors:
        return errors

    registry_file = root / registry_path
    registry_file.write_text(_canonical_json(payload, indent=2), encoding="utf-8")
    return []


def load_compatibility_matrix(
    root: Path,
    *,
    matrix_path: str = DEFAULT_MATRIX_PATH,
) -> tuple[dict[str, Any] | None, list[str]]:
    matrix_file = root / matrix_path
    if not matrix_file.exists():
        return None, [f"missing compatibility matrix file: {matrix_file.as_posix()}"]
    try:
        payload = json.loads(matrix_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid compatibility matrix json: {exc}"]
    if not isinstance(payload, dict):
        return None, ["compatibility matrix payload must be an object"]

    errors: list[str] = []
    matrix_version = str(payload.get("matrix_version", "")).strip()
    if matrix_version != "v1":
        errors.append(f"matrix_version must be v1, got {matrix_version!r}")

    sections = payload.get("sections")
    if not isinstance(sections, dict):
        errors.append("sections must be an object")
    else:
        for section, section_payload in sections.items():
            if not isinstance(section_payload, dict):
                errors.append(f"sections.{section} must be an object")
                continue
            current = str(section_payload.get("current_schema_version", "")).strip()
            supported = section_payload.get("supported_schema_versions")
            if not VERSION_PATTERN.match(current):
                errors.append(f"sections.{section}.current_schema_version must match v<integer>")
            if not isinstance(supported, list) or not supported:
                errors.append(
                    f"sections.{section}.supported_schema_versions must be a non-empty list"
                )
                continue
            normalized_supported = [str(item).strip() for item in supported]
            if any(not VERSION_PATTERN.match(value) for value in normalized_supported):
                errors.append(
                    f"sections.{section}.supported_schema_versions contains invalid schema versions"
                )
            if current and current not in normalized_supported:
                errors.append(
                    f"sections.{section}.current_schema_version must appear in "
                    "supported_schema_versions"
                )

    migrations = payload.get("migrations")
    if not isinstance(migrations, list):
        errors.append("migrations must be a list")
    else:
        for index, migration in enumerate(migrations):
            if not isinstance(migration, dict):
                errors.append(f"migrations[{index}] must be an object")
                continue
            section = str(migration.get("section", "")).strip()
            from_version = str(migration.get("from_schema_version", "")).strip()
            to_version = str(migration.get("to_schema_version", "")).strip()
            if not section:
                errors.append(f"migrations[{index}].section is required")
            if not VERSION_PATTERN.match(from_version):
                errors.append(f"migrations[{index}].from_schema_version must match v<integer>")
            if not VERSION_PATTERN.match(to_version):
                errors.append(f"migrations[{index}].to_schema_version must match v<integer>")

    return (payload if not errors else payload), errors


def _load_registry(
    *,
    root: Path,
    registry_path: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    registry_file = root / registry_path
    if not registry_file.exists():
        return None, [f"missing registry file: {registry_file.as_posix()}"]
    try:
        payload = json.loads(registry_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid registry json: {exc}"]
    if not isinstance(payload, dict):
        return None, ["registry payload must be an object"]

    errors: list[str] = []
    version = payload.get("registry_version")
    if version != "v1":
        errors.append(f"registry_version must be v1, got {version!r}")
    return payload, errors


def _extract_sections(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        section: entries
        for section, entries in payload.items()
        if section.endswith("_packs") or section.endswith("_examples")
    }


def _validate_registry_entry(
    *,
    root: Path,
    artifact_root: Path,
    matrix: dict[str, Any],
    section: str,
    entry: dict[str, Any],
    signing_key: str,
) -> list[str]:
    errors: list[str] = []
    fields = _extract_entry_fields(entry)
    pack_id = str(fields["pack_id"])
    path = str(fields["path"])
    if fields["errors"]:
        errors.extend([f"{section}: {message}" for message in fields["errors"]])
    if not path:
        return errors

    target = _resolve_artifact_path(
        root=root,
        artifact_root=artifact_root,
        path=path,
    )
    if not target.exists():
        errors.append(f"{section}: missing artifact {target.as_posix()}")
        return errors

    current_schema = _section_current_version(matrix, section=section)
    runtime_version = str(matrix.get("runtime_version", "")).strip() or "0.1.0"
    schema_version = _infer_schema_version(
        entry=entry,
        target=target,
        default_version=current_schema,
    )
    if not _version_supported(matrix, section=section, schema_version=schema_version):
        errors.append(
            f"{section}: schema_version {schema_version!r} is not supported for "
            f"{pack_id or '<unknown>'}"
        )
    elif schema_version != current_schema and not _has_migration_path(
        matrix,
        section=section,
        from_schema_version=schema_version,
        to_schema_version=current_schema,
    ):
        errors.append(
            f"{section}: missing migration path {schema_version}->{current_schema} for "
            f"{pack_id or '<unknown>'}"
        )

    if section in SIGNED_SECTIONS:
        semantic_schema_version = str(entry.get("semantic_schema_version", "")).strip()
        if not semantic_schema_version:
            errors.append(
                f"{section}: missing semantic_schema_version for {pack_id or '<unknown>'}"
            )
        elif semantic_schema_version != schema_version:
            errors.append(
                f"{section}: semantic_schema_version mismatch for {pack_id or '<unknown>'}"
            )

        compat_range = str(entry.get("compat_range", "")).strip()
        if not compat_range:
            errors.append(f"{section}: missing compat_range for {pack_id or '<unknown>'}")
        else:
            parsed_range = _parse_compat_range(compat_range)
            if parsed_range is None:
                errors.append(f"{section}: invalid compat_range for {pack_id or '<unknown>'}")
            elif not _version_matches(runtime_version, parsed_range):
                errors.append(
                    f"{section}: compat_range excludes runtime {runtime_version} for "
                    f"{pack_id or '<unknown>'}"
                )

        migration_available_raw = entry.get("migration_available")
        if not isinstance(migration_available_raw, bool):
            errors.append(
                f"{section}: missing migration_available for {pack_id or '<unknown>'}"
            )
        else:
            expected_migration_available = (
                schema_version != current_schema
                and _has_migration_path(
                    matrix,
                    section=section,
                    from_schema_version=schema_version,
                    to_schema_version=current_schema,
                )
            )
            if migration_available_raw != expected_migration_available:
                errors.append(
                    f"{section}: inconsistent migration_available for {pack_id or '<unknown>'}"
                )

    if section in SIGNED_SECTIONS:
        signature = entry.get("signature")
        if not isinstance(signature, dict):
            errors.append(f"{section}: missing signature for {pack_id or '<unknown>'}")
            return errors
        algorithm = str(signature.get("algorithm", "")).strip()
        key_id = str(signature.get("key_id", "")).strip()
        value = str(signature.get("value", "")).strip()
        if algorithm != SIGNATURE_ALGORITHM:
            errors.append(
                f"{section}: unsupported signature algorithm {algorithm!r} for "
                f"{pack_id or '<unknown>'}"
            )
        if not key_id:
            errors.append(f"{section}: missing signature key_id for {pack_id or '<unknown>'}")
        if not value:
            errors.append(f"{section}: missing signature value for {pack_id or '<unknown>'}")
        if algorithm == SIGNATURE_ALGORITHM and value:
            expected = _compute_signature(
                root=root,
                artifact_root=artifact_root,
                section=section,
                entry={
                    **entry,
                    "schema_version": schema_version,
                    "semantic_schema_version": str(
                        entry.get("semantic_schema_version", schema_version)
                    ).strip()
                    or schema_version,
                    "compat_range": str(entry.get("compat_range", "")).strip(),
                    "migration_available": bool(entry.get("migration_available", False)),
                },
                signing_key=signing_key,
            )
            if not hmac.compare_digest(value, expected):
                errors.append(f"{section}: signature verification failed for {pack_id}")
    return errors


def _extract_entry_fields(entry: dict[str, Any]) -> EntryFields:
    errors: list[str] = []
    pack_id = str(entry.get("pack_id", "")).strip()
    version = str(entry.get("version", "")).strip()
    path = str(entry.get("path", "")).strip()
    if not pack_id:
        errors.append("missing pack_id")
    if not version:
        errors.append(f"missing version for {pack_id or '<unknown>'}")
    if not path:
        errors.append(f"missing path for {pack_id or '<unknown>'}")
    return {
        "errors": errors,
        "pack_id": pack_id,
        "version": version,
        "path": path,
    }


def _infer_schema_version(*, entry: dict[str, Any], target: Path, default_version: str) -> str:
    from_entry = str(entry.get("schema_version", "")).strip()
    if from_entry:
        return from_entry
    if target.suffix.lower() == ".json":
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default_version
        if isinstance(payload, dict):
            from_payload = str(payload.get("schema_version", "")).strip()
            if from_payload:
                return from_payload
    return default_version


def _section_current_version(matrix: dict[str, Any], *, section: str) -> str:
    section_payload = matrix.get("sections", {}).get(section, {})
    if isinstance(section_payload, dict):
        current = str(section_payload.get("current_schema_version", "")).strip()
        if current:
            return current
    return "v1"


def _version_supported(matrix: dict[str, Any], *, section: str, schema_version: str) -> bool:
    section_payload = matrix.get("sections", {}).get(section, {})
    if not isinstance(section_payload, dict):
        return False
    supported = section_payload.get("supported_schema_versions", [])
    if not isinstance(supported, list):
        return False
    normalized = {str(item).strip() for item in supported}
    return schema_version in normalized


def _has_migration_path(
    matrix: dict[str, Any],
    *,
    section: str,
    from_schema_version: str,
    to_schema_version: str,
) -> bool:
    migrations = matrix.get("migrations", [])
    if not isinstance(migrations, list):
        return False
    for migration in migrations:
        if not isinstance(migration, dict):
            continue
        if (
            str(migration.get("section", "")).strip() == section
            and str(migration.get("from_schema_version", "")).strip() == from_schema_version
            and str(migration.get("to_schema_version", "")).strip() == to_schema_version
        ):
            return True
    return False


def _compute_signature(
    *,
    root: Path,
    artifact_root: Path,
    section: str,
    entry: dict[str, Any],
    signing_key: str,
) -> str:
    pack_id = str(entry.get("pack_id", "")).strip()
    version = str(entry.get("version", "")).strip()
    path = str(entry.get("path", "")).strip()
    schema_version = str(entry.get("schema_version", "")).strip() or "v1"
    semantic_schema_version = (
        str(entry.get("semantic_schema_version", "")).strip() or schema_version
    )
    compat_range = str(entry.get("compat_range", "")).strip()
    migration_available = bool(entry.get("migration_available", False))
    artifact_checksum = _artifact_checksum(
        _resolve_artifact_path(
            root=root,
            artifact_root=artifact_root,
            path=path,
        )
    )
    signature_input = _canonical_json_bytes(
        {
            "artifact_checksum": artifact_checksum,
            "compat_range": compat_range,
            "migration_available": migration_available,
            "pack_id": pack_id,
            "path": path,
            "schema_version": schema_version,
            "semantic_schema_version": semantic_schema_version,
            "section": section,
            "version": version,
        }
    )
    return hmac.new(signing_key.encode("utf-8"), signature_input, hashlib.sha256).hexdigest()


def _artifact_checksum(target: Path) -> str:
    canonical_bytes = _artifact_canonical_bytes(target)
    return hashlib.sha256(canonical_bytes).hexdigest()


def _resolve_registry_artifact_root(*, root: Path, registry_path: str) -> Path:
    registry_file = Path(registry_path)
    if not registry_file.is_absolute():
        registry_file = root / registry_path
    return registry_file.resolve().parent


def _resolve_artifact_path(*, root: Path, artifact_root: Path, path: str) -> Path:
    entry_path = Path(path)
    if entry_path.is_absolute():
        return entry_path.resolve()
    primary = (artifact_root / entry_path).resolve()
    if primary.exists():
        return primary
    fallback = (root / entry_path).resolve()
    if fallback.exists():
        return fallback
    return primary


def _artifact_canonical_bytes(target: Path) -> bytes:
    if target.suffix.lower() != ".json":
        return target.read_bytes()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return target.read_bytes()
    return _canonical_json_bytes(payload)


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_json(payload: object, *, indent: int) -> str:
    return json.dumps(payload, indent=indent, sort_keys=True) + "\n"


def _normalize_compat_range(*, value: str, runtime_version: str) -> str | None:
    if not value:
        return default_compat_range(runtime_version=runtime_version)
    parsed = _parse_compat_range(value)
    if parsed is None:
        return None
    if not _version_matches(runtime_version, parsed):
        return value
    return value


def _parse_compat_range(value: str) -> tuple[tuple[str, tuple[int, int, int]], ...] | None:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return None
    result: list[tuple[str, tuple[int, int, int]]] = []
    for part in parts:
        match = COMPARATOR_PATTERN.match(part)
        if match is None:
            return None
        comparator = match.group(1) or "=="
        parsed_version = _parse_semver(match.group(2))
        if parsed_version is None:
            return None
        result.append((comparator, parsed_version))
    return tuple(result)


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    parts = value.split(".")
    if not 1 <= len(parts) <= 3:
        return None
    normalized = list(parts)
    while len(normalized) < 3:
        normalized.append("0")
    try:
        parsed = tuple(int(part) for part in normalized)
    except ValueError:
        return None
    if any(number < 0 for number in parsed):
        return None
    return parsed[0], parsed[1], parsed[2]


def _version_matches(
    runtime_version: str, range_checks: tuple[tuple[str, tuple[int, int, int]], ...]
) -> bool:
    runtime = _parse_semver(runtime_version)
    if runtime is None:
        return False
    for comparator, bound in range_checks:
        if comparator == "==" and runtime != bound:
            return False
        if comparator == ">=" and runtime < bound:
            return False
        if comparator == "<=" and runtime > bound:
            return False
        if comparator == ">" and runtime <= bound:
            return False
        if comparator == "<" and runtime >= bound:
            return False
    return True


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.write_signatures:
        signing_errors = sign_pack_registry(
            root,
            registry_path=args.registry,
            matrix_path=args.matrix,
            signing_key=args.signing_key,
            key_id=args.key_id,
        )
        if signing_errors:
            for error in signing_errors:
                print(f"FAIL {error}")
            return 1
    errors = validate_pack_registry(
        root,
        registry_path=args.registry,
        matrix_path=args.matrix,
        signing_key=args.signing_key,
    )
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    if args.write_signatures:
        print("PASS CHK-PACK-SIGNATURES")
    print("PASS CHK-PACK-REGISTRY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
