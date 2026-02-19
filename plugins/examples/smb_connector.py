"""Reference SMB/CIFS connector (read-only strict mirror mode)."""

from __future__ import annotations

from pathlib import Path

from backend.shared_domain.streaming_io import sample_sha256


def plugin_id() -> str:
    """Return stable plugin identifier."""
    return "smb_connector"


def discover(scope: dict[str, object]) -> list[dict[str, object]]:
    """Discover files from a locally mounted SMB mirror directory."""
    root_path = str(scope.get("root_path", "")).strip()
    if not root_path:
        raise ValueError("root_path_required")
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError("root_path_not_found")
    include_globs = _normalize_globs(scope.get("include_globs"))
    discovered: list[dict[str, object]] = []
    candidates = list(root.rglob("*")) if not include_globs else _glob_candidates(root, include_globs)
    for path in sorted(candidates):
        if not path.is_file():
            continue
        stat = path.stat()
        discovered.append(
            {
                "path": path.as_posix(),
                "dataset_family": "smb",
                "size_bytes": int(stat.st_size),
                "mtime_epoch": float(stat.st_mtime),
                "content_hash_sample": _sample_hash(path),
            }
        )
    return discovered


def _normalize_globs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _glob_candidates(root: Path, include_globs: list[str]) -> list[Path]:
    results: list[Path] = []
    for pattern in include_globs:
        results.extend(root.glob(pattern))
    return results


def _sample_hash(path: Path, sample_bytes: int = 4096) -> str:
    return sample_sha256(path, sample_bytes=sample_bytes)
