"""Deterministic policy impact diff helpers."""

from __future__ import annotations

from collections.abc import Iterable


def compute_policy_impact_diff(
    *,
    before_report: dict[str, object],
    after_report: dict[str, object],
    protected_scenario_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    """Compute a deterministic no-data policy impact diff."""
    before_rows = _index_scenarios(before_report)
    after_rows = _index_scenarios(after_report)
    all_ids = sorted(set(before_rows).union(after_rows))
    protected = {item.strip() for item in (protected_scenario_ids or []) if item.strip()}

    result_changes: list[dict[str, object]] = []
    mask_changes: list[dict[str, object]] = []
    filter_changes: list[dict[str, object]] = []
    protected_denials: list[str] = []

    for scenario_id in all_ids:
        before = before_rows.get(scenario_id, {})
        after = after_rows.get(scenario_id, {})
        before_result = str(before.get("result", "missing"))
        after_result = str(after.get("result", "missing"))
        if before_result != after_result:
            result_changes.append(
                {
                    "id": scenario_id,
                    "before": before_result,
                    "after": after_result,
                    "before_reason": str(before.get("reason", "unknown")),
                    "after_reason": str(after.get("reason", "unknown")),
                }
            )
        before_masks = _normalize_mapping(before.get("applied_masks"))
        after_masks = _normalize_mapping(after.get("applied_masks"))
        if before_masks != after_masks:
            mask_changes.append(
                {
                    "id": scenario_id,
                    "before": before_masks,
                    "after": after_masks,
                }
            )
        before_filters = _normalize_mapping(before.get("applied_filters"))
        after_filters = _normalize_mapping(after.get("applied_filters"))
        if before_filters != after_filters:
            filter_changes.append(
                {
                    "id": scenario_id,
                    "before": before_filters,
                    "after": after_filters,
                }
            )
        if scenario_id in protected and after_result == "deny":
            protected_denials.append(scenario_id)

    return {
        "status": (
            "changed"
            if result_changes or mask_changes or filter_changes
            else "unchanged"
        ),
        "summary": {
            "before_scenario_count": len(before_rows),
            "after_scenario_count": len(after_rows),
            "result_change_count": len(result_changes),
            "mask_change_count": len(mask_changes),
            "filter_change_count": len(filter_changes),
            "protected_denial_count": len(protected_denials),
        },
        "result_changes": result_changes,
        "mask_changes": mask_changes,
        "filter_changes": filter_changes,
        "invariants": {
            "protected_scenario_ids": sorted(protected),
            "protected_denials": sorted(protected_denials),
        },
    }


def _index_scenarios(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    scenarios_raw = payload.get("scenarios", [])
    if not isinstance(scenarios_raw, list):
        return {}
    indexed: dict[str, dict[str, object]] = {}
    for row in scenarios_raw:
        if not isinstance(row, dict):
            continue
        scenario_id = str(row.get("id", "")).strip()
        if not scenario_id:
            continue
        indexed[scenario_id] = {str(key): value for key, value in row.items()}
    return indexed


def _normalize_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, object] = {}
    for key in sorted(value):
        normalized[str(key)] = value[key]
    return normalized
