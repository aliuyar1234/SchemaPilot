from __future__ import annotations

import json
from pathlib import Path

from cli.schemapilot_cli.promote import (
    build_promotion_import_payload,
    load_promotion_bundle,
    write_promotion_bundle,
)


def test_promote_helpers_roundtrip_bundle_file(tmp_path: Path) -> None:
    bundle = {
        "bundle": {"workspace_id": "w1"},
        "bundle_checksum": "abc",
        "signature": {"algorithm": "HMAC-SHA256", "signature": "sig"},
    }
    output_path = write_promotion_bundle(
        output_path=(tmp_path / "bundle.json").as_posix(),
        payload=bundle,
    )
    loaded = load_promotion_bundle(output_path.as_posix())
    assert loaded["bundle_checksum"] == "abc"
    request_payload = build_promotion_import_payload(bundle_payload=loaded)
    assert request_payload["bundle_checksum"] == "abc"
    assert request_payload["bundle"] == {"workspace_id": "w1"}


def test_promote_helpers_attach_policy_reports(tmp_path: Path) -> None:
    bundle = {
        "bundle": {"workspace_id": "w1"},
        "bundle_checksum": "abc",
        "signature": {"algorithm": "HMAC-SHA256", "signature": "sig"},
    }
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    report = {"workspace_id": "w1", "scenario_count": 0, "scenarios": []}
    before.write_text(json.dumps(report), encoding="utf-8")
    after.write_text(json.dumps(report), encoding="utf-8")
    request_payload = build_promotion_import_payload(
        bundle_payload=bundle,
        before_policy_report_path=before.as_posix(),
        after_policy_report_path=after.as_posix(),
        protected_scenario_ids=["s2", "s1", "s1"],
    )
    assert request_payload["protected_scenario_ids"] == ["s1", "s2"]
