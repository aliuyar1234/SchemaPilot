from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tools.diag_bundle_verify import verify_diag_bundle


def _write_bundle(path: Path, *, files: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)


def test_verify_diag_bundle_accepts_redacted_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "diag.zip"
    _write_bundle(
        bundle,
        files={
            "config/settings_redacted.json": json.dumps({"api_token": "<redacted>"}),
            "analysis/workspace_analysis.json": json.dumps({"workspace_id": "w1"}),
        },
    )
    violations = verify_diag_bundle(bundle.as_posix())
    assert violations == []


def test_verify_diag_bundle_flags_secret_leak(tmp_path: Path) -> None:
    bundle = tmp_path / "diag_secret.zip"
    _write_bundle(
        bundle,
        files={
            "config/settings_redacted.json": '{"database_password":"super-secret-value"}',
        },
    )
    violations = verify_diag_bundle(bundle.as_posix())
    assert any("secret-like assignment" in row for row in violations)


def test_verify_diag_bundle_flags_forbidden_raw_paths(tmp_path: Path) -> None:
    bundle = tmp_path / "diag_raw.zip"
    _write_bundle(
        bundle,
        files={
            "raw/payload.json": '{"sample":"value"}',
        },
    )
    violations = verify_diag_bundle(bundle.as_posix())
    assert any("forbidden path prefix" in row for row in violations)
