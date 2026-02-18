from __future__ import annotations

from pathlib import Path

from tools.generate_clients import render_generated_endpoints


def test_render_generated_endpoints_contains_core_paths() -> None:
    content = render_generated_endpoints(Path("."))
    assert "CONTROL_PLANE_PATHS" in content
    assert "GATEWAY_PATHS" in content
    assert "/api/v1/workspaces" in content
    assert "/api/v1/gateway/query" in content
