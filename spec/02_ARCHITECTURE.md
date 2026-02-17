# spec/02_ARCHITECTURE.md

## Architecture Summary

SchemaPilot architecture is split into:
- **Control Plane**: manages metadata, proposals, approvals, runs, and user experience.
- **Data Plane**: performs discovery, profiling, inference, ingestion, and builds.
- **Access Plane (Query Gateway)**: the single enforcement point for SQL and retrieval access.

The progressive profiles (Starter→Team→Enterprise) are implemented by enabling modules, not by changing the conceptual architecture.
evidence: DECISIONS.md :: D-0002 Progressive packaging profiles

## Component Boundary Table

| Component | Type | Primary responsibilities | MUST NOT do |
|---|---|---|---|
| UI (Wizard + Review Queue) | Web UI | Guided setup, approvals, run monitoring | Execute queries directly; store secrets |
| Control Plane API | Service | Workspace config, sources, datasets, proposals, tasks, builds, recommendation reports | Bypass gateway; run heavy transforms inline |
| Metadata Store (Postgres) | DB | Catalog, approvals, audit, ER decisions, policies metadata | Store raw bronze data blobs |
| Workers: Discovery/Connectors | Worker | Read-only discovery; bronze ingest; manifests | Execute queries against Trino/OpenSearch/Qdrant |
| Workers: Profiler | Worker | Sampling, stats, drift detection, evidence bundles | Write to gold directly |
| Workers: Inference Engine | Worker | Schema/key/relationship/PII proposals; confidence + evidence | Auto-apply risky changes without review |
| Workers: Builders | Worker | Silver build (normalize + ER); Gold build (semantic + metrics) | Publish gold on contract failure |
| Orchestrator | Service | Scheduling, retries, run state, backfills | Encode business logic outside tasks/contracts |
| Query Gateway | Service | RBAC/ABAC, masking, audit, provenance; executes SQL/retrieval | Permit direct engine access; return data without provenance |
| Query Engine (DuckDB/Trino) | Engine | SQL execution over tables | Enforce user policies directly (gateway does it) |
| Search/Vector Indexes (optional) | Engine | Full-text/vector retrieval with metadata | Serve data without gateway filtering |
| Policy Engine (Enterprise; OPA) | Service | ABAC decisions and policy evaluation | Store data; run queries |

## Dependency Direction Rules

The following dependency direction MUST be preserved in code and deployment:
- UI → Control Plane API
- Control Plane API → Metadata Store + internal domain services
- Workers → Storage layers + Metadata Store (through internal interfaces)
- Query Gateway → Policy Engine (optional) + Query Engine + Indexes
- Query Engine/Indexes MUST NOT call back into Control Plane for policy decisions (gateway already decided)
- No component except Query Gateway may access Query Engine or Indexes in production mode

Enforcement:
- evidence: CONSTITUTION.md :: Boundary & coupling guardrails (anti-erosion)
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

## Architecture Diagram

```mermaid
flowchart LR
  subgraph CP[Control Plane]
    UI[UI]
    API[Control Plane API]
    META[(Postgres
Metadata+Audit)]
  end

  subgraph DP[Data Plane]
    CONN[Connectors/Discovery]
    PROF[Profiler+Drift]
    INF[Inference Engine]
    ORCH[Orchestrator]
    STORE[(Storage
Local/MinIO/S3)]
    LAYERS[Bronze/Silver/Gold
Parquet/Iceberg]
  end

  subgraph AP[Access Plane]
    GW[Query Gateway]
    POL[Policy Engine
(OPA optional)]
    QRY[Query Engine
(DuckDB/Trino)]
    IDX[Search/Vector
(optional)]
  end

  UI --> API --> META
  API --> ORCH
  CONN --> STORE --> LAYERS
  CONN --> PROF --> META
  PROF --> INF --> META
  ORCH --> LAYERS

  GW --> QRY
  GW --> IDX
  GW --> POL
  GW --> META
```

## Critical Flows and Fail-Closed Handling

- **Auth/exposure**: localhost-only by default; non-local requires explicit auth config or fail to start.
  - evidence: DECISIONS.md :: D-0004 Safe startup defaults (localhost bind; auth required for non-local)
- **Policy enforcement**: Query Gateway is mandatory; bypass is forbidden and gated.
  - evidence: spec/11_QUALITY_GATES.md :: G-SEC-0002 Gateway Non-Bypass
- **Gold publication**: contracts must pass; otherwise do not publish new gold.
  - evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication
- **Deletion**: requires explicit workflow with evidence report; legal hold blocks execution.
  - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Retention and Deletion Mechanics

## Feature Add/Remove Playbook (safe change procedure)

When adding/removing a feature that affects a critical flow:
1) Classify with DSC and log decision/assumption/question.
   - evidence: spec/00_PROJECT_FINGERPRINT.md :: Decision Safety Classifier
2) Update the relevant public contract spec (API/CLI/file format).
   - evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Public Contract Policy
3) Add/modify gates/checks enforcing fail-closed behavior.
   - evidence: spec/11_QUALITY_GATES.md :: Gate Index
4) Add negative-path tests for denial and safe failure.
   - evidence: spec/09_TEST_STRATEGY.md :: Negative Path Requirements
5) Update runbook procedures if ops behavior changes.
   - evidence: spec/12_RUNBOOK.md :: Maintenance Playbook
