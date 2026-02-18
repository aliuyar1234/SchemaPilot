"""Minimal typed client wrappers for Control Plane and Gateway."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request as urlrequest


@dataclass(frozen=True)
class SchemaPilotClient:
    """Typed client with explicit base URLs and bearer tokens."""

    control_plane_url: str
    gateway_url: str
    control_plane_token: str | None = None
    gateway_token: str | None = None

    def list_workspaces(self) -> list[dict[str, object]]:
        payload = self._request_json(
            method="GET",
            url=f"{self.control_plane_url.rstrip('/')}/api/v1/workspaces",
            bearer_token=self.control_plane_token,
        )
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    def query_sql(
        self,
        *,
        workspace_id: str,
        sql_text: str,
        dataset_id: str,
    ) -> dict[str, object]:
        payload = self._request_json(
            method="POST",
            url=f"{self.gateway_url.rstrip('/')}/api/v1/gateway/query",
            bearer_token=self.gateway_token,
            payload={
                "workspace_id": workspace_id,
                "query": {"language": "sql", "text": sql_text},
                "resource_attributes": {"dataset_id": dataset_id},
            },
        )
        return payload if isinstance(payload, dict) else {}

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        bearer_token: str | None,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object] | list[dict[str, object]]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        request = urlrequest.Request(url=url, method=method.upper(), data=body, headers=headers)
        with urlrequest.urlopen(request, timeout=10) as response:  # nosec B310
            raw = response.read().decode("utf-8")
        if not raw.strip():
            return {}
        parsed: Any = json.loads(raw)
        if isinstance(parsed, list):
            return [row for row in parsed if isinstance(row, dict)]
        if isinstance(parsed, dict):
            return parsed
        return {}
