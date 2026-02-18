from __future__ import annotations

from pathlib import Path

from backend.control_plane.repository import create_run, create_source, create_workspace
from backend.shared_domain.connector_state import load_connector_state
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.shared_domain.plugin_loader import ConnectorPluginSpec
from backend.workers import run_processor


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'incremental_state.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_run_processor_persists_and_reuses_connector_cursor_state(
    tmp_path: Path, monkeypatch
) -> None:
    exports = tmp_path / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    first_file = exports / "custom_1.csv"
    first_file.write_text("id,value\n1,first\n", encoding="utf-8")
    observed_cursors: list[str] = []

    def plugin(scope: dict[str, object]) -> list[dict[str, object]]:
        cursor_state = scope.get("cursor_state", {})
        if isinstance(cursor_state, dict):
            observed_cursors.append(str(cursor_state.get("cursor", "")))
        files = sorted(exports.glob("*.csv"))
        rows: list[dict[str, object]] = []
        for path in files:
            stat = path.stat()
            rows.append(
                {
                    "path": path.as_posix(),
                    "dataset_family": "custom",
                    "size_bytes": int(stat.st_size),
                    "mtime_epoch": float(stat.st_mtime),
                    "content_hash_sample": "",
                }
            )
        return rows

    monkeypatch.setattr(
        run_processor,
        "load_connector_plugin_specs",
        lambda: {"custom": ConnectorPluginSpec(name="custom", plugin=plugin, entrypoint=None)},
    )
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()

    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Incremental State Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        source = create_source(
            session,
            workspace_id=workspace_id,
            source_type="custom",
            scope={"root_path": exports.as_posix()},
            display_name="Custom",
        )
        run = create_run(session, workspace_id=workspace_id, run_type="discover")
        session.commit()

    with session_factory() as session:
        first_result = run_processor.process_run_by_id(
            session,
            run_id=str(run["run_id"]),
            storage_root=storage_root,
            strict_ingest=True,
        )
        session.commit()
    assert first_result is not None
    assert first_result.status == "succeeded"

    second_file = exports / "custom_2.csv"
    second_file.write_text("id,value\n2,second\n", encoding="utf-8")
    with session_factory() as session:
        second_run = create_run(session, workspace_id=workspace_id, run_type="discover")
        session.commit()

    with session_factory() as session:
        second_result = run_processor.process_run_by_id(
            session,
            run_id=str(second_run["run_id"]),
            storage_root=storage_root,
            strict_ingest=True,
        )
        session.commit()
    assert second_result is not None
    assert second_result.status == "succeeded"
    assert observed_cursors[0] == ""
    assert observed_cursors[1] != ""
    state = load_connector_state(
        storage_root=storage_root,
        workspace_id=workspace_id,
        source_id=str(source["source_id"]),
    )
    assert isinstance(state, dict)
    assert str(state.get("cursor", "")).strip() != ""
