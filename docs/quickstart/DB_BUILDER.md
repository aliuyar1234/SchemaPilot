# Database Builder Quickstart (CLI-First)

This guide walks through the target database flow:

1. create target profile
2. validate
3. provision plan/apply
4. migration plan/apply
5. load plan/apply
6. sync run/status
7. query only through gateway

## 1) Create a target DB profile

```bash
schemapilot target-db create \
  --workspace <workspace_id> \
  --name serving-db \
  --type sqlite \
  --mode managed
```

## 2) Validate profile/credentials

```bash
schemapilot target-db validate \
  --workspace <workspace_id> \
  --target-db <target_db_id> \
  --wait
```

## 3) Provision

```bash
schemapilot target-db provision-plan \
  --workspace <workspace_id> \
  --target-db <target_db_id> \
  --wait

schemapilot target-db provision-apply \
  --workspace <workspace_id> \
  --target-db <target_db_id> \
  --plan-id <plan_id> \
  --expected-checksum <plan_checksum> \
  --wait
```

## 4) Plan/apply migrations

```bash
schemapilot target-db migrate-plan \
  --workspace <workspace_id> \
  --target-db <target_db_id> \
  --semantic <semantic_manifest_id> \
  --build <build_id> \
  --wait

schemapilot target-db migrate-apply \
  --workspace <workspace_id> \
  --target-db <target_db_id> \
  --plan-id <plan_id> \
  --expected-checksum <plan_checksum> \
  --wait
```

## 5) Initial load and publish

```bash
schemapilot target-db load-plan \
  --workspace <workspace_id> \
  --target-db <target_db_id> \
  --build <build_id> \
  --datasets gold.fact_metrics \
  --wait

schemapilot target-db load-apply \
  --workspace <workspace_id> \
  --target-db <target_db_id> \
  --plan-id <plan_id> \
  --expected-checksum <plan_checksum> \
  --publish-on-success \
  --wait
```

## 6) Incremental sync

```bash
schemapilot target-db sync-run \
  --workspace <workspace_id> \
  --target-db <target_db_id> \
  --datasets ds_invoices ds_customers \
  --strict \
  --wait

schemapilot target-db sync-status \
  --workspace <workspace_id> \
  --target-db <target_db_id>
```

## 7) Query via gateway (single enforcement point)

```bash
schemapilot query \
  --workspace <workspace_id> \
  --sql "select metric, value from fact_metrics" \
  --dataset-id dataset-1
```

## Operator checks

- Preflight: `schemapilot doctor`
- Diagnostics bundle: `schemapilot diag-bundle --workspace <workspace_id>`
- Governance analytics: `schemapilot analyze --workspace <workspace_id>`
