"""Semantic-constrained SQL agent planning helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.shared_domain.metadata_models import GovernancePolicy

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class SqlAgentPlan:
    """Planned semantic query for gateway execution."""

    workspace_id: str
    semantic_query: dict[str, object]
    confidence: float
    warnings: list[str]


def generate_sql_agent_plan(
    *,
    workspace_id: str,
    question: str,
    session_factory: sessionmaker[Session],
    metric_id: str | None = None,
    group_by: list[str] | None = None,
) -> SqlAgentPlan:
    """Generate semantic-constrained plan from question and optional hints."""
    manifest = _load_effective_semantic_manifest(
        session_factory=session_factory, workspace_id=workspace_id
    )
    metrics = _manifest_metrics(manifest)
    if not metrics:
        raise ValueError("semantic_manifest_missing")

    selected_metric = metric_id.strip() if metric_id else _guess_metric_id(question, metrics)
    if not selected_metric or selected_metric not in metrics:
        raise ValueError("semantic_metric_not_found")

    requested_group_by = list(group_by or _guess_group_by(question, manifest))
    semantic_query = {
        "metric_id": selected_metric,
        "group_by": requested_group_by,
        "filters": {},
    }
    warnings: list[str] = []
    confidence = 0.8
    if metric_id is None:
        warnings.append("metric_inferred")
        confidence = 0.7
    plan = SqlAgentPlan(
        workspace_id=workspace_id,
        semantic_query=semantic_query,
        confidence=confidence,
        warnings=warnings,
    )
    validate_sql_agent_plan(plan)
    return plan


def validate_sql_agent_plan(plan: SqlAgentPlan) -> None:
    """Validate generated plan structure and guard against unsafe identifiers."""
    metric_id = str(plan.semantic_query.get("metric_id", "")).strip()
    if not metric_id or not SAFE_IDENTIFIER.fullmatch(metric_id):
        raise ValueError("semantic_metric_invalid")
    group_by_raw = plan.semantic_query.get("group_by", [])
    if not isinstance(group_by_raw, list):
        raise ValueError("semantic_group_by_invalid")
    for item in group_by_raw:
        identifier = str(item).strip()
        if not identifier or not SAFE_IDENTIFIER.fullmatch(identifier):
            raise ValueError("semantic_group_by_invalid")


def _load_effective_semantic_manifest(
    *, session_factory: sessionmaker[Session], workspace_id: str
) -> dict[str, Any] | None:
    session = session_factory()
    try:
        row = (
            session.execute(
                select(GovernancePolicy).where(
                    GovernancePolicy.workspace_id == workspace_id,
                    GovernancePolicy.policy_type == "semantic_manifest",
                    GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
    finally:
        session.close()
    if row is None:
        return None
    try:
        payload = json.loads(row.definition_ref)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    manifest = payload.get("semantic_manifest", {})
    if not isinstance(manifest, dict):
        return None
    return manifest


def _manifest_metrics(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(manifest, dict):
        return {}
    metrics_raw = manifest.get("metrics", [])
    if not isinstance(metrics_raw, list):
        return {}
    metrics: dict[str, dict[str, Any]] = {}
    for item in metrics_raw:
        if not isinstance(item, dict):
            continue
        metric_id = str(item.get("metric_id", "")).strip()
        if metric_id:
            metrics[metric_id] = item
    return metrics


def _guess_metric_id(question: str, metrics: dict[str, dict[str, Any]]) -> str:
    lowered = question.lower()
    for metric_id in sorted(metrics):
        if metric_id.lower() in lowered:
            return metric_id
    if "count" in lowered:
        for metric_id in sorted(metrics):
            if "count" in metric_id.lower():
                return metric_id
    return sorted(metrics)[0] if metrics else ""


def _guess_group_by(question: str, manifest: dict[str, Any] | None) -> list[str]:
    if not isinstance(manifest, dict):
        return []
    dims_raw = manifest.get("dimensions", [])
    if not isinstance(dims_raw, list):
        return []
    lowered = question.lower()
    candidates: list[str] = []
    for item in dims_raw:
        if not isinstance(item, dict):
            continue
        dim_id = str(item.get("dimension_id", "")).strip()
        if dim_id and dim_id.lower() in lowered and SAFE_IDENTIFIER.fullmatch(dim_id):
            candidates.append(dim_id)
    return sorted(set(candidates))

