from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_docs_wave_files_exist_with_expected_markers() -> None:
    quickstart = _read("docs/quickstart/FIRST_HOUR.md")
    security = _read("docs/security/SECURITY_MODEL.md")
    connectors = _read("docs/connectors/CONNECTOR_GUIDE.md")
    assert "schemapilot demo-generate" in quickstart
    assert "single enforcement point" in security.lower()
    assert "plugins scaffold" in connectors
