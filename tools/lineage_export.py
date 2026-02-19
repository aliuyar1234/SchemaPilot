#!/usr/bin/env python3
"""Export deterministic SQL lineage payload through control-plane API."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path


def _request_json(*, method: str, url: str, payload: dict[str, object]) -> dict[str, object]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("unsupported_scheme")
    if not parsed.netloc:
        raise ValueError("missing_host")
    encoded = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        method=method.upper(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer local-platform-admin-token",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:  # nosec B310
        return json.loads(response.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--sql-file", required=True)
    parser.add_argument("--cp-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sql_path = Path(args.sql_file)
    if not sql_path.exists():
        print(f"FAIL missing_sql_file:{sql_path.as_posix()}")
        return 1
    sql_text = sql_path.read_text(encoding="utf-8")
    payload = _request_json(
        method="POST",
        url=f"{args.cp_base_url}/api/v1/workspaces/{args.workspace}/lineage/sql",
        payload={"sql_text": sql_text},
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(output_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
