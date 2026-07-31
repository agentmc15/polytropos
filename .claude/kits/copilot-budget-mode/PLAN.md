# PLAN — copilot-budget-mode

Give the Copilot CLI harness — and ONLY the Copilot harness — a **budget mode**: a way for a
developer up against their AI-Credits budget to run an execution kit on a cheaper ladder of
models than the default, enforced mechanically by `bin/copilot_execute.py run --budget` and
taught by a new `budget` skill in the bundle. Budget mode must **measure itself honestly**:
every run reports estimated actual-vs-standard cost *including escalations*, so the mode can
prove — or plainly disprove — its own value on a given kit.

autonomy: advisory

## The ladder (final — revised by the user; do not re-litigate)

| Role | Standard tier | Budget tier | How enforced |
|---|---|---|---|
| architect (planner) | frontier | **strong** (downgraded) | taught by the `budget` skill (the driver never dispatches the architect) |
| implementer | mid | **cheap** (downgraded) | enforced by `run --budget` (one-rung demotion of the dispatch) |
| verifier | cheap | cheap (unchanged) | nothing to do — already the floor, and the driver's verify is a shell command, not a model |
| reviewer | strong | **strong (UNCHANGED — deliberately preserved)** | `review` gains NO budget flag; reviews always run at full strength |

The originally requested ladder downgraded the reviewer strong→mid. The user revised that
after direct counter-evidence from this repo's own runs (see D2). Savings therefore come from
exactly two moves — planner frontier→strong and implementer mid→cheap — and the two quality
gates are asymmetric on purpose: the verifier stays cheap because it always was, the reviewer
stays strong because it is the load-bearing defect net.

## Goal

`bin/copilot_execute.py run` accepts `--budget` (plus `--budget-profile PROFILE`, default
`M`), demoting each task's effective dispatch model exactly one tier rung (floor = the
cheapest tier), escalating up the unchanged ladder on verified failure, and printing +
recording an honest estimated actual-vs-standard comparison per run; a new
`budget --kit DIR` subcommand totals those records into a kit-level verdict that says plainly
whether budget mode is saving or losing money on that kit; a new `budget` skill in
`copilot/.github/skills/` teaches the ladder, the flag, the reviewer-preserved rationale, and
how to read the measurements; the `execute` skill gains one pinned paragraph; all roster
surfaces (aesop.yaml, EXPECTED_SKILLS, copilot-docs/SKILLS.md) move together.

**Done looks like:**

1. `python3 bin/copilot_execute.py run --kit <dir> --task <id> --budget --dry-run --no-prefs`
   prints a `budget:` demotion line and a dispatch argv at the demoted model, spawning and
   writing nothing. Without `--budget`, every engine output, result key, exit code, and
   NOTES.md byte is identical to today.
2. A real (test-stubbed) budget run that escalates reports its own backfire: the
   `budget est.:` line says `BACKFIRED` with the overspend in labeled estimated dollars, and
   the NOTES.md block carries a machine-parseable `- budget:` line. A first-try budget run
   reports `saved`. Every dollar is labeled an estimate, never a bill; anything unpriceable
   says `unpriced` — no dollars are ever fabricated.
3. `python3 bin/copilot_execute.py budget --kit <dir>` sums the per-run records into
   per-task rows, a net total over priced runs, and one of the pinned verdicts (SAVING /
   LOSING / break-even), degrading honestly when NOTES.md or budget lines are absent.
4. `tests/test_copilot_budget.py` (new, stdlib unittest, fully stubbed dispatch) covers
   demotion semantics, prefs composition, escalation-from-demoted, the backfire report, NOTES
   format, the `budget` subcommand, and no-budget byte-stability;
   `python3 -m unittest discover -s tests` is fully green.
5. The `budget` skill exists with `name:` + `description:` frontmatter only, tier-worded and
   id-free; `copilot/aesop.yaml` skills list, `EXPECTED_SKILLS` in
   `tests/test_copilot_docs_content.py`, and an authored `## budget` section in
   `copilot-docs/SKILLS.md` all land in the SAME task, followed by
   `python3 bin/copilot_docs.py build`.
6. `review --help` shows no budget flag. `git diff --quiet -- data skills codex bin/copilot_prefs.py bin/copilot_pricing.py tests/test_copilot_execute.py tests/test_copilot_prefs.py tests/test_copilot_pricing.py` exits 0.

## Ground truth (verified in-tree 2026-07-25 — pinned; executors do NOT re-derive)

- `bin/copilot_execute.py`: `TIER_ORDER = ("cheap", "mid", "strong", "frontier")` (~line 54),
  `DEFAULT_ESCALATION_START = "mid"` (~line 56), `EM_DASH = " — "`.
  `escalation_ladder(pricing, model_id=None, prefs=None)` (~line 245) walks tiers strictly
  ABOVE the start model's tier. `_effective_task_model(task, pricing, prefs)` (~line 307) is
  the ONE home of task-pin-vs-excludes substitution; returns `(model, notes)`; passthrough
  when `prefs is None`. `run_task(task, pricing, runner, verify_runner, agent, max_escalations,
  copilot_bin, extra_args, prefs=None)` (~line 347) returns
  `{"id","status","model_used","escalations","verify_rc"}` (+`prefs_notes` only when prefs).
  `append_note(notes_path, result, task)` (~line 408) writes blocks headed
  `## <UTC ISO ts> — <task id>` with bullets `- agent:`, `- model used:`, `- escalations:`,
  `- verify: exit <rc>`, plus a `lesson-candidate (routing):` line only on escalations.
  `cmd_run`'s dry-run prints (in order): optional `prefs:` + `note:` lines, then `task:`,
  `dispatch:`, `verify:`. `cmd_run` loads pricing ONLY when prefs are engaged today.
  `cmd_review` dispatches the `reviewer` agent with `model=None` (agent frontmatter applies)
  and has NO model/prefs flags. The house lazy-loader pattern is `_load_prefs_module()`
  (module-global `_prefs_mod`, importlib by absolute path) — mirror it for pricing.
- `bin/copilot_prefs.py`: prefs map **tier → model** (pins) and exclude model ids.
  `resolve_tier(pricing, tier, prefs=None)` returns the pin outright, else first non-excluded
  model in file order carrying `tier`, else `None`. `effective_prefs` is the one entry point.
  This module is the ONLY home of prefs logic — never duplicate it.
- `bin/copilot_pricing.py`: `est_cost(pricing, profile, model_id, cache_hit=0.8, today=None)`
  returns `{"usd","aic","rates_used","warnings"}`; raises `KeyError` (message lists
  `valid choices: {sorted(...)}`) on unknown profile or model id. It requires the pricing
  dict to carry `task_profiles`, `billing_unit.usd_per_credit`, and per-model
  `cached_input_per_mtok` — **the fixture in `tests/test_copilot_execute.py` lacks all
  three**, which is one reason this kit's tests live in a NEW file with a richer fixture.
- Bundle agent frontmatter pins resolve to these tiers in `data/pricing.copilot.json`
  (verified 2026-07-25): architect → frontier, implementer → mid, verifier → cheap,
  reviewer → strong. (Ids stay out of this kit's new prose — tier words only.)
- Skill files carry `name:` + `description:` frontmatter ONLY — a `model:` line in any
  SKILL.md fails `tests/test_copilot_bundle.py`; `SkillNoModelIdTests` sweeps every skill
  file for live pricing-key model ids. `copilot/aesop.yaml`'s `skills:` list must stay
  set-equal to the directories under `copilot/.github/skills/`
  (`ManifestSkillsMatchBundleTests`). The doctrine sentence must stay verbatim in BOTH
  `copilot/aesop.yaml` and `copilot/.github/copilot-instructions.md`
  (`DoctrineSentenceSyncTests`).
- Docs center: `bin/copilot_docs.py discover_skills` scans `copilot/.github/skills/*/SKILL.md`;
  `tests/test_copilot_docs_content.py` pins `EXPECTED_SKILLS` as a HARDCODED set (lines
  62–65), requires `copilot-docs/SKILLS.md`'s `##` headings to equal it exactly, and requires
  each section body to contain (lowercase) "when to use it", "how to request it", and
  "safety and cost notes". `copilot-docs/SKILLS.md` is HAND-AUTHORED with builder-spliced
  `<!-- BEGIN/END GENERATED: skills-inventory -->` blocks — edit authored prose by hand,
  regenerate everything generated with `python3 bin/copilot_docs.py build`, never hand-edit a
  generated block, an `.html` file, or `aic-report.*`. Any sentence in copilot-docs authored
  prose containing both the words "slash" and "command" must carry an honesty negation —
  simplest rule: never write the phrase "slash command" in new docs prose; `/budget` alone is
  safe.
- Adding a skill therefore requires FOUR coordinated edits in ONE task: the bundle skill
  file, the `aesop.yaml` list line, the `EXPECTED_SKILLS` constant, and the authored
  `## budget` docs section — then `python3 bin/copilot_docs.py build`. A task doing only some
  of these leaves the suite red (this failure shipped in a prior kit; do not repeat it).
- Routing-ledger evidence (2026-07-25, `routing_scorecard --history`): 24 kits, 150/154
  first-try; haiku 23/23, sonnet 102/106, opus 25/25; reviewer precision 96% (25/26 findings
  confirmed, all at the strong/opus class). Caveat: haiku's 100% is on architect-judged
  trivial tasks — it says nothing about cheap models on mid-tier work, which is exactly what
  budget mode's implementer downgrade creates. That is why the measurement machinery here is
  not optional decoration.

## Decisions

**D1 — Mechanism is skill + driver flag (given, not re-litigated).** Advice alone is
unenforceable and unmeasurable; a flag alone is undiscoverable. The `budget` skill teaches;
`run --budget` enforces and measures.

**D2 — The reviewer is NOT downgraded (revised ladder; the single most important call).**
In a run completed 2026-07-24/25, three separate cheap-tier verifiers returned ZERO findings
on material in which a strong-tier phase reviewer then found SEVEN real, confirmed defects —
two of them blocking honesty defects where documentation contradicted engine output. The
lesson recorded: *a verifier finds what its brief points it at; the strong reviewer
independently compared claims against reality.* The reviewer is also the very instrument that
detects budget mode's own backfires — downgrading it would corrupt the measurement this
feature is required to produce (D5). So `review` gains no budget flag, no budget code path,
nothing. Budget mode pays full price for its one defect net and buys savings only where the
ledger supports it. Corollary (D7): budget mode should use that net MORE, not less.

**D3 — Demotion is a per-dispatch tier step owned by the driver; prefs keep owning
tier→model.** Prefs answer "which model IS tier X" (pins/excludes); budget answers "dispatch
one tier lower than the task asked". These axes never merge: the new `budget_demote` function
in `bin/copilot_execute.py` computes the target tier (exactly one rung below the effective
model's tier, floor = cheapest tier) and delegates its resolution to
`copilot_prefs.resolve_tier(pricing, target_tier, prefs)` — zero duplicated prefs logic, and
user pins/excludes automatically shape what "cheap" or "strong" means under budget too.
Composition order is pinned: task pin → `_effective_task_model` (exclude substitution) →
`budget_demote` → dispatch → `escalation_ladder` from the demoted model. There is no role→tier
config file and no prefs-file budget key — the ladder is two tier-worded moves, not a policy
engine. The architect row cannot be driver-enforced (the driver never dispatches the
architect) and is taught in the skill instead: enforced where enforceable, taught where not —
and the skill says which is which.

**D4 — Budget mode is "start one rung lower on the SAME ladder", so it is self-limiting by
construction.** The escalation ladder is untouched: a demoted dispatch that fails verify
escalates first to exactly the tier the task would have started at under standard mode. Worst
case = standard behavior plus one cheap attempt (plus its verify), never a runaway. This is
the structural answer to the central tension: a cheap implementer that fails twice costs more
than a mid implementer that passes once — budget mode cannot prevent that, so it bounds it
(one extra rung of spend at the cheapest prices) and measures it (D5). `--max-escalations`
still applies; the skill warns that `--budget --max-escalations 0` converts failures straight
to `blocked`.

**D5 — Self-measurement is estimates-only, labeled, and allowed to condemn the feature.**
The driver never sees real token counts, so every figure comes from
`copilot_pricing.est_cost` under a named task profile (default `M`), computed for each
dispatch that actually happened (initial + every escalation rung) versus ONE dispatch at the
standard model. The label states the assumptions ("single dispatch, assumes first-try;
profile estimate — not a bill"). With only two roles downgraded, one escalation can erase a
whole run's saving — so the per-run line says `saved $X` or `BACKFIRED — overspent $Y`
explicitly, the NOTES.md record is machine-parseable, and the `budget --kit` ledger renders
the kit-level verdict, including "budget mode is LOSING money on this kit — consider dropping
--budget". Anything unpriceable (agent-default dispatch, id missing from pricing, unknown
profile at report time) degrades to `unpriced` with the reason; dollars are never fabricated,
and a report failure never flips a task's status or exit code — the work outcome and the
accounting are separate concerns.

**D6 — Edge semantics: never fabricate, never double-demote, never silently jump.** Pinned in
`budget_demote`: a pin-less task assumes the `mid` standard tier (= `DEFAULT_ESCALATION_START`,
the implementer agent's tier — stated as an assumption in output); an id unknown to pricing is
dispatched as pinned with a "cannot demote" note; a cheap-tier pin is already at the floor
(no-op, noted); a target tier emptied by excludes means NO demotion (dispatch at standard —
never a two-rung fall); a resolution equal to the standard model is a noted no-op.

**D7 — Budget mode recommends a phase review at EVERY phase boundary.** The retained strong
reviewer partially compensates for the cheap implementer: reviews are priced per phase, not
per task, so they are cheap insurance exactly when implementation quality drops. This is
teaching (skill + docs wording), not a driver auto-dispatch — the driver never spends AIC
uninvited.

**D8 — `budget` is a skill-only capability, like `execute` and `lessons-loop`.** A mode of
the driver is not a persona; a same-named agent would need a model pin and would double the
roster edits for zero capability. The skill closes with an honest "Same-named agent — no"
paragraph plus the verbatim "Installed?" paragraph.

**D9 — Everything is additive and byte-stable without the flag.** No existing flag,
signature, result key, output line, exit code, or NOTES byte changes unless `--budget` is
given. `run_task` gains a default-`False` kwarg; results gain `budget`/`budget_report` keys
only when active; `append_note` emits the `- budget:` line only when the result carries one.
Tests for all of this live in the NEW `tests/test_copilot_budget.py`;
`tests/test_copilot_execute.py` stays byte-frozen.

## Out of scope (executors must NOT build)

- No Claude-side (`skills/`) or Codex-side (`codex/`) port — future kits.
- No changes to `bin/copilot_prefs.py`, `bin/copilot_pricing.py`, `bin/copilot_ralph.py`,
  `bin/routing_scorecard.py`, or any pricing file — the driver consumes them read-only.
- No budget flag on `review` or `status`; no auto-dispatched reviews; no re-dispatch loops.
- No budget key in `prefs/copilot.json`, no new config file, no role→tier policy engine, no
  new tier vocabulary, no per-role flags (`--budget-implementer=...` etc.).
- No real token measurement, no reading `~/.copilot`, no telemetry/journal wiring.
- No new file under `docs/` or `copilot-docs/` (the docs land inside existing SKILLS.md);
  `copilot-docs/WORKFLOWS.md` has a pinned-headings test — do not touch it.
- No new same-named `budget` agent; no edits to any bundle agent file.
- No commit, no push.

## Risks & tripwires

- **Cheap-implementer escalation loops eating the saving** — the designed-for risk. Tripwire:
  a `BACKFIRED` per-run line, and `budget --kit` totals going negative → the skill's pinned
  advice is to drop `--budget` for the remainder of that kit. The measurement exists to be
  believed; never soften its wording.
- **Estimate-vs-reality divergence.** Profile-based estimates are synthetic. Tripwire: any
  new output line showing a dollar figure without its "estimate — not a bill" label is a
  defect; the reviewer must grep rendered output, not just source.
- **The pin-less-task assumption.** Assuming `mid` for pin-less tasks matches the driver's
  own `DEFAULT_ESCALATION_START` and the implementer frontmatter tier, but it IS an
  assumption — it must appear in the output label (`assumed`), never silently.
- **Roster/docs drift.** T4's four coordinated edits must land together; T6 cross-checks
  every flag the skill mentions against real `--help` output (the "docs contradicted the
  engine" defect class from the prior run, made a task).
- **Fixture drift.** `est_cost` needs `cached_input_per_mtok`/`task_profiles`/`billing_unit`;
  reusing the old execute-test fixture will KeyError — the new test file owns a richer one.
- **Hermeticity.** A real `prefs/copilot.json` may exist on this machine: every `main()`
  invocation in tests passes `--no-prefs` (or a temp `--prefs`), and `load_pricing` is
  patched to the fixture in end-to-end tests so live-roster changes never flake the suite.
