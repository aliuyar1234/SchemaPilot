# checks/CHECKS_INDEX.md

## Checks Index

This file defines all check IDs referenced by this SSOT pack.

Evidence pointer rule:
- All evidence pointers must follow:
  evidence: README.md :: Where to find X
evidence: checks/CHECKS_INDEX.md :: CHK-EVIDENCE-POINTER-FORMAT

### SSOT pack integrity checks (apply to this ZIP)
- CHK-MANIFEST-VERIFY
- CHK-CORE-FILES
- CHK-FINGERPRINT-MATRIX
- CHK-NO-ADHOC-FILES
- CHK-EVIDENCE-POINTER-FORMAT
- CHK-REF-INTEGRITY
- CHK-FORBIDDEN-TERMS
- CHK-QAC-COVERAGE
- CHK-SLOP-MAPPING

### Implementation repo checks (apply to the code repo once implemented)
- CHK-TOOLING-BASELINE
- CHK-SMOKE
- CHK-BOUNDARY-FITNESS
- CHK-NONBYPASS-E2E
- CHK-POLICY-DENY-BY-DEFAULT
- CHK-SEC-STARTUP
- CHK-SECRETS-HYGIENE
- CHK-SEC-STATIC
- CHK-SUPPLY-CHAIN
- CHK-TIMEOUTS-RETRIES
- CHK-DETERMINISM
- CHK-ERROR-PATHS
- CHK-GOLD-PUBLISH-GATES
- CHK-MIGRATIONS
- CHK-CONTRACT-COMPAT
- CHK-UPGRADE-DRILL
- CHK-PERF-HARNESS
- CHK-EVIDENCE-COMPLETENESS
- CHK-DUPLICATION
- CHK-BACKUP-RESTORE

---

## CHK-MANIFEST-VERIFY

Purpose:
- Detect drift by verifying MANIFEST.sha256 matches current file hashes.

Type:
- Automated (scriptable)

How to run (from the directory containing MANIFEST.sha256):
```bash
python - <<'PY'
import hashlib, pathlib, sys

base = pathlib.Path(".")
manifest = base/"MANIFEST.sha256"
lines = [ln.strip() for ln in manifest.read_text(encoding="utf-8").splitlines() if ln.strip()]
ok = True
for ln in lines:
    h, rel = ln.split("  ", 1)
    p = base/rel
    data = p.read_bytes()
    hh = hashlib.sha256(data).hexdigest()
    if hh != h:
        ok = False
        print(f"FAIL {rel}: expected {h} got {hh}")
if ok:
    print("PASS")
sys.exit(0 if ok else 1)
PY
```

Pass/fail rule:
- PASS if output is `PASS` and exit code is 0.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: Preflight Self-Audit Results
- evidence: PROGRESS.md :: Session history (SSOT pack only)

---

## CHK-CORE-FILES

Purpose:
- Ensure non-omittable core files exist.

Type:
- Manual or automated

How to run:
- Confirm these files exist at root:
  - README.md, AGENTS.md, CONSTITUTION.md, DECISIONS.md, ASSUMPTIONS.md, PROGRESS.md, CHANGELOG.md, AUDIT_REPORT.md, MANIFEST.sha256
- Confirm these exist:
  - spec/00_PROJECT_FINGERPRINT.md
  - spec/01_SCOPE.md
  - spec/10_PHASES_AND_TASKS.md
  - spec/11_QUALITY_GATES.md
  - templates/SESSION_PROTOCOL.md
  - templates/PR_REVIEW_CHECKLIST.md
  - checks/CHECKS_INDEX.md

Pass/fail rule:
- PASS if all exist.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: SSOT SCORECARD

---

## CHK-FINGERPRINT-MATRIX

Purpose:
- Validate Spec Applicability Matrix is complete and consistent.

Type:
- Manual or automated

How to run:
- In spec/00, confirm each spec/00..12 row is present with APPLICABLE or NON-APPLICABLE.
  - evidence: spec/00_PROJECT_FINGERPRINT.md :: Spec Applicability Matrix
- Cross-check filesystem:
  - If APPLICABLE → file exists
  - If NON-APPLICABLE → file does not exist

Pass/fail rule:
- PASS if matrix and filesystem match bidirectionally.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: Spec Applicability Matrix Compliance

---

## CHK-NO-ADHOC-FILES

Purpose:
- Ensure the SSOT file tree contains only canonical paths after applying Omit Policy.

Type:
- Automated (scriptable)

How to run:
- List all files and compare to the canonical structure.
- Allowed variability:
  - spec/* presence is governed only by the matrix in spec/00
  - checks/QUESTIONS_FOR_USER.md exists only if at least one question exists

Pass/fail rule:
- PASS if every file path is expected and no expected file is missing.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: Canonical Tree Compliance

---

## CHK-EVIDENCE-POINTER-FORMAT

Purpose:
- Ensure evidence pointers are machine-parseable.

Type:
- Automated (scriptable)

How to run:
- Scan all Markdown files for *occurrences* of evidence pointers using the required syntax:
  - `evidence: <relative/path> :: <heading-or-unique-phrase>`
- Treat an evidence pointer as any substring matching:
  - `evidence:\s*[A-Za-z0-9_./-]+\s*::\s*[^\n]+`
- FAIL if any detected evidence pointer does not match the pattern above exactly.

Pass/fail rule:
- PASS if every detected evidence pointer matches the required format.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: Reference Integrity

---

## CHK-REF-INTEGRITY

Purpose:
- Verify that all references resolve and IDs exist.

Type:
- Automated (scriptable)

Scope (normative):
- A “reference” is ONLY:
  1) an evidence pointer in the required format, or
  2) a Markdown link to a relative path.

Evidence pointer extraction (normative):
- Evidence pointers MUST be detected using the same pattern as:
  - evidence: checks/CHECKS_INDEX.md :: CHK-EVIDENCE-POINTER-FORMAT
- The extracted `(path, phrase)` MUST be trimmed of surrounding whitespace.
- When evidence pointers appear inside Markdown tables, the extraction MUST ignore any trailing table delimiter `|` after the phrase.

How to run:
- For each evidence pointer:
  - verify referenced relative path exists
  - verify the `heading-or-unique-phrase` appears as a substring in the referenced file
- For each relative Markdown link:
  - verify the target file exists
- Verify referenced IDs exist:
  - D- IDs exist in DECISIONS.md
  - A- IDs exist in ASSUMPTIONS.md
  - Q- IDs exist in checks/QUESTIONS_FOR_USER.md (if present)
  - T- IDs exist in spec/10
  - SB- IDs exist in CONSTITUTION.md
  - CHK- IDs exist in this file
- Ensure omitted specs are not referenced except via AUDIT_REPORT “Omitted Artifacts”.

Pass/fail rule:
- PASS if all references and IDs resolve.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: Reference Integrity

---

## CHK-FORBIDDEN-TERMS

Purpose:
- Enforce “no placeholders” discipline by preventing placeholder tokens outside this section.

Type:
- Automated (scriptable)

Forbidden placeholder token list (MUST appear only here):
- TBD
- FIXME
- WIP
- <<FILL_ME>>
- __REPLACE_ME__
- LOREM_IPSUM
- ???

How to run:
- Scan all files in the SSOT pack EXCEPT checks/CHECKS_INDEX.md.
- FAIL if any forbidden token appears.

Pass/fail rule:
- PASS if none of the forbidden tokens appear outside this section.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: Forbidden Terms Scope

---

## CHK-QAC-COVERAGE

Purpose:
- Ensure every quality attribute in spec/00 has at least one gate and that gates map to checks or manual verification.

Type:
- Manual or automated

How to run:
- Verify spec/00 Quality Attribute Profile rows map to gates/checks.
  - evidence: spec/00_PROJECT_FINGERPRINT.md :: Quality Attribute Profile (QAC)
- Verify spec/11 includes at least one gate per attribute.
  - evidence: spec/11_QUALITY_GATES.md :: Gate Index

Pass/fail rule:
- PASS if coverage exists and mappings are explicit.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: QAC Coverage

---

## CHK-SLOP-MAPPING

Purpose:
- Ensure SB-0001..SB-0012 are fully mapped to enforcement mechanisms.

Type:
- Manual or automated

How to run:
- Verify mapping table contains every SB rule exactly once and maps to checks/checklist.
  - evidence: spec/11_QUALITY_GATES.md :: SLOP_BLACKLIST Enforcement Mapping

Pass/fail rule:
- PASS if every SB rule is present and mapped.
- FAIL otherwise.

Evidence recording location:
- evidence: AUDIT_REPORT.md :: SLOP_BLACKLIST Mapping

---

## CHK-TOOLING-BASELINE

Purpose:
- Ensure formatting/lint/typecheck/tests run deterministically.

Type:
- Automated (CI)

How to run:
- Run the single entrypoint:
  - `schemapilot check`

Pass/fail rule:
- PASS if all tooling steps succeed and exit code is 0.
- FAIL otherwise.

Evidence recording location:
- Implementation repo CI artifacts + PROGRESS evidence pointers.

---

## CHK-SMOKE

Purpose:
- Verify minimal runnable path starts and health endpoints respond.

Type:
- Automated

How to run:
- Start services in dev/compose mode.
- Call `/api/v1/health` and gateway health.
- Verify UI loads.

Pass/fail rule:
- PASS if all health checks succeed.
- FAIL otherwise.

Evidence recording location:
- CI logs and screenshots as needed.

---

## CHK-BOUNDARY-FITNESS

Purpose:
- Enforce dependency direction and prevent cross-layer coupling.

Type:
- Automated (CI)

How to run:
- Run dependency rule tools (import-linter / dependency-cruiser or equivalents).
- Run static checks ensuring non-gateway code cannot import engine/index clients.

Pass/fail rule:
- PASS if no forbidden dependencies/imports exist.
- FAIL otherwise.

Evidence recording location:
- CI check output.

---

## CHK-NONBYPASS-E2E

Purpose:
- Validate gateway is the only access path at runtime.

Type:
- Automated (integration/e2e)

How to run:
- In a production-like compose profile, attempt direct connections to engine/index ports.
- Validate direct TCP connections to expected engine/index ports are blocked from non-gateway clients
  (baseline ports: Trino `8083`, OpenSearch `9200`, Qdrant `6333`).
- Attempt gateway queries and confirm they succeed with provenance.

Pass/fail rule:
- PASS if direct connections fail and gateway path succeeds.
- FAIL otherwise.

Evidence recording location:
- CI logs.

---

## CHK-POLICY-DENY-BY-DEFAULT

Purpose:
- Ensure protected operations are denied unless explicitly allowed.

Type:
- Automated

How to run:
- Run tests with empty policy set and with policy engine unavailable.
- Confirm access is denied for protected operations.

Pass/fail rule:
- PASS if denials occur as required.
- FAIL otherwise.

Evidence recording location:
- CI logs.

---

## CHK-SEC-STARTUP

Purpose:
- Validate safe startup defaults (localhost bind; fail-to-start on non-local without auth).

Type:
- Automated

How to run:
- Start with default config: confirm local bind only.
- Start with non-local bind and no auth: confirm process exits with clear error.
- Start with non-local bind and auth: confirm requests require auth.

Pass/fail rule:
- PASS if behaviors match.
- FAIL otherwise.

Evidence recording location:
- CI logs.

---

## CHK-SECRETS-HYGIENE

Purpose:
- Prevent secrets in repo and logs.

Type:
- Automated

How to run:
- Run secret scanning tool over repo.
- Run tests ensuring logs redact secret patterns.

Pass/fail rule:
- PASS if no secrets detected and redaction tests pass.
- FAIL otherwise.

Evidence recording location:
- CI logs.
---

## CHK-SEC-STATIC

Purpose:
- Run static security analysis to detect common issues early (unsafe APIs, dependency vulnerabilities).

Type:
- Automated (CI)

How to run:
- Run Python static security scanner (example: bandit) on backend code.
- Run dependency vulnerability scanning (example: pip-audit / npm audit) with allowlisted suppressions.

Pass/fail rule:
- PASS if no high-severity findings exist without an explicit DECISIONS entry and mitigation.
- FAIL otherwise.

Evidence recording location:
- CI security scan reports + DECISIONS (for approved suppressions).


---

## CHK-SUPPLY-CHAIN

Purpose:
- Ensure plugin allowlisting and optional integrity checks are enforced.

Type:
- Automated + manual (Enterprise)

How to run:
- Attempt to load a non-allowlisted plugin; must fail.
- Validate plugin capabilities are restricted.

Pass/fail rule:
- PASS if enforcement works and tests exist.
- FAIL otherwise.

Evidence recording location:
- CI logs + security review notes.

---

## CHK-TIMEOUTS-RETRIES

Purpose:
- Enforce bounded retries and timeouts.

Type:
- Automated (lint/tests)

How to run:
- Static scan for network calls without timeouts.
- Tests validate retry caps.

Pass/fail rule:
- PASS if no missing timeouts and retry caps enforced.
- FAIL otherwise.

Evidence recording location:
- CI logs.

---

## CHK-DETERMINISM

Purpose:
- Detect non-deterministic outputs in builds and scoring.

Type:
- Automated

How to run:
- Run deterministic build tests twice; compare outputs.
- Run decision engine on fixed inputs; compare ranking and report outputs.

Pass/fail rule:
- PASS if outputs match.
- FAIL otherwise.

Evidence recording location:
- CI artifacts (diff reports).

---

## CHK-ERROR-PATHS

Purpose:
- Ensure negative-path tests exist and run.

Type:
- Automated

How to run:
- Execute test suite including explicit negative-path cases.

Pass/fail rule:
- PASS if negative-path tests run and pass.
- FAIL otherwise.

Evidence recording location:
- CI logs.

---

## CHK-GOLD-PUBLISH-GATES

Purpose:
- Ensure gold publish pointer updates only after gates.

Type:
- Automated

How to run:
- Create a contract failure scenario and ensure publish does not occur.
- Resolve contracts and ensure publish occurs.

Pass/fail rule:
- PASS if pointer behavior matches spec.
- FAIL otherwise.

Evidence recording location:
- CI logs and artifact pointers.

---

## CHK-MIGRATIONS

Purpose:
- Ensure database migrations apply cleanly and are safe.

Type:
- Automated

How to run:
- Apply migrations from empty DB.
- Upgrade from a previous snapshot state.

Pass/fail rule:
- PASS if migrations succeed and tests pass.
- FAIL otherwise.

Evidence recording location:
- CI logs.

---

## CHK-CONTRACT-COMPAT

Purpose:
- Prevent public contract drift.

Type:
- Automated

How to run:
- Schema validation for API payloads and file formats.
- Snapshot tests for template IDs and recommendation report format.

Pass/fail rule:
- PASS if validation succeeds and snapshots match.
- FAIL otherwise.

Evidence recording location:
- CI artifacts.

---

## CHK-UPGRADE-DRILL

Purpose:
- Validate profile upgrade without re-ingestion.

Type:
- Automated (CI)

How to run:
- Run Starter profile pipeline on a fixed dataset.
- Upgrade to Team and re-materialize from bronze.
- Validate dataset IDs stable and gold semantics still correct.

Pass/fail rule:
- PASS if upgrade succeeds and validations pass.
- FAIL otherwise.

Evidence recording location:
- CI logs and reports.

---

## CHK-PERF-HARNESS

Purpose:
- Provide baseline capture and regression detection.

Type:
- Automated

How to run:
- Execute perf harness on fixed dataset and query set.
- Compare results to stored baseline.

Pass/fail rule:
- PASS if no regression beyond configured threshold, or if a decision+mitigation exists.
- FAIL otherwise.

Evidence recording location:
- CI perf artifacts + DECISIONS (for approved regressions).

---

## CHK-EVIDENCE-COMPLETENESS

Purpose:
- Ensure proposals and recommendation reports include required fields.

Type:
- Automated

How to run:
- Validate proposal/report schemas in tests.
- E2E test ensures UI renders evidence/confidence and blocks missing fields.

Pass/fail rule:
- PASS if schema validation and tests succeed.
- FAIL otherwise.

Evidence recording location:
- CI logs.

---

## CHK-DUPLICATION

Purpose:
- Detect copy-paste duplication in critical logic modules.

Type:
- Automated

How to run:
- Run duplication detector on targeted directories (policy, gateway, manifest handling).
- Fail if duplication above threshold unless decision record exists.

Pass/fail rule:
- PASS if under threshold or decision record exists with mitigation.
- FAIL otherwise.

Evidence recording location:
- CI report + DECISIONS.

---

## CHK-BACKUP-RESTORE

Purpose:
- Ensure backup and restore procedures are tested.

Type:
- Manual initially; automated later

How to run:
- Execute restore drill procedure in runbook.
  - evidence: spec/12_RUNBOOK.md :: Backup and Restore

Pass/fail rule:
- PASS if restore drill succeeds and evidence recorded.
- FAIL otherwise.

Evidence recording location:
- PROGRESS evidence pointers to drill logs.
