from __future__ import annotations

import json
from pathlib import Path

from backend.shared_domain.demo_scenario import generate_demo_scenario


def test_generate_demo_scenario_writes_expected_files(tmp_path: Path) -> None:
    result = generate_demo_scenario(output_root=(tmp_path / "scenario").as_posix())
    manifest_path = Path(result.manifest_path)
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario_version"] == "v1"
    assert manifest["exports"] == ["customers.csv", "invoices.csv", "tickets.csv"]
    assert manifest["documents"] == ["faq.txt", "runbook_note.txt"]
