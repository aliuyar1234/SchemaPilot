"""CLI helpers for pack signing and verification tooling."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_REGISTRY_PATH = "packs/registry.json"
DEFAULT_MATRIX_PATH = "packs/compatibility_matrix.json"


def run_pack_verify(
    *,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    matrix_path: str = DEFAULT_MATRIX_PATH,
    signing_key: str | None = None,
) -> dict[str, object]:
    """Run pack verification tool and return structured result."""

    cmd = [
        sys.executable,
        "tools/pack_verify.py",
        "--registry",
        registry_path,
        "--matrix",
        matrix_path,
    ]
    resolved_key = _resolve_signing_key(signing_key)
    if resolved_key is not None:
        cmd.extend(["--signing-key", resolved_key])
    return _run_tool(cmd)


def run_pack_sign(
    *,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    matrix_path: str = DEFAULT_MATRIX_PATH,
    signing_key: str | None = None,
    key_id: str = "local-dev-v1",
) -> dict[str, object]:
    """Run pack signing tool and return structured result."""

    cmd = [
        sys.executable,
        "tools/pack_sign.py",
        "--registry",
        registry_path,
        "--matrix",
        matrix_path,
        "--key-id",
        key_id,
    ]
    resolved_key = _resolve_signing_key(signing_key)
    if resolved_key is not None:
        cmd.extend(["--signing-key", resolved_key])
    return _run_tool(cmd)


def _resolve_signing_key(signing_key: str | None) -> str | None:
    if signing_key is not None and signing_key.strip():
        return signing_key
    env_value = os.getenv("SCHEMAPILOT_PACK_SIGNING_KEY")
    if env_value is not None and env_value.strip():
        return env_value
    return None


def _run_tool(command: list[str]) -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    return {
        "command": command,
        "status": "ok" if result.returncode == 0 else "fail",
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
