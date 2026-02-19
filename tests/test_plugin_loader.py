from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.shared_domain import plugin_loader
from backend.shared_domain.plugin_registry import sign_plugin_registry


@dataclass(frozen=True)
class _FakeEntryPoint:
    name: str
    value: object

    def load(self) -> object:
        return self.value


@dataclass(frozen=True)
class _VerifiedEntryPoint:
    name: str
    plugin: object
    value: str

    def load(self) -> object:
        return self.plugin


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


def test_connector_plugin_loader_enterprise_blocks_unsigned_plugins(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "registry_version": "v1",
                "plugins": [
                    {
                        "name": "signed",
                        "entrypoint": "plugins.examples.connector_plugin_example:discover",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    entries = [
        _VerifiedEntryPoint(
            name="signed",
            plugin=lambda scope: [],
            value="plugins.examples.connector_plugin_example:discover",
        )
    ]
    monkeypatch.setattr(plugin_loader, "_select_entry_points", lambda group: entries)
    specs = plugin_loader.load_connector_plugin_specs(
        allowlist={"signed"},
        workspace_profile="enterprise",
        registry_path=registry_path.as_posix(),
        signing_key="test-key",
        repo_root=tmp_path,
    )
    assert specs == {}


def test_connector_plugin_loader_enterprise_allows_signed_plugins(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "registry_version": "v1",
                "plugins": [
                    {
                        "name": "signed",
                        "entrypoint": "plugins.examples.connector_plugin_example:discover",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert (
        sign_plugin_registry(
            tmp_path,
            registry_path="registry.json",
            signing_key="test-key",
            key_id="test",
        )
        == []
    )
    entries = [
        _VerifiedEntryPoint(
            name="signed",
            plugin=lambda scope: [],
            value="plugins.examples.connector_plugin_example:discover",
        )
    ]
    monkeypatch.setattr(plugin_loader, "_select_entry_points", lambda group: entries)
    specs = plugin_loader.load_connector_plugin_specs(
        allowlist={"signed"},
        workspace_profile="enterprise",
        registry_path=registry_path.as_posix(),
        signing_key="test-key",
        repo_root=tmp_path,
    )
    assert set(specs.keys()) == {"signed"}
    assert specs["signed"].verified is True
