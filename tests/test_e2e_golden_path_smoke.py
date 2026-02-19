from __future__ import annotations

from pathlib import Path

from tools.e2e_golden_path import run_golden_path


def test_e2e_golden_path_smoke() -> None:
    report = run_golden_path(root=Path("."), smoke=True)
    assert report["status"] == "pass"
    assert report["provenance_version"] == "1"
    assert report["run_status"] == "succeeded"
    assert report["rollback_build_id"] == "build_old"
    assert report["provenance_target_schema_ref"] == "main"
    assert str(report["provenance_target_db_id"]).startswith("01")
