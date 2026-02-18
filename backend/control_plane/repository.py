"""SQLAlchemy-backed repository for control-plane operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.errors import NotFoundError
from backend.shared_domain.ids import new_ulid, new_uuid
from backend.shared_domain.metadata_models import (
    CatalogDataset,
    CatalogSource,
    RunRecord,
    Workspace,
)


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
