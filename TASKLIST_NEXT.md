# TASKLIST_NEXT.md — SchemaPilot Next Wave

> Captured from GPT Pro proposal and normalized as next execution board input.
> No timelines. IDs are stable: NW-0001..NW-0034.

## P0 — Must ship to unlock “default OSS AI-readiness” adoption

- [x] NW-0001 Semantic Manifest Schema + Validator (v1)
- [x] NW-0002 Control Plane Semantic Manifest Lifecycle (request/approve/publish/rollback)
  - depends: NW-0001
- [x] NW-0003 Worker Semantic Builder (bootstrap manifest from gold/silver + evidence)
  - depends: NW-0001, NW-0002 (draft storage)
- [x] NW-0004 Gateway Semantic Resolver + semantic-bound AI query mode
  - depends: NW-0002
- [x] NW-0005 Gold Template Packs (Invoices/CRM/Support) + CLI generator
  - depends: NW-0001 (semantic starter)
- [x] NW-0006 Document Connectors v1 (PDF/EML/MBOX) with extraction evidence scoring
- [x] NW-0007 Optional OpenSearch Index Module (behind gateway)
  - depends: NW-0006
- [x] NW-0008 Optional Qdrant Vector Index Module + Embedding Provider Interface
  - depends: NW-0006
- [x] NW-0009 Retrieval Policy Binding Enhancements (metadata-bound filters + masking)
  - depends: NW-0007 and/or NW-0008
- [x] NW-0010 Optional AI Service Skeleton (provider plugins, disabled-by-default)
  - depends: NW-0004
- [x] NW-0011 SQL Agent v1 (semantic constrained + plan validator)
  - depends: NW-0010, NW-0004
- [x] NW-0012 AI Eval Harness v1 (SQL agent + retrieval)
  - depends: NW-0011
- [x] NW-0013 Helm/K8s Distribution (hardened, no-bypass, secrets wiring)
- [x] NW-0014 Secrets Store Abstraction (local-encrypted default, Vault optional)
- [x] NW-0015 Connector SDK + Scaffold CLI + Reference SaaS Connectors (plugins)
  - depends: NW-0014

## P1 — Operability and scale (keep defaults safe; modules opt-in)

- [x] NW-0016 Catalog Export/Import (portable metadata snapshot, redacted)
- [x] NW-0017 Run Scheduling (cron-like) with fail-closed config
- [x] NW-0018 Multi-worker Scaling + Fairness (per-workspace concurrency quotas)
  - depends: NW-0017 (optional)
- [x] NW-0019 Query Cost Estimation + Budgets (bytes scanned, time, result size)
- [x] NW-0020 Audit Streaming Sink Plugins (SIEM/webhook/syslog), disabled-by-default
- [x] NW-0021 Policy Simulation API (no data)
- [x] NW-0022 Policy Pack Test Harness (prevent lockouts + invariants)
- [x] NW-0023 Semantic Drift Detection (manifest vs schema changes) + blocking tasks
  - depends: NW-0002
- [x] NW-0024 Column-level lineage derivation for deterministic SQL transforms (export)
- [x] NW-0025 Source Health + Freshness SLAs + Alerts

## P2 — Ecosystem acceleration + polish (still execution-grade)

- [x] NW-0026 “First hour demo” scenario generator (CLI + deterministic dataset)
- [x] NW-0027 Documentation wave (quickstart + security model + connector guide + ops)
- [x] NW-0028 Ecosystem distribution: “pack registry” (policy packs + semantic packs + connector examples)
  - depends: NW-0001, NW-0015
- [x] NW-0029 Trino/Iceberg operational hardening (cancellation, retries, compaction hooks)
- [x] NW-0030 Small-file management & compaction for Parquet/DuckDB mode
- [x] NW-0031 Data quality anomaly detection (distribution drift, outliers) + review tasks
- [x] NW-0032 Entity Resolution v2 (probabilistic matcher plugin + calibration + rollback)
- [x] NW-0033 Locale/encoding hardening (dates, currency, unicode normalization)
- [x] NW-0034 Typed client SDKs (Python) generated from OpenAPI + stability gate

## AI Feature Track (captured reference set)

- [x] AI-0101 AskSQL endpoint (NL -> semantic object -> SQL -> gateway)
- [x] AI-0102 Metric-first answering
- [x] AI-0103 Catalog assistant
- [x] AI-0104 Join-path suggestion assistant
- [x] AI-0105 Contract threshold proposer
- [x] AI-0106 Drift impact explainer
- [x] AI-0107 PII classification explainer
- [x] AI-0108 Entity-resolution merge suggestion assistant
- [x] AI-0109 Semantic model generator
- [x] AI-0110 Doc QA with citations
- [x] AI-0111 Policy simulation assistant
- [x] AI-0112 Query debugging assistant
- [x] AI-0113 Quality triage assistant
- [x] AI-0114 Release gate assistant
- [x] AI-0115 AI evaluation generator

## Non-blocking questions captured

- Embedding provider default for OSS examples (conservative default: disabled unless configured).
- Document search default module for Team/Enterprise (conservative default: optional profile only).
- Whether semantic enforcement should apply to human actors by default (conservative default: AI-first strict mode).
