"""Target database adapter interfaces."""

from backend.shared_domain.target_db.adapters.base import (
    MigrationPlanResult,
    SyncResult,
    TargetDbAdapter,
    TargetDbProfileConfig,
    ValidationResult,
)

__all__ = [
    "MigrationPlanResult",
    "SyncResult",
    "TargetDbAdapter",
    "TargetDbProfileConfig",
    "ValidationResult",
]
