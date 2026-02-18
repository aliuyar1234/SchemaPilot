from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.errors import StartupConfigurationError
from backend.shared_domain.secrets_store import (
    LocalEncryptedSecretsStore,
    load_secrets_store,
)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    data = {
        "profile": "starter",
        "bind_address": "127.0.0.1",
        "auth_mode": "local",
        "require_auth_for_non_local": True,
        "storage_root": (tmp_path / "storage").as_posix(),
        "database_url": f"sqlite:///{(tmp_path / 'secrets_store.db').as_posix()}",
        "secrets_store_backend": "local_encrypted",
        "secrets_store_root": (tmp_path / "secrets").as_posix(),
        "secrets_master_key": "test-master-key",
    }
    data.update(overrides)
    return Settings(**data)


def test_local_encrypted_secrets_store_roundtrip(tmp_path: Path) -> None:
    store = LocalEncryptedSecretsStore(root=tmp_path / "secrets", master_key="master")
    reference = store.put_secret(
        scope="workspace/w1/source/filesystem", key="bundle", value="secret"
    )
    assert reference.startswith("secret://local/")
    value = store.get_secret(reference)
    assert value == "secret"


def test_vault_secrets_backend_requires_url_and_token(tmp_path: Path) -> None:
    settings = _settings(tmp_path, secrets_store_backend="vault", vault_url=None, vault_token=None)
    try:
        load_secrets_store(settings)
    except StartupConfigurationError as exc:
        assert exc.details["secrets_store_backend"] == "vault"
    else:  # pragma: no cover
        raise AssertionError("expected StartupConfigurationError")


def test_control_plane_source_create_stores_credentials_ref(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    headers = {"Authorization": "Bearer local-platform-admin-token"}
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "Secrets Workspace", "profile": "starter", "security_baseline": "standard"},
        headers=headers,
    )
    workspace_id = workspace.json()["workspace_id"]

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "filesystem",
            "scope": {"root_path": "/tmp/data"},
            "display_name": "Source With Secrets",
            "credentials": {"username": "user", "password": "super-secret"},
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    credentials_ref = str(body["credentials_ref"])
    assert credentials_ref.startswith("secret://local/")

    secret_files = list((tmp_path / "secrets").glob("*.json"))
    assert secret_files
    stored_payload = json.loads(secret_files[0].read_text(encoding="utf-8"))
    serialized = json.dumps(stored_payload, sort_keys=True)
    assert "super-secret" not in serialized
