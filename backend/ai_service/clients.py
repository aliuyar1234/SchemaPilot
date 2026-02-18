"""HTTP clients for AI service integrations."""

from __future__ import annotations

import json
from urllib import error as urlerror
from urllib import request as urlrequest


class ServiceClientError(RuntimeError):
    """Raised when upstream service call fails."""


def request_json(
    *,
    method: str,
    url: str,
    payload: dict[str, object] | None = None,
    bearer_token: str | None = None,
) -> dict[str, object]:
    """Execute JSON HTTP request and parse JSON response."""
    body = json.dumps(payload, sort_keys=True).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = urlrequest.Request(  # nosec B310 - URL from operator config
        url,
        data=body,
        method=method.upper(),
        headers=headers,
    )
    try:
        with urlrequest.urlopen(req, timeout=5) as response:  # nosec B310
            raw = response.read().decode("utf-8")
            code = int(getattr(response, "status", 200))
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise ServiceClientError(f"upstream_http_{exc.code}:{raw}") from exc
    except (OSError, TimeoutError, urlerror.URLError) as exc:
        raise ServiceClientError("upstream_unavailable") from exc
    if code >= 400:
        raise ServiceClientError(f"upstream_http_{code}")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ServiceClientError("upstream_invalid_json") from exc
    if not isinstance(parsed, dict):
        raise ServiceClientError("upstream_invalid_json")
    return {str(k): v for k, v in parsed.items()}

