# AGENTS.md — Operating Protocol (Highest Precedence)

This file defines **how to work** using this SSOT pack. If any other file conflicts with this, **this wins**.

## Precedence order (conflict resolution)

AGENTS.md

CONSTITUTION.md

spec/* (numeric order; existing files only)

DECISIONS.md

ASSUMPTIONS.md

README.md

templates/, checks/, runbook content

## Read-order vs precedence clarification (mandatory)

Read-order is onboarding guidance.

Precedence order is conflict resolution.

If they conflict, precedence wins.

## Mandatory session read-order (every session)

README → AGENTS → CONSTITUTION → spec/* (existing files only; numeric order) → DECISIONS → ASSUMPTIONS → PROGRESS → QUESTIONS (if present) → AUDIT_REPORT.

## Session protocol (mandatory)

- Follow:
  - evidence: templates/SESSION_PROTOCOL.md :: SESSION_START
  - evidence: templates/SESSION_PROTOCOL.md :: SESSION_END

- Every session MUST:
  - Update PROGRESS.md and DECISIONS.md if any decision or task status changes.
    - evidence: PROGRESS.md :: Task Status
    - evidence: DECISIONS.md :: Decision Index
  - Update ASSUMPTIONS.md when assumptions are introduced or retired.
    - evidence: ASSUMPTIONS.md :: Assumption Index
  - Regenerate MANIFEST.sha256 after **any** edit.
    - evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY
  - Classify uncertainties using DSC and record questions (blocking/non-blocking).
    - evidence: spec/00_PROJECT_FINGERPRINT.md :: Decision Safety Classifier

- Non-blocking questions MUST NOT halt progress:
  - proceed using the conservative baseline,
  - log the baseline (DECISIONS or ASSUMPTIONS),
  - add the question for later confirmation.
    - evidence: checks/QUESTIONS_FOR_USER.md :: Questions for User

## New session ramp-up checklist (copy/paste)

1) Verify drift state
   - Run CHK-MANIFEST-VERIFY; if it fails, session is BLOCKED until fixed.
   - evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY

2) Read in order
   - README.md
   - AGENTS.md
   - CONSTITUTION.md
   - spec/* (numeric order)
   - DECISIONS.md
   - ASSUMPTIONS.md
   - PROGRESS.md
   - checks/QUESTIONS_FOR_USER.md (if present)
   - AUDIT_REPORT.md

3) Declare intended changes (bullet list)
   - For each change, mark: critical flow impacted? (YES/NO)
   - evidence: spec/00_PROJECT_FINGERPRINT.md :: Critical Flow Inventory

4) Run DSC for every uncertainty
   - Record decisions (D-IDs) and assumptions (A-IDs) as required
   - Record questions (Q-IDs) with blocking YES/NO
   - evidence: spec/00_PROJECT_FINGERPRINT.md :: Decision Safety Classifier

5) Execute work against spec/10 tasks only
   - No ad-hoc task lists; no untracked work.
   - evidence: spec/10_PHASES_AND_TASKS.md :: PHASE_0_BOOTSTRAP

6) Update evidence
   - For every DONE task, add evidence pointers in PROGRESS.md (required).
   - evidence: PROGRESS.md :: Evidence Pointer Rules

7) Regenerate MANIFEST.sha256
   - Confirm CHK-MANIFEST-VERIFY passes after regeneration.
   - evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY
