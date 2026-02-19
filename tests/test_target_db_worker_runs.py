from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from backend.control_plane.repository import (
    create_run,
    create_target_db_plan,
    create_target_db_profile,
    create_workspace,
    get_run,
    upsert_target_db_sync_cursor,
)
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import (
    Base,
    GovernancePolicy,
    ReviewProposal,
    ReviewTask,
    RunRecord,
    TargetDbPlan,
    TargetDbProfile,
    TargetDbState,
)
from backend.workers.service import process_queued_runs_once


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'target_db_worker.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_worker_processes_target_db_provision_plan_run(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Run Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
        )
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="provision",
            payload={},
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_PROVISION_PLAN",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "provision",
            "plan_checksum": str(plan["plan_checksum"]),
        }
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
        assert run_state["status"] == "succeeded"
        output_refs = run_state["output_refs"]
        assert output_refs["status"] == "planned"
        assert str(output_refs["evidence_bundle_uri"]).startswith("evidence://")


def test_worker_processes_target_db_provision_apply_run(tmp_path: Path, monkeypatch) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    monkeypatch.setenv("SCHEMAPILOT_SECRETS_STORE_BACKEND", "local_encrypted")
    monkeypatch.setenv("SCHEMAPILOT_SECRETS_STORE_ROOT", (tmp_path / "secrets").as_posix())
    monkeypatch.setenv("SCHEMAPILOT_SECRETS_MASTER_KEY", "target-db-test-master-key")

    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Apply Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
            connection={"host": "postgres", "port": 5432},
        )
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="provision",
            payload={},
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_PROVISION_APPLY",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "provision",
            "plan_checksum": str(plan["plan_checksum"]),
        }
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
        assert run_state["status"] == "succeeded"
        profile_row = session.get(TargetDbProfile, str(profile["target_db_id"]))
        assert profile_row is not None
        assert profile_row.status == "provisioned"
        assert str(profile_row.credential_refs_json.get("reader", "")).startswith("secret://local/")
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        assert state_row.active_target_db_id == str(profile["target_db_id"])


def test_worker_external_validate_drift_fails_closed_and_creates_task(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Validate Drift Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="external-db",
            db_type="postgres",
            mode="external",
            connection={"host": "db.internal", "port": 5432, "database": "analytics"},
            credential_refs={
                "reader": "secret://local/external/reader",
                "writer": "secret://local/external/writer",
            },
        )
        profile_row = session.get(TargetDbProfile, str(profile["target_db_id"]))
        assert profile_row is not None
        profile_row.desired_config_hash = "sha256:drifted"

        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_VALIDATE",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_kind": "validate",
        }
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
        tasks = (
            session.execute(
                select(ReviewTask).where(
                    ReviewTask.workspace_id == workspace_id,
                    ReviewTask.priority == "quality_critical",
                    ReviewTask.blocking.is_(True),
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) >= 1


def test_worker_migration_plan_marks_destructive_and_creates_review_task(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Migration Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
            connection={"schema": "gold"},
        )
        semantic_manifest_current = {
            "manifest_version": "1",
            "workspace_id": workspace_id,
            "entities": [
                {
                    "entity_id": "invoice",
                    "dataset_id": "dataset_invoices",
                    "primary_key": "invoice_id",
                    "attributes": ["customer_id"],
                }
            ],
            "metrics": [],
            "joins": [],
        }
        semantic_manifest_previous = {
            "manifest_version": "1",
            "workspace_id": workspace_id,
            "entities": [
                {
                    "entity_id": "invoice",
                    "dataset_id": "dataset_invoices",
                    "primary_key": "invoice_id",
                    "attributes": ["customer_id"],
                },
                {
                    "entity_id": "customer",
                    "dataset_id": "dataset_customers",
                    "primary_key": "customer_id",
                    "attributes": ["customer_name"],
                },
            ],
            "metrics": [],
            "joins": [],
        }
        semantic_policy = GovernancePolicy(
            policy_id="sem_active_1",
            workspace_id=workspace_id,
            policy_type="semantic_manifest",
            status="active",
            definition_ref=json.dumps(
                {
                    "manifest": semantic_manifest_current,
                    "manifest_checksum": "new",
                    "previous_manifest": semantic_manifest_previous,
                    "previous_manifest_checksum": "old",
                },
                sort_keys=True,
            ),
        )
        session.add(semantic_policy)
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="migration",
            payload={"semantic_manifest_id": "sem_active_1", "target_build_id": "bld_1"},
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_MIGRATION_PLAN",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "migration",
            "plan_checksum": str(plan["plan_checksum"]),
            "target_build_id": "bld_1",
        }
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
        assert run_state["status"] == "succeeded"
        plan_row = session.get(TargetDbPlan, str(plan["plan_id"]))
        assert plan_row is not None
        assert plan_row.destructive is True
        assert plan_row.requires_approval is True
        assert plan_row.plan_checksum.startswith("sha256:")
        worker_plan = plan_row.payload_json.get("worker_plan", {})
        assert isinstance(worker_plan, dict)
        statements = worker_plan.get("statements", [])
        assert isinstance(statements, list)
        assert any(str(item).startswith("DROP TABLE IF EXISTS") for item in statements)
        review_tasks = (
            session.execute(
                select(ReviewTask).where(
                    ReviewTask.workspace_id == workspace_id,
                    ReviewTask.priority == "security_critical",
                    ReviewTask.blocking.is_(True),
                )
            )
            .scalars()
            .all()
        )
        assert len(review_tasks) == 1
        proposals = (
            session.execute(
                select(ReviewProposal).where(
                    ReviewProposal.workspace_id == workspace_id,
                    ReviewProposal.proposal_type == "target_db_migration_destructive_proposal",
                )
            )
            .scalars()
            .all()
        )
        assert len(proposals) == 1


def test_worker_migration_apply_records_applied_payload(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Migration Apply Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
        )
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="migration",
            payload={},
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_MIGRATION_APPLY",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "migration",
            "plan_checksum": str(plan["plan_checksum"]),
        }
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
        assert run_state["status"] == "succeeded"
        output_refs = run_state["output_refs"]
        assert str(output_refs["evidence_bundle_uri"]).startswith("evidence://")
        plan_row = session.get(TargetDbPlan, str(plan["plan_id"]))
        assert plan_row is not None
        assert plan_row.status == "applied"
        assert str(plan_row.payload_json.get("applied_by_run_id", "")) == str(run["run_id"])
        applied = plan_row.payload_json.get("applied_result", {})
        assert isinstance(applied, dict)
        assert str(applied.get("migration_id", "")).strip() != ""


def test_worker_migration_apply_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Migration Mismatch Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
        )
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="migration",
            payload={},
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_MIGRATION_APPLY",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "migration",
            "plan_checksum": "sha256:deadbeef",
        }
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
        plan_row = session.get(TargetDbPlan, str(plan["plan_id"]))
        assert plan_row is not None
        assert plan_row.status == "draft"


def test_worker_load_apply_updates_target_state_build_and_schema(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Load Apply Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
            connection={"schema": "gold_serving"},
        )
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="load",
            payload={"target_build_id": "bld_42"},
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_LOAD_APPLY",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "load",
            "plan_checksum": str(plan["plan_checksum"]),
        }
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
        assert run_state["status"] == "succeeded"
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        assert state_row.current_build_id == "bld_42"
        assert state_row.current_schema_ref == "gold_serving"


def test_worker_load_plan_writes_deterministic_worker_plan(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Load Plan Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
        )
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="load",
            payload={
                "target_build_id": "bld_100",
                "datasets": ["gold.orders", "gold.customers", "gold.orders"],
                "staging_strategy": "schema_staging_then_swap",
            },
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_LOAD_PLAN",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "load",
            "plan_checksum": str(plan["plan_checksum"]),
        }
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=storage_root,
        max_runs=1,
    )
    assert processed == 1

    with session_factory() as session:
        plan_row = session.get(TargetDbPlan, str(plan["plan_id"]))
        assert plan_row is not None
        worker_plan = plan_row.payload_json.get("worker_plan", {})
        assert isinstance(worker_plan, dict)
        assert worker_plan["target_build_id"] == "bld_100"
        assert worker_plan["datasets"] == ["gold.customers", "gold.orders"]
        assert worker_plan["staging_strategy"] == "schema_staging_then_swap"
        assert str(worker_plan["idempotency_key"]).startswith("sha256:")
        assert str(plan_row.plan_checksum).startswith("sha256:")


def test_worker_sync_strict_fail_closed_when_requested_dataset_missing(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Sync Strict Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_SYNC_RUN",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "datasets": ["ds_missing"],
            "strict_completeness": True,
        }
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
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        assert state_row.health_status == "unhealthy"
        assert str(state_row.last_error_evidence_bundle_uri or "").startswith("evidence://")


def test_worker_sync_preserves_build_schema_refs_in_state(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Sync Preserve Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
        )
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.active_target_db_id = str(profile["target_db_id"])
        state_row.current_build_id = "build_1"
        state_row.current_schema_ref = "gold_serving"
        state_row.health_status = "healthy"
        state_row.sync_status_json = {
            "datasets": [],
            "build_schema_refs": {"build_1": "gold_serving"},
        }
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_SYNC_RUN",
        )
        upsert_target_db_sync_cursor(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            dataset_id="ds_orders",
            cursor_hash="sha256:seed",
            run_id=str(run["run_id"]),
            status="queued",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "datasets": ["ds_orders"],
            "strict_completeness": True,
        }
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
        assert run_state["status"] == "succeeded"
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        build_refs_raw = state_row.sync_status_json.get("build_schema_refs", {})
        assert isinstance(build_refs_raw, dict)
        assert build_refs_raw.get("build_1") == "gold_serving"


def test_worker_index_plan_creates_quality_critical_review_task(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Index Plan Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
            connection={"schema": "gold"},
        )
        semantic_manifest = {
            "manifest_version": "1",
            "workspace_id": workspace_id,
            "entities": [
                {
                    "entity_id": "invoice",
                    "dataset_id": "dataset_invoices",
                    "primary_key": "invoice_id",
                    "attributes": ["customer_id", "region"],
                }
            ],
            "metrics": [],
            "joins": [],
        }
        session.add(
            GovernancePolicy(
                policy_id="sem_index_active",
                workspace_id=workspace_id,
                policy_type="semantic_manifest",
                status="active",
                definition_ref=json.dumps(
                    {"manifest": semantic_manifest, "manifest_checksum": "index"},
                    sort_keys=True,
                ),
            )
        )
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="index",
            payload={"target_build_id": "build_idx_1", "include_constraints": True},
        )
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_INDEX_PLAN",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "index",
            "plan_checksum": str(plan["plan_checksum"]),
            "target_build_id": "build_idx_1",
            "include_constraints": True,
        }
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=storage_root,
        max_runs=1,
    )
    assert processed == 1

    with session_factory() as session:
        run_state = get_run(session, workspace_id=workspace_id, run_id=str(run["run_id"]))
        assert run_state is not None
        assert run_state["status"] == "succeeded"
        plan_row = session.get(TargetDbPlan, str(plan["plan_id"]))
        assert plan_row is not None
        assert plan_row.requires_approval is True
        worker_plan = plan_row.payload_json.get("worker_plan", {})
        assert isinstance(worker_plan, dict)
        statements = worker_plan.get("statements", [])
        assert isinstance(statements, list)
        assert any(str(item).startswith("CREATE INDEX IF NOT EXISTS") for item in statements)
        review_tasks = (
            session.execute(
                select(ReviewTask).where(
                    ReviewTask.workspace_id == workspace_id,
                    ReviewTask.priority == "quality_critical",
                    ReviewTask.blocking.is_(True),
                )
            )
            .scalars()
            .all()
        )
        assert len(review_tasks) >= 1


def test_worker_sync_dataset_quota_fails_closed(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target Sync Quota Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
        )
        run = create_run(session, workspace_id=workspace_id, run_type="TARGET_DB_SYNC_RUN")
        upsert_target_db_sync_cursor(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            dataset_id="ds_a",
            cursor_hash="sha256:a",
            run_id=str(run["run_id"]),
            status="queued",
        )
        upsert_target_db_sync_cursor(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            dataset_id="ds_b",
            cursor_hash="sha256:b",
            run_id=str(run["run_id"]),
            status="queued",
        )
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "datasets": ["ds_a", "ds_b"],
            "strict_completeness": True,
            "max_datasets": 1,
        }
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=storage_root,
        max_runs=1,
    )
    assert processed == 1

    with session_factory() as session:
        run_state = get_run(session, workspace_id=workspace_id, run_id=str(run["run_id"]))
        assert run_state is not None
        assert run_state["status"] == "failed"
        assert run_state["output_refs"]["error"] == "target_db_sync_dataset_quota_exceeded"


def test_worker_rls_plan_generates_postgres_statements(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    storage_root = (tmp_path / "storage").as_posix()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Target RLS Plan Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="postgres",
            mode="managed",
            connection={"schema": "gold"},
        )
        semantic_manifest = {
            "manifest_version": "1",
            "workspace_id": workspace_id,
            "entities": [
                {
                    "entity_id": "invoice",
                    "dataset_id": "dataset_invoices",
                    "primary_key": "invoice_id",
                    "attributes": ["workspace_id", "customer_id"],
                }
            ],
            "metrics": [],
            "joins": [],
        }
        session.add(
            GovernancePolicy(
                policy_id="sem_rls_active",
                workspace_id=workspace_id,
                policy_type="semantic_manifest",
                status="active",
                definition_ref=json.dumps(
                    {"manifest": semantic_manifest, "manifest_checksum": "rls"},
                    sort_keys=True,
                ),
            )
        )
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=str(profile["target_db_id"]),
            plan_kind="rls",
            payload={},
        )
        run = create_run(session, workspace_id=workspace_id, run_type="TARGET_DB_RLS_PLAN")
        run_row = session.get(RunRecord, str(run["run_id"]))
        assert run_row is not None
        run_row.input_refs_json = {
            "target_db_id": str(profile["target_db_id"]),
            "plan_id": str(plan["plan_id"]),
            "plan_kind": "rls",
            "plan_checksum": str(plan["plan_checksum"]),
        }
        session.commit()

    processed = process_queued_runs_once(
        session_factory=session_factory,
        storage_root=storage_root,
        max_runs=1,
    )
    assert processed == 1

    with session_factory() as session:
        run_state = get_run(session, workspace_id=workspace_id, run_id=str(run["run_id"]))
        assert run_state is not None
        assert run_state["status"] == "succeeded"
        plan_row = session.get(TargetDbPlan, str(plan["plan_id"]))
        assert plan_row is not None
        assert plan_row.requires_approval is True
        worker_plan = plan_row.payload_json.get("worker_plan", {})
        assert isinstance(worker_plan, dict)
        statements = worker_plan.get("statements", [])
        assert isinstance(statements, list)
        assert any("ENABLE ROW LEVEL SECURITY" in str(item) for item in statements)
