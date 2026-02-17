# spec/06_SECURITY_AND_THREAT_MODEL.md

## Security Model Summary

SchemaPilot MUST be secure-by-default and fail-closed:
- localhost bind by default; explicit auth required for non-local exposure
- deny-by-default policy evaluation
- Query Gateway is the single enforcement point for SQL and retrieval
- secrets are never stored in plaintext and never logged
- audit logs are append-only and immutable

Security invariants are non-negotiable:
evidence: CONSTITUTION.md :: Core constraints (project-specific)

## Assets and Trust Boundaries

### Primary assets
- Source credentials (DB passwords, access keys, tokens)
- Raw and derived data (bronze/silver/gold; documents)
- Policies (RBAC/ABAC definitions, masking rules)
- Audit logs and access decisions
- Recommendation reports and evidence bundles

### Trust boundaries
- Between UI and API (browser boundary)
- Between Control Plane and Data Plane (job boundary)
- Between Query Gateway and engines/indexes (enforcement boundary)
- Between plugin code and core runtime (supply-chain boundary)

## Authentication and Authorization

### Authentication baseline
- Default: local-only access, local auth suitable for evaluation.
- Non-local exposure:
  - MUST require explicit auth configuration (OIDC or other), else FAIL TO START.
evidence: DECISIONS.md :: D-0004 Safe startup defaults (localhost bind; auth required for non-local)

### Authorization model
- RBAC roles define coarse capabilities.
- ABAC attributes refine access (department, region, purpose, clearance).
- Row/column controls are applied in Query Gateway.

RBAC baseline roles (minimum):
- `platform_admin`
- `data_steward`
- `data_engineer`
- `analyst`
- `ai_agent` (tool identity; least privilege)

Enforcement:
- evidence: spec/04_INTERFACES_AND_CONTRACTS.md :: Query Gateway Contract

## Secrets Handling

Rules:
- Secrets MUST NOT be committed to repo.
- Secrets MUST NOT appear in logs, errors, or UI.
- Secrets are referenced via `credentials_ref` and resolved at runtime from:
  - environment variables (dev), or
  - mounted secrets, or
  - a secret manager integration (Enterprise).

Rotation expectation:
- Credentials must be rotatable without redeploying the whole system; at minimum, reloading is supported.

Redaction:
- Logs must redact values matching configured secret patterns and known sensitive tokens.
evidence: spec/08_OBSERVABILITY.md :: Logging Standard

## PII Detection and Review Gates

PII detection produces proposals; it does not silently classify high-risk fields without review.

### Methods (evidence-backed)
- Rules: regex + checksum validators (email, phone, IBAN/CC patterns)
- Statistical signals: entropy, uniqueness, token shapes
- Optional classifier: predicts column sensitivity class, emits confidence and evidence bundle
- Optional LLM usage (strictly limited): header/description labeling only; never used to scan full values

### Review gating rules
- High-impact tags (PCI/PHI categories) require explicit approval if confidence is below threshold.
- In strict mode: unknown sensitivity defaults to restricted until resolved.

evidence: spec/01_SCOPE.md :: Evidence-Backed Autopilot Rules

## Retention and Deletion Workflow

Retention values are externally constrained; SchemaPilot provides mechanisms and evidence logs.

Fail-closed defaults:
- automatic retention enforcement disabled until configured
- deletion requires explicit approvals and emits evidence report
- legal hold blocks deletion and is audit logged
evidence: spec/05_DATASTORE_AND_MIGRATIONS.md :: Retention and Deletion Mechanics

## Threats and Mitigations (practical)

At minimum, the following threats MUST be addressed.

1) Over-broad connector scope exposes unintended data
- Mitigation: scope preview; least-privilege connector checks; approval required to expand scope; audit events for scope changes.

2) Credential leakage via logs or UI
- Mitigation: redact; never store plaintext secrets; secrets resolved only at runtime; secret scanning checks in CI.
- Enforce: evidence: checks/CHECKS_INDEX.md :: CHK-SECRETS-HYGIENE

3) Query Gateway bypass (direct engine/index access)
- Mitigation: network isolation; code boundary checks; integration tests that validate denial when bypass attempted.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-SEC-0002 Gateway Non-Bypass

4) Prompt injection / malicious document content affecting AI behavior
- Mitigation: treat documents as untrusted; AI tool cannot execute actions from content; tool access is allowlisted; gateway enforcement for retrieval.

5) Entity resolution over-merge corrupts identity
- Mitigation: conservative thresholds; reversible merge decisions; review tasks for borderline clusters; audit every merge and rollback.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-REL-0003 Negative Path Coverage

6) Schema drift silently changes gold metrics
- Mitigation: contracts + fail-closed gold publish; drift generates review tasks with diffs; last known good gold remains.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-REL-0004 Gold Fail-Closed Publication

7) Plugin supply-chain compromise
- Mitigation: plugin allowlist; optional signatures; restricted capabilities; sandboxed execution; no network by default for plugins.
- Enforce: evidence: checks/CHECKS_INDEX.md :: CHK-SUPPLY-CHAIN

8) Public exposure misconfiguration (listening on non-local without auth)
- Mitigation: fail-to-start behavior; explicit config required; runbook procedure for secure exposure.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-SEC-0001 Safe Startup Defaults

9) Data destruction (malicious or accidental)
- Mitigation: immutable bronze; snapshotting; guarded deletion workflow; backups and restore procedures; separation of duties for deletion approvals.
- Enforce: evidence: spec/12_RUNBOOK.md :: Backup and Restore

10) Index leakage (search/vector returns restricted content)
- Mitigation: indexes are queryable only through gateway; metadata binding; row/column policy filtering applied pre-return.
- Enforce: evidence: DECISIONS.md :: D-0003 Query Gateway is the single enforcement point (no bypass)

## Secure Defaults and Failure Modes

- If auth is misconfigured for non-local bind: FAIL TO START.
- If policy engine is unavailable (Enterprise): default to DENY for protected operations.
- If search/vector modules are unavailable: retrieval endpoints return a clear disabled/unavailable error; SQL path unaffected.
- If extraction fails: raw artifacts still stored; indexing is deferred; review task created.
evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Degradation and Backpressure
