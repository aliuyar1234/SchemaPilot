from __future__ import annotations

import json
from pathlib import Path

from tools.pack_lint import validate_pack_registry


def test_validate_pack_registry_passes_for_repo_default() -> None:
    errors = validate_pack_registry(Path("."), registry_path="packs/registry.json")
    assert errors == []


def test_validate_pack_registry_reports_missing_artifact(tmp_path: Path) -> None:
    registry = {
        "registry_version": "v1",
        "policy_packs": [
            {
                "pack_id": "broken",
                "version": "1.0.0",
                "path": "packs/policy/missing.json",
            }
        ],
        "semantic_packs": [],
        "connector_examples": [],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    errors = validate_pack_registry(tmp_path, registry_path="registry.json")
    assert any("missing artifact" in error for error in errors)
