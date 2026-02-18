"""Isolated execution path for connector plugins."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any, cast

from backend.shared_domain.plugin_loader import ConnectorPluginSpec


def execute_connector_plugin(
    *,
    plugin_spec: ConnectorPluginSpec,
    scope: dict[str, object],
) -> list[dict[str, object]]:
    """Execute connector plugin with restricted environment."""
    if plugin_spec.entrypoint:
        return _run_plugin_in_subprocess(
            entrypoint=plugin_spec.entrypoint,
            scope=scope,
        )
    with _temporary_plugin_env():
        raw = plugin_spec.plugin(scope)
    return _normalize_plugin_rows(raw)


def _run_plugin_in_subprocess(
    *, entrypoint: str, scope: dict[str, object]
) -> list[dict[str, object]]:
    command = [
        sys.executable,
        "-m",
        "backend.workers.connectors.plugin_runner",
        "--entrypoint",
        entrypoint,
    ]
    try:
        process = subprocess.run(
            command,
            input=json.dumps(scope, sort_keys=True),
            text=True,
            capture_output=True,
            check=False,
            env=_safe_subprocess_env(),
            timeout=max(_plugin_max_runtime_seconds(), 1),
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("plugin_execution_failed:timeout") from exc
    if process.returncode != 0:
        error = process.stderr.strip() or process.stdout.strip() or "unknown_plugin_error"
        raise ValueError(f"plugin_execution_failed:{error}")
    try:
        parsed = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("plugin_execution_failed:invalid_json_output") from exc
    return _normalize_plugin_rows(parsed)


def _normalize_plugin_rows(raw: Any) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        raise ValueError("plugin_execution_failed:expected_list_output")
    normalized: list[dict[str, object]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        normalized.append({str(key): value for key, value in row.items()})
    return normalized


def _safe_subprocess_env() -> dict[str, str]:
    allowed = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TMP",
        "TEMP",
        "PYTHONPATH",
    }
    env: dict[str, str] = {}
    for key in allowed:
        value = os.getenv(key)
        if value is not None:
            env[key] = value
    for key, value in os.environ.items():
        if key.startswith("SCHEMAPILOT_PLUGIN_"):
            env[key] = value
    return env


def _plugin_max_runtime_seconds() -> int:
    raw = os.getenv("SCHEMAPILOT_PLUGIN_MAX_RUNTIME_SECONDS", "30")
    try:
        return int(raw.strip())
    except ValueError:
        return 30


@contextmanager
def _temporary_plugin_env() -> Iterator[None]:
    original = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(_safe_subprocess_env())
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrypoint", required=True)
    args = parser.parse_args()
    try:
        scope = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        print("invalid_scope_json", file=sys.stderr)
        return 1
    if not isinstance(scope, dict):
        print("invalid_scope_type", file=sys.stderr)
        return 1
    if not _scope_root_allowed(scope):
        print("plugin_scope_root_not_allowed", file=sys.stderr)
        return 1
    entry = EntryPoint(
        name="connector_plugin",
        value=args.entrypoint,
        group="schemapilot.connectors",
    )
    plugin = entry.load()
    if not callable(plugin):
        print("plugin_not_callable", file=sys.stderr)
        return 1
    with _temporary_plugin_env(), _network_guard():
        raw = plugin(scope)
    rows = _normalize_plugin_rows(raw)
    print(json.dumps(rows, sort_keys=True))
    return 0


def _scope_root_allowed(scope: dict[str, object]) -> bool:
    allowed_root_raw = os.getenv("SCHEMAPILOT_PLUGIN_ALLOWED_ROOT", "").strip()
    if not allowed_root_raw:
        return True
    root_path_raw = str(scope.get("root_path", "")).strip()
    if not root_path_raw:
        return False
    allowed_root = Path(allowed_root_raw).resolve()
    candidate = Path(root_path_raw).resolve()
    return candidate == allowed_root or allowed_root in candidate.parents


@contextmanager
def _network_guard() -> Iterator[None]:
    enabled = os.getenv("SCHEMAPILOT_PLUGIN_NETWORK_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if enabled:
        yield
        return
    socket_module = cast(Any, socket)
    original_socket = socket_module.socket
    original_create_connection = socket_module.create_connection

    def _deny_socket(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise OSError("plugin_network_disabled")

    def _deny_create_connection(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise OSError("plugin_network_disabled")

    socket_module.socket = _deny_socket
    socket_module.create_connection = _deny_create_connection
    try:
        yield
    finally:
        socket_module.socket = original_socket
        socket_module.create_connection = original_create_connection


if __name__ == "__main__":
    raise SystemExit(_main())
