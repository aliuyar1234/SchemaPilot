"""Shared authentication helpers for control-plane and gateway services."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from copy import deepcopy

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
    """Resolve authenticated actor context from bearer token or trusted OIDC claims."""
    auth_mode = settings.auth_mode.lower()
    if auth_mode == "oidc":
        return authenticated_actor_from_oidc_claims(request, settings=settings)
    authorization = request.headers.get("authorization", "").strip()
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
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
    if settings.oidc_required_issuer:
        issuer = str(claims.get("iss", ""))
        if issuer != settings.oidc_required_issuer:
            return None
    if settings.oidc_required_audience:
        audience_claim = claims.get("aud")
        allowed = False
        if isinstance(audience_claim, str):
            allowed = audience_claim == settings.oidc_required_audience
        elif isinstance(audience_claim, list):
            allowed = settings.oidc_required_audience in {str(item) for item in audience_claim}
        if not allowed:
            return None
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
