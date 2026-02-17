# spec/03_DOMAIN_MODEL.md

## Domain Model Summary

SchemaPilot’s domain model is designed for:
- **auditability** (append-only evidence and decisions),
- **reproducibility** (snapshot-based builds),
- **human approvals** (review tasks),
- **policy enforcement** (gateway decisions),
- **progressive profiles** (capabilities can be enabled without changing core entities).

## Core Entities

### Workspace
Represents one installation context (a customer deployment or environment).

Fields (minimum):
- `workspace_id` (UUID)
- `name`
- `profile` enum: `starter | team | enterprise`
- `security_baseline` enum: `standard | strict`
- `created_at` (internal runtime timestamp; not exposed in SSOT docs)

Invariants:
- A workspace MUST have exactly one active profile.
- Changing profile MUST be recorded as an audit event and must not require re-ingesting sources.
  - evidence: spec/11_QUALITY_GATES.md :: G-COMP-0003 Profile Upgrade Safety

### Source
A configured data source (filesystem path, S3 bucket/prefix, DB connection, export folder).

Fields:
- `source_id` (UUID)
- `workspace_id`
- `source_type` enum: `filesystem | s3 | database`
- `scope` (structured; include/exclude patterns, schema allowlist)
- `credentials_ref` (pointer to secret store; never stored in plaintext)
- `status` enum: `active | paused | revoked`

Invariants:
- Discovery MUST be read-only.
- Scope expansions MUST be explicit and auditable.
  - evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secrets Handling

### Dataset
A logical dataset discovered from sources (a table-like unit).

Fields:
- `dataset_id` (UUID)
- `workspace_id`
- `source_id`
- `logical_name` (stable human-facing name)
- `physical_locator` (path/bucket/object identifiers)
- `schema_version` (monotonic integer)
- `sensitivity_summary` (computed summary; details at column level)

Invariants:
- Dataset identity MUST be stable across snapshots.
- Schema evolution MUST be versioned; breaking drift triggers review.
  - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Data Compatibility Policy

### Artifact (Bronze object)
Represents an immutable ingested item.

Fields:
- `artifact_id` (ULID)
- `dataset_id` (or source-only for unstructured docs)
- `content_hash` (SHA-256)
- `storage_uri` (relative path in storage)
- `ingest_manifest_uri`

Invariants:
- Bronze artifacts MUST be append-only; never overwritten.
  - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Object Store Layout

### Run
A unit of work performed by the system: discovery, profiling, inference, build.

Fields:
- `run_id` (ULID)
- `workspace_id`
- `run_type` enum: `discover | ingest_bronze | profile | infer | build_silver | build_gold | recommend`
- `status` enum: `queued | running | succeeded | failed | blocked`
- `input_refs` (snapshot IDs, artifact IDs)
- `output_refs` (snapshot IDs, report URIs)
- `correlation_id` (ULID; present in logs)

Invariants:
- Runs MUST be idempotent when re-executed with identical inputs and versions.
  - evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Idempotency Rules

### Proposal (Inference output)
A proposed change that requires evidence and may require approval.

Types:
- `schema_proposal` (canonical column naming/type mapping)
- `key_proposal` (PK/FK candidates)
- `relationship_proposal` (join hypotheses)
- `pii_tag_proposal` (sensitivity classification)
- `er_merge_proposal` (entity resolution merge cluster)

Common fields:
- `proposal_id` (ULID)
- `workspace_id`
- `proposal_type`
- `evidence_bundle_uri`
- `confidence` float [0,1]
- `status` enum: `open | approved | rejected | deferred`

Invariants:
- Proposals MUST include evidence and confidence; otherwise they are invalid.
  - evidence: CONSTITUTION.md :: Evidence-backed autopilot

### ReviewTask (Review Queue item)
A UI-presented task derived from proposals.

Fields:
- `task_id` (ULID)
- `workspace_id`
- `priority` enum: `security_critical | model_critical | quality_critical | optimization`
- `subject_ref` (proposal_id or drift_event_id)
- `status` enum: `open | in_review | approved | rejected | deferred`
- `blocking` boolean (blocks builds or exposure when true)

Invariants:
- Tasks MUST be small and bounded (one approval decision).
  - evidence: spec/01_SCOPE.md :: Review task sizing and prioritization (human-friendly)

### Approval
A human decision applied to a proposal/task.

Fields:
- `approval_id` (ULID)
- `task_id`
- `actor_id` (user identity)
- `decision` enum: `approve | reject | defer`
- `decision_reason` (required for reject/defer)
- `applied_changes_ref` (what changed)
- `audit_event_id`

Invariants:
- Approvals MUST be audit-logged (append-only).
  - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.audit_events (append-only)

### Build (Silver/Gold)
A build produces a new snapshot of a layer.

Fields:
- `build_id` (ULID)
- `workspace_id`
- `layer` enum: `silver | gold`
- `input_snapshot_refs` (bronze/silver snapshot IDs)
- `output_snapshot_ref`
- `semantic_manifest_ref` (gold only)
- `status` enum: `planned | running | succeeded | failed | published | blocked`

Invariants:
- Gold builds MUST NOT be published unless contracts pass.
  - evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication

### Policy + AccessDecision
Policies describe access; AccessDecision records enforcement results.

Policy fields:
- `policy_id` (UUID)
- `policy_type` enum: `rbac | abac | masking | row_filter`
- `definition_ref` (OPA bundle or internal policy JSON)
- `status` enum: `active | staged | retired`

AccessDecision fields:
- `decision_id` (ULID)
- `actor_id`
- `request_context` (purpose, attributes)
- `resources` (datasets/columns)
- `result` enum: `allow | deny`
- `applied_filters` / `applied_masks`
- `audit_event_id`

Invariants:
- Every gateway query MUST return `decision_id` and provenance.
  - evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Query Gateway Contract

### RecommendationReport (Decision Engine output)
Represents architecture recommendations.

Fields:
- `report_id` (ULID)
- `workspace_id`
- `ranked_templates` list (T1..T8) with score breakdown
- `hard_constraint_gates` pass/fail list
- `confidence` float [0,1]
- `missing_evidence` list
- `approval_required` boolean + reasons list

Invariant:
- Template IDs MUST be exactly T1..T8.
  - evidence: spec/01_SCOPE.md :: Template library (fixed; must be implemented)

## Invariants (cross-cutting)

- **Non-bypass**: no query execution or retrieval without passing through gateway.
  - evidence: DECISIONS.md :: D-0003 Query Gateway is the single enforcement point (no bypass)
- **Append-only audit**: audit events are immutable and cannot be updated.
  - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.audit_events (append-only)
- **Determinism**: runs and builds are keyed by input refs + versioned transforms.
  - evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Idempotency Rules

## Identity and ID Formats
- Operational IDs: ULID (`run_id`, `build_id`, `task_id`, `proposal_id`, `decision_id`)
- Domain IDs: UUID (`workspace_id`, `dataset_id`, `source_id`, `policy_id`)
evidence: DECISIONS.md :: D-0005 Stable identifier strategy (ULID/UUID usage)

## Entity State Machines (selected)

### ReviewTask
- `open` → `in_review` → (`approved` | `rejected` | `deferred`)
Rules:
- `security_critical` tasks default to `blocking=true` unless explicitly configured otherwise.
- `deferred` tasks MUST record why they are safe to defer.

### Build (Gold)
- `planned` → `running` → (`succeeded` | `failed` | `blocked`)
- If `succeeded` and contracts pass → `published`
- If contracts fail → `blocked` and do not move “latest” pointer

## Glossary (authoritative terms; prevents SB-0007)

- **Bronze**: immutable, source-faithful raw artifacts + manifests.
- **Silver**: typed, normalized canonical entities; includes entity resolution and crosswalk mappings.
- **Gold**: governed semantic surface (dims/facts/metrics); fail-closed publication.
- **Manifest**: machine-readable record of what was ingested/built, with content hashes and versions.
- **Evidence bundle**: compact, reviewable facts backing a proposal (stats, overlaps, samples redacted).
- **Review Queue**: prioritized list of ReviewTasks; the only way to approve risky changes.
- **Policy decision**: gateway-produced decision_id with applied filters/masks.
- **Provenance**: returned with every query; includes dataset IDs + snapshot IDs + decision_id.
