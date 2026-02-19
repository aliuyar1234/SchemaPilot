"""Control-plane FastAPI application."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable, Generator
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.control_plane import db_models
from backend.control_plane.catalog_snapshot import (
    export_catalog_snapshot,
    import_catalog_snapshot,
)
from backend.control_plane.decision_engine import build_recommendation_report
from backend.control_plane.deletion import (
    approve_deletion_request,
    execute_deletion_request,
    get_deletion_request,
    submit_deletion_request,
)
from backend.control_plane.gating import evaluate_gold_publish_gate
from backend.control_plane.policy_pack_service import (
    decide_policy_pack_change,
    get_effective_policy_pack,
    get_policy_pack_canary,
    promote_policy_pack_canary,
    request_policy_pack_change,
    rollback_policy_pack,
)
from backend.control_plane.repository import (
    append_audit_event as _append_audit_event,
)
from backend.control_plane.repository import (
    create_run,
    create_source,
    create_target_db_plan,
    create_target_db_profile,
    create_workspace,
    disable_target_db_profile,
    get_dataset,
    get_run,
    get_target_db_plan,
    get_target_db_profile,
    get_workspace,
    list_datasets,
    list_run_steps,
    list_sources,
    list_target_db_profiles,
    list_target_db_sync_cursors,
    list_workspaces,
    mark_target_db_plan_applied,
    update_source,
    upsert_target_db_sync_cursor,
)
from backend.control_plane.retention import (
    configure_retention_policy,
    execute_retention_purge,
    get_retention_policy,
)
from backend.control_plane.review_repository import (
    create_proposal,
    create_review_task,
    decide_review_task,
    get_review_queue_summary,
    list_review_tasks,
    unresolved_blocking_task_count,
)
from backend.control_plane.schemas import (
    ErrorInner,
    ErrorResponse,
    RecommendationCreateRequest,
    RunCreateRequest,
    SourceCreateRequest,
    WorkspaceCreateRequest,
)
from backend.control_plane.semantic_manifest_service import (
    decide_semantic_manifest_change,
    get_effective_semantic_manifest,
    request_semantic_manifest_change,
    rollback_semantic_manifest,
)
from backend.control_plane.source_health import (
    configure_source_sla,
    evaluate_source_slas,
    list_source_slas,
)
from backend.shared_domain.alert_sinks import AlertSinkError, load_alert_sink
from backend.shared_domain.audit_outbox import (
    dispatch_audit_outbox_batch,
    enqueue_audit_outbox_event,
)
from backend.shared_domain.audit_sinks import load_audit_sink
from backend.shared_domain.auth import (
    actor_has_any_role,
    authenticated_actor_from_request,
    load_local_auth_tokens,
)
from backend.shared_domain.config import Settings, load_settings
from backend.shared_domain.contract_reports import load_build_contract_report
from backend.shared_domain.db import get_session_factory, prepare_database
from backend.shared_domain.errors import NotFoundError, PolicyDeniedError, SchemaPilotError
from backend.shared_domain.evidence_store import load_evidence_bundle, store_evidence_bundle
from backend.shared_domain.gold_pointer import (
    load_latest_gold_pointer,
    publish_gold_pointer,
    rollback_gold_pointer,
)
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.lineage_sql import derive_column_lineage
from backend.shared_domain.observability import (
    increment_audit_write_failure,
    increment_contract_failure,
    log_structured_event,
    render_metrics,
    set_review_queue_backlog,
)
from backend.shared_domain.plugin_loader import load_connector_plugin_specs
from backend.shared_domain.policy_diff import compute_policy_impact_diff
from backend.shared_domain.policy_packs import list_policy_pack_summaries
from backend.shared_domain.scheduling import (
    create_run_schedule,
    list_run_schedules,
)
from backend.shared_domain.secrets_store import load_secrets_store
from backend.shared_domain.tracing import start_trace


def create_app(settings_factory: Callable[[], Settings] = load_settings) -> FastAPI:
    """Create control-plane application instance."""
    settings = settings_factory()
    settings.validate()
    secrets_store = load_secrets_store(settings)
    audit_sink = load_audit_sink(settings)
    alert_sink = load_alert_sink(settings)
    auth_tokens = load_local_auth_tokens()
    if settings.database_url.startswith("sqlite:///"):
        sqlite_path = settings.database_url.removeprefix("sqlite:///")
        db_file = Path(sqlite_path)
        if db_file.parent.as_posix() != ".":
            db_file.parent.mkdir(parents=True, exist_ok=True)
    session_factory = get_session_factory(settings.database_url)
    prepare_database(settings)
    app = FastAPI(title="SchemaPilot Control Plane", version="0.1.0")

    def get_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
            session.commit()
            if settings.audit_sink_mode == "outbox":
                try:
                    dispatch_audit_outbox_batch(
                        session_factory=session_factory,
                        sink=audit_sink,
                        service="control_plane",
                        max_batch=settings.audit_outbox_dispatch_batch_size,
                        max_attempts=settings.audit_outbox_max_attempts,
                    )
                except Exception as exc:  # pragma: no cover - defensive runtime fallback
                    log_structured_event(
                        level="error",
                        msg="audit.outbox_dispatch_failed",
                        service="control_plane",
                        correlation_id="control-plane-dispatch",
                        event_type="audit.outbox_dispatch_failed",
                        extra={"error": str(exc)},
                    )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Callable):
        request_id = request.headers.get("x-request-id", new_ulid())
        request.state.request_id = request_id
        trace_context = start_trace(
            service_name=settings.tracing_service_name,
            operation=f"{request.method}:{request.url.path}",
            correlation_id=request_id,
            enabled=settings.tracing_enabled,
        )
        request.state.trace_id = trace_context.trace_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-trace-id"] = trace_context.trace_id
        log_structured_event(
            level="info",
            msg="request.completed",
            service="control_plane",
            correlation_id=request_id,
            event_type="http.request",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
            },
        )
        return response

    @app.exception_handler(SchemaPilotError)
    async def schemapilot_error_handler(request: Request, exc: SchemaPilotError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", new_ulid())
        payload = ErrorResponse(
            error=ErrorInner(
                code=exc.error_code, message=str(exc), details=exc.details, request_id=request_id
            )
        )
        if exc.error_code == "NOT_FOUND":
            status_code = 404
        elif exc.error_code == "POLICY_DENIED":
            status_code = 403
        else:
            status_code = 400
        return JSONResponse(status_code=status_code, content=payload.model_dump())

    def require_actor(request: Request, *, roles: set[str]) -> dict[str, object]:
        actor = authenticated_actor_from_request(
            request,
            settings=settings,
            auth_tokens=auth_tokens,
        )
        if actor is None:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_or_invalid_auth_token"},
            )
        if roles and not actor_has_any_role(actor, roles):
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_required_role", "required_roles": sorted(roles)},
            )
        return actor

    platform_admin_roles = {"platform_admin"}
    steward_or_admin_roles = {"data_steward", "platform_admin"}
    analyst_or_steward_or_admin_roles = {"analyst", "data_steward", "platform_admin"}

    def not_found_response(
        *, request: Request, message: str, details: dict[str, object]
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", new_ulid())
        payload = ErrorResponse(
            error=ErrorInner(
                code="NOT_FOUND",
                message=message,
                details=details,
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=404, content=payload.model_dump())

    def target_db_operation_key(
        *,
        workspace_id: str,
        target_db_id: str,
        operation: str,
        plan_checksum: str,
    ) -> str:
        canonical = json_dumps_sorted(
            {
                "workspace_id": workspace_id,
                "target_db_id": target_db_id,
                "operation": operation,
                "plan_checksum": plan_checksum,
            }
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"opk_{digest}"

    def _sign_payload(
        *,
        payload: dict[str, object],
        key: str,
        key_id: str,
        algorithm: str = "HMAC-SHA256",
    ) -> dict[str, object]:
        canonical = json_dumps_sorted(payload).encode("utf-8")
        signature = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        return {"algorithm": algorithm, "key_id": key_id, "signature": signature}

    def _verify_signed_payload(
        *,
        payload: dict[str, object],
        signature: dict[str, object],
        key: str,
    ) -> bool:
        if str(signature.get("algorithm", "")).strip().upper() != "HMAC-SHA256":
            return False
        provided = str(signature.get("signature", "")).strip()
        if not provided:
            return False
        expected = _sign_payload(payload=payload, key=key, key_id=str(signature.get("key_id", "")))
        return hmac.compare_digest(provided, str(expected.get("signature", "")))

    def _emit_alert_non_blocking(*, alert_payload: dict[str, object]) -> None:
        try:
            alert_sink.emit(alert_payload)
        except AlertSinkError as exc:
            log_structured_event(
                level="error",
                msg="alert.sink_failed",
                service="control_plane",
                correlation_id=str(alert_payload.get("correlation_id", "alert")),
                event_type="alert.sink_failed",
                extra={"error": str(exc)},
            )

    def _target_db_state_snapshot(
        session: Session, *, workspace_id: str
    ) -> dict[str, object]:
        row = session.get(db_models.TargetDbState, workspace_id)
        if row is None:
            return {
                "active_target_db_id": None,
                "current_build_id": None,
                "current_schema_ref": None,
                "health_status": "unknown",
            }
        return {
            "active_target_db_id": row.active_target_db_id,
            "current_build_id": row.current_build_id,
            "current_schema_ref": row.current_schema_ref,
            "health_status": row.health_status,
        }

    def _ensure_target_db_state_row(
        session: Session, *, workspace_id: str
    ) -> db_models.TargetDbState:
        row = session.get(db_models.TargetDbState, workspace_id)
        if row is not None:
            return row
        row = db_models.TargetDbState(
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
        session.add(row)
        session.flush()
        return row

    def _derive_target_schema_ref(
        *,
        profile_row: db_models.TargetDbProfile | None,
        workspace_id: str,
        build_id: str,
    ) -> str:
        if profile_row is not None:
            schema = str(profile_row.connection_json.get("schema", "")).strip()
            if schema:
                return schema
            if str(profile_row.db_type).lower() == "sqlite":
                return f"sqlite_build_{build_id}"
        safe_workspace = workspace_id.replace("-", "_")
        safe_build = build_id.replace("-", "_")
        return f"sp_{safe_workspace}_{safe_build}"

    def _record_target_db_publish_state(
        *,
        session: Session,
        workspace_id: str,
        build_id: str,
        target_db_id: str | None,
        requested_schema_ref: str | None,
    ) -> dict[str, object]:
        state_row = _ensure_target_db_state_row(session, workspace_id=workspace_id)
        effective_target_db_id = (target_db_id or state_row.active_target_db_id or "").strip()
        if not effective_target_db_id:
            return _target_db_state_snapshot(session, workspace_id=workspace_id)
        profile_row = session.get(db_models.TargetDbProfile, effective_target_db_id)
        if profile_row is None or profile_row.workspace_id != workspace_id:
            return _target_db_state_snapshot(session, workspace_id=workspace_id)
        schema_ref = (
            str(requested_schema_ref).strip()
            if requested_schema_ref and str(requested_schema_ref).strip()
            else _derive_target_schema_ref(
                profile_row=profile_row, workspace_id=workspace_id, build_id=build_id
            )
        )
        sync_status_raw = state_row.sync_status_json
        sync_status = dict(sync_status_raw) if isinstance(sync_status_raw, dict) else {}
        dataset_rows = sync_status.get("datasets", [])
        build_schema_refs_raw = sync_status.get("build_schema_refs", {})
        build_schema_refs = (
            dict(build_schema_refs_raw) if isinstance(build_schema_refs_raw, dict) else {}
        )
        build_schema_refs[build_id] = schema_ref
        sync_status["datasets"] = dataset_rows if isinstance(dataset_rows, list) else []
        sync_status["build_schema_refs"] = build_schema_refs
        state_row.active_target_db_id = effective_target_db_id
        state_row.current_build_id = build_id
        state_row.current_schema_ref = schema_ref
        state_row.health_status = "healthy"
        if str(profile_row.db_type).lower() == "sqlite":
            build_database_refs_raw = sync_status.get("build_database_refs", {})
            build_database_refs = (
                dict(build_database_refs_raw)
                if isinstance(build_database_refs_raw, dict)
                else {}
            )
            active_database = str(build_database_refs.get(build_id, "")).strip()
            if active_database:
                connection_payload = dict(profile_row.connection_json)
                connection_payload["active_database"] = active_database
                profile_row.connection_json = connection_payload
        state_row.sync_status_json = sync_status
        session.flush()
        return _target_db_state_snapshot(session, workspace_id=workspace_id)

    def _rollback_target_db_publish_state(
        *,
        session: Session,
        workspace_id: str,
        rollback_build_id: str,
    ) -> dict[str, object]:
        state_row = session.get(db_models.TargetDbState, workspace_id)
        if state_row is None:
            return _target_db_state_snapshot(session, workspace_id=workspace_id)
        sync_status_raw = state_row.sync_status_json
        sync_status = dict(sync_status_raw) if isinstance(sync_status_raw, dict) else {}
        build_schema_refs_raw = sync_status.get("build_schema_refs", {})
        build_schema_refs = (
            dict(build_schema_refs_raw) if isinstance(build_schema_refs_raw, dict) else {}
        )
        target_schema_ref = str(build_schema_refs.get(rollback_build_id, "")).strip()
        profile_row = (
            session.get(db_models.TargetDbProfile, state_row.active_target_db_id)
            if state_row.active_target_db_id
            else None
        )
        if not target_schema_ref:
            target_schema_ref = _derive_target_schema_ref(
                profile_row=profile_row,
                workspace_id=workspace_id,
                build_id=rollback_build_id,
            )
        if profile_row is not None and str(profile_row.db_type).lower() == "sqlite":
            build_database_refs_raw = sync_status.get("build_database_refs", {})
            build_database_refs = (
                dict(build_database_refs_raw)
                if isinstance(build_database_refs_raw, dict)
                else {}
            )
            active_database = str(build_database_refs.get(rollback_build_id, "")).strip()
            if active_database:
                connection_payload = dict(profile_row.connection_json)
                connection_payload["active_database"] = active_database
                profile_row.connection_json = connection_payload
        state_row.current_build_id = rollback_build_id
        state_row.current_schema_ref = target_schema_ref
        state_row.health_status = "healthy"
        session.flush()
        return _target_db_state_snapshot(session, workspace_id=workspace_id)

    def append_audit_event(
        session: Session,
        *,
        workspace_id: str | None,
        actor_id: str,
        event_type: str,
        event_json: dict[str, object],
        correlation_id: str,
    ) -> dict[str, object]:
        try:
            event = _append_audit_event(
                session,
                workspace_id=workspace_id,
                actor_id=actor_id,
                event_type=event_type,
                event_json=event_json,
                correlation_id=correlation_id,
            )
            if settings.audit_sink_mode == "inline":
                audit_sink.emit(event)
            else:
                enqueue_audit_outbox_event(
                    session,
                    service="control_plane",
                    workspace_id=workspace_id,
                    audit_event_id=str(event["audit_event_id"]),
                    payload=event,
                )
            return event
        except Exception as exc:
            increment_audit_write_failure(
                workspace_id=workspace_id or "unknown",
                service="control_plane",
                operation=event_type,
            )
            log_structured_event(
                level="error",
                msg="audit.write_failed",
                service="control_plane",
                correlation_id=correlation_id,
                workspace_id=workspace_id,
                actor_id=actor_id,
                event_type="audit.write_failed",
                extra={"operation": event_type, "error": str(exc)},
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "audit_unavailable", "operation": event_type},
            ) from exc

    def ensure_contract_failure_review_task(
        *,
        session: Session,
        workspace_id: str,
        build_id: str,
        failures: list[dict[str, object]],
    ) -> dict[str, object]:
        stored = store_evidence_bundle(
            workspace_id=workspace_id,
            storage_root=settings.storage_root,
            bundle_type="contract_failure",
            payload={
                "workspace_id": workspace_id,
                "build_id": build_id,
                "failures": failures,
            },
        )
        proposal_row = (
            session.execute(
                select(db_models.ReviewProposal).where(
                    db_models.ReviewProposal.workspace_id == workspace_id,
                    db_models.ReviewProposal.proposal_type == "contract_failure_proposal",
                    db_models.ReviewProposal.evidence_bundle_uri == stored.evidence_bundle_uri,
                )
            )
            .scalars()
            .first()
        )
        if proposal_row is None:
            proposal = create_proposal(
                session,
                workspace_id=workspace_id,
                proposal_type="contract_failure_proposal",
                evidence_bundle_uri=stored.evidence_bundle_uri,
                confidence=1.0,
            )
            proposal_id = str(proposal["proposal_id"])
        else:
            proposal_id = proposal_row.proposal_id

        existing_task = (
            session.execute(
                select(db_models.ReviewTask).where(
                    db_models.ReviewTask.workspace_id == workspace_id,
                    db_models.ReviewTask.subject_ref == proposal_id,
                    db_models.ReviewTask.priority == "quality_critical",
                    db_models.ReviewTask.blocking.is_(True),
                    db_models.ReviewTask.status.in_(("open", "in_review")),
                )
            )
            .scalars()
            .first()
        )
        if existing_task is None:
            task = create_review_task(
                session,
                workspace_id=workspace_id,
                subject_ref=proposal_id,
                priority="quality_critical",
                blocking=True,
            )
            return {"proposal_id": proposal_id, "task_id": task["task_id"]}
        return {"proposal_id": proposal_id, "task_id": existing_task.task_id}

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "control_plane",
            "profile": settings.profile,
            "bind_address": settings.bind_address,
        }

    @app.get("/api/v1/metrics")
    async def metrics() -> Response:
        payload, media_type = render_metrics()
        return Response(content=payload, media_type=media_type)

    @app.get("/api/v1/policy-packs")
    async def api_list_policy_packs() -> list[dict[str, str]]:
        return list_policy_pack_summaries()

    @app.get("/api/v1/workspaces/{workspace_id}/policy-pack")
    async def api_get_effective_policy_pack(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        policy_pack = get_effective_policy_pack(session, workspace_id=workspace_id)
        if policy_pack is not None:
            return policy_pack
        return not_found_response(
            request=request,
            message="Effective policy pack not found.",
            details={"workspace_id": workspace_id},
        )  # type: ignore[return-value]

    @app.post("/api/v1/workspaces/{workspace_id}/policy-pack/change-request")
    async def api_request_policy_pack_change(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        requested_pack_id = str(payload.get("pack_id", "")).strip()
        if not requested_pack_id:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_pack_id"},
            )
        change_request = request_policy_pack_change(
            session,
            workspace_id=workspace_id,
            requester_actor_id=str(actor.get("actor_id", "unknown")),
            requested_pack_id=requested_pack_id,
            storage_root=settings.storage_root,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="policy_pack.change_requested",
            event_json=change_request,
            correlation_id=request.state.request_id,
        )
        return change_request

    @app.post(
        "/api/v1/workspaces/{workspace_id}/policy-pack/change-requests/{change_request_id}/decision"
    )
    async def api_decide_policy_pack_change(
        workspace_id: str,
        change_request_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        decision = str(payload.get("decision", "defer"))
        reason = str(payload.get("decision_reason", ""))
        canary_enabled = bool(payload.get("canary", settings.policy_pack_canary_enabled))
        result = decide_policy_pack_change(
            session,
            workspace_id=workspace_id,
            change_request_id=change_request_id,
            approver_actor_id=str(actor.get("actor_id", "unknown")),
            decision=decision,
            reason=reason,
            canary_enabled=canary_enabled,
        )
        if result is None:
            return not_found_response(
                request=request,
                message="Policy pack change request not found.",
                details={"workspace_id": workspace_id, "change_request_id": change_request_id},
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="policy_pack.change_decided",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/policy-pack/rollback")
    async def api_rollback_policy_pack(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=platform_admin_roles)
        result = rollback_policy_pack(session, workspace_id=workspace_id)
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="policy_pack.rolled_back",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.get("/api/v1/workspaces/{workspace_id}/policy-pack/canary")
    async def api_get_policy_pack_canary(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=steward_or_admin_roles)
        canary = get_policy_pack_canary(session, workspace_id=workspace_id)
        if canary is not None:
            return canary
        return not_found_response(
            request=request,
            message="Policy pack canary not found.",
            details={"workspace_id": workspace_id},
        )  # type: ignore[return-value]

    @app.post("/api/v1/workspaces/{workspace_id}/policy-pack/canary/promote")
    async def api_promote_policy_pack_canary(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=platform_admin_roles)
        result = promote_policy_pack_canary(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="policy_pack.canary_promoted",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.get("/api/v1/workspaces/{workspace_id}/semantic-manifest")
    async def api_get_effective_semantic_manifest(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        semantic_manifest = get_effective_semantic_manifest(session, workspace_id=workspace_id)
        if semantic_manifest is not None:
            return semantic_manifest
        return not_found_response(
            request=request,
            message="Effective semantic manifest not found.",
            details={"workspace_id": workspace_id},
        )  # type: ignore[return-value]

    @app.post("/api/v1/workspaces/{workspace_id}/semantic-manifest/change-request")
    async def api_request_semantic_manifest_change(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        manifest_raw = payload.get("semantic_manifest", {})
        if not isinstance(manifest_raw, dict):
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_semantic_manifest"},
            )
        change_request = request_semantic_manifest_change(
            session,
            workspace_id=workspace_id,
            requester_actor_id=str(actor.get("actor_id", "unknown")),
            semantic_manifest=manifest_raw,
            storage_root=settings.storage_root,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="semantic_manifest.change_requested",
            event_json=change_request,
            correlation_id=request.state.request_id,
        )
        return change_request

    @app.post(
        "/api/v1/workspaces/{workspace_id}/semantic-manifest/change-requests/{change_request_id}/decision"
    )
    async def api_decide_semantic_manifest_change(
        workspace_id: str,
        change_request_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        decision = str(payload.get("decision", "defer"))
        reason = str(payload.get("decision_reason", ""))
        result = decide_semantic_manifest_change(
            session,
            workspace_id=workspace_id,
            change_request_id=change_request_id,
            approver_actor_id=str(actor.get("actor_id", "unknown")),
            decision=decision,
            reason=reason,
        )
        if result is None:
            return not_found_response(
                request=request,
                message="Semantic manifest change request not found.",
                details={"workspace_id": workspace_id, "change_request_id": change_request_id},
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="semantic_manifest.change_decided",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/semantic-manifest/rollback")
    async def api_rollback_semantic_manifest(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=platform_admin_roles)
        result = rollback_semantic_manifest(session, workspace_id=workspace_id)
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="semantic_manifest.rolled_back",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.get("/api/v1/workspaces")
    async def api_list_workspaces(
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        return list_workspaces(session)

    @app.get("/api/v1/workspaces/{workspace_id}/retention/policy")
    async def api_get_retention_policy(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        policy = get_retention_policy(session, workspace_id=workspace_id)
        if policy is not None:
            return policy
        return not_found_response(
            request=request,
            message="Retention policy not found.",
            details={"workspace_id": workspace_id},
        )  # type: ignore[return-value]

    @app.post("/api/v1/workspaces/{workspace_id}/retention/policy")
    async def api_configure_retention_policy(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        retention_days_raw = payload.get("retention_days", 30)
        retention_days = (
            int(retention_days_raw) if isinstance(retention_days_raw, (int, float, str)) else 30
        )
        enabled = bool(payload.get("enabled", False))
        purge_enabled = bool(payload.get("purge_enabled", False))
        legal_hold_active = bool(payload.get("legal_hold_active", False))
        policy = configure_retention_policy(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            retention_days=retention_days,
            enabled=enabled,
            purge_enabled=purge_enabled,
            legal_hold_active=legal_hold_active,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="retention.policy_configured",
            event_json=policy,
            correlation_id=request.state.request_id,
        )
        return policy

    @app.post("/api/v1/workspaces/{workspace_id}/retention/purge")
    async def api_execute_retention_purge(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=platform_admin_roles)
        dry_run_raw = payload.get("dry_run", True)
        dry_run = bool(dry_run_raw)
        result = execute_retention_purge(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            storage_root=settings.storage_root,
            purge_root=settings.retention_purge_root,
            dry_run=dry_run,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="retention.purge_executed",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces")
    async def api_create_workspace(
        payload: WorkspaceCreateRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=platform_admin_roles)
        workspace = create_workspace(
            session,
            name=payload.name,
            profile=payload.profile,
            security_baseline=payload.security_baseline,
        )
        append_audit_event(
            session,
            workspace_id=str(workspace["workspace_id"]),
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="workspace.created",
            event_json=workspace,
            correlation_id=request.state.request_id,
        )
        return workspace

    @app.get("/api/v1/workspaces/{workspace_id}")
    async def api_get_workspace(
        workspace_id: str, request: Request, session: Session = Depends(get_session)
    ) -> dict[str, object]:
        workspace = get_workspace(session, workspace_id)
        if workspace is None:
            return not_found_response(
                request=request,
                message="Workspace not found.",
                details={"workspace_id": workspace_id},
            )  # type: ignore[return-value]
        return workspace

    @app.post("/api/v1/workspaces/{workspace_id}/sources")
    async def api_create_source(
        workspace_id: str,
        payload: SourceCreateRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        built_in_source_types = {
            "filesystem",
            "dropzone",
            "s3",
            "database",
            "sharepoint",
            "smb",
            "jira",
            "zendesk",
            "db_dump",
        }
        if payload.source_type not in built_in_source_types:
            plugin_specs = load_connector_plugin_specs()
            if payload.source_type not in plugin_specs:
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={
                        "reason": "plugin_not_allowlisted_or_unavailable",
                        "source_type": payload.source_type,
                    },
                )
        credentials_ref: str | None = None
        if payload.credentials:
            credentials_payload: dict[str, object] = {
                str(key): value for key, value in payload.credentials.items()
            }
            credentials_ref = secrets_store.put_secret(
                scope=f"workspace/{workspace_id}/source/{payload.source_type}",
                key="credentials_bundle",
                value=json_dumps_sorted(credentials_payload),
            )
        source = create_source(
            session,
            workspace_id=workspace_id,
            source_type=payload.source_type,
            scope=payload.scope,
            display_name=payload.display_name,
            credentials_ref=credentials_ref,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="source.created",
            event_json=source,
            correlation_id=request.state.request_id,
        )
        return source

    @app.get("/api/v1/workspaces/{workspace_id}/sources")
    async def api_list_sources(
        workspace_id: str, session: Session = Depends(get_session)
    ) -> list[dict[str, object]]:
        return list_sources(session, workspace_id)

    @app.patch("/api/v1/workspaces/{workspace_id}/sources/{source_id}")
    async def api_update_source(
        workspace_id: str,
        source_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        patch = dict(payload)
        credentials_raw = patch.pop("credentials", None)
        if isinstance(credentials_raw, dict) and credentials_raw:
            source_type_for_scope = str(patch.get("source_type", "custom"))
            patch["credentials_ref"] = secrets_store.put_secret(
                scope=f"workspace/{workspace_id}/source/{source_type_for_scope}",
                key=f"credentials_bundle_{source_id}",
                value=json_dumps_sorted({str(k): str(v) for k, v in credentials_raw.items()}),
            )
        source = update_source(
            session,
            workspace_id=workspace_id,
            source_id=source_id,
            patch=patch,
        )
        if source is None:
            return not_found_response(
                request=request,
                message="Source not found.",
                details={"workspace_id": workspace_id, "source_id": source_id},
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="source.updated",
            event_json=source,
            correlation_id=request.state.request_id,
        )
        return source

    def _target_db_not_found(
        *,
        request: Request,
        workspace_id: str,
        target_db_id: str,
    ) -> JSONResponse:
        return not_found_response(
            request=request,
            message="Target DB profile not found.",
            details={"workspace_id": workspace_id, "target_db_id": target_db_id},
        )

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs")
    async def api_create_target_db_profile(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        name = str(payload.get("name", "")).strip()
        db_type = str(payload.get("db_type", "")).strip()
        mode = str(payload.get("mode", "")).strip()
        connection_raw = payload.get("connection")
        connection = connection_raw if isinstance(connection_raw, dict) else {}
        credential_refs_raw = payload.get("credential_refs")
        credential_refs = credential_refs_raw if isinstance(credential_refs_raw, dict) else {}
        if not name or not db_type or not mode:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_target_db_profile_fields"},
            )
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name=name,
            db_type=db_type,
            mode=mode,
            connection=connection,
            credential_refs=credential_refs,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.profile_created",
            event_json=profile,
            correlation_id=request.state.request_id,
        )
        return {"target_db": profile}

    @app.get("/api/v1/workspaces/{workspace_id}/target-dbs")
    async def api_list_target_db_profiles(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        return list_target_db_profiles(session, workspace_id=workspace_id)

    @app.get("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}")
    async def api_get_target_db_profile(
        workspace_id: str,
        target_db_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        profile = get_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
        )
        if profile is None:
            return _target_db_not_found(
                request=request,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            )  # type: ignore[return-value]
        return profile

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}:disable")
    async def api_disable_target_db_profile(
        workspace_id: str,
        target_db_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        profile = disable_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
        )
        if profile is None:
            return _target_db_not_found(
                request=request,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.profile_disabled",
            event_json=profile,
            correlation_id=request.state.request_id,
        )
        return {"target_db": profile}

    def _create_target_db_plan_and_run(
        *,
        session: Session,
        workspace_id: str,
        target_db_id: str,
        plan_kind: str,
        run_type: str,
        payload: dict[str, object] | None = None,
        requires_approval: bool = False,
        destructive: bool = False,
    ) -> dict[str, object]:
        plan = create_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_kind=plan_kind,
            payload=payload,
            requires_approval=requires_approval,
            destructive=destructive,
        )
        run = create_run(session, workspace_id=workspace_id, run_type=run_type)
        run_row = session.get(db_models.RunRecord, str(run["run_id"]))
        if run_row is not None:
            run_input_refs: dict[str, object] = {
                "target_db_id": target_db_id,
                "plan_id": str(plan["plan_id"]),
                "plan_kind": plan_kind,
                "plan_checksum": str(plan["plan_checksum"]),
            }
            if payload:
                for key, value in payload.items():
                    run_input_refs[str(key)] = value
            run_row.input_refs_json = run_input_refs
            session.flush()
        return {
            "run_id": run["run_id"],
            "operation_key": target_db_operation_key(
                workspace_id=workspace_id,
                target_db_id=target_db_id,
                operation=plan_kind,
                plan_checksum=str(plan["plan_checksum"]),
            ),
            "status_url": f"/api/v1/workspaces/{workspace_id}/runs/{run['run_id']}",
            "plan": plan,
        }

    def _apply_target_db_plan(
        *,
        session: Session,
        workspace_id: str,
        target_db_id: str,
        run_type: str,
        plan_kind: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        plan_id = str(payload.get("plan_id", "")).strip()
        expected_checksum = str(payload.get("expected_plan_checksum", "")).strip()
        if not plan_id or not expected_checksum:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_plan_id_or_checksum"},
            )
        plan = get_target_db_plan(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_id=plan_id,
        )
        if plan is None:
            raise NotFoundError(
                "Target DB plan not found.",
                details={
                    "workspace_id": workspace_id,
                    "target_db_id": target_db_id,
                    "plan_id": plan_id,
                },
            )
        if str(plan.get("plan_kind")) != plan_kind:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "plan_kind_mismatch", "expected": plan_kind},
            )
        if str(plan.get("plan_checksum")) != expected_checksum:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "plan_checksum_mismatch"},
            )
        if bool(plan.get("requires_approval")):
            payload_raw = plan.get("payload", {})
            payload_details = payload_raw if isinstance(payload_raw, dict) else {}
            worker_plan = payload_details.get("worker_plan")
            worker_plan_details = worker_plan if isinstance(worker_plan, dict) else {}
            detail_payload_raw = worker_plan_details.get("details", {})
            detail_payload = detail_payload_raw if isinstance(detail_payload_raw, dict) else {}
            approval_task_id = str(
                detail_payload.get("approval_task_id")
                or payload_details.get("approval_task_id")
                or ""
            ).strip()
            task_row = (
                session.get(db_models.ReviewTask, approval_task_id)
                if approval_task_id
                else None
            )
            if task_row is None or task_row.workspace_id != workspace_id:
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={
                        "reason": "approval_required",
                        "plan_id": plan_id,
                        "blocking_review_task_ids": [approval_task_id]
                        if approval_task_id
                        else [],
                    },
                )
            if task_row.status != "approved":
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={
                        "reason": "approval_required",
                        "plan_id": plan_id,
                        "blocking_review_task_ids": [task_row.task_id],
                    },
                )
        mark_target_db_plan_applied(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_id=plan_id,
        )
        run = create_run(session, workspace_id=workspace_id, run_type=run_type)
        run_row = session.get(db_models.RunRecord, str(run["run_id"]))
        if run_row is not None:
            run_row.input_refs_json = {
                "target_db_id": target_db_id,
                "plan_id": plan_id,
                "plan_kind": plan_kind,
                "plan_checksum": expected_checksum,
            }
            session.flush()
        return {
            "run_id": run["run_id"],
            "status_url": f"/api/v1/workspaces/{workspace_id}/runs/{run['run_id']}",
            "operation_key": target_db_operation_key(
                workspace_id=workspace_id,
                target_db_id=target_db_id,
                operation=f"{plan_kind}_apply",
                plan_checksum=expected_checksum,
            ),
            "plan_id": plan_id,
            "plan_checksum": expected_checksum,
        }

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/validate")
    async def api_target_db_validate(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        profile = get_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
        )
        if profile is None:
            return _target_db_not_found(
                request=request,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            )  # type: ignore[return-value]
        result = _create_target_db_plan_and_run(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_kind="validate",
            run_type="TARGET_DB_VALIDATE",
            payload={"strict": bool(payload.get("strict", True))},
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.validate_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/provision/plan")
    async def api_target_db_provision_plan(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _create_target_db_plan_and_run(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_kind="provision",
            run_type="TARGET_DB_PROVISION_PLAN",
            payload=dict(payload),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.provision_plan_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/provision/apply")
    async def api_target_db_provision_apply(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _apply_target_db_plan(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            run_type="TARGET_DB_PROVISION_APPLY",
            plan_kind="provision",
            payload=payload,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.provision_apply_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/migrations/plan")
    async def api_target_db_migration_plan(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _create_target_db_plan_and_run(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_kind="migration",
            run_type="TARGET_DB_MIGRATION_PLAN",
            payload=dict(payload),
            requires_approval=bool(payload.get("requires_approval", False)),
            destructive=bool(payload.get("destructive", False)),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.migration_plan_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/migrations/apply")
    async def api_target_db_migration_apply(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _apply_target_db_plan(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            run_type="TARGET_DB_MIGRATION_APPLY",
            plan_kind="migration",
            payload=payload,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.migration_apply_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/load/plan")
    async def api_target_db_load_plan(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _create_target_db_plan_and_run(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_kind="load",
            run_type="TARGET_DB_LOAD_PLAN",
            payload=dict(payload),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.load_plan_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/load/apply")
    async def api_target_db_load_apply(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _apply_target_db_plan(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            run_type="TARGET_DB_LOAD_APPLY",
            plan_kind="load",
            payload=payload,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.load_apply_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/indexes/plan")
    async def api_target_db_index_plan(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _create_target_db_plan_and_run(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_kind="index",
            run_type="TARGET_DB_INDEX_PLAN",
            payload=dict(payload),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.index_plan_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/indexes/apply")
    async def api_target_db_index_apply(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _apply_target_db_plan(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            run_type="TARGET_DB_INDEX_APPLY",
            plan_kind="index",
            payload=payload,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.index_apply_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/rls/plan")
    async def api_target_db_rls_plan(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        if not settings.target_db_rls_enabled:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "module_disabled", "module": "target_db_rls"},
            )
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _create_target_db_plan_and_run(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            plan_kind="rls",
            run_type="TARGET_DB_RLS_PLAN",
            payload=dict(payload),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.rls_plan_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/rls/apply")
    async def api_target_db_rls_apply(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        if not settings.target_db_rls_enabled:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "module_disabled", "module": "target_db_rls"},
            )
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = _apply_target_db_plan(
            session=session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            run_type="TARGET_DB_RLS_APPLY",
            plan_kind="rls",
            payload=payload,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.rls_apply_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync:run")
    async def api_target_db_sync_run(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        profile = get_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
        )
        if profile is None:
            return _target_db_not_found(
                request=request,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            )  # type: ignore[return-value]
        run = create_run(session, workspace_id=workspace_id, run_type="TARGET_DB_SYNC_RUN")
        datasets_raw = payload.get("datasets", [])
        dataset_ids = (
            [str(item) for item in datasets_raw if isinstance(item, (str, int, float))]
            if isinstance(datasets_raw, list)
            else []
        )
        max_runtime_seconds_raw = payload.get("max_runtime_seconds", 0)
        max_rows_per_dataset_raw = payload.get("max_rows_per_dataset", 0)
        max_datasets_raw = payload.get("max_datasets", 0)
        max_runtime_seconds = (
            int(max_runtime_seconds_raw)
            if isinstance(max_runtime_seconds_raw, (int, float, str))
            else 0
        )
        max_rows_per_dataset = (
            int(max_rows_per_dataset_raw)
            if isinstance(max_rows_per_dataset_raw, (int, float, str))
            else 0
        )
        max_datasets = (
            int(max_datasets_raw)
            if isinstance(max_datasets_raw, (int, float, str))
            else 0
        )
        dataset_updates: list[dict[str, object]] = []
        for dataset_id in dataset_ids:
            cursor_hash = hashlib.sha256(
                json_dumps_sorted(
                    {
                        "dataset_id": dataset_id,
                        "run_id": str(run["run_id"]),
                        "target_db_id": target_db_id,
                    }
                ).encode("utf-8")
            ).hexdigest()
            dataset_updates.append(
                upsert_target_db_sync_cursor(
                    session,
                    workspace_id=workspace_id,
                    target_db_id=target_db_id,
                    dataset_id=dataset_id,
                    cursor_hash=f"sha256:{cursor_hash}",
                    run_id=str(run["run_id"]),
                    status="queued",
                )
            )
        result = {
            "run_id": run["run_id"],
            "status_url": f"/api/v1/workspaces/{workspace_id}/runs/{run['run_id']}",
            "target_db_id": target_db_id,
            "strict_completeness": bool(payload.get("strict_completeness", True)),
            "max_runtime_seconds": max_runtime_seconds,
            "max_rows_per_dataset": max_rows_per_dataset,
            "max_datasets": max_datasets,
            "datasets": dataset_updates,
        }
        run_row = session.get(db_models.RunRecord, str(run["run_id"]))
        if run_row is not None:
            run_row.input_refs_json = {
                "target_db_id": target_db_id,
                "datasets": dataset_ids,
                "strict_completeness": bool(payload.get("strict_completeness", True)),
                "max_runtime_seconds": max_runtime_seconds,
                "max_rows_per_dataset": max_rows_per_dataset,
                "max_datasets": max_datasets,
            }
            session.flush()
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.sync_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.get("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync/status")
    async def api_target_db_sync_status(
        workspace_id: str,
        target_db_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        profile = get_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
        )
        if profile is None:
            return _target_db_not_found(
                request=request,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            )  # type: ignore[return-value]
        state = profile.get("state", {})
        if not isinstance(state, dict):
            state = {}
        return {
            "workspace_id": workspace_id,
            "target_db_id": target_db_id,
            "last_successful_sync_at": state.get("last_successful_sync_at"),
            "datasets": list_target_db_sync_cursors(
                session,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            ),
        }

    @app.get("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync/schedules")
    async def api_target_db_sync_schedule_list(
        workspace_id: str,
        target_db_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        profile = get_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
        )
        if profile is None:
            return _target_db_not_found(
                request=request,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            )  # type: ignore[return-value]
        schedules = list_run_schedules(session, workspace_id=workspace_id)
        filtered: list[dict[str, object]] = []
        for schedule in schedules:
            if str(schedule.get("run_type", "")).strip() != "TARGET_DB_SYNC_RUN":
                continue
            input_refs_raw = schedule.get("input_refs", {})
            input_refs = input_refs_raw if isinstance(input_refs_raw, dict) else {}
            if str(input_refs.get("target_db_id", "")).strip() != target_db_id:
                continue
            filtered.append(schedule)
        return filtered

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync/schedules")
    async def api_target_db_sync_schedule_create(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        profile = get_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
        )
        if profile is None:
            return _target_db_not_found(
                request=request,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            )  # type: ignore[return-value]
        schedule_expression = str(payload.get("schedule_expression", "")).strip()
        if not schedule_expression:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_schedule_expression"},
            )
        datasets_raw = payload.get("datasets", [])
        datasets = (
            [str(item) for item in datasets_raw if str(item).strip()]
            if isinstance(datasets_raw, list)
            else []
        )
        def _payload_int(name: str) -> int:
            raw = payload.get(name, 0)
            if isinstance(raw, bool):
                return int(raw)
            if isinstance(raw, (int, float)):
                return int(raw)
            if isinstance(raw, str):
                try:
                    return int(raw.strip())
                except ValueError:
                    return 0
            return 0
        input_refs = {
            "target_db_id": target_db_id,
            "datasets": sorted(set(datasets)),
            "strict_completeness": bool(payload.get("strict_completeness", True)),
            "max_runtime_seconds": _payload_int("max_runtime_seconds"),
            "max_rows_per_dataset": _payload_int("max_rows_per_dataset"),
            "max_datasets": _payload_int("max_datasets"),
        }
        schedule = create_run_schedule(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_SYNC_RUN",
            schedule_expression=schedule_expression,
            enabled=bool(payload.get("enabled", True)),
            actor_id=str(actor.get("actor_id", "unknown")),
            input_refs=input_refs,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.sync_schedule_created",
            event_json=schedule,
            correlation_id=request.state.request_id,
        )
        return schedule

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/cutover")
    async def api_target_db_cutover(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        to_target_db_id = str(payload.get("to_target_db_id", "")).strip()
        from_target_db_id = str(payload.get("from_target_db_id", "")).strip()
        approval_task_id = str(payload.get("approval_task_id", "")).strip()
        if not to_target_db_id:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_to_target_db_id"},
            )
        to_profile = get_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=to_target_db_id,
        )
        if to_profile is None:
            raise NotFoundError(
                "Target DB profile not found.",
                details={"workspace_id": workspace_id, "target_db_id": to_target_db_id},
            )
        if bool(to_profile.get("disabled", False)):
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "target_db_disabled", "target_db_id": to_target_db_id},
            )
        state_row = _ensure_target_db_state_row(session, workspace_id=workspace_id)
        current_active = str(state_row.active_target_db_id or "").strip()
        if from_target_db_id and current_active and from_target_db_id != current_active:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={
                    "reason": "cutover_source_mismatch",
                    "current_active_target_db_id": current_active,
                },
            )
        if approval_task_id:
            task_row = session.get(db_models.ReviewTask, approval_task_id)
            if (
                task_row is None
                or task_row.workspace_id != workspace_id
                or task_row.status != "approved"
            ):
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={
                        "reason": "approval_required",
                        "blocking_review_task_ids": [approval_task_id],
                    },
                )
        state_row.active_target_db_id = to_target_db_id
        state_row.health_status = "healthy"
        session.flush()
        snapshot = _target_db_state_snapshot(session, workspace_id=workspace_id)
        result: dict[str, object] = {
            "workspace_id": workspace_id,
            "from_target_db_id": current_active or None,
            "to_target_db_id": to_target_db_id,
            "state": snapshot,
        }
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.cutover_requested",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/credentials/rotate")
    async def api_target_db_rotate_credentials(
        workspace_id: str,
        target_db_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        profile = get_target_db_profile(
            session,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
        )
        if profile is None:
            return _target_db_not_found(
                request=request,
                workspace_id=workspace_id,
                target_db_id=target_db_id,
            )  # type: ignore[return-value]
        run = create_run(
            session,
            workspace_id=workspace_id,
            run_type="TARGET_DB_ROTATE_CREDENTIALS",
        )
        run_row = session.get(db_models.RunRecord, str(run["run_id"]))
        if run_row is not None:
            run_row.input_refs_json = {
                "target_db_id": target_db_id,
                "rotation_reason": str(payload.get("reason", "operator_requested")),
            }
            session.flush()
        response_payload = {
            "workspace_id": workspace_id,
            "target_db_id": target_db_id,
            "run_id": run["run_id"],
            "status_url": f"/api/v1/workspaces/{workspace_id}/runs/{run['run_id']}",
        }
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="target_db.credentials_rotate_requested",
            event_json=response_payload,
            correlation_id=request.state.request_id,
        )
        return response_payload

    @app.get("/api/v1/workspaces/{workspace_id}/datasets")
    async def api_list_datasets(
        workspace_id: str, session: Session = Depends(get_session)
    ) -> list[dict[str, object]]:
        return list_datasets(session, workspace_id)

    @app.get("/api/v1/workspaces/{workspace_id}/datasets/{dataset_id}")
    async def api_get_dataset(
        workspace_id: str,
        dataset_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        dataset = get_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
        if dataset is not None:
            return dataset
        return not_found_response(
            request=request,
            message="Dataset not found.",
            details={"workspace_id": workspace_id, "dataset_id": dataset_id},
        )  # type: ignore[return-value]

    @app.get("/api/v1/workspaces/{workspace_id}/catalog/export")
    async def api_export_catalog(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        try:
            snapshot = export_catalog_snapshot(session, workspace_id=workspace_id)
        except ValueError:
            return not_found_response(
                request=request,
                message="Workspace not found.",
                details={"workspace_id": workspace_id},
            )  # type: ignore[return-value]
        return snapshot

    @app.post("/api/v1/workspaces/{workspace_id}/catalog/import")
    async def api_import_catalog(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        snapshot_raw = payload.get("snapshot", payload)
        snapshot = snapshot_raw if isinstance(snapshot_raw, dict) else {}
        try:
            result = import_catalog_snapshot(
                session,
                workspace_id=workspace_id,
                snapshot=snapshot,
            )
        except ValueError as exc:
            reason = str(exc)
            if reason == "workspace_not_found":
                return not_found_response(
                    request=request,
                    message="Workspace not found.",
                    details={"workspace_id": workspace_id},
                )  # type: ignore[return-value]
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason},
            ) from exc
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="catalog.imported",
            event_json={str(key): value for key, value in result.items()},
            correlation_id=request.state.request_id,
        )
        return {"workspace_id": workspace_id, **result}

    @app.get("/api/v1/workspaces/{workspace_id}/source-slas")
    async def api_list_source_slas(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        return list_source_slas(session, workspace_id=workspace_id)

    @app.post("/api/v1/workspaces/{workspace_id}/source-slas")
    async def api_configure_source_sla(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        dataset_id = str(payload.get("dataset_id", "")).strip()
        freshness_seconds_raw = payload.get("freshness_seconds", 86400)
        freshness_seconds = (
            int(freshness_seconds_raw)
            if isinstance(freshness_seconds_raw, (int, float, str))
            else 86400
        )
        enabled = bool(payload.get("enabled", True))
        if not dataset_id:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_dataset_id"},
            )
        try:
            sla = configure_source_sla(
                session,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                freshness_seconds=freshness_seconds,
                enabled=enabled,
                actor_id=str(actor.get("actor_id", "unknown")),
            )
        except ValueError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": str(exc)},
            ) from exc
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="source_sla.configured",
            event_json=sla,
            correlation_id=request.state.request_id,
        )
        return sla

    @app.post("/api/v1/workspaces/{workspace_id}/source-slas/evaluate")
    async def api_evaluate_source_slas(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        result = evaluate_source_slas(
            session,
            workspace_id=workspace_id,
            storage_root=settings.storage_root,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="source_sla.evaluated",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        violation_count_raw = result.get("violation_count", 0)
        if isinstance(violation_count_raw, bool):
            violation_count = int(violation_count_raw)
        elif isinstance(violation_count_raw, (int, float)):
            violation_count = int(violation_count_raw)
        elif isinstance(violation_count_raw, str):
            try:
                violation_count = int(violation_count_raw.strip())
            except ValueError:
                violation_count = 0
        else:
            violation_count = 0
        if violation_count > 0:
            _emit_alert_non_blocking(
                alert_payload={
                    "alert_type": "source_sla_violation",
                    "workspace_id": workspace_id,
                    "violation_count": violation_count,
                    "violations": result.get("violations", []),
                    "correlation_id": request.state.request_id,
                }
            )
        return result

    @app.post("/api/v1/workspaces/{workspace_id}/alerts/test")
    async def api_test_alert_sink(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        alert_payload = {
            "alert_type": "test",
            "workspace_id": workspace_id,
            "message": str(payload.get("message", "test_alert")),
            "actor_id": str(actor.get("actor_id", "unknown")),
            "correlation_id": request.state.request_id,
        }
        _emit_alert_non_blocking(alert_payload=alert_payload)
        return {"status": "emitted", "alert": alert_payload}

    @app.get("/api/v1/workspaces/{workspace_id}/query-budgets")
    async def api_get_query_budgets(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        row = (
            session.execute(
                select(db_models.GovernancePolicy).where(
                    db_models.GovernancePolicy.workspace_id == workspace_id,
                    db_models.GovernancePolicy.policy_type == "query_budget",
                    db_models.GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            return {
                "workspace_id": workspace_id,
                "default_bytes": settings.query_max_bytes,
                "per_role_bytes": {},
                "status": "default",
            }
        try:
            payload = json.loads(row.definition_ref)
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return {
            "workspace_id": workspace_id,
            "default_bytes": int(payload.get("default_bytes", settings.query_max_bytes)),
            "per_role_bytes": (
                payload.get("per_role_bytes", {})
                if isinstance(payload.get("per_role_bytes", {}), dict)
                else {}
            ),
            "status": "configured",
            "policy_id": row.policy_id,
        }

    @app.post("/api/v1/workspaces/{workspace_id}/query-budgets")
    async def api_set_query_budgets(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        default_bytes_raw = payload.get("default_bytes", settings.query_max_bytes)
        default_bytes = (
            int(default_bytes_raw) if isinstance(default_bytes_raw, (int, float, str)) else 0
        )
        if default_bytes <= 0:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "invalid_default_bytes"},
            )
        per_role_raw = payload.get("per_role_bytes", {})
        per_role_source = per_role_raw if isinstance(per_role_raw, dict) else {}
        per_role: dict[str, int] = {}
        for role, value in per_role_source.items():
            role_name = str(role).strip()
            if not role_name:
                continue
            value_int = int(value) if isinstance(value, (int, float, str)) else 0
            if value_int > 0:
                per_role[role_name] = value_int
        definition = {
            "workspace_id": workspace_id,
            "default_bytes": default_bytes,
            "per_role_bytes": per_role,
            "updated_by": str(actor.get("actor_id", "unknown")),
            "updated_at_epoch": int(time.time()),
        }
        row = (
            session.execute(
                select(db_models.GovernancePolicy).where(
                    db_models.GovernancePolicy.workspace_id == workspace_id,
                    db_models.GovernancePolicy.policy_type == "query_budget",
                    db_models.GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = db_models.GovernancePolicy(
                policy_id=new_ulid(),
                workspace_id=workspace_id,
                policy_type="query_budget",
                definition_ref=json.dumps(definition, sort_keys=True),
                status="active",
            )
            session.add(row)
        else:
            row.definition_ref = json.dumps(definition, sort_keys=True)
        session.flush()
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="query_budget.configured",
            event_json=definition,
            correlation_id=request.state.request_id,
        )
        return {"workspace_id": workspace_id, "policy_id": row.policy_id, **definition}

    @app.get("/api/v1/workspaces/{workspace_id}/evidence/{evidence_id}")
    async def api_get_evidence_bundle(
        workspace_id: str,
        evidence_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        bundle = load_evidence_bundle(
            workspace_id=workspace_id,
            evidence_id=evidence_id,
            storage_root=settings.storage_root,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="evidence.read",
            event_json={"workspace_id": workspace_id, "evidence_id": evidence_id},
            correlation_id=request.state.request_id,
        )
        return bundle

    @app.post("/api/v1/workspaces/{workspace_id}/runs")
    async def api_create_run(
        workspace_id: str,
        payload: RunCreateRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        run = create_run(session, workspace_id=workspace_id, run_type=payload.run_type)
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="run.created",
            event_json=run,
            correlation_id=request.state.request_id,
        )
        return run

    @app.get("/api/v1/workspaces/{workspace_id}/runs/{run_id}")
    async def api_get_run(
        workspace_id: str,
        run_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        run = get_run(session, workspace_id=workspace_id, run_id=run_id)
        if run is None:
            return not_found_response(
                request=request,
                message="Run not found.",
                details={"workspace_id": workspace_id, "run_id": run_id},
            )  # type: ignore[return-value]
        return run

    @app.get("/api/v1/workspaces/{workspace_id}/runs/{run_id}/steps")
    async def api_list_run_steps(
        workspace_id: str,
        run_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        run = get_run(session, workspace_id=workspace_id, run_id=run_id)
        if run is None:
            return not_found_response(
                request=request,
                message="Run not found.",
                details={"workspace_id": workspace_id, "run_id": run_id},
            )  # type: ignore[return-value]
        return list_run_steps(session, workspace_id=workspace_id, run_id=run_id)

    @app.get("/api/v1/workspaces/{workspace_id}/run-schedules")
    async def api_list_run_schedules(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        return list_run_schedules(session, workspace_id=workspace_id)

    @app.post("/api/v1/workspaces/{workspace_id}/run-schedules")
    async def api_create_run_schedule(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        run_type = str(payload.get("run_type", "discover")).strip()
        schedule_expression = str(payload.get("schedule_expression", "")).strip()
        enabled = bool(payload.get("enabled", True))
        input_refs_raw = payload.get("input_refs", {})
        input_refs = input_refs_raw if isinstance(input_refs_raw, dict) else {}
        if not run_type or not schedule_expression:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_schedule_fields"},
            )
        try:
            schedule = create_run_schedule(
                session,
                workspace_id=workspace_id,
                run_type=run_type,
                schedule_expression=schedule_expression,
                enabled=enabled,
                actor_id=str(actor.get("actor_id", "unknown")),
                input_refs=input_refs,
            )
        except ValueError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": str(exc)},
            ) from exc
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="run.schedule_created",
            event_json=schedule,
            correlation_id=request.state.request_id,
        )
        return schedule

    @app.get("/api/v1/workspaces/{workspace_id}/review_tasks")
    async def api_list_review_tasks(
        workspace_id: str, session: Session = Depends(get_session)
    ) -> list[dict[str, object]]:
        tasks = list_review_tasks(session, workspace_id)
        backlog: dict[str, int] = {}
        for task in tasks:
            priority = str(task.get("priority", "unknown"))
            backlog[priority] = backlog.get(priority, 0) + 1
        for priority, count in backlog.items():
            set_review_queue_backlog(workspace_id=workspace_id, priority=priority, count=count)
        return tasks

    @app.get("/api/v1/workspaces/{workspace_id}/review_tasks/summary")
    async def api_review_queue_summary(
        workspace_id: str, session: Session = Depends(get_session)
    ) -> dict[str, object]:
        summary = get_review_queue_summary(session, workspace_id)
        by_priority_raw = summary.get("by_priority", {})
        if isinstance(by_priority_raw, dict):
            for priority, count in by_priority_raw.items():
                set_review_queue_backlog(
                    workspace_id=workspace_id,
                    priority=str(priority),
                    count=int(count),
                )
        return summary

    @app.post("/api/v1/onboarding/demo_bootstrap")
    async def api_demo_bootstrap(
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        workspace = create_workspace(
            session,
            name=str(payload.get("workspace_name", "Demo Workspace")),
            profile=str(payload.get("profile", "starter")),
            security_baseline=str(payload.get("security_baseline", "standard")),
        )
        demo_root = Path(settings.storage_root).parent / "demo_data"
        demo_root.mkdir(parents=True, exist_ok=True)
        demo_csv = demo_root / "invoices_demo.csv"
        if not demo_csv.exists():
            demo_csv.write_text(
                "invoice_id,customer,region,amount,email\n"
                "1001,ACME,eu,1200.5,alice@acme.example\n"
                "1002,Beta,us,900.0,bob@beta.example\n",
                encoding="utf-8",
            )
        source = create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="filesystem",
            scope={"root_path": demo_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Demo Files",
        )
        run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        proposal = create_proposal(
            session,
            workspace_id=str(workspace["workspace_id"]),
            proposal_type="pii_tag_proposal",
            evidence_bundle_uri="evidence://demo/onboarding/pii",
            confidence=0.68,
        )
        review_task = create_review_task(
            session,
            workspace_id=str(workspace["workspace_id"]),
            subject_ref=str(proposal["proposal_id"]),
            priority="security_critical",
            blocking=True,
        )
        response_payload: dict[str, object] = {
            "workspace": workspace,
            "source": source,
            "run": run,
            "review_task": review_task,
            "demo_data_path": demo_root.as_posix(),
            "first_query_example": {
                "endpoint": "/api/v1/gateway/query",
                "authorization": "Bearer local-analyst-token",
                "payload": {
                    "workspace_id": str(workspace["workspace_id"]),
                    "query": {"language": "sql", "text": "select 1 as one"},
                    "resource_attributes": {"dataset_id": "dataset-1"},
                },
            },
            "next_steps": [
                "Review and approve the demo review task.",
                "Run a governed query through the gateway.",
                "Generate a recommendation report for your workspace.",
            ],
        }
        append_audit_event(
            session,
            workspace_id=str(workspace["workspace_id"]),
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="onboarding.demo_bootstrap",
            event_json=response_payload,
            correlation_id=request.state.request_id,
        )
        return response_payload

    @app.post("/api/v1/workspaces/{workspace_id}/proposals")
    async def api_create_proposal(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        confidence_raw = payload.get("confidence", 0.5)
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float, str)) else 0.5
        proposal = create_proposal(
            session,
            workspace_id=workspace_id,
            proposal_type=str(payload.get("proposal_type", "schema_proposal")),
            evidence_bundle_uri=str(payload.get("evidence_bundle_uri", "evidence://stub")),
            confidence=confidence,
        )
        task = create_review_task(
            session,
            workspace_id=workspace_id,
            subject_ref=str(proposal["proposal_id"]),
            priority=str(payload.get("priority", "quality_critical")),
            blocking=bool(payload.get("blocking", False)),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="proposal.created",
            event_json={"proposal": proposal, "task": task},
            correlation_id=request.state.request_id,
        )
        return {"proposal": proposal, "task": task}

    @app.post("/api/v1/workspaces/{workspace_id}/review_tasks/{task_id}/decision")
    async def api_decide_review_task(
        workspace_id: str,
        task_id: str,
        payload: dict[str, str],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        decision = decide_review_task(
            session,
            workspace_id=workspace_id,
            task_id=task_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            decision=str(payload.get("decision", "defer")),
            reason=str(payload.get("decision_reason", "")),
        )
        if decision is None:
            return not_found_response(
                request=request,
                message="Review task not found.",
                details={"workspace_id": workspace_id, "task_id": task_id},
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="review.decision",
            event_json=decision,
            correlation_id=request.state.request_id,
        )
        return decision

    @app.get("/api/v1/workspaces/{workspace_id}/access-requests")
    async def api_list_access_requests(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        rows = (
            session.execute(
                select(db_models.GovernancePolicy)
                .where(
                    db_models.GovernancePolicy.workspace_id == workspace_id,
                    db_models.GovernancePolicy.policy_type == "data_access_request",
                    db_models.GovernancePolicy.status == "active",
                )
                .order_by(db_models.GovernancePolicy.policy_id)
            )
            .scalars()
            .all()
        )
        requests: list[dict[str, object]] = []
        for row in rows:
            try:
                payload = json.loads(row.definition_ref)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                requests.append({"request_id": row.policy_id, **payload})
        return requests

    @app.post("/api/v1/workspaces/{workspace_id}/access-requests")
    async def api_create_access_request(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        dataset_id = str(payload.get("dataset_id", "")).strip()
        requested_role = str(payload.get("requested_role", "analyst")).strip() or "analyst"
        if not dataset_id:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "dataset_id_required"},
            )
        request_id = new_ulid()
        request_payload = {
            "workspace_id": workspace_id,
            "dataset_id": dataset_id,
            "requested_role": requested_role,
            "requester_actor_id": str(actor.get("actor_id", "unknown")),
            "status": "open",
            "created_at_epoch": int(time.time()),
        }
        session.add(
            db_models.GovernancePolicy(
                policy_id=request_id,
                workspace_id=workspace_id,
                policy_type="data_access_request",
                definition_ref=json.dumps(request_payload, sort_keys=True),
                status="active",
            )
        )
        session.flush()
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="access_request.created",
            event_json={"request_id": request_id, **request_payload},
            correlation_id=request.state.request_id,
        )
        return {"request_id": request_id, **request_payload}

    @app.post("/api/v1/workspaces/{workspace_id}/access-requests/{request_id}/decision")
    async def api_decide_access_request(
        workspace_id: str,
        request_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        row = session.get(db_models.GovernancePolicy, request_id)
        if (
            row is None
            or row.workspace_id != workspace_id
            or row.policy_type != "data_access_request"
            or row.status != "active"
        ):
            return not_found_response(
                request=request,
                message="Access request not found.",
                details={"workspace_id": workspace_id, "request_id": request_id},
            )  # type: ignore[return-value]
        try:
            request_payload = json.loads(row.definition_ref)
        except json.JSONDecodeError:
            request_payload = {}
        if not isinstance(request_payload, dict):
            request_payload = {}
        decision = str(payload.get("decision", "defer")).strip().lower()
        if decision not in {"approve", "reject", "defer"}:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "invalid_decision"},
            )
        request_payload["status"] = (
            "approved" if decision == "approve" else "rejected" if decision == "reject" else "open"
        )
        request_payload["decision_actor_id"] = str(actor.get("actor_id", "unknown"))
        request_payload["decision_reason"] = str(payload.get("decision_reason", "")).strip()
        request_payload["decision_at_epoch"] = int(time.time())
        row.definition_ref = json.dumps(request_payload, sort_keys=True)

        generated_task: dict[str, object] | None = None
        if decision == "approve":
            evidence = store_evidence_bundle(
                workspace_id=workspace_id,
                storage_root=settings.storage_root,
                bundle_type="data_access_request",
                payload={"request_id": request_id, **request_payload},
            )
            proposal = create_proposal(
                session,
                workspace_id=workspace_id,
                proposal_type="policy_pack_change_proposal",
                evidence_bundle_uri=evidence.evidence_bundle_uri,
                confidence=1.0,
            )
            generated_task = create_review_task(
                session,
                workspace_id=workspace_id,
                subject_ref=str(proposal["proposal_id"]),
                priority="security_critical",
                blocking=True,
            )
            request_payload["policy_change_task_id"] = generated_task["task_id"]
        session.flush()
        response_payload = {"request_id": request_id, **request_payload}
        if generated_task is not None:
            response_payload["generated_task"] = generated_task
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="access_request.decided",
            event_json=response_payload,
            correlation_id=request.state.request_id,
        )
        return response_payload

    @app.get("/api/v1/workspaces/{workspace_id}/breakglass/requests")
    async def api_list_breakglass_requests(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        _ = require_actor(request, roles=steward_or_admin_roles)
        rows = (
            session.execute(
                select(db_models.GovernancePolicy)
                .where(
                    db_models.GovernancePolicy.workspace_id == workspace_id,
                    db_models.GovernancePolicy.policy_type == "breakglass_request",
                    db_models.GovernancePolicy.status == "active",
                )
                .order_by(db_models.GovernancePolicy.policy_id)
            )
            .scalars()
            .all()
        )
        requests: list[dict[str, object]] = []
        for row in rows:
            try:
                payload = json.loads(row.definition_ref)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                requests.append({"request_id": row.policy_id, **payload})
        return requests

    @app.post("/api/v1/workspaces/{workspace_id}/breakglass/requests")
    async def api_create_breakglass_request(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        requested_actor_id = str(payload.get("actor_id", "")).strip()
        ttl_raw = payload.get("ttl_seconds", 900)
        ttl_seconds = int(ttl_raw) if isinstance(ttl_raw, (int, float, str)) else 0
        max_ttl = int(os.getenv("SCHEMAPILOT_BREAKGLASS_MAX_TTL_SECONDS", "3600"))
        if not requested_actor_id:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "actor_id_required"},
            )
        if ttl_seconds <= 0 or ttl_seconds > max_ttl:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "invalid_breakglass_ttl", "max_ttl_seconds": max_ttl},
            )
        request_id = new_ulid()
        request_payload = {
            "workspace_id": workspace_id,
            "actor_id": requested_actor_id,
            "ttl_seconds": ttl_seconds,
            "status": "pending",
            "approvals": [],
            "requested_by": str(actor.get("actor_id", "unknown")),
            "created_at_epoch": int(time.time()),
        }
        session.add(
            db_models.GovernancePolicy(
                policy_id=request_id,
                workspace_id=workspace_id,
                policy_type="breakglass_request",
                definition_ref=json.dumps(request_payload, sort_keys=True),
                status="active",
            )
        )
        session.flush()
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="breakglass.request_created",
            event_json={"request_id": request_id, **request_payload},
            correlation_id=request.state.request_id,
        )
        return {"request_id": request_id, **request_payload}

    @app.post("/api/v1/workspaces/{workspace_id}/breakglass/requests/{request_id}/approve")
    async def api_approve_breakglass_request(
        workspace_id: str,
        request_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        row = session.get(db_models.GovernancePolicy, request_id)
        if (
            row is None
            or row.workspace_id != workspace_id
            or row.policy_type != "breakglass_request"
            or row.status != "active"
        ):
            return not_found_response(
                request=request,
                message="Breakglass request not found.",
                details={"workspace_id": workspace_id, "request_id": request_id},
            )  # type: ignore[return-value]
        try:
            request_payload = json.loads(row.definition_ref)
        except json.JSONDecodeError:
            request_payload = {}
        if not isinstance(request_payload, dict):
            request_payload = {}
        status = str(request_payload.get("status", "pending")).strip().lower()
        if status in {"revoked", "expired"}:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": f"breakglass_{status}"},
            )
        decision = str(payload.get("decision", "approve")).strip().lower()
        if decision not in {"approve", "reject"}:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "invalid_decision"},
            )
        approvals_raw = request_payload.get("approvals", [])
        approvals = approvals_raw if isinstance(approvals_raw, list) else []
        actor_id = str(actor.get("actor_id", "unknown"))
        if decision == "approve":
            if actor_id not in approvals:
                approvals.append(actor_id)
        else:
            request_payload["status"] = "rejected"
        request_payload["approvals"] = sorted(
            {str(item) for item in approvals if str(item).strip()}
        )
        request_payload["last_decision_actor_id"] = actor_id
        request_payload["last_decision_reason"] = str(payload.get("decision_reason", "")).strip()
        request_payload["last_decision_at_epoch"] = int(time.time())
        if decision == "approve" and len(request_payload["approvals"]) >= 2:
            now_epoch = int(time.time())
            ttl_seconds = int(request_payload.get("ttl_seconds", 900))
            expires_epoch = now_epoch + max(ttl_seconds, 1)
            request_payload["status"] = "active"
            request_payload["active_from_epoch"] = now_epoch
            request_payload["expires_epoch"] = expires_epoch
            grant_id = new_ulid()
            grant_payload = {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "actor_id": str(request_payload.get("actor_id", "")),
                "status": "active",
                "expires_epoch": expires_epoch,
            }
            session.add(
                db_models.GovernancePolicy(
                    policy_id=grant_id,
                    workspace_id=workspace_id,
                    policy_type="breakglass_grant",
                    definition_ref=json.dumps(grant_payload, sort_keys=True),
                    status="active",
                )
            )
            request_payload["grant_policy_id"] = grant_id
        row.definition_ref = json.dumps(request_payload, sort_keys=True)
        session.flush()
        response_payload = {"request_id": request_id, **request_payload}
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=actor_id,
            event_type="breakglass.request_decided",
            event_json=response_payload,
            correlation_id=request.state.request_id,
        )
        return response_payload

    @app.post("/api/v1/workspaces/{workspace_id}/breakglass/requests/{request_id}/revoke")
    async def api_revoke_breakglass_request(
        workspace_id: str,
        request_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        row = session.get(db_models.GovernancePolicy, request_id)
        if (
            row is None
            or row.workspace_id != workspace_id
            or row.policy_type != "breakglass_request"
            or row.status != "active"
        ):
            return not_found_response(
                request=request,
                message="Breakglass request not found.",
                details={"workspace_id": workspace_id, "request_id": request_id},
            )  # type: ignore[return-value]
        try:
            request_payload = json.loads(row.definition_ref)
        except json.JSONDecodeError:
            request_payload = {}
        if not isinstance(request_payload, dict):
            request_payload = {}
        request_payload["status"] = "revoked"
        request_payload["revoked_by"] = str(actor.get("actor_id", "unknown"))
        request_payload["revoked_at_epoch"] = int(time.time())
        row.definition_ref = json.dumps(request_payload, sort_keys=True)
        grant_policy_id = str(request_payload.get("grant_policy_id", "")).strip()
        if grant_policy_id:
            grant_row = session.get(db_models.GovernancePolicy, grant_policy_id)
            if grant_row is not None:
                grant_row.status = "inactive"
        session.flush()
        response_payload = {"request_id": request_id, **request_payload}
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="breakglass.request_revoked",
            event_json=response_payload,
            correlation_id=request.state.request_id,
        )
        return response_payload

    @app.post("/api/v1/workspaces/{workspace_id}/glossary/generate")
    async def api_generate_glossary(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        datasets = list_datasets(session, workspace_id)
        entries: list[dict[str, object]] = []
        for dataset in datasets:
            logical_name = str(dataset.get("logical_name", "")).strip()
            if not logical_name:
                continue
            entries.append(
                {
                    "term": logical_name,
                    "kind": "dataset",
                    "dataset_id": str(dataset.get("dataset_id", "")),
                    "definition": f"Dataset {logical_name} available in workspace {workspace_id}.",
                }
            )
        semantic_row = (
            session.execute(
                select(db_models.GovernancePolicy).where(
                    db_models.GovernancePolicy.workspace_id == workspace_id,
                    db_models.GovernancePolicy.policy_type == "semantic_manifest",
                    db_models.GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
        if semantic_row is not None:
            try:
                semantic_payload = json.loads(semantic_row.definition_ref)
            except json.JSONDecodeError:
                semantic_payload = {}
            if isinstance(semantic_payload, dict):
                manifest = semantic_payload.get("manifest", {})
                if isinstance(manifest, dict):
                    metrics_raw = manifest.get("metrics", [])
                    metrics = metrics_raw if isinstance(metrics_raw, list) else []
                    for metric in metrics:
                        if not isinstance(metric, dict):
                            continue
                        metric_id = str(metric.get("metric_id", "")).strip()
                        if not metric_id:
                            continue
                        entries.append(
                            {
                                "term": metric_id,
                                "kind": "metric",
                                "definition": str(metric.get("description", "Semantic metric")),
                            }
                        )
        glossary_payload = {
            "workspace_id": workspace_id,
            "generated_at_epoch": int(time.time()),
            "entry_count": len(entries),
            "entries": sorted(
                entries,
                key=lambda item: (str(item.get("kind", "")), str(item.get("term", ""))),
            ),
        }
        row = (
            session.execute(
                select(db_models.GovernancePolicy).where(
                    db_models.GovernancePolicy.workspace_id == workspace_id,
                    db_models.GovernancePolicy.policy_type == "glossary",
                    db_models.GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = db_models.GovernancePolicy(
                policy_id=new_ulid(),
                workspace_id=workspace_id,
                policy_type="glossary",
                definition_ref=json.dumps(glossary_payload, sort_keys=True),
                status="active",
            )
            session.add(row)
        else:
            row.definition_ref = json.dumps(glossary_payload, sort_keys=True)
        session.flush()
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="glossary.generated",
            event_json=glossary_payload,
            correlation_id=request.state.request_id,
        )
        return glossary_payload

    @app.get("/api/v1/workspaces/{workspace_id}/glossary/export")
    async def api_export_glossary(
        workspace_id: str,
        request: Request,
        format: str = "json",  # noqa: A002
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        row = (
            session.execute(
                select(db_models.GovernancePolicy).where(
                    db_models.GovernancePolicy.workspace_id == workspace_id,
                    db_models.GovernancePolicy.policy_type == "glossary",
                    db_models.GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            return {"workspace_id": workspace_id, "entry_count": 0, "entries": [], "format": "json"}
        try:
            payload = json.loads(row.definition_ref)
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        normalized_format = str(format).strip().lower()
        if normalized_format == "markdown":
            entries_raw = payload.get("entries", [])
            entries = entries_raw if isinstance(entries_raw, list) else []
            lines = [f"# Glossary for {workspace_id}", ""]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                term = str(entry.get("term", "")).strip()
                if not term:
                    continue
                definition = str(entry.get("definition", "")).strip()
                kind = str(entry.get("kind", "")).strip()
                lines.append(f"- **{term}** ({kind}): {definition}")
            return {
                "workspace_id": workspace_id,
                "format": "markdown",
                "content": "\n".join(lines).strip() + "\n",
            }
        return {**payload, "format": "json"}

    @app.post("/api/v1/workspaces/{workspace_id}/promotion/export")
    async def api_promotion_export(
        workspace_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        snapshot = export_catalog_snapshot(session, workspace_id=workspace_id)
        bundle_payload = {
            "workspace_id": workspace_id,
            "snapshot": snapshot,
            "generated_at_epoch": int(time.time()),
        }
        signing_key = os.getenv("SCHEMAPILOT_PROMOTION_SIGNING_KEY", "schemapilot-promotion-key-v1")
        signature = _sign_payload(payload=bundle_payload, key=signing_key, key_id="promotion-v1")
        response_payload: dict[str, object] = {
            "bundle": bundle_payload,
            "signature": signature,
        }
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="promotion.bundle_exported",
            event_json=response_payload,
            correlation_id=request.state.request_id,
        )
        return response_payload

    @app.post("/api/v1/workspaces/{workspace_id}/promotion/import")
    async def api_promotion_import(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        bundle_raw = payload.get("bundle", {})
        signature_raw = payload.get("signature", {})
        bundle = bundle_raw if isinstance(bundle_raw, dict) else {}
        signature = signature_raw if isinstance(signature_raw, dict) else {}
        signing_key = os.getenv("SCHEMAPILOT_PROMOTION_SIGNING_KEY", "schemapilot-promotion-key-v1")
        if not _verify_signed_payload(payload=bundle, signature=signature, key=signing_key):
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "promotion_signature_invalid"},
            )
        before_report_raw = payload.get("before_policy_report")
        after_report_raw = payload.get("after_policy_report")
        if isinstance(before_report_raw, dict) and isinstance(after_report_raw, dict):
            protected_raw = payload.get("protected_scenario_ids", [])
            protected = (
                [str(item) for item in protected_raw if str(item).strip()]
                if isinstance(protected_raw, list)
                else []
            )
            diff = compute_policy_impact_diff(
                before_report={str(key): value for key, value in before_report_raw.items()},
                after_report={str(key): value for key, value in after_report_raw.items()},
                protected_scenario_ids=protected,
            )
            invariants = diff.get("invariants", {})
            protected_denials = (
                invariants.get("protected_denials", [])
                if isinstance(invariants, dict)
                else []
            )
            if isinstance(protected_denials, list) and protected_denials:
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={
                        "reason": "promotion_policy_gate_failed",
                        "protected_denials": protected_denials,
                    },
                )
        snapshot_raw = bundle.get("snapshot", {})
        snapshot = snapshot_raw if isinstance(snapshot_raw, dict) else {}
        result = import_catalog_snapshot(session, workspace_id=workspace_id, snapshot=snapshot)
        response_payload: dict[str, object] = {
            "workspace_id": workspace_id,
            "import": result,
        }
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="promotion.bundle_imported",
            event_json=response_payload,
            correlation_id=request.state.request_id,
        )
        return response_payload

    @app.post("/api/v1/workspaces/{workspace_id}/recommendations")
    async def api_create_recommendation(
        workspace_id: str, payload: RecommendationCreateRequest, request: Request
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        report = build_recommendation_report(payload.intent)
        return {
            "report_id": new_ulid(),
            "workspace_id": workspace_id,
            "ranked_templates": report["ranked_templates"],
            "hard_constraint_gates": report["hard_constraint_gates"],
            "confidence": report["confidence"],
            "missing_evidence": report["missing_evidence"],
            "approval_required": report["approval_required"],
            "approval_reasons": report["approval_reasons"],
            "intent": payload.intent,
        }

    @app.post("/api/v1/workspaces/{workspace_id}/lineage/sql")
    async def api_derive_sql_lineage(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        sql_text = str(payload.get("sql_text", "")).strip()
        if not sql_text:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_sql_text"},
            )
        lineage = derive_column_lineage(sql_text)
        return {
            "workspace_id": workspace_id,
            "lineage_version": "v1",
            "lineage": lineage,
            "lineage_available": bool(lineage),
        }

    @app.post("/api/v1/workspaces/{workspace_id}/lineage/export")
    async def api_export_lineage_graph(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        sql_text = str(payload.get("sql_text", "")).strip()
        if not sql_text:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_sql_text"},
            )
        lineage = derive_column_lineage(sql_text)
        nodes: set[str] = set()
        edges: list[dict[str, object]] = []
        for row in lineage:
            output_column = str(row.get("output_column", "")).strip()
            source_columns_raw = row.get("source_columns", [])
            source_columns = (
                [str(item) for item in source_columns_raw if str(item).strip()]
                if isinstance(source_columns_raw, list)
                else []
            )
            if output_column:
                nodes.add(output_column)
            for source in source_columns:
                nodes.add(source)
                if output_column:
                    edges.append({"from": source, "to": output_column})
        return {
            "workspace_id": workspace_id,
            "lineage_version": "v1",
            "graph": {
                "nodes": [{"id": node} for node in sorted(nodes)],
                "edges": sorted(
                    edges,
                    key=lambda item: (str(item.get("from", "")), str(item.get("to", ""))),
                ),
            },
            "lineage_available": bool(lineage),
        }

    @app.get("/api/v1/workspaces/{workspace_id}/recommendations/{report_id}")
    async def api_get_recommendation(
        workspace_id: str, report_id: str, request: Request
    ) -> dict[str, object]:
        _ = report_id
        return not_found_response(
            request=request,
            message="Recommendation report not found.",
            details={"workspace_id": workspace_id, "report_id": report_id},
        )  # type: ignore[return-value]

    @app.post("/api/v1/workspaces/{workspace_id}/builds/{build_id}/publish")
    async def api_publish_build(
        workspace_id: str,
        build_id: str,
        request: Request,
        payload: dict[str, object],
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        contract_report = load_build_contract_report(
            workspace_id=workspace_id,
            build_id=build_id,
            storage_root=settings.storage_root,
        )
        contract_failures: list[dict[str, object]] = []
        contract_report_present = contract_report is not None
        contracts_passed = False
        if contract_report is not None:
            contracts_passed = contract_report.contracts_passed
            contract_failures = contract_report.failures
        else:
            contract_failures = [{"reason": "contract_report_missing"}]
        gate = evaluate_gold_publish_gate(
            contracts_passed=contracts_passed,
            unresolved_blocking_tasks=unresolved_blocking_task_count(session, workspace_id),
        )
        target_db_state_before = _target_db_state_snapshot(session, workspace_id=workspace_id)
        latest_pointer_before = load_latest_gold_pointer(
            workspace_id=workspace_id,
            storage_root=settings.storage_root,
        )
        pointer: dict[str, object] | None = None
        target_db_state_after = target_db_state_before
        if gate["allowed"]:
            pointer = publish_gold_pointer(
                workspace_id=workspace_id,
                build_id=build_id,
                snapshot_id=str(payload.get("snapshot_id", build_id)),
                model_name=str(payload.get("model_name", "default_model")),
                storage_root=settings.storage_root,
            )
            target_db_state_after = _record_target_db_publish_state(
                session=session,
                workspace_id=workspace_id,
                build_id=build_id,
                target_db_id=str(payload.get("target_db_id", "")).strip() or None,
                requested_schema_ref=str(payload.get("target_schema_ref", "")).strip() or None,
            )
        result_payload: dict[str, object] = {
            "workspace_id": workspace_id,
            "build_id": build_id,
            "status": "published" if gate["allowed"] else "blocked",
            "gate_reason": gate["reason"],
            "contracts_report_present": contract_report_present,
            "contracts_passed": contracts_passed,
            "latest_pointer_before": latest_pointer_before,
            "latest_pointer_after": pointer
            if pointer is not None
            else load_latest_gold_pointer(
                workspace_id=workspace_id,
                storage_root=settings.storage_root,
            ),
            "target_db_state_before": target_db_state_before,
            "target_db_state_after": target_db_state_after,
        }
        if not gate["allowed"] and gate["reason"] == "contract_failure":
            increment_contract_failure(workspace_id=workspace_id, layer="gold")
            result_payload["contract_failure_task"] = ensure_contract_failure_review_task(
                session=session,
                workspace_id=workspace_id,
                build_id=build_id,
                failures=contract_failures,
            )
        build_attestation_payload = {
            "workspace_id": workspace_id,
            "build_id": build_id,
            "status": str(result_payload.get("status", "")),
            "gate_reason": str(result_payload.get("gate_reason", "")),
            "latest_pointer_after": result_payload.get("latest_pointer_after"),
            "target_db_state_after": result_payload.get("target_db_state_after"),
        }
        attestation_required = (
            os.getenv("SCHEMAPILOT_BUILD_ATTESTATION_REQUIRED", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        attestation_key = os.getenv("SCHEMAPILOT_BUILD_ATTESTATION_KEY", "").strip()
        if attestation_required and not attestation_key:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "build_attestation_key_required"},
            )
        if not attestation_key:
            attestation_key = "schemapilot-build-attestation-key-dev-v1"
        result_payload["build_attestation"] = _sign_payload(
            payload=build_attestation_payload,
            key=attestation_key,
            key_id="build-attestation-v1",
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="build.published",
            event_json=result_payload,
            correlation_id=request.state.request_id,
        )
        return result_payload

    @app.post("/api/v1/workspaces/{workspace_id}/builds/{build_id}/rollback")
    async def api_rollback_build(
        workspace_id: str,
        build_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=platform_admin_roles)
        target_db_state_before = _target_db_state_snapshot(session, workspace_id=workspace_id)
        try:
            rollback_result = rollback_gold_pointer(
                workspace_id=workspace_id,
                build_id=build_id,
                storage_root=settings.storage_root,
            )
        except ValueError as exc:
            return not_found_response(
                request=request,
                message="Rollback target not found.",
                details={"workspace_id": workspace_id, "build_id": build_id, "reason": str(exc)},
            )  # type: ignore[return-value]
        rolled_back_to_raw = rollback_result.get("rolled_back_to", {})
        rolled_back_to = rolled_back_to_raw if isinstance(rolled_back_to_raw, dict) else {}
        rollback_build_id = str(rolled_back_to.get("build_id", "")).strip()
        target_db_state_after = (
            _rollback_target_db_publish_state(
                session=session,
                workspace_id=workspace_id,
                rollback_build_id=rollback_build_id,
            )
            if rollback_build_id
            else target_db_state_before
        )
        payload: dict[str, object] = {
            "workspace_id": workspace_id,
            "build_id": build_id,
            "status": "rolled_back",
            "rollback": rollback_result,
            "target_db_state_before": target_db_state_before,
            "target_db_state_after": target_db_state_after,
        }
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="build.rollback",
            event_json=payload,
            correlation_id=request.state.request_id,
        )
        return payload

    @app.post("/api/v1/workspaces/{workspace_id}/deletions")
    async def api_create_deletion_request(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        if not settings.deletion_enabled:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "deletion_disabled"},
            )
        subject_selector_raw = payload.get("subject_selector", {})
        subject_selector: dict[str, object] = (
            subject_selector_raw if isinstance(subject_selector_raw, dict) else {}
        )
        affected_snapshots_raw = payload.get("affected_snapshots", [])
        affected_snapshots = (
            [str(item) for item in affected_snapshots_raw if isinstance(item, (str, int, float))]
            if isinstance(affected_snapshots_raw, list)
            else []
        )
        affected_indexes_raw = payload.get("affected_indexes", [])
        affected_indexes = (
            [str(item) for item in affected_indexes_raw if isinstance(item, (str, int, float))]
            if isinstance(affected_indexes_raw, list)
            else []
        )
        deletion_request = submit_deletion_request(
            session,
            workspace_id=workspace_id,
            subject_selector=subject_selector,
            affected_snapshots=affected_snapshots,
            affected_indexes=affected_indexes,
            requester_actor_id=str(actor.get("actor_id", "unknown")),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="deletion.requested",
            event_json=deletion_request,
            correlation_id=request.state.request_id,
        )
        return deletion_request

    @app.get("/api/v1/workspaces/{workspace_id}/deletions/{deletion_request_id}")
    async def api_get_deletion_request(
        workspace_id: str,
        deletion_request_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        _ = require_actor(request, roles=analyst_or_steward_or_admin_roles)
        deletion_request = get_deletion_request(
            session,
            workspace_id=workspace_id,
            deletion_request_id=deletion_request_id,
        )
        if deletion_request is not None:
            return deletion_request
        return not_found_response(
            request=request,
            message="Deletion request not found.",
            details={"workspace_id": workspace_id, "deletion_request_id": deletion_request_id},
        )  # type: ignore[return-value]

    @app.post("/api/v1/workspaces/{workspace_id}/deletions/{deletion_request_id}/approve")
    async def api_approve_deletion_request(
        workspace_id: str,
        deletion_request_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=steward_or_admin_roles)
        if not settings.deletion_enabled:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "deletion_disabled"},
            )
        decision = str(payload.get("decision", "defer"))
        reason = str(payload.get("decision_reason", ""))
        approval = approve_deletion_request(
            session,
            workspace_id=workspace_id,
            deletion_request_id=deletion_request_id,
            approver_actor_id=str(actor.get("actor_id", "unknown")),
            decision=decision,
            reason=reason,
        )
        if approval is None:
            return not_found_response(
                request=request,
                message="Deletion request not found.",
                details={"workspace_id": workspace_id, "deletion_request_id": deletion_request_id},
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="deletion.approved",
            event_json=approval,
            correlation_id=request.state.request_id,
        )
        return approval

    @app.post("/api/v1/workspaces/{workspace_id}/deletions/{deletion_request_id}/execute")
    async def api_execute_deletion_request(
        workspace_id: str,
        deletion_request_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        actor = require_actor(request, roles=platform_admin_roles)
        if not settings.deletion_enabled:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "deletion_disabled"},
            )
        backup_reference = payload.get("backup_reference")
        result = execute_deletion_request(
            session,
            workspace_id=workspace_id,
            deletion_request_id=deletion_request_id,
            output_root=str(payload.get("output_root", "./runtime")),
            storage_root=settings.storage_root,
            backup_reference=str(backup_reference) if backup_reference is not None else None,
        )
        if result is None:
            return not_found_response(
                request=request,
                message="Deletion request not found.",
                details={"workspace_id": workspace_id, "deletion_request_id": deletion_request_id},
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(actor.get("actor_id", "unknown")),
            event_type="deletion.executed",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    return app


def json_dumps_sorted(payload: dict[str, object]) -> str:
    """Serialize JSON payload deterministically for secret storage."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
