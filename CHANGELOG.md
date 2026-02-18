# CHANGELOG.md â€” SSOT Pack Evolution (Not Product Code)

## v1.0.0
- Initial SSOT pack for SchemaPilot.
- Established progressive profile strategy and Query Gateway non-bypass invariants.
  - evidence: DECISIONS.md :: D-0002 Progressive packaging profiles
  - evidence: DECISIONS.md :: D-0003 Query Gateway is the single enforcement point (no bypass)

## v1.0.1
- Patch release: fixed reference integrity and evidence pointer edge cases that could cause SSOT verification to fail.
  - evidence: AUDIT_REPORT.md :: Patch Summary (v1.0.1)
  - evidence: checks/CHECKS_INDEX.md :: CHK-REF-INTEGRITY
  - evidence: checks/CHECKS_INDEX.md :: CHK-EVIDENCE-POINTER-FORMAT

## v1.0.2
- Bootstrap implementation kickoff:
  - completed `T-0001` scaffold for `backend/`, `ui/`, `cli/`, and `deploy/`.
  - added boundary-fitness checker and rules baseline for dependency-direction and cycle enforcement.
  - evidence: PROGRESS.md :: PHASE_0_BOOTSTRAP
  - evidence: DECISIONS.md :: D-0008 Boundary fitness enforcement baseline (repo-local static checker + rules file)
  - evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

## v1.0.3
- Completed PHASE_0 bootstrap tasks `T-0002` through `T-0006`:
  - implemented `schemapilot check` baseline (ruff, mypy, pytest, migration check, SSOT checks, UI lint/type/test, smoke)
  - added manifest generation/verification tooling and SSOT verifier command
  - implemented disabled-by-default integration stubs and tests
  - evidence: PROGRESS.md :: PHASE_0_BOOTSTRAP
  - evidence: DECISIONS.md :: D-0010 Tooling baseline command contract (`schemapilot check` as single entrypoint)

- Completed PHASE_1 tasks `T-0007` through `T-0012`:
  - implemented persisted control-plane API skeleton and Alembic migrations baseline
  - implemented UI wizard/review queue shell and CLI shell commands
  - implemented append-only audit logging coverage for control-plane and gateway paths
  - enforced deny-by-default policy baseline in gateway
  - evidence: PROGRESS.md :: PHASE_1_CORE_CONTROL_PLANE
  - evidence: DECISIONS.md :: D-0009 Metadata persistence baseline (SQLAlchemy + Alembic schema-first)
  - evidence: DECISIONS.md :: D-0011 Shared audit persistence model (gateway + control plane append-only writes)
  - evidence: DECISIONS.md :: D-0012 Manifest scope excludes transient runtime/cache/vendor paths

## v1.0.4
- Completed PHASE_2 tasks `T-0013` through `T-0018`:
  - added read-only connector baseline for filesystem, S3-compatible object lists, and DB table discovery
  - added bronze ingest manifest/idempotency baseline
  - added bounded profiler evidence bundles and schema drift review-task conversion
  - evidence: PROGRESS.md :: PHASE_2_DATA_INGEST_AND_CATALOG
  - evidence: DECISIONS.md :: D-0013 Connector baseline implementation (filesystem, S3 read-only, DB read-only)
  - evidence: DECISIONS.md :: D-0014 Profiling/drift baseline (bounded CSV profiling + schema drift review tasks)

## v1.0.5
- Completed PHASE_3 tasks `T-0019` through `T-0024`:
  - added schema/key/relationship inference heuristics
  - added PII proposal detection with confidence and redacted evidence
  - implemented persisted review queue backend and decision workflow
  - implemented review queue UI decision controls with evidence display
  - enforced fail-closed gold publish gating on blocking review tasks/contracts
  - evidence: PROGRESS.md :: PHASE_3_MODELING_AND_REVIEW_QUEUE
  - evidence: DECISIONS.md :: D-0015 Modeling + review baseline (heuristic inference, PII proposals, gated gold publish)

## v1.0.6
- Completed PHASE_4 tasks `T-0025` through `T-0031`:
  - added silver normalization/crosswalk baseline and reversible ER merge helpers
  - added quality contract + quarantine evaluation
  - added gold semantic build/publish-pointer fail-closed baseline
  - added gateway SQL execution baseline with provenance and policy decision IDs
  - added non-bypass and Starterâ†’Team upgrade drill tests
  - evidence: PROGRESS.md :: PHASE_4_SILVER_GOLD_AND_QUERY_GATEWAY
  - evidence: DECISIONS.md :: D-0016 Silver/Gold build baseline (deterministic snapshots + fail-closed publish pointer)
  - evidence: DECISIONS.md :: D-0017 Gateway SQL execution baseline (policy-first execution + non-bypass enforcement tests)

## v1.0.7
- Completed PHASE_5 tasks `T-0032` through `T-0036`:
  - implemented fixed T1..T8 template library and gate-first decision logic
  - implemented weighted scoring and confidence/approval trigger model
  - wired recommendation report to API and UI display
  - evidence: PROGRESS.md :: PHASE_5_DECISION_ENGINE
  - evidence: DECISIONS.md :: D-0018 Decision engine baseline (fixed T1..T8 library + gate-first scoring + confidence triggers)

## v1.0.8
- Completed PHASE_6 tasks `T-0037` through `T-0041`:
  - added ABAC integration mode (`internal` + optional `opa`) with fail-closed deny behavior
  - added deletion workflow impact-preview/evidence-report baseline with legal-hold blocking
  - added metadata-bound document ingest extraction failure handling
  - added policy-filtered retrieval provenance/citations path in gateway
  - added secrets rotation drill command and tests
  - evidence: PROGRESS.md :: PHASE_6_GOVERNANCE_AND_DOCUMENT_RETRIEVAL
  - evidence: DECISIONS.md :: D-0019 PHASE_6 governance baseline (ABAC/OPA fail-closed + deletion/doc retrieval + secrets rotation drill)

- Completed PHASE_7 tasks `T-0042` through `T-0046`:
  - added structured observability module and `/metrics` endpoints with dashboard definition
  - added MessyBench generator/harness and performance regression harness artifacts
  - expanded `schemapilot check` gating with backup/restore and secrets rotation drills
  - added compose progressive profiles and optional k8s skeleton manifests
  - finalized runbook coverage for release readiness
  - evidence: PROGRESS.md :: PHASE_7_OBSERVABILITY_TESTS_RELEASE
  - evidence: DECISIONS.md :: D-0023 Release readiness baseline (`schemapilot check` includes governance/perf/backup/rotation drills)

## v1.0.9
- Hardened release-validation protocol for enterprise-like staging:
  - added clean-room install/bootstrap validation command
  - added deterministic Python dependency audit based on declared project requirements
  - added automated release-gate orchestration with machine-readable `go/no-go` output
  - added CI workflows for security scans and tag-driven release gating
  - added enterprise release checklist with P0/P1 matrix and sign-off flow
  - evidence: DECISIONS.md :: D-0024 Enterprise-like release simulation baseline (clean-room install + project-scoped dependency audit + automated release gate)
  - evidence: PROGRESS.md :: PHASE_7_OBSERVABILITY_TESTS_RELEASE

## v1.0.10
- Refreshed release-status evidence after validation rerun:
  - re-ran clean-room install check and release gate
  - recorded tracked evidence artifacts for final readiness snapshot
  - evidence: evidence/t0046/cleanroom_check.txt :: PASS clean-room install check
  - evidence: evidence/t0046/release_gate_status.txt :: status: go
  - evidence: PROGRESS.md :: PHASE_7_OBSERVABILITY_TESTS_RELEASE

## v1.0.11
- Security and determinism hardening update:
  - adopted authenticated gateway actor context and enforced ABAC filter application in query/retrieval paths
  - switched retrieval corpus loading to server-side artifacts and tightened dataset entitlement checks
  - tightened fail-closed connector/build behavior (S3 truncation handling, deterministic DB snapshots, silver natural-key validation)
  - strengthened non-bypass and error-contract verification coverage, plus CLI/UI regression tests
  - evidence: DECISIONS.md :: D-0025 Security and determinism hardening baseline (authenticated gateway context, enforced ABAC filtering, server-side retrieval corpus, and fail-closed ingest/build checks)
  - evidence: PROGRESS.md :: Session history (SSOT pack only)

## v1.0.12
- Adoption roadmap hardening update:
  - expanded operator/deploy documentation for OIDC claim mapping, policy-pack authoring, and plugin packaging entrypoints
  - added runbook index entrypoint under `docs/runbook/README.md`
  - expanded troubleshooting coverage for connector partial-ingest and `CHK-MANIFEST-VERIFY` drift recovery
  - added S3 `max_keys` fail-closed negative-path test coverage
  - evidence: DECISIONS.md :: D-0026 Adoption roadmap hardening baseline (demo-first onboarding, operator docs depth, and enterprise extension guidance)
  - evidence: spec/12_RUNBOOK.md :: Symptom: CHK-MANIFEST-VERIFY fails
  - evidence: tests/test_s3_connector.py :: test_s3_connector_fails_closed_when_max_keys_reached_without_truncation_metadata

## v1.0.13
- Systematic task-board execution update:
  - implemented control-plane auth hardening with role-based mutation guards (deny-by-default)
  - hardened gateway SQL path with read-only safety checks, timeout budgeting, and AI dataset entitlement enforcement
  - normalized service port conventions (CP `8000`, GW `8001`) across entrypoints and tests
  - replaced compose placeholders with Dockerfile-backed services and removed direct Trino port exposure
  - evidence: DECISIONS.md :: D-0027 Execution-priority hardening baseline (control-plane auth, gateway SQL safety/entitlements, and runnable deploy defaults)
  - evidence: TASKLIST.md :: Now (Sprint 1: S0 blockers)
  - evidence: tests/test_control_plane_auth.py :: test_control_plane_denies_missing_token_for_mutation
  - evidence: tests/test_gateway_sql_safety.py :: test_gateway_denies_non_read_sql
  - evidence: tests/test_gateway_dataset_entitlements.py :: test_gateway_denies_ai_query_for_unentitled_dataset

## v1.0.14
- Shared metadata model relocation update:
  - moved canonical metadata SQLAlchemy models into `backend/shared_domain/metadata_models.py`
  - kept `backend/control_plane/db_models.py` as compatibility re-export to avoid breakage
  - updated control-plane repositories to import shared metadata models directly
  - evidence: DECISIONS.md :: D-0028 Shared metadata model relocation baseline (move control-plane SQLAlchemy metadata models into shared domain)
  - evidence: TASKLIST.md :: PR-006 `shared-metadata-models-refactor`

## v1.0.15
- Worker orchestration and evidence-store update:
  - added deterministic worker run runner (`backend/workers/service.py`, `backend/workers/run_processor.py`) with queued-run status transitions and fail-closed run-type handling
  - wired discover runs to real catalog dataset creation, bronze ingest manifests, and profiling evidence outputs
  - introduced immutable evidence store with `evidence://` URIs and authenticated control-plane evidence retrieval endpoint
  - added worker/pipeline/evidence test coverage and compose worker container wiring
  - evidence: DECISIONS.md :: D-0029 Worker orchestration baseline (deterministic queued-run processor and discover-to-catalog pipeline)
  - evidence: DECISIONS.md :: D-0030 Evidence bundle immutability baseline (content-addressed evidence store + authenticated retrieval)
  - evidence: TASKLIST.md :: [x] PR-007 `worker-runner-service`
  - evidence: TASKLIST.md :: [x] PR-008 `discover-to-catalog-pipeline`
  - evidence: TASKLIST.md :: [x] PR-009 `evidence-bundle-store`

## v1.0.16
- PII governance automation update:
  - extended discover pipeline to evaluate high-risk PII patterns and create blocking review tasks automatically
  - persisted PII proposals with immutable evidence bundles and deduplicated open task creation on reruns
  - added pipeline regression test for end-to-end PII detection -> review queue behavior
  - evidence: DECISIONS.md :: D-0031 PII governance automation baseline (high-risk detection to blocking review tasks)
  - evidence: TASKLIST.md :: [x] PR-010 `pii-to-review-queue`
  - evidence: tests/test_pipeline_pii_review.py :: test_discover_pipeline_creates_blocking_pii_review_tasks

## v1.0.17
- Contract publish-gate hardening update:
  - added server-side contract report persistence/loading helpers and removed trust in client-provided contract pass flags
  - made publish fail closed when contract reports are missing or failing
  - added automatic quality-critical blocking review-task creation for contract failure signals
  - evidence: DECISIONS.md :: D-0032 Contract gate hardening baseline (server-side contract reports + fail-closed publish + quality tasks)
  - evidence: TASKLIST.md :: [x] PR-011 `contracts-and-quarantine-hard-gate`
  - evidence: tests/test_contracts_block_publish.py :: test_publish_fails_closed_without_contract_report_and_creates_quality_task

## v1.0.18
- Gold publish/rollback operationalization update:
  - added server-side gold pointer persistence with history tracking
  - publish endpoint now writes real pointer state only when gates pass and reports before/after pointers
  - rollback endpoint now restores pointer targets from history with stable not-found behavior
  - evidence: DECISIONS.md :: D-0033 Gold publish pointer baseline (server-side pointer writes + auditable rollback)
  - evidence: TASKLIST.md :: [x] PR-012 `gold-publish-and-rollback`
  - evidence: tests/test_gold_publish_rollback.py :: test_gold_publish_updates_pointer_and_rollback_restores_previous_build

## v1.0.19
- Gateway DuckDB read-path update:
  - replaced gateway SQLite execution path with DuckDB in-memory execution
  - bound queryable views to server-side published gold pointers (`gold.fact_metrics`)
  - expanded SQL safety denylist to block direct external file scan functions
  - evidence: DECISIONS.md :: D-0034 Gateway DuckDB read-path baseline (published gold views only + external scan denial)
  - evidence: TASKLIST.md :: [x] PR-013 `gateway-duckdb-read-path`
  - evidence: tests/test_gateway_duckdb_readonly.py :: test_gateway_reads_published_gold_metrics_from_duckdb

## v1.0.20
- Drift governance loop update:
  - connected schema drift detection to discover-run orchestration with immutable drift evidence bundles
  - created blocking quality-critical drift review tasks on schema changes (excluding initial baseline)
  - verified drift-generated blocking tasks prevent publish even when contract reports pass
  - evidence: DECISIONS.md :: D-0035 Drift governance baseline (schema-drift proposals from discover runs + publish blocking loop)
  - evidence: TASKLIST.md :: [x] PR-014 `drift-into-ops-loop`
  - evidence: tests/test_drift_blocks_publish.py :: test_schema_drift_creates_blocking_task_and_blocks_publish

## v1.0.21
- Connector plugin runtime update:
  - added Python entry-point plugin loader with duplicate/callable safety checks
  - wired worker discover pipeline to use plugin connectors for non-filesystem source types
  - added plugin loader and plugin-backed worker execution tests
  - evidence: DECISIONS.md :: D-0036 Plugin runtime baseline (entry-point connector loading + worker fallback wiring)
  - evidence: TASKLIST.md :: [x] PR-015 `plugin-loader-runtime`
  - evidence: tests/test_plugin_loader.py :: test_connector_plugin_loader_requires_callable_plugins

## v1.0.22
- KPI extraction automation update:
  - added `tools/kpi_extract.py` to derive weekly KPI snapshots from runtime metadata/audit state
  - added deterministic rebuild-rate and blocking-review backlog extraction
  - added regression test coverage for KPI extraction payloads
  - evidence: DECISIONS.md :: D-0037 KPI extraction baseline (runtime-derived weekly KPI snapshot generation)
  - evidence: TASKLIST.md :: [x] PR-016 `kpi-auto-extraction`
  - evidence: tests/test_kpi_extract.py :: test_kpi_extract_derives_runtime_metrics_from_metadata

## v1.0.23
- Deploy/community/UI completion update:
  - completed runnable compose verification with real local smoke cycle (`up --build`, health checks, auth fail-closed check, `down`)
  - added OSS contributor baseline documents and templates (`CONTRIBUTING.md`, issue templates, PR template)
  - closed low-priority UI card with additional behavior test coverage for review decisions and recommendation actions
  - evidence: DECISIONS.md :: D-0038 Completion baseline for deploy/community/UI thin slice (compose smoke validated, OSS templates added, UI kept intentionally lightweight)
  - evidence: TASKLIST.md :: [x] PR-005 `runnable-compose-profile-team`
  - evidence: TASKLIST.md :: [x] PR-017 `oss-community-basics`
  - evidence: TASKLIST.md :: [x] PR-018 `ui-wizard-upgrade` (low priority by design)
  - evidence: ui/src/App.test.tsx :: submits review decisions and recommendation requests for selected workspace

## v1.0.24
- Post-PR018 S0 hardening execution update:
  - added shared `oidc_jwt` JWT/JWKS verification in shared auth with fail-closed claim/time validation
  - unified gateway auth resolution to use shared auth helpers (removing duplicated gateway-local auth parsing)
  - enforced trusted-proxy startup guardrails for non-local binds and added OIDC JWT startup misconfiguration tests
  - added deploy no-bypass static checker and wired it into tooling baseline checks
  - evidence: DECISIONS.md :: D-0040 OIDC JWT verification and deploy no-bypass enforcement baseline (shared auth path, strict startup guards, and static deploy checks)
  - evidence: TASKLIST.md :: [x] PR-019 `gateway-oidc-jwt-verification` (S0)
  - evidence: TASKLIST.md :: [x] PR-020 `control-plane-oidc-jwt-verification` (S0)
  - evidence: TASKLIST.md :: [x] PR-021 `deploy-no-bypass-enforcement` (S0)
  - evidence: tests/test_gateway_oidc_jwt_auth.py :: test_gateway_oidc_jwt_allows_valid_token
  - evidence: tests/test_control_plane_oidc_jwt_auth.py :: test_control_plane_oidc_jwt_allows_platform_admin
  - evidence: tools/check_no_bypass_ports.py :: PASS CHK-NO-BYPASS-PORTS

## v1.0.25
- Audit fail-closed hardening update:
  - gateway access-decision audit persistence now denies requests on audit write failure (`reason=audit_unavailable`)
  - control-plane audit append path now denies mutating requests when audit persistence fails
  - added `schemapilot_audit_write_failures_total` metric for explicit operational visibility
  - added regression tests for gateway/control-plane deny behavior under audit persistence failure
  - evidence: DECISIONS.md :: D-0041 Audit fail-closed enforcement baseline (gateway/control-plane deny on audit write failures with explicit observability)
  - evidence: TASKLIST.md :: [x] PR-022 `audit-fail-closed-critical-flows` (S0)
  - evidence: tests/test_audit_fail_closed.py :: test_gateway_denies_query_when_audit_write_fails
  - evidence: tests/test_audit_fail_closed.py :: test_control_plane_denies_mutation_when_audit_write_fails

## v1.0.26
- Gateway workspace-isolation hardening update:
  - added cross-workspace dataset ownership checks for AI SQL query dataset context
  - added retrieval entitlement cross-workspace checks and deny path (`dataset_workspace_mismatch`)
  - added regression tests proving known foreign dataset IDs are denied for query and retrieval
  - evidence: DECISIONS.md :: D-0042 Gateway workspace isolation baseline (deny cross-workspace dataset access for AI SQL and retrieval paths)
  - evidence: TASKLIST.md :: [x] PR-023 `gateway-workspace-isolation` (S0)
  - evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_query_denies_ai_dataset_from_other_workspace
  - evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_retrieve_denies_cross_workspace_dataset_entitlement

## v1.0.27
- Gateway throttling hardening update:
  - added in-memory per-actor request-rate and in-flight concurrency guards in gateway
  - enforced fail-closed deny reasons for throttled requests (`rate_limit_exceeded`, `concurrency_limit_exceeded`)
  - added dedicated regression tests for both rate-limit and concurrency-limit denial paths
  - evidence: DECISIONS.md :: D-0043 Gateway actor throttling baseline (per-actor rate and concurrency deny controls with fail-closed decisions)
  - evidence: TASKLIST.md :: [x] PR-024 `gateway-rate-limit-and-cancel` (S1)
  - evidence: tests/test_gateway_rate_limits.py :: test_gateway_denies_when_rate_limit_exceeded
  - evidence: tests/test_gateway_rate_limits.py :: test_gateway_denies_when_concurrency_limit_exceeded

## v1.0.28
- Migration/startup safety hardening update:
  - introduced non-local startup migration-state enforcement via `alembic_version` revision checks
  - kept local-bind bootstrap autocreate path for developer workflow compatibility
  - added CLI migration commands (`migrate-up`, `migrate-status`)
  - added migration enforcement regression tests for missing/mismatched revision handling
  - evidence: DECISIONS.md :: D-0044 Migration-state startup enforcement baseline (non-local bind requires expected alembic revision; local bind retains bootstrap autocreate)
  - evidence: TASKLIST.md :: [x] PR-025 `migrations-enforced-at-startup` (S1)
  - evidence: tests/test_migrations_enforced.py :: test_gateway_non_local_requires_migration_state
  - evidence: tests/test_cli_commands.py :: test_migrate_up_invokes_alembic_upgrade_head

## v1.0.29
- Backup/restore operability hardening update:
  - added dedicated backup and restore utilities for metadata+storage snapshots
  - refactored backup/restore drill to execute through those utilities
  - added regression test coverage for explicit backup/restore round-trip behavior
  - evidence: DECISIONS.md :: D-0045 Backup/restore toolchain baseline (explicit backup + restore utilities with drill integration and regression tests)
  - evidence: TASKLIST.md :: [x] PR-026 `backup-restore-drill-hardening` (S1)
  - evidence: tests/test_backup_restore_tools.py :: test_backup_and_restore_tools_roundtrip
  - evidence: tests/test_backup_restore_drill.py :: test_backup_restore_drill_passes

## v1.0.30
- Post-PR026 governance and reliability completion update:
  - enforced strict ingest completeness defaults with fail-closed evidence/task behavior
  - added retention policy + purge workflow and separation-of-duties deletion workflow with server-side legal-hold checks
  - added provenance v1 contract and deterministic audit export tool
  - added policy-pack change/approval/rollback lifecycle controls
  - hardened plugin runtime with explicit allowlist + isolated execution path
  - added OpenAPI compatibility gating and deterministic golden-path/e2e regression harness wiring
  - evidence: DECISIONS.md :: D-0046 Strict ingest completeness baseline (team/enterprise default strict mode with fail-closed evidence and blocking quality tasks)
  - evidence: DECISIONS.md :: D-0047 Retention/deletion governance baseline (retention policy + purge controls and separation-of-duties deletion workflow)
  - evidence: DECISIONS.md :: D-0048 Provenance and policy lifecycle baseline (provenance v1 contract, audit export, policy-pack approval/rollback controls)
  - evidence: DECISIONS.md :: D-0049 Plugin security and contract gate baseline (plugin allowlist isolation + OpenAPI compatibility + golden-path regression gate)
  - evidence: TASKLIST.md :: [x] PR-027 `strict-ingest-completeness` (S1)
  - evidence: TASKLIST.md :: [x] PR-034 `e2e-golden-path-regression-gate` (S2)

## v1.0.31
- Team engine + docs finalization update:
  - added optional Trino gateway engine path with DuckDB fallback and SQL safety preserved
  - finalized runbook/readme/docs index for implemented auth, no-bypass, strict ingest, retention/deletion, plugin, and regression gates
  - marked execution board complete through PR-036 while keeping UI intentionally minimal
  - evidence: DECISIONS.md :: D-0050 Team query engine upgrade baseline (gateway trino adapter with duckdb fallback and docs/runbook finalization)
  - evidence: TASKLIST.md :: [x] PR-035 `team-engine-upgrade-path` (S2)
  - evidence: TASKLIST.md :: [x] PR-036 `docs-runbook-security-finalization` (S2)
  - evidence: spec/12_RUNBOOK.md :: Contract and regression gates
  - evidence: README.md :: Implemented Safe Defaults (Current)

## v1.0.32
- Next-wave semantic foundation kickoff:
  - added semantic manifest schema normalization/validation and deterministic checksum utilities
  - added semantic manifest validation tool and wired it into tooling baseline checks
  - implemented control-plane semantic manifest lifecycle (change request, review-gated decision/apply, rollback)
  - added regression tests for semantic schema and semantic lifecycle role/approval/rollback behavior
  - evidence: DECISIONS.md :: D-0051 Semantic manifest foundation baseline (schema validator + review-gated control-plane lifecycle + rollback)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0001 Semantic Manifest Schema + Validator (v1)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0002 Control Plane Semantic Manifest Lifecycle (request/approve/publish/rollback)
  - evidence: tests/test_semantic_schema.py :: test_validate_semantic_manifest_normalizes_and_hashes_deterministically
  - evidence: tests/test_semantic_manifest_lifecycle.py :: test_semantic_manifest_is_approval_gated_and_rollbackable

## v1.0.33
- Next-wave semantic worker bootstrap update:
  - added worker run-type `semantic_bootstrap` and deterministic run-processor dispatch/output refs
  - integrated semantic candidate generation into worker orchestration with immutable evidence bundle linkage
  - added regression tests for semantic bootstrap success, idempotent reruns, and fail-closed empty-catalog behavior
  - evidence: DECISIONS.md :: D-0052 Semantic bootstrap worker-run baseline (deterministic candidate generation with evidence-backed review artifacts)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0003 Worker Semantic Builder (bootstrap manifest from gold/silver + evidence)
  - evidence: tests/test_worker_runner.py :: test_worker_runner_processes_semantic_bootstrap_run
  - evidence: tests/test_worker_runner.py :: test_worker_runner_fails_semantic_bootstrap_without_catalog

## v1.0.34
- Next-wave gateway semantic enforcement update:
  - added gateway semantic binding resolver for active semantic manifests (`semantic_query` -> SQL + dataset bindings)
  - enforced AI-only semantic query requirement and denied raw AI SQL requests by default
  - applied dataset entitlement and workspace-isolation checks over semantic-bound dataset sets
  - added regression coverage for missing manifest, unknown metric, entitlement denial, and semantic-mode workspace mismatch
  - evidence: DECISIONS.md :: D-0053 Gateway semantic-bound AI query baseline (semantic resolver + AI-only semantic-query enforcement)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0004 Gateway Semantic Resolver + semantic-bound AI query mode
  - evidence: tests/test_gateway_dataset_entitlements.py :: test_gateway_denies_ai_semantic_query_without_manifest
  - evidence: tests/test_gateway_workspace_isolation.py :: test_gateway_query_denies_ai_dataset_from_other_workspace

## v1.0.35
- Next-wave template-pack adoption update:
  - added deterministic gold template pack registry (`invoices`, `crm`, `support`) with semantic starter manifests
  - added CLI commands `schemapilot templates list` and `schemapilot templates apply`
  - added regression coverage for deterministic bundle generation and CLI output paths
  - evidence: DECISIONS.md :: D-0054 Gold template pack baseline (invoices/crm/support packs + deterministic CLI bundle generation)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0005 Gold Template Packs (Invoices/CRM/Support) + CLI generator
  - evidence: tests/test_gold_templates.py :: test_generate_gold_template_bundle_is_deterministic
  - evidence: tests/test_cli_commands.py :: test_templates_apply_generates_bundle

## v1.0.36
- Determinism hardening update:
  - replaced randomized ULID suffix generation with lock-protected monotonic counters
  - stabilized same-millisecond run ordering for worker queue processing and semantic bootstrap sequencing
  - evidence: DECISIONS.md :: D-0055 Monotonic ULID generation baseline (per-process ordered ULIDs for deterministic queue execution)
  - evidence: backend/shared_domain/ids.py :: new_ulid
  - evidence: tests/test_worker_runner.py :: test_worker_runner_processes_semantic_bootstrap_run

## v1.0.37
- Document ingestion coverage update:
  - added read-only document discovery connector for `PDF/EML/MBOX` sources
  - added extraction-method aware parsing with confidence scoring and evidence labels
  - enforced fail-closed invalid PDF handling while preserving raw artifacts
  - evidence: DECISIONS.md :: D-0056 Document connector extraction baseline (PDF/EML/MBOX discovery + confidence-scored evidence)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0006 Document Connectors v1 (PDF/EML/MBOX) with extraction evidence scoring
  - evidence: tests/test_documents_extraction_quality.py :: test_ingest_eml_extracts_subject_and_body_with_confidence
  - evidence: tests/test_documents_extraction_quality.py :: test_ingest_pdf_fails_closed_on_invalid_signature

## v1.0.38
- Optional OpenSearch retrieval/index module update:
  - wired gateway retrieval backend switching for `filesystem|opensearch`
  - enforced fail-closed `module_disabled` behavior when OpenSearch backend is not explicitly enabled
  - added boundary-safe worker OpenSearch indexer helpers (no `workers -> gateway` imports)
  - added optional internal-only OpenSearch compose service profile with no bypass port exposure
  - added regression coverage for OpenSearch retrieval and indexer deterministic/error paths
  - evidence: DECISIONS.md :: D-0057 OpenSearch retrieval module baseline (optional gateway backend + internal-only indexing helpers)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0007 Optional OpenSearch Index Module (behind gateway)
  - evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_opensearch_module_disabled_fail_closed
  - evidence: tests/test_retrieval_opensearch.py :: test_search_opensearch_documents_filters_by_allowed_datasets
  - evidence: tests/test_opensearch_indexer.py :: test_build_bulk_payload_is_deterministic_and_sorted

## v1.0.39
- Optional Qdrant vector module update:
  - added shared embeddings-provider loader with fail-closed defaults (`disabled`, optional deterministic `hash`)
  - wired gateway retrieval backend switching for `qdrant` with explicit deny reasons (`module_disabled`, `embedding_provider_disabled`)
  - added worker-side deterministic Qdrant indexing helpers with boundary-safe imports
  - added optional internal-only Qdrant compose service profile with no bypass port exposure
  - added regression coverage for embeddings provider, Qdrant retrieval adapter, and Qdrant indexer deterministic/error paths
  - evidence: DECISIONS.md :: D-0058 Qdrant vector retrieval baseline (optional embeddings provider + internal-only vector index module)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0008 Optional Qdrant Vector Index Module + Embedding Provider Interface
  - evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_qdrant_backend_returns_results
  - evidence: tests/test_embeddings_provider.py :: test_hash_embeddings_provider_is_deterministic
  - evidence: tests/test_retrieval_qdrant.py :: test_search_qdrant_documents_filters_by_allowed_datasets
  - evidence: tests/test_qdrant_indexer.py :: test_build_points_payload_is_deterministic_and_sorted

## v1.0.40
- Retrieval policy parity update:
  - enforced ABAC checks on retrieval requests (`resource_attributes` + mode) across all retrieval backends
  - applied metadata-bound row filtering using server-side dataset sensitivity summaries
  - added retrieval snippet masking parity, including email token masking when email masks are active
  - included applied retrieval filters/masks in provenance/access-decision records for audit parity
  - added regression coverage for ABAC deny and metadata-filter + masking behavior on retrieval outputs
  - evidence: DECISIONS.md :: D-0059 Retrieval ABAC parity baseline (metadata-bound row filters + snippet masking across retrieval backends)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0009 Retrieval Policy Binding Enhancements (metadata-bound filters + masking)
  - evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_denies_abac_region_mismatch
  - evidence: tests/test_gateway_retrieve.py :: test_gateway_retrieval_applies_metadata_row_filter_and_email_mask

## v1.0.41
- Next-wave governance and operability completion update:
  - completed `NW-0010` through `NW-0025` with optional AI service baseline, semantic SQL agent path, deterministic AI eval harness, policy simulation endpoint, query/retrieval budget guards, run scheduling and workspace fairness controls
  - wired secrets-store abstraction into control-plane source credential handling and retained fail-closed behavior
  - completed audit sink plugin wiring and policy-pack invariant test harness integration
  - completed catalog export/import and source SLA endpoints with regression coverage
  - evidence: DECISIONS.md :: D-0060 AI/ops extension baseline (optional AI service + policy simulation + catalog/scheduling/fairness + audit sinks + secrets + Helm hardening)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0010 Optional AI Service Skeleton (provider plugins, disabled-by-default)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0025 Source Health + Freshness SLAs + Alerts
  - evidence: tests/test_ai_eval_harness.py :: test_ai_eval_harness_smoke_passes_and_writes_report
  - evidence: tests/test_gateway_policy_simulation.py :: test_policy_simulation_allows_steward_role

## v1.0.42
- Next-wave completion + AI track closure update:
  - completed `NW-0026` through `NW-0034` and marked AI track `AI-0101`..`AI-0115` complete
  - added first-hour deterministic demo generator (`schemapilot demo-generate` + `tools/demo_scenario_generator.py`)
  - added docs wave (`docs/quickstart/FIRST_HOUR.md`, `docs/security/SECURITY_MODEL.md`, `docs/connectors/CONNECTOR_GUIDE.md`)
  - added pack registry artifacts and lint gate (`packs/registry.json`, `tools/pack_lint.py`)
  - hardened Trino path with retries and cancellation hooks; added maintenance/compaction/anomaly/ERv2/locale-hardening modules
  - added generated Python SDK endpoint artifact + generation check gate (`tools/generate_clients.py --check`)
  - evidence: DECISIONS.md :: D-0061 Completion baseline for NW-0026..NW-0034 and AI track (demo generator, docs wave, pack registry, Trino hardening, compaction, anomaly/ERv2, locale parsing, typed SDK)
  - evidence: TASKLIST_NEXT.md :: [x] NW-0034 Typed client SDKs (Python) generated from OpenAPI + stability gate
  - evidence: TASKLIST_NEXT.md :: [x] AI-0115 AI evaluation generator
  - evidence: tests/test_demo_scenario_generator.py :: test_generate_demo_scenario_writes_expected_files
  - evidence: tests/test_pack_lint.py :: test_validate_pack_registry_passes_for_repo_default
  - evidence: tests/test_gateway_trino_adapter.py :: test_execute_sql_trino_cancels_query_on_timeout
  - evidence: tests/test_anomaly_detection.py :: test_discover_run_creates_anomaly_blocking_task
  - evidence: tests/test_generate_clients.py :: test_render_generated_endpoints_contains_core_paths

## v1.0.43
- Post-milestone lane A kickoff (`TASKLIST_NEXT_V2`) update:
  - implemented `V2-0005` strict config schema v2 with config-file support (`.json` + simple `.yaml`) and fail-closed unknown-key handling
  - added diagnostics redaction contract via `Settings.to_redacted_dict`
  - implemented `V2-0003` deterministic `schemapilot doctor` preflight checks (settings validation, storage/db, migration posture, no-bypass scan, secrets backend availability, JWKS reachability)
  - added regression coverage for config strictness/redaction and doctor preflight/CLI behavior
  - evidence: DECISIONS.md :: D-0062 Config/doctor operability baseline (`V2-0005` strict config schema and `V2-0003` deterministic preflight diagnostics)
  - evidence: TASKLIST_NEXT_V2.md :: [x] V2-0005 Strict config schema v2 (unknown keys fail; config file; redaction contract)
  - evidence: TASKLIST_NEXT_V2.md :: [x] V2-0003 `schemapilot doctor` preflight checks
  - evidence: tests/test_config_loading_v2.py :: test_load_settings_rejects_unknown_config_keys
  - evidence: tests/test_doctor_preflight.py :: test_doctor_preflight_passes_with_valid_local_config
  - evidence: tests/test_cli_commands.py :: test_doctor_command_returns_ok_report_for_valid_config

## v1.0.44
- Post-milestone lane A reliability update (`TASKLIST_NEXT_V2`):
  - completed `V2-0001` by adding durable audit outbox delivery (`audit_outbox_events`) and bounded sink dispatcher retries
  - decoupled optional audit sink outages from core request success while preserving fail-closed local audit persistence
  - added outbox observability metrics (delivery outcomes, backlog, delivery latency)
  - added migration `0002_audit_outbox_events` and advanced non-local required DB revision
  - added regression coverage for outbox dispatch success/failure bounds and sink-outage queue behavior in gateway/control-plane
  - evidence: DECISIONS.md :: D-0063 Audit outbox delivery baseline (`V2-0001` durable sink dispatch decoupling with fail-closed local audit writes)
  - evidence: TASKLIST_NEXT_V2.md :: [x] V2-0001 Audit outbox + sink dispatcher (decouple sinks; preserve fail-closed local audit)
  - evidence: tests/test_audit_outbox.py :: test_dispatch_outbox_writes_jsonl_and_marks_rows_sent
  - evidence: tests/test_audit_sinks.py :: test_webhook_audit_sink_failure_queues_outbox_without_denying_request
  - evidence: tests/test_migrations_enforced.py :: test_non_local_allows_expected_revision_present

## v1.0.45
- Post-milestone operator diagnostics update (`TASKLIST_NEXT_V2`):
  - completed `V2-0002` with run-step DAG persistence (`runs_run_steps`) and step-level status/evidence/error tracking in worker execution
  - exposed run-step visibility through control-plane run responses and a dedicated run-steps endpoint
  - completed `V2-0032` by adding `schemapilot analyze` workspace analytics (policy denials, review backlog, run/run-step health, outbox backlog)
  - completed `V2-0004` by adding `schemapilot diag-bundle` redacted support zip generation
  - advanced non-local required DB revision to `0003_run_step_dag`
  - evidence: DECISIONS.md :: D-0064 Operator diagnostics baseline (`V2-0002`, `V2-0004`, `V2-0032`: run-step DAG visibility + redacted support bundle + workspace analytics CLI)
  - evidence: TASKLIST_NEXT_V2.md :: [x] V2-0002 Run step DAG + step-level evidence/status
  - evidence: TASKLIST_NEXT_V2.md :: [x] V2-0004 `schemapilot diag bundle` (redacted support pack)
  - evidence: TASKLIST_NEXT_V2.md :: [x] V2-0032 Denials + review queue analytics CLI (`schemapilot analyze`)
  - evidence: tests/test_run_steps.py :: test_run_endpoint_includes_step_breakdown_after_success
  - evidence: tests/test_cli_operability_v2.py :: test_analyze_command_reports_denials_and_run_steps
  - evidence: tests/test_cli_operability_v2.py :: test_diag_bundle_command_writes_redacted_zip

## Notes
- This changelog records changes to the SSOT documents in this ZIP, not changes to the implemented repository.

