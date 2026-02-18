from __future__ import annotations

import json
import mailbox
from pathlib import Path

from backend.workers.connectors.documents import discover_document_files
from backend.workers.documents import ingest_document


def test_document_connector_discovers_supported_document_extensions(tmp_path: Path) -> None:
    exports = tmp_path / "docs"
    exports.mkdir(parents=True, exist_ok=True)
    (exports / "a.pdf").write_bytes(b"%PDF-1.4\n(Invoice)\n%%EOF")
    (exports / "b.eml").write_text("Subject: hello\n\nbody", encoding="utf-8")
    (exports / "c.mbox").write_text("", encoding="utf-8")
    (exports / "skip.csv").write_text("id,value\n1,a\n", encoding="utf-8")
    discovered = discover_document_files(root_path=exports.as_posix())
    names = sorted(Path(item.path).name for item in discovered)
    assert names == ["a.pdf", "b.eml", "c.mbox"]


def test_ingest_eml_extracts_subject_and_body_with_confidence(tmp_path: Path) -> None:
    source = tmp_path / "mail.eml"
    source.write_text(
        "Subject: Invoice Reminder\nFrom: bot@example.com\n\nInvoice 101 is due soon.",
        encoding="utf-8",
    )
    result = ingest_document(
        workspace_id="w1",
        source_id="s1",
        source_file=source.as_posix(),
        output_root=tmp_path.as_posix(),
        dataset_id="dataset-1",
    )
    assert result.extraction_status == "succeeded"
    payload = json.loads(Path(result.extracted_text_path).read_text(encoding="utf-8"))
    assert payload["extraction_method"] == "email_parser"
    assert "Invoice Reminder" in payload["text"]
    evidence = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
    assert evidence["confidence_label"] == "high"
    assert evidence["status"] == "succeeded"


def test_ingest_mbox_extracts_message_content(tmp_path: Path) -> None:
    source = tmp_path / "tickets.mbox"
    box = mailbox.mbox(source.as_posix())
    try:
        message = mailbox.mboxMessage()
        message["Subject"] = "Ticket Opened"
        message.set_payload("Customer reported issue in checkout flow.")
        box.add(message)
        box.flush()
    finally:
        box.close()

    result = ingest_document(
        workspace_id="w1",
        source_id="s1",
        source_file=source.as_posix(),
        output_root=tmp_path.as_posix(),
        dataset_id="dataset-1",
    )
    assert result.extraction_status == "succeeded"
    payload = json.loads(Path(result.extracted_text_path).read_text(encoding="utf-8"))
    assert payload["extraction_method"] == "mbox_parser"
    assert "Ticket Opened" in payload["text"]


def test_ingest_pdf_fails_closed_on_invalid_signature(tmp_path: Path) -> None:
    source = tmp_path / "corrupt.pdf"
    source.write_text("not-a-real-pdf", encoding="utf-8")
    result = ingest_document(
        workspace_id="w1",
        source_id="s1",
        source_file=source.as_posix(),
        output_root=tmp_path.as_posix(),
        dataset_id="dataset-1",
    )
    assert Path(result.raw_path).exists()
    assert result.extraction_status == "failed"
    evidence = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
    assert evidence["status"] == "failed"
    assert evidence["error"] == "invalid_pdf_signature"
    assert evidence["confidence_label"] == "low"
