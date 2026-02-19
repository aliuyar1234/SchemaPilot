from __future__ import annotations

from pathlib import Path

from backend.shared_domain.streaming_io import copy_file_streaming, iter_file_chunks, sample_sha256


def test_iter_file_chunks_is_deterministic_and_bounded(tmp_path: Path) -> None:
    source = tmp_path / "large.bin"
    source.write_bytes(b"a" * 1024 + b"b" * 1024)
    chunks = list(iter_file_chunks(source, chunk_bytes=300))
    assert sum(len(chunk) for chunk in chunks) == 2048
    assert all(len(chunk) <= 300 for chunk in chunks)


def test_sample_sha256_uses_prefix_only(tmp_path: Path) -> None:
    source = tmp_path / "sample.bin"
    source.write_bytes(b"a" * 4096 + b"z" * 4096)
    prefix_hash = sample_sha256(source, sample_bytes=4096)
    changed_tail = tmp_path / "sample_tail_changed.bin"
    changed_tail.write_bytes(b"a" * 4096 + b"x" * 4096)
    assert sample_sha256(changed_tail, sample_bytes=4096) == prefix_hash


def test_copy_file_streaming_supports_resume(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"0123456789" * 2000)
    destination = tmp_path / "dest.bin"

    observed_progress: list[int] = []

    def interrupting_progress(bytes_written: int) -> None:
        observed_progress.append(bytes_written)
        if bytes_written >= 4096:
            raise OSError("simulated network drop")

    try:
        copy_file_streaming(
            source=source,
            destination=destination,
            chunk_bytes=512,
            resume=True,
            on_progress=interrupting_progress,
        )
    except OSError:
        pass
    partial_size = destination.stat().st_size
    assert partial_size >= 4096

    final_size = copy_file_streaming(
        source=source,
        destination=destination,
        chunk_bytes=512,
        resume=True,
    )
    assert final_size == source.stat().st_size
    assert destination.read_bytes() == source.read_bytes()
