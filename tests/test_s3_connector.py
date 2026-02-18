from __future__ import annotations

import pytest

from backend.workers.connectors.s3 import S3ReadOnlyConnector


def test_s3_connector_lists_objects_read_only() -> None:
    def fake_lister(bucket: str, prefix: str, max_keys: int) -> list[dict[str, object]]:
        assert bucket == "demo"
        assert prefix == "exports/"
        assert max_keys == 1000
        return [
            {"Key": "exports/b.csv", "Size": 100, "ETag": "etag-b"},
            {"Key": "exports/a.csv", "Size": 100, "ETag": "etag-a"},
        ]

    connector = S3ReadOnlyConnector(fake_lister)
    objects = connector.discover(bucket="demo", prefix="exports/")
    assert len(objects) == 2
    assert objects[0].key == "exports/a.csv"


def test_s3_connector_fails_closed_when_listing_truncated() -> None:
    def fake_lister(bucket: str, prefix: str, max_keys: int) -> dict[str, object]:
        _ = bucket, prefix, max_keys
        return {
            "objects": [{"Key": "exports/a.csv", "Size": 100, "ETag": "etag-a"}],
            "is_truncated": True,
        }

    connector = S3ReadOnlyConnector(fake_lister)
    with pytest.raises(ValueError, match="truncated"):
        connector.discover(bucket="demo", prefix="exports/")


def test_s3_connector_fails_closed_when_max_keys_reached_without_truncation_metadata() -> None:
    def fake_lister(bucket: str, prefix: str, max_keys: int) -> list[dict[str, object]]:
        _ = bucket, prefix
        return [
            {"Key": f"exports/{i:04d}.csv", "Size": 100, "ETag": f"etag-{i}"}
            for i in range(max_keys)
        ]

    connector = S3ReadOnlyConnector(fake_lister)
    with pytest.raises(ValueError, match="max_keys"):
        connector.discover(bucket="demo", prefix="exports/", max_keys=3)
