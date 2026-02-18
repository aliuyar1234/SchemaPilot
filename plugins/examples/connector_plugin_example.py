"""Example connector plugin contract for SchemaPilot."""

from __future__ import annotations

from pathlib import Path


def plugin_id() -> str:
    return "example.local_csv_connector"


def discover(scope: dict[str, object]) -> list[dict[str, object]]:
    root = Path(str(scope.get("root_path", "")))
    include_ext = str(scope.get("extension", ".csv"))
    if not root.exists() or not root.is_dir():
        return []
    rows: list[dict[str, object]] = []
    for file_path in sorted(root.rglob(f"*{include_ext}")):
        if not file_path.is_file():
            continue
        rows.append(
            {
                "path": file_path.as_posix(),
                "size_bytes": file_path.stat().st_size,
            }
        )
    return rows
