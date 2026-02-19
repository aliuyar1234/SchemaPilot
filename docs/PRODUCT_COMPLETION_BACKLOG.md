# Product Completion Backlog (Current Snapshot)

Last updated: 2026-02-19  
Purpose: keep a practical view of what is still missing for a "complete" SchemaPilot product and how AI should be integrated safely.

## Current Repo Snapshot

- `master`: stable release baseline (`v1.0.1`), conservative production-facing branch.
- `dev`: advanced capability wave branch with major post-`v1.0.1` features (DB builder expansion, governance/ops enhancements, AI-safe extensions).

Note: "current state" is branch-dependent. For customer delivery, always state explicitly which branch/revision is the reference.

## What Is Still Missing For "Complete Product"

The core platform is strong. Main gaps are now productization/adoption, not basic architecture.

### 1) Adoption and Time-to-Value

- [ ] Ship robust "first-hour success" presets for common customer paths (SharePoint/exports/fileshare -> first governed query).
- [ ] Expand connector breadth for real enterprise stacks (priority SaaS + file ecosystems).
- [ ] Standardize operator onboarding diagnostics (`doctor` + guided remediation).

### 2) Operability and Reliability

- [ ] Enforce stable run-step failure taxonomy across all pipelines/connectors.
- [ ] Keep support-grade diagnostics bundles deterministic and redaction-safe.
- [ ] Add clear SLO/SLA dashboards/exports for sync freshness, queue depth, denial reasons, and review latency.

### 3) Ecosystem Trust / Supply Chain

- [ ] Make signed packs/plugins + verification mandatory in enterprise mode.
- [ ] Keep connector conformance harness as hard gate for first-party connectors.
- [ ] Maintain compatibility matrix and migration tooling for packs/semantic versions.

### 4) Enterprise Rollout Readiness

- [ ] Standardize promotion flow (`dev -> prod`) with signed bundles and policy simulation gates.
- [ ] Keep secrets rotation + break-glass procedures documented and tested in release drills.
- [ ] Maintain recovery drills (backup/restore) as release criteria.

### 5) AI Value Layer (Safe-by-Default)

- [ ] Keep AI strictly gateway-routed (no direct engine/index access).
- [ ] Enforce provenance/citations on AI outputs.
- [ ] Keep AI actions proposal-only for risky operations (approval-gated, no silent auto-apply).
- [ ] Expand AI eval harness from smoke to production-grade regression suites.

## AI Integration Blueprint (Customer Environment)

Target outcome: seamless AI on company data without bypass risk.

1. Connect messy sources (files, exports, SaaS snapshots) with deterministic ingestion.
2. Build canonical + semantic layer under governance controls.
3. Materialize customer-specific serving database via DB builder.
4. Expose only governed query surface through gateway.
5. Attach AI services to gateway/CP only, with full audit/provenance.
6. Evolve policies/semantics through review tasks and evidence bundles.

## Practical Definition of "Done"

SchemaPilot is product-complete for a customer profile when:

- first safe query is achieved in under 60 minutes from messy sources,
- governance controls remain fail-closed under outage tests,
- no-bypass invariants hold across compose/k8s paths,
- operators can diagnose issues end-to-end without source-code debugging,
- AI workflows are useful and auditable (not just demo-capable).

## Next Review Cadence

- Weekly: update this file with branch-specific status and top 5 blockers.
- Release cut: confirm this backlog before tagging.
