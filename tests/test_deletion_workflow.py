from __future__ import annotations

from pathlib import Path

from backend.control_plane.deletion import DeletionRequest, execute_deletion_workflow


def test_deletion_workflow_blocks_on_legal_hold(tmp_path: Path) -> None:
    result = execute_deletion_workflow(
        DeletionRequest(
            workspace_id="w1",
            subject_selector={"customer_id": "c1"},
            legal_hold_active=True,
            approved=True,
            affected_snapshots=["silver_snap_1"],
            affected_indexes=["search_idx_1"],
        ),
        output_root=tmp_path.as_posix(),
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "legal_hold_active"
    assert result["impact_preview"]["affected_snapshots"] == ["silver_snap_1"]


def test_deletion_workflow_writes_evidence_report_when_approved(tmp_path: Path) -> None:
    result = execute_deletion_workflow(
        DeletionRequest(
            workspace_id="w1",
            subject_selector={"customer_id": "c1"},
            legal_hold_active=False,
            approved=True,
            affected_snapshots=["silver_snap_1"],
            affected_indexes=["search_idx_1"],
            backup_reference="backup://2026-02-17/snap-1",
        ),
        output_root=tmp_path.as_posix(),
    )
    assert result["status"] == "executed"
    assert result["evidence_report_path"] is not None
    report_path = Path(str(result["evidence_report_path"]))
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "backup://2026-02-17/snap-1" in report
