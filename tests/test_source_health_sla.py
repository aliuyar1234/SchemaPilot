from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import CatalogDataset


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'source_sla.db').as_posix()}",
    )


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def _steward_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-data-steward-token"}


def test_source_sla_evaluation_creates_violation_tasks(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "SLA Workspace", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    )
    workspace_id = workspace_response.json()["workspace_id"]
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        session.add(
            CatalogDataset(
                dataset_id="dataset-sla",
                workspace_id=workspace_id,
                source_id="source-1",
                logical_name="dataset-sla",
                physical_locator="dataset://sla",
                schema_version=1,
                sensitivity_summary_json={
                    "profile": {"schema_columns": ["id"], "last_profile_epoch": 0}
                },
            )
        )
        session.commit()

    configure = client.post(
        f"/api/v1/workspaces/{workspace_id}/source-slas",
        json={"dataset_id": "dataset-sla", "freshness_seconds": 60, "enabled": True},
        headers=_steward_headers(),
    )
    assert configure.status_code == 200
    evaluate = client.post(
        f"/api/v1/workspaces/{workspace_id}/source-slas/evaluate",
        headers=_steward_headers(),
    )
    assert evaluate.status_code == 200
    body = evaluate.json()
    assert body["violation_count"] == 1
    assert len(body["created_task_ids"]) == 1
