from __future__ import annotations

from pathlib import Path

from backend.control_plane.repository import create_workspace
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base, RunRecord
from backend.shared_domain.ids import new_ulid
from backend.workers.run_processor import process_next_queued_run


def test_process_next_queued_run_respects_workspace_active_limit(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'worker_fairness.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace_a = create_workspace(
            session,
            name="Workspace A",
            profile="starter",
            security_baseline="standard",
        )
        workspace_b = create_workspace(
            session,
            name="Workspace B",
            profile="starter",
            security_baseline="standard",
        )
        session.add(
            RunRecord(
                run_id=new_ulid(),
                workspace_id=str(workspace_a["workspace_id"]),
                run_type="discover",
                status="running",
                input_refs_json={},
                output_refs_json={},
            )
        )
        session.add(
            RunRecord(
                run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
                workspace_id=str(workspace_a["workspace_id"]),
                run_type="discover",
                status="queued",
                input_refs_json={},
                output_refs_json={},
            )
        )
        run_b_id = "01ARZ3NDEKTSV4RRFFQ69G5FB0"
        session.add(
            RunRecord(
                run_id=run_b_id,
                workspace_id=str(workspace_b["workspace_id"]),
                run_type="discover",
                status="queued",
                input_refs_json={},
                output_refs_json={},
            )
        )
        session.commit()

    with session_factory() as session:
        processed = process_next_queued_run(
            session,
            storage_root=storage_root,
            max_active_per_workspace=1,
            strict_ingest=False,
        )
        session.commit()
    assert processed is not None
    assert processed.run_id == run_b_id
