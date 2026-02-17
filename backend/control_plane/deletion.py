"""Deletion workflow with legal hold blocking and evidence report output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.shared_domain.ids import new_ulid


@dataclass(frozen=True)
class DeletionRequest:
    """Deletion workflow request."""

    workspace_id: str
    subject_selector: dict[str, object]
    legal_hold_active: bool
    approved: bool
    affected_snapshots: list[str]
    affected_indexes: list[str]
    backup_reference: str | None = None


def execute_deletion_workflow(request: DeletionRequest, output_root: str) -> dict[str, object]:
    """Execute deletion workflow in fail-closed mode."""
    impact_preview = {
        "subject_selector": request.subject_selector,
        "affected_snapshots": sorted(request.affected_snapshots),
        "affected_indexes": sorted(request.affected_indexes),
    }
    if request.legal_hold_active:
        return {
            "status": "blocked",
            "reason": "legal_hold_active",
            "evidence_report_path": None,
            "impact_preview": impact_preview,
        }
    if not request.approved:
        return {
            "status": "blocked",
            "reason": "missing_approval",
            "evidence_report_path": None,
            "impact_preview": impact_preview,
        }
    evidence = {
        "deletion_id": new_ulid(),
        "workspace_id": request.workspace_id,
        "subject_selector": request.subject_selector,
        "impact_preview": impact_preview,
        "approval": {"approved": True, "mode": "explicit_workflow"},
        "execution": {
            "status": "executed_stub",
            "snapshots_updated": sorted(request.affected_snapshots),
            "indexes_updated": sorted(request.affected_indexes),
            "records_deleted_estimate": len(request.affected_snapshots)
            + len(request.affected_indexes),
            "backup_reference": request.backup_reference,
        },
    }
    out_dir = Path(output_root) / "deletions" / request.workspace_id
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{evidence['deletion_id']}.json"
    report_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "status": "executed",
        "reason": "approved",
        "evidence_report_path": report_path.as_posix(),
    }
