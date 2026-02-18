"""SQLAlchemy models for shared SchemaPilot metadata domains."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.db import Base


class Workspace(Base):
    """Workspace metadata."""

    __tablename__ = "workspaces"

    workspace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    profile: Mapped[str] = mapped_column(String(32), nullable=False)
    security_baseline: Mapped[str] = mapped_column(String(32), nullable=False)


class CatalogSource(Base):
    """Normative catalog.sources table."""

    __tablename__ = "catalog_sources"

    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.workspace_id"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    credentials_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)


class CatalogDataset(Base):
    """Normative catalog.datasets table."""

    __tablename__ = "catalog_datasets"

    dataset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    logical_name: Mapped[str] = mapped_column(Text, nullable=False)
    physical_locator: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sensitivity_summary_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class RunRecord(Base):
    """Normative runs.runs table."""

    __tablename__ = "runs_runs"

    run_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.workspace_id"), index=True, nullable=False
    )
    run_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_refs_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    output_refs_json: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class ReviewProposal(Base):
    """Normative review.proposals table."""

    __tablename__ = "review_proposals"

    proposal_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    proposal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_bundle_uri: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class ReviewTask(Base):
    """Normative review.review_tasks table."""

    __tablename__ = "review_review_tasks"

    task_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    priority: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ReviewApproval(Base):
    """Normative review.approvals table."""

    __tablename__ = "review_approvals"

    approval_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(26), nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)
    applied_changes_ref: Mapped[str] = mapped_column(Text, nullable=False)
    audit_event_id: Mapped[str] = mapped_column(String(26), nullable=False)


class GovernancePolicy(Base):
    """Normative governance.policies table."""

    __tablename__ = "governance_policies"

    policy_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class GovernanceRetentionPolicy(Base):
    """Retention policy configuration (disabled by default)."""

    __tablename__ = "governance_retention_policies"

    retention_policy_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    purge_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legal_hold_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class GovernancePurgeRun(Base):
    """Retention purge execution metadata and evidence linkage."""

    __tablename__ = "governance_purge_runs"

    purge_run_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    retention_policy_id: Mapped[str] = mapped_column(String(26), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    deleted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_paths_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_bundle_uri: Mapped[str] = mapped_column(Text, nullable=False)


class GovernanceDeletionRequest(Base):
    """Deletion workflow request state."""

    __tablename__ = "governance_deletion_requests"

    deletion_request_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    requester_actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_selector_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    affected_snapshots_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    affected_indexes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    legal_hold_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_bundle_uri: Mapped[str | None] = mapped_column(Text, nullable=True)


class GovernanceDeletionApproval(Base):
    """Deletion approval records enforcing separation of duties."""

    __tablename__ = "governance_deletion_approvals"

    deletion_approval_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    deletion_request_id: Mapped[str] = mapped_column(String(26), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    approver_actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = [
    "Workspace",
    "CatalogSource",
    "CatalogDataset",
    "RunRecord",
    "ReviewProposal",
    "ReviewTask",
    "ReviewApproval",
    "GovernancePolicy",
    "GovernanceRetentionPolicy",
    "GovernancePurgeRun",
    "GovernanceDeletionRequest",
    "GovernanceDeletionApproval",
    "AuditEvent",
    "AccessDecision",
]
