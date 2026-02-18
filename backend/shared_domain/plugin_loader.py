"""Runtime plugin loading helpers."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any, cast

ConnectorPlugin = Callable[[dict[str, object]], list[dict[str, object]]]


@dataclass(frozen=True)
class ConnectorPluginSpec:
    """Loaded connector plugin definition."""

    name: str
    plugin: ConnectorPlugin
    entrypoint: str | None = None


def load_connector_plugins(group: str = "schemapilot.connectors") -> dict[str, ConnectorPlugin]:
    """Load connector plugins from Python entry points."""
    loaded_specs = load_connector_plugin_specs(group)
    connectors: dict[str, ConnectorPlugin] = {}
    for name, spec in loaded_specs.items():
        connectors[name] = spec.plugin
    return connectors


def load_connector_plugin_specs(
    group: str = "schemapilot.connectors",
    *,
    allowlist: set[str] | None = None,
) -> dict[str, ConnectorPluginSpec]:
    """Load connector plugin specs with allowlist enforcement."""
    allowed = allowlist if allowlist is not None else configured_plugin_allowlist()
    if not allowed:
        return {}
    loaded: dict[str, ConnectorPluginSpec] = {}
    for ep in _select_entry_points(group):
        if ep.name not in allowed:
            continue
        if ep.name in loaded:
            raise ValueError(f"Duplicate plugin entry point: {ep.name}")
        plugin_obj = ep.load()
        if not callable(plugin_obj):
            raise TypeError(f"Connector plugin '{ep.name}' is not callable.")
        loaded[ep.name] = ConnectorPluginSpec(
            name=ep.name,
            plugin=cast(ConnectorPlugin, plugin_obj),
            entrypoint=getattr(ep, "value", None),
        )
    return loaded


def configured_plugin_allowlist() -> set[str]:
    """Parse connector plugin allowlist from environment."""
    raw = os.getenv("SCHEMAPILOT_PLUGINS_ALLOWED", "")
    names = [item.strip() for item in raw.split(",") if item.strip()]
    return {name for name in names if name}


def load_plugins(group: str) -> dict[str, Any]:
    """Load arbitrary plugins keyed by entry-point name."""
    return load_plugins_from_entry_points(_select_entry_points(group))


def load_plugins_from_entry_points(entries: Iterable[EntryPoint]) -> dict[str, Any]:
    """Load plugins from entry point objects."""
    plugins: dict[str, Any] = {}
    for ep in entries:
        if ep.name in plugins:
            raise ValueError(f"Duplicate plugin entry point: {ep.name}")
        plugins[ep.name] = ep.load()
    return plugins


def _select_entry_points(group: str) -> Iterable[EntryPoint]:
    discovered = entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group=group)
    legacy = cast(Any, discovered).get(group, [])
    return cast(Iterable[EntryPoint], legacy)
