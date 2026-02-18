from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _write_jwks(path: Path, *, secret: bytes, kid: str = "key-1") -> str:
    jwks = {
        "keys": [
            {
                "kid": kid,
                "kty": "oct",
                "use": "sig",
                "alg": "HS256",
                "k": _b64url(secret),
            }
        ]
    }
    target = path / "jwks.json"
    target.write_text(json.dumps(jwks), encoding="utf-8")
    return target.as_uri()


def _jwt(claims: dict[str, object], *, secret: bytes, kid: str = "key-1") -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": kid}
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_claims = _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_claims}".encode()
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_claims}.{_b64url(signature)}"


def _settings(jwks_url: str) -> Settings:
    return Settings(
        profile="enterprise",
        bind_address="127.0.0.1",
        auth_mode="oidc_jwt",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_control_oidc_jwt.db",
        oidc_required_issuer="https://issuer.example",
        oidc_required_audience="schemapilot-control-plane",
        oidc_jwks_url=jwks_url,
        oidc_jwt_allowed_algs=("HS256",),
    )


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_control_plane_oidc_jwt_allows_platform_admin(tmp_path: Path) -> None:
    secret = b"schemapilot-secret"
    settings = _settings(_write_jwks(tmp_path, secret=secret))
    client = TestClient(create_app(settings_factory=lambda: settings))
    claims = {
        "iss": "https://issuer.example",
        "aud": "schemapilot-control-plane",
        "sub": "user:jwt_admin",
        "roles": ["platform_admin"],
        "exp": int(time.time()) + 300,
    }
    token = _jwt(claims, secret=secret)
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "jwt-auth", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "jwt-auth"


def test_control_plane_oidc_jwt_denies_invalid_signature(tmp_path: Path) -> None:
    secret = b"schemapilot-secret"
    settings = _settings(_write_jwks(tmp_path, secret=secret))
    client = TestClient(create_app(settings_factory=lambda: settings))
    claims = {
        "iss": "https://issuer.example",
        "aud": "schemapilot-control-plane",
        "sub": "user:jwt_admin",
        "roles": ["platform_admin"],
        "exp": int(time.time()) + 300,
    }
    token = _jwt(claims, secret=b"wrong-secret")
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "jwt-auth", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_header(token),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "missing_or_invalid_auth_token"


def test_control_plane_oidc_jwt_denies_insufficient_role(tmp_path: Path) -> None:
    secret = b"schemapilot-secret"
    settings = _settings(_write_jwks(tmp_path, secret=secret))
    client = TestClient(create_app(settings_factory=lambda: settings))
    claims = {
        "iss": "https://issuer.example",
        "aud": "schemapilot-control-plane",
        "sub": "user:jwt_analyst",
        "roles": ["analyst"],
        "exp": int(time.time()) + 300,
    }
    token = _jwt(claims, secret=secret)
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "jwt-auth", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_header(token),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "missing_required_role"


def test_control_plane_oidc_jwt_denies_expired_token(tmp_path: Path) -> None:
    secret = b"schemapilot-secret"
    settings = _settings(_write_jwks(tmp_path, secret=secret))
    client = TestClient(create_app(settings_factory=lambda: settings))
    claims = {
        "iss": "https://issuer.example",
        "aud": "schemapilot-control-plane",
        "sub": "user:jwt_admin",
        "roles": ["platform_admin"],
        "exp": int(time.time()) - 60,
    }
    token = _jwt(claims, secret=secret)
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "jwt-auth", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_header(token),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "missing_or_invalid_auth_token"
