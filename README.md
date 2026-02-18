# SchemaPilot — SSOT Pack for Codex (ssot_codex_pack_v1.zip)

This ZIP is a **single source of truth (SSOT)** for implementing **SchemaPilot** end-to-end with senior engineering discipline:
- **No guessing in critical flows**
- **Fail-closed defaults**
- **Evidence-backed approvals**
- **Deterministic artifacts and drift control**

**This ZIP contains specifications only.** It is intended to be consumed by Codex (or any competent AI coding agent) to implement the actual repository.

## Precedence order (conflict resolution)

AGENTS.md

CONSTITUTION.md

spec/* (numeric order; existing files only)

DECISIONS.md

ASSUMPTIONS.md

README.md

templates/, checks/, runbook content

## Where to find X

evidence: spec/01_SCOPE.md :: Scope Summary
evidence: spec/02_ARCHITECTURE.md :: Architecture Summary
evidence: spec/03_DOMAIN_MODEL.md :: Domain Model Summary
evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: API Surface
evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Storage Overview
evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Security Model Summary
evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Reliability Strategy
evidence: spec/08_OBSERVABILITY.md :: Observability Strategy
evidence: spec/09_TEST_STRATEGY.md :: Test Pyramid
evidence: spec/10_PHASES_AND_TASKS.md :: Roadmap Summary Table
evidence: spec/11_QUALITY_GATES.md :: Gate Index
evidence: spec/12_RUNBOOK.md :: Local Development Runbook
evidence: DECISIONS.md :: Decision Index
evidence: ASSUMPTIONS.md :: Assumption Index
evidence: PROGRESS.md :: Task Status
evidence: checks/QUESTIONS_FOR_USER.md :: Questions for User
evidence: AUDIT_REPORT.md :: SSOT SCORECARD
evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY
## System Tour (15 minutes)

### Entrypoints (what will exist in the implemented repo)
- **Control Plane API**: orchestrates discovery, profiling, proposals, review tasks, builds, recommendation reports.
- **UI (Wizard + Review Queue)**: guided onboarding and human approvals; minimal required decisions (complexity budget).
- **Workers**: discovery connectors, profiler, inference engine, silver/gold builders.
- **Query Gateway**: the **only** data access path for humans and AI; enforces RBAC/ABAC, masking, audit, provenance.
- **Data stores**:
  - Starter: local filesystem + embedded DuckDB execution.
  - Team (default): object store + Iceberg + Trino.
  - Enterprise: adds OPA enforcement and stricter ops/observability modules.

(Design details and boundaries)
evidence: spec/02_ARCHITECTURE.md :: Component Boundary Table

### Main user journeys (must be implemented end-to-end)
1) **Install → connect sources → first catalog**
2) **Approve model/PII/relationships → build silver/gold → first governed AI query**
3) **Ongoing ops**: drift/new source/backfill/deletion request/rollback

(UX requirements and review queue rules)
evidence: spec/01_SCOPE.md :: User Journeys Requirements

### Critical flows (fail-closed required)
- Authentication/authorization and secrets handling
- Handling/storing sensitive data; PII detection and review gates
- Query enforcement (no bypass of gateway)
- Deletion/retention/backup/restore/rollback

(Security handling and controls)
evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secure Defaults and Failure Modes

## Minimal path to implementation (no drift across sessions)

Follow the ordered phases and tasks; do not reorder or parallelize without updating DECISIONS and PROGRESS.
evidence: spec/10_PHASES_AND_TASKS.md :: PHASE_0_BOOTSTRAP

## Drift detection: MANIFEST.sha256

- **Any change to any file** in this ZIP requires regenerating MANIFEST.sha256.
- If MANIFEST.sha256 is stale, **acceptance is blocked**.
evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY

## Demo Path: First Safe Query in Minutes

Use this path for "messy folders to governed AI-ready query" onboarding:

1) Bootstrap demo workspace and data:
```bash
python -m cli.schemapilot_cli.main onboard-demo --workspace-name "Demo Workspace"
```

2) Review queue summary:
```bash
python -m cli.schemapilot_cli.main status --workspace <workspace_id>
```

3) First governed query through gateway:
```bash
curl -s http://127.0.0.1:8001/api/v1/gateway/query \
  -H "Authorization: Bearer local-analyst-token" \
  -H "Content-Type: application/json" \
  -d "{\"workspace_id\":\"<workspace_id>\",\"query\":{\"text\":\"select 1 as one\"},\"resource_attributes\":{\"dataset_id\":\"dataset-1\"}}"
```

Expected:
- policy decision id in response provenance,
- applied filters/masks metadata,
- append-only audit rows in gateway audit tables.

## Weekly KPI Tracking

Track adoption and reliability every week:
- Time-to-first-safe-answer
- Install success rate
- Security regression count
- Deterministic rebuild pass rate
- Active contributors and issue response time

Generate report:
```bash
python tools/kpi_tracker.py \
  --week 2026-W08 \
  --ttfsa-minutes 24 \
  --install-success-rate 0.92 \
  --security-regressions 0 \
  --deterministic-pass-rate 1.0 \
  --active-contributors 5 \
  --issue-response-hours 12
```

## Change Map: If you change X, update Y (top 10)

1) **Public API shapes** → update contracts + compatibility policy + tests
   - evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Versioning and Deprecation Policy
   - evidence: spec/09_TEST_STRATEGY.md :: CI Gates Mapping

2) **Data model (entities/IDs/states)** → update domain model + datastore schema + migrations
   - evidence: spec/03_DOMAIN_MODEL.md :: Core Entities
   - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Postgres Schema

3) **Query Gateway enforcement logic** → update security model + threat mitigations + boundary fitness gates
   - evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Authentication and Authorization
   - evidence: spec/11_QUALITY_GATES.md :: G-SEC-0002 Gateway Non-Bypass

4) **Decision Engine templates or scoring** → update decision engine requirements + tests + recommendation report schema
   - evidence: spec/01_SCOPE.md :: Decision Engine Requirements
   - evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Recommendation Report Format

5) **Bronze/Silver/Gold rules** → update datastore conventions + reliability + contracts
   - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Object Store Layout
   - evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Idempotency Rules

6) **PII detection behavior** → update security spec + review queue requirements + tests
   - evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: PII Detection and Review Gates
   - evidence: spec/03_DOMAIN_MODEL.md :: ReviewTask

7) **Packaging profiles** → update architecture + runbook + decision engine templates
   - evidence: spec/01_SCOPE.md :: Packaging Profiles as Upgrade Path
   - evidence: spec/12_RUNBOOK.md :: Docker Compose Operations

8) **Migrations strategy** → update datastore/migrations + compatibility gates
   - evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Migrations and Rollback
   - evidence: spec/11_QUALITY_GATES.md :: G-COMP-0001 Migration Safety

9) **Observability signals** → update observability spec + runbook diagnostics + quality gates
   - evidence: spec/08_OBSERVABILITY.md :: Metrics
   - evidence: spec/12_RUNBOOK.md :: Troubleshooting

10) **Security posture changes** → update threat model + gates + decision log
   - evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Threats and Mitigations
   - evidence: CONSTITUTION.md :: Exception process
