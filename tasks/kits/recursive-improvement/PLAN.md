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
