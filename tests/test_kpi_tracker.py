from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from tools.kpi_tracker import write_kpi_report


def test_kpi_tracker_writes_weekly_and_latest_reports(tmp_path: Path) -> None:
    args = Namespace(
        week="2026-W08",
        ttfsa_minutes=22.0,
        install_success_rate=0.95,
        security_regressions=0,
        deterministic_pass_rate=1.0,
        active_contributors=4,
        issue_response_hours=10.0,
        output_root=tmp_path.as_posix(),
    )
    weekly_path = write_kpi_report(args)
    assert weekly_path.exists()
    latest_path = tmp_path / "latest.json"
    assert latest_path.exists()
    weekly = json.loads(weekly_path.read_text(encoding="utf-8"))
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert weekly["week"] == "2026-W08"
    assert weekly["kpis"]["security_regression_count"] == 0
    assert latest["kpis"]["install_success_rate"] == 0.95
