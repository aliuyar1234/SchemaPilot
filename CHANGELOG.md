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

## Notes
- This changelog records changes to the SSOT documents in this ZIP, not changes to the implemented repository.

