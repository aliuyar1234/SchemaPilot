from __future__ import annotations

import json
from pathlib import Path

from backend.shared_domain.plugin_registry import (
    load_plugin_registry_entries,
    sign_plugin_registry,
    validate_plugin_registry,
    verify_plugin_registry_entry,
)


def _write_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "registry_version": "v1",
                "plugins": [
                    {
                        "name": "custom",
                        "entrypoint": "plugins.examples.connector_plugin_example:discover",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_sign_and_validate_plugin_registry_roundtrip(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path)
    sign_errors = sign_plugin_registry(
        tmp_path,
        registry_path="registry.json",
        signing_key="test-key",
        key_id="test",
    )
    assert sign_errors == []
    validate_errors = validate_plugin_registry(
        tmp_path,
        registry_path="registry.json",
        signing_key="test-key",
    )
    assert validate_errors == []


def test_verify_plugin_registry_entry_detects_entrypoint_mismatch(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path)
    assert (
        sign_plugin_registry(
            tmp_path,
            registry_path="registry.json",
            signing_key="test-key",
            key_id="test",
        )
        == []
    )
    entries, errors = load_plugin_registry_entries(tmp_path, registry_path="registry.json")
    assert errors == []
    verification_errors = verify_plugin_registry_entry(
        plugin_name="custom",
        runtime_entrypoint="plugins.examples.connector_plugin_example:discover_v2",
        registry_entry=entries["custom"],
        signing_key="test-key",
    )
    assert "entrypoint_mismatch:custom" in verification_errors
