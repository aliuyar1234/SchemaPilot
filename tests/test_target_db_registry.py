from __future__ import annotations

from backend.shared_domain.target_db.adapters.base import TargetDbProfileConfig
from backend.shared_domain.target_db.registry import (
    get_target_db_adapter,
    list_target_db_adapters,
    register_target_db_adapter,
)


def _profile() -> TargetDbProfileConfig:
    return TargetDbProfileConfig(
        workspace_id="ws_1",
        target_db_id="tdb_1",
        db_type="postgres",
        mode="managed",
        connection={},
        credential_refs={},
    )


def test_registry_contains_default_adapters() -> None:
    adapters = list_target_db_adapters()
    assert adapters == ["mysql", "postgres", "sqlite"]
    postgres = get_target_db_adapter("postgres")
    validation = postgres.validate(_profile())
    assert validation.ok is True


def test_registry_supports_custom_registration() -> None:
    class _CustomAdapter:
        db_type = "custom"

        def validate(self, profile: TargetDbProfileConfig):  # noqa: ANN001
            _ = profile
            return type("ValidationResultProxy", (), {"ok": True, "details": {"custom": True}})()

        def generate_ddl(self, profile: TargetDbProfileConfig):  # noqa: ANN001
            _ = profile
            return []

        def plan_migrations(self, profile: TargetDbProfileConfig):  # noqa: ANN001
            _ = profile
            return type(
                "MigrationPlanProxy",
                (),
                {
                    "plan_checksum": "sha256:custom",
                    "destructive": False,
                    "statements": [],
                    "details": {},
                },
            )()

        def apply_migrations(self, profile: TargetDbProfileConfig, *, plan_checksum: str):  # noqa: ANN001
            _ = (profile, plan_checksum)
            return {"status": "ok"}

        def load_initial(self, profile: TargetDbProfileConfig):  # noqa: ANN001
            _ = profile
            return {"status": "ok"}

        def sync_incremental(self, profile: TargetDbProfileConfig):  # noqa: ANN001
            _ = profile
            return type("SyncResultProxy", (), {"ok": True, "datasets": [], "details": {}})()

    register_target_db_adapter("custom", _CustomAdapter())
    adapter = get_target_db_adapter("custom")
    assert adapter.db_type == "custom"
