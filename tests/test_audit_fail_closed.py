from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm.session import Session as SqlAlchemySession

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings


def _gateway_settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url=f"sqlite:///{(tmp_path / 'gateway.db').as_posix()}",
    )


def _control_plane_settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url=f"sqlite:///{(tmp_path / 'control_plane.db').as_posix()}",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_denies_query_when_audit_write_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    original_commit = SqlAlchemySession.commit

    def failing_commit(self: SqlAlchemySession) -> None:
        raise RuntimeError("audit storage unavailable")

    monkeypatch.setattr(SqlAlchemySession, "commit", failing_commit)
    client = TestClient(create_gateway_app(settings_factory=lambda: _gateway_settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"text": "select 1 as one"}},
        headers=_auth_headers("local-analyst-token"),
    )
    monkeypatch.setattr(SqlAlchemySession, "commit", original_commit)
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "audit_unavailable"


def test_control_plane_denies_mutation_when_audit_write_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from backend.control_plane import app as control_plane_app

    def failing_append(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("audit storage unavailable")

    monkeypatch.setattr(control_plane_app, "_append_audit_event", failing_append)
    client = TestClient(create_app(settings_factory=lambda: _control_plane_settings(tmp_path)))

    create_response = client.post(
        "/api/v1/workspaces",
        json={"name": "audit-fail", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_headers("local-platform-admin-token"),
    )
    assert create_response.status_code == 403
    body = create_response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "audit_unavailable"

    list_response = client.get("/api/v1/workspaces")
    assert list_response.status_code == 200
    assert list_response.json() == []
