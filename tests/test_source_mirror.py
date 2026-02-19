from __future__ import annotations

from pathlib import Path

from backend.shared_domain.source_mirror import (
    build_source_snapshot_manifest,
    load_latest_source_snapshot_manifest,
    persist_source_snapshot_manifest,
    source_snapshot_changed,
)


def test_source_snapshot_manifest_is_deterministic_for_same_rows(tmp_path: Path) -> None:
    rows = [
        {
            "path": "b.csv",
            "size_bytes": 12,
            "mtime_epoch": 10.0,
            "content_hash_sample": "bbb",
            "dataset_family": "orders",
        },
        {
            "path": "a.csv",
            "size_bytes": 8,
            "mtime_epoch": 9.0,
            "content_hash_sample": "aaa",
            "dataset_family": "orders",
        },
    ]
    manifest_a = build_source_snapshot_manifest(
        workspace_id="w1",
        source_id="s1",
        source_type="dropzone",
        root_path=tmp_path.as_posix(),
        cursor_before="",
        cursor_after="10.000:a.csv",
        rows=rows,
        strict_mode=True,
        generated_epoch=100,
    )
    manifest_b = build_source_snapshot_manifest(
        workspace_id="w1",
        source_id="s1",
        source_type="dropzone",
        root_path=tmp_path.as_posix(),
        cursor_before="",
        cursor_after="10.000:a.csv",
        rows=list(reversed(rows)),
        strict_mode=True,
        generated_epoch=200,
    )
    assert manifest_a["snapshot_checksum"] == manifest_b["snapshot_checksum"]


def test_source_snapshot_persist_and_changed_detection(tmp_path: Path) -> None:
    storage_root = (tmp_path / "storage").as_posix()
    first = build_source_snapshot_manifest(
        workspace_id="w2",
        source_id="s2",
        source_type="filesystem",
        root_path="/exports",
        cursor_before="",
        cursor_after="1.000:file.csv",
        rows=[
            {
                "path": "file.csv",
                "size_bytes": 12,
                "mtime_epoch": 1.0,
                "content_hash_sample": "h1",
                "dataset_family": "file",
            }
        ],
        strict_mode=True,
        generated_epoch=1,
    )
    persisted = persist_source_snapshot_manifest(storage_root=storage_root, manifest=first)
    assert persisted["snapshot_path"].endswith(".json")
    latest = load_latest_source_snapshot_manifest(
        storage_root=storage_root,
        workspace_id="w2",
        source_id="s2",
    )
    assert latest is not None
    assert source_snapshot_changed(previous=latest, current=first) is False
    second = build_source_snapshot_manifest(
        workspace_id="w2",
        source_id="s2",
        source_type="filesystem",
        root_path="/exports",
        cursor_before="1.000:file.csv",
        cursor_after="2.000:file.csv",
        rows=[
            {
                "path": "file.csv",
                "size_bytes": 13,
                "mtime_epoch": 2.0,
                "content_hash_sample": "h2",
                "dataset_family": "file",
            }
        ],
        strict_mode=True,
        generated_epoch=2,
    )
    assert source_snapshot_changed(previous=latest, current=second) is True
