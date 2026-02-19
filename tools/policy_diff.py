#!/usr/bin/env python3
"""Compute deterministic policy impact diffs between two simulation reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.shared_domain.policy_diff import compute_policy_impact_diff


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--before",
        required=True,
        help="Path to baseline policy audit report JSON.",
    )
    parser.add_argument(
        "--after",
        required=True,
        help="Path to candidate policy audit report JSON.",
    )
    parser.add_argument(
        "--protected-scenario-id",
        action="append",
        default=[],
        help="Scenario ID that must not regress to deny in after report.",
    )
    parser.add_argument(
        "--output",
        default="runtime/policy_diff/report.json",
        help="Output file path for diff payload.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json_object_required:{path.as_posix()}")
    return {str(key): value for key, value in payload.items()}


def main() -> int:
    args = parse_args()
    before_path = Path(args.before)
    after_path = Path(args.after)
    if not before_path.exists():
        print(f"FAIL before report not found: {before_path.as_posix()}")
        return 1
    if not after_path.exists():
        print(f"FAIL after report not found: {after_path.as_posix()}")
        return 1
    try:
        before_report = _load_json(before_path)
        after_report = _load_json(after_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL invalid report payload: {exc}")
        return 1

    diff = compute_policy_impact_diff(
        before_report=before_report,
        after_report=after_report,
        protected_scenario_ids=args.protected_scenario_id,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(diff, indent=2, sort_keys=True), encoding="utf-8")
    print(output_path.as_posix())
    protected_denials: list[str] = []
    invariants_raw = diff.get("invariants")
    if isinstance(invariants_raw, dict):
        denials_raw = invariants_raw.get("protected_denials", [])
        if isinstance(denials_raw, list):
            protected_denials = [str(item) for item in denials_raw]
    if protected_denials:
        print(
            "FAIL protected scenarios regressed to deny: "
            + ",".join(protected_denials),
        )
        return 1
    print("PASS CHK-POLICY-DIFF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
