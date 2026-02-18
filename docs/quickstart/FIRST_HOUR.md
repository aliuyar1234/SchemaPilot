# First Hour Quickstart (Minimal UI)

SchemaPilot is intentionally CLI-first. UI is optional and minimal.

## 1) Generate deterministic demo data

```bash
schemapilot demo-generate --output-root runtime/demo/first_hour
```

## 2) Start services

```bash
docker compose --profile team up -d control-plane gateway worker
```

Optional AI service:

```bash
docker compose --profile ai up -d ai-service
```

## 3) Bootstrap workspace and source

```bash
schemapilot onboard-demo --workspace-name "First Hour Demo"
```

Or connect local exports manually:

```bash
schemapilot connect filesystem --workspace <workspace_id> --root runtime/demo/first_hour/exports
schemapilot run --workspace <workspace_id> --type discover
schemapilot status --workspace <workspace_id>
```

## 4) Run a governed query through gateway

Use gateway endpoint `/api/v1/gateway/query` with an allowed actor token.
All query/retrieval access must flow through gateway and emits provenance/audit.
