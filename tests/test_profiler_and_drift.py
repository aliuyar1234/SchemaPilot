from __future__ import annotations

from pathlib import Path

from backend.workers.drift import detect_schema_drift, drift_to_review_task
from backend.workers.profiler import build_dataset_card, profile_csv_file, write_evidence_bundle


def test_profiler_and_drift_pipeline(tmp_path: Path) -> None:
    dataset = tmp_path / "customers.csv"
    dataset.write_text("id,name,email\n1,Alice,a@example.com\n2,Bob,\n", encoding="utf-8")

    evidence = profile_csv_file(dataset.as_posix(), sample_limit=100)
    evidence_path = write_evidence_bundle(
        workspace_id="w1",
        dataset_id="d1",
        evidence=evidence,
        output_root=tmp_path.as_posix(),
    )
    assert Path(evidence_path).exists()
    assert evidence.row_count_sampled == 2

    drift_event = detect_schema_drift(
        previous_columns=["id", "name"],
        current_columns=evidence.schema_columns,
    )
    assert drift_event["drift_detected"] is True
    task = drift_to_review_task(
        workspace_id="w1",
        dataset_id="d1",
        drift_event=drift_event,
    )
    assert task["blocking"] is True

    card = build_dataset_card(dataset_id="d1", evidence=evidence, drift=drift_event)
    assert card["dataset_id"] == "d1"
