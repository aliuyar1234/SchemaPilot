# Deploy Module

This folder contains local and production deployment assets.

## Docker Compose profiles

Starter profile (minimal local path):

```bash
docker compose --profile starter up -d
```

Team profile (adds object storage + Trino baseline):

```bash
docker compose --profile team up -d
```

Enterprise profile (adds OPA adapter path):

```bash
docker compose --profile enterprise up -d
```

Starter uses the minimal stack. Team and Enterprise add modules progressively without requiring
source re-ingestion.

## Enterprise auth path (OIDC-first)

Enterprise deployments should terminate authentication in a trusted ingress/proxy and forward
validated claims to SchemaPilot using a dedicated header.

Recommended environment variables:

- `SCHEMAPILOT_AUTH_MODE=oidc`
- `SCHEMAPILOT_OIDC_CLAIMS_HEADER=x-schemapilot-oidc-claims`
- `SCHEMAPILOT_OIDC_REQUIRED_ISSUER=https://<issuer>`
- `SCHEMAPILOT_OIDC_REQUIRED_AUDIENCE=<audience>`
- `SCHEMAPILOT_OIDC_ACTOR_ID_CLAIM=sub` (default claim for actor id)
- `SCHEMAPILOT_OIDC_ROLES_CLAIM=roles` (default claim for actor roles)
- `SCHEMAPILOT_OIDC_ATTRIBUTES_CLAIM=attributes` (default claim for ABAC attributes)

Gateway behavior is fail-closed:
- missing/invalid trusted claims header -> deny
- issuer/audience mismatch -> deny
- missing role claims -> deny by policy

## Policy packs and permission templates

Policy packs are bundled for common setups and can seed actor templates and role models:

- `starter_local_team`
- `enterprise_finance_strict`
- `enterprise_ai_assistant`

Discover packs through control plane API:

```bash
curl -s http://127.0.0.1:8000/api/v1/policy-packs
```

### Policy pack authoring

`backend/shared_domain/policy_packs.json` is the canonical bundle format.
Each pack entry must include:

- `id`: stable slug used by API and optional local auth template selection.
- `name`: operator-friendly label.
- `description`: short purpose statement.
- `template_actor`: actor payload used as default role/attribute template.

`template_actor` shape:

- `actor_type`: `human` or `ai`
- `roles`: list of role strings
- `attributes`: free-form object for ABAC and retrieval entitlements

The loader in `backend/shared_domain/policy_packs.py` reads this file, exposes summary metadata for discovery, and resolves `template_actor` by `id`.

## Optional Kubernetes skeleton

`deploy/k8s/` contains non-default manifests for operators that need Kubernetes deployment wiring.
These manifests are intentionally minimal and should be adapted per environment standards.
