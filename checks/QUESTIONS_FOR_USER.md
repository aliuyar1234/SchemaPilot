# checks/QUESTIONS_FOR_USER.md

## Questions for User

Questions are classified as blocking YES/NO per the autonomy policy.
Non-blocking questions MUST NOT halt progress; conservative fail-closed defaults are used and logged.

evidence: spec/00_PROJECT_FINGERPRINT.md :: Decision Safety Classifier

---

### Q-0001 — blocking: NO
- why needed: Retention, deletion, legal hold, and audit requirements are externally constrained (org policy and jurisdiction).
- what it blocks: Nothing in v1 baseline; blocks enabling automated retention enforcement and compliance claims.
- safe default if non-blocking: Retention enforcement disabled until explicitly configured; deletion only via explicit workflow with approvals and evidence report; no compliance claims.
- where encoded: spec/05 retention mechanics; spec/06 retention workflow; config keys in implementation.
- what proceeds safely now: Full ingestion/catalog/build/query flows with manual deletion workflow; audit logging enabled.
- risk if wrong: If retention obligations exist and enforcement is not configured, org may be non-compliant; baseline avoids claiming compliance.

---

### Q-0002 — blocking: NO
- why needed: Enterprise authentication standards (OIDC vs SAML), MFA, and identity attributes vary by org.
- what it blocks: Nothing in evaluation/team local-only; blocks exposing services publicly without correct auth integration.
- safe default if non-blocking: Bind localhost-only by default; if non-local bind is configured, require explicit auth configuration or fail to start.
- where encoded: DECISIONS D-0004; spec/06 auth; runbook safe exposure.
- what proceeds safely now: Local evaluation; Team deployments behind a reverse proxy with configured auth.
- risk if wrong: Public exposure without compliant auth would be unsafe; baseline prevents start.

---

### Q-0003 — blocking: NO
- why needed: Approved secret store and rotation processes are externally constrained.
- what it blocks: Nothing in dev/eval; blocks enterprise-grade secret management integration selection.
- safe default if non-blocking: Support environment variables and mounted secrets; add interface for secret manager; never store plaintext secrets.
- where encoded: spec/06 secrets handling; T-0005 stub interfaces.
- what proceeds safely now: All flows in local mode and controlled deployments.
- risk if wrong: If org disallows env-var secrets in prod, deployment needs secret manager integration; baseline avoids unsafe defaults.

---

### Q-0004 — blocking: NO
- why needed: Encryption requirements (in transit, at rest, key management) are externally constrained.
- what it blocks: Nothing in local mode; blocks compliance claims and some enterprise deployments until configured.
- safe default if non-blocking: Require TLS when exposed; rely on platform encryption-at-rest controls; do not claim compliance.
- where encoded: spec/06 secure defaults; runbook deployment.
- what proceeds safely now: Local-only and secured deployments where operator configures TLS and storage encryption.
- risk if wrong: Misconfigured encryption could violate org policy; baseline limits exposure until configured.

---

### Q-0005 — blocking: NO
- why needed: Data egress constraints affect optional LLM/embedding integrations and retrieval features.
- what it blocks: Enabling external model providers.
- safe default if non-blocking: External model calls disabled by default; retrieval modules optional and policy-filtered.
- where encoded: T-0005 stub integrations; spec/06 PII and prompt injection controls.
- what proceeds safely now: SQL-first AI over gold via gateway; no external calls.
- risk if wrong: If egress is required but disabled, capability is reduced; safe.

---

### Q-0006 — blocking: NO
- why needed: Some orgs require specific query engines (Trino vs Spark vs ClickHouse) or disallow Java services.
- what it blocks: Selecting a non-default engine as the Team baseline.
- safe default if non-blocking: Team baseline uses Trino; Starter uses DuckDB; Decision Engine can recommend additional modules only with approval.
- where encoded: DECISIONS D-0002; spec/01 templates; runbook profiles.
- what proceeds safely now: Implement core flows against DuckDB and Trino.
- risk if wrong: If Trino is disallowed, Team deployment would need alternative engine; architecture keeps engines modular.

---

### Q-0007 — blocking: NO
- why needed: Required initial connector targets (SaaS, ERP, CRM) determine connector roadmap.
- what it blocks: Connector prioritization beyond baseline connectors.
- safe default if non-blocking: Implement filesystem + S3 + DB read-only connectors first; plugin system supports expansion.
- where encoded: ASSUMPTIONS A-0002; plugin decision D-0007.
- what proceeds safely now: Core ingestion and catalog flows for messy exports.
- risk if wrong: Adoption could be slower until required connectors ship.

---

### Q-0008 — blocking: NO
- why needed: Environment model (single env vs dev/stage/prod), promotion rules, and change control vary by org.
- what it blocks: Enterprise promotion workflows and stricter release governance.
- safe default if non-blocking: Support a single environment model initially; document how to run separate stacks for dev/stage/prod if required.
- where encoded: runbook deployment; operability gates.
- what proceeds safely now: OSS deployments and a simple “one env” ops model.
- risk if wrong: Enterprises may require stricter separation; baseline does not claim to satisfy it.
