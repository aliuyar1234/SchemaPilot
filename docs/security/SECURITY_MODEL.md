# Security Model

SchemaPilot defaults to fail-closed behavior.

## Core invariants

- Gateway is the single enforcement point for query and retrieval.
- Control Plane and Gateway require auth on non-local bind.
- Audit writes are mandatory for critical operations.
- Policy denials and missing prerequisites return explicit errors.

## Auth modes

- `local`: token map for local/dev and controlled team environments.
- `oidc_jwt`: direct JWT verification via JWKS.
- `oidc_trusted_proxy`: allowed only with explicit trusted-proxy config.

## No-bypass

- Engine/index ports are internal-only in Compose/K8s defaults.
- Static checks (`tools/check_no_bypass_ports.py`) enforce deploy invariants.

## Optional modules

- AI service, OpenSearch, Qdrant, and plugin execution are disabled by default.
- Enabling optional modules requires explicit config and preserves gateway policy checks.
