# SchemaPilot Database Builder Contracts (v1, Contract-First)

Source: user-provided GPT Pro contract draft, adapted to current SchemaPilot endpoint conventions.

## 0) Contract Principles (Normative)

1. `Fail-closed`: critical operations MUST fail when audit write, secrets resolution, approvals, strict completeness, or plan checksum validation fails.
2. `Async runs`: provisioning/migration/load/sync are run-based operations that return `run_id`; no hidden synchronous side effects.
3. `Evidence-first`: every plan/apply emits evidence bundles with stable checksums.
4. `Idempotent mutations`: mutating endpoints support `Idempotency-Key`.
5. `Gateway single enforcement`: clients and AI query only through gateway; target DB remains internal.

## 1) Base Paths and Headers

- Control Plane base path: `/api/v1`
- Gateway base path: `/api/v1/gateway`
- Optional headers:
  - `X-Correlation-Id`
  - `Idempotency-Key` (required for mutating target-db plan/apply operations)

## 2) Error Contract (Shared)

```json
{
  "error_code": "APPROVAL_REQUIRED",
  "message": "Destructive migration requires approval.",
  "correlation_id": "req_01J0...",
  "details": {
    "workspace_id": "ws_123",
    "target_db_id": "tdb_456",
    "blocking_review_task_ids": ["rt_901", "rt_902"]
  }
}
```

Stable error codes (minimum set):

- `AUTH_REQUIRED`, `AUTH_INVALID`, `FORBIDDEN`
- `WORKSPACE_NOT_FOUND`, `TARGET_DB_NOT_FOUND`, `PLAN_NOT_FOUND`, `RUN_NOT_FOUND`
- `MODULE_DISABLED`
- `APPROVAL_REQUIRED`
- `PLAN_CHECKSUM_MISMATCH`, `OPERATION_ALREADY_APPLIED`, `RUN_IN_PROGRESS`
- `VALIDATION_FAILED`, `DRIFT_DETECTED`
- `STRICT_MODE_BLOCKED`
- `SECRETS_UNAVAILABLE`
- `AUDIT_WRITE_FAILED`
- `ENGINE_UNAVAILABLE`, `TIMEOUT`
- `INTERNAL_ERROR`

## 3) Canonical Resource Shapes

### 3.1 TargetDbProfile

```json
{
  "target_db_id": "tdb_456",
  "workspace_id": "ws_123",
  "name": "serving-db",
  "db_type": "postgres",
  "mode": "managed",
  "status": "draft",
  "desired_config_hash": "sha256:...",
  "connection": {
    "host": "postgres",
    "port": 5432,
    "database": "schemapilot_ws_123",
    "ssl_mode": "disable"
  },
  "credential_refs": {
    "reader": "sec_ref_reader_...",
    "writer": "sec_ref_writer_...",
    "admin_ephemeral": null
  }
}
```

Invariants:

- `mode=managed`: credentials are generated server-side/worker-side.
- `mode=external`: required credential refs must exist before validation/apply.
- Secret values are never returned, only references.

### 3.2 TargetDbState

```json
{
  "workspace_id": "ws_123",
  "active_target_db_id": "tdb_456",
  "current_build_id": "bld_789",
  "current_schema_ref": "sp_ws_123_bld_789",
  "last_successful_sync_at": "2026-02-18T00:00:00Z",
  "health": {
    "status": "healthy",
    "last_validation_run_id": "run_111",
    "last_error_evidence_bundle_id": null
  }
}
```

### 3.3 DbPlan (provision/migration/load/sync-plan)

```json
{
  "plan_id": "plan_abc",
  "plan_kind": "migration",
  "workspace_id": "ws_123",
  "target_db_id": "tdb_456",
  "plan_checksum": "sha256:...",
  "requires_approval": true,
  "destructive": true,
  "created_by_run_id": "run_222",
  "evidence_bundle_id": "ev_333",
  "status": "draft"
}
```

### 3.4 Evidence Contract: Migration Plan

`db_migration_plan_v1` should include:

- schema fingerprints (`from`/`to`)
- `plan_checksum`
- `destructive` + `risk_reasons`
- normalized SQL statement list
- prechecks/postchecks

Determinism rule:

- `plan_checksum = sha256(canonicalized_json)` with stable key ordering and normalized SQL whitespace.

### 3.5 Evidence Contract: Sync Report

`db_sync_report_v1` should include per dataset:

- sync strategy
- cursor hashes (before/after)
- row deltas
- strict completeness mode
- status and failure list

## 4) Control Plane API Contracts (v1)

All endpoints are run-based for plan/apply operations.

### 4.1 Target DB profile CRUD

- `POST /api/v1/workspaces/{workspace_id}/target-dbs`
- `GET /api/v1/workspaces/{workspace_id}/target-dbs`
- `GET /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}`
- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}:disable`

### 4.2 Validate

- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/validate`
- emits run kind: `TARGET_DB_VALIDATE`

### 4.3 Provision

- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/provision/plan`
- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/provision/apply`

Apply preconditions:

- plan exists
- checksum matches
- required approvals exist (server-side truth)
- audit write succeeds

### 4.4 Migrations

- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/migrations/plan`
- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/migrations/apply`

Destructive plans require explicit approval task decision(s).

### 4.5 Load + Publish

- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/load/plan`
- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/load/apply`

### 4.6 Sync

- `POST /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync:run`
- `GET /api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync/status`

### 4.7 Run + Evidence retrieval

- `GET /api/v1/workspaces/{workspace_id}/runs/{run_id}`
- `GET /api/v1/workspaces/{workspace_id}/runs/{run_id}/steps`
- `GET /api/v1/workspaces/{workspace_id}/evidence/{evidence_bundle_id}`

## 5) Gateway Contracts for Target DB Querying

Primary query endpoint (already existing):

- `POST /api/v1/gateway/query`

Extended request shape for target-db preference:

```json
{
  "workspace_id": "ws_123",
  "query": "SELECT ...",
  "engine_preference": "target_db",
  "max_rows": 1000
}
```

Response must include provenance fields when target-db engine is used:

- `target_db_id`
- `target_schema_ref`
- `build_id`
- `policy_decision_id`

Fail-closed semantics:

- unsafe SQL denied
- write operations denied
- entitlement and workspace violations denied
- unavailable target DB returns deterministic error

## 6) CLI Contracts (Operator-First)

### 6.1 Target DB lifecycle

```bash
schemapilot target-db create --workspace ws_123 --name serving-db --type postgres --mode managed
schemapilot target-db validate --workspace ws_123 --target-db tdb_456 --wait
schemapilot target-db provision plan --workspace ws_123 --target-db tdb_456 --wait
schemapilot target-db provision apply --workspace ws_123 --target-db tdb_456 --plan-id plan_prov_1 --expected-checksum sha256:... --wait
```

### 6.2 Migrations

```bash
schemapilot target-db migrate plan --workspace ws_123 --target-db tdb_456 --semantic sem_555 --build bld_789 --wait
schemapilot target-db migrate apply --workspace ws_123 --target-db tdb_456 --plan-id plan_mig_9 --expected-checksum sha256:... --wait
```

### 6.3 Load + publish

```bash
schemapilot target-db load plan --workspace ws_123 --target-db tdb_456 --build bld_789 --datasets gold.* --wait
schemapilot target-db load apply --workspace ws_123 --target-db tdb_456 --plan-id plan_load_3 --expected-checksum sha256:... --publish-on-success --wait
```

### 6.4 Sync + diagnostics

```bash
schemapilot target-db sync run --workspace ws_123 --target-db tdb_456 --datasets ds_invoices ds_customers --strict --wait
schemapilot target-db sync status --workspace ws_123 --target-db tdb_456
schemapilot run status --workspace ws_123 --run-id run_301
schemapilot evidence show --workspace ws_123 --evidence ev_333
schemapilot review list --workspace ws_123 --blocking
schemapilot review approve --workspace ws_123 --task rt_901
```

## 7) RBAC Baseline (v1)

- `workspace_admin`: target-db profile, plan/apply, non-destructive operations.
- `data_steward`: destructive migration approvals and sensitive governance decisions.
- `operator`: run triggers + status/evidence read; no destructive approvals.
- `auditor`: read-only audit/provenance/evidence export (redacted).

## 8) Required Test Matrix (Contract-Derived)

Control plane:

- plan/apply without approval -> `APPROVAL_REQUIRED`
- wrong checksum -> `PLAN_CHECKSUM_MISMATCH`
- idempotency key replay -> deduped outcome

Worker:

- deterministic plan checksums across repeated inputs
- transactional migration apply (no partial state)
- strict sync failure blocks run and cursor mutation

Gateway:

- read-only enforcement on target-db engine
- SQL safety denials for unsafe tokens/operators
- provenance target fields always present on target-db query

Deploy/security:

- no-bypass checks detect exposed target db ports
- doctor checks fail on unsafe bind/exposure

## 9) Mapping to Existing DB Task IDs

- `DB-0001`: adapter interface + registry
- `DB-0002`: target-db profile/state API + CLI wiring
- `DB-0003` + `DB-0004`: managed/external provisioning + validation
- `DB-0005`: deterministic DDL + type mapping
- `DB-0006` + `DB-0007`: migration plan/apply contracts and approval checks
- `DB-0008` + `DB-0009`: load/publish/rollback contract
- `DB-0010`: sync run + sync status + cursor semantics
- `DB-0011`: gateway target-db query contract + provenance fields
- `DB-0012`: no-bypass and doctor enforcement
- `DB-0013` + `DB-0014`: e2e and backup/restore contractual validation
- `DB-0015`: docs/runbook alignment
- `DB-0016`..`DB-0025`: engine expansion, ops hardening, caching, and advisory extensions

## 10) Non-Blocking Defaults (Conservative)

- MySQL managed mode is not required for v1; external-first is acceptable.
- DB-level RLS pushdown is optional defense-in-depth (gateway remains primary enforcement).
- For non-cursor sources in strict mode: deterministic full reload fallback is acceptable.
- Enterprise default should disable engine fallback and return explicit availability errors.
