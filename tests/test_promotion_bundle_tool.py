from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_promotion_bundle_tool_signs_and_verifies(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    envelope_path = tmp_path / "promotion_bundle.json"
    envelope_path.write_text(
        json.dumps({"bundle": {"workspace_id": "w1", "bundle_schema_version": "v1"}}),
        encoding="utf-8",
    )
    sign = subprocess.run(
        [
            sys.executable,
            "tools/promotion_bundle.py",
            "sign",
            "--input",
            envelope_path.as_posix(),
            "--signing-key",
            "test-key",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sign.returncode == 0, sign.stdout + sign.stderr
    verify = subprocess.run(
        [
            sys.executable,
            "tools/promotion_bundle.py",
            "verify",
            "--input",
            envelope_path.as_posix(),
            "--signing-key",
            "test-key",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert "PASS CHK-PROMOTION-BUNDLE-VERIFY" in verify.stdout


def test_promotion_bundle_tool_detects_checksum_mismatch(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    envelope_path = tmp_path / "promotion_bundle_tamper.json"
    envelope_path.write_text(
        json.dumps({"bundle": {"workspace_id": "w1", "bundle_schema_version": "v1"}}),
        encoding="utf-8",
    )
    sign = subprocess.run(
        [
            sys.executable,
            "tools/promotion_bundle.py",
            "sign",
            "--input",
            envelope_path.as_posix(),
            "--signing-key",
            "test-key",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sign.returncode == 0, sign.stdout + sign.stderr
    payload = json.loads(envelope_path.read_text(encoding="utf-8"))
    payload["bundle"]["workspace_id"] = "tampered"
    envelope_path.write_text(json.dumps(payload), encoding="utf-8")
    verify = subprocess.run(
        [
            sys.executable,
            "tools/promotion_bundle.py",
            "verify",
            "--input",
            envelope_path.as_posix(),
            "--signing-key",
            "test-key",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 1
    assert "bundle checksum mismatch" in verify.stdout
