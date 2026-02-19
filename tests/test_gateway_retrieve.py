from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.gateway import app as gateway_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory, prepare_database
from backend.shared_domain.metadata_models import CatalogDataset
from backend.workers.documents import ingest_document


def _settings(
    tmp_path: Path,
    *,
    retrieval_backend: str = "filesystem",
    opensearch_enabled: bool = False,
    qdrant_enabled: bool = False,
    embeddings_provider: str = "disabled",
) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_retrieve.db').as_posix()}",
        retrieval_backend=retrieval_backend,
        opensearch_enabled=opensearch_enabled,
        opensearch_url="http://opensearch:9200",
        opensearch_index="schemapilot_docs",
        opensearch_timeout_ms=3000,
        qdrant_enabled=qdrant_enabled,
        qdrant_url="http://qdrant:6333",
        qdrant_collection="schemapilot_docs",
        qdrant_timeout_ms=3000,
        embeddings_provider=embeddings_provider,
        embeddings_dimensions=8,
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_document(tmp_path: Path, *, dataset_id: str, filename: str, text: str) -> None:
    source = tmp_path / filename
    source.write_text(text, encoding="utf-8")
    ingest_document(
        workspace_id="w1",
        source_id=f"s-{dataset_id}",
        source_file=source.as_posix(),
        output_root=(tmp_path / "storage").as_posix(),
        dataset_id=dataset_id,
    )


def _seed_document_corpus(tmp_path: Path) -> None:
    _seed_document(
        tmp_path,
        dataset_id="dataset-1",
        filename="mail.txt",
        text="invoice for customer c-1",
    )


def _seed_dataset_summary(
    settings: Settings,
    *,
    dataset_id: str,
    summary: dict[str, object],
    workspace_id: str = "w1",
) -> None:
    prepare_database(settings)
    session_factory = get_session_factory(settings.database_url)
    session = session_factory()
    try:
        session.merge(
            CatalogDataset(
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                source_id="source-1",
                logical_name=dataset_id,
                physical_locator=f"dataset://{dataset_id}",
                schema_version=1,
                sensitivity_summary_json=summary,
            )
        )
        session.commit()
    finally:
        session.close()


def test_gateway_retrieval_for_allowlisted_ai_identity(tmp_path: Path) -> None:
    _seed_document_corpus(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-1"],
            "corpus": [
                {
                    "artifact_id": "spoofed",
                    "dataset_id": "dataset-2",
                    "text": "should be ignored",
                    "citation": "artifact:spoofed",
                }
            ],
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["provenance"]["datasets_used"] == ["dataset-1"]
    assert body["provenance"]["citations"] == [body["results"][0]["citation"]]
    assert body["provenance"]["allowed_dataset_ids"] == ["dataset-1"]
    assert body["results"][0]["dataset_id"] == "dataset-1"


def test_gateway_retrieval_denies_non_allowlisted_ai(tmp_path: Path) -> None:
    _seed_document_corpus(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
        },
        headers=_auth_headers("local-ai-token"),
    )
    assert response.status_code == 403


def test_gateway_retrieval_ai_requires_dataset_ids(tmp_path: Path) -> None:
    _seed_document_corpus(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "retrieval_dataset_ids_required"


def test_gateway_retrieval_ai_rejects_unauthorized_dataset_ids(tmp_path: Path) -> None:
    _seed_document_corpus(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-2"],
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    details = response.json()["error"]["details"]
    assert details["reason"] == "dataset_not_allowed"
    assert details["unauthorized_dataset_ids"] == ["dataset-2"]


def test_gateway_retrieval_opensearch_module_disabled_fail_closed(tmp_path: Path) -> None:
    client = TestClient(
        create_gateway_app(
            settings_factory=lambda: _settings(
                tmp_path,
                retrieval_backend="opensearch",
                opensearch_enabled=False,
            )
        )
    )
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-1"],
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "module_disabled"


def test_gateway_retrieval_opensearch_backend_returns_results(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_search(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return [
            {
                "artifact_id": "artifact-1",
                "dataset_id": "dataset-1",
                "snippet": "invoice for customer c-1",
                "citation": "artifact:artifact-1",
            }
        ]

    monkeypatch.setattr(gateway_app, "search_opensearch_documents", fake_search)
    client = TestClient(
        create_gateway_app(
            settings_factory=lambda: _settings(
                tmp_path,
                retrieval_backend="opensearch",
                opensearch_enabled=True,
            )
        )
    )
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-1"],
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["dataset_id"] == "dataset-1"
    assert captured["workspace_id"] == "w1"
    assert captured["allowed_dataset_ids"] == {"dataset-1"}
    assert captured["index_name"] == "schemapilot_docs"


def test_gateway_retrieval_opensearch_unavailable_denies(monkeypatch, tmp_path: Path) -> None:
    def fake_search(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        raise gateway_app.OpenSearchUnavailableError("opensearch_unavailable")

    monkeypatch.setattr(gateway_app, "search_opensearch_documents", fake_search)
    client = TestClient(
        create_gateway_app(
            settings_factory=lambda: _settings(
                tmp_path,
                retrieval_backend="opensearch",
                opensearch_enabled=True,
            )
        )
    )
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-1"],
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "opensearch_unavailable"


def test_gateway_retrieval_qdrant_module_disabled_fail_closed(tmp_path: Path) -> None:
    client = TestClient(
        create_gateway_app(
            settings_factory=lambda: _settings(
                tmp_path,
                retrieval_backend="qdrant",
                qdrant_enabled=False,
            )
        )
    )
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-1"],
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "module_disabled"


def test_gateway_retrieval_qdrant_denies_when_embedding_provider_disabled(tmp_path: Path) -> None:
    client = TestClient(
        create_gateway_app(
            settings_factory=lambda: _settings(
                tmp_path,
                retrieval_backend="qdrant",
                qdrant_enabled=True,
                embeddings_provider="disabled",
            )
        )
    )
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-1"],
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "embedding_provider_disabled"


def test_gateway_retrieval_qdrant_backend_returns_results(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_search(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return [
            {
                "artifact_id": "artifact-1",
                "dataset_id": "dataset-1",
                "snippet": "invoice for customer c-1",
                "citation": "artifact:artifact-1",
            }
        ]

    monkeypatch.setattr(gateway_app, "search_qdrant_documents", fake_search)
    client = TestClient(
        create_gateway_app(
            settings_factory=lambda: _settings(
                tmp_path,
                retrieval_backend="qdrant",
                qdrant_enabled=True,
                embeddings_provider="hash",
            )
        )
    )
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-1"],
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["dataset_id"] == "dataset-1"
    assert captured["workspace_id"] == "w1"
    assert captured["allowed_dataset_ids"] == {"dataset-1"}
    assert captured["collection_name"] == "schemapilot_docs"
    assert isinstance(captured["query_vector"], list)
    assert len(captured["query_vector"]) == 8


def test_gateway_retrieval_denies_abac_region_mismatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "SCHEMAPILOT_LOCAL_AUTH_TOKENS",
        json.dumps(
            {
                "local-ai-region-reader-token": {
                    "actor_id": "agent:regional_ai",
                    "actor_type": "ai",
                    "roles": ["ai_agent"],
                    "attributes": {
                        "ai_allowlisted": True,
                        "allowed_dataset_ids": ["dataset-1"],
                        "region": "eu",
                    },
                }
            }
        ),
    )
    settings = _settings(tmp_path)
    _seed_document_corpus(tmp_path)
    _seed_dataset_summary(settings, dataset_id="dataset-1", summary={"region": "eu"})
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
            "dataset_ids": ["dataset-1"],
            "resource_attributes": {"region": "us"},
        },
        headers=_auth_headers("local-ai-region-reader-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "region_mismatch"


def test_gateway_retrieval_applies_metadata_row_filter_and_email_mask(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "SCHEMAPILOT_LOCAL_AUTH_TOKENS",
        json.dumps(
            {
                "local-analyst-retrieve-token": {
                    "actor_id": "user:analyst1",
                    "actor_type": "human",
                    "roles": ["analyst"],
                    "attributes": {
                        "allowed_dataset_ids": ["dataset-1", "dataset-2"],
                        "region": "eu",
                    },
                }
            }
        ),
    )
    settings = _settings(tmp_path)
    _seed_document(
        tmp_path,
        dataset_id="dataset-1",
        filename="mail_eu.txt",
        text="invoice contact alice@example.com for details",
    )
    _seed_document(
        tmp_path,
        dataset_id="dataset-2",
        filename="mail_us.txt",
        text="invoice contact bob@example.com for details",
    )
    _seed_dataset_summary(settings, dataset_id="dataset-1", summary={"region": "eu"})
    _seed_dataset_summary(settings, dataset_id="dataset-2", summary={"region": "us"})

    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
        },
        headers=_auth_headers("local-analyst-retrieve-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["dataset_id"] == "dataset-1"
    assert "alice@example.com" not in body["results"][0]["snippet"]
