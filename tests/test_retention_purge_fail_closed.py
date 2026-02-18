from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.evidence_store import parse_evidence_uri


def _settings(tmp_path: Path, *, purge_root: str | None) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'retention.db').as_posix()}",
        retention_purge_root=purge_root,
    )


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def _create_workspace(client: TestClient, *, name: str) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": name, "profile": "team", "security_baseline": "strict"},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def test_retention_purge_denied_by_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path, purge_root=(tmp_path / "storage").as_posix())
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client, name="Retention Disabled")

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/retention/purge",
        json={"dry_run": True},
        headers=_admin_headers(),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "retention_disabled"


def test_retention_purge_requires_explicit_purge_path_config(tmp_path: Path) -> None:
    settings = _settings(tmp_path, purge_root=None)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client, name="Retention Missing Purge Root")

    policy_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/retention/policy",
        json={
            "retention_days": 7,
            "enabled": True,
            "purge_enabled": True,
            "legal_hold_active": False,
        },
        headers=_admin_headers(),
    )
    assert policy_response.status_code == 200

    purge_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/retention/purge",
        json={"dry_run": False},
        headers=_admin_headers(),
    )
    assert purge_response.status_code == 403
    body = purge_response.json()
    assert body["error"]["details"]["reason"] == "missing_purge_path_config"


def test_retention_purge_succeeds_with_evidence_and_file_cleanup(tmp_path: Path) -> None:
    purge_root = tmp_path / "storage"
    purge_root.mkdir(parents=True, exist_ok=True)
    settings = _settings(tmp_path, purge_root=purge_root.as_posix())
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client, name="Retention Active")

    old_file = purge_root / "bronze" / workspace_id / "s1" / "d1" / "legacy.txt"
    old_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.write_text("legacy", encoding="utf-8")
    old_epoch = time.time() - (3 * 86400)
    os.utime(old_file.as_posix(), (old_epoch, old_epoch))

    policy_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/retention/policy",
        json={
            "retention_days": 1,
            "enabled": True,
            "purge_enabled": True,
            "legal_hold_active": False,
        },
        headers=_admin_headers(),
    )
    assert policy_response.status_code == 200

    purge_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/retention/purge",
        json={"dry_run": False},
        headers=_admin_headers(),
    )
    assert purge_response.status_code == 200
    body = purge_response.json()
    assert body["status"] == "succeeded"
    assert int(body["deleted_count"]) >= 1
    assert old_file.exists() is False
    evidence_uri = str(body["evidence_bundle_uri"])
    _, evidence_id = parse_evidence_uri(evidence_uri)
    evidence_response = client.get(
        f"/api/v1/workspaces/{workspace_id}/evidence/{evidence_id}",
        headers=_admin_headers(),
    )
    assert evidence_response.status_code == 200
