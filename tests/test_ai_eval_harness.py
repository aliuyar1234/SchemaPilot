from __future__ import annotations

import json
from pathlib import Path

from tools.ai_eval_harness import run_ai_eval_harness


def test_ai_eval_harness_smoke_passes_and_writes_report(tmp_path: Path) -> None:
    report = run_ai_eval_harness(output_root=tmp_path, smoke=True)
    assert report["status"] == "pass"
    assert report["checks"]["ask_sql_status"] == 200
    assert report["checks"]["metric_answer_status"] == 200
    assert report["checks"]["doc_qa_status"] == 200
    assert report["checks"]["policy_assistant_status"] == 200
    assert report["checks"]["eval_generator_status"] == 200
    report_path = tmp_path / "results.json"
    assert report_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["status"] == "pass"
