# spec/01_SCOPE.md

## Scope Summary

SchemaPilot MUST deliver a guided product experience that converts “no database / bad database” into:
- a deployed data foundation (progressive profiles),
- an evidence-backed catalog,
- bronze/silver/gold layers with deterministic versioning,
- a governed gold semantic layer for SQL-first AI,
- a Query Gateway enforcing security and provenance for every query.

Non-negotiable product constraints and invariants are enforced via:
evidence: CONSTITUTION.md :: Core constraints (project-specific)

## In Scope

### User-visible workflows (end-to-end)
1) Install → connect sources → first catalog (with evidence)
2) Review Queue approvals (PII/model/relationships) → build silver/gold → first governed AI query
3) Ongoing ops: drift, new source, backfill, deletion request, rollback

(UX requirements and task sizing)
evidence: spec/01_SCOPE.md :: User Journeys Requirements

### Data source classes (v1 baseline)
- Files: CSV, XLSX, JSON, PDF/email artifacts (PDF indexing may be optional module).
- Object store: S3-compatible.
- Databases: read-only ingest from Postgres/MySQL (expandable).

### Platform outcomes
- Catalog with evidence: schema, stats, drift, sensitivity proposals, ownership hooks.
- Bronze: immutable raw + ingest manifests.
- Silver: canonical typed entities + entity resolution + crosswalk mappings (reversible).
- Gold: semantic views/tables + metrics pack + semantic manifest; fail-closed publication.

### Governance outcomes
- PII detection proposals with confidence and review gating.
- RBAC roles + ABAC attributes; row/column controls via Query Gateway.
- Audit logs (append-only) and provenance returned with every query.
- Deletion workflow with evidence report and legal hold blocking capability.
  - Retention enforcement values are externally constrained; enforcement is disabled by default until configured.
  - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Retention and Deletion Mechanics

### Decision Engine outcomes
- MUST rank templates T1..T8 exactly as defined.
- MUST output a recommendation report including:
  - hard constraint gates (pass/fail per gate),
  - score breakdown by criterion,
  - confidence,
  - missing evidence list,
  - approval-required triggers.
evidence: spec/01_SCOPE.md :: Decision Engine Requirements

### AI usage model (SQL-first, governed)
- AI MUST query governed gold views via Query Gateway only.
- Retrieval over documents (if enabled) MUST be policy-filtered and also via Query Gateway.
evidence: DECISIONS.md :: D-0003 Query Gateway is the single enforcement point (no bypass)

## Out of Scope (explicit non-goals for v1)

- Multi-tenant hosted SaaS control plane as a requirement.
- Automatic dashboard generation for arbitrary orgs.
- Fully autonomous semantic modeling without approvals.
- Graph database as a default dependency (graph may be optional later if evidence demands).
- Unrestricted document QA without metadata binding and policies.

## Success Criteria (measurable; used for acceptance)

1) Time-to-first-value (TTFV)
- Catalog populated after connecting sources, with profiling evidence.
- First gold metrics pack and at least one governed AI query.
evidence: spec/09_TEST_STRATEGY.md :: MessyBench

2) Coverage
- A measurable proportion of high-value datasets mapped to entities and gold views.

3) Policy enforcement
- No unauthorized rows/columns returned in security denial tests.

4) Determinism
- Rebuild from the same bronze snapshot + transform version yields the same gold outputs (within defined deterministic bounds).

5) Upgrade safety
- Starter → Team → Enterprise upgrades do not require re-ingestion of source data.

## Packaging Profiles as Upgrade Path

Profiles are not competing products; they are a single progressive approach.

### Starter (evaluation; single-node)
- Runs minimal components: local storage + embedded query execution.
- Used to validate onboarding, catalog, review queue, and basic silver/gold flows.

### Team (default recommended)
- Adds object store + Iceberg + Trino for multi-user SQL and snapshotting.
- Default target for production OSS deployments.

### Enterprise (adds stricter governance and scale)
- Adds OPA policy enforcement integration and stronger observability/ops modules.
- Optional modules (Spark, ClickHouse, search/vector) are added only when Decision Engine evidence justifies them.

(Upgrade constraints and safety)
evidence: spec/11_QUALITY_GATES.md :: G-COMP-0003 Profile Upgrade Safety

## User Journeys Requirements

### Autopilot Wizard (guided onboarding)
- MUST guide users through:
  - source connection and scope confirmation,
  - profiling budget defaults,
  - security baseline selection (standard vs strict),
  - initial intent capture for the Decision Engine.

### Review Queue (human approvals)
- MUST exist and MUST be the primary mechanism for:
  - PII tag approvals (high impact),
  - key/relationship confirmations,
  - entity resolution merge approvals when confidence is below auto-accept threshold,
  - drift remediation tasks.

### Review task sizing and prioritization (human-friendly)
- Tasks MUST be small and bounded:
  - “approve one tag”, “confirm one key”, “approve one merge cluster”
- Prioritization order (default):
  1) security-critical
  2) model-critical
  3) quality-critical
  4) optimization

### Complexity budget (first day)
- The system MUST be operable with ≤ 8 required user decisions to reach first gold + first governed AI query.
- If more decisions are required, they MUST be deferrable unless they impact critical flows.

## Evidence-Backed Autopilot Rules

For any “autopilot” output (inference, PII, Decision Engine):
- MUST specify input evidence used (profiling stats, observed logs, wizard intents).
- MUST output confidence and explicit failure modes.
- MUST trigger review when confidence is low or risk is high.
- MUST not silently apply risky changes.
evidence: CONSTITUTION.md :: Evidence-backed autopilot

## Decision Engine Requirements

### Template library (fixed; must be implemented)
- T1: Postgres + DuckDB (Starter)
- T2: Object Store + Iceberg + DuckDB
- T3: Lakehouse (Iceberg) + Trino (Team default)
- T4: Lakehouse + Trino + Search (OpenSearch)
- T5: Lakehouse + Trino + Vector (Qdrant)
- T6: OLTP + Lakehouse split
- T7: Lakehouse + Trino + ClickHouse mart
- T8: Streaming + Lakehouse

### Behavior requirements
- Proposes only; never deploys risky complexity without approval.
- Uses hard constraint gates first, then scoring.
- Includes missing evidence list (what would increase confidence).
- Emits approval-required triggers when:
  - adding new store types beyond baseline,
  - confidence below threshold,
  - strict security baseline + new exposure surfaces.

## Bronze Silver Gold Rules

- Bronze is immutable raw + manifests.
- Silver performs typing/normalization and entity resolution; maintains crosswalk.
- Gold is semantic layer and metrics; publication is fail-closed on contract failure.
evidence: DECISIONS.md :: D-0006 Storage layer strategy (Bronze immutable; Silver ER; Gold semantic)

## Query Gateway Invariants

- Gateway is the only enforcement point.
- Every query returns provenance and is audit-logged.
- Deny-by-default is required for AI tool identities.
evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Query Gateway Contract

## Fail-Closed Defaults

- Bind localhost-only by default.
- Optional integrations (indexes, external LLMs, CDC) disabled unless explicitly enabled.
- Gold publication blocked on contract failures; last known good remains available.
evidence: DECISIONS.md :: D-0004 Safe startup defaults (localhost bind; auth required for non-local)
