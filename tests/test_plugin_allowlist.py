from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import backend.control_plane.app as control_plane_app
from backend.control_plane.app import create_app
from backend.control_plane.repository import create_run, create_source, create_workspace, get_run
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.evidence_store import load_evidence_bundle, parse_evidence_uri
from backend.shared_domain.metadata_models import Base
from backend.shared_domain.plugin_loader import ConnectorPluginSpec
from backend.workers import run_processor


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'plugin_allowlist.db').as_posix()}",
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'plugin_worker.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_source_connect_denied_when_plugin_not_allowlisted(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "Plugin Guard", "profile": "team", "security_baseline": "strict"},
        headers=_headers("local-platform-admin-token"),
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["workspace_id"]

    monkeypatch.setattr(control_plane_app, "load_connector_plugin_specs", lambda **kwargs: {})
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "custom_plugin_source",
            "scope": {"root_path": tmp_path.as_posix()},
            "display_name": "Blocked Plugin Source",
        },
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "plugin_not_allowlisted_or_unavailable"


def test_plugin_error_fails_closed_with_strict_ingest_evidence(tmp_path: Path, monkeypatch) -> None:
    exports_root = tmp_path / "plugin_exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    plugin_file = exports_root / "source.csv"
    plugin_file.write_text("id,value\n1,plugin\n", encoding="utf-8")

    def broken_plugin(scope: dict[str, object]) -> list[dict[str, object]]:
        _ = scope
        raise ValueError("plugin_boom")

    monkeypatch.setattr(
        run_processor,
        "load_connector_plugin_specs",
        lambda **kwargs: {
            "custom": ConnectorPluginSpec(
                name="custom",
                plugin=broken_plugin,
                entrypoint=None,
            )
        },
    )

    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Plugin Strict Workspace",
            profile="team",
            security_baseline="strict",
        )
        create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="custom",
            scope={"root_path": exports_root.as_posix()},
            display_name="Broken Plugin",
        )
        run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        session.commit()

    with session_factory() as session:
        result = run_processor.process_run_by_id(
            session,
            run_id=str(run["run_id"]),
            storage_root=storage_root,
            strict_ingest=True,
        )
        assert result is not None
        assert result.status == "failed"
        session.commit()

    with session_factory() as session:
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(run["run_id"]),
        )
        assert run_state is not None
        output_refs = run_state["output_refs"]
        assert output_refs["reason"] == "strict_ingest_completeness_failed"
        workspace_id, evidence_id = parse_evidence_uri(str(output_refs["evidence_bundle_uri"]))
        bundle = load_evidence_bundle(
            workspace_id=workspace_id,
            evidence_id=evidence_id,
            storage_root=storage_root,
        )
        failures = bundle["payload"]["failures"]
        assert len(failures) == 1
        assert failures[0]["stage"] == "discovery"
        assert "plugin_boom" in str(failures[0]["error"])
