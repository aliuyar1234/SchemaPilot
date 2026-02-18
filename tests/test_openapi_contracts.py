from __future__ import annotations

from pathlib import Path

from tools.check_openapi_compat import (
    compare_openapi_compatibility,
    validate_openapi_compatibility,
)


def test_openapi_contract_baselines_are_compatible() -> None:
    errors = validate_openapi_compatibility(Path("."))
    assert errors == []


def test_openapi_contract_checker_detects_missing_path() -> None:
    canonical = {
        "paths": {
            "/api/v1/example": {
                "get": {"responses": {"200": {"description": "ok"}}},
            }
        }
    }
    current = {"paths": {}}
    errors = compare_openapi_compatibility(
        canonical=canonical,
        current=current,
        service_name="control_plane",
    )
    assert any("missing path /api/v1/example" in error for error in errors)
