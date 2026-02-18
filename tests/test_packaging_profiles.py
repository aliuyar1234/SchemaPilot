from __future__ import annotations

from pathlib import Path


def test_compose_includes_progressive_profiles() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = (root / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "starter" in compose
    assert "team" in compose
    assert "enterprise" in compose
    assert "profiles" in compose


def test_optional_k8s_skeleton_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    required = [
        root / "deploy" / "k8s" / "namespace.yaml",
        root / "deploy" / "k8s" / "control-plane-deployment.yaml",
        root / "deploy" / "k8s" / "gateway-deployment.yaml",
        root / "deploy" / "k8s" / "ui-deployment.yaml",
    ]
    for path in required:
        assert path.exists()


def test_dashboard_definition_references_observability_metrics() -> None:
    root = Path(__file__).resolve().parents[1]
    dashboard = (root / "deploy" / "dashboards" / "schemapilot_overview.json").read_text(
        encoding="utf-8"
    )
    assert "schemapilot_query_latency_ms" in dashboard
    assert "schemapilot_policy_denials_total" in dashboard
