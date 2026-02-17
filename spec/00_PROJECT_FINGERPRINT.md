# spec/00_PROJECT_FINGERPRINT.md

## Project fingerprint summary

SchemaPilot is an open-source, self-hosted system that turns messy business data (file shares, exports, PDFs/emails, DB dumps) into:
- an evidence-backed catalog,
- bronze/silver/gold data layers,
- a governed semantic layer for SQL-first AI,
- a Query Gateway that enforces RBAC/ABAC, masking, audit logging, and provenance.

Packaging is progressive (single recommended approach):
- Starter: single-node evaluation (minimal components)
- Team: default recommended profile (Iceberg + Trino)
- Enterprise: adds stricter governance and scale modules (OPA, stronger observability, optional Spark/ClickHouse)

Canonical product definition lives in:
evidence: spec/01_SCOPE.md :: Scope Summary

## Runtime and deployment shape

- Deployable software: API service + UI + background workers + gateway.
- Local-first: Docker Compose is first-class; Kubernetes is optional later.
- Data plane includes local filesystem/MinIO/S3, DuckDB/Trino, and optional indexes.

## Data sensitivity tier

- Expected data: business records and documents; may include PII/regulated fields.
- Governance posture: deny-by-default; explicit approvals; auditability.
evidence: spec/06_SECURITY_AND_THREAT_MODEL.md :: Security Model Summary

## Determinism and drift-proofing requirements

- Bronze is immutable and append-only; every ingest creates a manifest with content hash.
- Silver/gold builds are snapshot-driven and reproducible.
- SSOT pack drift is controlled via MANIFEST.sha256.
evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY

## Critical Flow Inventory

Critical flows (fail-closed required) include:
- Authentication/authorization/secrets handling
- Sensitive data handling (PII detection, masking, policy enforcement)
- Query execution and retrieval access (gateway non-bypass)
- Data deletion/retention/backups/restores/rollback
- Public contracts (API/CLI/events/file formats), migrations, upgrades

Controls must be defined and gated:
evidence: spec/11_QUALITY_GATES.md :: Gate Index

## Decision Safety Classifier

For every ambiguity, missing datum, assumption, contradiction, or design choice that affects behavior:

1) State the decision precisely: what is being decided, impacted flows, impacted files.
2) Classify:
   - Externally constrained? (YES/NO)
   - Critical flow impacted? (YES/NO)
   - Unsafe/high-risk? (YES/NO)
   - Conservative baseline available? (YES/NO)
   - Safe to decide? (YES/NO)
3) Outcome:
   - If externally constrained: only decide a conservative baseline that reduces capability and does not claim compliance; otherwise ask a blocking question.
   - If unsafe/high-risk: decide conservative baseline if it keeps fail-closed and reversible; otherwise ask a blocking question.
   - Else: decide a single default and log it.
4) Log target:
   - Decisions → DECISIONS.md
   - Assumptions → ASSUMPTIONS.md
   - Questions → checks/QUESTIONS_FOR_USER.md

## Externally constrained unknowns (tracked as questions; not guessed)

- Compliance regime requirements (privacy, audit, retention, deletion obligations)
- Required retention durations and legal hold rules
- Identity provider standards (OIDC/SAML details, MFA requirements)
- Approved deployment standards (networking, encryption, secret stores)

Questions are recorded here:
evidence: checks/QUESTIONS_FOR_USER.md :: Questions for User

## Spec Applicability Matrix

All spec documents are required for this project because the fingerprint indicates a deployable, security-sensitive system with public contracts.

| Spec path | Applicability | Justification |
|---|---|---|
| spec/00_PROJECT_FINGERPRINT.md | APPLICABLE | Defines applicability, QAC profile, and critical-flow inventory. |
| spec/01_SCOPE.md | APPLICABLE | Defines user journeys, constraints, and success criteria. |
| spec/02_ARCHITECTURE.md | APPLICABLE | Defines component boundaries, flows, and non-bypass rules. |
| spec/03_DOMAIN_MODEL.md | APPLICABLE | Defines canonical domain entities and invariants needed for auditability. |
| spec/04_INTERFACES_AND_CONTRACTS.md | APPLICABLE | Defines API/CLI/events/file formats as compatibility surfaces. |
| spec/05_DATASTORE_AND_MIGRATIONS.md | APPLICABLE | Defines storage schemas, migrations, retention/deletion mechanics. |
| spec/06_SECURITY_AND_THREAT_MODEL.md | APPLICABLE | Required due to PII handling and gateway enforcement. |
| spec/07_RELIABILITY_AND_OPERATIONS.md | APPLICABLE | Required due to external I/O, orchestrated jobs, and rollback needs. |
| spec/08_OBSERVABILITY.md | APPLICABLE | Required to prove correctness and support incident response. |
| spec/09_TEST_STRATEGY.md | APPLICABLE | Required to enforce fail-closed behavior and prevent drift/regressions. |
| spec/10_PHASES_AND_TASKS.md | APPLICABLE | Required to execute without guessing (PHASE_0 → DONE). |
| spec/11_QUALITY_GATES.md | APPLICABLE | Required to enforce the Quality Attribute Contract. |
| spec/12_RUNBOOK.md | APPLICABLE | Required due to deployable software and operational procedures. |

## Quality Attribute Profile (QAC)

| Quality attribute | Intent | Primary risks | Invariants (MUST / MUST NOT) | Verification mapping | Fail-closed default |
|---|---|---|---|---|---|
| Security | Prevent unauthorized access and data exfiltration; centralize enforcement | Misconfig exposure; gateway bypass; secret leakage; plugin abuse | MUST deny-by-default; MUST NOT allow bypass; MUST redact sensitive logs | Gates: G-SEC-0001..0004; Checks: CHK-BOUNDARY-FITNESS, CHK-SEC-STATIC | Bind localhost-only; require auth for non-local; disable optional integrations unless enabled |
| Performance | Meet declared constraints with minimal complexity; avoid regressions | Unbounded scans; index bloat; slow profiling | MUST provide perf harness; MUST NOT regress without decision + mitigation | Gate: G-PERF-0001; Check: CHK-PERF-HARNESS | Prefer sampling budgets; optional marts/indexes disabled unless justified |
| Reliability | Reproducible builds; safe retries; no silent partial publish | Non-determinism; schema drift corrupting gold; unbounded retries | MUST be idempotent; MUST fail-closed for gold publish | Gates: G-REL-0001..0004; Checks: CHK-ERROR-PATHS | Gold publish blocked on contract failure |
| Operability | A small team can run it; clear runbooks and safe rollback | Complex upgrades; unclear failure recovery | MUST have runbook; MUST support rollback to last good | Gates: G-OPS-0001..0002 | Disable risky features unless configured; safe startup constraints |
| Maintainability | Prevent architecture erosion; keep boundaries stable | God modules; copy-paste; semantics drift | MUST enforce boundary rules; MUST keep glossary authoritative | Gates: G-MAINT-0001..0003; Checks: CHK-BOUNDARY-FITNESS | Prefer explicit interfaces; no cross-layer imports |
| Compatibility/Upgradability | Public contracts and data migrations are safe and versioned | Breaking API/data changes; migration failure | MUST have deprecation policy; MUST keep migrations reversible | Gates: G-COMP-0001..0003; Checks: CHK-CONTRACT-COMPAT | Fail to start on incompatible schema; block release without migration plan |
