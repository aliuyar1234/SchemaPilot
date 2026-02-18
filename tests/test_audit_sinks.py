from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings


def _control_plane_settings(tmp_path: Path, sink_type: str, sink_target: str | None) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'audit_sinks_cp.db').as_posix()}",
        audit_sink_type=sink_type,
        audit_sink_target=sink_target,
    )


def _gateway_settings(tmp_path: Path, sink_type: str, sink_target: str | None) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'audit_sinks_gw.db').as_posix()}",
        audit_sink_type=sink_type,
        audit_sink_target=sink_target,
    )


def test_jsonl_audit_sink_writes_events_from_control_plane(tmp_path: Path) -> None:
    sink_path = tmp_path / "audit" / "events.jsonl"
    settings = _control_plane_settings(tmp_path, sink_type="jsonl", sink_target=sink_path.as_posix())
    client = TestClient(create_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": "Bearer local-platform-admin-token"},
        json={"name": "Audit Sink Workspace", "profile": "starter", "security_baseline": "standard"},
    )
    assert response.status_code == 200
    assert sink_path.exists()
    lines = sink_path.read_text(encoding="utf-8").splitlines()
    assert lines
    first = json.loads(lines[0])
    assert first["event_type"] == "workspace.created"


def test_webhook_audit_sink_failure_denies_gateway_request(tmp_path: Path) -> None:
    settings = _gateway_settings(
        tmp_path,
        sink_type="webhook",
        sink_target="http://127.0.0.1:1/unreachable",
    )
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query",
        headers={"Authorization": "Bearer local-analyst-token"},
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "audit_sink_unavailable"
