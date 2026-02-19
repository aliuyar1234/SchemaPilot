from __future__ import annotations

import json
from pathlib import Path

from tools.pack_lint import validate_pack_registry
from tools.pack_migrate import migrate_registry_packs


def _write_matrix(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "matrix_version": "v1",
                "runtime_version": "0.1.0",
                "sections": {
                    "policy_packs": {
                        "current_schema_version": "v2",
                        "supported_schema_versions": ["v1", "v2"],
                    },
                    "semantic_packs": {
                        "current_schema_version": "v2",
                        "supported_schema_versions": ["v1", "v2"],
                    },
                    "template_packs": {
                        "current_schema_version": "v2",
                        "supported_schema_versions": ["v1", "v2"],
                    },
                    "connector_examples": {
                        "current_schema_version": "v1",
                        "supported_schema_versions": ["v1"],
                    },
                },
                "migrations": [
                    {
                        "section": "policy_packs",
                        "from_schema_version": "v1",
                        "to_schema_version": "v2",
                        "tool": "tools/pack_migrate.py",
                    },
                    {
                        "section": "semantic_packs",
                        "from_schema_version": "v1",
                        "to_schema_version": "v2",
                        "tool": "tools/pack_migrate.py",
                    },
                    {
                        "section": "template_packs",
                        "from_schema_version": "v1",
                        "to_schema_version": "v2",
                        "tool": "tools/pack_migrate.py",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_migrate_registry_packs_updates_schema_and_signatures(tmp_path: Path) -> None:
    signing_key = "test-signing-key"
    _write_matrix(tmp_path / "packs" / "compatibility_matrix.json")

    policy_pack = tmp_path / "packs" / "policy" / "legacy.json"
    policy_pack.parent.mkdir(parents=True, exist_ok=True)
    policy_pack.write_text(
        json.dumps(
            {
                "pack_id": "legacy-policy",
                "version": "1.0.0",
                "defaults": {"abac_mode": "strict"},
            }
        ),
        encoding="utf-8",
    )
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "registry_version": "v1",
                "policy_packs": [
                    {
                        "pack_id": "legacy-policy",
                        "version": "1.0.0",
                        "schema_version": "v1",
                        "path": "packs/policy/legacy.json",
                    }
                ],
                "semantic_packs": [],
                "template_packs": [],
                "connector_examples": [],
            }
        ),
        encoding="utf-8",
    )

    report, errors = migrate_registry_packs(
        tmp_path,
        registry_path="registry.json",
        matrix_path="packs/compatibility_matrix.json",
        signing_key=signing_key,
        key_id="test",
        write=True,
    )
    assert errors == []
    migrated_items = [item for item in report if item["status"] == "migrated"]
    assert migrated_items
    assert migrated_items[0]["artifact_before_checksum"]
    assert migrated_items[0]["artifact_after_checksum"]
    assert migrated_items[0]["diff_checksum"]

    migrated_payload = json.loads(policy_pack.read_text(encoding="utf-8"))
    assert migrated_payload["schema_version"] == "v2"
    assert migrated_payload["compatibility"]["min_runtime_version"] == "0.1.0"
    assert migrated_payload["compatibility"]["max_runtime_version"] == "0.x"

    migrated_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = migrated_registry["policy_packs"][0]
    assert entry["schema_version"] == "v2"
    assert entry["signature"]["key_id"] == "test"

    validation_errors = validate_pack_registry(
        tmp_path,
        registry_path="registry.json",
        matrix_path="packs/compatibility_matrix.json",
        signing_key=signing_key,
    )
    assert validation_errors == []


def test_migrate_registry_packs_fails_for_unsupported_source_schema(tmp_path: Path) -> None:
    _write_matrix(tmp_path / "packs" / "compatibility_matrix.json")

    policy_pack = tmp_path / "packs" / "policy" / "broken.json"
    policy_pack.parent.mkdir(parents=True, exist_ok=True)
    policy_pack.write_text(
        json.dumps(
            {
                "pack_id": "broken-policy",
                "version": "1.0.0",
                "schema_version": "v3",
                "defaults": {"abac_mode": "strict"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "registry.json").write_text(
        json.dumps(
            {
                "registry_version": "v1",
                "policy_packs": [
                    {
                        "pack_id": "broken-policy",
                        "version": "1.0.0",
                        "schema_version": "v3",
                        "path": "packs/policy/broken.json",
                    }
                ],
                "semantic_packs": [],
                "template_packs": [],
                "connector_examples": [],
            }
        ),
        encoding="utf-8",
    )

    _, errors = migrate_registry_packs(
        tmp_path,
        registry_path="registry.json",
        matrix_path="packs/compatibility_matrix.json",
        write=False,
    )
    assert any("is not supported" in error for error in errors)
