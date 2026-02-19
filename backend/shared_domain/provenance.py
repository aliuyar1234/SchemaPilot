"""Versioned provenance contracts used by gateway responses."""

from __future__ import annotations

from collections.abc import Mapping

PROVENANCE_VERSION = "1"
PROVENANCE_VERSION_V2 = "2"


def build_provenance_v1(
    *,
    workspace_id: str,
    policy_decision_id: str,
    datasets_used: list[str],
    build_id: str,
    query_id: str,
    snapshots: list[dict[str, object]] | None = None,
    decision_reason: str,
    applied_filters: Mapping[str, object] | None = None,
    applied_masks: Mapping[str, object] | None = None,
    citations: list[str] | None = None,
    allowed_dataset_ids: list[str] | None = None,
    policy_pack: Mapping[str, object] | None = None,
    target_db_id: str | None = None,
    target_schema_ref: str | None = None,
    breakglass_active: bool = False,
    breakglass_request_id: str | None = None,
) -> dict[str, object]:
    """Construct a stable provenance payload for gateway responses."""
    payload: dict[str, object] = {
        "provenance_version": PROVENANCE_VERSION,
        "workspace_id": workspace_id,
        "policy_decision_id": policy_decision_id,
        "query_id": query_id,
        "build_id": build_id,
        "datasets_used": sorted({str(item) for item in datasets_used if str(item)}),
        "snapshots": _normalize_snapshots(snapshots),
        "decision_reason": decision_reason,
        "applied_filters": dict(applied_filters or {}),
        "applied_masks": dict(applied_masks or {}),
    }
    if citations is not None:
        payload["citations"] = sorted({str(item) for item in citations if str(item)})
    if allowed_dataset_ids is not None:
        payload["allowed_dataset_ids"] = sorted(
            {str(item) for item in allowed_dataset_ids if str(item)}
        )
    if policy_pack is not None:
        payload["policy_pack"] = {
            "pack_id": str(policy_pack.get("pack_id", "")),
            "version": _coerce_int(policy_pack.get("version"), default=0),
        }
    if target_db_id is not None:
        payload["target_db_id"] = str(target_db_id)
    if target_schema_ref is not None:
        payload["target_schema_ref"] = str(target_schema_ref)
    if breakglass_active:
        payload["breakglass"] = True
        if breakglass_request_id is not None:
            payload["breakglass_request_id"] = str(breakglass_request_id)
    _validate_provenance_v1(payload)
    return payload


def build_provenance_v2(
    *,
    workspace_id: str,
    policy_decision_id: str,
    datasets_used: list[str],
    build_id: str,
    query_id: str,
    snapshots: list[dict[str, object]] | None = None,
    decision_reason: str,
    applied_filters: Mapping[str, object] | None = None,
    applied_masks: Mapping[str, object] | None = None,
    citations: list[str] | None = None,
    allowed_dataset_ids: list[str] | None = None,
    policy_pack: Mapping[str, object] | None = None,
    target_db_id: str | None = None,
    target_schema_ref: str | None = None,
    breakglass_active: bool = False,
    breakglass_request_id: str | None = None,
    engine_type: str | None = None,
    evidence_bundle_refs: list[str] | None = None,
) -> dict[str, object]:
    """Construct provenance schema v2 while preserving v1-compatible semantics."""
    payload: dict[str, object] = {
        "provenance_version": PROVENANCE_VERSION_V2,
        "workspace_id": workspace_id,
        "policy_decision_id": policy_decision_id,
        "query_id": query_id,
        "build_id": build_id,
        "datasets_used": sorted({str(item) for item in datasets_used if str(item)}),
        "snapshots": _normalize_snapshots(snapshots),
        "decision_reason": decision_reason,
        "applied_filters": dict(applied_filters or {}),
        "applied_masks": dict(applied_masks or {}),
        "engine_type": str(engine_type or "unknown").strip() or "unknown",
        "evidence_bundle_refs": sorted(
            {str(item).strip() for item in (evidence_bundle_refs or []) if str(item).strip()}
        ),
    }
    if citations is not None:
        payload["citations"] = sorted({str(item) for item in citations if str(item)})
    if allowed_dataset_ids is not None:
        payload["allowed_dataset_ids"] = sorted(
            {str(item) for item in allowed_dataset_ids if str(item)}
        )
    if policy_pack is not None:
        payload["policy_pack"] = {
            "pack_id": str(policy_pack.get("pack_id", "")),
            "version": _coerce_int(policy_pack.get("version"), default=0),
        }
    if target_db_id is not None:
        payload["target_db_id"] = str(target_db_id)
    if target_schema_ref is not None:
        payload["target_schema_ref"] = str(target_schema_ref)
    if breakglass_active:
        payload["breakglass"] = True
        if breakglass_request_id is not None:
            payload["breakglass_request_id"] = str(breakglass_request_id)
    _validate_provenance_v2(payload)
    return payload


def _normalize_snapshots(
    snapshots: list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    if snapshots is None:
        return []
    normalized: list[dict[str, object]] = []
    for row in snapshots:
        if not isinstance(row, dict):
            continue
        dataset_id = str(row.get("dataset_id", "")).strip()
        snapshot_id = str(row.get("snapshot_id", "")).strip()
        if not dataset_id or not snapshot_id:
            continue
        normalized.append({"dataset_id": dataset_id, "snapshot_id": snapshot_id})
    return sorted(normalized, key=lambda item: (item["dataset_id"], item["snapshot_id"]))


def _validate_provenance_v1(payload: Mapping[str, object]) -> None:
    required_fields = (
        "provenance_version",
        "workspace_id",
        "policy_decision_id",
        "query_id",
        "build_id",
        "datasets_used",
        "snapshots",
    )
    for field in required_fields:
        if field not in payload:
            raise ValueError(f"missing_provenance_field:{field}")
        value = payload[field]
        if field in {
            "provenance_version",
            "workspace_id",
            "policy_decision_id",
            "query_id",
            "build_id",
        }:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"invalid_provenance_field:{field}")
        if field in {"datasets_used", "snapshots"} and not isinstance(value, list):
            raise ValueError(f"invalid_provenance_field:{field}")


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


def _validate_provenance_v2(payload: Mapping[str, object]) -> None:
    _validate_provenance_v1(
        {
            **payload,
            "provenance_version": PROVENANCE_VERSION,
        }
    )
    if payload.get("provenance_version") != PROVENANCE_VERSION_V2:
        raise ValueError("invalid_provenance_field:provenance_version")
    engine_type = payload.get("engine_type")
    if not isinstance(engine_type, str) or not engine_type.strip():
        raise ValueError("invalid_provenance_field:engine_type")
    evidence_bundle_refs = payload.get("evidence_bundle_refs")
    if not isinstance(evidence_bundle_refs, list):
        raise ValueError("invalid_provenance_field:evidence_bundle_refs")
