# spec/12_RUNBOOK.md

## Local Development Runbook

Goal: run SchemaPilot locally in progressive profiles with safe defaults.

### Prerequisites
- Docker + Docker Compose
- A local directory for data (or a local MinIO container)
- Ports available on localhost for API/UI/gateway

### Start (Team profile)
1) Configure environment (example keys; values are implementation-specific):
- `SCHEMAPILOT_PROFILE=team`
- `SCHEMAPILOT_BIND_ADDRESS=127.0.0.1`
- `SCHEMAPILOT_STORAGE_ROOT=/var/lib/schemapilot`
- `SCHEMAPILOT_POSTGRES_DSN=...`

2) Start services:
```bash
docker compose --profile team up -d
```

Expected:
- Containers are running.
- Health endpoints return success for API and gateway.

3) Verify health:
```bash
curl -s http://127.0.0.1:PORT/api/v1/health
```

Expected:
- JSON response indicates healthy status.

### Start (Starter profile)
Use the minimal stack:
```bash
docker compose --profile starter up -d
```

### Start (Enterprise profile)
Use strict governance modules (includes OPA profile wiring):
```bash
docker compose --profile enterprise up -d
```

evidence: spec/01_SCOPE.md :: Packaging Profiles as Upgrade Path

## Docker Compose Operations

### Stop
```bash
docker compose down
```

### Logs
```bash
docker compose logs -f --tail=200
```

### Safe exposure (non-local)
Rule:
- If `SCHEMAPILOT_BIND_ADDRESS` is non-local, authentication MUST be configured or the service fails to start.
evidence: DECISIONS.md :: D-0004 Safe startup defaults (localhost bind; auth required for non-local)

Procedure:
1) Configure auth (OIDC or enterprise-approved method).
2) Confirm deny-by-default policy.
3) Validate gateway non-bypass network isolation.
4) Run security denial tests before allowing external traffic.

## CI and Test Commands

Single entrypoint (recommended):
```bash
schemapilot check
```

Must include:
- formatting/lint/typecheck
- unit + integration + e2e
- security denial tests
- MessyBench generation/evaluation harness
- performance regression harness
- backup/restore drill
- secrets rotation drill
- manifest verification (for SSOT pack and repo as applicable)
evidence: checks/CHECKS_INDEX.md :: CHK-TOOLING-BASELINE

## Deployment Runbook (production baseline)

Production principles:
- Prefer immutable container images.
- Apply config via environment variables or mounted config files.
- Store secrets in secret stores; never in plaintext configs.

Deployment steps (Team profile):
1) Provision Postgres and object store (S3/MinIO).
2) Deploy control plane + workers + gateway.
3) Run migrations (one-time per version).
4) Verify health and deny-by-default posture.
5) Connect sources using UI or CLI.

Rollback:
- Roll back containers to prior image tags.
- Restore Postgres and object store from backups if required.
- Roll back gold `latest` pointer to last known good build if a publish is incorrect.
evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Deployment and Rollback

## Upgrade Procedure

Starter -> Team:
1) Enable object store + Iceberg + Trino services.
2) Configure storage root/bucket and metadata DB.
3) Re-materialize silver/gold from bronze snapshots.
4) Verify dataset IDs remain stable and gold semantics are versioned.
5) Record upgrade evidence.

evidence: spec/11_QUALITY_GATES.md :: G-COMP-0003 Profile Upgrade Safety

## Backup and Restore

### Backup
- Postgres: create a consistent logical backup.
- Object store: ensure versioning/snapshots for bronze/silver/gold prefixes.

### Restore drill (required before releases)
1) Restore Postgres into a new environment.
2) Restore object store data or pointers.
3) Start services and verify:
  - catalog is present,
  - last published gold pointer is readable,
  - gateway queries succeed with provenance.
4) Execute local drill command and archive report:
```bash
python tools/backup_restore_drill.py
```

Expected:
- output includes `PASS CHK-BACKUP-RESTORE`
- report is written to `runtime/backup_restore_drill/report.json`

evidence: spec/11_QUALITY_GATES.md :: G-OPS-0002 Backup Restore Drills

## Maintenance Playbook

### Common operational tasks
- Add a new source (scope preview -> approve -> discover -> profile)
- Handle schema drift (review task -> approve remediation -> rebuild)
- Backfill a dataset (bounded run; ensure idempotency)
- Execute deletion request (intake -> preview -> approvals -> execute -> evidence report)
- Rotate secrets (update secret store -> reload -> validate no leaks)
- Compact small files (if Iceberg; per ops procedure)

Secrets rotation drill command:
```bash
python tools/secrets_rotation_drill.py
```

Expected:
- output includes `PASS secrets rotation drill`
- report is written to `runtime/secrets_rotation_drill/report.json`

MessyBench and perf harness commands:
```bash
python tools/messybench_harness.py
python tools/perf_harness.py
```

Expected:
- outputs include `PASS MessyBench harness` and `PASS CHK-PERF-HARNESS`
- machine-readable results are written to `runtime/messybench/results.json` and `runtime/perf/results.json`

Deletion workflow reference:
evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Retention and Deletion Mechanics

## Troubleshooting

### Symptom: gold not publishing
Check:
- contract failures
- unresolved blocking review tasks
- drift events
- builder logs

Reference:
evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication

### Symptom: query denied unexpectedly
Check:
- policy decision logs and access decisions
- actor roles/attributes
- masking rules applied

Reference:
evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.access_decisions (append-only)

### Symptom: missing observability signals
Check:
- `/api/v1/metrics` on control plane and gateway
- dashboard definition at `deploy/dashboards/schemapilot_overview.json`
- structured logs include `correlation_id`, `service`, and `event_type`
