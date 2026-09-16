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
