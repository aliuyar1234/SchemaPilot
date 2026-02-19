from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cli.schemapilot_cli.main import app

runner = CliRunner()


def test_plugins_sign_and_verify_commands_roundtrip(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
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
    sign = runner.invoke(
        app,
        [
            "plugins",
            "sign",
            "--registry",
            registry.as_posix(),
            "--signing-key",
            "test-key",
            "--key-id",
            "test",
        ],
    )
    assert sign.exit_code == 0, sign.stdout
    verify = runner.invoke(
        app,
        [
            "plugins",
            "verify",
            "--registry",
            registry.as_posix(),
            "--signing-key",
            "test-key",
        ],
    )
    assert verify.exit_code == 0, verify.stdout
