# Optional V1 advice and later decision families

These are planned tasks, not implicit work after V1. Start only when the user selects this extension; materialize it as its own native kit using the same plan/guardrails and current pricing aliases. Cross-kit prerequisites appear in briefs, never in `depends:`. All tasks below are pending. They do not block deterministic rules/replay or the first context-repair trial. No live calls are part of offline implementation verification.

## Phase 1 — Optional current-model advice

### O01 — Admit every decision operation under existing authority
- id: O01
- title: Versioned inference-operation admission
- status: pending
- model: opus
- depends: (none)

**Brief.** Prerequisites: core decision contracts, provenance and legacy compatibility accepted. Extend `bin/kit_contract.py`, `bin/attempt_ledger.py`, `bin/attempt_history.py` and their tests with a separately named decision-operation scope and aggregate model-call accounting for provider attempts, retries and response repair. Keep historical task `max-dispatches` semantics unchanged. Rules/replay create no new external inference debit. Admission precedes every optional model call, and crash/unknown results preserve reservations and history. The task owns no new ledger or pricing data. Add `tests/test_decision_advice.py` with `OperationAdmissionTests`; work from the existing admission schema rather than introducing a second counter.

**Acceptance.** Exhausted decision or aggregate caps prevent calls; crash-after-dispatch does not refund unknown use; retries/repair are bounded; old kits preserve behavior; nullable usage is unknown.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_advice.OperationAdmissionTests test_attempt_ledger test_kit_contract
```

### O02 — Enforce tool-free structured shadow inference
- id: O02
- title: Optional structured-model provider
- status: pending
- model: opus
- depends: O01

**Brief.** Extend `bin/decision_provider.py`, the existing adapter capability seam and `tests/test_decision_advice.py` (`ShadowProviderTests`). Use only a currently documented, explicitly configured supported transport with verified tool-free mode. Read current official transport documentation during implementation; do not invent flags or treat a prompt restriction as enforcement. If no transport can enforce this, return unsupported while rules/replay continue. Validate only correlated terminal output using the core contract; reject tool-origin fake results, wrong final events, truncation, stale state and invalid JSON. Shadow records advice without changing route, context, acceptance or permissions. Use bounded approved state and existing redaction/privacy rules; one measured bounded batch is preferable to speculative fan-out. Provider/model observations remain unknown if unattested. Prepare live probes separately, with approved data and resource ceilings.

**Acceptance.** Fake-runner output/injection/outage/privacy/cap tests pass; unsupported transport calls nothing; malformed output abstains; shadow output cannot affect baseline behavior; no provider credentials or real calls in tests.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_advice.ShadowProviderTests test_decision_provider test_decision_legacy
```

## Phase 2 — Calibration and extension acceptance

### O03 — Fit calibration only for defensible targets
- id: O03
- title: Versioned held-out calibration
- status: pending
- model: opus
- depends: O02

**Brief.** Extend `bin/decision_eval.py` and `tests/test_decision_advice.py` (`CalibrationFitTests`) using the core target/label and partition contracts. Implement a simple documented calibration method only for targets with defensible labels and sufficient approved data; use known synthetic labels to test mechanics. The artifact binds provider/model/question/target/domain/dataset/method/sample coverage and versions. Fit only on the designated calibration partition, validate on promotion/audit partitions and invalidate on drift. Reuse the core decision metrics contract: define missing/censored/disputed label handling and report classification quality, Brier/log loss when valid, reliability bins and false-action risk at proposed thresholds, with uncertainty and raw-versus-calibrated comparisons. Mark inappropriate metrics not-applicable. No private trace collection or production fitting is implied. Keep vendor confidence, raw probability, rubric score and calibrated probability distinct. Do not infer counterfactual success from logs of only the selected model.

**Acceptance.** Partition leakage and stale target/provider/version reuse refuse; metrics include sample counts/coverage; thin data returns insufficient-evidence; calibration does not itself promote a policy.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_advice.CalibrationFitTests test_decision_eval
```

### O04 — Publish optional advice capability without changing defaults
- id: O04
- title: Advice conformance and operator handoff
- status: pending
- model: sonnet
- depends: O02

**Brief.** Extend release-gate mapping and source docs with the supported/offline/unverified advice surfaces, per harness/client/version/OS. Consume an O03 artifact only when available; otherwise show calibration as unavailable or insufficient-evidence without blocking honest shadow support. Update `tests/test_decision_advice.py` (`AdviceReleaseTests`) to prove startup and recovery with optional provider/calibrator absent, disabled or incompatible. Preserve baseline defaults and no-Jev operation. Record what was actually tested and prepare any separately authorized live shadow evaluation using the core workflow protocol. Rebuild generated documentation via its owning tools. Do not declare transport verified from stub conformance or enable a default.

**Acceptance.** Absent provider is harmless; unsupported matrix is explicit; docs and mappings agree; runtime baseline unchanged; checks never contact a real model.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_advice.AdviceReleaseTests test_release_gate
```

## Decision-family backlog after evidence (R08)

Create a separate bounded implementation kit for each selected family after the first trial has evidence. These are not prerequisites for V1:

| Family | Existing owner | Required counterexample and experiment |
| --- | --- | --- |
| Workflow/model/effort | routing_policy and per-harness policy data | Explicit user pin, unavailable model/effort and privacy exclusion stay hard filters; compare one changed choice with fixed assurance; no unsupported success probabilities |
| Optional roles | kit_contract role roster, routing_scorecard | Required roles never removed; unsupported client refuses before spending; measure confirmed/marginal findings and full cost, recognizing order dependence |
| Context strategy | graph_ground/graph_brief | Irrelevant hub, stale/dirty/untracked context and absent graph; compare bounded relevant retrieval with the simpler search baseline, not just context byte counts |
| Skill/lesson applicability | existing skill bundles and lessons_store | Non-trigger, contradiction, expiry, wrong project and no evidence; prove inappropriate skills remain unloaded and a one-off failure never becomes a global rule |

Each resulting kit needs a trigger, bounded input, fallback, immutable candidate, independent evaluation, rollback, offline verify and human promotion scope. Reuse the core protocol; do not implement all families merely because the interface permits them.

## Meta-improvement research (M01)

Defer until the fixed improvement procedure repeatedly produces validated transferable gains. Version the procedure separately and compare original/candidate from identical initial policy/evidence under matched total budgets, including failed proposals and evaluation. Evaluate multiple trajectories on unseen tasks for successor quality, retained capability, regressions, transfer, operator effort and resources per validated gain. Keep final audit and acceptance outside candidate control. Changing a provider or accepting one proposal is not evidence of effective recursive improvement; this research does not depend on Jev.

M01 is now specified in `tasks/kits/recursive-improvement/PLAN.md` and `TASKS.md`: eight pending tasks across four phases. Those records/backend tasks may be prepared offline after V1 contracts stabilize; the live research prerequisites above remain mandatory. This is a separately selected research extension, not an automatic continuation of V1 or Jev V2.
