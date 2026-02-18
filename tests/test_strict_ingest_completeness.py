from __future__ import annotations

from pathlib import Path

from backend.control_plane.repository import create_run, create_source, create_workspace, get_run
from backend.control_plane.review_repository import (
    list_review_tasks,
    unresolved_blocking_task_count,
)
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.evidence_store import load_evidence_bundle, parse_evidence_uri
from backend.shared_domain.metadata_models import Base
from backend.workers import run_processor


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'strict_ingest.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_strict_ingest_fails_closed_and_creates_blocking_task(tmp_path: Path, monkeypatch) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    good_file = exports_root / "good.csv"
    bad_file = exports_root / "bad.csv"
    good_file.write_text("id,value\n1,ok\n", encoding="utf-8")
    bad_file.write_text("id,value\n2,bad\n", encoding="utf-8")

    original_ingest = run_processor.ingest_file_to_bronze

    def failing_ingest(**kwargs):  # type: ignore[no-untyped-def]
        source_file = str(kwargs.get("source_file", ""))
        if source_file.endswith("bad.csv"):
            raise ValueError("simulated_ingest_failure")
        return original_ingest(**kwargs)

    monkeypatch.setattr(run_processor, "ingest_file_to_bronze", failing_ingest)

    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Strict Ingest Workspace",
            profile="team",
            security_baseline="strict",
        )
        create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Strict Files",
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
        assert int(output_refs["failure_count"]) == 1
        evidence_uri = str(output_refs["evidence_bundle_uri"])
        workspace_id, evidence_id = parse_evidence_uri(evidence_uri)
        bundle = load_evidence_bundle(
            workspace_id=workspace_id,
            evidence_id=evidence_id,
            storage_root=storage_root,
        )
        failures = bundle["payload"]["failures"]
        assert isinstance(failures, list)
        assert len(failures) == 1
        assert str(failures[0]["error"]) == "simulated_ingest_failure"
        assert unresolved_blocking_task_count(session, str(workspace["workspace_id"])) == 1
        tasks = list_review_tasks(session, str(workspace["workspace_id"]))
        assert any(
            task["priority"] == "quality_critical"
            and task["blocking"] is True
            and task["status"] == "open"
            for task in tasks
        )


def test_non_strict_ingest_records_warning_and_continues(tmp_path: Path, monkeypatch) -> None:
    exports_root = tmp_path / "exports_non_strict"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "good.csv").write_text("id,value\n1,ok\n", encoding="utf-8")
    (exports_root / "bad.csv").write_text("id,value\n2,bad\n", encoding="utf-8")

    original_ingest = run_processor.ingest_file_to_bronze

    def failing_ingest(**kwargs):  # type: ignore[no-untyped-def]
        source_file = str(kwargs.get("source_file", ""))
        if source_file.endswith("bad.csv"):
            raise ValueError("simulated_ingest_failure")
        return original_ingest(**kwargs)

    monkeypatch.setattr(run_processor, "ingest_file_to_bronze", failing_ingest)

    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Non-Strict Ingest Workspace",
            profile="starter",
            security_baseline="standard",
        )
        create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Non-Strict Files",
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
            strict_ingest=False,
        )
        assert result is not None
        assert result.status == "succeeded"
        session.commit()

    with session_factory() as session:
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(run["run_id"]),
        )
        assert run_state is not None
        output_refs = run_state["output_refs"]
        assert output_refs["strict_ingest"] is False
        assert int(output_refs["completeness_failure_count"]) == 1
        warning_uri = str(output_refs["completeness_warning_evidence_uri"])
        assert warning_uri.startswith("evidence://")
        assert unresolved_blocking_task_count(session, str(workspace["workspace_id"])) == 0
