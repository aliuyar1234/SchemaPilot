"""Allowlisted AI tool endpoints (gateway/control-plane only)."""

from __future__ import annotations

from urllib.parse import urlsplit

_GATEWAY_ALLOWED: set[tuple[str, str]] = {
    ("POST", "/api/v1/gateway/query"),
    ("POST", "/api/v1/gateway/retrieve"),
    ("POST", "/api/v1/gateway/policy/simulate"),
}
_CONTROL_PLANE_ALLOWED: set[tuple[str, str]] = {
    ("GET", "/datasets"),
}


def validate_tool_endpoint(
    *,
    method: str,
    url: str,
    gateway_base_url: str,
    control_plane_base_url: str,
) -> None:
    """Fail closed when AI service tries to call non-allowlisted endpoints."""

    gateway_origin = _origin(gateway_base_url)
    control_plane_origin = _origin(control_plane_base_url)
    target = urlsplit(url.strip())
    target_origin = (target.scheme.lower(), target.netloc.lower())
    normalized_method = method.strip().upper()
    normalized_path = target.path.rstrip("/") or "/"
    if target_origin == gateway_origin and (normalized_method, normalized_path) in _GATEWAY_ALLOWED:
        return
    if target_origin == control_plane_origin and normalized_method == "GET":
        for _, suffix in _CONTROL_PLANE_ALLOWED:
            if (
                normalized_path.startswith("/api/v1/workspaces/")
                and normalized_path.endswith(suffix)
            ):
                return
    raise ValueError("ai_tool_endpoint_not_allowed")


def _origin(url: str) -> tuple[str, str]:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if scheme not in {"http", "https"} or not netloc:
        raise ValueError("ai_tool_endpoint_not_allowed")
    return scheme, netloc
