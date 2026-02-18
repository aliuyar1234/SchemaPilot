"""Shared authentication helpers for control-plane and gateway services."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import Request

from backend.shared_domain.config import Settings
from backend.shared_domain.policy_packs import find_policy_pack_template

DEFAULT_LOCAL_AUTH_TOKENS: dict[str, dict[str, object]] = {
    "local-analyst-token": {
        "actor_id": "user:local_analyst",
        "actor_type": "human",
        "roles": ["analyst"],
        "attributes": {},
    },
    "local-region-analyst-token": {
        "actor_id": "user:regional_analyst",
        "actor_type": "human",
        "roles": ["analyst"],
        "attributes": {"region": "eu"},
    },
    "local-data-steward-token": {
        "actor_id": "user:local_steward",
        "actor_type": "human",
        "roles": ["data_steward"],
        "attributes": {},
    },
    "local-platform-admin-token": {
        "actor_id": "user:local_admin",
        "actor_type": "human",
        "roles": ["platform_admin"],
        "attributes": {},
    },
    "local-ai-token": {
        "actor_id": "agent:local_ai",
        "actor_type": "ai",
        "roles": ["ai_agent"],
        "attributes": {"ai_allowlisted": False, "allowed_dataset_ids": []},
    },
    "local-ai-reader-token": {
        "actor_id": "agent:local_ai_reader",
        "actor_type": "ai",
        "roles": ["ai_agent"],
        "attributes": {"ai_allowlisted": True, "allowed_dataset_ids": ["dataset-1"]},
    },
}


@dataclass(frozen=True)
class _JwksCacheEntry:
    expires_at: float
    keys: list[dict[str, object]]


_JWKS_CACHE: dict[str, _JwksCacheEntry] = {}


def load_local_auth_tokens(
    defaults: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, dict[str, object]]:
    """Load local bearer token mappings from defaults + env overrides."""
    tokens: dict[str, dict[str, object]] = {}
    for token, actor in (defaults or DEFAULT_LOCAL_AUTH_TOKENS).items():
        if not isinstance(token, str):
            continue
        tokens[token] = _sanitize_actor_payload(actor, fallback_actor_id=f"user:{token}")
    tokens = deepcopy(tokens)
    raw = os.getenv("SCHEMAPILOT_LOCAL_AUTH_TOKENS")
    if raw is not None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            overrides: dict[str, dict[str, object]] = {}
            for token, actor in parsed.items():
                if not isinstance(token, str) or not isinstance(actor, dict):
                    continue
                overrides[token] = _sanitize_actor_payload(actor, fallback_actor_id=f"user:{token}")
            if overrides:
                tokens = overrides
    _apply_policy_pack_overrides(tokens)
    return tokens


def authenticated_actor_from_request(
    request: Request,
    *,
    settings: Settings,
    auth_tokens: Mapping[str, Mapping[str, object]],
) -> dict[str, object] | None:
    """Resolve authenticated actor context from bearer token, trusted OIDC claims, or OIDC JWT."""
    auth_mode = _normalized_auth_mode(settings.auth_mode)
    if auth_mode == "oidc_trusted_proxy":
        return authenticated_actor_from_oidc_claims(request, settings=settings)
    if auth_mode == "oidc_jwt":
        return authenticated_actor_from_oidc_jwt(request, settings=settings)
    token = _bearer_token(request)
    if token is None:
        return None
    actor = auth_tokens.get(token)
    if actor is None:
        return None
    return _sanitize_actor_payload(actor, fallback_actor_id=f"user:{token}")


def authenticated_actor_from_oidc_claims(
    request: Request, *, settings: Settings
) -> dict[str, object] | None:
    """Resolve actor context from trusted ingress-provided OIDC claims."""
    claims_header = request.headers.get(settings.oidc_claims_header, "")
    if not claims_header:
        return None
    try:
        claims = json.loads(claims_header)
    except json.JSONDecodeError:
        return None
    if not isinstance(claims, dict):
        return None
    if not _claims_match_issuer_and_audience(claims, settings=settings):
        return None
    return _actor_from_claims(claims, settings=settings)


def authenticated_actor_from_oidc_jwt(
    request: Request, *, settings: Settings
) -> dict[str, object] | None:
    """Resolve actor context from verified OIDC JWT bearer tokens."""
    token = _bearer_token(request)
    if token is None:
        return None
    claims = _verified_oidc_jwt_claims(token, settings=settings)
    if claims is None:
        return None
    return _actor_from_claims(claims, settings=settings)


def _verified_oidc_jwt_claims(token: str, *, settings: Settings) -> dict[str, object] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header = _decode_jwt_segment(parts[0])
    claims = _decode_jwt_segment(parts[1])
    if not isinstance(header, dict) or not isinstance(claims, dict):
        return None
    alg = str(header.get("alg", "")).strip()
    if not alg or alg.lower() == "none":
        return None
    allowed_algs = {item.strip() for item in settings.oidc_jwt_allowed_algs if item.strip()}
    if alg not in allowed_algs:
        return None

    signing_input = f"{parts[0]}.{parts[1]}".encode()
    signature = _decode_base64url(parts[2])
    if signature is None:
        return None

    keys = _load_jwks_keys(settings=settings)
    if not keys:
        return None
    kid_raw = header.get("kid")
    kid = str(kid_raw).strip() if isinstance(kid_raw, str) and kid_raw.strip() else None
    candidates = _select_jwks_candidates(keys=keys, kid=kid, alg=alg)
    if not candidates:
        return None
    if not any(
        _verify_jwt_signature(signing_input, signature, alg=alg, jwk=key) for key in candidates
    ):
        return None

    if not _claims_match_issuer_and_audience(claims, settings=settings):
        return None
    if not _claims_within_time_window(claims, settings=settings):
        return None
    return claims


def _claims_match_issuer_and_audience(claims: dict[str, object], *, settings: Settings) -> bool:
    if settings.oidc_required_issuer:
        issuer = str(claims.get("iss", ""))
        if issuer != settings.oidc_required_issuer:
            return False
    if settings.oidc_required_audience:
        audience_claim = claims.get("aud")
        if isinstance(audience_claim, str):
            return audience_claim == settings.oidc_required_audience
        if isinstance(audience_claim, list):
            return settings.oidc_required_audience in {str(item) for item in audience_claim}
        return False
    return True


def _claims_within_time_window(claims: dict[str, object], *, settings: Settings) -> bool:
    now = int(time.time())
    skew = max(0, settings.oidc_clock_skew_seconds)
    exp = _as_int(claims.get("exp"))
    if exp is not None and now > exp + skew:
        return False
    nbf = _as_int(claims.get("nbf"))
    if nbf is not None and now + skew < nbf:
        return False
    iat = _as_int(claims.get("iat"))
    if iat is not None and now + skew < iat:
        return False
    return True


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _select_jwks_candidates(
    *, keys: list[dict[str, object]], kid: str | None, alg: str
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for key in keys:
        key_kid = str(key.get("kid", "")).strip()
        if kid is not None and key_kid != kid:
            continue
        key_alg = str(key.get("alg", "")).strip()
        if key_alg and key_alg != alg:
            continue
        key_use = str(key.get("use", "")).strip().lower()
        if key_use and key_use != "sig":
            continue
        candidates.append(key)
    return candidates


def _verify_jwt_signature(
    signing_input: bytes, signature: bytes, *, alg: str, jwk: dict[str, object]
) -> bool:
    if alg not in {"HS256", "HS384", "HS512"}:
        return False
    if str(jwk.get("kty", "")).lower() != "oct":
        return False
    key_material_raw = jwk.get("k")
    if not isinstance(key_material_raw, str):
        return False
    key_material = _decode_base64url(key_material_raw)
    if key_material is None:
        return False

    if alg == "HS256":
        digest = hashlib.sha256
    elif alg == "HS384":
        digest = hashlib.sha384
    elif alg == "HS512":
        digest = hashlib.sha512
    else:
        return False
    expected = hmac.new(key_material, signing_input, digest).digest()
    return hmac.compare_digest(expected, signature)


def _load_jwks_keys(*, settings: Settings) -> list[dict[str, object]]:
    jwks_url = _resolve_jwks_url(settings=settings)
    if jwks_url is None:
        return []
    now = time.time()
    cached = _JWKS_CACHE.get(jwks_url)
    if cached is not None and now < cached.expires_at:
        return cached.keys

    keys = _fetch_jwks_keys(jwks_url)
    if not keys:
        return []
    expires_at = now + float(max(1, settings.oidc_jwks_cache_ttl_seconds))
    _JWKS_CACHE[jwks_url] = _JwksCacheEntry(expires_at=expires_at, keys=keys)
    return keys


def _fetch_jwks_keys(jwks_url: str) -> list[dict[str, object]]:
    try:
        with urlrequest.urlopen(jwks_url, timeout=3) as response:  # nosec B310
            payload = response.read().decode("utf-8")
    except (OSError, TimeoutError, ValueError, urlerror.URLError):
        return []
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        keys_raw = parsed.get("keys", [])
    else:
        keys_raw = parsed
    if not isinstance(keys_raw, list):
        return []
    keys: list[dict[str, object]] = []
    for item in keys_raw:
        if isinstance(item, dict):
            keys.append(item)
    return keys


def _resolve_jwks_url(*, settings: Settings) -> str | None:
    if settings.oidc_jwks_url and settings.oidc_jwks_url.strip():
        return settings.oidc_jwks_url.strip()
    if settings.oidc_required_issuer and settings.oidc_required_issuer.strip():
        return settings.oidc_required_issuer.rstrip("/") + "/.well-known/jwks.json"
    return None


def _decode_jwt_segment(encoded: str) -> dict[str, object] | None:
    decoded_bytes = _decode_base64url(encoded)
    if decoded_bytes is None:
        return None
    try:
        payload = json.loads(decoded_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _decode_base64url(value: str) -> bytes | None:
    if not value:
        return b""
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, binascii.Error, AttributeError):
        return None


def _normalized_auth_mode(auth_mode: str) -> str:
    normalized = auth_mode.strip().lower()
    if normalized == "oidc":
        return "oidc_trusted_proxy"
    return normalized


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "").strip()
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return token or None


def _actor_from_claims(
    claims: dict[str, object], *, settings: Settings
) -> dict[str, object] | None:
    actor_id = str(claims.get(settings.oidc_actor_id_claim, "")).strip()
    if not actor_id:
        return None
    roles_raw = claims.get(settings.oidc_roles_claim, [])
    roles = [str(item) for item in roles_raw] if isinstance(roles_raw, list) else []
    if not roles:
        role_text = str(roles_raw) if roles_raw else ""
        roles = [role_text] if role_text else []
    attributes_raw = claims.get(settings.oidc_attributes_claim, {})
    attributes = attributes_raw if isinstance(attributes_raw, dict) else {}
    return {
        "actor_id": actor_id,
        "actor_type": str(claims.get("actor_type", "human")),
        "roles": roles,
        "attributes": attributes,
    }


def actor_has_any_role(actor: Mapping[str, object], required_roles: set[str]) -> bool:
    """Check whether actor roles satisfy at least one required role."""
    roles_raw = actor.get("roles", [])
    if not isinstance(roles_raw, list):
        return False
    roles = {str(item) for item in roles_raw}
    return bool(roles & required_roles)


def _sanitize_actor_payload(
    actor: Mapping[str, object], *, fallback_actor_id: str
) -> dict[str, object]:
    roles_raw = actor.get("roles", [])
    roles = [str(item) for item in roles_raw] if isinstance(roles_raw, list) else []
    attributes_raw = actor.get("attributes", {})
    attributes = attributes_raw if isinstance(attributes_raw, dict) else {}
    return {
        "actor_id": str(actor.get("actor_id", fallback_actor_id)),
        "actor_type": str(actor.get("actor_type", "human")),
        "roles": roles,
        "attributes": attributes,
    }


def _apply_policy_pack_overrides(tokens: dict[str, dict[str, object]]) -> None:
    raw = os.getenv("SCHEMAPILOT_LOCAL_AUTH_PACKS")
    if raw is None:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(parsed, dict):
        return
    for token, pack_id in parsed.items():
        if not isinstance(token, str) or not isinstance(pack_id, str):
            continue
        template = find_policy_pack_template(pack_id)
        if template is None:
            continue
        current = tokens.get(token, {"actor_id": f"user:{token}"})
        roles_raw = template.get("roles", [])
        roles = [str(item) for item in roles_raw] if isinstance(roles_raw, list) else []
        attributes_raw = template.get("attributes", {})
        attributes = attributes_raw if isinstance(attributes_raw, dict) else {}
        current["actor_type"] = str(template.get("actor_type", current.get("actor_type", "human")))
        current["roles"] = roles
        current["attributes"] = attributes
        tokens[token] = current
