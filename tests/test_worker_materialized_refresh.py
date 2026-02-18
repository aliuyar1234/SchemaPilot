from __future__ import annotations

from pathlib import Path

from backend.control_plane.repository import create_run, create_workspace, get_run
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.workers.run_processor import process_run_by_id


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'materialized_refresh.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_materialized_refresh_run_fails_closed_when_disabled(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Refresh Disabled",
            profile="team",
            security_baseline="strict",
        )
        run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="materialize_refresh",
        )
        session.commit()
    with session_factory() as session:
        result = process_run_by_id(session, run_id=str(run["run_id"]), storage_root=storage_root)
        session.commit()
    assert result is not None
    assert result.status == "failed"


def test_materialized_refresh_run_succeeds_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCHEMAPILOT_MATERIALIZED_REFRESH_ENABLED", "true")
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Refresh Enabled",
            profile="team",
            security_baseline="strict",
        )
        run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="materialize_refresh",
        )
        session.commit()
    with session_factory() as session:
        result = process_run_by_id(session, run_id=str(run["run_id"]), storage_root=storage_root)
        session.commit()
    assert result is not None
    assert result.status == "succeeded"
    snapshot_path = Path(str(result.output_refs["materialized_snapshot_path"]))
    assert snapshot_path.exists()


def test_worker_step_item_quota_fails_closed(tmp_path: Path, monkeypatch) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    for idx in range(3):
        (exports_root / f"data_{idx}.csv").write_text("id,value\n1,a\n", encoding="utf-8")
    monkeypatch.setenv("SCHEMAPILOT_WORKER_STEP_MAX_ITEMS", "1")
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Quota Workspace",
            profile="team",
            security_baseline="strict",
        )
        source = {
            "source_type": "filesystem",
            "scope": {"root_path": exports_root.as_posix()},
            "display_name": "Exports",
        }
        from backend.control_plane.repository import create_source

        create_source(session, workspace_id=str(workspace["workspace_id"]), **source)
        run = create_run(session, workspace_id=str(workspace["workspace_id"]), run_type="discover")
        session.commit()
    with session_factory() as session:
        result = process_run_by_id(session, run_id=str(run["run_id"]), storage_root=storage_root)
        session.commit()
    assert result is not None
    assert result.status == "failed"
    with session_factory() as session:
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(run["run_id"]),
        )
    assert run_state is not None
    assert run_state["output_refs"]["error"] == "worker_step_item_quota_exceeded"
