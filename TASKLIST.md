# SchemaPilot Execution Board (Post PR-018)

This is the active implementation queue from the current baseline (`902238d`).

Rules:
- Security/governance correctness first.
- Backend determinism and deploy safety second.
- No architecture rewrites.
- UI must stay minimal (only unblocker-level changes).
- No timeline planning; execution order only.

Status legend: `[ ]` pending, `[~]` in progress, `[x]` completed.

## Completed Baseline

- [x] PR-001 .. PR-018 complete.
- [x] Core hardening, worker orchestration, evidence store, publish/rollback, DuckDB read path, plugin runtime, KPI extraction, deploy Dockerfiles, OSS templates.

## Active Queue (Execute In Order)

### [x] PR-019 `gateway-oidc-jwt-verification` (S0)
- Task IDs: `T-0201`
- Scope:
  - `backend/shared_domain/auth.py` or `backend/shared_domain/auth/*`
  - `backend/gateway/app.py`
  - `backend/shared_domain/config.py`
  - `tests/test_gateway_oidc_jwt_auth.py` (new)
- Done when:
  - Gateway supports `auth_mode=oidc_jwt` (JWKS verification).
  - Invalid/expired/wrong issuer-or-audience tokens are denied.
  - JWKS unavailable with no valid cache denies requests (fail-closed).

### [x] PR-020 `control-plane-oidc-jwt-verification` (S0)
- Task IDs: `T-0202`
- Scope:
  - `backend/control_plane/app.py`
  - `backend/shared_domain/auth.py` or `backend/shared_domain/auth/*`
  - `backend/shared_domain/config.py`
  - `tests/test_control_plane_oidc_jwt_auth.py` (new)
- Done when:
  - Control Plane supports `auth_mode=oidc_jwt`.
  - Non-local bind fails startup if auth is not configured safely.
  - Mutating endpoints remain deny-by-default with role checks.

### [x] PR-021 `deploy-no-bypass-enforcement` (S0)
- Task IDs: `T-0203`
- Scope:
  - `deploy/docker-compose.yml`
  - `deploy/k8s/*` or `deploy/helm/*`
  - `tools/check_no_bypass_ports.py` (new)
  - `tests/test_no_bypass_deploy_artifacts.py` (new)
- Done when:
  - Query engines/indexes are never exposed directly in default deploy paths.
  - Static checks fail CI on bypass port exposure.

### [x] PR-022 `audit-fail-closed-critical-flows` (S0)
- Task IDs: `T-0204`
- Scope:
  - `backend/shared_domain/audit_models.py` and audit write path
  - `backend/gateway/app.py`
  - `backend/control_plane/app.py`
  - `tests/test_audit_fail_closed.py` (new)
- Done when:
  - Critical operations deny/abort if audit writes fail.
  - Failures are observable in metrics/logs with stable error codes.

### [x] PR-023 `gateway-workspace-isolation` (S0)
- Task IDs: `T-0205`
- Scope:
  - `backend/gateway/app.py`
  - `backend/gateway/policy.py`
  - `backend/gateway/abac.py`
  - `tests/test_gateway_workspace_isolation.py` (new)
- Done when:
  - Cross-workspace SQL/retrieval access is denied.
  - Workspace scope is included in access decision evidence.

### [x] PR-024 `gateway-rate-limit-and-cancel` (S1)
- Task IDs: `T-0206`
- Scope:
  - `backend/gateway/app.py`
  - `backend/gateway/executor.py`
  - `backend/shared_domain/observability.py`
  - `tests/test_gateway_rate_limits.py` (new)
- Done when:
  - Per-actor rate/concurrency limits are enforced.
  - Timeout/cancellation paths are enforced and audited.

### [x] PR-025 `migrations-enforced-at-startup` (S1)
- Task IDs: `T-0207`
- Scope:
  - `backend/control_plane/main.py`
  - `backend/gateway/main.py`
  - `backend/shared_domain/db.py` (or equivalent startup DB module)
  - `cli/schemapilot_cli/main.py`
  - `tests/test_migrations_enforced.py` (new)
- Done when:
  - Non-dev startup requires expected Alembic revision.
  - No unsafe auto-`create_all` behavior in non-dev paths.

### [x] PR-026 `backup-restore-drill-hardening` (S1)
- Task IDs: `T-0208`
- Scope:
  - `tools/backup_restore_drill.py`
  - `tools/backup.py` / `tools/restore.py` (new if needed)
  - `spec/12_RUNBOOK.md`
  - `tests/test_backup_restore_tools.py` (new)
- Done when:
  - Metadata + artifacts restore path is automated and repeatable.
  - Drill produces machine-readable pass/fail evidence.

### [x] PR-027 `strict-ingest-completeness` (S1)
- Task IDs: `T-0209`
- Scope:
  - `backend/workers/run_processor.py`
  - `backend/workers/connectors/*`
  - `backend/workers/bronze.py`
  - `backend/shared_domain/evidence_store.py`
  - `tests/test_strict_ingest_completeness.py` (new)
- Done when:
  - Strict mode fails run on unreadable/unparseable discovered items.
  - Evidence bundle records completeness failures; publish remains blocked.

### [x] PR-028 `retention-purge-engine` (S1)
- Task IDs: `T-0210`
- Scope:
  - `backend/control_plane/app.py`
  - `backend/shared_domain/metadata_models.py`
  - `backend/workers/*` (retention/purge worker path)
  - `tests/test_retention_purge_fail_closed.py` (new)
- Done when:
  - Retention remains disabled-by-default.
  - Enabled purge path is explicit, auditable, and fail-closed.

### [x] PR-029 `deletion-separation-of-duties` (S1)
- Task IDs: `T-0211`
- Scope:
  - `backend/control_plane/deletion.py`
  - `backend/control_plane/app.py`
  - `backend/shared_domain/metadata_models.py`
  - `tests/test_deletion_separation_of_duties.py` (new)
- Done when:
  - Requester cannot self-approve deletion.
  - Legal hold is server-side truth and blocks execution.
  - Deletion flow remains disabled-by-default unless explicitly enabled.

### [x] PR-030 `provenance-schema-v1-and-audit-export` (S1)
- Task IDs: `T-0213`
- Scope:
  - `backend/gateway/app.py`
  - `backend/shared_domain/*` (provenance contract module)
  - `tools/audit_export.py` (new)
  - `tests/test_provenance_schema_stability.py` (new)
- Done when:
  - Versioned provenance schema is stable and tested.
  - Audit export format is deterministic and documented.

## Backlog (After PR-030)

### [x] PR-031 `policy-pack-lifecycle-controls` (S1)
- Task IDs: `T-0214`
- Scope:
  - `backend/control_plane/*` (policy pack service + approval path)
  - `backend/shared_domain/policy_packs.json`
  - `tests/test_policy_pack_change_gating.py` (new)

### [x] PR-032 `plugin-security-hardening` (S2)
- Task IDs: `T-0215`
- Scope:
  - `backend/shared_domain/plugin_loader.py`
  - `backend/workers/connectors/*`
  - `tests/test_plugin_allowlist.py` (new)

### [x] PR-033 `openapi-and-compat-gate` (S2)
- Task IDs: `T-0216`
- Scope:
  - `backend/control_plane/app.py`
  - `backend/gateway/app.py`
  - `tools/check_openapi_compat.py` (new)
  - `tests/test_openapi_contracts.py` (new)

### [x] PR-034 `e2e-golden-path-regression-gate` (S2)
- Task IDs: `T-0217`
- Scope:
  - `tools/e2e_golden_path.py` (new)
  - `tools/messybench_harness.py`
  - `tests/test_e2e_golden_path_smoke.py` (new)

### [x] PR-035 `team-engine-upgrade-path` (S2)
- Task IDs: `T-0212`
- Scope:
  - `backend/gateway/executor.py` and optional `backend/gateway/executor_trino.py`
  - `backend/workers/silver.py`, `backend/workers/gold.py`
  - `deploy/docker-compose.yml`
  - `tests/test_gateway_trino_adapter.py` (new)
- Note:
  - Must preserve no-bypass invariant and keep DuckDB fallback path.

### [x] PR-036 `docs-runbook-security-finalization` (S2)
- Task IDs: `T-0218`
- Scope:
  - `README.md`
  - `spec/12_RUNBOOK.md`
  - `docs/runbook/*`
- Note:
  - UI updates remain minimal and documentation-only unless a core blocker appears.

## Quality Gate For Every PR

- `python tools/check_tooling_baseline.py` passes.
- `python tools/verify_manifest.py` passes.
- `python tools/check_boundary_fitness.py` passes.
- New critical-path behavior has negative-path tests.

## Legacy Evidence Anchors

These anchors are kept for SSOT reference integrity from historical changelog/decision entries.

- Now (Sprint 1: S0 blockers)
- PR-006 `shared-metadata-models-refactor`
- [x] PR-005 `runnable-compose-profile-team`
- [x] PR-007 `worker-runner-service`
- [x] PR-008 `discover-to-catalog-pipeline`
- [x] PR-009 `evidence-bundle-store`
- [x] PR-010 `pii-to-review-queue`
- [x] PR-011 `contracts-and-quarantine-hard-gate`
- [x] PR-012 `gold-publish-and-rollback`
- [x] PR-013 `gateway-duckdb-read-path`
- [x] PR-014 `drift-into-ops-loop`
- [x] PR-015 `plugin-loader-runtime`
- [x] PR-016 `kpi-auto-extraction`
- [x] PR-017 `oss-community-basics`
- [x] PR-018 `ui-wizard-upgrade` (low priority by design)
