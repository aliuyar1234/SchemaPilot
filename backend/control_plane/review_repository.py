"""Review queue repository operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.control_plane.db_models import ReviewApproval, ReviewProposal, ReviewTask
from backend.shared_domain.ids import new_ulid


def create_proposal(
    session: Session,
    *,
    workspace_id: str,
    proposal_type: str,
    evidence_bundle_uri: str,
    confidence: float,
) -> dict[str, object]:
    proposal = ReviewProposal(
        proposal_id=new_ulid(),
        workspace_id=workspace_id,
        proposal_type=proposal_type,
        evidence_bundle_uri=evidence_bundle_uri,
        confidence=confidence,
        status="open",
    )
    session.add(proposal)
    session.flush()
    return {
        "proposal_id": proposal.proposal_id,
        "workspace_id": proposal.workspace_id,
        "proposal_type": proposal.proposal_type,
        "evidence_bundle_uri": proposal.evidence_bundle_uri,
        "confidence": proposal.confidence,
        "status": proposal.status,
    }


def create_review_task(
    session: Session,
    *,
    workspace_id: str,
    subject_ref: str,
    priority: str,
    blocking: bool,
) -> dict[str, object]:
    task = ReviewTask(
        task_id=new_ulid(),
        workspace_id=workspace_id,
        priority=priority,
        subject_ref=subject_ref,
        status="open",
        blocking=blocking,
    )
    session.add(task)
    session.flush()
    return {
        "task_id": task.task_id,
        "workspace_id": task.workspace_id,
        "priority": task.priority,
        "subject_ref": task.subject_ref,
        "status": task.status,
        "blocking": task.blocking,
    }


def list_review_tasks(session: Session, workspace_id: str) -> list[dict[str, object]]:
    rows = session.execute(
        select(ReviewTask).where(ReviewTask.workspace_id == workspace_id)
    ).scalars()
    tasks: list[dict[str, object]] = []
    for row in rows:
        proposal = session.get(ReviewProposal, row.subject_ref)
        tasks.append(
            {
                "task_id": row.task_id,
                "workspace_id": row.workspace_id,
                "priority": row.priority,
                "subject_ref": row.subject_ref,
                "status": row.status,
                "blocking": row.blocking,
                "evidence_bundle_uri": proposal.evidence_bundle_uri if proposal else None,
                "confidence": proposal.confidence if proposal else None,
                "proposal_type": proposal.proposal_type if proposal else None,
            }
        )
    return tasks


def decide_review_task(
    session: Session,
    *,
    workspace_id: str,
    task_id: str,
    actor_id: str,
    decision: str,
    reason: str,
) -> dict[str, object] | None:
    task = session.get(ReviewTask, task_id)
    if task is None or task.workspace_id != workspace_id:
        return None
    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "defer": "deferred",
    }
    task.status = status_map.get(decision, "deferred")

    approval = ReviewApproval(
        approval_id=new_ulid(),
        task_id=task_id,
        actor_id=actor_id,
        decision=decision,
        decision_reason=reason,
        applied_changes_ref="review_queue",
        audit_event_id=new_ulid(),
    )
    session.add(approval)
    session.flush()
    return {
        "approval_id": approval.approval_id,
        "task_id": approval.task_id,
        "actor_id": approval.actor_id,
        "decision": approval.decision,
        "decision_reason": approval.decision_reason,
    }


def unresolved_blocking_task_count(session: Session, workspace_id: str) -> int:
    rows = session.execute(
        select(ReviewTask).where(
            ReviewTask.workspace_id == workspace_id,
            ReviewTask.blocking.is_(True),
            ReviewTask.status.in_(("open", "in_review")),
        )
    ).scalars()
    return len(list(rows))
