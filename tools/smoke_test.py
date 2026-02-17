#!/usr/bin/env python3
"""Minimal smoke test for API and gateway health endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app


def main() -> int:
    control_client = TestClient(create_app())
    gateway_client = TestClient(create_gateway_app())

    control_response = control_client.get("/api/v1/health")
    gateway_response = gateway_client.get("/api/v1/health")

    if control_response.status_code != 200:
        print("FAIL control-plane health")
        return 1
    if gateway_response.status_code != 200:
        print("FAIL gateway health")
        return 1
    print("PASS CHK-SMOKE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
