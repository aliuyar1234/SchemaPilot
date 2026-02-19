"""Promotion bundle export/import helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.control_plane.catalog_snapshot import export_catalog_snapshot
from backend.control_plane.policy_pack_service import get_effective_policy_pack
from backend.control_plane.semantic_manifest_service import get_effective_semantic_manifest
from backend.shared_domain.config import Settings
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import (
    ReviewProposal,
    RunStepRecord,
    TargetDbPlan,
    TargetDbState,
)

BUNDLE_SCHEMA_VERSION = "v1"
SIGNED_PACK_SECTIONS = ("policy_packs", "semantic_packs", "template_packs")
CONFIG_EXPORT_KEYS = (
    "profile",
    "auth_mode",
    "require_auth_for_non_local",
    "query_engine",
    "retrieval_backend",
    "ai_service_enabled",
    "ai_provider",
    "audit_sink_mode",
    "pack_registry_path",
    "pack_matrix_path",
    "plugin_registry_path",
    "policy_pack_canary_enabled",
    "target_db_rls_enabled",
    "database_url",
)


@dataclass(frozen=True)
class PromotionBundleEnvelope:
    """Canonical promotion bundle envelope."""

    bundle: dict[str, object]
    bundle_checksum: str

    def signature_payload(self) -> dict[str, object]:
        """Return deterministic payload used for bundle signatures."""

        return {
            "bundle": self.bundle,
            "bundle_checksum": self.bundle_checksum,
        }


def build_promotion_bundle_envelope(
    session: Session,
    *,
    workspace_id: str,
    settings: Settings,
    repo_root: Path,
) -> PromotionBundleEnvelope:
    """Build deterministic promotion bundle and checksum for a workspace."""

    bundle_payload: dict[str, object] = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "workspace_profile": str(settings.profile).strip().lower(),
        "catalog_snapshot": export_catalog_snapshot(session, workspace_id=workspace_id),
        "policy_pack_state": get_effective_policy_pack(session, workspace_id=workspace_id) or {},
        "semantic_manifest_state": (
            get_effective_semantic_manifest(session, workspace_id=workspace_id) or {}
        ),
        "pack_registry": _build_pack_registry_snapshot(
            repo_root=repo_root,
            registry_path=settings.pack_registry_path,
        ),
        "migration_checksums": _list_migration_checksums(session, workspace_id=workspace_id),
        "target_db_state": _build_target_db_state_snapshot(session, workspace_id=workspace_id),
        "config_redacted": _build_redacted_config(settings),
        "evidence_refs": _collect_evidence_references(session, workspace_id=workspace_id),
    }
    return PromotionBundleEnvelope(
        bundle=bundle_payload,
        bundle_checksum=compute_bundle_checksum(bundle_payload),
    )


def compute_bundle_checksum(bundle_payload: dict[str, object]) -> str:
    """Return deterministic SHA256 checksum for a promotion bundle payload."""

    canonical = _canonical_json(bundle_payload).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_promotion_attestation(
    *,
    workspace_id: str,
    actor_id: str,
    bundle_checksum: str,
    action: str,
    signature_key_id: str,
    policy_gate: dict[str, object],
    source_workspace_id: str | None = None,
) -> dict[str, object]:
    """Build promotion attestation payload for audit trails."""

    return {
        "attestation_id": new_ulid(),
        "attestation_type": "promotion_bundle",
        "workspace_id": workspace_id,
        "source_workspace_id": source_workspace_id or workspace_id,
        "actor_id": actor_id,
        "action": action,
        "bundle_checksum": bundle_checksum,
        "signature_key_id": signature_key_id,
        "policy_gate": policy_gate,
    }


def _build_pack_registry_snapshot(*, repo_root: Path, registry_path: str) -> dict[str, object]:
    registry_file = _resolve_repo_path(repo_root=repo_root, candidate=registry_path)
    if not registry_file.exists():
        return {
            "registry_path": registry_path,
            "registry_available": False,
            "registry_checksum": "",
            "sections": {},
        }
    payload = json.loads(registry_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid_pack_registry_payload:{registry_file.as_posix()}")
    sections: dict[str, list[dict[str, object]]] = {}
    for section in SIGNED_PACK_SECTIONS:
        entries_raw = payload.get(section, [])
        entries: list[dict[str, object]] = []
        if isinstance(entries_raw, list):
            for entry in entries_raw:
                if not isinstance(entry, dict):
                    continue
                pack_id = str(entry.get("pack_id", "")).strip()
                version = str(entry.get("version", "")).strip()
                if not pack_id or not version:
                    continue
                entries.append(
                    {
                        "pack_id": pack_id,
                        "version": version,
                        "schema_version": str(entry.get("schema_version", "")).strip() or "v1",
                        "semantic_schema_version": (
                            str(entry.get("semantic_schema_version", "")).strip() or "v1"
                        ),
                        "compat_range": str(entry.get("compat_range", "")).strip(),
                        "migration_available": bool(entry.get("migration_available", False)),
                        "path": str(entry.get("path", "")).strip(),
                    }
                )
        sections[section] = sorted(entries, key=lambda item: (item["pack_id"], item["version"]))
    return {
        "registry_path": registry_path,
        "registry_available": True,
        "registry_checksum": hashlib.sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest(),
        "sections": sections,
    }


def _build_redacted_config(settings: Settings) -> dict[str, object]:
    redacted = settings.to_redacted_dict()
    return {
        key: redacted.get(key)
        for key in CONFIG_EXPORT_KEYS
    }


def _list_migration_checksums(session: Session, *, workspace_id: str) -> list[dict[str, object]]:
    rows = (
        session.execute(
            select(TargetDbPlan)
            .where(TargetDbPlan.workspace_id == workspace_id)
            .order_by(TargetDbPlan.target_db_id, TargetDbPlan.plan_kind, TargetDbPlan.plan_id)
        )
        .scalars()
        .all()
    )
    migration_rows: list[dict[str, object]] = []
    for row in rows:
        migration_rows.append(
            {
                "plan_id": row.plan_id,
                "target_db_id": row.target_db_id,
                "plan_kind": row.plan_kind,
                "plan_checksum": row.plan_checksum,
                "status": row.status,
                "evidence_bundle_uri": row.evidence_bundle_uri or "",
            }
        )
    return migration_rows


def _build_target_db_state_snapshot(
    session: Session, *, workspace_id: str
) -> dict[str, object]:
    state = session.get(TargetDbState, workspace_id)
    if state is None:
        return {}
    return {
        "active_target_db_id": state.active_target_db_id,
        "current_build_id": state.current_build_id,
        "current_schema_ref": state.current_schema_ref,
        "last_successful_sync_epoch": state.last_successful_sync_epoch,
        "health_status": state.health_status,
        "last_validation_run_id": state.last_validation_run_id,
        "last_error_evidence_bundle_uri": state.last_error_evidence_bundle_uri,
    }


def _collect_evidence_references(
    session: Session, *, workspace_id: str
) -> dict[str, list[str] | str]:
    proposal_rows = (
        session.execute(
            select(ReviewProposal)
            .where(ReviewProposal.workspace_id == workspace_id)
            .order_by(ReviewProposal.proposal_id)
        )
        .scalars()
        .all()
    )
    run_step_rows = (
        session.execute(
            select(RunStepRecord)
            .where(
                RunStepRecord.workspace_id == workspace_id,
                RunStepRecord.evidence_bundle_uri.is_not(None),
            )
            .order_by(RunStepRecord.run_id, RunStepRecord.step_order, RunStepRecord.run_step_id)
        )
        .scalars()
        .all()
    )
    proposal_refs = sorted(
        {
            str(row.evidence_bundle_uri)
            for row in proposal_rows
            if str(row.evidence_bundle_uri).strip()
        }
    )
    run_step_refs = sorted(
        {
            str(row.evidence_bundle_uri)
            for row in run_step_rows
            if str(row.evidence_bundle_uri).strip()
        }
    )
    target_db_state = session.get(TargetDbState, workspace_id)
    target_db_error_ref = (
        str(target_db_state.last_error_evidence_bundle_uri)
        if target_db_state is not None and target_db_state.last_error_evidence_bundle_uri
        else ""
    )
    return {
        "review_proposal_evidence": proposal_refs,
        "run_step_evidence": run_step_refs,
        "target_db_last_error_evidence": target_db_error_ref,
    }


def _resolve_repo_path(*, repo_root: Path, candidate: str) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
