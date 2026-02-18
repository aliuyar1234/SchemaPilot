#!/usr/bin/env python3
"""Fail when deploy artifacts expose direct engine/index bypass ports."""

from __future__ import annotations

import re
from pathlib import Path

BYPASS_PORTS = (8080, 8083, 9200, 6333)
BYPASS_TOKENS = tuple(f"{port}:{port}" for port in BYPASS_PORTS)
PORT_PATTERN = re.compile(r"\b(?:port|targetPort|nodePort)\s*:\s*(\d+)\b")


def validate_no_bypass_ports(root: Path) -> list[str]:
    errors: list[str] = []
    compose_path = root / "deploy" / "docker-compose.yml"
    compose = compose_path.read_text(encoding="utf-8")
    for token in BYPASS_TOKENS:
        if token in compose:
            errors.append(
                f"{compose_path.as_posix()}: direct bypass port mapping detected ({token})"
            )

    k8s_root = root / "deploy" / "k8s"
    for file in sorted(k8s_root.glob("*.yaml")):
        content = file.read_text(encoding="utf-8")
        for match in PORT_PATTERN.finditer(content):
            port = int(match.group(1))
            if port in BYPASS_PORTS:
                errors.append(
                    f"{file.as_posix()}: direct bypass service port detected ({port})"
                )
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate_no_bypass_ports(root)
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("PASS CHK-NO-BYPASS-PORTS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
