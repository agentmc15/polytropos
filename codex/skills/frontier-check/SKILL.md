---
name: frontier-check
description: Decide whether a task is worth the frontier-tier model in the GPT-5.6 family versus a mid or cheap candidate, and how to run it optimally — reasoning effort, task spec, refusal fallbacks. Use when the user asks "is the top model worth it here" or how to get the most out of it.
metadata:
  short-description: Is the frontier GPT-5.6 tier worth it, and how to run it
---

# Frontier-tier check

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/frontier-check/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and every referenced
`$POLYTROPOS_ROOT/bin/` engine exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

You decide whether a task justifies the frontier tier of the GPT-5.6 family, and — if it
does — how to run it well. You are a decision aid, not a report.

## Determine the billing mode FIRST

How the user pays decides which framing leads — establish it before anything else:

- **ChatGPT sign-in ⇒ subscription framing.** The frontier question is really a question
  about usage-limit burn, not dollars. Lead with the burn index; any dollar figure you show
  is a labeled API-equivalent proxy — never present it as a bill.
- **`OPENAI_API_KEY` auth ⇒ API framing.** The token-metered dollars are real and
  authoritative.
- If you are unsure which mode applies, ask before estimating.

## Get the numbers from data — never from memory

All pricing lives in `$POLYTROPOS_ROOT/data/pricing.codex.json`. Do not quote prices,
ratios, or model ids from memory.

- `python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" models --json` — the full roster;
  filter for the row(s) whose `tier` is `"frontier"` to find today's frontier model.
- `python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" est <PROFILE> frontier` — `est`
  accepts a tier word directly, so you never have to hardcode the model id it resolves to.
  Run the same command with `mid` and `cheap` to build the comparison ratios yourself.
- `python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" plans` — ChatGPT plan facts (no
  invented allowances).

Per the data's `tier_note`, this roster ships three durable tiers, so `strong` is unpopulated
and resolves UPWARD — asking for `strong` today lands you on the frontier model. This file
must never contain a real model id: derive it fresh, every time, from the engine's output.

## Is the frontier tier worth it here?

Route to the frontier tier when the task is:

- **Long-horizon autonomous work** — a run expected to complete without correction: large
  multi-file migrations, overnight agentic loops, complex refactors.
- **A concrete failure by the mid tier on this same task** — the strongest signal available,
  since the data ships no populated strong tier to fall back on first.
- **The deepest reasoning or multi-source synthesis** — ambiguous problems needing real
  judgment, not lookup.
- **Heavy parallel sub-agent orchestration** — long-running coordination across many
  sub-agents.

Do NOT reach for the frontier tier for: routine coding, tasks with well-known solutions,
anything the mid tier already handles well, or low-latency work — the cheap tier is the speed
lane per the data's `knobs`, and frontier burns usage limits fastest of anything on the
roster.

## Caveats to surface every time the frontier tier is recommended

- Pull the frontier model's `notes` from the data and relay them verbatim — they change which
  caveats matter this run (e.g. Cerebras availability is a speed fact there, not a price).
- If the vendor or the model's `notes` indicate safety-classifier refusals on cyber/bio-
  adjacent requests, say so and name the fallback: rerun the same prompt on the mid tier and
  explain why.
- If `/model` does not list a frontier-tier candidate, the plan doesn't have it yet (limited
  preview) — route among what `/model` actually lists and say so plainly.

## How to run it optimally

1. **Full spec up front.** One well-specified turn (goal, constraints, what "done" looks
   like) beats drip-fed instructions.
2. **Sweep reasoning effort — don't default to `max`.** Use
   `-c model_reasoning_effort=<level>` (levels from the data's `knobs.reasoning_efforts`); `max` and the new `ultra` mode
   trade speed for depth, so reserve them for the hardest agentic work and pick a lower rung
   for routine tasks. This is the main burn/cost lever.
3. **De-prescribe migrated prompts.** State goals and constraints, not a numbered list of
   steps written for a weaker model.
4. **Let it delegate.** Encourage parallel sub-agents for independent workstreams, and give it
   a persistent notes surface for multi-session work.
5. **Ground progress claims.** Require it to verify claims against tool results before
   reporting a long run as done.

Codex fast mode (priority processing for time-sensitive work) exists but its CLI surface is
unpublished as of the data's `cached_date` — point the user at release notes rather than
inventing a flag.

## Recommend, then tell the user exactly how to act

| goal | how |
| --- | --- |
| one-shot dispatch | `codex exec "<task>" --model <model-id>` (add `--full-auto` when it must edit files) |
| interactive switch | `/model` picker in the Codex TUI |
| persistent default | `model = "<model-id>"` in `~/.codex/config.toml` |
| reasoning effort | `-c model_reasoning_effort=<level>` (levels from the data's `knobs.reasoning_efforts`) |

## Standing recommendation

- **Multi-task frontier-class work** → use the `architect` skill instead of a raw dispatch:
  it plans once on the frontier tier and emits a kit that cheaper tiers execute.
- **A single verify-gated task** → use the `escalate` skill: it starts cheap, retries once on
  failure evidence, and climbs the ladder only as far as the task needs — frontier last.

The root proof above applies before every pricing command.
