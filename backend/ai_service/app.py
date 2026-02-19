"""Optional AI service application."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.ai_service.clients import ServiceClientError, request_json
from backend.ai_service.schema_change_advisor import build_schema_evolution_proposals
from backend.ai_service.sql_agent import (
    _load_effective_semantic_manifest,
    generate_sql_agent_plan,
)
from backend.shared_domain.auth import authenticated_actor_from_request, load_local_auth_tokens
from backend.shared_domain.config import Settings, load_settings
from backend.shared_domain.db import get_session_factory, prepare_database
from backend.shared_domain.errors import (
    DisabledIntegrationError,
    PolicyDeniedError,
    SchemaPilotError,
)
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.llm_provider import load_llm_provider


def create_ai_service_app(settings_factory: Callable[[], Settings] = load_settings) -> FastAPI:
    """Create optional AI service app with fail-closed defaults."""
    settings = settings_factory()
    settings.validate()
    prepare_database(settings)
    session_factory = get_session_factory(settings.database_url)
    auth_tokens = load_local_auth_tokens()
    llm_provider = load_llm_provider(settings.ai_provider)
    app = FastAPI(title="SchemaPilot AI Service", version="0.1.0")

    @app.exception_handler(SchemaPilotError)
    async def error_handler(request: Request, exc: SchemaPilotError) -> JSONResponse:
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

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Callable):
        request.state.request_id = request.headers.get("x-request-id", new_ulid())
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    def require_ai_enabled(request: Request) -> dict[str, object]:
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
        if not settings.ai_service_enabled:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "module_disabled"},
            )
        return actor

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "ai_service",
            "enabled": settings.ai_service_enabled,
            "provider": settings.ai_provider,
        }

    @app.post("/api/v1/ai/ask-sql")
    async def ask_sql(payload: dict[str, object], request: Request) -> dict[str, object]:
        actor = require_ai_enabled(request)
        question = str(payload.get("question", "")).strip()
        workspace_id = str(payload.get("workspace_id", "")).strip()
        if not question or not workspace_id:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_question_or_workspace"},
            )
        metric_id_raw = payload.get("metric_id")
        metric_id = str(metric_id_raw).strip() if isinstance(metric_id_raw, str) else None
        group_by_raw = payload.get("group_by", [])
        group_by = [str(item) for item in group_by_raw] if isinstance(group_by_raw, list) else []
        try:
            plan = generate_sql_agent_plan(
                workspace_id=workspace_id,
                question=question,
                session_factory=session_factory,
                metric_id=metric_id,
                group_by=group_by,
            )
        except ValueError as exc:
            reason = str(exc).strip() if str(exc).strip() else "sql_agent_plan_invalid"
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason},
            ) from exc
        try:
            gateway_response = request_json(
                method="POST",
                url=f"{settings.ai_gateway_url.rstrip('/')}/api/v1/gateway/query",
                payload={
                    "workspace_id": workspace_id,
                    "query": {"language": "sql", "text": "select 1 as one"},
                    "semantic_query": plan.semantic_query,
                    "resource_attributes": {},
                },
                bearer_token=str(payload.get("gateway_token", "local-ai-reader-token")),
            )
        except ServiceClientError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "gateway_unavailable", "error": str(exc)},
            ) from exc
        result = gateway_response.get("result", {})
        rows = result.get("rows", []) if isinstance(result, dict) else []
        row_count = len(rows) if isinstance(rows, list) else 0
        return {
            "workspace_id": workspace_id,
            "question": question,
            "plan": {
                "semantic_query": plan.semantic_query,
                "confidence": plan.confidence,
                "warnings": plan.warnings,
            },
            "answer": {
                "row_count": row_count,
                "summary": f"Returned {row_count} rows.",
            },
            "provenance": gateway_response.get("provenance", {}),
            "request_id": request.state.request_id,
            "actor_id": str(actor.get("actor_id", "unknown")),
        }

    @app.post("/api/v1/ai/metric-answer")
    async def metric_answer(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        workspace_id = str(payload.get("workspace_id", "")).strip()
        metric_id = str(payload.get("metric_id", "")).strip()
        question = str(payload.get("question", "")).strip() or f"metric {metric_id}"
        group_by_raw = payload.get("group_by", [])
        group_by = [str(item) for item in group_by_raw] if isinstance(group_by_raw, list) else []
        if not workspace_id or not metric_id:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_workspace_or_metric"},
            )
        try:
            plan = generate_sql_agent_plan(
                workspace_id=workspace_id,
                question=question,
                session_factory=session_factory,
                metric_id=metric_id,
                group_by=group_by,
            )
        except ValueError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": str(exc) or "metric_plan_invalid"},
            ) from exc
        try:
            gateway_response = request_json(
                method="POST",
                url=f"{settings.ai_gateway_url.rstrip('/')}/api/v1/gateway/query",
                payload={
                    "workspace_id": workspace_id,
                    "query": {"language": "sql", "text": "select 1 as one"},
                    "semantic_query": plan.semantic_query,
                    "resource_attributes": {},
                },
                bearer_token=str(payload.get("gateway_token", "local-ai-reader-token")),
            )
        except ServiceClientError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "gateway_unavailable", "error": str(exc)},
            ) from exc
        result = gateway_response.get("result", {})
        rows = result.get("rows", []) if isinstance(result, dict) else []
        row_count = len(rows) if isinstance(rows, list) else 0
        return {
            "workspace_id": workspace_id,
            "metric_id": metric_id,
            "plan": {
                "semantic_query": plan.semantic_query,
                "confidence": plan.confidence,
                "warnings": plan.warnings,
            },
            "answer": {
                "row_count": row_count,
                "summary": f"Metric {metric_id} returned {row_count} rows.",
            },
            "provenance": gateway_response.get("provenance", {}),
        }

    @app.post("/api/v1/ai/catalog-assistant")
    async def catalog_assistant(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        workspace_id = str(payload.get("workspace_id", "")).strip()
        concept = str(payload.get("concept", "")).strip().lower()
        if not workspace_id:
            raise PolicyDeniedError(
                "Access denied by policy", details={"reason": "missing_workspace"}
            )
        try:
            datasets_response = request_json(
                method="GET",
                url=f"{settings.ai_control_plane_url.rstrip('/')}/api/v1/workspaces/{workspace_id}/datasets",
                bearer_token=str(payload.get("control_plane_token", "local-data-steward-token")),
            )
        except ServiceClientError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "control_plane_unavailable", "error": str(exc)},
            ) from exc
        datasets_raw = (
            datasets_response
            if isinstance(datasets_response, list)
            else datasets_response.get("datasets", [])
        )
        datasets: list[object] = datasets_raw if isinstance(datasets_raw, list) else []
        matches: list[dict[str, object]] = []
        for item in datasets:
            if not isinstance(item, dict):
                continue
            logical_name = str(item.get("logical_name", "")).lower()
            if concept and concept not in logical_name:
                continue
            matches.append(item)
        return {
            "workspace_id": workspace_id,
            "concept": concept,
            "matches": matches,
            "count": len(matches),
        }

    @app.post("/api/v1/ai/policy-assistant")
    async def policy_assistant(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        workspace_id = str(payload.get("workspace_id", "")).strip()
        actor_preview = payload.get("actor", {})
        resource_attributes = payload.get("resource_attributes", {})
        if not workspace_id:
            raise PolicyDeniedError(
                "Access denied by policy", details={"reason": "missing_workspace"}
            )
        try:
            simulation = request_json(
                method="POST",
                url=f"{settings.ai_gateway_url.rstrip('/')}/api/v1/gateway/policy/simulate",
                payload={
                    "workspace_id": workspace_id,
                    "actor": actor_preview,
                    "resource_attributes": resource_attributes,
                    "action": str(payload.get("action", "query")),
                },
                bearer_token=str(payload.get("gateway_token", "local-data-steward-token")),
            )
        except ServiceClientError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "gateway_unavailable", "error": str(exc)},
            ) from exc
        return {"workspace_id": workspace_id, "simulation": simulation}

    @app.post("/api/v1/ai/doc-qa")
    async def doc_qa(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        workspace_id = str(payload.get("workspace_id", "")).strip()
        question = str(payload.get("question", "")).strip()
        if not workspace_id or not question:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_question_or_workspace"},
            )
        try:
            retrieval = request_json(
                method="POST",
                url=f"{settings.ai_gateway_url.rstrip('/')}/api/v1/gateway/retrieve",
                payload={"workspace_id": workspace_id, "query_text": question},
                bearer_token=str(payload.get("gateway_token", "local-ai-reader-token")),
            )
        except ServiceClientError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "gateway_unavailable", "error": str(exc)},
            ) from exc
        snippets = retrieval.get("results", [])
        snippet_count = len(snippets) if isinstance(snippets, list) else 0
        try:
            completion = llm_provider.complete(
                system_prompt="Grounded Doc QA",
                user_prompt=f"{question}\nSnippets:{snippet_count}",
            )
        except DisabledIntegrationError as exc:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "ai_provider_disabled", "error": str(exc)},
            ) from exc
        provenance_raw = retrieval.get("provenance", {})
        provenance = provenance_raw if isinstance(provenance_raw, dict) else {}
        citations_raw = provenance.get("citations", [])
        citations = citations_raw if isinstance(citations_raw, list) else []
        return {
            "workspace_id": workspace_id,
            "question": question,
            "answer": completion,
            "citations": citations,
            "result_count": snippet_count,
        }

    @app.post("/api/v1/ai/query-debug")
    async def query_debug(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        error_payload = payload.get("gateway_error", {})
        if not isinstance(error_payload, dict):
            error_payload = {}
        code = str(error_payload.get("code", "unknown"))
        reason = (
            str(error_payload.get("details", {}).get("reason", "unknown"))
            if isinstance(error_payload.get("details"), dict)
            else "unknown"
        )
        return {
            "diagnosis": f"Gateway denied request with code={code}, reason={reason}.",
            "next_steps": [
                "Verify actor auth token and roles.",
                "Verify semantic manifest is active for AI SQL flows.",
                "Check dataset entitlements and workspace isolation.",
            ],
        }

    @app.post("/api/v1/ai/release-gate-assistant")
    async def release_gate_assistant(
        payload: dict[str, object], request: Request
    ) -> dict[str, object]:
        _ = require_ai_enabled(request)
        gate_output = str(payload.get("gate_output", "")).strip()
        summary = "Release gate passed." if "PASS" in gate_output else "Release gate failed."
        return {
            "summary": summary,
            "actions": [
                "Run check_tooling_baseline and inspect first failing command.",
                "Regenerate MANIFEST.sha256 after edits.",
                "Re-run targeted tests before full baseline.",
            ],
        }

    # AI helper endpoints with deterministic proposal payloads.
    @app.post("/api/v1/ai/join-suggestion")
    async def join_suggestion(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        return {
            "status": "proposal_created",
            "proposal_type": "relationship_proposal",
            "input": payload,
        }

    @app.post("/api/v1/ai/contract-proposer")
    async def contract_proposer(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        return {
            "status": "proposal_created",
            "proposal_type": "quality_contract_proposal",
            "input": payload,
        }

    @app.post("/api/v1/ai/drift-explainer")
    async def drift_explainer(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        return {"status": "task_created", "task_type": "drift_investigation", "input": payload}

    @app.post("/api/v1/ai/pii-explainer")
    async def pii_explainer(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        return {"status": "task_created", "task_type": "pii_review", "input": payload}

    @app.post("/api/v1/ai/er-suggestions")
    async def er_suggestions(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        return {
            "status": "proposal_created",
            "proposal_type": "er_merge_proposal",
            "input": payload,
        }

    @app.post("/api/v1/ai/semantic-generator")
    async def semantic_generator(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        return {
            "status": "proposal_created",
            "proposal_type": "semantic_manifest_proposal",
            "input": payload,
        }

    @app.post("/api/v1/ai/quality-triage")
    async def quality_triage(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        return {"status": "task_created", "task_type": "quality_triage", "input": payload}

    @app.post("/api/v1/ai/eval-generator")
    async def eval_generator(payload: dict[str, object], request: Request) -> dict[str, object]:
        _ = require_ai_enabled(request)
        questions = payload.get("questions", [])
        count = len(questions) if isinstance(questions, list) else 0
        return {"status": "generated", "question_count": count, "input": payload}

    @app.post("/api/v1/ai/schema-evolution-advisor")
    async def schema_evolution_advisor(
        payload: dict[str, object], request: Request
    ) -> dict[str, object]:
        _ = require_ai_enabled(request)
        workspace_id = str(payload.get("workspace_id", "")).strip()
        if not workspace_id:
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "missing_workspace"},
            )
        observed_raw = payload.get("observed_columns_by_entity", {})
        if not isinstance(observed_raw, dict):
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": "invalid_observed_columns"},
            )
        observed: dict[str, list[str]] = {}
        for entity_id, columns_raw in observed_raw.items():
            if not isinstance(columns_raw, list):
                continue
            observed[str(entity_id)] = [str(item) for item in columns_raw if str(item).strip()]
        semantic_manifest = _load_effective_semantic_manifest(
            session_factory=session_factory,
            workspace_id=workspace_id,
        )
        proposals = build_schema_evolution_proposals(
            semantic_manifest=semantic_manifest,
            observed_columns_by_entity=observed,
        )
        return {
            "workspace_id": workspace_id,
            "status": "proposal_only",
            "auto_apply": False,
            "proposal_count": len(proposals),
            "proposals": proposals,
        }

    return app
