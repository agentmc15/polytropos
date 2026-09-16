# Handoff — roadmap implementation, steps 01–26 (complete)

**As of 2026-09-07.** Steps 01–15 are committed as a single change set on top of `fb40925`:
66 files modified, 17 added, +5,485 / −1,860 lines. Full suite green: **3,727 tests, OK
(2 skipped)**, ~3 minutes.

They landed as one commit rather than fourteen. Splitting them after the fact would have meant
fourteen intermediate states nobody ever ran the suite against, and a bisect that lands inside a
half-migrated driver is worse than one that lands on a green boundary.

Source of work: `/Users/michaelcave/Downloads/polytropos-master-implementation-roadmap.md` — an
outside audit consolidated into 26 ordered implementation steps.

**Committed on top of `dc67555` on 2026-09-12** as `097b84e`, then the commit rule below as
its own commit, each with the full suite green and both doc generators' `check` clean first:

- `primitives/harness-capabilities.json` — three codex rows for API primitives a circulated
  "graph engineering" note leans on (`async_tools`, `mid_turn_steering`, `effort_per_turn`),
  all `product=unknown` / `implemented=unsupported` / `verified=unknown`, so steps 19 and 24
  cannot assume them. The copilot `tool_pin` note was corrected: it still said review carries a
  full grant, which step 06 made false.
- `SECURITY.md` — new section "Where the approval line sits" naming the reversible /
  consequential / irreversible lanes against the flags that enforce them. Also corrected the
  "Role names are not permissions" bullet, which still claimed Claude and Copilot review carry a
  blanket grant; both default to `restricted` since step 06.
- `HANDOFF.md` — the step-24 amendment below.

The note's "operator block" was deliberately **not** brought into the plugin: it is per-user
model tuning, and three of its lines contradict repo invariants (skip tests on small changes;
user instructions outrank rule files; delegate in parallel by default).

---

## Where things stand

**All 26 steps are done.** That is all of Phase A (input/artifact/acceptance boundaries), all of
Phase B (the execution boundary and the P0/P1 security remediation), all of Phase C (the
shared runtime: durable attempts, cross-harness evidence, the validated execution DAG), all
of Phase D (named routing policies; the role contract; fresh, bounded code-graph grounding;
lean entry points and scoped lessons; the Cursor adapter; artifact-aware scheduling with
opt-in bounded concurrency), and all of Phase E (workflow evaluation with a reviewed,
versioned, reversible policy process; the release gate). Steps 16–25 landed on 2026-09-12/13
and step 26 on 2026-09-15, on branch `harden/roadmap-steps-16-26`, one commit each, then fast-forwarded into `main` and pushed
on 2026-09-15 on the user's go-ahead. What remains after step 26 is external validation — the
prepared live commands in `docs/RELEASE.md` — and that is a person's, not a session's.

| Step | What it closed |
|---|---|
| 01 | Acceptance depends on a typed JSONL ledger, not prose; fails closed on absent/malformed/conflicting verdicts |
| 02 | Benchmark patch, reference-test, and artifact filesystem escapes |
| 03 | Git metadata parsing; "read-only" git verbs that weren't |
| 04 | Journal commands rendered as literal argv, not shell strings |
| 05 | OS execution boundary for verify commands (`bin/exec_policy.py`, macOS Seatbelt) |
| 06 | Native role permissions preserved through dispatch |
| 07 | Dispatch success separated from dependency readiness |
| 08 | Pre-dispatch admission for every consuming operation |
| 09 | Completion bound to current, task-appropriate evidence |
| 10 | One path-containment helper (`bin/safe_paths.py`); no check-then-use races |
| 11 | Ownership-aware installs; stale plans fail safe; rollback preserves concurrent edits |
| 12 | Subprocess lifetime/output/env/cwd bounded (`bin/proc_runner.py`) |
| 13 | Private-data scope, redaction, isolated summaries, memory provenance |
| 14 | Build supply chain pinned; deploy credentials scoped; unsafe link schemes rejected |
| 15 | One kit contract (`bin/kit_contract.py`) + adapter seam + capability registry |
| 16 | Durable attempts (`bin/attempt_ledger.py`): recorded before/after every dispatch, resume without replay, budget carried across runs, failure classes, real progress detection, task claims, fresh-read projection |
| 17 | Cross-harness evidence (`bin/attempt_history.py` + `bin/model_registry.py`): one record per attempt over ledger + NOTES.md + role-use, unknowns kept, history never collapsed, failed consults keep lineage, cost per basis; reviews recorded on all three drivers; concrete ids resolve to tiers; telemetry `attempts` source |
| 18 | Validated execution DAG (`kit_contract.validate_graph` / `graph_state` / `readiness`): duplicate ids, self and unknown dependencies, cycles refuse with zero dispatches and zero writes on all three drivers; one readiness rule with `fresh | retry | resume | rerun` modes; automatic selection refuses while a task is in-progress; the task state machine (`TRANSITIONS`) checked at every status write; worker edits to a task block detected as `plan.drift`; `status` ends with the graph verdict; `kit_contract.py graph` / `demo` |
| 19 | Named routing policies (`bin/routing_policy.py` + `codex_policy.route`): `reserved` is the legacy behaviour under its own name and the default, `adaptive` is opt-in (`--policy`, PLAN.md `routing:`); shape, model, initial effort, and assurance decided separately; hard filters before any preference; pins and unsupported efforts refused, never substituted; an unavailable orchestrator disables nothing a worker path does not need; auth/config/permission/infrastructure dispatch failures stop the ladder on Codex; every decision explainable with its alternatives and an `est.` workflow figure; the same contract routes Claude/Copilot-shaped rosters by rank |
| 20 | The role contract (`kit_contract.ROLE_CONTRACTS` / `WORKFLOWS` / `resolve_roster` / `ROLE_SUPPORT`): each role's responsibility, scope, hook, assurance, capabilities, and result fields as data, separate from whether an agent is spawned; three workflows (`direct` named on purpose, `reviewed` the default, `extended`) with explicit assurance; one grammar for PLAN.md `roles:`/`workflow:` shared by the skill and every driver; every driver checks the roster before preview or claim and refuses or discloses (`--roster-gap`) a declared role it cannot sequence, recording `roster.checked`; consumer-neutral templates (`<repo-root>`); `independent_review`/`extended_roles` registry rows; a written test plan for trio-vs-direct with no live spend |
| 21 | Fresh, bounded, task-relevant code-graph grounding (`bin/graph_ground.py`): an optional provenance sidecar stamped from what is actually available (revision, dirty set, per-file content fingerprints, the graph's hash, the operator's extraction label, graphify's own metadata), freshness against the working tree with dirty and untracked files (`fresh` / `partial` naming changed and deleted files / `stale` / `unknown`, never a manufactured revision), a bounded impact walk from changed files or symbols (depth, node limit, hubs listed and never expanded through, configurable excludes), a bounded code-search fallback when the graph is absent, stale, unknown, silent, or weakly covering, one `polytropos.grounding/1` result any adapter can attach, graph paths validated before any read, git read-only through the process runner |
| 22 | Lean entry points and scoped lessons: the architect, execute, and repo-bench skills split into a mandatory core plus verbatim references with a "read when" trigger each (3060/6267/6677 words to 2311/2690/1353; thirteen reference files), descriptions with positive and negative triggers, a "what binds, what adapts" rule with bounded adaptation, the exact word-count and 200-byte guards replaced by ceilings and contract checks; `bin/lessons_store.py` replaces automatic lessons with observations carrying provenance, scope, and expiry, rules only by recurrence across distinct sources or by explicit ask, contests, eligibility-gated and budgeted recall (step 13's rule reused), legacy entries as candidates never rules; the Copilot lessons-loop skill and route agent read through it |
| 23 | A real Cursor adapter on the shared runtime (`bin/cursor_adapter.py` + `bin/cursor_execute.py`): the generically named `agent` binary identified before any dispatch (`--version`, then `about --format json`; unknown or absent fails closed before a claim or a write); `agent -p --output-format json --trust --workspace … [--model …] --force` for implementation and `--mode ask` for review, with overriding extra flags refused; IDE, CLI, and cloud modes reported separately (product / implemented / verified, all `verified: unknown`); a project-scoped `.cursor/` bundle (skill, implementer, read-only verifier) with an ownership-aware, manifest-backed, no-clobber installer (`harness_select install --harness cursor --project`) and a `doctor` that diagnoses ambient files carrying another harness's commands; `data/pricing.cursor.json` as Cursor's own empty roster, usage unknown, `usd: null` on every block; no ladder; the shared conformance (ready, dispatch failure, verify failure, budget stop, resume, roster gap, review) through a stub; `kit_contract.budget_gate` and `append_run_note` extracted for adapters; the anti-triplication guard now spans four drivers |
| 24 | Artifact-aware scheduling and opt-in bounded concurrency (`bin/kit_scheduler.py` + step-24 additions to `bin/kit_contract.py` / `bin/attempt_ledger.py`): every acceptance records the artifact version accepted and the upstream versions it rested on (`task.projected` carries `artifact` and `upstream`); `evidence_freshness` names a done task `stale` when a dependency was re-accepted with a different artifact (`unknown` for legacy or non-git, disclosed, never rounded); `graph_state`/`readiness` keep dependents of a stale acceptance out of the frontier, every driver's selection sees it, `status`/`graph` print the stale clause, `kit_contract.py freshness` reports and `refresh` re-verifies in place with zero attempts; the scheduler (sequential by default, `--max-parallel` ≤ 8 opt-in) claims a batch atomically, admits it in ONE budget decision, runs each task in its own copy of the tree under the store, measures write sets, integrates from a manifest (paths, verdicts, bounded diagnostics; never a transcript), keeps and names conflicts (two writers, or a user change during the batch) without applying or resetting, verifies every integrated task again on the merged tree, records kit edits from a worker as `security.violation`, refuses proposals that touch acceptance, records dependency proposals and applies them only under `--accept-revisions` after revalidation, sizes the manifest against the integrating model's own long-context field (the recorded amendment), cancels what has not started with zero-attempt `result=cancelled` lines and settles dead runs first; `stub` and `cursor` are the dispatchers; `ROLE_SUPPORT["stub"]` and `concurrent_dispatch` registry rows added |
| 25 | Workflow evaluation (`bin/workflow_eval.py` on the repo-bench seam; `repo_bench.mine_tasks` lifted out of `build_plan` unchanged): complete workflows compared on the same held-out tasks from the same clean snapshots — `direct`, `reviewed` (an independent read-only review whose verdict is recorded beside the grade), `kit` (the task as a one-task kit on the contract: claim, admission, the repository's own check under the execution boundary, projection, resume) — under pinned or routed (`reserved` / `adaptive`, decision recorded) models and instruction versions, counterbalanced repeats; five adapters (claude, codex, copilot, cursor, stub) each built from its own driver's argv and its own pricing file, with a read-only review form; every dispatch in the attempt ledger and joined through `attempt_history` with registry tiers; `solved` from the tests oracle alone; accepted completion with Wilson intervals, incorrect acceptances, interventions, wall-clock, coverage, stability, strata, usage per basis never summed (reported / estimated / proxy / credits / unpriced; only priced bases count against `--max-usd`); security outcomes recorded (incorrect acceptance, tampering, policy violation, capability refusal, budget overshoot, resume, privacy redaction by kind); a priced plan naming hard caps that is never dispatched; `prefs/routing-policy.json` changed only through `propose` (refused below floor, single repeat, or on reserved tasks) → named `review` → `apply` (refused unreviewed or stale) with every version kept and `rollback`; the `evals` store; `workflow_evaluation` registry rows |
| 26 | The release gate (`bin/release_gate.py` + `docs/RELEASE.md`): the supported matrix computed from the evidence and never typed — contract versions read from their owning modules, package and toolchain versions from the manifests, `cached_date` and roster size per pricing file, every registry row's three states with its date and (from now on) the client version a verification ran against, `ROLE_SUPPORT` per harness, the historical primitive matrix summarised and left unrewritten; eleven shared contracts each mapped to the tests that prove them through a stub per harness beside the registry rows a real client would have to verify (STUB CONFORMANCE and INSTALLED-CLIENT VERIFICATION never merged; `check` refuses a test id that resolves to nothing and `--run` runs the map in-process); the packaging review (every `runtime_data.STORES` name needs its root-anchored ignore rule, no tracked file under a store or matching a junk pattern, every top-level path has a role, the plugin manifest and marketplace agree, the workflow's actions are SHA-pinned with deploy credentials only in the deploy job, every site package hashed); the checklist, migration and rollback notes, re-evaluation triggers, and prepared-not-run live commands as data, every cited `bin/X.py sub` resolved against the script's own parser; `reverify --harness --released` partitions rows by date and edits nothing; the marked block of `docs/RELEASE.md` is the deterministic render and drifts fail `check` (exit 3). Reconciled: PRIVACY.md (three stores missing from its table and its test; the step-13 closure of the plugin-cache runtime hazard), GRAPH-ENGINEERING.md (four drivers; 3-of-4 prompt attribution; opt-in concurrency beside sequential default), DAILY-JOURNAL.md (three of four pricing files); `tests/test_privacy_layout.py` now derives its list from `runtime_data.STORES`; the marketplace description matched to `plugin.json` |

### New modules, and what each is the *one place* for

- `bin/safe_paths.py` — whether a path is safe to write, read, or delete. Directory-relative,
  `O_NOFOLLOW`, refuses rather than falling back.
- `bin/exec_policy.py` — the OS execution boundary for verify commands.
- `bin/proc_runner.py` — starting an external process: wall clock, output ceiling, validated
  cwd, own process group, named outcome for every failure mode.
- `bin/redact.py` — what may not leave the machine in plain text.
- `bin/runtime_data.py` — where personal stores live (outside the plugin tree).
- `bin/kit_contract.py` — parsing, graph validation, readiness, status transitions, budget
  admission, outcome vocabulary, and (step 20) the role contract: `ROLE_CONTRACTS`,
  `WORKFLOWS`, the `roles:`/`workflow:` grammar, `resolve_roster`, `ROLE_SUPPORT` per
  executor, and `roster_for_run`, the pre-dispatch check every driver calls. Its command
  line: `graph --kit DIR [--json]` (exit 2 on an invalid graph), `roster --kit DIR
  [--executor X] [--json]` (exit 2 on a grammar error, 1 on a gap), and `demo`.
- `bin/harness_adapter.py` + `primitives/harness-capabilities.json` — what a host can actually
  do, with `unknown` as a first-class answer.
- `bin/attempt_ledger.py` — what a run did, recorded before and after it did it, outside the
  tree. Claims, failure classes, normalized progress signatures, bounded retry context. The
  drivers reach it only through `kit_contract.TaskRun` / `start_task_lifecycle` /
  `reconcile_task` / `finish_task_projection` / `record_role_dispatch`; Ralph reaches it
  directly.
- `bin/model_registry.py` — which harness knows a model id and what tier it sits in there.
  Reads ids and tiers from the three pricing files, never a price; refuses to guess between
  harnesses that disagree. `routing_scorecard.tier_for` and `bench_routing` resolve through it.
- `bin/attempt_history.py` — one record per attempt over the ledger, `NOTES.md` outcome lines
  and Codex `role-use.jsonl`; unknowns kept and counted; latest state a separate projection;
  lineage including failed consults; cost per basis. Captured daily as telemetry's `attempts`
  source.
- `bin/graph_ground.py` — whether a graphify graph.json still describes the tree, and what
  near a task's files is worth reading. `stamp` writes the one provenance sidecar beside the
  graph; `freshness`, `impact`, `search`, and `ground` read. `bin/graph_brief.py` stays the
  pure whole-graph summary and still carries no process primitive; this module reaches git
  only through `proc_runner` with read-only verbs.
- `bin/lessons_store.py` — the per-project lessons file (`tasks/lessons.md`, JSON lines,
  append-only) with kinds: `observation` (provenance, scope, expiry; a candidate),
  `rule` (only by `promote`: recurrence across distinct kits or tasks, or `--by user`),
  `contest` (withholds a rule until re-promoted), `legacy` (pre-kind entries; candidates,
  never rules). `recall` is eligibility-gated through `memory_recall._eligible` (one rule,
  reused), expiry- and contest-gated, budgeted. `bin/lessons_promote.py` stays the cross-kit
  defect-kind draft tool.
- `bin/routing_policy.py` — the harness-neutral routing decision: workflow shape, model,
  initial effort, and assurance as four separate answers, under a named policy (`reserved` |
  `adaptive`) and a preference that never outranks a hard filter. Compares tier RANKS in each
  harness's own order, never tier names; never reads a pricing file itself (each harness
  builds a catalog from its own). `codex_policy.catalog` / `request_for` / `route` are the
  Codex side; the Codex driver is the only one dispatching under it so far.
- `bin/cursor_adapter.py` — everything Cursor-specific that is not the run loop: identity
  (`identify` / `require_cursor`, fail-closed), the argv (`build_dispatch`, blocked extra
  flags), output reading (`parse_output`: a `model` field or unknown; never usage), the
  three modes (`MODES`), the project bundle (`BUNDLE`, `bundle_sources` resolving
  `{{POLYTROPOS_ROOT}}`), the install plan and its writer (`plan_install` / `apply_install`
  through `safe_paths`, manifest at `.cursor/polytropos/install-manifest.json`), ambient
  diagnosis, `doctor`, the documented-not-run smoke, and the `harness_adapter.Adapter`
  subclass (`adapter()`) whose capabilities are the registry's rows. Carries no process
  primitive; probes go through `proc_runner` with `dispatch_env("cursor")`.
- `bin/cursor_execute.py` — the fourth driver, and the first written entirely on the
  contract: `probe` / `status` / `run` / `review`. `run` is roster check, selection, dry-run
  or identity, lifecycle, `budget_gate`, projection, `reconcile_task`, one dispatch, one
  verification, `finish_task_projection`, `append_run_note`. No ladder, no price list, no
  cost figure.
- `bin/kit_scheduler.py` — the one scheduler: batch selection (dead-run resumes first, then
  the frontier, bounded), atomic claims + one `BudgetAdmission` per batch, tree snapshots
  (`snapshot_tree` / `index_tree` / `write_set`), the dispatcher seam (`StubDispatcher`,
  `CursorDispatcher`, or any callable `(task, prompt, workspace) -> (rc, output, proc)`), the
  integration manifest and its bound (`build_manifest` / `manifest_bound` / `fit_manifest`;
  `THRESHOLD_FIELDS` names each harness's own field), `_integrate` (from the manifest only),
  the merged-tree re-verification, revision proposals (`read_revision`,
  `apply_dependency_additions`), cancellation, `plan` / `run` / `demo`. The step-24 contract
  half lives in `kit_contract.py`: `FRESHNESS_STATES`, `REFRESH_MODE`, `evidence_freshness`,
  `kit_freshness`, `refresh_task`, `render_stale`, and the `freshness=` parameter on
  `graph_state` / `readiness` / `select_task`; `attempt_ledger.py` gained
  `latest_acceptance` / `latest_artifact` and the `artifact` / `upstream` projection fields.
- `bin/workflow_eval.py` — the one place workflows are compared and routing defaults are
  changed: the five adapters on the repo-bench seam (`claude_adapter` … `stub_adapter`,
  `make_adapter`), variants and counterbalanced trials (`build_variants`, `trial_matrix`),
  prompts (`build_stage_prompt`, `build_review_prompt`, `redacted_statement`), costs per
  basis (`stage_cost`, `add_cost`, `priced_usd`), routing (`route_stage`), the plan
  (`build_plan`, `render_plan_markdown`), the run (`Evaluation`: `_dispatch`, `_grade`,
  `_review_stage`, `_kit_stage`), the card (`build_card`, `render_card_markdown`,
  `wilson`), store readers (`read_envelope`, `list_runs`, `history_records`,
  `adjudicate`), and the policy process (`build_proposal`, `review_proposal`,
  `apply_proposal`, `rollback_policy`, `policy_report`). `repo_bench.mine_tasks` is the
  miner it calls; it forks none of repo_bench's oracles, sandboxes, or ceilings.
- `bin/release_gate.py` — the one place release claims are computed: `HARNESS_FACTS`,
  `VERSION_SOURCES`, `CONTRACTS` (the contract → harness → test-id map, with the registry
  rows each cell cites), `LEGACY_TESTS`, `NO_REAL_CLI_TESTS`, `CHECKLIST`, `MIGRATION_NOTES`,
  `REEVALUATION_TRIGGERS`, `PREPARED_COMMANDS`, `TREE_ROLES`, `FORBIDDEN_TRACKED`;
  `contract_versions`, `package_versions`, `harness_matrix`, `historical_matrix`,
  `contracts_report` (`resolve_test_ids` / `run_test_ids`, both injectable),
  `packaging_review` (tracked list injectable), `registry_findings`, `reverify`,
  `command_findings`, `render_block` / `build_release_doc` / `check_release_doc`,
  `run_check`. Read-only git through `proc_runner` (`GIT_READ_VERBS`), nothing else spawned.

---

## Next: nothing in the roadmap — what remains is external validation

The 26 steps are implemented. What a session cannot do is in `docs/RELEASE.md` under "Prepared,
not run": the Cursor identity smoke, one authorised live `run` per driver, the bounded workflow
evaluation, the bounded benchmark. Each records into a registry row by hand (`verified`,
`verified_on`, `client_version`, the command in the note) — `release_gate.py reverify` lists
which rows a client release invalidates and writes nothing. If a later session picks this up:

- `python3 bin/release_gate.py check` first; then `check --run` if there is time (it runs the
  whole contract map in-process, several minutes).
- A new `docs/*.md` still moves the census pins (now 29 / 31 / 73 and 30 / 32 / 74).
- `CLAUDE.md` has 8 bytes of headroom under its 16,000-byte ceiling; trim before adding.

### Step 26's own deliberate limits

- **Nothing ran live.** The gate reads the registry; it does not verify anything itself. Every
  real-harness row stays `unknown` or `unsupported` except Claude's three from 2026-09-06.
- **Client versions are `not recorded` everywhere.** The 2026-09-06 Claude verification wrote
  none and is not backfilled (that would be hand-authoring evidence). A `verified: supported`
  row dated on or after 2026-09-13 must carry `client_version` or `check` fails
  (`CLIENT_VERSION_REQUIRED_FROM`); older rows are exempt and say so.
- **The contract map is a curated table, not a discovery.** `CONTRACTS` names the tests that
  prove each contract per harness; `check` proves those ids exist and `--run` proves they pass,
  but a new test proving a contract joins the map only when someone adds it.
- **`check` does not run the map by default.** Resolving ids takes seconds; running them takes
  minutes and spawns the drivers' stub executables. `--run` is the opt-in.
- **Packaging is reviewed, not built.** There is no package artifact to inspect: the plugin is
  installed from this directory, so the review is of the tracked tree, the ignore rules, the
  manifests, the workflow, and the lock file. The Codex package version line
  (`0.5.0+codex.…`) differs from the plugin version and is reported as a note, not a finding,
  because rewriting it changes the ownership keys of every installed Codex copy.
- **The generated block carries no revision or date.** Determinism is what lets `check` fail
  on drift; the live `check` output carries the sha, commit date, and dirty count instead.
- **The map is only as good as its ids, and the gate already caught one.** The first populated
  map named `test_kit_graph.ReadinessTests.test_interrupted_outranks_ready…`; the method lives in
  `FrontierAndStateTests`. `check` reported it as resolving to no test before any run, which is
  the failure mode the resolver exists for. The verification-isolation row had no per-driver
  evidence at all until `test_proc_runner_wiring.DriverVerifyWiringTests` pinned that every
  driver builds its verify runner from `exec_policy` with the parsed `--exec-mode` and exposes
  `trusted-host` as the one opt-out; the boundary's behaviour itself stays `test_exec_policy`'s.
- **`harness_update.py check` exits 3 on this machine and that is not a repository finding.** Its
  `data` section is up-to-date; the `claude` and `copilot` sections describe the user's installed
  homes, which lag an unmerged branch. The checklist row cites the `data` section, not the exit.
- **Doc reconciliation covered the three pages the roadmap named plus README and SECURITY.**
  Other deep-dives written before the Cursor adapter still say "three harnesses" where they
  describe their own kit's history; those are records of the kit, not present-tense claims.

### Step 25's own deliberate limits

- **Nothing ran live.** Every adapter's argv is its driver's documented shape and every dollar
  figure is an estimate at the harness's own rates; the registry's `workflow_evaluation` rows
  are `verified: unknown` for all four real harnesses and `supported` only for the stub. The
  bounded plan in `docs/WORKFLOW-EVAL.md` is a command, not a result.
- **`solved` is the tests oracle and only that.** The full-patch diagnostic and the blind
  judge stay repo_bench's; the evaluator does not dispatch a judge. A reviewer's verdict, the
  kit's own check, and an adjudication are recorded beside `solved`, never in it.
- **The reviewer's read-only mode is a CLI flag.** Only the kit workflow's check runs under
  `exec_policy`; a review dispatch runs in a throwaway directory outside the run dir with the
  harness's documented read-only form and nothing more.
- **Usage extraction is Claude's only.** The other adapters return no usage from stdout (their
  drivers never parsed it either), so their trials are `estimated` / `proxy` / `unpriced`.
- **Grounding and lessons are not variant axes.** Instruction versions are; graph-grounded
  versus search-grounded prompts, and lesson versions, are listed as untested on every card.
- **The policy file has no reader.** `prefs/routing-policy.json` is pull-only by design; the
  drivers keep reading PLAN.md. `repo_bench apply` (the tier map) is not versioned by this
  process and keeps its own refusals.
- **One repository per run.** Strata carry a `repository` bucket, but a run mines one target;
  cross-repository comparison is a reader's job over several cards, not a single ranking.
- **Cost of a dead attempt is the contract's.** The eval kit admits two dispatches (one plus
  one recovery) because a dead attempt closed as unknown still counts; a third is refused and
  recorded as the budget outcome.

### Step 24's own deliberate limits

- **No live model ran in parallel.** The `stub` executor is the conformance harness and
  `cursor` is the only real dispatcher wired; the Claude Code, Copilot, and Codex drivers keep
  their sequential loops until their argument builders are lifted into `harness_adapter`
  subclasses. `primitives/harness-capabilities.json` says so per harness
  (`concurrent_dispatch`).
- **Isolation is of files.** A worker's copy separates writes; it shares the machine, the
  network, and the dispatch environment's credentials. A worker that READS a file another is
  changing is not detected -- only conflicting writes are. Copies are history-free tree
  extractions (no `.git`), so a verify command that needs git history fails in a copy.
- **Merging is not attempted.** A conflict keeps the worker's copy and names the files; no
  three-way merge, no automatic reset. Resolving it is the operator's or the architect's work.
- **Revision proposals apply only edges.** `--accept-revisions` adds dependencies that keep
  the graph valid; new tasks are recorded for the architect and never written into TASKS.md.
- **The manifest bound is exercised, not lived.** Integration here is mechanical; the sizing
  against the integrating model's long-context field is what a model integrator would be
  handed, and it is tested (trim with note, refuse, unbounded for Cursor) without one being
  dispatched.
- **Fingerprints are git-derived.** `workspace_fingerprint` is HEAD + diff + untracked
  metadata; outside git it is `None`, freshness is `unknown`, and nothing is invalidated.
  Two acceptances of one task on byte-identical trees carry the same version, as intended.
- **Cancellation is cooperative.** It stops what has not started and releases those claims; a
  running dispatch is bounded by the process runner's clock and its allowance is spent.

### Step 23's own deliberate limits

- **Nothing was run against Cursor.** No `agent` binary exists on this machine
  (`/usr/local/bin/cursor` is the IDE launcher and was not run); the flags, file locations,
  and the JSON output shape come from Cursor's documentation, cited in `cursor_adapter.DOCS`.
  Every `verified` cell in the registry's `cursor` rows and in `MODES` is `unknown`, and the
  smoke command is printed, never executed. When the binary and the documentation disagree,
  the binary wins and the adapter is what to correct.
- **`parse_output` reads a documented format with an undocumented schema.** A top-level JSON
  object (or the last object line of a stream) is kept; a string `model` field is the only
  thing taken as an observed model; usage is always `None`. Nothing is guessed from prompt
  text, and the editor's SQLite store is never opened.
- **No ladder, no cost.** `data/pricing.cursor.json` has an empty roster and no rates, so a
  failed verification blocks after one attempt and every NOTES block says `usd: null`. The
  file exists so the one-file-per-harness rule holds and so a future roster lands in one place.
- **Cancellation and status are unsupported and say so** (`CapabilityError`); the process
  runner's wall-clock bound is the only stop. `harness_update.py check` does not yet know
  Cursor; `detect()` still reports three harnesses (pinned by tests) — the Cursor binary's
  presence is `cursor_execute.py probe`'s job.
- **Project scope only.** The bundle installs under the project's `.cursor/`; a user-scope
  install (`~/.cursor/`) was not added because nothing here may touch a home directory and
  the roadmap prefers project scope. `harness_select.py detect`'s keys are unchanged.
- **The verifier subagent is a file, not a dispatch.** `run` executes the verify command
  under the execution boundary itself (`ROLE_SUPPORT["cursor"]["verifier"]` is `partial`);
  the read-only verifier prompt is used by `review` and is available to the IDE.
- **Two contract extractions, no behaviour change for the three original drivers.**
  `kit_contract.budget_gate` and `append_run_note` were added for adapters; the original
  drivers keep their inline budget block and their own `append_note` (each carries a bullet
  the others do not). The anti-triplication guard covers all four; the highest cross-driver
  similarity of any shared name is `_kc` (exempt bootstrap) at 80%.

### Step 22's own deliberate limits

- **The moves are verbatim.** Every section that left an entry point landed in a reference
  file unchanged, with a one-line header; nothing was rewritten to be shorter. The entry
  points are leaner because they carry less, not because the rules got vaguer. Rewriting
  the moved grammar for concision is a separate, riskier edit.
- **The size numbers are measured, not the goal.** Words and description characters were
  recorded before and after; loaded-context and task-outcome effects were NOT measured (no
  live dispatch), so "3060 → 2311" says what moved, not what improved.
- **The exact word-count guard is gone; ceilings remain.** `EntryPointContractTests` pins a
  generous ceiling per entry point, the operational phrases that must stay readable there,
  and the moved phrases that must exist in their reference. A ceiling is still a size test;
  it is not a floor and it does not need re-freezing when a rule changes.
- **`GUARDRAILS.md` no longer needs 200 bytes; it needs a fence.** One substantive line, or a
  pointer at PLAN.md's out-of-scope section.
- **Codex and Copilot descriptions were surveyed, not edited.** Codex descriptions are short
  (57–187 chars); Copilot's run 198–333; `copilot/journal` and `claude/journal` share one
  description (310 chars, the same tool). No invocation policy was changed.
- **Legacy lesson entries are demoted, not deleted.** An entry with no `kind` is recalled as a
  `LEGACY, unscoped candidate`, never as a rule; promoting one takes `--by user`. This
  changes what the Copilot route agent applies at session start — it is the point of the
  step, and the skill and agent say so.
- **Lessons stay a tracked, project-scoped file** (`tasks/lessons.md`), not a per-user store:
  a team's rules are shared knowledge. The engine appends and never rewrites; supersession
  is by id.
- **The execute driver's `lesson-candidate (routing):` line is unchanged**: it names an
  observation to record, and the skill says that is what it is.

### Step 21's own deliberate limits

- **The sidecar is written by an operator command, not by graphify.** graphify emits no
  provenance and this step did not ask it to; `graph_ground.py stamp` records what git and
  the file system say at stamp time. A graph stamped long after it was built has a stamp
  that is honest about the stamp, not about the build — `graph.mtime` is reported with a
  note saying exactly that.
- **`generated_at` is not known.** The sidecar carries `stamped_at` and the graph file's
  mtime, each labelled; an extractor version appears only when graphify wrote one into
  graph.json (`EXTRACTOR_KEYS`), otherwise `unknown`.
- **No driver attaches the grounding to a prompt yet.** `grounding()` and
  `render_grounding()` are the shared result and its bounded text; the graphify and
  architect skills instruct their use, and any driver can call them, but a `--grounding`
  flag on the three drivers is a prompt-composition change left to the step that reworks
  prompts (22) or roles (24).
- **The search fallback is substring matching over the tracked tree**, bounded by files,
  hits, and bytes, with no regular expression built from graph or task text. It is a
  fallback, not a code-search engine, and the result says which reason triggered it.
- **`stale` versus `partial` is a whole-graph rule**: the graph is `stale` when its bytes
  differ from the stamped ones or every covered file differs, `partial` when some do. The
  per-file states are the useful part; the verdict word is the summary.
- **The architect ceiling was re-frozen a fourth time** (2997 words) for the grounding
  pointer; step 22 is the right place to retire that guard.

### Step 20's own deliberate limits

- **No headless driver sequences an optional role.** `ROLE_SUPPORT` says so per executor and
  the drivers refuse (or disclose) rather than pretend; the interactive execute skill is
  the only executor that runs scout / test-author / second-verifier / red-team /
  security-auditor / docs-editor / synthesizer at their hooks. Making a driver sequence
  them is a scheduler-shaped change (step 24 territory), not a contract one.
- **The per-task verifier is `partial` on every driver and always was.** `run` executes the
  verify command; no verifier agent is dispatched per task; `review` provides the
  independent look at phase end. This is disclosed on every run, never refused, because
  refusing it would refuse every kit ever written.
- **`direct` is a named opt-in and cannot coexist with declared roles**; `reviewed` with
  declared roles is a contradiction too. The grammar is strict on purpose: a roster that
  says two things dispatches under neither.
- **Roles are declared, never selected by the code.** "Select additional roles from task
  risk and a stated purpose" is the architect's instruction (the skill says so); the
  contract gives it the vocabulary and the drivers enforce that what was declared is what
  runs. No signal-driven role selection was added, so no role can be promoted by a prompt.
- **The `agent:` line grammar is unchanged.** Severity, duplicates, and latency live in the
  contract's `RESULT_ENVELOPE` (what a recorded role result should carry) and in the
  attempt ledger's per-dispatch durations, not as new optional fields the scorecard parses;
  adding them to the line family would be a reader change first.
- **The trio-vs-direct comparison is a written test plan** (`docs/ROLE-EXPERIMENT.md`),
  not a run: it needs `direct` kits to exist, and none has been run yet.
- **The two legacy kits with declared roles** (`aesop-fold`, `docs-site`) now resolve as
  `extended` and would be refused by a headless driver; both are complete, so nothing
  changes for them, and the test pins exactly those two.
- **The architect and execute ceilings were re-frozen again** (2969 / 6217 words) for the
  `workflow:` line, the shared grammar, the contract pointer, and `<repo-root>`.

### Step 19's own deliberate limits

- **Only the Codex driver dispatches under a routing decision.** `bin/routing_policy.py`
  routes a Claude- or Copilot-shaped catalog by rank (tested, and `routing_policy.py decide
  --harness claude` previews it), but `claude_execute` and `copilot_execute` still resolve
  models exactly as before. The roadmap said "Codex first"; wiring the other two is a
  behaviour change to their installed defaults and was not taken silently.
- **Nothing in the capability registry is verified, so the shape filter treats `unknown` as
  offered-and-named-unverified**, not as unsupported. Reading `unknown` strictly would exclude
  the default `direct` path too, since `dispatch` itself is unverified (nothing is run live
  from this repository). `unsupported` rows do drop a shape to a simpler one.
- **`latency` is a preference the catalog has no data for.** It routes as `balanced` and the
  decision says so; adding latency data is a pricing-file change, not a router change.
- **The estimate needs a profile.** Without `--profile`/`routing: profile=`, every stage reads
  `unpriced`; a size assumption is not invented. With one, the figure is `codex_pricing`'s
  own `usd_api`, labelled est. and API-equivalent — never a bill.
- **`unknown`-class dispatch failures still climb the ladder on Codex** (a bare non-zero exit
  with no recognisable cause), because two existing tests and the `lower_tier_correction_failed`
  recovery kind depend on that path. Only `auth` / `config` / `permission` / `infrastructure`
  stop it. Claude's driver stops on ANY failed dispatch; the two are not yet the same rule.
- **Adaptive removes the separate recovery step** (the frontier is an ordinary rung), so an
  adaptive run never writes `recovery evidence` lines to NOTES.md. The ledger still records
  every attempt.
- **`bench_routing` roles card is unchanged** and still reflects the reserved eligibility;
  it does not take a `--policy`.
- **`prepare` output grew two keys** (`policy` inside the assignment, `decision` beside it);
  no consumer in the repo read the old keys by set.

### Step 18's own deliberate limits

- **An invalid graph refuses the whole kit, not the broken tasks.** A cycle between T3 and T4
  stops T1 too. This is the strict reading of the roadmap's "zero dispatches" and it is on
  purpose: dispatching around a self-contradicting plan mutates state on a plan nobody has
  confirmed. The cost is that a typo in one `depends:` line halts a kit until it is fixed; the
  findings say exactly which line.
- **Automatic selection now refuses while any task is `in-progress`** (`graph: interrupted`),
  where it used to walk past and dispatch the next pending task. Naming a task (`--task`) is
  the way past it, for the interrupted task (resume) or another ready one (deliberate). This
  is the sequential default the roadmap asks for; two tasks at once is step 24's scheduler.
  The interactive execute skill, which parallelises `independent:` tasks through the Agent
  tool, is prose and unaffected.
- **`interrupted` cannot say whether the run is alive.** `graph_state` is pure and reads only
  the file; the claim taken at dispatch (step 16) is what knows the pid. The reason text says
  both possibilities.
- **Plan drift is reported, not reverted.** A worker's edit to its own brief, verify command,
  or dependencies is named on stderr, recorded as a `plan.drift` ledger event, and carried in
  `result["plan_drift"]`; the file keeps the worker's version for the architect to judge, and
  no NOTES.md line is written for it (a new bullet family would need the history reader to
  learn it; deferred until something reads it).
- **Two finished legacy kits are invalid by this validator**: `aesop-bridge` and
  `context-rules` carry prose in `- depends:` lines (`(none within this kit)`, `T1–T8
  (documents their output)`). Both are complete, so nothing changes for them; the test pins
  that the invalid set is a subset of those two and that every kit with work left is valid.
  Fixing the lines removes them from the set.
- **The `status --json` shape is unchanged** (still the task list); the structured graph is
  `kit_contract.py graph --json`, not a new key in the drivers' JSON.
- **No `harness-capabilities.json` row.** Graph validation is the coordinator's, not a host
  capability; the Cursor seam is the same `select_task`/`readiness` call every driver makes.
- **The architect and execute skill ceilings were re-frozen** (`tests/test_docs_skill_dispositions.py`,
  2866 and 6132 words) because the `depends:` rules are a kit-contract change both skills must
  state. The "may only shrink" rule resumes from there; the next contract change re-freezes
  again with its own dated comment, never by loosening.

### Step 17's own deliberate limits

- **`billed` cost is never populated by the history.** Pricing a Claude session needs its
  transcript, which stays `routing_scorecard --history`'s job through `session:` lines. The
  history carries what the records themselves held: Copilot `- budget:` estimates and Ralph
  ticks (`estimated`, or `model-reported` when the model wrote the number). Codex subscription
  proxies appear in no per-attempt record yet, so they are absent, not zero.
- **An infrastructure-class dispatch failure still writes `result=blocked`** to the outcome
  line; the class rides beside it (`- failure-class:`) and in the ledger, and the history's
  `failure_classes` counts it. The scorecard's `failure=` vocabulary was left alone: adding a
  value the reader drops would be a line the reader has to ignore.
- **A chain's `attempts` mixes granularities**: ledger records count one each, a `NOTES.md`
  line without ledger twins counts its own `attempts=`. Stated in the field's docstring.
- **The scorecard's Claude-oriented per-tier stats now count a Codex `frontier` pass under
  `frontier`** because the tier word is the same; `mid`/`strong`/`cheap` still fall outside
  `LIVE_TIER_ORDER` with the existing note. Per-harness tier stats live in the history card,
  not the scorecard.
- **`--demo --alarm` changed meaning deliberately**: `driver-blind` now HAS evidence (its
  concrete id resolves) and a new `pin-unknown` kit carries the no-evidence path. The test says
  so in a comment.

### Step 16's own deliberate limits

- A resume **restarts the ladder at the task's pinned model**, not at the rung the dead run had
  reached. The retry context tells the model what rungs were tried; the driver does not skip them.
- Automatic task selection picks `pending` tasks, so **resuming an `in-progress` task means
  naming it** (`--task E1`). The status says which one.
- Copilot and Codex have no precheck, so their resume never has to distinguish a tautological
  pass; Claude's does, from the precheck the first run recorded in the ledger.
- The claim uses the pid: a recycled pid reads as alive and the run refuses. `--break-claim` is
  the deliberate way past it, recorded as such.

---

## Roadmap amendments recorded here

The roadmap file lives outside the repo and is the user's document; amendments agreed in a
session are recorded here so the implementer of the affected step sees them without depending
on that file having been edited. Paste-ready text for the roadmap is in each entry.

### Step 24 — bound the integration step by the model's own long-context threshold

Agreed 2026-09-11, from reading a circulated engineering note on running agents as a graph:
its one idea polytropos had as principle but not as data was "workers write files, the root
reads a manifest, because the merging root hits the long-context cliff first." Add to step 24's
implementation prompt:

~~~text
The central integration step reads a manifest, not the corpus: artifact paths, verdicts, and
bounded diagnostics, never worker transcripts or evidence dumps. Size that manifest under the
long-context threshold of the model dispatched to integrate, read at run time from the
integrating harness's own pricing file under that file's own field name:
`long_context.threshold_input_tokens` in data/pricing.codex.json,
`long_context.threshold_tokens` in data/pricing.copilot.json, and `context_window` in
data/pricing.json, which carries no separate long-context tier. Do not introduce a shared
schema across the three files to do this; they never merge. Estimate the manifest's size with
the repo's one estimator (`EST_CHARS_PER_TOKEN` in bin/context_weight.py), label the figure
est., and do not add a second estimator. When the model carries no threshold, the manifest is
unbounded and the run's report says so rather than assuming one.

Test a manifest that exceeds the threshold (the run refuses, or trims with a recorded note;
never silent truncation), a model with no threshold, and that no worker output reaches the
integrator except through the manifest.
~~~

Not added to step 16: its "bounded diagnostics" are verifier output sized for the next attempt's
prompt, orders of magnitude below any long-context threshold, so that bound belongs to the
threshold's own scale, not this one.

---

## Traps this work hit — read before editing

These cost real time to discover. All are still live.

1. **Generated doc mirrors fail the suite on drift.** `README.md`, `SECURITY.md`, `docs/*.md`
   and every `SKILL.md` feed generators. After editing any of them run **both**:
   `python3 bin/copilot_docs.py build` and `python3 bin/docs_build.py build`. Drift here caught
   me twice. (Measured 2026-09-11: a `SECURITY.md`-only edit rebuilt both mirrors byte-identical,
   so that file is not currently a mirror source — run both builds anyway; it is cheap.)
2. **`CLAUDE.md` has a 16,000-byte ceiling** (`tests/test_guardrails_layout.py`). Measure it
   with `wc -c CLAUDE.md`; after step 16 the headroom is under 200 bytes. The next rule that
   needs adding has to displace words, not join them. It was rebalanced once already by
   consolidating repeated rules; that is the move to repeat.
3. **Never invoke a real `claude` / `copilot` / `codex` CLI** from tests, verify commands, or
   kit execution. One live invocation was authorized in step 06, scoped to that single test, and
   was never wired into the suite.
4. **Commit at every green boundary; never push, merge, or commit on `main` without being
   asked** (rule adopted 2026-09-12, replacing "do not commit unless asked"). A dirty tree at
   session end is now a defect, not an expected state. `tests/test_guardrails_layout.py` pins
   the sentence.
5. **Byte-stability and key-set guards exist** on ledgers, budget result keys, demo output and
   docs. When one fires it is usually correct — update it deliberately with a comment saying
   why, never loosen it to make a run pass.
6. **`tests/test_kit_contract.py` fails if two drivers share an implementation** above 85%
   similarity. If you add a function to one driver, it probably belongs in `kit_contract.py`.
7. **Every test module that drives a real `cmd_run`/`main` path patches `POLYTROPOS_DATA_HOME`**
   to a temp dir at module level (`setUpModule` in the three driver tests, the Ralph tests, and
   `test_attempt_ledger.py`). The drivers default the attempt ledger to the per-user data root;
   a new test file that forgets the patch writes into the real store. Copy the block.
9. **`tests/test_telemetry_snapshot.py` counts sources as `len(ts.SOURCES)`**, not a literal,
   since step 17 added the sixth. Its `--days 5` assertion is a literal 5 that has nothing to
   do with the count; a blanket replace there is the mistake this line exists to prevent.
8. **`kit_contract._al()` caches the loaded module, and must.** The other lazy loaders reload
   per call; this one cannot, because `ClaimHeld` is caught by class identity, and a ledger
   opened by one load raising past an `except` naming another load's class was an uncaught
   exception where a refusal was meant. Tests loading `attempt_ledger` themselves hold a
   third copy; they never compare its classes with the contract's.
10. **A kit fixture with an `in-progress` task no longer auto-selects the next pending one**
   (step 18). A test that sets a task in-progress and then runs a driver without `--task`
   gets exit 2 and "is in-progress"; name the task. No existing test relied on the old walk-past,
   but the next one written from memory will. `NOTES.md` outcome lines are `- outcome: …`
   bullets (leading dash), which the first version of `test_kit_graph.py` forgot.
11. **`project_status` now refuses an edge `TRANSITIONS` lacks** (`pending -> done`, say) with
   `InvalidTransition`, a `ValueError` that `run_cli` turns into exit 2. A test that writes a
   verdict straight over `pending` must go through `in-progress` first, as the drivers do.
12. **Modules loaded by path are separate copies, and so are their exception classes.** A test
   that loads `harness_adapter` itself and asserts `assertRaises(ha.CapabilityError)` against
   an adapter that loaded its own copy never catches it. `test_cursor_adapter.py` takes
   `ha = ca._ha()`; `test_kit_contract.py` hands its `ha` to the cursor module through
   `_SIBLINGS["harness_adapter"]`. The same rule made `harness_select.py` load
   `cursor_adapter` by path (`_cursor_adapter()`), not `import cursor_adapter`, because
   `harness_update.py` loads `harness_select` by path and `bin/` is not on `sys.path` there.
13. **argparse eats a flag-shaped value.** `--extra-arg --force` is a parse error ("expected
   one argument"); the form that reaches the adapter's refusal is `--extra-arg=--force`. The
   drivers' `status` subparsers take only `--kit`/`--json`, so a helper that appends
   `--cursor-bin`/`--attempt-store` to every command breaks on `status`.
14. **Adding a `docs/*.md` page moves six census pins.** `tests/test_docs_build_adversarial.py`
   (27 sources / 29 page-map keys / 71 pages, and the "one more" targets 28 / 30 / 72),
   `tests/test_docs_build_cli.py` (71 then), and `tests/test_primitives_doc_adversarial.py` mirror
   each other by design: `CensusBumpTripwireTests` exists to prove the other two are real
   tripwires. Move all of them in the same edit, with the date and the file that moved them.

15. **A ledger reader must tolerate an absent store root.** `status`, `graph`, `freshness`, and
   the scheduler's `plan` read the ledger before any run has written it; `safe_paths` opens
   the root with `O_DIRECTORY` and raised `FileNotFoundError` there. `events()` and `holder()`
   now return empty for a root that does not exist, and only a write creates it. A new reader
   that opens the store through another path will hit the same thing.
16. **Cancellation and budget-stop are not verdicts.** A task the scheduler cancels never
   moved (`pending`, no in-progress projection, no snapshot) and gets a zero-attempt
   `result=cancelled` line; `finish_task_projection` would have written `attempts=1` for it
   and `TRANSITIONS` has no `in-progress -> pending` edge, which is why the in-progress
   projection now happens inside the worker after the cancel check. `combined_usage` counts
   NOTES outcome lines' `attempts=`, not raw ledger events, so a test of "spend not refunded"
   reads `combined_usage`, not `ledger.usage()`.
17. **`Scheduler._record(ledger, kind, **fields)` reserves `kind`.** A ledger field named
   `kind` collides with the event kind; the violation event's field is `violation`.
18. **A same-size rewrite within one second reuses a stale `.pyc`.** A fixture check that
   `import`s the module the candidate edits judged the pre-fix bytecode: pyc headers keep
   the source mtime in whole seconds and `return 1` / `return 2` have the same size. The
   strict fixture in `tests/test_workflow_eval.py` `exec`s the source instead. Any test
   whose stub rewrites a Python file and then imports it is exposed.
19. **`routing_policy.catalog_from_pricing`'s `estimator` must return a dict.** It is
   `codex_policy.default_estimator`'s shape (`{"api_equivalent_usd", "profile"}`), and
   `decide` reads `.get` on it; a bare float raises inside `_estimate`.
20. **`kit_contract.budget_gate` and `start_task_lifecycle` call `sys.exit`.** They are
   driver entry points. A loop that runs many kits (the evaluator) uses the primitives
   underneath (`parse_plan_budget` + `combined_usage` + `BudgetAdmission`; `open_ledger`
   + `TaskRun.begin`) so one kit's refusal is a record, not the end of the process.
21. **The census pins moved again**: 28 sources / 30 page-map keys / 72 pages, and the
   "one more" targets 29 / 31 / 73 (step 25, `docs/WORKFLOW-EVAL.md`).
22. **Patch `POLYTROPOS_DATA_HOME` in `setUpModule`, never at import.** Discovery imports
   every test module before any test runs, so an import-time `os.environ[...] = ...` leaks
   into every other module and every subprocess they spawn: the first full run of step 25
   moved `test_lessons_promote`'s default `journal/promotions` path out of the tree and
   failed a test that had nothing to do with the change. Trap 7's block is the pattern.
23. **Every command the release checklist cites goes through `release_gate.command_findings`.**
   Its first run caught its own data naming `lessons_store.py record` (the subcommand is
   `observe`). A script without `build_parser` (`runtime_data`, `kit_contract`,
   `sync_pricing_refs`) is checked for existence only, so cite its subcommands carefully.
24. **A YAML comment that mentions a credential reads as a grant to a line-based check.** The
   workflow's header comment names `pages: write` and `id-token: write`; the packaging review
   strips comments first (`_strip_yaml_comments`, not a YAML parser) and a test pins that a
   comment is not a grant.
25. **`tests/test_privacy_layout.PRIVATE_DIRS` is `runtime_data.STORES` now.** It had stopped at
   five while the engines had eight stores. Adding a store means: `runtime_data.STORES`, a
   root-anchored `.gitignore` rule, the CLAUDE.md store list, PRIVACY.md's table — and
   `release_gate.py packaging` names the missing rule before the privacy test does.
26. **The census pins moved again**: 29 sources / 31 page-map keys / 73 pages, and the
   "one more" targets 30 / 32 / 74 (step 26, `docs/RELEASE.md`).
27. **The generated block of `docs/RELEASE.md` must stay deterministic.** No date, revision,
   dirty count, interpreter version, or test result goes into `render_block`; those live in
   the live `check` output. `binary_name` loads four driver modules to read parser defaults,
   which is deterministic but not free — `harness_matrix(with_binaries=False)` where speed matters.

---

## Known gaps, deliberately left open

Each is recorded in `SECURITY.md` rather than hidden. None is a surprise; all are honest limits.

- **Model dispatch is not confined and cannot be under subscription auth.** Measured: Seatbelt
  blocks Keychain access, so a confined `claude -p` reports "Not logged in". Entitlement-gated,
  not fixable by profile rules.
- **No Linux or Windows sandbox backend.** `--exec-mode enforced` refuses there rather than
  downgrading silently.
- **Benchmark candidates and judges are not confined.** `repo_bench` builds history-free
  sandboxes and withholds reference tests structurally, but dispatch runs with driver privileges.
- **Role names are not permissions.** Since step 06 no review dispatch carries a blanket grant
  (this bullet used to say the opposite; `SECURITY.md` was corrected on 2026-09-12 and this line
  on 2026-09-13). What remains: Copilot has no citable per-tool flag, so its restricted review is
  only the absence of `--allow-all-tools`; inventing a narrower pin was refused.
- **Execution state is not tamper-proof.** The attempt ledger is outside the workspace, so the
  confined verify path cannot reach it; a dispatch is unconfined and a worker with the user's
  privileges can write anywhere the user can. `TASKS.md`/`NOTES.md`/markers stay in the tree; a
  worker's own status flip is overwritten by the driver's verdict and reported, not prevented.
- **The ledger is not exactly-once.** It knows a call was made, closes a resultless one as
  unknown, never replays it, and cannot know whether the provider billed it.
- **`evidence:` gating is wired into Claude's driver only.** Copilot and Codex parse the field
  but do not gate on it.
- **`mkdocs build --strict` was never run locally.** The lock targets Linux and the toolchain is
  not installed here. The drift gate that runs before it passes; the build itself is unexercised
  until CI runs it.

---

## Waiting on you

- **Private vulnerability reporting** — you enabled it; `SECURITY.md`'s callout was removed.
  ✅ done.
- **GitHub repo settings the code cannot touch**, now named in `SECURITY.md`: Pages source set to
  "GitHub Actions", Dependabot (nothing auto-updates now that actions are SHA-pinned and the
  toolchain is hash-locked), and secret scanning / push protection.
- **Existing Copilot users will see conflicts on their first update** after step 11. Files
  installed before the ownership manifest existed classify as unmanaged if they differ from the
  current bundle. `harness_select install --harness copilot --adopt-existing` clears it in one
  run, keeping a `.polytropos-bak` of each. That is the honest cost of no longer overwriting
  silently, but it is visible and worth expecting.
- **Merged.** `harden/roadmap-steps-01-15` was fast-forwarded into `main` and pushed on
  2026-09-12, and `harden/roadmap-steps-16-26` (steps 16–26) the same way on 2026-09-15. Any
  further work starts on a fresh branch off `main`; the commit rule forbids committing on `main`
  directly.

---

## Resuming

```bash
cd /Users/michaelcave/Developer/reposV2/polytropos
python3 -m unittest discover -s tests          # expect OK (2 skipped), ~4 min; the count is in the last commit that changed it
git log --oneline -12                          # steps 16–26 on top of the merged 01–15
python3 bin/release_gate.py check              # the release gate: registry, contract ids, packaging, commands, doc block
python3 bin/release_gate.py contracts          # stub conformance beside installed-client verification, per contract
python3 bin/runtime_data.py where              # where your stores resolved to
python3 bin/harness_adapter.py                 # what each harness can actually do
python3 bin/attempt_ledger.py demo             # crash / resume / progress walkthrough, temp dir only
python3 bin/attempt_history.py demo            # the cross-harness join, temp dir only
python3 bin/kit_contract.py demo               # a diamond DAG walked, an interrupted kit, four invalid graphs
python3 bin/routing_policy.py demo             # both routing policies over two synthetic rosters
python3 bin/codex_execute.py prepare --model strong --policy adaptive --explain   # the real roster, no dispatch
python3 bin/kit_contract.py roster --kit .claude/kits/docs-site --executor codex   # a declared roster a driver cannot run
python3 bin/graph_ground.py demo               # stamp / freshness / bounded impact / search fallback, temp tree, canned git
python3 bin/lessons_store.py demo              # an anecdote refused, recurrence promoted, a rule contested, temp store
python3 bin/cursor_adapter.py demo             # identity accept/refuse, argv, install states, ambient diagnosis, temp dirs
python3 bin/cursor_execute.py run --kit .claude/kits/docs-site --dry-run   # the Cursor argv; spawns nothing
python3 bin/kit_scheduler.py demo              # two tasks batched and integrated, a conflict kept, a sized manifest
python3 bin/kit_contract.py freshness --kit .claude/kits/docs-site   # stale evidence, if any (exit 1)
python3 bin/workflow_eval.py demo              # three workflows on a stub harness, the card, a refused proposal; temp dirs only
python3 bin/workflow_eval.py policy            # the routing policy in force (none until someone applies one)
```

Then read step 26 in the roadmap and continue. The pattern that has worked: verify the step's
claims against HEAD first, implement, run the affected suites, then the full suite, then update
`SECURITY.md` / `CLAUDE.md` / the doc mirrors together.
