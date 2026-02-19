"""Worker-side processing helpers for target database lifecycle runs."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.config import load_settings
from backend.shared_domain.evidence_store import store_evidence_bundle
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import (
    GovernancePolicy,
    ReviewProposal,
    ReviewTask,
    TargetDbPlan,
    TargetDbProfile,
    TargetDbState,
    TargetDbSyncCursor,
)
from backend.shared_domain.secrets_store import load_secrets_store
from backend.shared_domain.target_db import TargetDbProfileConfig, get_target_db_adapter
from backend.workers.db_builder.index_planner import build_index_constraint_plan
from backend.workers.db_builder.postgres_rls import build_postgres_rls_plan
from backend.workers.db_builder.provision_postgres import (
    build_managed_postgres_provision_plan,
    managed_postgres_identifiers,
    provision_managed_postgres_secret_refs,
)
from backend.workers.db_builder.rotate_creds import rotate_target_db_credentials
from backend.workers.db_builder.validate_external_db import validate_external_target_db_profile

TARGET_DB_PLAN_RUN_TYPES = {
    "TARGET_DB_VALIDATE",
    "TARGET_DB_PROVISION_PLAN",
    "TARGET_DB_MIGRATION_PLAN",
    "TARGET_DB_LOAD_PLAN",
    "TARGET_DB_INDEX_PLAN",
    "TARGET_DB_RLS_PLAN",
}
TARGET_DB_APPLY_RUN_TYPES = {
    "TARGET_DB_PROVISION_APPLY",
    "TARGET_DB_MIGRATION_APPLY",
    "TARGET_DB_LOAD_APPLY",
    "TARGET_DB_INDEX_APPLY",
    "TARGET_DB_RLS_APPLY",
}
TARGET_DB_SYNC_RUN_TYPES = {"TARGET_DB_SYNC_RUN"}
TARGET_DB_ROTATION_RUN_TYPES = {"TARGET_DB_ROTATE_CREDENTIALS"}
SEMANTIC_MANIFEST_POLICY_TYPE = "semantic_manifest"


def process_target_db_run(
    session: Session,
    *,
    run_id: str,
    run_type: str,
    workspace_id: str,
    input_refs: dict[str, object],
    storage_root: str,
) -> dict[str, object]:
    """Execute deterministic target-db lifecycle run and return output refs."""
    target_db_id = str(input_refs.get("target_db_id", "")).strip()
    if not target_db_id:
        raise ValueError("target_db_id_required")
    profile = session.get(TargetDbProfile, target_db_id)
    if profile is None or profile.workspace_id != workspace_id:
        raise ValueError("target_db_profile_not_found")
    adapter_profile = TargetDbProfileConfig(
        workspace_id=workspace_id,
        target_db_id=target_db_id,
        db_type=profile.db_type,
        mode=profile.mode,
        connection=dict(profile.connection_json),
        credential_refs=dict(profile.credential_refs_json),
    )
    adapter = get_target_db_adapter(profile.db_type)
    state = _ensure_state(session=session, workspace_id=workspace_id)

    if run_type == "TARGET_DB_VALIDATE":
        if profile.mode == "external":
            result = validate_external_target_db_profile(
                profile=adapter_profile,
                profile_name=profile.name,
                desired_config_hash=profile.desired_config_hash,
            )
        else:
            result = adapter.validate(adapter_profile)
        state.last_validation_run_id = run_id
        state.health_status = "healthy" if result.ok else "unhealthy"
        evidence = store_evidence_bundle(
            workspace_id=workspace_id,
            storage_root=storage_root,
            bundle_type="target_db_validation",
            payload={
                "workspace_id": workspace_id,
                "target_db_id": target_db_id,
                "run_id": run_id,
                "db_type": profile.db_type,
                "mode": profile.mode,
                "result": result.details,
                "ok": result.ok,
            },
        )
        if result.ok:
            state.last_error_evidence_bundle_uri = None
        else:
            state.last_error_evidence_bundle_uri = evidence.evidence_bundle_uri
            if bool(result.details.get("drift_detected", False)):
                _ensure_target_db_drift_review_task(
                    session=session,
                    workspace_id=workspace_id,
                    target_db_id=target_db_id,
                    evidence_bundle_uri=evidence.evidence_bundle_uri,
                )
            session.flush()
            raise ValueError("target_db_validation_failed")
        session.flush()
        return {
            "target_db_id": target_db_id,
            "status": "validated" if result.ok else "validation_failed",
            "validation": result.details,
            "evidence_bundle_uri": evidence.evidence_bundle_uri,
        }

    if run_type in TARGET_DB_PLAN_RUN_TYPES:
        plan_id = str(input_refs.get("plan_id", "")).strip()
        plan_row = session.get(TargetDbPlan, plan_id) if plan_id else None
        plan_requires_approval = False
        if (
            run_type == "TARGET_DB_PROVISION_PLAN"
            and profile.db_type == "postgres"
            and profile.mode == "managed"
        ):
            host = str(profile.connection_json.get("host", "postgres"))
            port = _as_int(profile.connection_json.get("port"), default=5432)
            plan_payload = build_managed_postgres_provision_plan(
                workspace_id=workspace_id,
                target_db_id=target_db_id,
                host=host,
                port=port,
            )
        elif run_type == "TARGET_DB_MIGRATION_PLAN":
            semantic_state = _load_effective_semantic_state(
                session=session, workspace_id=workspace_id
            )
            if semantic_state is None:
                raise ValueError("semantic_manifest_required")
            migration_connection = dict(adapter_profile.connection)
            migration_connection["__semantic_manifest"] = semantic_state["manifest"]
            previous_manifest = semantic_state.get("previous_manifest")
            if isinstance(previous_manifest, dict):
                migration_connection["__previous_semantic_manifest"] = previous_manifest
            migration_connection["__target_build_id"] = str(
                input_refs.get("target_build_id", "")
            ).strip()
            migration_profile = TargetDbProfileConfig(
                workspace_id=adapter_profile.workspace_id,
                target_db_id=adapter_profile.target_db_id,
                db_type=adapter_profile.db_type,
                mode=adapter_profile.mode,
                connection=migration_connection,
                credential_refs=dict(adapter_profile.credential_refs),
            )
            plan_result = adapter.plan_migrations(migration_profile)
            plan_payload = {
                "plan_checksum": plan_result.plan_checksum,
                "destructive": plan_result.destructive,
                "statements": plan_result.statements,
                "details": plan_result.details,
            }
            plan_requires_approval = bool(plan_result.destructive)
        elif run_type == "TARGET_DB_LOAD_PLAN":
            requested_payload = dict(plan_row.payload_json) if plan_row is not None else {}
            plan_payload = _build_target_db_load_plan_payload(
                workspace_id=workspace_id,
                target_db_id=target_db_id,
                requested_payload=requested_payload,
            )
        elif run_type == "TARGET_DB_INDEX_PLAN":
            semantic_state = _load_effective_semantic_state(
                session=session, workspace_id=workspace_id
            )
            if semantic_state is None:
                raise ValueError("semantic_manifest_required")
            manifest = semantic_state.get("manifest")
            if not isinstance(manifest, dict):
                raise ValueError("semantic_manifest_required")
            include_constraints = bool(input_refs.get("include_constraints", True))
            target_build_id = str(input_refs.get("target_build_id", "")).strip()
            schema = str(profile.connection_json.get("schema", "")).strip() or None
            index_plan = build_index_constraint_plan(
                workspace_id=workspace_id,
                target_db_id=target_db_id,
                db_type=profile.db_type,
                schema=schema,
                target_build_id=target_build_id,
                semantic_manifest=manifest,
                include_constraints=include_constraints,
            )
            plan_payload = {
                "plan_checksum": index_plan.plan_checksum,
                "destructive": False,
                "statements": index_plan.statements,
                "details": {
                    "target_build_id": target_build_id,
                    "index_count": len(index_plan.indexes),
                    "constraint_count": len(index_plan.constraints),
                    "indexes": index_plan.indexes,
                    "constraints": index_plan.constraints,
                    "include_constraints": include_constraints,
                },
            }
            plan_requires_approval = bool(index_plan.statements)
        elif run_type == "TARGET_DB_RLS_PLAN":
            if str(profile.db_type).lower() != "postgres":
                raise ValueError("rls_supported_postgres_only")
            semantic_state = _load_effective_semantic_state(
                session=session, workspace_id=workspace_id
            )
            if semantic_state is None:
                raise ValueError("semantic_manifest_required")
            manifest = semantic_state.get("manifest")
            if not isinstance(manifest, dict):
                raise ValueError("semantic_manifest_required")
            schema = str(profile.connection_json.get("schema", "")).strip() or "public"
            rls_plan = build_postgres_rls_plan(
                workspace_id=workspace_id,
                target_db_id=target_db_id,
                schema=schema,
                semantic_manifest=manifest,
            )
            plan_payload = {
                "plan_checksum": rls_plan.plan_checksum,
                "destructive": False,
                "statements": rls_plan.statements,
                "details": {
                    "schema": schema,
                    "policy_count": len(rls_plan.policy_rows),
                    "policies": rls_plan.policy_rows,
                },
            }
            plan_requires_approval = bool(rls_plan.statements)
        else:
            plan_payload = {
                "plan_kind": run_type.lower(),
                "db_type": profile.db_type,
                "mode": profile.mode,
                "details": {"status": "planned"},
            }
        evidence = store_evidence_bundle(
            workspace_id=workspace_id,
            storage_root=storage_root,
            bundle_type="target_db_plan",
            payload={
                "workspace_id": workspace_id,
                "target_db_id": target_db_id,
                "run_id": run_id,
                "run_type": run_type,
                "plan_payload": plan_payload,
            },
        )
        if plan_row is not None:
            if run_type == "TARGET_DB_MIGRATION_PLAN":
                worker_plan_checksum = str(plan_payload.get("plan_checksum", "")).strip()
                if worker_plan_checksum:
                    plan_row.plan_checksum = worker_plan_checksum
                destructive = bool(plan_payload.get("destructive", False))
                plan_row.destructive = destructive
                plan_row.requires_approval = destructive
                if destructive:
                    review = _ensure_target_db_migration_review_task(
                        session=session,
                        workspace_id=workspace_id,
                        target_db_id=target_db_id,
                        plan_id=plan_row.plan_id,
                        evidence_bundle_uri=evidence.evidence_bundle_uri,
                    )
                    details_payload = plan_payload.get("details", {})
                    details = details_payload if isinstance(details_payload, dict) else {}
                    details["approval_task_id"] = review["task_id"]
                    details["approval_proposal_id"] = review["proposal_id"]
                    plan_payload["details"] = details
            elif run_type == "TARGET_DB_LOAD_PLAN":
                worker_plan_checksum = str(plan_payload.get("plan_checksum", "")).strip()
                if worker_plan_checksum:
                    plan_row.plan_checksum = worker_plan_checksum
                plan_row.destructive = False
                plan_row.requires_approval = False
            elif run_type == "TARGET_DB_INDEX_PLAN":
                worker_plan_checksum = str(plan_payload.get("plan_checksum", "")).strip()
                if worker_plan_checksum:
                    plan_row.plan_checksum = worker_plan_checksum
                plan_row.destructive = False
                plan_row.requires_approval = plan_requires_approval
                if plan_requires_approval:
                    review = _ensure_target_db_index_review_task(
                        session=session,
                        workspace_id=workspace_id,
                        target_db_id=target_db_id,
                        plan_id=plan_row.plan_id,
                        evidence_bundle_uri=evidence.evidence_bundle_uri,
                    )
                    details_payload = plan_payload.get("details", {})
                    details = details_payload if isinstance(details_payload, dict) else {}
                    details["approval_task_id"] = review["task_id"]
                    details["approval_proposal_id"] = review["proposal_id"]
                    plan_payload["details"] = details
            elif run_type == "TARGET_DB_RLS_PLAN":
                worker_plan_checksum = str(plan_payload.get("plan_checksum", "")).strip()
                if worker_plan_checksum:
                    plan_row.plan_checksum = worker_plan_checksum
                plan_row.destructive = False
                plan_row.requires_approval = plan_requires_approval
                if plan_requires_approval:
                    review = _ensure_target_db_rls_review_task(
                        session=session,
                        workspace_id=workspace_id,
                        target_db_id=target_db_id,
                        plan_id=plan_row.plan_id,
                        evidence_bundle_uri=evidence.evidence_bundle_uri,
                    )
                    details_payload = plan_payload.get("details", {})
                    details = details_payload if isinstance(details_payload, dict) else {}
                    details["approval_task_id"] = review["task_id"]
                    details["approval_proposal_id"] = review["proposal_id"]
                    plan_payload["details"] = details
            plan_row.status = "planned"
            plan_row.evidence_bundle_uri = evidence.evidence_bundle_uri
            merged = dict(plan_row.payload_json)
            merged["worker_plan"] = plan_payload
            plan_row.payload_json = merged
        session.flush()
        return {
            "target_db_id": target_db_id,
            "status": "planned",
            "run_type": run_type,
            "plan_id": plan_id or None,
            "plan_checksum": str(plan_payload.get("plan_checksum", "")),
            "requires_approval": plan_requires_approval,
            "plan_payload": plan_payload,
            "evidence_bundle_uri": evidence.evidence_bundle_uri,
        }

    if run_type in TARGET_DB_APPLY_RUN_TYPES:
        plan_id = str(input_refs.get("plan_id", "")).strip()
        plan_row = session.get(TargetDbPlan, plan_id) if plan_id else None
        if (
            run_type == "TARGET_DB_PROVISION_APPLY"
            and profile.db_type == "postgres"
            and profile.mode == "managed"
        ):
            settings = load_settings()
            secrets_store = load_secrets_store(settings)
            host = str(profile.connection_json.get("host", "postgres"))
            port = _as_int(profile.connection_json.get("port"), default=5432)
            identifiers = managed_postgres_identifiers(workspace_id=workspace_id)
            credential_refs = provision_managed_postgres_secret_refs(
                secrets_store=secrets_store,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
                host=host,
                port=port,
                identifiers=identifiers,
            )
            profile.connection_json = {
                "host": host,
                "port": int(port),
                "database": identifiers.database,
                "schema": identifiers.schema,
                "ssl_mode": str(profile.connection_json.get("ssl_mode", "disable")),
            }
            profile.credential_refs_json = credential_refs
            profile.status = "provisioned"
            profile.disabled = False
            state.active_target_db_id = target_db_id
            state.health_status = "healthy"
            apply_payload: dict[str, object] = {
                "status": "provisioned",
                "connection": dict(profile.connection_json),
                "credential_refs": credential_refs,
            }
        elif run_type == "TARGET_DB_MIGRATION_APPLY":
            plan_checksum = str(input_refs.get("plan_checksum", ""))
            if plan_row is None:
                raise ValueError("migration_plan_required")
            if str(plan_row.plan_checksum) != plan_checksum:
                raise ValueError("plan_checksum_mismatch")
            apply_payload = adapter.apply_migrations(adapter_profile, plan_checksum=plan_checksum)
            migration_id = new_ulid()
            apply_payload["migration_id"] = migration_id
            apply_payload["applied_plan_checksum"] = plan_checksum
            apply_payload["applied_at_epoch"] = int(time.time())
            profile.status = "ready"
        elif run_type == "TARGET_DB_LOAD_APPLY":
            apply_payload = adapter.load_initial(adapter_profile)
            load_plan = _load_worker_plan(plan_row)
            target_build_id = str(load_plan.get("target_build_id", "")).strip()
            if not target_build_id and plan_row is not None:
                target_build_id = str(plan_row.payload_json.get("target_build_id", "")).strip()
            staged_schema_ref = _derive_staging_schema_ref(
                profile=profile,
                workspace_id=workspace_id,
                target_build_id=target_build_id,
            )
            published_schema_ref = _derive_target_schema_ref(
                profile=profile,
                workspace_id=workspace_id,
                target_build_id=target_build_id,
            )
            datasets = _normalized_dataset_ids(load_plan.get("datasets", []))
            load_checksum = _stable_checksum(
                {
                    "workspace_id": workspace_id,
                    "target_db_id": target_db_id,
                    "target_build_id": target_build_id,
                    "datasets": datasets,
                    "staging_strategy": str(
                        load_plan.get("staging_strategy", "schema_staging_then_swap")
                    ),
                    "plan_checksum": str(input_refs.get("plan_checksum", "")).strip(),
                }
            )
            if target_build_id:
                state.current_build_id = target_build_id
                state.current_schema_ref = published_schema_ref
                apply_payload["current_build_id"] = target_build_id
                apply_payload["current_schema_ref"] = state.current_schema_ref
                if str(profile.db_type).lower() == "sqlite":
                    sqlite_database_ref = _materialize_sqlite_build_file(
                        workspace_id=workspace_id,
                        target_db_id=target_db_id,
                        target_build_id=target_build_id,
                        profile=profile,
                        storage_root=storage_root,
                    )
                    if sqlite_database_ref:
                        connection_payload = dict(profile.connection_json)
                        connection_payload["active_database"] = sqlite_database_ref
                        profile.connection_json = connection_payload
                        sync_status_raw = state.sync_status_json
                        sync_status = (
                            dict(sync_status_raw) if isinstance(sync_status_raw, dict) else {}
                        )
                        build_database_refs_raw = sync_status.get("build_database_refs", {})
                        build_database_refs = (
                            dict(build_database_refs_raw)
                            if isinstance(build_database_refs_raw, dict)
                            else {}
                        )
                        build_database_refs[target_build_id] = sqlite_database_ref
                        sync_status["build_database_refs"] = build_database_refs
                        state.sync_status_json = sync_status
                        apply_payload["sqlite_active_database"] = sqlite_database_ref
            apply_payload["datasets_loaded"] = datasets
            apply_payload["dataset_count"] = len(datasets)
            apply_payload["staging_strategy"] = str(
                load_plan.get("staging_strategy", "schema_staging_then_swap")
            )
            apply_payload["staging_schema_ref"] = staged_schema_ref
            apply_payload["published_schema_ref"] = published_schema_ref
            apply_payload["load_checksum"] = load_checksum
            apply_payload["idempotency_key"] = str(load_plan.get("idempotency_key", ""))
            profile.status = "ready"
        elif run_type == "TARGET_DB_INDEX_APPLY":
            plan_checksum = str(input_refs.get("plan_checksum", ""))
            if plan_row is None:
                raise ValueError("index_plan_required")
            if str(plan_row.plan_checksum) != plan_checksum:
                raise ValueError("plan_checksum_mismatch")
            worker_plan = _load_worker_plan(plan_row)
            statements_raw = worker_plan.get("statements", [])
            statements = (
                [str(item) for item in statements_raw if str(item).strip()]
                if isinstance(statements_raw, list)
                else []
            )
            apply_payload = {
                "status": "indexes_applied",
                "applied_plan_checksum": plan_checksum,
                "statement_count": len(statements),
                "statements": statements,
            }
        elif run_type == "TARGET_DB_RLS_APPLY":
            plan_checksum = str(input_refs.get("plan_checksum", ""))
            if plan_row is None:
                raise ValueError("rls_plan_required")
            if str(plan_row.plan_checksum) != plan_checksum:
                raise ValueError("plan_checksum_mismatch")
            worker_plan = _load_worker_plan(plan_row)
            statements_raw = worker_plan.get("statements", [])
            statements = (
                [str(item) for item in statements_raw if str(item).strip()]
                if isinstance(statements_raw, list)
                else []
            )
            apply_payload = {
                "status": "rls_applied",
                "applied_plan_checksum": plan_checksum,
                "statement_count": len(statements),
                "statements": statements,
            }
        else:
            apply_payload = {"status": "applied"}
        if plan_row is not None:
            plan_row.status = "applied"
            merged_payload = dict(plan_row.payload_json)
            merged_payload["applied_by_run_id"] = run_id
            merged_payload["applied_at_epoch"] = int(time.time())
            merged_payload["applied_result"] = dict(apply_payload)
            plan_row.payload_json = merged_payload
        evidence = store_evidence_bundle(
            workspace_id=workspace_id,
            storage_root=storage_root,
            bundle_type="target_db_apply",
            payload={
                "workspace_id": workspace_id,
                "target_db_id": target_db_id,
                "run_id": run_id,
                "run_type": run_type,
                "plan_id": plan_id or None,
                "result": apply_payload,
            },
        )
        state.last_error_evidence_bundle_uri = None
        state.health_status = "healthy"
        session.flush()
        return {
            "target_db_id": target_db_id,
            "status": "applied",
            "run_type": run_type,
            "plan_id": plan_id or None,
            "result": apply_payload,
            "evidence_bundle_uri": evidence.evidence_bundle_uri,
        }

    if run_type in TARGET_DB_ROTATION_RUN_TYPES:
        settings = load_settings()
        secrets_store = load_secrets_store(settings)
        rotation_window_seconds = _as_int(
            input_refs.get("dual_validity_window_seconds"),
            default=300,
        )
        rotation = rotate_target_db_credentials(
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            profile=profile,
            secrets_store=secrets_store,
            dual_validity_window_seconds=rotation_window_seconds,
        )
        profile.credential_refs_json = dict(rotation.rotated_refs)
        profile.disabled = False
        state.health_status = "healthy"
        state.last_error_evidence_bundle_uri = None
        evidence = store_evidence_bundle(
            workspace_id=workspace_id,
            storage_root=storage_root,
            bundle_type="target_db_credentials_rotation",
            payload={
                "workspace_id": workspace_id,
                "target_db_id": target_db_id,
                "run_id": run_id,
                "previous_credential_refs": rotation.previous_refs,
                "rotated_credential_refs": rotation.rotated_refs,
                "revoked_credential_refs": rotation.revoked_refs,
                "dual_validity_window_seconds": rotation.dual_validity_window_seconds,
            },
        )
        session.flush()
        return {
            "target_db_id": target_db_id,
            "status": "credentials_rotated",
            "previous_credential_refs": rotation.previous_refs,
            "rotated_credential_refs": rotation.rotated_refs,
            "revoked_credential_refs": rotation.revoked_refs,
            "dual_validity_window_seconds": rotation.dual_validity_window_seconds,
            "evidence_bundle_uri": evidence.evidence_bundle_uri,
        }

    if run_type in TARGET_DB_SYNC_RUN_TYPES:
        requested_dataset_ids = _normalized_dataset_ids(input_refs.get("datasets", []))
        strict_completeness = bool(input_refs.get("strict_completeness", True))
        max_runtime_seconds = _as_int(input_refs.get("max_runtime_seconds"), default=0)
        max_rows_per_dataset = _as_int(input_refs.get("max_rows_per_dataset"), default=0)
        max_datasets = _as_int(input_refs.get("max_datasets"), default=0)
        if max_datasets > 0 and len(requested_dataset_ids) > max_datasets:
            raise ValueError("target_db_sync_dataset_quota_exceeded")
        rows = (
            session.execute(
                select(TargetDbSyncCursor).where(
                    TargetDbSyncCursor.workspace_id == workspace_id,
                    TargetDbSyncCursor.target_db_id == target_db_id,
                    TargetDbSyncCursor.last_run_id == run_id,
                )
            )
            .scalars()
            .all()
        )
        rows_by_dataset_id = {row.dataset_id: row for row in rows}
        missing_dataset_ids = [
            dataset_id
            for dataset_id in requested_dataset_ids
            if dataset_id not in rows_by_dataset_id
        ]
        started_epoch = time.time()
        sync_result = adapter.sync_incremental(adapter_profile)
        elapsed_seconds = int(max(time.time() - started_epoch, 0.0))
        adapter_rows_raw = sync_result.datasets if isinstance(sync_result.datasets, list) else []
        adapter_rows: dict[str, int] = {}
        for item in adapter_rows_raw:
            if not isinstance(item, dict):
                continue
            dataset_id = str(item.get("dataset_id", "")).strip()
            if not dataset_id:
                continue
            row_count = _as_int(item.get("rows_upserted"), default=0)
            adapter_rows[dataset_id] = row_count
        if max_rows_per_dataset > 0:
            over_limit = sorted(
                dataset_id
                for dataset_id, row_count in adapter_rows.items()
                if row_count > max_rows_per_dataset
            )
            if over_limit:
                failure_payload = {
                    "workspace_id": workspace_id,
                    "target_db_id": target_db_id,
                    "run_id": run_id,
                    "reason": "target_db_sync_row_budget_exceeded",
                    "max_rows_per_dataset": max_rows_per_dataset,
                    "over_limit_dataset_ids": over_limit,
                    "adapter_rows": adapter_rows,
                }
                failure_evidence = store_evidence_bundle(
                    workspace_id=workspace_id,
                    storage_root=storage_root,
                    bundle_type="target_db_sync_failure",
                    payload=failure_payload,
                )
                state.last_error_evidence_bundle_uri = failure_evidence.evidence_bundle_uri
                state.health_status = "unhealthy"
                session.flush()
                raise ValueError("target_db_sync_row_budget_exceeded")
        if max_runtime_seconds > 0 and elapsed_seconds > max_runtime_seconds:
            failure_payload = {
                "workspace_id": workspace_id,
                "target_db_id": target_db_id,
                "run_id": run_id,
                "reason": "target_db_sync_runtime_budget_exceeded",
                "max_runtime_seconds": max_runtime_seconds,
                "elapsed_seconds": elapsed_seconds,
            }
            failure_evidence = store_evidence_bundle(
                workspace_id=workspace_id,
                storage_root=storage_root,
                bundle_type="target_db_sync_failure",
                payload=failure_payload,
            )
            state.last_error_evidence_bundle_uri = failure_evidence.evidence_bundle_uri
            state.health_status = "unhealthy"
            session.flush()
            raise ValueError("target_db_sync_runtime_budget_exceeded")
        if strict_completeness and (missing_dataset_ids or not sync_result.ok):
            failure_payload = {
                "workspace_id": workspace_id,
                "target_db_id": target_db_id,
                "run_id": run_id,
                "requested_dataset_ids": requested_dataset_ids,
                "missing_dataset_ids": missing_dataset_ids,
                "adapter_sync_ok": sync_result.ok,
                "adapter_sync_details": sync_result.details,
            }
            failure_evidence = store_evidence_bundle(
                workspace_id=workspace_id,
                storage_root=storage_root,
                bundle_type="target_db_sync_failure",
                payload=failure_payload,
            )
            state.last_error_evidence_bundle_uri = failure_evidence.evidence_bundle_uri
            state.health_status = "unhealthy"
            session.flush()
            raise ValueError("target_db_sync_failed_strict_completeness")
        sync_datasets: list[dict[str, object]] = []
        for row in rows:
            if requested_dataset_ids and row.dataset_id not in requested_dataset_ids:
                continue
            row.cursor_hash = stable_cursor_hash(
                {
                    "dataset_id": row.dataset_id,
                    "run_id": run_id,
                    "previous_cursor_hash": row.cursor_hash,
                }
            )
            row.last_status = "succeeded"
            sync_datasets.append(
                {
                    "dataset_id": row.dataset_id,
                    "cursor_hash": row.cursor_hash,
                    "last_run_id": row.last_run_id,
                    "last_status": row.last_status,
                    "rows_upserted": adapter_rows.get(row.dataset_id, 0),
                }
            )
        state.last_successful_sync_epoch = int(time.time())
        current_sync_status_raw = state.sync_status_json
        current_sync_status = (
            dict(current_sync_status_raw) if isinstance(current_sync_status_raw, dict) else {}
        )
        current_sync_status["datasets"] = sync_datasets
        state.sync_status_json = current_sync_status
        state.health_status = "healthy"
        state.last_error_evidence_bundle_uri = None
        evidence = store_evidence_bundle(
            workspace_id=workspace_id,
            storage_root=storage_root,
            bundle_type="target_db_sync",
            payload={
                "workspace_id": workspace_id,
                "target_db_id": target_db_id,
                "run_id": run_id,
                "requested_dataset_ids": requested_dataset_ids,
                "datasets": sync_datasets,
                "adapter_sync_ok": sync_result.ok,
                "adapter_sync_details": sync_result.details,
                "elapsed_seconds": elapsed_seconds,
                "max_runtime_seconds": max_runtime_seconds,
                "max_rows_per_dataset": max_rows_per_dataset,
                "max_datasets": max_datasets,
            },
        )
        session.flush()
        return {
            "target_db_id": target_db_id,
            "status": "synced",
            "dataset_count": len(sync_datasets),
            "datasets": sync_datasets,
            "elapsed_seconds": elapsed_seconds,
            "max_runtime_seconds": max_runtime_seconds,
            "max_rows_per_dataset": max_rows_per_dataset,
            "max_datasets": max_datasets,
            "evidence_bundle_uri": evidence.evidence_bundle_uri,
        }

    raise ValueError(f"unsupported_target_db_run_type:{run_type}")


def _ensure_state(*, session: Session, workspace_id: str) -> TargetDbState:
    state = session.get(TargetDbState, workspace_id)
    if state is not None:
        return state
    state = TargetDbState(
        workspace_id=workspace_id,
        active_target_db_id=None,
        current_build_id=None,
        current_schema_ref=None,
        last_successful_sync_epoch=None,
        health_status="unknown",
        last_validation_run_id=None,
        last_error_evidence_bundle_uri=None,
        sync_status_json={"datasets": []},
    )
    session.add(state)
    session.flush()
    return state


def _ensure_target_db_drift_review_task(
    *,
    session: Session,
    workspace_id: str,
    target_db_id: str,
    evidence_bundle_uri: str,
) -> None:
    proposal = (
        session.execute(
            select(ReviewProposal).where(
                ReviewProposal.workspace_id == workspace_id,
                ReviewProposal.proposal_type == "target_db_drift_proposal",
                ReviewProposal.evidence_bundle_uri == evidence_bundle_uri,
            )
        )
        .scalars()
        .first()
    )
    if proposal is None:
        proposal = ReviewProposal(
            proposal_id=new_ulid(),
            workspace_id=workspace_id,
            proposal_type="target_db_drift_proposal",
            evidence_bundle_uri=evidence_bundle_uri,
            confidence=1.0,
            status="open",
        )
        session.add(proposal)
        session.flush()
    existing_task = (
        session.execute(
            select(ReviewTask).where(
                ReviewTask.workspace_id == workspace_id,
                ReviewTask.subject_ref == proposal.proposal_id,
                ReviewTask.priority == "quality_critical",
                ReviewTask.blocking.is_(True),
                ReviewTask.status.in_(("open", "in_review")),
            )
        )
        .scalars()
        .first()
    )
    if existing_task is None:
        session.add(
            ReviewTask(
                task_id=new_ulid(),
                workspace_id=workspace_id,
                priority="quality_critical",
                subject_ref=proposal.proposal_id,
                status="open",
                blocking=True,
            )
        )
        session.flush()


def _ensure_target_db_migration_review_task(
    *,
    session: Session,
    workspace_id: str,
    target_db_id: str,
    plan_id: str,
    evidence_bundle_uri: str,
) -> dict[str, str]:
    proposal = (
        session.execute(
            select(ReviewProposal).where(
                ReviewProposal.workspace_id == workspace_id,
                ReviewProposal.proposal_type == "target_db_migration_destructive_proposal",
                ReviewProposal.evidence_bundle_uri == evidence_bundle_uri,
            )
        )
        .scalars()
        .first()
    )
    if proposal is None:
        proposal = ReviewProposal(
            proposal_id=new_ulid(),
            workspace_id=workspace_id,
            proposal_type="target_db_migration_destructive_proposal",
            evidence_bundle_uri=evidence_bundle_uri,
            confidence=1.0,
            status="open",
        )
        session.add(proposal)
        session.flush()
    existing_task = (
        session.execute(
            select(ReviewTask).where(
                ReviewTask.workspace_id == workspace_id,
                ReviewTask.subject_ref == proposal.proposal_id,
                ReviewTask.priority == "security_critical",
                ReviewTask.blocking.is_(True),
                ReviewTask.status.in_(("open", "in_review")),
            )
        )
        .scalars()
        .first()
    )
    if existing_task is None:
        task = ReviewTask(
            task_id=new_ulid(),
            workspace_id=workspace_id,
            priority="security_critical",
            subject_ref=proposal.proposal_id,
            status="open",
            blocking=True,
        )
        session.add(task)
        session.flush()
        task_id = task.task_id
    else:
        task_id = existing_task.task_id
    plan_row = session.get(TargetDbPlan, plan_id)
    if plan_row is not None:
        merged_payload = dict(plan_row.payload_json)
        merged_payload["approval_task_id"] = task_id
        merged_payload["approval_proposal_id"] = proposal.proposal_id
        plan_row.payload_json = merged_payload
        session.flush()
    return {"proposal_id": proposal.proposal_id, "task_id": task_id}


def _ensure_target_db_index_review_task(
    *,
    session: Session,
    workspace_id: str,
    target_db_id: str,
    plan_id: str,
    evidence_bundle_uri: str,
) -> dict[str, str]:
    return _ensure_target_db_generic_review_task(
        session=session,
        workspace_id=workspace_id,
        target_db_id=target_db_id,
        plan_id=plan_id,
        evidence_bundle_uri=evidence_bundle_uri,
        proposal_type="target_db_index_plan_proposal",
        priority="quality_critical",
    )


def _ensure_target_db_rls_review_task(
    *,
    session: Session,
    workspace_id: str,
    target_db_id: str,
    plan_id: str,
    evidence_bundle_uri: str,
) -> dict[str, str]:
    return _ensure_target_db_generic_review_task(
        session=session,
        workspace_id=workspace_id,
        target_db_id=target_db_id,
        plan_id=plan_id,
        evidence_bundle_uri=evidence_bundle_uri,
        proposal_type="target_db_rls_plan_proposal",
        priority="security_critical",
    )


def _ensure_target_db_generic_review_task(
    *,
    session: Session,
    workspace_id: str,
    target_db_id: str,
    plan_id: str,
    evidence_bundle_uri: str,
    proposal_type: str,
    priority: str,
) -> dict[str, str]:
    _ = target_db_id
    proposal = (
        session.execute(
            select(ReviewProposal).where(
                ReviewProposal.workspace_id == workspace_id,
                ReviewProposal.proposal_type == proposal_type,
                ReviewProposal.evidence_bundle_uri == evidence_bundle_uri,
            )
        )
        .scalars()
        .first()
    )
    if proposal is None:
        proposal = ReviewProposal(
            proposal_id=new_ulid(),
            workspace_id=workspace_id,
            proposal_type=proposal_type,
            evidence_bundle_uri=evidence_bundle_uri,
            confidence=1.0,
            status="open",
        )
        session.add(proposal)
        session.flush()
    existing_task = (
        session.execute(
            select(ReviewTask).where(
                ReviewTask.workspace_id == workspace_id,
                ReviewTask.subject_ref == proposal.proposal_id,
                ReviewTask.priority == priority,
                ReviewTask.blocking.is_(True),
                ReviewTask.status.in_(("open", "in_review")),
            )
        )
        .scalars()
        .first()
    )
    if existing_task is None:
        task = ReviewTask(
            task_id=new_ulid(),
            workspace_id=workspace_id,
            priority=priority,
            subject_ref=proposal.proposal_id,
            status="open",
            blocking=True,
        )
        session.add(task)
        session.flush()
        task_id = task.task_id
    else:
        task_id = existing_task.task_id
    plan_row = session.get(TargetDbPlan, plan_id)
    if plan_row is not None:
        merged_payload = dict(plan_row.payload_json)
        merged_payload["approval_task_id"] = task_id
        merged_payload["approval_proposal_id"] = proposal.proposal_id
        plan_row.payload_json = merged_payload
        session.flush()
    return {"proposal_id": proposal.proposal_id, "task_id": task_id}


def _load_effective_semantic_state(
    *, session: Session, workspace_id: str
) -> dict[str, object] | None:
    row = (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == SEMANTIC_MANIFEST_POLICY_TYPE,
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    try:
        payload = json.loads(row.definition_ref)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict):
        return None
    previous_manifest = payload.get("previous_manifest")
    return {
        "manifest": manifest,
        "previous_manifest": previous_manifest if isinstance(previous_manifest, dict) else None,
        "manifest_checksum": str(payload.get("manifest_checksum", "")),
        "previous_manifest_checksum": str(payload.get("previous_manifest_checksum", "")),
    }


def _build_target_db_load_plan_payload(
    *,
    workspace_id: str,
    target_db_id: str,
    requested_payload: dict[str, object],
) -> dict[str, object]:
    datasets = _normalized_dataset_ids(requested_payload.get("datasets", []))
    staging_strategy = str(
        requested_payload.get("staging_strategy", "schema_staging_then_swap")
    ).strip() or "schema_staging_then_swap"
    target_build_id = str(requested_payload.get("target_build_id", "")).strip()
    plan_checksum = _stable_checksum(
        {
            "workspace_id": workspace_id,
            "target_db_id": target_db_id,
            "target_build_id": target_build_id,
            "datasets": datasets,
            "staging_strategy": staging_strategy,
        }
    )
    idempotency_key = _stable_checksum(
        {
            "workspace_id": workspace_id,
            "target_db_id": target_db_id,
            "op": "target_db_load_apply",
            "plan_checksum": plan_checksum,
        }
    )
    return {
        "plan_checksum": plan_checksum,
        "destructive": False,
        "target_build_id": target_build_id,
        "datasets": datasets,
        "staging_strategy": staging_strategy,
        "idempotency_key": idempotency_key,
        "details": {
            "dataset_count": len(datasets),
            "row_estimate": len(datasets) * 1000,
            "strict_completeness": True,
        },
    }


def _load_worker_plan(plan_row: TargetDbPlan | None) -> dict[str, object]:
    if plan_row is None:
        return {}
    payload = dict(plan_row.payload_json)
    worker_plan_raw = payload.get("worker_plan", {})
    if not isinstance(worker_plan_raw, dict):
        return {}
    return worker_plan_raw


def _normalized_dataset_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    dataset_ids = [str(item).strip() for item in value if str(item).strip()]
    return sorted(set(dataset_ids))


def _stable_checksum(payload: dict[str, object]) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def stable_cursor_hash(payload: dict[str, object]) -> str:
    """Deterministic helper for sync cursor hashing."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _as_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _derive_target_schema_ref(
    *,
    profile: TargetDbProfile,
    workspace_id: str,
    target_build_id: str,
) -> str:
    schema = str(profile.connection_json.get("schema", "")).strip()
    if schema:
        return schema
    if profile.db_type == "sqlite":
        return f"sqlite_build_{target_build_id}"
    safe_workspace = workspace_id.replace("-", "_")
    safe_build = target_build_id.replace("-", "_")
    return f"sp_{safe_workspace}_{safe_build}"


def _derive_staging_schema_ref(
    *,
    profile: TargetDbProfile,
    workspace_id: str,
    target_build_id: str,
) -> str:
    base = _derive_target_schema_ref(
        profile=profile,
        workspace_id=workspace_id,
        target_build_id=target_build_id or "pending",
    )
    return f"{base}__staging"


def _materialize_sqlite_build_file(
    *,
    workspace_id: str,
    target_db_id: str,
    target_build_id: str,
    profile: TargetDbProfile,
    storage_root: str,
) -> str | None:
    connection = dict(profile.connection_json)
    source_path_raw = str(connection.get("database", "")).strip()
    if not source_path_raw:
        return None
    source_path = Path(source_path_raw)
    if not source_path.exists():
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.touch()
    build_root = (
        Path(storage_root)
        / "target_db"
        / workspace_id
        / target_db_id
        / "builds"
    )
    build_root.mkdir(parents=True, exist_ok=True)
    build_path = build_root / f"{target_build_id}.sqlite"
    shutil.copy2(source_path, build_path)
    return build_path.as_posix()


