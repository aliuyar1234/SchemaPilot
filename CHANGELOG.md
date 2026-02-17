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

## Notes
- This changelog records changes to the SSOT documents in this ZIP, not changes to the implemented repository.

