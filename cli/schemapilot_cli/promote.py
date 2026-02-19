"""Promotion flow CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path


def load_promotion_bundle(bundle_path: str) -> dict[str, object]:
    """Load one promotion bundle envelope from disk."""

    path = Path(bundle_path)
    if not path.exists():
        raise FileNotFoundError(path.as_posix())
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("promotion_bundle_payload_must_be_object")
    return {str(key): value for key, value in payload.items()}


def write_promotion_bundle(*, output_path: str, payload: dict[str, object]) -> Path:
    """Write one promotion bundle envelope to disk deterministically."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def build_promotion_import_payload(
    *,
    bundle_payload: dict[str, object],
    before_policy_report_path: str | None = None,
    after_policy_report_path: str | None = None,
    protected_scenario_ids: list[str] | None = None,
) -> dict[str, object]:
    """Build request payload for promotion import endpoint."""

    request_payload: dict[str, object] = {
        "bundle": bundle_payload.get("bundle", {}),
        "bundle_checksum": str(bundle_payload.get("bundle_checksum", "")),
        "signature": bundle_payload.get("signature", {}),
    }
    if before_policy_report_path and after_policy_report_path:
        before_path = Path(before_policy_report_path)
        after_path = Path(after_policy_report_path)
        if not before_path.exists() or not after_path.exists():
            raise FileNotFoundError("policy_report_path_missing")
        request_payload["before_policy_report"] = json.loads(
            before_path.read_text(encoding="utf-8")
        )
        request_payload["after_policy_report"] = json.loads(
            after_path.read_text(encoding="utf-8")
        )
        request_payload["protected_scenario_ids"] = sorted(
            {
                str(item).strip()
                for item in (protected_scenario_ids or [])
                if str(item).strip()
            }
        )
    return request_payload
