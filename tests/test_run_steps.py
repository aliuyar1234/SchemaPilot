from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from backend.workers.service import process_queued_runs_once


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'run_steps.db').as_posix()}",
    )


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def test_run_endpoint_includes_step_breakdown_after_success(tmp_path: Path) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "orders.csv").write_text("id,amount\n1,10\n", encoding="utf-8")

    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))

    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "Steps WS", "profile": "team", "security_baseline": "strict"},
        headers=_admin_headers(),
    ).json()
    workspace_id = str(workspace["workspace_id"])
    client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "filesystem",
            "scope": {"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            "display_name": "Exports",
        },
        headers=_admin_headers(),
    )
    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/runs",
        json={"run_type": "discover"},
        headers=_admin_headers(),
    ).json()
    run_id = str(run["run_id"])

    processed = process_queued_runs_once(
        session_factory=get_session_factory(settings.database_url),
        storage_root=settings.storage_root,
        max_runs=1,
        strict_ingest=True,
    )
    assert processed == 1

    run_state = client.get(f"/api/v1/workspaces/{workspace_id}/runs/{run_id}").json()
    assert run_state["status"] == "succeeded"
    run_steps = run_state["run_steps"]
    assert isinstance(run_steps, list)
    assert [step["step_key"] for step in run_steps] == [
        "discover_inventory",
        "ingest_profile_governance",
        "semantic_drift_gate",
        "finalize_output",
    ]
    assert all(step["status"] == "succeeded" for step in run_steps)

    listed_steps = client.get(
        f"/api/v1/workspaces/{workspace_id}/runs/{run_id}/steps"
    ).json()
    assert listed_steps == run_steps


def test_run_step_failure_records_evidence_for_strict_completeness(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing_source"
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))

    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "Steps Fail WS", "profile": "team", "security_baseline": "strict"},
        headers=_admin_headers(),
    ).json()
    workspace_id = str(workspace["workspace_id"])
    client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "filesystem",
            "scope": {"root_path": missing_root.as_posix(), "include_globs": ["**/*.csv"]},
            "display_name": "Missing",
        },
        headers=_admin_headers(),
    )
    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/runs",
        json={"run_type": "discover"},
        headers=_admin_headers(),
    ).json()
    run_id = str(run["run_id"])

    processed = process_queued_runs_once(
        session_factory=get_session_factory(settings.database_url),
        storage_root=settings.storage_root,
        max_runs=1,
        strict_ingest=True,
    )
    assert processed == 1

    run_state = client.get(f"/api/v1/workspaces/{workspace_id}/runs/{run_id}").json()
    assert run_state["status"] == "failed"
    failed_step = next(
        step
        for step in run_state["run_steps"]
        if step["step_key"] == "ingest_profile_governance"
    )
    assert failed_step["status"] == "failed"
    assert failed_step["error_code"] == "strict_ingest_completeness_failed"
    assert str(failed_step["evidence_bundle_uri"]).startswith("evidence://")
