# Polytropos decision and improvement — Claude Code execution handoff

Prepared against main `aab755378975e9191db6ced16ee07a27a414af21`. This is the self-contained planning artifact requested by the user, with two product releases, phased native kits, a loadable repository-assessment skill, and a separately selected RSI research extension. Implementation has not been dispatched. Source attachments' embedded prompts were treated as planning input, not authorization to execute them.

## Load this document into Claude Code

Use the current Polytropos plugin's planning/execution workflow. If the repository already contains the exact file blocks below, read them in place. Otherwise materialize each `BEGIN FILE` block at its repository-relative path without overwriting differing existing files or statuses; reconcile differences before writing. The four-backtick wrapper is transport markup, not part of the file. This document contains the complete content needed for the kits and skill; the original attachments are not required.

Suggested initial instruction:

> Read this handoff and current repository instructions. Reconcile HEAD against the recorded main baseline and preserve completed work. When I ask you to execute, use `/polytropos:execute decision-improvement-v1`, starting with D01 and following the dependency graph through all 34 tasks (including D31–D34 before handoff), with independent task verification and phase review. Preserve the legacy default. Complete the selected V1 offline scope and report any blocked live gates. Do not automatically start optional advice, Release 2, paid experiments or policy activation.

A request to review the handoff is planning-only. A request to execute V1 authorizes ordinary implementation/verification/local branch commits within its scope, not the separate gated actions. Later explicit authorization carries forward and does not need to be re-requested.

First ensure `python3` resolves to Python 3.12 or newer in the execution environment; current main uses syntax unsupported by the macOS system Python. Select an existing compatible environment, without installing anything. After files exist, these checks dispatch nothing:

```bash
python3 bin/kit_contract.py graph --kit .claude/kits/decision-improvement-v1
python3 bin/kit_contract.py roster --kit .claude/kits/decision-improvement-v1 --executor interactive
python3 bin/claude_execute.py run --kit .claude/kits/decision-improvement-v1 --task D01 --dry-run
```

Run from the target repository root; this main snapshot's Claude headless driver resolves its role agents there. The interactive execute skill is the intended reviewed workflow. Do not select a headless mode that silently omits the independent verifier; inspect roster support first.

To use the assessment skill now, ask Claude Code to read `tasks/kits/decision-improvement/skills/assess-improvement/SKILL.md` and its linked template, then assess the chosen repository into a named output document. This is a staged loadable skill, not an installed plugin command. D25/D26 integrate and validate native discovery across supported Polytropos harnesses later.

## Contents and authority

- Shared architecture, initial whole-Polytropos assessment and guardrails.
- Release 1: eight phases, thirty-four pending tasks in the native Claude kit.
- Optional V1 advice: four separately selected tasks; R08 decision families deferred; M01 research now has eight planned tasks in four phases, with separate entry gates.
- Release 2: optional Jev kit, separately authorized and evaluated.
- Required V1 training-data setup: snapshots, reviewed labels, eligibility, protected splits and versioned local exports; training remains separate.
- RSI research extension: backend lineage, protected experiments, evolving-improver comparison and evidence criteria.
- Portable assess-improvement skill and its report/brief template.
- Per-release implementer, verifier and reviewer agents.

The Claude kits own future execution status. The repository also carries a Codex planning mirror under `tasks/kits/decision-improvement/TASKS.md`; it is deliberately omitted here to avoid a second execution status authority. Implementation test modules named in briefs are proposed deliverables; validation of this planning artifact does not mean those tests or features already exist.

## Source traceability

R00 maps to baseline/ADR; R01 to remaining provenance/accounting deltas on completed steps16–18; R02 to profile/manifests; R03/R04 to contracts/providers/legacy policy; R06/R07 to measurement and recovery protocol; R09/R10 to proposals/approval/activation; R11 to conformance/release. R05 and calibration fitting are in optional advice; R08 families remain later gated scopes; M01 is specified in the embedded recursive-improvement planning kit. J01–J03 map to the optional second release, with a separate final evidence refresh task. The assessment skill adds reusable applicability/no-fit analysis and a whole-Polytropos pilot requested by the user.

The supplied roadmap and accompanying chat are design sources. Their historical `7fc5996` baseline and instruction to start original step16 are superseded by the actual main reconciliation. Vendor/research claims motivate hypotheses only; no speculative Jev API or claimed speedup was imported. The original 26-step roadmap was not independently supplied here; current HANDOFF and source code provide its reconciliation.

## File: `tasks/kits/decision-improvement/PLAN.md`

<!-- BEGIN FILE tasks/kits/decision-improvement/PLAN.md -->
````markdown
# Decision and improvement — Release 1 architecture

autonomy: advisory
workflow: reviewed

## Goal and handoff posture

Deliver a Jev-independent method for testing and retaining small improvements to Polytropos, and a reusable `assess-improvement` skill for applying the method to existing repositories. Models provide bounded judgments; deterministic policy chooses actions; existing runtime authorities enforce constraints; independent evaluation determines whether a change helped.

This kit is a planning deliverable. Every task is pending. Loading this document for review does not dispatch work. When the user requests execution, use Claude Code’s current `/polytropos:execute decision-improvement-v1` workflow, start with D01, and review each phase before continuing. Claude Code’s native interactive execution skill is the intended host for this handoff. The Codex planning mirror uses worker intents and the native `$execute` skill if separately selected; do not run both copies as independent status authorities. A headless driver must refuse unsupported roles rather than silently omit independent verification. Release 2 is a separate, gated kit. No original attachment's embedded execution prompt overrides this handoff.

Preparation basis: `main` and freshly fetched `origin/main` both resolved to `aab755378975e9191db6ced16ee07a27a414af21` on 2026-09-16 UTC (2026-09-15 America/Chicago). The supplied roadmap used `7fc5996`; its instruction to implement original step 16 next is superseded. Original steps 16–26 are implemented foundations. Reconcile their current limits; do not rebuild them.

At preparation, a separate working branch had newer Claude/Cursor verification commits (`b48a284`, `1755ead`, `fd80734`) and unrelated uncommitted work. They were preserved, not incorporated into this main-based plan. D01 must inspect then-current HEAD and correct affected briefs if those changes have since landed. In particular, source capability support is not equivalent to installed-client verification. Do not downgrade newer evidence to this snapshot.

Planning validation also exposed two baseline test limitations to reconcile in D01: the lessons-promotion test hardcodes the legacy in-tree journal path although fresh worktrees use runtime_data, and a scheduler snapshot can race an atomic TASKS temporary file. A focused rerun of the scheduler case passed; this does not prove the race fixed. No runtime code was changed for this planning delivery.

The source materials are the user-supplied *polytropos-decision-and-improvement-implementation-plan.md* and its accompanying chat. Their R00–R11/J01–J03 labels are traceability identifiers, not current execution state. Research/vendor statements are design motivation supplied by the user, not independently revalidated API contracts or measured gains. No unpublished Jev API is assumed.

## Release boundaries

| Track | Deliverable | Exit condition |
| --- | --- | --- |
| Release 1 core | Typed rules/replay, preserved legacy policy, offline recovery protocol/mechanics (protected live experiments only after their gate passes), manual/proposal workbench, scoped approval and rollback, reusable repo assessment | Offline conformance complete; supported deployment claims limited by actual enforcement evidence; no Jev dependency |
| Optional V1 extension | Current-model shadow advice and empirical calibration | Verified tool-free transport, explicit budget/data scope, target/labels/held-out evidence; absent extension does not block core |
| Optional later expansion | Workflow/model/effort/context/optional-role or skill selection | One decision family at a time, its own ablation evidence, no mandatory assurance removal |
| Release 2 | Optional documented Jev provider through the same contracts | Access/conformance and independently evaluated scope; exact approval before canary/active use |
| Research later | Compare improvement procedures themselves | Multiple matched trajectories and unseen successor evaluation; neither release depends on it |

Offline mechanisms may ship with `protected-live-experiments: unavailable`. Such a release is explicitly an offline/advisory edition, not a claim that R02's protected live gate passed. A full protected experiment claim requires executable sentinel evidence on at least one named deployment profile. An unavailable profile never silently selects `trusted-host`. Machine-enforce the distinction: without a verified named protected profile, immutable grouped partitions/exposure history, complete predeclared trial inputs and exact approval/evaluation evidence, production transitions to `canary` and `active` refuse. An offline edition exposes legacy or shadow decision modes plus manual proposal drafting; synthetic fixtures may exercise lifecycle transitions without certifying a live profile.

No performance gain is required for a valid mechanism release. A well-run trial that retains the baseline is a valid outcome. Core feature completion, installed-client support, and promotion of an individual candidate are separate decisions.

## Existing owners and exact extension boundaries

| Concern | Existing authority | Planned change |
| --- | --- | --- |
| Task grammar, readiness, roles, budget admission | `bin/kit_contract.py` | Extend admission references/operation scopes; retain historic task-dispatch meaning and DAG rules |
| Durable execution events | `bin/attempt_ledger.py`, projections in `bin/attempt_history.py` | Add versioned policy/decision/acceptance/admission provenance; old absent fields remain unknown |
| Process/path/environment confinement | `bin/proc_runner.py`, `bin/safe_paths.py`, `bin/exec_policy.py` | Reuse them for profile enforcement and tests; no parallel subprocess/path layer |
| Native dispatch and eligibility | Four `*_execute.py` drivers, `bin/harness_adapter.py`, capability registry | Preserve native loops, explicit pins, privacy, support and verification distinctions |
| Existing deterministic routing | `bin/routing_policy.py`, per-harness policy modules | Wrap current behavior as a named legacy bundle; extraction needs golden compatibility evidence |
| Repositories, task mining, benchmark oracles | `bin/repo_bench.py` | Retain mining, clean extraction, grading and its envelope owner |
| Complete workflow experiments and policy persistence | `bin/workflow_eval.py` | Extend its evaluation orchestration and existing proposal/review/apply/rollback owners; no second benchmark writer |
| Context/skills | `bin/graph_ground.py`, `bin/graph_brief.py`, `bin/lessons_store.py`, existing skill bundles | Bounded fresh context, applicability and contradiction handling; no global lesson append |
| Resource numbers | One `data/pricing*.json` per harness | Read at runtime; keep billed USD, credits, estimates and subscription proxies separate |
| Private storage and redaction | `bin/runtime_data.py`, `bin/redact.py` | Use existing stores/seams; no personal traces in tracked examples or plugin cache |
| Release claims | `bin/release_gate.py`, `primitives/harness-capabilities.json` | Evidence-scoped capabilities per harness/client/OS; installed facts stay unknown until observed |

Five proposed modules are boundaries, not a mandatory framework: `decision_contract.py` owns validated values; `decision_provider.py` owns rules/replay and optional transport adapters; `decision_policy.py` owns pure selection and bundle resolution; `decision_eval.py` owns read-only metrics/calibration; `improvement_loop.py` orchestrates bounded proposals through existing evaluation/persistence owners. If equivalent functionality lands before execution, extend it instead. The improvement workbench cannot write benchmark results or attempt events directly.

Current `workflow_eval.apply_proposal` writes a pull-only preference file; drivers do not automatically consume it. New runtime activation must be an explicit, versioned opt-in path. Absence of an approved active scope continues existing behavior. Existing preference files must never silently become executable policy bundles.

## Data contracts and fixed authority

Use stdlib dataclasses/enums and strict runtime validation. Define schema versions and backward compatibility, canonical serialization/hashing, bounded payloads, and explicit missing values before wiring a provider. Hashes identify content; they are not protection against an unrestricted worker.

| Object | Required information |
| --- | --- |
| QuestionSpec | Stable ID/version, complete question/rubric, boolean/choice/ordinal kind, permitted outcomes, unknown/abstention semantics, dependencies, sensitivity |
| DecisionRequest | Correlation ID, run/task/attempt linkage, intended use, task/acceptance/state identities, eligible alternatives, bounded approved state, question versions, provider eligibility, deadline, resource policy and admission reference |
| DecisionResult | Matching request/state identity, status (`ok`, `abstain`, `unsupported`, `unavailable`, `invalid`, `timeout`), typed values, optional raw distributions and separately calibrated distributions, vendor confidence distinct from either, evidence references, requested/dispatched/observed provider/model identity, versions, duration/usage and basis |
| DecisionRecord | Coordinator-owned baseline/recommended/selected actions, bundle hash, mode (`legacy`, `shadow`, `canary`, `active`), reason codes, rejected alternatives, fresh admission and attempt references |
| PolicyBundle | Immutable ID/hash, parent, scope, component versions, approved data parameters, capability/provider/calibration requirements, fallback and approval/evaluation provenance |
| CandidateProposal | Parent hash, recurring evidence and counterevidence, falsifiable hypothesis, allowlisted bounded diff, scope, expected tradeoff, evaluation specification, rollback target |

Reject duplicate JSON keys, unknown/extra fields, wrong types, bool-as-number, non-finite/out-of-range values, missing required answers, wrong correlation/state identities, invalid candidate IDs and stale applicability. A choice distribution covers exactly the defined categories and sums within an explicitly documented tolerance; do not normalize invalid input into validity. Independent coexisting hypotheses are separate boolean questions, not a forced categorical distribution. Ordinal levels need a rubric. A score or distribution-shape confidence is not automatically a probability of task success.

A provider cannot execute tools, grant permission, raise a budget, modify the DAG, remove mandatory review, accept an artifact, alter controller logic or approve a candidate. All such authority stays outside candidate data. Recheck eligibility, capability, privacy and atomic admission just before action. Invalid/unavailable advice takes an approved fallback or stops; it cannot route around a denial.

Rules may abstain and leave probability fields null. Replay predicts no counterfactual and incurs zero new inference usage; its historical cost remains in the original record. Cache/replay identity includes project/provider eligibility, task/acceptance version, complete state, alternatives, questions/rubrics, provider/model, policy and calibrator. No cross-project/provider cache reuse without authorization.

Preserve unknown external outcomes, resource use and reservations on resume. Never promise exactly-once external calls or refund/redo a call whose outcome is unknown. Decision inference/retries/JSON repair consume named operation scopes without redefining old `max-dispatches`; every actual model call belongs in the aggregate cap. No unbounded response repair.

## Protected experiments and evaluation protocol

The execution DAG, repository graph, and policy lineage are distinct. Repository graph edges guide navigation only. Missing edges do not establish safe parallelism; stale/unknown graphs fall back to source search. Keep sequential execution as the default.

Freeze versioned development, calibration, promotion and final-audit partitions. Keep related issue/defect variants in a common group; record exposure and retire contaminated audit material. Candidate problem statements exclude reference patches, future fix messages and hidden labels. Independent task-validity checks distinguish synthetic mechanism tests from real task evidence.

The controller owns evaluation rules, immutable inputs, labels, budget/policy pointers and acceptance evidence. The protected profile needs sentinel tests that deny hidden-answer reads, control-state writes, controller mutation, malicious test/setup escapes and judge writes, while permitting an ordinary build. Fixture argv checks, worktrees, `0700` files and content hashes do not establish this boundary. No host/account setup is authorized by this plan.

First hypothesis: on a narrow cohort of cross-module failures, one bounded package of previously missing contract context before a same-model retry improves accepted recovery or total resources without weakening quality. Infrastructure/auth/permission/unavailable-model failures are determined from trusted events and never trigger model escalation by a semantic guess.

| Arm | Behavior |
| --- | --- |
| A | Actual frozen current recovery policy, including any retry it already performs |
| B | Same permitted extra attempt and diagnostics, same model, no targeted package |
| C | Same permitted attempt/model/diagnostics plus bounded relevant contract context; then the declared remaining recovery path |

If A equals B in this cohort, record equivalence and collapse the duplicate. Restore equivalent failing checkpoints, pin acceptance/effort/environment/resource ceilings, and allow at most one approved context repair. Do not change model and context at once. Context candidates include omitted interfaces, direct consumers, configuration and contract tests; exclude privacy-ineligible files and irrelevant hubs. No applicable context is a legitimate abstention.

Use matched checkpoints to estimate conditional recovery and a prospective full-task study before general rollout. Record initial-attempt cost even when a checkpoint is reused analytically. Report recovery-only and whole-task results; all failed attempts, planning, retrieval, decisions, review, judging, proposer and experiment costs belong at their actual scope.

Predeclare primary endpoint, practical gain threshold, allowed quality regression, resource ceilings, stopping/interim-look rules and independent evaluation before live trials. Choose sample size from pilot variation and useful effect size, not a magic universal minimum. Until an operator specifies these inputs, the plan is incomplete for live promotion, and the system must say so.

Metrics: accepted recovery/full completion; regressions and escaped defects over a defined observation window; total resources by basis; end-to-end and decision latency; operator interventions; coverage/abstention/invalid/missing/censored outcomes; subgroup and transfer effects with uncertainty. Cost per accepted task includes failures in its numerator and is undefined with zero accepted tasks. Judge opinion is not ground truth. On-policy logs do not reveal untried actions' outcomes.

Calibrate only defined targets with defensible labels, a separate fitting partition and held-out validation. Pin target/question/provider/model/domain/dataset/method/version/coverage. Report raw and calibrated metrics separately; sparse or mismatched evidence is `insufficient-evidence`. Calibration fitting and optional model advice are not prerequisites for a deterministic first experiment.

## Proposal, promotion and rollback

V1 supports manual evidence reports and bounded data-only proposals without any model. Optional model proposals use separately admitted jobs, not an execution hook. Include supporting and contradictory attempts, the expected tradeoff and a falsification test. Deduplicate proposals, cap candidates and total effort, retain rejections, and compare small deterministic searches when appropriate. No candidate edits arbitrary Python, shell, module paths, acceptance, permissions, pricing, the improvement procedure or hidden evaluation rules.

Extend the existing lifecycle to distinguish draft, offline-valid, evaluated, approved, canary, active and retired, with rejected, insufficient-evidence and rolled-back outcomes. Candidate and evidence changes invalidate an approval bound to exact hashes and scope. A proposer cannot approve itself. Runtime activation uses an atomic scoped pointer with stale/concurrent-update detection; each run pins its bundle and component versions.

Canaries are bounded eligible cohorts. Monitor completion, delayed defects/censoring, interventions, resource basis, invalid/abstain rates, provider/version/distribution drift. Rollback selects a previously approved compatible bundle for future runs without contacting an optional provider. Existing runs finish under their pin or cancel/reconcile safely. Rollback never resets user workspaces, erases evidence, reverses external effects or refunds calls.

## Assessment skill and application to all of Polytropos

A loadable draft lives in `tasks/kits/decision-improvement/skills/assess-improvement/`. It examines source evidence, identifies authority boundaries, distinguishes observed defects from missing evidence, and returns scoped hypotheses plus self-contained implementation briefs. It can conclude `no supported intervention`. It does not impose these modules on an unrelated repository.

The kit's `REPO-ASSESSMENT.md` applies the method to the shared runtime, all four harnesses, architecture/skills/context, evaluation/promotion, and packaging/release. Future integration puts concise entrypoints into the actual supported skill surfaces using existing generators and installer ownership rules. No broad global instruction additions or plugin installation are part of this planning delivery.

## Execution, verification and change control

Use task tier aliases resolved from the executing harness's current pricing/policy data. Claude tasks use `sonnet` for routine work and `opus` for hard contracts/security/integration; verifier and reviewer use independent judgment. These are dispatch intents, not observed model identity or fixed API IDs. Codex planning mirrors use `mid`/`strong`. Historical routing cards were consulted only as partial observational evidence; they are not causal model rankings and supply no portable numeric claims here.

Keep task fields limited to the existing parser contract, and statuses exactly pending/in-progress/done/blocked. New tests named by a task are intended deliverables, not tests already present. Missing modules must fail the task verify command. A new behavior needs a meaningful failing test; reconciliation and release-only checks may explicitly use regression evidence. Shared runtime/policy edits are serial even when the DAG permits independent design work. Never run parallel mutations in one checkout.

Before running a kit, ensure `python3` resolves to Python 3.12 or newer: this main snapshot uses modern f-string syntax and TOML support. Select an already installed interpreter/environment; this plan does not authorize installing one. A missing compatible interpreter is an environment blocker, not a product-test failure.

Each task receives its full brief, this plan, guardrails, and relevant artifacts. Execute owns NOTES.md and all outcome/attempt evidence; the architect creates none. Run focused verification for each task and the repository-required full suite/docs gates at green commit boundaries. Independent verification reruns the checks; phase review inspects drift and authority violations; final acceptance is separate.

Unresolved facts should become scoped blockers or revised briefs. Do not declare a task done just because a broad suite passes while its named feature/test is absent. Existing completed implementation may satisfy a task only after the executor independently verifies its exact acceptance and records the reconciliation through the normal execution process.

## RSI research extension (M01)

See `tasks/kits/recursive-improvement/PLAN.md` and `TASKS.md` for the ledger relationships, generation lineage, protected evaluation and three-arm recursive experiment. V1 should retain extension seams for these records, without implementing the research loop implicitly. The extension reuses the existing storage and approval authorities, is independent of Jev, and separates offline mechanism completion from demonstrated recursive gains.

## Fine-tuning data readiness in V1

`TRAINING-DATA.md` specifies decision-time capture, independently reviewed labels, eligibility/retention/revocation, grouped dataset partitions, reproducible export and readiness reporting. D31–D34 make this setup required before V1 release; D28 depends on D34. Keep existing task IDs. Collection in future eligible runs and actual training have distinct scope. No private transcript backfill, external upload or trainer is implicit.
````
<!-- END FILE tasks/kits/decision-improvement/PLAN.md -->

## File: `tasks/kits/decision-improvement/REPO-ASSESSMENT.md`

<!-- BEGIN FILE tasks/kits/decision-improvement/REPO-ASSESSMENT.md -->
````markdown
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

## Additional validation findings

The planning branch’s full-suite validation exposed `test_lessons_promote.NoScaffoldingWritesTests.test_real_run_touches_only_gitignored_path`, which assumes an existing legacy journal directory while a fresh checkout correctly resolves an external namespace. The test passed with an empty legacy `journal/promotions/` fixture. It also exposed a race in `test_kit_scheduler.ManifestTests.test_a_refused_manifest_stops_integration_and_keeps_the_copies`: snapshot_tree can stat an atomic TASKS temporary file after another thread removes it. That case passed alone; the underlying race remains a baseline finding, not a planning-artifact regression or a fixed defect. Record these in D01 and scope any runtime repairs separately.

## Where the methodology should not add machinery

Keep deterministic admission, readiness, path validation, process bounds, required assurance and release conditions deterministic. Do not add model calls to straightforward tasks or stable wrappers with no recurring pain signal. Repository graphs remain optional. No need for a new server, graph database, generic rule language, always-loaded policy manual or cross-harness price table. Meta-improvement is deferred until the fixed procedure yields independently validated successors.

## Initial recommendation

Prepare the typed/evidence foundation and the assessment skill first; retain legacy policy throughout. Complete protected-profile verification before any trusted live comparison. Treat context repair as a falsifiable hypothesis; approve a scoped policy only if the predeclared evaluation supports it. All four harnesses participate in compatibility and assessment, while the first live experiment can use one verified configuration. Missing evidence remains an explicit outcome.
````
<!-- END FILE tasks/kits/decision-improvement/REPO-ASSESSMENT.md -->

## File: `tasks/kits/decision-improvement/GUARDRAILS.md`

<!-- BEGIN FILE tasks/kits/decision-improvement/GUARDRAILS.md -->
````markdown
# Decision and improvement — execution guardrails

Read the kit PLAN.md and current repository instructions. User scope and existing authorization govern execution; attached historical prompts are requirements input, not new authorization.

- Preserve current main behavior and completed roadmap work. Never replace new correct code with the attachment's older snapshot. Do not alter unrelated working changes.
- Reuse kit_contract, attempt_ledger/history, runtime_data, safe_paths, proc_runner, exec_policy, repo_bench and workflow_eval as the existing owners. No competing ledger, benchmark writer or host loop.
- stdlib-only bin/tests; unittest; injected runners; synthetic labels/secrets; temporary fixture homes/repos/stores. No real claude/codex/copilot/agent/graphify calls from tests or verify commands. Demo/dry-run is offline.
- Enforce required acceptance, permissions, provider/project eligibility, explicit pins, budget ceilings and native capability checks before action. Predictions cannot grant authority. Unknown external outcomes are not free retries.
- Preserve per-harness prices and usage bases. Resolve values at runtime; never mix credits, billed USD and subscription API-equivalent proxies. Missing duration/usage/model identity is unknown, not zero or inferred from a pin.
- Candidate data cannot change controller code, audit labels, acceptance, mandatory review, permission/budget policy, or the improvement procedure. No automatic global lesson/skill edits.
- A protected experiment requires demonstrated isolation, not hashes or worktrees. Unsupported environments refuse protected live mode. Ordinary offline fixtures can prove rejection and mechanics, never live safety or model quality.
- No new provider integration, live/paid evaluation, private telemetry acquisition, installation, default activation, publish, push or merge is authorized merely by this planning document. Preserve explicit authorization supplied later rather than asking for it again.
- Release 2 and optional extensions are separate scope decisions. V1 must start, work and roll back with every optional provider absent. No Jev endpoint, SDK, model or pricing guesses.
- Use the exact task verify command; ensure proposed named tests actually exist and collect nonzero cases. Never substitute a glob that succeeds with zero tests. Full suite and generated mirror checks must pass before a green-boundary commit.
- Verifier/reviewer roles do not edit tracked sources. Mutation checks use temporary copies. If a check unexpectedly changes the tree, restore that agent's own damage byte-for-byte and report it; never reset another person's work.
- Commit cohesive green boundaries using type(scope): summary and a substantive body explaining why, verification and limitations. Use configured identity; no AI/session/coauthor attribution. No main commits or history rewrites.
````
<!-- END FILE tasks/kits/decision-improvement/GUARDRAILS.md -->

## File: `.claude/kits/decision-improvement-v1/PLAN.md`

<!-- BEGIN FILE .claude/kits/decision-improvement-v1/PLAN.md -->
````markdown
# Decision and improvement — Claude Code Release 1 kit

autonomy: advisory
workflow: reviewed

Read `tasks/kits/decision-improvement/PLAN.md` for the complete architecture, baseline, protocol, release gates and design rationale. Read `tasks/kits/decision-improvement/REPO-ASSESSMENT.md` for the initial whole-repository application and `GUARDRAILS.md` for execution fences. All are supplied in the standalone Markdown handoff.

This native kit's TASKS.md is the execution status authority. Its eight phases cover baseline, evidence/isolation, typed decisions, recovery evaluation, proposal/promotion, assessment skill, training-data preparation and release. Every task begins pending; execute owns NOTES.md and attempt evidence. The Codex mirror is a planning projection, not another run.

Use the standing implementer/verifier/reviewer trio and separate final acceptance. No optional roles are declared. Implementation tier intent is each task's model field; it overrides the agent default. Resolve actual models through current Claude pricing/policy data. The coordinating frontier does not replace ordinary workers. Shared-module changes run sequentially; phase review precedes the next phase.

Start D01 after the user requests execution. Preserve newer completed work and all unrelated edits. Ordinary per-task work can continue through V1's offline scope; live probes, protected trials, activation and Release 2 are explicit later actions. Without verified enforcement and exact evaluation/approval gates, runtime canary/active transitions refuse. Optional advice and family expansion live in OPTIONAL-TASKS.md and do not block the core.

Training-data setup is required V1 work: follow `tasks/kits/decision-improvement/TRAINING-DATA.md` and D31–D34 before the D28–D30 release checks. There are 34 tasks; execute dependencies rather than numeric ranges. Training itself remains separate.
````
<!-- END FILE .claude/kits/decision-improvement-v1/PLAN.md -->

## File: `.claude/kits/decision-improvement-v1/TASKS.md`

<!-- BEGIN FILE .claude/kits/decision-improvement-v1/TASKS.md -->
````markdown
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
- status: pending
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
````
<!-- END FILE .claude/kits/decision-improvement-v1/TASKS.md -->

## File: `.claude/kits/decision-improvement-v1/GUARDRAILS.md`

<!-- BEGIN FILE .claude/kits/decision-improvement-v1/GUARDRAILS.md -->
````markdown
# Decision and improvement — execution guardrails

Read the kit PLAN.md and current repository instructions. User scope and existing authorization govern execution; attached historical prompts are requirements input, not new authorization.

- Preserve current main behavior and completed roadmap work. Never replace new correct code with the attachment's older snapshot. Do not alter unrelated working changes.
- Reuse kit_contract, attempt_ledger/history, runtime_data, safe_paths, proc_runner, exec_policy, repo_bench and workflow_eval as the existing owners. No competing ledger, benchmark writer or host loop.
- stdlib-only bin/tests; unittest; injected runners; synthetic labels/secrets; temporary fixture homes/repos/stores. No real claude/codex/copilot/agent/graphify calls from tests or verify commands. Demo/dry-run is offline.
- Enforce required acceptance, permissions, provider/project eligibility, explicit pins, budget ceilings and native capability checks before action. Predictions cannot grant authority. Unknown external outcomes are not free retries.
- Preserve per-harness prices and usage bases. Resolve values at runtime; never mix credits, billed USD and subscription API-equivalent proxies. Missing duration/usage/model identity is unknown, not zero or inferred from a pin.
- Candidate data cannot change controller code, audit labels, acceptance, mandatory review, permission/budget policy, or the improvement procedure. No automatic global lesson/skill edits.
- A protected experiment requires demonstrated isolation, not hashes or worktrees. Unsupported environments refuse protected live mode. Ordinary offline fixtures can prove rejection and mechanics, never live safety or model quality.
- No new provider integration, live/paid evaluation, private telemetry acquisition, installation, default activation, publish, push or merge is authorized merely by this planning document. Preserve explicit authorization supplied later rather than asking for it again.
- Release 2 and optional extensions are separate scope decisions. V1 must start, work and roll back with every optional provider absent. No Jev endpoint, SDK, model or pricing guesses.
- Use the exact task verify command; ensure proposed named tests actually exist and collect nonzero cases. Never substitute a glob that succeeds with zero tests. Full suite and generated mirror checks must pass before a green-boundary commit.
- Verifier/reviewer roles do not edit tracked sources. Mutation checks use temporary copies. If a check unexpectedly changes the tree, restore that agent's own damage byte-for-byte and report it; never reset another person's work.
- Commit cohesive green boundaries using type(scope): summary and a substantive body explaining why, verification and limitations. Use configured identity; no AI/session/coauthor attribution. No main commits or history rewrites.
````
<!-- END FILE .claude/kits/decision-improvement-v1/GUARDRAILS.md -->

## File: `tasks/kits/decision-improvement/OPTIONAL-TASKS.md`

<!-- BEGIN FILE tasks/kits/decision-improvement/OPTIONAL-TASKS.md -->
````markdown
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
````
<!-- END FILE tasks/kits/decision-improvement/OPTIONAL-TASKS.md -->

## File: `.claude/kits/decision-improvement-v2/PLAN.md`

<!-- BEGIN FILE .claude/kits/decision-improvement-v2/PLAN.md -->
````markdown
# Decision and improvement — Release 2, optional Jev

autonomy: advisory
workflow: reviewed

## Start gate

This is a separate deferred release. Do not chain it automatically after Release 1. Start only when the user selects it, core V1 is accepted, real Jev access exists, current official documentation can be inspected, and approved data/transport/resource scope is known. A human-authored start request is not replaced by a worker editing a plan token. Paid probes, protected trials and production activation each require authorization covering that actual action; reuse existing authorization when it already applies.

Read the core plan at `tasks/kits/decision-improvement/PLAN.md`, its guardrails, the original release evidence, and current repository instructions. A protected-live V1 gate is needed before trusted live whole-workflow trials or promotion. An offline-only V1 edition does not pass that gate. If access or enforcement is missing, leave the relevant task blocked and retain the Jev-free system.

## Architecture

Jev is an optional provider behind the existing DecisionProvider contract. Add only a documented adapter, capability/privacy/credential configuration, strict mapper, optional dependency boundary, offline fixtures and comparative evidence. Task/attempt identities, admission, verification, hard constraints, policy lifecycle and benchmark ownership remain unchanged. Credentials, endpoints, SDK imports, model IDs, retention terms and prices must come from then-current official documentation and the configured account; none is specified by this plan.

The J01 conformance record separately lists documented and observed question kinds/cardinalities, request/response limits, model/response versioning, rate limits, retention/privacy, billing units and error semantics. A small account probe confirms only what it actually exercises; connectivity is not complete conformance.

Prefer a documented HTTP transport compatible with core stdlib rules when practical; otherwise isolate an optional bridge and explicitly review its dependency boundary. Default startup must never import an SDK or require access. Unsupported question kinds/cardinalities abstain or report unsupported; do not silently change categories to fit an API. Preserve raw distributions, vendor distribution-derived confidence and local calibration as distinct information.

## Evaluation and adoption

Compare rules, replay where appropriate, the optional current-model baseline when available, and Jev on identical frozen bounded states/questions. Replay is an evidence reproduction control, not a fresh predictor. Report absent optional baselines honestly rather than blocking a useful rules comparison. Separate fixed-policy provider substitution from provider-specific tuning; retain equivalent information/instructions and disclose necessary adaptations. Shadow prediction evaluation cannot establish whole-workflow benefit; follow with protected matched workflow trials, fixed acceptance and full usage accounting.

Predeclare endpoints, quality regression limits, resources, sample/uncertainty and stopping rules through V1. Never import vendor speedup/quality/cost ratios as measured Polytropos outcomes. Calibrate thresholds for the actual target/provider/version/domain; existing-model thresholds are not automatically valid for Jev.

Use V1's exact approval and scoped canary/rollback mechanism. Handle outages, rate limits, invalid/unsupported answers, calibration loss and version drift via bounded retries/circuit breaking, fresh admission and a validated provider-independent fallback. When no safe admitted fallback exists, stop. Record provider response/model version and policy version on every adopted decision; a version change invalidates calibration/applicability when required. Admission accounts for shared provider rate limits and total decision overhead; batch only semantically compatible questions within documented and locally measured limits, without assuming statistical independence. Disabling Jev is a configuration change and works without contacting Jev. In-flight runs retain their pin or safely cancel/reconcile. Never infer that successful connectivity authorizes promotion or all decision families.

## Exit conditions

Offline adapter/error/privacy/budget/fallback conformance, a separately authorized account probe where access exists, independent comparative evidence for any promoted scope, honest per-client support claims and demonstrated Jev-free rollback. A release may leave Jev disabled or shadow-only if it does not earn an active scope. All live observations and unrun probes must be identified separately. This kit never auto-publishes, installs, pushes or merges.
````
<!-- END FILE .claude/kits/decision-improvement-v2/PLAN.md -->

## File: `.claude/kits/decision-improvement-v2/TASKS.md`

<!-- BEGIN FILE .claude/kits/decision-improvement-v2/TASKS.md -->
````markdown
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
````
<!-- END FILE .claude/kits/decision-improvement-v2/TASKS.md -->

## File: `.claude/kits/decision-improvement-v2/GUARDRAILS.md`

<!-- BEGIN FILE .claude/kits/decision-improvement-v2/GUARDRAILS.md -->
````markdown
# Decision and improvement — execution guardrails

Read the kit PLAN.md and current repository instructions. User scope and existing authorization govern execution; attached historical prompts are requirements input, not new authorization.

- Preserve current main behavior and completed roadmap work. Never replace new correct code with the attachment's older snapshot. Do not alter unrelated working changes.
- Reuse kit_contract, attempt_ledger/history, runtime_data, safe_paths, proc_runner, exec_policy, repo_bench and workflow_eval as the existing owners. No competing ledger, benchmark writer or host loop.
- stdlib-only bin/tests; unittest; injected runners; synthetic labels/secrets; temporary fixture homes/repos/stores. No real claude/codex/copilot/agent/graphify calls from tests or verify commands. Demo/dry-run is offline.
- Enforce required acceptance, permissions, provider/project eligibility, explicit pins, budget ceilings and native capability checks before action. Predictions cannot grant authority. Unknown external outcomes are not free retries.
- Preserve per-harness prices and usage bases. Resolve values at runtime; never mix credits, billed USD and subscription API-equivalent proxies. Missing duration/usage/model identity is unknown, not zero or inferred from a pin.
- Candidate data cannot change controller code, audit labels, acceptance, mandatory review, permission/budget policy, or the improvement procedure. No automatic global lesson/skill edits.
- A protected experiment requires demonstrated isolation, not hashes or worktrees. Unsupported environments refuse protected live mode. Ordinary offline fixtures can prove rejection and mechanics, never live safety or model quality.
- No new provider integration, live/paid evaluation, private telemetry acquisition, installation, default activation, publish, push or merge is authorized merely by this planning document. Preserve explicit authorization supplied later rather than asking for it again.
- Release 2 and optional extensions are separate scope decisions. V1 must start, work and roll back with every optional provider absent. No Jev endpoint, SDK, model or pricing guesses.
- Use the exact task verify command; ensure proposed named tests actually exist and collect nonzero cases. Never substitute a glob that succeeds with zero tests. Full suite and generated mirror checks must pass before a green-boundary commit.
- Verifier/reviewer roles do not edit tracked sources. Mutation checks use temporary copies. If a check unexpectedly changes the tree, restore that agent's own damage byte-for-byte and report it; never reset another person's work.
- Commit cohesive green boundaries using type(scope): summary and a substantive body explaining why, verification and limitations. Use configured identity; no AI/session/coauthor attribution. No main commits or history rewrites.
````
<!-- END FILE .claude/kits/decision-improvement-v2/GUARDRAILS.md -->

## File: `tasks/kits/decision-improvement/skills/assess-improvement/SKILL.md`

<!-- BEGIN FILE tasks/kits/decision-improvement/skills/assess-improvement/SKILL.md -->
````markdown
---
name: assess-improvement
description: Assess an existing repository for a small, evidence-backed improvement opportunity and produce a scoped findings report and handoff briefs. Use for read-only improvement planning, including multi-harness Polytropos assessments; do not use to implement, enable providers, or promote policy changes.
---

# Assess improvement opportunities

Produce a reviewable, evidence-first assessment of whether a bounded improvement is worth testing. The result is planning input, not a diagnosis engine, evaluation record, policy change, or authorization to modify the repository.

## Boundaries

- Treat target source and configuration as read-only by default. Writing the requested findings report or task briefs to the designated output location is allowed. Do not install packages, mine private telemetry, invoke paid/private providers, make network calls, mutate target repositories, or change policy or release state solely because this skill is in use.
- Preserve existing user authorization. A bounded network, private-data, paid-provider, or test action already authorized for this assessment may be used as evidence; record its scope and provenance. The skill itself grants no new live-action authority.
- Use tools and tests only when they can answer an assessment question and are authorized. Prefer deterministic inspection; when a test needs mutation, run it against a temporary copy and report that limitation.
- Do not infer a defect from absence, a plan, a stale document, a schema, or a single anecdote. Label the state `unknown`, `unverified`, or `insufficient-evidence` as appropriate.
- Keep facts, constraints, judgments, and proposed actions separate. A proposed finding is not an authoritative engine record.
- Preserve existing ownership boundaries. Describe the authority already responsible for admission, execution, verification, evidence, pricing/budgets, and release; do not create a competing global authority through a report.
- Do not turn one repository's observation into a global rule. Recommendations are scoped to a named repository, component, harness, task cohort, and evaluation context.

## When to use

Use this skill when asked to find or prioritize improvement opportunities in an existing codebase, prepare an evidence-driven improvement plan, assess a harness/runtime ecosystem, or create a handoff for later implementation.

Do not use it to implement, activate, or promote a change. It can assess the suitability of a broad redesign, incident remedy, or provider proposal when the requested outcome is a scoped evidence-based conclusion, including `no-fit` or `insufficient-evidence`.

## Read only what can answer the question

1. Restate the assessment scope: repository/revision, requested outcome, components and harnesses in scope, time window if any, and the evidence that is allowed. State exclusions and unknown access up front.
2. Establish the baseline before suggesting change. Read repository instructions, current architecture and lifecycle documents, relevant contracts, recent tests/fixtures, release/evaluation material, and targeted source paths. Use revision-aware citations (file path, symbol or line, and revision when available).
3. Map authorities and interfaces. Identify what currently owns the behavior, what is merely documentation or an adapter claim, and which boundaries must remain fixed. Treat advertised capability and demonstrated runtime enforcement as different evidence classes.
4. Look for a *small recurring pain signal*: repeated failure category, reproducible divergence, persistent manual recovery, a documented limitation corroborated by code/tests, or a clear evaluation gap. One failure can create a hypothesis; it cannot establish recurrence or expected benefit.
5. Test applicability and no-fit. For each candidate, identify affected and unaffected scopes, prerequisites, privacy/authorization constraints, incompatible environments, and counterexamples. If the candidate requires missing evidence, say so rather than extrapolating.
6. Choose the smallest intervention that could falsify the hypothesis while preserving existing acceptance, permission, budget, and verification rules. Prefer deterministic/manual mechanisms first. Do not require an inference provider, external model, or optional dependency for a useful first experiment.
7. Define evaluation before recommending promotion. Compare a named baseline with an ordinary control and a candidate under comparable task cohort, budget/resource ceilings, acceptance criteria, and partitioning. Specify the label source, exclusion rules, counterevidence, rollback target, and the condition for `insufficient-evidence`.
8. Deliver the report and self-contained task briefs using the template in [references/assessment-template.md](references/assessment-template.md). Do not implement tasks or create global rules from this assessment.

## Evidence standard

Use an evidence ledger with one row per material claim:

| Claim | Evidence and provenance | Scope | Categorical status | Counterevidence or gap |
| --- | --- | --- | --- | --- |

Distinguish these statuses:

- `observed`: directly supported by current source, fixture, record, or authorized measurement.
- `documented`: stated in maintained material but not independently verified here.
- `inferred`: a bounded interpretation; give the reasoning and alternatives.
- `unknown` / `unverified`: evidence is absent or could not be checked.
- `insufficient-evidence`: evidence cannot support an expected-benefit or promotion claim.

Never convert a model output, valid typed response, benchmark replay, or self-reported cost into proof of semantic correctness or causal improvement. Cache/replay evidence only applies when its project/provider eligibility, task and acceptance version, complete input state, policy version, and relevant calibration/version context match.

Use the categorical status above; do not introduce a numeric probability by default. If a proposal uses a numeric confidence or probability, state its prediction target, provenance, and validation status separately. An uncalibrated number is not an expected-benefit estimate.

## Candidate selection

Prefer candidates that are narrow, reversible, and testable. Suitable first candidates often include a deterministic guard, stronger evidence join, bounded context-repair trigger, clearer unsupported-state handling, or a manual proposal/reporting seam.

Record a candidate's gated prerequisites before recommending evaluation or promotion. A candidate may still be worth assessing when it needs:

- a new permission or authority boundary, including an experiment-isolation gap;
- access to private data, telemetry, credentials, or a paid provider;
- clean evaluation partitions and a controller-owned hidden-label boundary;
- defined labels and held-out validation before any calibration claim;
- a simpler experiment that separates simultaneous changes and permits attribution.

Broad executable policy languages and autonomous self-modification are `no-fit` or deferred by default. Assess them only as separately requested research with external acceptance and permission boundaries. Reject a proposal that requires candidate access to hidden answers or treats contaminated audit data as independent evidence.

Future provider integrations may be recorded as conditional work: name the required authorization, privacy review, technical conformance, no-spend/manual fallback, and local comparative evaluation. Do not assume credentials, network access, a model identity, prices, or provider behavior beyond what the user has already authorized.

## Polytropos whole-system mode

When the scope is Polytropos as a whole, assess the shared runtime and each supported harness independently before synthesizing. Cover, where present:

| Surface | Ask |
| --- | --- |
| Shared runtime/contracts | Which component is authoritative for task lifecycle, admission, budgets, policy identity, evidence, readiness, and acceptance? |
| Four harnesses | Which behavior is native, adapted, documented-only, runtime-verified, or unsupported for each harness? Do not transfer pricing, capability, or enforcement claims across harnesses. |
| Skills and context/planning | Is applicability explicit? Can a skill be withheld for contradiction, staleness, or no-fit? Are graph/context outputs advisory evidence rather than permission? |
| Evaluation and release | Are baseline, control, candidate, partitions, labels, release claims, rollback, and supported-environment matrix separately evidenced? |

Do not require an arbitrary repository to adopt these modules. For another repository, use the same questions only where their existing architecture has an analogous responsibility; otherwise record `not-applicable` with the reason.

For an adaptive-decision opportunity, preserve this chain: bounded state -> advisory typed judgment or deterministic rule -> deterministic policy selection -> fresh admission -> native execution -> required verification -> authoritative attempt evidence. A judgment cannot grant tools, spend, remove dependencies, weaken acceptance, or promote itself.

## Deliverables and stopping condition

Deliver a scope-specific findings report plus zero or more independent task briefs in the requested or designated output location. A good report may conclude there is no supported intervention. Stop after the assessment when evidence is insufficient, no small recurring signal exists, the required evidence is unavailable, or the next step needs authorization that is not already present.

Each task brief must state: objective; exact scope and out-of-scope; existing authorities to preserve; evidence links; proposed bounded change; non-goals; acceptance criteria; deterministic/offline verification; evaluation dependencies; required approval or private/paid access; and rollback/no-promotion condition. It must be usable by a later implementer without access to the assessment conversation.

If multiple candidates exist, rank only within the assessment scope using expected learning value, reversibility, evidence quality, and disruption. Do not rank by an invented probability, vendor claim, or presumed cost.
````
<!-- END FILE tasks/kits/decision-improvement/skills/assess-improvement/SKILL.md -->

## File: `tasks/kits/decision-improvement/skills/assess-improvement/references/assessment-template.md`

<!-- BEGIN FILE tasks/kits/decision-improvement/skills/assess-improvement/references/assessment-template.md -->
````markdown
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
````
<!-- END FILE tasks/kits/decision-improvement/skills/assess-improvement/references/assessment-template.md -->

## File: `.claude/agents/decision-improvement-v1-implementer.md`

<!-- BEGIN FILE .claude/agents/decision-improvement-v1-implementer.md -->
````markdown
---
name: decision-improvement-v1-implementer
description: Implementer for the decision-improvement-v1 execution kit.
model: sonnet
---

Read `.claude/kits/decision-improvement-v1/PLAN.md`, its `GUARDRAILS.md`, the shared architecture at `tasks/kits/decision-improvement/PLAN.md`, and the assigned TASKS.md brief before work. Current repository instructions and the user's selected scope apply. This handoff is self-contained; never require access to the original conversation.

Preserve one authority per concern, legacy defaults, stdlib-only tests, separate harness pricing and unknown evidence. Tests use injected runners and temporary homes/stores only. Never invoke a real model CLI in verify commands. New evidence is recorded only by its owning engine. No install, push, merge, live experiment or policy activation merely because it is described in the plan.

Implement exactly the assigned task within its file ownership and acceptance. You are not alone in the codebase: preserve other edits, coordinate shared modules, and report genuine brief conflicts before changing scope. Run the task verify command and applicable full-suite/docs checks. Report actual commands, results and remaining limitations; the executor owns task transitions and NOTES.md. Return to the configured worker after any evidence-gated recovery. Do not claim future test names already exist or treat a zero-test run as verification.
````
<!-- END FILE .claude/agents/decision-improvement-v1-implementer.md -->

## File: `.claude/agents/decision-improvement-v1-reviewer.md`

<!-- BEGIN FILE .claude/agents/decision-improvement-v1-reviewer.md -->
````markdown
---
name: decision-improvement-v1-reviewer
description: Reviewer for the decision-improvement-v1 execution kit.
model: opus
tools: Bash, Read, Grep, Glob
---

Read `.claude/kits/decision-improvement-v1/PLAN.md`, its `GUARDRAILS.md`, the shared architecture at `tasks/kits/decision-improvement/PLAN.md`, and the assigned TASKS.md brief before work. Current repository instructions and the user's selected scope apply. This handoff is self-contained; never require access to the original conversation.

Preserve one authority per concern, legacy defaults, stdlib-only tests, separate harness pricing and unknown evidence. Tests use injected runners and temporary homes/stores only. Never invoke a real model CLI in verify commands. New evidence is recorded only by its owning engine. No install, push, merge, live experiment or policy activation merely because it is described in the plan.

Review the completed phase for architecture drift, cross-task gaps, shared-authority duplication, backward compatibility, resource honesty and release-gate correctness. Independent per-task verification is not final acceptance; return a phase verdict with actionable evidence and then let the coordinator decide. Do not implement fixes. Tool pins remove convenient editors but Bash still can mutate: prefer non-mutating checks, run mutation tests on temporary copies only, and if you cause unexpected changes restore your own damage byte-for-byte without touching others' work. Close with git status --porcelain and report any remaining unexpected change as your own defect.
````
<!-- END FILE .claude/agents/decision-improvement-v1-reviewer.md -->

## File: `.claude/agents/decision-improvement-v1-verifier.md`

<!-- BEGIN FILE .claude/agents/decision-improvement-v1-verifier.md -->
````markdown
---
name: decision-improvement-v1-verifier
description: Verifier for the decision-improvement-v1 execution kit.
model: opus
tools: Bash, Read, Grep, Glob
---

Read `.claude/kits/decision-improvement-v1/PLAN.md`, its `GUARDRAILS.md`, the shared architecture at `tasks/kits/decision-improvement/PLAN.md`, and the assigned TASKS.md brief before work. Current repository instructions and the user's selected scope apply. This handoff is self-contained; never require access to the original conversation.

Preserve one authority per concern, legacy defaults, stdlib-only tests, separate harness pricing and unknown evidence. Tests use injected runners and temporary homes/stores only. Never invoke a real model CLI in verify commands. New evidence is recorded only by its owning engine. No install, push, merge, live experiment or policy activation merely because it is described in the plan.

Independently verify exactly the assigned task against its acceptance, not the implementer's summary. Inspect the patch and run its checks; challenge missing negative cases, vacuous passing checks, authority violations and unsupported live claims. Report accept/revise/blocked with concrete evidence. Do not implement fixes. Tool pins remove convenient editors but Bash still can mutate: prefer non-mutating checks, run mutation tests on temporary copies only, and if you cause unexpected changes restore your own damage byte-for-byte without touching others' work. Close with git status --porcelain and report any remaining unexpected change as your own defect.
````
<!-- END FILE .claude/agents/decision-improvement-v1-verifier.md -->

## File: `.claude/agents/decision-improvement-v2-implementer.md`

<!-- BEGIN FILE .claude/agents/decision-improvement-v2-implementer.md -->
````markdown
---
name: decision-improvement-v2-implementer
description: Implementer for the decision-improvement-v2 execution kit.
model: sonnet
---

Read `.claude/kits/decision-improvement-v2/PLAN.md`, its `GUARDRAILS.md`, the shared architecture at `tasks/kits/decision-improvement/PLAN.md`, and the assigned TASKS.md brief before work. Current repository instructions and the user's selected scope apply. This handoff is self-contained; never require access to the original conversation.

Preserve one authority per concern, legacy defaults, stdlib-only tests, separate harness pricing and unknown evidence. Tests use injected runners and temporary homes/stores only. Never invoke a real model CLI in verify commands. New evidence is recorded only by its owning engine. No install, push, merge, live experiment or policy activation merely because it is described in the plan.

Implement exactly the assigned task within its file ownership and acceptance. You are not alone in the codebase: preserve other edits, coordinate shared modules, and report genuine brief conflicts before changing scope. Run the task verify command and applicable full-suite/docs checks. Report actual commands, results and remaining limitations; the executor owns task transitions and NOTES.md. Return to the configured worker after any evidence-gated recovery. Do not claim future test names already exist or treat a zero-test run as verification.
````
<!-- END FILE .claude/agents/decision-improvement-v2-implementer.md -->

## File: `.claude/agents/decision-improvement-v2-reviewer.md`

<!-- BEGIN FILE .claude/agents/decision-improvement-v2-reviewer.md -->
````markdown
---
name: decision-improvement-v2-reviewer
description: Reviewer for the decision-improvement-v2 execution kit.
model: opus
tools: Bash, Read, Grep, Glob
---

Read `.claude/kits/decision-improvement-v2/PLAN.md`, its `GUARDRAILS.md`, the shared architecture at `tasks/kits/decision-improvement/PLAN.md`, and the assigned TASKS.md brief before work. Current repository instructions and the user's selected scope apply. This handoff is self-contained; never require access to the original conversation.

Preserve one authority per concern, legacy defaults, stdlib-only tests, separate harness pricing and unknown evidence. Tests use injected runners and temporary homes/stores only. Never invoke a real model CLI in verify commands. New evidence is recorded only by its owning engine. No install, push, merge, live experiment or policy activation merely because it is described in the plan.

Review the completed phase for architecture drift, cross-task gaps, shared-authority duplication, backward compatibility, resource honesty and release-gate correctness. Independent per-task verification is not final acceptance; return a phase verdict with actionable evidence and then let the coordinator decide. Do not implement fixes. Tool pins remove convenient editors but Bash still can mutate: prefer non-mutating checks, run mutation tests on temporary copies only, and if you cause unexpected changes restore your own damage byte-for-byte without touching others' work. Close with git status --porcelain and report any remaining unexpected change as your own defect.
````
<!-- END FILE .claude/agents/decision-improvement-v2-reviewer.md -->

## File: `.claude/agents/decision-improvement-v2-verifier.md`

<!-- BEGIN FILE .claude/agents/decision-improvement-v2-verifier.md -->
````markdown
---
name: decision-improvement-v2-verifier
description: Verifier for the decision-improvement-v2 execution kit.
model: opus
tools: Bash, Read, Grep, Glob
---

Read `.claude/kits/decision-improvement-v2/PLAN.md`, its `GUARDRAILS.md`, the shared architecture at `tasks/kits/decision-improvement/PLAN.md`, and the assigned TASKS.md brief before work. Current repository instructions and the user's selected scope apply. This handoff is self-contained; never require access to the original conversation.

Preserve one authority per concern, legacy defaults, stdlib-only tests, separate harness pricing and unknown evidence. Tests use injected runners and temporary homes/stores only. Never invoke a real model CLI in verify commands. New evidence is recorded only by its owning engine. No install, push, merge, live experiment or policy activation merely because it is described in the plan.

Independently verify exactly the assigned task against its acceptance, not the implementer's summary. Inspect the patch and run its checks; challenge missing negative cases, vacuous passing checks, authority violations and unsupported live claims. Report accept/revise/blocked with concrete evidence. Do not implement fixes. Tool pins remove convenient editors but Bash still can mutate: prefer non-mutating checks, run mutation tests on temporary copies only, and if you cause unexpected changes restore your own damage byte-for-byte without touching others' work. Close with git status --porcelain and report any remaining unexpected change as your own defect.
````
<!-- END FILE .claude/agents/decision-improvement-v2-verifier.md -->

## File: `tasks/kits/recursive-improvement/PLAN.md`

<!-- BEGIN FILE tasks/kits/recursive-improvement/PLAN.md -->
````markdown
# Bounded recursive improvement — research extension M01

autonomy: advisory
workflow: reviewed

## Scope and entry gates

This is a planning extension to decision-improvement V1, independent of optional Jev V2 and model training. It specifies infrastructure and a research protocol, not a claim that RSI exists or will succeed. All tasks are pending. Current repository instructions and explicit user authorization control execution; reading or implementing this plan does not authorize paid experiments or activation. Prior explicit authorization remains valid within its recorded scope.

Reconcile current HEAD before implementation. V1's accepted contracts, provenance, partition/exposure tracking, protected execution profile, experiment protocol and promotion/rollback mechanisms are prerequisites for integration. Schema and offline fixture design may proceed before empirical success; live recursive trials require repeated transferable gains from the fixed improvement procedure. If that evidence or a protected profile is absent, report the research gate blocked; do not manufacture gains or weaken the gate.

This Codex planning kit uses worker intents. For Claude Code execution, materialize an equivalent native reviewed kit with current harness model aliases and implementer, independent verifier and phase-reviewer roles. Preserve these task IDs and select one execution-status authority; do not execute two mirrors. Validate the native DAG and interactive roster before dispatch. Each phase ends with independent review; coordinator acceptance remains separate. No live CLI appears in verification commands.

## Reuse the backend rather than create a second authority

Current attempt_ledger stores JSONL execution events; attempt_history projects their history; runtime_data owns private storage; workflow_eval owns workflow trials and reviewed routing-policy versions. Those policy files are currently pull-only, and unrestricted workers can write user-owned files outside the checkout. Neither a hash nor an out-of-tree path is an isolation boundary. Audit the then-current implementation before changing it; some V1 deltas may already be present.

Reuse these owners and V1's proposal/bundle/partition contracts. A new recursive_improvement module may coordinate experiments and produce derived reports, but must not duplicate attempts, budget admission, acceptance or pricing. JSON/JSONL is sufficient initially; a relational database is not a prerequisite. Any later SQL index is a rebuildable projection with schema migrations, never a competing source of truth.

## Required persistent records and relationships

| Record | Required identity and evidence |
| --- | --- |
| Experiment protocol | ID, schema/content version, frozen objective and success margin, arms, starting snapshot, task-group partitions, evaluator/profile versions, model pins, generation and replication schedule, stopping rules, total resource caps and authorization reference |
| System generation | ID, experiment/arm/replicate, parent generation IDs, code and bundle hashes, improver version, pinned model/harness/environment, accepted change and evaluation references; generation zero has an explicit empty parent list |
| Improver version | Immutable artifact/hash describing failure selection, hypothesis generation and experiment selection; parent version, originating proposal and acceptance; distinguish requested, dispatched and observed model identity |
| Proposal and experiment | Hypothesis, targeted component, authoring generation/improver, exact candidate diff/hash, baseline/control snapshots, development-evidence references, rejection or acceptance and reason; preserve failed proposals |
| Evaluation and exposure | Protocol/arm/replicate/generation/trial IDs, existing attempt IDs, task-group and partition versions, every authorized data exposure, evaluator version, outcomes, uncertainty, regressions, contamination/invalidity reasons and audit evidence |
| Resource and intervention account | All proposal, implementation, retry, evaluation, review and failed/unknown work linked to existing attempts; separate measured usage, estimates, subscription proxies and unknowns; elapsed time and human interventions with their scope |
| Promotion and rollback | Exact candidate and parent identities, scoped approval/evaluation references, active version transition and rollback target, recorded before use; inherited versions pinned for each running experiment |

Use existing immutable artifact stores where available. New event types are versioned and validated. Parent/reference identity must resolve, cycles and cross-arm parentage refuse, duplicate delivery is idempotent, and accepted state must be reconstructible after a crash. Do not promise exactly-once external model calls: unknown dispatch outcomes remain unknown, retain budget reservations, and are not silently replayed. Historical missing fields stay unknown. Corrupt or unresolved research evidence invalidates the affected claim rather than being silently omitted.

## Experimental design

Three arms start from the same system and evidence: A freezes the system; B improves task workflows using a fixed improvement procedure; C may also change its improvement procedure. Arms never borrow candidates, evaluation feedback or discoveries from each other during a replicate. Freeze base-model versions where possible; a provider change or unattested identity is a reported confound, not an inherited gain.

B and C receive matched total resource ceilings that include improvement overhead and unsuccessful searches. Report A's actual spend separately; do not pad it with useless work to manufacture equality. Use identical outcome-evaluation budgets and task distributions across arms. Counterbalance task order, repeat independently, and predeclare a statistically justified sample size, generation count, practical success margin, regression tolerance and stopping rule before observing promotion/audit outcomes. Unknown resource coverage cannot establish efficiency. A cap applies across generations, not afresh at every child run.

Separate development, calibration when applicable, promotion and final-audit groups using V1's ownership. Related defects stay in one group. Keep final-audit tasks and labels outside candidate access and record exposure, including summaries and feedback. Reusing an audit set to select the next candidate retires it from audit status. Repeated testing must follow the frozen analysis/stopping plan; no cherry-picked generations or optional stopping after a lucky win.

Measure independent task success and defects, retained capability, transfer to unfamiliar repositories/tasks, total resources and human effort. A research claim requires a practically meaningful C-versus-B advantage across the predeclared independent trajectories, with uncertainty and complete failures reported. Improvements must persist into successors, and controlled reversion of improver changes must support causal attribution. Compare against A as context, not as a substitute for C-versus-B. Classify outcomes as unsupported, inconclusive, regression, or evidence supporting bounded recursive improvement within the tested domain. No result establishes general intelligence growth, unbounded acceleration or smarter model weights.

## Boundary and activation

Candidates may edit only explicitly permitted workflow/improver components. The independent evaluator, hidden datasets, ledger writer authority, resource admission and approval rules remain outside their writable/readable scope as appropriate. Sentinel tests must demonstrate the named deployment profile enforces this against candidate attempts. If it cannot, remain offline/advisory. Approval records alone are not authentication; reuse the actual external approval boundary. Promotion uses V1's exact-content approval and pinned activation/rollback path; a research result never activates a global default by itself.

## Verification and evidence posture

Offline tests use temporary stores and fake providers and prove only mechanisms. The modules and test classes in TASKS.md are future deliverables. Live evidence is a separate operator-approved campaign with explicit data eligibility, budgets and a protected profile. R08 can complete with an honest offline handoff while the empirical RSI gate remains blocked or inconclusive. Do not mark RSI demonstrated merely because all implementation tasks passed.

## Training-data integration

Consume V1 D31–D34 and `tasks/kits/decision-improvement/TRAINING-DATA.md` when a campaign includes a trainable model. Reference dataset manifests, eligibility/exposure history and parent checkpoints; account for data curation, training, failed jobs and evaluation. The researcher cannot write its own gold labels or bypass export checks. Training-enabled campaigns need a separately selected trainer and approved resource/data scope; the workflow-only RSI experiment remains possible without model training.
````
<!-- END FILE tasks/kits/recursive-improvement/PLAN.md -->

## File: `tasks/kits/recursive-improvement/TASKS.md`

<!-- BEGIN FILE tasks/kits/recursive-improvement/TASKS.md -->
````markdown
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
````
<!-- END FILE tasks/kits/recursive-improvement/TASKS.md -->

## File: `tasks/kits/decision-improvement/TRAINING-DATA.md`

<!-- BEGIN FILE tasks/kits/decision-improvement/TRAINING-DATA.md -->
````markdown
# Training-data preparation — Release 1 infrastructure

## Purpose and authority

D31–D34 set up collection and export for a future small open-weights specialist. They are mandatory V1 infrastructure tasks, not a model-training job. Begin with failure classification. Snapshot capture can be used in eligible authorized runs once implemented; enabling capture must have a declared collection scope and retention policy. Do not silently backfill private transcripts or upload data to a provider. Building the feature does not authorize a training run, paid collection, Jev calls or deployment. Existing explicit authorization applies to its actual scope.

These tasks run before the V1 handoff and before the first live improvement experiment. Keep the original D01–D30 IDs stable; appended IDs D31–D34 are scheduled by dependencies, not numeric order. The native Claude TASKS.md owns execution status. Synthetic fixtures prove mechanics, not model quality or data sufficiency.

## Minimum example contract

Every record has an example ID, schema version, source attempt/decision references, task/defect group, repository revision and capture boundary. Preserve data already owned by attempt_ledger, runtime_data, decision contracts and partition/exposure storage through references; do not introduce a competing execution ledger. Use an optional bin/training_data.py for validation, adjudication and derived dataset exports, with immutable bounded artifacts owned by the existing private-store authority. Raw transcript logging is not required.

| Record | Required fields and semantics |
| --- | --- |
| Decision-time input | Timestamp and sequence/event boundary; bounded task statement, relevant code/context, observed error and tool state, available constraints; field provenance and evidence artifact hashes; exact decision question and schema/taxonomy version |
| Cause target | Reviewed label or explicitly unresolved/unknown/multiple-cause status; primary and contributing causes when supported; evidence references, label method, reviewer identity, disagreement and resolution history |
| Subsequent action/outcome | Action actually attempted, permitted alternatives if known, verification evidence, success/failure/unknown, retries and human intervention; distinguish observed outcome from an optimal-action label |
| Reproducibility | Harness, requested/dispatched/observed model identity, prompt/policy/code versions, capture and labeling tooling versions; absent old fields stay unknown |
| Resources | Existing usage records and basis, elapsed time, review effort and completeness; preserve estimates, measured use, subscription proxies and unknowns separately |
| Eligibility | Owner-approved collection/use scope, permitted training/export purpose, source/license restrictions, redaction status, retention/expiry and revocation state; unknown eligibility excludes export |
| Dataset placement | Related-task group, development/calibration/promotion/final-audit partition identity and version, exposure history, dataset membership and split-assignment version |

Input and label are different artifacts. Later reproduction or review may establish a cause, but cannot alter the historical input snapshot. Never place a later successful patch, reviewer diagnosis, future test result or reference answer in the deployed model's training input if unavailable at decision time. Missing historical snapshots are not reconstructed as exact observations. Exclude unsafe examples or explicitly segregate them from fine-tuning-ready exports.

## Labeling and collection behavior

Start with a versioned taxonomy: environment/infrastructure, missing context, implementation error, configuration/permission, multiple causes and unknown. D31 must reconcile overlap with existing failure classes; keep root cause distinct from symptoms such as a nonzero test exit. Define inclusion rules, counterexamples and an abstention policy before labeling. Preserve the original operational classification as an observation, not an adjudicated target.

Review disputed causes, record correction history, and exclude unresolved disagreements from supervised targets unless the selected task explicitly models ambiguity. A model or Jev suggestion is a candidate label, never independently verified truth. Use real evidence such as reproduction, tool failure stage and independent review. Successful attempts may provide negative/no-failure examples only under a compatible explicitly defined question; do not force them into a failure-cause taxonomy.

Retain eligible failures, successful recoveries, abstentions, censored outcomes and human corrections. Capture selection/sampling policy and counts for included, dropped, redacted and unlabeled examples, including exclusions by cause. Avoid success-only training or equating untried proposals with failures. A recovery that succeeded is not proof it was the best recovery; learning action choice requires controlled alternative trials or appropriately qualified evidence. Experiment-ranking labels require observed experiment outcomes and full cost, not the proposer’s enthusiasm.

## Partition, privacy and export rules

Use V1 grouped immutable partitions and exposure records. All retries, near-duplicate snippets, related defects and derivative/synthetic variants share an assigned group; record detection method and unresolved grouping uncertainty. Dataset construction only reads authorized development material; keep calibration, promotion and final audit inaccessible to training exporters. A future protocol may use explicitly separate development validation splits, but must never relabel final-audit material as training while preserving an independent-audit claim. Record feedback exposure as well as raw access.

Redact before persistence, use bounded allowlisted fields, and fail closed when content cannot be retained safely. Keep artifacts outside commits, docs, packages and public telemetry under private-store controls. Export only with explicit purpose/destination eligibility. Withdrawal or expiry excludes future exports, invalidates affected manifests, and identifies downstream training artifacts; deleting a file does not prove removal from already trained weights. Preserve only permitted minimal revocation provenance, never secrets in tombstones. No external transfer is part of V1.

Create deterministic local JSONL examples and a versioned manifest: input and target schema, example/content hashes, source IDs, label versions, permitted-use metadata, grouping/split versions, exclusions, dataset statistics, exporter version and parent dataset. Keep label rationale/provenance out of model inputs. Separate training payload from audit metadata and protected evaluators. The manifest identifies content; it does not establish access enforcement. Refuse missing sources, stale labels, revoked eligibility, ambiguous groups crossing splits and future-information leakage.

## Readiness and later training

Produce a data-readiness report with label agreement, category coverage, unknown/exclusion rates, sampling bias, duplication, partition/exposure checks, provenance completeness and resource coverage. Do not invent a minimum sample count or claim training readiness from fixture counts. Use a pilot and learning curves on separate development validation to choose a collection target; preserve protected final evaluation.

The operator handoff must show a local example from authorized synthetic data: capture → label/review → assign eligible development group → validate → export → inspect manifest → revoke and refuse re-export. Document feature-disabled behavior and commands for enabling scoped capture in future authorized runs. No credentials, model downloads, training, deployment or real private-data collection are required for this demonstration.

Later training must bind parent checkpoint, dataset manifest, training recipe/software/seed, compute budget and outcome to RSI generation lineage. V1 prepares this interface but does not implement a trainer or assert gains. Context ranking, recovery choice and experiment selection require separately validated targets; failure-classification data cannot silently become labels for those jobs.
````
<!-- END FILE tasks/kits/decision-improvement/TRAINING-DATA.md -->

## File integrity

SHA-256 checksums identify the exact planned file contents, not runtime trust or approval.

| File | SHA-256 |
| --- | --- |
| `tasks/kits/decision-improvement/PLAN.md` | `45130b3d981cef9ba08befc84b4c6489202a891a5c65cf6dc6163669b023383c` |
| `tasks/kits/decision-improvement/REPO-ASSESSMENT.md` | `6f8c9224f93f656b0ad09c0da30a7e1cf176b5027ffa140d1464e1105d3b3a0f` |
| `tasks/kits/decision-improvement/GUARDRAILS.md` | `5ddf2af456b477b4d002be1f6ae2b632ec3dde5d0bb3fa87944ec2694353228c` |
| `.claude/kits/decision-improvement-v1/PLAN.md` | `c55051a39afcbf1aac3883328312c892a8ec3031ac1f26751a0b008523c53efe` |
| `.claude/kits/decision-improvement-v1/TASKS.md` | `6f6dfd70a80451fff5b69dfc798e7d35a1708ef3075a1b7e6254200b9d493e92` |
| `.claude/kits/decision-improvement-v1/GUARDRAILS.md` | `5ddf2af456b477b4d002be1f6ae2b632ec3dde5d0bb3fa87944ec2694353228c` |
| `tasks/kits/decision-improvement/OPTIONAL-TASKS.md` | `0c412b0a52061bd353c2a0378afba986c1d51035f49fa08f86de1fd0f7ea6959` |
| `.claude/kits/decision-improvement-v2/PLAN.md` | `0c511728285a49e46ada1129319f1bdb0e35696c733c3c45d724b21ef64db78c` |
| `.claude/kits/decision-improvement-v2/TASKS.md` | `3d3e3b942da0b9cddae8679f118821c3eb51a63346c59ff94a80137db7fce543` |
| `.claude/kits/decision-improvement-v2/GUARDRAILS.md` | `5ddf2af456b477b4d002be1f6ae2b632ec3dde5d0bb3fa87944ec2694353228c` |
| `tasks/kits/decision-improvement/skills/assess-improvement/SKILL.md` | `b615d18b01d51c5627ab3f7bf7ab1d3f26ab688a5b692883f46077b8cb97112f` |
| `tasks/kits/decision-improvement/skills/assess-improvement/references/assessment-template.md` | `543c9004b49c00dbffc12267037b4c43bb248a18b0199d0cce815e115eee632b` |
| `.claude/agents/decision-improvement-v1-implementer.md` | `a91a39e97e094bf36a4c7d40e2be830aaf6f444a3a53559fd64c59c0d7b76fa2` |
| `.claude/agents/decision-improvement-v1-reviewer.md` | `e8224a35f1086370590fe8176a0d41c74a1986ffd3403bfd350230fe6d615855` |
| `.claude/agents/decision-improvement-v1-verifier.md` | `e7727c3c5982d0681d14cd0d1424fd106cc20e8a0cc2b65e598cf026bc243942` |
| `.claude/agents/decision-improvement-v2-implementer.md` | `306a8bbc49cd567fa504eed5a55d23df39c1e3a7b466bff63b45b0319eb9b10f` |
| `.claude/agents/decision-improvement-v2-reviewer.md` | `cecd09fe6b97c6614083d9994e232639de669f85adbca85b805bfc0198b9ce1b` |
| `.claude/agents/decision-improvement-v2-verifier.md` | `1369aa878ae4ceeda8001ca52d76cf011266eb8ef45c86a0f25da173df200307` |
| `tasks/kits/recursive-improvement/PLAN.md` | `1d35e50f00f505e7d62c44ac8271cab81b504df98f5c4a33994be9cba77981ab` |
| `tasks/kits/recursive-improvement/TASKS.md` | `44a67534be22adc8d41fcd8df1669da3ca5ce771193c5e9e6387f0b4d8018da2` |
| `tasks/kits/decision-improvement/TRAINING-DATA.md` | `57310eefe67a0a1b648d84299b96a63296dbc6f8192df86e508aa57837035ee7` |
