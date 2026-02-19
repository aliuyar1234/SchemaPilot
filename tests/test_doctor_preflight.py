from __future__ import annotations

import json
from pathlib import Path

from cli.schemapilot_cli.doctor import remediation_for_check, run_doctor_preflight


def test_doctor_preflight_passes_with_valid_local_config(tmp_path: Path) -> None:
    config_path = tmp_path / "doctor.json"
    config_path.write_text(
        json.dumps(
            {
                "profile": "starter",
                "bind_address": "127.0.0.1",
                "auth_mode": "local",
                "database_url": f"sqlite:///{(tmp_path / 'doctor.db').as_posix()}",
                "storage_root": (tmp_path / "storage").as_posix(),
                "secrets_store_backend": "local_encrypted",
                "secrets_store_root": (tmp_path / "secrets").as_posix(),
            }
        ),
        encoding="utf-8",
    )
    report = run_doctor_preflight(config_path=config_path.as_posix())
    assert report["status"] == "ok"
    check_ids = {str(item["check_id"]) for item in report["checks"]}  # type: ignore[index]
    assert "settings.load" in check_ids
    assert "database.connectivity" in check_ids
    assert "deploy.no_bypass_ports" in check_ids
    auth_checks = [
        item
        for item in report["checks"]  # type: ignore[index]
        if str(item.get("check_id")) == "auth.configuration"
    ]
    assert len(auth_checks) == 1
    assert auth_checks[0]["category"] == "security"
    assert auth_checks[0]["remediation_id"] is None


def test_doctor_preflight_fails_when_settings_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"unknown_key": "x"}), encoding="utf-8")
    report = run_doctor_preflight(config_path=bad.as_posix())
    assert report["status"] == "fail"
    first = report["checks"][0]  # type: ignore[index]
    assert first["check_id"] == "settings.load"
    assert first["status"] == "fail"
    assert first["remediation_id"] == "DR-0001"


def test_doctor_remediation_mapping_is_stable() -> None:
    assert remediation_for_check("deploy.no_bypass_ports") == "DR-0005"
    assert remediation_for_check("target_db.health") == "DR-0008"
