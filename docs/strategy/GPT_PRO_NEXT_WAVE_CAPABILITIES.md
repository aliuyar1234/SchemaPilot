# GPT Pro Next-Wave Capabilities (Archived Input)

Source: user-provided GPT Pro strategy response (archived to avoid context-window dependency).

Status: reference document for next planning and implementation cycles.

## 1) Executive Summary

- SchemaPilot is already production-credible (governance-first, deterministic pipelines, review/gates, target-db builder, gateway enforcement, optional AI, hardened deploys, strong test gates).
- Biggest next jump is not "more AI", but source coverage, operator CLI UX, ecosystem trust, and BI integration without bypass.
- Highest first-hour value is SharePoint/fileshare onboarding to target DB and safe gateway query in under 60 minutes.
- Export/dropzone ingestion is the practical no-API SaaS entry path and should be boring/reliable.
- Supply-chain hardening must become default as connector/pack/plugin ecosystem grows (signing + verification + conformance).
- Ops usability should center on doctor/diag/run-step introspection and standardized failure taxonomy.
- Optional PGWire at gateway is a high adoption lever for BI tooling if strictly gated.
- New risks in next wave: connector exfiltration, protocol exposure, policy/pack tampering, partial ingest/sync.
- Recommended architecture path: source mirror manifest + watcher + audit outbox + run step DAG + pack/plugin signing.
- All new modules should stay optional and disabled by default.
- Team profile should remain operationally simple.
- KPI focus should include first-hour funnel, sync reliability, policy denials, review latency, connector failures, supply-chain verification, determinism pass rate.

## 2) Gap Analysis

### Product

- Source coverage needs first-class SharePoint/SMB/Exports.
- BI integration needs SQL endpoint compatibility for Tableau/PowerBI style tooling.
- Onboarding presets are missing for common paths.

### Security

- Supply chain needs signature/verification and enforcement modes.
- Plugin sandbox must be stricter for network/file/resource bounds.
- Break-glass access pattern is missing for controlled emergency access.

### Architecture

- Source mirror standard missing across connectors.
- Audit sink delivery can couple availability without outbox pattern.
- Run debugability still costly without step DAG + failure codes.

### Operability

- Doctor and diagnostic bundle are needed for OSS install/support.
- SLA alert routing and disable-by-default behavior need consistent handling.
- Query budget explain/reporting should be operator-friendly.

### Ecosystem

- Connector conformance and certification loop needed to scale contributions.
- Pack compatibility matrix and migrations needed for safe upgrades.
- Starter role/policy/semantic templates are needed for adoption.

## 3) Architecture Evolution Proposals

### Option A (Recommended): Source Mirror Manifest + Watcher + Step DAG

- Standardize connector output as deterministic source snapshot manifests.
- Add watcher trigger path and step-level run status/evidence/failure taxonomy.
- Benefits: determinism, reproducibility, easier incremental sync, better support/debug.

### Option B (Recommended, optional): Gateway PGWire Adapter

- Optional, disabled-by-default PGWire listener at gateway.
- Enforce same policy/masking/audit/provenance, SELECT-only subset.
- Benefits: BI adoption without introducing bypass.

### Option C (Later, optional): Message Broker Adapter (NATS)

- Optional enterprise scale queue backend.
- Not default due to component sprawl and ops overhead.

## 4) Prioritized Backlog (CAP-0001..CAP-0040)

This is the archived task set from the GPT Pro response.

### P0: Adoption + Safety Spine

- CAP-0001 SharePoint/OneDrive Connector (Graph snapshot) [first-hour]
- CAP-0002 SharePoint Delta Sync
- CAP-0003 SMB/CIFS Fileshare Connector [first-hour]
- CAP-0004 Export Dropzone Connector [first-hour]
- CAP-0005 Source Mirror Manifest v1
- CAP-0006 Ingestion Watcher (poll-based)
- CAP-0007 Run Step DAG + Failure Taxonomy surfaced
- CAP-0008 Audit Outbox Dispatcher
- CAP-0009 `schemapilot doctor` [first-hour]
- CAP-0010 `schemapilot diag bundle` (redacted)
- CAP-0011 Pack Signing + Verification Enforcement
- CAP-0012 Plugin Sandbox Policy v2
- CAP-0013 Connector Conformance Harness v2
- CAP-0014 Policy Impact Diff (simulate before/after)
- CAP-0015 Semantic Test Harness
- CAP-0016 Gateway PGWire Proxy (optional) [first-hour]
- CAP-0017 Safe Query Templates Library + CLI run
- CAP-0018 Onboarding Presets [first-hour]
- CAP-0019 Target DB Credential Rotation Workflow
- CAP-0020 Break-glass Read Access (TTL + dual approval)

### P1: Expansion

- CAP-0021 Jira Connector
- CAP-0022 Zendesk Connector
- CAP-0023 CRM Export Pack
- CAP-0024 DB Dump Ingestion v2
- CAP-0025 Data Access Request Workflow
- CAP-0026 Policy Pack Template Library
- CAP-0027 Semantic Pack Library + tests
- CAP-0028 Glossary/Data Dictionary Generator + export
- CAP-0029 Alert Sinks for SLA/Drift
- CAP-0030 Per-role Query Budgets + query explain CLI
- CAP-0031 Target DB Index/Materialization Recommendations (approval-gated)
- CAP-0032 Gateway HA mode + optional Redis
- CAP-0033 Environment Promotion with signed export/import + policy simulation gates
- CAP-0034 Build Attestation Signing
- CAP-0035 Deletion/Retention Attestation

### P2: Advanced Optional

- CAP-0036 Optional NATS queue adapter
- CAP-0037 Multi-target shadow cutover
- CAP-0038 Lineage graph API + export
- CAP-0039 Optional tokenization vault
- CAP-0040 Policy-bound sampling endpoint

## 5) Dependency Graph (Archived)

Critical adoption path:

1. CAP-0005 -> CAP-0001/CAP-0003/CAP-0004
2. CAP-0001 -> CAP-0002
3. CAP-0005 -> CAP-0006
4. CAP-0007 + CAP-0009 + CAP-0010 for operability
5. CAP-0016 (optional) after governance/debug baseline

Supply-chain path:

1. CAP-0011 -> CAP-0013
2. CAP-0011 -> CAP-0026/CAP-0027
3. CAP-0011 + CAP-0014 -> CAP-0033

Reliability path:

1. CAP-0008 -> CAP-0029 -> CAP-0035

## 6) PR/Delivery Grouping (Archived)

- Group A: Source mirror + watcher foundation
- Group B: First-hour connectors (dropzone/sharepoint/smb)
- Group C: CLI operability (doctor/diag/presets)
- Group D: Ecosystem trust (signing/conformance/sandbox)
- Group E: Policy/Semantic guardrails
- Group F: Optional BI integration (PGWire)
- Group G: Security workflows (credential rotation, break-glass)
- Group H: P1/P2 expansion after stabilization

## 7) KPI/Observability Expansion

- First-hour funnel (`onboarding_start`, `onboarding_complete`, `time_to_first_safe_query`)
- Connector reliability (`connector_snapshot_success/failed`, failure reasons)
- Mirror integrity (`source_mirror_manifest_mismatch_total`)
- Watcher health (`watcher_cycles_total`, change detection count)
- Sync lag (`sync_lag_seconds`)
- Governance friction (review queue size/time-to-close, policy denials, masking count)
- Supply-chain safety (pack verification failures, sandbox violations)
- Optional PGWire usage and denials

Recommended instrumentation anchors:

- `backend/shared_domain/observability.py`
- `backend/gateway/*` (policy/sql safety/pgwire)
- `backend/control_plane/*` (review/packs/target-db lifecycle)
- `backend/workers/*` (connector wrappers + evidence IDs)
- `tools/kpi_extract.py`

## 8) Anti-Patterns (Do Not Build Now)

- No dashboard-first UI expansion.
- No bypass-friendly direct DB/index exposure.
- No auto-approval AI actions for policy/semantic/schema.
- No mandatory broker in default setup.
- No silent partial ingest/sync under strict mode.
- No uncontrolled connector ecosystem without conformance/sandbox/signing.

## 9) Essential Open Questions + Conservative Defaults

- BI path first: default to optional PGWire (SELECT-only, disabled by default).
- SMB mode: support direct SMB as optional, mount fallback as baseline.
- SharePoint scope baseline: minimal read-only scopes, fallback to export dropzone.
- Break-glass: dual approval mandatory in enterprise mode.

## 10) First-Hour Top Capabilities (Archived Priority)

1. CAP-0001 SharePoint snapshot connector
2. CAP-0004 Export dropzone connector
3. CAP-0009 Doctor + CAP-0018 presets
4. CAP-0016 Optional PGWire
5. CAP-0007 Step DAG + CAP-0010 diag bundle

---

Implementation note:

- Keep this file as planning reference.
- Use concrete execution tracking in tasklist artifacts (for example `docs/strategy/TASKLIST_NEXT_CAPABILITIES.md` once execution starts).
