# Assessment report and handoff template

Read this reference when preparing the deliverables. Fill only sections supported by the assessment; use `not-applicable`, `unknown`, or `insufficient-evidence` rather than inventing detail.

## Findings report

### Scope and posture

- **Repository and revision:**
- **Question being assessed:**
- **Included surfaces / harnesses:**
- **Excluded surfaces:**
- **Read-only evidence used:**
- **Evidence not available or not authorized:**
- **Decision requested from the report:** (for example: prioritize a brief, gather evidence, or defer)

### Baseline and authorities

| Behavior / surface | Current owner | Baseline behavior | Evidence status | Constraint to preserve |
| --- | --- | --- | --- | --- |

List documentation separately when it conflicts with or exceeds source/test evidence.

### Evidence ledger

| ID | Claim | Evidence and provenance | Scope | Categorical status | Counterevidence, alternative explanation, or gap |
| --- | --- | --- | --- | --- |

### Pain signals and applicability

| Candidate signal | Recurrence evidence | Affected scope | No-fit / unaffected scope | Preconditions and constraints | Assessment |
| --- | --- | --- | --- | --- |

Permitted assessments: `candidate`, `defer`, `not-applicable`, `unknown`, `insufficient-evidence`.

### Candidate assessment

For each candidate retained:

- **Hypothesis:** State a falsifiable relationship between a named cohort, a bounded intervention, and an outcome.
- **Baseline:** Name the actual existing policy/behavior and its version or revision.
- **Ordinary control:** Explain the comparison that separates the intervention from a generic retry or unrelated change.
- **Candidate:** Smallest scoped change, exact authority that would own it, and fixed boundaries it cannot change.
- **Expected tradeoff:** State as a hypothesis, never a guaranteed gain.
- **Numeric confidence/probability, if used:** Prediction target, provenance, and validation status; otherwise state `not used`.
- **Counterevidence and falsification:** What result, subgroup, or observation would reject it?
- **Applicability:** Included harnesses/environments and explicit no-fit cases.
- **Prerequisites:** Evidence, isolation, permissions, or release gates still needed.
- **Recommendation:** `prepare brief`, `collect evidence`, `manual-only`, `defer`, or `no supported intervention`.

### Evaluation and release posture

| Item | Requirement |
| --- | --- |
| Cohort | Define inclusion/exclusion and group related variants to prevent leakage. |
| Arms | Baseline, ordinary control, candidate. Keep assurance/acceptance fixed. |
| Resources | Comparable ceilings; retain all attempts and unknown external outcomes. |
| Labels | Source, owner, provenance, and timing. |
| Measures | Completion/acceptance plus regressions, resource use, operator effort, and false-action risk as applicable. |
| Analysis | Report sample counts, exclusions, missingness, and `insufficient-evidence` rather than overclaiming. |
| Promotion | Human approval bound to immutable evidence, candidate, scope, and version. |
| Rollback | Previous compatible policy/configuration for future runs; do not erase evidence or claim to undo external effects. |

### Decision and next handoff

State one of: `no supported intervention`, `evidence collection needed`, `draft task brief(s)`, or `requires explicit authorization`. Include what would change the conclusion.

## Task brief

### [ID] Title

- **Objective and success condition:**
- **Scope / out of scope:**
- **Existing authorities and contracts to preserve:**
- **Evidence motivating the task:** links to findings IDs; distinguish observed from inferred.
- **Proposed bounded change:** data/configuration/interface only as appropriate; no automatic activation.
- **No-fit cases and counterexamples:**
- **Acceptance criteria:**
- **Verification:** deterministic or offline checks first; no network/provider call by default.
- **Evaluation dependency:** baseline/control/candidate detail or reason this is an evidence-collection task.
- **Release posture:** advisory, shadow, manual approval, or deferred; never infer active promotion.
- **Authorization required later:** private data, credentials, paid access, live evaluation, release/publish, if any.
- **Rollback / no-promotion condition:**
- **Open questions:**
