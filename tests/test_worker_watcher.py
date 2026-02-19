from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from backend.control_plane.repository import create_source, create_workspace
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base, RunRecord
from backend.workers.watcher import enqueue_source_watcher_runs


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'watcher.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_watcher_enqueues_discover_run_when_source_snapshot_changes(tmp_path: Path) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "orders.csv").write_text("id,amount\n1,10\n", encoding="utf-8")
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Watcher Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        create_source(
            session,
            workspace_id=workspace_id,
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Exports",
        )
        session.commit()

    with session_factory() as session:
        result = enqueue_source_watcher_runs(
            session,
            storage_root=storage_root,
            strict_ingest=True,
        )
        session.commit()
        assert int(result["evaluated_sources"]) == 1
        assert int(result["enqueued_run_count"]) == 1
        queued = (
            session.execute(select(RunRecord).where(RunRecord.workspace_id == workspace_id))
            .scalars()
            .all()
        )
        assert len(queued) == 1
        assert queued[0].run_type == "discover"
        assert queued[0].status == "queued"
        assert str(queued[0].input_refs_json.get("trigger")) == "watcher"


def test_watcher_avoids_duplicate_discover_runs_when_one_is_pending(tmp_path: Path) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "orders.csv").write_text("id,amount\n1,10\n", encoding="utf-8")
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Watcher Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        create_source(
            session,
            workspace_id=workspace_id,
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Exports",
        )
        session.commit()

    with session_factory() as session:
        first = enqueue_source_watcher_runs(
            session,
            storage_root=storage_root,
            strict_ingest=True,
        )
        second = enqueue_source_watcher_runs(
            session,
            storage_root=storage_root,
            strict_ingest=True,
        )
        session.commit()
        assert int(first["enqueued_run_count"]) == 1
        assert int(second["enqueued_run_count"]) == 0
        queued = (
            session.execute(select(RunRecord).where(RunRecord.workspace_id == workspace_id))
            .scalars()
            .all()
        )
        assert len(queued) == 1
