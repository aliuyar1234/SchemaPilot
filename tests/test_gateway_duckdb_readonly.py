from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.gold_pointer import publish_gold_pointer


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_reads_published_gold_metrics_from_duckdb(tmp_path) -> None:
    storage_root = tmp_path / "storage"
    metrics_path = (
        storage_root / "gold" / "w1" / "orders" / "snapshots" / "snap-1" / "metrics.json"
    )
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps([{"metric": "sum_amount", "value": 2100.5}], indent=2),
        encoding="utf-8",
    )
    publish_gold_pointer(
        workspace_id="w1",
        build_id="build-1",
        snapshot_id="snap-1",
        model_name="orders",
        storage_root=storage_root.as_posix(),
    )
    settings = Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=storage_root.as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_duckdb.db').as_posix()}",
    )
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))

    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select metric, value from gold.fact_metrics"},
        },
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"][0][0] == "sum_amount"
    assert float(body["result"]["rows"][0][1]) == 2100.5


def test_gateway_denies_external_file_scan_functions_in_sql(tmp_path) -> None:
    settings = Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_duckdb_deny.db').as_posix()}",
    )
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))

    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select * from read_csv_auto('secret.csv')"},
        },
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "sql_unsafe"
