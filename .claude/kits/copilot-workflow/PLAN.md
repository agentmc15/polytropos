# PLAN — copilot-workflow

Phase 2 of the Copilot harness: give GitHub Copilot CLI users the same
plan → execute → verify → escalate workflow the Claude Code plugin has, plus the two
harness-engineering primitives the copilot-harness kit deferred — the Ralph goal loop and the
lessons-loop skill. Builds ON the completed copilot-harness MVP (`data/pricing.copilot.json`,
`bin/copilot_pricing.py`, `bin/harness_select.py`, the `copilot/` bundle, 83 tests green);
duplicates nothing. All aesop behavior claims are pinned to commit `5506617`
(full: `55066175a5268887acad39bc859584d13fab09db`). The aesop clone the architect consulted
lives in a session-scratchpad directory that may not exist when tasks execute — every aesop
fact a task needs is therefore pinned verbatim inside its brief; **no task reads the clone**.

## Goal

Ship three things, end-to-end verified without ever calling the real `copilot` CLI:

1. **Architect/execute/escalate port** — four Copilot custom agents
   (`architect`/`implementer`/`verifier`/`reviewer` as `.agent.md` files with per-agent
   `model:` pins from `data/pricing.copilot.json`) plus a thin stdlib driver
   (`bin/copilot_execute.py`) that parses a kit's TASKS.md, dispatches
   `copilot --agent <name> --model <id> --allow-all-tools -p "<brief>"`, runs the task's verify
   command, escalates up the pricing tiers on failure, and writes statuses/NOTES back.
2. **Ralph goal loop** — `bin/copilot_ralph.py`: aesop's portable Ralph loop adapted to drive
   `copilot -p`, with the three hard stops (iteration ceiling, no-progress detector, budget
   cap), per-tick cost + budget runway fed from `bin/copilot_pricing.py` instead of a flat
   default, and stop values selected by profile (token-lean / balanced / accuracy-max).
3. **lessons-loop** — aesop's Reflexion skill vendored to
   `copilot/.github/skills/lessons-loop/SKILL.md`, listed in `copilot/aesop.yaml`, with a
   routing-specific lesson category wired to the `route` agent and the execute driver.

**Done looks like:** `python3 -m unittest discover -s tests -v` green with three new test files
(`test_copilot_execute.py`, `test_copilot_ralph.py` — plus extended `test_copilot_bundle.py` and
`test_harness_select.py`); `python3 bin/copilot_ralph.py --demo` completes `verified` with
pricing-fed tick costs and runway lines, zero network; `bin/copilot_execute.py run --dry-run`
against a fixture kit prints the exact dispatch argv and mutates nothing;
`bin/harness_select.py install` into a temp home materializes agents AND skills with the
placeholder resolved; four new agents + one skill listed in `copilot/aesop.yaml` and enforced by
the bundle test; `docs/COPILOT-WORKFLOW.md` exists; no file anywhere invokes the real `copilot`;
`data/pricing.json`, `data/pricing.copilot.json`, `.claude-plugin/`, `skills/`, and the completed
kits are byte-identical to git HEAD except where a task pins an exact insertion.

## Research findings (recorded per the kit mandate)

### Copilot CLI flags — CONFIRMED from local `copilot --help` output, 2026-07-01

Captured by the architect from the installed CLI's help text (a local print — no model call, no
AI Credits, no network). Executors need not and must not run `copilot` themselves:

- `--agent <agent>` — "Specify a custom agent to use".
- `--model <model>` — "Set the AI model to use ('auto' …)".
- `-p, --prompt <text>` — "Execute a prompt in non-interactive mode".
- `--allow-all-tools` — "Allow all tools to run automatically without confirmation; **required
  for non-interactive mode** (env: COPILOT_ALLOW_ALL)". This is the tool-permission flag the
  Phase-2 design asked to confirm. Granular alternatives exist (`--allow-tool[=tools...]`,
  `--deny-tool[=tools...]`, e.g. `--allow-tool='shell(git:*)'`), plus `--allow-all-paths`,
  `--allow-all-urls`, and umbrella `--allow-all`.
- `-s, --silent` — agent response only. Not used by the driver (full output is kept as
  escalation evidence).

### aesop@5506617: the portable Ralph runner is NOT runnable as shipped

`registry/loops/ralph/ralph_loop.py` at that commit imports `Guardrails`/`run_loop` from
`registry/harness/python/agent_harness.py` — **which does not exist anywhere in the tree at
5506617**. The working reference for loop semantics is `src/loops/ralph.ts` (the compiled
TypeScript loop), whose exact behavior is pinned in T5's brief: verify-first short-circuit;
per tick → dispatch, cost accrual (parse JSON-line cost else flat estimate), verify, state-file
write, stop checks in order verified → budget → no-progress; halt statuses
`verified | max_iterations | no_progress | budget`. Our runner implements those semantics
directly, stdlib-only, with the flat estimate replaced by `bin/copilot_pricing.py` math.

### aesop@5506617 profile guardrails (the three hard stops per profile)

From `profiles/{token-lean,balanced,accuracy-max}.yaml` `guardrails:` blocks:
token-lean `max_iterations: 20, no_progress_stop: 2, budget_usd: 5.0`;
balanced `40, 3, 25.0`; accuracy-max `80, 4, 100.0`. These are loop knobs (halt conditions),
not pricing facts — they are pinned in code with the commit cited, unlike prices, which always
come from `data/pricing.copilot.json` at run time.

### lessons-loop source

`registry/skills/lessons-loop/SKILL.md` at 5506617: prompted-Reflexion — on correction, append
`{failure_pattern, lesson, applies_to}` entries to `tasks/lessons.md`; reload at session start;
dedupe/prune hygiene. T7 pins the full vendored adaptation verbatim.

## Architecture & key decisions

- **D1 — Driver shape: a thin stdlib driver script, not an orchestrating session.** The execute
  port's driver is `bin/copilot_execute.py`. Rationale, in order of weight:
  1. *AIC safety is only testable in code.* The kit contract (task `model` field → `--model`
     flag, status vocabulary, escalation ladder) becomes pure functions exercised with mocked
     subprocesses at zero AI-Credit cost. A prose-orchestrated Copilot session could only be
     tested by burning real credits — which this kit forbids.
  2. *Copilot has no in-session dispatch surface with a per-dispatch model override.* Unlike
     Claude Code's Agent tool (`model` parameter), the only per-dispatch model control is the
     CLI `--model` flag — so any orchestration bottoms out in shelling
     `copilot --agent … --model … -p …`. The driver makes that one tested code path instead of
     prose an orchestrating model may drift on.
  3. *Orchestration itself costs nothing in a driver.* Python is free; only dispatched agents
     spend AIC. A Copilot session doing the same loop would bill every orchestration turn.
  The interactive story still exists: a user (or any agent) runs the driver; the `architect`
  agent produces the kits it consumes.
- **D2 — Dispatch command anatomy (flags confirmed above).** One tick of the execute driver is
  `[copilot_bin, "--agent", <name>] + (["--model", <id>] if the task pins one) +
  ["--allow-all-tools"] + extra_args + ["-p", <brief>]`, built as an argv list (never
  `shell=True` for dispatch). A task without a `model:` field dispatches without `--model`, so
  the agent's frontmatter pin applies — the exact carry-over of the kit contract's override
  rule. `--allow-all-tools` is the default permission grant (required for non-interactive
  mode); a repeatable `--extra-arg` flag lets users add `--deny-tool …` etc.
- **D3 — Escalation ladder is tier-data-driven, no ids in code.** Tier order is
  `cheap < mid < strong < frontier` (the data file's four-value vocabulary). A failed task
  escalates through each tier strictly above its pinned model's tier (unpinned tasks start at
  `mid`), taking the FIRST model in pricing-file order carrying that tier — the file is
  deliberately ordered best-first within tiers. With today's data the ladder from `mid` is
  exactly the Phase-2 design's "strong then frontier": `claude-opus-4.8` → `claude-fable-5`
  (the sole frontier model). Each escalation re-dispatches the SAME brief with the verify
  failure evidence appended (command, exit code, output tail) — the Claude-side escalate
  skill's evidence-carrying rule, ported. Ladder exhausted ⇒ status `blocked`.
- **D4 — Copilot-side workflow agents and their model pins.** Four new `.agent.md` files in
  `copilot/.github/agents/`, pins chosen from the live roster by tier:
  `architect` → `claude-fable-5` (kit-building is the expensive meta-work done once; Fable 5 is
  the sole frontier model and this is exactly what it is reserved for);
  `implementer` → `claude-sonnet-5` (the mid-tier workhorse, best value at promo pricing);
  `verifier` → `claude-haiku-4.5` (adversarially rerunning a verify command is mechanical —
  cheap tier suffices); `reviewer` → `claude-opus-4.8` (drift review is judgment work — strong
  tier, and the roster's default strong pick). The bundle test enforces pins **by tier via data
  lookup** (architect's pin must carry `tier: frontier`, etc.), not by id literal, so a future
  roster change fails loudly instead of silently ossifying ids.
- **D5 — The kit contract carries over verbatim; Copilot-side kits live at
  `tasks/kits/<slug>/`.** Layout `PLAN.md` + `TASKS.md` (+ `NOTES.md`, owned by the driver);
  task fields `id`, `title`, `status`, `model`, brief, acceptance, verify; status vocabulary
  exactly `pending | in-progress | done | blocked`; `## Phase N` headings;
  `depends:`/`independent:`. The `tasks/` root matches `copilot/aesop.yaml`'s `state.dir:
  tasks/` and the lessons file `tasks/lessons.md` — one state tree per consumer repo. The
  driver's TASKS.md status writeback is a surgical single-line replacement (tested
  byte-for-byte elsewhere-identical).
- **D6 — Ralph runner: `bin/copilot_ralph.py`, self-contained, ralph.ts semantics.** Lives in
  `bin/` (it is a stdlib script with a test file, not Copilot config; `copilot/.github/` holds
  prompt-surface primitives only). Three hard stops per the research finding; anchor prompt as
  a module constant adapted from aesop's `prompt.md` (`{{goal}}`/`{{state_summary}}`
  placeholders, `--prompt-file` override); per-tick cost = `parse_cost(output)` (port of
  ralph.ts's JSON-line scan for `total_cost_usd`/`cost_usd`) with fallback to
  `copilot_pricing.est_cost(tick profile, model)` — the designed replacement for ralph.ts's
  flat `0.25` default — and a budget-runway line every tick (remaining budget ÷ est per tick).
  Profiles select stop values (pinned dict, commit-cited, CLI-overridable). The tick command it
  builds for real runs is `copilot --model <id> --allow-all-tools -p "<anchor prompt>"` (the
  goal loop drives plain `copilot -p`, per the Phase-2 design — no `--agent`). Dispatch and
  verify are **injectable callables**; `--demo` runs a fully mocked loop (no subprocess to any
  CLI, no network, exercises the real pricing math), `--dry-run` prints stops/estimate/runway/
  argv and exits without spawning anything.
- **D7 — lessons-loop vendored with a routing category, closing the loop to `route`.** The
  skill lands at `copilot/.github/skills/lessons-loop/SKILL.md` (content pinned in T7,
  provenance line citing aesop@5506617), listed under a new `primitives.skills:` block in
  `copilot/aesop.yaml`. The routing category: escalations (pinned model failed verify; a higher
  tier finished it) and gross overprovisioning become `applies_to: ["routing"]` entries in
  `tasks/lessons.md`; the execute driver emits a `lesson-candidate (routing):` line into the
  kit's NOTES.md whenever a task escalated; the `route` agent gets a pinned insertion telling
  it to read routing lessons at session start and let them override its tier heuristics.
- **D8 — `bin/harness_select.py` grows skills install (the ONE existing-script edit this kit
  sanctions).** `install_copilot` already copies every `*.agent.md` (T1's four new agents need
  zero installer work); T8 extends it to also materialize `copilot/.github/skills/**` into
  `<home>/skills/**`, same placeholder resolution, same dry-run discipline, missing skills dir
  tolerated (agents remain the required core). All conventions of the existing script and its
  test suite (temp homes, `unittest.mock`, no `Path.home()`) carry over unchanged.
- **D9 — Stdlib-only, discovery-only, fixture-pricing tests.** New scripts follow `bin/`
  conventions (module docstring, pure functions taking dicts/callables, `main(argv=None)`,
  argparse subcommands, `KeyError`/errors → stderr + exit 2); new tests follow `tests/`
  conventions (importlib `_load` off `BIN_DIR`, synthetic pricing fixtures with fake round
  numbers — e.g. `usd_per_credit: 0.5` to prove nothing hardcodes the real unit — no wall-clock
  assertions, `python3 -m unittest discover -s tests [-p '<file>.py']`, never dotted-module).

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Invoke the real `copilot` CLI, EVER — not even `--help`.** `copilot -p` / `copilot --agent`
  calls a model, spends the user's real AI Credits, and hits the network; the user has a real
  `~/.copilot` install. Every CLI fact this kit needs is pinned in this PLAN (Research
  findings) and in the briefs. Tests mock or stub every dispatch (temp stub executables and
  injected callables only — never a binary named `copilot` from PATH); the only sanctioned CLI
  smoke paths are `--dry-run` and `--demo`, which spawn nothing.
- **Touch anything outside this repo.** No `~/.copilot/` (installs go only to temp
  `--copilot-home` dirs), no `~/.claude/`, no plugin re-install. The aesop clone is
  reference-only, session-scoped, and may not exist — no task reads it.
- **Move or edit the live Claude Code plugin surface**: `.claude-plugin/`, `skills/`, the
  generated `skills/*/references/` mirrors, `data/pricing.json`. Do not edit
  `data/pricing.copilot.json` at all (no task in this kit touches pricing values).
- **Edit existing `bin/` scripts other than `bin/harness_select.py`** (T8's sanctioned
  extension) — `copilot_pricing.py`, `aesop_bridge.py`, `cost_report.py`, `statusline.py`,
  `sync_pricing_refs.py`, `agent_tracker.py` stay untouched.
- **Run node/npm/`aesop compile`** anywhere, or add any dependency/tooling. Python stays
  stdlib-only; no pytest; no requirements files.
- **Touch the completed kits** (`.claude/kits/harden-plugin/`, `.claude/kits/aesop-bridge/`,
  `.claude/kits/copilot-harness/`) or their agents beyond reading them.
- **Build Phase-3 items**: no aesop-compile round-trip, no Copilot cost-visibility/usage
  report, no repo-root `.github/`, no MCP config, no new Claude Code skills.
- **Commit or push.**

## Risks & tripwires

- **AIC / network safety — THE #1 RISK.** Any code path that reaches a real
  `copilot` invocation spends real money and hits the network. TRIPWIRE: if a task, test, or
  verify command would invoke `copilot` (any subcommand, any flag), STOP — that is a wrong
  change even if it works. Tests prove the negative: dry-run/demo paths run with
  `subprocess` patched to raise; real-run test paths use temp stub executables passed via
  `--copilot-bin`. The kit verifier adversarially audits for this on every task.
- **`--model` flag vs agent `model:` frontmatter precedence is unverified.** GitHub's docs
  confirm both mechanisms but not their interaction; this kit asserts the kit-contract rule
  (task pin → `--model` flag overrides) and cannot verify it live (doing so would spend AIC).
  Mitigation: the driver always passes `--model` when a task pins one; docs tell the user how
  to check once (`--dry-run` shows the argv). TRIPWIRE: do not delete agent frontmatter pins to
  "guarantee" the override.
- **Copilot's programmatic cost output is opaque.** `parse_cost` implements the generic
  JSON-line contract from ralph.ts (`total_cost_usd`/`cost_usd`); Copilot CLI likely emits
  neither, so the data-driven estimate is the expected steady state, by design. TRIPWIRE: no
  task may invent a Copilot cost-output format or assert one in tests beyond the generic
  contract.
- **Session-scratchpad paths must never enter repo files.** The architect's aesop clone lives
  under `/private/tmp/claude-501/...` — if that string (or any `/private/tmp/` path) appears in
  a deliverable, that is drift. Aesop provenance is cited as `aesop@5506617`, nothing more.
- **Generic agent names collide in `~/.copilot/agents/`.** `implementer`/`verifier`/`reviewer`
  installed at user level shadow same-named repo agents everywhere (home-dir precedence,
  documented since the MVP). T9's doc must restate this for the four new agents.
- **User-home skills install location is best-effort.** The repo-level `.github/skills/` path
  is the pinned bundle surface; the installer mirrors it to `<home>/skills/`. If Copilot CLI
  expects a different home-dir layout, the fix is in `bin/harness_select.py` only — never move
  the bundle. TRIPWIRE: do not rename `copilot/.github/skills/`.
- **Driver writes into consumer TASKS.md files.** `set_status` must replace exactly one
  `- status:` line inside exactly the matched task block; the test asserts everything else is
  byte-identical. TRIPWIRE: a regex that can match across task boundaries is a FAIL.
- **Live-install hazard (Claude side).** Any stray edit under `skills/` or `.claude-plugin/`
  changes the user's live Claude Code behavior immediately. The verifier sweeps `git status`
  for out-of-fence modifications on every task.
- **Site-packages `tests` shadowing.** Verify commands use
  `python3 -m unittest discover -s tests [-p '<file>.py']` — never the dotted-module form.
  Path resolution uses `Path(__file__).resolve()`, never `$PWD` (Desktop/desktop case quirk).

## Phase 3 — further deferred (designed in copilot-harness PLAN.md, still not built)

Carried forward deliberately; the natural next kit(s):

1. **Aesop compile round-trip.** Make the copilot bundle a real `aesop compile` target: expose
   this repo's copilot content to aesop's registry lookup, run `aesop compile` from a built
   checkout, and reconcile the `.agent.md` vs `.md` emitter divergence upstream in the aesop
   repo, through its own phase-gated process — never from here.
2. **Cost visibility.** A Copilot `/usage`-equivalent report mirroring
   `/polytropos:cost-report` (whatever session/usage surface the CLI exposes by then);
   org/Business pooled-AIC awareness in `copilot_pricing.py runway`; feeding real per-tick
   costs back into the Ralph loop once the CLI exposes them.
