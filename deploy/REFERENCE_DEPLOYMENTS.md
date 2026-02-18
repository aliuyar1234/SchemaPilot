# Reference Deployments

SchemaPilot ships three reference deployment profiles with secure defaults.

## Minimal

- target: local evaluation
- command: `docker compose --profile starter up -d`
- external ports: control plane `8000`, gateway `8001`, UI `5173`
- notes: query/retrieval enforcement remains gateway-only; no direct engine ports.

## Team

- target: small/medium production-like teams
- command: `docker compose --profile team up -d`
- adds: worker loop, Trino path (internal-only), stronger policy/review defaults.
- notes: run `python -m cli.schemapilot_cli.main doctor` after startup.

## Enterprise

- target: hardened org environments
- command: `docker compose --profile enterprise up -d`
- adds: stricter auth/integration expectations and no-bypass network posture.
- notes: prefer Helm/K8s manifests under `deploy/helm` and `deploy/k8s`.

## Validation checklist

1. `python tools/check_no_bypass_ports.py`
2. `python -m cli.schemapilot_cli.main doctor`
3. `python tools/release_gate.py --output runtime/release_gate/report.json`
