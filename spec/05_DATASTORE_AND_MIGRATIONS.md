# spec/05_DATASTORE_AND_MIGRATIONS.md

## Storage Overview

SchemaPilot uses:
- **Postgres** for metadata, approvals, audit logs, policies, ER decisions.
- **Object storage** (local filesystem, MinIO, or S3) for bronze/silver/gold artifacts.
- **Query engines** (DuckDB/Trino) read from object storage; writes happen via builders.

Layer rules are canonical:
evidence: DECISIONS.md :: D-0006 Storage layer strategy (Bronze immutable; Silver ER; Gold semantic)

## Postgres Schema

### Schema namespaces (recommended)
- `catalog` — sources, datasets, schemas, profiling evidence refs
- `runs` — runs/builds state and pointers to artifacts
- `review` — proposals, review tasks, approvals
- `governance` — policies metadata, sensitivity tags, masking configs
- `er` — entity resolution decisions, clusters, crosswalks
- `audit` — append-only audit events and access decisions

### Core tables (minimum; field lists are normative)

#### catalog.sources
- `source_id` UUID PK
- `workspace_id` UUID (indexed)
- `source_type` TEXT
- `scope_json` JSONB
- `credentials_ref` TEXT (nullable; pointer only)
- `status` TEXT
- `created_at` TIMESTAMPTZ

Invariants:
- credentials are never stored in plaintext.
  - evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secrets Handling

#### catalog.datasets
- `dataset_id` UUID PK
- `workspace_id` UUID (indexed)
- `source_id` UUID FK
- `logical_name` TEXT
- `physical_locator` TEXT
- `schema_version` INT
- `sensitivity_summary_json` JSONB
- `created_at` TIMESTAMPTZ

#### runs.runs
- `run_id` TEXT PK (ULID)
- `workspace_id` UUID (indexed)
- `run_type` TEXT
- `status` TEXT
- `input_refs_json` JSONB
- `output_refs_json` JSONB
- `started_at` TIMESTAMPTZ (nullable)
- `ended_at` TIMESTAMPTZ (nullable)

#### review.proposals
- `proposal_id` TEXT PK (ULID)
- `workspace_id` UUID
- `proposal_type` TEXT
- `evidence_bundle_uri` TEXT
- `confidence` DOUBLE PRECISION
- `status` TEXT
- `created_at` TIMESTAMPTZ

Constraint:
- `confidence` must be between 0 and 1.

#### review.review_tasks
- `task_id` TEXT PK (ULID)
- `workspace_id` UUID
- `priority` TEXT
- `subject_ref` TEXT
- `status` TEXT
- `blocking` BOOLEAN
- `created_at` TIMESTAMPTZ

#### review.approvals
- `approval_id` TEXT PK (ULID)
- `task_id` TEXT FK
- `actor_id` TEXT
- `decision` TEXT
- `decision_reason` TEXT
- `applied_changes_ref` TEXT
- `audit_event_id` TEXT
- `created_at` TIMESTAMPTZ

#### governance.policies
- `policy_id` UUID PK
- `workspace_id` UUID
- `policy_type` TEXT
- `definition_ref` TEXT
- `status` TEXT
- `created_at` TIMESTAMPTZ

#### audit.audit_events (append-only)
- `audit_event_id` TEXT PK (ULID)
- `workspace_id` UUID
- `actor_id` TEXT
- `event_type` TEXT
- `event_json` JSONB
- `correlation_id` TEXT
- `created_at` TIMESTAMPTZ

Invariants:
- Append-only: no updates or deletes permitted via application paths.
- Must include correlation_id to link to runs/builds/gateway queries.
  - evidence: spec/08_OBSERVABILITY.md :: Audit Logging Signals

#### audit.access_decisions (append-only)
- `decision_id` TEXT PK (ULID)
- `workspace_id` UUID
- `actor_id` TEXT
- `request_context_json` JSONB
- `resources_json` JSONB
- `result` TEXT
- `applied_filters_json` JSONB
- `applied_masks_json` JSONB
- `audit_event_id` TEXT
- `created_at` TIMESTAMPTZ

## Object Store Layout (normative)

All paths are relative to a configured storage root (local directory or bucket).

### Bronze (immutable)
- `bronze/{workspace_id}/{source_id}/{dataset_id}/{ingest_date}/`
  - `artifact_{artifact_id}/raw/...` (original bytes)
  - `artifact_{artifact_id}/manifest.json`
  - `artifact_{artifact_id}/parsed.parquet` (optional; derived from raw; never overwrites raw)

Rules:
- Raw bytes are preserved.
- The manifest includes content_hash and parser metadata.

### Silver (canonical)
- `silver/{workspace_id}/{entity_name}/snapshots/{snapshot_id}/data/` (Parquet or Iceberg files)
- `silver/{workspace_id}/crosswalk/{source_id}/{dataset_id}/snapshots/{snapshot_id}/...`

Rules:
- Silver snapshots are immutable.
- ER merge decisions are recorded in Postgres and referenced by snapshot metadata.

### Gold (semantic; fail-closed publication)
- `gold/{workspace_id}/{model_name}/snapshots/{snapshot_id}/...`
- `gold/{workspace_id}/semantic_manifest/{version}/manifest.json`

Publication pointers (atomic):
- `gold/{workspace_id}/_published/latest.json` (points to snapshot IDs)

Rule:
- `latest.json` is updated only when contracts pass.
  - evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication

### Documents (optional module)
- `documents/{workspace_id}/{source_id}/artifact_{artifact_id}/raw/...`
- `documents/{workspace_id}/{source_id}/artifact_{artifact_id}/extracted/text.json`
- `documents/{workspace_id}/{source_id}/artifact_{artifact_id}/extracted/evidence.json`

## Iceberg/Parquet Table Conventions

Team/Enterprise default:
- Silver and gold are Iceberg tables stored in object store.
- Snapshot ID maps to Iceberg snapshot or tag.

Starter:
- Parquet snapshots with manifest pointer files.

Partitioning defaults (safe and minimal):
- Time partitioning only when a reliable date column exists and is validated.
- Otherwise, prefer compaction over partitioning to avoid small-file explosion.

## Migrations and Rollback

### Postgres migrations
- Use Alembic migrations.
- Migration rules:
  - Additive changes preferred (add columns/tables).
  - Destructive changes require a major version and a documented rollback plan.

Rollback safety:
- Migrations MUST support rollback in dev/test.
- For prod, if rollback is not possible, MUST provide forward-fix migration and documented procedure.
evidence: spec/11_QUALITY_GATES.md :: G-COMP-0001 Migration Safety

### Data format evolution (bronze/silver/gold)
- Bronze manifests are versioned (`manifest_version`) and must remain readable.
- Silver/gold schema evolution must be compatible or gated by review tasks.
evidence: spec/01_SCOPE.md :: Bronze Silver Gold Rules

## Retention and Deletion Mechanics

Externally constrained:
- Retention durations and legal hold rules depend on the deploying org.
- SchemaPilot MUST NOT claim compliance by default.

Fail-closed defaults:
- Automatic retention enforcement is **disabled** until explicitly configured.
- Deletion requests require explicit workflow approval and produce an evidence report.
evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Retention and Deletion Workflow

Deletion workflow (mechanics):
1) Intake request → create audit event
2) Identify subject selectors → map to canonical IDs (using crosswalk + ER clusters)
3) Preview impact → list affected snapshots and indexes
4) Check legal hold → block if active
5) Execute deletion:
   - mark records for deletion in silver/gold (Iceberg delete or rebuild partitions)
   - remove from indexes (if enabled)
6) Emit evidence report with:
   - what changed, snapshot IDs, counts, approval and audit IDs

## Backup and Restore Strategy

Minimum:
- Postgres: logical backups and restore procedure.
- Object storage: bucket versioning or snapshot strategy (implementation-specific), documented.
- Restore procedure must support:
  - restoring metadata,
  - restoring object store pointers,
  - republishing last known good gold pointer.

evidence: spec/12_RUNBOOK.md :: Backup and Restore

## Data Compatibility Policy

- Dataset IDs and logical names are stable identifiers; renames require explicit mapping.
- Gold semantics are versioned; consumers rely on semantic manifest versions.
- Breaking changes require deprecation cycle and/or new major semantic version.
evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Versioning and Deprecation Policy
