from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.shared_domain import plugin_loader


@dataclass(frozen=True)
class _FakeEntryPoint:
    name: str
    value: object

    def load(self) -> object:
        return self.value


def test_plugin_loader_loads_named_plugins() -> None:
    entries = [
        _FakeEntryPoint(name="foo", value=lambda scope: [{"path": "a.csv"}]),
        _FakeEntryPoint(name="bar", value=lambda scope: [{"path": "b.csv"}]),
    ]
    loaded = plugin_loader.load_plugins_from_entry_points(entries)
    assert set(loaded) == {"foo", "bar"}


def test_plugin_loader_rejects_duplicate_entry_point_names() -> None:
    entries = [
        _FakeEntryPoint(name="dup", value=lambda scope: []),
        _FakeEntryPoint(name="dup", value=lambda scope: []),
    ]
    with pytest.raises(ValueError, match="Duplicate plugin entry point"):
        plugin_loader.load_plugins_from_entry_points(entries)


def test_connector_plugin_loader_requires_callable_plugins(monkeypatch) -> None:
    entries = [_FakeEntryPoint(name="bad", value={"not": "callable"})]
    monkeypatch.setattr(plugin_loader, "_select_entry_points", lambda group: entries)
    with pytest.raises(TypeError, match="not callable"):
        plugin_loader.load_connector_plugin_specs(allowlist={"bad"})


def test_connector_plugin_loader_respects_allowlist(monkeypatch) -> None:
    entries = [
        _FakeEntryPoint(name="allowed", value=lambda scope: []),
        _FakeEntryPoint(name="blocked", value=lambda scope: []),
    ]
    monkeypatch.setattr(plugin_loader, "_select_entry_points", lambda group: entries)
    specs = plugin_loader.load_connector_plugin_specs(allowlist={"allowed"})
    assert set(specs.keys()) == {"allowed"}
