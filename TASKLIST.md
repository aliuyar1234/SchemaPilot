# SchemaPilot Execution Board

This is the active implementation queue.  
Priority rule: security + backend pipeline + deploy reliability first.  
UI is intentionally low priority until core flows are production-safe.

Status legend: `[ ]` pending, `[~]` in progress, `[x]` completed.

## Now (Sprint 1: S0 blockers)

### [x] PR-001 `control-plane-auth-deny-by-default`
- Owner: `backend/security`
- Scope:
  - `backend/control_plane/app.py`
  - `backend/shared_domain/config.py`
  - `backend/shared_domain/auth.py` (new)
  - `tests/test_control_plane_auth.py` (new)
- Done when:
  - Mutating Control Plane endpoints require valid auth.
  - Role checks enforced for privileged actions.
  - Missing/invalid auth fails closed.

### [x] PR-002 `gateway-sql-safety-guardrails`
- Owner: `backend/gateway`
- Scope:
  - `backend/gateway/executor.py`
  - `backend/gateway/app.py`
  - `tests/test_gateway_sql_safety.py` (new)
- Done when:
  - Non-read SQL is denied.
  - Dangerous SQL keywords are denied.
  - Timeout + max-row protections are enforced.

### [x] PR-003 `gateway-sql-dataset-entitlements`
- Owner: `backend/gateway`
- Scope:
  - `backend/gateway/app.py`
  - `backend/gateway/policy.py`
  - `tests/test_gateway_dataset_entitlements.py` (new)
- Done when:
  - AI SQL queries require `dataset_id`.
  - AI actors are denied for datasets outside `allowed_dataset_ids`.
  - Audit/provenance includes dataset entitlement decision.

### [x] PR-004 `port-and-endpoint-conventions`
- Owner: `platform/backend`
- Scope:
  - `backend/control_plane/main.py`
  - `backend/gateway/main.py`
  - `cli/schemapilot_cli/main.py`
  - `deploy/docker-compose.yml`
- Done when:
  - Canonical defaults are consistent: Control Plane `8000`, Gateway `8001`.
  - CLI defaults match runtime defaults.

### [x] PR-005 `runnable-compose-profile-team`
- Owner: `platform/deploy`
- Scope:
  - `deploy/docker-compose.yml`
  - `deploy/Dockerfile.control-plane` (new)
  - `deploy/Dockerfile.gateway` (new)
  - `deploy/README.md`
- Done when:
  - Team profile starts real services (no placeholder sleep commands).
  - Unsafe direct data-plane exposure is not enabled by default.
  - Quickstart path works on clean machine.

Current state:
- Dockerfiles and compose service wiring are implemented.
- Background worker container wiring is now included (`deploy/Dockerfile.worker`, `worker` service in compose).
- Compose profile resolves via `docker compose --profile starter config`.
- Compose smoke executed with Docker daemon:
  - `docker compose -f deploy/docker-compose.yml --profile starter up -d --build` succeeded.
  - Control Plane and Gateway health endpoints returned `ok`.
  - Control Plane auth was fail-closed (`403` without token, `200` with valid local token).
  - Stack shut down cleanly with `docker compose ... down`.

## Next (Sprint 2: make pipeline real)

### [x] PR-006 `shared-metadata-models-refactor`
- Owner: `backend/platform`
- Scope:
  - `backend/shared_domain/metadata_models.py` (new)
  - `backend/control_plane/repository.py`
  - `backend/control_plane/review_repository.py`
  - `tools/check_boundary_fitness.py`
- Done when:
  - Worker services can use metadata models without boundary violations.

### [x] PR-007 `worker-runner-service`
- Owner: `backend/workers`
- Scope:
  - `backend/workers/service.py` (new)
  - `backend/workers/run_processor.py` (new)
  - `tests/test_worker_runner.py` (new)
- Done when:
  - Queued runs are processed with deterministic status transitions.

### [x] PR-008 `discover-to-catalog-pipeline`
- Owner: `backend/workers`
- Scope:
  - `backend/workers/connectors/*`
  - `backend/workers/bronze.py`
  - `backend/workers/profiler.py`
  - `backend/control_plane/app.py` (dataset endpoints)
  - `tests/test_pipeline_discover_catalog.py` (new)
- Done when:
  - Discover runs produce real catalog datasets and profiling artifacts.

### [x] PR-009 `evidence-bundle-store`
- Owner: `backend/governance`
- Scope:
  - `backend/shared_domain/evidence_store.py` (new)
  - `backend/control_plane/app.py`
  - `tests/test_evidence_store.py` (new)
- Done when:
  - Review tasks/proposals point to immutable, retrievable evidence bundles.

### [x] PR-010 `pii-to-review-queue`
- Owner: `backend/governance`
- Scope:
  - `backend/workers/pii.py`
  - `backend/workers/run_processor.py`
  - `backend/control_plane/review_repository.py`
  - `tests/test_pipeline_pii_review.py` (new)
- Done when:
  - High-risk PII detections create blocking review tasks automatically.

### [x] PR-011 `contracts-and-quarantine-hard-gate`
- Owner: `backend/reliability`
- Scope:
  - `backend/workers/contracts.py`
  - `backend/control_plane/gating.py`
  - `tests/test_contracts_block_publish.py` (new)
- Done when:
  - Failed quality contracts block publish and generate actionable signals.

### [x] PR-012 `gold-publish-and-rollback`
- Owner: `backend/reliability`
- Scope:
  - `backend/workers/gold.py`
  - `backend/control_plane/app.py`
  - `tests/test_gold_publish_rollback.py` (new)
- Done when:
  - Publish pointer supports last-known-good rollback with full audit.

### [x] PR-013 `gateway-duckdb-read-path`
- Owner: `backend/gateway`
- Scope:
  - `backend/gateway/executor.py`
  - `backend/gateway/app.py`
  - `tests/test_gateway_duckdb_readonly.py` (new)
- Done when:
  - Gateway serves read-only queries from published gold artifacts safely.

## Later (Sprint 3+: scale and ecosystem)

### [x] PR-014 `drift-into-ops-loop`
- Owner: `backend/workers`
- Scope:
  - `backend/workers/drift.py`
  - `backend/workers/run_processor.py`
  - `tests/test_drift_blocks_publish.py` (new)

### [x] PR-015 `plugin-loader-runtime`
- Owner: `backend/platform`
- Scope:
  - `backend/shared_domain/plugin_loader.py` (new)
  - `backend/workers/connectors/*`
  - `tests/test_plugin_loader.py` (new)

### [x] PR-016 `kpi-auto-extraction`
- Owner: `platform/ops`
- Scope:
  - `tools/kpi_extract.py` (new)
  - `tools/kpi_tracker.py`
  - `deploy/dashboards/schemapilot_overview.json`
  - `tests/test_kpi_extract.py` (new)

### [x] PR-017 `oss-community-basics`
- Owner: `docs/community`
- Scope:
  - `LICENSE` (new)
  - `CONTRIBUTING.md` (new)
  - `.github/ISSUE_TEMPLATE/*` (new)
  - `.github/pull_request_template.md` (new)

### [x] PR-018 `ui-wizard-upgrade` (low priority by design)
- Owner: `ui`
- Scope:
  - `ui/src/App.tsx`
  - `ui/src/App.test.tsx`
- Note:
  - Kept intentionally thin while backend/governance paths remain primary.
  - Expanded UI behavioral coverage in `ui/src/App.test.tsx` (3 tests total).

## Release Gate For Any PR

- `python tools/check_tooling_baseline.py` passes.
- `python tools/verify_manifest.py` passes.
- New critical-path behavior has negative-path tests.
- Boundary fitness remains green.
