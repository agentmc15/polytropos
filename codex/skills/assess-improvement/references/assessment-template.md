# Assessment report and handoff template

Read this reference when preparing deliverables. Fill only supported sections; use `not-applicable`, `unknown`, or `insufficient-evidence` rather than inventing detail.

## Findings report

### Scope and posture

- **Repository and revision:**
- **Question being assessed:**
- **Included surfaces / harnesses:**
- **Excluded surfaces:**
- **Read-only evidence used:**
- **Evidence not available or not authorized:**
- **Decision requested from the report:**

### Baseline and authorities

| Behavior / surface | Current owner | Baseline behavior | Evidence status | Constraint to preserve |
| --- | --- | --- | --- | --- |

List documentation separately when it conflicts with or exceeds source or test evidence.

### Evidence ledger

| ID | Claim | Evidence and provenance | Scope | Categorical status | Counterevidence, alternative explanation, or gap |
| --- | --- | --- | --- | --- | --- |

### Pain signals and applicability

| Candidate signal | Recurrence evidence | Affected scope | No-fit / unaffected scope | Preconditions and constraints | Assessment |
| --- | --- | --- | --- | --- | --- |

Permitted assessments: `candidate`, `defer`, `not-applicable`, `unknown`, `insufficient-evidence`.

### Candidate assessment

For each retained candidate:

- **Hypothesis:** falsifiable relationship between a named cohort, bounded intervention, and outcome.
- **Baseline:** actual existing policy or behavior and its revision.
- **Ordinary control:** comparison separating the intervention from a generic retry or unrelated change.
- **Candidate:** smallest scoped change, its owner, and boundaries it cannot change.
- **Expected tradeoff:** a hypothesis, never a guaranteed gain.
- **Numeric confidence/probability, if used:** target, provenance, and validation; otherwise `not used`.
- **Counterevidence and falsification:** result, subgroup, or observation that rejects it.
- **Applicability:** included environments and explicit no-fit cases.
- **Prerequisites:** evidence, isolation, permissions, or release gates still needed.
- **Recommendation:** `prepare brief`, `collect evidence`, `manual-only`, `defer`, or `no supported intervention`.

### Evaluation and release posture

| Item | Requirement |
| --- | --- |
| Cohort | Define inclusion and exclusion; group related variants to prevent leakage. |
| Arms | Baseline, ordinary control, candidate; keep assurance and acceptance fixed. |
| Resources | Comparable ceilings; retain all attempts and unknown external outcomes. |
| Labels | Source, owner, provenance, and timing. |
| Measures | Completion/acceptance plus regressions, resource use, operator effort, and false-action risk as applicable. |
| Analysis | Report sample counts, exclusions, missingness, and `insufficient-evidence` rather than overclaiming. |
| Promotion | Human approval bound to immutable evidence, candidate, scope, and version. |
| Rollback | Previous compatible policy/configuration for future runs; preserve evidence and disclose external effects. |

### Decision and next handoff

State one of: `no supported intervention`, `evidence collection needed`, `draft task brief(s)`, or `requires explicit authorization`. Include what would change the conclusion.

## Task brief

### [ID] Title

- **Objective and success condition:**
- **Scope / out of scope:**
- **Existing authorities and contracts to preserve:**
- **Evidence motivating the task:** link findings IDs and distinguish observed from inferred.
- **Proposed bounded change:** data, configuration, or interface only as appropriate; no automatic activation.
- **No-fit cases and counterexamples:**
- **Acceptance criteria:**
- **Verification:** deterministic or offline checks first; no network/provider call by default.
- **Evaluation dependency:** baseline/control/candidate detail or why this is an evidence-collection task.
- **Release posture:** advisory, shadow, manual approval, or deferred; never infer active promotion.
- **Authorization required later:** private data, credentials, paid access, live evaluation, release, or publication.
- **Rollback / no-promotion condition:**
- **Open questions:**
