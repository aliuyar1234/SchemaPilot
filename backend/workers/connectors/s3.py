"""Read-only S3/MinIO connector abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ObjectLister(Protocol):
    """Protocol for S3 object listing clients."""

    def __call__(self, bucket: str, prefix: str, max_keys: int) -> list[dict[str, object]]:
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
        rows = self._lister(bucket, prefix, max_keys)
        objects: list[S3Object] = []
        for row in rows:
            key = str(row.get("Key", ""))
            if not key:
                continue
            size_raw = row.get("Size", 0)
            size_bytes = int(size_raw) if isinstance(size_raw, (int, float, str)) else 0
            objects.append(
                S3Object(
                    key=key,
                    size_bytes=size_bytes,
                    etag=str(row.get("ETag", "")),
                )
            )
        return objects
