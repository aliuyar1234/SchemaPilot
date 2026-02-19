#!/usr/bin/env python3
"""Semantic pack harness for deterministic contract checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default="packs/registry.json",
        help="Registry JSON containing semantic pack references.",
    )
    parser.add_argument(
        "--output",
        default="runtime/semantic_test/report.json",
        help="Output report path.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json_object_required")
    return {str(key): value for key, value in payload.items()}


def _checksum(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    import hashlib

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_semantic_manifest(manifest: dict[str, object]) -> list[str]:
    errors: list[str] = []
    version = str(manifest.get("manifest_version", "")).strip()
    if not version:
        errors.append("missing_manifest_version")
    entities_raw = manifest.get("entities", [])
    if not isinstance(entities_raw, list):
        return ["invalid_entities"]
    entity_ids: set[str] = set()
    for row in entities_raw:
        if not isinstance(row, dict):
            errors.append("invalid_entity_row")
            continue
        entity_id = str(row.get("entity_id", "")).strip()
        dataset_id = str(row.get("dataset_id", "")).strip()
        if not entity_id:
            errors.append("missing_entity_id")
            continue
        if entity_id in entity_ids:
            errors.append(f"duplicate_entity_id:{entity_id}")
            continue
        entity_ids.add(entity_id)
        if not dataset_id:
            errors.append(f"missing_entity_dataset_id:{entity_id}")
    metrics_raw = manifest.get("metrics", [])
    if not isinstance(metrics_raw, list):
        errors.append("invalid_metrics")
        metrics_raw = []
    metric_ids: set[str] = set()
    for row in metrics_raw:
        if not isinstance(row, dict):
            errors.append("invalid_metric_row")
            continue
        metric_id = str(row.get("metric_id", "")).strip()
        entity_id = str(row.get("entity_id", "")).strip()
        expression = str(row.get("expression", "")).strip()
        if not metric_id:
            errors.append("missing_metric_id")
            continue
        if metric_id in metric_ids:
            errors.append(f"duplicate_metric_id:{metric_id}")
            continue
        metric_ids.add(metric_id)
        if not entity_id or entity_id not in entity_ids:
            errors.append(f"metric_entity_not_found:{metric_id}")
        if not expression:
            errors.append(f"missing_metric_expression:{metric_id}")
    joins_raw = manifest.get("joins", [])
    if joins_raw is None:
        joins_raw = []
    if not isinstance(joins_raw, list):
        errors.append("invalid_joins")
        joins_raw = []
    join_ids: set[str] = set()
    for index, row in enumerate(joins_raw):
        if not isinstance(row, dict):
            errors.append("invalid_join_row")
            continue
        join_id = str(row.get("join_id", f"join_{index + 1}")).strip()
        if join_id in join_ids:
            errors.append(f"duplicate_join_id:{join_id}")
        join_ids.add(join_id)
        left_entity = str(row.get("left_entity_id", "")).strip()
        right_entity = str(row.get("right_entity_id", "")).strip()
        if left_entity not in entity_ids:
            errors.append(f"join_left_entity_not_found:{join_id}")
        if right_entity not in entity_ids:
            errors.append(f"join_right_entity_not_found:{join_id}")
    tests_raw = manifest.get("semantic_tests", [])
    if tests_raw not in (None, []):
        if not isinstance(tests_raw, list):
            errors.append("invalid_semantic_tests")
        else:
            for row in tests_raw:
                if not isinstance(row, dict):
                    errors.append("invalid_semantic_test_row")
                    continue
                metric_id = str(row.get("metric_id", "")).strip()
                if metric_id and metric_id not in metric_ids:
                    errors.append(f"semantic_test_metric_not_found:{metric_id}")
    if not entity_ids:
        errors.append("empty_entities")
    if not metric_ids:
        errors.append("empty_metrics")
    return sorted(set(errors))


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    if not registry_path.exists():
        print(f"FAIL registry_not_found:{registry_path.as_posix()}")
        return 1
    try:
        registry = _load_json(registry_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL invalid_registry:{exc}")
        return 1
    semantic_entries_raw = registry.get("semantic_packs", [])
    if not isinstance(semantic_entries_raw, list):
        print("FAIL invalid_registry_semantic_packs")
        return 1

    results: list[dict[str, object]] = []
    for entry in semantic_entries_raw:
        if not isinstance(entry, dict):
            continue
        pack_id = str(entry.get("pack_id", "")).strip()
        relative_path = str(entry.get("path", "")).strip()
        if not pack_id or not relative_path:
            results.append(
                {
                    "pack_id": pack_id or "unknown",
                    "status": "fail",
                    "errors": ["missing_pack_id_or_path"],
                }
            )
            continue
        pack_path = Path(relative_path)
        if not pack_path.is_absolute():
            pack_path = root / pack_path
        if not pack_path.exists():
            results.append(
                {
                    "pack_id": pack_id,
                    "status": "fail",
                    "errors": [f"missing_pack_file:{relative_path}"],
                }
            )
            continue
        try:
            pack_payload = _load_json(pack_path)
        except (json.JSONDecodeError, ValueError) as exc:
            results.append(
                {
                    "pack_id": pack_id,
                    "status": "fail",
                    "errors": [f"invalid_pack_json:{exc}"],
                }
            )
            continue
        manifest_raw = pack_payload.get("semantic_manifest")
        if not isinstance(manifest_raw, dict):
            results.append(
                {
                    "pack_id": pack_id,
                    "status": "fail",
                    "errors": ["missing_semantic_manifest"],
                }
            )
            continue
        manifest = {str(key): value for key, value in manifest_raw.items()}
        errors = _validate_semantic_manifest(manifest)
        results.append(
            {
                "pack_id": pack_id,
                "status": "pass" if not errors else "fail",
                "errors": errors,
                "manifest_checksum": _checksum(manifest),
                "pack_checksum": _checksum(pack_payload),
                "entity_count": len(manifest.get("entities", []))
                if isinstance(manifest.get("entities"), list)
                else 0,
                "metric_count": len(manifest.get("metrics", []))
                if isinstance(manifest.get("metrics"), list)
                else 0,
            }
        )

    report = {
        "status": "pass" if all(item.get("status") == "pass" for item in results) else "fail",
        "pack_count": len(results),
        "results": sorted(results, key=lambda item: str(item.get("pack_id", ""))),
    }
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(output_path.as_posix())
    if report["status"] == "pass":
        print("PASS CHK-SEMANTIC-TEST")
        return 0
    print("FAIL CHK-SEMANTIC-TEST")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
