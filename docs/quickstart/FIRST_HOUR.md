# First Hour Quickstart (Minimal UI)

SchemaPilot is intentionally CLI-first. UI is optional and minimal.

## 1) Start services

```bash
docker compose --profile team up -d control-plane gateway worker
```

Optional AI service:

```bash
docker compose --profile ai up -d ai-service
```

## 2) One-command first-hour onboarding (recommended)

```bash
schemapilot first-hour --workspace-name "First Hour Demo"
```

This command will:

- generate deterministic demo exports/documents,
- create a workspace and connect the source,
- queue a discover run (and wait by default),
- generate a semantic starter pack bundle,
- print exact next commands (status/query/analyze).

## 3) Guided onboarding alternative

```bash
schemapilot init --interactive --template-pack invoices --wait-for-run
```

## 4) Manual path (if needed)

```bash
schemapilot demo-generate --output-root runtime/demo/first_hour
schemapilot connect filesystem --workspace <workspace_id> --root runtime/demo/first_hour/exports
schemapilot run --workspace <workspace_id> --type discover
schemapilot status --workspace <workspace_id>
schemapilot templates apply invoices --workspace <workspace_id>
```

## 5) Run a governed query through gateway

Use gateway endpoint `/api/v1/gateway/query` with an allowed actor token.
All query/retrieval access must flow through gateway and emits provenance/audit.
