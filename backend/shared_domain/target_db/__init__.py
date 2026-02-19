"""Target database adapter contracts and registry helpers."""

from backend.shared_domain.target_db.adapters.base import (
    MigrationPlanResult,
    SyncResult,
    TargetDbAdapter,
    TargetDbProfileConfig,
    ValidationResult,
)
from backend.shared_domain.target_db.ddl_generator import (
    generate_target_db_ddl,
    migration_drop_statements,
)
from backend.shared_domain.target_db.hash import target_db_profile_hash
from backend.shared_domain.target_db.registry import (
    get_target_db_adapter,
    list_target_db_adapters,
    register_target_db_adapter,
)
from backend.shared_domain.target_db.type_mapping import map_canonical_type

__all__ = [
    "MigrationPlanResult",
    "SyncResult",
    "TargetDbAdapter",
    "TargetDbProfileConfig",
    "ValidationResult",
    "generate_target_db_ddl",
    "migration_drop_statements",
    "map_canonical_type",
    "target_db_profile_hash",
    "get_target_db_adapter",
    "list_target_db_adapters",
    "register_target_db_adapter",
]
