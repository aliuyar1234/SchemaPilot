from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_supply_chain_tools_generate_outputs(tmp_path: Path) -> None:
    sbom_path = tmp_path / "sbom.json"
    provenance_path = tmp_path / "provenance.json"
    signature_path = tmp_path / "signature.json"
    for command in (
        [sys.executable, "tools/generate_sbom.py", "--output", sbom_path.as_posix()],
        [
            sys.executable,
            "tools/generate_build_provenance.py",
            "--output",
            provenance_path.as_posix(),
        ],
        [
            sys.executable,
            "tools/sign_release_artifacts.py",
            "--output",
            signature_path.as_posix(),
            "--artifacts",
            "MANIFEST.sha256",
        ],
    ):
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    signature = json.loads(signature_path.read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert "git_commit" in provenance
    assert signature["algorithm"] == "HMAC-SHA256"
