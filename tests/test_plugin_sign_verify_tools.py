from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_plugin_sign_and_verify_scripts_roundtrip(tmp_path: Path) -> None:
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
    sign = subprocess.run(
        [
            sys.executable,
            "tools/plugin_sign.py",
            "--registry",
            registry.as_posix(),
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
            "tools/plugin_verify.py",
            "--registry",
            registry.as_posix(),
            "--signing-key",
            "test-key",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr
