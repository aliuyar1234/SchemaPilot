"""Read-only S3/MinIO connector abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ObjectLister(Protocol):
    """Protocol for S3 object listing clients."""

    def __call__(
        self, bucket: str, prefix: str, max_keys: int
    ) -> list[dict[str, object]] | dict[str, object]:
        """List objects in bucket/prefix."""


@dataclass(frozen=True)
class S3Object:
    """Discovered S3 object metadata."""

    key: str
    size_bytes: int
    etag: str


class S3ReadOnlyConnector:
    """S3 connector using an injected read-only listing function."""

    def __init__(self, lister: ObjectLister) -> None:
        self._lister = lister

    def discover(self, *, bucket: str, prefix: str, max_keys: int = 1000) -> list[S3Object]:
        response = self._lister(bucket, prefix, max_keys)
        rows: list[dict[str, object]]
        truncated: bool | None
        if isinstance(response, dict):
            objects_raw = response.get("objects", [])
            rows = (
                [item for item in objects_raw if isinstance(item, dict)]
                if isinstance(objects_raw, list)
                else []
            )
            truncated_raw = response.get("is_truncated", False)
            truncated = bool(truncated_raw)
        elif isinstance(response, list):
            rows = [item for item in response if isinstance(item, dict)]
            truncated = None
        else:
            raise ValueError("S3 lister returned an unsupported response shape.")
        if truncated is True:
            raise ValueError(
                "S3 listing was truncated; fail-closed until pagination is handled explicitly."
            )
        if truncated is None and len(rows) >= max_keys:
            raise ValueError(
                "S3 lister reached max_keys without truncation metadata; "
                "fail-closed to avoid silent partial discovery."
            )
        objects: list[S3Object] = []
        for row in rows:
            key = str(row.get("Key", ""))
            if not key:
                continue
            size_raw: Any = row.get("Size", 0)
            size_bytes = int(size_raw) if isinstance(size_raw, (int, float, str)) else 0
            objects.append(
                S3Object(
                    key=key,
                    size_bytes=size_bytes,
                    etag=str(row.get("ETag", "")),
                )
            )
        return sorted(objects, key=lambda item: item.key)
