"""Portable catalog export/import helpers with credential redaction."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.metadata_models import CatalogDataset, CatalogSource, Workspace

CATALOG_SNAPSHOT_VERSION = "v1"


def export_catalog_snapshot(session: Session, *, workspace_id: str) -> dict[str, object]:
    """Export workspace catalog metadata in a portable redacted snapshot."""
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("workspace_not_found")
    sources = (
        session.execute(
            select(CatalogSource)
            .where(CatalogSource.workspace_id == workspace_id)
            .order_by(CatalogSource.source_id)
        )
        .scalars()
        .all()
    )
    datasets = (
        session.execute(
            select(CatalogDataset)
            .where(CatalogDataset.workspace_id == workspace_id)
            .order_by(CatalogDataset.dataset_id)
        )
        .scalars()
        .all()
    )
    return {
        "snapshot_version": CATALOG_SNAPSHOT_VERSION,
        "workspace": {
            "workspace_id": workspace.workspace_id,
            "name": workspace.name,
            "profile": workspace.profile,
            "security_baseline": workspace.security_baseline,
        },
        "sources": [
            {
                "source_id": row.source_id,
                "source_type": row.source_type,
                "scope": row.scope_json,
                "display_name": row.display_name,
                "status": row.status,
                "credentials_redacted": bool(row.credentials_ref),
            }
            for row in sources
        ],
        "datasets": [
            {
                "dataset_id": row.dataset_id,
                "source_id": row.source_id,
                "logical_name": row.logical_name,
                "physical_locator": row.physical_locator,
                "schema_version": row.schema_version,
                "sensitivity_summary": row.sensitivity_summary_json,
            }
            for row in datasets
        ],
    }


def import_catalog_snapshot(
    session: Session,
    *,
    workspace_id: str,
    snapshot: dict[str, object],
) -> dict[str, int]:
    """Import redacted workspace snapshot metadata into the current workspace."""
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("workspace_not_found")
    workspace_snapshot = snapshot.get("workspace", {})
    if isinstance(workspace_snapshot, dict):
        source_workspace_id = str(workspace_snapshot.get("workspace_id", workspace_id))
        if source_workspace_id and source_workspace_id != workspace_id:
            raise ValueError("workspace_mismatch")

    imported_sources = 0
    imported_datasets = 0
    source_id_map: dict[str, str] = {}

    sources_raw = snapshot.get("sources", [])
    if isinstance(sources_raw, list):
        for item in sources_raw:
            if not isinstance(item, dict):
                continue
            source_id_original = str(item.get("source_id", "")).strip()
            if not source_id_original:
                continue
            source_id = source_id_original
            source = session.get(CatalogSource, source_id)
            if source is not None and source.workspace_id != workspace_id:
                source_id = str(uuid.uuid4())
                source = None
            if source is None:
                source = CatalogSource(
                    source_id=source_id,
                    workspace_id=workspace_id,
                    source_type=str(item.get("source_type", "filesystem")),
                    scope_json=item.get("scope", {}) if isinstance(item.get("scope"), dict) else {},
                    credentials_ref=None,
                    status=str(item.get("status", "active")),
                    display_name=str(item.get("display_name", source_id)),
                )
                session.add(source)
                imported_sources += 1
            source_id_map[source_id_original] = source_id

    datasets_raw = snapshot.get("datasets", [])
    if isinstance(datasets_raw, list):
        for item in datasets_raw:
            if not isinstance(item, dict):
                continue
            dataset_id_original = str(item.get("dataset_id", "")).strip()
            source_id_original = str(item.get("source_id", "")).strip()
            if not dataset_id_original or not source_id_original:
                continue
            dataset_id = dataset_id_original
            source_id = source_id_map.get(source_id_original, source_id_original)
            dataset = session.get(CatalogDataset, dataset_id)
            if dataset is not None and dataset.workspace_id != workspace_id:
                dataset_id = str(uuid.uuid4())
                dataset = None
            if dataset is None:
                sensitivity_summary = (
                    item.get("sensitivity_summary", {})
                    if isinstance(item.get("sensitivity_summary"), dict)
                    else {}
                )
                dataset = CatalogDataset(
                    dataset_id=dataset_id,
                    workspace_id=workspace_id,
                    source_id=source_id,
                    logical_name=str(item.get("logical_name", dataset_id)),
                    physical_locator=str(item.get("physical_locator", dataset_id)),
                    schema_version=int(item.get("schema_version", 1)),
                    sensitivity_summary_json=sensitivity_summary,
                )
                session.add(dataset)
                imported_datasets += 1
    session.flush()
    return {"imported_sources": imported_sources, "imported_datasets": imported_datasets}
