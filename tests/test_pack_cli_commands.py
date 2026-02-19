from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cli.schemapilot_cli.main import app
from tools.pack_lint import sign_pack_registry

runner = CliRunner()


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


def test_pack_verify_command_reports_ok_for_signed_registry(tmp_path: Path) -> None:
    pack_file = tmp_path / "packs" / "policy" / "enterprise_ai_assistant.json"
    pack_file.parent.mkdir(parents=True, exist_ok=True)
    pack_file.write_text(
        json.dumps({"pack_id": "enterprise_ai_assistant", "schema_version": "v2"}),
        encoding="utf-8",
    )
    matrix_path = tmp_path / "matrix.json"
    _write_matrix(matrix_path)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "registry_version": "v1",
                "policy_packs": [
                    {
                        "pack_id": "enterprise_ai_assistant",
                        "version": "1.0.0",
                        "schema_version": "v2",
                        "path": "packs/policy/enterprise_ai_assistant.json",
                    }
                ],
                "semantic_packs": [],
                "template_packs": [],
                "connector_examples": [],
            }
        ),
        encoding="utf-8",
    )
    sign_errors = sign_pack_registry(
        tmp_path,
        registry_path="registry.json",
        matrix_path="matrix.json",
        signing_key="test-key",
        key_id="test",
    )
    assert sign_errors == []

    result = runner.invoke(
        app,
        [
            "pack",
            "verify",
            "--registry",
            registry_path.as_posix(),
            "--matrix",
            matrix_path.as_posix(),
            "--signing-key",
            "test-key",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
