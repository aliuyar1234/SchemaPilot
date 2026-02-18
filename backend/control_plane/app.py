"""Control-plane FastAPI application."""

from __future__ import annotations

import json
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
    create_workspace,
    get_dataset,
    get_run,
    get_workspace,
    list_datasets,
    list_run_steps,
    list_sources,
    list_workspaces,
    update_source,
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
from backend.shared_domain.errors import PolicyDeniedError, SchemaPilotError
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
        built_in_source_types = {"filesystem", "s3", "database"}
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
        return result

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
        latest_pointer_before = load_latest_gold_pointer(
            workspace_id=workspace_id,
            storage_root=settings.storage_root,
        )
        pointer: dict[str, object] | None = None
        if gate["allowed"]:
            pointer = publish_gold_pointer(
                workspace_id=workspace_id,
                build_id=build_id,
                snapshot_id=str(payload.get("snapshot_id", build_id)),
                model_name=str(payload.get("model_name", "default_model")),
                storage_root=settings.storage_root,
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
        }
        if not gate["allowed"] and gate["reason"] == "contract_failure":
            increment_contract_failure(workspace_id=workspace_id, layer="gold")
            result_payload["contract_failure_task"] = ensure_contract_failure_review_task(
                session=session,
                workspace_id=workspace_id,
                build_id=build_id,
                failures=contract_failures,
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
        payload: dict[str, object] = {
            "workspace_id": workspace_id,
            "build_id": build_id,
            "status": "rolled_back",
            "rollback": rollback_result,
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
