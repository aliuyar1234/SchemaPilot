from __future__ import annotations

import json
from pathlib import Path

from backend.control_plane.packs.compat import evaluate_policy_pack_entry_compatibility


def _write_matrix(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "matrix_version": "v1",
                "runtime_version": "0.1.0",
                "sections": {
                    "policy_packs": {
                        "current_schema_version": "v2",
                        "supported_schema_versions": ["v1", "v2"],
                    }
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


def test_compatibility_is_unchecked_when_registry_entry_is_missing(tmp_path: Path) -> None:
    _write_matrix(tmp_path / "matrix.json")
    result = evaluate_policy_pack_entry_compatibility(
        entry=None,
        matrix_path="matrix.json",
        repo_root=tmp_path,
    )
    assert result.checked is False
    assert result.compatible is True


def test_compatibility_requires_migration_for_legacy_schema(tmp_path: Path) -> None:
    _write_matrix(tmp_path / "matrix.json")
    result = evaluate_policy_pack_entry_compatibility(
        entry={
            "pack_id": "legacy-policy",
            "schema_version": "v1",
            "semantic_schema_version": "v1",
            "compat_range": ">=0.1.0,<1.0.0",
            "migration_available": True,
        },
        matrix_path="matrix.json",
        repo_root=tmp_path,
    )
    assert result.checked is True
    assert result.compatible is False
    assert result.requires_migration is True
    assert any("migration_required:legacy-policy" in error for error in result.errors)


def test_compatibility_blocks_runtime_range_mismatch(tmp_path: Path) -> None:
    _write_matrix(tmp_path / "matrix.json")
    result = evaluate_policy_pack_entry_compatibility(
        entry={
            "pack_id": "runtime-bad-policy",
            "schema_version": "v2",
            "semantic_schema_version": "v2",
            "compat_range": ">=0.2.0,<1.0.0",
            "migration_available": False,
        },
        matrix_path="matrix.json",
        repo_root=tmp_path,
    )
    assert result.checked is True
    assert result.compatible is False
    assert result.requires_migration is False
    assert any("runtime_out_of_range:runtime-bad-policy" in error for error in result.errors)
