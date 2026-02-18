from __future__ import annotations

from pathlib import Path


def test_helm_chart_has_hardened_defaults() -> None:
    chart = Path("deploy/helm/Chart.yaml").read_text(encoding="utf-8")
    values = Path("deploy/helm/values.yaml").read_text(encoding="utf-8")
    network_policy = Path("deploy/helm/templates/networkpolicy.yaml").read_text(encoding="utf-8")
    assert "name: schemapilot" in chart
    assert "gateway" in values
    assert "NetworkPolicy" in network_policy
    assert "control-plane" in network_policy
