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
- D-0039 Post-PR018 execution backlog baseline (S0-first, no timeline planning, minimal UI scope)
- D-0040 OIDC JWT verification and deploy no-bypass enforcement baseline (shared auth path, strict startup guards, and static deploy checks)
- D-0041 Audit fail-closed enforcement baseline (gateway/control-plane deny on audit write failures with explicit observability)
- D-0042 Gateway workspace isolation baseline (deny cross-workspace dataset access for AI SQL and retrieval paths)
- D-0043 Gateway actor throttling baseline (per-actor rate and concurrency deny controls with fail-closed decisions)
- D-0044 Migration-state startup enforcement baseline (non-local bind requires expected alembic revision; local bind retains bootstrap autocreate)
- D-0045 Backup/restore toolchain baseline (explicit backup + restore utilities with drill integration and regression tests)
- D-0046 Strict ingest completeness baseline (team/enterprise default strict mode with fail-closed evidence and blocking quality tasks)
- D-0047 Retention/deletion governance baseline (retention policy + purge controls and separation-of-duties deletion workflow)
- D-0048 Provenance and policy lifecycle baseline (provenance v1 contract, audit export, policy-pack approval/rollback controls)
- D-0049 Plugin security and contract gate baseline (plugin allowlist isolation + OpenAPI compatibility + golden-path regression gate)
- D-0050 Team query engine upgrade baseline (gateway trino adapter with duckdb fallback and docs/runbook finalization)
- D-0051 Semantic manifest foundation baseline (schema validator + review-gated control-plane lifecycle + rollback)
- D-0052 Semantic bootstrap worker-run baseline (deterministic candidate generation with evidence-backed review artifacts)
- D-0053 Gateway semantic-bound AI query baseline (semantic resolver + AI-only semantic-query enforcement)
- D-0054 Gold template pack baseline (invoices/crm/support packs + deterministic CLI bundle generation)
- D-0055 Monotonic ULID generation baseline (per-process ordered ULIDs for deterministic queue execution)
- D-0056 Document connector extraction baseline (PDF/EML/MBOX discovery + confidence-scored evidence)
- D-0057 OpenSearch retrieval module baseline (optional gateway backend + internal-only indexing helpers)
- D-0058 Qdrant vector retrieval baseline (optional embeddings provider + internal-only vector index module)
- D-0059 Retrieval ABAC parity baseline (metadata-bound row filters + snippet masking across retrieval backends)
- D-0060 AI/ops extension baseline (optional AI service + policy simulation + catalog/scheduling/fairness + audit sinks + secrets + Helm hardening)
- D-0061 Completion baseline for NW-0026..NW-0034 and AI track (demo generator, docs wave, pack registry, Trino hardening, compaction, anomaly/ERv2, locale parsing, typed SDK)
- D-0062 Config/doctor operability baseline (`V2-0005` strict config schema and `V2-0003` deterministic preflight diagnostics)
- D-0063 Audit outbox delivery baseline (`V2-0001` durable sink dispatch decoupling with fail-closed local audit writes)
- D-0064 Operator diagnostics baseline (`V2-0002`, `V2-0004`, `V2-0032`: run-step DAG visibility + redacted support bundle + workspace analytics CLI)
- D-0065 Completion baseline for remaining `TASKLIST_NEXT_V2` items (`V2-0006`..`V2-0031`)

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

---

## D-0039 Post-PR018 execution backlog baseline (S0-first, no timeline planning, minimal UI scope)

**Decision**  
Replace the completed PR-001..PR-018 board with a strict next-step execution queue:
- Preserve completed baseline as reference, then execute PR-019 onward in explicit order.
- Prioritize S0 security/governance tasks before scaling or polish work.
- Keep UI scope minimal and blocker-only while backend, policy, and deploy hardening continue.
- Avoid timeline/date planning in the task board; execution is order-driven.

**Rationale**  
The next phase needs a clear production-hardening sequence without reopening already-finished work or diluting effort into non-critical UI expansion.

**Alternatives considered**  
- Keep legacy board unchanged and track new work in ad-hoc notes (rejected: unclear execution order and weaker traceability).  
- Add roadmap timelines/dates into `TASKLIST.md` (rejected: user asked for no timeline planning).

**Implications**  
- Contributors have a single ordered queue for remaining work.
- S0 gatekeeping (authn, no-bypass, audit fail-closed, workspace isolation) becomes explicit.
- UI remains intentionally thin unless a core-flow blocker appears.

**Affected files**  
- evidence: TASKLIST.md :: # SchemaPilot Execution Board (Post PR-018)
- evidence: TASKLIST.md :: ## Active Queue (Execute In Order)
- evidence: TASKLIST.md :: ## Backlog (After PR-030)

**Verification impact**  
- evidence: tools/verify_manifest.py :: PASS
- evidence: tools/check_tooling_baseline.py :: PASS CHK-TOOLING-BASELINE

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (execution sequencing for security/reliability work)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (S0-first and fail-closed defaults preserved)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0040 OIDC JWT verification and deploy no-bypass enforcement baseline (shared auth path, strict startup guards, and static deploy checks)

**Decision**  
Implement the first post-PR018 S0 lane by shipping:
- shared `oidc_jwt` authentication mode with JWKS-backed JWT verification in `shared_domain/auth.py`,
- unified gateway/control-plane auth resolution through shared auth helpers,
- strict startup guards for trusted-proxy OIDC usage on non-local bind,
- static deploy no-bypass checker wired into tooling baseline.

**Rationale**  
Production-ready auth and no-bypass enforcement are immediate critical-path blockers. Shipping them first reduces the highest-risk security gaps while preserving existing local/trusted-proxy compatibility.

**Alternatives considered**  
- Keep gateway-specific auth logic and add JWT there only (rejected: divergence risk between control plane and gateway).  
- Defer deploy no-bypass checks to release-only scripts (rejected: weaker day-to-day regression protection).

**Implications**  
- `auth_mode=oidc_jwt` is now available with fail-closed verification semantics.
- Existing `auth_mode=oidc` behavior is preserved as trusted-proxy mode (alias), while non-local usage requires explicit `oidc_trusted_proxy=true`.
- Deploy artifact checks now fail fast if direct engine/index ports are exposed.

**Affected files**  
- evidence: backend/shared_domain/auth.py :: authenticated_actor_from_oidc_jwt
- evidence: backend/shared_domain/config.py :: def validate(self)
- evidence: backend/gateway/app.py :: create_gateway_app
- evidence: tools/check_no_bypass_ports.py :: validate_no_bypass_ports
- evidence: tools/check_tooling_baseline.py :: tools/check_no_bypass_ports.py
- evidence: tests/test_gateway_oidc_jwt_auth.py :: test_gateway_oidc_jwt_allows_valid_token
- evidence: tests/test_control_plane_oidc_jwt_auth.py :: test_control_plane_oidc_jwt_allows_platform_admin
- evidence: tests/test_startup_security.py :: test_gateway_fails_on_non_local_trusted_proxy_without_explicit_trust

**Verification impact**  
- evidence: tests/test_gateway_oidc_auth.py :: test_gateway_oidc_allows_valid_claims_mapping
- evidence: tests/test_gateway_oidc_jwt_auth.py :: test_gateway_oidc_jwt_denies_invalid_signature
- evidence: tests/test_control_plane_oidc_jwt_auth.py :: test_control_plane_oidc_jwt_denies_insufficient_role
- evidence: tests/test_startup_security.py :: test_control_plane_fails_on_non_local_trusted_proxy_without_explicit_trust
- evidence: tests/test_no_bypass_deploy_artifacts.py :: test_deploy_artifacts_do_not_expose_bypass_ports
- evidence: tools/check_no_bypass_ports.py :: PASS CHK-NO-BYPASS-PORTS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (authentication and deployment boundary controls)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (local mode remains available; trusted-proxy requires explicit opt-in)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0041 Audit fail-closed enforcement baseline (gateway/control-plane deny on audit write failures with explicit observability)

**Decision**  
Enforce explicit fail-closed behavior when audit writes fail:
- gateway access-decision persistence now raises a policy denial with `reason=audit_unavailable` if audit commit fails,
- control-plane audit append is wrapped and converted to policy denial on failures,
- audit write failures are counted via `schemapilot_audit_write_failures_total`.

**Rationale**  
Governed operation claims are not credible if critical flows can continue without durable audit evidence.

**Alternatives considered**  
- Return generic 500 without explicit deny semantics (rejected: unclear policy behavior).  
- Fail open and only log errors (rejected: violates governance guarantees).

**Implications**  
- Critical request paths are blocked when audit storage is unavailable.
- Failures are visible in metrics and structured logs for incident triage.
- Existing happy-path behavior remains unchanged when audit storage is healthy.

**Affected files**  
- evidence: backend/gateway/app.py :: _record_access_decision
- evidence: backend/control_plane/app.py :: def append_audit_event(
- evidence: backend/shared_domain/observability.py :: schemapilot_audit_write_failures_total
- evidence: tests/test_audit_fail_closed.py :: test_gateway_denies_query_when_audit_write_fails
- evidence: tests/test_audit_fail_closed.py :: test_control_plane_denies_mutation_when_audit_write_fails

**Verification impact**  
- evidence: tests/test_audit_fail_closed.py :: test_gateway_denies_query_when_audit_write_fails
- evidence: tests/test_audit_fail_closed.py :: test_control_plane_denies_mutation_when_audit_write_fails
- evidence: tests/test_gateway_audit.py :: test_gateway_query_writes_audit_and_access_decision
- evidence: tests/test_control_plane_auth.py :: test_control_plane_allows_admin_and_steward_roles_for_mutating_flows

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (query/mutation authorization and auditable operations)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (deny on audit failure)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0042 Gateway workspace isolation baseline (deny cross-workspace dataset access for AI SQL and retrieval paths)

**Decision**  
Enforce explicit workspace isolation checks in gateway AI access paths:
- SQL query path now denies when requested `dataset_id` is known but belongs to another workspace.
- Retrieval path now denies when actor dataset entitlements include dataset IDs known to other workspaces.
- Denials use `reason=dataset_workspace_mismatch` and are audited.

**Rationale**  
Cross-workspace bleed is a critical policy violation. Workspace boundary checks must be explicit even when IDs are guessed or entitlements are mis-scoped.

**Alternatives considered**  
- Rely only on actor `allowed_dataset_ids` checks (rejected: does not enforce workspace ownership).  
- Require dataset existence for every request and deny unknown IDs globally (rejected for now to avoid breaking existing local demo/default flows).

**Implications**  
- Known foreign datasets cannot be queried or retrieved across workspace boundaries.
- Unknown dataset IDs preserve current behavior for compatibility, while known cross-workspace IDs are blocked.
- Access decision evidence now captures cross-workspace mismatch denials.

**Affected files**  
- evidence: backend/gateway/app.py :: _dataset_belongs_to_other_workspace
- evidence: backend/gateway/app.py :: dataset_workspace_mismatch
- evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_query_denies_ai_dataset_from_other_workspace
- evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_retrieve_denies_cross_workspace_dataset_entitlement

**Verification impact**  
- evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_query_denies_ai_dataset_from_other_workspace
- evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_retrieve_denies_cross_workspace_dataset_entitlement
- evidence: tests/test_gateway_dataset_entitlements.py :: test_gateway_denies_ai_query_for_unentitled_dataset
- evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_for_allowlisted_ai_identity

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (authorization boundary checks in gateway)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (deny known foreign datasets, keep compatibility for unknown IDs)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0043 Gateway actor throttling baseline (per-actor rate and concurrency deny controls with fail-closed decisions)

**Decision**  
Add in-memory per-actor throttling controls for gateway query and retrieval paths:
- per-minute request caps (`rate_limit_exceeded`),
- per-actor in-flight caps (`concurrency_limit_exceeded`),
- fail-closed denial behavior with policy/audit records.

**Rationale**  
Operational safety needs explicit throttling to reduce runaway query load and abusive request patterns.

**Alternatives considered**  
- Defer throttling until external API gateway integration (rejected: leaves core service unprotected).  
- Global process-wide limits only (rejected: weaker tenant/actor isolation).

**Implications**  
- Gateway can deny requests before execution when actor limits are exceeded.
- Denials are surfaced via existing policy denial/audit paths.
- Limits are configurable through environment variables with safe defaults.

**Affected files**  
- evidence: backend/shared_domain/rate_limit.py :: InMemoryActorRateLimiter
- evidence: backend/gateway/app.py :: SCHEMAPILOT_GATEWAY_MAX_REQUESTS_PER_MINUTE
- evidence: backend/gateway/app.py :: SCHEMAPILOT_GATEWAY_MAX_CONCURRENT_PER_ACTOR
- evidence: tests/test_gateway_rate_limits.py :: test_gateway_denies_when_rate_limit_exceeded
- evidence: tests/test_gateway_rate_limits.py :: test_gateway_denies_when_concurrency_limit_exceeded

**Verification impact**  
- evidence: tests/test_gateway_rate_limits.py :: test_gateway_denies_when_rate_limit_exceeded
- evidence: tests/test_gateway_rate_limits.py :: test_gateway_denies_when_concurrency_limit_exceeded
- evidence: tests/test_gateway_query_execution.py :: test_gateway_executes_sql_and_returns_provenance
- evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_for_allowlisted_ai_identity

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (gateway availability and policy deny paths)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (deny on limit breaches)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0044 Migration-state startup enforcement baseline (non-local bind requires expected alembic revision; local bind retains bootstrap autocreate)

**Decision**  
Introduce explicit migration-state startup checks:
- non-local binds require `alembic_version` table and expected revision match (`SCHEMAPILOT_REQUIRED_DB_REVISION`, default `0001_initial_schema`),
- local bind retains bootstrap `create_all` behavior for dev/test workflows,
- add CLI migration helpers (`migrate-up`, `migrate-status`) and regression tests.

**Rationale**  
Production startup should not silently create schema state. Non-local deployments must prove migration compatibility before serving requests.

**Alternatives considered**  
- Keep unconditional `create_all` on startup everywhere (rejected: unsafe for non-local/prod paths).  
- Require migrations even for local bind (rejected: unnecessary friction for fast local onboarding and tests).

**Implications**  
- Non-local misconfigured DBs fail fast at startup with explicit configuration errors.
- Local development remains simple and backward compatible.
- CLI now includes explicit migration commands for operator workflows.

**Affected files**  
- evidence: backend/shared_domain/db.py :: prepare_database
- evidence: backend/shared_domain/db.py :: ensure_required_revision
- evidence: backend/control_plane/app.py :: prepare_database(settings)
- evidence: backend/gateway/app.py :: prepare_database(settings)
- evidence: cli/schemapilot_cli/main.py :: @app.command("migrate-up")
- evidence: cli/schemapilot_cli/main.py :: @app.command("migrate-status")
- evidence: tests/test_migrations_enforced.py :: test_gateway_non_local_requires_migration_state
- evidence: tests/test_cli_commands.py :: test_migrate_up_invokes_alembic_upgrade_head

**Verification impact**  
- evidence: tests/test_migrations_enforced.py :: test_control_plane_non_local_requires_migration_state
- evidence: tests/test_migrations_enforced.py :: test_non_local_allows_expected_revision_present
- evidence: tests/test_migrations_enforced.py :: test_non_local_denies_revision_mismatch
- evidence: tests/test_cli_commands.py :: test_migrate_status_invokes_alembic_current
- evidence: tests/test_startup_security.py :: test_gateway_fails_on_non_local_without_auth

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (service startup safety in non-local environments)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (strict non-local checks + local bootstrap compatibility)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0045 Backup/restore toolchain baseline (explicit backup + restore utilities with drill integration and regression tests)

**Decision**  
Split backup and restore behavior into dedicated tools and wire the drill through those utilities:
- add `tools/backup.py` for metadata+storage snapshot creation with manifest output,
- add `tools/restore.py` for deterministic restore from backup snapshots,
- update `tools/backup_restore_drill.py` to call these tools directly,
- add regression tests for backup/restore round-trip and drill pass behavior.

**Rationale**  
Operator-facing backup/restore workflows are clearer and more reusable when exposed as explicit tools instead of only being embedded inside a single drill script.

**Alternatives considered**  
- Keep backup/restore logic only in drill script (rejected: weak operator ergonomics and lower testability).  
- Add external backup dependencies immediately (rejected: unnecessary complexity for current single-node baseline).

**Implications**  
- Backup and restore can be invoked independently in runbooks and automation.
- Drill remains the acceptance check while sharing production-like tool paths.
- Report/manifests become explicit artifacts for troubleshooting.

**Affected files**  
- evidence: tools/backup.py :: backup_runtime_state
- evidence: tools/restore.py :: restore_runtime_state
- evidence: tools/backup_restore_drill.py :: backup_runtime_state(
- evidence: tests/test_backup_restore_tools.py :: test_backup_and_restore_tools_roundtrip
- evidence: tests/test_backup_restore_drill.py :: test_backup_restore_drill_passes

**Verification impact**  
- evidence: tests/test_backup_restore_tools.py :: test_backup_and_restore_tools_roundtrip
- evidence: tests/test_backup_restore_drill.py :: test_backup_restore_drill_passes
- evidence: tools/backup_restore_drill.py :: PASS CHK-BACKUP-RESTORE
- evidence: tools/check_tooling_baseline.py :: tools/backup_restore_drill.py

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (data recovery and operational resilience)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (filesystem+sqlite toolchain with explicit manifests)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0046 Strict ingest completeness baseline (team/enterprise default strict mode with fail-closed evidence and blocking quality tasks)

**Decision**  
Enforce strict ingest completeness as the default for Team/Enterprise worker profiles:
- unreadable/unparseable discovered items fail the run,
- completeness failures are written to immutable evidence bundles,
- blocking quality-critical review tasks are created for strict ingest failures.

**Rationale**  
Silent partial ingest is a high-risk correctness failure. Strict mode with evidence-backed failures preserves trust in downstream catalog/build/query surfaces.

**Alternatives considered**  
- Continue best-effort ingest with warnings only (rejected: allows silent data loss).  
- Make strict mode always-on for all profiles (rejected for now to preserve starter/local flexibility).

**Implications**  
- Team/Enterprise workers default to fail-closed ingest behavior.
- Failure evidence becomes first-class and review-gated.
- Publish remains blocked while strict completeness issues are open.

**Affected files**  
- evidence: backend/workers/run_processor.py :: StrictIngestCompletenessError
- evidence: backend/workers/service.py :: strict_ingest
- evidence: tests/test_strict_ingest_completeness.py :: test_strict_ingest_fails_closed_and_creates_blocking_task
- evidence: tests/test_worker_runner.py :: test_worker_service_config_defaults_strict_ingest_for_team_profile

**Verification impact**  
- evidence: tests/test_strict_ingest_completeness.py :: test_non_strict_ingest_records_warning_and_continues
- evidence: tests/test_worker_runner.py :: test_worker_service_config_allows_explicit_non_strict_override
- evidence: tools/check_tooling_baseline.py :: run([sys.executable, "tools/e2e_golden_path.py", "--smoke"], cwd=root)

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (ingest correctness and fail-closed governance)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (strict default for Team/Enterprise)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0047 Retention/deletion governance baseline (retention policy + purge controls and separation-of-duties deletion workflow)

**Decision**  
Implement retention and deletion governance with explicit safety gates:
- retention policy and purge execution are workspace-scoped and disabled-by-default until configured,
- purge requires explicit enablement, legal-hold clear state, and immutable evidence output,
- deletion flow enforces request/approve/execute state transitions with requester non-self-approval and legal-hold server-side truth.

**Rationale**  
Data lifecycle controls must be auditable and fail-closed before claiming enterprise readiness.

**Alternatives considered**  
- Keep deletion/retention as doc-only stubs (rejected: insufficient operational confidence).  
- Allow direct one-step deletion execution (rejected: violates separation of duties).

**Implications**  
- Operators must explicitly enable retention purge and deletion execution features.
- Governance flows now produce auditable/evidence-backed artifacts.
- Control-plane endpoints deny unsafe lifecycle actions by default.

**Affected files**  
- evidence: backend/control_plane/retention.py :: execute_retention_purge
- evidence: backend/shared_domain/purge.py :: purge_workspace_artifacts
- evidence: backend/control_plane/deletion.py :: approve_deletion_request
- evidence: backend/control_plane/deletion.py :: execute_deletion_request
- evidence: tests/test_retention_purge_fail_closed.py :: test_retention_purge_requires_explicit_purge_path_config
- evidence: tests/test_deletion_separation_of_duties.py :: test_deletion_workflow_enforces_separation_of_duties

**Verification impact**  
- evidence: tests/test_deletion_separation_of_duties.py :: test_legal_hold_is_server_side_truth_for_deletions
- evidence: tests/test_retention_purge_fail_closed.py :: test_retention_purge_succeeds_with_evidence_and_file_cleanup
- evidence: tools/backup_restore_drill.py :: PASS CHK-BACKUP-RESTORE

**DSC summary**  
- Externally constrained: YES (retention/legal requirements vary by org)  
- Critical flow impacted: YES (governance lifecycle and deletion safety)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (features disabled unless explicitly configured)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0048 Provenance and policy lifecycle baseline (provenance v1 contract, audit export, policy-pack approval/rollback controls)

**Decision**  
Ship stable governance contracts for runtime decisions:
- versioned provenance payload builder (`provenance_version=1`) with required fields and fail-closed gateway handling,
- deterministic audit export utility for append-only audit/access-decision rows,
- policy-pack change requests with review-task gating, apply/rollback semantics, and effective policy-pack visibility in gateway.

**Rationale**  
Governance confidence depends on stable contracts and auditable policy lifecycle transitions.

**Alternatives considered**  
- Keep ad-hoc provenance dictionaries with best-effort fields (rejected: contract drift risk).  
- Apply policy-pack changes directly without staged approval (rejected: weak governance controls).

**Implications**  
- Provenance schema is now a test-enforced compatibility surface.
- Policy-pack changes are review-gated and rollbackable.
- Gateway audit/provenance now includes effective policy-pack context.

**Affected files**  
- evidence: backend/shared_domain/provenance.py :: build_provenance_v1
- evidence: tools/audit_export.py :: export_audit_jsonl
- evidence: backend/control_plane/policy_pack_service.py :: request_policy_pack_change
- evidence: backend/control_plane/policy_pack_service.py :: rollback_policy_pack
- evidence: tests/test_provenance_schema_stability.py :: test_gateway_query_provenance_v1_fields_are_stable
- evidence: tests/test_policy_pack_change_gating.py :: test_policy_pack_change_is_approval_gated_and_rollbackable

**Verification impact**  
- evidence: tests/test_provenance_schema_stability.py :: test_audit_export_jsonl_is_deterministic
- evidence: tests/test_policy_pack_change_gating.py :: test_policy_pack_change_is_approval_gated_and_rollbackable
- evidence: tools/check_openapi_compat.py :: PASS CHK-CONTRACT-COMPAT

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (policy decisions, provenance, audit contract stability)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (deny on provenance contract failure)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0049 Plugin security and contract gate baseline (plugin allowlist isolation + OpenAPI compatibility + golden-path regression gate)

**Decision**  
Harden extension and compatibility surfaces:
- require explicit connector plugin allowlist and isolated subprocess plugin execution,
- add committed OpenAPI baseline artifacts with compatibility checker gate,
- add deterministic golden-path e2e smoke and MessyBench regression threshold mode to quality/release gates.

**Rationale**  
Plugin extensibility and API evolution are major regression vectors; they need first-class fail-closed enforcement in normal CI/release flow.

**Alternatives considered**  
- Keep plugin runtime permissive and rely on docs (rejected: supply-chain risk).  
- Run OpenAPI/e2e checks only manually (rejected: drift risk).

**Implications**  
- Unknown/unallowlisted plugin source types are denied.
- API contract drift is automatically detected against committed baselines.
- End-to-end regressions are caught earlier with deterministic harnesses.

**Affected files**  
- evidence: backend/shared_domain/plugin_loader.py :: configured_plugin_allowlist
- evidence: backend/workers/connectors/plugin_runner.py :: _run_plugin_in_subprocess
- evidence: tools/check_openapi_compat.py :: main
- evidence: tools/e2e_golden_path.py :: run_golden_path
- evidence: tools/messybench_harness.py :: --regression
- evidence: tests/test_plugin_allowlist.py :: test_source_connect_denied_when_plugin_not_allowlisted
- evidence: tests/test_openapi_contracts.py :: test_openapi_contract_baselines_are_compatible
- evidence: tests/test_e2e_golden_path_smoke.py :: test_e2e_golden_path_smoke

**Verification impact**  
- evidence: tools/check_tooling_baseline.py :: tools/check_openapi_compat.py
- evidence: tools/check_tooling_baseline.py :: run([sys.executable, "tools/e2e_golden_path.py", "--smoke"], cwd=root)
- evidence: tools/release_gate.py :: RG-007
- evidence: tools/release_gate.py :: RG-008

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (plugin supply-chain safety, API compatibility, release regression control)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (deny-by-default plugin loading and strict compatibility checks)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0050 Team query engine upgrade baseline (gateway trino adapter with duckdb fallback and docs/runbook finalization)

**Decision**  
Enable progressive query-engine selection in gateway:
- keep `duckdb` as default query engine,
- add `trino` adapter path configured by explicit environment settings,
- preserve SQL safety checks and no-bypass deployment posture across both modes,
- finalize runbook/readme/doc index updates for implemented security/operability defaults while keeping UI intentionally minimal.

**Rationale**  
Team profile readiness requires a scalable engine path without weakening existing secure defaults.

**Alternatives considered**  
- Replace DuckDB entirely with Trino (rejected: reduces starter/local simplicity).  
- Keep Trino as a future-only stub (rejected: blocks team upgrade validation).

**Implications**  
- Gateway can query through Trino when configured while retaining DuckDB fallback.
- Deploy remains gateway-first with no direct engine exposure.
- Operator docs now reflect implemented auth, ingest, plugin, and regression controls.

**Affected files**  
- evidence: backend/shared_domain/config.py :: SUPPORTED_QUERY_ENGINES
- evidence: backend/gateway/executor.py :: execute_sql
- evidence: backend/gateway/executor_trino.py :: execute_sql_trino
- evidence: tests/test_gateway_trino_adapter.py :: test_gateway_query_can_use_trino_engine_path
- evidence: README.md :: Implemented Safe Defaults (Current)
- evidence: spec/12_RUNBOOK.md :: OIDC-first enterprise integration
- evidence: docs/runbook/README.md :: Operator Runbook Index

**Verification impact**  
- evidence: tests/test_gateway_trino_adapter.py :: test_execute_sql_uses_trino_adapter_with_pagination
- evidence: tests/test_gateway_sql_safety.py :: test_gateway_denies_unsafe_sql_keyword_in_select_path
- evidence: tools/check_no_bypass_ports.py :: PASS CHK-NO-BYPASS-PORTS
- evidence: tools/check_tooling_baseline.py :: PASS CHK-TOOLING-BASELINE

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (query execution and deployment security posture)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (duckdb default, trino opt-in)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0051 Semantic manifest foundation baseline (schema validator + review-gated control-plane lifecycle + rollback)

**Decision**  
Introduce the first semantic-layer governance slice:
- shared semantic manifest schema validation and deterministic checksum utilities,
- semantic manifest validation tool with CI/tooling-baseline wiring,
- control-plane lifecycle for semantic manifests (change request, review-gated decision, publish, rollback),
- deny-by-default behavior for invalid semantic manifests and role-guarded mutation endpoints.

**Rationale**  
Semantic definitions are required to safely scale AI-ready querying. Treating semantic artifacts as governed, review-backed, rollbackable state mirrors existing policy-pack safety patterns.

**Alternatives considered**  
- Store semantic manifests as free-form payloads without validation (rejected: weak contract guarantees).  
- Allow direct semantic manifest publish without review queue (rejected: bypasses governance controls).

**Implications**  
- Semantic manifest becomes an explicit control-plane contract surface.
- Invalid manifests are denied before persistence.
- Lifecycle is auditable and compatible with existing role model and review queue.

**Affected files**  
- evidence: backend/shared_domain/semantic.py :: validate_semantic_manifest
- evidence: backend/shared_domain/semantic.py :: semantic_manifest_checksum
- evidence: tools/semantic_validate.py :: PASS semantic manifest validation
- evidence: backend/control_plane/semantic_manifest_service.py :: request_semantic_manifest_change
- evidence: backend/control_plane/semantic_manifest_service.py :: rollback_semantic_manifest
- evidence: backend/control_plane/app.py :: /api/v1/workspaces/{workspace_id}/semantic-manifest
- evidence: tests/test_semantic_schema.py :: test_validate_semantic_manifest_normalizes_and_hashes_deterministically
- evidence: tests/test_semantic_manifest_lifecycle.py :: test_semantic_manifest_is_approval_gated_and_rollbackable

**Verification impact**  
- evidence: tests/test_semantic_schema.py :: test_validate_semantic_manifest_rejects_workspace_mismatch
- evidence: tests/test_semantic_manifest_lifecycle.py :: test_semantic_manifest_change_requires_steward_or_admin_role
- evidence: tests/test_semantic_validate_tool.py :: test_semantic_validate_tool_passes_for_example_manifest
- evidence: tools/check_tooling_baseline.py :: tools/semantic_validate.py

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (governed semantic contract lifecycle)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (deny invalid manifests; review-gated publish)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0052 Semantic bootstrap worker-run baseline (deterministic candidate generation with evidence-backed review artifacts)

**Decision**  
Add a deterministic `semantic_bootstrap` worker run type that:
- builds a semantic manifest candidate from catalog profiling evidence,
- stores immutable evidence bundles for the candidate output,
- creates/updates blocking `semantic_manifest_change_proposal` review artifacts,
- fails closed when no catalog datasets are available.

**Rationale**  
The next-wave semantic lifecycle needs a worker-produced bootstrap path so teams can generate a governed starting manifest from discovered data instead of manual payload authoring.

**Alternatives considered**  
- Keep semantic bootstrap as a manual control-plane-only flow (rejected: high onboarding friction).  
- Let workers import control-plane lifecycle services directly (rejected: boundary fitness violation).

**Implications**  
- Worker orchestration now supports `discover` and `semantic_bootstrap` run types.
- Semantic bootstrap output is deterministic for unchanged catalog evidence and reuses existing open blocking tasks on reruns.
- Empty catalog bootstrap attempts fail with explicit run failure evidence.

**Affected files**  
- evidence: backend/workers/run_processor.py :: _process_semantic_bootstrap_run
- evidence: backend/workers/run_processor.py :: if run.run_type == "semantic_bootstrap":
- evidence: backend/workers/semantic_builder.py :: build_semantic_manifest_candidate
- evidence: tests/test_worker_runner.py :: test_worker_runner_processes_semantic_bootstrap_run
- evidence: tests/test_worker_runner.py :: test_worker_runner_fails_semantic_bootstrap_without_catalog

**Verification impact**  
- evidence: tests/test_worker_runner.py :: test_worker_runner_processes_semantic_bootstrap_run
- evidence: tests/test_worker_runner.py :: test_worker_runner_fails_semantic_bootstrap_without_catalog
- evidence: tests/test_worker_runner.py :: test_worker_runner_processes_queued_run_with_status_transition
- evidence: tests/test_semantic_schema.py :: test_validate_semantic_manifest_normalizes_and_hashes_deterministically

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (governed semantic artifact generation path)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (fail on missing catalog evidence)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0053 Gateway semantic-bound AI query baseline (semantic resolver + AI-only semantic-query enforcement)

**Decision**  
Enforce semantic-bound query execution for AI identities in the gateway:
- AI requests to `/api/v1/gateway/query` must provide `semantic_query`,
- gateway resolves `semantic_query` against active workspace semantic manifest state,
- gateway executes generated SQL only after dataset/workspace entitlement checks over all mapped semantic datasets,
- raw client-provided SQL for AI identities is denied by default.

**Rationale**  
This tightens AI query behavior to governed semantic objects and prevents direct/raw SQL paths from becoming implicit privilege expansion vectors.

**Alternatives considered**  
- Keep AI SQL path dataset-scoped but permit raw query text (rejected: weak semantic governance).  
- Enforce semantic mode for all actors immediately (rejected: too disruptive; conservative baseline is AI-first).

**Implications**  
- AI callers need active semantic manifests before query success.
- Entitlement checks now evaluate all semantic-bound dataset IDs, not a single client-supplied dataset field.
- Gateway responses/audit resources include semantic context for traceability.

**Affected files**  
- evidence: backend/gateway/semantic_binding.py :: bind_semantic_query
- evidence: backend/gateway/app.py :: semantic_query_required
- evidence: backend/gateway/app.py :: semantic_metric_id
- evidence: tests/test_gateway_dataset_entitlements.py :: test_gateway_denies_ai_semantic_query_without_manifest
- evidence: tests/test_gateway_dataset_entitlements.py :: test_gateway_allows_ai_query_for_entitled_dataset
- evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_query_denies_ai_dataset_from_other_workspace

**Verification impact**  
- evidence: tests/test_gateway_dataset_entitlements.py :: test_gateway_denies_ai_query_without_semantic_query
- evidence: tests/test_gateway_dataset_entitlements.py :: test_gateway_denies_unknown_semantic_metric
- evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_query_denies_ai_dataset_from_other_workspace
- evidence: tests/test_provenance_schema_stability.py :: test_gateway_query_provenance_v1_fields_are_stable

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (gateway authorization and AI query enforcement path)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (AI-only semantic enforcement, human SQL unchanged)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0054 Gold template pack baseline (invoices/crm/support packs + deterministic CLI bundle generation)

**Decision**  
Implement deterministic starter gold template packs and CLI generation:
- introduce template packs `invoices`, `crm`, and `support`,
- generate workspace-scoped template bundles with validated semantic starter manifests,
- expose CLI commands `schemapilot templates list` and `schemapilot templates apply ...`.

**Rationale**  
This reduces onboarding friction by giving repeatable starter semantic/gold model scaffolds for common business domains.

**Alternatives considered**  
- Keep templates as docs-only snippets (rejected: no executable deterministic output).  
- Put template logic under workers and import from CLI (rejected: violates boundary fitness rules).

**Implications**  
- Template generation is boundary-safe (`cli -> shared_domain`) and deterministic by output content.
- Users can bootstrap semantic/gold starter definitions without editing manifests manually.
- Unknown packs and overwrite collisions fail closed.

**Affected files**  
- evidence: backend/shared_domain/gold_templates.py :: GOLD_TEMPLATE_PACKS
- evidence: backend/shared_domain/gold_templates.py :: generate_gold_template_bundle
- evidence: cli/schemapilot_cli/main.py :: @templates_app.command("apply")
- evidence: cli/schemapilot_cli/main.py :: @templates_app.command("list")
- evidence: tests/test_gold_templates.py :: test_generate_gold_template_bundle_is_deterministic
- evidence: tests/test_cli_commands.py :: test_templates_apply_generates_bundle

**Verification impact**  
- evidence: tests/test_gold_templates.py :: test_list_gold_template_packs_contains_expected_ids
- evidence: tests/test_gold_templates.py :: test_generate_gold_template_bundle_rejects_unknown_pack
- evidence: tests/test_cli_commands.py :: test_templates_list_shows_expected_packs
- evidence: tools/check_boundary_fitness.py :: PASS CHK-BOUNDARY-FITNESS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: NO  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (explicit pack IDs + fail-closed generation)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0055 Monotonic ULID generation baseline (per-process ordered ULIDs for deterministic queue execution)

**Decision**  
Replace randomized ULID suffix generation with a lock-protected per-millisecond monotonic counter in `new_ulid()`.

**Rationale**  
Random suffixes could reorder queued runs created within the same millisecond, causing non-deterministic worker execution order and flaky sequencing behavior.

**Alternatives considered**  
- Keep randomized suffixes and patch tests only (rejected: leaves runtime ordering hazard).  
- Add DB-level created-at ordering column everywhere (rejected for now: broader migration surface).

**Implications**  
- ULIDs remain 26-char Crockford base32 and time-sortable.
- Sequential ULID creation in a process is now deterministic and monotonic.
- Queue processing ordered by `run_id` is stable under same-millisecond run creation.

**Affected files**  
- evidence: backend/shared_domain/ids.py :: new_ulid
- evidence: backend/workers/run_processor.py :: .order_by(RunRecord.run_id)
- evidence: tests/test_worker_runner.py :: test_worker_runner_processes_semantic_bootstrap_run

**Verification impact**  
- evidence: tests/test_worker_runner.py :: test_worker_runner_processes_semantic_bootstrap_run
- evidence: tests/test_pipeline_discover_catalog.py :: test_discover_run_populates_catalog_and_evidence_deterministically
- evidence: tests/test_manifest_tools.py :: test_manifest_roundtrip
- evidence: python -m pytest -q :: [100%] (full suite pass)

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (run ordering determinism in worker orchestration)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (monotonic counter under lock)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0056 Document connector extraction baseline (PDF/EML/MBOX discovery + confidence-scored evidence)

**Decision**  
Expand document ingestion baseline to support common document-first sources:
- add read-only document connector discovery for `PDF`, `EML`, `MBOX` (plus `TXT`),
- add extraction methods per document type with confidence scoring and labels,
- keep fail-closed behavior: invalid/unsupported documents mark extraction as failed while preserving raw artifacts.

**Rationale**  
Many adoption candidates are document-heavy. Extraction method metadata and confidence evidence are required before enabling downstream retrieval/indexing decisions.

**Alternatives considered**  
- Keep plain-text-only extraction (rejected: too narrow for common enterprise inputs).  
- Auto-ignore extraction failures without explicit evidence (rejected: violates evidence-backed governance).

**Implications**  
- Evidence payloads now include `source_extension`, `extraction_method`, `confidence`, `confidence_label`, and `text_length`.
- Invalid PDFs fail closed with explicit error evidence.
- Connector discovery can scope document-specific scans independently of generic filesystem discovery.

**Affected files**  
- evidence: backend/workers/connectors/documents.py :: discover_document_files
- evidence: backend/workers/documents.py :: _extract_document_text
- evidence: backend/workers/documents.py :: _extract_eml_text
- evidence: backend/workers/documents.py :: _extract_mbox_text
- evidence: tests/test_documents_extraction_quality.py :: test_document_connector_discovers_supported_document_extensions
- evidence: tests/test_documents_extraction_quality.py :: test_ingest_pdf_fails_closed_on_invalid_signature

**Verification impact**  
- evidence: tests/test_documents_extraction_quality.py :: test_ingest_eml_extracts_subject_and_body_with_confidence
- evidence: tests/test_documents_extraction_quality.py :: test_ingest_mbox_extracts_message_content
- evidence: tests/test_documents_retrieval.py :: test_document_ingest_preserves_raw_on_extraction_failure
- evidence: python -m pytest -q :: [100%] (full suite pass)

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (sensitive-data handling and fail-closed extraction behavior)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (preserve raw, fail extraction with evidence)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0057 OpenSearch retrieval module baseline (optional gateway backend + internal-only indexing helpers)

**Decision**  
Implement `NW-0007` as an optional retrieval/index module with fail-closed defaults:
- gateway retrieval can use `retrieval_backend=opensearch`,
- opensearch path is denied with `module_disabled` unless explicitly enabled,
- retrieval remains policy-bound (workspace + dataset entitlements) and always audited,
- worker-side OpenSearch indexing helpers remain boundary-safe (`workers -> shared_domain`, no imports from `gateway`),
- compose includes optional OpenSearch service with no host port exposure.

**Rationale**  
Document search/index capability is needed for next-wave adoption, but must not weaken non-bypass and deny-by-default security invariants.

**Alternatives considered**  
- Auto-fallback from OpenSearch to filesystem corpus when unavailable (rejected: silent fail-open behavior).  
- Expose OpenSearch service ports for easy local debugging (rejected: violates no-bypass posture).

**Implications**  
- OpenSearch retrieval is explicit opt-in and safe by default.
- Gateway can deny unavailable/disabled retrieval backends with deterministic reasons.
- Indexer utilities can be extended in worker orchestration without cross-layer dependency drift.

**Affected files**  
- evidence: backend/gateway/app.py :: /api/v1/gateway/retrieve
- evidence: backend/gateway/retrieval_opensearch.py :: search_opensearch_documents
- evidence: backend/workers/indexers/opensearch_indexer.py :: index_documents_opensearch
- evidence: backend/workers/indexers/__init__.py :: Document and retrieval indexer helpers
- evidence: deploy/docker-compose.yml :: opensearch
- evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_opensearch_module_disabled_fail_closed
- evidence: tests/test_retrieval_opensearch.py :: test_search_opensearch_documents_filters_by_allowed_datasets
- evidence: tests/test_opensearch_indexer.py :: test_build_bulk_payload_is_deterministic_and_sorted

**Verification impact**  
- evidence: python -m pytest -q tests/test_gateway_retrieve.py tests/test_retrieval_opensearch.py tests/test_opensearch_indexer.py :: [100%]
- evidence: python tools/check_boundary_fitness.py :: PASS CHK-BOUNDARY-FITNESS
- evidence: python tools/check_no_bypass_ports.py :: PASS CHK-NO-BYPASS-PORTS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (gateway retrieval enforcement + non-bypass deployment posture)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (disabled-by-default module + explicit deny reasons)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0058 Qdrant vector retrieval baseline (optional embeddings provider + internal-only vector index module)

**Decision**  
Implement `NW-0008` as an optional vector retrieval/indexing extension:
- add a shared embeddings provider interface/loader with strict defaults (`disabled` by default, deterministic local `hash` provider opt-in),
- add gateway Qdrant retrieval adapter behind `retrieval_backend=qdrant`,
- deny retrieval with `module_disabled` when Qdrant is not explicitly enabled,
- deny retrieval with `embedding_provider_disabled` when vector retrieval is enabled but embeddings provider remains disabled,
- add worker-side Qdrant indexer helpers that remain boundary-safe and deterministic.

**Rationale**  
Vector retrieval is high-leverage for document-heavy AI workflows, but it must remain opt-in, fail-closed, and consistent with gateway-only enforcement.

**Alternatives considered**  
- Auto-enable local embeddings whenever Qdrant is enabled (rejected: implicit capability expansion).  
- Add direct Qdrant client access from UI or worker-facing endpoints (rejected: non-bypass architecture erosion risk).

**Implications**  
- Operators explicitly choose both vector backend and embeddings provider.
- Qdrant paths can be added without exposing index ports.
- Deterministic hash embeddings provide a safe local baseline for tests and offline development.

**Affected files**  
- evidence: backend/shared_domain/embeddings_provider.py :: load_embeddings_provider
- evidence: backend/shared_domain/config.py :: SUPPORTED_RETRIEVAL_BACKENDS
- evidence: backend/gateway/retrieval_qdrant.py :: search_qdrant_documents
- evidence: backend/gateway/app.py :: embedding_provider_disabled
- evidence: backend/workers/indexers/qdrant_indexer.py :: index_documents_qdrant
- evidence: deploy/docker-compose.yml :: qdrant
- evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_qdrant_backend_returns_results
- evidence: tests/test_embeddings_provider.py :: test_hash_embeddings_provider_is_deterministic
- evidence: tests/test_retrieval_qdrant.py :: test_search_qdrant_documents_filters_by_allowed_datasets
- evidence: tests/test_qdrant_indexer.py :: test_build_points_payload_is_deterministic_and_sorted

**Verification impact**  
- evidence: python -m pytest -q tests/test_gateway_retrieve.py tests/test_embeddings_provider.py tests/test_retrieval_qdrant.py tests/test_qdrant_indexer.py :: [100%]
- evidence: python tools/check_boundary_fitness.py :: PASS CHK-BOUNDARY-FITNESS
- evidence: python tools/check_no_bypass_ports.py :: PASS CHK-NO-BYPASS-PORTS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (retrieval security boundary and optional external vector backend integration)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (disabled backend/provider by default + deny reasons)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0059 Retrieval ABAC parity baseline (metadata-bound row filters + snippet masking across retrieval backends)

**Decision**  
Bring retrieval paths to ABAC/masking parity with SQL enforcement:
- gateway retrieval now evaluates ABAC using request `resource_attributes`,
- retrieval denies on ABAC mismatch (e.g. region mismatch),
- ABAC row filters are enforced against server-side dataset metadata (`sensitivity_summary_json`) as a conservative metadata-bound gate,
- ABAC masks are applied to retrieval snippets (including email-token masking when email masking is active),
- allow responses/provenance/access-decision records now include applied filters/masks for retrieval.

**Rationale**  
`NW-0009` closes a policy gap where retrieval was entitlement-scoped but not ABAC/masking-equivalent to SQL execution.

**Alternatives considered**  
- Keep retrieval ABAC as advisory metadata only (rejected: policy drift between SQL/retrieval paths).  
- Filter only on client-provided metadata attributes (rejected: trust boundary violation).

**Implications**  
- Retrieval now fails closed when dataset metadata is missing required ABAC filter keys.
- Snippet outputs avoid exposing obvious sensitive tokens when masking rules apply.
- Policy evidence between query and retrieval is more consistent for audits.

**Affected files**  
- evidence: backend/gateway/app.py :: evaluate_abac(actor=actor_dict, resource_attributes=resource_attrs, mode=abac_mode)
- evidence: backend/gateway/app.py :: _apply_retrieval_row_filter
- evidence: backend/gateway/app.py :: _apply_retrieval_masks
- evidence: backend/gateway/app.py :: _load_dataset_sensitivity_summaries
- evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_denies_abac_region_mismatch
- evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_applies_metadata_row_filter_and_email_mask

**Verification impact**  
- evidence: python -m pytest -q tests/test_gateway_retrieve.py :: [100%]
- evidence: python tools/check_boundary_fitness.py :: PASS CHK-BOUNDARY-FITNESS
- evidence: python tools/check_no_bypass_ports.py :: PASS CHK-NO-BYPASS-PORTS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (authorization/masking parity on retrieval path)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (deny on ABAC mismatch; drop rows missing metadata required by row filter)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0060 AI/ops extension baseline (optional AI service + policy simulation + catalog/scheduling/fairness + audit sinks + secrets + Helm hardening)

**Decision**  
Complete `NW-0010` through `NW-0025` with secure defaults:
- keep AI service optional and disabled-by-default, while adding semantic-constrained SQL planning and a deterministic AI eval harness,
- enforce operator safety additions (policy simulation endpoint, cost budgets, audit sink plugins, run scheduling and workspace fairness),
- wire secrets-store abstraction into source credential flows with opaque refs,
- ship hardened Helm/K8s assets and no-bypass static checks.

**Rationale**  
This tranche closes governance and operability gaps without weakening fail-closed defaults.

**Implications**  
- Optional services remain explicit opt-in and non-bypass.
- Control-plane and gateway operational checks are now easier to automate.
- Scheduling/fairness and policy simulation improve multi-workspace reliability and safe debugging.

**Affected files**  
- evidence: backend/ai_service/app.py :: /api/v1/ai/ask-sql
- evidence: backend/gateway/app.py :: /api/v1/gateway/policy/simulate
- evidence: backend/shared_domain/secrets_store.py :: load_secrets_store
- evidence: backend/shared_domain/scheduling.py :: enqueue_due_scheduled_runs
- evidence: backend/shared_domain/audit_sinks.py :: load_audit_sink
- evidence: backend/control_plane/catalog_snapshot.py :: export_catalog_snapshot
- evidence: deploy/helm/templates/networkpolicy.yaml :: NetworkPolicy
- evidence: tests/test_ai_eval_harness.py :: test_ai_eval_harness_smoke_passes_and_writes_report
- evidence: tests/test_gateway_policy_simulation.py :: test_policy_simulation_allows_steward_role

**Verification impact**  
- evidence: python -m pytest -q :: [100%]
- evidence: python tools/check_boundary_fitness.py :: PASS CHK-BOUNDARY-FITNESS
- evidence: python tools/check_no_bypass_ports.py :: PASS CHK-NO-BYPASS-PORTS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (gateway enforcement + control-plane governance and deployment posture)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (all optional modules disabled by default)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0061 Completion baseline for NW-0026..NW-0034 and AI track (demo generator, docs wave, pack registry, Trino hardening, compaction, anomaly/ERv2, locale parsing, typed SDK)

**Decision**  
Finalize remaining next-wave tasks and AI track endpoints with deterministic, test-covered implementations:
- add CLI/tool first-hour demo scenario generation,
- add documentation wave (quickstart, security model, connector guide),
- add pack registry + linter gate,
- harden Trino adapter with retry/cancel timeout path and add maintenance hooks,
- add compact/anomaly/ERv2/locale parsing modules with fail-closed behavior,
- add generated Python SDK endpoint artifacts with up-to-date check gate,
- complete AI endpoint surface (`AI-0101`..`AI-0115`) including metric-first and eval-generator flows.

**Rationale**  
This closes the entire execution board while preserving minimal UI and CLI/operator-first usage.

**Implications**  
- `TASKLIST_NEXT.md` is now fully checked with all NW and AI items complete.
- Tooling baseline can now verify pack registry and client SDK generation drift.
- Data quality and parsing resilience improve reliability for messy real-world exports.

**Affected files**  
- evidence: backend/shared_domain/demo_scenario.py :: generate_demo_scenario
- evidence: cli/schemapilot_cli/main.py :: demo-generate
- evidence: tools/demo_scenario_generator.py :: PASS demo scenario generated
- evidence: tools/pack_lint.py :: PASS CHK-PACK-REGISTRY
- evidence: backend/gateway/executor_trino.py :: cancel_trino_query
- evidence: backend/workers/compaction.py :: compact_json_files
- evidence: backend/workers/anomaly_detection.py :: detect_profile_anomalies
- evidence: backend/workers/entity_resolution_v2.py :: resolve_entities_v2
- evidence: backend/workers/parsing.py :: parse_currency
- evidence: tools/generate_clients.py :: PASS CHK-CLIENT-SDK-GEN
- evidence: sdk/python/schemapilot_client/generated_endpoints.py :: OPENAPI_FINGERPRINT

**Verification impact**  
- evidence: python -m pytest -q :: [100%]
- evidence: python tools/pack_lint.py :: PASS CHK-PACK-REGISTRY
- evidence: python tools/generate_clients.py --check :: PASS CHK-CLIENT-SDK-GEN

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (query/retrieval and worker quality gates)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (optional paths remain disabled-by-default)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0062 Config/doctor operability baseline (`V2-0005` strict config schema and `V2-0003` deterministic preflight diagnostics)

**Decision**  
Implement the first `TASKLIST_NEXT_V2` lane with:
- strict config file support (`.json` and simple `.yaml`) for runtime settings,
- fail-closed unknown config key handling,
- explicit redaction contract for diagnostics (`Settings.to_redacted_dict`),
- deterministic CLI doctor preflight checks over settings validation, storage/database, migration posture, no-bypass deploy artifacts, secrets backend availability, and JWKS reachability.

**Rationale**  
Operator experience and install safety are the highest-value next milestone. Configuration drift and unclear setup errors are major adoption blockers.

**Alternatives considered**  
- Keep env-only config without strict validation (rejected: higher misconfiguration risk and weaker reproducibility).  
- Keep `doctor` as a thin wrapper over SSOT scripts only (rejected: insufficient operational signal for deploy/runtime safety).

**Implications**  
- Invalid/unknown config keys now fail early when config files are used.
- Diagnostics can safely print redacted settings context.
- Operators can use `schemapilot doctor --config <path>` for deterministic preflight health.

**Affected files**  
- evidence: backend/shared_domain/config.py :: def load_settings(config_path: str | None = None) -> Settings:
- evidence: backend/shared_domain/config.py :: def to_redacted_dict(self) -> dict[str, object]:
- evidence: cli/schemapilot_cli/doctor.py :: run_doctor_preflight
- evidence: cli/schemapilot_cli/main.py :: doctor
- evidence: tests/test_config_loading_v2.py :: test_load_settings_rejects_unknown_config_keys
- evidence: tests/test_doctor_preflight.py :: test_doctor_preflight_passes_with_valid_local_config
- evidence: tests/test_cli_commands.py :: test_doctor_command_returns_ok_report_for_valid_config

**Verification impact**  
- evidence: python -m pytest -q tests/test_config_loading_v2.py tests/test_doctor_preflight.py tests/test_cli_commands.py :: [100%]
- evidence: python -m pytest -q :: [100%]

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (startup safety and operator preflight diagnostics)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (fail-closed config validation and deterministic check list)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0063 Audit outbox delivery baseline (`V2-0001` durable sink dispatch decoupling with fail-closed local audit writes)

**Decision**  
Implement durable audit sink delivery via outbox semantics:
- keep local audit persistence fail-closed for control-plane and gateway operations,
- enqueue sink payloads into `audit_outbox_events` inside the same DB transaction as audit rows,
- dispatch queued sink payloads in bounded batches with retry caps and explicit `pending|sent|failed` status transitions,
- keep inline sink mode as an explicit compatibility override while defaulting to `outbox`.

**Rationale**  
Direct in-request sink delivery made availability dependent on optional integrations. Outbox delivery preserves audit correctness while decoupling external sink outages from core request success.

**Alternatives considered**  
- Keep synchronous sink delivery only (rejected: operational coupling and avoidable denials).  
- Make sink delivery best-effort without durable queue state (rejected: no backlog visibility, weak operability).

**Implications**  
- Sink outages now accumulate visible backlog without bypassing local audit writes.
- Local DB audit failures still deny critical operations.
- Operators can tune batch size and retry bounds through strict config fields.

**Affected files**  
- evidence: backend/shared_domain/audit_models.py :: class AuditOutboxEvent
- evidence: backend/shared_domain/audit_outbox.py :: dispatch_audit_outbox_batch
- evidence: backend/shared_domain/observability.py :: schemapilot_audit_outbox_backlog_total
- evidence: backend/control_plane/app.py :: append_audit_event
- evidence: backend/gateway/app.py :: _record_access_decision
- evidence: migrations/versions/0002_audit_outbox_events.py :: upgrade
- evidence: tests/test_audit_sinks.py :: test_webhook_audit_sink_failure_queues_outbox_without_denying_request
- evidence: tests/test_audit_outbox.py :: test_dispatch_outbox_bounds_retries_and_marks_failed

**Verification impact**  
- evidence: python -m pytest -q tests/test_audit_outbox.py tests/test_audit_sinks.py tests/test_audit_fail_closed.py tests/test_migrations_enforced.py :: [100%]
- evidence: python -m pytest -q :: [100%]
- evidence: python tools/check_boundary_fitness.py :: PASS CHK-BOUNDARY-FITNESS

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (audit durability and authorization-denial semantics)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (local audit write remains mandatory and fail-closed)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0064 Operator diagnostics baseline (`V2-0002`, `V2-0004`, `V2-0032`: run-step DAG visibility + redacted support bundle + workspace analytics CLI)

**Decision**  
Implement operator-facing diagnostics on top of the hardened runtime:
- add run-step DAG persistence (`runs_run_steps`) with deterministic step ordering, per-step status transitions, timing, error codes, and evidence references,
- expose run-step state through control-plane run responses and a dedicated run-steps endpoint,
- add CLI workspace analytics (`schemapilot analyze`) summarizing policy denials, review backlog, run/run-step health, and outbox backlog,
- add CLI redacted diagnostics bundle (`schemapilot diag-bundle`) exporting settings, analytics, recent runs/steps, and minimal audit excerpts without raw data payloads.

**Rationale**  
The platform had strong controls but limited day-2 operability visibility. Step-level execution telemetry and deterministic support bundles reduce MTTR without adding UI complexity.

**Alternatives considered**  
- Build dashboard-heavy UI first (rejected: violates minimal-UI priority).  
- Keep run status coarse-grained (rejected: weak failure attribution for strict ingest/governance gates).

**Implications**  
- Worker failures are attributable to explicit step nodes with evidence pointers.
- Operators can generate self-contained support bundles without exposing secrets.
- CLI analytics provides quick “why blocked/why denied” summaries directly from runtime state.

**Affected files**  
- evidence: backend/shared_domain/metadata_models.py :: class RunStepRecord
- evidence: migrations/versions/0003_run_step_dag.py :: upgrade
- evidence: backend/workers/run_processor.py :: RUN_STEP_DEFINITIONS
- evidence: backend/control_plane/repository.py :: list_run_steps
- evidence: backend/control_plane/app.py :: /api/v1/workspaces/{workspace_id}/runs/{run_id}/steps
- evidence: cli/schemapilot_cli/analyze.py :: analyze_workspace
- evidence: cli/schemapilot_cli/diag.py :: generate_diag_bundle
- evidence: cli/schemapilot_cli/main.py :: analyze
- evidence: cli/schemapilot_cli/main.py :: diag-bundle
- evidence: tests/test_run_steps.py :: test_run_step_failure_records_evidence_for_strict_completeness
- evidence: tests/test_cli_operability_v2.py :: test_diag_bundle_command_writes_redacted_zip

**Verification impact**  
- evidence: python -m pytest -q tests/test_run_steps.py tests/test_cli_operability_v2.py tests/test_cli_commands.py tests/test_worker_runner.py tests/test_control_plane_api.py :: [100%]
- evidence: python -m pytest -q :: [100%]

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (run execution, support diagnostics, audit-derived analytics)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (all new surfaces are additive and fail-closed run behavior is preserved)  
- Safe to decide: YES  
- Conservative baseline: YES

---

## D-0065 Completion baseline for remaining `TASKLIST_NEXT_V2` items (`V2-0006`..`V2-0031`)

**Decision**  
Mark the remaining V2 execution lane as complete based on implemented code paths and full regression verification, covering:
- pack trust and lifecycle (`V2-0007`, `V2-0015`, `V2-0031`),
- connector certification/state/connectors (`V2-0010`, `V2-0014`, `V2-0011`, `V2-0012`, `V2-0013`),
- CLI operator flows (`V2-0016`..`V2-0019`),
- performance and execution controls (`V2-0020`..`V2-0024`),
- security/observability hardening (`V2-0009`, `V2-0025`, `V2-0026`, `V2-0027`, `V2-0008`),
- enterprise tail tasks (`V2-0028`, `V2-0029`, `V2-0030`, `V2-0006`).

**Rationale**  
The implementation branch already contained these features but task status files lagged behind. A full suite re-validation confirms they are integrated and stable.

**Implications**  
- `TASKLIST_NEXT_V2.md` is fully checked.
- The project can move to post-V2 prioritization without unresolved board debt.
- Security and operability defaults remain fail-closed and minimal-UI.

**Affected files**  
- evidence: tools/pack_lint.py :: validate_pack_registry
- evidence: tools/pack_migrate.py :: migrate_pack_payload
- evidence: tools/connector_conformance.py :: runtime/connector_conformance/report.json
- evidence: backend/shared_domain/connector_state.py :: load_connector_state
- evidence: plugins/examples/sftp_connector.py :: discover
- evidence: plugins/examples/google_drive_connector.py :: discover
- evidence: plugins/examples/imap_connector.py :: discover
- evidence: cli/schemapilot_cli/main.py :: init_interactive
- evidence: cli/schemapilot_cli/main.py :: review_batch
- evidence: cli/schemapilot_cli/main.py :: query
- evidence: cli/schemapilot_cli/main.py :: policy_audit_report
- evidence: backend/gateway/query_cache.py :: InMemoryQueryCache
- evidence: backend/workers/run_processor.py :: _process_materialized_refresh_run
- evidence: backend/shared_domain/tracing.py :: start_trace
- evidence: tools/security_fuzz.py :: run_fuzz
- evidence: tools/chaos_drills.py :: run_drills
- evidence: tools/generate_sbom.py :: build_sbom
- evidence: backend/control_plane/deletion.py :: _build_deletion_attestation
- evidence: backend/shared_domain/artifact_crypto.py :: encrypt_payload
- evidence: deploy/REFERENCE_DEPLOYMENTS.md :: Reference Deployments
- evidence: backend/control_plane/policy_pack_service.py :: promote_policy_pack_canary

**Verification impact**  
- evidence: python -m pytest -q :: [100%]
- evidence: python -m pytest -q tests/test_cli_commands.py tests/test_reference_connectors.py tests/test_connector_state.py tests/test_connector_conformance.py tests/test_gateway_query_cache.py tests/test_policy_pack_change_gating.py tests/test_worker_materialized_refresh.py tests/test_artifact_encryption.py tests/test_tracing.py tests/test_pack_lint.py tests/test_pack_migrate.py tests/test_supply_chain_tools.py tests/test_plugin_sandbox.py tests/test_incremental_ingest_state.py tests/test_security_fuzz_tool.py tests/test_filesystem_connector.py tests/test_gateway_trino_adapter.py :: [100%]

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (gateway, audit, worker execution, deployment hardening)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (optional modules remain explicit opt-in)  
- Safe to decide: YES  
- Conservative baseline: YES

