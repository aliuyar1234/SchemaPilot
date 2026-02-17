# spec/07_RELIABILITY_AND_OPERATIONS.md

## Reliability Strategy

SchemaPilot reliability is built on:
- idempotent runs and builds,
- bounded retries and explicit timeouts,
- fail-closed gates for gold publication and security decisions,
- immutable bronze and snapshot-based silver/gold,
- safe rollback to last known good.

## Idempotency Rules

### Discovery and ingest
- Discovery is read-only; repeating discovery must not create duplicate datasets without evidence.
- Bronze ingest idempotency key: `(source_id, physical_locator, content_hash)`.
- If content_hash is unchanged, the ingest MUST NOT rewrite raw bytes; it MAY emit a new manifest record only if metadata differs.

### Builds
- Build idempotency key: `(workspace_id, layer, input_snapshot_refs, transform_version, params_hash)`.
- Re-running the same build inputs and transform version MUST produce the same output snapshot (within deterministic bounds) or fail with an explicit non-determinism error.

Enforcement:
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0002 Deterministic Builds

## Retry and Timeout Policy

Rules:
- External calls MUST include timeouts.
- Retries MUST be bounded with exponential backoff and jitter.
- Retries MUST NOT be used for deterministic validation failures (policy denied, contract failed).

Recommended defaults (configurable):
- Connectors:
  - timeout per remote call
  - retries capped
- Query Gateway:
  - request timeout enforced
  - circuit breaker for engine/index outages
- Orchestrator:
  - retries capped per run type

Enforcement:
- evidence: CONSTITUTION.md :: SB-0005 Unbounded retries / missing timeouts

## Degradation and Backpressure

Principles:
- Prefer partial progress with quarantine for non-critical data issues (silver), but never publish unsafe gold.
- If indexing modules fail, disable retrieval; do not degrade policy enforcement.

Backpressure:
- Profiling budgets (row/byte sampling caps) prevent runaway scans.
- ER pairwise comparisons must be bounded via blocking and candidate limits.
evidence: spec/09_TEST_STRATEGY.md :: Determinism and Reproducibility

## Deployment and Rollback

### Deployment assumptions
- Compose is the primary deployment method; optional Kubernetes support later.
- Services must support health checks and readiness probes.
evidence: spec/12_RUNBOOK.md :: Docker Compose Operations

### Rollback principles
- Rollback MUST be possible for:
  - gold publication pointer (revert to last known good)
  - configuration changes
  - code deployments (container tags)
- Rollback MUST NOT delete data; it changes pointers/versions and records audit events.

## Incident Response Baseline

Minimum incident workflow:
1) Identify correlation IDs for failing runs/builds/queries.
2) Inspect audit events and access decisions for policy-related failures.
3) Verify storage layer health and latest published gold pointer.
4) If necessary, rollback gold pointer to last known good build.
5) Document incident cause and remediation tasks.

Evidence sources:
- Audit logs and access decisions
  - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.access_decisions (append-only)
- Observability signals
  - evidence: spec/08_OBSERVABILITY.md :: Dashboards and Alerts
