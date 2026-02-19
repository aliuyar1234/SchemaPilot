#!/usr/bin/env python3
"""Fail when deploy artifacts expose direct engine/index bypass ports."""

from __future__ import annotations

import re
from pathlib import Path

BYPASS_PORTS = (6432, 8080, 8083, 9200, 6333)
BYPASS_TOKENS = tuple(f"{port}:{port}" for port in BYPASS_PORTS)
COMPOSE_ONLY_BLOCKED_MAPPINGS = ("5432:5432",)
PORT_PATTERN = re.compile(r"\b(?:port|targetPort|nodePort)\s*:\s*(\d+)\b")
AI_URL_CONFIG_PATTERN = re.compile(r"SCHEMAPILOT_AI_(?:GATEWAY|CONTROL_PLANE)_URL:\s*(.+)$")
URL_PORT_PATTERN = re.compile(r":(\d+)\b")


def validate_no_bypass_ports(root: Path) -> list[str]:
    errors: list[str] = []
    compose_path = root / "deploy" / "docker-compose.yml"
    compose = compose_path.read_text(encoding="utf-8")
    for token in BYPASS_TOKENS:
        if token in compose:
            errors.append(
                f"{compose_path.as_posix()}: direct bypass port mapping detected ({token})"
            )
    for mapping in COMPOSE_ONLY_BLOCKED_MAPPINGS:
        if mapping in compose:
            errors.append(
                f"{compose_path.as_posix()}: direct managed target-db mapping detected ({mapping})"
            )
    for line_no, line in enumerate(compose.splitlines(), start=1):
        match = AI_URL_CONFIG_PATTERN.search(line)
        if match is None:
            continue
        value = match.group(1)
        for port_raw in URL_PORT_PATTERN.findall(value):
            port = int(port_raw)
            if port in BYPASS_PORTS:
                errors.append(
                    f"{compose_path.as_posix()}:{line_no}: "
                    f"AI routing points to bypass port ({port})"
                )

    k8s_root = root / "deploy" / "k8s"
    for file in sorted(k8s_root.glob("*.yaml")):
        content = file.read_text(encoding="utf-8")
        for match in PORT_PATTERN.finditer(content):
            port = int(match.group(1))
            if port in BYPASS_PORTS:
                errors.append(f"{file.as_posix()}: direct bypass service port detected ({port})")
    helm_root = root / "deploy" / "helm" / "templates"
    if helm_root.exists():
        for file in sorted(helm_root.glob("*.yaml")):
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
