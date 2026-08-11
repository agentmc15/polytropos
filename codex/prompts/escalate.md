---
description: "Run one task on the cheapest sufficient GPT-5.6 tier behind a machine-checkable success check, escalating up the tiers — frontier last — only if the check fails. Use for \"try it cheap first, fall back to the top model if it doesn't work\" or an auto-escalating, verify-gated dispatch."
---

> Deprecated compatibility prompt; prefer `$escalate`.

# Escalating dispatch

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/escalate/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and every referenced
`$POLYTROPOS_ROOT/bin/` engine exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

You run ONE task through a cost-ascending ladder of Codex tiers, promoting to the next tier
**only when a check fails** — so the frontier tier is spent on genuine difficulty, never on
routine work. You are the orchestrator: you stay on your own session and dispatch each attempt
as a fresh `codex exec` run so you can grade it with fresh eyes.

## Determine the billing mode FIRST

How the user pays decides the framing — establish it before dispatching anything:

- **ChatGPT sign-in ⇒ subscription framing.** Every hop draws down opaque usage limits, not
  dollars. Any dollar figure you report is a labeled API-equivalent proxy — never a bill.
- **`OPENAI_API_KEY` auth ⇒ API framing.** The token-metered dollars are real and authoritative.
- If unsure, ask before estimating.

## Step 0 — Establish the trigger (the verify command)

Automatic escalation needs a failing check to fire on. Before dispatching anything, pin a
**machine-checkable success condition**: a test command, a build, a lint, a `curl` + grep, a
script that exits non-zero on failure. State it explicitly.

- If the task already implies one (a failing test, "make X pass"), use it.
- If it doesn't, derive the cheapest sufficient check and say what you chose.
- If the task genuinely has no checkable outcome (open-ended writing, judgment calls), say so
  plainly: automatic escalation can't trigger reliably here. Fall back to attempting on the
  cheaper tier and escalating on the run reporting blocked or on your own adversarial read —
  don't pretend a vibe is a verify.

## Step 1 — Pick the first (cheapest sufficient) tier

Default to the **cheapest tier you'd actually trust for this task**, from the data's
`cheap|mid|strong|frontier` vocabulary via
`python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" models --json`. Use the `route` skill's
framing if unsure. Per the data's `tier_note`, this roster is missing a populated `strong` tier,
so asking for `strong` resolves UPWARD to the frontier model — the same skip-up rule
`bin/codex_execute.py` implements. Never quote a model id or price from memory.

## Step 2 — Dispatch

`codex exec "<self-contained brief>" --model <model-id>` (add `--full-auto` when it must edit
files). The dispatched run sees nothing of this session, so the brief must carry the task, the
needed context, and the verify command with an instruction to run it and report the output.

## Step 3 — Verify independently, then decide

Run the verify command **yourself**. The dispatched run's success claim is not evidence.

- **Passes** → done. Report the result and note it never needed the frontier tier.
- **Fails** → retry ONCE on the same model, handing it the exact failure output — cheap attempts
  often just need to see the error. Re-verify.
- **Fails again** → escalate (Step 4).

## Step 4 — Climb the ladder

Exactly the rule `bin/codex_execute.py` implements for kit tasks: tiers strictly ABOVE the
current model's tier in `cheap → mid → strong → frontier` order, FIRST model in pricing-file
order per tier, empty tiers skipped (so an empty `strong` is skipped straight to `frontier`) —
derive the ladder from `models --json` at run time, never from memory. Each hop carries evidence
only: what was tried and the exact check output — the diagnosis is what keeps the expensive hop
short.

The extra lever the frontier hop has here: **reasoning effort**. Prefer
`-c model_reasoning_effort=medium` for the first frontier attempt and step upward through the
data's `knobs.reasoning_efforts` ladder one level at a time, only if the check still fails —
don't start at the deepest level.

The frontier rung is last: say what makes the task frontier-worthy when you reach it. If the
frontier model declines the request (vendor safety classifiers — see its `notes` in the data),
fall back to a mid-tier hop at higher effort and say why. If the top rung still fails, stop and
report honestly — what each tier tried, the final check output, and whether the task looks
mis-specified.

## Cost posture

In **subscription** mode the marginal cost of every hop is usage-limit burn, not dollars — a
labeled API-equivalent proxy only, never a bill; the effort/scope levers still matter for burn.
In **API** mode, price attempts with `codex_pricing.py est <PROFILE> <MODEL_ID>` when asked.
Always report which rung passed so the ladder's savings are visible.

## Kit tasks

For a task that lives in a kit, prefer
`python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit <dir> --task <id> [--effort E]`
— the driver implements this same ladder with statuses, NOTES writeback, and
`--max-escalations`; this skill is for one-off tasks outside a kit. For multi-task work, prefer
the `architect` skill over calling this in a loop.

The root proof above applies before every driver or pricing command.
