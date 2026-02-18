from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.control_plane.repository import create_workspace
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.shared_domain.scheduling import (
    create_run_schedule,
    enqueue_due_scheduled_runs,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'scheduling.db').as_posix()}",
    )


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def test_run_schedule_endpoint_and_validation(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "Sched Workspace", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    )
    workspace_id = workspace.json()["workspace_id"]

    invalid = client.post(
        f"/api/v1/workspaces/{workspace_id}/run-schedules",
        json={"run_type": "discover", "schedule_expression": "bad-cron"},
        headers={"Authorization": "Bearer local-data-steward-token"},
    )
    assert invalid.status_code == 403
    assert invalid.json()["error"]["details"]["reason"] == "invalid_schedule_expression"

    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/run-schedules",
        json={"run_type": "discover", "schedule_expression": "*/5 * * * *", "enabled": True},
        headers={"Authorization": "Bearer local-data-steward-token"},
    )
    assert created.status_code == 200
    listed = client.get(
        f"/api/v1/workspaces/{workspace_id}/run-schedules",
        headers={"Authorization": "Bearer local-analyst-token"},
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_enqueue_due_schedules_creates_runs(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Sched Worker Workspace",
            profile="starter",
            security_baseline="standard",
        )
        schedule = create_run_schedule(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
            schedule_expression="*/1 * * * *",
            enabled=True,
            actor_id="user:local_steward",
        )
        created = enqueue_due_scheduled_runs(
            session,
            now_epoch=int(schedule["next_run_epoch"]) + 1,  # type: ignore[arg-type]
        )
        session.commit()
    assert len(created) == 1
    assert created[0]["run_type"] == "discover"
