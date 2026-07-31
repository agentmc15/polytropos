# polytropos — complete guide & cookbook

The full reference for the plugin: what every skill does, how the iterative workflows chain, how
the **routing scorecard** proves the cheap models held, how **aesop** fits alongside it, and
**11 worked examples** spanning one-off tasks, greenfield builds, brownfield work, backlog
burndown, and security.

- Companion architecture deep-dive: [HOW-IT-WORKS.md](HOW-IT-WORKS.md) · [how-it-works.html](how-it-works.html)
- Aesop integration reference: [AESOP-INTEGRATION.md](AESOP-INTEGRATION.md)
- Styled version of this guide: [guide.html](guide.html)

> Prices in this document are a **labeled snapshot** (cached `2026-07-24`) of
> `data/pricing.json` — the single source of truth. Nothing else hard-codes a price; when
> `pricing.json` changes, these tables are updated together with its `cached_date`.

---

## Table of contents

1. [The one idea](#1-the-one-idea)
2. [The model lineup and the two billing modes](#2-the-model-lineup-and-the-two-billing-modes)
3. [The one hard constraint](#3-the-one-hard-constraint)
4. [What each skill does](#4-what-each-skill-does)
5. [The iterative workflows](#5-the-iterative-workflows)
6. [The routing scorecard — proving the cheap models held](#6-the-routing-scorecard--proving-the-cheap-models-held)
7. [What aesop is, and how it fits](#7-what-aesop-is-and-how-it-fits)
8. [The 11 examples](#8-the-11-examples)

---

## 1. The one idea

Claude Code runs one model per session, and the price spread across the lineup is large. Running
the frontier model as a standing default is harmless on a subscription (marginal dollars are
zero) but becomes a 2×–10× overpayment the moment you move to pay-per-token. The plugin's whole
job is to **spend frontier-model capability only where it changes the outcome, and make that
capability persist afterward** so cheaper models finish the work at near-frontier quality.

Three moves make that real:

- **Route per task** — decide the cheapest *sufficient* model before running, with a cost estimate.
- **Escalate, don't default** — start cheap behind a check; promote to Fable 5 only on failure, or
  concentrate Fable in a one-time planning phase whose judgment is written down as scaffolding.
- **See the spend, and prove it held** — historical transcript analysis, an ambient statusline, and
  a routing scorecard that audits whether the cheap tiers actually held quality.

---

## 2. The model lineup and the two billing modes

Labeled snapshot (cached `2026-07-24`, from `data/pricing.json`):

| Model | Input $/MTok | Output $/MTok | Best for |
|---|--:|--:|---|
| **Fable 5** | 10 | 50 | Long-horizon autonomous work, hardest reasoning, planning |
| **Opus 5** | 5 | 25 | Multi-file features, hard debugging, review — the daily driver |
| **Opus 4.8** | 5 | 25 | Superseded by Opus 5 at the same rate; costing historical transcripts |
| **Sonnet 5** | 3 (2 intro until 2026-08-31) | 15 (10 intro) | Day-to-day workhorse; near Opus-tier at high effort |
| **Haiku 4.5** | 1 | 5 | Classification, extraction, bulk API calls |

The same routing question gets **opposite answers** depending on how tokens are paid for. Every
skill reads the mode from `pricing.json → billing_mode` (currently `subscription`), overridable
per invocation with `--api` / `--sub`.

- **`api` mode — optimize dollars.** Any pay-per-token usage (an app you're building, or Claude
  Code on API-key billing). The cheapest *sufficient* model wins; Haiku earns its keep; cache
  reads (0.1×), the 50% batch discount, and Sonnet's intro pricing all factor in.
- **`subscription` mode — optimize rate-limit burn.** On a plan, marginal dollar cost is zero; the
  scarce resource is the 5-hour and 7-day windows. Haiku is pointless (you'd only lose
  capability), the daily driver is the best sustainable model, and burn is managed with **effort
  levels**, not model downgrades. Dollar figures are labeled *API-equivalent burn* — a proxy for
  window pressure, not spend.

The mode attaches to the **question, not the user**: "which model should my app call?" is always
an `api`-mode question, even asked from a subscription session.

---

## 3. The one hard constraint

**Nothing in Claude Code can programmatically switch the main session's model** — only you, via
`/model`. Two things *are* programmable, and every automation in the plugin is built on them:

1. **Subagents pin models.** Agent frontmatter declares `model: sonnet` (aliases
   `haiku`/`sonnet`/`opus`/`fable`), and the Agent tool takes a per-dispatch `model` parameter.
2. **Skills orchestrate.** A skill can't change the model it runs on, but it can dispatch work to
   subagents on any model and grade the results.

So the router is **advisory** for the main session (it prints the `/model` command) and
**operational** for everything it can delegate. "Opus checks, then calls Fable automatically" is
always: the orchestrator stays on its model and dispatches a Fable *subagent*.

---

## 4. What each skill does

### `/polytropos:route <task>`
Picks the right model for one task and estimates its cost before you run it.
1. **Resolve mode** — `--api`/`--sub` flag > task framing (app-building forces `api`) > pricing.json default.
2. **Classify** — in `api` mode, a cheapest-sufficient ladder Haiku → Sonnet 5 → Opus 4.8 → Fable 5,
   ties broken *down* with an explicit "upgrade if you see X" signal; in `subscription` mode, Opus
   as daily driver, complex work escalating toward Fable via the architect pattern, Haiku skipped,
   effort as the burn lever.
3. **Estimate** — match a task-size profile (XS…XL), price each candidate, show cache-discounted
   figures for agentic sizes, apply intro/batch adjustments.
4. **Recommend + act** — compact table, recommendation bolded, then *dispatch now* (Agent tool with
   the recommended `model` + a self-contained brief), *switch the session* (prints `/model …`), or —
   for big Fable-worthy tasks — hand off to `/architect`. App questions get a model ID + API params.

### `/polytropos:architect <task>`
**Fable 5 runs once, at the start; its judgment persists as scaffolding.** Pay frontier rates for
the phase that buys the most — decomposition, contracts, guardrails — and encode the results so
cheaper models execute at near-Fable quality. Two entry modes: from an Opus/Sonnet session it
dispatches a **Fable subagent** (the session never changes model); or run natively after
`/model fable`. It produces an **execution kit** in the target project:
- `.claude/kits/<slug>/PLAN.md` — goal, constraints, out-of-scope fence, architecture decisions
  *with rationale*, risks with tripwires.
- `.claude/kits/<slug>/TASKS.md` — ordered tasks, each a self-contained brief (files, conventions,
  exact contracts, gotchas, acceptance criteria, a shell **verify command**, a suggested `model`),
  grouped under `## Phase N` headings, marked `depends:` / `independent:`.
- `.claude/agents/<slug>-{implementer,verifier,reviewer}.md` — model-pinned (sonnet / haiku / opus)
  so the model mix self-enforces.
- Guardrails in `CLAUDE.md` or a project skill. **Aesop-managed target?** If the project has an
  `aesop.yaml` or an `<!-- aesop:begin` fence, those files are compiled output — the architect puts
  guardrails in `aesop.yaml` under `primitives.instructions.blocks` + `aesop compile` instead.

### `/polytropos:execute <slug>`
The kit orchestration loop, run on the daily driver — faithful dispatch, verification, and
state-keeping; it does not re-litigate the plan. Per task: mark `in-progress` → dispatch the brief
**verbatim** to the implementer (passing the task's `model` as the Agent `model` parameter, which
overrides the agent's frontmatter default) → **verify independently** (run the verify command
yourself *and* dispatch the fresh-context verifier — the implementer's success claim is never
evidence) → on pass mark `done` and append learnings to `NOTES.md`; on fail retry once with the
failure output, then mark `blocked`. Independent tasks dispatch in parallel; phase boundaries
trigger the Opus reviewer. **Escalation valve:** a blocked task goes back to Fable as a
single-task consult (one brief + failure evidence + plan excerpt). In an aesop-managed project,
compiled/fenced files are treated as read-only.

**Fusion-era loop.** The orchestrator runs **lean** — it reads only kit state and verify output,
delegating exploration to cheap **haiku scouts** rather than pulling files into its own context.
A serial chain of tasks on the *same file and same model* can reuse **one warm implementer**
(a "sidekick" continued across the chain, ~4-task cap; verifiers are always fresh spawns). It
writes the `outcome:` and (optionally) `agent:` ledger lines the scorecard reads, and does
**upgrade-only, autonomy-gated live re-routing**: when a tier's first-try rate sags mid-run it
recommends exactly one tier up (haiku→sonnet, sonnet→opus) — **advisory** prints by default, or,
with PLAN.md's optional `autonomy: auto` dial, applies a budget-capped runtime `model` override for
the next dispatch. It **never** auto-routes to frontier and **never** rewrites a task's `model`
field — Fable stays reachable only through the evidence-carrying escalation valve.

### `/polytropos:escalate <task>`
The per-task sibling of execute's escalation valve — a verify-gated, cost-ascending ladder.
0. **Pin a machine-checkable success check** (the escalation trigger). No checkable outcome →
   say so; don't pretend a vibe is a verify.
1. Pick the **cheapest sufficient tier**.
2. Dispatch a subagent with a self-contained brief + the verify command.
3. **Verify yourself.** Pass → done (Fable never touched). Fail → retry once with the failure
   output. Fail again → escalate.
4. Dispatch a **Fable subagent** carrying the task, the verify command, and the failure evidence.
   The always-available cost lever is **scope** (hand it the diagnosis, not a blank re-attempt);
   the **effort** lever (`medium`) applies only where the invocation exposes per-agent effort.
   Refusal fallback: a Fable `refusal` stop reason → retry that hop on Opus 4.8.

### `/polytropos:fable-check <task>`
The judgment reference: **is Fable worth it here, and how to run it.** Route to Fable for
long-horizon autonomous work, problems Opus already failed on, deep research, and heavy parallel
sub-agent orchestration — **not** for routine coding, solved problems, work Sonnet handles at high
effort, or **security-analysis-heavy work** (Fable's cyber classifiers refuse much of it; Opus 4.8
is the better tool there). Surfaces the caveats every time: `refusal` stop reason (Opus fallback),
minutes-long turns, the 30-day data-retention requirement, always-on thinking. Optimal use: full
spec up front, sweep effort (Fable at `low` often beats older models at `max`), de-prescribe
prompts, let it delegate, give it a memory surface.

### `/polytropos:cost-report`
Wraps `bin/cost_report.py` (python3, stdlib only). Walks `~/.claude/projects/**/*.jsonl`, dedupes
by message id, normalizes model strings onto pricing keys (unknowns tallied, never dropped), and
prices each record from `pricing.json` (intro rates applied by date). Reports spend by model, top
sessions, and **downgrade candidates** — Fable/Opus-only sessions with a Sonnet-sized footprint,
with the exact delta of re-pricing at Sonnet 5. `--days N`, `--mode api|subscription`.

### `/polytropos:journal`
Builds the **daily work journal**. A read-only collector (`bin/journal_collect.py`) sweeps *today's*
AI usage across **Claude Code, Copilot CLI, and Codex CLI** — plus git activity — into a
**metadata-only** `digest.json` (session counts, models, token/turn tallies, commits — never any
transcript text). `bin/journal_summarize.py` then writes three summaries — `narrative.md`,
`technical.md`, `next-day.md` — under the gitignored `journal/<date>/`; its `claude -p` runner is
injectable and `--dry-run` prints the prompts and spawns nothing. `bin/journal_schedule.py` installs
a macOS launchd job for a nightly run. Codex activity is counted but never priced (no Codex prices
exist in `data/` by design). `allowed-tools: Bash, Read, Write`.

### `/polytropos:setup`
Installs the statusline into `~/.claude/settings.json` with confirmation. `bin/statusline.py`
prints one line: model name **color-coded by price tier** (red = Fable, amber = Opus, green =
Sonnet, cyan = Haiku), effort, estimated session cost, context %, and — on subscription sessions —
5h/7d rate-limit burn. The command written into settings must be a **literal absolute path**
(`${CLAUDE_PLUGIN_ROOT}` doesn't exist outside plugin context). Costs shown are client-side
estimates, not bills.

### Companion scripts (the aesop bridge)
- `bin/sync_pricing_refs.py` — writes byte-identical mirrors of `pricing.json` into
  `skills/{route,fable-check}/references/` so those skills stay self-contained when vendored into
  another repo by aesop. Rerun it whenever `pricing.json` changes (a test fails on drift).
- `bin/aesop_bridge.py` — turns `pricing.json` into the concrete numbers aesop's abstract dials
  need: `tiers` (which model each aesop tier maps to now), `est-tick` (estimated cost per goal-loop
  iteration), `check-budget` (how many iterations a `budget_usd` buys).

---

## 5. The iterative workflows

The plugin is a set of **loops**, each spending Fable proportionally to genuine difficulty.

**The escalation ladder (`/escalate`, one task).** cheap attempt → *verify* → fail → retry with the
error → *verify* → fail → Fable subagent with the failure evidence → *verify*. Terminates the
instant a check passes; Fable is reached only by the hard fraction.

**The kit lifecycle (`/architect` → `/execute`, many tasks).**
```
daily driver ── /architect ──► Fable runs ONCE ──► execution kit (PLAN, TASKS, agents, guardrails)
                                                          │
                              /execute ◄──────────────────┘   loop, on the daily driver:
                                 ├─ dispatch brief verbatim (task's model pin)
                                 ├─ verify independently (command + fresh-context verifier)
                                 ├─ pass → done + NOTES.md   |   fail → retry once → blocked
                                 ├─ blocked → single-task Fable consult → resume cheap
                                 └─ phase end → Opus reviewer checks against PLAN.md
```
Fable spend = the one planning pass plus the occasional consult. Execution quality is bounded below
by the kit, not by the executor's unaided judgment. This guide's own existence is an example:
**11 kits have shipped this way** — each architected once by Fable, then executed on Sonnet/Opus
with adversarial verifiers and phase reviews. The routing scorecard (§6) audits the result:
**32/32 first-try task passes, zero escalations, zero execution work on Fable.**

**The aesop goal loop (recurring, verifiable work).** A portable "Ralph" runner: a fresh agent
invocation per tick against a fixed prompt, `self_verify()` after every tick, and **three hard
stops** — an iteration ceiling, a no-progress detector, and a `budget_usd` cap. Right for
grindable, measurable goals ("keep the test suite green", "fix CI"); the kit pattern is for
judgment-heavy builds. `bin/aesop_bridge.py check-budget` sizes the budget stop from real prices.

**The routing ladder (`/route`, decision only).** In `api` mode, cheapest-sufficient with ties
broken down; in `subscription` mode, Opus daily driver with effort as the lever and Fable reached
via the architect pattern.

---

## 6. The routing scorecard — proving the cheap models held

The loops above are only trustworthy if you can *check* that the cheap tiers held — that routing
Sonnet/Opus instead of defaulting to Fable didn't quietly cost quality. That is the **measurement
layer**: `bin/routing_scorecard.py`, fed by ledger lines the executor writes as it runs. Every mode
is **read-only** except two clearly-marked writes, every mode has a `--demo`, and nothing is ever
fabricated — missing data renders `null`/`n/a`, never a guessed or zeroed figure.

**Four execute-owned ledger lines** (appended to a kit's `NOTES.md`) feed it:

| Line | Written | Carries |
|---|---|---|
| `outcome:` | one per finished task | model, attempts, pass/blocked/escalated, review result |
| `reroute:` | when a live upgrade fires | from-tier → to-tier, advisory/applied, the rate that triggered it |
| `session:` | optional, once per run | the run's session id — attaches real transcript dollars |
| `agent:` | optional, per dispatch | the subagent id + role — enables per-task dollar attribution |

**Five additive modes** (all off one script):

- **`routing_scorecard.py <kit>`** (plain) — parses `TASKS.md` + the `outcome:` ledger into a
  verdict: per-task outcomes, model mix, and the **cheap-model review-survival rate**. Add
  `--session <id>` to fold in real transcript dollars beside an **all-Fable counterfactual**.
- **`--live`** — a mid-run re-route signal: each tier's live first-try rate and an **upgrade-only,
  one-tier-step, never-frontier** recommendation (haiku→sonnet, sonnet→opus). Loads no pricing,
  writes nothing.
- **`--history [--kits-dir DIR …]`** — the cross-kit per-tier track record (first-try rate,
  escalation rate, re-route tallies, and dollars for the kits carrying a `session:` line).
  `--kits-dir` is **repeatable** → cross-repo, namespacing rows `<label>/<kit>`; a lone dir stays
  byte-identical to today's output.
- **`--by-task`** (requires `--session`) — per-task dollars by role from the `agent:` ledger. The
  orchestrator's own transcript is **one un-split line**; a warm-cluster shared transcript is
  attributed to the cluster **as a unit**; a task whose transcript is gone reads `null`, never a
  guess.
- **`--snapshot` / `--trend`** (both ride `--history`) — `--snapshot` writes the history card as a
  dated JSON into the gitignored `trends/` store (**the one sanctioned write**); `--trend` renders
  per-tier first-try rate across stored snapshots as a **text table** (needs ≥2 snapshots, else it
  says so).

`bin/session_cost.py` is the single-session companion: it prices **one** session — the main
transcript plus each subagent's `*.output` — against an **all-one-model counterfactual**, so you
see what a run cost and what defaulting to Fable *would* have cost.

*Real track record:* **11 kits** have now shipped through architect → execute — harden-plugin,
aesop-bridge, copilot-harness, copilot-workflow, copilot-costviz, daily-journal, fusion-tier1,
fusion-tier2, routing-history, per-task-dollars, crossrepo-trend — for **32/32 first-try task
passes, zero escalations, and zero execution work on Fable**. This guide is one of their outputs.

## 7. What aesop is, and how it fits

**Aesop** (`github:agentmc15/aesop`) is an *environment compiler* for AI coding agents. One
manifest — `aesop.yaml` — is compiled into native configuration (instruction files, skills,
subagents, commands, MCP servers, hooks, permissions, loops, goals) for **any harness**: Claude
Code, Codex, Copilot, Cursor, Antigravity, VS Code. It federates content registries, offers
**pathway profiles** as a cost/accuracy dial (`token-lean` → `balanced` → `accuracy-max`), and
runs **goal loops with the three hard stops**. *(Aesop behavior described here is pinned to aesop
commit `5506617`.)*

The key fact for integration: **aesop is deliberately price- and model-version-agnostic.** Its
tiers are abstract (`strong` → opus, `mid` → sonnet, `cheap` → haiku), its budget stops are plain
dollar numbers, and its loop runner falls back to a flat per-tick cost estimate. That is exactly
the gap polytropos fills.

**Two layers, one boundary:**

| Layer | Owns | Examples |
|---|---|---|
| **aesop** | The harness-portable *environment* | `aesop.yaml`, compiled `CLAUDE.md`/`AGENTS.md`, pathways, goal loops, drift-checking |
| **polytropos** | The Claude-concrete *pricing/routing* | live rates in `pricing.json`, task-size cost math, the Fable architect/execute posture |

Integration goes one way — **aesop consumes this repo; nothing here imports aesop**:
1. **Registry.** This repo's `skills/<name>/SKILL.md` layout already matches aesop's registry
   lookup, so `aesop add skill route --from polytropos` (and `fable-check`) vendors them,
   pricing snapshot riding along. `cost-report`, `setup`, `architect`, `execute` stay plugin-only
   (they depend on `bin/` scripts, `~/.claude` paths, or the Agent-tool `model` parameter).
2. **Bridge numbers.** `bin/aesop_bridge.py` feeds aesop's abstract dials real values —
   `tiers`/`est-tick`/`check-budget` — computed from `pricing.json`, to paste into `aesop.yaml`.
3. **Managed-project etiquette.** `/architect` and `/execute` detect aesop-managed projects and
   treat compiled/fenced files as read-only, writing guardrails into `aesop.yaml` instead.

Full detail: [AESOP-INTEGRATION.md](AESOP-INTEGRATION.md).

### The second harness — GitHub Copilot CLI
The same per-task routing/cost discipline is ported to **GitHub Copilot CLI** under `copilot/`: a
cross-vendor `route` agent plus an architect → execute → verify → escalate port and a
budget-capped **Ralph** goal loop. Copilot usage settles in **AI Credits** (1 AIC = $0.01), priced
by `bin/copilot_pricing.py` (`est` / `models` / `runway`) from a **separate**
`data/pricing.copilot.json` — the two harnesses never share a pricing file. The bundle under
`copilot/.github/` carries a `{{POLYTROPOS_ROOT}}` placeholder that `bin/harness_select.py`
resolves to an absolute path at install time. `bin/copilot_usage.py` reads Copilot's local session
events read-only for a usage report; `bin/copilot_ralph.py --demo` mocks the goal loop with no
model, network, or AI Credits spent.

---

## 8. The 11 examples

Each example labels its **category**, the **command(s)**, what **happens**, and **why**.

### Example 1 — Task · "Which model, and what will it cost?"
**Command:** `/polytropos:route add input validation to the signup form handler`
**Happens:** route resolves `subscription` mode, classifies the task as routine single-file work,
and prints a compact table: Sonnet 5 (recommended, effort `medium`), Opus 4.8 (overkill here),
with API-equivalent burn per candidate from the XS/S profile. It then offers to *dispatch now* or
prints `` `/model sonnet` ``.
**Why:** the cheapest sufficient model for routine edits is Sonnet 5; the estimate is a burn proxy,
not a bill. This is the everyday "should I even be on Opus for this?" check.

### Example 2 — Task · Dispatch a self-contained job to a cheaper subagent
**Command:** `/polytropos:route --sub write unit tests for utils/date.py`
**Happens:** route recommends Sonnet 5 and offers *dispatch now*. You accept; the orchestrator
writes a self-contained brief (the subagent sees none of your conversation), dispatches
`Agent(model="sonnet")`, and relays the result. Your Opus session's context stays clean.
**Why:** delegation is the automatable half of routing (the session model can't be switched
programmatically). Read-heavy or context-polluting work belongs in a pinned-cheap subagent.

### Example 3 — Task · Try it cheap, fall back to Fable only if it fails
**Command:** `/polytropos:escalate implement an RFC-3339 duration parser that passes tests/test_duration.py`
**Happens:** escalate pins the verify command (`python3 -m pytest tests/test_duration.py`),
dispatches a Sonnet subagent, then **runs the tests itself**. Green → done, Fable never touched.
Red twice → a Fable subagent gets the failing output and the diagnosis; escalate re-runs the tests
to confirm.
**Why:** frontier capability is spent *only* on the fraction the cheap tier fails — and the trigger
is an objective check, not a guess. (Verified end-to-end: a naive attempt failing subtractive
Roman-numeral cases was resolved by a real Fable hop; a real semver-precedence task passed on
Sonnet with no escalation at all.)

### Example 4 — Greenfield · Plan once with Fable, build cheap
**Commands:** `/polytropos:architect build a markdown-to-slides CLI: parse a .md file into
slides, render to a self-contained HTML deck, with a --watch mode` → then
`/polytropos:execute md-slides`
**Happens:** a Fable subagent interrogates the scope once and writes the kit — PLAN.md (parser vs
renderer boundary, the deck format contract, watch-mode debounce decision, all with rationale),
~12 task briefs each with a verify command, three model-pinned agents, and CLAUDE.md conventions.
Fable's involvement ends (~10–20 min). `/execute` then runs for the rest of the build on
Sonnet/Opus: implementer builds each task, verifier re-runs its check in fresh context, the Opus
reviewer checks each phase against the plan.
**Why:** greenfield is where up-front decomposition pays the most. One frontier planning pass sets
the contracts; cheap models fill them in at near-Fable quality.

### Example 5 — Greenfield · A new project under aesop, fed by the bridge
**Commands:**
```
aesop init && aesop compile && aesop doctor --fix        # scaffold the environment (start token-lean)
python3 bin/aesop_bridge.py tiers                         # which concrete model each tier means now
python3 bin/aesop_bridge.py check-budget 25 M claude-sonnet-5   # does budget_usd:25 buy enough iterations?
/polytropos:architect <the build spec>             # detects aesop.yaml → guardrails go in the manifest
/polytropos:execute <slug>
```
**Happens:** aesop compiles a correct, drift-checked environment for every harness you selected.
The bridge tells you `strong→claude-opus-4-8, mid→claude-sonnet-5, cheap→claude-haiku-4-5` to pin
in profiles, and sizes the goal-loop budget from real prices. `/architect`, seeing the
`<!-- aesop:begin` fence, writes its guardrails into `aesop.yaml` (`primitives.instructions.blocks`)
and recompiles rather than hand-editing the compiled `CLAUDE.md`.
**Why:** aesop builds the static rails once; the optimizer decides the model economics inside them.
The two layers compose cleanly — this is the recommended greenfield path when you use multiple
harnesses or a team.

### Example 6 — Brownfield · Review an existing codebase
**Command:** `/polytropos:architect review this service for correctness bugs and
architecture risk; produce a prioritized, verifiable fix plan`
**Happens:** Fable reads across the subsystems once and emits a kit whose PLAN.md is the review
(findings ranked by severity, each empirically confirmed) and whose TASKS.md is the prioritized,
individually-verifiable fixes with model pins. You then `/execute` the fixes cheaply.
**Why:** "understand this code and tell me what's wrong" is judgment-heavy — worth one Fable pass —
but the *fixing* is routine once the findings are pinned. This is exactly how the plugin's own
harden-plugin kit was built: a Fable review that became a fix-it kit executed on Sonnet/Opus.

### Example 7 — Brownfield · A large migration or refactor
**Commands:** `/polytropos:architect migrate all call sites from the deprecated fetchJSON()
to the new typed httpClient; preserve behavior` → then `/polytropos:execute http-migration`
**Happens:** Fable pins the exact old→new contract and writes one self-contained brief per call
site (with worktree isolation where sites would collide), all model-pinned to Sonnet. `/execute`
fans out the independent sites in parallel; each verifier re-runs the touched tests; a site whose
behavior can't be preserved cleanly becomes a single-task Fable consult rather than stalling the
run.
**Why:** mechanical breadth belongs on cheap models in parallel; only the genuinely ambiguous sites
reach Fable. The contract pinned once keeps 40 parallel edits consistent.

### Example 8 — Backlog · Burn it down cost-optimally, then keep it green
**Commands (one-off backlog):** for each item, `/polytropos:escalate <item with its check>` —
or, if the items share a theme, one `/polytropos:architect <backlog theme>` producing a
multi-task kit you `/execute`.
**Commands (recurring maintenance):** an aesop goal loop with a bridge-sized budget:
```
python3 bin/aesop_bridge.py check-budget 25 M claude-sonnet-5   # size the budget_usd stop
# aesop.yaml → loops: [{ name: green-tests, goal: "suite passes", verify: "npm test",
#                        stops: { max_iterations: 40, no_progress_after: 3, budget_usd: 25 } }]
```
**Happens:** the one-off backlog is cleared with Fable touched only on the items a cheap tier fails.
The recurring "keep it green" work runs as a bounded goal loop — verify after every tick, halting
on the iteration ceiling, the no-progress detector, or the dollar cap.
**Why:** a backlog is a stream of independent tasks with objective checks — the ideal shape for
verify-gated escalation (dollars concentrate on the hard few) and for a hard-stopped goal loop
(unbounded loops are the classic production failure).

### Example 9 — Security · Reviewing a diff (and why *not* Fable)
**Commands:** `/security-review` (built-in) for the pending diff; for model choice on the analysis,
`/polytropos:route --sub security review of the new auth/session changes`
**Happens:** route recommends **Opus 4.8, not Fable 5**, and says why: Fable's cyber-adjacent
safety classifiers **refuse** much security-analysis work (`stop_reason: "refusal"`), and Opus 4.8
is the stronger tool for cybersecurity analysis regardless. If a Fable hop is ever mid-flight and
returns a refusal, escalate's **refusal fallback** reruns that hop on Opus 4.8.
**Why:** more expensive is not more capable here. This is the one place the "escalate to Fable"
instinct is wrong — `fable-check` encodes it so you don't learn it the hard way.

### Example 10 — Security · Hardening an existing codebase as a kit
**Commands:** `/polytropos:architect harden this plugin: fix confirmed bugs, add a regression
test suite, close contract drift, without changing public behavior` → then
`/polytropos:execute harden-plugin`
**Happens:** Fable produces a kit whose PLAN.md lists only *empirically confirmed* findings (each
with a repro), a fenced out-of-scope section, and fix tasks with verify commands; the kit's
verifier agent re-runs every check adversarially in fresh context and the reviewer catches drift
at each phase boundary. Execution runs on Sonnet/Opus; only genuinely blocked tasks consult Fable.
**Why:** hardening is a review (Fable-worthy, once) plus disciplined, individually-verified fixes
(cheap). This is a real worked precedent — the plugin's own `harden-plugin` kit did exactly this,
finishing 8 tasks with every phase reviewer-approved. For the *security-analysis* portions of such
work, pin Opus rather than Fable (Example 9).

### Example 11 — Measurement · Prove the cheap tiers actually held
**Command:** `python3 bin/routing_scorecard.py harden-plugin --session <id>` (after `/execute`
finishes and has recorded its `outcome:` / `session:` lines)
**Happens:** the scorecard parses `TASKS.md` + the `outcome:` ledger into a verdict — per-task
outcomes, the model mix, and the **cheap-model review-survival rate** — then, from the `session:`
line, folds in the run's real transcript dollars beside an **all-Fable counterfactual**. Across the
plugin's own 11 kits it reads 32/32 first-try passes with zero escalations. `--history` widens the
lens to the per-tier track record across every kit; `--by-task` (with `--session`) splits the
dollars per task by role; `--snapshot` / `--trend` chart first-try rate over time.
**Why:** routing cheap is only a saving if quality held — this closes the loop with evidence, not
faith. Nothing is fabricated: a missing transcript reads `null`, never a guess.

---

*polytropos · guide generated 2026-07-01, refreshed 2026-07-24 · prices are a labeled
snapshot cached `2026-07-24` in `data/pricing.json` (single source of truth) · aesop claims pinned
to commit `5506617`.*
