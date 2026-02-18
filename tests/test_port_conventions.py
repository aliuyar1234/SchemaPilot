from __future__ import annotations

from pathlib import Path

from backend.control_plane.main import CONTROL_PLANE_PORT
from backend.gateway.main import GATEWAY_PORT
from cli.schemapilot_cli.main import DEFAULT_API_BASE_URL


def test_port_conventions_are_consistent() -> None:
    assert CONTROL_PLANE_PORT == 8000
    assert GATEWAY_PORT == 8001
    assert DEFAULT_API_BASE_URL == "http://127.0.0.1:8000"


def test_compose_exposes_control_plane_and_gateway_ports() -> None:
    compose = Path("deploy/docker-compose.yml").read_text(encoding="utf-8")
    assert "8000:8000" in compose
    assert "8001:8001" in compose

