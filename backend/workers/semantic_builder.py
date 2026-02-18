"""Semantic manifest bootstrap builder from catalog/profile evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.evidence_store import store_evidence_bundle
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import CatalogDataset, ReviewProposal, ReviewTask
from backend.shared_domain.semantic import semantic_manifest_checksum, validate_semantic_manifest

MAX_ATTRIBUTES_PER_ENTITY = 40


def build_semantic_manifest_candidate(
    session: Session,
    *,
    workspace_id: str,
    storage_root: str,
) -> dict[str, object]:
    """Build semantic manifest candidate and create blocking review task."""
    datasets = (
        session.execute(
            select(CatalogDataset)
            .where(CatalogDataset.workspace_id == workspace_id)
            .order_by(CatalogDataset.logical_name, CatalogDataset.dataset_id)
        )
        .scalars()
        .all()
    )
    if not datasets:
        raise ValueError("semantic_bootstrap_requires_catalog_datasets")

    entities: list[dict[str, object]] = []
    dataset_entity_map: list[dict[str, str]] = []
    confidence_flags: list[dict[str, str]] = []
    existing_entity_ids: set[str] = set()

    for dataset in datasets:
        summary = _json_dict(dataset.sensitivity_summary_json)
        profile_raw = summary.get("profile", {})
        profile = profile_raw if isinstance(profile_raw, Mapping) else {}
        columns = _string_list(profile.get("schema_columns"))
        entity_id = _unique_entity_id(
            base=_safe_identifier(dataset.logical_name or dataset.dataset_id),
            existing=existing_entity_ids,
        )
        primary_key = _pick_primary_key(columns)
        if not columns:
            confidence_flags.append(
                {
                    "dataset_id": dataset.dataset_id,
                    "reason": "missing_profile_columns",
                }
            )
        elif primary_key == "id" and "id" not in columns:
            confidence_flags.append(
                {"dataset_id": dataset.dataset_id, "reason": "fallback_primary_key"}
            )
        attributes = [column for column in columns if column != primary_key]
        entities.append(
            {
                "entity_id": entity_id,
                "dataset_id": dataset.dataset_id,
                "primary_key": primary_key,
                "attributes": sorted(set(attributes))[:MAX_ATTRIBUTES_PER_ENTITY],
            }
        )
        dataset_entity_map.append(
            {"dataset_id": dataset.dataset_id, "entity_id": entity_id, "primary_key": primary_key}
        )

    metrics = [
        {
            "metric_id": f"{row['entity_id']}_count",
            "entity_id": row["entity_id"],
            "aggregation": "count",
            "field": row["primary_key"],
            "expression": f"count({row['primary_key']})",
        }
        for row in entities
    ]
    joins = _infer_joins(entities)
    manifest = validate_semantic_manifest(
        {
            "manifest_version": "1",
            "workspace_id": workspace_id,
            "entities": entities,
            "metrics": metrics,
            "joins": joins,
        },
        expected_workspace_id=workspace_id,
    )
    checksum = semantic_manifest_checksum(manifest)
    confidence = max(0.4, min(1.0, 0.95 - (0.2 * len(confidence_flags))))

    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=storage_root,
        bundle_type="semantic_manifest_candidate",
        payload={
            "workspace_id": workspace_id,
            "manifest": manifest,
            "manifest_checksum": checksum,
            "dataset_entity_map": dataset_entity_map,
            "confidence_flags": confidence_flags,
            "confidence": confidence,
        },
    )
    proposal = _get_or_create_proposal(
        session=session,
        workspace_id=workspace_id,
        evidence_bundle_uri=stored.evidence_bundle_uri,
        confidence=confidence,
    )
    task = _get_or_create_blocking_task(
        session=session,
        workspace_id=workspace_id,
        proposal_id=proposal.proposal_id,
    )
    return {
        "semantic_manifest": manifest,
        "manifest_checksum": checksum,
        "evidence_bundle_uri": stored.evidence_bundle_uri,
        "confidence": confidence,
        "confidence_flag_count": len(confidence_flags),
        "proposal_id": proposal.proposal_id,
        "task_id": task.task_id,
        "entity_count": len(entities),
        "metric_count": len(metrics),
        "join_count": len(joins),
    }


def _get_or_create_proposal(
    *,
    session: Session,
    workspace_id: str,
    evidence_bundle_uri: str,
    confidence: float,
) -> ReviewProposal:
    existing = (
        session.execute(
            select(ReviewProposal).where(
                ReviewProposal.workspace_id == workspace_id,
                ReviewProposal.proposal_type == "semantic_manifest_change_proposal",
                ReviewProposal.evidence_bundle_uri == evidence_bundle_uri,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing
    row = ReviewProposal(
        proposal_id=new_ulid(),
        workspace_id=workspace_id,
        proposal_type="semantic_manifest_change_proposal",
        evidence_bundle_uri=evidence_bundle_uri,
        confidence=confidence,
        status="open",
    )
    session.add(row)
    session.flush()
    return row


def _get_or_create_blocking_task(
    *,
    session: Session,
    workspace_id: str,
    proposal_id: str,
) -> ReviewTask:
    existing = (
        session.execute(
            select(ReviewTask).where(
                ReviewTask.workspace_id == workspace_id,
                ReviewTask.subject_ref == proposal_id,
                ReviewTask.priority == "quality_critical",
                ReviewTask.blocking.is_(True),
                ReviewTask.status.in_(("open", "in_review")),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing
    row = ReviewTask(
        task_id=new_ulid(),
        workspace_id=workspace_id,
        priority="quality_critical",
        subject_ref=proposal_id,
        status="open",
        blocking=True,
    )
    session.add(row)
    session.flush()
    return row


def _json_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item).strip()]
        return sorted(set(result))
    return []


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value.strip().lower())
    if not normalized:
        return "entity"
    if normalized[0].isdigit():
        return f"e_{normalized}"
    return normalized


def _unique_entity_id(*, base: str, existing: set[str]) -> str:
    candidate = base
    suffix = 1
    while candidate in existing:
        suffix += 1
        candidate = f"{base}_{suffix}"
    existing.add(candidate)
    return candidate


def _pick_primary_key(columns: list[str]) -> str:
    if not columns:
        return "id"
    lower = {column.lower(): column for column in columns}
    if "id" in lower:
        return lower["id"]
    for column in columns:
        if column.lower().endswith("_id"):
            return column
    return columns[0]


def _infer_joins(entities: list[dict[str, object]]) -> list[dict[str, object]]:
    joins: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for left in entities:
        left_entity_id = str(left["entity_id"])
        left_primary_key = str(left["primary_key"])
        for right in entities:
            right_entity_id = str(right["entity_id"])
            if left_entity_id == right_entity_id:
                continue
            right_attributes_raw = right.get("attributes", [])
            right_attributes = (
                [str(item) for item in right_attributes_raw]
                if isinstance(right_attributes_raw, list)
                else []
            )
            if left_primary_key not in right_attributes:
                continue
            join_id = f"{right_entity_id}_to_{left_entity_id}"
            if join_id in seen_ids:
                continue
            seen_ids.add(join_id)
            joins.append(
                {
                    "join_id": join_id,
                    "left_entity_id": right_entity_id,
                    "right_entity_id": left_entity_id,
                    "left_key": left_primary_key,
                    "right_key": left_primary_key,
                    "join_type": "left",
                }
            )
    return sorted(joins, key=lambda item: str(item["join_id"]))
