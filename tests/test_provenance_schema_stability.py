from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import backend.gateway.app as gateway_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.workers.documents import ingest_document
from tools.audit_export import export_audit_jsonl


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'provenance.db').as_posix()}",
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_query_provenance_v1_fields_are_stable(tmp_path: Path) -> None:
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_headers("local-analyst-token"),
    )
    assert response.status_code == 200
    provenance = response.json()["provenance"]
    required = {
        "provenance_version",
        "workspace_id",
        "policy_decision_id",
        "query_id",
        "build_id",
        "datasets_used",
        "snapshots",
    }
    assert required.issubset(provenance.keys())
    assert provenance["provenance_version"] == "1"
    assert provenance["workspace_id"] == "w1"
    assert provenance["datasets_used"] == ["dataset-1"]
    assert isinstance(provenance["snapshots"], list)


def test_gateway_retrieve_provenance_v1_fields_are_stable(tmp_path: Path) -> None:
    source = tmp_path / "doc.txt"
    source.write_text("invoice for dataset-1", encoding="utf-8")
    ingest_document(
        workspace_id="w1",
        source_id="s1",
        source_file=source.as_posix(),
        output_root=(tmp_path / "storage").as_posix(),
        dataset_id="dataset-1",
    )
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={"workspace_id": "w1", "query_text": "invoice"},
        headers=_headers("local-ai-reader-token"),
    )
    assert response.status_code == 200
    provenance = response.json()["provenance"]
    assert provenance["provenance_version"] == "1"
    assert provenance["workspace_id"] == "w1"
    assert provenance["datasets_used"] == ["dataset-1"]
    assert provenance["allowed_dataset_ids"] == ["dataset-1"]
    assert isinstance(provenance["citations"], list)


def test_gateway_denies_when_provenance_contract_cannot_be_built(
    tmp_path: Path, monkeypatch
) -> None:
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))

    def _raise(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("broken_provenance")

    monkeypatch.setattr(gateway_app, "build_provenance_v1", _raise)
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "provenance_unavailable"


def test_audit_export_jsonl_is_deterministic(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_headers("local-analyst-token"),
    )
    assert response.status_code == 200

    first_output = tmp_path / "audit_export_1.jsonl"
    second_output = tmp_path / "audit_export_2.jsonl"
    first_stats = export_audit_jsonl(database_url=settings.database_url, output_path=first_output)
    export_audit_jsonl(
        database_url=settings.database_url,
        output_path=second_output,
    )
    assert first_stats["total_count"] >= 2
    first_lines = first_output.read_text(encoding="utf-8").splitlines()
    second_lines = second_output.read_text(encoding="utf-8").splitlines()
    assert first_lines == second_lines
    assert all('"schema_version": "1"' in line for line in first_lines)
