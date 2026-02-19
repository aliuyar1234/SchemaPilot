from __future__ import annotations

import json
from pathlib import Path

from tools.pack_lint import sign_pack_registry, validate_pack_registry


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
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_validate_pack_registry_passes_for_repo_default() -> None:
    errors = validate_pack_registry(
        Path("."),
        registry_path="packs/registry.json",
        matrix_path="packs/compatibility_matrix.json",
    )
    assert errors == []


def test_validate_pack_registry_reports_missing_artifact(tmp_path: Path) -> None:
    _write_matrix(tmp_path / "packs" / "compatibility_matrix.json")
    registry = {
        "registry_version": "v1",
        "policy_packs": [
            {
                "pack_id": "broken",
                "version": "1.0.0",
                "schema_version": "v2",
                "path": "packs/policy/missing.json",
            }
        ],
        "semantic_packs": [],
        "template_packs": [],
        "connector_examples": [],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    errors = validate_pack_registry(
        tmp_path,
        registry_path="registry.json",
        matrix_path="packs/compatibility_matrix.json",
    )
    assert any("missing artifact" in error for error in errors)


def test_validate_pack_registry_detects_signature_tampering(tmp_path: Path) -> None:
    signing_key = "test-key"
    _write_matrix(tmp_path / "packs" / "compatibility_matrix.json")
    pack_file = tmp_path / "packs" / "policy" / "baseline-team.json"
    pack_file.parent.mkdir(parents=True, exist_ok=True)
    pack_file.write_text(
        json.dumps(
            {
                "pack_id": "baseline-team",
                "schema_version": "v2",
                "version": "1.0.0",
                "compatibility": {
                    "min_runtime_version": "0.1.0",
                    "max_runtime_version": "0.x",
                },
                "defaults": {"abac_mode": "strict"},
            }
        ),
        encoding="utf-8",
    )
    registry_payload = {
        "registry_version": "v1",
        "policy_packs": [
            {
                "pack_id": "baseline-team",
                "version": "1.0.0",
                "schema_version": "v2",
                "path": "packs/policy/baseline-team.json",
            }
        ],
        "semantic_packs": [],
        "template_packs": [],
        "connector_examples": [],
    }
    (tmp_path / "registry.json").write_text(json.dumps(registry_payload), encoding="utf-8")
    sign_errors = sign_pack_registry(
        tmp_path,
        registry_path="registry.json",
        matrix_path="packs/compatibility_matrix.json",
        signing_key=signing_key,
        key_id="test",
    )
    assert sign_errors == []
    assert (
        validate_pack_registry(
            tmp_path,
            registry_path="registry.json",
            matrix_path="packs/compatibility_matrix.json",
            signing_key=signing_key,
        )
        == []
    )

    pack_file.write_text(
        json.dumps(
            {
                "pack_id": "baseline-team",
                "schema_version": "v2",
                "version": "1.0.0",
                "compatibility": {
                    "min_runtime_version": "0.1.0",
                    "max_runtime_version": "0.x",
                },
                "defaults": {"abac_mode": "relaxed"},
            }
        ),
        encoding="utf-8",
    )
    errors = validate_pack_registry(
        tmp_path,
        registry_path="registry.json",
        matrix_path="packs/compatibility_matrix.json",
        signing_key=signing_key,
    )
    assert any("signature verification failed" in error for error in errors)


def test_validate_pack_registry_requires_declared_compat_metadata(tmp_path: Path) -> None:
    signing_key = "test-key"
    _write_matrix(tmp_path / "packs" / "compatibility_matrix.json")
    pack_file = tmp_path / "packs" / "policy" / "baseline-team.json"
    pack_file.parent.mkdir(parents=True, exist_ok=True)
    pack_file.write_text(
        json.dumps({"pack_id": "baseline-team", "schema_version": "v2", "version": "1.0.0"}),
        encoding="utf-8",
    )
    registry_payload = {
        "registry_version": "v1",
        "policy_packs": [
            {
                "pack_id": "baseline-team",
                "version": "1.0.0",
                "schema_version": "v2",
                "path": "packs/policy/baseline-team.json",
            }
        ],
        "semantic_packs": [],
        "template_packs": [],
        "connector_examples": [],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry_payload), encoding="utf-8")
    assert (
        sign_pack_registry(
            tmp_path,
            registry_path="registry.json",
            matrix_path="packs/compatibility_matrix.json",
            signing_key=signing_key,
            key_id="test",
        )
        == []
    )
    signed_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    signed_registry["policy_packs"][0].pop("compat_range", None)
    registry_path.write_text(json.dumps(signed_registry), encoding="utf-8")
    errors = validate_pack_registry(
        tmp_path,
        registry_path="registry.json",
        matrix_path="packs/compatibility_matrix.json",
        signing_key=signing_key,
    )
    assert any("missing compat_range" in error for error in errors)
