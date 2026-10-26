# Guardrails, safety and hardening in polytropos

*polytropos · guardrails · safety · security hardening*

polytropos dispatches coding agents, runs the checks a kit names, and writes execution state. Running a kit's checks is intentional code execution, so its safety comes from naming exactly what is confined, what is gated, what is only recorded, and what is not a boundary at all. This page lists every guardrail, how each one is built, the test that proves it, and the stages where it acts. SECURITY.md is the policy; this page maps it.

This is the Markdown form of [docs/sdd/guardrails.html](guardrails.html), which draws the execution boundary as a diagram. The stage numbers are the ones on [docs/sdd/pipelines.html](pipelines.html).

- **Part 1:** [The posture](#the-posture)
- **Part 2:** [Every control, and how it is implemented](#every-control-and-how-it-is-implemented)
- **Part 3:** [Stage by stage](#stage-by-stage)
- **Part 4:** [What is not a boundary](#what-is-not-a-boundary)

---

**Part 1**

## The posture

Three ideas hold the rest together: the approval line follows reversibility, the tool is for repositories you control, and only one thing runs inside an OS boundary.

### Where the approval line sits

The line between what runs unasked and what waits for you is reversibility, not task size. Each lane is a code path, not a policy a model is asked to follow.

| Lane | Covers | What it means in code |
|---|---|---|
| Runs without asking | Reversible work | Reading, planning, checking and rehearsing. Every `demo`, `--demo` and `--dry-run` path is synthetic or spawns nothing; `harness_update.py check` and `preflight`, `exec_policy.py check` and the docs generators' `check` compare and write nothing. |
| Prepared, then gated on one named switch | Consequential actions | Spending needs `--live` with `--max-usd`. Writing a harness home goes only through `harness_select.py install` or `harness_update.py apply`, and overwriting what it does not own takes `--adopt-existing`. Leaving the OS boundary is `--exec-mode trusted-host`; restoring a reviewer's blanket grant is `--review-permissions bypass`. Each opt-out reports itself. |
| Never on the engine's own initiative | Irreversible actions | Nothing relocates a store. The one deletion, `runtime_data.py forget`, is a dry run unless given `--apply`. Installation never overwrites what it does not own, and `harness_update.py apply` prints the `~/.claude` remedy rather than running it. |

### Who it is for

polytropos is appropriate for repositories you control, run by the person who owns the machine. It is not an isolation boundary for unattended execution against untrusted repositories from a credential-rich host.

An outer sandbox — a container, a VM, a separate user account — is what limits host exposure today. polytropos does not provide one, and a kit is trusted input: its verify commands are code.

### The execution boundary

During a headless kit run, only the verify command runs inside the OS boundary. The model dispatch runs with your privileges, because the sandbox blocks the Keychain where subscription credentials live.

| Part of the run | Confined? | What it can reach |
|---|---|---|
| Kit driver (`bin/claude_execute.py` and its siblings) | No | Runs the check itself; records every dispatch before and after |
| Model dispatch (claude, copilot, codex, agent) | **No** | Your privileges, your network, its own provider's login; it edits the workspace tree |
| Verify command | **Yes**, under `sandbox-exec` | Reads and writes the workspace and a run scratch directory; network denied; credential stores unreadable; an allowlisted environment |
| Workspace tree (code, `TASKS.md`, `NOTES.md`) | — | The tree a worker edits |
| Attempt ledger and private stores | — | Outside the tree, `0700` / `0600`; out of a confined check's reach |

A headless kit driver's run on macOS. In the interactive loop the orchestrator runs each check through the session's own shell instead (Part 4).

### How to read the controls

Each control in Part 2 says what it stops, how it works, the code that implements it, the test classes that prove it, and the stages where it acts. Where a search of the suite found no test, the card says No test found. A red note marks a limit of the control itself.

---

**Part 2**

## Every control, and how it is implemented

Grouped by layer. The letter and number identify a control everywhere on this page.

### A · Standing rules, enforced by tests

Rules that hold for every change, written once and backed by tests that fail when one is broken.

#### A1 · Invariants that fail the suite

- **Stops:** a rule that lives only in prose and quietly erodes.
- **How:** `CLAUDE.md` lists the always-on invariants, and many of them are backed by tests that fail when one is broken. Each kit's `GUARDRAILS.md` adds fences for that change only.
- **Code:** `CLAUDE.md`, `.claude/kits/<slug>/GUARDRAILS.md`
- **Proved by:** `tests/test_privacy_layout.py` → `PrivacyLayoutTests`; `tests/test_pricing_refs.py` → `LiveTreeMirrorTests`; `tests/test_kit_contract.py` → `TripleImplementationTests`
- **Limit:** Not every invariant has a test; each card below names the tests behind its own rule.
- **Stages:** 1 Standing rules

#### A2 · One kit contract

- **Stops:** drivers drifting apart in how they parse, validate and count a kit.
- **How:** Task parsing, graph validation, readiness, status transitions, budget admission, run ids and the outcome vocabulary are defined once and re-exported by every driver.
- **Code:** `bin/kit_contract.py`
- **Proved by:** `tests/test_kit_contract.py` → `TripleImplementationTests`
- **Stages:** 1 Standing rules, 6 Tasks, 7 Analyze, 8 Implement

#### A3 · A stdlib-only runtime

- **Stops:** a third-party package entering the code that runs on your machine.
- **How:** `bin/` and `tests/` import only the Python standard library. The docs site's toolchain is the one exception, and it is hash-locked (I2).
- **Code:** `bin/`, `tests/`
- **Proved by:** `tests/test_primitives_adversarial.py` → `EngineHardConstraints`
- **Limit:** Only some modules carry their own stdlib-only check; no test scans the whole tree.
- **Stages:** 1 Standing rules, Release and CI

#### A4 · One pricing file per harness

- **Stops:** a price, ratio or model id typed into a skill and going stale.
- **How:** Prices live only in `data/pricing.json` and one sibling file per harness. The mirrors under the skills are generated by `bin/sync_pricing_refs.py`, never hand-edited.
- **Code:** `data/pricing.json`, `bin/sync_pricing_refs.py`
- **Proved by:** `tests/test_pricing_refs.py` → `LiveTreeMirrorTests`; `tests/test_docs_skill_dispositions.py` → `NoNewLiteralsTests`
- **Limit:** The literal ban covers a named set of skill files, not every skill.
- **Stages:** 1 Standing rules, 6 Tasks, 10 Feedback

#### A5 · Generated documentation is never hand-edited

- **Stops:** documentation that claims what its source no longer says.
- **How:** `bin/docs_build.py`, `bin/copilot_docs.py` and `bin/release_gate.py build` write their outputs, and each has a `check` that fails on drift.
- **Code:** `bin/docs_build.py`, `bin/copilot_docs.py`, `bin/release_gate.py`
- **Proved by:** `tests/test_release_gate.py` → `ReleaseDocTests`
- **Stages:** 1 Standing rules, Release and CI

#### A6 · Tests never call a real model CLI

- **Stops:** a test spending real credits or touching your live harness homes.
- **How:** Every dispatcher takes an injectable runner, tests use stubs and temporary homes, and `--dry-run` and `--demo` spawn nothing. No module in `bin/` starts a process except through `bin/proc_runner.py`.
- **Code:** `run_task(…, runner, verify_runner)` in each driver, `NO_REAL_CLI_TESTS` in `bin/release_gate.py`
- **Proved by:** `tests/test_proc_runner_wiring.py` → `OneRunnerTests`
- **Limit:** Nothing scans the tests for a real-CLI call; that part is a convention.
- **Stages:** 1 Standing rules, 9 Verify and converge

### B · Spec and plan gates

What the architect writes into a kit, and the rules the run must honor because the kit says so.

#### B1 · The approval pause

- **Stops:** a plan built on a spec nobody agreed to.
- **How:** The architect shows the spec draft and writes nothing to disk until you approve it.
- **Code:** `skills/architect/SKILL.md`, Step 1
- **Proved by:** `tests/test_architect_approval_pause.py` → `ArchitectApprovalPauseTests`
- **Stages:** 3 Specify, 4 Clarify

#### B2 · Kit fences, re-read at every phase start

- **Stops:** constraints that a long run or a compaction quietly dropped.
- **How:** `PLAN.md`'s out-of-scope section and the kit's `GUARDRAILS.md` bind every task. The execute loop re-reads both from disk before the first task of every phase.
- **Code:** `skills/execute/SKILL.md`
- **Proved by:** No test found.
- **Limit:** No test pins the re-read, and a compaction mid-phase is caught only at the next phase start.
- **Stages:** 3 Specify, 5 Plan, 8 Implement, 9 Verify and converge

#### B3 · The red-green evidence rule

- **Stops:** a check that proves nothing because it passed before the work began.
- **How:** Before a task's work starts, its check runs on the pre-task tree. A pass there is a `tautological-verify` defect and blocks the task. Tasks marked `regression` or `precondition` are expected to pass first.
- **Code:** `run_precheck` in `bin/kit_verify_hook.py`, `reconcile_task` in `bin/kit_contract.py`
- **Proved by:** `tests/test_kit_verify_hook.py` → `PrecheckTautologicalTests`; `tests/test_claude_execute.py` → `EndToEndTautologicalVerifyTests`
- **Stages:** 6 Tasks, 9 Verify and converge

#### B4 · The budget dial

- **Stops:** a run dispatching past what the plan allows.
- **How:** `PLAN.md`'s optional `budget:` line caps dispatches, escalations, consults and model calls. Usage is recounted from what is already recorded, and a reached cap stops the run without marking the task. A budget stop never overwrites a real verdict.
- **Code:** `budget_gate` and `parse_plan_budget` in `bin/kit_contract.py`
- **Proved by:** `tests/test_claude_execute.py` → `EndToEndPlanBudgetStopTests`; `tests/test_routing_scorecard.py` → `BudgetStopNeverSupersedesVerdictTests`
- **Stages:** 5 Plan, 8 Implement

#### B5 · Declared roles run, or the run stops

- **Stops:** a review step the kit asked for being skipped in silence.
- **How:** `roles:` and `workflow:` are parsed by one grammar. A role a driver cannot sequence stops the run unless `--roster-gap disclose` prints the gap and records it in the attempt ledger.
- **Code:** `ROLE_CONTRACTS` and `ROLE_SUPPORT` in `bin/kit_contract.py`
- **Proved by:** `tests/test_role_contract.py` → `RosterCheckTests`, `SupportTests`
- **Stages:** 5 Plan, 7 Analyze, 8 Implement

#### B6 · Re-routing is upgrade-only and advisory by default

- **Stops:** a run quietly moving work to a weaker model.
- **How:** A recommendation only ever moves a tier up. In the default advisory mode it is printed and recorded, and nothing changes until a person decides.
- **Code:** `skills/execute/references/rerouting.md`, `bin/routing_scorecard.py`
- **Proved by:** `tests/test_reroute_live.py` → `UpgradeDecisionTests`, `ParseAutonomyTests`
- **Stages:** 8 Implement

#### B7 · Routing policy is selected, never learned

- **Stops:** observations or model output changing which policy routes a task.
- **How:** A Codex task's policy comes only from a `--policy` flag or `PLAN.md`'s `routing:` line. Hard filters (availability, an explicit pin, an exclusion, effort support, the budget) apply before any preference is weighed.
- **Code:** `bin/routing_policy.py`
- **Proved by:** `tests/test_routing_policy.py` → `FiltersTests`
- **Stages:** 5 Plan, 8 Implement

### C · Checks before anything runs

The kit is checked before the first dispatch, without executing anything it contains.

#### C1 · The task graph is validated first

- **Stops:** a plan with a cycle, a duplicate id or a missing dependency running partway.
- **How:** `kit_contract.py graph` names every such defect with its fix and exits 2. A driver dispatches nothing on an invalid graph.
- **Code:** `validate_graph` in `bin/kit_contract.py`
- **Proved by:** `tests/test_kit_graph.py` → `ValidateGraphTests`, `ZeroDispatchOnInvalidGraphTests`
- **Stages:** 7 Analyze

#### C2 · analyze is static by construction

- **Stops:** a pre-run check that itself executes the kit's commands.
- **How:** `kit_contract.py analyze` checks the paths each brief names and whether each verify command can be resolved. It has no runner, so it cannot execute anything.
- **Code:** `analyze_kit` in `bin/kit_contract.py`
- **Proved by:** `tests/test_kit_analyze.py` → `StaticByConstructionTests`
- **Stages:** 7 Analyze

#### C3 · The spec review before dispatch

- **Stops:** contradictory acceptance or an uncovered goal reaching the implementers.
- **How:** In an interactive run, one opus reviewer reads the kit before the first dispatch and reports contradictions and goals no task covers.
- **Code:** `skills/execute/references/spec-review.md`
- **Proved by:** `tests/test_execute_preflight.py` → `PreDispatchStepTests`, `SpecReviewReferenceTests`
- **Limit:** Interactive only: headless drivers and `workflow: direct` kits print the analyze warnings, and nothing judges them.
- **Stages:** 7 Analyze

### D · The execution boundary

How processes, paths, credentials and dispatches are confined or recorded while a kit runs.

#### D1 · Verify commands run inside an OS sandbox

- **Stops:** a check writing outside the workspace, reaching the network or reading credentials.
- **How:** On macOS the kit drivers run each check under `sandbox-exec`: writes only to the workspace and a run scratch directory, network denied, credential stores unreadable, and the environment reduced to an allowlist. It refuses rather than falling back when no backend exists, and `--exec-mode trusted-host` is the named opt-out that reports itself.
- **Code:** `run_confined`, `verify_runner`, `_CONFIDENTIAL_HOME_PATHS` and `DEFAULT_ENV_ALLOWLIST` in `bin/exec_policy.py`
- **Proved by:** `tests/test_exec_policy.py` → `FailClosedTests`, `EnforcementTests`, `ProfileRenderingTests`; `tests/test_proc_runner_wiring.py` → `DriverVerifyWiringTests`
- **Limit:** The enforcement tests run only where a sandbox is available. Linux and Windows have no backend.
- **Stages:** 8 Implement, 9 Verify and converge, 11 Keep in sync

#### D2 · Every external process is bounded

- **Stops:** a hung or noisy process, or children that outlive the run.
- **How:** Each process gets a validated working directory, a wall-clock limit, an output ceiling that keeps draining, and a session of its own, so ending it ends its whole process group.
- **Code:** `run`, `validate_workdir` and `_terminate_tree` in `bin/proc_runner.py`
- **Proved by:** `tests/test_proc_runner.py` → `WorkdirTests`, `TimeoutAndTreeCleanupTests`, `OutputBoundTests`
- **Stages:** 2 Research, 8 Implement, 9 Verify and converge, 11 Keep in sync, Evaluation and benchmarks

#### D3 · A dispatch carries only its provider's credentials

- **Stops:** one provider's agent receiving another provider's keys.
- **How:** The environment handed to a harness CLI is a base set plus that provider's own variables.
- **Code:** `dispatch_env` and `PROVIDER_ENV_PREFIXES` in `bin/proc_runner.py`
- **Proved by:** `tests/test_proc_runner.py` → `DispatchEnvironmentTests`; `tests/test_proc_runner_wiring.py` → `DriverDispatchTests`
- **Stages:** 8 Implement, 9 Verify and converge

#### D4 · Paths are contained without a race

- **Stops:** a symlink swapped in mid-operation redirecting a write.
- **How:** Every store, marker and install destination is reached directory-relative with `O_NOFOLLOW`. Where the runtime lacks directory-relative operations, it refuses instead of using the racy form.
- **Code:** `_descend` and `_require_dir_fd` in `bin/safe_paths.py`
- **Proved by:** `tests/test_safe_paths.py` → `ContainmentTests`
- **Limit:** The refusal on a host without directory-relative operations has no test.
- **Stages:** 8 Implement, 10 Feedback, Install and update

#### D5 · Every dispatch is recorded before and after

- **Stops:** a crash losing track of what ran, or a dead attempt counted as a success.
- **How:** An append-only ledger outside the tree. An attempt with no result is closed as unknown, never as success, and never replayed; a task is claimed with `O_EXCL`; prior attempts count against the budget. A logged-out CLI or a missing binary stops the run instead of escalating.
- **Code:** `claim`, `record_started` and `reconcile_open` in `bin/attempt_ledger.py`
- **Proved by:** `tests/test_attempt_ledger.py` → `LedgerRecordTests`, `ClaimTests`, `CrashAfterDispatchTests`, `BudgetCarriesAcrossRunsTests`
- **Stages:** 8 Implement, 9 Verify and converge

#### D6 · Codex review and acceptance are read-only

- **Stops:** a reviewer changing the code it is reviewing.
- **How:** `bin/codex_execute.py` forces `--sandbox read-only` on review and acceptance, and refuses extra arguments that would override it or displace the selected model.
- **Code:** `cmd_review` and `cmd_accept` in `bin/codex_execute.py`
- **Proved by:** `tests/test_codex_execute.py` → `EndToEndRunHappyPathTests`
- **Limit:** The review path is tested; acceptance and the override refusal have no test.
- **Stages:** 9 Verify and converge

#### D7 · Cursor is identified before it is trusted

- **Stops:** dispatching to some other binary that happens to be named `agent`.
- **How:** `--version` or `about --format json` must identify Cursor before any claim, ledger entry or write. Review runs under `--mode ask`, and arguments that would change the mode, model, workspace or session are refused.
- **Code:** `require_cursor`, `READ_ONLY_MODE` and `BLOCKED_EXTRA_ARGS` in `bin/cursor_adapter.py`
- **Proved by:** `tests/test_cursor_adapter.py` → `IdentityTests`, `DispatchArgvTests`; `tests/test_cursor_execute.py` → `IdentityRefusalTests`
- **Stages:** 8 Implement, 9 Verify and converge

#### D8 · Reviewers get no blanket permission grant

- **Stops:** a review dispatch running with every tool pre-approved.
- **How:** Review carries no blanket grant by default. Claude turns the reviewer's declared tool pin into `--allowedTools`, and `--review-permissions bypass` is the named opt-out.
- **Code:** `role_permission_profile` and `allowed_tools_arg` in `bin/claude_execute.py`
- **Proved by:** `tests/test_claude_execute.py` → `RolePermissionTests`; `tests/test_copilot_execute.py` → `ReviewPermissionTests`
- **Limit:** A pin that includes Bash still reaches everything a shell reaches (see Part 4).
- **Stages:** 9 Verify and converge

#### D9 · Concurrent work cannot collide silently

- **Stops:** two workers' writes merging into a broken tree.
- **How:** Sequential by default. With `--max-parallel`, each task runs in its own copy outside the workspace, writes are measured rather than declared, a conflicting write applies nothing from that task, a worker that edits the kit is recorded as a violation, and the merged tree is verified again.
- **Code:** `DEFAULT_MAX_PARALLEL` and `snapshot_tree` in `bin/kit_scheduler.py`
- **Proved by:** `tests/test_kit_scheduler.py` → `SequentialDefaultTests`, `ConflictTests`, `MergedTreeTests`, `SecurityTests`
- **Stages:** 8 Implement, 9 Verify and converge

#### D10 · A code graph is read as untrusted evidence

- **Stops:** a crafted graph steering reads outside the repository or walking without bound.
- **How:** A graph's `source_file` must be relative and traversal-free; the graph has a byte ceiling; walks and searches are bounded; git is reached only with read-only verbs.
- **Code:** `MAX_GRAPH_BYTES` in `bin/graph_ground.py`
- **Proved by:** `tests/test_graph_ground.py` → `StampTests`, `FreshnessTests`, `ImpactTests`
- **Stages:** 2 Research

### E · Independent verification

Who decides a task is done. The builder never does.

#### E1 · The loop runs the check, not the builder

- **Stops:** an implementer grading its own work.
- **How:** The orchestrator runs each task's verify command itself. An implementer's claim of success is not evidence. A failure gets one retry with the failure output, then a frontier consult.
- **Code:** `skills/execute/SKILL.md`, the loop
- **Proved by:** No test found.
- **Limit:** This is a rule in the skill text the orchestrator follows; no test found pins it.
- **Stages:** 8 Implement, 9 Verify and converge

#### E2 · A fresh-context verifier, and optional adversaries

- **Stops:** review that is anchored on the builder's view.
- **How:** A verifier with none of the builder's context re-checks acceptance against the files. A kit can add a test-author, who writes tests from the brief alone, and a red-team, who tries to break the result.
- **Code:** `skills/execute/SKILL.md`, `skills/execute/references/roster.md`
- **Proved by:** No test found.
- **Limit:** The role vocabulary is tested (`tests/test_role_contract.py`), but no test found checks that the verifier is dispatched without the builder's context.
- **Stages:** 9 Verify and converge

#### E3 · Phase review against the plan

- **Stops:** a phase drifting from the plan before the next one starts.
- **How:** At each phase end an opus reviewer checks the phase against `PLAN.md`, and its findings are adjudicated and recorded before the run continues.
- **Code:** `skills/execute/SKILL.md`, phase boundaries
- **Proved by:** No test found.
- **Limit:** This is a rule in the skill text the orchestrator follows; no test found pins it.
- **Stages:** 9 Verify and converge

#### E4 · A rewritten brief is caught

- **Stops:** a worker editing its own brief, check or dependencies to make a task pass.
- **How:** The task block is re-read at projection time. A change is reported and recorded as `plan.drift`, and the verdict stays the one for the plan the run started with.
- **Code:** `plan_drift` in `bin/kit_contract.py`
- **Proved by:** `tests/test_kit_graph.py` → `PlanDriftTests`
- **Stages:** 8 Implement, 9 Verify and converge

### F · Honest records and claims

What the ledger, the release matrix and the cost figures may and may not say.

#### F1 · An acceptance is bound to its own run

- **Stops:** backfilling acceptances for work that was finished long ago.
- **How:** `kit_contract.py accept` refuses unless the task's latest passing outcome line carries the same `run=` id it was given, dated today or yesterday in UTC.
- **Code:** `accept_task` in `bin/kit_contract.py`
- **Proved by:** `tests/test_kit_evidence.py` → `AcceptRunGuardTests`
- **Stages:** 10 Feedback

#### F2 · drift reports, and writes nothing in the tree

- **Stops:** a later re-check silently failing or rewriting finished work.
- **How:** `kit_contract.py drift` re-runs a finished kit's checks inside the execution boundary and reports drift, not failure. It writes nothing in the tree or the kit directory; its events go to the ledger outside the tree.
- **Code:** `drift_kit` in `bin/kit_contract.py`
- **Proved by:** `tests/test_kit_evidence.py` → `DriftTests`, `DriftTestAuthorTests`
- **Limit:** The checks it runs may write, since the workspace is writable under the policy.
- **Stages:** 11 Keep in sync

#### F3 · Release claims are computed, never typed

- **Stops:** a release document claiming support the evidence does not show.
- **How:** The supported matrix in `docs/RELEASE.md` is rendered from the capability registry, the contract versions and the manifests. `check` fails on a drifted block, an unpinned workflow action, or a private store without its ignore rule.
- **Code:** `run_check` and `packaging_review` in `bin/release_gate.py`
- **Proved by:** `tests/test_release_gate.py` → `PackagingTests`, `ReleaseDocTests`
- **Stages:** Release and CI

#### F4 · Unknown means no

- **Stops:** a driver relying on a capability nobody has run.
- **How:** `primitives/harness-capabilities.json` records support, implementation and verification separately. A capability recorded as `unknown` counts as unsupported.
- **Code:** `UNKNOWN` and `supports` in `bin/harness_adapter.py`
- **Proved by:** `tests/test_kit_contract.py` → `CapabilityRegistryTests`
- **Stages:** 1 Standing rules, 8 Implement, Release and CI

#### F5 · A subscription run is never shown as a bill

- **Stops:** a ChatGPT-plan Codex run reported as dollars spent.
- **How:** Its dollar figure is a labelled relative-burn proxy: `billed_usd` stays null and the source stays unpriced, and proxy figures never enter a priced total.
- **Code:** `est_cost` in `bin/codex_pricing.py`, `bin/codex_usage.py`
- **Proved by:** `tests/test_codex_pricing.py` → `BurnIndexTests`; `tests/test_journal_sources.py` → `CodexAdapterTests`
- **Stages:** 10 Feedback

### G · Data and privacy

Where personal data lives, what is read, and what reaches a model.

#### G1 · Stores live outside the tree, private

- **Stops:** personal data landing in a distributed, synced or committed tree.
- **How:** Every store resolves to a per-user application-data directory, namespaced per checkout, created `0700` with `0600` files. An existing in-tree store keeps being used, and migration copies without deleting the original. The ignore rules are root-anchored.
- **Code:** `resolve_store`, `ensure_private` and `migrate` in `bin/runtime_data.py`
- **Proved by:** `tests/test_privacy_primitives.py` → `ResolutionTests`, `PrivateCreationTests`, `MigrationTests`; `tests/test_privacy_layout.py` → `PrivacyLayoutTests`
- **Stages:** 10 Feedback, Install and update

#### G2 · Harness homes are read read-only, from JSONL

- **Stops:** a usage report writing into your harness home or opening its database.
- **How:** The usage, journal and context readers read `~/.claude`, `~/.copilot` and `~/.codex` strictly read-only, and never open a SQLite file.
- **Code:** `bin/copilot_usage.py`, `bin/codex_usage.py`, `bin/journal_sources.py`
- **Proved by:** `tests/test_copilot_usage.py` → `ReadOnlyProofTests`; `tests/test_codex_usage.py` → `ReadOnlyProofTests`; `tests/test_journal_sources.py` → `CodexAdapterTests`
- **Limit:** These are behavior tests on fixtures; no test scans the readers' source.
- **Stages:** 10 Feedback

#### G3 · Free text is redacted before it is kept or sent

- **Stops:** a credential pasted into an inbox line reaching the digest or a model.
- **How:** Inbox lines pass through the redactor on the way into the journal and on the way to a model. What it caught is reported by kind and count, never by value.
- **Code:** `redact_all` and `describe` in `bin/redact.py`
- **Proved by:** `tests/test_journal_collect.py` → `InboxRedactionTests`; `tests/test_privacy_primitives.py` → `RedactionTests`
- **Limit:** Shape-matching only (see Part 4).
- **Stages:** 10 Feedback

#### G4 · Memory recall is pulled, capped and labelled

- **Stops:** a store being bulk-injected into a session, or a recalled fact read as an instruction.
- **How:** Recall returns a few relevant facts under a budget, with each one's source, scope and trust. A fact scoped to another project or provider is withheld.
- **Code:** `recall` and `apply_budget` in `bin/memory_recall.py`
- **Proved by:** `tests/test_memory_recall.py` → `BudgetTests`, `ProvenanceAndScopeTests`, `GateTests`
- **Limit:** That recall is pull-only, never injected, has no test of its own.
- **Stages:** 2 Research, 10 Feedback

#### G5 · The journal summary runs isolated

- **Stops:** the summarizing model reading the repo's instructions or writing files.
- **How:** The summary runs in an empty temporary directory with a reduced environment, and is rejected if anything was written there.
- **Code:** `default_runner` in `bin/journal_summarize.py`
- **Proved by:** `tests/test_journal_summarize.py` → `IsolatedSummaryDispatchTests`
- **Stages:** 10 Feedback

### H · Install, update and release

How polytropos writes into a harness home, and how a release is cut.

#### H1 · Installation never overwrites what it does not own

- **Stops:** an install replacing your own agent, skill or instructions file.
- **How:** Each destination is classified before a byte is written; creation uses `O_EXCL`; a managed refresh re-reads the file just before replacing it; rollback takes back only bytes this run wrote; `--adopt-existing` keeps the prior bytes.
- **Code:** `apply_copilot_plan` and `_rollback_written` in `bin/harness_select.py`
- **Proved by:** `tests/test_install_ownership.py` → `CopilotRollbackTests`, `CopilotAdoptionTests`, `CodexStalePlanTests`, `SafeCreateTests`
- **Stages:** Install and update

#### H2 · The freshness check only reads

- **Stops:** a status check that changes what it reports on.
- **How:** `harness_update.py check` compares and writes nothing. `apply` writes only the Copilot and Codex homes and the repo's generated mirrors, never `~/.claude`: that remedy is printed for you to run.
- **Code:** `cmd_check` in `bin/harness_update.py`
- **Proved by:** `tests/test_harness_update.py` → `ReadOnlyTests`, `ApplyNeverNamesTheClaudeHomeTests`
- **Stages:** Install and update

#### H3 · The install preflight

- **Stops:** installing from a dirty, unpushed or credential-bearing checkout.
- **How:** Eight gates: the source exists, the marketplace installs from it, git can read it, it is on `main`, clean, level with origin, carries nothing credential-shaped, and its version changed.
- **Code:** `PREFLIGHT_GATES` and `run_preflight` in `bin/harness_update.py`
- **Proved by:** `tests/test_harness_update.py` → `PreflightTests`
- **Stages:** Install and update

#### H4 · The version bump touches only the version

- **Stops:** a release step that edits or commits more than it says.
- **How:** `release_gate.py bump` edits only where the version is stated and what reports it, refuses while uncommitted work is present, and never commits.
- **Code:** `bin/release_gate.py` bump
- **Proved by:** `tests/test_release_gate.py` → `BumpPlanTests`
- **Stages:** Release and CI

### I · Build supply chain

The one non-stdlib toolchain, the docs site, is pinned rather than trusted.

#### I1 · Actions are pinned to commit SHAs

- **Stops:** a re-pointed or compromised tag changing what CI runs.
- **How:** Every GitHub Action is pinned to a full commit SHA, with its release in a trailing comment.
- **Code:** `.github/workflows/docs-site.yml`
- **Proved by:** `tests/test_docs_site_workflow.py` → `WorkflowBuildJobTests`; `tests/test_release_gate.py` → `PackagingTests`
- **Stages:** Release and CI

#### I2 · The docs toolchain is hash-locked

- **Stops:** a substituted package running inside the docs build.
- **How:** `docs-src/requirements.txt` pins every package, transitives included, with a sha256, and CI installs with `--require-hashes`.
- **Code:** `docs-src/requirements.txt`
- **Proved by:** `tests/test_docs_site_workflow.py` → `WorkflowBuildJobTests`
- **Stages:** Release and CI

#### I3 · Deploy credentials live only in the deploy job

- **Stops:** repository content running with the right to publish.
- **How:** The build job holds `contents: read` only. `pages: write` and `id-token: write` exist only in the deploy job, which runs no repository code.
- **Code:** `.github/workflows/docs-site.yml`
- **Proved by:** `tests/test_docs_site_workflow.py` → `WorkflowDeployJobTests`
- **Stages:** Release and CI

#### I4 · Generated links are scheme-checked

- **Stops:** an unsafe link hiding in generated documentation.
- **How:** Each URL's scheme is checked after rewriting against a small allowlist, and control characters are refused. An unsupported scheme fails the build.
- **Code:** `ALLOWED_URL_SCHEMES` and `safe_href` in `bin/copilot_docs.py`
- **Proved by:** `tests/test_copilot_docs_content.py` → `LinkSchemeTests`
- **Stages:** Release and CI

### J · Spend and evaluation

What can spend money, and what can change a routing default.

#### J1 · Benchmark spending is ceiling-gated

- **Stops:** a benchmark spending without a stated limit.
- **How:** No dispatch happens without `--live` and an explicit `--max-usd`, validated finite and non-negative on every check. `plan` and `demo` spend nothing.
- **Code:** `validate_ceiling` in `bin/repo_bench.py`
- **Proved by:** `tests/test_repo_bench.py` → `RunCliTests`
- **Stages:** Evaluation and benchmarks

#### J2 · Target repositories are read-only

- **Stops:** a benchmark changing the repository it measures, or leaking the answer.
- **How:** A target is reached only through a read-only git verb allowlist. Sandboxes are history-free tree extractions, and reference tests are never written into a candidate's tree.
- **Code:** `git_target` and `READ_ONLY_GIT` in `bin/repo_bench.py`
- **Proved by:** `tests/test_repo_bench.py` → `AllowlistTests`, `SandboxTests`
- **Stages:** Evaluation and benchmarks

#### J3 · A routing default changes only through review

- **Stops:** one lucky run changing how every later task is routed.
- **How:** The policy file is written only by `apply`, which refuses a proposal below the evidence floor, from a single repeat, or without a named reviewer's acceptance. Every version is kept, and `rollback` restores one.
- **Code:** `apply_proposal` and `rollback_policy` in `bin/workflow_eval.py`
- **Proved by:** `tests/test_workflow_eval.py` → `PolicyProcessTests`
- **Stages:** 10 Feedback, Evaluation and benchmarks

---

**Part 3**

## Stage by stage

The stages are the ones on docs/sdd/pipelines.html, numbered the same, plus the three places polytropos acts outside a kit's lifecycle: installing and updating, releasing and building, and evaluating models.

### The matrix

A dot means at least one control in that layer acts at that stage. The last three columns are install and update, release and CI, and evaluation and benchmarks.

| Layer | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | install | release | bench |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A · Standing rules, enforced by tests | ● |   |   |   |   | ● | ● | ● | ● | ● |   |   | ● |   |
| B · Spec and plan gates |   |   | ● | ● | ● | ● | ● | ● | ● |   |   |   |   |   |
| C · Checks before anything runs |   |   |   |   |   |   | ● |   |   |   |   |   |   |   |
| D · The execution boundary |   | ● |   |   |   |   |   | ● | ● | ● | ● | ● |   | ● |
| E · Independent verification |   |   |   |   |   |   |   | ● | ● |   |   |   |   |   |
| F · Honest records and claims | ● |   |   |   |   |   |   | ● |   | ● | ● |   | ● |   |
| G · Data and privacy |   | ● |   |   |   |   |   |   |   | ● |   | ● |   |   |
| H · Install, update and release |   |   |   |   |   |   |   |   |   |   |   | ● | ● |   |
| I · Build supply chain |   |   |   |   |   |   |   |   |   |   |   |   | ● |   |
| J · Spend and evaluation |   |   |   |   |   |   |   |   |   | ● |   |   |   | ● |

### Each stage

The controls that act at each stage.

**1 · Standing rules**

- A1 · Invariants that fail the suite
- A2 · One kit contract
- A3 · A stdlib-only runtime
- A4 · One pricing file per harness
- A5 · Generated documentation is never hand-edited
- A6 · Tests never call a real model CLI
- F4 · Unknown means no

**2 · Research**

- D2 · Every external process is bounded
- D10 · A code graph is read as untrusted evidence
- G4 · Memory recall is pulled, capped and labelled

**3 · Specify**

- B1 · The approval pause
- B2 · Kit fences, re-read at every phase start

**4 · Clarify**

- B1 · The approval pause

**5 · Plan**

- B2 · Kit fences, re-read at every phase start
- B4 · The budget dial
- B5 · Declared roles run, or the run stops
- B7 · Routing policy is selected, never learned

**6 · Tasks**

- A2 · One kit contract
- A4 · One pricing file per harness
- B3 · The red-green evidence rule

**7 · Analyze**

- A2 · One kit contract
- B5 · Declared roles run, or the run stops
- C1 · The task graph is validated first
- C2 · analyze is static by construction
- C3 · The spec review before dispatch

**8 · Implement**

- A2 · One kit contract
- B2 · Kit fences, re-read at every phase start
- B4 · The budget dial
- B5 · Declared roles run, or the run stops
- B6 · Re-routing is upgrade-only and advisory by default
- B7 · Routing policy is selected, never learned
- D1 · Verify commands run inside an OS sandbox
- D2 · Every external process is bounded
- D3 · A dispatch carries only its provider's credentials
- D4 · Paths are contained without a race
- D5 · Every dispatch is recorded before and after
- D7 · Cursor is identified before it is trusted
- D9 · Concurrent work cannot collide silently
- E1 · The loop runs the check, not the builder
- E4 · A rewritten brief is caught
- F4 · Unknown means no

**9 · Verify and converge**

- A6 · Tests never call a real model CLI
- B2 · Kit fences, re-read at every phase start
- B3 · The red-green evidence rule
- D1 · Verify commands run inside an OS sandbox
- D2 · Every external process is bounded
- D3 · A dispatch carries only its provider's credentials
- D5 · Every dispatch is recorded before and after
- D6 · Codex review and acceptance are read-only
- D7 · Cursor is identified before it is trusted
- D8 · Reviewers get no blanket permission grant
- D9 · Concurrent work cannot collide silently
- E1 · The loop runs the check, not the builder
- E2 · A fresh-context verifier, and optional adversaries
- E3 · Phase review against the plan
- E4 · A rewritten brief is caught

**10 · Feedback**

- A4 · One pricing file per harness
- D4 · Paths are contained without a race
- F1 · An acceptance is bound to its own run
- F5 · A subscription run is never shown as a bill
- G1 · Stores live outside the tree, private
- G2 · Harness homes are read read-only, from JSONL
- G3 · Free text is redacted before it is kept or sent
- G4 · Memory recall is pulled, capped and labelled
- G5 · The journal summary runs isolated
- J3 · A routing default changes only through review

**11 · Keep in sync**

- D1 · Verify commands run inside an OS sandbox
- D2 · Every external process is bounded
- F2 · drift reports, and writes nothing in the tree

**Install and update**

- D4 · Paths are contained without a race
- G1 · Stores live outside the tree, private
- H1 · Installation never overwrites what it does not own
- H2 · The freshness check only reads
- H3 · The install preflight

**Release and CI**

- A3 · A stdlib-only runtime
- A5 · Generated documentation is never hand-edited
- F3 · Release claims are computed, never typed
- F4 · Unknown means no
- H4 · The version bump touches only the version
- I1 · Actions are pinned to commit SHAs
- I2 · The docs toolchain is hash-locked
- I3 · Deploy credentials live only in the deploy job
- I4 · Generated links are scheme-checked

**Evaluation and benchmarks**

- D2 · Every external process is bounded
- J1 · Benchmark spending is ceiling-gated
- J2 · Target repositories are read-only
- J3 · A routing default changes only through review

---

**Part 4**

## What is not a boundary

Do not rely on any of these. Each is a known gap, stated so that the controls above are not read as stronger than they are.

- **Model dispatch is not confined.** The macOS sandbox blocks the Keychain, where subscription credentials live, so a confined model CLI cannot log in. A dispatch runs with your privileges, your network and its provider's login.
- **The interactive loop's own checks are not sandboxed.** `exec_policy` confines a check when a driver, the verify hook's precheck or `drift` runs it. In the interactive `/polytropos:execute` loop, the orchestrator runs each verify command through the session's own shell.
- **Linux and Windows have no sandbox backend.** `--exec-mode enforced` refuses there, and only the explicit trusted-host mode runs. That is a stated gap, not a silent downgrade.
- **A worktree or a scheduler copy is not a sandbox.** Separate directories separate files and writes. They do not separate privileges, credentials or network access, and a worker reading a file another is changing is not detected.
- **Benchmark candidates and judges are not yet confined.** A protected-experiment profile exists in `bin/exec_policy.py`, but nothing dispatches through it yet; benchmark setup and test commands run with the driver's privileges.
- **Role names are not permissions.** A prompt that says read-only does not make a reviewer read-only. A tool pin that includes Bash reaches everything a shell reaches, Copilot has no per-tool flag, and only Codex pins review to a read-only sandbox.
- **Execution state is not tamper-proof.** `TASKS.md`, `NOTES.md` and the verify markers sit in the tree a worker edits. Edits are detected and reported, not prevented, and the ledger outside the tree is out of a confined check's reach but not an unconfined dispatch's.
- **A spend cap is not a provider cap.** Budget dials and `--max-usd` stop polytropos from dispatching. They cannot stop a provider from billing, or undo spend already incurred.
- **A capability nobody has run is not a control.** Most capability rows say `unknown`, and that is the honest state until someone runs them.
- **Redaction is shape-matching.** It catches strings shaped like published credential formats. A password that reads as a word, a name or an address has no shape and is not caught.
- **Recording an attempt is not exactly-once execution.** A process killed at its limit may already have been billed or written a file. The ledger closes it as unknown and never replays it; it cannot know what the provider billed.
- **An isolated summary is not proof the model had no tools.** The journal summary is shown to have run outside the project and written nothing there. No tool-restricting flag is passed.
- **drift cannot yet tell a nested sandbox from real drift.** A check that starts its own sandbox is refused inside `drift`'s, and reads as drifted.
- **Kits are trusted input.** A kit's verify commands are code. Running a kit you did not write is running its scripts.
- **Repository settings are not set by code.** Dependabot, secret scanning and push protection are account switches; nothing here claims they are on.

---

Policy: SECURITY.md · Rules: CLAUDE.md · Stages: [docs/sdd/pipelines.html](pipelines.html) · HTML form: [docs/sdd/guardrails.html](guardrails.html) · Long form: [docs/SPEC-DRIVEN.md](../SPEC-DRIVEN.md)
