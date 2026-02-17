from __future__ import annotations

from backend.workers.connectors.s3 import S3ReadOnlyConnector


def test_s3_connector_lists_objects_read_only() -> None:
    def fake_lister(bucket: str, prefix: str, max_keys: int) -> list[dict[str, object]]:
        assert bucket == "demo"
        assert prefix == "exports/"
        assert max_keys == 1000
        return [{"Key": "exports/a.csv", "Size": 100, "ETag": "etag-a"}]

    connector = S3ReadOnlyConnector(fake_lister)
    objects = connector.discover(bucket="demo", prefix="exports/")
    assert len(objects) == 1
    assert objects[0].key == "exports/a.csv"
