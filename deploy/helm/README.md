# SchemaPilot Helm Chart

This chart ships a hardened baseline with:

- gateway-first service exposure (`control-plane`, `gateway`, `ui`; optional `ai-service`),
- default deny ingress network policy,
- secret-driven runtime config (`.Values.secrets.name`),
- non-root containers with dropped Linux capabilities.

Install:

```bash
helm install schemapilot ./deploy/helm --namespace schemapilot --create-namespace
```

Enable AI service:

```bash
helm install schemapilot ./deploy/helm \
  --namespace schemapilot --create-namespace \
  --set aiService.enabled=true
```
