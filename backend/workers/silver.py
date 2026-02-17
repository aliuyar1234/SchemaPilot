"""Silver layer build helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SilverBuildResult:
    """Silver build output."""

    snapshot_id: str
    data_path: str
    crosswalk_path: str


def build_silver_snapshot(
    *,
    workspace_id: str,
    entity_name: str,
    source_records: list[dict[str, object]],
    natural_key_fields: list[str],
    output_root: str,
    snapshot_id: str,
) -> SilverBuildResult:
    """Normalize records and write silver snapshot + crosswalk."""
    normalized = [_normalize_record(record) for record in source_records]
    with_ids = []
    crosswalk = []
    for index, record in enumerate(normalized):
        natural_key = "|".join(str(record.get(field, "")) for field in natural_key_fields)
        canonical_id = _stable_id(entity_name, natural_key)
        with_ids.append({"canonical_id": canonical_id, **record})
        crosswalk.append(
            {
                "source_record_index": index,
                "canonical_id": canonical_id,
                "natural_key": natural_key,
            }
        )

    snapshot_root = (
        Path(output_root) / "silver" / workspace_id / entity_name / "snapshots" / snapshot_id
    )
    snapshot_root.mkdir(parents=True, exist_ok=True)
    data_path = snapshot_root / "data.json"
    crosswalk_path = snapshot_root / "crosswalk.json"
    data_path.write_text(json.dumps(with_ids, indent=2, sort_keys=True), encoding="utf-8")
    crosswalk_path.write_text(json.dumps(crosswalk, indent=2, sort_keys=True), encoding="utf-8")
    return SilverBuildResult(
        snapshot_id=snapshot_id,
        data_path=data_path.as_posix(),
        crosswalk_path=crosswalk_path.as_posix(),
    )


def _normalize_record(record: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in record.items():
        if isinstance(value, str):
            value = value.strip()
            if value.isdigit():
                normalized[key] = int(value)
                continue
            try:
                normalized[key] = float(value.replace(",", "."))
                continue
            except ValueError:
                normalized[key] = value
                continue
        normalized[key] = value
    return normalized


def _stable_id(entity_name: str, natural_key: str) -> str:
    digest = hashlib.sha256(f"{entity_name}::{natural_key}".encode()).hexdigest()
    return f"sid_{digest[:16]}"
