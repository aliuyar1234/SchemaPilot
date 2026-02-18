"""Semantic query binding for AI gateway requests."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.metadata_models import GovernancePolicy
from backend.shared_domain.semantic import semantic_manifest_checksum, validate_semantic_manifest

ACTIVE_POLICY_TYPE = "semantic_manifest"
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class SemanticQueryBinding:
    """Resolved semantic query details used by gateway execution."""

    sql_text: str
    dataset_ids: list[str]
    metric_id: str
    group_by: list[str]
    manifest_checksum: str


def bind_semantic_query(
    *,
    session_factory: Callable[[], Session],
    workspace_id: str,
    semantic_query: Mapping[str, object],
) -> SemanticQueryBinding:
    """Resolve a semantic query payload into executable SQL and dataset context."""
    metric_id = str(semantic_query.get("metric_id", "")).strip()
    if not metric_id:
        raise ValueError("semantic_metric_required")
    if not _is_safe_identifier(metric_id):
        raise ValueError("semantic_metric_invalid")

    state = _load_active_semantic_state(
        session_factory=session_factory,
        workspace_id=workspace_id,
    )
    if state is None:
        raise ValueError("semantic_manifest_not_configured")
    manifest_raw = state.get("manifest")
    if not isinstance(manifest_raw, dict):
        raise ValueError("semantic_manifest_not_configured")
    try:
        manifest = validate_semantic_manifest(
            manifest_raw,
            expected_workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise ValueError("semantic_manifest_invalid") from exc

    entities_raw = manifest.get("entities", [])
    metrics_raw = manifest.get("metrics", [])
    joins_raw = manifest.get("joins", [])
    entities: list[dict[str, object]] = []
    metrics: list[dict[str, object]] = []
    joins: list[dict[str, object]] = []
    if isinstance(entities_raw, list):
        entities = [entity for entity in entities_raw if isinstance(entity, dict)]
    if isinstance(metrics_raw, list):
        metrics = [metric for metric in metrics_raw if isinstance(metric, dict)]
    if isinstance(joins_raw, list):
        joins = [join for join in joins_raw if isinstance(join, dict)]
    entity_by_id = {
        str(entity["entity_id"]): entity
        for entity in entities
        if isinstance(entity, dict) and isinstance(entity.get("entity_id"), str)
    }
    metric = _find_metric(metrics, metric_id)
    if metric is None:
        raise ValueError("semantic_metric_not_found")

    metric_entity_id = str(metric["entity_id"])
    if metric_entity_id not in entity_by_id:
        raise ValueError("semantic_metric_entity_missing")
    group_by = _parse_group_by(
        semantic_query=semantic_query,
        default_entity_id=metric_entity_id,
        entity_by_id=entity_by_id,
    )

    involved_entities = [metric_entity_id]
    for value in group_by:
        entity_id = value.split(".", 1)[0]
        if entity_id not in involved_entities:
            involved_entities.append(entity_id)
    aliases = {entity_id: f"t{idx}" for idx, entity_id in enumerate(involved_entities)}

    select_parts: list[str] = []
    group_by_expressions: list[str] = []
    for group_item in group_by:
        entity_id, column = group_item.split(".", 1)
        alias = aliases[entity_id]
        select_parts.append(f"{alias}.{column} as {entity_id}__{column}")
        group_by_expressions.append(f"{alias}.{column}")

    metric_sql = _build_metric_expression(metric=metric, alias=aliases[metric_entity_id])
    select_parts.append(f"{metric_sql} as metric_value")

    from_clause = f"from gold.{metric_entity_id} as {aliases[metric_entity_id]}"
    join_clauses = [
        _build_join_clause(
            base_entity_id=metric_entity_id,
            target_entity_id=entity_id,
            joins=joins,
            aliases=aliases,
        )
        for entity_id in involved_entities
        if entity_id != metric_entity_id
    ]
    group_clause = ""
    if group_by_expressions:
        group_clause = " group by " + ", ".join(group_by_expressions)
    sql_text = (
        "select "
        + ", ".join(select_parts)
        + " "
        + from_clause
        + (" " + " ".join(join_clauses) if join_clauses else "")
        + group_clause
    )

    dataset_ids = sorted(
        {
            str(entity_by_id[entity_id]["dataset_id"])
            for entity_id in involved_entities
            if str(entity_by_id[entity_id]["dataset_id"]).strip()
        }
    )
    if not dataset_ids:
        raise ValueError("semantic_dataset_binding_missing")

    manifest_checksum = str(state.get("manifest_checksum", "")).strip()
    if not manifest_checksum:
        manifest_checksum = semantic_manifest_checksum(manifest)
    return SemanticQueryBinding(
        sql_text=sql_text,
        dataset_ids=dataset_ids,
        metric_id=metric_id,
        group_by=group_by,
        manifest_checksum=manifest_checksum,
    )


def _load_active_semantic_state(
    *,
    session_factory: Callable[[], Session],
    workspace_id: str,
) -> dict[str, object] | None:
    session = session_factory()
    try:
        row = (
            session.execute(
                select(GovernancePolicy).where(
                    GovernancePolicy.workspace_id == workspace_id,
                    GovernancePolicy.policy_type == ACTIVE_POLICY_TYPE,
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
    return {str(key): value for key, value in payload.items()}


def _find_metric(metrics: list[dict[str, object]], metric_id: str) -> dict[str, object] | None:
    for metric in metrics:
        if str(metric.get("metric_id", "")) == metric_id:
            return metric
    return None


def _parse_group_by(
    *,
    semantic_query: Mapping[str, object],
    default_entity_id: str,
    entity_by_id: dict[str, dict[str, object]],
) -> list[str]:
    group_by_raw = semantic_query.get("group_by", [])
    if not isinstance(group_by_raw, list):
        raise ValueError("semantic_group_by_invalid")
    normalized: list[str] = []
    for item_raw in group_by_raw:
        item = str(item_raw).strip()
        if not item:
            continue
        if "." in item:
            parts = item.split(".", 1)
            entity_id, column = parts[0].strip(), parts[1].strip()
        else:
            entity_id, column = default_entity_id, item
        if not _is_safe_identifier(entity_id) or not _is_safe_identifier(column):
            raise ValueError("semantic_group_by_invalid")
        entity = entity_by_id.get(entity_id)
        if entity is None:
            raise ValueError("semantic_group_by_entity_not_found")
        attribute_values = entity.get("attributes", [])
        attributes = (
            [str(value) for value in attribute_values if isinstance(value, str)]
            if isinstance(attribute_values, list)
            else []
        )
        allowed_columns = {
            str(entity.get("primary_key", "")),
            *attributes,
        }
        if column not in allowed_columns:
            raise ValueError("semantic_group_by_column_not_found")
        key = f"{entity_id}.{column}"
        if key not in normalized:
            normalized.append(key)
    return normalized


def _build_metric_expression(*, metric: dict[str, object], alias: str) -> str:
    aggregation = str(metric.get("aggregation", "")).strip().lower()
    field = str(metric.get("field", "")).strip()
    allowed_aggregations = {"count", "sum", "avg", "min", "max"}
    if aggregation not in allowed_aggregations:
        raise ValueError("semantic_metric_aggregation_not_supported")
    if field == "*":
        if aggregation != "count":
            raise ValueError("semantic_metric_field_invalid")
        return "count(*)"
    if not _is_safe_identifier(field):
        raise ValueError("semantic_metric_field_invalid")
    return f"{aggregation}({alias}.{field})"


def _build_join_clause(
    *,
    base_entity_id: str,
    target_entity_id: str,
    joins: list[dict[str, object]],
    aliases: dict[str, str],
) -> str:
    join = _find_join_between(joins=joins, left=base_entity_id, right=target_entity_id)
    if join is None:
        raise ValueError("semantic_join_path_missing")
    join_type_raw = str(join.get("join_type", "inner")).strip().lower()
    join_type = {
        "inner": "inner join",
        "left": "left join",
        "right": "right join",
        "full": "full outer join",
    }.get(join_type_raw, "inner join")
    left_entity_id = str(join["left_entity_id"])
    right_entity_id = str(join["right_entity_id"])
    left_key = str(join["left_key"])
    right_key = str(join["right_key"])
    if not _is_safe_identifier(left_key) or not _is_safe_identifier(right_key):
        raise ValueError("semantic_join_key_invalid")

    return (
        f"{join_type} gold.{target_entity_id} as {aliases[target_entity_id]} on "
        f"{aliases[left_entity_id]}.{left_key} = {aliases[right_entity_id]}.{right_key}"
    )


def _find_join_between(
    *,
    joins: list[dict[str, object]],
    left: str,
    right: str,
) -> dict[str, object] | None:
    for join in joins:
        left_entity_id = str(join.get("left_entity_id", "")).strip()
        right_entity_id = str(join.get("right_entity_id", "")).strip()
        if {left_entity_id, right_entity_id} != {left, right}:
            continue
        return {
            "join_id": str(join.get("join_id", "")),
            "left_entity_id": left_entity_id,
            "right_entity_id": right_entity_id,
            "left_key": str(join.get("left_key", "")),
            "right_key": str(join.get("right_key", "")),
            "join_type": str(join.get("join_type", "inner")),
        }
    return None


def _is_safe_identifier(value: str) -> bool:
    return bool(IDENTIFIER_RE.match(value))
