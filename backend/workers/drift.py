"""Schema drift detection and review-task generation."""

from __future__ import annotations

from backend.shared_domain.ids import new_ulid


def detect_schema_drift(
    previous_columns: list[str], current_columns: list[str]
) -> dict[str, object]:
    """Compute drift event between two schema snapshots."""
    previous = set(previous_columns)
    current = set(current_columns)
    added = sorted(current - previous)
    removed = sorted(previous - current)
    changed = bool(added or removed)
    severity = "none"
    if changed and removed:
        severity = "high"
    elif changed:
        severity = "medium"
    return {
        "drift_detected": changed,
        "severity": severity,
        "added_columns": added,
        "removed_columns": removed,
    }


def drift_to_review_task(
    *,
    workspace_id: str,
    dataset_id: str,
    drift_event: dict[str, object],
) -> dict[str, object]:
    """Create review task payload from drift event."""
    return {
        "task_id": new_ulid(),
        "workspace_id": workspace_id,
        "dataset_id": dataset_id,
        "priority": "quality_critical",
        "status": "open",
        "blocking": bool(drift_event.get("drift_detected", False)),
        "drift": drift_event,
    }
