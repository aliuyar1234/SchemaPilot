# GPT Pro Next-Wave Plan (Noted)

Source: user-provided GPT Pro response  
Purpose: preserve proposed next-feature direction and architecture evolution in-repo for execution planning.

## Current state (as captured)

- Project is in a security-hardened Team-ready core state.
- Gateway-only enforcement, fail-closed audit, deterministic ingest/build, review gates, policy-pack lifecycle, retention/deletion controls are in place.
- Multi-engine query path exists (DuckDB default, Trino opt-in behind gateway).
- Main blockers to become default OSS AI-readiness platform:
  - first-hour value density (connectors, semantic layer, safe AI workflows),
  - ecosystem scale (plugins/packs/dev ergonomics),
  - hardened distribution path (compose + helm/k8s with strict no-bypass defaults).

## Architecture evolution proposed

1. AEP-01: Semantic layer as first-class subsystem.
- Add semantic manifest schema/validator + lifecycle + resolver.
- Enable semantic-bound query mode for AI identities.

2. AEP-02: Optional document index modules behind gateway.
- OpenSearch/Qdrant style modules optional and disabled-by-default.
- Strict no-bypass networking and policy-filtered retrieval.

3. AEP-03: Optional AI service.
- AI service talks only to gateway/control-plane, never directly to engines/indexes.
- Full audit/provenance and fail-closed module gating.

4. AEP-04: Secrets store abstraction.
- Local-encrypted default + optional enterprise secret-store adapter.

## Priority direction captured

- P0: semantic manifest + semantic-bound AI query mode + template packs + docs indexing + AI skeleton.
- P1: operability and scale (scheduling, fairness, budgets, policy simulation, audit sinks).
- P2: ecosystem acceleration (demo generator, registry/packs, docs wave, typed clients, anomaly/ER v2).

## AI track captured

- Safe SQL agent constrained by semantic manifest.
- Doc QA with citations behind gateway retrieval.
- Catalog/join/contract/drift/PII assistants that produce evidence + review tasks.
- Policy simulation assistant and AI evaluation harness.
- All risky automation remains approval-gated and fail-closed.

## Execution artifact

- `TASKLIST_NEXT.md` stores the actionable checklist (NW-0001..NW-0034) copied from the GPT Pro proposal format.
