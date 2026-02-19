"""Compatibility re-export for shared metadata SQLAlchemy models."""

from __future__ import annotations

from backend.shared_domain.db import Base
from backend.shared_domain.metadata_models import (
    AccessDecision,
    AuditEvent,
    AuditOutboxEvent,
    CatalogDataset,
    CatalogSource,
    GovernancePolicy,
    ReviewApproval,
    ReviewProposal,
    ReviewTask,
    RunRecord,
    RunStepRecord,
    TargetDbPlan,
    TargetDbProfile,
    TargetDbState,
    TargetDbSyncCursor,
    Workspace,
)

__all__ = [
    "Workspace",
    "CatalogSource",
    "CatalogDataset",
    "RunRecord",
    "RunStepRecord",
    "TargetDbProfile",
    "TargetDbState",
    "TargetDbPlan",
    "TargetDbSyncCursor",
    "ReviewProposal",
    "ReviewTask",
    "ReviewApproval",
    "GovernancePolicy",
    "AuditEvent",
    "AccessDecision",
    "AuditOutboxEvent",
    "Base",
]
