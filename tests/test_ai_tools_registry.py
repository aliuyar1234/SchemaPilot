from __future__ import annotations

import pytest

from backend.ai_service.clients import ServiceClientError, request_json
from backend.ai_service.tools_registry import validate_tool_endpoint


def test_validate_tool_endpoint_allows_gateway_query() -> None:
    validate_tool_endpoint(
        method="POST",
        url="http://127.0.0.1:8001/api/v1/gateway/query",
        gateway_base_url="http://127.0.0.1:8001",
        control_plane_base_url="http://127.0.0.1:8000",
    )


def test_validate_tool_endpoint_allows_control_plane_datasets() -> None:
    validate_tool_endpoint(
        method="GET",
        url="http://127.0.0.1:8000/api/v1/workspaces/ws-1/datasets",
        gateway_base_url="http://127.0.0.1:8001",
        control_plane_base_url="http://127.0.0.1:8000",
    )


def test_validate_tool_endpoint_blocks_non_allowlisted_path() -> None:
    with pytest.raises(ValueError, match="ai_tool_endpoint_not_allowed"):
        validate_tool_endpoint(
            method="POST",
            url="http://127.0.0.1:8001/api/v1/gateway/admin",
            gateway_base_url="http://127.0.0.1:8001",
            control_plane_base_url="http://127.0.0.1:8000",
        )


def test_validate_tool_endpoint_blocks_control_plane_apply_endpoint() -> None:
    with pytest.raises(ValueError, match="ai_tool_endpoint_not_allowed"):
        validate_tool_endpoint(
            method="POST",
            url=(
                "http://127.0.0.1:8000/api/v1/workspaces/ws-1/"
                "policy-pack/change-requests/cr-1/decision"
            ),
            gateway_base_url="http://127.0.0.1:8001",
            control_plane_base_url="http://127.0.0.1:8000",
        )


def test_request_json_blocks_disallowed_ai_tool_endpoint_preflight() -> None:
    with pytest.raises(ServiceClientError, match="ai_tool_endpoint_not_allowed"):
        request_json(
            method="POST",
            url="http://127.0.0.1:8001/api/v1/gateway/admin",
            gateway_base_url="http://127.0.0.1:8001",
            control_plane_base_url="http://127.0.0.1:8000",
        )
