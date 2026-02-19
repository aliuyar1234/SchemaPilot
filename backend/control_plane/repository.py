"""SQLAlchemy-backed repository for control-plane operations."""

from __future__ import annotations

import hashlib
import json
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.errors import NotFoundError, PolicyDeniedError
from backend.shared_domain.ids import new_ulid, new_uuid
from backend.shared_domain.metadata_models import (
    CatalogDataset,
    CatalogSource,
    RunRecord,
    RunStepRecord,
    TargetDbPlan,
    TargetDbProfile,
    TargetDbState,
    TargetDbSyncCursor,
    Workspace,
)
from backend.shared_domain.target_db.hash import target_db_profile_hash


def create_workspace(
    session: Session, *, name: str, profile: str, security_baseline: str
) -> dict[str, object]:
    workspace = Workspace(
        workspace_id=new_uuid(),
        name=name,
        profile=profile,
        security_baseline=security_baseline,
    )
    session.add(workspace)
    session.flush()
    return {
        "workspace_id": workspace.workspace_id,
        "name": workspace.name,
        "profile": workspace.profile,
        "security_baseline": workspace.security_baseline,
    }


def list_workspaces(session: Session) -> list[dict[str, object]]:
    rows = session.execute(select(Workspace)).scalars().all()
    return [
        {
            "workspace_id": row.workspace_id,
            "name": row.name,
            "profile": row.profile,
            "security_baseline": row.security_baseline,
        }
        for row in rows
    ]


def get_workspace(session: Session, workspace_id: str) -> dict[str, object] | None:
    row = session.get(Workspace, workspace_id)
    if row is None:
        return None
    return {
        "workspace_id": row.workspace_id,
        "name": row.name,
        "profile": row.profile,
        "security_baseline": row.security_baseline,
    }


def create_source(
    session: Session,
    *,
    workspace_id: str,
    source_type: str,
    scope: dict[str, object],
    display_name: str,
    credentials_ref: str | None = None,
) -> dict[str, object]:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError(
            "Workspace not found.",
            details={"workspace_id": workspace_id},
        )
    source = CatalogSource(
        source_id=new_uuid(),
        workspace_id=workspace_id,
        source_type=source_type,
        scope_json=scope,
        credentials_ref=credentials_ref,
        status="active",
        display_name=display_name,
    )
    session.add(source)
    session.flush()
    return {
        "source_id": source.source_id,
        "workspace_id": source.workspace_id,
        "source_type": source.source_type,
        "scope": source.scope_json,
        "display_name": source.display_name,
        "status": source.status,
        "credentials_ref": source.credentials_ref,
    }


def list_sources(session: Session, workspace_id: str) -> list[dict[str, object]]:
    rows = session.execute(
        select(CatalogSource).where(CatalogSource.workspace_id == workspace_id)
    ).scalars()
    return [
        {
            "source_id": row.source_id,
            "workspace_id": row.workspace_id,
            "source_type": row.source_type,
            "scope": row.scope_json,
            "display_name": row.display_name,
            "status": row.status,
            "credentials_ref": row.credentials_ref,
        }
        for row in rows
    ]


def update_source(
    session: Session,
    *,
    workspace_id: str,
    source_id: str,
    patch: dict[str, object],
) -> dict[str, object] | None:
    """Update source fields allowed in PHASE_1."""
    source = session.get(CatalogSource, source_id)
    if source is None or source.workspace_id != workspace_id:
        return None
    if "status" in patch:
        source.status = str(patch["status"])
    if "scope" in patch and isinstance(patch["scope"], dict):
        source.scope_json = patch["scope"]
    if "display_name" in patch:
        source.display_name = str(patch["display_name"])
    if "credentials_ref" in patch:
        credentials_ref_raw = patch.get("credentials_ref")
        source.credentials_ref = (
            str(credentials_ref_raw) if credentials_ref_raw is not None else None
        )
    session.flush()
    return {
        "source_id": source.source_id,
        "workspace_id": source.workspace_id,
        "source_type": source.source_type,
        "scope": source.scope_json,
        "display_name": source.display_name,
        "status": source.status,
        "credentials_ref": source.credentials_ref,
    }


def list_datasets(session: Session, workspace_id: str) -> list[dict[str, object]]:
    rows = session.execute(
        select(CatalogDataset)
        .where(CatalogDataset.workspace_id == workspace_id)
        .order_by(CatalogDataset.dataset_id)
    ).scalars()
    return [
        {
            "dataset_id": row.dataset_id,
            "workspace_id": row.workspace_id,
            "source_id": row.source_id,
            "logical_name": row.logical_name,
            "physical_locator": row.physical_locator,
            "schema_version": row.schema_version,
            "sensitivity_summary": row.sensitivity_summary_json,
        }
        for row in rows
    ]


def get_dataset(
    session: Session, *, workspace_id: str, dataset_id: str
) -> dict[str, object] | None:
    row = session.get(CatalogDataset, dataset_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    return {
        "dataset_id": row.dataset_id,
        "workspace_id": row.workspace_id,
        "source_id": row.source_id,
        "logical_name": row.logical_name,
        "physical_locator": row.physical_locator,
        "schema_version": row.schema_version,
        "sensitivity_summary": row.sensitivity_summary_json,
    }


def create_run(session: Session, *, workspace_id: str, run_type: str) -> dict[str, object]:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError(
            "Workspace not found.",
            details={"workspace_id": workspace_id},
        )
    run = RunRecord(
        run_id=new_ulid(),
        workspace_id=workspace_id,
        run_type=run_type,
        status="queued",
        input_refs_json={},
        output_refs_json={},
    )
    session.add(run)
    session.flush()
    return {
        "run_id": run.run_id,
        "workspace_id": run.workspace_id,
        "run_type": run.run_type,
        "status": run.status,
        "input_refs": run.input_refs_json,
        "output_refs": run.output_refs_json,
    }


SUPPORTED_TARGET_DB_TYPES = {"postgres", "mysql", "sqlite"}
SUPPORTED_TARGET_DB_MODES = {"managed", "external"}


def _canonical_checksum(payload: dict[str, object]) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _serialize_target_db_profile(row: TargetDbProfile) -> dict[str, object]:
    return {
        "target_db_id": row.target_db_id,
        "workspace_id": row.workspace_id,
        "name": row.name,
        "db_type": row.db_type,
        "mode": row.mode,
        "status": row.status,
        "desired_config_hash": row.desired_config_hash,
        "connection": dict(row.connection_json),
        "credential_refs": dict(row.credential_refs_json),
        "disabled": bool(row.disabled),
    }


def _serialize_target_db_state(row: TargetDbState | None) -> dict[str, object]:
    if row is None:
        return {
            "active_target_db_id": None,
            "current_build_id": None,
            "current_schema_ref": None,
            "last_successful_sync_at": None,
            "health": {
                "status": "unknown",
                "last_validation_run_id": None,
                "last_error_evidence_bundle_id": None,
            },
            "datasets": [],
        }
    return {
        "active_target_db_id": row.active_target_db_id,
        "current_build_id": row.current_build_id,
        "current_schema_ref": row.current_schema_ref,
        "last_successful_sync_at": row.last_successful_sync_epoch,
        "health": {
            "status": row.health_status,
            "last_validation_run_id": row.last_validation_run_id,
            "last_error_evidence_bundle_id": row.last_error_evidence_bundle_uri,
        },
        "datasets": row.sync_status_json.get("datasets", []),
    }


def _ensure_target_db_state(session: Session, workspace_id: str) -> TargetDbState:
    row = session.get(TargetDbState, workspace_id)
    if row is not None:
        return row
    row = TargetDbState(
        workspace_id=workspace_id,
        active_target_db_id=None,
        current_build_id=None,
        current_schema_ref=None,
        last_successful_sync_epoch=None,
        health_status="unknown",
        last_validation_run_id=None,
        last_error_evidence_bundle_uri=None,
        sync_status_json={"datasets": []},
    )
    session.add(row)
    session.flush()
    return row


def create_target_db_profile(
    session: Session,
    *,
    workspace_id: str,
    name: str,
    db_type: str,
    mode: str,
    connection: dict[str, object] | None = None,
    credential_refs: dict[str, object] | None = None,
) -> dict[str, object]:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError(
            "Workspace not found.",
            details={"workspace_id": workspace_id},
        )
    normalized_db_type = db_type.strip().lower()
    normalized_mode = mode.strip().lower()
    if normalized_db_type not in SUPPORTED_TARGET_DB_TYPES:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "unsupported_target_db_type", "db_type": normalized_db_type},
        )
    if normalized_mode not in SUPPORTED_TARGET_DB_MODES:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "unsupported_target_db_mode", "mode": normalized_mode},
        )
    resolved_connection = dict(connection or {})
    resolved_credential_refs = dict(credential_refs or {})
    profile = TargetDbProfile(
        target_db_id=new_ulid(),
        workspace_id=workspace_id,
        name=name.strip(),
        db_type=normalized_db_type,
        mode=normalized_mode,
        status="draft",
        desired_config_hash=target_db_profile_hash(
            workspace_id=workspace_id,
            name=name.strip(),
            db_type=normalized_db_type,
            mode=normalized_mode,
            connection=resolved_connection,
            credential_refs=resolved_credential_refs,
        ),
        connection_json=resolved_connection,
        credential_refs_json=resolved_credential_refs,
        disabled=False,
    )
    session.add(profile)
    state = _ensure_target_db_state(session, workspace_id)
    if state.active_target_db_id is None:
        state.active_target_db_id = profile.target_db_id
        state.health_status = "draft"
    session.flush()
    return _serialize_target_db_profile(profile)


def list_target_db_profiles(session: Session, *, workspace_id: str) -> list[dict[str, object]]:
    rows = (
        session.execute(
            select(TargetDbProfile)
            .where(TargetDbProfile.workspace_id == workspace_id)
            .order_by(TargetDbProfile.target_db_id)
        )
        .scalars()
        .all()
    )
    return [_serialize_target_db_profile(row) for row in rows]


def get_target_db_profile(
    session: Session, *, workspace_id: str, target_db_id: str
) -> dict[str, object] | None:
    row = session.get(TargetDbProfile, target_db_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    profile = _serialize_target_db_profile(row)
    state = session.get(TargetDbState, workspace_id)
    profile["state"] = _serialize_target_db_state(state)
    return profile


def disable_target_db_profile(
    session: Session, *, workspace_id: str, target_db_id: str
) -> dict[str, object] | None:
    row = session.get(TargetDbProfile, target_db_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    row.disabled = True
    row.status = "disabled"
    state = _ensure_target_db_state(session, workspace_id)
    if state.active_target_db_id == target_db_id:
        state.active_target_db_id = None
        state.health_status = "disabled"
    session.flush()
    response = _serialize_target_db_profile(row)
    response["disabled_at_epoch"] = int(time.time())
    return response


def create_target_db_plan(
    session: Session,
    *,
    workspace_id: str,
    target_db_id: str,
    plan_kind: str,
    payload: dict[str, object] | None = None,
    requires_approval: bool = False,
    destructive: bool = False,
) -> dict[str, object]:
    profile = session.get(TargetDbProfile, target_db_id)
    if profile is None or profile.workspace_id != workspace_id:
        raise NotFoundError(
            "Target DB profile not found.",
            details={"workspace_id": workspace_id, "target_db_id": target_db_id},
        )
    payload_json = dict(payload or {})
    checksum = _canonical_checksum(
        {
            "workspace_id": workspace_id,
            "target_db_id": target_db_id,
            "plan_kind": plan_kind,
            "payload": payload_json,
        }
    )
    plan = TargetDbPlan(
        plan_id=new_ulid(),
        workspace_id=workspace_id,
        target_db_id=target_db_id,
        plan_kind=plan_kind,
        plan_checksum=checksum,
        status="draft",
        requires_approval=requires_approval,
        destructive=destructive,
        created_by_run_id=None,
        evidence_bundle_uri=None,
        payload_json=payload_json,
    )
    session.add(plan)
    session.flush()
    return {
        "plan_id": plan.plan_id,
        "plan_kind": plan.plan_kind,
        "workspace_id": plan.workspace_id,
        "target_db_id": plan.target_db_id,
        "plan_checksum": plan.plan_checksum,
        "requires_approval": bool(plan.requires_approval),
        "destructive": bool(plan.destructive),
        "status": plan.status,
        "payload": dict(plan.payload_json),
    }


def get_target_db_plan(
    session: Session, *, workspace_id: str, target_db_id: str, plan_id: str
) -> dict[str, object] | None:
    row = session.get(TargetDbPlan, plan_id)
    if row is None or row.workspace_id != workspace_id or row.target_db_id != target_db_id:
        return None
    return {
        "plan_id": row.plan_id,
        "plan_kind": row.plan_kind,
        "workspace_id": row.workspace_id,
        "target_db_id": row.target_db_id,
        "plan_checksum": row.plan_checksum,
        "requires_approval": bool(row.requires_approval),
        "destructive": bool(row.destructive),
        "status": row.status,
        "payload": dict(row.payload_json),
    }


def mark_target_db_plan_applied(
    session: Session, *, workspace_id: str, target_db_id: str, plan_id: str
) -> dict[str, object] | None:
    row = session.get(TargetDbPlan, plan_id)
    if row is None or row.workspace_id != workspace_id or row.target_db_id != target_db_id:
        return None
    row.status = "applied"
    session.flush()
    return {
        "plan_id": row.plan_id,
        "plan_kind": row.plan_kind,
        "status": row.status,
    }


def upsert_target_db_sync_cursor(
    session: Session,
    *,
    workspace_id: str,
    target_db_id: str,
    dataset_id: str,
    cursor_hash: str,
    run_id: str | None,
    status: str,
) -> dict[str, object]:
    row = (
        session.execute(
            select(TargetDbSyncCursor).where(
                TargetDbSyncCursor.workspace_id == workspace_id,
                TargetDbSyncCursor.target_db_id == target_db_id,
                TargetDbSyncCursor.dataset_id == dataset_id,
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        row = TargetDbSyncCursor(
            sync_cursor_id=new_ulid(),
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            dataset_id=dataset_id,
            cursor_hash=cursor_hash,
            last_run_id=run_id,
            last_status=status,
        )
        session.add(row)
    else:
        row.cursor_hash = cursor_hash
        row.last_run_id = run_id
        row.last_status = status
    session.flush()
    return {
        "dataset_id": row.dataset_id,
        "cursor_hash": row.cursor_hash,
        "last_run_id": row.last_run_id,
        "last_status": row.last_status,
    }


def list_target_db_sync_cursors(
    session: Session, *, workspace_id: str, target_db_id: str
) -> list[dict[str, object]]:
    rows = (
        session.execute(
            select(TargetDbSyncCursor)
            .where(
                TargetDbSyncCursor.workspace_id == workspace_id,
                TargetDbSyncCursor.target_db_id == target_db_id,
            )
            .order_by(TargetDbSyncCursor.dataset_id)
        )
        .scalars()
        .all()
    )
    return [
        {
            "dataset_id": row.dataset_id,
            "cursor_hash": row.cursor_hash,
            "last_run_id": row.last_run_id,
            "last_status": row.last_status,
        }
        for row in rows
    ]


def get_run(session: Session, *, workspace_id: str, run_id: str) -> dict[str, object] | None:
    run = session.get(RunRecord, run_id)
    if run is None or run.workspace_id != workspace_id:
        return None
    return {
        "run_id": run.run_id,
        "workspace_id": run.workspace_id,
        "run_type": run.run_type,
        "status": run.status,
        "input_refs": run.input_refs_json,
        "output_refs": run.output_refs_json,
        "run_steps": list_run_steps(session, workspace_id=workspace_id, run_id=run_id),
    }


def list_run_steps(session: Session, *, workspace_id: str, run_id: str) -> list[dict[str, object]]:
    rows = (
        session.execute(
            select(RunStepRecord)
            .where(
                RunStepRecord.workspace_id == workspace_id,
                RunStepRecord.run_id == run_id,
            )
            .order_by(RunStepRecord.step_order, RunStepRecord.run_step_id)
        )
        .scalars()
        .all()
    )
    return [_serialize_run_step(row) for row in rows]


def _serialize_run_step(row: RunStepRecord) -> dict[str, object]:
    return {
        "run_step_id": row.run_step_id,
        "run_id": row.run_id,
        "workspace_id": row.workspace_id,
        "run_type": row.run_type,
        "step_key": row.step_key,
        "step_order": row.step_order,
        "depends_on": list(row.depends_on_json),
        "status": row.status,
        "started_epoch": row.started_epoch,
        "finished_epoch": row.finished_epoch,
        "duration_ms": row.duration_ms,
        "attempt_count": row.attempt_count,
        "error_code": row.error_code,
        "evidence_bundle_uri": row.evidence_bundle_uri,
        "details": dict(row.details_json),
    }


def append_audit_event(
    session: Session,
    *,
    workspace_id: str | None,
    actor_id: str,
    event_type: str,
    event_json: dict[str, object],
    correlation_id: str,
) -> dict[str, object]:
    event = AuditEvent(
        audit_event_id=new_ulid(),
        workspace_id=workspace_id,
        actor_id=actor_id,
        event_type=event_type,
        event_json=event_json,
        correlation_id=correlation_id,
    )
    session.add(event)
    session.flush()
    return {
        "audit_event_id": event.audit_event_id,
        "workspace_id": event.workspace_id,
        "actor_id": event.actor_id,
        "event_type": event.event_type,
        "event_json": event.event_json,
        "correlation_id": event.correlation_id,
    }
