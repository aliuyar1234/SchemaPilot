#!/usr/bin/env python3
"""Migrate pack payloads to the current schema versions in the compatibility matrix."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    from tools.pack_lint import (
        DEFAULT_KEY_ID,
        DEFAULT_MATRIX_PATH,
        DEFAULT_REGISTRY_PATH,
        DEFAULT_SIGNING_KEY,
        SIGNED_SECTIONS,
        _canonical_json,
        _section_current_version,
        _version_supported,
        load_compatibility_matrix,
        sign_pack_registry,
    )
except ModuleNotFoundError:  # pragma: no cover - CLI script invocation fallback
    from pack_lint import (  # type: ignore[no-redef]
        DEFAULT_KEY_ID,
        DEFAULT_MATRIX_PATH,
        DEFAULT_REGISTRY_PATH,
        DEFAULT_SIGNING_KEY,
        SIGNED_SECTIONS,
        _canonical_json,
        _section_current_version,
        _version_supported,
        load_compatibility_matrix,
        sign_pack_registry,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help="Path to pack registry JSON file.",
    )
    parser.add_argument(
        "--matrix",
        default=DEFAULT_MATRIX_PATH,
        help="Path to compatibility matrix JSON file.",
    )
    parser.add_argument(
        "--signing-key",
        default=os.getenv("SCHEMAPILOT_PACK_SIGNING_KEY", DEFAULT_SIGNING_KEY),
        help="Signing key used to refresh signatures after migration.",
    )
    parser.add_argument(
        "--key-id",
        default=DEFAULT_KEY_ID,
        help="Signer key identifier to write into registry signatures.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write migrated artifacts and updated registry/signatures to disk.",
    )
    parser.add_argument(
        "--output",
        default="runtime/pack_migrations/report.json",
        help="Path to write deterministic migration evidence report.",
    )
    return parser.parse_args()


def migrate_pack_payload(
    payload: dict[str, Any],
    *,
    section: str,
    source_schema_version: str,
    target_schema_version: str,
) -> dict[str, Any]:
    """Apply one supported pack schema migration."""
    if source_schema_version == target_schema_version:
        return copy.deepcopy(payload)
    if source_schema_version == "v1" and target_schema_version == "v2":
        migrated = copy.deepcopy(payload)
        migrated["schema_version"] = "v2"
        compatibility = migrated.get("compatibility")
        if not isinstance(compatibility, dict):
            compatibility = {}
        compatibility.setdefault("min_runtime_version", "0.1.0")
        compatibility.setdefault("max_runtime_version", "0.x")
        if section in {"semantic_packs", "template_packs"}:
            compatibility.setdefault("semantic_manifest_version", "1")
        migrated["compatibility"] = compatibility
        return migrated
    raise ValueError(
        f"unsupported_migration:{section}:{source_schema_version}->{target_schema_version}"
    )


def migrate_registry_packs(
    root: Path,
    *,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    matrix_path: str = DEFAULT_MATRIX_PATH,
    signing_key: str = DEFAULT_SIGNING_KEY,
    key_id: str = DEFAULT_KEY_ID,
    write: bool = False,
) -> tuple[list[dict[str, str]], list[str]]:
    matrix, matrix_errors = load_compatibility_matrix(root, matrix_path=matrix_path)
    if matrix is None:
        return [], matrix_errors
    registry_file = root / registry_path
    if not registry_file.exists():
        return [], matrix_errors + [f"missing registry file: {registry_file.as_posix()}"]
    try:
        registry_payload = json.loads(registry_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], matrix_errors + [f"invalid registry json: {exc}"]
    if not isinstance(registry_payload, dict):
        return [], matrix_errors + ["registry payload must be an object"]

    errors = list(matrix_errors)
    report: list[dict[str, str]] = []

    for section in SIGNED_SECTIONS:
        entries = registry_payload.get(section, [])
        if not isinstance(entries, list):
            errors.append(f"{section} must be a list")
            continue
        target_schema_version = _section_current_version(matrix, section=section)
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append(f"{section}: entry must be an object")
                continue
            pack_id = str(entry.get("pack_id", "")).strip() or "<unknown>"
            path = str(entry.get("path", "")).strip()
            if not path:
                errors.append(f"{section}: missing path for {pack_id}")
                continue
            artifact = root / path
            if not artifact.exists():
                errors.append(f"{section}: missing artifact {artifact.as_posix()}")
                continue
            try:
                payload = json.loads(artifact.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{section}: invalid json payload for {pack_id}: {exc}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"{section}: payload must be an object for {pack_id}")
                continue
            source_schema_version = (
                str(entry.get("schema_version", payload.get("schema_version", "v1"))).strip()
                or "v1"
            )
            if not _version_supported(
                matrix,
                section=section,
                schema_version=source_schema_version,
            ):
                errors.append(
                    f"{section}: schema_version {source_schema_version!r} is not supported "
                    f"for {pack_id}"
                )
                continue
            if source_schema_version == target_schema_version:
                report.append(
                    {
                        "pack_id": pack_id,
                        "section": section,
                        "status": "up_to_date",
                        "from_schema_version": source_schema_version,
                        "to_schema_version": target_schema_version,
                        "artifact_before_checksum": _payload_checksum(payload),
                        "artifact_after_checksum": _payload_checksum(payload),
                        "diff_checksum": _diff_checksum(
                            before_payload=payload,
                            after_payload=payload,
                        ),
                    }
                )
                entry["schema_version"] = source_schema_version
                continue

            migrations = matrix.get("migrations", [])
            if not _has_migration(
                migrations,
                section=section,
                from_schema_version=source_schema_version,
                to_schema_version=target_schema_version,
            ):
                errors.append(
                    f"{section}: no migration path {source_schema_version}"
                    f"->{target_schema_version} for {pack_id}"
                )
                continue

            try:
                migrated_payload = migrate_pack_payload(
                    payload,
                    section=section,
                    source_schema_version=source_schema_version,
                    target_schema_version=target_schema_version,
                )
            except ValueError as exc:
                errors.append(f"{section}: {exc}")
                continue

            report.append(
                {
                    "pack_id": pack_id,
                    "section": section,
                    "status": "migrated" if write else "migration_available",
                    "from_schema_version": source_schema_version,
                    "to_schema_version": target_schema_version,
                    "artifact_before_checksum": _payload_checksum(payload),
                    "artifact_after_checksum": _payload_checksum(migrated_payload),
                    "diff_checksum": _diff_checksum(
                        before_payload=payload,
                        after_payload=migrated_payload,
                    ),
                }
            )
            if write:
                artifact.write_text(_canonical_json(migrated_payload, indent=2), encoding="utf-8")
                entry["schema_version"] = target_schema_version

    if errors or not write:
        return report, errors

    registry_file.write_text(_canonical_json(registry_payload, indent=2), encoding="utf-8")
    sign_errors = sign_pack_registry(
        root,
        registry_path=registry_path,
        matrix_path=matrix_path,
        signing_key=signing_key,
        key_id=key_id,
    )
    return report, sign_errors


def _has_migration(
    migrations: object,
    *,
    section: str,
    from_schema_version: str,
    to_schema_version: str,
) -> bool:
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


def _payload_checksum(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _diff_checksum(*, before_payload: dict[str, Any], after_payload: dict[str, Any]) -> str:
    before_keys = set(before_payload.keys())
    after_keys = set(after_payload.keys())
    changed_keys = sorted(
        key
        for key in before_keys & after_keys
        if before_payload[key] != after_payload[key]
    )
    diff_payload = {
        "added_keys": sorted(after_keys - before_keys),
        "changed_keys": changed_keys,
        "removed_keys": sorted(before_keys - after_keys),
    }
    canonical = json.dumps(diff_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    report, errors = migrate_registry_packs(
        root,
        registry_path=args.registry,
        matrix_path=args.matrix,
        signing_key=args.signing_key,
        key_id=args.key_id,
        write=args.write,
    )
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_payload: dict[str, object] = {
        "errors": list(errors),
        "matrix_path": args.matrix,
        "registry_path": args.registry,
        "report": report,
        "status": "fail" if errors else "pass",
        "write_mode": bool(args.write),
    }
    output_path.write_text(_canonical_json(output_payload, indent=2), encoding="utf-8")
    print(output_path.as_posix())
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print(json.dumps({"report": report}, indent=2, sort_keys=True))
    if args.write:
        print("PASS CHK-PACK-MIGRATIONS")
    else:
        print("PASS CHK-PACK-MIGRATIONS (dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
