# Recursive improvement research tasks

All tasks are pending planning briefs; see PLAN.md for cross-kit entry gates, selected execution authority and live-experiment boundaries. Model fields are Codex worker intents. Proposed tests are implementation deliverables, not currently passing evidence.

## Phase 1 — Records and lineage

### R01 — Backend ownership and versioned lineage contract
- id: R01
- title: Backend ownership and versioned lineage contract
- status: pending
- model: strong
- depends: (none)

**Brief.** Reconcile V1 and current backend; document field ownership and migration in this PLAN. Implement strict generation, improver and experiment contracts in bin/recursive_improvement.py, referencing V1 contracts rather than copying them. Add tests/test_recursive_improvement.py ContractTests.

**Acceptance.** Reject missing identities, cycles, cross-arm parents, invalid schemas and mutable hash mismatches; old absent data remains unknown.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_recursive_improvement.ContractTests
```

### R02 — Durable links, recovery and history projection
- id: R02
- title: Durable links, recovery and history projection
- status: pending
- model: strong
- depends: R01

**Brief.** Extend attempt_ledger, attempt_history and existing proposal storage only where needed for research references; build derived lineage through recursive_improvement. Add LedgerTests with crash, duplicate delivery, corrupt event and missing-artifact fixtures.

**Acceptance.** History rebuilds from owning records; duplicate events do not double-count; unknown dispatch is not rerun or refunded; unresolved evidence cannot pass a claim gate.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_recursive_improvement.LedgerTests
```

## Phase 2 — Protocol and evaluation integrity

### R03 — Frozen protocol and cross-generation budgets
- id: R03
- title: Frozen protocol and cross-generation budgets
- status: pending
- model: strong
- depends: R02

**Brief.** Extend existing admission/workflow_eval seams with immutable protocol identity and aggregate campaign accounting. Add ProtocolTests covering generation-level and campaign-level resource records, all three arms, interventions, model drift and predeclared analysis parameters.

**Acceptance.** No dispatch without protocol and admission; child runs cannot reset campaign caps; failed research work remains charged; mixed units and unknown costs are never summed into fictitious dollars.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_recursive_improvement.ProtocolTests
```

### R04 — Evaluation exposure and protected profile integration
- id: R04
- title: Evaluation exposure and protected profile integration
- status: pending
- model: strong
- depends: R03

**Brief.** Reuse V1 grouped partitions, exposure registry and execution profile. Add BoundaryTests for cross-arm leakage, related-defect overlap, reused audit feedback and attempted edits to evaluator, ledger or budget authority. Fake-runner tests exercise refusal, not real-profile certification.

**Acceptance.** Absent protection refuses live trials; exposed audit tasks retire; tampering invalidates evidence; real sentinel evidence is required before claiming a live boundary.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_recursive_improvement.BoundaryTests
```

## Phase 3 — Improver and experimental runner

### R05 — Versioned improver candidates and controlled succession
- id: R05
- title: Versioned improver candidates and controlled succession
- status: pending
- model: strong
- depends: R04

**Brief.** Implement bounded proposal generation orchestration using existing approved provider/admission seams, with deterministic fixtures offline. Candidate scope includes failure selection and experiment design, not evaluation or authority. Reuse V1 exact-content acceptance, pinned runs and rollback; add SuccessionTests.

**Acceptance.** Rejected candidates never become parents; B cannot edit its improver; C can only inherit accepted versions; no implicit global activation; resumed runs retain their versions and budgets.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_recursive_improvement.SuccessionTests
```

### R06 — Three-arm replicated experiment runner
- id: R06
- title: Three-arm replicated experiment runner
- status: pending
- model: strong
- depends: R05

**Brief.** Extend workflow_eval with campaign orchestration, independent replicates, counterbalanced scheduling, fixed-procedure and evolving-procedure arms. Add ExperimentTests using synthetic fixtures whose expected effects are known; record these as synthetic.

**Acceptance.** Arms share only initial conditions; gains do not leak across replicates; order and missing outcomes are recorded; stop/resume preserves assignment and cumulative spend.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_recursive_improvement.ExperimentTests
```

## Phase 4 — Evidence and handoff

### R07 — Independent analysis and attribution report
- id: R07
- title: Independent analysis and attribution report
- status: pending
- model: strong
- depends: R06

**Brief.** Implement derived campaign reports with predeclared primary endpoint, C-versus-B effect and uncertainty, practical margin, task-group dependence, regressions, transfer, interventions and total cost. Add AnalysisTests with no-effect, real-effect, confounded, censored and selective-reporting fixtures; implement controlled improver reversion comparisons.

**Acceptance.** A-only gains cannot pass RSI criteria; single lucky trajectories and changed models do not pass; insufficient power/coverage returns inconclusive; all failed and stopped trajectories appear.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_recursive_improvement.AnalysisTests
```

### R08 — Research handoff and empirical readiness gate
- id: R08
- title: Research handoff and empirical readiness gate
- status: pending
- model: strong
- depends: R07

**Brief.** Publish current capability matrix, campaign protocol template and operator runbook; integrate checks into existing release_gate without making research success a normal product requirement. Add ReadinessTests and document selected execution status, evidence locations and rollback. Prepare a live campaign only if prerequisites and explicit authorization are present; otherwise report the exact missing evidence.

**Acceptance.** Separate infrastructure complete from campaign authorized and bounded RSI supported; no synthetic test or approved proposal is reported as empirical RSI. No Jev or training dependency.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_recursive_improvement.ReadinessTests
```
