"""Runtime plugin loading helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Any, cast

ConnectorPlugin = Callable[[dict[str, object]], list[dict[str, object]]]


def load_connector_plugins(group: str = "schemapilot.connectors") -> dict[str, ConnectorPlugin]:
    """Load connector plugins from Python entry points."""
    loaded = load_plugins(group)
    connectors: dict[str, ConnectorPlugin] = {}
    for name, plugin in loaded.items():
        if not callable(plugin):
            raise TypeError(f"Connector plugin '{name}' is not callable.")
        connectors[name] = cast(ConnectorPlugin, plugin)
    return connectors


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
