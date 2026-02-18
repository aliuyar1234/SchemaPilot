"""Document ingest and extraction helpers with metadata binding."""

from __future__ import annotations

import json
import mailbox
import re
import shutil
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
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
    extraction_method = "plain_text_reader"
    confidence = 0.0
    try:
        if force_extraction_failure:
            raise ValueError("forced_extraction_failure")
        text, extraction_method, confidence = _extract_document_text(source)
    except Exception as exc:  # pragma: no cover - exercised through tests
        extraction_status = "failed"
        extraction_error = str(exc)
        confidence = 0.0
        extraction_method = "failed_extraction"

    extracted_text_path = extracted_dir / "text.json"
    extracted_text_path.write_text(
        json.dumps(
            {
                "text": text,
                "status": extraction_status,
                "extraction_method": extraction_method,
                "confidence": confidence,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    evidence = {
        "dataset_id": dataset_id,
        "source_id": source_id,
        "artifact_id": artifact_id,
        "source_extension": source.suffix.lower(),
        "extraction_method": extraction_method,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "status": extraction_status,
        "error": extraction_error,
        "text_length": len(text),
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


def _extract_document_text(source: Path) -> tuple[str, str, float]:
    extension = source.suffix.lower()
    if extension == ".pdf":
        text = _extract_pdf_text(source)
        return text, "pdf_text_scanner", 0.55 if text.strip() else 0.2
    if extension == ".eml":
        text = _extract_eml_text(source)
        return text, "email_parser", 0.85 if text.strip() else 0.4
    if extension == ".mbox":
        text = _extract_mbox_text(source)
        return text, "mbox_parser", 0.8 if text.strip() else 0.35
    if extension in {"", ".txt", ".csv", ".json", ".md"}:
        text = source.read_text(encoding="utf-8", errors="ignore")
        return text, "plain_text_reader", 0.9 if text.strip() else 0.5
    raise ValueError(f"unsupported_document_type:{extension}")


def _extract_pdf_text(source: Path) -> str:
    payload = source.read_bytes()
    if not payload.startswith(b"%PDF"):
        raise ValueError("invalid_pdf_signature")
    matches = re.findall(rb"[A-Za-z0-9][A-Za-z0-9 ,.;:_/\\-]{2,}", payload)
    if not matches:
        return ""
    return "\n".join(match.decode("utf-8", errors="ignore").strip() for match in matches).strip()


def _extract_eml_text(source: Path) -> str:
    message = BytesParser(policy=policy.default).parsebytes(source.read_bytes())
    parts: list[str] = []
    subject = str(message.get("subject", "")).strip()
    if subject:
        parts.append(subject)
    if message.is_multipart():
        for item in message.walk():
            if item.get_content_maintype() == "multipart":
                continue
            content_type = item.get_content_type()
            if content_type != "text/plain":
                continue
            body = item.get_content()
            if isinstance(body, str) and body.strip():
                parts.append(body.strip())
    else:
        content = message.get_content()
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
    return "\n".join(parts).strip()


def _extract_mbox_text(source: Path) -> str:
    box = mailbox.mbox(source.as_posix())
    parts: list[str] = []
    try:
        for idx, message in enumerate(box):
            if idx >= 25:
                break
            subject = str(message.get("subject", "")).strip()
            if subject:
                parts.append(subject)
            payload = message.get_payload(decode=True)
            if isinstance(payload, bytes):
                body = payload.decode("utf-8", errors="ignore").strip()
                if body:
                    parts.append(body)
            elif isinstance(payload, str):
                body = payload.strip()
                if body:
                    parts.append(body)
    finally:
        box.close()
    return "\n".join(parts).strip()


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"
