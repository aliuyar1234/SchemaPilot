"""Query gateway FastAPI application."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.gateway.abac import apply_mask, evaluate_abac
from backend.gateway.executor import QueryTimeoutError, UnsafeSqlError, execute_sql
from backend.gateway.policy import AccessDecision, evaluate_access
from backend.shared_domain.audit_models import AccessDecision as AccessDecisionRow
from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.auth import authenticated_actor_from_request, load_local_auth_tokens
from backend.shared_domain.config import Settings, load_settings
from backend.shared_domain.db import get_session_factory, prepare_database
from backend.shared_domain.errors import PolicyDeniedError, SchemaPilotError
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import CatalogDataset, GovernancePolicy
from backend.shared_domain.observability import (
    increment_audit_write_failure,
    increment_cost_bytes_scanned,
    increment_policy_denial,
    log_structured_event,
    observe_query_latency,
    render_metrics,
)
from backend.shared_domain.provenance import build_provenance_v1
from backend.shared_domain.rate_limit import InMemoryActorRateLimiter
from backend.shared_domain.retrieval import load_retrieval_corpus, retrieve_documents


def create_gateway_app(settings_factory: Callable[[], Settings] = load_settings) -> FastAPI:
    """Create gateway app with deny-by-default behavior."""
    settings = settings_factory()
    settings.validate()
    session_factory = get_session_factory(settings.database_url)
    prepare_database(settings)
    auth_tokens = load_local_auth_tokens()
    rate_limiter = InMemoryActorRateLimiter(
        max_requests_per_minute=_env_int("SCHEMAPILOT_GATEWAY_MAX_REQUESTS_PER_MINUTE", 120),
        max_concurrent_per_actor=_env_int("SCHEMAPILOT_GATEWAY_MAX_CONCURRENT_PER_ACTOR", 4),
    )
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
        effective_policy_pack = _load_effective_policy_pack(
            session_factory=session_factory,
            workspace_id=workspace_id,
        )
        request_context = _request_context(payload)
        actor_dict = authenticated_actor_from_request(
            request,
            settings=settings,
            auth_tokens=auth_tokens,
        )
        policy_decision_id = new_ulid()

        if actor_dict is None:
            reason = "missing_or_invalid_auth_token"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id="unknown",
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        actor_attributes_raw = actor_dict.get("attributes", {})
        actor_attributes = actor_attributes_raw if isinstance(actor_attributes_raw, dict) else {}
        allowlisted_ai = bool(actor_attributes.get("ai_allowlisted", False))
        decision = evaluate_access(actor_dict, allow_ai=allowlisted_ai)
        if decision.result != "allow":
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result=decision.result,
                reason=decision.reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
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
        actor_id = str(actor_dict.get("actor_id", "unknown"))
        rate_limit_decision = rate_limiter.try_acquire(actor_id)
        if not rate_limit_decision.allowed:
            reason = rate_limit_decision.reason
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=actor_id,
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        resource_attributes = payload.get("resource_attributes", {})
        resource_attrs = resource_attributes if isinstance(resource_attributes, dict) else {}
        if str(actor_dict.get("actor_type", "human")) == "ai":
            dataset_id = str(resource_attrs.get("dataset_id", "")).strip()
            if not dataset_id:
                reason = "missing_dataset_context"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query"},
                    applied_filters={},
                    applied_masks={},
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={"reason": reason, "policy_decision_id": policy_decision_id},
                )
            if _dataset_belongs_to_other_workspace(
                session_factory=session_factory,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
            ):
                reason = "dataset_workspace_mismatch"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query", "dataset_id": dataset_id},
                    applied_filters={},
                    applied_masks={},
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={"reason": reason, "policy_decision_id": policy_decision_id},
                )
            allowed_raw = actor_attributes.get("allowed_dataset_ids", [])
            allowed = (
                {str(item) for item in allowed_raw} if isinstance(allowed_raw, list) else set()
            )
            if dataset_id not in allowed:
                reason = "dataset_not_allowed"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query", "dataset_id": dataset_id},
                    applied_filters={},
                    applied_masks={},
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={"reason": reason, "policy_decision_id": policy_decision_id},
                )
        abac_mode = str(payload.get("abac_mode", "internal"))
        abac = evaluate_abac(actor=actor_dict, resource_attributes=resource_attrs, mode=abac_mode)
        if not abac.allow:
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=abac.reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
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
        timeout_ms = 5000
        if isinstance(constraints, dict):
            max_rows_raw = constraints.get("max_rows", 1000)
            if isinstance(max_rows_raw, (int, float, str)):
                max_rows = int(max_rows_raw)
            timeout_raw = constraints.get("timeout_ms", 5000)
            if isinstance(timeout_raw, (int, float, str)):
                timeout_ms = int(timeout_raw)

        try:
            try:
                result_set = execute_sql(
                    query_text or "select 1 as one",
                    max_rows=max_rows,
                    row_filter=abac.row_filter,
                    timeout_ms=timeout_ms,
                    workspace_id=workspace_id,
                    storage_root=settings.storage_root,
                    query_engine=settings.query_engine,
                    trino_url=settings.trino_url,
                    trino_user=settings.trino_user,
                    trino_catalog=settings.trino_catalog,
                    trino_schema=settings.trino_schema,
                )
            except UnsafeSqlError as exc:
                reason = "sql_unsafe"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query", "query_text": query_text},
                    applied_filters=_serialize_row_filter(abac.row_filter),
                    applied_masks=abac.masks,
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={
                        "reason": reason,
                        "policy_decision_id": policy_decision_id,
                        "error": str(exc),
                    },
                ) from exc
            except QueryTimeoutError as exc:
                reason = "query_timeout"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query", "query_text": query_text},
                    applied_filters=_serialize_row_filter(abac.row_filter),
                    applied_masks=abac.masks,
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={
                        "reason": reason,
                        "policy_decision_id": policy_decision_id,
                        "error": str(exc),
                    },
                ) from exc
            except Exception as exc:  # pragma: no cover - exercised by API tests
                reason = (
                    "abac_filter_not_enforceable"
                    if abac.row_filter is not None
                    else "query_error"
                )
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query", "query_text": query_text},
                    applied_filters=_serialize_row_filter(abac.row_filter),
                    applied_masks=abac.masks,
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                if abac.row_filter is not None:
                    raise PolicyDeniedError(
                        "Access denied by ABAC",
                        details={
                            "reason": reason,
                            "policy_decision_id": policy_decision_id,
                            "error": str(exc),
                        },
                    ) from exc
                raise
        finally:
            rate_limiter.release(actor_id)

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

        datasets_used = []
        dataset_ref = resource_attrs.get("dataset_id")
        if dataset_ref is not None:
            datasets_used.append(str(dataset_ref))

        build_id = new_ulid()
        query_id = new_ulid()
        try:
            provenance = build_provenance_v1(
                workspace_id=workspace_id,
                policy_decision_id=policy_decision_id,
                query_id=query_id,
                build_id=build_id,
                datasets_used=datasets_used,
                snapshots=[],
                decision_reason="allow",
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_pack=effective_policy_pack,
            )
        except ValueError as exc:
            reason = "provenance_unavailable"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={
                    "reason": reason,
                    "policy_decision_id": policy_decision_id,
                    "error": str(exc),
                },
            ) from exc

        _record_access_decision(
            session_factory(),
            workspace_id=workspace_id,
            actor_id=str(actor_dict.get("actor_id", "unknown")),
            result="allow",
            reason="allow",
            request_context=request_context,
            resources={
                "endpoint": "query",
                "query_text": query_text,
                "dataset_ids": datasets_used,
                "policy_pack": effective_policy_pack,
            },
            applied_filters=_serialize_row_filter(abac.row_filter),
            applied_masks=abac.masks,
            policy_decision_id=policy_decision_id,
            event_type="gateway.query",
            correlation_id=request.state.request_id,
        )
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
            "provenance": provenance,
            "audit_event_id": new_ulid(),
            "request_id": request.state.request_id,
        }

    @app.post("/api/v1/gateway/retrieve")
    async def retrieve(payload: dict[str, object], request: Request) -> dict[str, object]:
        started_at = perf_counter()
        workspace_id = str(payload.get("workspace_id", "unknown"))
        effective_policy_pack = _load_effective_policy_pack(
            session_factory=session_factory,
            workspace_id=workspace_id,
        )
        request_context = _request_context(payload)
        actor_dict = authenticated_actor_from_request(
            request,
            settings=settings,
            auth_tokens=auth_tokens,
        )
        policy_decision_id = new_ulid()

        if actor_dict is None:
            reason = "missing_or_invalid_auth_token"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id="unknown",
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        attributes = actor_dict.get("attributes", {})
        attributes_dict = attributes if isinstance(attributes, dict) else {}
        actor_type = str(actor_dict.get("actor_type", "")).lower()
        allowlisted_ai = actor_type == "ai" and bool(attributes_dict.get("ai_allowlisted", False))
        decision: AccessDecision = evaluate_access(actor_dict, allow_ai=allowlisted_ai)
        if decision.result != "allow":
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=decision.reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
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
        actor_id = str(actor_dict.get("actor_id", "unknown"))
        rate_limit_decision = rate_limiter.try_acquire(actor_id)
        if not rate_limit_decision.allowed:
            reason = rate_limit_decision.reason
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=actor_id,
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        allowed_dataset_ids_raw = attributes_dict.get("allowed_dataset_ids", [])
        allowed_dataset_ids = (
            {str(item) for item in allowed_dataset_ids_raw}
            if isinstance(allowed_dataset_ids_raw, list)
            else set()
        )
        if not allowed_dataset_ids:
            reason = "missing_dataset_entitlements"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )
        cross_workspace_dataset_ids = sorted(
            dataset_id
            for dataset_id in allowed_dataset_ids
            if _dataset_belongs_to_other_workspace(
                session_factory=session_factory,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
            )
        )
        if cross_workspace_dataset_ids:
            reason = "dataset_workspace_mismatch"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={
                    "endpoint": "retrieve",
                    "cross_workspace_dataset_ids": cross_workspace_dataset_ids,
                },
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        try:
            corpus = load_retrieval_corpus(
                storage_root=settings.storage_root,
                workspace_id=workspace_id,
            )
            query_text = str(payload.get("query_text", ""))
            results = retrieve_documents(
                query_text=query_text,
                corpus=corpus,
                allowed_dataset_ids=allowed_dataset_ids,
            )
        finally:
            rate_limiter.release(actor_id)
        increment_cost_bytes_scanned(
            workspace_id=workspace_id,
            engine="retrieve",
            bytes_scanned=max(len(query_text.encode("utf-8")), 1),
        )
        observe_query_latency(
            workspace_id=workspace_id,
            engine="retrieve",
            result="allow",
            latency_ms=(perf_counter() - started_at) * 1000.0,
        )
        citations = [str(item.get("citation", "")) for item in results if item.get("citation")]
        dataset_ids = sorted({str(item.get("dataset_id", "")) for item in results})
        query_id = new_ulid()
        try:
            provenance = build_provenance_v1(
                workspace_id=workspace_id,
                policy_decision_id=policy_decision_id,
                query_id=query_id,
                build_id=new_ulid(),
                datasets_used=dataset_ids,
                snapshots=[],
                decision_reason="allow",
                applied_filters={},
                applied_masks={},
                citations=citations,
                allowed_dataset_ids=sorted(allowed_dataset_ids),
                policy_pack=effective_policy_pack,
            )
        except ValueError as exc:
            reason = "provenance_unavailable"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={
                    "reason": reason,
                    "policy_decision_id": policy_decision_id,
                    "error": str(exc),
                },
            ) from exc
        _record_access_decision(
            session_factory(),
            workspace_id=workspace_id,
            actor_id=str(actor_dict.get("actor_id", "unknown")),
            result="allow",
            reason="allow",
            request_context=request_context,
            resources={
                "endpoint": "retrieve",
                "query_text": query_text,
                "allowed_dataset_ids": sorted(allowed_dataset_ids),
                "datasets_used": dataset_ids,
                "policy_pack": effective_policy_pack,
            },
            applied_filters={},
            applied_masks={},
            policy_decision_id=policy_decision_id,
            event_type="gateway.retrieve",
            correlation_id=request.state.request_id,
        )
        return {
            "results": results,
            "provenance": provenance,
            "audit_event_id": new_ulid(),
            "request_id": request.state.request_id,
        }

    return app


def _request_context(payload: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in payload.items() if k not in {"actor", "corpus"}}


def _serialize_row_filter(row_filter: tuple[str, str] | None) -> dict[str, object]:
    if row_filter is None:
        return {}
    return {"row_filter": {"column": row_filter[0], "value": row_filter[1]}}


def _record_access_decision(
    session: Session,
    *,
    workspace_id: str,
    actor_id: str,
    result: str,
    reason: str,
    request_context: dict[str, object],
    resources: dict[str, object],
    applied_filters: Mapping[str, object],
    applied_masks: Mapping[str, object],
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
    try:
        session.add(event)
        decision = AccessDecisionRow(
            decision_id=policy_decision_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            request_context_json=request_context,
            resources_json=resources,
            result=result,
            applied_filters_json=dict(applied_filters),
            applied_masks_json=dict(applied_masks),
            audit_event_id=event.audit_event_id,
        )
        session.add(decision)
        session.commit()
    except Exception as exc:
        session.rollback()
        increment_audit_write_failure(
            workspace_id=workspace_id,
            service="gateway",
            operation=event_type,
        )
        log_structured_event(
            level="error",
            msg="audit.write_failed",
            service="gateway",
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
    finally:
        session.close()


def _dataset_belongs_to_other_workspace(
    *,
    session_factory: Callable[[], Session],
    workspace_id: str,
    dataset_id: str,
) -> bool:
    session = session_factory()
    try:
        row = session.execute(
            select(CatalogDataset.workspace_id).where(CatalogDataset.dataset_id == dataset_id)
        ).scalar_one_or_none()
    finally:
        session.close()
    if row is None:
        return False
    return str(row) != workspace_id


def _load_effective_policy_pack(
    *,
    session_factory: Callable[[], Session],
    workspace_id: str,
) -> dict[str, object] | None:
    session = session_factory()
    try:
        row = (
            session.execute(
                select(GovernancePolicy).where(
                    GovernancePolicy.workspace_id == workspace_id,
                    GovernancePolicy.policy_type == "policy_pack",
                    GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
    finally:
        session.close()
    if row is None:
        return None
    try:
        payload = json.loads(row.definition_ref)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    pack_id = str(payload.get("pack_id", "")).strip()
    version_raw = payload.get("version", 0)
    version = int(version_raw) if isinstance(version_raw, (int, float, str)) else 0
    if not pack_id:
        return None
    return {"pack_id": pack_id, "version": version}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default
