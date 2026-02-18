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
- D-0027 Execution-priority hardening baseline (control-plane auth, gateway SQL safety/entitlements, and runnable deploy defaults)
- D-0028 Shared metadata model relocation baseline (move control-plane SQLAlchemy metadata models into shared domain)
- D-0029 Worker orchestration baseline (deterministic queued-run processor and discover-to-catalog pipeline)
- D-0030 Evidence bundle immutability baseline (content-addressed evidence store + authenticated retrieval)
- D-0031 PII governance automation baseline (high-risk detection to blocking review tasks)
- D-0032 Contract gate hardening baseline (server-side contract reports + fail-closed publish + quality tasks)
- D-0033 Gold publish pointer baseline (server-side pointer writes + auditable rollback)
- D-0034 Gateway DuckDB read-path baseline (published gold views only + external scan denial)
- D-0035 Drift governance baseline (schema-drift proposals from discover runs + publish blocking loop)
- D-0036 Plugin runtime baseline (entry-point connector loading + worker fallback wiring)
- D-0037 KPI extraction baseline (runtime-derived weekly KPI snapshot generation)
- D-0038 Completion baseline for deploy/community/UI thin slice (compose smoke validated, OSS templates added, UI kept intentionally lightweight)

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

---

## D-0027 Execution-priority hardening baseline (control-plane auth, gateway SQL safety/entitlements, and runnable deploy defaults)

**Decision**  
Execute the `TASKLIST.md` backlog in strict security-first order and ship the first block as baseline hardening:
- Control Plane mutating endpoints require authenticated actors with role checks.
- Gateway SQL execution is read-only with unsafe SQL denial, timeout budgeting, and row-limit clamping.
- AI SQL requests require dataset context and dataset entitlement membership.
- Runtime conventions are normalized (Control Plane `8000`, Gateway `8001`) and compose assets move from placeholders to runnable Dockerfile-backed services.

**Rationale**  
This sequence removes the highest-risk exposure paths first while preserving adoption momentum through runnable local deployment assets.

**Alternatives considered**  
- Prioritize UI-first improvements (rejected: increases polish while leaving core security/runnability gaps).  
- Add full engine stack before SQL sandboxing (rejected: expands blast radius before guardrails).

**Implications**  
- Mutating control-plane API calls now require bearer auth and suitable roles.
- Gateway denies unsafe SQL operations before execution.
- AI actors cannot run SQL without explicit dataset entitlements.
- Compose defaults now align with the documented service ports and local profile behavior.

**Affected files**  
- evidence: backend/control_plane/app.py :: require_actor
- evidence: backend/shared_domain/auth.py :: load_local_auth_tokens
- evidence: backend/gateway/executor.py :: _validate_read_only_query
- evidence: backend/gateway/app.py :: reason = "sql_unsafe"
- evidence: backend/gateway/app.py :: reason = "dataset_not_allowed"
- evidence: backend/control_plane/main.py :: CONTROL_PLANE_PORT = 8000
- evidence: backend/gateway/main.py :: GATEWAY_PORT = 8001
- evidence: deploy/docker-compose.yml :: dockerfile: deploy/Dockerfile.control-plane

**Verification impact**  
- evidence: tests/test_control_plane_auth.py :: test_control_plane_denies_missing_token_for_mutation
- evidence: tests/test_gateway_sql_safety.py :: test_gateway_denies_non_read_sql
- evidence: tests/test_gateway_sql_safety.py :: test_gateway_denies_query_that_exceeds_timeout_budget
- evidence: tests/test_gateway_dataset_entitlements.py :: test_gateway_denies_ai_query_for_unentitled_dataset
- evidence: tests/test_port_conventions.py :: test_port_conventions_are_consistent
- evidence: tests/test_deploy_no_bypass_ports.py :: test_compose_does_not_publish_direct_query_engine_or_index_ports

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (deny-by-default auth and SQL rejection on unsafe/ambiguous execution paths)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0028 Shared metadata model relocation baseline (move control-plane SQLAlchemy metadata models into shared domain)

**Decision**  
Relocate canonical metadata SQLAlchemy models from `backend/control_plane/db_models.py` to
`backend/shared_domain/metadata_models.py`, and keep `backend/control_plane/db_models.py` as a
compatibility re-export shim.

**Rationale**  
This avoids future boundary erosion when worker/orchestration services need direct metadata model
access, while preserving backward compatibility for existing control-plane imports.

**Alternatives considered**  
- Keep models under control-plane and duplicate worker-side model definitions (rejected: drift risk).  
- Move models and break all old imports immediately (rejected: unnecessary migration friction).

**Implications**  
- Shared domain becomes the canonical source of metadata table models.
- Existing control-plane code remains stable via explicit re-export compatibility.
- Worker-side orchestration can import metadata models without cross-layer violations.

**Affected files**  
- evidence: backend/shared_domain/metadata_models.py :: class Workspace
- evidence: backend/control_plane/db_models.py :: Compatibility re-export for shared metadata SQLAlchemy models.
- evidence: backend/control_plane/repository.py :: from backend.shared_domain.metadata_models import
- evidence: backend/control_plane/review_repository.py :: from backend.shared_domain.metadata_models import

**Verification impact**  
- evidence: tools/check_boundary_fitness.py :: PASS CHK-BOUNDARY-FITNESS
- evidence: tests/test_control_plane_api.py :: test_workspace_source_run_flow
- evidence: tests/test_review_queue_backend.py :: test_review_queue_create_list_decide

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (metadata persistence and service boundaries)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (compatibility shim preserves existing imports)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0029 Worker orchestration baseline (deterministic queued-run processor and discover-to-catalog pipeline)

**Decision**  
Implement a backend worker runner that deterministically processes queued runs and executes a discover pipeline:
- Add `backend/workers/run_processor.py` for queued-run selection, status transitions (`queued -> running -> succeeded|failed`), and fail-closed error handling.
- Add `backend/workers/service.py` as polling runner service and compose worker container wiring.
- For `discover` runs, process active filesystem sources, upsert stable catalog datasets, ingest bronze artifacts, and generate profiling evidence links.

**Rationale**  
Run orchestration was the key gap between control-plane run creation and real data-catalog outcomes. This baseline closes that gap while preserving deterministic ordering and fail-closed execution.

**Alternatives considered**  
- Keep runs as metadata-only queue records (rejected: no executable pipeline path).  
- Let workers import control-plane repository directly (rejected: boundary drift risk).

**Implications**  
- Queued runs now move through explicit statuses with worker-generated audit events.
- Discover runs produce non-empty dataset catalog entries and output references to artifacts/evidence.
- Compose profiles can include a worker service without exposing additional data-plane ports.

**Affected files**  
- evidence: backend/workers/run_processor.py :: process_next_queued_run
- evidence: backend/workers/service.py :: process_queued_runs_once
- evidence: deploy/docker-compose.yml :: worker:
- evidence: deploy/Dockerfile.worker :: CMD ["python", "-m", "backend.workers.service"]
- evidence: tests/test_worker_runner.py :: test_worker_runner_processes_queued_run_with_status_transition
- evidence: tests/test_pipeline_discover_catalog.py :: test_discover_run_populates_catalog_and_evidence_deterministically

**Verification impact**  
- evidence: tests/test_worker_runner.py :: test_worker_runner_marks_unsupported_run_type_failed
- evidence: tests/test_pipeline_discover_catalog.py :: test_discover_run_populates_catalog_and_evidence_deterministically
- evidence: tests/test_control_plane_api.py :: test_dataset_endpoints_return_expected_contracts

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (reliability, determinism, catalog correctness)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (single-threaded deterministic polling with fail-closed unsupported run/source handling)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0030 Evidence bundle immutability baseline (content-addressed evidence store + authenticated retrieval)

**Decision**  
Introduce an immutable evidence storage layer and authenticated retrieval path:
- Add `backend/shared_domain/evidence_store.py` with content-hash-based bundle IDs, immutable write semantics, and `evidence://<workspace>/<evidence_id>` URIs.
- Wire worker discover profiling outputs to stored evidence bundles.
- Add control-plane endpoint `GET /api/v1/workspaces/{workspace_id}/evidence/{evidence_id}` with role-gated access and audit event emission.

**Rationale**  
Evidence-backed governance requires retrievable and tamper-evident bundles, not ad-hoc file paths. This baseline provides stable retrieval contracts with immutable storage behavior.

**Alternatives considered**  
- Continue raw file-path references only (rejected: weak retrieval contract and weaker immutability guarantees).  
- Store mutable evidence records in-place (rejected: breaks auditability).

**Implications**  
- Worker outputs now include evidence URIs and content hashes.
- Control-plane consumers can retrieve evidence by stable ID with standard error contracts.
- Attempts to overwrite existing evidence IDs with different payloads fail closed.

**Affected files**  
- evidence: backend/shared_domain/evidence_store.py :: store_evidence_bundle
- evidence: backend/shared_domain/evidence_store.py :: load_evidence_bundle
- evidence: backend/control_plane/app.py :: /api/v1/workspaces/{workspace_id}/evidence/{evidence_id}
- evidence: backend/workers/run_processor.py :: content_hash
- evidence: tests/test_evidence_store.py :: test_evidence_store_enforces_immutability_for_existing_bundle_id
- evidence: tests/test_control_plane_api.py :: test_evidence_endpoint_returns_stored_bundle

**Verification impact**  
- evidence: tests/test_evidence_store.py :: test_evidence_store_roundtrip_and_stable_uri
- evidence: tests/test_pipeline_discover_catalog.py :: resolve_evidence_uri
- evidence: tests/test_control_plane_auth.py :: test_control_plane_allows_admin_and_steward_roles_for_mutating_flows

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (governance evidence and auditability)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (immutable writes and authenticated read path)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0031 PII governance automation baseline (high-risk detection to blocking review tasks)

**Decision**  
Wire high-risk PII detections into the discover pipeline so they automatically produce blocking review tasks:
- Extend worker discover processing to evaluate CSV column samples via `backend/workers/pii.py`.
- For high-risk tags (`email`, `phone`, `iban`) above a conservative confidence threshold, create immutable PII evidence bundles.
- Create/open `pii_tag_proposal` records and `security_critical` blocking review tasks idempotently.

**Rationale**  
PII detection existed as a standalone utility, but governance enforcement needed automatic conversion into review queue work to keep publish/query flows safe-by-default.

**Alternatives considered**  
- Keep PII detection as non-persistent heuristic output (rejected: no governance action path).  
- Auto-approve high-confidence tags (rejected: violates human-in-the-loop baseline).

**Implications**  
- Discover runs now emit `pii_blocking_tasks_created` and can open security-critical review backlog.
- Repeat discover runs avoid duplicate open tasks for the same evidence/proposal subject.
- Review queue reflects security risk earlier in the ingest lifecycle.

**Affected files**  
- evidence: backend/workers/run_processor.py :: _create_pii_review_tasks_from_csv
- evidence: backend/workers/run_processor.py :: pii_blocking_tasks_created
- evidence: backend/workers/pii.py :: detect_pii_proposals
- evidence: tests/test_pipeline_pii_review.py :: test_discover_pipeline_creates_blocking_pii_review_tasks

**Verification impact**  
- evidence: tests/test_pipeline_pii_review.py :: test_discover_pipeline_creates_blocking_pii_review_tasks
- evidence: tests/test_review_queue_backend.py :: test_review_queue_create_list_decide
- evidence: tests/test_control_plane_api.py :: test_demo_bootstrap_creates_workspace_and_review_task

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (security-critical review gating)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (thresholded high-risk tags only; blocking tasks require human decisions)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0032 Contract gate hardening baseline (server-side contract reports + fail-closed publish + quality tasks)

**Decision**  
Harden publish gating so contract status is derived from server-side reports and contract failures create actionable quality tasks:
- Add `backend/shared_domain/contract_reports.py` for persisted build contract reports under storage root.
- Update publish endpoint to load contract status from server-side report files (ignore client contract booleans).
- Fail closed (`contract_failure`) when contract report is missing or failing.
- On contract failure, create/deduplicate `contract_failure_proposal` + `quality_critical` blocking review task with immutable evidence.

**Rationale**  
Client-provided `contracts_passed` made publish gating trust-based and bypassable. Server-side reports with fail-closed behavior align publish controls with governance requirements.

**Alternatives considered**  
- Keep client-supplied `contracts_passed` payload (rejected: privilege abuse and inconsistent semantics).  
- Block publish without creating review tasks (rejected: weaker operator actionability).

**Implications**  
- Publish requests now require server-generated contract artifacts for pass conditions.
- Missing contract reports no longer silently pass; they block publish and create actionable review items.
- Existing blocking-task gate still applies after contract gate.

**Affected files**  
- evidence: backend/shared_domain/contract_reports.py :: load_build_contract_report
- evidence: backend/shared_domain/contract_reports.py :: write_build_contract_report
- evidence: backend/control_plane/app.py :: contracts_report_present
- evidence: backend/control_plane/app.py :: ensure_contract_failure_review_task
- evidence: tests/test_contracts_block_publish.py :: test_publish_fails_closed_without_contract_report_and_creates_quality_task
- evidence: tests/test_build_gating.py :: test_gold_publish_blocked_when_blocking_review_task_open

**Verification impact**  
- evidence: tests/test_contracts_block_publish.py :: test_publish_uses_server_side_contract_report_and_allows_pass_case
- evidence: tests/test_contracts_block_publish.py :: test_publish_fails_closed_without_contract_report_and_creates_quality_task
- evidence: tests/test_review_queue_backend.py :: test_review_queue_create_list_decide

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (publish safety and governance gates)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (missing report blocks publish and creates blocking quality task)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0033 Gold publish pointer baseline (server-side pointer writes + auditable rollback)

**Decision**  
Replace publish/rollback stubs with server-side gold pointer management:
- Add `backend/shared_domain/gold_pointer.py` for latest pointer and history persistence.
- Publish endpoint writes pointer only when all gates pass and returns pointer before/after metadata.
- Rollback endpoint resolves target builds from server-side history and updates pointer deterministically.
- Rollback failures return stable `NOT_FOUND` contract responses.

**Rationale**  
Gold promotion required real pointer semantics to support safe release/rollback operations and audit traceability.

**Alternatives considered**  
- Keep publish/rollback as stubs (rejected: no operational recovery path).  
- Allow rollback without history tracking (rejected: weak auditability and ambiguous state recovery).

**Implications**  
- Gold `latest.json` is now authoritative server-side state, not response-only metadata.
- Operators can rollback to a prior published build id using the control-plane endpoint.
- Publish remains blocked when gates fail, leaving the previous pointer untouched.

**Affected files**  
- evidence: backend/shared_domain/gold_pointer.py :: publish_gold_pointer
- evidence: backend/shared_domain/gold_pointer.py :: rollback_gold_pointer
- evidence: backend/control_plane/app.py :: latest_pointer_before
- evidence: backend/control_plane/app.py :: latest_pointer_after
- evidence: tests/test_gold_publish_rollback.py :: test_gold_publish_updates_pointer_and_rollback_restores_previous_build

**Verification impact**  
- evidence: tests/test_gold_publish_rollback.py :: test_gold_rollback_returns_not_found_for_unknown_target
- evidence: tests/test_build_gating.py :: test_gold_publish_blocked_when_blocking_review_task_open
- evidence: tests/test_audit_events.py :: test_create_operations_emit_audit_events

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (rollback and publish safety)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (history-backed rollback and fail-closed not-found behavior)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0034 Gateway DuckDB read-path baseline (published gold views only + external scan denial)

**Decision**  
Upgrade gateway SQL execution to use in-memory DuckDB with published-gold view wiring:
- Gateway executor now uses DuckDB and auto-registers `gold.fact_metrics` (and model alias view) from the currently published gold pointer for the workspace.
- SQL safety denylist now blocks direct file scan functions (`read_csv*`, `read_parquet`, `read_json*`, `glob`, etc.) and other unsafe tokens.
- Gateway query execution now passes `workspace_id` + `storage_root` into executor so reads are bound to server-side published artifacts.

**Rationale**  
The bootstrap SQLite stub could not query real gold artifacts. DuckDB gives immediate local-read capability while keeping a strong read-only security envelope.

**Alternatives considered**  
- Keep SQLite stub and postpone real artifact queries (rejected: blocks end-to-end governed query value).  
- Expose direct file-read SQL functions for flexibility (rejected: weakens non-bypass and least-privilege posture).

**Implications**  
- Published gold metrics become queryable through gateway without exposing data-plane ports.
- Unsafe SQL patterns that could read arbitrary files are denied before execution.
- Existing deny-by-default and ABAC/masking behavior remains enforced around DuckDB results.

**Affected files**  
- evidence: backend/gateway/executor.py :: execute_sql
- evidence: backend/gateway/executor.py :: _prepare_published_gold_views
- evidence: backend/gateway/executor.py :: UNSAFE_SQL_KEYWORDS
- evidence: backend/gateway/app.py :: storage_root=settings.storage_root
- evidence: tests/test_gateway_duckdb_readonly.py :: test_gateway_reads_published_gold_metrics_from_duckdb

**Verification impact**  
- evidence: tests/test_gateway_duckdb_readonly.py :: test_gateway_denies_external_file_scan_functions_in_sql
- evidence: tests/test_gateway_sql_safety.py :: test_gateway_denies_non_read_sql
- evidence: tests/test_gateway_query_execution.py :: test_gateway_executes_sql_and_returns_provenance

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (query security and governed data access)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (published-pointer-only registration + denylisted external scan functions)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0035 Drift governance baseline (schema-drift proposals from discover runs + publish blocking loop)

**Decision**  
Integrate schema drift detection directly into discover-run processing and route drift events into governance workflow:
- Discover pipeline now compares previous vs current schema columns per dataset.
- On drift detection (excluding initial baseline snapshots), worker writes immutable drift evidence and creates/deduplicates `drift_proposal` review items.
- Drift review tasks are blocking `quality_critical`, so publish remains blocked until resolved.

**Rationale**  
Drift detection existed as a utility but was not connected to run orchestration or gating. This closes the loop between data change and governance enforcement.

**Alternatives considered**  
- Keep drift output as logs-only signal (rejected: no enforced remediation path).  
- Treat first-run baseline as drift (rejected: noisy false positives).

**Implications**  
- Discover reruns with schema changes now increase actionable review backlog.
- Publish endpoint naturally blocks via unresolved blocking task gate even when contracts pass.
- Operators get explicit drift evidence URIs tied to review tasks.

**Affected files**  
- evidence: backend/workers/run_processor.py :: _create_drift_review_task_if_needed
- evidence: backend/workers/run_processor.py :: drift_blocking_tasks_created
- evidence: backend/workers/drift.py :: detect_schema_drift
- evidence: tests/test_drift_blocks_publish.py :: test_schema_drift_creates_blocking_task_and_blocks_publish

**Verification impact**  
- evidence: tests/test_drift_blocks_publish.py :: test_schema_drift_creates_blocking_task_and_blocks_publish
- evidence: tests/test_pipeline_discover_catalog.py :: test_discover_run_populates_catalog_and_evidence_deterministically
- evidence: tests/test_build_gating.py :: test_gold_publish_blocked_when_blocking_review_task_open

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (reliability + governance publish safety)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (baseline snapshots excluded; only real schema change opens blocking tasks)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0036 Plugin runtime baseline (entry-point connector loading + worker fallback wiring)

**Decision**  
Add runtime plugin loading for connectors via Python entry points and wire it into discover-run processing:
- Add `backend/shared_domain/plugin_loader.py` for entry-point discovery, duplicate-name protection, and callable validation.
- Worker discover loop now supports non-filesystem `source_type` via loaded connector plugins.
- Plugin discovery rows are normalized into the same `DiscoveredFile` shape used by built-in connectors.

**Rationale**  
Connector extensibility was documented but not executable at runtime. Entry-point loading provides an OSS-friendly extension path without modifying core code for every new connector.

**Alternatives considered**  
- Keep plugin docs only with no runtime loader (rejected: contributor path blocked).  
- Hardcode connector registry in core code (rejected: poorer ecosystem scalability).

**Implications**  
- New connector types can be added by installing packages exposing `schemapilot.connectors` entry points.
- Misconfigured/non-callable plugin definitions fail closed during loading.
- Worker pipelines can process plugin-backed source types while preserving existing filesystem behavior.

**Affected files**  
- evidence: backend/shared_domain/plugin_loader.py :: load_connector_plugins
- evidence: backend/workers/run_processor.py :: _discover_files_via_plugin
- evidence: tests/test_plugin_loader.py :: test_plugin_loader_rejects_duplicate_entry_point_names
- evidence: tests/test_worker_runner.py :: test_worker_runner_uses_connector_plugin_for_non_filesystem_source

**Verification impact**  
- evidence: tests/test_plugin_loader.py :: test_connector_plugin_loader_requires_callable_plugins
- evidence: tests/test_worker_runner.py :: test_worker_runner_uses_connector_plugin_for_non_filesystem_source
- evidence: tools/check_boundary_fitness.py :: PASS CHK-BOUNDARY-FITNESS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (connector discovery and external I/O)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (unsupported source types still fail closed without plugin)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0037 KPI extraction baseline (runtime-derived weekly KPI snapshot generation)

**Decision**  
Add an automated KPI extraction tool that derives weekly operational KPIs from metadata/audit state:
- Add `tools/kpi_extract.py` to compute runtime KPIs (TTFSA proxy, run success rate, policy denials, deterministic rebuild rate, publish count, blocking review backlog).
- Persist extracted snapshots under `runtime/kpi/extracted/<week>.json` and update `runtime/kpi/latest_extracted.json`.
- Keep unavailable metrics explicit via `notes` entries instead of silent defaults.

**Rationale**  
Manual KPI entry alone is brittle for tracking regressions. Runtime extraction gives consistent, reproducible telemetry for weekly review.

**Alternatives considered**  
- Keep only manual `kpi_tracker.py` entry workflow (rejected: weak observability and drift detection).  
- Hard fail when a KPI source is missing (rejected: too brittle for early-stage installs).

**Implications**  
- Operators can generate KPI snapshots from actual system state without manual counting.
- KPI outputs now separate measured values from unavailable metrics with explicit notes.
- Determinism health for rebuilds can be tracked from run input/output references.

**Affected files**  
- evidence: tools/kpi_extract.py :: extract_kpis
- evidence: tools/kpi_extract.py :: write_kpi_extract
- evidence: tests/test_kpi_extract.py :: test_kpi_extract_derives_runtime_metrics_from_metadata

**Verification impact**  
- evidence: tests/test_kpi_extract.py :: test_kpi_extract_derives_runtime_metrics_from_metadata
- evidence: tests/test_kpi_tracker.py :: test_kpi_tracker_writes_weekly_and_latest_reports
- evidence: tools/check_tooling_baseline.py :: PASS CHK-TOOLING-BASELINE

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: NO  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (explicit null + notes for unavailable KPIs)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0038 Completion baseline for deploy/community/UI thin slice (compose smoke validated, OSS templates added, UI kept intentionally lightweight)

**Decision**  
Close the remaining task-board items using a conservative adoption-first finish:
- Mark runnable compose verification complete using an actual local smoke cycle (`up --build`, health checks, auth fail-closed check, `down`).
- Add OSS contributor fundamentals (`CONTRIBUTING.md`, issue templates, PR template) to reduce maintainer friction.
- Keep the UI card intentionally thin while adding focused behavioral coverage instead of expanding UI surface area.

**Rationale**  
The project objective is backend governance reliability and installability. This closure pattern completes execution commitments without diluting effort into non-critical UI complexity.

**Alternatives considered**  
- Keep PR-005 open until repeated clean-room compose runs across machines (rejected: defers closure despite successful runnable evidence).  
- Expand UI scope significantly before closing PR-018 (rejected: conflicts with current priority and user direction).

**Implications**  
- Deploy path now has concrete smoke evidence beyond static config validation.
- Contributor onboarding path is explicit and standardized in-repo.
- UI remains minimal by design, with tests guarding existing core interactions.

**Affected files**  
- evidence: deploy/docker-compose.yml :: profiles: ["starter", "team", "enterprise"]
- evidence: CONTRIBUTING.md :: Required checks before opening a PR
- evidence: .github/ISSUE_TEMPLATE/bug_report.md :: ## Reproduction steps
- evidence: .github/pull_request_template.md :: ## Evidence updates
- evidence: ui/src/App.test.tsx :: submits review decisions and recommendation requests
- evidence: TASKLIST.md :: [x] PR-005 `runnable-compose-profile-team`

**Verification impact**  
- evidence: tests/test_deploy_no_bypass_ports.py :: test_compose_does_not_publish_direct_query_engine_or_index_ports
- evidence: tests/test_port_conventions.py :: test_port_conventions_are_consistent
- evidence: ui/src/App.test.tsx :: submits review decisions and recommendation requests for selected workspace
- evidence: runtime checks :: compose `starter` profile health/auth smoke

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (deployment and contributor workflow)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (thin UI retained; hardening defaults unchanged)  
- Safe to decide: YES  
- Conservative baseline: YES

