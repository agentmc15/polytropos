---
name: route
description: Pick the right Claude model for a task and estimate its cost before running it. Use when the user asks which model to use, whether a task needs Fable/Opus, what a task will cost, or wants a task dispatched to a cheaper model. Args are the task description, optionally prefixed with --api or --sub to force a billing mode.
---

# Model router

You are routing ONE task to the right model with a cost estimate. Read the plugin's `data/pricing.json` for all prices, model notes, and task-size profiles — resolve in order: `${CLAUDE_PLUGIN_ROOT}/data/pricing.json`; if that variable is unset, `../../data/pricing.json` relative to this SKILL.md; if neither exists, `references/pricing.json` beside this SKILL.md (a vendored snapshot — check its `cached_date` and flag prices as possibly stale if it is more than 60 days old). Never use prices from memory.

## Step 1 — Determine the billing mode

Two different questions get two different framings:

1. **"Which model should this Claude Code / Claude UI session use?"** → mode comes from `billing_mode` in pricing.json (overridable: `--api` / `--sub` flag at the start of the args wins).
2. **"Which model should the application I'm building call?"** → always `api` mode, regardless of the user's own plan. Detect this framing from the task: mentions of "my app", "endpoint", "pipeline", "batch job", "users", SDK code, production traffic.

State which mode you chose and why in one sentence.

## Step 2 — Classify the task

**`api` mode — dollar-optimized: cheapest sufficient model wins.**

| Model | Route here when |
|---|---|
| Haiku 4.5 | Classification, extraction, formatting, simple lookups, high-volume/bulk calls. Caveat: 200K context ceiling. |
| Sonnet 5 | The workhorse. Day-to-day coding, tests, docs, refactors, most app inference. Near Opus 4.8 at higher effort. Intro pricing until the `intro_pricing.until` date in pricing.json. |
| Opus 4.8 | Multi-file features, hard debugging, architecture, code review, moderate agentic loops — where Sonnet 5 at high effort falls short. |
| Fable 5 | Long-horizon autonomous runs, large migrations, deep research, problems Opus failed on. Flag the caveats from pricing.json notes (refusal classifiers, long turns, 30-day retention). |

When in doubt between two tiers in api mode, recommend the cheaper one and say what failure signal would justify upgrading.

**`subscription` mode — capability-first, burn-aware.** Marginal dollar cost is zero; the only cost is 5-hour/7-day rate-limit burn. The user's working posture:

- **Opus 4.8 is the daily driver.** Skip Haiku entirely — there is no reason to use it when dollars don't apply.
- **Escalate to Fable 5 for complex planning and genuinely complex tasks** — and for those, don't just recommend the model: recommend `/polytropos:architect`, which has Fable do the meta-work once (plan + execution kit of task briefs, model-pinned subagents, skills, verification loops) so Opus/Sonnet execute the rest at near-Fable quality. Fable for the portion that needs it, then back down.
- Drop to Sonnet 5 for trivial tasks or when rate-limit windows are running hot (statusline / `/usage` `rate_limits.*.used_percentage` high).
- Manage burn primarily via **effort level**, not model downgrades: `low`/`medium` for routine work, `high`/`xhigh` for hard agentic work.

## Step 3 — Estimate cost

Pick the closest `task_profiles` size (XS/S/M/L/XL) from pricing.json, or estimate tokens directly if the task gives you better information. For each candidate model:

- base cost = input_tokens/1M × input_per_mtok + output_tokens/1M × output_per_mtok
- For agentic loops (M and up), also show a cache-discounted figure: assume ~80% of cumulative input is cache reads at `cache_read_multiplier` (0.1×).
- Apply Sonnet 5 `intro_pricing` if today ≤ its `until` date.
- Mention `batch_discount` (50%) when the task is batchable (non-latency-sensitive bulk work).

In `subscription` mode, present the dollar figure as "API-equivalent burn" — a proxy for how hard the task hits rate limits, not money spent.

## Step 4 — Recommend and offer dispatch

Output, in order:

1. A short table: candidate models, estimated cost (or API-equivalent burn), one-line rationale each. Bold the recommendation.
2. The actions (session-routing questions only):
   - **Dispatch now**: offer to run the task immediately via the Agent tool with `model` set to the recommended alias (`haiku`/`sonnet`/`opus`/`fable`). Warn that the subagent does not share this conversation's context, so you will pass it a self-contained brief — write that brief from the conversation, run it, and relay the result.
   - **Switch the session**: print the exact command, e.g. `` `/model sonnet` `` — only the user can switch the main session's model.
   - **If the recommendation is Fable 5 and the task is big** (codebase review, greenfield plan, migration — anything with an execution phase): the default offer is `/polytropos:architect` instead of a plain dispatch — Fable plans and builds the execution kit, then `/polytropos:execute` runs it on cheaper models. Plain Fable dispatch is for small, self-contained Fable-worthy tasks only.
3. For app-building questions, skip the dispatch offer; instead give the exact model ID string and the API params to use (effort level, whether to batch, cache breakpoints), ready to paste into their code.

Keep the whole response compact — this is a decision aid, not a report.

## Measured tier map (repo-bench, optional)

Before recommending, check for `${CLAUDE_PLUGIN_ROOT}/prefs/repo-bench.json` (gitignored;
written only by an explicit `repo_bench.py apply` after a measured benchmark run). If it
exists and its `repo` matches the project being routed for, prefer its `tiers` /
`daily_driver` model ids over the default tier picks and SAY SO, citing `source_run` and
`applied_at`. If any id in it is missing from `data/pricing.json`, ignore the file and
say it is stale. Absent file = no change to this skill's behavior.
