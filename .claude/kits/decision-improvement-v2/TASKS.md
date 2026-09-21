# TASKS — decision-improvement-v2 (deferred)

No task executes until explicit later human authorization covers Jev access, data, spending,
scope and activation. This is a handoff stop, not a mutable authorization token. `python3`
must resolve to 3.12+; do not install it. V1 admission, protected profile, grouped immutable
partitions, independent acceptance and exact approval gates remain mandatory.

## Phase 1 — Optional provider

### J01 — Document access and adapter
- id: J01
- title: Document access and adapter
- status: pending
- model: opus
- depends: (none)
**Brief.** After authorization, own `docs/JEV-ACCESS-CONTRACT.md`, optional `bin/jev_decision_provider.py`, and `tests/test_jev_provider.py:JevProviderContractTests`. Inspect current official API, limits, privacy, versioning and errors; record documented versus authorized observed behavior before mapping supported values into V1 contracts. Preserve Jev-free imports/startup.
The conformance record lists documented versus observed question kinds/cardinalities, request/response limits, response/model version, rate limits, retention/privacy, billing and error semantics. Use a documented stdlib HTTP interface or an optional isolated bridge; default imports cannot depend on an SDK. Unsupported types/cardinalities stay unsupported.

**Acceptance.** Official facts cited; probe separately authorized; malformed/privacy tests; unsupported rejects; connectivity promotes nothing.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_jev_provider.JevProviderContractTests
```

## Phase 2 — Comparative evaluation

### J02 — Fixed-policy comparison
- id: J02
- title: Fixed-policy comparison
- status: pending
- model: opus
- depends: J01
**Brief.** Own `bin/decision_eval.py`, workflow_eval provider-substitution seam and `tests/test_jev_evaluation.py:FixedPolicyProviderComparisonTests`. Compare Jev and rules/replay under frozen V1 policy, question, partition, acceptance and resource protocol. Separate fixed-policy provider substitution from a separately predeclared provider-specific tuning study. Include the optional current-model provider when available; explain its absence otherwise. Compare prediction targets/coverage/latency/usage/calibration and subgroup errors on frozen inputs; distinguish true billed units from estimated/proxy/unpriced usage, then compare protected whole-workflow quality; shadow agreement does not establish policy value. This is not the context-repair three-arm experiment, and tuning cannot reuse exposed audit outcomes as independent evidence.
**Acceptance.** Targets frozen; subgroup errors and true-billed/estimated/proxy/unpriced usage separately reported; confidence bases separate; untried outcomes not inferred; thin data insufficient; no live run without authorization.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_jev_evaluation.FixedPolicyProviderComparisonTests
```

## Phase 3 — Scoped adoption and release

### J03 — Scoped adoption
- id: J03
- title: Scoped adoption
- status: pending
- model: opus
- depends: J02
**Brief.** Own workflow_eval activation seam and `tests/test_jev_activation.py:JevScopedActivationTests`. Route Jev through D23 exact approval/canary/rollback gates while preserving rules/replay fallback, pins, eligibility, caps, assurance and run-pinned bundle versions.
Record provider response/model and policy versions on every adopted decision. Account for shared rate limits and total decision overhead; batch only semantically compatible questions within documented/measured limits. Circuit breaking, invalid outputs, version/calibration drift and exhausted retry budgets must use fresh gates and a validated fallback or stop. Disabling Jev requires no Jev contact.

**Acceptance.** D23 gates required; outage falls back; scope bounded; no default expansion; rollback retains evidence.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_jev_activation.JevScopedActivationTests
```

### J04 — Refresh release evidence
- id: J04
- title: Refresh release evidence
- status: pending
- model: opus
- depends: J03
**Brief.** Own `docs/JEV-RELEASE-EVIDENCE.md` and `tests/test_jev_release.py:JevReleaseEvidenceTests`. Reconcile official versus observed API, privacy, retention, version and resource facts before any release decision.
**Acceptance.** Unknowns explicit; evidence dated; capability separate from gain; no activation; no equivalence claim.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_jev_release.JevReleaseEvidenceTests
```
