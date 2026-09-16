# Applying the protocol to Polytropos as a whole

Assessment snapshot: main `aab755378975e9191db6ced16ee07a27a414af21`. Source inspection supports the claims below. No private run traces or paid experiments were used to establish frequency or benefit; there is no measured improvement claim. Reconcile newer work before executing the resulting tasks.

## Authority and evidence map

| Surface | Evidence at this revision | Assessment |
| --- | --- | --- |
| Durable runtime | attempt_ledger.AttemptLedger/record_started/record_finished/reconcile_open; kit_contract.start_task_lifecycle/reconcile_task/finish_task_projection | Implemented lifecycle foundation; preserve unknown outcomes and no replay |
| Evidence joins | attempt_history.RECORD_FIELDS/ledger_records | Existing uncollapsed joins; policy/decision/admission/acceptance provenance needs extension |
| Routing and assurance | routing_policy; kit_contract.resolve_roster/roster_for_run; harness_adapter | Existing deterministic choices and capability filters; advisory layer must be additive |
| Claude, Codex, Copilot, Cursor | Four *_execute drivers, adapter modules, primitives/harness-capabilities.json | All four require separate baseline conformance; installed support varies, no inference from another harness |
| Planning, skills and context | skills/architect, skills/execute; graph_ground/graph_brief; lessons_store | Existing scoped planning/navigation/learning mechanisms; assess applicability before adding inference |
| Workflow evaluation | workflow_eval.Evaluation/build_card; repo_bench mining/oracles | Reuse complete workflow evaluation and reconstructed grading substrate |
| Policy promotion | workflow_eval.build_proposal/review_proposal/apply_proposal/rollback_policy | Present but narrower than proposed immutable approvals/canaries; applied file is deliberately pull-only |
| Isolation | SECURITY.md "What is NOT a boundary"; exec_policy/proc_runner | Verification confined on supported backend; candidates/judges/controller state lack required protected profile |
| Packaging/release | release_gate, runtime_data.STORES, generated doc builders | Reuse existing evidence matrix, private-store exclusion and generator ownership |

## Prioritized opportunities

Priority expresses prerequisite order and learning value, not a fabricated benefit score.

### F1 — Make policy attribution trustworthy before learning from outcomes

Observed: current attempt/history schemas do not identify the new decision bundle, acceptance version, admission and component provenance. Hypothesis: adding these identities will make replay/applicability and comparisons auditable without inventing counterfactuals. The deterministic test is a complete joined record across failure/resume/retry with historical missing fields still unknown. This is an evidence prerequisite, not a measured model-quality improvement. Counterevidence: if equivalent fields land before execution, reuse them and reduce the task.

### F2 — Keep protected experiments unavailable until their authority is protected

Observed/documented: SECURITY.md explicitly disclaims candidate/judge confinement and tamper-proof execution state. Existing oracle reconstruction addresses grading contamination but not host reads or controller-state access. The intervention is a named enforcement profile and fail-closed availability check, followed by executable synthetic sentinels. A normal allowed build must still pass. A unsupported host stays offline/advisory; no credential or account migration is implied. This is a safety prerequisite, not an instruction to add probabilistic security decisions.

### F3 — Test missing contract context as a recovery hypothesis

Inferred, not established recurrence: cross-module tasks may fail because required interfaces/consumers/tests were omitted. Source architecture exposes places to collect bounded context, but this assessment has no labeled failure cohort proving frequency. First collect approved evidence and predeclare a cohort; then compare actual baseline, ordinary same-model retry and targeted context repair. A and B may coincide. Negative cases include local edits, irrelevant hubs, environment/auth failures, absent context and exhausted budget. Reject if context adds cost without useful accepted recovery or harms prior successes. This is the first policy experiment, not a preselected winner.

### F4 — Strengthen exact approval without silently activating existing preferences

Observed: workflow_eval's current proposal/review/apply/rollback is narrower than the roadmap; drivers do not read applied preferences automatically. Add immutable data-only bundles, exact evidence binding, scoped opt-in pointer, run pinning, bounded canary and compatible fallback within the existing persistence owner. Counterevidence: retaining pull-only behavior may be sufficient for manual use; keep it usable. Never label a file replacement as trusted promotion without F2's authority boundary.

### F5 — Make the assessment method reusable and test its no-fit behavior

Observed: existing architecture/route/graph/lessons skills provide useful components, but no combined repository-wide assessment skill implements this protocol. Package the staged assess-improvement skill and test it on synthetic repositories with a recurring gap, a mature no-change case, conflicting docs, absent evidence, and a non-agent project. Include a case where only one of four harnesses supports a capability. Success means bounded, evidence-linked reports and useful briefs; a content check alone cannot prove better agent behavior. The whole-Polytropos pilot must identify unchanged strengths as well as candidates.

### F6 — Close capability and measurement gaps without duplicating concurrent work

Documented on main: installed-client verification is incomplete and resource/model identity coverage has gaps. Later work on the other local branch records Claude/Cursor and further in-progress checks. D01 must reconcile those changes before scheduling fixes; no previously observed support is downgraded. Use existing release_gate and attempt_history owners to disclose unknowns. Adding an optional provider cannot repair missing runtime measurements automatically.

**Plan revision, D01, 2026-09-16 — reconciled.** That branch's work is merged and reachable from HEAD `e6cf4bd6c86daac53ac99d4d484c4bb802b84bb5`. Installed-client verification now exists for all four clients, dated 2026-09-16 with client versions, and Cursor moved from every row unknown to six rows verified; that evidence stands and is never rolled back to this snapshot. The measurement gap this opportunity names is still open and now has a precise shape: `duration_s` is null on every live attempt on every harness, because the drivers' runners drop `proc_runner`'s timing and `cursor_adapter.parse_output` never reads the `duration_ms` and `usage` the Cursor CLI actually reports. No duration fix has landed anywhere, so D03 should tell D05 there is nothing to deduplicate. Per-step classifications and evidence paths are in `docs/DECISION-IMPROVEMENT-RECONCILIATION.md` and its JSON twin.

## Additional validation findings

The planning branch’s full-suite validation exposed `test_lessons_promote.NoScaffoldingWritesTests.test_real_run_touches_only_gitignored_path`, which assumes an existing legacy journal directory while a fresh checkout correctly resolves an external namespace. The test passed with an empty legacy `journal/promotions/` fixture. It also exposed a race in `test_kit_scheduler.ManifestTests.test_a_refused_manifest_stops_integration_and_keeps_the_copies`: snapshot_tree can stat an atomic TASKS temporary file after another thread removes it. That case passed alone; the underlying race remains a baseline finding, not a planning-artifact regression or a fixed defect. Record these in D01 and scope any runtime repairs separately.

**Plan revision, D01, 2026-09-16 — recorded, not repaired.** Both are in `docs/DECISION-IMPROVEMENT-RECONCILIATION.md` as `BL1` and `BL2`, with the exact mechanism of each. `BL1` reproduces on this HEAD and is the full suite's single failure: `tests/test_lessons_promote.py:551` builds its expected path from the repository root while `bin/lessons_promote.py:93` resolves it through `bin/runtime_data.py`, which returns the in-tree location only when it exists and has content — so the product is obeying the outside-the-tree store invariant and the test is asserting a checkout shape. The earlier empty-fixture accommodation was not repeated. `BL2` did not reproduce here, which proves nothing about the race. Neither was touched; D01 changed no test.

## Where the methodology should not add machinery

Keep deterministic admission, readiness, path validation, process bounds, required assurance and release conditions deterministic. Do not add model calls to straightforward tasks or stable wrappers with no recurring pain signal. Repository graphs remain optional. No need for a new server, graph database, generic rule language, always-loaded policy manual or cross-harness price table. Meta-improvement is deferred until the fixed procedure yields independently validated successors.

## Initial recommendation

Prepare the typed/evidence foundation and the assessment skill first; retain legacy policy throughout. Complete protected-profile verification before any trusted live comparison. Treat context repair as a falsifiable hypothesis; approve a scoped policy only if the predeclared evaluation supports it. All four harnesses participate in compatibility and assessment, while the first live experiment can use one verified configuration. Missing evidence remains an explicit outcome.
