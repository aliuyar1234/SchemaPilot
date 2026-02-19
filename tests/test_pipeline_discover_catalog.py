from __future__ import annotations

from pathlib import Path

from backend.control_plane.repository import (
    create_run,
    create_source,
    create_workspace,
    get_run,
    list_datasets,
)
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.evidence_store import load_evidence_bundle, resolve_evidence_uri
from backend.shared_domain.metadata_models import Base
from backend.workers.run_processor import process_run_by_id


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'pipeline.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_discover_run_populates_catalog_and_evidence_deterministically(tmp_path: Path) -> None:
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "customers.csv").write_text("id,name\n1,Alice\n", encoding="utf-8")
    (exports_root / "orders.csv").write_text("id,amount\n10,99.5\n", encoding="utf-8")

    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()

    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Pipeline Workspace",
            profile="starter",
            security_baseline="standard",
        )
        source = create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Pipeline Exports",
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
        datasets_after_first = list_datasets(session, str(workspace["workspace_id"]))
        assert len(datasets_after_first) == 2
        dataset_ids_after_first = sorted(
            str(dataset["dataset_id"]) for dataset in datasets_after_first
        )
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(first_run["run_id"]),
        )
        assert run_state is not None
        output_refs = run_state["output_refs"]
        assert isinstance(output_refs, dict)
        assert output_refs["dataset_count"] == 2
        assert sorted(str(item) for item in output_refs["dataset_ids"]) == dataset_ids_after_first
        first_snapshots = output_refs.get("source_snapshot_manifests", [])
        assert isinstance(first_snapshots, list)
        assert len(first_snapshots) == 1
        assert str(first_snapshots[0]["snapshot_uri"]).startswith("source-mirror://")
        for evidence in output_refs["evidence_bundles"]:
            resolved = resolve_evidence_uri(
                str(evidence["evidence_bundle_uri"]),
                storage_root=storage_root,
            )
            evidence_path = Path(str(resolved["path"]))
            assert evidence_path.exists()
            loaded = load_evidence_bundle(
                workspace_id=str(resolved["workspace_id"]),
                evidence_id=str(resolved["evidence_id"]),
                storage_root=storage_root,
            )
            assert loaded["content_hash"] == evidence["content_hash"]

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
        datasets_after_second = list_datasets(session, str(workspace["workspace_id"]))
        assert len(datasets_after_second) == 2
        dataset_ids_after_second = sorted(
            str(dataset["dataset_id"]) for dataset in datasets_after_second
        )
        assert dataset_ids_after_second == dataset_ids_after_first
        run_state = get_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_id=str(second_run["run_id"]),
        )
        assert run_state is not None
        output_refs = run_state["output_refs"]
        assert isinstance(output_refs, dict)
        assert sorted(str(item) for item in output_refs["dataset_ids"]) == dataset_ids_after_second
        assert str(source["source_id"]) in output_refs.get("source_ids", [])
        second_snapshots = output_refs.get("source_snapshot_manifests", [])
        assert isinstance(second_snapshots, list)
        assert len(second_snapshots) == 1
        assert str(first_snapshots[0]["snapshot_checksum"]) == str(
            second_snapshots[0]["snapshot_checksum"]
        )
