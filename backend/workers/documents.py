"""Document ingest and extraction helpers with metadata binding."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.shared_domain.ids import new_ulid
from backend.shared_domain.retrieval import retrieve_documents as shared_retrieve_documents


@dataclass(frozen=True)
class DocumentIngestResult:
    """Document ingest output."""

    artifact_id: str
    raw_path: str
    extracted_text_path: str
    evidence_path: str
    extraction_status: str


def ingest_document(
    *,
    workspace_id: str,
    source_id: str,
    source_file: str,
    output_root: str,
    dataset_id: str,
    force_extraction_failure: bool = False,
) -> DocumentIngestResult:
    """Store raw document and extracted text/evidence with metadata binding."""
    artifact_id = new_ulid()
    artifact_root = (
        Path(output_root) / "documents" / workspace_id / source_id / f"artifact_{artifact_id}"
    )
    raw_dir = artifact_root / "raw"
    extracted_dir = artifact_root / "extracted"
    raw_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    source = Path(source_file)
    raw_path = raw_dir / source.name
    shutil.copy2(source, raw_path)
    extraction_status = "succeeded"
    extraction_error: str | None = None
    text = ""
    try:
        if force_extraction_failure:
            raise ValueError("forced_extraction_failure")
        text = source.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - exercised through tests
        extraction_status = "failed"
        extraction_error = str(exc)

    extracted_text_path = extracted_dir / "text.json"
    extracted_text_path.write_text(
        json.dumps({"text": text, "status": extraction_status}),
        encoding="utf-8",
    )
    evidence = {
        "dataset_id": dataset_id,
        "source_id": source_id,
        "artifact_id": artifact_id,
        "extraction_method": "plain_text_reader",
        "confidence": 0.7,
        "status": extraction_status,
        "error": extraction_error,
    }
    evidence_path = extracted_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return DocumentIngestResult(
        artifact_id=artifact_id,
        raw_path=raw_path.as_posix(),
        extracted_text_path=extracted_text_path.as_posix(),
        evidence_path=evidence_path.as_posix(),
        extraction_status=extraction_status,
    )


def retrieve_documents(
    *,
    query_text: str,
    corpus: list[dict[str, object]],
    allowed_dataset_ids: set[str],
) -> list[dict[str, object]]:
    """Return policy-filtered retrieval results with citations."""
    return shared_retrieve_documents(
        query_text=query_text,
        corpus=corpus,
        allowed_dataset_ids=allowed_dataset_ids,
    )
