"""Streaming helpers for connector I/O with backpressure-aware chunking."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from pathlib import Path

DEFAULT_STREAM_CHUNK_BYTES = 64 * 1024


def iter_file_chunks(
    path: Path,
    *,
    chunk_bytes: int = DEFAULT_STREAM_CHUNK_BYTES,
    start_offset: int = 0,
    max_bytes: int | None = None,
) -> Iterator[bytes]:
    """Yield file bytes in bounded chunks without loading full files into memory."""
    resolved_chunk = max(int(chunk_bytes), 1)
    remaining = max_bytes if max_bytes is None else max(int(max_bytes), 0)
    with path.open("rb") as handle:
        if start_offset > 0:
            handle.seek(start_offset)
        while True:
            if remaining is not None and remaining <= 0:
                break
            read_size = resolved_chunk if remaining is None else min(resolved_chunk, remaining)
            chunk = handle.read(read_size)
            if not chunk:
                break
            yield chunk
            if remaining is not None:
                remaining -= len(chunk)


def sample_sha256(path: Path, *, sample_bytes: int = 8192) -> str:
    """Hash only a deterministic byte prefix from a file."""
    hasher = hashlib.sha256()
    for chunk in iter_file_chunks(path, chunk_bytes=4096, max_bytes=sample_bytes):
        hasher.update(chunk)
    return hasher.hexdigest()


def copy_file_streaming(
    *,
    source: Path,
    destination: Path,
    chunk_bytes: int = DEFAULT_STREAM_CHUNK_BYTES,
    resume: bool = True,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Copy a file in chunks with optional resume support and progress callback."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    start_offset = destination.stat().st_size if resume and destination.exists() else 0
    written_total = start_offset
    mode = "ab" if start_offset > 0 else "wb"
    with destination.open(mode) as out:
        for chunk in iter_file_chunks(source, chunk_bytes=chunk_bytes, start_offset=start_offset):
            out.write(chunk)
            written_total += len(chunk)
            if on_progress is not None:
                on_progress(written_total)
    return written_total
