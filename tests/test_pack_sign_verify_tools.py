from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


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
                "migrations": [],
            }
        ),
        encoding="utf-8",
    )


def test_pack_sign_and_verify_scripts_roundtrip(tmp_path: Path) -> None:
    root = tmp_path
    _write_matrix(root / "packs" / "compatibility_matrix.json")
    artifact = root / "packs" / "policy" / "baseline-team.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "pack_id": "baseline-team",
                "schema_version": "v2",
                "version": "1.0.0",
                "defaults": {"abac_mode": "strict"},
                "compatibility": {"min_runtime_version": "0.1.0", "max_runtime_version": "0.x"},
            }
        ),
        encoding="utf-8",
    )
    registry = {
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
    (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    sign = subprocess.run(
        [
            sys.executable,
            "tools/pack_sign.py",
            "--registry",
            (root / "registry.json").as_posix(),
            "--matrix",
            (root / "packs" / "compatibility_matrix.json").as_posix(),
            "--signing-key",
            "test-key",
            "--key-id",
            "test",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert sign.returncode == 0, sign.stdout + sign.stderr

    verify = subprocess.run(
        [
            sys.executable,
            "tools/pack_verify.py",
            "--registry",
            (root / "registry.json").as_posix(),
            "--matrix",
            (root / "packs" / "compatibility_matrix.json").as_posix(),
            "--signing-key",
            "test-key",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr
