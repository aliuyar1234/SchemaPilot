"""Contract report persistence helpers for build gating."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildContractReport:
    """Normalized contract report payload."""

    workspace_id: str
    build_id: str
    contracts_passed: bool
    failure_count: int
    failures: list[dict[str, object]]
    path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "build_id": self.build_id,
            "contracts_passed": self.contracts_passed,
            "failure_count": self.failure_count,
            "failures": self.failures,
            "path": self.path,
        }


def write_build_contract_report(
    *,
    workspace_id: str,
    build_id: str,
    contracts_passed: bool,
    failures: list[dict[str, object]],
    storage_root: str,
) -> BuildContractReport:
    """Write a build contract report under storage root."""
    report_root = Path(storage_root) / "contracts" / workspace_id
    report_root.mkdir(parents=True, exist_ok=True)
    report_path = report_root / f"{build_id}.json"
    payload = {
        "workspace_id": workspace_id,
        "build_id": build_id,
        "contracts_passed": bool(contracts_passed),
        "failure_count": len(failures),
        "failures": failures,
    }
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return BuildContractReport(
        workspace_id=workspace_id,
        build_id=build_id,
        contracts_passed=bool(contracts_passed),
        failure_count=len(failures),
        failures=failures,
        path=report_path.as_posix(),
    )


def load_build_contract_report(
    *, workspace_id: str, build_id: str, storage_root: str
) -> BuildContractReport | None:
    """Load a build contract report if present."""
    report_path = Path(storage_root) / "contracts" / workspace_id / f"{build_id}.json"
    if not report_path.exists():
        return None
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    failures_raw = raw.get("failures", [])
    failures = (
        [item for item in failures_raw if isinstance(item, dict)]
        if isinstance(failures_raw, list)
        else []
    )
    return BuildContractReport(
        workspace_id=workspace_id,
        build_id=build_id,
        contracts_passed=bool(raw.get("contracts_passed", False)),
        failure_count=int(raw.get("failure_count", len(failures))),
        failures=[{str(key): value for key, value in item.items()} for item in failures],
        path=report_path.as_posix(),
    )
