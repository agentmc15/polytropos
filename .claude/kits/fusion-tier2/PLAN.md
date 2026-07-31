# PLAN — fusion-tier2

autonomy: advisory

(That line is not decoration — this kit BUILDS the optional PLAN.md `autonomy:` convention and
dogfoods it: this kit itself runs in advisory posture. Default when the line is absent is also
advisory, so the line is belt-and-braces plus a live example.)

Tier 2 of the Fusion borrows, building directly on the shipped `fusion-tier1` kit (warm
sidekick, lean driver, outcome ledger + `bin/routing_scorecard.py`). Two features, both riding
the Tier-1 outcome ledger as their data substrate:

1. **Dynamic mid-kit re-routing (UPGRADE-ONLY).** After each task's `outcome:` line lands,
   `/execute` consults a LIVE signal computed from the ledger-so-far: per-model-tier first-try
   pass rate THIS kit. When a tier's live rate drops below a threshold over a minimum sample of
   that tier's finished tasks, the loop upgrades that tier's REMAINING PENDING tasks up exactly
   ONE tier (haiku→sonnet, sonnet→opus). Never down. Never automatically to frontier/Fable —
   Fable stays reserved for the existing per-task, evidence-carrying escalation valve, whose
   mechanism is unchanged.
2. **Opt-in autonomy dial.** OFF by default = ADVISORY: the loop only PRINTS the re-routing
   recommendation and the human decides; nothing is auto-changed. ON = the loop acts on the
   upgrade-only signal automatically (behind a budget guardrail capping auto-upgrades), AND a
   blocked task auto-consults Fable through the existing valve without pausing to ask. The dial
   is per-kit (optional `autonomy:` line in PLAN.md, default advisory) with a per-run user
   override at invocation.

The #1 invariant this kit must thread: **the architect/execute shared kit contract stays
byte-intact.** The clean design that makes both features contract-safe: a re-route is a
**runtime orchestrator override applied at dispatch and LOGGED — never a rewrite of the
TASKS.md `model` field** (see D3).

## Goal

Ship, end to end, with the full suite staying green, the shared kit contract provably intact,
and `bin/routing_scorecard.py` extended additively:

1. **`bin/routing_scorecard.py` extended** (additive only): pinned live-policy constants, pure
   tested functions (`parse_reroutes`, `parse_autonomy`, `effective_alias`, `live_tier_stats`,
   `upgrade_decision`, `build_live_card`, `render_live_markdown`), a `--live` CLI mode (plus
   `--live-threshold` / `--live-min-sample` / `--live-max-auto` knobs), and a `--demo --live`
   synthetic smoke. Existing flags, output shapes, exit codes, and the Tier-1 `--demo` numbers
   are byte-stable; `tests/test_routing_scorecard.py` is untouched.
2. **`tests/test_reroute_live.py`** — new stdlib unittest file: pure-function coverage of the
   upgrade-only / never-frontier / min-sample / threshold / budget properties, CLI end-to-end
   against temp kits, the Tier-1-demo additive-regression check, and a read-only proof.
3. **`skills/execute/SKILL.md` reworked** (body only, frontmatter untouched): a new
   `## Live re-routing — upgrade-only, autonomy-gated` section between the Outcome ledger and
   the Escalation valve, plus pinned one-line touches to Setup step 2, loop steps 2 and 4, and
   the escalation-valve sentence (tying its existing "if running autonomously" parenthetical to
   the dial). Every existing contract element survives verbatim.
4. **`skills/architect/SKILL.md` synced** (body only): an optional-autonomy-posture bullet in
   Step 1 and a one-sentence extension of the model-authoritative bullet in Step 2 — then the
   dual-file contract audit (the CLAUDE.md invariant: touch either skill, re-check BOTH).
5. **`docs/FUSION-TIER2.md`** (new) + a pinned pointer paragraph appended to
   `docs/FUSION-TIER1.md`'s `## Deferred — Tier 2` section, and one pinned CLAUDE.md run-line.

**Done looks like:** `python3 -m unittest discover -s tests` green (baseline 332 tests, plus
`tests/test_reroute_live.py`); `python3 bin/sync_pricing_refs.py --check` exits 0;
`python3 bin/routing_scorecard.py --demo --json` still yields the Tier-1 pinned numbers
(quality 6/6/3/1/1/1, mix {haiku 1, sonnet 4, fable 1}, survival 0.75);
`python3 bin/routing_scorecard.py --demo --live --json` yields the D9 pinned live numbers (one
recommendation, sonnet→opus, tasks L5+L6, budget 0/2 applied); the T4 dual-file contract grep
passes (every pinned element in BOTH skills, frontmatter intact); `git status` shows changes
ONLY to sanctioned targets (edits: `bin/routing_scorecard.py`, `skills/execute/SKILL.md`,
`skills/architect/SKILL.md`, `docs/FUSION-TIER1.md`, `CLAUDE.md`; new:
`tests/test_reroute_live.py`, `docs/FUSION-TIER2.md`, this kit + its agents); and
`git diff --quiet -- tests/test_routing_scorecard.py bin/cost_report.py bin/session_cost.py
bin/copilot_execute.py data` stays clean throughout.

## Repo facts (confirmed by the architect — trust these, do not re-derive)

- **The shared kit contract** (CLAUDE.md invariant; both skills must keep expressing it):
  layout `.claude/kits/<slug>/PLAN.md` + `TASKS.md` (+ `NOTES.md`, owned by execute); task
  fields `id`, `title`, `status`, `model`, brief, acceptance, verify; status vocabulary exactly
  `pending | in-progress | done | blocked`; `## Phase N — <name>` headings;
  `depends:`/`independent:` marking; and the rule that a task's `model` field overrides the
  implementer agent's frontmatter at dispatch (execute passes it as the Agent tool's `model`
  parameter). This kit adds NO new required task field; the only new kit-file convention is the
  OPTIONAL PLAN.md `autonomy:` line. `copilot_execute.parse_tasks` needs no change.
- **This plugin is installed LIVE** from this directory — skill files are runtime behavior.
  Their YAML frontmatter must never be touched by this kit.
- **Tier-1 state of `skills/execute/SKILL.md`** (final section order — the new section slots
  between Outcome ledger and Escalation valve): `## Setup` → `## Operating rule — lean driver`
  → `## The loop` → `## Dispatch modes — fresh fan-out vs warm sidekick` →
  `## Outcome ledger — one line per finished task` → `## Escalation valve — blocked tasks go
  back to Fable, one at a time` → `## End of run`. The outcome-ledger grammar (pinned, already
  shipped): `outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>`
  with `result ∈ pass|retry-pass|escalated-pass|blocked`, `review ∈ clean|revised|none`;
  unknown `key=value` pairs are IGNORED by the parser (designed forward-compatibility — this
  kit's new `reroute:` lines simply do not match `OUTCOME_RE` and are invisible to Tier-1
  consumers). The escalation valve already contains the phrase `offer (or if running
  autonomously, do) a **targeted Fable consult**:` — Tier 2 formalizes what "running
  autonomously" means; the valve mechanism (per-task, evidence-carrying, `model: fable`
  subagent, `result=escalated-pass`) is unchanged.
- **`bin/routing_scorecard.py` today** (all reusable in place — extend, never fork):
  `_load(name)` importlib loader; `ce = _load("copilot_execute")`, `sc = _load("session_cost")`,
  `cr = sc.cr`; `TASK_MODEL_TIERS = {"fable": "frontier"}` and `tier_for(alias)`;
  `OUTCOME_RE` / `PAIR_RE` and `parse_outcomes(text) -> (outcomes, notes)` (tolerant,
  last-line-wins per task id); `build_scorecard(...)`; `run_demo(as_json)` with
  `DEMO_TASKS_MD`/`DEMO_NOTES_MD`/`DEMO_VOLUMES`; `_resolve_kit_dir(kit, kits_dir)`; `main()`
  argparse with `kit` positional, `--kits-dir`, `--session`, `--projects-dir`, `--tasks-dir`,
  `--include`, `--no-subagents`, `--vs`, `--json`, `--demo`. `ce.parse_tasks(text)` returns
  dicts `{id, title, status, model, depends, independent, brief, verify}`; task headings are
  `### <id> — <title>` with a spaced em dash; it raises ValueError on a malformed status.
- **pricing.json tier vocabulary:** `frontier`, `opus`, `sonnet`, `haiku`. Task `model` values
  are the Agent-tool aliases `fable | opus | sonnet | haiku`; alias→tier is identity except
  `fable → frontier`. The upgrade ladder is cheap→expensive `haiku < sonnet < opus < frontier`;
  upgrades stop BEFORE frontier, so every legal upgrade target (`sonnet`, `opus`) is both a
  tier name and its own Agent-tool alias — no alias translation needed on the upgrade path.
- **Suite:** `python3 -m unittest discover -s tests [-p '<file>.py']` — never the dotted-module
  form (broken on this machine). Baseline 332 tests, green.
  `python3 bin/sync_pricing_refs.py --check` must stay exit 0 (this kit gives it no reason to
  drift; a failure means an out-of-fence edit).

## Architecture & key decisions

- **D1 — The live signal: per-tier first-try rate over the ledger-so-far, with pinned
  attribution.** For each pricing tier, over this kit's tasks that already carry a recognized
  `outcome:` line: `completed` = count of outcomes attributed to the tier (all four results
  count); `first_try` = count with `result=pass`; `rate = first_try / completed` (None when
  completed is 0). **Attribution:** `pass` / `retry-pass` / `blocked` attribute to
  `tier_for(outcome["model"])` — the ledger's `model=` records what the task actually ran on,
  which for those results IS the model that produced the evidence. `escalated-pass` attributes
  to `tier_for(effective_alias(task, applied_events))` — the DISPATCH model reconstructed from
  the task's pin plus any prior applied re-routes — because the ledger's `model=` on an
  escalated line names the Fable fixer, while the failure evidence belongs to the tier that
  failed. Crediting frontier with a cheap tier's failure would both pollute frontier's stats
  and hide the struggling tier's signal. Rationale for the two knobs: `LIVE_MIN_SAMPLE = 3` is
  the smallest sample where a sub-majority pass rate is signal rather than a single unlucky
  task; `LIVE_RATE_THRESHOLD = 0.5` means "this tier fails first-try more often than it
  passes" — an intentionally conservative trigger for an intentionally cheap correction (one
  tier step). Both are CLI-tunable; neither is a price.
- **D2 — Upgrade-only, exactly one step, NEVER frontier.** A recommendation moves a tier's
  remaining PENDING tasks up exactly one rung of `LIVE_TIER_ORDER = ("haiku", "sonnet", "opus",
  "frontier")` — haiku→sonnet, sonnet→opus. Never down (a mid-run downgrade risks quality on
  the strength of a small sample and saves little; over-provisioning is reported at end of run
  for the HUMAN to re-pin the next kit). Never skipping a rung. And structurally never to
  frontier: when the struggling tier sits one rung under frontier (opus), `upgrade_decision`
  emits NO recommendation — only an `at_ceiling` flag and the pinned note
  `frontier locked: escalation valve only`. Reaching Fable stays exclusively the existing
  per-task, evidence-carrying escalation valve, which keeps Fable spend proportional to
  demonstrated difficulty rather than to a statistical trend. In-progress tasks are never
  re-routed — only `pending` ones.
- **D3 — A re-route is a runtime dispatch override, NEVER a TASKS.md `model`-field rewrite —
  THE contract-safety decision.** The shared contract says the task's `model` field overrides
  the implementer agent's frontmatter at dispatch. That stays TRUE, verbatim, in both skills:
  the pin remains the dispatch DEFAULT, and the field-beats-frontmatter precedence is untouched
  in all cases. What Tier 2 adds is an explicit, opt-in, logged, upgrade-only orchestrator
  layer ON TOP: when (and only when) the dial is `auto` and a logged `mode=applied` re-route
  covers a pending task, execute passes the upgraded alias as the Agent tool's `model`
  parameter instead of the pin. When the dial is off (advisory — the default), the pin is
  ALWAYS honored. TASKS.md is never rewritten by re-routing (`set_status` remains the only
  mid-run TASKS.md mutation), so `parse_tasks` needs no change, old kits stay executable, the
  ledger's `model=` already records "what the task actually ran on" (now: pin, upgrade target,
  or escalation target), and a later reader can always reconstruct pin vs actual from
  TASKS.md + NOTES.md. An applied upgrade also ENDS any warm cluster serving those tasks — a
  model change always ends a cluster (Tier-1 D1(c) — SendMessage cannot override a continued
  agent's model).
- **D4 — The `reroute:` ledger line: durable, machine-readable, execute-owned.** Grammar
  (pinned; the skill text and `parse_reroutes` must match):
  `reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>`
  NOTES.md is execute-owned, so adding a second line format inside it is NOT a contract change
  (precedent: the Tier-1 `outcome:` line), and Tier-1's `OUTCOME_RE` cannot match a `reroute:`
  line — old consumers are unaffected. The line is load-bearing, not decoration: the budget
  guardrail needs durable state that survives orchestrator compaction, and NOTES.md is the
  kit's durable state — `upgrade_decision` counts prior `mode=applied` lines to enforce the
  cap, and reconstructs each pending task's effective dispatch model from them
  (`effective_alias`). `mode=advisory` lines record printed recommendations (so an unchanged
  signal is not re-announced) and never consume budget. The ORCHESTRATOR appends these lines;
  `bin/routing_scorecard.py --live` is read-only and never writes one. Parsing is tolerant like
  `parse_outcomes`: optional `-`/`*` bullet, unknown keys ignored, malformed lines skipped with
  a note, `from`/`to` must be tier names and `mode` must be `advisory|applied` or the line is
  skipped with a note; a `to=frontier` line still parses (honest state reconstruction) but
  appends an out-of-policy note.
- **D5 — The autonomy dial: an optional PLAN.md line plus a per-run invocation override.**
  Declared as a single line in the kit's PLAN.md — `autonomy: advisory` or `autonomy: auto` —
  matched by `AUTONOMY_RE = ^\s*autonomy:\s*(advisory|auto)\s*$` (multiline, lowercase, first
  match wins; a line starting `autonomy:` with any other value is noted and treated as
  advisory). Absent line = advisory. Read precedence (pinned in the execute skill): an explicit
  user instruction at invocation ("execute <slug> autonomously" / "advisory") wins for that
  run, else the PLAN.md line, else advisory. The dial is read once at Setup. It is an OPTIONAL
  PLAN.md line — deliberately not a task field, not a TASKS.md marker, not frontmatter — so
  the task-field contract is untouched and kits without the line behave exactly as today.
  ADVISORY means print-only: the loop announces the recommendation (logging it once as
  `mode=advisory`) and changes NOTHING — every dispatch stays on the pin. `--live` reports the
  PLAN.md posture in its output (informational); the invocation override lives in the
  orchestrator's conversation and always wins over the reported posture.
- **D6 — The budget guardrail: a hard cap on applied auto-upgrades, counted from the ledger.**
  `LIVE_MAX_AUTO_UPGRADES = 2` applied re-route EVENTS per kit run (one event = one tier's
  remaining pending tasks upgraded, logged as one `mode=applied` line). Two is structurally
  sufficient: only haiku→sonnet and sonnet→opus are legal, and once a tier's pending tasks are
  upgraded there is nothing left of that tier to upgrade again (the decision converges) — so
  the cap is belt-and-braces against pathological loops, not a tuning knob. `upgrade_decision`
  always reports the full recommendation list (advisory printing must keep working after the
  budget is gone) plus `budget: {cap, applied, remaining}`; the SKILL rule is that auto mode
  applies recommendations only while `remaining > 0` and falls back to advisory printing at 0.
  Advisory-mode recommendations never consume budget.
- **D7 — Auto-escalation rides the EXISTING valve, unchanged in mechanism.** When the dial is
  `auto`, a task `blocked` after retry goes straight to the targeted Fable consult without
  pausing to ask — that is the whole change. Everything else about the valve is byte-identical
  in behavior: per-task, one at a time, carrying the brief + failure evidence + PLAN.md
  excerpts, `model: fable` subagent, `result=escalated-pass` recorded on success. The valve's
  existing parenthetical "(or if running autonomously, do)" already anticipated this; Tier 2
  replaces the vague phrase with an explicit reference to the dial. This is also exactly why
  re-routing may never reach frontier: the valve is the one Fable path, and it stays
  evidence-carrying and per-task even in auto mode.
- **D8 — The decision logic lives in `bin/routing_scorecard.py`, additively — not a new
  script.** Rationale: the live signal consumes exactly the inputs the scorecard already
  parses (`ce.parse_tasks` for TASKS.md, `parse_outcomes` for the ledger) and the same alias
  machinery (`TASK_MODEL_TIERS`, `tier_for`); a separate helper would either duplicate that
  plumbing or importlib-load routing_scorecard anyway; and one script keeps ONE surface for
  /execute to shell out to (`--live` mid-run, the plain scorecard at end of run). ADDITIVE
  means: new constants, new pure functions, new argparse flags, new render path — zero changes
  to existing function signatures, outputs, exit codes, or the Tier-1 demo numbers, and
  `tests/test_routing_scorecard.py` stays byte-untouched (enforced by `git diff --quiet` in
  every verify; new tests live in the new `tests/test_reroute_live.py`). The `--live` path
  loads NO pricing (quality-only — `cr.load_pricing()` is never called on it) and combining
  `--live` with `--session` is an error: dollars belong to the end-of-run scorecard.
- **D9 — `--live` CLI and demo contracts (pinned).** Invocation:
  `python3 bin/routing_scorecard.py <slug> --live [--json] [--live-threshold F]
  [--live-min-sample N] [--live-max-auto N]` (also honors `--kits-dir`; `--live` + `--session`
  → `sys.exit("--live takes no --session")`). Inputs: TASKS.md (required, as today), NOTES.md
  (optional — missing → empty outcomes/events + note), PLAN.md (optional — missing → advisory
  + note). JSON top-level keys exactly: `schema_version` (`LIVE_SCHEMA_VERSION = 1`), `kit`,
  `generated_at`, `autonomy`, `signals`, `recommendations`, `budget`, `notes`. `signals` maps
  every tier in `LIVE_TIER_ORDER` to `{completed, first_try, rate (float|None),
  below_threshold (bool), at_ceiling (bool)}`; `recommendations` is a list of `{from, to,
  task_ids, rate, completed, first_try}` ordered by ladder position, task_ids in TASKS.md
  order, pending-status tasks only, and NEVER contains `to == "frontier"`; `budget` is
  `{cap, applied, remaining}`. Markdown: H1 `# Live re-route signal — <kit>`, an
  `autonomy: <posture>` line, one line per tier, `recommend: <from> → <to> — tasks <ids> …`
  lines or exactly `no re-route recommended`, a `budget: <applied>/<cap> auto-upgrades applied`
  line, then notes. Exit 0 on success including degraded input. `--demo --live` builds a
  synthetic MID-RUN kit (`DEMO_LIVE_TASKS_MD`: L1 haiku done, L2–L4 sonnet done/done/blocked,
  L5–L6 sonnet pending, L7 opus pending, L8 haiku pending, L9 fable pending;
  `DEMO_LIVE_NOTES_MD`: L1 pass, L2 pass, L3 retry-pass, L4 blocked, plus one
  `mode=advisory` reroute line) in a temp dir and runs the normal live path. Pinned demo
  expectations: sonnet `{completed 3, first_try 1}` (rate 1/3 < 0.5 at sample 3) → exactly one
  recommendation `{from: sonnet, to: opus, task_ids: [L5, L6]}`; haiku sample 1 → none; L7/L8/L9
  in no recommendation; budget `{cap 2, applied 0, remaining 2}` (the advisory line consumes
  nothing); autonomy `advisory` (no PLAN.md in the demo kit).
- **D10 — The live-policy constants are structural, not prices.** `LIVE_TIER_ORDER`,
  `LIVE_RATE_THRESHOLD = 0.5`, `LIVE_MIN_SAMPLE = 3`, `LIVE_MAX_AUTO_UPGRADES = 2`,
  `LIVE_SCHEMA_VERSION = 1` are behavioral policy of the same species as the warm sidekick's
  ~4-task cap and `SCHEMA_VERSION` — sanctioned literals (they encode no price, price ratio,
  model id, or pricing date). The tier ladder is the same sanctioned tier vocabulary the
  scorecard already carries. The SKILL text never restates the numbers — it defers to the
  `--live` output's `budget` block and thresholds, so there is exactly one home for each value.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Break the architect/execute shared kit contract.** No new required task field, no status
  vocabulary change, no removal/rewording of any pinned contract element (the T4 grep list) in
  EITHER skill. The `autonomy:` line is an OPTIONAL PLAN.md line and free text — nothing in
  TASKS.md changes shape; `copilot_execute.parse_tasks` needs no modification. Skill edits are
  BODY-only — never touch the YAML frontmatter of any `skills/*/SKILL.md` (the plugin is
  installed live). If a brief's anchor text is not present verbatim, STOP and report — do not
  approximate.
- **Auto-downgrade, skip rungs, or auto-route to frontier/Fable.** Re-routing is upgrade-only,
  one step, and stops before frontier — structurally (in `upgrade_decision`), textually (in
  both skills), and in every fixture. Moving to Fable remains exclusively the per-task
  escalation valve, whose mechanism this kit must not alter (only the pause-to-ask is dropped
  when the dial is `auto`). No skill text may permit advisory mode to change anything.
- **Rewrite a TASKS.md `model` field from the re-routing path**, in skill text or anywhere
  else. The override is runtime + logged (`reroute:` lines in NOTES.md, appended by the
  ORCHESTRATOR — `--live` itself never writes).
- **Break `bin/routing_scorecard.py`'s existing behavior.** Additive only: existing flags,
  functions, output shapes, exit codes, and the Tier-1 `--demo` numbers stay byte-stable;
  `tests/test_routing_scorecard.py` is never edited (`git diff --quiet` on it in every
  verify — new tests go in `tests/test_reroute_live.py`). Never edit `bin/cost_report.py`,
  `bin/session_cost.py`, `bin/copilot_execute.py`, any other existing `bin/`/`tests/` file,
  `data/` (either pricing file), `.claude-plugin/`, `copilot/`, `README.md`, the generated
  `skills/*/references/` mirrors, any skill other than execute/architect, or the completed
  kits and their agents.
- **Hardcode prices, price ratios, or real model ids** in any new or edited file. Sanctioned
  exceptions: tier vocabulary (`frontier`/`opus`/`sonnet`/`haiku` and `LIVE_TIER_ORDER`), the
  alias map `TASK_MODEL_TIERS = {"fable": "frontier"}`, the D10 live-policy constants, and
  synthetic fixture ids/values in tests and the demos. The `--live` path never loads
  pricing.json.
- **Read the real `~/.claude` from any test or verify command.** Every test/verify passes
  explicit temp-kit paths or `--kits-dir` fixtures; `Path.home()` count in
  `tests/test_reroute_live.py` and in the `bin/routing_scorecard.py` diff: ZERO. Never write
  outside this repo and temp dirs; the only run-time writers are the demos' own temp dirs.
  No network. No plugin re-install.
- **Add dependencies or tooling.** Python stdlib-only; no pip/pytest/requirements; no
  Copilot-side changes; no changes to `/route`/`/escalate`/`/fable-check`.
- **Build past Tier 2.** No scorecard-over-time / cross-kit aggregation, no main-session model
  switching (still the documented upstream ask), no per-task dollar telemetry in `--live`.
- **Commit or push.**

Sanctioned edit targets among existing files: `bin/routing_scorecard.py` (T1, additive),
`skills/execute/SKILL.md` (T3), `skills/architect/SKILL.md` (T4), `docs/FUSION-TIER1.md`
(T5, pinned Deferred-section pointer only), `CLAUDE.md` (T6, pinned run-line only — the
fusion-tier2 fence paragraph was already added by the architect). Sanctioned new files:
`tests/test_reroute_live.py`, `docs/FUSION-TIER2.md`.

## Risks & tripwires

- **Breaking the shared contract — THE #1 RISK.** Both skills are live runtime behavior; every
  existing kit depends on their contract, and this kit's whole design exists to add re-routing
  WITHOUT touching it. TRIPWIRES: any pinned grep string from the T4 verify missing from either
  skill; a skill file whose frontmatter changed; any text making the re-route a TASKS.md
  `model`-field rewrite or weakening "the task's `model` field overrides the implementer
  agent's frontmatter at dispatch"; a new REQUIRED task field or TASKS.md marker;
  `parse_tasks` needing modification. Any hit → stop, revert the edit, report.
- **Re-routing reaching frontier.** TRIPWIRES: any `upgrade_decision` output (any input) with
  `to == "frontier"`; skill text offering an opus→frontier upgrade; a fixture asserting one.
  The never-frontier property is tested as a sweep, not a single case.
- **Runaway auto-upgrades.** TRIPWIRES: skill text letting auto mode apply with
  `remaining == 0`; `mode=advisory` lines counted against the budget; `upgrade_decision`
  recommending a tier whose pending tasks were already upgraded (effective-pin reconstruction
  broken — it must converge to no-op).
- **Advisory mode accidentally acting.** The default MUST be print-only. TRIPWIRES: any skill
  sentence permitting a dispatch-model change while the dial is advisory; the dial defaulting
  to anything but advisory (in `parse_autonomy`, in the skill text, in the docs); the
  invocation-override precedence dropped.
- **The live signal on a tiny sample.** TRIPWIRES: a recommendation from fewer than
  `min_sample` completed tasks of that tier; a rate of None (zero completed) treated as below
  threshold; the threshold comparison flipped (`<`, not `<=` — a tier exactly AT the threshold
  is not below it).
- **Additive-only breakage of the scorecard.** TRIPWIRES:
  `git diff --quiet -- tests/test_routing_scorecard.py` failing at any point; the Tier-1
  `--demo --json` numbers shifting; any existing flag/exit-code behavior changing; `--live`
  loading pricing or accepting `--session`.
- **Attribution subtlety.** `escalated-pass` must count against the DISPATCH tier
  (pin ± applied re-routes), never against frontier; `pass`/`retry-pass`/`blocked` follow the
  ledger's `model=`. TRIPWIRE: a test showing an escalated task inflating frontier's
  `completed`. (Known, accepted approximation: an escalated task records the failure against
  its reconstructed dispatch tier — exact by construction since applied re-routes are logged.)
- **Anchor drift in prose edits.** The skill briefs pin exact old/new strings. TRIPWIRE: an
  anchor not found verbatim — report, never fuzzy-match; duplicated sections from re-running an
  edit (grep counts in verifies guard this: each new element must appear exactly once).
- **Suite/path quirks.** Verify with `python3 -m unittest discover -s tests [-p '<file>.py']` —
  never the dotted-module form. Paths via `Path(__file__).resolve()`, never `$PWD`. No
  `/private/tmp/` session path in any deliverable. Run `python3 bin/sync_pricing_refs.py
  --check` after skill edits.

## Still deferred after this kit (named, not built)

1. **Scorecard-over-time:** aggregating outcome ledgers and re-route events across kits into a
   per-tier routing track record that could inform the architect's INITIAL pins. The per-kit
   JSON (`--json`, `--live --json`) is the substrate; explicitly not in v2.
2. **Auto-downgrade:** never automatic by design (not merely deferred) — over-provisioning is
   reported at end of run for the human to re-pin the next kit.
3. **Upstream — main-session model switching at compaction boundaries:** unchanged from Tier 1;
   tracked in `docs/FUSION-TIER1.md`.
