from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

import backend.gateway.app as gateway_app
from backend.gateway.app import create_gateway_app
from backend.gateway.executor import QueryResult
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base, GovernancePolicy
from backend.shared_domain.semantic import semantic_manifest_checksum


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'test_gateway_dataset_entitlements.db').as_posix()}",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _manifest(workspace_id: str, *, dataset_id: str) -> dict[str, object]:
    return {
        "manifest_version": "1",
        "workspace_id": workspace_id,
        "entities": [
            {
                "entity_id": "invoice",
                "dataset_id": dataset_id,
                "primary_key": "invoice_id",
                "attributes": ["amount", "customer_id"],
            }
        ],
        "metrics": [
            {
                "metric_id": "invoice_count",
                "entity_id": "invoice",
                "aggregation": "count",
                "field": "invoice_id",
                "expression": "count(invoice_id)",
            }
        ],
        "joins": [],
    }


def _install_semantic_manifest(*, settings: Settings, workspace_id: str, dataset_id: str) -> None:
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    session_factory = get_session_factory(settings.database_url)
    manifest = _manifest(workspace_id, dataset_id=dataset_id)
    with session_factory() as session:
        session.add(
            GovernancePolicy(
                policy_id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                policy_type="semantic_manifest",
                definition_ref=json.dumps(
                    {
                        "workspace_id": workspace_id,
                        "manifest": manifest,
                        "manifest_checksum": semantic_manifest_checksum(manifest),
                        "version": 1,
                    },
                    sort_keys=True,
                ),
                status="active",
            )
        )
        session.commit()


def test_gateway_denies_ai_query_without_semantic_query(tmp_path: Path) -> None:
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"language": "sql", "text": "select 1 as one"}},
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "semantic_query_required"


def test_gateway_denies_ai_semantic_query_without_manifest(tmp_path: Path) -> None:
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "semantic_query": {"metric_id": "invoice_count"},
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "semantic_manifest_not_configured"


def test_gateway_denies_ai_query_for_unentitled_dataset(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _install_semantic_manifest(settings=settings, workspace_id="w1", dataset_id="dataset-forbidden")
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "semantic_query": {"metric_id": "invoice_count"},
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "dataset_not_allowed"


def test_gateway_denies_unknown_semantic_metric(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _install_semantic_manifest(settings=settings, workspace_id="w1", dataset_id="dataset-1")
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "semantic_query": {"metric_id": "unknown_metric"},
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "semantic_metric_not_found"


def test_gateway_allows_ai_query_for_entitled_dataset(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    _install_semantic_manifest(settings=settings, workspace_id="w1", dataset_id="dataset-1")
    captured: dict[str, str] = {}

    def _fake_execute_sql(sql: str, **kwargs) -> QueryResult:  # type: ignore[no-untyped-def]
        captured["sql"] = sql
        return QueryResult(
            columns=[{"name": "metric_value", "type": "BIGINT"}],
            rows=[[2]],
            row_count=1,
        )

    monkeypatch.setattr(gateway_app, "execute_sql", _fake_execute_sql)
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "semantic_query": {"metric_id": "invoice_count"},
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["row_count"] == 1
    assert body["provenance"]["datasets_used"] == ["dataset-1"]
    assert body["semantic"]["metric_id"] == "invoice_count"
    assert "from gold.invoice as t0" in captured["sql"].lower()
