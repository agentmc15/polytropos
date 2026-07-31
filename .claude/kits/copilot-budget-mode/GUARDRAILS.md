# copilot-budget-mode — kit guardrails

Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

For `copilot-budget-mode` specifically: Copilot CLI harness ONLY — nothing under `skills/`
(Claude side), `codex/`, or `.claude-plugin/` changes, and no Claude-/Codex-side budget
parity lands (future kits). The final ladder is LAW and is not re-litigated by any executor:
architect frontier→strong (taught only — the driver never dispatches the planner),
implementer mid→cheap (enforced as a one-rung demotion of the dispatch), verifier unchanged
at cheap, reviewer UNCHANGED at strong — `review` and `status` gain NO budget flag, no
budget code path, and no model flag, and no task adds an auto-dispatched review or any
re-dispatch loop. Demotion is exactly ONE tier rung with the cheapest tier as floor — never
two rungs, never a fabricated rung, never below the floor, and a target tier emptied by
excludes means NO demotion (dispatch at the standard model, stated in a note). `TIER_ORDER`
and the escalation ladder's trigger, walk order, and `--max-escalations` semantics are
byte-untouched; budget mode changes only WHERE a dispatch starts, never how it climbs.

Ownership boundaries are absolute: tier→model resolution happens ONLY through
`copilot_prefs.resolve_tier` via the existing lazy loader (prefs logic is never duplicated,
`bin/copilot_prefs.py` is never edited); ALL cost math happens ONLY through
`copilot_pricing.est_cost` via a new `_load_pricing_module()` mirroring the prefs loader
(`bin/copilot_pricing.py` is never edited; no `*_per_mtok` arithmetic may appear in
`bin/copilot_execute.py`); there is no role→tier config file, no budget key in
`prefs/copilot.json`, no new tier vocabulary, and no per-role budget flags.

NEVER invoke the real `copilot`, `codex`, or `claude` CLI from any task, test, or verify
command (command lines WRITTEN into skill/docs bodies are runtime instructions the kit never
executes); every dispatch in tests goes through injected fake runners or temp stub
executables; every `main()` invocation in tests passes `--no-prefs` (or a temp `--prefs`)
and patches `load_pricing` to the synthetic fixture — no test may depend on the live roster
or on the presence/absence of a real `prefs/copilot.json`; zero `Path.home()`, zero network,
stdlib-only; the `budget` subcommand is read-only over the kit dir and loads no prefs.

Engine changes are ADDITIVE and byte-stable without the flag: `run` gains only `--budget` /
`--budget-profile`, `run_task` gains only a default-`False` `budget` kwarg, results gain
only `budget`/`budget_report` keys and NOTES blocks gain only the single `- budget:` line —
and only when budget is active; with `--budget` absent, every output line, result key, exit
code, NOTES byte, and dry-run byte is identical to before the kit.

Honesty is absolute: every dollar printed is an `est_cost` estimate labeled with its profile
and its "single dispatch, assumes first-try" counterfactual and the words "estimate — not a
bill"; a backfire says `BACKFIRED` verbatim and the kit ledger says
`LOSING money on this kit` verbatim — no task may soften, rename, or bury these strings;
anything unpriceable prints `unpriced` with its reason and fabricates nothing; a cost-report
exception NEVER changes a task's status or exit code; the pin-less-task standard tier is
always labeled `assumed`.

No hardcoded prices or live pricing-key model ids anywhere new — tier vocabulary, the
validated `--budget-profile` default `M`, flag-grammar strings, pinned message text, and
synthetic `fake-*` fixture ids are the sanctioned literals; the budget skill and every
edited/added bundle or docs surface stays id-free (`SkillNoModelIdTests` sweeps skills; docs
have their own sweep); skill frontmatter is `name:` + `description:` only.

Roster edits move as ONE task (T4): the skill file, the `aesop.yaml` skills-list line, the
`EXPECTED_SKILLS` constant, and the authored `## budget` SKILLS.md section, then
`python3 bin/copilot_docs.py build` — never hand-edit a generated block, an `.html`, or
`aic-report.*`, never touch `copilot-docs/WORKFLOWS.md` (pinned-headings test), never edit
any bundle agent file, and never add a `budget` agent or an `EXPECTED_AGENTS` entry. The
doctrine sentence in `copilot/aesop.yaml` and `copilot/.github/copilot-instructions.md`
stays byte-intact; the only edit to those two files is the pinned `/budget` sentence
substitution.

Sanctioned edit targets are ONLY: `bin/copilot_execute.py`;
`copilot/.github/skills/execute/SKILL.md` (one pinned paragraph);
`copilot/aesop.yaml` and `copilot/.github/copilot-instructions.md` (pinned substitutions +
list line); `tests/test_copilot_docs_content.py` (the one `EXPECTED_SKILLS` line);
`copilot-docs/SKILLS.md` (the authored `## budget` section) plus whatever
`bin/copilot_docs.py build` regenerates under `copilot-docs/`; with NEW files
`tests/test_copilot_budget.py` and `copilot/.github/skills/budget/SKILL.md`. Explicitly
FROZEN (byte-clean in git at T6): `data/` (all three pricing files), `skills/`, `codex/`,
`bin/copilot_prefs.py`, `bin/copilot_pricing.py`, `bin/copilot_ralph.py`,
`tests/test_copilot_execute.py`, `tests/test_copilot_prefs.py`,
`tests/test_copilot_pricing.py`, `copilot-docs/WORKFLOWS.md`, every bundle agent file,
`README.md`, and CLAUDE.md. No new `docs/` file. No commit, no push.
