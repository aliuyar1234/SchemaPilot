#!/usr/bin/env python3
"""CHK-BOUNDARY-FITNESS static checker for scaffold boundaries."""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckState:
    edges: dict[str, set[str]] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)


def load_rules(repo_root: Path) -> dict:
    rules_path = repo_root / "tools" / "boundary_rules.json"
    return json.loads(rules_path.read_text(encoding="utf-8"))


def normalize_import_target(name: str) -> str:
    parts = name.split(".")
    if not parts:
        return ""
    if parts[0] == "backend" and len(parts) > 1:
        return parts[1]
    if parts[0] == "cli" and len(parts) > 1:
        return "cli"
    return parts[0]


def module_owner(path: Path, module_roots: dict[str, str], repo_root: Path) -> str | None:
    rel = path.relative_to(repo_root).as_posix()
    for module, root in module_roots.items():
        root_prefix = root.replace("\\", "/") + "/"
        if rel == root.replace("\\", "/") or rel.startswith(root_prefix):
            return module
    return None


def parse_python_import_targets(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.append(node.module)
    return targets


IMPORT_RE = re.compile(r"""(?:import|export)\s+(?:[^'"]+\s+from\s+)?["']([^"']+)["']""")


def parse_ts_import_targets(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return IMPORT_RE.findall(text)


def check_python(repo_root: Path, rules: dict, state: CheckState) -> None:
    module_roots: dict[str, str] = rules["python_module_roots"]
    managed_prefixes: list[str] = list(rules.get("managed_python_prefixes", []))
    unmanaged_allowlist: set[str] = set(rules.get("unmanaged_python_path_allowlist", []))
    allowed_imports: dict[str, list[str]] = rules["allowed_module_imports"]
    engine_import_roots: set[str] = set(rules["engine_client_import_roots"])
    modules: set[str] = set(rules["modules"])

    for module in modules:
        state.edges[module] = set()

    py_files = sorted(
        p
        for p in repo_root.rglob("*.py")
        if ".venv" not in p.parts and "__pycache__" not in p.parts
    )
    for py_file in py_files:
        rel = py_file.relative_to(repo_root).as_posix()
        owner = module_owner(py_file, module_roots, repo_root)
        if owner is None:
            is_managed_path = any(
                rel == prefix.replace("\\", "/") or rel.startswith(prefix.replace("\\", "/") + "/")
                for prefix in managed_prefixes
            )
            if is_managed_path and rel not in unmanaged_allowlist:
                state.violations.append(f"Unregistered module root: {rel}")
            continue
        for raw_target in parse_python_import_targets(py_file):
            target = normalize_import_target(raw_target)
            if target in modules:
                state.edges[owner].add(target)
                if owner == target:
                    continue
                if target not in allowed_imports.get(owner, []):
                    state.violations.append(f"Forbidden import: {owner} -> {target} in {rel}")
            if owner != "gateway":
                target_root = normalize_import_target(raw_target)
                if target_root in engine_import_roots:
                    state.violations.append(
                        f"Engine client import outside gateway: {raw_target} in {rel}"
                    )


def check_ui(repo_root: Path, rules: dict, state: CheckState) -> None:
    forbidden_patterns: list[str] = rules["forbidden_ui_import_patterns"]
    ts_files = sorted(repo_root.glob("ui/src/**/*.[tj]s")) + sorted(
        repo_root.glob("ui/src/**/*.[tj]sx")
    )
    for ts_file in ts_files:
        for target in parse_ts_import_targets(ts_file):
            normalized = target.replace("/", "\\")
            for pattern in forbidden_patterns:
                pattern_normalized = pattern.replace("/", "\\")
                if pattern_normalized in normalized:
                    rel = ts_file.relative_to(repo_root).as_posix()
                    state.violations.append(f"UI import crosses boundary: {target} in {rel}")


def detect_cycles(state: CheckState) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str, stack: list[str]) -> None:
        if node in visiting:
            start = stack.index(node)
            cycle = stack[start:] + [node]
            state.violations.append("Cycle detected: " + " -> ".join(cycle))
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for nxt in sorted(state.edges.get(node, set())):
            if nxt == node:
                continue
            dfs(nxt, stack)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(state.edges):
        dfs(node, [])


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    rules = load_rules(repo_root)
    state = CheckState()

    check_python(repo_root, rules, state)
    check_ui(repo_root, rules, state)
    detect_cycles(state)

    if state.violations:
        print("FAIL CHK-BOUNDARY-FITNESS")
        for violation in sorted(state.violations):
            print(f"- {violation}")
        return 1

    print("PASS CHK-BOUNDARY-FITNESS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
