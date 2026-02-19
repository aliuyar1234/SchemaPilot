"""Adapter registry for target database engines."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from backend.shared_domain.semantic import semantic_manifest_checksum, validate_semantic_manifest
from backend.shared_domain.target_db.adapters.base import (
    MigrationPlanResult,
    SyncResult,
    TargetDbAdapter,
    TargetDbProfileConfig,
    ValidationResult,
)
from backend.shared_domain.target_db.ddl_generator import (
    generate_target_db_ddl,
    migration_drop_statements,
)


def _checksum(payload: dict[str, object]) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContractTargetDbAdapter:
    """Deterministic contract-first adapter for target DB lifecycle operations."""

    db_type: str

    def validate(self, profile: TargetDbProfileConfig) -> ValidationResult:
        required_connection = {"host", "port", "database"}
        enforce_connection = profile.mode == "external"
        missing_connection = (
            sorted(
                key
                for key in required_connection
                if not str(profile.connection.get(key, "")).strip()
            )
            if enforce_connection
            else []
        )
        missing_credentials = sorted(
            key
            for key in ("reader", "writer")
            if not str(profile.credential_refs.get(key, "")).strip()
        )
        return ValidationResult(
            ok=not missing_connection,
            details={
                "db_type": self.db_type,
                "target_db_id": profile.target_db_id,
                "status": "validated" if not missing_connection else "invalid_connection",
                "missing_connection_fields": missing_connection,
                "missing_credential_refs": missing_credentials,
            },
        )

    def generate_ddl(self, profile: TargetDbProfileConfig) -> list[str]:
        semantic_manifest = _manifest_from_profile(profile)
        if semantic_manifest is None:
            return []
        return generate_target_db_ddl(
            manifest=semantic_manifest,
            db_type=self.db_type,
            schema=_schema_name_from_profile(profile),
        )

    def plan_migrations(self, profile: TargetDbProfileConfig) -> MigrationPlanResult:
        semantic_manifest = _manifest_from_profile(profile)
        if semantic_manifest is None:
            checksum = _checksum(
                {
                    "db_type": self.db_type,
                    "workspace_id": profile.workspace_id,
                    "target_db_id": profile.target_db_id,
                    "status": "missing_semantic_manifest",
                }
            )
            return MigrationPlanResult(
                plan_checksum=checksum,
                destructive=False,
                statements=[],
                details={"status": "missing_semantic_manifest"},
            )
        previous_manifest = _previous_manifest_from_profile(profile)
        create_statements = generate_target_db_ddl(
            manifest=semantic_manifest,
            db_type=self.db_type,
            schema=_schema_name_from_profile(profile),
        )
        drop_statements = migration_drop_statements(
            previous_manifest=previous_manifest,
            current_manifest=semantic_manifest,
            db_type=self.db_type,
            schema=_schema_name_from_profile(profile),
        )
        statements = [*drop_statements, *create_statements]
        destructive = len(drop_statements) > 0
        manifest_checksum = semantic_manifest_checksum(semantic_manifest)
        previous_checksum = (
            semantic_manifest_checksum(previous_manifest)
            if previous_manifest is not None
            else None
        )
        checksum = _checksum(
            {
                "db_type": self.db_type,
                "workspace_id": profile.workspace_id,
                "target_db_id": profile.target_db_id,
                "manifest_checksum": manifest_checksum,
                "previous_manifest_checksum": previous_checksum,
                "statements": statements,
            }
        )
        return MigrationPlanResult(
            plan_checksum=checksum,
            destructive=destructive,
            statements=statements,
            details={
                "status": "planned",
                "statement_count": len(statements),
                "drop_statement_count": len(drop_statements),
                "create_statement_count": len(create_statements),
                "manifest_checksum": manifest_checksum,
                "previous_manifest_checksum": previous_checksum,
                "schema": _schema_name_from_profile(profile),
            },
        )

    def apply_migrations(
        self, profile: TargetDbProfileConfig, *, plan_checksum: str
    ) -> dict[str, object]:
        planned = self.plan_migrations(profile)
        if (
            str(planned.details.get("status")) != "missing_semantic_manifest"
            and planned.plan_checksum != plan_checksum
        ):
            raise ValueError("plan_checksum_mismatch")
        return {
            "db_type": self.db_type,
            "target_db_id": profile.target_db_id,
            "plan_checksum": plan_checksum,
            "status": "migrations_applied",
            "statement_count": len(planned.statements),
        }

    def load_initial(self, profile: TargetDbProfileConfig) -> dict[str, object]:
        return {
            "db_type": self.db_type,
            "target_db_id": profile.target_db_id,
            "status": "initial_load_completed",
        }

    def sync_incremental(self, profile: TargetDbProfileConfig) -> SyncResult:
        return SyncResult(
            ok=True,
            datasets=[],
            details={
                "db_type": self.db_type,
                "target_db_id": profile.target_db_id,
                "status": "sync_completed",
            },
        )


_ADAPTERS: dict[str, TargetDbAdapter] = {
    "postgres": cast(TargetDbAdapter, ContractTargetDbAdapter(db_type="postgres")),
    "mysql": cast(TargetDbAdapter, ContractTargetDbAdapter(db_type="mysql")),
    "sqlite": cast(TargetDbAdapter, ContractTargetDbAdapter(db_type="sqlite")),
}


def register_target_db_adapter(db_type: str, adapter: TargetDbAdapter) -> None:
    """Register or override target-db adapter by db type."""
    normalized = db_type.strip().lower()
    if not normalized:
        raise ValueError("db_type_required")
    _ADAPTERS[normalized] = adapter


def get_target_db_adapter(db_type: str) -> TargetDbAdapter:
    """Resolve adapter for configured db type."""
    normalized = db_type.strip().lower()
    adapter = _ADAPTERS.get(normalized)
    if adapter is None:
        raise KeyError(f"unknown_target_db_adapter:{normalized}")
    return adapter


def list_target_db_adapters() -> list[str]:
    """List registered adapter keys deterministically."""
    return sorted(_ADAPTERS)


def _manifest_from_profile(profile: TargetDbProfileConfig) -> dict[str, object] | None:
    raw_manifest = profile.connection.get("__semantic_manifest")
    if not isinstance(raw_manifest, Mapping):
        return None
    return validate_semantic_manifest(raw_manifest, expected_workspace_id=profile.workspace_id)


def _previous_manifest_from_profile(profile: TargetDbProfileConfig) -> dict[str, object] | None:
    raw_manifest = profile.connection.get("__previous_semantic_manifest")
    if not isinstance(raw_manifest, Mapping):
        return None
    return validate_semantic_manifest(raw_manifest, expected_workspace_id=profile.workspace_id)


def _schema_name_from_profile(profile: TargetDbProfileConfig) -> str | None:
    schema = str(profile.connection.get("schema", "")).strip()
    return schema or None
