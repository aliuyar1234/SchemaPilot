from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import CatalogDataset


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url=f"sqlite:///{(tmp_path / 'gateway_workspace_isolation.db').as_posix()}",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _insert_foreign_dataset(*, database_url: str, dataset_id: str) -> None:
    session = get_session_factory(database_url)()
    try:
        session.merge(
            CatalogDataset(
                dataset_id=dataset_id,
                workspace_id="workspace-b",
                source_id="source-b",
                logical_name="orders",
                physical_locator="/tmp/orders.csv",
                schema_version=1,
                sensitivity_summary_json={},
            )
        )
        session.commit()
    finally:
        session.close()


def test_gateway_query_denies_ai_dataset_from_other_workspace(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(
        "SCHEMAPILOT_LOCAL_AUTH_TOKENS",
        json.dumps(
            {
                "ai-cross-workspace-token": {
                    "actor_id": "agent:cross_workspace",
                    "actor_type": "ai",
                    "roles": ["ai_agent"],
                    "attributes": {
                        "ai_allowlisted": True,
                        "allowed_dataset_ids": ["dataset-cross-workspace"],
                    },
                }
            }
        ),
    )
    settings = _settings(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    _insert_foreign_dataset(
        database_url=settings.database_url, dataset_id="dataset-cross-workspace"
    )

    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "workspace-a",
            "query": {"text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-cross-workspace"},
        },
        headers=_auth_headers("ai-cross-workspace-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "dataset_workspace_mismatch"


def test_gateway_retrieve_denies_cross_workspace_dataset_entitlement(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(
        "SCHEMAPILOT_LOCAL_AUTH_TOKENS",
        json.dumps(
            {
                "ai-cross-workspace-token": {
                    "actor_id": "agent:cross_workspace",
                    "actor_type": "ai",
                    "roles": ["ai_agent"],
                    "attributes": {
                        "ai_allowlisted": True,
                        "allowed_dataset_ids": ["dataset-cross-workspace"],
                    },
                }
            }
        ),
    )
    settings = _settings(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    _insert_foreign_dataset(
        database_url=settings.database_url, dataset_id="dataset-cross-workspace"
    )

    response = client.post(
        "/api/v1/gateway/retrieve",
        json={"workspace_id": "workspace-a", "query_text": "invoice total"},
        headers=_auth_headers("ai-cross-workspace-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "dataset_workspace_mismatch"
