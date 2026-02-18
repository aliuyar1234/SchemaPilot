from __future__ import annotations

from pathlib import Path

from backend.control_plane.repository import create_run, create_source, create_workspace, get_run
from backend.control_plane.review_repository import list_review_tasks
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.shared_domain.plugin_loader import ConnectorPluginSpec
from backend.workers import run_processor
from backend.workers.service import load_worker_service_config, process_queued_runs_once


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

    monkeypatch.setattr(
        run_processor,
        "load_connector_plugin_specs",
        lambda: {
            "custom": ConnectorPluginSpec(
                name="custom",
                plugin=plugin,
                entrypoint=None,
            )
        },
    )

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


def test_worker_service_config_defaults_strict_ingest_for_team_profile(monkeypatch) -> None:
    monkeypatch.setenv("SCHEMAPILOT_PROFILE", "team")
    monkeypatch.delenv("SCHEMAPILOT_INGEST_STRICT", raising=False)
    config = load_worker_service_config()
    assert config.strict_ingest is True


def test_worker_service_config_allows_explicit_non_strict_override(monkeypatch) -> None:
    monkeypatch.setenv("SCHEMAPILOT_PROFILE", "enterprise")
    monkeypatch.setenv("SCHEMAPILOT_INGEST_STRICT", "false")
    config = load_worker_service_config()
    assert config.strict_ingest is False


def test_worker_runner_processes_semantic_bootstrap_run(tmp_path: Path) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "customers.csv").write_text(
        "customer_id,name,email\n1,Alice,alice@example.com\n",
        encoding="utf-8",
    )

    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Runner Semantic Workspace",
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
        discover_run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="discover",
        )
        semantic_run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="semantic_bootstrap",
        )
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=storage_root,
        max_runs=2,
    )
    assert processed == 2

    with session_factory() as session:
        discover_state = get_run(
            session,
            workspace_id=workspace_id,
            run_id=str(discover_run["run_id"]),
        )
        assert discover_state is not None
        assert discover_state["status"] == "succeeded"

        semantic_state = get_run(
            session,
            workspace_id=workspace_id,
            run_id=str(semantic_run["run_id"]),
        )
        assert semantic_state is not None
        assert semantic_state["status"] == "succeeded"
        output_refs = semantic_state["output_refs"]
        assert isinstance(output_refs, dict)
        assert output_refs["manifest_version"] == "1"
        assert int(output_refs["entity_count"]) >= 1
        assert int(output_refs["metric_count"]) >= 1
        assert str(output_refs["evidence_bundle_uri"]).startswith("evidence://")
        assert str(output_refs["manifest_checksum"])
        tasks = list_review_tasks(session, workspace_id)
        matching = [
            task
            for task in tasks
            if task["proposal_type"] == "semantic_manifest_change_proposal"
            and task["blocking"] is True
            and task["priority"] == "quality_critical"
        ]
        assert len(matching) == 1

    with session_factory() as session:
        repeat_run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="semantic_bootstrap",
        )
        session.commit()

    repeat_processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=storage_root,
        max_runs=1,
    )
    assert repeat_processed == 1

    with session_factory() as session:
        repeat_state = get_run(
            session,
            workspace_id=workspace_id,
            run_id=str(repeat_run["run_id"]),
        )
        assert repeat_state is not None
        assert repeat_state["status"] == "succeeded"
        tasks_after_repeat = list_review_tasks(session, workspace_id)
        matching_after_repeat = [
            task
            for task in tasks_after_repeat
            if task["proposal_type"] == "semantic_manifest_change_proposal"
            and task["blocking"] is True
            and task["priority"] == "quality_critical"
        ]
        assert len(matching_after_repeat) == 1


def test_worker_runner_fails_semantic_bootstrap_without_catalog(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Runner Semantic Empty Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="semantic_bootstrap",
        )
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=storage_root,
        max_runs=1,
    )
    assert processed == 1

    with session_factory() as session:
        run_state = get_run(
            session,
            workspace_id=workspace_id,
            run_id=str(run["run_id"]),
        )
        assert run_state is not None
        assert run_state["status"] == "failed"
        output_refs = run_state["output_refs"]
        assert isinstance(output_refs, dict)
        assert "semantic_bootstrap_requires_catalog_datasets" in str(output_refs.get("error", ""))
