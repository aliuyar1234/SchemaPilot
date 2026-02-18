# TASKLIST_NEXT_V2.md — Post-milestone Next Wave

> No timelines. Grouped by priority and dependency.
> IDs: V2-0001..V2-0032.

## P0 — Operability + ecosystem trust (ship first)

- [x] V2-0005 Strict config schema v2 (unknown keys fail; config file; redaction contract)
- [x] V2-0001 Audit outbox + sink dispatcher (decouple sinks; preserve fail-closed local audit)
  - depends: V2-0005 (config contract)
- [x] V2-0002 Run step DAG + step-level evidence/status
- [x] V2-0003 `schemapilot doctor` preflight checks
  - depends: V2-0005
- [x] V2-0004 `schemapilot diag bundle` (redacted support pack)
  - depends: V2-0002, V2-0005
- [x] V2-0032 Denials + review queue analytics CLI (`schemapilot analyze`)
  - depends: V2-0001, V2-0002
- [x] V2-0007 Pack signing + verification (policy/semantic/templates)
- [x] V2-0015 Pack compatibility matrix + auto-migration tooling
  - depends: V2-0007
- [x] V2-0031 Pack/connector CI templates (GitHub Actions)
  - depends: V2-0007, V2-0010

## P1 — Connector safety + high-value connectors

- [x] V2-0010 Connector conformance suite (“certification harness”)
- [x] V2-0014 Incremental ingestion standard (cursor/state contract)
  - depends: V2-0010
- [x] V2-0012 SFTP connector plugin (read-only strict)
  - depends: V2-0010, V2-0014
- [x] V2-0011 Google Drive connector plugin (read-only snapshot)
  - depends: V2-0010, V2-0014
- [x] V2-0013 IMAP email ingestion connector (incremental + attachments)
  - depends: V2-0010, V2-0014

## P1 — Operator workflows via CLI (no UI creep)

- [x] V2-0016 CLI interactive onboarding (`schemapilot init`)
  - depends: V2-0003
- [x] V2-0017 Review queue TUI/CLI improvements (batch approve w/ safeguards)
  - depends: V2-0002
- [x] V2-0018 CLI query console (provenance + citations formatting/export)
- [x] V2-0019 Policy simulation CLI + auditor report generator (no data)

## P2 — Performance and stability

- [x] V2-0020 Policy-aware query result cache (gateway) (disabled-by-default)
- [x] V2-0021 Materialized metric refresh manager (scheduled) (opt-in)
  - depends: V2-0020
- [x] V2-0022 Worker resource quotas per step (cpu/mem/time)
  - depends: V2-0002
- [x] V2-0023 Large-file streaming + backpressure in connectors
- [x] V2-0024 Trino audit correlation + plan/cost introspection improvements

## P2 — Security/observability hardening

- [x] V2-0025 OpenTelemetry tracing (GW/CP/workers) (disabled-by-default)
- [x] V2-0009 Tighten plugin sandbox: network/file allowlists + resource/time limits
- [x] V2-0026 Security fuzzing: SQL safety + retrieval sanitization (release-gate first)
- [x] V2-0027 Expanded chaos drills integrated into release gate
- [x] V2-0008 Release supply-chain: SBOM + signed images + provenance (release-only gate)

## P3 — Higher-risk enterprise features (last)

- [x] V2-0028 Deletion verification attestation + signed evidence
- [x] V2-0029 Optional local artifact encryption (envelope) + key rotation (opt-in)
- [x] V2-0030 Reference deployments + upgrade playbooks (compose + helm)
- [x] V2-0006 Policy pack staged rollout (canary apply + simulation gates)
