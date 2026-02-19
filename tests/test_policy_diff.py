from __future__ import annotations

from backend.shared_domain.policy_diff import compute_policy_impact_diff


def test_compute_policy_impact_diff_detects_result_and_mask_changes() -> None:
    before = {
        "scenarios": [
            {
                "id": "s1",
                "result": "allow",
                "reason": "allow",
                "applied_masks": {"email": "hash"},
                "applied_filters": {},
            },
            {
                "id": "s2",
                "result": "allow",
                "reason": "allow",
                "applied_masks": {},
                "applied_filters": {},
            },
        ]
    }
    after = {
        "scenarios": [
            {
                "id": "s1",
                "result": "allow",
                "reason": "allow",
                "applied_masks": {"email": "redact"},
                "applied_filters": {},
            },
            {
                "id": "s2",
                "result": "deny",
                "reason": "policy_denied",
                "applied_masks": {},
                "applied_filters": {"workspace_id": "w1"},
            },
        ]
    }
    diff = compute_policy_impact_diff(
        before_report=before,
        after_report=after,
        protected_scenario_ids=["s2"],
    )
    assert diff["status"] == "changed"
    summary = diff["summary"]
    assert isinstance(summary, dict)
    assert summary["result_change_count"] == 1
    assert summary["mask_change_count"] == 1
    assert summary["filter_change_count"] == 1
    invariants = diff["invariants"]
    assert isinstance(invariants, dict)
    assert invariants["protected_denials"] == ["s2"]


def test_compute_policy_impact_diff_returns_unchanged_status() -> None:
    payload = {
        "scenarios": [
            {
                "id": "same",
                "result": "allow",
                "reason": "allow",
                "applied_masks": {"col": "hash"},
                "applied_filters": {"workspace_id": "w1"},
            }
        ]
    }
    diff = compute_policy_impact_diff(before_report=payload, after_report=payload)
    assert diff["status"] == "unchanged"
    summary = diff["summary"]
    assert isinstance(summary, dict)
    assert summary["result_change_count"] == 0
    assert summary["mask_change_count"] == 0
    assert summary["filter_change_count"] == 0
