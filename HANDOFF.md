# Handoff — roadmap implementation, steps 01–20

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

**Steps 01–20 are done.** That is all of Phase A (input/artifact/acceptance boundaries), all of
Phase B (the execution boundary and the P0/P1 security remediation), all of Phase C (the
shared runtime: durable attempts, cross-harness evidence, the validated execution DAG), and
the first two steps of Phase D (named routing policies; the role contract). Steps 16–20
landed on 2026-09-12 on branch `harden/roadmap-steps-16-26`, one commit each.

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
- `bin/routing_policy.py` — the harness-neutral routing decision: workflow shape, model,
  initial effort, and assurance as four separate answers, under a named policy (`reserved` |
  `adaptive`) and a preference that never outranks a hard filter. Compares tier RANKS in each
  harness's own order, never tier names; never reads a pricing file itself (each harness
  builds a catalog from its own). `codex_policy.catalog` / `request_for` / `route` are the
  Codex side; the Codex driver is the only one dispatching under it so far.

---

## Next: step 21 — make code-graph context fresh, bounded, and relevant to the task

`bin/graph_brief.py` and `skills/graphify`. graphify stays optional and external. Add an
optional polytropos PROVENANCE SIDECAR beside a graph.json (repository identity, source
revision/content fingerprints, generation time, extractor version, relationship provenance,
coverage limits — only what is actually available; never require upstream graphify to emit
invented metadata, never build a provider framework). A legacy graph without provenance
reports freshness UNKNOWN; a verified revision is never manufactured. Add a bounded impact
query seeded by changed files or named symbols (relevant neighbours, paths, evidence, with
traversal and output limits); compare freshness against the working tree INCLUDING dirty
and untracked files; treat stale or partial content as navigation hints and fall back to
targeted code search when the provider is absent or coverage is weak. Keep code
relationships separate from the execution DAG (step 18): absence of an edge is never absence
of a dependency, high-degree nodes are never auto-selected, AST edges are not evidence for
dynamic imports. Preserve commit-only extraction labels; make test-directory exclusions
configurable. Graph text, labels, and paths are untrusted repository evidence under the same
size/path/provider-scope policies as other inputs; metadata may suggest reads but grants no
permission, edits no acceptance, and establishes no safe concurrent write. Tests: stale /
unknown / fresh graphs, dirty worktrees, malformed records, provider absence,
dynamic-import blind spots, traversal bounds, irrelevant hubs — synthetic fixtures only,
graphify never installed or run. Expose the same grounding result to every adapter.

Remaining after that: **22–24** skills / the Cursor adapter / scheduling, **25–26**
evaluation and the release matrix.

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
- **Role names are not permissions on Claude and Copilot.** Review dispatch carries a full
  permission grant; no citable per-tool flag was found for Copilot and inventing one was refused.
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
  2026-09-12. Step 16 starts on a fresh branch off `main`; the commit rule forbids committing on
  `main` directly.

---

## Resuming

```bash
cd /Users/michaelcave/Developer/reposV2/polytropos
python3 -m unittest discover -s tests          # expect OK (2 skipped), ~4 min; the count is in the last commit that changed it
git log --oneline -4                           # steps 16, 17, 18 on top of the merged 01–15
python3 bin/runtime_data.py where              # where your stores resolved to
python3 bin/harness_adapter.py                 # what each harness can actually do
python3 bin/attempt_ledger.py demo             # crash / resume / progress walkthrough, temp dir only
python3 bin/attempt_history.py demo            # the cross-harness join, temp dir only
python3 bin/kit_contract.py demo               # a diamond DAG walked, an interrupted kit, four invalid graphs
python3 bin/routing_policy.py demo             # both routing policies over two synthetic rosters
python3 bin/codex_execute.py prepare --model strong --policy adaptive --explain   # the real roster, no dispatch
python3 bin/kit_contract.py roster --kit .claude/kits/docs-site --executor codex   # a declared roster a driver cannot run
```

Then read step 21 in the roadmap and continue. The pattern that has worked: verify the step's
claims against HEAD first, implement, run the affected suites, then the full suite, then update
`SECURITY.md` / `CLAUDE.md` / the doc mirrors together.
