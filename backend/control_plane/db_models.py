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
    Workspace,
)

__all__ = [
    "Workspace",
    "CatalogSource",
    "CatalogDataset",
    "RunRecord",
    "RunStepRecord",
    "ReviewProposal",
    "ReviewTask",
    "ReviewApproval",
    "GovernancePolicy",
    "AuditEvent",
    "AccessDecision",
    "AuditOutboxEvent",
    "Base",
]
