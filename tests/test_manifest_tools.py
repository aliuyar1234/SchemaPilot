from __future__ import annotations

from pathlib import Path

from tools.generate_manifest import generate_manifest
from tools.verify_manifest import verify_manifest


def test_manifest_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    (root / "b.txt").write_text("beta", encoding="utf-8")
    manifest = root / "MANIFEST.sha256"

    generate_manifest(root, manifest)
    assert verify_manifest(root, manifest)
