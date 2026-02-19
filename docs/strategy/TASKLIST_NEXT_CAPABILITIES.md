# TASKLIST_NEXT_CAPABILITIES.md - SchemaPilot Next Capabilities Wave

Source baseline: `docs/strategy/GPT_PRO_NEXT_WAVE_CAPABILITIES.md`

Execution policy:

- Keep security/governance fail-closed by default.
- Keep gateway as single enforcement point.
- Keep optional modules disabled by default.
- Prefer CLI-first operator workflows.

## P0 - Adoption + Safety Spine

- [x] CAP-0001 SharePoint/OneDrive Connector (Graph Snapshot)
- [x] CAP-0002 SharePoint Delta Sync
- [x] CAP-0003 SMB/CIFS Fileshare Connector
- [x] CAP-0004 Export Dropzone Connector (folder ingestion)
- [x] CAP-0005 Source Mirror Manifest v1
- [x] CAP-0006 Ingestion Watcher (poll-based triggers)
- [x] CAP-0007 Run Step DAG + Failure Taxonomy surfaced
- [x] CAP-0008 Audit Outbox Dispatcher
- [x] CAP-0009 `schemapilot doctor` preflight
- [x] CAP-0010 `schemapilot diag bundle` (redacted)
- [x] CAP-0011 Pack Signing + Verification Enforcement
- [x] CAP-0012 Plugin Sandbox Policy v2
- [x] CAP-0013 Connector Conformance Harness v2
- [x] CAP-0014 Policy Impact Diff (simulate before/after)
- [x] CAP-0015 Semantic Test Harness
- [x] CAP-0016 Gateway PGWire Proxy (optional)
- [x] CAP-0017 Safe Query Templates Library + CLI run
- [x] CAP-0018 Onboarding Presets (SharePoint/Dropzone->TargetDB->Query)
- [x] CAP-0019 Target DB Credential Rotation Workflow
- [x] CAP-0020 Break-glass Read Access (TTL + dual approval)

## P1 - Expansion

- [x] CAP-0021 Jira Connector
- [x] CAP-0022 Zendesk Connector
- [x] CAP-0023 CRM Export Pack
- [x] CAP-0024 DB Dump Ingestion v2
- [x] CAP-0025 Data Access Request Workflow (CLI-first)
- [x] CAP-0026 Policy Pack Template Library
- [x] CAP-0027 Semantic Pack Library + tests
- [x] CAP-0028 Glossary/Data Dictionary Generator + export
- [x] CAP-0029 Alert Sinks for SLA/Drift
- [x] CAP-0030 Per-role Query Budgets + query explain CLI
- [x] CAP-0031 Target DB Index/Materialization Recommendations
- [x] CAP-0032 Gateway HA Mode + optional Redis
- [x] CAP-0033 Environment Promotion (signed export/import + policy simulation gates)
- [x] CAP-0034 Build Attestation Signing
- [x] CAP-0035 Deletion/Retention Attestation

## P2 - Advanced Optional

- [x] CAP-0036 Optional NATS Run Queue Adapter
- [x] CAP-0037 Multi-target Shadow Cutover
- [x] CAP-0038 Lineage Graph API + export
- [x] CAP-0039 Tokenization Vault (optional)
- [x] CAP-0040 Policy-bound Sampling Endpoint

## Notes

- CAP-0001/0002/0003 were implemented as deterministic reference connectors.
- CAP-0004/0005/0006/0018 were introduced in this implementation cycle.
- CAP-0007/0008/0009/0010/0013 were already present and validated as existing capabilities.
- CAP-0011/0014/0015/0017 were implemented as tooling + CLI additions in this cycle.
- CAP-0012 was hardened with explicit plugin env allowlists and connector row limits.
