# PLAN — copilot-harness

Grow this repo into a two-harness monorepo **without moving anything**: keep the live-installed
Claude Code plugin exactly where it is at the repo root, and add a GitHub Copilot CLI harness as
new sibling trees — Copilot pricing data (AI Credits), a Copilot `route` equivalent, and a
harness-selection mechanism. Aesop (github:agentmc15/aesop) is the harness-engineering backbone
for the new side. All aesop behavior claims in this kit were verified against commit
`5506617` (full: `55066175a5268887acad39bc859584d13fab09db`); a built checkout at that same
commit exists at `/path/to/aesop` (reference-only — never edited, never
executed by this kit).

## Goal

Ship the MVP first slice, end-to-end verified:

1. **Copilot pricing data** — `data/pricing.copilot.json`: the AIC token-billing model
   (1 AIC = `usd_per_credit` dollars, encoded as data), the cross-vendor model roster with
   per-model input/cached-input/output rates, plan allowances, and cross-vendor routing tiers.
2. **A Copilot `route` equivalent** — a Copilot custom agent (`copilot/.github/agents/
   route.agent.md`) plus a stdlib cost engine (`bin/copilot_pricing.py`) that classifies a task,
   estimates cost in USD and AIC, and tells the user exactly how to act on the recommendation
   (`/model`, `--model`, `COPILOT_MODEL`, settings.json, agent `model:` pins).
3. **Harness selection** — `bin/harness_select.py`: detect which harness CLIs are present and
   install the Copilot bundle into a Copilot home (`~/.copilot` for the user at run time; always
   a temp dir during kit verification). Claude Code needs no install step (live local
   marketplace) — the selector says so instead of touching anything.

**Done looks like:** `python3 -m unittest discover -s tests -v` green including three new test
files (`test_copilot_pricing.py`, `test_copilot_bundle.py`, `test_harness_select.py`);
`python3 bin/copilot_pricing.py models --json` emits the roster with tiers;
`python3 bin/copilot_pricing.py est M claude-fable-5` prints a USD + AIC estimate;
`python3 bin/harness_select.py install --harness copilot --copilot-home <tmp>` materializes a
working agent file with the repo's absolute path baked in and no placeholder left;
`copilot/aesop.yaml` exists and `tests/test_copilot_bundle.py` proves manifest ↔ bundle
consistency; `docs/COPILOT-HARNESS.md` exists; `data/pricing.json` and every existing Claude Code
file are byte-identical to git HEAD except where a task pins an exact insertion.

## Research findings (recorded per the kit mandate)

### Copilot CLI model selection — CONFIRMED, the workflow ports closely

GitHub Copilot CLI supports per-invocation, per-session, persistent, AND per-agent model choice:

- **Per invocation:** `copilot -p "<prompt>" --model <model-id>` (programmatic mode), e.g.
  `copilot -p "What does this project do?" -s --model claude-haiku-4.5`. Source:
  docs.github.com → *GitHub Copilot CLI programmatic reference*
  (`/copilot/reference/copilot-cli-reference/cli-programmatic-reference`).
- **Per shell session:** `COPILOT_MODEL` environment variable. Same source.
- **Persistent:** `model` key in `~/.copilot/settings.json` (or `$COPILOT_HOME/settings.json`).
  Same source.
- **Interactive:** `/model` slash command lists available models; selecting a policy-disabled
  model prompts to enable it in place. Source: GitHub changelog, *GitHub Copilot CLI: Enhanced
  agents, context management, and new ways to install* (2026-01-14).
- **Per custom agent:** agent frontmatter supports a `model` field — "Model to use when this
  custom agent executes. If unset, inherits the default model." Copilot CLI supports **all**
  custom-agent frontmatter fields. Source: docs.github.com → *Custom agents configuration*
  (`/copilot/reference/custom-agents-configuration`).
- **Custom agents:** `.agent.md` files at `.github/agents/` (repo) and `~/.copilot/agents/`
  (user); home-dir agents win name collisions; invoked via `/agent`, by inference, or
  `copilot --agent <name> --prompt "..."`. Source: docs.github.com → *Creating and using custom
  agents for GitHub Copilot CLI* (`/copilot/how-tos/copilot-cli/customize-copilot/
  create-custom-agents-for-cli`).

Consequence: the route → dispatch pattern (and later the architect/execute/escalate port) maps
onto Copilot natively. One residual unknown is a RISK below: the docs confirm the `model` field
and show only two concrete id strings (`claude-haiku-4.5`, `gpt-5.3-codex`); the full roster's
exact CLI id strings are best-effort.

### Copilot pricing — captured 2026-07-01 from
https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing

- Billing is per-million-token (input, cached input, output; Anthropic models also list a cache
  *write* rate), settled in **AI Credits: 1 AIC = $0.01 USD**.
- Plan allowances (per month, individual): Pro $10 → 1,500 AIC; Pro+ $39 → 7,000 AIC; Max $100 →
  20,000 AIC (base credits matched 1:1 to price + a "flex allotment" that GitHub can rebalance).
  Business/Enterprise pool AIC at the org level. Code completions / next-edit suggestions are
  not billed in AIC. Sources: docs.github.com *Plans for GitHub Copilot*; GitHub changelog
  *Updates to GitHub Copilot billing and plans* (2026-06-01).
- Claude Sonnet 5 is promo-priced ($2 in / $10 out) **through 2026-08-31**; the post-promo rate
  is not yet published. GPT-5.4/5.5 and Gemini 3.1 Pro have two-tier long-context pricing
  (rate step-up above 272K / 200K input tokens).
- The full per-model table is pinned verbatim inside task T1's brief so execution needs no
  network access.

## Architecture & key decisions

- **D1 — Additive monorepo layout; nothing moves.** The Claude Code plugin is installed live at
  user scope from this directory (`.claude-plugin/marketplace.json`, `source: ./`); moving files
  or editing that manifest breaks the live install and violates the no-`~/.claude` invariant.
  New sibling trees only:
  - `data/pricing.copilot.json` — Copilot numeric source of truth (beside, never inside,
    `data/pricing.json`).
  - `bin/copilot_pricing.py`, `bin/harness_select.py` — shared-core scripts (stdlib, like all of
    `bin/`).
  - `copilot/` — the Copilot harness package: `aesop.yaml` (manifest, source of truth) +
    `.github/` (the native config bundle: `copilot-instructions.md`, `agents/route.agent.md`).
  - `tests/test_copilot_*.py`, `tests/test_harness_select.py`, `docs/COPILOT-HARNESS.md`.
  The bundle lives under `copilot/.github/` (a staging tree no harness reads in place), not the
  repo root, so nothing about this repo's own tooling changes; the selector installs it where
  Copilot actually looks.

- **D2 — Aesop-manifest-first, hand-emitted bundle, zero node in the kit.** `copilot/aesop.yaml`
  is the declarative source of truth for the Copilot side (harnesses, invariants, instruction
  block, agent list), and the `.github/` files are authored **in aesop's emitted formats as of
  commit 5506617** (instructions at `.github/copilot-instructions.md`; agents under
  `.github/agents/` with YAML frontmatter; prompts/skills paths reserved for Phase 2). The kit
  never runs `aesop compile` — the executors have no node toolchain in scope and this repo's
  rails forbid new tooling — so manifest ↔ bundle consistency is enforced by a **unittest**
  (`tests/test_copilot_bundle.py`) instead of by the compiler: every agent named in the manifest
  must exist as a bundle file, the shared doctrine sentence must appear verbatim in both the
  manifest block and `copilot-instructions.md`, and the agent's pinned `model` must be a key in
  `data/pricing.copilot.json`. Divergence pinned deliberately: aesop@5506617 emits agents as
  `<name>.md`, while Copilot CLI's how-to documents `<name>.agent.md`; GitHub's config reference
  accepts both — we use `.agent.md` (the CLI-documented form) and reconciling the emitter is a
  Phase-2 proposal for the aesop repo. The user's own hand-authored Claude Code skills and this
  repo's CLAUDE.md stay hand-authored — aesop drives the **new Copilot side only**.

- **D3 — Copilot pricing schema: AIC as data, absolute cached rates, vendor + tier fields.**
  `data/pricing.copilot.json` mirrors `data/pricing.json`'s shape where that helps
  (`cached_date`, `update_from`, `models`, `task_profiles`) and diverges where GitHub's billing
  model demands it: a `billing_unit` object (`{"name": "AIC", "usd_per_credit": 0.01, ...}` —
  the unit is data, never prose); per-model `cached_input_per_mtok` as an **absolute rate**
  (GitHub publishes absolute cached prices, not one global multiplier); optional
  `cache_write_per_mtok` (Anthropic rows only); optional `long_context` sub-object
  (`threshold_tokens` + step-up rates) for GPT-5.4/5.5 and Gemini 3.1 Pro; optional
  `promo` sub-object with an `until` date (Sonnet 5); a `vendor` field; a `plans` map with
  `included_aic_per_month`. `task_profiles` duplicates the XS–XL token counts from
  pricing.json so each file is self-contained (they are task-size conventions, not prices). The
  two files never merge and neither harness reads the other's — cross-vendor comparison is
  exactly what the Copilot file exists for, and the Claude file's invariants stay untouched.

- **D4 — Cross-vendor routing = aesop's abstract tiers, assigned in data.** Every model carries
  `tier: frontier | strong | mid | cheap` (aesop's vocabulary, so Phase-2 aesop wiring is a
  no-op mapping). Routing logic lives in the route agent's prose (which tier a task deserves)
  while all numbers come from the data at run time via `bin/copilot_pricing.py`. Tier
  assignments are a judgment call pinned once in T1's brief (e.g. Fable 5 + GPT-5.5 = frontier;
  Opus 4.8, GPT-5.3-Codex, Gemini 3.1 Pro = strong) so no executor re-derives them.

- **D5 — The route agent acts through Copilot's own control surfaces.** The agent (pinned
  `model:` on a mid-tier model — routing is judgment work but not frontier work) reads pricing
  via the shared core and recommends; the *user* acts via the confirmed mechanisms (`/model`,
  `copilot --model <id> -p`, `COPILOT_MODEL`, settings.json `model` key, per-agent `model:`
  pins). Unlike Claude Code there is no Agent-tool `model` parameter to dispatch through, so the
  MVP route agent recommends + prints exact commands rather than self-dispatching; agent-to-agent
  dispatch is a Phase-2 design item.

- **D6 — Path resolution: placeholder + install-time absolute paths.** `${CLAUDE_PLUGIN_ROOT}`
  is Claude-Code-only and Copilot has no equivalent, while user-level agents in
  `~/.copilot/agents/` are single files that can't carry a `references/` snapshot. So bundle
  files reference `{{POLYTROPOS_ROOT}}` and `bin/harness_select.py` rewrites it to the
  literal absolute repo root at install time — the same precedent as the statusline exception in
  CLAUDE.md (absolute paths where the env var can't reach). The placeholder must never appear
  resolved inside `copilot/.github/` (test-enforced), and installed copies must never retain it
  (verify-enforced).

- **D7 — Harness selection is detect + install, not a runtime dispatcher.** Each harness already
  auto-loads its native config (Claude Code: the installed plugin; Copilot: `~/.copilot/agents`
  + repo `.github/agents`). So "selecting the harness" means: `bin/harness_select.py detect`
  reports which harness CLIs are on PATH and what (if anything) to do; `install --harness
  copilot` materializes the bundle into a Copilot home; `install --harness claude-code` writes
  **nothing** and explains the plugin is already live from this directory. The kit itself never
  writes to `~/.copilot` — executors always pass `--copilot-home` pointing at a temp dir; the
  real install is a one-line command the user runs.

- **D8 — Stdlib-only shared core, tests in the existing suite.** `bin/copilot_pricing.py` and
  `bin/harness_select.py` follow the existing `bin/` conventions (module docstring, pure
  functions taking the data dict / explicit roots so tests inject fixtures, `main(argv)`,
  argparse subcommands, `--json` flags) and `tests/` conventions (importlib `_load` off
  `BIN_DIR`, synthetic fixtures with fake round numbers, no wall-clock assertions, discovery via
  `python3 -m unittest discover -s tests` — the dotted-module form is broken on this machine by
  a site-packages `tests` package).

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Touch anything outside this repo.** No `~/.claude/`, **no `~/.copilot/`** (harness_select
  runs only with `--copilot-home` pointing at a temp dir during this kit), no edits to the aesop
  checkout at `/path/to/aesop` (reference-only), no plugin
  re-install.
- **Move or edit the live Claude Code plugin surface**: `.claude-plugin/` (marketplace.json,
  plugin.json), `skills/`, existing `bin/` scripts, `data/pricing.json`, or the generated
  mirrors under `skills/*/references/`. The only existing files this kit touches are `CLAUDE.md`
  and `README.md`, via pinned insertions in T9/T10.
- **Run node/npm/`aesop compile`** anywhere, or add any dependency/tooling. Python stays
  stdlib-only; no requirements files; no pytest.
- **Edit `data/pricing.copilot.json` outside its own tasks.** After T1 lands it is the
  Copilot-side numeric source of truth with the same no-hardcoding rules as pricing.json.
- **Build Phase-2 features**: no architect/execute/escalate port to Copilot, no Ralph loop
  wiring, no lessons-loop vendoring, no new Claude Code skills, no repo-root `.github/`, no
  writes into `~/.copilot`, no MCP config, no statusline/cost-report Copilot equivalents.
- **Touch the completed kits** (`.claude/kits/harden-plugin/`, `.claude/kits/aesop-bridge/`) or
  their agents beyond reading them.
- **Commit or push.**

## Risks & tripwires

- **Unverified CLI model-id strings (the big one).** GitHub's docs confirm the `model`
  frontmatter field and the `--model` flag but publish only two concrete ids
  (`claude-haiku-4.5`, `gpt-5.3-codex`). T1's ids follow that observed pattern
  (lowercase, dots for versions, e.g. `claude-sonnet-5`, `gpt-5.4-mini`, `gemini-3-flash`) and
  are best-effort. Mitigations baked in: pricing.copilot.json carries a top-level
  `model_ids_note` telling readers to confirm against `/model`; the route agent must present ids
  as "as listed by `/model`"; docs tell the user to correct ids in ONE place
  (pricing.copilot.json) if the CLI disagrees. Tripwire: if any executor finds authoritative id
  strings that contradict T1, STOP and report — do not silently rewrite the data file.
- **Sonnet 5 post-promo rate unknown.** The GitHub table publishes only the promo rate (until
  2026-08-31). Encoded as current rates + `promo.until` + a note to re-check `update_from` after
  that date. Tripwire: no task may invent a post-promo number.
- **Docs churn.** Copilot CLI ships fast (the model-selection surface itself changed in the
  2026-01-14 release). Every capability claim above carries its source; `cached_date` in the
  data file dates the prices. If repo reality or a fetched doc contradicts a brief, executors
  stop and report per the standing rule.
- **`.agent.md` vs `.md` emitter divergence** (D2): deliberate, documented, reconciled in
  Phase 2 on the aesop side. Tripwire: if a task output "fixes" the extension to match
  aesop@5506617's emitter, that is drift — the bundle uses `.agent.md`.
- **Long-context pricing approximation.** `bin/copilot_pricing.py` applies a model's
  `long_context` step-up rates to the whole estimate when the profile's input tokens exceed the
  threshold — a deliberate conservative simplification (GitHub bills the step-up on the
  over-threshold request, and profiles are coarse anyway). The docstring must say so; tests must
  encode this exact rule, not a blended one.
- **Home-dir agent precedence.** `~/.copilot/agents/route.agent.md` overrides a same-named repo
  agent. Docs (T9) must state this; it is a feature for the user (one global route agent) but a
  surprise if they later add per-repo variants.
- **Live-install hazard.** Any stray edit under `skills/` or `.claude-plugin/` changes the
  user's live Claude Code behavior immediately. The verifier sweeps `git status` for
  out-of-fence modifications on every task.
- **Site-packages `tests` shadowing.** Verify commands use
  `python3 -m unittest discover -s tests [-p '<file>.py']` — never the dotted-module form.

## Phase 2 — out of this kit's scope (designed, not built)

Deferred by decision; the natural next kit(s) after the MVP proves out:

1. **Architect/execute/escalate port.** Copilot custom agents give everything needed:
   kit-pinned implementer/verifier/reviewer as `.agent.md` files with per-agent `model:` pins;
   dispatch via `copilot --agent <name> --model <id> -p "<self-contained brief>"
   --allow-tool ...` from a driver (the orchestrating session or a thin stdlib driver script);
   escalation = re-dispatch the same brief with a `strong`/`frontier`-tier model id from
   pricing.copilot.json. The kit contract (PLAN/TASKS/NOTES, status vocabulary, model field
   overriding agent default) carries over: the task `model` field becomes the `--model` flag.
2. **Loop engineering — Ralph.** Copilot has no first-party goal loop (aesop capability matrix:
   `loop` is a fallback, `goalMode: "ralph"`). Wire aesop's portable Ralph runner
   (`registry/loops/ralph/ralph_loop.py`, three hard stops: iteration ceiling, no-progress
   detector, `budget_usd` cap) with `--harness-cmd "copilot -p"`; feed its per-tick cost
   estimate and budget runway from `bin/copilot_pricing.py est` / a new `runway`-style
   subcommand instead of the runner's flat default. Profiles (`token-lean`/`balanced`/
   `accuracy-max`) select the stop values.
3. **Self-improving primitive — lessons-loop.** Vendor aesop's `registry/skills/lessons-loop`
   (prompted-Reflexion: corrections → durable rules in `tasks/lessons.md`, reloaded at session
   start) into `copilot/.github/skills/lessons-loop/` and list it in `copilot/aesop.yaml`
   `primitives.skills`; add a routing-specific lesson category (misrouted tasks become routing
   rules the route agent reloads).
4. **Aesop compile round-trip.** Make the copilot bundle a real aesop compile target: expose
   this repo's copilot content to aesop's registry lookup, run `aesop compile` from the built
   checkout, and reconcile the `.agent.md` extension in aesop's copilot emitter (a proposal for
   the aesop repo, through its own phase-gated process — never from here).
5. **Cost visibility.** A Copilot `/usage`-equivalent report (whatever session/usage surface the
   CLI exposes by then) mirroring `cost-report`; org/Business pooled-AIC awareness in `runway`.
