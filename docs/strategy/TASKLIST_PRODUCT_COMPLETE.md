# TASKLIST_PRODUCT_COMPLETE.md — SchemaPilot “Product-Complete” Wave (Final Tasklist)

> Zweck: Was noch fehlt, bis SchemaPilot als „produkt-komplett“ gilt.
> Fokusbereiche: Adoption/Time-to-Value, Operability/Reliability, Ecosystem Trust/Supply Chain,
> Enterprise Rollout Readiness, AI Value Layer (Safe-by-Default), Database Builder Abschluss.
>
> Regeln (implizit für alle Tasks):
> - fail-closed by default
> - Gateway bleibt Single Enforcement Point (no bypass)
> - Audit + Provenance Pflicht in kritischen Flows
> - deterministische Pipelines/Artefakte
> - optionale Module disabled-by-default + explicit enable + startup guards
> - CLI-first, UI minimal
>
> Stable IDs: PC-0001… (nicht renumbern). Gruppen: P0/P1/P2.
> Jeder Task enthält: ID, Titel, Why, Scope, Acceptance Criteria, Required Tests, Risks+Rollback, Dependencies.

---

## P0 — Product-Complete Critical Path (muss sitzen)

### Adoption / Time-to-Value

- [x] PC-0001 — “First-hour success” Presets v2 (SharePoint / Dropzone / SMB / Legacy Dump)
  - Why: Maximaler Nutzen <60 Minuten ohne Data Engineer; reduziert Abbruchrate.
  - Scope:
    - cli/init_presets.py
    - cli/init.py
    - backend/control_plane/onboarding_state.py
    - backend/control_plane/review_tasks.py (preset-blockers mapping)
    - packs/ (preset pack definitions, falls vorhanden)
  - Acceptance Criteria:
    - `schemapilot init --preset <name>` führt deterministisch durch: connect → discover → review summary → target-db plan/apply → first query
    - Preset stoppt **immer** bei blocking tasks (PII/drift/migration approvals) und druckt „Next Actions“ + Task IDs.
    - Preset schreibt audit events: `onboarding.preset_started`, `onboarding.preset_completed`, `onboarding.blocked`.
  - Required Tests:
    - e2e: preset happy path (local demo + target db)
    - negative: missing secrets → preset fails closed + doctor hint
    - negative: blocking tasks exist → preset exits non-zero, prints tasks
  - Risks + Rollback:
    - Risiko: Flaky flows → keep deterministic fixtures; heavy e2e in release gate, smoke in CI
    - Rollback: preset feature flag; manual CLI remains
  - Dependencies: PC-0011, PC-0031, PC-0032

- [x] PC-0002 — Enterprise Connector Pack v1 (Jira + Zendesk + Google Drive/SharePoint + SFTP/SMB)
  - Why: Adoption hängt an “works with my stack”.
  - Scope:
    - plugins/jira_connector/
    - plugins/zendesk_connector/
    - plugins/google_drive_connector/ OR plugins/sharepoint_connector/
    - plugins/sftp_connector/
    - plugins/smb_connector/
    - backend/shared_domain/plugin_loader.py (allowlist)
    - tools/connector_conformance.py
  - Acceptance Criteria:
    - Jeder Connector: read-only, deterministic snapshot, strict completeness support, cursor where possible.
    - Jeder Connector erfüllt conformance harness (hard gate).
    - Secrets werden ausschließlich über secrets store refs bezogen; nie geloggt.
  - Required Tests:
    - conformance harness pass pro connector
    - negative: oauth scope missing → fail-closed
    - negative: partial page fetch in strict mode → fail + evidence
    - security: sandbox blocks network/file escape (wenn policy disables)
  - Risks + Rollback:
    - Risiko: OAuth/API volatility → connector disabled-by-default; dropzone export fallback documented
    - Rollback: disable specific connector via allowlist
  - Dependencies: PC-0021, PC-0022, PC-0023

- [x] PC-0003 — Doctor v2 + Guided Remediation (standardisierte Diagnostik + konkrete Fixes)
  - Why: OSS Adoption scheitert an Setup-Friktion; doctor muss “fix-forward” führen.
  - Scope:
    - cli/doctor.py
    - cli/remediate.py (new)
    - backend/shared_domain/config.py
    - deploy/ (compose/helm validations)
    - tools/check_no_bypass_ports.py
  - Acceptance Criteria:
    - `schemapilot doctor` liefert kategorisierte Findings mit Remediation-IDs (DR-####).
    - `schemapilot remediate DR-####` führt sichere, reversible Fixes aus (nur lokal) oder druckt exakte Schritte.
    - Doctor prüft: no-bypass (ports), auth config, migrations, secrets store reachability, target-db health, plugin sandbox settings.
  - Required Tests:
    - unit: remediation mapping deterministic
    - negative: exposed engine port → doctor fail + remediation
    - negative: non-local bind without auth → startup guards fail, doctor explains
  - Risks + Rollback:
    - Risiko: remediation doing unsafe changes → allow only reversible local actions; else print-only
    - Rollback: remediate off by default; doctor only
  - Dependencies: PC-0014, PC-0031

---

### Operability / Reliability

- [x] PC-0004 — Run-Step Failure Taxonomy v1 (einheitliche Codes + Mapping)
  - Why: Ohne stabile Fehlercodes sind Support/KPIs/Runbooks teuer und inkonsistent.
  - Scope:
    - backend/shared_domain/failure_codes.py (new)
    - backend/workers/run_processor.py (emit codes)
    - backend/gateway/* (denials map)
    - backend/control_plane/runs_api.py
    - tools/kpi_extract.py
  - Acceptance Criteria:
    - Canonical failure codes (FC-####) für: secrets, authz, strict completeness, drift, schema mismatch, engine unavailable, timeouts, sandbox violations.
    - Jeder Run-Step hat: `failure_code`, `failure_category`, `operator_hint_ref` (runbook anchor).
    - Codes sind **stabil** (nicht renumbern) und versioniert.
  - Required Tests:
    - unit: mapping functions
    - integration: induced failures result in expected code
    - negative: unknown error must map to `FC-0000_UNKNOWN` + evidence, never silent success
  - Risks + Rollback:
    - Risiko: code churn → lock down list; new codes only append
    - Rollback: keep old strings, add codes additive
  - Dependencies: PC-0012, PC-0035

- [x] PC-0005 — Deterministic Redaction-Safe Support Bundles v2 (diag bundle produktionsreif)
  - Why: Support-Bundles müssen debug-valuable sein ohne Daten/Secrets zu leaken.
  - Scope:
    - cli/diag.py
    - backend/shared_domain/redaction.py
    - backend/control_plane/audit_export.py
    - backend/control_plane/evidence_api.py
    - tools/diag_bundle_verify.py (new)
  - Acceptance Criteria:
    - Bundle enthält: config (redacted), last N runs/steps, failure codes, denial summary, outbox backlog, pack versions, manifest hashes.
    - Bundle enthält **nie** raw data, access tokens, passwords, PII samples.
    - `tools/diag_bundle_verify.py` prüft Bundle auf forbidden patterns.
  - Required Tests:
    - security: secret leak tests (fixtures with fake secrets)
    - negative: attempt include artifacts/raw data → blocked
    - determinism: same inputs → same bundle structure/hashes (excluding runtime timestamps inside evidence, but stable keys)
  - Risks + Rollback:
    - Risiko: over-redaction reduces utility → include evidence references + IDs, not content
    - Rollback: minimal bundle mode
  - Dependencies: PC-0004, PC-0014

- [x] PC-0006 — SLO/SLA Exports v1 (Freshness, Queue, Denials, Review-Latency) CLI-first
  - Why: Teams brauchen “Are we healthy?” ohne UI; Exporte für BI/Alerts.
  - Scope:
    - tools/slo_export.py (new)
    - backend/control_plane/sla_models.py
    - backend/control_plane/review_queue_api.py
    - backend/gateway/metrics_api.py
    - cli/slo.py
  - Acceptance Criteria:
    - `schemapilot slo export --format json|csv` liefert:
      - data freshness per dataset/source
      - run queue depth/age
      - denials by reason
      - review task age (blocking)
      - sync lag
    - Export ist deterministisch sortiert; redaction-safe.
  - Required Tests:
    - unit: stable ordering
    - integration: sample workspace yields expected schema
    - negative: unauthorized role cannot export sensitive breakdown
  - Risks + Rollback:
    - Risiko: metric drift → version export schema, compat tests
    - Rollback: keep minimal export
  - Dependencies: PC-0004, PC-0035

---

### Ecosystem Trust / Supply Chain

- [x] PC-0007 — Enterprise Mode: Signed Packs Mandatory (policy/semantic/templates) + Verify-on-Install
  - Why: Supply chain ist #1 Enterprise blocker.
  - Scope:
    - tools/pack_sign.py
    - tools/pack_verify.py
    - backend/control_plane/packs/*
    - cli/packs.py
    - deploy/ (enterprise mode config)
  - Acceptance Criteria:
    - Enterprise mode: unsigned/tampered packs **block** install/apply.
    - Dev/team mode: warn by default, optional enforce.
    - Audit event emitted for every verify outcome (pass/fail).
  - Required Tests:
    - negative: tampered pack blocked
    - negative: unsigned pack blocked in enterprise
    - determinism: manifest checksum stable for same pack content
  - Risks + Rollback:
    - Risiko: ecosystem friction → provide `schemapilot pack sign --local` workflow
    - Rollback: allow unsigned only in dev
  - Dependencies: PC-0030

- [x] PC-0008 — Enterprise Mode: Signed Plugins Mandatory + Connector Allowlist Integrity
  - Why: Plugins können exfiltrieren; sign/verify + allowlist integrity nötig.
  - Scope:
    - backend/shared_domain/plugin_loader.py
    - tools/plugin_sign.py (new)
    - tools/plugin_verify.py (new)
    - backend/control_plane/plugin_registry.py (new or extend pack registry)
  - Acceptance Criteria:
    - Enterprise mode refuses to load unsigned plugins.
    - Allowlist entries include plugin hash + signature metadata.
    - Startup guard fails if enforcement enabled but verification keys missing.
  - Required Tests:
    - negative: unsigned plugin blocked
    - negative: hash mismatch blocked
    - security: sandbox still enforced (signing does not imply trust)
  - Risks + Rollback:
    - Risiko: dev friction → enforcement off in dev by default
    - Rollback: per-plugin exception only via explicit config + audit
  - Dependencies: PC-0021, PC-0007

- [x] PC-0009 — Connector Conformance as Hard Gate (CI + release gates)
  - Why: Maintainer scalability + reliability.
  - Scope:
    - tools/connector_conformance.py
    - .github/workflows/* (if present)
    - tools/release_gate.py
    - tests/fixtures/connectors/
  - Acceptance Criteria:
    - Every first-party connector must pass conformance in CI.
    - Release gate refuses to publish if any recommended connector fails.
  - Required Tests:
    - harness self-tests + sample failing connector case
  - Risks + Rollback:
    - Risiko: CI time → run full harness in release gate, smoke subset in CI
    - Rollback: staged enforcement per connector tier
  - Dependencies: PC-0004

- [x] PC-0010 — Pack Compatibility Matrix + Migration Tooling (Semantic schema versions)
  - Why: verhindert “pack drift” und breaking changes.
  - Scope:
    - tools/pack_lint.py (extend)
    - tools/pack_migrate.py (new)
    - backend/control_plane/packs/compat.py
    - backend/shared_domain/semantic/schema_versions.py
  - Acceptance Criteria:
    - Pack declares: `semantic_schema_version`, `compat_range`, `migration_available`.
    - Install/apply blocks incompatible packs unless migration executed.
    - Migration produces deterministic diff + evidence bundle.
  - Required Tests:
    - negative: incompatible pack blocked
    - migration: vN→vN+1 deterministic transformation + tests
  - Risks + Rollback:
    - Risiko: tool complexity → start with minimal compat rules + explicit block
    - Rollback: manual migration only with clear error
  - Dependencies: PC-0007, PC-0015

---

### Enterprise Rollout Readiness

- [x] PC-0011 — Dev→Prod Promotion Flow (signed export/import + policy simulation gates)
  - Why: Real enterprise rollout requires reproducible promotion without surprises.
  - Scope:
    - backend/control_plane/export_import.py
    - tools/promotion_bundle.py (new)
    - tools/policy_diff.py
    - cli/promote.py
  - Acceptance Criteria:
    - Export bundle contains: packs versions, configs (redacted), semantic manifests, migration checksums, evidence refs.
    - Bundle is signed; prod import verifies signature; policy simulation diff must pass.
    - Promotion emits attestation record + audit events.
  - Required Tests:
    - negative: unsigned bundle blocked in enterprise
    - negative: policy diff indicates lockout → import blocked
    - determinism: same source => same bundle checksum
  - Risks + Rollback:
    - Risiko: over-blocking → allow staged import “dry-run only” mode
    - Rollback: keep manual export/import behind flags
  - Dependencies: PC-0007, PC-0014

- [x] PC-0012 — Secrets Rotation Drills (target DB + OIDC keys + connector secrets) as Release Criterion
  - Why: Secrets hygiene is table stakes; must be drilled and tested.
  - Scope:
    - backend/shared_domain/secrets_store.py
    - backend/control_plane/target_db_credentials.py
    - backend/workers/db_builder/rotate_creds.py
    - tools/rotation_drill.py (new)
    - deploy/helm/* secrets docs
  - Acceptance Criteria:
    - Rotation drill rotates: gateway reader creds + worker writer creds without downtime; old creds revoked.
    - OIDC JWKS rotation path validated (cache invalidation + fail-closed).
    - Drill produces evidence bundle + pass/fail gate output.
  - Required Tests:
    - integration: rotation success path
    - negative: rotation fails mid-way → system remains consistent (no partial revoke)
  - Risks + Rollback:
    - Risiko: downtime → staged rotation with dual validity window, audited
    - Rollback: abort drill and keep current secrets active
  - Dependencies: PC-0004, PC-0024

- [x] PC-0013 — Break-glass Procedure (TTL + dual approval) + tested drill
  - Why: Ops need exceptions without weakening governance.
  - Scope:
    - backend/control_plane/breakglass.py
    - backend/gateway/policy.py
    - cli/breakglass.py
    - tools/breakglass_drill.py (new)
  - Acceptance Criteria:
    - Break-glass grants temporary attribute/role with max TTL; dual approval in enterprise.
    - Every gateway query under break-glass is tagged in audit/provenance.
    - Auto revoke always occurs; revocation is auditable.
  - Required Tests:
    - negative: TTL exceed blocked
    - negative: unauthorized approve blocked
    - drill: end-to-end grant→query→auto revoke
  - Risks + Rollback:
    - Risiko: abuse → enterprise mode dual control mandatory, strict logging
    - Rollback: disable break-glass globally
  - Dependencies: PC-0014, PC-0035

- [x] PC-0014 — Backup/Restore Recovery Drills as Release Gate (artifacts + metadata + target DB)
  - Why: Production credibility requires repeatable recovery.
  - Scope:
    - tools/backup.py
    - tools/restore.py
    - tools/backup_restore_drill.py
    - backend/shared_domain/artifact_store.py
    - backend/workers/db_builder/* (target db restore)
  - Acceptance Criteria:
    - Drill restores: metadata DB, artifact store pointers, target DB state, packs registry state.
    - Post-restore: gateway query returns expected masked results + provenance.
    - Drill output is evidence-backed and deterministic.
  - Required Tests:
    - release gate: drill run
    - negative: restore missing component → fail-closed, explicit error
  - Risks + Rollback:
    - Risiko: runtime cost → release-only gate; smoke subset in CI
    - Rollback: none; drill is non-prod
  - Dependencies: PC-0031, PC-0032, PC-0005

---

### AI Value Layer (Safe-by-Default)

- [x] PC-0015 — AI Output Contract v2: mandatory Provenance + Citations (gateway-sourced)
  - Why: Vertrauen in AI hängt an nachprüfbaren Quellen.
  - Scope:
    - backend/ai_service/output_contract.py
    - backend/gateway/provenance.py
    - backend/gateway/query_api.py
    - tests/ai/test_ai_citations_required.py
  - Acceptance Criteria:
    - Jede AI Antwort enthält `citations[]` mit stable IDs, dataset/build pointers, query ids.
    - Ohne provenance/citations → AI response fails closed (returns error + guidance).
  - Required Tests:
    - negative: AI tries to answer without citations → blocked
    - security: citations cannot reference unauthorized datasets
  - Risks + Rollback:
    - Risiko: degraded UX → provide “cannot answer safely” response template
    - Rollback: none (core trust)
  - Dependencies: PC-0027, PC-0031

- [x] PC-0016 — AI Gateway Routing Enforcement (no direct engine/index access)
  - Why: No-bypass must extend to AI module.
  - Scope:
    - backend/ai_service/client.py
    - backend/ai_service/tools_registry.py
    - backend/gateway/* (tool endpoints)
    - deploy/ no-bypass checks update for AI
  - Acceptance Criteria:
    - AI module can only call gateway tool endpoints; no direct DB/index credentials exist in AI config.
    - Startup guard fails if AI configured with direct engine endpoints.
  - Required Tests:
    - negative: AI config tries direct engine → fail start
    - integration: AI query uses gateway, produces audit/provenance
  - Risks + Rollback:
    - Risiko: breaking existing dev configs → provide migration notes
    - Rollback: disable AI module (optional)
  - Dependencies: PC-0033

- [x] PC-0017 — Risky AI Actions: proposal-only + approval-gated (schema/policy changes)
  - Why: AI darf nichts mutieren ohne Mensch + Evidence.
  - Scope:
    - backend/ai_service/schema_advisor.py
    - backend/control_plane/review_tasks.py (AI proposal types)
    - backend/control_plane/packs/* (proposal apply)
  - Acceptance Criteria:
    - AI outputs proposals with evidence refs + confidence; never auto-applies.
    - Applying proposal requires explicit review approval and re-validation (policy diff / migration plan checksums).
  - Required Tests:
    - negative: AI cannot call apply endpoints
    - integration: proposal→review→apply flow audited
  - Risks + Rollback:
    - Risiko: users expect automation → clear operator messaging
    - Rollback: disable AI proposals feature
  - Dependencies: PC-0014, PC-0010, PC-0007

- [x] PC-0018 — AI Eval: from Smoke to Regression Suites (MessyBench + policy/semantic cases)
  - Why: Prevent silent degradation; production confidence.
  - Scope:
    - tools/ai_eval_harness.py
    - tools/messybench_harness.py
    - tests/ai/regression_cases/
    - backend/ai_service/eval_runner.py
  - Acceptance Criteria:
    - Regression suite covers: SQL correctness, provenance correctness, policy denial behavior, citation completeness.
    - Release gate blocks on regression failures; baseline capture and no-regression policy.
  - Required Tests:
    - determinism: eval results stable on fixed fixtures
    - negative: AI answer with missing citations fails
  - Risks + Rollback:
    - Risiko: flaky evals → freeze fixtures + deterministic seeds
    - Rollback: run full suite in release gate, smoke in CI
  - Dependencies: PC-0015, PC-0004

---

### Database Builder Abschluss (v1 “done”)

- [x] PC-0019 — DB Builder: Index/Materialization Advisor (approval-gated) + rollback
  - Why: Performance for real usage without unsafe auto-tuning.
  - Scope:
    - backend/workers/db_builder/index_advisor.py
    - backend/workers/db_builder/materialize_manager.py
    - backend/control_plane/review_tasks.py
    - backend/control_plane/publish.py (materialization refs)
  - Acceptance Criteria:
    - Advisor proposes indexes/materializations w/ evidence; apply requires approval; rollback supported.
  - Required Tests:
    - negative: apply without approval blocked
    - integration: index apply then rollback restores baseline
  - Risks + Rollback:
    - Risiko: index bloat → budgets + quotas; operator confirmation
    - Rollback: disable advisor; keep manual indexes
  - Dependencies: PC-0004, PC-0031

- [x] PC-0020 — DB Builder: Multi-target Shadow Cutover (optional) + safe defaults
  - Why: Real enterprises need switching target db without rebuild downtime; optional.
  - Scope:
    - backend/workers/db_builder/cutover.py
    - backend/control_plane/target_db_api.py
    - cli/target_db.py
  - Acceptance Criteria:
    - Shadow target built/validated; approval required; atomic cutover; rollback to previous target.
    - Disabled-by-default.
  - Required Tests:
    - integration: shadow load → cutover → rollback
    - negative: cutover without approval blocked
  - Risks + Rollback:
    - Risiko: complexity → optional module, explicit enable
    - Rollback: keep single target
  - Dependencies: PC-0014, PC-0031, PC-0032

---

## P1 — Completeness & Enterprise Polish (wichtig, aber nach P0)

- [x] PC-0021 — Plugin Signing & Verification Toolchain (dev workflow + enterprise enforcement)
  - Why: Make supply-chain enforceable end-to-end.
  - Scope: tools/plugin_sign.py; tools/plugin_verify.py; backend/shared_domain/plugin_loader.py; docs
  - Acceptance: plugins verified w/ hash+sig; enterprise blocks unsigned
  - Tests: tamper blocked; missing key blocks when enforce enabled
  - Risks/Rollback: local dev friction; allow dev mode
  - Dependencies: PC-0008

- [x] PC-0022 — Connector Tiering (recommended vs community) + gating policy
  - Why: Users need trust signal.
  - Scope: backend/control_plane/plugin_registry.py; tools/connector_conformance.py; docs
  - Acceptance: connectors labeled; only “recommended” require strict gates
  - Tests: tier metadata validated; enforcement works
  - Risks/Rollback: governance complexity; keep minimal tiers
  - Dependencies: PC-0009

- [x] PC-0023 — Connector Error Budgeting + bounded retries (standard wrapper)
  - Why: Avoid runaway retries, improve reliability.
  - Scope: backend/workers/connectors/wrapper.py; backend/shared_domain/retry_policy.py
  - Acceptance: bounded retries/timeouts; failure codes mapped; no infinite loops
  - Tests: negative: forced failure stops; metrics emitted
  - Risks/Rollback: might reduce success in flaky env; adjustable config
  - Dependencies: PC-0004

- [x] PC-0024 — Secrets Store Backends: Vault + File + K8s Secret (uniform interface) + rotation hooks
  - Why: Enterprise compatibility.
  - Scope: backend/shared_domain/secrets_store.py; deploy/helm; cli/secrets.py
  - Acceptance: backend selection via config; disabled-by-default non-local; rotation hooks exist
  - Tests: negative: enabled backend missing config -> fail start
  - Risks/Rollback: complexity; keep one default backend
  - Dependencies: PC-0012

- [x] PC-0025 — Policy/Pack “Canary Apply” mode (shadow simulation) (optional)
  - Why: Reduce lockout risk further.
  - Scope: backend/control_plane/packs/apply.py; backend/gateway/policy_simulation.py
  - Acceptance: canary mode runs simulation + produces diff; requires approval to promote
  - Tests: negative: canary detects violation -> blocks
  - Risks/Rollback: optional only
  - Dependencies: PC-0014, PC-0007

- [x] PC-0026 — Governance Exports: auditor bundle (no data) (signed optional)
  - Why: Enterprise audits.
  - Scope: tools/auditor_export.py; backend/control_plane/audit_export.py
  - Acceptance: exports policy decisions, pack versions, attestations, lineage refs; no data
  - Tests: unauthorized denied; redaction enforced
  - Risks/Rollback: none (export-only)
  - Dependencies: PC-0011, PC-0014

- [x] PC-0027 — Provenance v2: unify artifacts + target-db + AI citations (schema bump)
  - Why: End-to-end traceability needs a single shape.
  - Scope: backend/shared_domain/provenance.py; backend/gateway/provenance.py; backend/ai_service/output_contract.py
  - Acceptance: provenance includes engine type, build id, target schema ref, evidence bundle refs; stable schema versioning
  - Tests: compat tests; regression on v1 fields
  - Risks/Rollback: schema churn; keep v1 alongside v2 for a deprecation window
  - Dependencies: PC-0004, PC-0015

- [x] PC-0028 — “Denials & Review” CLI analytics (stuck reasons, top blockers, suggested next action)
  - Why: Operator value without UI.
  - Scope: cli/analyze.py; tools/kpi_extract.py; backend/control_plane/review_queue_api.py
  - Acceptance: CLI prints top denials, oldest blocking tasks, recommended remediations, SLO export link
  - Tests: redaction; role-based access
  - Risks/Rollback: none
  - Dependencies: PC-0006, PC-0004

- [x] PC-0029 — Reference Deployments + Upgrade Playbooks (compose + helm) as release artifacts
  - Why: Widely usable OSS needs boring installs.
  - Scope: deploy/; docs/; tools/release_gate.py
  - Acceptance: cleanroom installs validated; upgrade path documented; doctor expectations in docs
  - Tests: release gate cleanroom + upgrade smoke
  - Risks/Rollback: docs drift; tie to e2e outputs
  - Dependencies: PC-0009

---

## P2 — Optional/Advanced (nur wenn Bedarf)

- [x] PC-0030 — SBOM + Image Signing + Provenance Attestation (release only)
  - Why: supply-chain enterprise requirements
  - Scope: tools/release_gate.py; CI workflows; deploy/
  - Acceptance: SBOM generated; images signed; attestations produced; verified in gate
  - Tests: tamper fails verification
  - Risks/Rollback: CI complexity; gate only
  - Dependencies: —

- [x] PC-0031 — “No bypass” enforcement extensions (PGWire, target-db, indexes, AI)
  - Why: new surfaces must not create bypass
  - Scope: tools/check_no_bypass_ports.py; deploy/; backend/gateway/pgwire/; backend/ai_service/
  - Acceptance: checks catch any non-gateway exposure; doctor reports; startup guards
  - Tests: negative deploy fixtures fail check
  - Risks/Rollback: none
  - Dependencies: —

- [x] PC-0032 — Policy-aware Query Cache hardening (cross-actor non-leak) (optional)
  - Why: performance without leaks
  - Scope: backend/gateway/cache.py; backend/gateway/policy.py; tests/security/
  - Acceptance: cache key includes actor attrs + policy version + build id; default off
  - Tests: cross-actor leak tests; publish invalidation tests
  - Risks/Rollback: leakage risk; keep off by default
  - Dependencies: PC-0027

- [x] PC-0033 — AI Retrieval Hardening: metadata-bound retrieval only (no freeform)
  - Why: prevent prompt injection / unauthorized retrieval
  - Scope: backend/ai_service/retrieval_tools.py; backend/gateway/retrieval_api.py
  - Acceptance: AI retrieval must specify dataset ids; gateway enforces entitlements; citations mandatory
  - Tests: unauthorized dataset denied; injection attempts ignored
  - Risks/Rollback: disable retrieval tool
  - Dependencies: PC-0016, PC-0015

- [x] PC-0034 — Large-file streaming + backpressure standardization across connectors
  - Why: reduce OOM and improve reliability
  - Scope: backend/workers/connectors/*; backend/shared_domain/streaming_io.py
  - Acceptance: no connector reads whole file into memory; progress evidence emitted
  - Tests: simulated large file; network drop/resume
  - Risks/Rollback: fallback to old path in dev only
  - Dependencies: PC-0002

- [x] PC-0035 — KPI Baseline Capture + No-regression gates (perf + ai + determinism)
  - Why: keep product stable as ecosystem grows
  - Scope: tools/kpi_extract.py; tools/perf_harness.py; tools/ai_eval_harness.py; tools/release_gate.py
  - Acceptance: baseline captured; regressions require decision + evidence; release gate blocks uncontrolled regression
  - Tests: regression fixture triggers fail
  - Risks/Rollback: slower releases; limit to release gates
  - Dependencies: PC-0018, PC-0006
Exakte PR-Sequenz (PR-001 … PR-030+) zur Abarbeitung dieser Tasklist
Ziel: klein, merge-bar, unabhängige PRs; jede PR hat Minimal-Checks.
Minimal-Checks (immer):
pytest -q
boundary check (z. B. python tools/check_boundary_fitness.py)
tooling baseline check (z. B. python tools/check_tooling_baseline.py)
Zusatzchecks je nach Scope: OpenAPI compat, no-bypass, e2e smoke, conformance, fuzz/chaos/drills.
PR-001 — PC-0004 Failure Codes v1 (shared_domain + mapping skeleton)
Checks: minimal + unit mapping suite
PR-002 — PC-0007 Pack signing/verify tooling (no enforcement yet)
Checks: minimal + pack verify unit tests
PR-003 — PC-0007 Enterprise enforcement verify-on-install (feature flag)
Checks: minimal + negative tamper tests
PR-004 — PC-0009 Conformance harness hard gate (tool + CI hook)
Checks: minimal + harness self-tests
PR-005 — PC-0008 Plugin signing/verify skeleton + loader hooks (no enforcement yet)
Checks: minimal + negative hash mismatch tests
PR-006 — PC-0008 Enterprise plugin enforcement + startup guards
Checks: minimal + startup guard tests
PR-007 — PC-0005 Support bundle v2: redaction upgrades + verify tool
Checks: minimal + secrets/PII leak tests
PR-008 — PC-0006 SLO export schema v1 + tool scaffold
Checks: minimal + export ordering tests
PR-009 — PC-0006 Wire up SLO export endpoints + CLI command
Checks: minimal + OpenAPI compat + role-based tests
PR-010 — PC-0009 doctor v2 scaffold + remediation IDs mapping
Checks: minimal + negative config tests
PR-011 — PC-0003 Guided remediation CLI (schemapilot remediate) (print-only first)
Checks: minimal
PR-012 — PC-0003 doctor: no-bypass + auth/migrations + target-db health checks
Checks: minimal + python tools/check_no_bypass_ports.py
PR-013 — PC-0011 Promotion bundle schema + signing/verify (dry-run)
Checks: minimal + negative unsigned bundle tests
PR-014 — PC-0011 Import with policy simulation gate (block on lockout)
Checks: minimal + policy diff tests
PR-015 — PC-0012 Rotation drill tool scaffold + target-db creds rotation integration
Checks: minimal + integration rotation tests
PR-016 — PC-0013 Break-glass core models + CP endpoints (disabled-by-default)
Checks: minimal + OpenAPI compat + authz tests
PR-017 — PC-0013 Break-glass drill tool + audit/provenance tagging tests
Checks: minimal + drill unit/integration
PR-018 — PC-0014 Backup/restore drill expanded acceptance assertions (release gate wiring)
Checks: minimal + release-gate-only drill
PR-019 — PC-0015 AI output contract v2 (citations mandatory)
Checks: minimal + AI negative tests
PR-020 — PC-0016 AI gateway routing enforcement + startup guards
Checks: minimal + no-bypass + negative config tests
PR-021 — PC-0018 AI eval regression suite harness expansion + gating
Checks: minimal + deterministic eval fixture
PR-022 — PC-0001 Presets v2 (dropzone-team preset first)
Checks: minimal + e2e smoke
PR-023 — PC-0004 Presets v2 (sharepoint-team preset)
Checks: minimal + e2e smoke (mock if needed)
PR-024 — PC-0002 Connector pack: SFTP + SMB (conformance hard gate)
Checks: minimal + conformance
PR-025 — PC-0002 Connector pack: Jira
Checks: minimal + conformance
PR-026 — PC-0002 Connector pack: Zendesk
Checks: minimal + conformance
PR-027 — PC-0010 Pack compat matrix + migration tooling (minimal rules)
Checks: minimal + compat negative tests
PR-028 — PC-0027 Provenance v2 (dual-emit v1+v2 with deprecation window)
Checks: minimal + compat suite
PR-029 — PC-0019 Index/materialization advisor (proposal-only + approval gated)
Checks: minimal + approval negative tests
PR-030 — PC-0020 Multi-target cutover (optional module)
Checks: minimal + integration cutover smoke (release gate)
(Optional, wenn ihr es wirklich braucht: SBOM/signing/attestations, cache hardening, PGWire etc. sind als eigene PRs in P2 vorgesehen.)
Essential Open Questions (nur nötig) + konservative Defaults
Q1 (non-blocking): Welche Connectoren sind „must-have“ für euren ICP (Jira vs ServiceNow vs SAP)?
Default: Jira + Zendesk + SharePoint + SMB/SFTP + Dropzone als Minimum-Set.
Q2 (non-blocking): Enterprise enforcement: pack/plugin signing sofort mandatory oder staged?
Default: Enterprise = mandatory, Dev/Team = warn-only (opt-in enforce).
Q3 (non-blocking): Promotion-flow: welche Artefakte dürfen exportiert werden (no data vs masked samples)?
Default: no data; nur metadata + evidence refs + attestations.
Q4 (non-blocking): Break-glass: dual approval immer oder nur enterprise?
Default: enterprise dual approval; team optional single approval, aber immer TTL + audit tags.
