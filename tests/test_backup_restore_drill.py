from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_backup_restore_drill_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/backup_restore_drill.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "PASS CHK-BACKUP-RESTORE" in result.stdout
    report = json.loads(
        (root / "runtime" / "backup_restore_drill" / "report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "pass"
    assert report["gateway_query_value"] == 42
    assert report["mask_applied"] is True
    assert report["provenance_ok"] is True
    assert report["artifact_pointer_checksum"]
    assert report["packs_registry_checksum"]
