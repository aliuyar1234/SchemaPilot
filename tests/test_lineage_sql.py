from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.lineage_sql import derive_column_lineage
from backend.shared_domain.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'lineage.db').as_posix()}",
    )


def test_derive_column_lineage_from_simple_select() -> None:
    lineage = derive_column_lineage("select amount as total_amount, region from invoices")
    assert len(lineage) == 2
    assert lineage[0]["output_column"] == "total_amount"
    assert "amount" in lineage[0]["source_columns"]


def test_lineage_api_returns_lineage_payload(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "Lineage Workspace", "profile": "starter", "security_baseline": "standard"},
        headers={"Authorization": "Bearer local-platform-admin-token"},
    )
    workspace_id = workspace_response.json()["workspace_id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/lineage/sql",
        headers={"Authorization": "Bearer local-analyst-token"},
        json={"sql_text": "select amount as total_amount from invoices"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lineage_available"] is True
    assert body["lineage"][0]["output_column"] == "total_amount"
