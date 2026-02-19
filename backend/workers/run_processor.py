"""Deterministic queued-run processing for worker services."""

from __future__ import annotations

import csv
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.connector_state import (
    load_connector_state,
    next_cursor_from_discovery_rows,
    save_connector_state,
)
from backend.shared_domain.evidence_store import store_evidence_bundle
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import (
    CatalogDataset,
    CatalogSource,
    GovernancePolicy,
    ReviewProposal,
    ReviewTask,
    RunRecord,
    RunStepRecord,
)
from backend.shared_domain.observability import observe_worker_step_duration
from backend.shared_domain.plugin_loader import ConnectorPluginSpec, load_connector_plugin_specs
from backend.shared_domain.source_mirror import (
    build_source_snapshot_manifest,
    persist_source_snapshot_manifest,
)
from backend.workers.anomaly_detection import detect_profile_anomalies
from backend.workers.bronze import ingest_file_to_bronze
from backend.workers.connectors.db_dumps import discover as discover_db_dumps
from backend.workers.connectors.dropzone import discover_dropzone_files
from backend.workers.connectors.filesystem import DiscoveredFile, discover_files
from backend.workers.connectors.jira_exports import discover_jira_exports
from backend.workers.connectors.plugin_runner import execute_connector_plugin
from backend.workers.connectors.zendesk_exports import discover_zendesk_exports
from backend.workers.drift import detect_schema_drift
from backend.workers.pii import detect_pii_proposals
from backend.workers.profiler import profile_csv_file
from backend.workers.semantic_builder import build_semantic_manifest_candidate
from backend.workers.semantic_drift import detect_semantic_manifest_drift
from backend.workers.target_db_builder import process_target_db_run

DEFAULT_INCLUDE_GLOBS = ["**/*.csv"]
PROFILE_SAMPLE_LIMIT = 1000
WORKER_ACTOR_ID = "worker:runner"
PII_HIGH_RISK_TAGS = {"email", "phone", "iban"}
PII_REVIEW_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_WORKER_STEP_TIMEOUT_SECONDS = 300
DEFAULT_WORKER_STEP_MAX_ITEMS = 10_000


@dataclass(frozen=True)
class ProcessedRun:
    """Result metadata for a processed run."""

    run_id: str
    workspace_id: str
    run_type: str
    status: str
    output_refs: dict[str, object]


@dataclass(frozen=True)
class RunStepDefinition:
    """Deterministic run-step node in a run-type DAG."""

    step_key: str
    step_order: int
    depends_on: tuple[str, ...]


class StrictIngestCompletenessError(ValueError):
    """Raised when strict ingest detects incomplete discovery/ingest execution."""

    def __init__(
        self,
        *,
        evidence_bundle_uri: str,
        failure_count: int,
        proposal_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        super().__init__("strict_ingest_completeness_failed")
        self.evidence_bundle_uri = evidence_bundle_uri
        self.failure_count = failure_count
        self.proposal_id = proposal_id
        self.task_id = task_id


RUN_STEP_DEFINITIONS: dict[str, tuple[RunStepDefinition, ...]] = {
    "discover": (
        RunStepDefinition(step_key="discover_inventory", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="ingest_profile_governance",
            step_order=20,
            depends_on=("discover_inventory",),
        ),
        RunStepDefinition(
            step_key="semantic_drift_gate",
            step_order=30,
            depends_on=("ingest_profile_governance",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=40,
            depends_on=("semantic_drift_gate",),
        ),
    ),
    "semantic_bootstrap": (
        RunStepDefinition(step_key="collect_catalog", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="build_manifest_candidate",
            step_order=20,
            depends_on=("collect_catalog",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("build_manifest_candidate",),
        ),
    ),
    "materialize_refresh": (
        RunStepDefinition(step_key="collect_inputs", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="refresh_materializations",
            step_order=20,
            depends_on=("collect_inputs",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("refresh_materializations",),
        ),
    ),
    "TARGET_DB_VALIDATE": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_PROVISION_PLAN": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_PROVISION_APPLY": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_MIGRATION_PLAN": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_MIGRATION_APPLY": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_LOAD_PLAN": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_LOAD_APPLY": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_INDEX_PLAN": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_INDEX_APPLY": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_RLS_PLAN": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_RLS_APPLY": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_SYNC_RUN": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
    "TARGET_DB_ROTATE_CREDENTIALS": (
        RunStepDefinition(step_key="prepare_target_profile", step_order=10, depends_on=()),
        RunStepDefinition(
            step_key="execute_target_operation",
            step_order=20,
            depends_on=("prepare_target_profile",),
        ),
        RunStepDefinition(
            step_key="finalize_output",
            step_order=30,
            depends_on=("execute_target_operation",),
        ),
    ),
}


def process_next_queued_run(
    session: Session,
    *,
    storage_root: str,
    max_active_per_workspace: int = 1,
    strict_ingest: bool = True,
) -> ProcessedRun | None:
    """Process the oldest queued run deterministically."""
    queued = (
        session.execute(
            select(RunRecord).where(RunRecord.status == "queued").order_by(RunRecord.run_id)
        )
        .scalars()
        .all()
    )
    run = None
    workspace_limit = max(max_active_per_workspace, 1)
    for candidate in queued:
        running_count = int(
            session.execute(
                select(func.count())
                .select_from(RunRecord)
                .where(
                    RunRecord.workspace_id == candidate.workspace_id,
                    RunRecord.status == "running",
                )
            ).scalar_one()
        )
        if running_count < workspace_limit:
            run = candidate
            break
    if run is None:
        return None
    return process_run_by_id(
        session,
        run_id=run.run_id,
        storage_root=storage_root,
        strict_ingest=strict_ingest,
    )


def process_run_by_id(
    session: Session, *, run_id: str, storage_root: str, strict_ingest: bool = True
) -> ProcessedRun | None:
    """Process a specific run if it is queued."""
    run = session.get(RunRecord, run_id)
    if run is None:
        return None
    if run.status != "queued":
        return ProcessedRun(
            run_id=run.run_id,
            workspace_id=run.workspace_id,
            run_type=run.run_type,
            status=run.status,
            output_refs=_json_dict(run.output_refs_json),
        )
    return _process_queued_run(
        session,
        run=run,
        storage_root=storage_root,
        strict_ingest=strict_ingest,
    )


def _process_queued_run(
    session: Session, *, run: RunRecord, storage_root: str, strict_ingest: bool
) -> ProcessedRun:
    run.status = "running"
    step_rows = _ensure_run_steps(session, run=run)
    session.flush()
    _append_run_audit_event(
        session,
        workspace_id=run.workspace_id,
        correlation_id=run.run_id,
        event_type="run.started",
        payload={"run_id": run.run_id, "run_type": run.run_type},
    )
    try:
        output_refs = _execute_run(
            session,
            run=run,
            storage_root=storage_root,
            strict_ingest=strict_ingest,
            step_rows=step_rows,
        )
        run.status = "succeeded"
        run.output_refs_json = output_refs
        session.flush()
        _append_run_audit_event(
            session,
            workspace_id=run.workspace_id,
            correlation_id=run.run_id,
            event_type="run.succeeded",
            payload={"run_id": run.run_id, "run_type": run.run_type, "output_refs": output_refs},
        )
        return ProcessedRun(
            run_id=run.run_id,
            workspace_id=run.workspace_id,
            run_type=run.run_type,
            status=run.status,
            output_refs=output_refs,
        )
    except Exception as exc:  # pragma: no cover - branch validated by failure tests
        _ensure_failed_run_step(
            session,
            step_rows=step_rows,
            error_code=_error_code_from_exception(exc),
            details={"error": str(exc), "run_id": run.run_id},
            evidence_bundle_uri=(
                exc.evidence_bundle_uri if isinstance(exc, StrictIngestCompletenessError) else None
            ),
        )
        failure_payload: dict[str, object] = {
            "run_id": run.run_id,
            "run_type": run.run_type,
            "error": str(exc),
        }
        if isinstance(exc, StrictIngestCompletenessError):
            failure_payload["reason"] = "strict_ingest_completeness_failed"
            failure_payload["failure_count"] = exc.failure_count
            failure_payload["evidence_bundle_uri"] = exc.evidence_bundle_uri
            if exc.proposal_id is not None:
                failure_payload["proposal_id"] = exc.proposal_id
            if exc.task_id is not None:
                failure_payload["task_id"] = exc.task_id
        run.status = "failed"
        run.output_refs_json = failure_payload
        session.flush()
        _append_run_audit_event(
            session,
            workspace_id=run.workspace_id,
            correlation_id=run.run_id,
            event_type="run.failed",
            payload=failure_payload,
        )
        return ProcessedRun(
            run_id=run.run_id,
            workspace_id=run.workspace_id,
            run_type=run.run_type,
            status=run.status,
            output_refs=failure_payload,
        )


def _execute_run(
    session: Session,
    *,
    run: RunRecord,
    storage_root: str,
    strict_ingest: bool,
    step_rows: dict[str, RunStepRecord],
) -> dict[str, object]:
    if run.run_type == "discover":
        return _process_discover_run(
            session,
            run=run,
            storage_root=storage_root,
            strict_ingest=strict_ingest,
            step_rows=step_rows,
        )
    if run.run_type == "semantic_bootstrap":
        return _process_semantic_bootstrap_run(
            session,
            run=run,
            storage_root=storage_root,
            step_rows=step_rows,
        )
    if run.run_type == "materialize_refresh":
        return _process_materialized_refresh_run(
            session,
            run=run,
            storage_root=storage_root,
            step_rows=step_rows,
        )
    if run.run_type.startswith("TARGET_DB_"):
        return _process_target_db_lifecycle_run(
            session,
            run=run,
            storage_root=storage_root,
            step_rows=step_rows,
        )
    raise ValueError(f"Unsupported run_type for worker processor: {run.run_type}")


def _process_target_db_lifecycle_run(
    session: Session,
    *,
    run: RunRecord,
    storage_root: str,
    step_rows: dict[str, RunStepRecord],
) -> dict[str, object]:
    _start_step(session, step_rows=step_rows, step_key="prepare_target_profile")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="prepare_target_profile")
    input_refs = _json_dict(run.input_refs_json)
    target_db_id = str(input_refs.get("target_db_id", "")).strip()
    plan_id = str(input_refs.get("plan_id", "")).strip()
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="prepare_target_profile",
        details={
            "target_db_id": target_db_id,
            "plan_id": plan_id or None,
            "run_type": run.run_type,
        },
    )

    _start_step(session, step_rows=step_rows, step_key="execute_target_operation")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="execute_target_operation")
    output = process_target_db_run(
        session,
        run_id=run.run_id,
        run_type=run.run_type,
        workspace_id=run.workspace_id,
        input_refs=input_refs,
        storage_root=storage_root,
    )
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="execute_target_operation",
        details={
            "target_db_id": target_db_id,
            "status": str(output.get("status", "unknown")),
        },
        evidence_bundle_uri=str(output.get("evidence_bundle_uri", "")) or None,
    )

    _start_step(session, step_rows=step_rows, step_key="finalize_output")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="finalize_output")
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="finalize_output",
        details={
            "target_db_id": target_db_id,
            "status": str(output.get("status", "unknown")),
        },
        evidence_bundle_uri=str(output.get("evidence_bundle_uri", "")) or None,
    )
    return output


def _ensure_run_steps(session: Session, *, run: RunRecord) -> dict[str, RunStepRecord]:
    existing_rows = (
        session.execute(
            select(RunStepRecord)
            .where(
                RunStepRecord.workspace_id == run.workspace_id,
                RunStepRecord.run_id == run.run_id,
            )
            .order_by(RunStepRecord.step_order, RunStepRecord.run_step_id)
        )
        .scalars()
        .all()
    )
    if existing_rows:
        return {row.step_key: row for row in existing_rows}
    definitions = RUN_STEP_DEFINITIONS.get(run.run_type, ())
    rows: list[RunStepRecord] = []
    for definition in definitions:
        row = RunStepRecord(
            run_step_id=new_ulid(),
            run_id=run.run_id,
            workspace_id=run.workspace_id,
            run_type=run.run_type,
            step_key=definition.step_key,
            step_order=definition.step_order,
            depends_on_json=list(definition.depends_on),
            status="queued",
            started_epoch=None,
            finished_epoch=None,
            duration_ms=None,
            attempt_count=0,
            error_code=None,
            evidence_bundle_uri=None,
            details_json={},
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return {row.step_key: row for row in rows}


def _start_step(session: Session, *, step_rows: dict[str, RunStepRecord], step_key: str) -> None:
    row = step_rows.get(step_key)
    if row is None:
        return
    row.status = "running"
    row.attempt_count = int(row.attempt_count) + 1
    row.started_epoch = int(time.time())
    row.finished_epoch = None
    row.duration_ms = None
    row.error_code = None
    row.evidence_bundle_uri = None
    row.details_json = {}
    session.flush()


def _succeed_step(
    session: Session,
    *,
    step_rows: dict[str, RunStepRecord],
    step_key: str,
    details: dict[str, object] | None = None,
    evidence_bundle_uri: str | None = None,
) -> None:
    row = step_rows.get(step_key)
    if row is None:
        return
    finished_epoch = int(time.time())
    started_epoch = int(row.started_epoch or finished_epoch)
    row.status = "succeeded"
    row.finished_epoch = finished_epoch
    row.duration_ms = max((finished_epoch - started_epoch) * 1000, 0)
    row.error_code = None
    row.evidence_bundle_uri = evidence_bundle_uri
    row.details_json = dict(details or {})
    observe_worker_step_duration(
        workspace_id=row.workspace_id,
        run_type=row.run_type,
        step_key=row.step_key,
        result="succeeded",
        duration_ms=float(row.duration_ms or 0),
    )
    session.flush()


def _fail_step(
    session: Session,
    *,
    step_rows: dict[str, RunStepRecord],
    step_key: str,
    error_code: str,
    details: dict[str, object] | None = None,
    evidence_bundle_uri: str | None = None,
) -> None:
    row = step_rows.get(step_key)
    if row is None:
        return
    finished_epoch = int(time.time())
    started_epoch = int(row.started_epoch or finished_epoch)
    row.status = "failed"
    row.finished_epoch = finished_epoch
    row.duration_ms = max((finished_epoch - started_epoch) * 1000, 0)
    row.error_code = error_code
    row.evidence_bundle_uri = evidence_bundle_uri
    row.details_json = dict(details or {})
    observe_worker_step_duration(
        workspace_id=row.workspace_id,
        run_type=row.run_type,
        step_key=row.step_key,
        result="failed",
        duration_ms=float(row.duration_ms or 0),
    )
    session.flush()


def _ensure_failed_run_step(
    session: Session,
    *,
    step_rows: dict[str, RunStepRecord],
    error_code: str,
    details: dict[str, object],
    evidence_bundle_uri: str | None,
) -> None:
    if not step_rows:
        return
    if any(row.status == "failed" for row in step_rows.values()):
        return
    running = next((row for row in step_rows.values() if row.status == "running"), None)
    if running is None:
        running = sorted(
            step_rows.values(),
            key=lambda row: (int(row.step_order), str(row.run_step_id)),
        )[0]
    _fail_step(
        session,
        step_rows=step_rows,
        step_key=running.step_key,
        error_code=error_code,
        details=details,
        evidence_bundle_uri=evidence_bundle_uri,
    )


def _error_code_from_exception(exc: Exception) -> str:
    if isinstance(exc, StrictIngestCompletenessError):
        return "strict_ingest_completeness_failed"
    if isinstance(exc, ValueError):
        raw = str(exc).strip().lower().replace(" ", "_")
        normalized = re.sub(r"[^a-z0-9_]+", "_", raw).strip("_")
        if normalized:
            return normalized[:80]
    return exc.__class__.__name__.lower()


def _process_semantic_bootstrap_run(
    session: Session,
    *,
    run: RunRecord,
    storage_root: str,
    step_rows: dict[str, RunStepRecord],
) -> dict[str, object]:
    _start_step(session, step_rows=step_rows, step_key="collect_catalog")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="collect_catalog")
    dataset_ids = sorted(
        session.execute(
            select(CatalogDataset.dataset_id).where(CatalogDataset.workspace_id == run.workspace_id)
        )
        .scalars()
        .all()
    )
    run.input_refs_json = {
        "dataset_ids": dataset_ids,
        "dataset_count": len(dataset_ids),
    }
    session.flush()
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="collect_catalog",
        details={"dataset_count": len(dataset_ids)},
    )

    _start_step(session, step_rows=step_rows, step_key="build_manifest_candidate")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="build_manifest_candidate")
    candidate = build_semantic_manifest_candidate(
        session,
        workspace_id=run.workspace_id,
        storage_root=storage_root,
    )
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="build_manifest_candidate",
        details={
            "entity_count": _coerce_int(candidate.get("entity_count"), default=0),
            "metric_count": _coerce_int(candidate.get("metric_count"), default=0),
            "join_count": _coerce_int(candidate.get("join_count"), default=0),
        },
        evidence_bundle_uri=str(candidate.get("evidence_bundle_uri", "")) or None,
    )
    manifest = candidate.get("semantic_manifest", {})
    manifest_version = ""
    if isinstance(manifest, dict):
        manifest_version = str(manifest.get("manifest_version", ""))
    output = {
        "dataset_ids": dataset_ids,
        "dataset_count": len(dataset_ids),
        "manifest_version": manifest_version,
        "manifest_checksum": candidate["manifest_checksum"],
        "evidence_bundle_uri": candidate["evidence_bundle_uri"],
        "confidence": candidate["confidence"],
        "confidence_flag_count": candidate["confidence_flag_count"],
        "proposal_id": candidate["proposal_id"],
        "task_id": candidate["task_id"],
        "entity_count": candidate["entity_count"],
        "metric_count": candidate["metric_count"],
        "join_count": candidate["join_count"],
    }
    _start_step(session, step_rows=step_rows, step_key="finalize_output")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="finalize_output")
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="finalize_output",
        details={
            "manifest_version": manifest_version,
            "dataset_count": len(dataset_ids),
        },
        evidence_bundle_uri=str(candidate.get("evidence_bundle_uri", "")) or None,
    )
    return output


def _process_discover_run(
    session: Session,
    *,
    run: RunRecord,
    storage_root: str,
    strict_ingest: bool,
    step_rows: dict[str, RunStepRecord],
) -> dict[str, object]:
    _start_step(session, step_rows=step_rows, step_key="discover_inventory")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="discover_inventory")
    sources = (
        session.execute(
            select(CatalogSource)
            .where(
                CatalogSource.workspace_id == run.workspace_id,
                CatalogSource.status == "active",
            )
            .order_by(CatalogSource.source_id)
        )
        .scalars()
        .all()
    )
    if not sources:
        raise ValueError("Discover run requires at least one active source.")

    run.input_refs_json = {
        "source_ids": [source.source_id for source in sources],
        "source_count": len(sources),
    }
    session.flush()
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="discover_inventory",
        details={"source_count": len(sources)},
    )

    _start_step(session, step_rows=step_rows, step_key="ingest_profile_governance")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="ingest_profile_governance")
    dataset_ids: set[str] = set()
    artifact_manifests: list[dict[str, object]] = []
    source_snapshot_manifests: list[dict[str, object]] = []
    evidence_bundles: list[dict[str, object]] = []
    completeness_expected_items: list[dict[str, object]] = []
    completeness_failures: list[dict[str, object]] = []
    successful_item_count = 0
    pii_blocking_tasks_created = 0
    drift_blocking_tasks_created = 0
    semantic_drift_blocking_tasks_created = 0
    anomaly_blocking_tasks_created = 0
    connector_plugins = load_connector_plugin_specs()

    for source in sources:
        scope = _json_dict(source.scope_json)
        state = load_connector_state(
            storage_root=storage_root,
            workspace_id=run.workspace_id,
            source_id=source.source_id,
        )
        try:
            if source.source_type == "filesystem":
                root_path = str(scope.get("root_path", "")).strip()
                if not root_path:
                    raise ValueError(f"Filesystem source {source.source_id} is missing root_path.")
                include_globs = _string_list(
                    scope.get("include_globs"),
                    default=DEFAULT_INCLUDE_GLOBS,
                )
                exclude_globs = _string_list(scope.get("exclude_globs"), default=[])
                discovered_files = discover_files(
                    root_path=root_path,
                    include_globs=include_globs,
                    exclude_globs=exclude_globs,
                )
            elif source.source_type == "dropzone":
                root_path = str(scope.get("root_path", "")).strip()
                if not root_path:
                    raise ValueError(f"Dropzone source {source.source_id} is missing root_path.")
                include_globs = _string_list(scope.get("include_globs"), default=[])
                exclude_globs = _string_list(scope.get("exclude_globs"), default=[])
                required_files = _string_list(scope.get("required_files"), default=[])
                discovered_files = discover_dropzone_files(
                    root_path=root_path,
                    include_globs=include_globs or None,
                    exclude_globs=exclude_globs or None,
                    required_files=required_files or None,
                )
            elif source.source_type == "db_dump":
                root_path = str(scope.get("root_path", "")).strip()
                if not root_path:
                    raise ValueError(f"DB dump source {source.source_id} is missing root_path.")
                discovered_files = [
                    DiscoveredFile(
                        path=str(row.get("path", "")),
                        dataset_family=str(row.get("dataset_family", "db_dump")),
                        size_bytes=_coerce_int(row.get("size_bytes", 0), default=0),
                        mtime_epoch=_coerce_float(row.get("mtime_epoch", 0.0), default=0.0),
                        content_hash_sample=str(row.get("content_hash_sample", "")),
                    )
                    for row in discover_db_dumps(scope)
                ]
            elif source.source_type == "jira":
                root_path = str(scope.get("root_path", "")).strip()
                if not root_path:
                    raise ValueError(f"Jira source {source.source_id} is missing root_path.")
                discovered_files = [
                    DiscoveredFile(
                        path=str(row.get("path", "")),
                        dataset_family=str(row.get("dataset_family", "jira")),
                        size_bytes=_coerce_int(row.get("size_bytes", 0), default=0),
                        mtime_epoch=_coerce_float(row.get("mtime_epoch", 0.0), default=0.0),
                        content_hash_sample=str(row.get("content_hash_sample", "")),
                    )
                    for row in discover_jira_exports(scope)
                ]
            elif source.source_type == "zendesk":
                root_path = str(scope.get("root_path", "")).strip()
                if not root_path:
                    raise ValueError(f"Zendesk source {source.source_id} is missing root_path.")
                discovered_files = [
                    DiscoveredFile(
                        path=str(row.get("path", "")),
                        dataset_family=str(row.get("dataset_family", "zendesk")),
                        size_bytes=_coerce_int(row.get("size_bytes", 0), default=0),
                        mtime_epoch=_coerce_float(row.get("mtime_epoch", 0.0), default=0.0),
                        content_hash_sample=str(row.get("content_hash_sample", "")),
                    )
                    for row in discover_zendesk_exports(scope)
                ]
            else:
                plugin = connector_plugins.get(source.source_type)
                if plugin is None:
                    raise ValueError(
                        f"Unsupported source_type for discover run: {source.source_type}"
                    )
                root_path = str(scope.get("root_path", "")).strip() or "."
                plugin_scope = dict(scope)
                plugin_scope["cursor_state"] = state
                discovered_files = _discover_files_via_plugin(
                    plugin,
                    scope=plugin_scope,
                    source_type=source.source_type,
                )
        except Exception as exc:
            completeness_failures.append(
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type,
                    "stage": "discovery",
                    "error": str(exc),
                }
            )
            continue
        next_cursor = next_cursor_from_discovery_rows(
            [{"path": item.path, "mtime_epoch": item.mtime_epoch} for item in discovered_files],
            previous_cursor=str(state.get("cursor", "")),
        )
        source_snapshot = build_source_snapshot_manifest(
            workspace_id=run.workspace_id,
            source_id=source.source_id,
            source_type=source.source_type,
            root_path=root_path,
            cursor_before=str(state.get("cursor", "")),
            cursor_after=next_cursor,
            rows=[
                {
                    "path": _relative_locator(root_path=root_path, path=item.path),
                    "size_bytes": item.size_bytes,
                    "mtime_epoch": item.mtime_epoch,
                    "content_hash_sample": item.content_hash_sample,
                    "dataset_family": item.dataset_family,
                }
                for item in discovered_files
            ],
            strict_mode=strict_ingest,
        )
        source_snapshot_materialized = persist_source_snapshot_manifest(
            storage_root=storage_root,
            manifest=source_snapshot,
        )
        source_snapshot_manifests.append(
            {
                "source_id": source.source_id,
                "source_type": source.source_type,
                "snapshot_checksum": source_snapshot_materialized["snapshot_checksum"],
                "snapshot_uri": source_snapshot_materialized["snapshot_uri"],
                "entry_count": _coerce_int(source_snapshot.get("entry_count"), default=0),
            }
        )
        if len(discovered_files) > _worker_step_max_items():
            raise ValueError("worker_step_item_quota_exceeded")
        connector_state_payload: dict[str, object] = {
            "cursor": next_cursor,
            "source_type": source.source_type,
            "last_discovered_count": len(discovered_files),
        }
        if source.source_type == "sharepoint":
            connector_state_payload["delta_cursor"] = next_cursor
        save_connector_state(
            storage_root=storage_root,
            workspace_id=run.workspace_id,
            source_id=source.source_id,
            state=connector_state_payload,
        )
        for discovered in discovered_files:
            _enforce_worker_step_timeout(step_rows=step_rows, step_key="ingest_profile_governance")
            physical_locator = _relative_locator(root_path=root_path, path=discovered.path)
            completeness_expected_items.append(
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type,
                    "path": discovered.path,
                    "physical_locator": physical_locator,
                }
            )
            try:
                logical_name = discovered.dataset_family or Path(physical_locator).stem
                dataset = _upsert_catalog_dataset(
                    session,
                    workspace_id=run.workspace_id,
                    source_id=source.source_id,
                    physical_locator=physical_locator,
                    logical_name=logical_name,
                )
                dataset_ids.add(dataset.dataset_id)

                bronze_result = ingest_file_to_bronze(
                    workspace_id=run.workspace_id,
                    source_id=source.source_id,
                    dataset_id=dataset.dataset_id,
                    source_file=discovered.path,
                    storage_root=storage_root,
                    run_id=run.run_id,
                )
                artifact_manifests.append(
                    {
                        "dataset_id": dataset.dataset_id,
                        "artifact_id": bronze_result.artifact_id,
                        "manifest_path": bronze_result.manifest_path,
                    }
                )

                if discovered.path.lower().endswith(".csv"):
                    evidence = profile_csv_file(discovered.path, sample_limit=PROFILE_SAMPLE_LIMIT)
                    previous_summary = _json_dict(dataset.sensitivity_summary_json)
                    previous_profile = previous_summary.get("profile", {})
                    previous_columns = (
                        [
                            str(column)
                            for column in previous_profile.get("schema_columns", [])
                            if isinstance(column, (str, int, float))
                        ]
                        if isinstance(previous_profile, dict)
                        else []
                    )
                    stored_evidence = store_evidence_bundle(
                        workspace_id=run.workspace_id,
                        storage_root=storage_root,
                        bundle_type="profile",
                        payload={
                            "dataset_id": dataset.dataset_id,
                            "source_id": source.source_id,
                            "physical_locator": physical_locator,
                            "profile": evidence.to_dict(),
                        },
                    )
                    summary = previous_summary
                    summary["profile"] = {
                        "row_count_sampled": evidence.row_count_sampled,
                        "parse_error_rate": evidence.parse_error_rate,
                        "schema_columns": evidence.schema_columns,
                        "last_profile_epoch": int(time.time()),
                    }
                    summary["last_evidence_bundle_uri"] = stored_evidence.evidence_bundle_uri
                    summary["last_evidence_content_hash"] = stored_evidence.content_hash
                    dataset.sensitivity_summary_json = summary
                    evidence_bundles.append(
                        {
                            "dataset_id": dataset.dataset_id,
                            "evidence_bundle_uri": stored_evidence.evidence_bundle_uri,
                            "content_hash": stored_evidence.content_hash,
                            "evidence_path": stored_evidence.path,
                            "row_count_sampled": evidence.row_count_sampled,
                        }
                    )
                    pii_blocking_tasks_created += _create_pii_review_tasks_from_csv(
                        session,
                        workspace_id=run.workspace_id,
                        dataset_id=dataset.dataset_id,
                        source_id=source.source_id,
                        csv_path=discovered.path,
                        physical_locator=physical_locator,
                        storage_root=storage_root,
                    )
                    drift_blocking_tasks_created += _create_drift_review_task_if_needed(
                        session,
                        workspace_id=run.workspace_id,
                        dataset_id=dataset.dataset_id,
                        source_id=source.source_id,
                        physical_locator=physical_locator,
                        previous_columns=previous_columns,
                        current_columns=evidence.schema_columns,
                        storage_root=storage_root,
                    )
                    anomaly_blocking_tasks_created += _create_anomaly_review_task_if_needed(
                        session=session,
                        workspace_id=run.workspace_id,
                        dataset_id=dataset.dataset_id,
                        source_id=source.source_id,
                        physical_locator=physical_locator,
                        profile=evidence.to_dict(),
                        storage_root=storage_root,
                    )
                    session.flush()
                successful_item_count += 1
                if successful_item_count > _worker_step_max_items():
                    raise ValueError("worker_step_item_quota_exceeded")
            except Exception as exc:
                if str(exc) in {
                    "worker_step_item_quota_exceeded",
                    "worker_step_timeout_exceeded",
                }:
                    raise
                completeness_failures.append(
                    {
                        "source_id": source.source_id,
                        "source_type": source.source_type,
                        "path": discovered.path,
                        "physical_locator": physical_locator,
                        "stage": "ingest_profile",
                        "error": str(exc),
                    }
                )

    sorted_dataset_ids = sorted(dataset_ids)
    if completeness_failures:
        completeness_payload = {
            "workspace_id": run.workspace_id,
            "run_id": run.run_id,
            "strict_mode": strict_ingest,
            "expected_items": sorted(
                completeness_expected_items,
                key=lambda row: (
                    str(row.get("source_id")),
                    str(row.get("physical_locator")),
                ),
            ),
            "failure_count": len(completeness_failures),
            "success_count": successful_item_count,
            "failures": sorted(
                completeness_failures,
                key=lambda row: (
                    str(row.get("source_id")),
                    str(row.get("stage")),
                    str(row.get("physical_locator", row.get("path", ""))),
                ),
            ),
        }
        if strict_ingest:
            stored_failure = store_evidence_bundle(
                workspace_id=run.workspace_id,
                storage_root=storage_root,
                bundle_type="ingest_completeness_failure",
                payload=completeness_payload,
            )
            failure_task = _ensure_ingest_completeness_review_task(
                session=session,
                workspace_id=run.workspace_id,
                evidence_bundle_uri=stored_failure.evidence_bundle_uri,
            )
            _fail_step(
                session,
                step_rows=step_rows,
                step_key="ingest_profile_governance",
                error_code="strict_ingest_completeness_failed",
                evidence_bundle_uri=stored_failure.evidence_bundle_uri,
                details={
                    "failure_count": len(completeness_failures),
                    "success_count": successful_item_count,
                },
            )
            raise StrictIngestCompletenessError(
                evidence_bundle_uri=stored_failure.evidence_bundle_uri,
                failure_count=len(completeness_failures),
                proposal_id=str(failure_task["proposal_id"]),
                task_id=str(failure_task["task_id"]),
            )
        stored_warning = store_evidence_bundle(
            workspace_id=run.workspace_id,
            storage_root=storage_root,
            bundle_type="ingest_completeness_warning",
            payload=completeness_payload,
        )
    else:
        stored_warning = None
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="ingest_profile_governance",
        details={
            "processed_item_count": successful_item_count,
            "expected_item_count": len(completeness_expected_items),
            "failure_count": len(completeness_failures),
            "dataset_count": len(sorted_dataset_ids),
        },
        evidence_bundle_uri=(
            stored_warning.evidence_bundle_uri if stored_warning is not None else None
        ),
    )

    _start_step(session, step_rows=step_rows, step_key="semantic_drift_gate")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="semantic_drift_gate")
    semantic_drift_blocking_tasks_created += _create_semantic_drift_review_task_if_needed(
        session=session,
        workspace_id=run.workspace_id,
        storage_root=storage_root,
    )
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="semantic_drift_gate",
        details={"semantic_drift_blocking_tasks_created": semantic_drift_blocking_tasks_created},
    )

    _start_step(session, step_rows=step_rows, step_key="finalize_output")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="finalize_output")
    output = {
        "source_ids": [source.source_id for source in sources],
        "dataset_ids": sorted_dataset_ids,
        "dataset_count": len(sorted_dataset_ids),
        "strict_ingest": strict_ingest,
        "pii_blocking_tasks_created": pii_blocking_tasks_created,
        "drift_blocking_tasks_created": drift_blocking_tasks_created,
        "semantic_drift_blocking_tasks_created": semantic_drift_blocking_tasks_created,
        "anomaly_blocking_tasks_created": anomaly_blocking_tasks_created,
        "expected_item_count": len(completeness_expected_items),
        "processed_item_count": successful_item_count,
        "completeness_failure_count": len(completeness_failures),
        "completeness_warning_evidence_uri": (
            stored_warning.evidence_bundle_uri if stored_warning is not None else None
        ),
        "artifact_manifests": sorted(
            artifact_manifests,
            key=lambda row: (str(row.get("dataset_id")), str(row.get("artifact_id"))),
        ),
        "source_snapshot_manifests": sorted(
            source_snapshot_manifests,
            key=lambda row: (str(row.get("source_id")), str(row.get("snapshot_checksum"))),
        ),
        "evidence_bundles": sorted(
            evidence_bundles,
            key=lambda row: (
                str(row.get("dataset_id")),
                str(row.get("evidence_bundle_uri")),
            ),
        ),
    }
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="finalize_output",
        details={
            "dataset_count": len(sorted_dataset_ids),
            "processed_item_count": successful_item_count,
            "completeness_failure_count": len(completeness_failures),
        },
        evidence_bundle_uri=(
            stored_warning.evidence_bundle_uri if stored_warning is not None else None
        ),
    )
    return output


def _process_materialized_refresh_run(
    session: Session,
    *,
    run: RunRecord,
    storage_root: str,
    step_rows: dict[str, RunStepRecord],
) -> dict[str, object]:
    if not _materialized_refresh_enabled():
        raise ValueError("materialized_refresh_disabled")
    _start_step(session, step_rows=step_rows, step_key="collect_inputs")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="collect_inputs")
    datasets = (
        session.execute(
            select(CatalogDataset).where(CatalogDataset.workspace_id == run.workspace_id)
        )
        .scalars()
        .all()
    )
    dataset_ids = sorted(dataset.dataset_id for dataset in datasets)
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="collect_inputs",
        details={"dataset_count": len(dataset_ids)},
    )

    _start_step(session, step_rows=step_rows, step_key="refresh_materializations")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="refresh_materializations")
    snapshot_dir = Path(storage_root) / "materialized" / run.workspace_id / "snapshots" / new_ulid()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_payload = {
        "workspace_id": run.workspace_id,
        "run_id": run.run_id,
        "run_type": run.run_type,
        "dataset_ids": dataset_ids,
        "dataset_count": len(dataset_ids),
        "refreshed_epoch": int(time.time()),
    }
    snapshot_path = snapshot_dir / "refresh.json"
    snapshot_path.write_text(
        json.dumps(snapshot_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="refresh_materializations",
        details={"snapshot_path": snapshot_path.as_posix(), "dataset_count": len(dataset_ids)},
    )

    _start_step(session, step_rows=step_rows, step_key="finalize_output")
    _enforce_worker_step_timeout(step_rows=step_rows, step_key="finalize_output")
    output = {
        "materialized_snapshot_path": snapshot_path.as_posix(),
        "dataset_ids": dataset_ids,
        "dataset_count": len(dataset_ids),
    }
    _succeed_step(
        session,
        step_rows=step_rows,
        step_key="finalize_output",
        details={"dataset_count": len(dataset_ids)},
    )
    return output


def _discover_files_via_plugin(
    plugin_spec: ConnectorPluginSpec,
    *,
    scope: dict[str, object],
    source_type: str,
) -> list[DiscoveredFile]:
    raw = execute_connector_plugin(plugin_spec=plugin_spec, scope=scope)
    if not isinstance(raw, list):
        raise ValueError(f"Connector plugin '{source_type}' must return a list of discovery rows.")
    discovered: list[DiscoveredFile] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path", "")).strip()
        if not path:
            continue
        size_raw = row.get("size_bytes", 0)
        mtime_raw = row.get("mtime_epoch", 0.0)
        size_bytes = int(size_raw) if isinstance(size_raw, (int, float, str)) else 0
        mtime_epoch = float(mtime_raw) if isinstance(mtime_raw, (int, float, str)) else 0.0
        discovered.append(
            DiscoveredFile(
                path=path,
                size_bytes=size_bytes,
                mtime_epoch=mtime_epoch,
                content_hash_sample=str(row.get("content_hash_sample", "")),
                dataset_family=str(row.get("dataset_family", Path(path).stem)),
            )
        )
    return sorted(discovered, key=lambda item: item.path)


def _create_pii_review_tasks_from_csv(
    session: Session,
    *,
    workspace_id: str,
    dataset_id: str,
    source_id: str,
    csv_path: str,
    physical_locator: str,
    storage_root: str,
) -> int:
    samples_by_column = _read_csv_column_samples(csv_path, sample_limit=PROFILE_SAMPLE_LIMIT)
    created_count = 0
    for column_name in sorted(samples_by_column):
        detection = detect_pii_proposals(column_name, samples_by_column[column_name])
        tag = str(detection.get("tag", "none"))
        confidence_raw = detection.get("confidence", 0.0)
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float, str)) else 0.0
        if tag not in PII_HIGH_RISK_TAGS or confidence < PII_REVIEW_CONFIDENCE_THRESHOLD:
            continue
        stored = store_evidence_bundle(
            workspace_id=workspace_id,
            storage_root=storage_root,
            bundle_type="pii",
            payload={
                "dataset_id": dataset_id,
                "source_id": source_id,
                "physical_locator": physical_locator,
                "column_name": column_name,
                "tag": tag,
                "confidence": confidence,
                "evidence": detection.get("evidence", {}),
            },
        )
        proposal = _get_or_create_review_proposal(
            session,
            workspace_id=workspace_id,
            proposal_type="pii_tag_proposal",
            evidence_bundle_uri=stored.evidence_bundle_uri,
            confidence=confidence,
        )
        if _create_blocking_review_task_if_missing(
            session,
            workspace_id=workspace_id,
            proposal_id=proposal.proposal_id,
            priority="security_critical",
        ):
            created_count += 1
    return created_count


def _create_drift_review_task_if_needed(
    session: Session,
    *,
    workspace_id: str,
    dataset_id: str,
    source_id: str,
    physical_locator: str,
    previous_columns: list[str],
    current_columns: list[str],
    storage_root: str,
) -> int:
    if not previous_columns:
        return 0
    drift_event = detect_schema_drift(
        previous_columns=previous_columns,
        current_columns=current_columns,
    )
    if not bool(drift_event.get("drift_detected", False)):
        return 0
    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=storage_root,
        bundle_type="drift",
        payload={
            "dataset_id": dataset_id,
            "source_id": source_id,
            "physical_locator": physical_locator,
            "previous_columns": previous_columns,
            "current_columns": current_columns,
            "drift": drift_event,
        },
    )
    proposal = _get_or_create_review_proposal(
        session,
        workspace_id=workspace_id,
        proposal_type="drift_proposal",
        evidence_bundle_uri=stored.evidence_bundle_uri,
        confidence=1.0,
    )
    created = _create_blocking_review_task_if_missing(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal.proposal_id,
        priority="quality_critical",
    )
    return 1 if created else 0


def _create_semantic_drift_review_task_if_needed(
    session: Session,
    *,
    workspace_id: str,
    storage_root: str,
) -> int:
    semantic_policy = (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == "semantic_manifest",
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .first()
    )
    if semantic_policy is None:
        return 0
    try:
        payload = json.loads(semantic_policy.definition_ref)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    manifest = payload.get("semantic_manifest", {})
    if not isinstance(manifest, dict):
        return 0
    datasets = (
        session.execute(select(CatalogDataset).where(CatalogDataset.workspace_id == workspace_id))
        .scalars()
        .all()
    )
    available_columns_by_dataset: dict[str, set[str]] = {}
    for dataset in datasets:
        summary = _json_dict(dataset.sensitivity_summary_json)
        profile = summary.get("profile", {})
        if not isinstance(profile, dict):
            continue
        columns_raw = profile.get("schema_columns", [])
        if not isinstance(columns_raw, list):
            continue
        available_columns_by_dataset[dataset.dataset_id] = {
            str(column).lower() for column in columns_raw if str(column).strip()
        }
    if not available_columns_by_dataset:
        return 0
    drift = detect_semantic_manifest_drift(
        semantic_manifest=manifest,
        available_columns_by_dataset=available_columns_by_dataset,
    )
    if not bool(drift.get("drift_detected", False)):
        return 0
    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=storage_root,
        bundle_type="semantic_drift",
        payload={
            "workspace_id": workspace_id,
            "drift": drift,
            "available_columns_by_dataset": {
                dataset_id: sorted(columns)
                for dataset_id, columns in sorted(available_columns_by_dataset.items())
            },
        },
    )
    proposal = _get_or_create_review_proposal(
        session,
        workspace_id=workspace_id,
        proposal_type="semantic_drift_proposal",
        evidence_bundle_uri=stored.evidence_bundle_uri,
        confidence=1.0,
    )
    created = _create_blocking_review_task_if_missing(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal.proposal_id,
        priority="quality_critical",
    )
    return 1 if created else 0


def _create_anomaly_review_task_if_needed(
    session: Session,
    *,
    workspace_id: str,
    dataset_id: str,
    source_id: str,
    physical_locator: str,
    profile: dict[str, object],
    storage_root: str,
) -> int:
    anomalies = detect_profile_anomalies(profile)
    if not anomalies:
        return 0
    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=storage_root,
        bundle_type="anomaly_detection",
        payload={
            "dataset_id": dataset_id,
            "source_id": source_id,
            "physical_locator": physical_locator,
            "profile": profile,
            "anomalies": anomalies,
        },
    )
    proposal = _get_or_create_review_proposal(
        session,
        workspace_id=workspace_id,
        proposal_type="anomaly_detection_proposal",
        evidence_bundle_uri=stored.evidence_bundle_uri,
        confidence=1.0,
    )
    created = _create_blocking_review_task_if_missing(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal.proposal_id,
        priority="quality_critical",
    )
    return 1 if created else 0


def _read_csv_column_samples(path: str, *, sample_limit: int) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = [str(column) for column in (reader.fieldnames or [])]
        for column in columns:
            samples[column] = []
        row_count = 0
        for row in reader:
            if row_count >= sample_limit:
                break
            row_count += 1
            for column in columns:
                value = (row.get(column) or "").strip()
                if value:
                    samples[column].append(value)
    return samples


def _get_or_create_review_proposal(
    session: Session,
    *,
    workspace_id: str,
    proposal_type: str,
    evidence_bundle_uri: str,
    confidence: float,
) -> ReviewProposal:
    existing = (
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
    if existing is not None:
        return existing
    proposal = ReviewProposal(
        proposal_id=new_ulid(),
        workspace_id=workspace_id,
        proposal_type=proposal_type,
        evidence_bundle_uri=evidence_bundle_uri,
        confidence=confidence,
        status="open",
    )
    session.add(proposal)
    session.flush()
    return proposal


def _create_blocking_review_task_if_missing(
    session: Session, *, workspace_id: str, proposal_id: str, priority: str
) -> bool:
    existing = (
        session.execute(
            select(ReviewTask).where(
                ReviewTask.workspace_id == workspace_id,
                ReviewTask.subject_ref == proposal_id,
                ReviewTask.priority == priority,
                ReviewTask.blocking.is_(True),
                ReviewTask.status.in_(("open", "in_review")),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return False
    session.add(
        ReviewTask(
            task_id=new_ulid(),
            workspace_id=workspace_id,
            priority=priority,
            subject_ref=proposal_id,
            status="open",
            blocking=True,
        )
    )
    session.flush()
    return True


def _ensure_ingest_completeness_review_task(
    session: Session,
    *,
    workspace_id: str,
    evidence_bundle_uri: str,
) -> dict[str, str]:
    proposal = _get_or_create_review_proposal(
        session,
        workspace_id=workspace_id,
        proposal_type="ingest_completeness_proposal",
        evidence_bundle_uri=evidence_bundle_uri,
        confidence=1.0,
    )
    existing = (
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
    if existing is not None:
        return {"proposal_id": proposal.proposal_id, "task_id": existing.task_id}
    task = ReviewTask(
        task_id=new_ulid(),
        workspace_id=workspace_id,
        priority="quality_critical",
        subject_ref=proposal.proposal_id,
        status="open",
        blocking=True,
    )
    session.add(task)
    session.flush()
    return {"proposal_id": proposal.proposal_id, "task_id": task.task_id}


def _upsert_catalog_dataset(
    session: Session,
    *,
    workspace_id: str,
    source_id: str,
    physical_locator: str,
    logical_name: str,
) -> CatalogDataset:
    existing = (
        session.execute(
            select(CatalogDataset).where(
                CatalogDataset.workspace_id == workspace_id,
                CatalogDataset.source_id == source_id,
                CatalogDataset.physical_locator == physical_locator,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        existing.logical_name = logical_name
        return existing

    dataset_id = _stable_dataset_id(
        workspace_id=workspace_id,
        source_id=source_id,
        physical_locator=physical_locator,
    )
    collision = session.get(CatalogDataset, dataset_id)
    if collision is not None and (
        collision.workspace_id != workspace_id
        or collision.source_id != source_id
        or collision.physical_locator != physical_locator
    ):
        raise ValueError(f"Deterministic dataset id collision for locator {physical_locator}.")

    if collision is not None:
        collision.logical_name = logical_name
        return collision

    created = CatalogDataset(
        dataset_id=dataset_id,
        workspace_id=workspace_id,
        source_id=source_id,
        logical_name=logical_name,
        physical_locator=physical_locator,
        schema_version=1,
        sensitivity_summary_json={"classification": "unknown"},
    )
    session.add(created)
    session.flush()
    return created


def _stable_dataset_id(*, workspace_id: str, source_id: str, physical_locator: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"schemapilot://dataset/{workspace_id}/{source_id}/{physical_locator}",
        )
    )


def _relative_locator(*, root_path: str, path: str) -> str:
    root = Path(root_path).resolve()
    target = Path(path).resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return target.as_posix()


def _string_list(value: object, *, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    parsed = [str(item) for item in value if str(item).strip()]
    return parsed if parsed else list(default)


def _worker_step_max_items() -> int:
    return _env_int("SCHEMAPILOT_WORKER_STEP_MAX_ITEMS", DEFAULT_WORKER_STEP_MAX_ITEMS)


def _worker_step_timeout_seconds() -> int:
    return _env_int("SCHEMAPILOT_WORKER_STEP_TIMEOUT_SECONDS", DEFAULT_WORKER_STEP_TIMEOUT_SECONDS)


def _materialized_refresh_enabled() -> bool:
    raw = os.getenv("SCHEMAPILOT_MATERIALIZED_REFRESH_ENABLED")
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _enforce_worker_step_timeout(*, step_rows: dict[str, RunStepRecord], step_key: str) -> None:
    row = step_rows.get(step_key)
    if row is None:
        return
    started = int(row.started_epoch or int(time.time()))
    elapsed = int(time.time()) - started
    if elapsed > _worker_step_timeout_seconds():
        raise ValueError("worker_step_timeout_exceeded")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _coerce_int(value: object, *, default: int) -> int:
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


def _coerce_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _json_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    return {}


def _append_run_audit_event(
    session: Session,
    *,
    workspace_id: str,
    correlation_id: str,
    event_type: str,
    payload: dict[str, object],
) -> None:
    session.add(
        AuditEvent(
            audit_event_id=new_ulid(),
            workspace_id=workspace_id,
            actor_id=WORKER_ACTOR_ID,
            event_type=event_type,
            event_json=payload,
            correlation_id=correlation_id,
        )
    )
    session.flush()
