# PLAN — fusion-tier1

Apply three learnings from Cognition's "Devin Fusion" multi-model orchestration write-up to
this plugin, **Tier 1 only** — all three land inside the plugin, no upstream changes:

1. **Warm sidekick** — `/execute` today spawns a fresh, cold implementer per task; each one
   re-reads the same files and pays a cold prompt-cache start. Fusion's structural edge is a
   persistent cheap agent holding cached context. The plugin cannot warm its DRIVER (the main
   session), but it CAN warm a SIDEKICK: for a cohesive task cluster, reuse ONE implementer
   across the cluster by continuing it (SendMessage + the agent id) instead of spawning N
   cold agents. Fresh parallel fan-out stays the default for `independent:` tasks.
2. **Lean driver** — Fusion's main agent takes minimal actions and by default delegates and
   monitors. In this plugin's cost model the orchestrator's context is the single most
   expensive thing in a run (priced, cached, re-sent every turn); every inline grep/read
   bloats it. `/execute` gets an explicit operating rule: delegate reads and independent
   verification to cheap scouts that return conclusions only.
3. **Quality scorecard** — Fusion validates on real merged PRs; this plugin measures only
   dollars and merely *asserts* near-Fable quality. New stdlib script
   `bin/routing_scorecard.py` turns an executed kit's outcomes into a routing-quality
   scorecard (first-try pass rate, escalations, blocked tasks, model mix, cheap-model review
   survival, dollars vs an all-frontier counterfactual), fed by a new machine-readable
   `outcome:` ledger that `/execute` appends to NOTES.md.

The one Fusion trick NOT buildable inside a plugin — switching the MAIN session's model at
context-compaction boundaries — is documented as a known limitation / upstream ask
(`docs/FUSION-TIER1.md`), never built. Tier 2 (dynamic mid-kit re-routing, an opt-in autonomy
dial) is an explicit planned FOLLOW-UP kit — out of scope here.

## Goal

Ship, end to end, with the full suite staying green and the architect/execute shared kit
contract provably intact:

1. **`skills/execute/SKILL.md` reworked** (body only, frontmatter untouched): a new
   `## Operating rule — lean driver` section, a new
   `## Dispatch modes — fresh fan-out vs warm sidekick` section, a new
   `## Outcome ledger — one line per finished task` section, and matching one-line touches to
   loop steps 2–5, the escalation valve, and End of run. Every existing contract element
   survives verbatim (the pinned grep list below).
2. **`skills/architect/SKILL.md` synced** (body only): the NOTES.md bullet now mentions the
   `outcome:` ledger, and a new bullet tells architects to flag warm-cluster candidates as
   free text in the TASKS.md dispatch preamble — a hint, NOT a new task field.
3. **`bin/routing_scorecard.py`** — stdlib-only, read-only CLI: parses a kit's TASKS.md (via
   `copilot_execute.parse_tasks`, reused) and NOTES.md `outcome:` lines (tolerant), computes
   the quality metrics, optionally folds in one session's dollars vs the all-frontier
   counterfactual (via `session_cost` functions, reused), and emits human markdown or
   `--json`. `--demo` runs the whole pipeline against a built-in synthetic kit + synthetic
   transcript in a temp dir — the sanctioned smoke test.
4. **`tests/test_routing_scorecard.py`** — stdlib unittest, synthetic fixtures in temp dirs,
   never the real `~/.claude`.
5. **`docs/FUSION-TIER1.md`** — the borrows, the ledger grammar, the scorecard, the upstream
   limitation, and the Tier-2 deferral. Plus two pinned README insertions and one pinned
   CLAUDE.md run-line (T8).

**Done looks like:** `python3 -m unittest discover -s tests` green (baseline 300 tests, plus
the new file); `python3 bin/sync_pricing_refs.py --check` exits 0; the T4 verify's dual-file
contract grep passes (every pinned element present in BOTH skills, frontmatter intact);
`python3 bin/routing_scorecard.py --demo` prints a scorecard with the five pinned H2s and
`--demo --json` parses with `schema_version: 1` and the pinned demo numbers;
`git status` shows changes ONLY to the sanctioned targets (edits: `skills/execute/SKILL.md`,
`skills/architect/SKILL.md`, `README.md`, `CLAUDE.md`; new: `bin/routing_scorecard.py`,
`tests/test_routing_scorecard.py`, `docs/FUSION-TIER1.md`, this kit + its agents);
`git diff --quiet -- bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data
skills/route skills/fable-check` stays clean.

## Repo facts (confirmed by the architect — trust these, do not re-derive)

- **The shared kit contract** (CLAUDE.md invariant; both skills must keep expressing it):
  layout `.claude/kits/<slug>/PLAN.md` + `TASKS.md` (+ `NOTES.md`, owned by execute); task
  fields `id`, `title`, `status`, `model`, brief, acceptance, verify; status vocabulary
  exactly `pending | in-progress | done | blocked`; `## Phase N — <name>` headings;
  `depends:`/`independent:` marking; and the rule that a task's `model` field overrides the
  implementer agent's frontmatter at dispatch (execute passes it as the Agent tool's `model`
  parameter).
- **This plugin is installed LIVE** from this directory — skill files are runtime behavior.
  Their YAML frontmatter (`name:`, `description:`) must never be touched by this kit.
- **The Agent tool contract** (how warmth works): spawning returns an agent id; SendMessage
  with that id continues the agent with its context intact; a continued agent keeps its
  spawn-time model — there is no model override on continuation. That last fact is why warm
  clusters require identical `model` pins.
- **Reuse functions** (all loaded read-only via the importlib `_load` pattern —
  `spec_from_file_location(name, Path(__file__).resolve().parent / f"{name}.py")` — exactly
  as `bin/journal_sources.py` and `bin/session_cost.py` already do):
  - `copilot_execute.parse_tasks(text)` → list of dicts `{id, title, status, model, depends,
    independent, brief, verify}`; raises ValueError on a malformed status. Task headings are
    `### <id> — <title>` with a spaced em dash.
  - `session_cost` (as `sc`): `find_main_transcript(session_id, projects_dir)`,
    `discover_task_dirs(session_id)`, `gather_files(main, task_dirs, includes)`,
    `collect(files, pricing)`, `resolve_counterfactual_model(arg, pricing)` (arg None → the
    first `tier == "frontier"` model in pricing file order),
    `build_report(data, cf_key, pricing, mode)` (returns `actual_total`, `cf_total`,
    `cf_key`, `cf_display`, `savings`, `ratio`, `rows`, `grand`), and the constant
    `DEFAULT_PROJECTS_DIR` (the ONLY place `Path.home()` may enter the scorecard — borrow it,
    never call `Path.home()` yourself).
  - `session_cost` loads `cost_report` internally as `sc.cr` — alias `cr = sc.cr` instead of
    loading cost_report twice. `cr.load_pricing()`, `cr.price(key, u, when, pricing)`,
    `cr.EXPENSIVE_TIERS == {"frontier", "opus"}` (the structural tier-vocabulary precedent).
- **pricing.json tier vocabulary:** `frontier`, `opus`, `sonnet`, `haiku`. Kit task `model`
  values are the Agent-tool aliases `fable | opus | sonnet | haiku`. The alias→tier map is
  identity except `fable → frontier`.
- **NOTES.md is free-form prose today** (see `.claude/kits/daily-journal/NOTES.md`) — the
  scorecard must tolerate kits with no ledger lines at all.
- **Suite:** `python3 -m unittest discover -s tests [-p '<file>.py']` — never the
  dotted-module form (broken on this machine). Baseline 300 tests, green.

## Architecture & key decisions

- **D1 — Warm sidekick = a continued implementer, opt-in, cluster-scoped.** `/execute` gets a
  `## Dispatch modes` section: fresh parallel fan-out remains the DEFAULT for `independent:`
  tasks with disjoint files (unchanged rule); a warm sidekick serves only a *cohesive
  cluster* — a maximal run of tasks that (a) form a serial `depends:` chain within one phase,
  (b) share a primary file or subsystem (same file in their briefs, or a TASKS.md-preamble
  hint), and (c) carry the SAME `model` value. Requirement (c) is load-bearing: SendMessage
  cannot change a continued agent's model, so serving a differently-pinned task warm would
  silently violate the model-override contract — a model change always ends the cluster.
  Rationale: the cluster is exactly where N cold cache starts are pure waste (daily-journal's
  T2→T3→T4 same-file chain is the canonical case), while independent tasks get zero benefit
  and lose parallelism.
- **D2 — Warmth has a cost, and the skill says so.** A warm agent accumulates context and
  eventually needs compaction, which destroys the cache advantage. Pinned guidance: cap a
  warm sidekick at ~4 tasks, end it early on degraded replies or reported context pressure,
  and record warm-cluster use in NOTES.md. Verification is NEVER warmed — the verifier agent
  is always a fresh spawn, because its value IS adversarial fresh context. Continuation
  messages stay contract-shaped: the next task's self-contained brief verbatim, prefixed only
  with "Previous cluster task is done; next task:".
- **D3 — Cluster detection is a heuristic plus free-text hints — NOT a new task field.** The
  architect skill gains a bullet: flag warm-cluster candidates in the TASKS.md dispatch
  preamble as free text (precedent: daily-journal's "T2 → T3 → T4 are strictly serial (same
  file)" line). The task-field contract (`id`, `title`, `status`, `model`, brief, acceptance,
  verify + `depends:`/`independent:`) is byte-for-byte unchanged; old kits stay executable;
  `parse_tasks` needs no change. This is the single most important scoping decision in the
  kit: the shared contract is an invariant, so the feature rides on existing fields.
- **D4 — Lean driver: pinned read-set, everything else delegated.** New `## Operating rule —
  lean driver` section in `/execute`: the orchestrator reads ONLY kit state (PLAN.md,
  TASKS.md, NOTES.md) plus the output of verify commands it runs; every exploratory read,
  grep, and failure investigation is delegated to a cheap scout (Agent tool, `model: haiku`)
  or the kit's verifier agent, which return few-line conclusions, never file dumps. The
  orchestrator STILL runs each task's verify command itself — that invariant (CLAUDE.md: your
  claim without its output counts as failure) is untouched; lean means it keeps only the
  decisive tail of long output and never digs inline. Rationale: every byte in the driver's
  context is re-priced on every later turn AND brings compaction closer, so delegation is
  cheaper twice.
- **D5 — The outcome ledger: one pinned machine-readable line per finished task, appended to
  NOTES.md by execute.** Grammar (pinned; the scorecard's parser and the skill text must
  match):
  `outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>`
  where `result` ∈ `pass` (first dispatch, verify passed) | `retry-pass` (passed on the
  retry) | `escalated-pass` (passed only via the escalation valve) | `blocked`; `review` ∈
  `clean` (verifier/reviewer accepted unchanged) | `revised` (changes required after the
  implementer claimed done) | `none` (no independent review beyond the verify command);
  `attempts` = implementer dispatches including retries/escalation; `model` = what the task
  actually ran on (the pin, or the escalation target). Parsing is TOLERANT: optional leading
  `-`/`*` bullet, unknown `key=value` pairs ignored (forward-compatible), unknown `result`
  vocabulary skipped with a note, last line per task id wins (re-runs append). NOTES.md is
  execute-owned, so adding a line format inside it is NOT a contract change; the architect
  skill's NOTES.md bullet just mentions it exists.
- **D6 — The scorecard is a read-only consumer that reuses, never re-implements.**
  `bin/routing_scorecard.py` loads `copilot_execute` (TASKS.md parsing) and `session_cost`
  (transcript dollars) via the importlib `_load` pattern and NEVER edits them. Quality comes
  from two layers: TASKS.md statuses (always available — `done`/`blocked` counts survive even
  with zero ledger lines) enriched by NOTES.md `outcome:` lines when present. Missing
  NOTES.md, or a ledger-free NOTES.md, degrades to status-only output with an explicit note —
  never a crash, never invented numbers. Zero-denominator rates are `null`/`n/a`, never a
  fabricated 0%.
- **D7 — Metric definitions (pinned).** Over tasks with a recognized outcome line:
  `first_try_pass` = count of `result=pass`; `retry_pass`, `escalated_pass`, `blocked`
  likewise; `first_try_rate` = first_try_pass / with_outcome; `escalation_rate` =
  escalated_pass / with_outcome. Model mix = task count per *effective model* (the outcome
  line's `model=`, else the task's `model` field, else `unspecified`). Cheap-model review
  survival: a task is CHEAP iff `TASK_MODEL_TIERS.get(alias, alias)` is NOT in
  `cr.EXPENSIVE_TIERS`, where `TASK_MODEL_TIERS = {"fable": "frontier"}` (structural
  vocabulary mapping the Agent-tool alias to the pricing tier — the sanctioned exception to
  the no-model-literals rule, mirroring `EXPENSIVE_TIERS` itself); `cheap_reviewed` = cheap
  tasks with `review != none`; `survival_rate` = share of those with `review == clean`. This
  is the Fusion "quality retained" number: how much cheap-model output survived independent
  review unchanged.
- **D8 — Dollars are optional and computed by session_cost, all-frontier by default.** With
  `--session <id>` (+ `--projects-dir`, `--tasks-dir`…, `--include`…, `--no-subagents`,
  `--vs`), the scorecard drives `sc.find_main_transcript → gather_files → collect →
  resolve_counterfactual_model → build_report` and reports
  `{session, files_scanned, actual_usd, counterfactual_usd, counterfactual_model
  {key, display}, delta_usd, ratio, pricing_cached}`. The counterfactual model comes from
  pricing.json at run time (first frontier-tier model; `--vs` overrides) — no hardcoded id
  anywhere. No `--session` → `cost: null` plus the note `"no session provided — pass
  --session to fold in transcript dollars"`. The real `~/.claude/projects` default is
  RUNTIME-only (borrowed from `sc.DEFAULT_PROJECTS_DIR`); every test and verify overrides
  `--projects-dir` to a temp fixture.
- **D9 — `--demo` is the sanctioned smoke test and it exercises the REAL pipeline.** Demo
  builds, in a `tempfile.TemporaryDirectory`, a synthetic kit (module constants
  `DEMO_TASKS_MD` / `DEMO_NOTES_MD`, six tasks D1–D6, models only as aliases
  haiku/sonnet/fable) AND a synthetic session transcript whose model ids are COMPUTED at run
  time (first model of each available tier in `data/pricing.json` file order) with pinned
  token VOLUMES (token counts are not prices — hardcoding them is sanctioned), then runs the
  normal scorecard path against it and cleans up. Expected demo quality numbers (pinned, used
  by verify): total 6, with_outcome 6, first_try_pass 3, retry_pass 1, escalated_pass 1,
  blocked 1, model mix {haiku 1, sonnet 4, fable 1}, cheap_reviewed 4, cheap_clean 3,
  survival 0.75. Demo dollars assert structure only (actual > 0, delta == cf − actual) —
  never pricing values.
- **D10 — Output contracts (pinned).** Markdown: H1 `# Routing scorecard — <kit>`; exactly
  these five H2s in order: `## Verdict`, `## Task outcomes`, `## Model mix`,
  `## Review survival`, `## Dollars`; the Verdict is one bold summary line; unavailable
  numbers render `n/a`, with the reason in the notes. JSON (`--json`): top-level keys exactly
  `schema_version` (1), `kit`, `generated_at`, `tasks`, `quality`, `model_mix`, `review`,
  `cost`, `notes` — `quality` keys `total, with_outcome, first_try_pass, retry_pass,
  escalated_pass, blocked, first_try_rate, escalation_rate` (rates float or null); `review`
  keys `cheap_reviewed, cheap_clean, survival_rate`; `cost` the D8 dict or null. Exit 0 on
  success (including degraded output); `sys.exit(message)` on unusable input (no kit and no
  `--demo`, kit dir/TASKS.md missing, `parse_tasks` ValueError, bad `--vs`).
- **D11 — The upstream limitation is documented, not built.** `docs/FUSION-TIER1.md` states:
  nothing in a plugin can switch the MAIN session's model — only the user via `/model` — so
  Fusion's cheap-driver-after-compaction trick (swap the driver to a cheaper model at
  context-compaction boundaries, where the cache is invalidated anyway) needs Claude Code /
  the Agent SDK to expose main-session model control; until then the plugin's equivalents are
  the warm sidekick + lean driver. README's existing "Key constraint to know" section gains
  one pinned sentence pointing there. Tier 2 (dynamic mid-kit re-routing off scorecard
  feedback, an opt-in autonomy dial) is named there as the planned follow-up kit.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Break the architect/execute shared kit contract.** No new required task field, no status
  vocabulary change, no removal/rewording of any pinned contract element (the T4 grep list) in
  EITHER skill. Skill edits are BODY-only — never touch the YAML frontmatter of any
  `skills/*/SKILL.md` (the plugin is installed live; frontmatter is load-bearing). If a brief's
  anchor text is not present verbatim, STOP and report — do not approximate.
- **Build Tier 2 or the upstream item.** No dynamic mid-kit re-routing, no autonomy dial, no
  attempt to switch or automate the MAIN session's model (compaction-boundary switching is
  documented in docs/FUSION-TIER1.md only). No changes to `/route`, `/escalate`,
  `/fable-check`, or any skill other than execute + architect.
- **Edit `bin/cost_report.py`, `bin/session_cost.py`, or `bin/copilot_execute.py`** — the
  scorecard reuses them read-only via importlib. No edits to ANY existing `bin/` or `tests/`
  file, `data/` (either pricing file), `.claude-plugin/`, `copilot/`, the generated
  `skills/*/references/` mirrors, or the completed kits and their agents.
- **Hardcode prices, price ratios, or real model ids** in any new or edited file. Sanctioned
  exceptions: tier-vocabulary strings (`frontier`/`opus`/`sonnet`/`haiku`), the Agent-tool
  alias map `TASK_MODEL_TIERS = {"fable": "frontier"}`, synthetic fixture ids/values in
  tests, and pinned token VOLUMES in the demo (counts, not prices). Demo model ids are
  computed from `data/pricing.json` at run time.
- **Read the real `~/.claude` from any test or verify command.** The scorecard's
  projects-dir default is runtime-only; every test/verify passes `--projects-dir` (and
  explicit `--tasks-dir`/`--no-subagents`) against temp fixtures. `Path.home()` count in
  `bin/routing_scorecard.py` and `tests/test_routing_scorecard.py`: ZERO (the default is
  borrowed from `sc.DEFAULT_PROJECTS_DIR`).
- **Write anywhere at run time** except: the scorecard's `--demo` temp dir, and test temp
  dirs. The scorecard never writes into a kit dir, never modifies NOTES.md, never touches
  `~/.claude`. Nothing outside this repo, ever; no plugin re-install.
- **Add dependencies or tooling.** Python stdlib-only; no pip/pytest/requirements; no
  network; no Copilot-side changes (`copilot/`, `data/pricing.copilot.json` untouched —
  Claude-side first).
- **Commit or push.**

Sanctioned edit targets among existing files: `skills/execute/SKILL.md` (T1–T3),
`skills/architect/SKILL.md` (T4), `README.md` + `CLAUDE.md` (T8, pinned insertions only).
Sanctioned new files: `bin/routing_scorecard.py`, `tests/test_routing_scorecard.py`,
`docs/FUSION-TIER1.md`.

## Risks & tripwires

- **Breaking the shared contract — THE #1 RISK.** The two skills are live runtime behavior
  and every existing kit depends on their contract. TRIPWIRES: any pinned grep string from
  the T4 verify missing from either skill; a skill file whose first line is no longer `---`
  or whose `name:`/`description:` frontmatter changed; a new REQUIRED task field or marker
  appearing in either skill's text; `parse_tasks` needing modification for anything in this
  kit. Any hit → stop, revert the edit, report.
- **Warm sidekick violating the model-pin rule.** A continued agent keeps its spawn model.
  TRIPWIRE: skill text that permits continuing a warm agent across a `model` change, that
  makes warmth the default, that warms the verifier, or that drops the ~4-task cap /
  compaction warning. The `independent:` fresh fan-out sentence must survive unchanged.
- **The scorecard inventing quality.** NOTES.md ledger lines may be absent (every kit
  executed before this one). TRIPWIRES: a crash on missing NOTES.md or ledger-free notes; a
  rate rendered as `0%` when its denominator is 0 (must be `null`/`n/a` + note); an
  unrecognized `result` silently coerced instead of skipped-with-note; dollars shown without
  `--session` data.
- **Editing the reused scripts.** TRIPWIRE: `git diff --quiet -- bin/cost_report.py
  bin/session_cost.py bin/copilot_execute.py` failing at any point → stop and revert.
- **Same-file serialization.** T1 → T2 → T3 all edit `skills/execute/SKILL.md` and are
  STRICTLY serial (and, being same-file + same-model, are themselves a warm-cluster
  candidate). TRIPWIRE: parallel dispatch of any two of T1/T2/T3, or T4 starting before T3
  is done.
- **Anchor drift in prose edits.** The skill briefs pin exact old/new strings. TRIPWIRE: an
  anchor not found verbatim — report, never fuzzy-match; duplicated sections from re-running
  an edit (grep counts in verifies guard this: each new H2 must appear exactly once).
- **Suite/path quirks.** Verify with `python3 -m unittest discover -s tests
  [-p '<file>.py']` — never the dotted-module form. Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` session-scratchpad path in any deliverable. Run
  `python3 bin/sync_pricing_refs.py --check` after skill edits (it must stay exit 0 — this
  kit gives it no reason to drift, so a failure means an out-of-fence edit).

## Still deferred after this kit (named, not built)

1. **Tier 2 — dynamic mid-kit re-routing:** let the execute loop consult live scorecard
   numbers (e.g. sonnet's first-try rate this kit) and re-pin later tasks' models mid-run,
   behind an opt-in autonomy dial in PLAN.md. Follow-up kit; the outcome ledger built here is
   its data substrate.
2. **Upstream — main-session model switching at compaction boundaries:** needs Claude Code /
   Agent SDK support; tracked as the upstream ask in docs/FUSION-TIER1.md.
3. **Scorecard-over-time:** aggregating scorecards across kits (a routing track record per
   model tier). The per-kit JSON output is the substrate; explicitly not in v1.
