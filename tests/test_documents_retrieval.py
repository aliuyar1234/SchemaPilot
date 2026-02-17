from __future__ import annotations

from pathlib import Path

from backend.workers.documents import ingest_document, retrieve_documents


def test_document_ingest_writes_metadata_bound_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "mail.txt"
    source.write_text("Invoice 100 for customer C-1", encoding="utf-8")
    result = ingest_document(
        workspace_id="w1",
        source_id="s1",
        source_file=source.as_posix(),
        output_root=tmp_path.as_posix(),
        dataset_id="dataset-1",
    )
    assert Path(result.raw_path).exists()
    assert Path(result.evidence_path).exists()
    assert result.extraction_status == "succeeded"


def test_document_ingest_preserves_raw_on_extraction_failure(tmp_path: Path) -> None:
    source = tmp_path / "mail.txt"
    source.write_text("Invoice 100 for customer C-1", encoding="utf-8")
    result = ingest_document(
        workspace_id="w1",
        source_id="s1",
        source_file=source.as_posix(),
        output_root=tmp_path.as_posix(),
        dataset_id="dataset-1",
        force_extraction_failure=True,
    )
    assert Path(result.raw_path).exists()
    assert result.extraction_status == "failed"
    evidence_text = Path(result.evidence_path).read_text(encoding="utf-8")
    assert '"status": "failed"' in evidence_text


def test_retrieval_respects_dataset_policy_filter() -> None:
    corpus = [
        {
            "artifact_id": "a1",
            "dataset_id": "dataset-1",
            "text": "invoice for customer c-1",
            "citation": "artifact:a1",
        },
        {
            "artifact_id": "a2",
            "dataset_id": "dataset-2",
            "text": "invoice for customer c-2",
            "citation": "artifact:a2",
        },
    ]
    results = retrieve_documents(
        query_text="customer",
        corpus=corpus,
        allowed_dataset_ids={"dataset-1"},
    )
    assert len(results) == 1
    assert results[0]["dataset_id"] == "dataset-1"
