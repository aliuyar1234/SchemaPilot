"""Query gateway FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.gateway.abac import apply_mask, evaluate_abac
from backend.gateway.executor import execute_sql
from backend.gateway.policy import AccessDecision, evaluate_access
from backend.shared_domain.audit_models import AccessDecision as AccessDecisionRow
from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.config import Settings, load_settings
from backend.shared_domain.db import Base, get_engine, get_session_factory
from backend.shared_domain.errors import PolicyDeniedError, SchemaPilotError
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.observability import (
    increment_cost_bytes_scanned,
    increment_policy_denial,
    log_structured_event,
    observe_query_latency,
    render_metrics,
)
from backend.shared_domain.retrieval import retrieve_documents


def create_gateway_app(settings_factory: Callable[[], Settings] = load_settings) -> FastAPI:
    """Create gateway app with deny-by-default behavior."""
    settings = settings_factory()
    settings.validate()
    session_factory = get_session_factory(settings.database_url)
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    app = FastAPI(title="SchemaPilot Gateway", version="0.1.0")

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Callable):
        request_id = request.headers.get("x-request-id", new_ulid())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        log_structured_event(
            level="info",
            msg="request.completed",
            service="gateway",
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
        return JSONResponse(
            status_code=403 if exc.error_code == "POLICY_DENIED" else 400,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": str(exc),
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
        )

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "gateway",
            "profile": settings.profile,
            "bind_address": settings.bind_address,
        }

    @app.get("/api/v1/metrics")
    async def metrics() -> Response:
        payload, media_type = render_metrics()
        return Response(content=payload, media_type=media_type)

    @app.post("/api/v1/gateway/query")
    async def query(payload: dict[str, object], request: Request) -> dict[str, object]:
        started_at = perf_counter()
        workspace_id = str(payload.get("workspace_id", "unknown"))
        actor = payload.get("actor", {})
        actor_dict = actor if isinstance(actor, dict) else {}
        decision = evaluate_access(actor_dict)
        policy_decision_id = new_ulid()
        _record_access_decision(
            session_factory(),
            workspace_id=workspace_id,
            actor_id=str(actor_dict.get("actor_id", "unknown")),
            result=decision.result,
            reason=decision.reason,
            request_context=payload,
            policy_decision_id=policy_decision_id,
            event_type="gateway.query",
            correlation_id=request.state.request_id,
        )
        if decision.result != "allow":
            increment_policy_denial(workspace_id=workspace_id, reason=decision.reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": decision.reason, "policy_decision_id": policy_decision_id},
            )
        resource_attributes = payload.get("resource_attributes", {})
        resource_attrs = resource_attributes if isinstance(resource_attributes, dict) else {}
        abac_mode = str(payload.get("abac_mode", "internal"))
        abac = evaluate_abac(actor=actor_dict, resource_attributes=resource_attrs, mode=abac_mode)
        if not abac.allow:
            increment_policy_denial(workspace_id=workspace_id, reason=abac.reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by ABAC",
                details={"reason": abac.reason, "policy_decision_id": policy_decision_id},
            )
        query_payload = payload.get("query", {})
        query_text = ""
        if isinstance(query_payload, dict):
            query_text = str(query_payload.get("text", ""))
        constraints = payload.get("constraints", {})
        max_rows = 1000
        if isinstance(constraints, dict):
            max_rows_raw = constraints.get("max_rows", 1000)
            if isinstance(max_rows_raw, (int, float, str)):
                max_rows = int(max_rows_raw)
        result_set = execute_sql(query_text or "select 1 as one", max_rows=max_rows)
        increment_cost_bytes_scanned(
            workspace_id=workspace_id,
            engine="sql",
            bytes_scanned=max(len(query_text.encode("utf-8")), 1),
        )
        masked_rows = []
        column_names = [column["name"] for column in result_set.columns]
        for row in result_set.rows:
            masked_row = []
            for idx, value in enumerate(row):
                column_name = str(column_names[idx]) if idx < len(column_names) else f"col_{idx}"
                mask_mode = abac.masks.get(column_name)
                masked_row.append(apply_mask(value, mask_mode) if mask_mode else value)
            masked_rows.append(masked_row)
        observe_query_latency(
            workspace_id=workspace_id,
            engine="sql",
            result="allow",
            latency_ms=(perf_counter() - started_at) * 1000.0,
        )

        return {
            "result": {
                "columns": result_set.columns,
                "rows": masked_rows,
                "row_count": len(masked_rows),
            },
            "provenance": {
                "datasets_used": [],
                "policy_decision_id": policy_decision_id,
                "build_id": new_ulid(),
            },
            "audit_event_id": new_ulid(),
            "request_id": request.state.request_id,
        }

    @app.post("/api/v1/gateway/retrieve")
    async def retrieve(payload: dict[str, object], request: Request) -> dict[str, object]:
        started_at = perf_counter()
        workspace_id = str(payload.get("workspace_id", "unknown"))
        actor = payload.get("actor", {})
        actor_dict = actor if isinstance(actor, dict) else {}
        attributes = actor_dict.get("attributes", {})
        attributes_dict = attributes if isinstance(attributes, dict) else {}
        actor_type = str(actor_dict.get("actor_type", "")).lower()
        allowlisted_ai = actor_type == "ai" and bool(attributes_dict.get("allowlisted", False))
        decision: AccessDecision
        if allowlisted_ai:
            decision = AccessDecision(
                result="allow",
                reason="ai_allowlisted",
                applied_filters=[],
                applied_masks=[],
            )
        else:
            decision = evaluate_access(actor_dict)
        policy_decision_id = new_ulid()
        _record_access_decision(
            session_factory(),
            workspace_id=workspace_id,
            actor_id=str(actor_dict.get("actor_id", "unknown")),
            result=decision.result,
            reason=decision.reason,
            request_context=payload,
            policy_decision_id=policy_decision_id,
            event_type="gateway.retrieve",
            correlation_id=request.state.request_id,
        )
        if decision.result != "allow":
            increment_policy_denial(workspace_id=workspace_id, reason=decision.reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": decision.reason, "policy_decision_id": policy_decision_id},
            )
        corpus_raw = payload.get("corpus", [])
        corpus = corpus_raw if isinstance(corpus_raw, list) else []
        allowed_dataset_ids_raw = attributes_dict.get("allowed_dataset_ids", [])
        allowed_dataset_ids = (
            {str(item) for item in allowed_dataset_ids_raw}
            if isinstance(allowed_dataset_ids_raw, list)
            else set()
        )
        results = retrieve_documents(
            query_text=str(payload.get("query_text", "")),
            corpus=[item for item in corpus if isinstance(item, dict)],
            allowed_dataset_ids=allowed_dataset_ids,
        )
        increment_cost_bytes_scanned(
            workspace_id=workspace_id,
            engine="retrieve",
            bytes_scanned=max(len(str(payload.get("query_text", "")).encode("utf-8")), 1),
        )
        observe_query_latency(
            workspace_id=workspace_id,
            engine="retrieve",
            result="allow",
            latency_ms=(perf_counter() - started_at) * 1000.0,
        )
        citations = [str(item.get("citation", "")) for item in results if item.get("citation")]
        dataset_ids = sorted({str(item.get("dataset_id", "")) for item in results})
        return {
            "results": results,
            "provenance": {
                "policy_decision_id": policy_decision_id,
                "datasets_used": dataset_ids,
                "citations": citations,
            },
            "audit_event_id": new_ulid(),
            "request_id": request.state.request_id,
        }

    return app


def _record_access_decision(
    session: Session,
    *,
    workspace_id: str,
    actor_id: str,
    result: str,
    reason: str,
    request_context: dict[str, object],
    policy_decision_id: str,
    event_type: str,
    correlation_id: str,
) -> None:
    """Write append-only audit and access-decision rows."""
    event = AuditEvent(
        audit_event_id=new_ulid(),
        workspace_id=workspace_id,
        actor_id=actor_id,
        event_type=event_type,
        event_json={"reason": reason},
        correlation_id=correlation_id,
    )
    session.add(event)
    decision = AccessDecisionRow(
        decision_id=policy_decision_id,
        workspace_id=workspace_id,
        actor_id=actor_id,
        request_context_json=request_context,
        resources_json={},
        result=result,
        applied_filters_json={},
        applied_masks_json={},
        audit_event_id=event.audit_event_id,
    )
    session.add(decision)
    session.commit()
    session.close()
