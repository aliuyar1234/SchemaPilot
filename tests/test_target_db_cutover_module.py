from __future__ import annotations

from backend.workers.db_builder.cutover import (
    apply_shadow_cutover,
    build_shadow_cutover_plan,
    rollback_shadow_cutover,
)


def test_shadow_cutover_apply_and_rollback_payloads() -> None:
    plan = build_shadow_cutover_plan(
        workspace_id="w1",
        from_target_db_id="tdb-old",
        to_target_db_id="tdb-new",
    )
    try:
        apply_shadow_cutover(
            plan=plan,
            approved=False,
            current_active_target_db_id="tdb-old",
        )
    except ValueError as exc:
        assert "shadow_cutover_approval_required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")

    applied = apply_shadow_cutover(
        plan=plan,
        approved=True,
        current_active_target_db_id="tdb-old",
    )
    assert applied["status"] == "cutover_applied"
    rollback = rollback_shadow_cutover(
        workspace_id="w1",
        rollback_target_db_id=str(applied["rollback_target_db_id"]),
    )
    assert rollback["status"] == "rollback_ready"
