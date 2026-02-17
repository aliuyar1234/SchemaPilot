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

## Optional Kubernetes skeleton

`deploy/k8s/` contains non-default manifests for operators that need Kubernetes deployment wiring.
These manifests are intentionally minimal and should be adapted per environment standards.
