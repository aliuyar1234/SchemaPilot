from __future__ import annotations

from pathlib import Path

import pytest

from backend.shared_domain.plugin_loader import ConnectorPluginSpec
from backend.workers.connectors.plugin_runner import execute_connector_plugin


def _write_plugin_module(tmp_path: Path, module_name: str, body: str) -> None:
    module_path = tmp_path / f"{module_name}.py"
    module_path.write_text(body, encoding="utf-8")


def test_plugin_runner_denies_scope_outside_allowed_root(tmp_path: Path, monkeypatch) -> None:
    _write_plugin_module(
        tmp_path,
        "sandbox_plugin_a",
        "def discover(scope):\n    return []\n",
    )
    monkeypatch.setenv("PYTHONPATH", tmp_path.as_posix())
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir(parents=True, exist_ok=True)
    outside_root = tmp_path / "outside"
    outside_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SCHEMAPILOT_PLUGIN_ALLOWED_ROOT", allowed_root.as_posix())
    spec = ConnectorPluginSpec(
        name="sandbox",
        plugin=lambda scope: [],
        entrypoint="sandbox_plugin_a:discover",
    )
    with pytest.raises(ValueError, match="plugin_scope_root_not_allowed"):
        execute_connector_plugin(
            plugin_spec=spec,
            scope={"root_path": outside_root.as_posix()},
        )


def test_plugin_runner_blocks_network_when_disabled(tmp_path: Path, monkeypatch) -> None:
    _write_plugin_module(
        tmp_path,
        "sandbox_plugin_b",
        (
            "import socket\n"
            "def discover(scope):\n"
            "    socket.create_connection(('example.com', 80), timeout=1)\n"
            "    return []\n"
        ),
    )
    monkeypatch.setenv("PYTHONPATH", tmp_path.as_posix())
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SCHEMAPILOT_PLUGIN_ALLOWED_ROOT", allowed_root.as_posix())
    monkeypatch.setenv("SCHEMAPILOT_PLUGIN_NETWORK_ENABLED", "false")
    spec = ConnectorPluginSpec(
        name="sandbox-network",
        plugin=lambda scope: [],
        entrypoint="sandbox_plugin_b:discover",
    )
    with pytest.raises(ValueError, match="plugin_network_disabled"):
        execute_connector_plugin(
            plugin_spec=spec,
            scope={"root_path": allowed_root.as_posix()},
        )
