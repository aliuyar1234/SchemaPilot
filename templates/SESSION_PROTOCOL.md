# templates/SESSION_PROTOCOL.md

## SESSION_START

1) Verify drift status
- Run CHK-MANIFEST-VERIFY (SSOT pack) before making changes.
- If it fails, session is BLOCKED until MANIFEST is regenerated and verified.
evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY

2) Read required files in order
- README.md
- AGENTS.md
- CONSTITUTION.md
- spec/* (numeric order)
- DECISIONS.md
- ASSUMPTIONS.md
- PROGRESS.md
- checks/QUESTIONS_FOR_USER.md (if present)
- AUDIT_REPORT.md

3) Declare planned changes
For each planned change, state:
- what will change
- which critical flows are impacted (YES/NO)
- what gates/checks will be affected

Critical flow list:
evidence: spec/00_PROJECT_FINGERPRINT.md :: Critical Flow Inventory

4) Run DSC for uncertainties
- For every ambiguity or missing datum, run the Decision Safety Classifier.
- Record:
  - decisions in DECISIONS.md (D-IDs),
  - assumptions in ASSUMPTIONS.md (A-IDs),
  - questions in checks/QUESTIONS_FOR_USER.md (Q-IDs; blocking YES/NO).
evidence: spec/00_PROJECT_FINGERPRINT.md :: Decision Safety Classifier

5) Confirm conservative baselines
- For non-blocking questions, proceed with conservative fail-closed baselines and record them.
evidence: CONSTITUTION.md :: Fail-closed by default

## SESSION_END

1) Update logs
- Update DECISIONS.md for any new decisions or structural changes.
- Update ASSUMPTIONS.md for any assumptions introduced/retired.
- Update PROGRESS.md statuses and add evidence pointers for DONE tasks.
evidence: PROGRESS.md :: Evidence Pointer Rules

2) Update CHANGELOG.md (SSOT pack changes only)
- Record which SSOT docs changed and why (reference D-IDs).

3) Regenerate MANIFEST.sha256
- Run generator and verify CHK-MANIFEST-VERIFY passes.
- If not regenerated, acceptance is blocked.
evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY

4) Record new questions
- Add new Q-IDs with blocking YES/NO classification.
evidence: checks/QUESTIONS_FOR_USER.md :: Questions for User

## QUESTION_ENTRY_FORMAT

Each question entry MUST include:

- Q-ID
- blocking: YES/NO
- why needed
- what it blocks
- safe default if non-blocking
- where encoded (decision/assumption/config)
- what proceeds safely now
- risk if wrong
