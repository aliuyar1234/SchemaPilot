"""Runtime plugin loading helpers."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, cast

from backend.shared_domain.plugin_registry import (
    DEFAULT_PLUGIN_REGISTRY_PATH,
    DEFAULT_PLUGIN_SIGNING_KEY,
    load_plugin_registry_entries,
    verify_plugin_registry_entry,
)

ConnectorPlugin = Callable[[dict[str, object]], list[dict[str, object]]]
DEFAULT_FIRST_PARTY_CONNECTOR_ALLOWLIST = {
    "google_drive",
    "hubspot_export",
    "imap",
    "jira",
    "mysql_cdc",
    "postgres_cdc",
    "sftp",
    "sharepoint",
    "smb",
    "zendesk_export",
}
BUILTIN_CONNECTOR_MODULES = {
    "google_drive": "plugins.examples.google_drive_connector",
    "hubspot_export": "plugins.examples.hubspot_export_connector",
    "imap": "plugins.examples.imap_connector",
    "jira": "plugins.examples.jira_connector",
    "mysql_cdc": "plugins.examples.mysql_cdc_connector",
    "postgres_cdc": "plugins.examples.postgres_cdc_connector",
    "sftp": "plugins.examples.sftp_connector",
    "sharepoint": "plugins.examples.sharepoint_connector",
    "smb": "plugins.examples.smb_connector",
    "zendesk_export": "plugins.examples.zendesk_export_connector",
}


@dataclass(frozen=True)
class ConnectorPluginSpec:
    """Loaded connector plugin definition."""

    name: str
    plugin: ConnectorPlugin
    entrypoint: str | None = None
    verified: bool = True
    verification_errors: tuple[str, ...] = ()


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
    workspace_profile: str | None = None,
    registry_path: str | None = None,
    signing_key: str | None = None,
    enforce_non_enterprise: bool | None = None,
    repo_root: Path | None = None,
) -> dict[str, ConnectorPluginSpec]:
    """Load connector plugin specs with allowlist enforcement."""
    allowed = allowlist if allowlist is not None else configured_plugin_allowlist()
    if not allowed:
        return {}
    normalized_profile = (
        str(workspace_profile or os.getenv("SCHEMAPILOT_PROFILE", "team")).strip().lower() or "team"
    )
    enforce_for_non_enterprise = (
        enforce_non_enterprise
        if enforce_non_enterprise is not None
        else _parse_bool_env("SCHEMAPILOT_PLUGIN_VERIFY_ENFORCE_NON_ENTERPRISE", default=False)
    )
    enforce = normalized_profile == "enterprise" or enforce_for_non_enterprise
    resolved_registry = (
        registry_path
        if registry_path is not None
        else os.getenv("SCHEMAPILOT_PLUGIN_REGISTRY_PATH", DEFAULT_PLUGIN_REGISTRY_PATH)
    )
    resolved_signing_key = (
        signing_key
        if signing_key is not None
        else os.getenv("SCHEMAPILOT_PLUGIN_SIGNING_KEY", DEFAULT_PLUGIN_SIGNING_KEY)
    )
    resolved_repo_root = repo_root or Path(__file__).resolve().parents[2]
    _ensure_repo_root_on_path(resolved_repo_root)
    registry_entries: dict[str, dict[str, object]] = {}
    registry_errors: tuple[str, ...] = ()
    if resolved_registry.strip():
        registry_entries, raw_registry_errors = load_plugin_registry_entries(
            resolved_repo_root,
            registry_path=resolved_registry,
        )
        registry_errors = tuple(raw_registry_errors)
    else:
        registry_errors = ("missing_plugin_registry_path",)

    loaded: dict[str, ConnectorPluginSpec] = {}
    seen_entrypoints: set[str] = set()
    for ep in _select_entry_points(group):
        if ep.name not in allowed:
            continue
        if ep.name in loaded:
            raise ValueError(f"Duplicate plugin entry point: {ep.name}")
        plugin_obj = ep.load()
        if not callable(plugin_obj):
            raise TypeError(f"Connector plugin '{ep.name}' is not callable.")
        runtime_entrypoint = str(getattr(ep, "value", "")).strip()
        verification_errors = list(registry_errors)
        if not verification_errors:
            verification_errors.extend(
                verify_plugin_registry_entry(
                    plugin_name=ep.name,
                    runtime_entrypoint=runtime_entrypoint,
                    registry_entry=registry_entries.get(ep.name),
                    signing_key=resolved_signing_key,
                )
            )
        verified = not verification_errors
        if enforce and not verified:
            continue
        loaded[ep.name] = ConnectorPluginSpec(
            name=ep.name,
            plugin=cast(ConnectorPlugin, plugin_obj),
            entrypoint=runtime_entrypoint or None,
            verified=verified,
            verification_errors=tuple(sorted(set(verification_errors))),
        )
        seen_entrypoints.add(ep.name)

    for plugin_name in sorted(allowed):
        if plugin_name in seen_entrypoints or plugin_name in loaded:
            continue
        module_name = BUILTIN_CONNECTOR_MODULES.get(plugin_name)
        if module_name is None:
            continue
        module = import_module(module_name)
        discover = getattr(module, "discover", None)
        if not callable(discover):
            continue
        runtime_entrypoint = f"{module_name}:discover"
        verification_errors = list(registry_errors)
        if not verification_errors:
            verification_errors.extend(
                verify_plugin_registry_entry(
                    plugin_name=plugin_name,
                    runtime_entrypoint=runtime_entrypoint,
                    registry_entry=registry_entries.get(plugin_name),
                    signing_key=resolved_signing_key,
                )
            )
        verified = not verification_errors
        if enforce and not verified:
            continue
        loaded[plugin_name] = ConnectorPluginSpec(
            name=plugin_name,
            plugin=cast(ConnectorPlugin, discover),
            entrypoint=runtime_entrypoint,
            verified=verified,
            verification_errors=tuple(sorted(set(verification_errors))),
        )
    return loaded


def configured_plugin_allowlist() -> set[str]:
    """Parse connector plugin allowlist from environment."""
    raw = os.getenv("SCHEMAPILOT_PLUGINS_ALLOWED", "")
    names = [item.strip() for item in raw.split(",") if item.strip()]
    if names:
        return {name for name in names if name}
    return set(DEFAULT_FIRST_PARTY_CONNECTOR_ALLOWLIST)


def _parse_bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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


def _ensure_repo_root_on_path(repo_root: Path) -> None:
    resolved = repo_root.resolve()
    root_text = resolved.as_posix()
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
