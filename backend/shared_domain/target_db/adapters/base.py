"""Contract-first adapter protocol for target database backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TargetDbProfileConfig:
    """Minimal runtime profile passed to adapters."""

    workspace_id: str
    target_db_id: str
    db_type: str
    mode: str
    connection: dict[str, object]
    credential_refs: dict[str, object]


@dataclass(frozen=True)
class ValidationResult:
    """Validation outcome for connectivity/least-privilege checks."""

    ok: bool
    details: dict[str, object]


@dataclass(frozen=True)
class MigrationPlanResult:
    """Deterministic migration planning payload."""

    plan_checksum: str
    destructive: bool
    statements: list[str]
    details: dict[str, object]


@dataclass(frozen=True)
class SyncResult:
    """Sync execution report shape."""

    ok: bool
    datasets: list[dict[str, object]]
    details: dict[str, object]


class TargetDbAdapter(Protocol):
    """Adapter protocol implemented by each target db engine."""

    db_type: str

    def validate(self, profile: TargetDbProfileConfig) -> ValidationResult:
        """Validate target DB connectivity and privilege posture."""

    def generate_ddl(self, profile: TargetDbProfileConfig) -> list[str]:
        """Generate deterministic DDL statements."""

    def plan_migrations(self, profile: TargetDbProfileConfig) -> MigrationPlanResult:
        """Produce deterministic migration plan and checksum."""

    def apply_migrations(
        self, profile: TargetDbProfileConfig, *, plan_checksum: str
    ) -> dict[str, object]:
        """Apply migration plan transactionally."""

    def load_initial(self, profile: TargetDbProfileConfig) -> dict[str, object]:
        """Load initial curated data into target DB."""

    def sync_incremental(self, profile: TargetDbProfileConfig) -> SyncResult:
        """Run incremental sync and return dataset-level status."""
