from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.control_plane.repository import create_run, create_source, create_workspace
from backend.control_plane.review_repository import list_review_tasks
from backend.shared_domain.config import Settings
from backend.shared_domain.contract_reports import write_build_contract_report
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.workers.run_processor import process_run_by_id


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def test_schema_drift_creates_blocking_task_and_blocks_publish(tmp_path) -> None:
    storage_root = (tmp_path / "storage").as_posix()
    database_url = f"sqlite:///{(tmp_path / 'drift_blocks_publish.db').as_posix()}"
    settings = Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=storage_root,
        database_url=database_url,
    )
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)

    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    csv_path = exports_root / "customers.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="drift",
            profile="starter",
            security_baseline="standard",
        )
        create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Drift Source",
        )
        first_run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        session.commit()

    with session_factory() as session:
        process_run_by_id(
            session,
            run_id=str(first_run["run_id"]),
            storage_root=storage_root,
        )
        session.commit()

    csv_path.write_text("id,name,email\n1,Alice,a@example.com\n", encoding="utf-8")

    with session_factory() as session:
        second_run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        session.commit()

    with session_factory() as session:
        process_run_by_id(
            session,
            run_id=str(second_run["run_id"]),
            storage_root=storage_root,
        )
        tasks = list_review_tasks(session, str(workspace["workspace_id"]))
        assert any(
            task["proposal_type"] == "drift_proposal"
            and task["priority"] == "quality_critical"
            and task["blocking"] is True
            for task in tasks
        )
        session.commit()

    workspace_id = str(workspace["workspace_id"])
    write_build_contract_report(
        workspace_id=workspace_id,
        build_id="build-drift",
        contracts_passed=True,
        failures=[],
        storage_root=storage_root,
    )
    client = TestClient(create_app(settings_factory=lambda: settings))
    publish = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-drift/publish",
        json={},
        headers=_admin_headers(),
    )
    assert publish.status_code == 200
    body = publish.json()
    assert body["status"] == "blocked"
    assert body["gate_reason"] == "blocking_review_tasks"
