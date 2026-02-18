"""Compatibility re-export for shared metadata SQLAlchemy models."""

from __future__ import annotations

from backend.shared_domain.db import Base
from backend.shared_domain.metadata_models import (
    AccessDecision,
    AuditEvent,
    CatalogDataset,
    CatalogSource,
    GovernancePolicy,
    ReviewApproval,
    ReviewProposal,
    ReviewTask,
    RunRecord,
    Workspace,
)

__all__ = [
    "Workspace",
    "CatalogSource",
    "CatalogDataset",
    "RunRecord",
    "ReviewProposal",
    "ReviewTask",
    "ReviewApproval",
    "GovernancePolicy",
    "AuditEvent",
    "AccessDecision",
    "Base",
]
