# polytropos

> *aesop tells the fables; polytropos finds the way.*

*(polytropos — “of many ways”, Odysseus’s epithet and the fourth word of the Odyssey: many models, many paths, resourceful under constraint.)*

A Claude Code plugin that picks the right model per task, estimates the cost before you run it, and keeps Fable 5 reserved for work that actually needs it.

**In-depth architecture guide:** [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) (Markdown) · [docs/how-it-works.html](docs/how-it-works.html) (styled HTML — open in a browser).

**Complete guide & cookbook:** [docs/GUIDE.md](docs/GUIDE.md) · [docs/guide.html](docs/guide.html) — every skill documented, the iterative workflows, how aesop fits, and 10 worked examples (tasks, greenfield, brownfield, backlog, security).

**Aesop integration:** [docs/AESOP-INTEGRATION.md](docs/AESOP-INTEGRATION.md) — consume `route`/`fable-check` from [aesop](https://github.com/agentmc15/aesop) registries, and feed aesop's budget dials with numbers computed from `data/pricing.json` (`bin/aesop_bridge.py`).

**GitHub Copilot harness:** [docs/COPILOT-HARNESS.md](docs/COPILOT-HARNESS.md) — the same routing workflow for GitHub Copilot CLI: AI-Credit pricing data in `data/pricing.copilot.json`, a cross-vendor `route` agent in `copilot/`, installed via `bin/harness_select.py`.

**Copilot documentation center:** [copilot-docs/README.md](copilot-docs/README.md) ([HTML](copilot-docs/index.html)) — installation, skills, agents, models, workflows, and per-document AIC estimates.

**OpenAI Codex harness:** [docs/CODEX-HARNESS.md](docs/CODEX-HARNESS.md) — the same routing workflow for OpenAI Codex CLI: GPT-5.6 (Sol/Terra/Luna) pricing data in `data/pricing.codex.json` with honest subscription-vs-API framing, a `/route` custom prompt and workflow prompts in `codex/`, a kit-dispatch driver (`bin/codex_execute.py`), and a read-only usage report (`bin/codex_usage.py`), installed via `bin/harness_select.py`.

**Copilot workflow (Phase 2):** [docs/COPILOT-WORKFLOW.md](docs/COPILOT-WORKFLOW.md) — architect → execute → verify → escalate for Copilot CLI (`bin/copilot_execute.py` + workflow agents in `copilot/`), a budget-capped Ralph goal loop (`bin/copilot_ralph.py`), and the vendored `lessons-loop` skill.

**Copilot cost visibility (Phase 3):** [docs/COPILOT-COSTVIZ.md](docs/COPILOT-COSTVIZ.md) — a usage report over Copilot CLI's session logs (`bin/copilot_usage.py`, read-only, priced from `data/pricing.copilot.json` in USD + AIC), pooled-AIC runway for org plans (`bin/copilot_pricing.py runway --pool-aic`), and the aesop compile round-trip proposal ([docs/AESOP-COMPILE-PROPOSAL.md](docs/AESOP-COMPILE-PROPOSAL.md)).

**Daily work journal:** [docs/DAILY-JOURNAL.md](docs/DAILY-JOURNAL.md) — a nightly, scheduled work journal: a deterministic collector ingests the day's usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into a gitignored `journal/<date>/digest.json`, then a routed cheap/mid model writes `narrative.md`, `technical.md`, and `next-day.md` (fed by open kit tasks, a local `journal/inbox.md`, and uncommitted work).

**Graph-engineering properties:** [docs/GRAPH-ENGINEERING.md](docs/GRAPH-ENGINEERING.md) — the kit that converges the three harnesses toward shared graph properties (node isolation, deterministic verify, attribution, lineage, budget, headless drivers), what was rejected and why, and how the ledger substrate works.

**Evidence-loop measurement surfaces:** [docs/EVIDENCE-LOOP.md](docs/EVIDENCE-LOOP.md) — auditing whether guardrails survive compaction (residency), when recurring lessons can become skills (promotion), and whether the escalation ladder outperforms simpler cascades (envelope).

**Repo-bench — measure models on a repo's own real work:** [skills/repo-bench/SKILL.md](skills/repo-bench/SKILL.md) — mine a target repo's issue-fix history into benchmark tasks, run candidate models in history-free sandboxes, grade through four oracle classes (tests, structural, blind LLM judge, cost/latency) on a leak-proof substrate, and get an interval-honest verdict you can opt into applying to routing (`bin/repo_bench.py`; `plan`/`demo` spend nothing — only `run --live --max-usd` ever spends).

**All-harness freshness — the update skill:** [skills/update/SKILL.md](skills/update/SKILL.md) — one read-only card (`bin/harness_update.py check`, exit 3 on drift) covering the Claude plugin cache, Copilot and Codex bundle drift, pricing-file ages, generated mirrors, and docs snapshot labels; `apply` refreshes exactly what each harness's own writer sanctions and never touches `~/.claude` (the remedy is printed, never executed).

**Graph grounding — repo analysis via graphify:** [skills/graphify/SKILL.md](skills/graphify/SKILL.md) — build a local knowledge graph of a repo with the external, user-installed graphify CLI (offline subcommand set only) and read it through `bin/graph_brief.py`: an architect-grounding card that compresses a multi-megabyte graph to one honest screen, with its blind spots (dynamic loaders invisible to AST extraction) labeled rather than hidden.

**The role-roster experiment — do more agents pay?:** [docs/ROLE-EXPERIMENT.md](docs/ROLE-EXPERIMENT.md) — grow a kit's execution roster from the trio to up to ten roles (`roles:` line in PLAN.md; scout, test-author, second-verifier, red-team, security-auditor, docs-editor, synthesizer), with every extra role's marginal catches measured against its cost by `bin/routing_scorecard.py --roles`. Extended roles are measured, never mandated — absent line means the trio, unchanged.

## Why

Model lineup and API pricing (per million tokens, cached 2026-07-24):

| Model | Input | Output | Best for |
|---|---:|---:|---|
| Fable 5 | $10 | $50 | Long-horizon autonomous work, hardest reasoning |
| Opus 5 | $5 | $25 | Multi-file features, hard debugging, review — same rate as Opus 4.8 |
| Opus 4.8 | $5 | $25 | Superseded by Opus 5; kept for costing historical transcripts |
| Sonnet 5 | $3 ($2 intro until 2026-08-31) | $15 ($10 intro) | Day-to-day workhorse; near Opus-tier at high effort |
| Haiku 4.5 | $1 | $5 | Classification, extraction, bulk API calls |

Two billing modes with **opposite** optimization goals:

- **`api`** — building an app, or any pay-per-token usage. Optimize dollars: cheapest sufficient model. Haiku earns its keep here.
- **`subscription`** — Claude Code / Claude UI on a plan. Marginal dollar cost is zero; the only cost is 5-hour/7-day rate-limit burn. Haiku is pointless here — use the best model on the plan and manage burn with **effort levels**, not model downgrades.

Set your default mode in `data/pricing.json` → `billing_mode` (currently `subscription`). Override per invocation with `--api` / `--sub`.

## Install

Persistent install via the local marketplace this repo provides
(`.claude-plugin/marketplace.json`, marketplace name `polytropos-local`):

```
/plugin marketplace add /path/to/polytropos
/plugin install polytropos@polytropos-local
```

Non-interactive CLI equivalent (confirmed via `claude plugin --help`):

```bash
claude plugin marketplace add /path/to/polytropos
claude plugin install polytropos@polytropos-local
```

One-off session only (dev/testing, not a persistent install):

```bash
claude --plugin-dir /path/to/polytropos
```

## The intended workflow

**Opus 5 is the daily driver. Fable 5 is escalated per-portion, then you come back down.**

```
daily work (Opus 5)
   │  complex planning / complex task detected (/route flags it, or you know)
   ▼
/polytropos:architect <task>        ← Fable 5 runs ONCE (in-session or as a subagent)
   │  emits an execution kit: .claude/kits/<slug>/PLAN.md + TASKS.md,
   │  model-pinned subagents (implementer=sonnet, verifier=haiku, reviewer=opus),
   │  CLAUDE.md guardrails — Fable's judgment encoded as scaffolding
   ▼
/polytropos:execute <slug>          ← back on Opus/Sonnet; loop dispatches tasks
   │  to the kit's agents, verifies independently, updates state
   ▼
blocked task? → targeted Fable consult (one task's brief only) → resume cheap execution
```

The kit's agents pin their own models in frontmatter, so the model mix enforces itself during execution — Fable spend stays concentrated in the short architecture phase.

## Skills

| Skill | What it does |
|---|---|
| `/polytropos:route <task>` | Classifies the task, shows a per-model cost table, recommends a model, and offers to dispatch the task to a subagent on that model (or prints the `/model` command to switch your session). Big Fable-worthy tasks get routed to `architect` instead. `--api` / `--sub` forces the billing framing. |
| `/polytropos:architect <task>` | Fable 5 deep-plans a complex task AND builds the execution kit (task briefs, model-pinned subagents, skills, verification loops) so cheaper models execute at near-Fable quality. Works from an Opus session (dispatches a Fable subagent) or natively on `/model fable`. |
| `/polytropos:execute <slug>` | Runs a kit: loops TASKS.md, dispatches each task to the kit's agents, verifies independently, retries once, escalates blocked tasks back to Fable one at a time. |
| `/polytropos:escalate <task>` | Runs one task on the cheapest sufficient model behind a machine-checkable success check, verifies it independently, retries once, and auto-escalates to a Fable 5 subagent (carrying the failure evidence, at `medium` effort where the invocation allows) only if the check fails. The per-task sibling of `execute`'s escalation valve. |
| `/polytropos:cost-report` | Analyzes your local transcripts (`~/.claude/projects`): spend by model, top sessions, and Fable/Opus sessions that were Sonnet-sized — with dollar deltas. |
| `bin/session_cost.py` (script) | The single-session companion to `/cost-report`: sums the main loop **plus every subagent transcript** (deduped by message id), prices it per model, and computes what the same work would have cost with Fable 5 — or any `--vs` model — as the sole driver. Shows actual-vs-counterfactual totals and the % the model mix saved. Read-only; `--json` for machine output. |
| `bin/routing_scorecard.py` (script) | Turns an executed kit's outcomes into a routing-quality scorecard: verify passed first-try vs retry vs escalated vs blocked, the model mix, the share of cheap-model work that survived review unchanged, and — with `--session` — dollars vs an all-Fable counterfactual (via `session_cost`). Read-only; `--json` for machine output; `--demo` runs on a built-in synthetic kit. |
| `/polytropos:fable-check <task>` | Is this task worth 2× Opus pricing on Fable 5, and if so how to run it well (effort, spec-up-front, refusal fallbacks). |
| `/polytropos:setup` | Installs the statusline (model · session cost · context % · rate-limit burn) into `~/.claude/settings.json`, with confirmation. |
| `/polytropos:journal` | The daily work journal: collect yesterday's activity across all three harnesses (read-only), summarize via a routed cheap model, plan today from due cards. |
| `/polytropos:memory` | Durable facts across sessions with pull-only, relevance-gated, budget-capped recall — never bulk-injected into context. |
| `/polytropos:bench-routing` | External benchmark rankings joined against this repo's own measured outcomes; `compare` answers "should role X move up a model?" — and measured outcomes beat benchmark priors. |
| `/polytropos:context-weight` | What fills your context window and what to do about it: per-call weight curves, ranked contributors, sidechain split, and a live watch with checkpoint-before-compact guidance. |
| `/polytropos:repo-bench` | Benchmark models against a target repo's own issue-fix history — sandboxed, leak-proofed, four oracle classes, spend only behind `--live --max-usd`, verdicts below the evidence floor never applied. |
| `/polytropos:update` | One freshness card across all three harness installs and every data surface; `apply` refreshes what each harness's own writer sanctions and never writes `~/.claude`. |
| `/polytropos:graphify` | Local knowledge graph of a repo via the external graphify CLI (offline set only, availability-gated), read through the `graph_brief` architect-grounding card. |

## Key constraint to know

Nothing in Claude Code can programmatically switch the **main session's** model — only you, via `/model`. What *can* be automated is delegation: the Agent tool accepts a `model` parameter, so `/route` offers to run a task in a subagent pinned to the cheaper model. The same constraint blocks the strongest remaining multi-model trick — swapping the main-session model at context-compaction boundaries — which stays an upstream ask, documented in [docs/FUSION-TIER1.md](docs/FUSION-TIER1.md).

## Updating prices

All prices live in `data/pricing.json` — nothing else hard-codes them. When prices or models change, update that file from <https://platform.claude.com/docs/en/pricing.md> (or ask Claude to re-run the `/claude-api` skill and copy the current-models table). Bump `cached_date`. Then run `python3 bin/sync_pricing_refs.py` to refresh the generated mirrors under `skills/*/references/` — the test suite fails if they drift.

## When Fable 5 leaves the subscription

Checklist:

1. Set `billing_mode` to `"api"` in `data/pricing.json`.
2. Flip your global default in `~/.claude/settings.json` from `claude-fable-5[1m]` to `sonnet` or `opus`, and remove the standing `xhigh` effort default.
3. Route *up* to Fable deliberately: `/model fable` for a session, or `/polytropos:route` per task.
4. Run `/polytropos:cost-report` after a couple of weeks to sanity-check where the money goes.
