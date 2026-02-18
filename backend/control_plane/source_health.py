"""Source freshness SLA management and evaluation helpers."""

from __future__ import annotations

import json
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.control_plane.review_repository import create_proposal, create_review_task
from backend.shared_domain.evidence_store import store_evidence_bundle
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import CatalogDataset, GovernancePolicy, ReviewTask

SOURCE_SLA_POLICY_TYPE = "source_sla"


def configure_source_sla(
    session: Session,
    *,
    workspace_id: str,
    dataset_id: str,
    freshness_seconds: int,
    enabled: bool,
    actor_id: str,
) -> dict[str, object]:
    """Configure freshness SLA for one dataset."""
    if freshness_seconds <= 0:
        raise ValueError("invalid_freshness_seconds")
    existing = (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == SOURCE_SLA_POLICY_TYPE,
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .all()
    )
    for row in existing:
        payload = _load_payload(row.definition_ref)
        if str(payload.get("dataset_id", "")) == dataset_id:
            payload.update(
                {
                    "freshness_seconds": freshness_seconds,
                    "enabled": enabled,
                    "updated_by": actor_id,
                }
            )
            row.definition_ref = json.dumps(payload, sort_keys=True)
            session.flush()
            return payload

    policy_id = new_ulid()
    payload = {
        "sla_id": policy_id,
        "workspace_id": workspace_id,
        "dataset_id": dataset_id,
        "freshness_seconds": freshness_seconds,
        "enabled": enabled,
        "created_by": actor_id,
    }
    session.add(
        GovernancePolicy(
            policy_id=policy_id,
            workspace_id=workspace_id,
            policy_type=SOURCE_SLA_POLICY_TYPE,
            definition_ref=json.dumps(payload, sort_keys=True),
            status="active",
        )
    )
    session.flush()
    return payload


def list_source_slas(session: Session, *, workspace_id: str) -> list[dict[str, object]]:
    """List configured source freshness SLAs."""
    rows = (
        session.execute(
            select(GovernancePolicy)
            .where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == SOURCE_SLA_POLICY_TYPE,
                GovernancePolicy.status == "active",
            )
            .order_by(GovernancePolicy.policy_id)
        )
        .scalars()
        .all()
    )
    return [_load_payload(row.definition_ref) for row in rows]


def evaluate_source_slas(
    session: Session,
    *,
    workspace_id: str,
    storage_root: str,
    now_epoch: int | None = None,
) -> dict[str, object]:
    """Evaluate freshness SLAs and create review tasks for violations."""
    now = int(time.time()) if now_epoch is None else now_epoch
    violations: list[dict[str, object]] = []
    created_task_ids: list[str] = []
    for sla in list_source_slas(session, workspace_id=workspace_id):
        if not bool(sla.get("enabled", False)):
            continue
        dataset_id = str(sla.get("dataset_id", "")).strip()
        freshness_seconds = _coerce_int(sla.get("freshness_seconds"), default=0)
        dataset = session.get(CatalogDataset, dataset_id)
        if dataset is None:
            continue
        summary = (
            dataset.sensitivity_summary_json
            if isinstance(dataset.sensitivity_summary_json, dict)
            else {}
        )
        profile = summary.get("profile", {})
        if not isinstance(profile, dict):
            profile = {}
        last_profile_epoch = _coerce_int(profile.get("last_profile_epoch"), default=0)
        age_seconds = max(now - last_profile_epoch, 0)
        if last_profile_epoch == 0 or age_seconds > freshness_seconds:
            violation = {
                "dataset_id": dataset_id,
                "freshness_seconds": freshness_seconds,
                "last_profile_epoch": last_profile_epoch,
                "age_seconds": age_seconds,
            }
            violations.append(violation)
            stored = store_evidence_bundle(
                workspace_id=workspace_id,
                storage_root=storage_root,
                bundle_type="source_sla_violation",
                payload=violation,
            )
            proposal = create_proposal(
                session,
                workspace_id=workspace_id,
                proposal_type="source_freshness_violation",
                evidence_bundle_uri=stored.evidence_bundle_uri,
                confidence=1.0,
            )
            if _has_open_quality_task(
                session, workspace_id=workspace_id, proposal_id=str(proposal["proposal_id"])
            ):
                continue
            task = create_review_task(
                session,
                workspace_id=workspace_id,
                subject_ref=str(proposal["proposal_id"]),
                priority="quality_critical",
                blocking=True,
            )
            created_task_ids.append(str(task["task_id"]))
    return {
        "workspace_id": workspace_id,
        "evaluated_slas": len(list_source_slas(session, workspace_id=workspace_id)),
        "violation_count": len(violations),
        "violations": violations,
        "created_task_ids": created_task_ids,
    }


def _load_payload(definition_ref: str) -> dict[str, object]:
    try:
        payload = json.loads(definition_ref)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        return {}
    return {str(k): v for k, v in payload.items()}


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _has_open_quality_task(session: Session, *, workspace_id: str, proposal_id: str) -> bool:
    existing = (
        session.execute(
            select(ReviewTask).where(
                ReviewTask.workspace_id == workspace_id,
                ReviewTask.subject_ref == proposal_id,
                ReviewTask.priority == "quality_critical",
                ReviewTask.status.in_(("open", "in_review")),
            )
        )
        .scalars()
        .first()
    )
    return existing is not None
