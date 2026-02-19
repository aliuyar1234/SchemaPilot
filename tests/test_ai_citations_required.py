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


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'ai_citations_required.db').as_posix()}",
        ai_service_enabled=True,
        ai_provider="mock",
    )


def _seed_workspace_and_manifest(session: Session) -> str:
    workspace = create_workspace(
        session,
        name="AI Citations Required",
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
            {
                "metric_id": "invoice_count",
                "entity_id": "invoice",
                "expression": "count(*)",
            }
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


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-ai-reader-token"}


def test_ai_service_blocks_ask_sql_without_citations(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace_id = _seed_workspace_and_manifest(session)
        session.commit()

    def fake_request_json(
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        bearer_token: str | None = None,
        gateway_base_url: str | None = None,
        control_plane_base_url: str | None = None,
    ) -> dict[str, object]:
        _ = (
            method,
            payload,
            bearer_token,
            gateway_base_url,
            control_plane_base_url,
        )
        if url.endswith("/api/v1/gateway/query"):
            return {
                "result": {"rows": [{"invoice_count": 2}]},
                "provenance": {
                    "provenance_version": "1",
                    "workspace_id": workspace_id,
                    "policy_decision_id": "01HPOLICYAICIT0000000000",
                    "query_id": "01HQUERYAICIT000000000000",
                    "build_id": "build_ai_sql_1",
                    "datasets_used": ["dataset-1"],
                    "citations": [],
                },
            }
        return {}

    original_request_json = ai_service_app.request_json
    ai_service_app.request_json = fake_request_json
    try:
        client = TestClient(create_ai_service_app(settings_factory=lambda: settings))
        response = client.post(
            "/api/v1/ai/ask-sql",
            headers=_headers(),
            json={"workspace_id": workspace_id, "question": "invoice_count"},
        )
    finally:
        ai_service_app.request_json = original_request_json

    assert response.status_code == 403
    details = response.json()["error"]["details"]
    assert details["reason"] == "ai_citations_required"
    assert "cannot_answer_safely" in str(details["guidance"])


def test_ai_service_returns_normalized_sql_citations(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace_id = _seed_workspace_and_manifest(session)
        session.commit()

    def fake_request_json(
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        bearer_token: str | None = None,
        gateway_base_url: str | None = None,
        control_plane_base_url: str | None = None,
    ) -> dict[str, object]:
        _ = (
            method,
            payload,
            bearer_token,
            gateway_base_url,
            control_plane_base_url,
        )
        if url.endswith("/api/v1/gateway/query"):
            query_id = "01HQUERYNORM000000000000000"
            build_id = "build_norm_1"
            return {
                "result": {"rows": [{"invoice_count": 2}]},
                "provenance": {
                    "provenance_version": "1",
                    "workspace_id": workspace_id,
                    "policy_decision_id": "01HPOLICYNORM00000000000",
                    "query_id": query_id,
                    "build_id": build_id,
                    "datasets_used": ["dataset-1"],
                    "citations": [f"sp://query/{query_id}/dataset/dataset-1/build/{build_id}"],
                },
            }
        return {}

    original_request_json = ai_service_app.request_json
    ai_service_app.request_json = fake_request_json
    try:
        client = TestClient(create_ai_service_app(settings_factory=lambda: settings))
        response = client.post(
            "/api/v1/ai/ask-sql",
            headers=_headers(),
            json={"workspace_id": workspace_id, "question": "invoice_count by region"},
        )
    finally:
        ai_service_app.request_json = original_request_json

    assert response.status_code == 200
    citations = response.json()["citations"]
    assert citations
    assert citations[0]["source"] == "gateway.query"
    assert citations[0]["dataset_id"] == "dataset-1"
    assert citations[0]["query_id"] == "01HQUERYNORM000000000000000"
    assert citations[0]["build_id"] == "build_norm_1"


def test_ai_service_blocks_metric_answer_for_unauthorized_citation_dataset(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace_id = _seed_workspace_and_manifest(session)
        session.commit()

    def fake_request_json(
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        bearer_token: str | None = None,
        gateway_base_url: str | None = None,
        control_plane_base_url: str | None = None,
    ) -> dict[str, object]:
        _ = (
            method,
            payload,
            bearer_token,
            gateway_base_url,
            control_plane_base_url,
        )
        if url.endswith("/api/v1/gateway/query"):
            query_id = "01HQUERYUNAUTH0000000000000"
            build_id = "build_unauth_1"
            return {
                "result": {"rows": [{"invoice_count": 2}]},
                "provenance": {
                    "provenance_version": "1",
                    "workspace_id": workspace_id,
                    "policy_decision_id": "01HPOLICYUNAUTH000000000",
                    "query_id": query_id,
                    "build_id": build_id,
                    "datasets_used": ["dataset-2"],
                    "allowed_dataset_ids": ["dataset-1"],
                    "citations": [f"sp://query/{query_id}/dataset/dataset-2/build/{build_id}"],
                },
            }
        return {}

    original_request_json = ai_service_app.request_json
    ai_service_app.request_json = fake_request_json
    try:
        client = TestClient(create_ai_service_app(settings_factory=lambda: settings))
        response = client.post(
            "/api/v1/ai/metric-answer",
            headers=_headers(),
            json={"workspace_id": workspace_id, "metric_id": "invoice_count"},
        )
    finally:
        ai_service_app.request_json = original_request_json

    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "ai_citation_dataset_not_authorized"
