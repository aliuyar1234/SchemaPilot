from __future__ import annotations

from pathlib import Path

import pytest

from backend.workers.connectors.dropzone import discover_dropzone_files


def test_dropzone_discovers_supported_export_files(tmp_path: Path) -> None:
    root = tmp_path / "dropzone"
    root.mkdir(parents=True, exist_ok=True)
    (root / "invoices.csv").write_text("id,amount\n1,10\n", encoding="utf-8")
    (root / "customers.json").write_text('{"customers":[]}\n', encoding="utf-8")
    (root / "notes.txt").write_text("ignore", encoding="utf-8")

    discovered = discover_dropzone_files(root_path=root.as_posix())
    names = [Path(item.path).name for item in discovered]
    assert names == ["customers.json", "invoices.csv"]


def test_dropzone_required_files_missing_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "dropzone"
    root.mkdir(parents=True, exist_ok=True)
    (root / "invoices.csv").write_text("id,amount\n1,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="dropzone_required_files_missing"):
        discover_dropzone_files(
            root_path=root.as_posix(),
            required_files=["invoices.csv", "customers.csv"],
        )
