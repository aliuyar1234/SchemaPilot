#!/usr/bin/env python3
"""Extract weekly KPIs from metadata and audit state."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import ReviewTask, RunRecord

ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_CHAR_TO_VALUE = {char: index for index, char in enumerate(ULID_ALPHABET)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url",
        default="sqlite:///./runtime/schemapilot.db",
        help="Metadata database URL.",
    )
    parser.add_argument("--week", default=_current_week(), help="ISO week identifier.")
    parser.add_argument("--output-root", default="runtime/kpi", help="KPI output folder.")
    parser.add_argument(
        "--baseline",
        default="tools/kpi_baseline.json",
        help="KPI baseline policy file.",
    )
    parser.add_argument(
        "--enforce-baseline",
        action="store_true",
        help="Fail when extracted KPIs violate baseline policy.",
    )
    return parser.parse_args()


def extract_kpis(session: Session) -> dict[str, object]:
    runs = session.execute(select(RunRecord)).scalars().all()
    tasks = session.execute(select(ReviewTask)).scalars().all()
    decisions = session.execute(select(AccessDecision)).scalars().all()
    events = session.execute(select(AuditEvent)).scalars().all()

    total_runs = len(runs)
    succeeded_runs = sum(1 for run in runs if run.status == "succeeded")
    run_success_rate = (succeeded_runs / total_runs) if total_runs else None

    policy_denials = sum(1 for decision in decisions if decision.result == "deny")
    security_regressions = sum(1 for event in events if event.event_type == "security.regression")

    blocking_open = sum(
        1 for task in tasks if task.blocking and task.status in {"open", "in_review"}
    )
    published_builds = sum(
        1
        for event in events
        if event.event_type == "build.published"
        and isinstance(event.event_json, dict)
        and event.event_json.get("status") == "published"
    )

    ttfsa_minutes = _time_to_first_safe_answer_minutes(events, decisions)
    deterministic_rate = _deterministic_rebuild_pass_rate(runs)

    notes: list[str] = []
    if ttfsa_minutes is None:
        notes.append(
            "time_to_first_safe_answer_minutes unavailable (missing workspace/query events)"
        )
    if deterministic_rate is None:
        notes.append("deterministic_rebuild_pass_rate unavailable (insufficient repeated runs)")

    return {
        "time_to_first_safe_answer_minutes": ttfsa_minutes,
        "run_success_rate": run_success_rate,
        "security_regression_count": security_regressions,
        "policy_denial_count": policy_denials,
        "deterministic_rebuild_pass_rate": deterministic_rate,
        "review_queue_blocking_open_tasks": blocking_open,
        "published_build_count": published_builds,
        "notes": notes,
    }


def write_kpi_extract(*, week: str, output_root: str, payload: dict[str, object]) -> Path:
    root = Path(output_root)
    extract_dir = root / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "week": week,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "kpis": payload,
    }
    weekly_path = extract_dir / f"{week}.json"
    weekly_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (root / "latest_extracted.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return weekly_path


def _deterministic_rebuild_pass_rate(runs: Sequence[RunRecord]) -> float | None:
    groups: dict[tuple[str, tuple[str, ...]], list[tuple[str, ...]]] = defaultdict(list)
    for run in runs:
        if run.status != "succeeded":
            continue
        input_refs = run.input_refs_json if isinstance(run.input_refs_json, dict) else {}
        output_refs = run.output_refs_json if isinstance(run.output_refs_json, dict) else {}
        source_ids_raw = input_refs.get("source_ids", [])
        dataset_ids_raw = output_refs.get("dataset_ids", [])
        source_ids = (
            tuple(sorted(str(item) for item in source_ids_raw))
            if isinstance(source_ids_raw, list)
            else tuple()
        )
        dataset_ids = (
            tuple(sorted(str(item) for item in dataset_ids_raw))
            if isinstance(dataset_ids_raw, list)
            else tuple()
        )
        if not source_ids:
            continue
        groups[(run.run_type, source_ids)].append(dataset_ids)

    groups_with_rebuilds = [values for values in groups.values() if len(values) >= 2]
    if not groups_with_rebuilds:
        return None
    stable = sum(1 for values in groups_with_rebuilds if len(set(values)) == 1)
    return stable / len(groups_with_rebuilds)


def _time_to_first_safe_answer_minutes(
    events: Sequence[AuditEvent], decisions: Sequence[AccessDecision]
) -> float | None:
    workspace_events = sorted(
        (event for event in events if event.event_type == "workspace.created"),
        key=lambda event: event.audit_event_id,
    )
    allow_decisions = sorted(
        (decision for decision in decisions if decision.result == "allow"),
        key=lambda decision: decision.decision_id,
    )
    if not workspace_events or not allow_decisions:
        return None
    start_ms = _ulid_timestamp_ms(workspace_events[0].audit_event_id)
    end_ms = _ulid_timestamp_ms(allow_decisions[0].decision_id)
    if start_ms is None or end_ms is None:
        return None
    return max((end_ms - start_ms) / 60_000.0, 0.0)


def _ulid_timestamp_ms(value: str) -> int | None:
    normalized = value.strip().upper()
    if len(normalized) < 10:
        return None
    timestamp = 0
    for char in normalized[:10]:
        digit = ULID_CHAR_TO_VALUE.get(char)
        if digit is None:
            return None
        timestamp = (timestamp * 32) + digit
    return timestamp


def _current_week() -> str:
    now = datetime.now(tz=UTC)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def main() -> int:
    args = parse_args()
    session_factory = get_session_factory(args.database_url)
    session = session_factory()
    try:
        payload = extract_kpis(session)
    finally:
        session.close()
    path = write_kpi_extract(week=args.week, output_root=args.output_root, payload=payload)
    baseline_path = Path(str(args.baseline))
    baseline = _load_baseline(baseline_path)
    violations = _evaluate_baseline_violations(payload=payload, baseline=baseline)
    if violations:
        print("WARN KPI baseline violations detected:")
        for violation in violations:
            print("-", violation)
    if args.enforce_baseline and violations:
        print(f"FAIL KPI baseline regression gate: {path.as_posix()}")
        return 1
    print(f"PASS KPI extract generated: {path.as_posix()}")
    return 0


def _load_baseline(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def _evaluate_baseline_violations(
    *,
    payload: dict[str, object],
    baseline: dict[str, object],
) -> list[str]:
    rules_raw = baseline.get("rules", {})
    if not isinstance(rules_raw, dict):
        return []
    violations: list[str] = []
    for metric, rule_raw in sorted(rules_raw.items()):
        if not isinstance(rule_raw, dict):
            continue
        value = payload.get(metric)
        allow_null = bool(rule_raw.get("allow_null", False))
        if value is None:
            if not allow_null:
                violations.append(f"{metric}:value_missing")
            continue
        try:
            numeric_value = _to_float(value)
        except (TypeError, ValueError):
            violations.append(f"{metric}:not_numeric")
            continue
        if "min" in rule_raw:
            min_threshold = _to_float(rule_raw["min"])
            if numeric_value < min_threshold:
                violations.append(f"{metric}:below_min:{numeric_value:.6f}<{min_threshold:.6f}")
        if "max" in rule_raw:
            max_threshold = _to_float(rule_raw["max"])
            if numeric_value > max_threshold:
                violations.append(f"{metric}:above_max:{numeric_value:.6f}>{max_threshold:.6f}")
    return violations


def _to_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError("value_is_not_numeric")


if __name__ == "__main__":
    raise SystemExit(main())
