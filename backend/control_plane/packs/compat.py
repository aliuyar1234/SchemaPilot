"""Policy-pack compatibility enforcement helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_COMPARATOR_PATTERN = re.compile(r"^(>=|<=|>|<|==)?\s*([0-9]+(?:\.[0-9]+){0,2})$")
_SCHEMA_VERSION_PATTERN = re.compile(r"^v[0-9]+$")


@dataclass(frozen=True)
class PackCompatibilityResult:
    """Compatibility outcome for one policy pack entry."""

    pack_id: str
    checked: bool
    compatible: bool
    requires_migration: bool
    schema_version: str
    current_schema_version: str
    runtime_version: str
    compat_range: str
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "pack_id": self.pack_id,
            "checked": self.checked,
            "compatible": self.compatible,
            "requires_migration": self.requires_migration,
            "schema_version": self.schema_version,
            "current_schema_version": self.current_schema_version,
            "runtime_version": self.runtime_version,
            "compat_range": self.compat_range,
            "errors": list(self.errors),
        }


def evaluate_policy_pack_entry_compatibility(
    *,
    entry: dict[str, Any] | None,
    matrix_path: str,
    repo_root: Path,
) -> PackCompatibilityResult:
    """Evaluate policy pack schema/runtime compatibility for control-plane apply gates."""

    pack_id = (
        str(entry.get("pack_id", "")).strip()
        if isinstance(entry, dict)
        else "<unknown>"
    ) or "<unknown>"
    if not isinstance(entry, dict):
        return PackCompatibilityResult(
            pack_id=pack_id,
            checked=False,
            compatible=True,
            requires_migration=False,
            schema_version="",
            current_schema_version="",
            runtime_version="",
            compat_range="",
            errors=(),
        )

    matrix, matrix_errors = _load_compatibility_matrix(repo_root, matrix_path=matrix_path)
    if matrix is None:
        return PackCompatibilityResult(
            pack_id=pack_id,
            checked=False,
            compatible=False,
            requires_migration=False,
            schema_version="",
            current_schema_version="",
            runtime_version="",
            compat_range="",
            errors=tuple(sorted(set(matrix_errors))),
        )

    errors = list(matrix_errors)
    section_payload = matrix.get("sections", {}).get("policy_packs", {})
    if isinstance(section_payload, dict):
        current_schema_version = (
            str(section_payload.get("current_schema_version", "")).strip() or "v1"
        )
        supported_versions_raw = section_payload.get("supported_schema_versions", [])
        supported_versions = (
            {str(item).strip() for item in supported_versions_raw}
            if isinstance(supported_versions_raw, list)
            else set()
        )
    else:
        current_schema_version = "v1"
        supported_versions = {"v1"}
        errors.append("invalid_policy_pack_section")

    schema_version = str(entry.get("schema_version", "")).strip() or "v1"
    semantic_schema_version = str(entry.get("semantic_schema_version", "")).strip()
    if not semantic_schema_version:
        errors.append(f"missing_semantic_schema_version:{pack_id}")
    elif semantic_schema_version != schema_version:
        errors.append(
            f"semantic_schema_version_mismatch:{pack_id}:{semantic_schema_version}!={schema_version}"
        )

    compat_range = str(entry.get("compat_range", "")).strip()
    if not compat_range:
        errors.append(f"missing_compat_range:{pack_id}")
    runtime_version = str(matrix.get("runtime_version", "")).strip() or "0.1.0"
    parsed_range = _parse_compat_range(compat_range) if compat_range else None
    if compat_range and parsed_range is None:
        errors.append(f"invalid_compat_range:{pack_id}:{compat_range}")
    if parsed_range is not None and not _version_matches(runtime_version, parsed_range):
        errors.append(f"runtime_out_of_range:{pack_id}:{runtime_version}:{compat_range}")

    migration_available_raw = entry.get("migration_available")
    migration_available = (
        bool(migration_available_raw) if isinstance(migration_available_raw, bool) else None
    )
    if migration_available is None:
        errors.append(f"missing_migration_available:{pack_id}")

    requires_migration = schema_version != current_schema_version
    if schema_version not in supported_versions:
        errors.append(f"unsupported_schema_version:{pack_id}:{schema_version}")
    if requires_migration:
        errors.append(
            f"migration_required:{pack_id}:{schema_version}->{current_schema_version}"
        )
        if migration_available is not True:
            errors.append(
                f"migration_unavailable:{pack_id}:{schema_version}->{current_schema_version}"
            )
    elif migration_available is True:
        errors.append(f"inconsistent_migration_flag:{pack_id}")

    unique_errors = tuple(sorted(set(errors)))
    return PackCompatibilityResult(
        pack_id=pack_id,
        checked=True,
        compatible=not unique_errors,
        requires_migration=requires_migration,
        schema_version=schema_version,
        current_schema_version=current_schema_version,
        runtime_version=runtime_version,
        compat_range=compat_range,
        errors=unique_errors,
    )


def _load_compatibility_matrix(
    root: Path,
    *,
    matrix_path: str,
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
            if not _SCHEMA_VERSION_PATTERN.match(current):
                errors.append(f"sections.{section}.current_schema_version must match v<integer>")
            if not isinstance(supported, list) or not supported:
                errors.append(
                    f"sections.{section}.supported_schema_versions must be a non-empty list"
                )
                continue
            normalized_supported = [str(item).strip() for item in supported]
            if any(not _SCHEMA_VERSION_PATTERN.match(item) for item in normalized_supported):
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
            if not _SCHEMA_VERSION_PATTERN.match(from_version):
                errors.append(f"migrations[{index}].from_schema_version must match v<integer>")
            if not _SCHEMA_VERSION_PATTERN.match(to_version):
                errors.append(f"migrations[{index}].to_schema_version must match v<integer>")
            tool_path = str(migration.get("tool", "")).strip()
            if not tool_path:
                errors.append(f"migrations[{index}].tool is required")

    return payload, errors


def _parse_compat_range(value: str) -> tuple[tuple[str, tuple[int, int, int]], ...] | None:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return None
    result: list[tuple[str, tuple[int, int, int]]] = []
    for part in parts:
        match = _COMPARATOR_PATTERN.match(part)
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
