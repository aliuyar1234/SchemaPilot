from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.workers.documents import ingest_document


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_retrieve.db').as_posix()}",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_document_corpus(tmp_path: Path) -> None:
    source = tmp_path / "mail.txt"
    source.write_text("invoice for customer c-1", encoding="utf-8")
    ingest_document(
        workspace_id="w1",
        source_id="s1",
        source_file=source.as_posix(),
        output_root=(tmp_path / "storage").as_posix(),
        dataset_id="dataset-1",
    )


def test_gateway_retrieval_for_allowlisted_ai_identity(tmp_path: Path) -> None:
    _seed_document_corpus(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "query_text": "invoice",
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
