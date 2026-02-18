from __future__ import annotations

from pathlib import Path

from backend.control_plane.repository import create_run, create_source, create_workspace, get_run
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.workers import run_processor
from backend.workers.service import process_queued_runs_once


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'runner.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_worker_runner_processes_queued_run_with_status_transition(tmp_path: Path) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "orders.csv").write_text("id,amount\n1,10\n", encoding="utf-8")

    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Runner Workspace",
            profile="starter",
            security_baseline="standard",
        )
        create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Exports",
        )
        run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=(tmp_path / "storage").as_posix(),
        max_runs=1,
    )
    assert processed == 1

    with session_factory() as session:
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(run["run_id"]),
        )
        assert run_state is not None
        assert run_state["status"] == "succeeded"
        output_refs = run_state["output_refs"]
        assert isinstance(output_refs, dict)
        assert output_refs["dataset_count"] == 1

    processed_again = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=(tmp_path / "storage").as_posix(),
        max_runs=1,
    )
    assert processed_again == 0


def test_worker_runner_marks_unsupported_run_type_failed(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Runner Fail Workspace",
            profile="starter",
            security_baseline="standard",
        )
        run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="unsupported-run",
        )
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=(tmp_path / "storage").as_posix(),
        max_runs=1,
    )
    assert processed == 1

    with session_factory() as session:
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(run["run_id"]),
        )
        assert run_state is not None
        assert run_state["status"] == "failed"
        output_refs = run_state["output_refs"]
        assert isinstance(output_refs, dict)
        assert "Unsupported run_type" in str(output_refs.get("error", ""))


def test_worker_runner_uses_connector_plugin_for_non_filesystem_source(
    tmp_path: Path, monkeypatch
) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    custom_file = exports_root / "plugin.csv"
    custom_file.write_text("id,amount\n1,20\n", encoding="utf-8")

    def plugin(scope: dict[str, object]) -> list[dict[str, object]]:
        _ = scope
        return [
            {
                "path": custom_file.as_posix(),
                "size_bytes": custom_file.stat().st_size,
                "mtime_epoch": custom_file.stat().st_mtime,
                "content_hash_sample": "sample",
                "dataset_family": "plugin",
            }
        ]

    monkeypatch.setattr(run_processor, "load_connector_plugins", lambda: {"custom": plugin})

    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Runner Plugin Workspace",
            profile="starter",
            security_baseline="standard",
        )
        create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="custom",
            scope={"root_path": exports_root.as_posix()},
            display_name="Plugin Source",
        )
        run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=(tmp_path / "storage").as_posix(),
        max_runs=1,
    )
    assert processed == 1

    with session_factory() as session:
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(run["run_id"]),
        )
        assert run_state is not None
        assert run_state["status"] == "succeeded"
