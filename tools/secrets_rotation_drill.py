#!/usr/bin/env python3
"""Run a local secret-reference rotation drill."""

from __future__ import annotations

import json
from pathlib import Path

from backend.shared_domain.secrets import rotate_secret_reference


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    drill_dir = root / "runtime" / "secrets_rotation_drill"
    drill_dir.mkdir(parents=True, exist_ok=True)

    config_path = drill_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "credentials_ref": "vault://schemapilot/source/db-reader-v1",
                "profile": "team",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    previous, current = rotate_secret_reference(
        config_path=config_path,
        key="credentials_ref",
        new_reference="vault://schemapilot/source/db-reader-v2",
    )
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("credentials_ref") != current:
        print("FAIL rotation did not persist new credentials_ref")
        return 1

    report_path = drill_dir / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "pass",
                "previous_ref": previous,
                "current_ref": current,
                "config_path": config_path.relative_to(root).as_posix(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print("PASS secrets rotation drill")
    print(report_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
