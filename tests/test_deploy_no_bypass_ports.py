from __future__ import annotations

from pathlib import Path


def test_compose_does_not_publish_direct_query_engine_or_index_ports() -> None:
    compose = Path("deploy/docker-compose.yml").read_text(encoding="utf-8")
    assert "8080:8080" not in compose
    assert "8083:8083" not in compose
    assert "9200:9200" not in compose
    assert "6333:6333" not in compose
    assert "5432:5432" not in compose
