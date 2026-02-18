from __future__ import annotations

from pathlib import Path

from tools.check_no_bypass_ports import validate_no_bypass_ports


def test_deploy_artifacts_do_not_expose_bypass_ports() -> None:
    errors = validate_no_bypass_ports(Path("."))
    assert errors == []
