# spec/11_QUALITY_GATES.md

## Quality Attribute Contract Coverage

This document defines acceptance gates enforcing the Quality Attribute Profile in spec/00.
evidence: spec/00_PROJECT_FINGERPRINT.md :: Quality Attribute Profile (QAC)

## No Evidence, No Accept / No Progress

A change is acceptable only if:
- the relevant gates are PASS,
- evidence is recorded (CI artifacts, logs, reports, screenshots, run outputs),
- PROGRESS.md contains evidence pointers for any DONE tasks.

This rule is enforced via PR checklist and checks:
- evidence: templates/PR_REVIEW_CHECKLIST.md :: No Evidence, No Accept
- evidence: checks/CHECKS_INDEX.md :: CHK-EVIDENCE-POINTER-FORMAT

## Gate Index

Security
- G-SEC-0001 Safe Startup Defaults
- G-SEC-0002 Gateway Non-Bypass
- G-SEC-0003 Deny-By-Default Policy
- G-SEC-0004 Plugin Safety

Performance
- G-PERF-0001 Performance Harness and No Regression

Reliability
- G-REL-0001 Safe Failure Modes
- G-REL-0002 Deterministic Builds
- G-REL-0003 Negative Path Coverage
- G-REL-0004 Gold Fail-Closed Publication

Operability
- G-OPS-0001 Runbook Complete
- G-OPS-0002 Backup Restore Drills

Maintainability
- G-MAINT-0001 Boundary Fitness
- G-MAINT-0002 Evidence Completeness
- G-MAINT-0003 Duplication Control

Compatibility/Upgradability
- G-COMP-0001 Migration Safety
- G-COMP-0002 Contract Compatibility
- G-COMP-0003 Profile Upgrade Safety

## Gates

### G-SEC-0001 Safe Startup Defaults

Why: Prevent accidental exposure and unsafe defaults.

How to verify:
- Start services with default config; confirm they bind localhost-only.
- Configure non-local bind without auth; confirm service fails to start with explicit error.
- Configure non-local bind with auth enabled; confirm service starts and rejects unauthenticated requests.

Pass/fail:
- PASS if behavior matches the rules above across API and gateway.
- FAIL otherwise.

Evidence:
- Record test outputs and config snippets in the implementation repo; link via PROGRESS evidence pointers.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-SEC-STARTUP

---

### G-SEC-0002 Gateway Non-Bypass

Why: Ensure single enforcement point.

How to verify:
- Attempt direct network access to query engine/index from a client container; must fail.
- Attempt to use engine client libraries from non-gateway code paths; must be blocked by boundary checks.
- E2E test shows all access goes through gateway and includes AccessDecision + provenance.

Pass/fail:
- PASS if bypass is not possible in production profile configurations and tests.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS
- evidence: checks/CHECKS_INDEX.md :: CHK-NONBYPASS-E2E

---

### G-SEC-0003 Deny-By-Default Policy

Why: Reduce risk from missing policies or misconfig.

How to verify:
- With empty policy set:
  - AI tool identity must be denied for any data query.
  - Human identities are denied unless explicitly allowed.
- Policy engine outage in Enterprise results in deny for protected operations.

Pass/fail:
- PASS if deny is the default outcome for protected operations.
- FAIL if any access is permitted implicitly.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-POLICY-DENY-BY-DEFAULT

---

### G-SEC-0004 Plugin Safety

Why: Plugins are a supply-chain and privilege risk.

How to verify:
- Plugin allowlist enforcement: unallowlisted plugins are not loaded.
- Plugins run with restricted capabilities (no network by default; connector plugins cannot execute SQL).
- Plugin integrity checks (signing or hash allowlist) exist for Enterprise.

Pass/fail:
- PASS if unallowlisted plugins cannot run and capability restrictions are enforced.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-SUPPLY-CHAIN

---

### G-PERF-0001 Performance Harness and No Regression

Why: Avoid guessing absolute targets while preventing regressions.

How to verify:
- A repeatable perf harness exists with:
  - fixed datasets (MessyBench subset),
  - fixed query set,
  - fixed profiling budgets.
- CI captures baseline metrics and compares PR runs.
- Regressions require an explicit decision record and mitigation plan.

Pass/fail:
- PASS if harness exists and CI blocks regressions without decision + mitigation.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-PERF-HARNESS

---

### G-REL-0001 Safe Failure Modes

Why: External I/O and drift must not cause unsafe side effects.

How to verify:
- Extraction failures store raw and create review tasks; no partial publish.
- Connector failures are bounded and visible; runs fail with explicit status and audit events.
- Retry policy is bounded; no infinite retries.

Pass/fail:
- PASS if failures are explicit and bounded with no unsafe side effects.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-ERROR-PATHS

---

### G-REL-0002 Deterministic Builds

Why: Reproducibility and auditability depend on deterministic transforms.

How to verify:
- Re-running the same run/build with identical inputs and versions yields identical manifests and output snapshot refs.
- Outputs are stable under deterministic ordering rules.

Pass/fail:
- PASS if deterministic tests pass on CI for a fixed dataset.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-DETERMINISM

---

### G-REL-0003 Negative Path Coverage

Why: Fail-closed behavior must be tested (not assumed).

How to verify:
- Test suite includes explicit negative-path tests for:
  - policy denials,
  - contract failures,
  - bypass attempts,
  - extraction errors,
  - ER over-merge rollback.

Pass/fail:
- PASS if negative-path tests exist and run in CI.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-ERROR-PATHS

---

### G-REL-0004 Gold Fail-Closed Publication

Why: Prevent corrupt or unsafe semantics from becoming “latest”.

How to verify:
- If contracts fail or blocking tasks exist:
  - gold build may run but cannot publish,
  - “latest” pointer does not change,
  - last known good remains queryable.
- Publishing emits audit events.

Pass/fail:
- PASS if publish pointer updates only after passing gates.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-GOLD-PUBLISH-GATES

---

### G-OPS-0001 Runbook Complete

Why: Operability requires documented procedures; no one-off scripts.

How to verify:
- Runbook covers local run, test, deploy, rollback, backup/restore, deletion workflow.
- Procedures include explicit commands and expected outputs.

Pass/fail:
- PASS if runbook is complete and kept up to date with system behavior.
- FAIL otherwise.

Evidence:
- evidence: spec/12_RUNBOOK.md :: Local Development Runbook

---

### G-OPS-0002 Backup Restore Drills

Why: Data loss prevention is a critical flow.

How to verify:
- Backup procedure exists for Postgres and object store.
- Restore drill is executed periodically (at least before releases) and evidence is recorded.

Pass/fail:
- PASS if restore drill succeeds and evidence exists.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-BACKUP-RESTORE

---

### G-MAINT-0001 Boundary Fitness

Why: Prevent architecture erosion and hidden couplings.

How to verify:
- Dependency checks enforce direction rules (no cross-layer imports).
- Forbidden direct engine/index clients outside gateway are detected.
- UI does not duplicate backend business logic.

Pass/fail:
- PASS if boundary checks run in CI and no violations exist.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

---

### G-MAINT-0002 Evidence Completeness

Why: Autopilot outputs must be explainable and reviewable.

How to verify:
- Every proposal and recommendation includes:
  - evidence bundle refs,
  - confidence,
  - missing evidence list (where applicable),
  - explicit review triggers.
- UI renders these fields; API enforces presence.

Pass/fail:
- PASS if schema validators and tests enforce completeness.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-EVIDENCE-COMPLETENESS

---

### G-MAINT-0003 Duplication Control

Why: Prevent copy-paste drift in critical logic.

How to verify:
- Static analysis detects high duplication in policy enforcement and manifest handling modules.
- Duplicated logic is refactored into shared libraries with tests.

Pass/fail:
- PASS if duplication thresholds are respected and refactors are justified when exceeded.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-DUPLICATION

---

### G-COMP-0001 Migration Safety

Why: Migrations are hard to reverse and impact all users.

How to verify:
- Migration tests apply migrations to empty DB and upgrade from prior version snapshot.
- Rollback is verified in dev/test or forward-fix is documented with procedure.

Pass/fail:
- PASS if migration tests pass and rollback/forward-fix plan exists.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-MIGRATIONS

---

### G-COMP-0002 Contract Compatibility

Why: Users depend on API/CLI/file formats; drift breaks them.

How to verify:
- Contract tests validate request/response schemas and file formats.
- Template IDs T1..T8 remain stable.
- Deprecation policy is followed.

Pass/fail:
- PASS if compatibility tests and schema validation pass.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-CONTRACT-COMPAT

---

### G-COMP-0003 Profile Upgrade Safety

Why: Progressive disclosure must work without rebuild.

How to verify:
- Starter→Team upgrade path exists and is tested.
- Dataset IDs remain stable; gold semantics remain versioned.
- No re-ingestion from source is required.

Pass/fail:
- PASS if upgrade drill passes on CI for a representative dataset.
- FAIL otherwise.

Related checks:
- evidence: checks/CHECKS_INDEX.md :: CHK-UPGRADE-DRILL

---

## SLOP_BLACKLIST Enforcement Mapping

Each SB rule MUST be enforced by at least one automated check and/or acceptance checklist item.

| SB-ID | Enforcement type | Check ID(s) / Checklist | Required evidence |
|---|---|---|---|
| SB-0001 | Automated + checklist | CHK-POLICY-DENY-BY-DEFAULT; PR checklist | evidence: templates/PR_REVIEW_CHECKLIST.md :: SLOP_BLACKLIST Compliance
| SB-0002 | Automated | CHK-BOUNDARY-FITNESS | evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS
| SB-0003 | Automated | CHK-DUPLICATION | evidence: checks/CHECKS_INDEX.md :: CHK-DUPLICATION
| SB-0004 | Automated | CHK-ERROR-PATHS | evidence: checks/CHECKS_INDEX.md :: CHK-ERROR-PATHS
| SB-0005 | Automated | CHK-TIMEOUTS-RETRIES | evidence: checks/CHECKS_INDEX.md :: CHK-TIMEOUTS-RETRIES
| SB-0006 | Checklist | PR checklist | evidence: templates/PR_REVIEW_CHECKLIST.md :: SLOP_BLACKLIST Compliance
| SB-0007 | Checklist | PR checklist + glossary review | evidence: spec/03_DOMAIN_MODEL.md :: Glossary (authoritative terms; prevents SB-0007)
| SB-0008 | Automated | CHK-SECRETS-HYGIENE | evidence: checks/CHECKS_INDEX.md :: CHK-SECRETS-HYGIENE
| SB-0009 | Automated + checklist | CHK-CONTRACT-COMPAT; PR checklist | evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Public Contract Policy
| SB-0010 | Checklist | PR checklist | evidence: templates/PR_REVIEW_CHECKLIST.md :: SLOP_BLACKLIST Compliance
| SB-0011 | Checklist | PR checklist + runbook | evidence: spec/12_RUNBOOK.md :: Maintenance Playbook
| SB-0012 | Checklist | PR checklist + decision log | evidence: templates/PR_REVIEW_CHECKLIST.md :: Structural changes recorded

Mapping completeness is validated by:
evidence: checks/CHECKS_INDEX.md :: CHK-SLOP-MAPPING
