# ASSUMPTIONS.md

## Assumption Index
- A-0001 Deployment baseline: Docker Compose on a single host is available for dev/eval
- A-0002 Initial connector set: filesystem + S3-compatible + basic DB read-only are sufficient for v1
- A-0003 Identity provider integration: OIDC/SAML are optional modules; local auth is acceptable for Starter/Team dev
- A-0004 Embeddings provider: vector embeddings are pluggable; default is disabled unless explicitly configured
- A-0005 Typical early adopters have limited historical query logs; wizard-collected intents are acceptable
- A-0006 OIDC trusted claims are supplied by a validated ingress/proxy in enterprise deployments

---

## A-0001 Deployment baseline: Docker Compose on a single host is available for dev/eval

**Assumption**  
A single host can run Docker Compose for development/evaluation deployments.

**Why**  
This is required to deliver an installable OSS experience with minimal friction.

**Risk if wrong**  
Users in restricted environments may require Kubernetes-only or air-gapped packaging earlier.

**How to validate**  
Track installation feedback and adoption; if a meaningful segment cannot use Compose, promote Kubernetes packaging earlier.

**Promote to decision when**  
A target customer profile mandates Kubernetes-only as an externally constrained requirement.

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (deployment/ops)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (document k8s path as optional)  
- Safe to decide: NO (assumption)

---

## A-0002 Initial connector set: filesystem + S3-compatible + basic DB read-only are sufficient for v1

**Assumption**  
The initial connectors cover the “messy reality” for most early adopters.

**Why**  
Allows core flows (discovery, bronze ingest, profiling, modeling, review, builds) without a large connector surface.

**Risk if wrong**  
If SaaS APIs are the primary data source, adoption slows until SaaS connectors exist.

**How to validate**  
Collect source inventories in early installs; prioritize missing connector classes.

**Promote to decision when**  
Connector roadmap becomes a committed compatibility surface.

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: YES (external I/O)  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES (manual export ingestion remains supported)  
- Safe to decide: NO (assumption)

---

## A-0003 Identity provider integration: OIDC/SAML are optional modules; local auth is acceptable for Starter/Team dev

**Assumption**  
Local auth is acceptable for non-production evaluation and Team deployments.

**Why**  
Enables fast setup while keeping secure-by-default behavior (localhost bind; deny-by-default).

**Risk if wrong**  
Enterprises may require SSO early; deployment blocks until implemented.

**How to validate**  
Ask adopters which IdP is required; track non-blocking questions.

**Promote to decision when**  
A specific enterprise IdP requirement is contractual or mandated.

**DSC summary**  
- Externally constrained: YES (enterprise standards vary)  
- Critical flow impacted: YES (auth)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (localhost-only + explicit auth required for non-local)  
- Safe to decide: NO (assumption)

---

## A-0004 Embeddings provider: vector embeddings are pluggable; default is disabled unless explicitly configured

**Assumption**  
Vector embeddings can be treated as an optional capability and do not block core SQL-first operation.

**Why**  
Embedding model choice is often externally constrained (privacy, costs, hosting). Disabling by default avoids unsafe defaults.

**Risk if wrong**  
Users may expect out-of-box retrieval over documents.

**How to validate**  
Measure demand for immediate doc QA; if required, ship a local embeddings option with clear constraints.

**Promote to decision when**  
A default embedding strategy becomes a supported compatibility surface.

**DSC summary**  
- Externally constrained: YES (privacy/hosting constraints vary)  
- Critical flow impacted: YES (sensitive data handling)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (disable retrieval modules)  
- Safe to decide: NO (assumption)

---

## A-0005 Typical early adopters have limited historical query logs; wizard-collected intents are acceptable

**Assumption**  
Most installations will not have existing query logs, so query intents must be collected via the wizard.

**Why**  
Decision Engine needs intents; wizard collection is the minimal viable evidence path.

**Risk if wrong**  
If query logs exist and are ignored, recommendations may be less precise than possible.

**How to validate**  
During onboarding, ask for existing BI/DB logs; add ingestion of logs if common.

**Promote to decision when**  
Query log ingestion is required for enterprise customers.

**DSC summary**  
- Externally constrained: NO  
- Critical flow impacted: NO  
- Unsafe/high-risk: NO  
- Conservative baseline available: YES  
- Safe to decide: NO (assumption)

---

## A-0006 OIDC trusted claims are supplied by a validated ingress/proxy in enterprise deployments

**Assumption**  
When `SCHEMAPILOT_AUTH_MODE=oidc` is enabled, upstream infrastructure validates identity tokens and forwards trusted claims to SchemaPilot.

**Why**  
SchemaPilot's gateway consumes a trusted claims header and applies fail-closed issuer/audience checks, but enterprise ingress hardening is environment-specific.

**Risk if wrong**  
If ingress is misconfigured and untrusted headers reach the gateway, actor context could be spoofed.

**How to validate**  
Verify ingress strips client-provided claims headers, enforces token validation, and injects only server-generated claims headers.

**Promote to decision when**  
An enterprise deployment standard defines mandatory ingress products/policies for claims forwarding.

**DSC summary**  
- Externally constrained: YES (enterprise network/IdP controls vary)  
- Critical flow impacted: YES (authentication and authorization)  
- Unsafe/high-risk: YES  
- Conservative baseline available: YES (deny on missing/invalid claims header and issuer/audience mismatch)  
- Safe to decide: NO (assumption)
