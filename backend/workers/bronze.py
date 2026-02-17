"""Bronze ingest and manifest writing utilities."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.shared_domain.ids import new_ulid


@dataclass(frozen=True)
class BronzeIngestResult:
    """Output paths for bronze ingest."""

    artifact_id: str
    raw_path: str
    manifest_path: str
    content_hash: str


def ingest_file_to_bronze(
    *,
    workspace_id: str,
    source_id: str,
    dataset_id: str,
    source_file: str,
    storage_root: str,
    run_id: str,
    parser: str = "raw_copy",
    parser_version: str = "1.0.0",
) -> BronzeIngestResult:
    """Ingest one file into bronze immutable layout with manifest."""
    src = Path(source_file)
    root = Path(storage_root)
    ingest_date = dt.datetime.now(tz=dt.UTC).strftime("%Y-%m-%d")
    content_hash = _sha256(src)
    existing = _find_existing_artifact(root, workspace_id, source_id, dataset_id, content_hash)
    if existing is not None:
        artifact_root = existing
    else:
        artifact_id = new_ulid()
        artifact_root = (
            root
            / "bronze"
            / workspace_id
            / source_id
            / dataset_id
            / ingest_date
            / f"artifact_{artifact_id}"
        )
        raw_dir = artifact_root / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        target_raw = raw_dir / src.name
        shutil.copy2(src, target_raw)

    artifact_id = artifact_root.name.replace("artifact_", "", 1)
    target_raw = next((artifact_root / "raw").iterdir())
    manifest = {
        "manifest_version": "1.0.0",
        "artifact_id": artifact_id,
        "content_hash": content_hash,
        "source_locator": src.as_posix(),
        "parser": parser,
        "parser_version": parser_version,
        "parse_params": {},
        "discovered_schema": {},
        "run_id": run_id,
    }
    manifest_path = artifact_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return BronzeIngestResult(
        artifact_id=artifact_id,
        raw_path=target_raw.as_posix(),
        manifest_path=manifest_path.as_posix(),
        content_hash=content_hash,
    )


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _find_existing_artifact(
    root: Path,
    workspace_id: str,
    source_id: str,
    dataset_id: str,
    content_hash: str,
) -> Path | None:
    dataset_root = root / "bronze" / workspace_id / source_id / dataset_id
    if not dataset_root.exists():
        return None
    for manifest in dataset_root.rglob("manifest.json"):
        body = json.loads(manifest.read_text(encoding="utf-8"))
        if body.get("content_hash") == content_hash:
            return manifest.parent
    return None
