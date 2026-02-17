# templates/PR_REVIEW_CHECKLIST.md

## No Evidence, No Accept

Acceptance is blocked unless:
- [ ] Relevant quality gates are PASS and evidence is recorded.
  - evidence: spec/11_QUALITY_GATES.md :: No Evidence, No Accept / No Progress
- [ ] PROGRESS.md is updated for any task status changes, with evidence pointers for DONE tasks.
  - evidence: PROGRESS.md :: Evidence Pointer Rules
- [ ] MANIFEST.sha256 is regenerated after any SSOT pack change.
  - evidence: checks/CHECKS_INDEX.md :: CHK-MANIFEST-VERIFY

## SLOP_BLACKLIST Compliance

For each item, check the box and provide evidence pointers.

- [ ] SB-0001 Silent defaults in critical flows — evidence: ________
- [ ] SB-0002 God objects / mega-modules — evidence: ________
- [ ] SB-0003 Copy-paste duplication instead of abstraction — evidence: ________
- [ ] SB-0004 Untested error paths — evidence: ________
- [ ] SB-0005 Unbounded retries / missing timeouts — evidence: ________
- [ ] SB-0006 Hidden global state / implicit singletons — evidence: ________
- [ ] SB-0007 Naming/semantics drift — evidence: ________
- [ ] SB-0008 Logging without correlation OR leaking sensitive data — evidence: ________
- [ ] SB-0009 Contract drift (implementation ≠ interfaces/spec) — evidence: ________
- [ ] SB-0010 Convenience over fail-closed — evidence: ________
- [ ] SB-0011 One-off scripts without runbook/checks — evidence: ________
- [ ] SB-0012 Structural changes without decision log — evidence: ________

Mapping table:
evidence: spec/11_QUALITY_GATES.md :: SLOP_BLACKLIST Enforcement Mapping

## Structural changes recorded

- [ ] Any structural change (new component/module, new persistence surface, new external integration) has a DECISIONS.md entry with:
  - justification,
  - mitigation plan,
  - verification impact.
evidence: CONSTITUTION.md :: Exception process

## Questions classification and autonomy

- [ ] New questions are recorded with blocking YES/NO.
- [ ] Non-blocking questions did not halt progress; conservative baselines were used and logged.
evidence: templates/SESSION_PROTOCOL.md :: QUESTION_ENTRY_FORMAT

## Checks pass before acceptance

- [ ] CHK-FORBIDDEN-TERMS
- [ ] CHK-REF-INTEGRITY
- [ ] CHK-EVIDENCE-POINTER-FORMAT
- [ ] CHK-QAC-COVERAGE
- [ ] CHK-BOUNDARY-FITNESS

Check definitions:
evidence: checks/CHECKS_INDEX.md :: Checks Index
