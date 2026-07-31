# How polytropos works

An in-depth walkthrough of the plugin's architecture, the reasoning behind it, and every component's mechanics. Companion HTML version: [`how-it-works.html`](how-it-works.html).

---

## 1. The problem

Claude Code sessions run on one model at a time, and the price spread across the lineup is large:

| Model | Input $/MTok | Output $/MTok | Relative cost |
|---|---:|---:|---|
| Fable 5 | $10 | $50 | 2× Opus, ~3.3× Sonnet, 10× Haiku |
| Opus 5 | $5 | $25 | baseline daily driver |
| Opus 4.8 | $5 | $25 | superseded by Opus 5 at the same rate |
| Sonnet 5 | $3 ($2 intro until 2026-08-31) | $15 ($10 intro) | near Opus-tier at high effort |
| Haiku 4.5 | $1 | $5 | bulk/simple API work |

*(Prices cached 2026-07-24 in `data/pricing.json` — the single source of truth; nothing else hard-codes a price.)*

Running Fable 5 as a standing default is harmless on a subscription (dollars don't change) but becomes a 2×–10× overpayment the day Fable moves to pay-per-token — a real 30-day baseline measured on this machine showed **~$614 API-equivalent with 87% of it on Fable 5**, mostly from cache reads in long agentic sessions.

The plugin solves three problems:

1. **Per-task routing** — which model should handle *this* task, with a cost estimate before running it.
2. **The Fable escalation pattern** — use Fable 5 only for the portion of work that needs it, and make its quality persist after you leave it.
3. **Visibility** — historical spend analysis and an ambient statusline so drift is noticed, not discovered on an invoice.

## 2. Two billing modes with opposite goals

The same routing question gets opposite answers depending on how tokens are paid for. Every skill reads the mode from `data/pricing.json → billing_mode` (overridable per invocation with `--api` / `--sub`).

**`api` mode — optimize dollars.** Any pay-per-token usage: an application you're building, or Claude Code on API-key billing. The cheapest *sufficient* model wins. Haiku 4.5 earns its keep for classification, extraction, and bulk calls. Cache discounts (reads at 0.1×), batch processing (50% off), and Sonnet 5's introductory pricing all factor into the estimate.

**`subscription` mode — optimize rate-limit burn.** Claude Code / Claude UI on a plan: the marginal dollar cost of any request is zero, and the only scarce resource is the 5-hour and 7-day rate-limit windows. Consequences:

- **Haiku is pointless** — downgrading saves nothing that matters; you'd only lose capability.
- The daily driver should be the best sustainable model (**Opus 4.8** in this setup).
- Burn is managed with **effort levels** (`low`/`medium` for routine work), not model downgrades.
- Dollar figures are still shown, but labeled *API-equivalent burn* — a proxy for how hard a task hits the windows.

A subtlety the router handles: the mode attaches to the *question*, not the user. "Which model should my app call?" is always an `api`-mode question, even when asked from a subscription session.

## 3. The one constraint that shapes everything

**Nothing in Claude Code can programmatically switch the main session's model.** Not a hook, not a skill, not a settings write mid-session — only the user typing `/model`. Two things *are* programmable:

1. **Subagents can pin models.** An agent file's frontmatter can declare `model: sonnet` (aliases `haiku`/`sonnet`/`opus`/`fable` or full IDs), and the Agent tool accepts a per-invocation `model` parameter.
2. **Skills can orchestrate.** A skill can't change the model it runs on, but it can *dispatch* work to subagents on any model.

So the router is advisory for the main session (it prints the `/model` command) and *operational* for everything it can delegate. The entire architect/execute design is built on lever #1: model choice is embedded in agent files, where it enforces itself.

## 4. Component architecture

```
polytropos/
├── .claude-plugin/plugin.json      manifest
├── data/
│   ├── pricing.json                Claude prices, cache/batch multipliers, task-size
│   │                               profiles, billing_mode — single source of truth
│   └── pricing.copilot.json        Copilot prices in AI Credits — a separate source of
│                                   truth; the two pricing files never merge
├── skills/                         each skill = one slash command
│   ├── route/SKILL.md              per-task routing + cost estimate + dispatch
│   ├── architect/SKILL.md          Fable-as-architect: plan + execution kit
│   ├── execute/SKILL.md            kit orchestration loop on cheaper models
│   ├── escalate/SKILL.md           one task, cheapest tier, verify-gated Fable fallback
│   ├── fable-check/SKILL.md        "is Fable worth it here, and how to run it"
│   ├── cost-report/SKILL.md        wraps bin/cost_report.py
│   ├── journal/SKILL.md            daily cross-tool work journal
│   └── setup/SKILL.md              installs the statusline (with consent)
├── bin/                            python3, stdlib only — no pip, no requirements
│   ├── routing_scorecard.py        routing-quality + dollars scorecard (five modes)
│   ├── session_cost.py             one session's cost vs an all-one-model counterfactual
│   ├── cost_report.py              historical transcript analyzer
│   ├── statusline.py               one-line ambient status
│   ├── agent_tracker.py            statusline hook: live subagent + Fable usage tally
│   ├── sync_pricing_refs.py        regenerates the vendored pricing mirrors
│   ├── aesop_bridge.py             aesop (env-compiler) interop
│   ├── harness_select.py           detects harnesses; installs the Copilot bundle
│   ├── copilot_pricing.py          Copilot cost engine (USD + AIC)
│   ├── copilot_execute.py          Copilot architect→execute→verify port
│   ├── copilot_ralph.py            budget-capped Ralph goal loop
│   ├── copilot_usage.py            Copilot usage report (reads ~/.copilot read-only)
│   ├── journal_collect.py          deterministic daily digest collector
│   ├── journal_sources.py          per-tool read-only ingestion adapters
│   ├── journal_summarize.py        routed-model narrative/technical/next-day writer
│   └── journal_schedule.py         macOS launchd nightly scheduler
├── copilot/                        the Copilot CLI harness bundle (aesop.yaml + .github/)
└── .claude/
    ├── kits/<slug>/                PLAN.md + TASKS.md + NOTES.md — one execution kit
    └── agents/                     per-kit model-pinned implementer/verifier/reviewer trio
```

Three families of `bin/` script, plus plumbing: the **routing/cost core**
(`routing_scorecard.py`, `session_cost.py`, `cost_report.py`, `statusline.py`,
`agent_tracker.py`), the **Copilot harness** (`copilot_*`), and the **daily journal**
(`journal_*`) — the two extensions get their own sections (§7). Subsections below cover the
Claude-side pieces in dependency order.

### 4.1 `data/pricing.json`

Everything numeric lives here: per-model input/output rates, `intro_pricing` windows (Sonnet 5's $2/$10 until 2026-08-31 is applied automatically by date), cache multipliers (reads 0.1×, 5-minute-TTL writes 1.25×), the 50% batch discount, per-model context windows and notes, the default `billing_mode`, and the task-size token profiles used for estimation. When prices change, this file is the only edit; bump `cached_date`. Its Copilot-side twin, `data/pricing.copilot.json`, is the same kind of single source of truth for the Copilot harness (§7) — the AI-Credit unit itself is data — and the two files never merge; neither harness reads the other's file. Two generated mirrors under `skills/*/references/` keep the aesop-vendored copies self-contained and are never hand-edited — `bin/sync_pricing_refs.py` regenerates them whenever this file changes.

### 4.2 `/route` — the decision procedure

Four steps, executed by the model reading the skill:

1. **Mode.** Resolve `api` vs `subscription` (flag > task framing > pricing.json default). App-building questions force `api`.
2. **Classify.** In `api` mode, a cheapest-sufficient ladder: Haiku (bulk/simple) → Sonnet 5 (workhorse) → Opus 4.8 (hard debugging, architecture) → Fable 5 (long-horizon, Opus-failed). Ties break *down*, with an explicit "upgrade if you see X" signal. In `subscription` mode: Opus 4.8 daily driver, escalate complex work toward Fable (via the architect pattern), Haiku skipped, effort as the burn lever.
3. **Estimate.** Match the task to a size profile (XS 10K/1K tokens through XL 1.5M/100K), price each candidate model, show cache-discounted figures for agentic sizes (≈80% of cumulative input assumed to be 0.1× cache reads), apply intro/batch adjustments.
4. **Recommend + act.** A compact table with the recommendation bolded, then: **dispatch now** (Agent tool, `model` set to the recommendation, self-contained brief written from the conversation), **switch the session** (prints the `/model` command), or — for big Fable-worthy tasks — hand off to `/architect`. App questions get model ID + API parameters to paste into code instead.

### 4.3 `/architect` — Fable as architect

The core idea: **Fable 5 runs once, at the start; its judgment persists as scaffolding.** Instead of paying Fable rates for a whole project, you pay them for the phase where they buy the most — decomposition, contracts, and guardrails — and encode the results so cheaper models execute at near-Fable quality.

Two entry modes. From the Opus daily driver, the skill dispatches the architecture work to a **Fable subagent** (the session never changes model). Alternatively the user runs `/model fable` and does it natively for interactive steering.

Fable produces an **execution kit** in the target project:

| Artifact | Location | Purpose |
|---|---|---|
| `PLAN.md` | `.claude/kits/<slug>/` | Goal, constraints, out-of-scope, architecture decisions **with rationale**, risks with tripwires. The rationale is load-bearing: it's what lets a cheaper model make consistent micro-decisions later. |
| `TASKS.md` | same | Ordered tasks. Each is a self-contained brief executable by a model with **zero access to the planning conversation**: files, conventions, exact interfaces/contracts, gotchas, acceptance criteria, a shell verify command, and a suggested model (`sonnet` default, `opus` for hard ones, `haiku` for mechanical ones). |
| Subagents | `.claude/agents/` | `<slug>-implementer` (`model: sonnet`) executes one brief exactly; `<slug>-verifier` (`model: haiku`) re-checks acceptance criteria in fresh context, adversarially; `<slug>-reviewer` (`model: opus`) reviews phases against PLAN.md. Model pinning in frontmatter means the mix enforces itself. |
| Guardrails | project `CLAUDE.md` / skills | Conventions, invariants, "run X before claiming done", forbidden shortcuts — the Fable-judgment rails the executors run on. |

The kit's calibration rule: **pin down contracts exactly, leave implementation judgment open.** Over-prescription wastes the kit (and degrades output — prescriptive scaffolding hurts strong models); under-specification wastes the executor.

### 4.4 `/execute` — the orchestration loop

Runs on the daily driver. The skill frames the orchestrator's job explicitly: the expensive thinking is done — faithful dispatch, verification, state-keeping; don't re-litigate the plan.

Per task: mark in-progress → dispatch the brief verbatim to the kit's implementer → **verify independently** (the orchestrator runs the verify command itself *and* dispatches the fresh-context verifier; the implementer's success claim is never treated as evidence) → on pass, mark done and append learnings to `NOTES.md`; on fail, retry once with the failure output, then mark blocked and move on. Independent tasks dispatch in parallel; phase boundaries trigger the Opus reviewer.

**The escalation valve** is what keeps Fable spend proportional to genuine difficulty: a blocked task goes back to Fable as a *single-task consult* — one brief, the failure evidence, the relevant PLAN.md excerpt — asking Fable to fix it or rewrite the brief. You never pay Fable prices for routine execution, and never get stuck at Sonnet-level on the genuinely hard 5%.

Four refinements from the "fusion" arc make the loop cheaper and self-measuring without changing its contract:

- **Lean driver.** The orchestrator's own context is the run's single most expensive artifact — priced, cached, and re-sent every turn. So it reads *only* kit state (`PLAN.md` / `TASKS.md` / `NOTES.md`) plus the exit status of verify commands it runs itself, and delegates every exploratory read, grep, and failure-investigation to a cheap **haiku scout** subagent that returns a few-line conclusion, never a file dump. Delegate and monitor; touch files directly only to keep state current.
- **Warm-sidekick clusters.** For a *cohesive cluster* — a serial `depends:` chain within one phase that shares a file/subsystem and carries the **same** `model` pin — one warm implementer is continued across the chain (via `SendMessage`) instead of paying N cold prompt-cache starts, so shared files are read and cached once. Capped at ~4 tasks; a model-pin change always ends a cluster; `independent:` disjoint-file tasks still fan out fresh; and **verifiers are never warmed** — their value is the adversarial fresh context.
- **Two ledgers in `NOTES.md`.** Every finished task appends an `outcome:` line (model, attempts, `result`, review status) and every per-task dispatch appends an `agent:` line (task id, agent id, role, model). These are the machine-readable inputs the measurement layer (§6) reads back — a warm cluster's shared agent id is what lets the scorecard attribute one shared transcript to the cluster as a unit rather than faking a per-task split.
- **Upgrade-only, autonomy-gated live re-routing.** Each fresh `outcome:` line is also a routing signal: the orchestrator consults the kit's running per-tier first-try rate (`routing_scorecard.py <slug> --live`) and, when a tier is struggling over a minimum sample, recommends promoting its *remaining pending* tasks exactly one rung (haiku→sonnet, sonnet→opus). It never routes to frontier/Fable (the evidence-carrying escalation valve is the only path there), and never rewrites a task's `model` field — a re-route is a runtime dispatch override, logged as a `reroute:` line. An optional PLAN.md **`autonomy: advisory|auto`** dial decides what happens: **advisory** (the default) prints the recommendation and changes nothing; **auto** applies it — dispatching the named tasks one tier up — capped by a per-run budget guardrail, never downgrading.

### 4.5 `/escalate` — verify-gated, cost-ascending dispatch

The per-task sibling of `/execute`'s escalation valve, for a single task rather than a kit: run the cheapest sufficient model first, and promote toward Fable **only when a machine check fails**. The procedure:

1. **Pin the trigger.** Automatic escalation needs a failing check to fire on, so first state a machine-checkable success condition — a test, a build, a lint, a `curl` + grep, any command that exits non-zero on failure. If the task has no checkable outcome, the skill says so plainly rather than pretending a vibe is a verify.
2. **Attempt cheap.** Dispatch a subagent at the cheapest tier you'd actually trust (typically Sonnet 5 for routine coding, Opus 4.8 for harder reasoning) with a self-contained brief.
3. **Verify yourself, then decide.** The orchestrator runs the check itself — the subagent's claim is not evidence. Pass → done, and it never needed Fable. Fail → retry once on the *same* model with the exact failure output (a cheap attempt often just needs to see the error). Fail again → escalate.
4. **Escalate cheaply.** Dispatch a `model: fable` subagent carrying *only* the task, the check, and the evidence from both failed attempts. Two cost levers, in order of control: **scope** (hand it the diagnosis, not a blank re-attempt — the failure evidence is what makes the Fable hop short) and **effort** (prefer `medium`, where the invocation exposes it — Fable at `medium` often beats older models at `max`). Re-verify Fable's output too; if even Fable fails, stop and report honestly.

**Refusal fallback:** a Fable subagent that returns `stop_reason: "refusal"` (its cyber/bio-adjacent classifiers) won't retry into success, so that hop falls back to an Opus 4.8 subagent at high effort. In `api` mode the payoff is concrete — Fable runs only on the fraction of tasks the cheaper tier failed, so the skill reports roughly what fraction escalated. For multi-task work, prefer a kit (`/architect`) over calling this in a loop.

### 4.6 `/cost-report` + `bin/cost_report.py`

The analyzer walks `~/.claude/projects/**/*.jsonl` (Claude Code's local transcripts). Each assistant message carries `model` plus usage fields: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`. The script:

- **Dedupes by message id** (resumed sessions duplicate history into new files).
- **Normalizes model strings** — `claude-fable-5[1m]`, date-suffixed IDs — onto pricing.json keys by prefix match; unknown models are tallied and reported, never silently dropped.
- **Prices each record**: `(input×in + output×out + cache_read×in×0.1 + cache_write×in×1.25) / 1e6`, with Sonnet 5 intro rates applied by record date.
- **Aggregates** by model and session, then flags **downgrade candidates**: sessions whose models were all Fable/Opus-tier but whose footprint was Sonnet-sized (< 50K tokens, < 10 tool calls), with the exact dollar delta vs re-pricing every record at Sonnet 5 rates.
- Frames output per mode: savings (`api`) vs burn share (`subscription`).

### 4.7 Statusline + `/setup`

`bin/statusline.py` reads Claude Code's statusline JSON from stdin and prints one ANSI line: model name **color-coded by price tier** (red = Fable, yellow = Opus, green = Sonnet, cyan = Haiku), effort level, estimated session cost, context %, and — on subscription sessions — 5h/7d rate-limit burn with green/yellow/red thresholds at 60/80%. The red model name is the ambient nudge: *you are on frontier pricing right now — is this task worth it?* A companion hook, `bin/agent_tracker.py`, registered against Claude Code's subagent events, keeps a live count of running subagents and a running tally of Fable usage in a state dir the statusline reads back — always best-effort, always exits 0, never disrupts the session.

`/setup` wires it into `~/.claude/settings.json` (`statusLine.command`), showing the exact block and warning about any existing statusline before writing. Cost figures are client-side estimates, not bills.

### 4.8 `/fable-check`

The judgment reference: route to Fable for long-horizon autonomous work, problems Opus already failed on, deep research, heavy sub-agent orchestration — and *not* for routine coding, solved problems, or security-analysis-heavy work (Fable's cyber classifiers refuse much of it; Opus 4.8 is the better tool there). Every Fable recommendation surfaces the operational caveats: `refusal` stop reason with Opus fallback, minutes-long turns, the 30-day data-retention requirement, and always-on thinking. Optimal-use rules: full spec up front, sweep effort levels (Fable at `low` often beats older models at `max` — don't default to `xhigh`), de-prescribe prompts, let it delegate, give it a memory surface.

## 5. The workflow end to end

```
daily work (Opus 4.8)
   │  complex planning / complex task detected (/route flags it, or you know)
   ▼
/polytropos:architect <task>        ← Fable 5 runs ONCE (subagent or /model fable)
   │  emits the execution kit: PLAN.md + TASKS.md + model-pinned agents + guardrails
   ▼
/polytropos:execute <slug>          ← back on Opus/Sonnet; loop dispatches,
   │                                        verifies independently, updates state,
   │                                        writes the outcome/agent ledgers to NOTES.md
   ├─ task blocked? → single-task Fable consult → resume cheap execution
   ▼
done: overall "done" check from PLAN.md, faithful report
   │
   ▼
routing_scorecard.py <slug> --session <id>  ← measure (§6): did the cheap models hold
                                              quality, and what did it cost vs all-Fable?
```

Concretely: you're on Opus and say "plan and build a greenfield polymarket data pipeline." `/route` (or you directly) invokes `/architect`. A Fable subagent interrogates the scope once, then writes `PLAN.md` (architecture decisions + rationale), fifteen task briefs with verify commands, three model-pinned agents, and CLAUDE.md guardrails. Fable's involvement ends — perhaps 10–20 minutes of frontier-model time. `/execute` then runs for hours on Sonnet/Opus: implementer builds task 3, verifier re-runs its test in fresh context, task 7 fails twice and gets a one-task Fable consult that rewrites the brief, the Opus reviewer checks phase 1 against the plan. Fable spend: the planning phase plus one consult. Execution quality: bounded below by the kit, not by the executor's unaided judgment.

The loop then **closes with measurement**. Because `/execute` recorded per-task ledger lines in `NOTES.md`, running `python3 bin/routing_scorecard.py <slug> --session <id>` after the kit finishes proves the cheap models actually held quality (first-try pass rate, cheap-model review survival) and prices the real transcript dollars against an all-Fable counterfactual — turning "Sonnet was probably fine here" into an evidence-backed number. That measurement is what makes the next kit's model pins a data-driven choice rather than a guess (§6).

## 6. The measurement layer

Everything above *routes* work to cheaper models on the belief they'll suffice. The measurement layer turns that belief into evidence, by reading the ledgers `/execute` leaves behind in each kit's `NOTES.md` — and it never fabricates a number: missing data renders `null`/`n/a`, never a zero or a guess.

**`bin/session_cost.py`** prices one session end to end: the main transcript plus every subagent `*.output` transcript, deduped and model-normalized the way the cost report is, then repriced under an all-one-model counterfactual (default: the frontier tier). It is the engine the scorecard's `--session` dollars reuse.

The **four execute-owned `NOTES.md` ledger lines** are the machine-readable seam between the loop and the measurement:

- **`outcome:`** — one line per finished task: the model it ran on, attempt count, `result` (`pass` / `retry-pass` / `escalated-pass` / `blocked`), and whether independent review left it `clean` or `revised`.
- **`reroute:`** — one line per live re-routing recommendation acted on or announced: from/to tier, `advisory` vs `applied`, the tasks covered, and the rate that triggered it.
- **`session:`** — one line per run: the session id (transcript filename stem), recorded best-effort and skipped when ambiguous — the seam the cross-kit history prices dollars through.
- **`agent:`** — one line per per-task subagent: task id, agent id, role (`implementer` / `verifier` / `escalation`), model — the map from transcript to task that per-task dollars need.

**`bin/routing_scorecard.py`** reads those lines plus `TASKS.md` and has **five additive modes** (all read-only except `--demo` and `--history --snapshot`; each mode carries a `--demo` that runs the whole pipeline against a synthetic kit in a temp dir):

- **plain** `<kit> [--session ID]` — the per-kit verdict: first-try pass rate, per-task outcomes, model mix, and cheap-model review survival. With `--session`, it folds in the real transcript dollars (main + subagents) and shows them against an all-Fable counterfactual.
- **`--live`** — the mid-run signal `/execute` consults: reads the ledger so far and recommends an upgrade-only, one-step, never-frontier re-route when a tier is struggling over a minimum sample. Loads no pricing and writes nothing.
- **`--history [--kits-dir DIR …]`** — a cross-kit per-tier track record aggregated over every kit under the kits dir. `--kits-dir` is **repeatable** → cross-repo, namespacing rows `<label>/<kit>`; a lone dir keeps the output byte-identical to single-repo mode. Dollars are aggregated only over kits carrying a `session:` line, coverage labeled `partial`/`full`.
- **`--by-task`** (requires `--session`) — per-task dollars by role, read from the `agent:` ledger. The honesty boundary is absolute: the orchestrator's own main-session transcript is **one un-split line**, a warm cluster's shared transcript is attributed to the cluster **as a unit** (never divided), and a recorded agent whose transcript is gone prices `null` with a note — a per-task figure is only ever the sum of transcripts that actually exist.
- **`--snapshot` / `--trend`** — `--history --snapshot` writes the history card as a dated `<YYYY-MM-DD>.json` under the gitignored `trends/` dir (the one sanctioned write; latest-wins per day), and `--trend` renders per-tier first-try rate across those snapshots as a text time series (needs ≥2 snapshots to count as a trend; text only, no charts).

## 7. Two extensions

Two surfaces reuse this same routing-and-cost-awareness workflow beyond the Claude Code plugin.

**The Copilot harness (`copilot/`).** The same per-task routing and cost discipline ported to GitHub Copilot CLI. A cross-vendor `route` agent classifies a task into a tier (cheap / mid / strong / frontier) and prices 2–3 candidate models across vendors; an architect→execute→verify→escalate port (`bin/copilot_execute.py` plus model-pinned agents) mirrors the kit loop; and a budget-capped **Ralph** goal loop (`bin/copilot_ralph.py`) drives a self-directed objective under a spend ceiling. Copilot meters everything in **AI Credits (1 AIC = $0.01)**, priced by `bin/copilot_pricing.py` from the separate `data/pricing.copilot.json` (where Claude Fable 5 is the sole frontier-tier model on the roster). Because Copilot has no `${CLAUDE_PLUGIN_ROOT}`-style runtime variable, the bundle's config carries a `{{POLYTROPOS_ROOT}}` placeholder that `bin/harness_select.py` resolves to an absolute path at install time. Full guide: `docs/COPILOT-HARNESS.md`.

**The daily journal (`journal/`).** A nightly, gitignored, read-only cross-tool work journal. A deterministic collector (`bin/journal_collect.py` — no model, no network) ingests the day's activity across Claude Code, Copilot CLI, Codex CLI, and git — JSONL / flat-text only, never a SQLite file, never a shelled-out CLI — into a **metadata-only** `digest.json` (never transcript text). A scheduled summarizer (`bin/journal_summarize.py`) then routes that digest to a cheap/mid model that writes three short documents: the day's narrative, a technical breakdown, and a next-day plan. Codex activity is counted and, when the day's rollout logs carry tokens, shown as a clearly-labeled API-equivalent relative-burn proxy priced from `data/pricing.codex.json` — never a bill, never added to the priced total. The whole tree — digest, documents, inbox, logs — lives under one gitignored `journal/` entry, so personal data never lands in git. Full guide: `docs/DAILY-JOURNAL.md`.

## 8. Operational playbooks

**Today (Fable on subscription).** Daily driver Opus 4.8; `xhigh` standing effort removed in favor of per-task effort; escalate via `/architect`; watch the statusline's 5h/7d burn. This posture is not hypothetical — **11 execution kits have now shipped through architect → execute, 32 of 32 tasks passing on the first try, zero escalations to the Fable valve, and zero execution work run on Fable at all** (only haiku/sonnet/opus). Measurement (§6) is what makes each downgrade decision evidence-based rather than a hunch: the scorecard proves after the fact that the cheap tiers held quality.

**When Fable 5 leaves the subscription:**
1. `data/pricing.json` → `billing_mode: "api"`.
2. `~/.claude/settings.json` → default model `opus` (or `sonnet`), remove standing `effortLevel`.
3. Same architect/execute posture — it is now also the *dollar*-optimal shape, concentrating Fable spend in the short planning phase.
4. `/cost-report` after two weeks to sanity-check where money goes.

## 9. Limitations and design notes

- **Cost figures are estimates.** Task-size profiles are priors, not measurements; transcript costing uses API list prices and a 5-minute-TTL cache-write assumption. Authoritative billing is the Console.
- **Measurement degrades honestly rather than guessing.** The scorecard (§6) never fabricates a figure: a missing transcript, an un-attributable orchestrator turn, or a zero-denominator rate renders `null`/`n/a` with a note, never a zero or an estimated split. A number it shows is one it can stand behind.
- **Dispatched subagents lose conversation context** by design; both `/route` dispatch and the kit briefs compensate by requiring self-contained briefs. Interactive, context-heavy work belongs in the main session (switch with `/model`).
- **Prices go stale.** `cached_date` is printed on every report; updating means editing one file.
- **Advisory routing is a feature, not a gap** — since the main loop's model can't be automated, the design pushes automation to where it's reliable: agent frontmatter and dispatch-time `model` parameters.
