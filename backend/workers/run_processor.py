"""Deterministic queued-run processing for worker services."""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.evidence_store import store_evidence_bundle
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import (
    CatalogDataset,
    CatalogSource,
    ReviewProposal,
    ReviewTask,
    RunRecord,
)
from backend.shared_domain.plugin_loader import ConnectorPluginSpec, load_connector_plugin_specs
from backend.workers.bronze import ingest_file_to_bronze
from backend.workers.connectors.filesystem import DiscoveredFile, discover_files
from backend.workers.connectors.plugin_runner import execute_connector_plugin
from backend.workers.drift import detect_schema_drift
from backend.workers.pii import detect_pii_proposals
from backend.workers.profiler import profile_csv_file

DEFAULT_INCLUDE_GLOBS = ["**/*.csv"]
PROFILE_SAMPLE_LIMIT = 1000
WORKER_ACTOR_ID = "worker:runner"
PII_HIGH_RISK_TAGS = {"email", "phone", "iban"}
PII_REVIEW_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True)
class ProcessedRun:
    """Result metadata for a processed run."""

    run_id: str
    workspace_id: str
    run_type: str
    status: str
    output_refs: dict[str, object]


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


def process_next_queued_run(
    session: Session, *, storage_root: str, strict_ingest: bool = True
) -> ProcessedRun | None:
    """Process the oldest queued run deterministically."""
    run = (
        session.execute(
            select(RunRecord)
            .where(RunRecord.status == "queued")
            .order_by(RunRecord.run_id)
            .limit(1)
        )
        .scalars()
        .first()
    )
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
    session: Session, *, run: RunRecord, storage_root: str, strict_ingest: bool
) -> dict[str, object]:
    if run.run_type == "discover":
        return _process_discover_run(
            session,
            run=run,
            storage_root=storage_root,
            strict_ingest=strict_ingest,
        )
    raise ValueError(f"Unsupported run_type for worker processor: {run.run_type}")


def _process_discover_run(
    session: Session,
    *,
    run: RunRecord,
    storage_root: str,
    strict_ingest: bool,
) -> dict[str, object]:
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

    dataset_ids: set[str] = set()
    artifact_manifests: list[dict[str, object]] = []
    evidence_bundles: list[dict[str, object]] = []
    completeness_expected_items: list[dict[str, object]] = []
    completeness_failures: list[dict[str, object]] = []
    successful_item_count = 0
    pii_blocking_tasks_created = 0
    drift_blocking_tasks_created = 0
    connector_plugins = load_connector_plugin_specs()

    for source in sources:
        scope = _json_dict(source.scope_json)
        try:
            if source.source_type == "filesystem":
                root_path = str(scope.get("root_path", "")).strip()
                if not root_path:
                    raise ValueError(
                        f"Filesystem source {source.source_id} is missing root_path."
                    )
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
            else:
                plugin = connector_plugins.get(source.source_type)
                if plugin is None:
                    raise ValueError(
                        f"Unsupported source_type for discover run: {source.source_type}"
                    )
                root_path = str(scope.get("root_path", "")).strip() or "."
                discovered_files = _discover_files_via_plugin(
                    plugin,
                    scope=scope,
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
        for discovered in discovered_files:
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
                    session.flush()
                successful_item_count += 1
            except Exception as exc:
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

    return {
        "source_ids": [source.source_id for source in sources],
        "dataset_ids": sorted_dataset_ids,
        "dataset_count": len(sorted_dataset_ids),
        "strict_ingest": strict_ingest,
        "pii_blocking_tasks_created": pii_blocking_tasks_created,
        "drift_blocking_tasks_created": drift_blocking_tasks_created,
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
        "evidence_bundles": sorted(
            evidence_bundles,
            key=lambda row: (
                str(row.get("dataset_id")),
                str(row.get("evidence_bundle_uri")),
            ),
        ),
    }


def _discover_files_via_plugin(
    plugin_spec: ConnectorPluginSpec,
    *,
    scope: dict[str, object],
    source_type: str,
) -> list[DiscoveredFile]:
    raw = execute_connector_plugin(plugin_spec=plugin_spec, scope=scope)
    if not isinstance(raw, list):
        raise ValueError(
            f"Connector plugin '{source_type}' must return a list of discovery rows."
        )
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
        confidence = (
            float(confidence_raw)
            if isinstance(confidence_raw, (int, float, str))
            else 0.0
        )
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
