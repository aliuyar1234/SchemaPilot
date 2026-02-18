from __future__ import annotations

from pathlib import Path

import pytest

from backend.workers.connectors.filesystem import discover_files


def test_filesystem_connector_discovers_by_scope(tmp_path: Path) -> None:
    data = tmp_path / "exports"
    data.mkdir()
    (data / "orders_2026.csv").write_text("id,amount\n1,10\n", encoding="utf-8")
    (data / "notes.txt").write_text("ignore", encoding="utf-8")
    archive = data / "archive"
    archive.mkdir()
    (archive / "orders_2025.csv").write_text("id,amount\n1,11\n", encoding="utf-8")

    results = discover_files(
        root_path=data.as_posix(),
        include_globs=["**/*.csv"],
        exclude_globs=["archive/**"],
    )
    assert len(results) == 1
    assert results[0].dataset_family == "orders"


def test_filesystem_connector_fails_when_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="does not exist"):
        discover_files(root_path=missing.as_posix(), include_globs=["**/*.csv"])


def test_filesystem_connector_fails_when_include_globs_empty(tmp_path: Path) -> None:
    data = tmp_path / "exports"
    data.mkdir()
    with pytest.raises(ValueError, match="include_globs"):
        discover_files(root_path=data.as_posix(), include_globs=[])
