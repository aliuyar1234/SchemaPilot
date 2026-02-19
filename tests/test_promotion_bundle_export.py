from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'promotion_bundle.db').as_posix()}",
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace(client: TestClient) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "Promotion Bundle", "profile": "team", "security_baseline": "strict"},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def test_promotion_export_bundle_is_deterministic_and_contains_required_sections(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    first = client.post(
        f"/api/v1/workspaces/{workspace_id}/promotion/export",
        headers=_headers("local-platform-admin-token"),
    )
    second = client.post(
        f"/api/v1/workspaces/{workspace_id}/promotion/export",
        headers=_headers("local-platform-admin-token"),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["bundle_checksum"] == second_payload["bundle_checksum"]
    bundle = first_payload["bundle"]
    assert bundle["bundle_schema_version"] == "v1"
    assert "catalog_snapshot" in bundle
    assert "pack_registry" in bundle
    assert "migration_checksums" in bundle
    assert "config_redacted" in bundle
    assert "evidence_refs" in bundle
