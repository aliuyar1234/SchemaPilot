from __future__ import annotations

from backend.control_plane.repository import create_run, create_source, create_workspace, get_run
from backend.control_plane.review_repository import list_review_tasks
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.workers.run_processor import process_run_by_id


def test_discover_pipeline_creates_blocking_pii_review_tasks(tmp_path) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "customers.csv").write_text(
        "id,name,email\n1,Alice,alice@example.com\n2,Bob,bob@example.com\n",
        encoding="utf-8",
    )

    database_url = f"sqlite:///{(tmp_path / 'pii_pipeline.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    storage_root = (tmp_path / "storage").as_posix()

    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="PII Pipeline",
            profile="starter",
            security_baseline="standard",
        )
        create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="PII Exports",
        )
        first_run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        session.commit()

    with session_factory() as session:
        first_result = process_run_by_id(
            session,
            run_id=str(first_run["run_id"]),
            storage_root=storage_root,
        )
        assert first_result is not None
        assert first_result.status == "succeeded"
        session.commit()

    with session_factory() as session:
        tasks = list_review_tasks(session, str(workspace["workspace_id"]))
        assert any(
            task["priority"] == "security_critical"
            and task["blocking"] is True
            and task["proposal_type"] == "pii_tag_proposal"
            for task in tasks
        )
        first_task_count = len(tasks)
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(first_run["run_id"]),
        )
        assert run_state is not None
        output_refs = run_state["output_refs"]
        assert isinstance(output_refs, dict)
        assert int(output_refs.get("pii_blocking_tasks_created", 0)) >= 1

    with session_factory() as session:
        second_run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        session.commit()

    with session_factory() as session:
        second_result = process_run_by_id(
            session,
            run_id=str(second_run["run_id"]),
            storage_root=storage_root,
        )
        assert second_result is not None
        assert second_result.status == "succeeded"
        session.commit()

    with session_factory() as session:
        tasks_after_second = list_review_tasks(session, str(workspace["workspace_id"]))
        assert len(tasks_after_second) == first_task_count
