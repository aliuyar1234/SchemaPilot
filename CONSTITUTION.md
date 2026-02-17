# CONSTITUTION.md — Non-Negotiable Engineering Constraints

These rules exist to keep SchemaPilot implementable, auditable, and safe under AI-assisted development.
Every rule below is **enforceable**: each includes Detect → Remediate → Enforce mappings to checks/gates.

Canonical enforcement mappings:
- evidence: spec/11_QUALITY_GATES.md :: SLOP_BLACKLIST Enforcement Mapping
- evidence: checks/CHECKS_INDEX.md :: Checks Index

## Core constraints (project-specific)

1) **Single enforcement point (Query Gateway)**
- Rule: Humans and AI MUST NOT bypass the Query Gateway to reach query engines or indexes.
- Detect: any direct client library usage or network route to Trino/DuckDB/OpenSearch/Qdrant outside the gateway path.
- Remediate: route all access through the gateway; add boundary checks; add e2e denial tests.
- Enforce:
  - evidence: spec/11_QUALITY_GATES.md :: G-SEC-0002 Gateway Non-Bypass
  - evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

2) **Fail-closed by default**
- Rule: When uncertain, system behavior MUST deny, disable, or stop rather than guess.
- Detect: permissive defaults, silent fallbacks, unreviewed “auto-accept” in critical flows.
- Remediate: add explicit config gates + human approvals + clear errors.
- Enforce:
  - evidence: spec/11_QUALITY_GATES.md :: G-SEC-0001 Safe Startup Defaults
  - evidence: checks/CHECKS_INDEX.md :: CHK-SLOP-MAPPING

3) **Evidence-backed autopilot**
- Rule: Any recommendation (Decision Engine, inference, PII) MUST carry evidence + confidence + failure modes + review triggers.
- Detect: outputs without confidence, without missing-evidence list, or without review gating.
- Remediate: require evidence bundles; block promotion without approval.
- Enforce:
  - evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0002 Evidence Completeness
  - evidence: spec/01_SCOPE.md :: Evidence-Backed Autopilot Rules

4) **Deterministic artifacts**
- Rule: Builds MUST be reproducible from inputs, versions, and configs; no hidden state.
- Detect: non-deterministic IDs/time usage; transforms without versioning; mutable bronze.
- Remediate: stable IDs, snapshot-based builds, content hashes, manifest discipline.
- Enforce:
  - evidence: spec/11_QUALITY_GATES.md :: G-REL-0002 Deterministic Builds
  - evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY

## Boundary & coupling guardrails (anti-erosion)

### Layering rules (must be enforced)
- UI MAY call only Control Plane API.
- Control Plane API MAY call only internal domain services and metadata store.
- Workers (connectors/profilers/builders) MAY write to storage layers and metadata store via internal service interfaces.
- Query engines and indexes MUST be reachable only via Query Gateway in production mode.
- Plugin code MUST be sandboxed by capability: connectors cannot execute queries; they can only discover + ingest to bronze.

Enforcement:
- evidence: spec/02_ARCHITECTURE.md :: Dependency Direction Rules
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

### “No cross-layer imports” policy (code-level)
- Control-plane modules MUST NOT import data-plane execution modules directly; interactions are via defined interfaces.
- UI MUST NOT embed business logic duplicated from backend; it renders backend-provided state.
- Gateway MUST NOT import UI or inference modules.

Enforcement:
- evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0001 Boundary Fitness
- evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

## SLOP_BLACKLIST

Each item is a “never without explicit exception” rule.

### SB-0001 Silent defaults in critical flows
- Detect: critical flow proceeds with implicit defaults (auth, deletion, policy, external I/O).
- Remediate: require explicit config and approvals; fail to start or deny by default.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: SLOP_BLACKLIST Enforcement Mapping

### SB-0002 God objects / mega-modules
- Detect: modules that accumulate unrelated responsibilities; circular dependencies.
- Remediate: split by bounded context; enforce dependency direction.
- Enforce: evidence: checks/CHECKS_INDEX.md :: CHK-BOUNDARY-FITNESS

### SB-0003 Copy-paste duplication instead of abstraction
- Detect: repeated logic across services; inconsistent policy handling.
- Remediate: extract shared libraries or canonical services; remove duplication.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-MAINT-0003 Duplication Control

### SB-0004 Untested error paths
- Detect: missing negative-path tests for denial, drift breakage, extractor failure.
- Remediate: add explicit tests for fail-closed behavior.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-REL-0003 Negative Path Coverage

### SB-0005 Unbounded retries / missing timeouts
- Detect: retry loops without cap; external calls without timeouts.
- Remediate: bounded retries, exponential backoff, deadlines.
- Enforce: evidence: spec/07_RELIABILITY_AND_OPERATIONS.md :: Retry and Timeout Policy

### SB-0006 Hidden global state / implicit singletons
- Detect: hidden caches and mutable globals affecting outputs.
- Remediate: explicit dependency injection; pure functions for scoring/inference.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-REL-0002 Deterministic Builds

### SB-0007 Naming/semantics drift
- Detect: inconsistent terms (dataset vs table vs entity); mismatched UI vs API naming.
- Remediate: enforce glossary; align domain objects.
- Enforce: evidence: spec/03_DOMAIN_MODEL.md :: Glossary

### SB-0008 Logging without correlation OR leaking sensitive data
- Detect: logs without request/run IDs; logs containing secrets/PII samples.
- Remediate: structured logging; redaction; correlation IDs everywhere.
- Enforce: evidence: spec/08_OBSERVABILITY.md :: Logging Standard

### SB-0009 Contract drift (implementation ≠ interfaces/spec)
- Detect: API/CLI changes not reflected in spec/04; breaking changes without deprecation.
- Remediate: contract-first updates; compatibility gates.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-COMP-0002 Contract Compatibility

### SB-0010 Convenience over fail-closed
- Detect: “best effort” paths returning partial sensitive data or skipping checks.
- Remediate: deny or stop; require explicit override with audit.
- Enforce: evidence: spec/11_QUALITY_GATES.md :: G-SEC-0003 Deny-By-Default Policy

### SB-0011 One-off scripts without runbook/checks
- Detect: operational actions only documented in chat or ad-hoc commands.
- Remediate: encode procedures in runbook; add checks.
- Enforce: evidence: spec/12_RUNBOOK.md :: Maintenance Playbook

### SB-0012 Structural changes without decision log
- Detect: new components/modules/persistence surfaces without DECISIONS entry.
- Remediate: add decision record with verification impact and mitigation.
- Enforce: evidence: templates/PR_REVIEW_CHECKLIST.md :: Structural changes recorded

## Exception process

Violating any SLOP_BLACKLIST rule requires ALL of:
(1) a DECISIONS.md entry with explicit justification,
(2) an explicit mitigation plan,
(3) a check or test plan that prevents uncontrolled spread,
(4) acceptance checklist evidence pointers to (1)-(3).
