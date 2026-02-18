from __future__ import annotations

from pathlib import Path

import pytest

from backend.shared_domain.errors import NotFoundError
from backend.shared_domain.evidence_store import (
    build_evidence_uri,
    load_evidence_bundle,
    parse_evidence_uri,
    store_evidence_bundle,
)


def test_evidence_store_roundtrip_and_stable_uri(tmp_path: Path) -> None:
    stored = store_evidence_bundle(
        workspace_id="workspace-1",
        storage_root=tmp_path.as_posix(),
        bundle_type="profile",
        payload={"dataset_id": "d1", "profile": {"row_count_sampled": 10}},
    )

    assert stored.evidence_bundle_uri == build_evidence_uri(
        workspace_id="workspace-1",
        evidence_id=stored.evidence_id,
    )
    workspace_id, evidence_id = parse_evidence_uri(stored.evidence_bundle_uri)
    loaded = load_evidence_bundle(
        workspace_id=workspace_id,
        evidence_id=evidence_id,
        storage_root=tmp_path.as_posix(),
    )
    assert loaded["workspace_id"] == "workspace-1"
    assert loaded["content_hash"] == stored.content_hash
    assert Path(stored.path).exists()


def test_evidence_store_enforces_immutability_for_existing_bundle_id(tmp_path: Path) -> None:
    _ = store_evidence_bundle(
        workspace_id="workspace-1",
        storage_root=tmp_path.as_posix(),
        bundle_type="profile",
        evidence_id="fixed-bundle",
        payload={"dataset_id": "d1", "profile": {"row_count_sampled": 10}},
    )

    with pytest.raises(ValueError, match="immutability"):
        store_evidence_bundle(
            workspace_id="workspace-1",
            storage_root=tmp_path.as_posix(),
            bundle_type="profile",
            evidence_id="fixed-bundle",
            payload={"dataset_id": "d1", "profile": {"row_count_sampled": 20}},
        )


def test_evidence_store_not_found_error_shape(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        load_evidence_bundle(
            workspace_id="workspace-1",
            evidence_id="missing",
            storage_root=tmp_path.as_posix(),
        )
