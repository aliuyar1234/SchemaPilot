from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.shared_domain.gold_templates import (
    generate_gold_template_bundle,
    list_gold_template_packs,
)


def test_list_gold_template_packs_contains_expected_ids() -> None:
    assert list_gold_template_packs() == ["crm", "invoices", "support"]


def test_generate_gold_template_bundle_is_deterministic(tmp_path: Path) -> None:
    first = generate_gold_template_bundle(
        pack_id="invoices",
        workspace_id="workspace-a",
        output_root=tmp_path.as_posix(),
    )
    first_path = Path(first["output_path"])
    first_payload = first_path.read_text(encoding="utf-8")

    second = generate_gold_template_bundle(
        pack_id="invoices",
        workspace_id="workspace-a",
        output_root=tmp_path.as_posix(),
        overwrite=True,
    )
    second_path = Path(second["output_path"])
    second_payload = second_path.read_text(encoding="utf-8")

    assert first_payload == second_payload
    parsed = json.loads(first_payload)
    assert parsed["semantic_manifest"]["workspace_id"] == "workspace-a"
    assert parsed["semantic_manifest_checksum"] == first["semantic_manifest_checksum"]
    assert parsed["semantic_manifest_checksum"] == second["semantic_manifest_checksum"]


def test_generate_gold_template_bundle_rejects_unknown_pack(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown_template_pack"):
        generate_gold_template_bundle(
            pack_id="unknown",
            workspace_id="workspace-a",
            output_root=tmp_path.as_posix(),
        )
