from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'catalog_snapshot.db').as_posix()}",
        secrets_store_backend="local_encrypted",
        secrets_store_root=(tmp_path / "secrets").as_posix(),
        secrets_master_key="snapshot-key",
    )


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def test_catalog_export_redacts_credentials_and_imports_into_workspace(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))

    workspace_one = client.post(
        "/api/v1/workspaces",
        json={"name": "Workspace One", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    )
    workspace_one_id = workspace_one.json()["workspace_id"]
    create_source = client.post(
        f"/api/v1/workspaces/{workspace_one_id}/sources",
        json={
            "source_type": "filesystem",
            "scope": {"root_path": "/tmp/a"},
            "display_name": "Exports One",
            "credentials": {"token": "very-secret"},
        },
        headers=_admin_headers(),
    )
    assert create_source.status_code == 200

    export_response = client.get(
        f"/api/v1/workspaces/{workspace_one_id}/catalog/export",
        headers=_admin_headers(),
    )
    assert export_response.status_code == 200
    snapshot = export_response.json()
    assert snapshot["sources"][0]["credentials_redacted"] is True
    assert "very-secret" not in str(snapshot)

    workspace_two = client.post(
        "/api/v1/workspaces",
        json={"name": "Workspace Two", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    )
    workspace_two_id = workspace_two.json()["workspace_id"]
    snapshot["workspace"]["workspace_id"] = workspace_two_id
    import_response = client.post(
        f"/api/v1/workspaces/{workspace_two_id}/catalog/import",
        json={"snapshot": snapshot},
        headers=_admin_headers(),
    )
    assert import_response.status_code == 200
    body = import_response.json()
    assert body["imported_sources"] == 1
