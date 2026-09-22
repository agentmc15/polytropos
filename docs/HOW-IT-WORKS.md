# How polytropos works

An in-depth walkthrough of the plugin's architecture, the reasoning behind it, and every component's mechanics. Companion HTML version: [`how-it-works.html`](how-it-works.html).

---

## 1. The problem

Claude Code sessions run on one model at a time, and the price spread across the lineup is large:

| Model | Input $/MTok | Output $/MTok | Relative cost |
|---|---:|---:|---|
| Fable 5.1 | $10 | $50 | 2× Opus, 5× Sonnet, 10× Haiku |
| Fable 5 | $10 | $50 | same rate as Fable 5.1, which supersedes it |
| Opus 5 | $5 | $25 | baseline daily driver |
| Opus 4.8 | $5 | $25 | superseded by Opus 5 at the same rate |
| Sonnet 5 | $2 | $10 | near Opus-tier at high effort |
| Haiku 4.5 | $1 | $5 | bulk/simple API work |

*(Prices cached 2026-09-21 in `data/pricing.json` — the single source of truth; nothing else hard-codes a price.)*

Running Fable 5 as a standing default is harmless on a subscription (dollars don't change) but becomes a 2×–10× overpayment the day Fable moves to pay-per-token — a real 30-day baseline measured on this machine showed **~$614 API-equivalent with 87% of it on Fable 5**, mostly from cache reads in long agentic sessions. That is one dated observation on one machine, not a standing figure — `python3 bin/cost_report.py --days 30` re-measures it on yours.

The plugin solves three problems:

1. **Per-task routing** — which model should handle *this* task, with a cost estimate before running it.
2. **The Fable escalation pattern** — use Fable 5 only for the portion of work that needs it, and make its quality persist after you leave it.
3. **Visibility** — historical spend analysis and an ambient statusline so drift is noticed, not discovered on an invoice.

## 2. Two billing modes with opposite goals

The same routing question gets opposite answers depending on how tokens are paid for. Every skill reads the mode from `data/pricing.json → billing_mode` (overridable per invocation with `--api` / `--sub`).

**`api` mode — optimize dollars.** Any pay-per-token usage: an application you're building, or Claude Code on API-key billing. The cheapest *sufficient* model wins. Haiku 4.5 earns its keep for classification, extraction, and bulk calls. Cache discounts (reads at 0.1×) and batch processing (50% off) factor into the estimate; an `intro_pricing` window would too, but no model in the file carries one today.

**`subscription` mode — optimize rate-limit burn.** Claude Code / Claude UI on a plan: the marginal dollar cost of any request is zero, and the only scarce resource is the 5-hour and 7-day rate-limit windows. Consequences:

- **Haiku is pointless** — downgrading saves nothing that matters; you'd only lose capability.
- The daily driver should be the best sustainable model — the **Opus tier** in this setup. Which
  concrete model that tier means is derived, never typed: `python3 bin/aesop_bridge.py tiers`
  resolves each tier to the model `data/pricing.json` currently carries for it, and that file
  marks Opus 4.8 superseded at the same rate (kept for costing historical transcripts, and as
  the standard fallback target for a Fable or Opus refusal). The daily-driver sentences in
  `skills/route/SKILL.md` and `skills/fable-check/SKILL.md` now name the Opus *tier* and point at
  that command; Opus 4.8 still appears in both as the refusal-fallback target and the
  Sonnet-comparison rung, which is what the file says it is.
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
├── .claude-plugin/
│   ├── plugin.json                 the plugin manifest (name, version, description)
│   └── marketplace.json            the local marketplace this repo serves itself from
├── data/                           the numeric sources of truth — ONE FILE PER HARNESS,
│                                   never merged; no harness's config reads another's
│   ├── pricing.json                Claude: rates, cache/batch multipliers, intro windows,
│   │                               per-model notes, task-size profiles, billing_mode
│   ├── pricing.copilot.json        Copilot: AI Credits — the credit unit itself is data
│   ├── pricing.codex.json          Codex: roster + burn index; model ids are best-effort
│   ├── pricing.cursor.json         Cursor: carries no rates at all — usage stays unknown
│   └── benchmarks.aa.json          a transcribed snapshot of an external capability
│                                   benchmark — a prior, never this repo's pricing
├── primitives/                     the aesop fold, as data plus a read-only validator
│   ├── model.json                  the nine converged AI primitives
│   ├── aesop.schema.v1.json        the manifest schema bin/primitives.py validates against
│   ├── harness-matrix.json         the historical product matrix (provenance, not the
│   │                               operational view)
│   └── harness-capabilities.json   per-harness rows: product / implemented / verified.
│                                   `unknown` means NO until a person runs the client and
│                                   records verified_on + client_version by hand
├── skills/                         one dir per skill; the SKILL.md IS the runtime behavior
│   ├── route/ fable-check/         routing decision + the Fable-worth-it judgment
│   ├── architect/ execute/         the kit lifecycle (one shared kit contract)
│   ├── escalate/                   one task, cheapest tier, verify-gated Fable fallback
│   ├── cost-report/ context-weight/  spend history; what filled the context window
│   ├── setup/ update/              statusline install; all-harness freshness
│   ├── journal/ memory/            daily cross-tool journal; durable facts with gated recall
│   ├── bench-routing/ repo-bench/  external benchmark join; measure models on a real repo
│   ├── graphify/                   local knowledge graph of a repo, read offline
│   ├── assess-improvement/         read-only improvement assessment (also under cursor/)
│   └── {route,fable-check}/references/pricing.json
│                                   GENERATED mirrors — never hand-edited; regenerate with
│                                   bin/sync_pricing_refs.py (a test fails on drift)
├── bin/                            python3, STDLIB ONLY — no pip, no requirements, no pytest
│                                   grouped by family below; `ls bin/*.py` is the real list
├── copilot/                        Copilot CLI bundle: aesop.toml + .github/{agents,skills}
├── codex/                          Codex plugin: AGENTS.md + agents/ + skills/ + prompts/
├── cursor/                         Cursor bundle: agents/ + skills/, installed project-scoped
│                                   into a target's .cursor/
├── copilot-docs/                   GENERATED Copilot doc center (bin/copilot_docs.py only)
├── docs/                           hand-written references — this file among them
├── docs-src/                       fragments/ (hand-written site source) + the hash-locked
│                                   requirements.txt for the one non-stdlib toolchain
├── docs-site/                      GENERATED mkdocs-material site (bin/docs_build.py only)
├── tasks/                          plan and spec material kits are written from, + lessons.md
├── tests/                          stdlib unittest; temp stubs and temp homes only — never a
│                                   real claude/codex/copilot/agent/graphify invocation
└── .claude/
    ├── kits/<slug>/                PLAN.md + TASKS.md + GUARDRAILS.md (architect-owned)
    │                               + NOTES.md (execute-owned) — one execution kit
    └── agents/                     per-kit model-pinned agents: the standing
                                    implementer/verifier/reviewer trio, plus any role a
                                    kit's PLAN.md `roles:` line declares
```

`bin/` is one flat directory of single-purpose scripts, and it is easier to read as families
than as a list. Every script's own module docstring states what it is and what it refuses, and
that docstring is the authority — this table is a map, not a contract. Nearly every script with a
CLI answers `--help`; the exceptions are `exec_policy.py` (which prints a usage line),
`proc_runner.py` (whose argv *is* the process to run) and `redact.py` (which reads stdin or a file
path). Eleven are libraries with no CLI at all: the five `decision_*` modules, `safe_paths`,
`copilot_prefs`, `codex_policy`, `codex_legacy_migration`, `journal_advisor` and `journal_sources`.

| Family | Scripts | What the family owns |
|---|---|---|
| **Routing and cost (Claude)** | `routing_scorecard` `session_cost` `cost_report` `statusline` `agent_tracker` `context_weight` `routing_policy` `model_registry` `aesop_bridge` | Per-task routing, transcript pricing, the ambient statusline, what filled the window, and the ONE cross-harness reader of model ids and tiers (`model_registry`, which never reads a price) |
| **Benchmark and evaluation** | `bench_routing` `repo_bench` `workflow_eval` | External benchmark rankings joined against this repo's own ledger; models measured on a target repo's real work; whole workflows compared on held-out tasks. `repo_bench` and `workflow_eval` spend only behind `--live` plus an explicit `--max-usd` |
| **Kit contract and the four drivers** | `kit_contract` `claude_execute` `copilot_execute` `codex_execute` `cursor_execute` `copilot_ralph` `kit_scheduler` `attempt_ledger` `attempt_history` `kit_verify_hook` | One contract (§4.4) and four headless drivers over it. Every dispatch is recorded in the ledger before and after it runs; `kit_scheduler` adds opt-in bounded concurrency in isolated tree copies |
| **Execution boundary** | `exec_policy` `proc_runner` `safe_paths` `runtime_data` `redact` | One place each that decides whether code may run, how a process is bounded, whether a path may be written, where runtime data lives, and what must not leave the machine in plain text (§4.9) |
| **Decision and improvement** | `decision_contract` `decision_policy` `decision_provider` `decision_eval` `decision_context` `improvement_loop` | The decision mechanism, with every live switch off (§4.10) |
| **Training-data preparation** | `training_data` | Decision-time snapshots, labels, eligibility, revocation, splits and a local export — collection not authorized, no production call site (§4.10) |
| **Copilot harness** | `copilot_pricing` `copilot_prefs` `copilot_usage` `copilot_statusline` | AI-Credit cost math, user model pins/excludes, a read-only usage report over `~/.copilot`, and the Copilot-side statusline twin |
| **Codex harness** | `codex_pricing` `codex_usage` `codex_policy` `codex_app_policy` `codex_legacy_migration` | Codex cost math and roster, a read-only usage report with an honest unpriced fallback, the central orchestration/worker policy, and reversible legacy-copy retirement |
| **Cursor harness** | `cursor_adapter` | Identity probe before any dispatch, the model list, the ownership-aware project install, ambient-file diagnosis, and the live smoke that is printed and never run |
| **Install, capability, freshness** | `harness_select` `harness_adapter` `harness_update` `plugin_staleness` | What is installed where, what each harness can actually be relied on to do, and what has drifted. `harness_select` classifies every destination before writing and never overwrites what it does not own |
| **Daily journal** | `journal_collect` `journal_sources` `journal_summarize` `journal_schedule` `journal_plan` `journal_askpack` `journal_advisor` | Read-only, JSONL-only ingestion into a metadata-only digest, a routed summarizer, a next-day runbook, and an offline ask-the-tools prompt pack |
| **Memory, lessons, telemetry** | `memory_store` `memory_recall` `lessons_store` `lessons_promote` `telemetry_snapshot` | Durable facts with pull-only budget-capped recall, scoped lessons that become rules only by recurrence or explicit ask, and dated telemetry envelopes. Every store is personal data outside the plugin tree |
| **Graph grounding** | `graph_brief` `graph_ground` | Read a graphify `graph.json` — an architect-grounding card, freshness against the working tree, bounded impact, and a search fallback. Neither ever invokes graphify |
| **Primitive model** | `primitives` | A read-only validator and preview over `primitives/*.json` — see [PRIMITIVES.md](PRIMITIVES.md) |
| **Generated output and the release gate** | `docs_build` `copilot_docs` `sync_pricing_refs` `sync_codex_surfaces` `release_gate` | Every generated surface has exactly one writer and a `check` that fails on drift. Edit the SOURCE and rebuild; never hand-edit the output |

The subsections below cover the Claude-side pieces in dependency order; the other three
harnesses and the journal get §7.

### 4.1 `data/pricing.json`

Everything numeric lives here: per-model input/output rates, optional `intro_pricing` windows (applied automatically by date — no model carries one today, Sonnet 5's launch rate having become its base rate, but the mechanism stays for the next one), cache multipliers (reads 0.1×, 5-minute-TTL writes 1.25×), the 50% batch discount, per-model context windows and notes, the default `billing_mode`, and the task-size token profiles used for estimation. The multipliers are global, so a model that prices cache reads differently from the file-wide `cache_read_multiplier` is over- or under-estimated until a per-model override exists — Fable 5.1's notes say so in as many words. When Claude prices change, this file is the only edit; bump `cached_date`.

It has **three siblings, one per harness (§7), and they never merge** — no harness's config reads another's file. `data/pricing.copilot.json` is the same kind of single source of truth for Copilot, where the AI-Credit unit itself is data rather than a constant in code. `data/pricing.codex.json` carries the Codex roster and burn index, with a `model_ids_note` saying that its model ids are best-effort — corrections land in that file and nowhere else. `data/pricing.cursor.json` carries **no rates at all**, because Cursor publishes no per-model CLI price table this repo could mirror; that absence is the honest state, and it is why a Cursor dispatch is unpriced rather than estimated from someone else's numbers. The one cross-file reader is `bin/model_registry.py`, and it reads model ids and tiers only — never a price — and reports an ambiguity rather than picking when one id sits in two files under two tier names.

Two generated mirrors under `skills/{route,fable-check}/references/` keep the aesop-vendored copies self-contained and are never hand-edited — `bin/sync_pricing_refs.py` regenerates them whenever this file changes, and a test fails on drift. Nothing outside `data/` hardcodes a price, ratio, plan fact, credit value, model id, or pricing date; the tables in `README.md` and `docs/` are **labeled snapshots tied to a file's `cached_date`** and change only in the same edit as the file.

### 4.2 `/route` — the decision procedure

Four steps, executed by the model reading the skill:

1. **Mode.** Resolve `api` vs `subscription` (flag > task framing > pricing.json default). App-building questions force `api`.
2. **Classify.** In `api` mode, a cheapest-sufficient ladder: Haiku (bulk/simple) → Sonnet 5 (workhorse) → the Opus tier (hard debugging, architecture) → Fable 5 (long-horizon, Opus-failed). Ties break *down*, with an explicit "upgrade if you see X" signal. In `subscription` mode: the Opus tier as daily driver, escalate complex work toward Fable (via the architect pattern), Haiku skipped, effort as the burn lever.
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

### 4.4 `/execute` — the orchestration loop, on one kit contract

Runs on the daily driver. The skill frames the orchestrator's job explicitly: the expensive thinking is done — faithful dispatch, verification, state-keeping; don't re-litigate the plan.

Per task: mark `in-progress` → dispatch the brief verbatim to the kit's implementer (passing the task's `model` field as the Agent tool's `model` parameter, which overrides the agent file's frontmatter) → **verify independently** (the orchestrator runs the verify command itself *and* dispatches the fresh-context verifier; the implementer's success claim is never treated as evidence) → on pass, mark `done` and append learnings to `NOTES.md`; on fail, retry once with the failure output, then mark `blocked` and move on. Independent tasks dispatch in parallel; phase boundaries trigger the Opus reviewer, and a kit's PLAN.md may declare extra roles beyond the trio.

**`bin/kit_contract.py` is the one kit contract.** What a task id is, how `TASKS.md` parses, when a task may be dispatched, what a budget refusal means, how a run id is minted, what evidence a completed task carries, and the status vocabulary — exactly `pending | in-progress | done | blocked` — are defined there once and re-exported by every driver. It exists because the three original drivers shared thirty-five top-level names, twenty-seven of which were the same code copied between them; `TripleImplementationTests` now fails if a driver grows its own copy back. What stays per-harness is what must: each CLI's argument vector, each host's own loop, its escalation ladder, and its pricing file. `/execute` calls it before the first dispatch:

```bash
python3 bin/kit_contract.py graph --kit .claude/kits/<slug>     # validate the DAG; exit 2 if invalid
python3 bin/kit_contract.py roster --kit .claude/kits/<slug>    # workflow, roles, assurance
python3 bin/kit_contract.py freshness --kit .claude/kits/<slug> # acceptances vs upstream versions
python3 bin/kit_contract.py demo                                # synthetic graphs; spends nothing
```

A `graph` exit of 2 means a duplicate id, an unknown or self dependency, or a cycle — each named with its fix. The orchestrator fixes `TASKS.md` and reports the defect; it never routes around an invalid plan.

**Every dispatch is recorded in `bin/attempt_ledger.py` before and after it runs.** `TASKS.md` status and the `NOTES.md` outcome line are *projections* of that ledger, not the record: an append-only JSONL stream per kit, written through `bin/safe_paths.py` into the per-user data root (`bin/runtime_data.py`) rather than into the workspace, so a verify command, a git operation, or a synced tree never touches it. An attempt is written as `attempt.started` before its dispatch and `attempt.finished` after; a crash in between leaves a started attempt with no finish, which a resuming run **closes as `unknown`** — never as success, and never re-dispatched as if it had not happened. It is explicitly not exactly-once execution: a process killed after the call was made has still made the call, and nothing here can know whether the provider billed it. `classify_dispatch` separates the failures that would fail the same way on a costlier model (missing CLI, logged out, unknown flag, network down) so the ladder stops and names the class instead of climbing, and so an infrastructure failure never enters the routing history as a verdict on a model that never ran. `bin/attempt_history.py` joins the ledger, the `NOTES.md` outcome lines, and Codex role-use records into one record shape with unknowns kept.

**`bin/kit_scheduler.py` adds opt-in bounded concurrency.** Sequential by default; above one parallel slot it runs ready independent tasks in isolated copies of the workspace, admits the batch against one budget, measures each task's write set, integrates them, keeps and names conflicts rather than resolving them silently, and verifies the merged tree again. `plan` reads only; `demo` walks two integrated tasks, a conflict and a sized manifest and spawns nothing.

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

### 4.9 The execution boundary — one place each for run, path, process, store, and redaction

Everything above dispatches work and then *runs code to check it*. Five scripts hold the
decisions that has to make, one place each, and [SECURITY.md](../SECURITY.md) is the authority on
exactly what each does and does not promise — read it there rather than inferring it from the
summary here.

- **`bin/exec_policy.py`** — the OS-enforced boundary every verify command runs inside.
  `python3 bin/exec_policy.py check` reports which backend this host enforces and exits 3 when
  none does. On macOS that backend is `sandbox-exec`: writes confined to the workspace, network
  denied, credential stores unreadable. It is the default, and **it refuses rather than
  downgrading**. Linux and Windows have no backend implemented, so verification there needs the
  explicit `--exec-mode trusted-host`, which enforces nothing and reports itself as the opt-out.
  Dispatch is *not* confined — `confined_dispatch` is recorded `unsupported` with a dated,
  measured reason in `primitives/harness-capabilities.json` (subscription credentials live in the
  Keychain, which a sandboxed process cannot reach, so a confined dispatch reports "Not logged
  in"). Detecting a backend is not certifying one: `certify_profile` certifies nothing without a
  sentinel report, and no sentinel report exists here.
- **`bin/proc_runner.py`** — the only place this repo starts an external process. It validates the
  working directory, bounds wall time and output, gives the process its own group so nothing it
  spawned outlives it, and names each way a run can fail. A bare `subprocess.run` inherits the
  launch directory and bounds none of that, which is why there are none.
- **`bin/safe_paths.py`** — the only place a path is judged safe to write, read, or delete inside
  a caller-selected root. No destination path is hand-composed.
- **`bin/runtime_data.py`** — where this machine's runtime data lives: a per-user application-data
  dir, per checkout, `0700`/`0600`, deliberately **outside** the plugin tree, because this tree is
  distributed, cached, and often cloud-synced. `where` shows each store's resolved location;
  `migrate` copies an in-tree store out without relocating or deleting the original; `export` and
  `forget` list before they act.
- **`bin/redact.py`** — the only place this repo decides what must not leave a machine in plain
  text. Findings are reported by **kind and count, never by value**. It is shape-matching, so it
  cannot prove absence, and nothing here claims it can.

### 4.10 Decision and improvement — the mechanism, with every live switch off

Release 1 of the decision-and-improvement work is a **mechanism release**. It makes no
performance claim, and there is nothing it could make one from: no trial has been declared, no
data has been collected, and no vendor client has been run by any test, verify command, or gate.
[DECISION-IMPROVEMENT-V1-HANDOFF.md](DECISION-IMPROVEMENT-V1-HANDOFF.md) is the authority —
read it before acting on any of this. Its companions are the offline conformance report
[DECISION-IMPROVEMENT-CONFORMANCE.md](DECISION-IMPROVEMENT-CONFORMANCE.md) and the
collection runbook [TRAINING-DATA-READINESS.md](TRAINING-DATA-READINESS.md).

The pieces, each a library module with no CLI of its own:

| Module | What it decides |
|---|---|
| `bin/decision_contract.py` | what may be asked of a decision, answered, and recorded — strictly, with no invalid value normalised into validity |
| `bin/decision_policy.py` | which policy bundle a run is entitled to read, and what it falls back to. `SELECTION_MODES` holds `legacy` and `shadow`; `DEFERRED_MODES` holds `canary` and `active`, refused by name |
| `bin/decision_provider.py` | one bounded request-to-result interface with two providers: a deterministic `rules` path, and `replay`, which incurs no new inference |
| `bin/decision_eval.py` | the read-only prediction-time join — what was knowable when a decision was taken against what was observed after, with `insufficient-evidence` for thin or mismatched data |
| `bin/decision_context.py` | which files a failed attempt was not shown, as a bounded versioned manifest, under a policy of at most one approved repair, never changing model and context at once |
| `bin/improvement_loop.py` | bounded, falsifiable, **data-only** candidate drafts, validated through `workflow_eval` — it stores nothing and calls no model (`evidence` / `draft` / `demo`) |

Four constants are the reason none of it is live, and the refusals are *derived* from them rather
than written down separately: `workflow_eval.CONFINED_DISPATCH_WIRED`,
`training_data.COLLECTION_ENABLED`, `training_data.CAPTURE_WIRED` and
`improvement_loop.PROPOSER_WIRED` are all `False`. Because the first is `False`, the activation
gate refuses every transition to `canary` and `active` and every run resolves to the legacy
bundle — on every harness, with no partially available canary. Routing policy still changes only
the way it always did: a reviewed, versioned, reversible proposal
(`python3 bin/workflow_eval.py propose` → `review` → `apply`, with `rollback` appending a
generation and deleting nothing; `activation` reports what is in force).

Two facts about Cursor are linked here and never merged, because conflating them misreads the
release in both directions. Cursor's **current CLI implementation is present and verified** —
six dated `verified: supported` rows in `primitives/harness-capabilities.json` against a named
client version — and nothing in this release retires, reimplements, or reports it as absent.
Cursor's **adaptive-decision profile is not**: that row is `implemented: unsupported` with
`verified: unknown`, pending independent proof that a Cursor run can take a decision bundle in a
running state.

Training-data preparation (`bin/training_data.py`) is three separate things and the distinction
is the one most easily blurred. **What shipped** is the code: decision-time snapshots, the cause
taxonomy, reviewed labels, eligibility and retention, revocation, grouped dataset splits and a
reproducible local export (`status` / `taxonomy` / `readiness` / `demo`). **What was not
authorized** is collection — no scope has been declared and no eligible run has been collected
from. **What has not happened** is training: there is no trainer here, nothing downloads,
uploads, fine-tunes, or evaluates a model, and no checkpoint exists. "Zero examples collected" is
the absence of a production call site, not a gate met and not a privacy achievement. Read the
report's `readiness_codes()` and not its gate tally: the tally is a property of the material
handed in, while the codes ride on every report shape unconditionally. Revocation marks an export
manifest, a derived dataset, and a readiness report `invalidated` and a checkpoint
`identified-only` — it removes nothing from a model.

## 5. The workflow end to end

```
daily work (the Opus tier)
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

The **execute-owned `NOTES.md` ledger lines** are the machine-readable seam between the loop and the measurement. `skills/execute/SKILL.md` names six machine-read tokens, and the rule that goes with them is load-bearing: a line that merely *starts* with one parses as real data whether it is plain, bulleted, or indented, so the skill requires every one of them to be backticked when quoted in prose.

- **`outcome:`** — one line per finished task: the model it ran on, attempt count, `result` (`pass` / `retry-pass` / `escalated-pass` / `blocked`), and whether independent review left it `clean` or `revised`.
- **`reroute:`** — one line per live re-routing recommendation acted on or announced: from/to tier, `advisory` vs `applied`, the tasks covered, and the rate that triggered it.
- **`session:`** — one line per run: the session id (transcript filename stem), recorded best-effort and skipped when ambiguous — the seam the cross-kit history prices dollars through.
- **`agent:`** — one line per per-task subagent: task id, agent id, role (`implementer` / `verifier` / `escalation`), model — the map from transcript to task that per-task dollars need.
- **`reviewer:`** — one line per phase review: the phase, the model, findings raised and findings confirmed, and optionally `result=accepted|revised|blocked` — the input to the per-role value view.
- **`defect:`** — one line per defect the run had to report rather than fix: the task id (or `-`) and a `kind=` token. The loop records a defect and stops; it never widens a task's scope or acceptance to make it pass.

**`bin/routing_scorecard.py`** reads those lines plus `TASKS.md` through a set of **additive modes**. All are read-only except `--demo` and the snapshot write; each carries a `--demo` that runs the whole pipeline against a synthetic kit in a temp dir. `python3 bin/routing_scorecard.py --help` is the current flag set — the modes below are the main ones, and the list grows:

- **plain** `<kit> [--session ID]` — the per-kit verdict: first-try pass rate, per-task outcomes, model mix, and cheap-model review survival. With `--session`, it folds in the real transcript dollars (main + subagents) and shows them against an all-Fable counterfactual.
- **`--live`** — the mid-run signal `/execute` consults: reads the ledger so far and recommends an upgrade-only, one-step, never-frontier re-route when a tier is struggling over a minimum sample. Loads no pricing and writes nothing.
- **`--history [--kits-dir DIR …]`** — a cross-kit per-tier track record aggregated over every kit under the kits dir. `--kits-dir` is **repeatable** → cross-repo, namespacing rows `<label>/<kit>`; a lone dir keeps the output byte-identical to single-repo mode. Dollars are aggregated only over kits carrying a `session:` line, coverage labeled `partial`/`full`.
- **`--by-task`** (requires `--session`) — per-task dollars by role, read from the `agent:` ledger. The honesty boundary is absolute: the orchestrator's own main-session transcript is **one un-split line**, a warm cluster's shared transcript is attributed to the cluster **as a unit** (never divided), and a recorded agent whose transcript is gone prices `null` with a note — a per-task figure is only ever the sum of transcripts that actually exist.
- **`--snapshot` / `--trend`** — `--history --snapshot` writes the history card as a dated `<YYYY-MM-DD>.json` into the gitignored `trends/` store (the one sanctioned write; latest-wins per day), and `--trend` renders per-tier first-try rate across those snapshots as a text time series (needs ≥2 snapshots to count as a trend; text only, no charts). `--trend` also renders an escalation-rate alarm whose trip value is derived from those same snapshots as a trailing per-kit baseline — never a hardcoded threshold — and degrades to an honest insufficient-history line.
- **`--envelope`** (rides `--history`) — per-class ladder-walk cost against the best two-model cascade, priced from `pricing.json`. Read-only; it changes no dispatch, pin, or escalation behavior.
- **`--roles`** — the per-role value view for kits that declared roles beyond the trio: dispatches, findings, confirmed findings, precision and marginal catches per role, cross-kit and per-kit. Its own card; it never rides `--history`.

**`bin/attempt_history.py`** is the other reader over the same ground, joining the attempt ledger (§4.4), the `NOTES.md` outcome lines and Codex role-use records into one record shape per dispatch with unknowns kept as unknown (`demo` / `show`). Where the scorecard answers "did the cheap tiers hold quality", the history answers "what was actually dispatched, by which driver, and how did it end".

## 7. The other harnesses, and the journal

Four surfaces reuse this routing-and-cost-awareness workflow beyond the Claude Code plugin. Three
are full harnesses with their own drivers, their own pricing file, and their own reference
document; the fourth is the daily journal. Everything that must mean the same thing on every
harness comes from `bin/kit_contract.py` (§4.4) — what each harness adds is only what it makes
different: its argument vector, its own loop, its escalation ladder, and its pricing file. No
harness's config reads another's pricing file, and none of them is invoked by a test, a verify
command, or kit execution; `--dry-run` and `--demo` are the sanctioned smoke paths and spawn
nothing.

**The Copilot harness (`copilot/`).** The same per-task routing and cost discipline ported to GitHub Copilot CLI. A cross-vendor `route` agent classifies a task into a tier (cheap / mid / strong / frontier) and prices 2–3 candidate models across vendors; an architect→execute→verify→escalate port (`bin/copilot_execute.py` plus model-pinned agents) mirrors the kit loop; and a budget-capped **Ralph** goal loop (`bin/copilot_ralph.py`) drives a self-directed objective under a spend ceiling. Copilot meters everything in **AI Credits** (the AIC's dollar value is data — `billing_unit.usd_per_credit` in `data/pricing.copilot.json` — never a literal in a doc or skill), priced by `bin/copilot_pricing.py` from the separate `data/pricing.copilot.json` (which ids sit in which tier is data read from that file, never a list memorised in a doc — `python3 bin/copilot_pricing.py models` prints every row with the tier it carries, and more than one of them currently reads `frontier`). Because Copilot has no `${CLAUDE_PLUGIN_ROOT}`-style runtime variable, the bundle's config carries a `{{POLYTROPOS_ROOT}}` placeholder that `bin/harness_select.py` resolves to an absolute path at install time. Beside those: `bin/copilot_usage.py` reads `~/.copilot`'s session logs strictly read-only for a usage report, `bin/copilot_prefs.py` is the single home for the user's own model pins and excludes, `bin/copilot_statusline.py` is the Copilot-side twin of the statusline, and `copilot-docs/` is a generated doc center written only by `bin/copilot_docs.py`. Full guides: `docs/COPILOT-HARNESS.md`, `docs/COPILOT-WORKFLOW.md`, `docs/COPILOT-COSTVIZ.md`.

**The Codex harness (`codex/`).** Native `$skill` workflows packaged as a Codex plugin, with routing data in `data/pricing.codex.json`. Its distinguishing feature is **central application policy** (`bin/codex_policy.py`, `bin/codex_app_policy.py`): Astra owns planning, dependency coordination, bounded recovery and final acceptance, while Luna, Terra and Sol implement — cheap mechanical, routine, and hard/security/integration work respectively — and model identity, availability, effort support and pricing are all derived from the pricing file at run time rather than written into the policy. The kit-dispatch driver is `bin/codex_execute.py` (`status` / `run` / `review` / `accept` / `prepare`), which instantiates no warm pool and whose recovery path requires driver-recorded lower-tier attempts plus a real failure signal before it climbs; a dispatch that failed for an `auth`, `config`, `permission` or `infrastructure` reason stops the ladder and names the class instead. Two routing policies are selectable by name — `reserved` (the default) and an opt-in `adaptive` one — and which is in force is an explicit selection written into the run's NOTES.md, never learned from observations. `bin/codex_usage.py` reads `~/.codex` read-only with an honest unpriced fallback, and `bin/codex_legacy_migration.py` retires proven legacy copies reversibly. **A ChatGPT-plan Codex run is usage-limited, not token-billed**, so every dollar figure for one is a labeled API-equivalent relative-burn proxy and never a bill: `billed_usd` stays null and proxy dollars never enter a priced total. Full guide: `docs/CODEX-HARNESS.md`.

**The Cursor harness (`cursor/`).** The same kit contract driven through Cursor's headless CLI (`agent -p`) by `bin/cursor_execute.py` on `bin/cursor_adapter.py`. What Cursor makes different is **identity before trust**: the CLI installs as a binary named `agent`, a name any tool might carry, so the driver refuses to dispatch until the binary has said what it is — either `agent --version` names Cursor, or `agent about --format json` answers with Cursor's own schema. A binary matching neither is `unknown` and is refused before a claim is taken, before the ledger is opened, and before any file is written; an absent one is `absent`. Cursor ships three products — an IDE agent, a command-line agent, and cloud agents — and they are **reported separately**, because only the CLI is driven from here and files-only support for the other two is not a claim about driving them. `data/pricing.cursor.json` carries no rates, so Cursor usage is honestly unknown rather than estimated. The install is project-scoped into a target's `.cursor/` with an ownership-aware writer. Two facts stay apart: the **CLI implementation is present and verified** (six dated `verified: supported` rows in `primitives/harness-capabilities.json` against a named client version), while the **adaptive-decision profile is `implemented: unsupported` / `verified: unknown`**, pending independent proof (§4.10). Full guide: `docs/CURSOR-HARNESS.md`.

**The daily journal (`journal/`).** A nightly, gitignored, read-only cross-tool work journal. A deterministic collector (`bin/journal_collect.py` — no model, no network) ingests the day's activity across Claude Code, Copilot CLI, Codex CLI, and git — JSONL / flat-text only, never a SQLite file, never a shelled-out CLI — into a **metadata-only** `digest.json` (never transcript text). A scheduled summarizer (`bin/journal_summarize.py`) then routes that digest to a cheap/mid model that writes three short documents: the day's narrative, a technical breakdown, and a next-day plan. Codex activity is counted and, when the day's rollout logs carry tokens, shown as a clearly-labeled API-equivalent relative-burn proxy priced from `data/pricing.codex.json` — never a bill, never added to the priced total. The whole tree — digest, documents, inbox, logs — lives under one gitignored `journal/` entry, so personal data never lands in git. Full guide: `docs/DAILY-JOURNAL.md`.

## 8. Operational playbooks

**Today (Fable on subscription).** Daily driver is the Opus tier (`python3 bin/aesop_bridge.py tiers` says which model that is now); `xhigh` standing effort removed in favor of per-task effort; escalate via `/architect`; watch the statusline's 5h/7d burn. This posture is not hypothetical — this repository is itself built by it, and every kit it has executed left a ledger behind. The track record is a **measurement, not a figure to quote**: run

```bash
python3 bin/routing_scorecard.py --history --kits-dir .claude/kits
```

for the current cross-kit per-tier card, and `python3 bin/attempt_history.py show --kits-dir .claude/kits` for the dispatch-level join. The card's own columns are the answer: per tier, how many tasks were pinned to it, how many carry an outcome, and how those outcomes split across **first-try / retry / escalated / blocked**, with a first-try and an escalation rate beside them, plus per-role findings-and-confirmed counts and the re-route history. Read those columns; do not read a number out of this page. What is safe to say qualitatively is only this: the great majority of execution work passes verify on the first attempt at the tier it was pinned to, retries are a real recorded minority rather than a theoretical one, and the escalated and frontier columns are there precisely so that "the cheap tiers held" is something you check rather than something you assume. Any figure fixed here would be wrong by the next kit; the command is the claim. Measurement (§6) is what makes each downgrade decision evidence-based rather than a hunch.

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
