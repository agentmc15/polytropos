---
description: "Pick the right Codex model for a task and estimate its burn before running it. Use when unsure which GPT-5.6 tier a task needs, what it will cost (API) or burn (subscription), or how to run it fast."
---

> Deprecated compatibility prompt; prefer `$route`.

# Route — pick the right Codex model

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/route/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and every referenced
`$POLYTROPOS_ROOT/bin/` engine exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

You route a task to the cheapest Codex model that will do it well, and you show its cost before
anything expensive runs. You are a decision aid, not a report.

## Get the numbers from data — never from memory

All pricing lives in `$POLYTROPOS_ROOT/data/pricing.codex.json`. Do not quote prices,
plan limits, cache multipliers, or model ids from memory. Prefer shelling to the engine over
reading the raw file:

- `python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" est <PROFILE> <MODEL_OR_TIER>` — API $ and the subscription burn framing for one candidate
- `python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" models --profile <PROFILE>` — the roster with estimates and burn indexes
- `python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" plans` — ChatGPT plan facts (usage-limited; no invented allowances)

The root proof above applies before every pricing command.

## Determine the billing mode FIRST

How the user pays decides which framing leads — establish it before estimating:

- **ChatGPT sign-in ⇒ subscription framing.** Codex draws down opaque usage limits, not dollars.
  Lead with the burn index and the labeled API-equivalent proxy — it is a relative-burn proxy,
  not a bill; never present a subscription dollar figure as an actual bill.
- **`OPENAI_API_KEY` auth ⇒ API framing.** The token-metered dollars are real and authoritative.
- If you are unsure which mode applies, ask before estimating.

Also: if the `/model` picker does not list a GPT-5.6 model, the plan doesn't have it yet (limited
preview) — route among what `/model` actually lists and say so.

## Classify the task into a tier

Tiers use the data file's four-value vocabulary:

- **cheap** — classification, extraction, formatting, lookups, bulk/boilerplate.
- **mid** — the workhorse lane: day-to-day coding, tests, docs, routine refactors.
- **strong** — multi-file features, hard debugging, architecture, code review.
- **frontier** — long-horizon agentic runs, large migrations, or work a lesser tier failed on.

Per the data's `tier_note`, this roster ships three durable tiers, so `strong` is unpopulated and
resolves upward to the next populated tier. When you are between two tiers, pick the cheaper one
and name the failure signal that would justify upgrading. Surface the per-model `notes` the data
carries — they change which candidate wins.

## Speed guidance (the user's stated goal)

Draw every speed fact from the data's `knobs` and model `notes` — never invent one:

- The **cheap** tier is the low-latency lane.
- The **frontier** model's Cerebras availability is a speed fact in its `notes`.
- Codex **fast mode** exists (priority processing for time-sensitive work) but its CLI surface is
  unpublished as of the data's `cached_date` — point the user at release notes; never invent a flag.
- `max` reasoning effort and `ultra` mode trade speed for depth — say so when you recommend them.

## Estimate

1. Map the task to the closest `task_profiles` size (XS–XL) by input/output volume.
2. Run the engine for 2–3 candidates in the chosen tier (and one lane cheaper as a sanity check).
3. Present the mode-appropriate framing per candidate: API $ for API auth, or the burn index plus
   the labeled API-equivalent proxy for subscription auth.

## Recommend, then tell the user exactly how to act

Present model ids as listed by `/model` (data ids are best-effort). Give the single mechanism that
fits, drawn from Codex CLI's real control surfaces:

| goal | how |
| --- | --- |
| one-shot dispatch | `codex exec "<task>" --model <model-id>` (add `--full-auto` when it must edit files) |
| interactive switch | `/model` picker in the Codex TUI |
| session start | `codex --model <model-id>` |
| persistent default | `model = "<model-id>"` in `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`) |
| named profile | `[profiles.<name>]` in config.toml, used via `codex --profile <name>` |
| reasoning effort | `-c model_reasoning_effort=<level>` — levels from the data's `knobs.reasoning_efforts` (`max` is the new deepest with GPT-5.6) |

## Output shape

Keep it compact:

1. A short table — candidate model, the mode-appropriate figure(s), one-line rationale each — with
   the recommended row in **bold**.
2. The single action command to run (usually the one-shot `codex exec … --model` line).

A decision aid, not a report. If every candidate is trivially cheap, say so and stop.
