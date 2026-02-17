# spec/04_INTERFACES_AND_CONTRACTS.md

## Public Contract Policy

Compatibility surfaces include:
- REST API endpoints and payloads
- CLI commands and flags
- Machine-readable file formats: manifests, recommendation reports, semantic manifests
- Event schemas (if emitted)

Rules:
- Any change to a public contract MUST:
  1) update this spec,
  2) include compatibility rationale,
  3) add tests enforcing compatibility.
- Breaking changes require explicit deprecation lifecycle.
evidence: CONSTITUTION.md :: SB-0009 Contract drift (implementation ≠ interfaces/spec)

## API Surface

### Base
- Base path: `/api/v1`
- Transport: HTTPS when exposed; localhost-only by default.
- Auth: see security baseline.
  - evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Authentication and Authorization

### Core resources (minimum)
- Workspaces
  - `GET /api/v1/workspaces`
  - `POST /api/v1/workspaces`
  - `GET /api/v1/workspaces/{workspace_id}`
- Sources
  - `POST /api/v1/workspaces/{workspace_id}/sources`
  - `GET /api/v1/workspaces/{workspace_id}/sources`
- Datasets
  - `GET /api/v1/workspaces/{workspace_id}/datasets`
  - `GET /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}`
- Runs
  - `POST /api/v1/workspaces/{workspace_id}/runs` (start discover/profile/build/recommend)
  - `GET /api/v1/workspaces/{workspace_id}/runs/{run_id}`
- Review Queue
  - `GET /api/v1/workspaces/{workspace_id}/review_tasks`
  - `POST /api/v1/workspaces/{workspace_id}/review_tasks/{task_id}/decision`
- Decision Engine
  - `POST /api/v1/workspaces/{workspace_id}/recommendations`
  - `GET /api/v1/workspaces/{workspace_id}/recommendations/{report_id}`
- Gateway (SQL/retrieval)
  - `POST /api/v1/gateway/query`
  - `POST /api/v1/gateway/retrieve`

### Example: create a source (filesystem)

Request:
```json
{
  "source_type": "filesystem",
  "scope": {
    "root_path": "/data/exports",
    "include_globs": ["**/*.csv", "**/*.xlsx", "**/*.json", "**/*.pdf"],
    "exclude_globs": ["**/archive/**"]
  },
  "display_name": "Exports share"
}
```

Response:
```json
{
  "source_id": "9f4e2c36-0a3b-4d1d-9b7c-4c2a2b9e4f21",
  "status": "active"
}
```

Invariants:
- Source discovery is read-only.
- Scope changes require audit log entries.
evidence: spec/03_DOMAIN_MODEL.md :: Source

## Query Gateway Contract

### SQL query (required; SQL-first AI)

Endpoint: `POST /api/v1/gateway/query`

Request:
```json
{
  "workspace_id": "4f4b83b3-4a3f-4d7d-8cf1-3c9a7e0b2d11",
  "actor": {
    "actor_id": "user:alice",
    "actor_type": "human",
    "roles": ["analyst"],
    "attributes": {"department": "finance", "region": "eu"}
  },
  "query": {
    "language": "sql",
    "text": "SELECT region, SUM(amount_eur) AS revenue FROM gold.fact_invoices GROUP BY region"
  },
  "constraints": {
    "max_rows": 1000,
    "timeout_ms": 30000
  }
}
```

Response:
```json
{
  "result": {
    "columns": [{"name": "region", "type": "varchar"}, {"name": "revenue", "type": "decimal"}],
    "rows": [["EU", "12345.67"], ["US", "8901.23"]],
    "row_count": 2
  },
  "provenance": {
    "datasets_used": [
      {"dataset_id": "b6c3f1d2-5b6c-4c1a-9a0d-4a3b2c1d0e9f", "snapshot_id": "snap_01"}
    ],
    "policy_decision_id": "01J2V0C0P8G8F7Q2A0K9F2Q1D3",
    "build_id": "01J2V0A7E9S2F1Q8M2N3P4R5T6"
  },
  "audit_event_id": "01J2V0D9C1N2M3B4V5C6X7Z8Y9"
}
```

MUST requirements:
- Gateway MUST evaluate RBAC/ABAC, apply masking/row filters, and emit an AccessDecision.
- Gateway MUST attach provenance and policy decision ID to every response.
- Gateway MUST deny by default for AI tool identities.
- Gateway MUST be the only path to query engines and indexes.
evidence: DECISIONS.md :: D-0003 Query Gateway is the single enforcement point (no bypass)

### Retrieval (optional module; policy-filtered)

Endpoint: `POST /api/v1/gateway/retrieve`

Request includes:
- query text
- requested corpus constraints (dataset IDs, date ranges)
- actor identity and attributes

Response includes:
- results with citations to bronze artifacts
- provenance and policy decision ID

## CLI Surface

CLI is a thin wrapper around API contracts; it MUST NOT implement hidden logic.

Commands (minimum):
- `schemapilot doctor` (environment preflight; prints required fixes)
- `schemapilot init` (generates local config skeleton; does not store secrets)
- `schemapilot connect` (registers sources; read-only discovery)
- `schemapilot run` (start runs: discover/profile/build/recommend)
- `schemapilot status` (show runs, tasks, builds)
- `schemapilot check` (runs quality checks locally/CI)

Example:
```bash
schemapilot doctor
schemapilot init --profile team
schemapilot connect --source filesystem --root /data/exports
schemapilot run --workspace default --type discover
schemapilot status --workspace default
```

## Event and File Formats

### Ingest manifest format (bronze; required)
Stored alongside bronze artifacts.

Fields (minimum):
- `manifest_version`
- `artifact_id`, `content_hash`, `source_locator`
- `parser` + `parser_version` + `parse_params`
- `discovered_schema` (if parsed)
- `run_id`

### Recommendation Report Format (Decision Engine; required)
The report MUST include:
- fixed template IDs T1..T8
- hard constraint gates (pass/fail)
- score breakdown (per criterion)
- confidence
- missing evidence list
- approval_required boolean with reasons list

This report is stored as YAML or JSON and referenced by `report_id`.
evidence: spec/03_DOMAIN_MODEL.md :: RecommendationReport (Decision Engine output)

### Semantic manifest (gold; required)
A versioned manifest describing:
- gold views/tables
- metric definitions, grains, and dependencies
- published snapshot IDs

## Error Model

All API endpoints MUST return a standard error shape on failure:

```json
{
  "error": {
    "code": "POLICY_DENIED",
    "message": "Access denied by policy",
    "details": {"policy_decision_id": "01J2..."},
    "request_id": "01J2..."
  }
}
```

Rules:
- `code` is stable and documented.
- `request_id` is returned for correlation and must appear in logs.
evidence: spec/08_OBSERVABILITY.md :: Logging Standard

## Versioning and Deprecation Policy

- API versioning: `/api/v1` path version.
- Contract changes:
  - Patch: bug fixes; no contract changes.
  - Minor: backward compatible additions only.
  - Major: may include removals after deprecation window.

Deprecation lifecycle (minimum):
1) Mark deprecated fields/endpoints; keep behavior compatible.
2) Emit warnings (logs and API metadata).
3) Remove only in next major release with migration guidance.

## Compatibility Guarantees

- Template IDs T1..T8 are stable (Decision Engine contract).
- Gateway provenance fields are stable; clients rely on them.
- Bronze manifest schema changes require version bump and backward compatibility reader.
- Postgres migrations must be reversible or have a documented rollback strategy.
evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Migrations and Rollback
