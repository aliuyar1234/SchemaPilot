from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from backend.shared_domain.evidence_store import load_evidence_bundle, store_evidence_bundle


def test_evidence_store_encryption_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY", "key-old")
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY_ID", "old")
    stored = store_evidence_bundle(
        workspace_id="w1",
        storage_root=tmp_path.as_posix(),
        bundle_type="test",
        payload={"secret_field": "should_not_be_plaintext"},
    )
    raw = Path(stored.path).read_text(encoding="utf-8")
    assert "should_not_be_plaintext" not in raw
    loaded = load_evidence_bundle(
        workspace_id="w1",
        evidence_id=stored.evidence_id,
        storage_root=tmp_path.as_posix(),
    )
    assert loaded["payload"]["secret_field"] == "should_not_be_plaintext"


def test_rotate_artifact_key_reencrypts_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY", "key-old")
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY_ID", "old")
    stored = store_evidence_bundle(
        workspace_id="w1",
        storage_root=tmp_path.as_posix(),
        bundle_type="rotation",
        payload={"value": "v1"},
    )
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_NEW_KEY", "key-new")
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_NEW_KEY_ID", "new")
    completed = subprocess.run(
        [
            sys.executable,
            "tools/rotate_artifact_key.py",
            "--storage-root",
            tmp_path.as_posix(),
            "--workspace-id",
            "w1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY", "key-new")
    monkeypatch.setenv("SCHEMAPILOT_ARTIFACT_ENCRYPTION_KEY_ID", "new")
    loaded = load_evidence_bundle(
        workspace_id="w1",
        evidence_id=stored.evidence_id,
        storage_root=tmp_path.as_posix(),
    )
    assert loaded["payload"]["value"] == "v1"
    envelope = json.loads(Path(stored.path).read_text(encoding="utf-8"))
    assert envelope["key_id"] == "new"
