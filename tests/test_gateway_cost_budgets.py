from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.workers.documents import ingest_document


def _settings(tmp_path: Path, *, query_max_bytes: int = 5_000_000, retrieval_max_bytes: int = 2_000_000) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_budget.db').as_posix()}",
        query_max_bytes=query_max_bytes,
        retrieval_max_bytes=retrieval_max_bytes,
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_query_budget_denies_over_limit(tmp_path: Path) -> None:
    settings = _settings(tmp_path, query_max_bytes=20)
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query",
        headers=_headers("local-analyst-token"),
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 12345678901234567890 as large_value"},
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "query_budget_exceeded"


def test_gateway_retrieval_budget_denies_over_limit(tmp_path: Path) -> None:
    source = tmp_path / "doc.txt"
    source.write_text("invoice reference", encoding="utf-8")
    ingest_document(
        workspace_id="w1",
        source_id="s1",
        source_file=source.as_posix(),
        output_root=(tmp_path / "storage").as_posix(),
        dataset_id="dataset-1",
    )
    settings = _settings(tmp_path, retrieval_max_bytes=20)
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/retrieve",
        headers=_headers("local-ai-reader-token"),
        json={"workspace_id": "w1", "query_text": "find invoice reference in dataset"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "retrieval_budget_exceeded"
