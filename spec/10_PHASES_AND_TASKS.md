# spec/10_PHASES_AND_TASKS.md

## Roadmap Summary Table

| Phase | Goal | Primary deliverables | Exit gates (must pass) |
|---|---|---|---|
| PHASE_0_BOOTSTRAP | Make repo buildable/testable with guardrails | Repo scaffold, tooling, smoke run, determinism baseline, stub integrations, navigable docs | G-MAINT-0001, G-OPS-0001 |
| PHASE_1_CORE_CONTROL_PLANE | Establish control plane foundations | API skeleton, metadata DB/migrations, UI skeleton, CLI skeleton, audit logging, policy interface | G-SEC-0001, G-COMP-0001 |
| PHASE_2_DATA_INGEST_AND_CATALOG | Connect messy sources into evidence-backed catalog | Connector framework, bronze manifests, profiling evidence, drift detection | G-REL-0001, G-MAINT-0002 |
| PHASE_3_MODELING_AND_REVIEW_QUEUE | Turn evidence into reviewable proposals | Schema/key/PII proposals, review queue backend+UI, build gating | G-SEC-0003, G-REL-0003 |
| PHASE_4_SILVER_GOLD_AND_QUERY_GATEWAY | Produce governed semantics and safe queries | Silver builder with ER, gold semantic builder, contracts + fail-closed publish, gateway with provenance | G-SEC-0002, G-REL-0004 |
| PHASE_5_DECISION_ENGINE | Rank architecture templates safely | T1..T8 library, gates, scoring, confidence, report UI | G-MAINT-0002, G-COMP-0002 |
| PHASE_6_GOVERNANCE_AND_DOCUMENT_RETRIEVAL | Add enterprise controls and optional retrieval | ABAC/OPA integration, masking, deletion workflow, doc indexing via gateway | G-SEC-0004, G-OPS-0002 |
| PHASE_7_OBSERVABILITY_TESTS_RELEASE | Prove readiness and prevent regressions | Observability, MessyBench, CI gates, packaging, release checks | G-PERF-0001, G-COMP-0003 |

Gate definitions:
evidence: spec/11_QUALITY_GATES.md :: Gate Index

---

## PHASE_0_BOOTSTRAP

### Phase goal
Create a buildable/testable repository scaffold with enforceable guardrails so an agent can progress without drift.

### Entry criteria
- None.

### Exit criteria
- Tooling baseline passes (format/lint/typecheck/test skeleton).
- Boundary fitness checks exist (even if initially minimal).
- Minimal runnable path exists with smoke test.
- Determinism baseline for manifests and checks is in place.
- Docs navigability and ref-integrity checks pass.

Mapped gates:
- evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0001 Boundary Fitness
- evidence: spec/11_QUALITY_GATES.md :: G-OPS-0001 Runbook Complete

#### T-0001 Repo scaffold + module boundaries (no mega-modules)

Purpose: Define the codebase structure and boundary rules early.

Acceptance criteria:
- Repository contains separate modules for: control plane, gateway, workers, shared domain, UI, CLI.
- A boundary enforcement mechanism exists (import rules or dependency checker).
- No circular dependency across top-level modules.

Required evidence pointers:
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS
- evidence: spec/02_ARCHITECTURE.md :: Dependency Direction Rules

Implementation Notes:
- Create a monorepo structure (example):
  - `backend/` (Python packages)
  - `ui/` (TypeScript React)
  - `cli/` (Python)
  - `deploy/` (compose and k8s manifests)
- Add boundary enforcement tooling configuration:
  - Python: import-linter (or equivalent)
  - TypeScript: dependency-cruiser (or equivalent)
- Failure interpretation:
  - If boundary enforcement cannot be wired in the first pass, create a minimal check that fails when forbidden imports are detected and document it in checks index.

#### T-0002 Tooling baseline (format/lint/typecheck/test) + CI wiring

Purpose: Ensure repeatable quality gates are executable on every change.

Acceptance criteria:
- CI pipeline runs:
  - Python formatting/linting/type checks
  - TypeScript formatting/linting/type checks
  - unit test runner (even if minimal)
- CI produces machine-readable outputs for gate evidence.

Required evidence pointers:
- evidence: checks/CHECKS_INDEX.md :: CHK-TOOLING-BASELINE
- evidence: templates/PR_REVIEW_CHECKLIST.md :: No Evidence, No Accept

Implementation Notes:
- Establish standard tools (example choices):
  - Python: ruff + mypy + pytest
  - TypeScript: eslint + tsc + vitest
- Add `schemapilot check` CLI that runs the same checks locally.
- Failure interpretation:
  - If CI differs from local runs, fix by making `schemapilot check` the single entry for checks.

#### T-0003 Minimal runnable path (service entrypoint) + smoke test

Purpose: Provide an end-to-end “it runs” baseline without implementing product logic.

Acceptance criteria:
- Control Plane API can start locally in dev mode and responds to a health endpoint.
- UI can load and reach API health endpoint.
- A smoke test verifies startup and health checks.

Required evidence pointers:
- evidence: spec/12_RUNBOOK.md :: Local Development Runbook
- evidence: checks/CHECKS_INDEX.md :: CHK-SMOKE

Implementation Notes:
- Implement:
  - API: `/api/v1/health`
  - UI: minimal page with API connectivity indicator
- Smoke test:
  - start services (compose or dev scripts)
  - call health endpoint
  - assert expected response
- Failure interpretation:
  - If health endpoint is unstable, fix first; do not build additional features on unstable startup.

#### T-0004 Determinism baseline: manifest generation + verification check definitions

Purpose: Make drift measurable and block acceptance when manifests are stale.

Acceptance criteria:
- A manifest generation command exists and produces MANIFEST.sha256 in lexicographic order.
- CHK-MANIFEST-VERIFY exists and fails when any file hash differs.
- CI includes manifest verification.

Required evidence pointers:
- evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY
- evidence: spec/11_QUALITY_GATES.md :: No Evidence, No Accept / No Progress

Implementation Notes:
- Provide a small manifest generator script in the implementation repo (not in this ZIP).
- Ensure it excludes MANIFEST.sha256 itself.
- Failure interpretation:
  - If manifest update is frequently missed, enforce it as a mandatory PR checklist item.

#### T-0005 Stub interfaces for externally constrained integrations (disabled-by-default)

Purpose: Avoid blocking on external constraints while preventing unsafe defaults.

Acceptance criteria:
- Interfaces exist for:
  - policy engine integration (OPA)
  - identity provider integration (OIDC/SAML placeholders at interface level)
  - external embedding provider (for vector module)
- All are disabled unless explicitly configured; no side effects when disabled.

Required evidence pointers:
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secure Defaults and Failure Modes
- evidence: checks/QUESTIONS_FOR_USER.md :: Questions for User

Implementation Notes:
- Define interfaces and configuration keys; return clear “disabled” errors when not enabled.
- Failure interpretation:
  - If any stub accidentally enables external calls, treat as a security defect.

#### T-0006 Documentation navigability (“Where to find X”) + ref-integrity checks pass

Purpose: Ensure a fresh agent can navigate the SSOT and find canonical rules.

Acceptance criteria:
- README index and AGENTS protocol are complete.
- CHK-REF-INTEGRITY and CHK-NO-ADHOC-FILES pass on the SSOT pack.
- PR checklist requires these checks before acceptance.

Required evidence pointers:
- evidence: README.md :: Where to find X
- evidence: checks/CHECKS_INDEX.md :: CHK-REF-INTEGRITY

Implementation Notes:
- Implement `schemapilot ssot-verify` command in the implementation repo to run these checks against the unpacked SSOT pack.
- Failure interpretation:
  - If ref-integrity fails, fix references immediately; do not defer.

---

## PHASE_1_CORE_CONTROL_PLANE

### Phase goal
Establish control plane primitives: workspace config, metadata DB, audit, and UI/CLI shells.

### Entry criteria
- PHASE_0 exit criteria met.

### Exit criteria
- Workspace can be created and stored.
- Metadata tables exist via migrations.
- Auth baseline and safe startup defaults enforced.
- Audit logging is append-only.

Mapped gates:
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0001 Safe Startup Defaults
- evidence: spec/11_QUALITY_GATES.md :: G-COMP-0001 Migration Safety

#### T-0007 Control Plane API skeleton (workspace + sources + datasets)

Purpose: Provide minimal CRUD for core domain objects.

Acceptance criteria:
- API supports create/list/read for workspaces and sources.
- API stores state in Postgres and returns stable IDs.
- API emits audit events for create operations.

Required evidence pointers:
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: API Surface
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Postgres Schema

Implementation Notes:
- Implement request validation and error model.
- Failure interpretation:
  - If API errors are inconsistent, align with spec/04 error model before building more endpoints.

#### T-0008 Postgres migrations baseline (schemas + tables)

Purpose: Make metadata persistent and upgradeable.

Acceptance criteria:
- Alembic migrations create the normative tables from spec/05.
- Migration can be applied on empty DB and validates schema invariants.

Required evidence pointers:
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Postgres Schema
- evidence: spec/11_QUALITY_GATES.md :: G-COMP-0001 Migration Safety

Implementation Notes:
- Add migration tests in CI.
- Failure interpretation:
  - If migrations are not reversible in dev, document forward-fix plan and gate releases.

#### T-0009 UI shell: Wizard stepper + Review Queue shell

Purpose: Establish UX scaffolding early.

Acceptance criteria:
- UI provides:
  - workspace selection/creation screen,
  - wizard stepper skeleton,
  - review queue list skeleton.
- UI calls API; no hard-coded business logic.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: User Journeys Requirements
- evidence: CONSTITUTION.md :: Boundary & coupling guardrails (anti-erosion)

Implementation Notes:
- Implement minimal pages and routing.
- Failure interpretation:
  - If UI duplicates backend logic, refactor to backend-provided state.

#### T-0010 CLI shell (doctor/init/connect/run/status/check)

Purpose: Provide a scriptable interface and preflight checks.

Acceptance criteria:
- CLI commands exist per spec/04.
- `doctor` identifies missing dependencies and prints deterministic remediation steps.
- CLI does not store secrets; it references credentials via config.

Required evidence pointers:
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: CLI Surface
- evidence: spec/12_RUNBOOK.md :: Local Development Runbook

Implementation Notes:
- Implement config file loading with explicit keys.
- Failure interpretation:
  - If CLI behavior diverges from API, treat as contract drift.

#### T-0011 Audit logging pipeline (append-only)

Purpose: Ensure every significant action is auditable.

Acceptance criteria:
- API writes audit events for:
  - workspace create,
  - source create/update,
  - review approvals,
  - build publish/rollback,
  - gateway queries.
- Audit events are immutable via application paths.

Required evidence pointers:
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.audit_events (append-only)
- evidence: spec/08_OBSERVABILITY.md :: Audit Logging Signals

Implementation Notes:
- Ensure correlation_id is present.
- Failure interpretation:
  - If audit logging can be bypassed, block feature work until fixed.

#### T-0012 Policy interface (internal) + deny-by-default baseline

Purpose: Provide a policy evaluation interface used by the gateway.

Acceptance criteria:
- Policy evaluator exists with:
  - RBAC/ABAC input structure,
  - allow/deny output with applied masks/filters.
- Default behavior is deny unless explicitly allowed.

Required evidence pointers:
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Authorization model
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0003 Deny-By-Default Policy

Implementation Notes:
- Implement internal policy rules first; add OPA adapter later.
- Failure interpretation:
  - If any request is allowed without explicit policy, treat as a security defect.

---

## PHASE_2_DATA_INGEST_AND_CATALOG

### Phase goal
Connect sources and create an evidence-backed catalog with profiling and drift detection.

### Entry criteria
- PHASE_1 exit criteria met.

### Exit criteria
- Connectors can discover datasets and ingest bronze artifacts.
- Profiling produces evidence bundles stored in metadata.
- Drift detection produces review tasks.

Mapped gates:
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0001 Safe Failure Modes
- evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0002 Evidence Completeness

#### T-0013 Connector framework + filesystem connector (read-only discovery)

Purpose: Enable connecting messy folder landscapes.

Acceptance criteria:
- Filesystem connector:
  - enumerates files within scope,
  - fingerprints (size, mtime, content hash sampling strategy),
  - detects dataset families by naming patterns,
  - creates dataset records without modifying source.
- Produces discovery run records.

Required evidence pointers:
- evidence: spec/03_DOMAIN_MODEL.md :: Source
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Object Store Layout (normative)

Implementation Notes:
- Scope must support include/exclude globs.
- Failure interpretation:
  - If scope is too broad, connector must refuse or require explicit confirmation in UI.

#### T-0014 S3/MinIO connector (read-only discovery)

Purpose: Support object storage as source.

Acceptance criteria:
- S3 connector supports bucket/prefix scoping and object listing.
- Uses least privilege and never writes to source buckets.

Required evidence pointers:
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secrets Handling
- evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Retry and Timeout Policy

Implementation Notes:
- Ensure timeouts and bounded pagination.
- Failure interpretation:
  - If listing is too expensive, apply sampling and emit missing evidence notes.

#### T-0015 DB connector (read-only ingest; Postgres/MySQL baseline)

Purpose: Support existing databases as sources.

Acceptance criteria:
- Connects with read-only credentials; introspects schema/table list.
- Extracts snapshots to bronze with manifests.
- Does not require CDC in v1.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Data source classes (v1 baseline)
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secrets Handling

Implementation Notes:
- Add per-table sampling for profiling.
- Failure interpretation:
  - If permissions insufficient, produce a clear remediation checklist.

#### T-0016 Bronze ingest manifests + raw storage layout

Purpose: Make raw ingestion immutable and reproducible.

Acceptance criteria:
- Bronze storage layout matches spec/05.
- Every ingested artifact writes manifest including content_hash and parser metadata.
- Re-ingesting same content does not overwrite raw bytes.

Required evidence pointers:
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Bronze (immutable)
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0002 Deterministic Builds

Implementation Notes:
- Implement manifest writer and validator.
- Failure interpretation:
  - If raw overwrite occurs, treat as data loss bug.

#### T-0017 Profiler service (sampling budgets; evidence bundles)

Purpose: Produce measured evidence that drives autopilot recommendations.

Acceptance criteria:
- Profiler computes:
  - type candidates, null rates, uniqueness hints,
  - basic distributions (bounded),
  - parse error rates,
  - drift baseline per dataset schema version.
- Stores evidence bundle URIs in metadata.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Evidence-Backed Autopilot Rules
- evidence: spec/08_OBSERVABILITY.md :: Metrics

Implementation Notes:
- Enforce sampling budgets and record budgets used.
- Failure interpretation:
  - If profiling scans unbounded data by default, fix budgets before proceeding.

#### T-0018 Drift detection + dataset cards

Purpose: Detect schema changes and surface impact.

Acceptance criteria:
- Drift detector compares new profiling evidence to prior baseline and emits drift events.
- Drift events generate review tasks with severity and affected downstream models.

Required evidence pointers:
- evidence: spec/03_DOMAIN_MODEL.md :: ReviewTask (Review Queue item)
- evidence: spec/09_TEST_STRATEGY.md :: Negative Path Requirements

Implementation Notes:
- Start with schema-level drift; extend to distribution drift later.
- Failure interpretation:
  - If drift detection produces noisy false positives, adjust thresholds but keep fail-closed for gold publish.

---

## PHASE_3_MODELING_AND_REVIEW_QUEUE

### Phase goal
Convert profiling evidence into model/PII/relationship proposals and a usable review queue.

### Entry criteria
- PHASE_2 exit criteria met.

### Exit criteria
- Inference proposals exist with confidence and evidence.
- Review tasks are created and can be approved/rejected/deferred.
- Builds are gated by blocking tasks.

Mapped gates:
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0003 Deny-By-Default Policy
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0003 Negative Path Coverage

#### T-0019 Schema inference v0 (dataset family clustering)

Purpose: Detect entity candidates from messy files.

Acceptance criteria:
- Inference clusters datasets into families and proposes entity candidates.
- Outputs evidence bundle (column similarity, naming signals, stats fingerprints).
- Confidence scoring is present.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Evidence-Backed Autopilot Rules
- evidence: spec/03_DOMAIN_MODEL.md :: Proposal (Inference output)

Implementation Notes:
- Start with deterministic heuristics; keep ML optional and gated.
- Failure interpretation:
  - If clustering is unstable across runs, enforce deterministic sorting and stable keys.

#### T-0020 Key/relationship inference proposals (PK/FK candidates)

Purpose: Build joinable models with measured confidence.

Acceptance criteria:
- Proposes PK candidates using uniqueness/null signals.
- Proposes FK candidates using overlap sampling and type compatibility.
- Produces review tasks when confidence is below threshold.

Required evidence pointers:
- evidence: spec/03_DOMAIN_MODEL.md :: Proposal (Inference output)
- evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0002 Evidence Completeness

Implementation Notes:
- Output “missing evidence” when overlap sampling is insufficient.
- Failure interpretation:
  - If wrong key proposals auto-apply, treat as fail-closed violation.

#### T-0021 PII detection proposals (rules + optional classifier)

Purpose: Identify sensitive columns and require approvals.

Acceptance criteria:
- Rules-based PII detection produces column tag proposals with evidence.
- In strict mode, unknown sensitivity defaults to restricted.
- High-risk tags require review if confidence below threshold.

Required evidence pointers:
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: PII Detection and Review Gates
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0003 Deny-By-Default Policy

Implementation Notes:
- Store only redacted samples in evidence bundles.
- Failure interpretation:
  - If PII is logged or exposed in evidence bundles, treat as security defect.

#### T-0022 Review Queue backend (tasks, assignments, gating)

Purpose: Provide a stable approval system.

Acceptance criteria:
- Review tasks can be listed, filtered by priority, and decided.
- Decisions create approvals and audit events.
- Blocking tasks prevent gated actions (gold publish, sensitive exposure).

Required evidence pointers:
- evidence: spec/03_DOMAIN_MODEL.md :: ReviewTask (Review Queue item)
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: review.approvals

Implementation Notes:
- Implement optimistic concurrency for task decisions.
- Failure interpretation:
  - If two approvals conflict, reject second with clear error and audit.

#### T-0023 Review Queue UI (approve/reject/defer) with evidence view

Purpose: Make approvals usable and low-jargon.

Acceptance criteria:
- UI renders tasks with:
  - summary, risk, confidence, evidence bundle preview,
  - decision controls and reason fields.
- UI supports “defer” and shows impact of deferral.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Review task sizing and prioritization (human-friendly)
- evidence: spec/08_OBSERVABILITY.md :: Logging Standard

Implementation Notes:
- Evidence preview must be redacted.
- Failure interpretation:
  - If evidence is too large/noisy, revise evidence bundle format.

#### T-0024 Build gating integration (no publish without approvals)

Purpose: Enforce fail-closed behavior.

Acceptance criteria:
- Gold publication is blocked when:
  - contracts fail,
  - required blocking tasks are unresolved.
- Silver may proceed with quarantine policy (as specified), but must not bypass security gates.

Required evidence pointers:
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Publication pointers (atomic)

Implementation Notes:
- Define which tasks are blocking by default.
- Failure interpretation:
  - If gold publishes despite unresolved blocking tasks, treat as critical defect.

---

## PHASE_4_SILVER_GOLD_AND_QUERY_GATEWAY

### Phase goal
Produce canonical silver entities, governed gold semantics, and enforce safe querying via gateway.

### Entry criteria
- PHASE_3 exit criteria met.

### Exit criteria
- Silver build produces canonical entities with reversible ER decisions.
- Gold build produces semantic models and metrics, fail-closed.
- Query Gateway returns provenance and enforces policies; bypass is blocked.

Mapped gates:
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0002 Gateway Non-Bypass
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication

#### T-0025 Silver build pipeline (normalize + stable IDs + crosswalk)

Purpose: Convert bronze artifacts into canonical entities.

Acceptance criteria:
- Silver builder:
  - normalizes types (locale-aware),
  - generates stable canonical IDs,
  - maintains crosswalk mappings from source records to canonical IDs.
- Produces immutable snapshots and records snapshot metadata.

Required evidence pointers:
- evidence: spec/03_DOMAIN_MODEL.md :: Build (Silver/Gold)
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Silver (canonical)

Implementation Notes:
- Locale parsing rules must be explicit and testable.
- Failure interpretation:
  - If parsing is ambiguous, quarantine and create review task; do not guess silently.

#### T-0026 Entity Resolution v0 (blocking + deterministic matches + reversibility)

Purpose: Deduplicate entities safely.

Acceptance criteria:
- ER includes:
  - blocking keys,
  - deterministic match rules,
  - confidence scoring for probabilistic matches,
  - reversible merge decisions stored in Postgres.
- Borderline merges generate review tasks.

Required evidence pointers:
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Entity resolution over-merge corrupts identity
- evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Idempotency Rules

Implementation Notes:
- Store pre-merge references for rollback.
- Failure interpretation:
  - If merges cannot be reversed, do not ship; treat as unsafe.

#### T-0027 Quality contracts + quarantine partitions

Purpose: Ensure data quality is measurable and gating is possible.

Acceptance criteria:
- Contract framework supports:
  - schema assertions,
  - not-null and uniqueness constraints,
  - anomaly checks (bounded),
  - quarantine outputs with reasons.
- Contracts gate gold publication.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Bronze Silver Gold Rules
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication

Implementation Notes:
- Start with minimal contract types; expand later.
- Failure interpretation:
  - If quarantine reasons are missing, treat as operability defect.

#### T-0028 Gold build: semantic models + metrics pack + semantic manifest

Purpose: Publish a governed semantic surface.

Acceptance criteria:
- Gold builder produces:
  - dims/facts views/tables,
  - starter metrics pack definitions,
  - semantic manifest with dependencies and grains.
- Gold publish uses atomic pointer update only after passing gates.

Required evidence pointers:
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Semantic manifest (gold; required)
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Publication pointers (atomic)

Implementation Notes:
- Choose dbt or native SQL builder, but keep output manifest stable.
- Failure interpretation:
  - If metric definitions drift without version bump, treat as compatibility defect.

#### T-0029 Query Gateway v1 (SQL execution + RBAC/ABAC + audit + provenance)

Purpose: Enforce access centrally and return trustworthy answers.

Acceptance criteria:
- Gateway:
  - evaluates policies,
  - applies masking/row filters,
  - executes SQL against DuckDB (Starter) or Trino (Team),
  - logs AccessDecision and returns provenance with each response.
- Deny-by-default for AI tool identity.

Required evidence pointers:
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Query Gateway Contract
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.access_decisions (append-only)

Implementation Notes:
- Include query timeouts and max rows limits.
- Failure interpretation:
  - If any query returns data without provenance, treat as critical defect.

#### T-0030 Enforce non-bypass (network + code boundaries + tests)

Purpose: Prevent accidental or malicious bypass paths.

Acceptance criteria:
- Production compose/k8s network config prevents direct access to query engines/indexes.
- Code boundary checks prevent importing engine clients outside gateway.
- E2E test verifies bypass attempt fails.

Required evidence pointers:
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0002 Gateway Non-Bypass

Implementation Notes:
- Use network policies or container network isolation.
- Failure interpretation:
  - If bypass is possible, do not proceed to additional features.

#### T-0031 Profile upgrade path implementation (Starter → Team) without rebuild

Purpose: Ensure progressive disclosure is real, not a fork.

Acceptance criteria:
- Starter can be upgraded to Team:
  - object store + Iceberg + Trino added,
  - silver/gold re-materialized from bronze snapshots,
  - dataset IDs remain stable.
- No re-ingestion of source systems is required.

Required evidence pointers:
- evidence: spec/11_QUALITY_GATES.md :: G-COMP-0003 Profile Upgrade Safety
- evidence: spec/12_RUNBOOK.md :: Upgrade Procedure

Implementation Notes:
- Provide explicit migration command and verification checks.
- Failure interpretation:
  - If upgrade requires manual data surgery, revise upgrade design.

---

## PHASE_5_DECISION_ENGINE

### Phase goal
Implement the “right database for this company” engine as a safe, template-ranked recommendation system.

### Entry criteria
- PHASE_4 exit criteria met.

### Exit criteria
- T1..T8 templates exist exactly.
- Hard constraint gates are applied before scoring.
- Recommendation report contains required sections and triggers review when needed.

Mapped gates:
- evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0002 Evidence Completeness
- evidence: spec/11_QUALITY_GATES.md :: G-COMP-0002 Contract Compatibility

#### T-0032 Implement templates T1..T8 library exactly

Purpose: Provide a fixed candidate library for ranking.

Acceptance criteria:
- Templates T1..T8 exist exactly and are immutable identifiers.
- Each template defines required components and capability flags.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Template library (fixed; must be implemented)
- evidence: spec/03_DOMAIN_MODEL.md :: RecommendationReport (Decision Engine output)

Implementation Notes:
- Store templates as data (YAML/JSON) with schema validation.
- Failure interpretation:
  - If templates drift, treat as contract compatibility break.

#### T-0033 Implement hard constraint gates

Purpose: Eliminate candidates that violate declared constraints.

Acceptance criteria:
- Hard constraint gates exist at minimum for:
  - deployment constraints (on-prem/local-only),
  - security baseline (strict),
  - ops tolerance (single-node only),
  - document requirements.
- Gates output pass/fail and missing evidence notes.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Decision Engine Requirements
- evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0002 Evidence Completeness

Implementation Notes:
- Gates must be deterministic and explainable.
- Failure interpretation:
  - If gates pass without evidence, mark as missing evidence and reduce confidence.

#### T-0034 Implement scoring model + customizable weights

Purpose: Rank remaining candidates with explainable criteria.

Acceptance criteria:
- Scoring uses weighted criteria and outputs per-criterion subscores.
- Weights are configurable via a single config file with bounded ranges.
- Defaults align to “minimal complexity that meets constraints”.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Evidence-Backed Autopilot Rules
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Recommendation Report Format

Implementation Notes:
- Keep criteria list stable; changes require a decision record.
- Failure interpretation:
  - If scoring uses hidden heuristics, treat as maintainability defect.

#### T-0035 Implement confidence model + approval-required triggers

Purpose: Prevent silent risky recommendations.

Acceptance criteria:
- Confidence is computed from evidence completeness and stability indicators.
- Approval-required triggers are emitted when:
  - confidence below threshold,
  - adding store types beyond baseline,
  - strict security baseline plus new exposure surfaces.

Required evidence pointers:
- evidence: spec/01_SCOPE.md :: Decision Engine Requirements
- evidence: CONSTITUTION.md :: Fail-closed by default

Implementation Notes:
- Define thresholds as config with conservative defaults.
- Failure interpretation:
  - If risky complexity can be deployed without approval, treat as critical defect.

#### T-0036 Recommendation report generation + UI display

Purpose: Make recommendations usable and auditable.

Acceptance criteria:
- Report includes:
  - ranked top-3 templates,
  - hard constraint gate results,
  - score breakdown,
  - confidence,
  - missing evidence list,
  - approval_required and reasons.
- UI shows report and allows “approve” to proceed to deployment plan steps (plan only; no silent deploy).

Required evidence pointers:
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Recommendation Report Format
- evidence: spec/03_DOMAIN_MODEL.md :: RecommendationReport (Decision Engine output)

Implementation Notes:
- Ensure the report is stored and versioned.
- Failure interpretation:
  - If UI hides evidence/confidence, treat as UX defect.

---

## PHASE_6_GOVERNANCE_AND_DOCUMENT_RETRIEVAL

### Phase goal
Add enterprise governance controls and optional document retrieval modules, still enforced by gateway.

### Entry criteria
- PHASE_5 exit criteria met.

### Exit criteria
- ABAC enforcement supports OPA adapter (Enterprise).
- Column masking and row filtering are enforced in gateway.
- Deletion workflow exists with evidence reporting.
- Document retrieval (if enabled) is policy-filtered via gateway.

Mapped gates:
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0004 Plugin Safety
- evidence: spec/11_QUALITY_GATES.md :: G-OPS-0002 Backup Restore Drills

#### T-0037 ABAC integration (OPA optional) + masking rules

Purpose: Enforce fine-grained access.

Acceptance criteria:
- Gateway supports ABAC decisions from:
  - internal evaluator (baseline),
  - OPA adapter (Enterprise).
- Masking supports at least:
  - nulling,
  - hashing/tokenization,
  - partial reveal.

Required evidence pointers:
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Authorization model
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0003 Deny-By-Default Policy

Implementation Notes:
- Ensure policy evaluation failures default to deny.
- Failure interpretation:
  - If policy engine outage allows access, treat as critical defect.

#### T-0038 Deletion request workflow + evidence report (legal hold blocking)

Purpose: Support right-to-erasure and internal deletion operations safely.

Acceptance criteria:
- Workflow supports:
  - intake, subject identification, impact preview, approval, execution, evidence report.
- Legal hold blocks execution and is logged.
- Deletion updates derived layers and indexes consistently.

Required evidence pointers:
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Retention and Deletion Mechanics
- evidence: spec/12_RUNBOOK.md :: Maintenance Playbook

Implementation Notes:
- Default: retention enforcement disabled; deletion only via workflow.
- Failure interpretation:
  - If deletion is irreversible without backup, block release until backup/restore verified.

#### T-0039 Document ingest + extraction (optional module) with metadata binding

Purpose: Enable retrieval over PDFs/emails safely.

Acceptance criteria:
- Raw documents are stored immutably.
- Extraction produces text plus evidence (confidence, extraction method).
- Indexing binds documents to dataset IDs and access attributes.

Required evidence pointers:
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Documents (optional module)
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Prompt injection / malicious document content affecting AI behavior

Implementation Notes:
- Extraction failures create review tasks; raw still preserved.
- Failure interpretation:
  - If indexing proceeds without metadata binding, disable module until fixed.

#### T-0040 Retrieval via gateway (policy-filtered) + AI tool integration

Purpose: Allow governed retrieval without bypass.

Acceptance criteria:
- Retrieval endpoint exists in gateway and enforces the same policies as SQL.
- AI tool identity uses allowlists and cannot access non-gold tables by default.
- Responses include citations to bronze artifacts and provenance.

Required evidence pointers:
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Retrieval (optional module; policy-filtered)
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0002 Gateway Non-Bypass

Implementation Notes:
- Implement safe prompt handling: data content is not treated as instructions.
- Failure interpretation:
  - If retrieval bypass is possible, treat as critical defect.

#### T-0041 Secrets handling hardening + rotation runbook integration

Purpose: Make secret hygiene production-ready.

Acceptance criteria:
- Secrets are stored only in secret mechanisms; never in DB plaintext.
- Logs are redacted; secret scanning check exists.
- Rotation procedure documented and tested.

Required evidence pointers:
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secrets Handling
- evidence: checks/CHECKS_INDEX.md :: CHK-SECRETS-HYGIENE

Implementation Notes:
- Provide a rotation drill in runbook.
- Failure interpretation:
  - Any secret leak is a stop-ship defect.

---

## PHASE_7_OBSERVABILITY_TESTS_RELEASE

### Phase goal
Prove readiness: observability, benchmarks, CI gates, packaging, and release acceptance.

### Entry criteria
- PHASE_6 exit criteria met.

### Exit criteria
- Observability metrics exist and dashboards are defined.
- MessyBench and CI harness run and produce results.
- Packaging includes compose profiles and upgrade docs.
- All gates pass.

Mapped gates:
- evidence: spec/11_QUALITY_GATES.md :: G-PERF-0001 Performance Harness and No Regression
- evidence: spec/11_QUALITY_GATES.md :: G-OPS-0001 Runbook Complete

#### T-0042 Observability instrumentation + dashboards

Purpose: Provide operator signals that prove correctness.

Acceptance criteria:
- Logs include correlation IDs.
- Metrics from spec/08 are emitted.
- Dashboard definitions exist and are documented.

Required evidence pointers:
- evidence: spec/08_OBSERVABILITY.md :: Metrics
- evidence: spec/12_RUNBOOK.md :: Troubleshooting

Implementation Notes:
- Start with Prometheus metrics endpoint; add traces in Enterprise.
- Failure interpretation:
  - If correlation IDs are missing, fix before adding more features.

#### T-0043 MessyBench generator + evaluation harness

Purpose: Provide regression-proof messy-data benchmarks.

Acceptance criteria:
- Generator produces datasets and ground truth.
- Harness runs pipeline on MessyBench and compares outputs to golden expectations.
- Results are produced as machine-readable artifacts in CI.

Required evidence pointers:
- evidence: spec/09_TEST_STRATEGY.md :: MessyBench
- evidence: spec/11_QUALITY_GATES.md :: G-PERF-0001 Performance Harness and No Regression

Implementation Notes:
- Keep dataset sizes bounded for CI; provide optional larger runs.
- Failure interpretation:
  - If goldens are unstable, enforce determinism rules.

#### T-0044 CI pipelines: unit/integration/e2e/security/perf harness gating

Purpose: Prevent regressions and enforce gates automatically.

Acceptance criteria:
- CI runs:
  - unit + integration + e2e
  - security denial tests
  - performance harness baseline compare
- CI fails on gate violations.

Required evidence pointers:
- evidence: spec/11_QUALITY_GATES.md :: Gate Index
- evidence: templates/PR_REVIEW_CHECKLIST.md :: Checks pass before acceptance

Implementation Notes:
- Use a single `schemapilot check` entry to run all checks locally and in CI.
- Failure interpretation:
  - If CI is flaky, quarantine the flaky test and fix determinism before release.

#### T-0045 Packaging: docker compose profiles + optional k8s skeleton

Purpose: Deliver installable OSS deployment.

Acceptance criteria:
- Docker Compose supports progressive profiles (Starter/Team/Enterprise) as config-driven modules.
- Upgrade procedure exists and is tested in CI for Starter→Team baseline.
- Optional k8s manifests exist as non-default path.

Required evidence pointers:
- evidence: spec/12_RUNBOOK.md :: Docker Compose Operations
- evidence: spec/11_QUALITY_GATES.md :: G-COMP-0003 Profile Upgrade Safety

Implementation Notes:
- Avoid mandatory component sprawl in Enterprise; modules are enabled only when required.
- Failure interpretation:
  - If Enterprise profile requires many mandatory systems, revisit progressive module design.

#### T-0046 Release readiness: runbook completeness + all quality gates pass

Purpose: Declare DONE for v1 implementation readiness.

Acceptance criteria:
- Runbook covers local run, test, deploy, rollback, backup/restore, deletion workflow.
- All quality gates are passing and evidenced.
- No blocking questions remain for critical flows; if any remain, release is blocked.

Required evidence pointers:
- evidence: spec/11_QUALITY_GATES.md :: No Evidence, No Accept / No Progress
- evidence: spec/12_RUNBOOK.md :: Maintenance Playbook

Implementation Notes:
- Record final release evidence in PROGRESS and in implementation repo artifacts.
- Failure interpretation:
  - If any critical flow lacks evidence, do not declare release.

---

## DONE Criteria

The implementation is considered DONE for v1 when:
- PHASE_0..PHASE_7 tasks are DONE with evidence.
- All gates in spec/11 are PASS with recorded evidence.
- Non-blocking questions may remain, but must not affect critical flows without conservative fail-closed baselines.
evidence: checks/QUESTIONS_FOR_USER.md :: Questions for User
