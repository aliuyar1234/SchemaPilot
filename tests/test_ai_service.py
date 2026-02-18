from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import backend.ai_service.app as ai_service_app
from backend.ai_service.app import create_ai_service_app
from backend.control_plane.repository import create_workspace
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import Base, GovernancePolicy


def _settings(tmp_path: Path, *, enabled: bool = True, provider: str = "mock") -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'ai_service.db').as_posix()}",
        ai_service_enabled=enabled,
        ai_provider=provider,
    )


def _seed_workspace_and_semantic_manifest(
    session: Session, *, workspace_name: str = "AI Service Workspace"
) -> str:
    workspace = create_workspace(
        session,
        name=workspace_name,
        profile="starter",
        security_baseline="standard",
    )
    workspace_id = str(workspace["workspace_id"])
    semantic_manifest = {
        "workspace_id": workspace_id,
        "manifest_version": "1.0.0",
        "entities": [{"entity_id": "invoice", "dataset_id": "dataset-1"}],
        "dimensions": [{"dimension_id": "region", "entity_id": "invoice"}],
        "metrics": [
            {"metric_id": "invoice_count", "entity_id": "invoice", "expression": "count(*)"}
        ],
        "joins": [],
    }
    session.add(
        GovernancePolicy(
            policy_id=new_ulid(),
            workspace_id=workspace_id,
            policy_type="semantic_manifest",
            definition_ref=json.dumps({"semantic_manifest": semantic_manifest}, sort_keys=True),
            status="active",
        )
    )
    session.flush()
    return workspace_id


def _auth_headers(token: str = "local-ai-reader-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_ai_service_denies_when_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=False, provider="disabled")
    client = TestClient(create_ai_service_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/ai/ask-sql",
        headers=_auth_headers(),
        json={"workspace_id": "w1", "question": "count invoices"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "module_disabled"


def test_ai_service_ask_sql_returns_plan_and_provenance(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True, provider="mock")
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace_id = _seed_workspace_and_semantic_manifest(session)
        session.commit()

    def fake_request_json(
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        bearer_token: str | None = None,
    ) -> dict[str, object]:
        _ = (method, payload, bearer_token)
        if url.endswith("/api/v1/gateway/query"):
            return {
                "result": {"rows": [{"invoice_count": 2}]},
                "provenance": {"provenance_version": "1"},
            }
        return {}

    original_request_json = ai_service_app.request_json
    ai_service_app.request_json = fake_request_json
    try:
        client = TestClient(create_ai_service_app(settings_factory=lambda: settings))
        response = client.post(
            "/api/v1/ai/ask-sql",
            headers=_auth_headers(),
            json={"workspace_id": workspace_id, "question": "invoice_count by region"},
        )
    finally:
        ai_service_app.request_json = original_request_json

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["semantic_query"]["metric_id"] == "invoice_count"
    assert body["provenance"]["provenance_version"] == "1"


def test_ai_service_ai_track_endpoints_return_success(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled=True, provider="mock")
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace_id = _seed_workspace_and_semantic_manifest(session)
        session.commit()

    def fake_request_json(
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        bearer_token: str | None = None,
    ) -> dict[str, object]:
        _ = (method, payload, bearer_token)
        if url.endswith("/api/v1/gateway/query"):
            return {"result": {"rows": []}, "provenance": {"provenance_version": "1"}}
        if url.endswith("/api/v1/gateway/retrieve"):
            return {
                "results": [{"dataset_id": "dataset-1", "citation": "doc://1", "snippet": "hello"}],
                "provenance": {"citations": ["doc://1"]},
            }
        if url.endswith("/api/v1/gateway/policy/simulate"):
            return {
                "result": "allow",
                "reason": "allow",
                "applied_masks": {},
                "applied_filters": {},
            }
        if url.endswith(f"/api/v1/workspaces/{workspace_id}/datasets"):
            return [{"dataset_id": "dataset-1", "logical_name": "invoices"}]
        return {}

    original_request_json = ai_service_app.request_json
    ai_service_app.request_json = fake_request_json
    try:
        client = TestClient(create_ai_service_app(settings_factory=lambda: settings))
        headers = _auth_headers()
        requests: list[tuple[str, dict[str, object]]] = [
            ("/api/v1/ai/catalog-assistant", {"workspace_id": workspace_id, "concept": "invoice"}),
            (
                "/api/v1/ai/metric-answer",
                {
                    "workspace_id": workspace_id,
                    "metric_id": "invoice_count",
                    "question": "invoice_count by region",
                    "group_by": ["region"],
                },
            ),
            (
                "/api/v1/ai/policy-assistant",
                {
                    "workspace_id": workspace_id,
                    "actor": {"actor_type": "human", "roles": ["analyst"], "attributes": {}},
                    "resource_attributes": {"dataset_id": "dataset-1"},
                },
            ),
            ("/api/v1/ai/doc-qa", {"workspace_id": workspace_id, "question": "latest invoice"}),
            (
                "/api/v1/ai/query-debug",
                {"gateway_error": {"code": "POLICY_DENIED", "details": {"reason": "dataset_not_allowed"}}},
            ),
            ("/api/v1/ai/release-gate-assistant", {"gate_output": "PASS CHK-TOOLING-BASELINE"}),
            ("/api/v1/ai/join-suggestion", {"workspace_id": workspace_id, "left": "a", "right": "b"}),
            ("/api/v1/ai/contract-proposer", {"workspace_id": workspace_id, "dataset_id": "dataset-1"}),
            ("/api/v1/ai/drift-explainer", {"workspace_id": workspace_id, "dataset_id": "dataset-1"}),
            ("/api/v1/ai/pii-explainer", {"workspace_id": workspace_id, "column": "email"}),
            ("/api/v1/ai/er-suggestions", {"workspace_id": workspace_id, "entity_id": "customer"}),
            ("/api/v1/ai/semantic-generator", {"workspace_id": workspace_id}),
            ("/api/v1/ai/quality-triage", {"workspace_id": workspace_id, "dataset_id": "dataset-1"}),
            ("/api/v1/ai/eval-generator", {"workspace_id": workspace_id, "questions": ["q1", "q2"]}),
        ]
        for path, payload in requests:
            response = client.post(path, headers=headers, json=payload)
            assert response.status_code == 200, path
    finally:
        ai_service_app.request_json = original_request_json
