# DECISIONS.md (Append-only)

## Decision Index
- D-0001 Default implementation stack (backend/worker/UI/CLI)
- D-0002 Progressive packaging profiles (Starter â†’ Team â†’ Enterprise) as a single upgrade path
- D-0003 Query Gateway is the single enforcement point (no bypass)
- D-0004 Safe startup defaults (localhost bind; auth required for non-local)
- D-0005 Stable identifier strategy (ULID/UUID usage)
- D-0006 Storage layer strategy (Bronze immutable; Silver ER; Gold semantic)
- D-0007 Plugin architecture baseline (connectors/transforms/checks)
- D-0008 Boundary fitness enforcement baseline (repo-local static checker + rules file)
- D-0009 Metadata persistence baseline (SQLAlchemy + Alembic schema-first)
- D-0010 Tooling baseline command contract (`schemapilot check` as single entrypoint)
- D-0011 Shared audit persistence model (gateway + control plane append-only writes)
- D-0012 Manifest scope excludes transient runtime/cache/vendor paths
- D-0013 Connector baseline implementation (filesystem, S3 read-only, DB read-only)
- D-0014 Profiling/drift baseline (bounded CSV profiling + schema drift review tasks)
- D-0015 Modeling + review baseline (heuristic inference, PII proposals, gated gold publish)
- D-0016 Silver/Gold build baseline (deterministic snapshots + fail-closed publish pointer)
- D-0017 Gateway SQL execution baseline (policy-first execution + non-bypass enforcement tests)
- D-0018 Decision engine baseline (fixed T1..T8 library + gate-first scoring + confidence triggers)
- D-0019 PHASE_6 governance baseline (ABAC/OPA fail-closed + deletion/doc retrieval + secrets rotation drill)
- D-0020 Observability baseline (structured logs + metrics endpoints + dashboard definition)
- D-0021 MessyBench and performance harness baseline (machine-readable outputs + regression thresholds)
- D-0022 Packaging baseline (compose progressive profiles + optional k8s skeleton)
- D-0023 Release readiness baseline (`schemapilot check` includes governance/perf/backup/rotation drills)
- D-0024 Enterprise-like release simulation baseline (clean-room install + project-scoped dependency audit + automated release gate)
- D-0025 Security and determinism hardening baseline (authenticated gateway context, enforced ABAC filtering, server-side retrieval corpus, and fail-closed ingest/build checks)
- D-0026 Adoption roadmap hardening baseline (demo-first onboarding, operator docs depth, and enterprise extension guidance)

---

## D-0001 Default implementation stack (backend/worker/UI/CLI)

**Decision**  
Implement SchemaPilot as a monorepo with:
- Backend + workers: **Python 3.12**
  - API: **FastAPI**
  - DB access: **SQLAlchemy**
  - Migrations: **Alembic**
  - Background jobs/orchestration: **Dagster** (Team/Enterprise), embedded scheduler (Starter)
- CLI: **Python** (Typer)
- UI: **TypeScript + React** (Vite)
- Default runtime: **Docker Compose**; optional Kubernetes manifests.

**Rationale**  
- Minimizes operational burden while supporting enterprise-grade controls.
- Python accelerates data profiling/inference and integrates well with DuckDB/Iceberg tooling.
- FastAPI + React provides an operable UI/API split with clear contracts.

**Alternatives considered**  
- Go backend: stronger single-binary ops but slower iteration on data tooling.
- Node backend: strong web ecosystem but weaker default fit for profiling/ETL libraries.

**Implications**  
- All public contracts must be specified in spec/04 and enforced via gates.
- CI must include Python + TypeScript checks.

**Affected files**  
- evidence: spec/02_ARCHITECTURE.md :: Component Boundary Table
- evidence: spec/10_PHASES_AND_TASKS.md :: PHASE_0_BOOTSTRAP

**Verification impact**  
- evidence: checks/CHECKS_INDEX.md :: CHK-TOOLING-BASELINE
- evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0001 Boundary Fitness

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (tooling affects all flows)  
- Unsafe/high-risk: NO (reversible with bounded effort early)  
- Conservative baseline available: YES  
- Safe to decide: YES  
- Conservative baseline: NO

---

## D-0002 Progressive packaging profiles (Starter â†’ Team â†’ Enterprise) as a single upgrade path

**Decision**  
Treat profiles as **one coherent recommended approach** with progressive disclosure:
- Starter: single-node evaluation only
- Team: default recommended profile
- Enterprise: adds stricter governance and scale modules

**Rationale**  
Avoids â€œoptions menuâ€ drift and supports predictable upgrades without rebuild.

**Alternatives considered**  
- Multiple competing reference architectures (rejected: increases drift and operational confusion).

**Implications**  
- Decision Engine templates MUST map to this progression.
- Runbook MUST describe upgrade path steps.

**Affected files**  
- evidence: spec/01_SCOPE.md :: Packaging Profiles as Upgrade Path
- evidence: spec/12_RUNBOOK.md :: Docker Compose Operations

**Verification impact**  
- evidence: spec/11_QUALITY_GATES.md :: G-COMP-0003 Profile Upgrade Safety

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (deployment/ops)  
- Unsafe/high-risk: NO (upgrade path is additive)  
- Conservative baseline available: YES  
- Safe to decide: YES  
- Conservative baseline: NO

---

## D-0003 Query Gateway is the single enforcement point (no bypass)

**Decision**  
All SQL and retrieval access MUST pass through the Query Gateway. No component (including AI tools) may connect directly to query engines or indexes in production mode.

**Rationale**  
Centralizes ABAC/RBAC, masking, audit logging, provenance, and rate limiting.

**Alternatives considered**  
- Distributed enforcement in each engine (rejected: inconsistent policy enforcement and audit gaps).

**Implications**  
- Gateway must support SQL (DuckDB/Trino) and optional retrieval (OpenSearch/Qdrant) behind the same policy checks.
- Network and code boundaries must prevent bypass.

**Affected files**  
- evidence: spec/02_ARCHITECTURE.md :: Dependency Direction Rules
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Query Gateway Contract

**Verification impact**  
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0002 Gateway Non-Bypass
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES  
- Unsafe/high-risk: YES (security posture)  
- Conservative baseline available: YES (deny-by-default + localhost-only)  
- Safe to decide: YES  
- Conservative baseline: NO

---

## D-0004 Safe startup defaults (localhost bind; auth required for non-local)

**Decision**  
Default runtime behavior:
- Bind services to **localhost only** by default.
- If configured to listen on non-local interfaces:
  - MUST require explicit authentication configuration; otherwise FAIL TO START.

**Rationale**  
Prevents accidental exposure of data services and admin APIs.

**Alternatives considered**  
- Open-by-default with optional auth (rejected).

**Implications**  
- Runbook must document secure exposure procedure.
- Tests must cover fail-to-start behavior when misconfigured.

**Affected files**  
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Secure Defaults and Failure Modes
- evidence: spec/12_RUNBOOK.md :: Deployment Runbook

**Verification impact**  
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0001 Safe Startup Defaults
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0001 Safe Failure Modes

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES  
- Unsafe/high-risk: NO (safe default)  
- Conservative baseline available: YES  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0005 Stable identifier strategy (ULID/UUID usage)

**Decision**  
- Use **ULID** for time-sortable operational IDs: `run_id`, `build_id`, `task_id` (review tasks), `artifact_id`.
- Use **UUID** for long-lived domain IDs where sorting is not required: `workspace_id`, `dataset_id`, `source_id`, `policy_id`.

**Rationale**  
Improves traceability (chronological sort) without coupling domain identity to time.

**Alternatives considered**  
- UUID everywhere (simpler but weaker operational sorting).
- Snowflake IDs (introduces infra coupling).

**Implications**  
- ID formats must be validated at boundaries (API/DB).
- Logs and audit events must include correlation IDs derived from run/build IDs.

**Affected files**  
- evidence: spec/03_DOMAIN_MODEL.md :: Identity and ID Formats
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Postgres Schema

**Verification impact**  
- evidence: spec/11_QUALITY_GATES.md :: G-COMP-0002 Contract Compatibility

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (public contracts)  
- Unsafe/high-risk: YES (breaking change if altered later)  
- Conservative baseline available: YES  
- Safe to decide: YES  
- Conservative baseline: NO

---

## D-0006 Storage layer strategy (Bronze immutable; Silver ER; Gold semantic)

**Decision**  
- Bronze: immutable raw artifacts + manifests (append-only)
- Silver: canonical typed entities + entity resolution + crosswalk tables (reversible decisions)
- Gold: governed semantic views/tables + metrics pack; fail-closed publication

**Rationale**  
Separates provenance preservation (bronze), canonical identity (silver), and business semantics (gold).

**Alternatives considered**  
- â€œWarehouse-onlyâ€ without bronze (rejected: loses forensic traceability and drift evidence).

**Implications**  
- Deletion/retention must account for derived layers and indexes.
- Quality contracts must gate gold publication.

**Affected files**  
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Storage Overview
- evidence: spec/01_SCOPE.md :: Bronze Silver Gold Rules

**Verification impact**  
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0002 Deterministic Builds
- evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication

**DSC summary**  
- Externally constrained: YES (retention policy values are external)  
- Critical flow impacted: YES  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (retention enforcement disabled by default)  
- Safe to decide: YES  
- Conservative baseline: YES (retention enforcement disabled until configured)

---

## D-0007 Plugin architecture baseline (connectors/transforms/checks)

**Decision**  
Implement plugins as **capability-scoped packages**:
- Connector plugins: discovery + bronze ingest only
- Transform plugins: deterministic transforms only unless explicitly approved
- Check plugins: quality checks producing machine-readable results

Plugin discovery mechanism:
- Python entry points (or a manifest directory) with explicit allowlist configuration.

**Rationale**  
Enables extension without compromising security or determinism.

**Alternatives considered**  
- Arbitrary executable scripts (rejected: weak sandboxing and auditability).

**Implications**  
- Plugin allowlisting and signature policy must be enforced in Enterprise.
- Docs must include connector authoring guide in repo (implemented later).

**Affected files**  
- evidence: spec/02_ARCHITECTURE.md :: Component Boundary Table
- evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Plugin supply-chain compromise

**Verification impact**  
- evidence: spec/11_QUALITY_GATES.md :: G-SEC-0004 Plugin Safety
- evidence: checks/CHECKS_INDEX.md :: CHK-SUPPLY-CHAIN

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (external I/O)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (plugins disabled unless allowlisted)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0008 Boundary fitness enforcement baseline (repo-local static checker + rules file)

**Decision**  
Implement CHK-BOUNDARY-FITNESS initially with a repo-local static checker and explicit rules file:
- checker: `tools/check_boundary_fitness.py`
- rules: `tools/boundary_rules.json`

The checker enforces module-direction imports and detects cross-module dependency cycles for the scaffolded monorepo modules (`control_plane`, `gateway`, `workers`, `shared_domain`, `cli`).

**Rationale**  
- Provides immediate, deterministic enforcement without adding external toolchain dependencies in bootstrap.
- Keeps boundary policy machine-readable and easy to evolve.

**Alternatives considered**  
- Immediate `import-linter` and `dependency-cruiser` integration (deferred to a later tooling phase).

**Implications**  
- Boundary policy changes must update `tools/boundary_rules.json` and remain aligned with architecture rules.
- CI can run the checker directly via Python without additional runtime prerequisites.

**Affected files**  
- evidence: spec/02_ARCHITECTURE.md :: Dependency Direction Rules
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

**Verification impact**  
- evidence: evidence/t0001/boundary_check.txt :: PASS CHK-BOUNDARY-FITNESS
- evidence: tools/check_boundary_fitness.py :: CHK-BOUNDARY-FITNESS static checker for scaffold boundaries.

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (gateway non-bypass and boundary integrity)  
- Unsafe/high-risk: YES (boundary erosion risk if not enforced)  
- Conservative baseline available: YES (deny forbidden imports and fail check)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0009 Metadata persistence baseline (SQLAlchemy + Alembic schema-first)

**Decision**  
Implement control-plane metadata persistence with SQLAlchemy models and Alembic migrations:
- ORM models in `backend/control_plane/db_models.py`
- migration baseline in `migrations/versions/0001_initial_schema.py`
- migration safety check command `tools/migration_check.py`

**Rationale**  
- Satisfies PHASE_1 requirements for durable metadata and migration discipline.
- Keeps runtime database implementation portable (SQLite for local tests, Postgres-compatible schema design).

**Alternatives considered**  
- Continue with in-memory-only state (rejected: not durable and not migration-safe).

**Implications**  
- API behavior is now backed by database sessions.
- Migration checks become required in the local/CI check pipeline.

**Affected files**  
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Postgres Schema
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0008 Postgres migrations baseline (schemas + tables)

**Verification impact**  
- evidence: evidence/t0008/migration_check.txt :: PASS CHK-MIGRATIONS
- evidence: tests/test_migrations.py :: test_alembic_migration_upgrade_and_downgrade

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (migrations and metadata durability)  
- Unsafe/high-risk: YES (schema drift risk)  
- Conservative baseline available: YES (single revision with reversible downgrade)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0010 Tooling baseline command contract (`schemapilot check` as single entrypoint)

**Decision**  
Define `schemapilot check` as the authoritative local/CI entrypoint for tooling baseline:
- Python lint (`ruff`)
- Python typecheck (`mypy`)
- unit/integration tests (`pytest`)
- migration drill (`tools/migration_check.py`)
- SSOT checks (`tools/ssot_verify.py`, `tools/verify_manifest.py`)
- UI lint/type/test (`npm run lint`, `npm run typecheck`, `npm run test`)
- smoke test (`tools/smoke_test.py`)

**Rationale**  
Prevents local/CI drift and keeps checks reproducible.

**Alternatives considered**  
- Separate local and CI scripts (rejected: drift risk).

**Implications**  
- CI now invokes the same check path as local development.
- Phase gates can rely on one deterministic command contract.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0002 Tooling baseline (format/lint/typecheck/test) + CI wiring
- evidence: spec/12_RUNBOOK.md :: CI and Test Commands

**Verification impact**  
- evidence: evidence/t0002/tooling_components.txt :: All checks passed!
- evidence: .github/workflows/ci.yml :: Run SchemaPilot checks

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (quality gates and release safety)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES  
- Safe to decide: YES  
- Conservative baseline: NO

---

## D-0011 Shared audit persistence model (gateway + control plane append-only writes)

**Decision**  
Centralize append-only audit models in `backend/shared_domain/audit_models.py` and have both control plane and gateway write audit/access-decision rows through that shared schema.

**Rationale**  
Maintains single semantics for audit invariants while preserving boundary rules (both modules import from shared domain).

**Alternatives considered**  
- Duplicate audit model definitions per module (rejected: duplication and drift risk).

**Implications**  
- Gateway query/retrieve requests now produce audit rows and access-decision rows.
- Control-plane review/build lifecycle stubs emit audit events.

**Affected files**  
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.audit_events (append-only)
- evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: audit.access_decisions (append-only)

**Verification impact**  
- evidence: evidence/t0011/audit_pipeline_tests.txt :: test_gateway_query_writes_audit_and_access_decision PASSED
- evidence: evidence/t0011/audit_pipeline_tests.txt :: test_create_operations_emit_audit_events PASSED

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (auditability and policy enforcement traceability)  
- Unsafe/high-risk: YES (audit gaps if wrong)  
- Conservative baseline available: YES (append-only writes only)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0012 Manifest scope excludes transient runtime/cache/vendor paths

**Decision**  
Manifest generation/verification excludes transient and machine-local directories:
- `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
- `__pycache__`, `.venv`
- `node_modules`
- `runtime`
- `.git`

**Rationale**  
Keeps drift checks deterministic and prevents false failures caused by ephemeral runtime artifacts.

**Alternatives considered**  
- Hash every file recursively (rejected: unstable and noisy in development).

**Implications**  
- MANIFEST verification focuses on versioned project artifacts and evidence files.
- Runtime and dependency caches are intentionally outside drift scope.

**Affected files**  
- evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0004 Determinism baseline: manifest generation + verification check definitions

**Verification impact**  
- evidence: evidence/t0004/manifest_generate.txt :: Generated MANIFEST.sha256
- evidence: evidence/t0004/manifest_verify.txt :: PASS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (drift detection gate)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0013 Connector baseline implementation (filesystem, S3 read-only, DB read-only)

**Decision**  
Implement PHASE_2 connector baseline with three read-only connector paths:
- Filesystem discovery connector with include/exclude scope matching
- S3 connector abstraction using injected list-only capability
- Database connector for schema discovery and bounded snapshot extraction

**Rationale**  
Delivers v1 source coverage baseline without introducing write-side risks to source systems.

**Alternatives considered**  
- Broad SaaS/API connector scope in PHASE_2 (rejected: large surface area with weak early evidence).

**Implications**  
- Connectors are read-only by design and bounded by explicit scope controls.
- S3 and DB implementations are capability abstractions that can be wired to production clients later.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0013 Connector framework + filesystem connector (read-only discovery)
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0014 S3/MinIO connector (read-only discovery)
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0015 DB connector (read-only ingest; Postgres/MySQL baseline)

**Verification impact**  
- evidence: evidence/t0013/filesystem_connector_tests.txt :: test_filesystem_connector_discovers_by_scope PASSED
- evidence: evidence/t0014/s3_connector_tests.txt :: test_s3_connector_lists_objects_read_only PASSED
- evidence: evidence/t0015/database_connector_tests.txt :: test_database_connector_discovery_and_snapshot PASSED

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (external I/O and discovery scope)  
- Unsafe/high-risk: YES (over-broad ingestion risk)  
- Conservative baseline available: YES (read-only, scoped connectors)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0014 Profiling/drift baseline (bounded CSV profiling + schema drift review tasks)

**Decision**  
Implement deterministic profiling and drift baseline for PHASE_2:
- bounded CSV profiling (`sample_limit`)
- evidence bundle persistence in deterministic JSON paths
- schema drift detection based on added/removed columns
- drift-to-review-task transformation for queue integration
- bronze ingest manifest writer with content-hash idempotency checks

**Rationale**  
Provides evidence-backed autopilot inputs and early drift visibility without unbounded scans.

**Alternatives considered**  
- Unbounded full-table profiling by default (rejected: performance and operability risk).

**Implications**  
- Profiling results become explicit artifacts referenced by downstream inference/review.
- Drift severity can gate downstream model publication decisions.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0016 Bronze ingest manifests + raw storage layout
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0017 Profiler service (sampling budgets; evidence bundles)
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0018 Drift detection + dataset cards

**Verification impact**  
- evidence: evidence/t0016/bronze_ingest_tests.txt :: test_bronze_ingest_writes_manifest_and_is_idempotent PASSED
- evidence: evidence/t0017/profiler_tests.txt :: test_profiler_and_drift_pipeline PASSED
- evidence: evidence/t0018/drift_detection_tests.txt :: test_profiler_and_drift_pipeline PASSED

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (determinism and drift safety)  
- Unsafe/high-risk: NO (bounded and review-triggered baseline)  
- Conservative baseline available: YES  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0015 Modeling + review baseline (heuristic inference, PII proposals, gated gold publish)

**Decision**  
Implement PHASE_3 baseline with deterministic heuristic inference and explicit review gating:
- schema clustering and key/relationship proposal heuristics in workers
- PII proposal engine with confidence + redacted evidence samples
- review queue backend persisted in review tables with approve/reject/defer flows
- UI review controls with evidence/confidence visibility
- gold publish gate blocks on unresolved blocking review tasks or contract failure

**Rationale**  
Provides evidence-backed autopilot with human control, while keeping fail-closed publication behavior explicit.

**Alternatives considered**  
- Fully autonomous model/PII auto-apply in PHASE_3 (rejected: violates approval-first posture).

**Implications**  
- Proposal flows are review-first and auditable.
- Gold publication endpoint checks review-task blocking state before allowing publish.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0019 Schema inference v0 (dataset family clustering)
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0021 PII detection proposals (rules + optional classifier)
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0024 Build gating integration (no publish without approvals)

**Verification impact**  
- evidence: evidence/t0019/schema_inference_tests.txt :: test_schema_inference_clusters_dataset_families PASSED
- evidence: evidence/t0022/review_queue_backend_tests.txt :: test_review_queue_create_list_decide PASSED
- evidence: evidence/t0024/build_gating_tests.txt :: test_gold_publish_blocked_when_blocking_review_task_open PASSED

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (security/model approvals and publish gating)  
- Unsafe/high-risk: YES (auto-apply risk without human checks)  
- Conservative baseline available: YES (blocking tasks + deny publish)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0016 Silver/Gold build baseline (deterministic snapshots + fail-closed publish pointer)

**Decision**  
Implement PHASE_4 data-plane build baseline with deterministic JSON snapshot artifacts:
- silver builder normalizes records, assigns stable canonical IDs, and writes crosswalk mappings
- quality-contract evaluator routes failing rows to quarantine with explicit reasons
- gold builder emits semantic manifest and updates published pointer only when publish is allowed
- ER baseline provides reversible merge payloads

**Rationale**  
Creates an auditable path from source rows to semantic outputs while preserving rollback and quarantine behavior.

**Alternatives considered**  
- Immediate full lakehouse implementation in PHASE_4 (rejected for bootstrap complexity).

**Implications**  
- Build outputs are deterministic for fixed inputs and snapshot IDs.
- Publication pointer behavior is explicitly fail-closed.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0025 Silver build pipeline (normalize + stable IDs + crosswalk)
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0028 Gold build: semantic models + metrics pack + semantic manifest

**Verification impact**  
- evidence: evidence/t0025/silver_build_tests.txt :: test_silver_build_normalizes_and_writes_crosswalk PASSED
- evidence: evidence/t0028/gold_build_tests.txt :: test_gold_build_writes_manifest_and_pointer_fail_closed PASSED

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (determinism + publication safety)  
- Unsafe/high-risk: YES (publish corruption risk)  
- Conservative baseline available: YES (block publish and preserve pointer)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0017 Gateway SQL execution baseline (policy-first execution + non-bypass enforcement tests)

**Decision**  
Implement gateway SQL execution path with policy-first evaluation:
- deny-by-default policy checks run before SQL execution
- SQL execution handled by gateway executor utility
- responses always include provenance and policy decision ID
- non-bypass behavior validated by tests ensuring control plane does not expose gateway query route

**Rationale**  
Preserves single enforcement point while enabling functional SQL-first querying in bootstrap profiles.

**Alternatives considered**  
- Keep gateway responses mocked without SQL execution (rejected: insufficient for query contract progress).

**Implications**  
- Query execution remains coupled to policy evaluation and audit writes.
- Non-bypass safety has executable evidence in tests.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0029 Query Gateway v1 (SQL execution + RBAC/ABAC + audit + provenance)
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0030 Enforce non-bypass (network + code boundaries + tests)

**Verification impact**  
- evidence: evidence/t0029/gateway_query_tests.txt :: test_gateway_executes_sql_and_returns_provenance PASSED
- evidence: evidence/t0030/non_bypass_tests.txt :: test_control_plane_has_no_gateway_query_endpoint PASSED

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (policy enforcement and data exposure path)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (deny-by-default + route isolation test)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0018 Decision engine baseline (fixed T1..T8 library + gate-first scoring + confidence triggers)

**Decision**  
Implement PHASE_5 decision engine with:
- fixed template data file for T1..T8 IDs
- hard-constraint gate evaluation before scoring
- configurable weighted scoring model
- confidence and approval-required trigger logic
- recommendation report rendering through API and UI

**Rationale**  
Provides explainable architecture recommendations with conservative approval triggers.

**Alternatives considered**  
- Dynamic/unbounded template IDs (rejected: contract instability risk).

**Implications**  
- Recommendation report is now structured and testable.
- Approval-required behavior is deterministic and tied to confidence/complexity signals.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0032 Implement templates T1..T8 library exactly
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0035 Implement confidence model + approval-required triggers

**Verification impact**  
- evidence: evidence/t0032/template_library_tests.txt :: test_template_library_contains_t1_to_t8_exactly PASSED
- evidence: evidence/t0036/recommendation_api_tests.txt :: test_recommendation_endpoint_returns_report_fields PASSED

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (autopilot recommendation safety)  
- Unsafe/high-risk: YES (complexity escalation without review risk)  
- Conservative baseline available: YES (approval_required triggers)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0019 PHASE_6 governance baseline (ABAC/OPA fail-closed + deletion/doc retrieval + secrets rotation drill)

**Decision**  
Implement PHASE_6 governance controls with conservative fail-closed behavior:
- ABAC supports internal evaluation and optional OPA mode, with deny on OPA unavailability.
- Deletion workflow emits impact preview and evidence report; legal hold and missing approvals block execution.
- Document ingest keeps raw immutable artifacts and metadata-bound extraction evidence; extraction failures preserve raw and mark failed status.
- Retrieval stays gateway-only with policy evaluation, AI allowlist checks, citations, and provenance.
- Secrets hygiene includes repository scanning and a deterministic rotation drill command.

**Rationale**  
Delivers governance requirements while preserving single enforcement point and fail-closed semantics for externally constrained integrations.

**Alternatives considered**  
- Enable OPA by default in all profiles (rejected: external dependency risk and unsafe startup coupling).
- Allow deletion without explicit approval workflow (rejected: violates critical-flow safety).

**Implications**  
- Governance features now have executable checks and drill outputs.
- AI retrieval capability remains constrained to allowlisted identities with explicit dataset permissions.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0037 ABAC integration (OPA optional) + masking rules
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0041 Secrets handling hardening + rotation runbook integration

**Verification impact**  
- evidence: evidence/t0037/abac_masking_tests.txt :: [100%]
- evidence: evidence/t0038/deletion_workflow_tests.txt :: [100%]
- evidence: evidence/t0039/document_ingest_retrieval_tests.txt :: [100%]
- evidence: evidence/t0040/gateway_retrieve_tests.txt :: [100%]
- evidence: evidence/t0041/secrets_hardening_tests.txt :: [100%]
- evidence: evidence/t0041/secrets_rotation_drill.txt :: PASS secrets rotation drill

**DSC summary**  
- Externally constrained: YES (OPA and enterprise auth/policy infrastructure)  
- Critical flow impacted: YES  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (deny on policy uncertainty; explicit approvals required)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0020 Observability baseline (structured logs + metrics endpoints + dashboard definition)

**Decision**  
Adopt a single observability module with:
- structured JSON logging helpers that include correlation IDs and redact secret-like values,
- Prometheus metrics registry for required spec/08 signals,
- `/api/v1/metrics` endpoints on control plane and gateway,
- dashboard definition in deployment assets.

**Rationale**  
Provides portable, testable observability without requiring a heavyweight monitoring stack during local development.

**Alternatives considered**  
- Ad-hoc service-specific logging and metrics wiring (rejected: duplication and drift risk).

**Implications**  
- Gateway and control plane now emit consistent request-completion logs.
- Metrics can be scraped uniformly and validated in tests.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0042 Observability instrumentation + dashboards
- evidence: spec/08_OBSERVABILITY.md :: Metrics

**Verification impact**  
- evidence: evidence/t0042/observability_tests.txt :: [100%]
- evidence: deploy/dashboards/schemapilot_overview.json :: schemapilot_query_latency_ms

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (auditability and incident response)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (local metrics + redacted logging)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0021 MessyBench and performance harness baseline (machine-readable outputs + regression thresholds)

**Decision**  
Implement a bounded benchmarking baseline:
- MessyBench generator + evaluation harness with machine-readable results artifact.
- Performance harness with baseline thresholds and conservative tolerance multiplier.
- Harness outputs persisted under `runtime/` and integrated into check tooling.

**Rationale**  
Enforces repeatable regression detection without guessing absolute SLA values.

**Alternatives considered**  
- Hard absolute performance targets for all environments (rejected: non-portable and noisy).

**Implications**  
- CI/local checks can fail deterministically on relative regressions.
- Dataset generator and harness artifacts become part of release evidence.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0043 MessyBench generator + evaluation harness
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0044 CI pipelines: unit/integration/e2e/security/perf harness gating

**Verification impact**  
- evidence: evidence/t0043/messybench_harness.txt :: PASS MessyBench harness
- evidence: evidence/t0044/perf_harness.txt :: PASS CHK-PERF-HARNESS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (release gate integrity)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (bounded datasets + threshold multiplier)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0022 Packaging baseline (compose progressive profiles + optional k8s skeleton)

**Decision**  
Provide deployment assets for progressive profiles in one compose file and optional Kubernetes starter manifests:
- compose `starter`, `team`, `enterprise` profiles,
- optional `deploy/k8s/` skeleton manifests as non-default path.

**Rationale**  
Keeps deployment story aligned with progressive profiles while avoiding hard dependency on Kubernetes for v1.

**Alternatives considered**  
- Separate compose files per profile (rejected: duplication and drift risk).

**Implications**  
- Upgrade and deployment documentation now maps directly to profile toggles.
- Optional k8s path can be expanded without affecting default local path.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0045 Packaging: docker compose profiles + optional k8s skeleton
- evidence: spec/12_RUNBOOK.md :: Docker Compose Operations

**Verification impact**  
- evidence: evidence/t0045/packaging_profiles_tests.txt :: [100%]
- evidence: deploy/docker-compose.yml :: profiles: ["starter", "team", "enterprise"]

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (operability/deployment safety)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (compose-first with optional k8s path)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0023 Release readiness baseline (`schemapilot check` includes governance/perf/backup/rotation drills)

**Decision**  
Treat `schemapilot check` as the release-readiness gate for v1 by including:
- lint/type/tests,
- migration checks,
- secrets hygiene + rotation drill,
- backup/restore drill,
- MessyBench + performance harness,
- SSOT checks and manifest verification.

**Rationale**  
Consolidates release gating into one deterministic command that local and CI environments execute identically.

**Alternatives considered**  
- Multiple independent CI jobs with partially overlapping command logic (rejected: drift and observability gaps).

**Implications**  
- Release readiness can be proven with one command output and linked evidence.
- Failures in critical governance drills block release by default.

**Affected files**  
- evidence: spec/10_PHASES_AND_TASKS.md :: T-0046 Release readiness: runbook completeness + all quality gates pass
- evidence: checks/CHECKS_INDEX.md :: CHK-TOOLING-BASELINE

**Verification impact**  
- evidence: evidence/t0044/check_tooling_baseline_pre_manifest.txt :: All checks passed!
- evidence: tools/check_tooling_baseline.py :: PASS CHK-TOOLING-BASELINE

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES  
- Unsafe/high-risk: YES (false release readiness if checks drift)  
- Conservative baseline available: YES (single command + fail-on-error)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0024 Enterprise-like release simulation baseline (clean-room install + project-scoped dependency audit + automated release gate)

**Decision**  
Add an enterprise-like validation layer that is deterministic in local and CI contexts:
- clean-room bootstrap validation via `tools/cleanroom_install_check.py`,
- project-scoped Python dependency audit via `tools/dependency_audit.py`,
- automated release-gate orchestration via `tools/release_gate.py`,
- dedicated CI workflows for security scans and tagged releases.

**Rationale**  
`pip-audit` against a shared developer environment can produce nondeterministic failures unrelated to the project. The new baseline audits dependencies declared in `pyproject.toml`, preserves strict vulnerability gating, and combines critical-flow checks into one machine-readable release decision.

**Alternatives considered**  
- Continue scanning the full active Python environment (rejected: ambient editable packages and unrelated dependencies cause false/noisy failures).
- Keep release checks fully manual (rejected: weak repeatability and evidence quality).

**Implications**  
- Release readiness now has a single `go/no-go` report artifact.
- Security workflows stay strict but focus on project dependency scope.
- Enterprise controls remain conservative simulations unless externally constrained integrations are configured.

**Affected files**  
- evidence: tools/dependency_audit.py :: Audit project dependencies declared in pyproject.toml.
- evidence: tools/release_gate.py :: RG-010
- evidence: tools/cleanroom_install_check.py :: PASS clean-room install check
- evidence: .github/workflows/security.yml :: Python dependency vulnerability scan (pip-audit)
- evidence: .github/workflows/release.yml :: Run release gate
- evidence: ENTERPRISE_RELEASE_CHECKLIST.md :: Automated Gate Command

**Verification impact**  
- evidence: tools/check_tooling_baseline.py :: tools/dependency_audit.py
- evidence: tools/release_gate.py :: RG-003
- evidence: tools/release_gate.py :: RG-010
- evidence: ENTERPRISE_RELEASE_CHECKLIST.md :: Release decision:

**DSC summary**  
- Externally constrained: YES (true enterprise topology/auth/compliance controls vary by org)  
- Critical flow impacted: YES (security, non-bypass, deletion, backup/restore, release acceptance)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (fail-closed enterprise simulation with no compliance claims)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0025 Security and determinism hardening baseline (authenticated gateway context, enforced ABAC filtering, server-side retrieval corpus, and fail-closed ingest/build checks)

**Decision**  
Harden critical runtime paths with fail-closed defaults:
- Gateway policy decisions use authenticated token context instead of request-body actor claims.
- ABAC row filters are enforced during query execution and retrieval entitlements are resolved from authenticated actor attributes.
- Retrieval corpus is loaded server-side from metadata-bound document artifacts; request-body corpus payloads are ignored.
- Connector/build determinism checks fail-closed for truncated S3 discovery, non-deterministic DB snapshots, and missing silver natural keys.
- Control-plane `NOT_FOUND` responses are normalized to the shared error contract.

**Rationale**  
Closes privilege-escalation and silent-data-loss risks while preserving deterministic, auditable behavior in critical flows.

**Alternatives considered**  
- Keep actor context in request payload (rejected: self-asserted privilege escalation risk).  
- Keep client-supplied retrieval corpus (rejected: untrusted retrieval surface).  
- Keep permissive S3/silver fallback behavior (rejected: silent partial results and ID collapse risk).

**Implications**  
- Gateway callers must provide valid bearer tokens representing actor identity and entitlements.
- Retrieval results are now bounded to server-side corpus and server-side dataset entitlements.
- Determinism/fail-closed behavior is stricter in connector and silver build flows.

**Affected files**  
- evidence: backend/gateway/app.py :: missing_or_invalid_auth_token
- evidence: backend/gateway/executor.py :: row_filter
- evidence: backend/shared_domain/retrieval.py :: load_retrieval_corpus
- evidence: backend/workers/connectors/s3.py :: fail-closed to avoid silent partial discovery.
- evidence: backend/workers/connectors/database.py :: order_by
- evidence: backend/workers/silver.py :: Missing natural key component
- evidence: backend/control_plane/app.py :: code="NOT_FOUND"

**Verification impact**  
- evidence: tests/test_gateway_policy.py :: test_gateway_requires_authenticated_token_context
- evidence: tests/test_gateway_policy.py :: test_gateway_enforces_abac_row_filter_and_masking
- evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_for_allowlisted_ai_identity
- evidence: tests/test_database_connector.py :: rows_again = extract_snapshot
- evidence: tests/test_s3_connector.py :: test_s3_connector_fails_closed_when_listing_truncated
- evidence: tests/test_silver_build.py :: test_silver_build_fails_when_natural_key_component_missing
- evidence: tests/test_control_plane_api.py :: test_control_plane_not_found_responses_follow_error_contract

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (deny/stop on missing auth, missing entitlements, and ambiguous data states)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0026 Adoption roadmap hardening baseline (demo-first onboarding, operator docs depth, and enterprise extension guidance)

**Decision**  
Expand product adoption surfaces with implementation-backed, fail-closed guidance:
- Keep onboarding demo-first via API/CLI/UI flow with explicit first-query guidance.
- Expand operator runbook troubleshooting for connector partial-ingest and manifest drift handling.
- Document OIDC claim mapping configuration and policy-pack template authoring.
- Publish plugin SDK packaging and entrypoint registration guidance for connectors/checks.
- Track weekly KPIs using a deterministic JSON artifact workflow.

**Rationale**  
Broader adoption requires low-friction onboarding, clearer operator recovery playbooks, and explicit extension guidance without weakening security defaults.

**Alternatives considered**  
- Keep onboarding and extension docs minimal (rejected: slows adoption and increases misconfiguration risk).  
- Track KPIs manually in ad-hoc documents (rejected: weak reproducibility and trend visibility).

**Implications**  
- Operators have explicit, testable commands for onboarding, KPI tracking, and drift recovery.
- Enterprise deployments can map IdP claims without code changes.
- Plugin contributors can publish extensions using a stable packaging pattern.

**Affected files**  
- evidence: cli/schemapilot_cli/main.py :: onboard_demo
- evidence: ui/src/App.tsx :: Create Demo Workspace
- evidence: backend/control_plane/app.py :: /api/v1/onboarding/demo_bootstrap
- evidence: deploy/README.md :: Policy pack authoring
- evidence: docs/PLUGIN_SDK.md :: Entry point registration
- evidence: spec/12_RUNBOOK.md :: Symptom: CHK-MANIFEST-VERIFY fails
- evidence: tools/kpi_tracker.py :: PASS KPI report generated

**Verification impact**  
- evidence: tests/test_cli_commands.py :: test_onboard_demo_command_calls_bootstrap_endpoint
- evidence: tests/test_cli_commands.py :: test_status_command_reads_tasks_and_summary
- evidence: tests/test_cli_commands.py :: test_kpi_report_invokes_tracker_script
- evidence: ui/src/App.test.tsx :: bootstraps demo workspace and renders onboarding details
- evidence: tests/test_control_plane_api.py :: test_demo_bootstrap_creates_workspace_and_review_task
- evidence: tests/test_policy_packs.py :: test_policy_pack_template_lookup
- evidence: tests/test_kpi_tracker.py :: test_kpi_tracker_writes_weekly_and_latest_reports
- evidence: tests/test_s3_connector.py :: test_s3_connector_fails_closed_when_max_keys_reached_without_truncation_metadata

**DSC summary**  
- Externally constrained: YES (enterprise IdP claim conventions vary by org)  
- Critical flow impacted: YES (auth, policy enforcement, release/operator recovery)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (deny-by-default auth/policy behavior and documented fail-closed recovery paths)  
- Safe to decide: YES  
- Conservative baseline: YES

