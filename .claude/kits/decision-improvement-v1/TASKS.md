# TASKS — decision-improvement-v1

Planning-only kit against `aab755378975e9191db6ced16ee07a27a414af21`. Steps 16–26 already
exist: reconcile and preserve them. All work is stdlib-only with synthetic temp stores; no live
CLI/model, relaxed cap, arbitrary proposal code, second ledger, or authored NOTES.md.

Global prerequisite: before dispatch, `python3` must resolve to Python 3.12 or later; the
repository uses 3.12 syntax and `tomllib`. Do not install or mutate an interpreter in this kit.

## Phase 1 — Baseline

### D01 — Reconcile and ADR
- id: D01
- title: Reconcile and ADR
- status: done
- model: opus
- depends: (none)
**Brief.** Own `docs/DECISION-IMPROVEMENT-RECONCILIATION.md` and `docs/adr/decision-improvement-v1.md`. Compare exact HEAD, HANDOFF, SECURITY, roadmap and kit contract; classify steps 16–26, preserve legacy, distinguish advisory prediction from authority, and state Jev-free/human-gated/data-only design.

Also emit `docs/DECISION-IMPROVEMENT-RECONCILIATION.json` with baseline_revision, observed_revision and a prerequisites map keyed by strings 16 through 26; each entry has state (implemented/partial/unverified/pending), evidence paths and remaining_delta. Use this kit’s source reconciliation if the historical roadmap attachment is absent. Inspect later commits before assigning deltas; existing live evidence is never downgraded. Update only genuinely stale briefs through a documented plan revision, not product code.

**Acceptance.** Docs name HEAD; all steps classified; gaps cite paths; no code changes; completed work not rescheduled.
**Verify.**
```bash
python3 - <<'VERIFY'
from pathlib import Path
import json
r=json.loads(Path('docs/DECISION-IMPROVEMENT-RECONCILIATION.json').read_text())
assert r['baseline_revision']=='aab755378975e9191db6ced16ee07a27a414af21'
assert len(r['observed_revision'])==40
assert set(r['prerequisites'])==set(map(str,range(16,27)))
for row in r['prerequisites'].values():
    assert row['state'] in {'implemented','partial','unverified','pending'}
    assert row['evidence'] and 'remaining_delta' in row
for file in ['docs/DECISION-IMPROVEMENT-RECONCILIATION.md','docs/adr/decision-improvement-v1.md']:
    assert len(Path(file).read_text().split()) >= 100
VERIFY
```

### D02 — Legacy goldens
- id: D02
- title: Legacy goldens
- status: done
- model: sonnet
- depends: D01
**Brief.** Own `tests/test_decision_legacy.py:LegacyDecisionGoldenTests`; fixture `bin/kit_contract.py`, drivers and `bin/workflow_eval.py`. Pin parse/readiness/admission/recovery behavior and absent active pointer as legacy default; assert workflow_eval remains pull-only.

Exercise each native driver with injected runners and temporary fixture homes. Capture explicitly selected tasks with unmet dependencies, exhausted budgets, failed dispatch despite passing tests, and the actual retry/escalation sequence. Golden observations describe existing behavior, not desired behavior; freeze them before extraction so any drift has a reviewable cause.

**Acceptance.** Temp fixtures only; denied/stale cases covered; no driver policy read; no home/CLI; existing outputs unchanged.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_legacy.LegacyDecisionGoldenTests
```

### D03 — Authority inventory
- id: D03
- title: Authority inventory
- status: done
- model: opus
- depends: D01
**Brief.** Own `docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md`. Map attempt/admission/acceptance/policy/evaluation writers, missing full versions and acceptance/policy/decision/admission refs, duration coverage, unknown migration and workflow_eval pull-only limitation.

Name `attempt_ledger`, `attempt_history`, `kit_contract`, `workflow_eval`, `repo_bench`, `runtime_data` and the four native drivers precisely. Define which event owns each new reference, its correlation and schema version, the historical missing-field migration, and the report projection. Identify any duration fixes already landed elsewhere so D05 does not duplicate them.

**Acceptance.** One owner per concern; missing fields named; unknown migration explicit; hashes not security; no implementation claim.
**Verify.**
```bash
python3 -c "from pathlib import Path; t=Path('docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md').read_text(); assert all(x in t for x in ('workflow_eval','pull-only','duration','unknown'))"
```

### D04 — Attempt provenance
- id: D04
- title: Attempt provenance
- status: done
- model: opus
- depends: D02, D03
**Brief.** Own D03’s existing attempt authority and `tests/test_decision_provenance.py:AttemptProvenanceTests`. Persist correlated acceptance/policy/decision/admission/full-version refs; load historical omissions as unknown and preserve consult/review overhead and max-dispatches meaning.

Extend `bin/attempt_ledger.py`, `bin/attempt_history.py`, `bin/kit_contract.py` and only necessary driver call sites. These are additive versioned identities, not a second decision schema or store. Test crashes before dispatch, after dispatch, after verify/before projection; duplicate completion, stale claims, budget-exhausted resume and failed-dispatch/passing-verify. No exactly-once claim, blind replay or unknown-use refund.

**Acceptance.** Old records load; refs round-trip; crash/resume retains refs; unknown remains unknown; no second writer.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_provenance.AttemptProvenanceTests
```

## Phase 2 — Protected evaluation

### D05 — Duration coverage
- id: D05
- title: Duration coverage
- status: done
- model: sonnet
- depends: D04
**Brief.** Own attempt projection and `tests/test_decision_duration.py:DurationCoverageTests`. Record wall/decision duration basis, timeout, cancellation, censoring and external unknown without inferring free retries or refunds.

Change only `bin/proc_runner.py` result plumbing, `bin/attempt_ledger.py`/`bin/attempt_history.py`, and affected adapter/driver projections as needed. Preserve requested, dispatched and independently observed identities separately. Include review/consult overhead and all failed attempts in complete workflow totals. Distinguish measured duration from estimated/missing values and never sum incompatible resource bases.

**Acceptance.** Outcome distinctions persist; unknown retained; report separates latency/wall; temp stores; resume is compatible.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_duration.DurationCoverageTests
```

### D06 — Immutable manifests
- id: D06
- title: Immutable manifests
- status: done
- model: opus
- depends: D03
**Brief.** Extend the existing manifest/storage seam in `bin/workflow_eval.py` and `tests/test_decision_evaluation_manifest.py:EvaluationManifestTests`. Create content-addressed grouped development/calibration/promotion/audit partitions with exposure accounting and reference-leak/staleness rejection.

The owning workflow evaluator persists manifests; no new parallel writer. Include code/task/acceptance/artifact identities, group related issue and mutation variants into one partition, keep calibration fitting separate from promotion/audit, and record exposure/retirement. Test future-fix-message/reference-patch leakage and attempted post-result cohort selection. The controller owns the immutable labels/rules; a hash alone is not enforcement.

**Acceptance.** Hashes persist; variants group; stale fails; exposure records; synthetic data only.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_evaluation_manifest.EvaluationManifestTests
```

### D07 — Protected profile sentinels
- id: D07
- title: Protected profile sentinels
- status: done
- model: opus
- depends: D04, D06
**Brief.** Own `bin/exec_policy.py` and `tests/test_decision_experiment_boundary.py:ProtectedProfileSentinelTests`. Verify enforceable candidate/setup/test/judge/controller separation; worktrees are not isolation. Unsupported host/profile returns typed unavailable.

Extend shared enforcement plumbing rather than invent a dispatcher. Sentinels must exercise real OS boundaries using synthetic credentials/data and no model calls; include judge writes to accepted state, controller code/hash changes and malicious setup/tests. Skipped or unavailable sentinels cannot certify a profile. Offline implementation may complete with no supported live profile if refusal paths work and release claims stay unavailable. Host/account/container installation is a separate authorized action.

**Acceptance.** Hidden read denied; controller write denied; test escape denied; allowed fixture works; unsupported explicit.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_experiment_boundary.ProtectedProfileSentinelTests
```

### D08 — Offline-only fence
- id: D08
- title: Offline-only fence
- status: done
- model: sonnet
- depends: D07
**Brief.** Own profile/workflow gate and `tests/test_decision_experiment_boundary.py:UnavailableProfileTests`. Permit offline synthetic analysis and manual drafts when D07 is unavailable, but refuse protected live trials/autopromotion and record skipped sentinels.

Own `bin/workflow_eval.py` pre-dispatch gates and the D07 profile API. An offline/manual result is not a fallback to trusted-host. Prove no provider runner is reached after any missing enforcement requirement. Preserve a usable manual report/proposal path with temporary synthetic inputs, and carry profile/refusal evidence into the existing result owner. Later D23 must enforce the same distinction at activation.

**Acceptance.** No dispatch; unavailable visible; no-spend offline works; no live-ready claim; gate remains independent.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_experiment_boundary.UnavailableProfileTests
```

## Phase 3 — Contracts and policy

### D09 — Strict contract parser
- id: D09
- title: Strict contract parser
- status: done
- model: opus
- depends: D04, D06
**Brief.** Own `bin/decision_contract.py` and `tests/test_decision_contract.py:DecisionRequestValidationTests`. Implement QuestionSpec, DecisionRequest/Result/Record with duplicate-key-safe parsing and correlation/snapshot/schema validation; reject executable fields.

Use the object fields pinned in the shared PLAN, bounded payloads, explicit status enums and canonical versions. Unknown action IDs and stale candidate/state/question identities must reject. Question IDs do not substitute for complete question wording/rubrics. A schema-valid answer proves representation only; DecisionRecord construction stays coordinator-owned. Test wrong terminal/request correlation, unknown keys and required-answer omissions.

**Acceptance.** Extra/duplicate/wrong/missing reject; abstain parses; no authority field; stdlib only; synthetic fixtures.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_contract.DecisionRequestValidationTests
```

### D10 — Value validation
- id: D10
- title: Value validation
- status: done
- model: sonnet
- depends: D09
**Brief.** Own `bin/decision_contract.py` and `DecisionValueValidationTests`. Validate category coverage/sums, ordinal rubrics, multi-label hypotheses and raw versus calibrated nullable values; never normalize malformed provider output.

Use separate boolean questions for coexisting causes; do not infer independence or multiply their probabilities. Define a documented numerical sum tolerance and reject out-of-range/infinite values, nonnumeric distribution entries and ambiguous ordinal levels. Keep vendor confidence separate from raw and calibrated probability; heuristic rules can leave all numeric confidence absent. Include boundary fixtures, not merely happy-path serialization.

**Acceptance.** NaN/bool reject; incomplete maps reject; ambiguous rubric rejects; bases remain distinct; stable reason codes.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_contract.DecisionValueValidationTests
```

### D11 — Bundles and proposals
- id: D11
- title: Bundles and proposals
- status: done
- model: opus
- depends: D09
**Brief.** Own record definitions in `bin/decision_contract.py`, bundle identity helpers in `bin/decision_policy.py`, and `tests/test_decision_policy_bundle.py:PolicyBundleContractTests`. Define immutable bundle/proposal hashes, parent/scope/versions/fallback/evidence and data-only diffs; reject code, shell, imports, permissions, acceptance and hidden-eval changes.

Keep runtime code/controller permissions outside the proposal allowlist. Hash canonical content and bind parent, affected scope, component/provider/calibration requirements and rollback provenance. A legacy preference file does not silently become an active bundle. Record types belong to decision_contract; selection/resolution belongs to decision_policy; workflow_eval remains the persistence owner.

**Acceptance.** Stable hashes; fallback required; banned fields reject; historical shape loads; bundle grants no authority.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_policy_bundle.PolicyBundleContractTests
```

### D12 — Rules and replay
- id: D12
- title: Rules and replay
- status: done
- model: sonnet
- depends: D10, D11
**Brief.** Own `bin/decision_provider.py` and `tests/test_decision_provider.py:RulesReplayProviderTests`. Implement deterministic rules/replay keyed by project/provider/task/snapshot/candidates/questions/policy/calibration; semantic uncertainty abstains.

Expose a single bounded request-to-result interface with rules and replay implementations and test both through the D09 validator. Include task acceptance version, complete state and provider/model identity in replay keys. A cache miss abstains, and a replayed record is not a fresh vendor observation. Historical cost remains on its original record; zero new calls must not rewrite old resource evidence.

**Acceptance.** Replay makes no call; cross-project misses; invalid rejects; rules abstain; temp store only.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_provider.RulesReplayProviderTests
```

### D13 — Legacy policy selection
- id: D13
- title: Legacy policy selection
- status: done
- model: opus
- depends: D02, D12
**Brief.** Own `bin/decision_policy.py`, driver seam and `tests/test_decision_policy.py:LegacySelectionTests`. Implement pure selection/reason codes/rejections with legacy default and fresh capability/admission recheck; no active pointer consumption before D23.

Wrap `bin/routing_policy.py` and native driver selection seams as pure select_action(state, result, bundle); return baseline/recommendation/selection reasons without dispatch. Coordinator calls alone perform fresh capability/privacy/eligibility/budget checks. Explicit user pins and reserved-orchestrator defaults survive. Record legacy/shadow mode and rejected alternatives; a high-confidence result never overrides a hard denial.

**Acceptance.** D02 goldens hold; stale rejects; confidence cannot bypass denial; disabled restores; no network.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_policy.LegacySelectionTests test_decision_legacy.LegacyDecisionGoldenTests
```

## Phase 4 — Recovery evidence

### D14 — Read-only joins
- id: D14
- title: Read-only joins
- status: done
- model: opus
- depends: D05, D06, D10
**Brief.** Own `bin/decision_eval.py` and `tests/test_decision_eval.py:PredictionTimeJoinTests`. Join authoritative events/workflow_eval references available at prediction time; preserve target, label provenance, disagreement/censoring and decision basis.

Read existing attempt_history/workflow_eval projections, preserving coverage and unresolved joins rather than dropping bad rows. Define the prediction target and label provenance for every question, including missing/disputed labels. Deterministic infrastructure events remain facts, and a successful recovery does not prove the diagnosis caused the failure. Evaluation must not mutate attempt or benchmark records.

**Acceptance.** Future excluded; labels visible; censoring visible; no untried-action claim; input read-only.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_eval.PredictionTimeJoinTests
```

### D15 — Calibration reports
- id: D15
- title: Calibration reports
- status: done
- model: sonnet
- depends: D14
**Brief.** Own calibration artifact/report in `bin/decision_eval.py` and `CalibrationReportingTests`. Report coverage/abstention/valid metrics/bins; pin fit target/version/partition and preserve raw versus calibrated interpretation.

Report classification quality, Brier/log loss only for valid probabilistic targets, reliability bins/sample counts, false-action risk at candidate thresholds and uncertainty. Unsupported metrics are not-applicable; rule labels are not numeric probabilities. This task reports/imports versioned calibration artifacts and synthetic metric fixtures; fitting is optional O03, not a prerequisite for core recovery.

**Acceptance.** Sparse says insufficient; invalid metrics refuse; artifact pins inputs; audit separate; no private default fitting.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_eval.CalibrationReportingTests
```

### D16 — Context candidates
- id: D16
- title: Context candidates
- status: done
- model: opus
- depends: D13
**Brief.** Own the existing `bin/graph_ground.py`/`bin/graph_brief.py` graph/search seam and `tests/test_decision_context_repair.py:ContextCandidateTests`. Create bounded versioned manifests of interfaces/consumers/config/tests with provenance/privacy/dirty checks and graph-to-search fallback.

Include direct consumers, omitted interfaces, configuration and contract tests only under a bounded retrieval policy and provenance manifest. Graph freshness must include dirty/untracked context, with search fallback when unavailable. A graph edge is navigation evidence, never dependency or parallel-write authority. Test irrelevant hubs, privacy-ineligible files, no relevant context and stable output for identical artifacts.

**Acceptance.** Deterministic artifact; fallback works; privacy withheld; hubs excluded; no dispatch.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_context_repair.ContextCandidateTests
```

### D17 — Context-repair policy
- id: D17
- title: Context-repair policy
- status: done
- model: opus
- depends: D07, D16
**Brief.** Own policy/context seam and `ContextRepairPolicyTests`. Add off-by-default one retry after genuine implementation failure, excluding environment/auth/permission/model failures; preserve model, assurance and acceptance then return legacy path.

Extend `bin/decision_policy.py` and the existing driver recovery seam using authoritative failure events. One approved context repair is a separately identified admitted operation within existing ceilings, never an extra unbounded retry. Test negative local-task trigger, duplicate repair, no relevant context, stale state and insufficient budget. Preserve the original failed evidence in the retry input and return to the frozen remaining recovery ladder.

**Acceptance.** Duplicate/no-context/stale/budget paths safe; evidence retained; no default; no live trial; current cap enforced.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_context_repair.ContextRepairPolicyTests
```

### D18 — Three-arm protocol
- id: D18
- title: Three-arm protocol
- status: done
- model: opus
- depends: D08, D14, D17
**Brief.** Own `bin/workflow_eval.py` seam and `tests/test_decision_trial_protocol.py:ThreeArmProtocolTests`. Represent actual baseline, same-model retry control and context repair with pinned checkpoint/acceptance/model/effort/diagnostics/ceiling and recovery/whole-task accounting.

Use `repo_bench` extraction/oracles and workflow_eval as the only envelope writer. Frozen grouped checkpoints compare conditional recovery; prepare a prospective full-task study before general rollout. Include initial-attempt cost even when a checkpoint is reused analytically and preserve failures in cohort totals. No fixed sample count or universal success threshold is invented. The generated experiment specification is not a completed run.

**Acceptance.** Synthetic dispatches none; A=B collapse; inputs pinned; existing owner writes; D07 required live.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_trial_protocol.ThreeArmProtocolTests
```

### D19 — Outcomes and stopping
- id: D19
- title: Outcomes and stopping
- status: done
- model: sonnet
- depends: D15, D18
**Brief.** Own `bin/decision_eval.py` report and `RecoveryReportTests`. Report quality/regression/resources/time/operator/coverage/slices/censoring with complete predeclared endpoint/margins/caps/stops, never universal thresholds.

Pin independent label source, observation window, practical gain, tolerated regression, interim-look policy and stopping rules before any live evaluation. Missing operator parameters mean plan-incomplete and block promotion, not successful defaults. Count every tried/rejected candidate and exposure. Report paired effects and uncertainty, prospective versus checkpoint claims, and total resources divided by accepted count only when the count is nonzero.

**Acceptance.** Zero ratio undefined; bases separate; synthetic labeled; censoring visible; stop fields required.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_trial_protocol.RecoveryReportTests
```

## Phase 5 — Promotion

### D20 — Existing owner
- id: D20
- title: Existing owner
- status: done
- model: opus
- depends: D11, D18
**Brief.** Own workflow_eval proposal/review/apply/rollback and `tests/test_decision_workbench.py:WorkflowEvalOwnershipTests`. Extend its records with bundle/manifest refs; do not create improvement-loop writer and retain pull-only behavior until D23.

Extend `bin/workflow_eval.py` build_proposal/review_proposal/apply_proposal/rollback_policy with versioned migration while old preference files remain pull-only. Route bundle/manifest validation through the shared contracts. Legacy review by a name is not proof of controller-authenticated approval; D22/D23 strengthen it. Rejected candidates and old policy versions remain inspectable.

**Acceptance.** Existing behavior compatible; one writer; rejections retained; no auto consume; temp prefs.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_workbench.WorkflowEvalOwnershipTests
```

### D21 — Bounded drafts
- id: D21
- title: Bounded drafts
- status: done
- model: opus
- depends: D07, D20
**Brief.** Own workflow_eval validation and `BoundedProposalTests`. Support manual/deterministic hypothesis/counterexample/data-only/falsification/rollback drafts; optional proposer separately budgeted and audit-blind.

Add `bin/improvement_loop.py` as a bounded orchestrator calling workflow_eval, not a persistence owner. It reads approved evidence, emits a precise hypothesis and allowlisted diff, and can prepare evaluation through the existing seam. Keep manual reports and small deterministic search usable without inference. Cap candidate count and total proposal effort; no direct live policy, pricing, skill, lesson or benchmark-record writes. Proposer code and final audit are outside candidate authority.

**Acceptance.** Code/assurance/hidden/duplicate/budget reject; no-candidate valid; no live inference; one owner; evidence retained.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_workbench.BoundedProposalTests
```

### D22 — Exact approval
- id: D22
- title: Exact approval
- status: done
- model: opus
- depends: D21
**Brief.** Own workflow_eval lifecycle and `tests/test_decision_approval.py:ExactApprovalTests`. Bind reviewer/scope/exact candidate hash/immutable evaluation hash across draft/offline-valid/evaluated/approved/rejected/insufficient-evidence states; mutations invalidate approval.

Use the canonical lifecycle names draft, offline-valid, evaluated, approved, rejected and insufficient-evidence. Bind the approval to exact candidate/evaluation/partition/source hashes plus approving authority and scope. Partial evaluation, unverified profile, stale content or proposer self-approval cannot establish promotion eligibility. Protect authority at the execution boundary; a JSON actor string or content hash is not authentication.

**Acceptance.** Stale/partial/self/scope reject; rejections retained; hashes not isolation; temp prefs; no activation.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_approval.ExactApprovalTests
```

### D23 — Protected activation
- id: D23
- title: Protected activation
- status: pending
- model: opus
- depends: D07, D13, D19, D22
**Brief.** Own workflow_eval pointer/read seam and `tests/test_decision_activation.py:ProtectedActivationGateTests`. Canary/active machine-refuses unless named D07 profile, current grouped/exposure manifest, D19 endpoint/margins/caps/stops, and D22 exact approval all pass. Otherwise runtime stays legacy or shadow; manual proposal drafting remains available.

Implement the transition code in `bin/workflow_eval.py`, bundle resolution in `bin/decision_policy.py`, and the existing driver start seam through `bin/kit_contract.py`. Add canary/active/retired/rolled-back states, atomic compare-and-swap pointer semantics, eligibility limits and monitoring trigger inputs. Old preferences still do nothing automatically. Rollback selects an approved compatible fallback for future runs without any provider contact; in-flight runs remain pinned or cancel/reconcile safely. Synthetic success fixtures never certify live deployment.

**Acceptance.** Each missing gate refuses; absent pointer is legacy; concurrent update safe; run pins; rollback preserves evidence/workspaces.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_activation.ProtectedActivationGateTests
```

### D24 — Policy evidence report
- id: D24
- title: Policy evidence report
- status: pending
- model: sonnet
- depends: D19, D23
**Brief.** Own workflow_eval projection and `PolicyEvidenceReportTests`. Report lineage/scope/interventions/resource bases/invalid-abstain/drift/delayed-censored quality; never call mechanics performance.

Extend existing workflow_eval and `bin/routing_scorecard.py` projections without creating a results store. Include approval/evaluation/profile links, delayed escaped-defect window and resource bases at their proper scope. Missing/unobserved usage or provider/model version remains unknown. Monitoring can propose rollback or flag drift under an approved procedure but cannot rewrite controller conditions or grant approval.

**Acceptance.** Scope visible; unknown visible; bases distinct; lineage complete; no gain claim.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_activation.PolicyEvidenceReportTests
```

## Phase 6 — Assessment

### D25 — Harness assessment skill
- id: D25
- title: Harness assessment skill
- status: pending
- model: opus
- depends: D01
**Brief.** Own staged prototype in `skills/`, `.claude-plugin/`, `copilot/aesop.toml`, `copilot/.github/skills/`, `codex/skills/`, `.codex-plugin/plugin.json`, `cursor/skills/`, `bin/cursor_adapter.py` BUNDLE/MANIFEST_REL, `bin/harness_select.py`, docs fragments/generators; never edit docs-site.

Start from `tasks/kits/decision-improvement/skills/assess-improvement/`, retaining its linked template and no-fit behavior. Use exact skill name assess-improvement in native paths; preserve root plugin discovery and actual installer ownership. Add `tests/test_assessment_skill.py:SkillPackagingTests` to prove all intended entrypoints/references/package ownership and no-clobber installation into temporary homes. Modify manifest/generator code only where required by actual discovery, not every named file automatically. Do not install the plugin or alter global instructions.

**Acceptance.** Rosters/manifests agree; Cursor install includes skill; Codex plugin valid; docs regenerated; no borrowed CLI commands.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_assessment_skill.SkillPackagingTests test_codex_bundle test_copilot_bundle test_cursor_adapter test_harness_select
```

### D26 — Assessment fixtures
- id: D26
- title: Assessment fixtures
- status: pending
- model: opus
- depends: D25
**Brief.** Own `tests/test_assessment_skill.py:AssessmentSkillFixtureTests` and `tests/fixtures/assessment-skill/`; test healthy/partial/contradictory/unsafe claims for structured sources, unknowns, gaps, priorities and evidence.

Static fixtures prove packaging/report invariants, not that a model reliably follows prose. Include a non-agent repository, a mature no-change repository, a reproducible recurring pain signal and a capability supported by only one harness. Independently inspect a bounded application of the skill and label it qualitative; paid behavioral evaluation remains separately authorized. Reject fabricated gain/confidence, hidden-answer use, silent mutation and unrelated broad redesign.

**Acceptance.** No home/network/CLI; malformed bounded; contradictions surfaced; no gain inference; stable fixture output.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_assessment_skill.AssessmentSkillFixtureTests
```

### D27 — Whole-repo assessment
- id: D27
- title: Whole-repo assessment
- status: pending
- model: opus
- depends: D24, D26
**Brief.** Own dated `docs/ASSESSMENTS/polytropos-decision-improvement-v1.md` and JSON. Apply D26 read-only, label HEAD versus dirty/branch observations, link security/parity/readiness gaps and never infer measured gains.

Reassess current implementation rather than copying the planning snapshot. JSON fields: assessed_revision, generated_at, surfaces, findings; surfaces covers runtime, claude, codex, copilot, cursor, skills_context, evaluation_release. Each finding has status and evidence objects with repository-relative path plus a symbol/line and provenance. Include strengths/no-fit, contradicting evidence, next smallest experiment and uncertain benefit. This is an authored report, never a hand-authored attempt or evaluation envelope.

**Acceptance.** Fresh report/JSON exist; evidence paths resolve; readiness/gain separated; no activation; branch facts labeled.
**Verify.**
```bash
python3 - <<'VERIFY'
from pathlib import Path
import json
p=Path('docs/ASSESSMENTS/polytropos-decision-improvement-v1')
r=json.loads(p.with_suffix('.json').read_text())
assert len(r['assessed_revision'])==40 and r['generated_at']
assert set(r['surfaces']) >= {'runtime','claude','codex','copilot','cursor','skills_context','evaluation_release'}
assert len(p.with_suffix('.md').read_text().split()) >= 150
for finding in r['findings']:
    assert finding['status'] and finding['evidence']
    for e in finding['evidence']:
        assert Path(e['path']).is_file() and e.get('provenance') and (e.get('symbol') or e.get('line'))
VERIFY
```

## Phase 7 — Training-data preparation

Read `tasks/kits/decision-improvement/TRAINING-DATA.md`. Collection/export setup is required V1 scope; actual training and data transfers are separate actions. D31–D34 run before D28–D30; IDs are retained for compatibility.

### D31 — Decision-time snapshots and training example contracts
- id: D31
- title: Decision-time snapshots and training example contracts
- status: pending
- model: opus
- depends: D06, D09, D14

**Brief.** Own bin/training_data.py snapshot/schema seam, bounded artifact integration and tests/test_training_data.py SnapshotTests. Follow TRAINING-DATA.md. Reconcile existing root-cause classes and label taxonomy; add opt-in capture hooks through existing decision/attempt owners with source IDs, capture boundaries and redaction before persistence. This is not general transcript logging.

**Acceptance.** Exact input-time evidence is immutable; late labels cannot change input; missing historical fields stay unknown; disabled collection preserves legacy behavior; secrets, oversize payloads and unknown eligibility cannot be persisted as training content.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_training_data.SnapshotTests
```

### D32 — Reviewed labels and eligibility lifecycle
- id: D32
- title: Reviewed labels and eligibility lifecycle
- status: pending
- model: opus
- depends: D31

**Brief.** Extend training_data through existing private-store authority with label review/correction, evidence linkage, eligibility, retention and revocation; add LabelEligibilityTests. Keep raw operational labels and provider suggestions separate from adjudicated targets. Handle ambiguity, multiple causes, disagreement and successful/no-failure examples under explicit schemas.

**Acceptance.** Unsupported claims remain unresolved; future actions are separate from original inputs; unknown use rights refuse export; expiry and revocation invalidate dependent exports and identify downstream artifacts without claiming model unlearning.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_training_data.LabelEligibilityTests
```

### D33 — Grouped dataset splits and reproducible local exports
- id: D33
- title: Grouped dataset splits and reproducible local exports
- status: pending
- model: opus
- depends: D32

**Brief.** Reuse D06 partitions/exposure ownership for related-defect grouping and duplicate handling. Implement deterministic local JSONL exports and immutable manifests with provenance, label versions, sampling/exclusion counts and content identities; add DatasetExportTests. Train only from eligible development records and keep audit metadata separate from model inputs.

**Acceptance.** Related attempts cannot cross protected splits; exposed or revoked examples refuse; future-answer leakage and missing source references fail; repeated export is deterministic; no network or training action occurs.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_training_data.DatasetExportTests
```

### D34 — Collection readiness and operator runbook
- id: D34
- title: Collection readiness and operator runbook
- status: pending
- model: opus
- depends: D33

**Brief.** Own docs/TRAINING-DATA-READINESS.md, ReadinessTests in tests/test_training_data.py, source release-gate mappings and integration coverage. Demonstrate capture-to-review-to-export and revocation using synthetic temp stores. Document enable/disable, eligible-run scope, retention, destination restrictions, dataset quality checks and future checkpoint links.

**Acceptance.** V1 ships working collection/export setup with an explicit readiness report; no arbitrary dataset-size threshold; negative cases and disabled mode pass; synthetic tests are not training readiness; no model download, training, private backfill or upload.

**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_training_data.ReadinessTests
```

## Phase 8 — V1 handoff

### D28 — Jev-free matrix
- id: D28
- title: Jev-free matrix
- status: pending
- model: opus
- depends: D24, D27, D34
**Brief.** Own release matrix and `tests/test_decision_release_matrix.py:JevFreeMatrixTests`. Matrix harness/client/OS/adapter/enforcement/mode/fallback; canary/active unavailable absent D23 evidence and Cursor adaptive unsupported pending independent proof.

Extend `bin/release_gate.py`, `primitives/harness-capabilities.json` and source `docs/RELEASE.md` through its generator. Prove no Jev import/key/SDK/network is needed on startup, rules/replay or rollback. Compare baseline conformance across all four adapters separately; adaptive support only for verified scope. Current Cursor implementation must not be reimplemented or mislabeled absent just because its adaptive profile is unavailable.

**Acceptance.** Unsupported explicit; optional fallback passes; live gates linked; no credential; no performance claim.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_release_matrix.JevFreeMatrixTests
```

### D29 — Offline conformance
- id: D29
- title: Offline conformance
- status: pending
- model: opus
- depends: D28
**Brief.** Own conformance document and `JevFreeConformanceTests`; test contracts/privacy/caps/resume/acceptance/fallback/pins/rollback/migration/package/docs/private store and record run versus unavailable checks.

Write `docs/DECISION-IMPROVEMENT-CONFORMANCE.md` and add the named conformance class to `tests/test_decision_release_matrix.py`. Cover old ledgers/preferences with absent new fields, interrupted operations and schema migrations without relocating user data. Run all required source generators and drift checks as well as the full suite; report skipped/unavailable installed-client or enforcement checks separately. Keep runtime stores excluded from packaging.

**Acceptance.** Full suite green; gaps listed; no live calls; no publish; no default activation.
**Verify.**
```bash
PYTHONPATH=tests python3 -m unittest test_decision_release_matrix.JevFreeConformanceTests && python3 -m unittest discover -s tests && python3 bin/docs_build.py check && python3 bin/copilot_docs.py check && python3 bin/sync_codex_surfaces.py check && python3 bin/release_gate.py check
```

### D30 — V1 handoff
- id: D30
- title: V1 handoff
- status: pending
- model: opus
- depends: D29
**Brief.** Own `docs/DECISION-IMPROVEMENT-V1-HANDOFF.md`; state supported facts, rollback and gaps; defer R08 families, shadow/calibration, concurrency, Cursor adaptive and Jev. Source roadmap never authorizes V2.

Report the actual accepted commit, feature/support matrix, mechanical versus live-ready status, rollback/migration procedure, remaining operator inputs and authorized-but-unrun checks. Link existing evidence without reconstructing records. Concurrency and existing Cursor implementation remain intact; only new adaptive extensions are deferred. Include the D34 collection/export readiness report and capture configuration; distinguish shipped setup from authorized data collection and actual training. Identify optional O tasks, R08 families, separate J release and M01 research, with entry gates rather than an automatic queue.

**Acceptance.** Exact facts; live gaps; defer register; no authorization token; no release action.
**Verify.**
```bash
python3 -c "from pathlib import Path; t=Path('docs/DECISION-IMPROVEMENT-V1-HANDOFF.md').read_text().lower(); assert 'deferred' in t and 'not authorization' in t and 'rollback' in t"
```
