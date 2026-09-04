# Effort and context

Choosing a model is the coarse dial. Two finer ones decide what that choice actually costs
you, and on a subscription they are the only dials that move anything at all.

## Effort — how hard the chosen model thinks

Reasoning effort is a per-run setting, not a property of the model. Turning it down on
routine work is the subscription-mode equivalent of downgrading a tier in API mode: it
lowers burn without giving up the model's capability where you need it. Turning it up is
the cheap thing to try *before* concluding a task needs a more expensive tier — and the
escalation ladders do exactly that, preferring a middle effort level on a frontier hop and
stepping up one level at a time before giving up.

The level vocabulary is **data, not code**, and each harness ships its own ladder. Ask the
engine rather than assuming:

```bash
python3 bin/copilot_pricing.py knobs
python3 bin/codex_pricing.py knobs
```

Each prints its harness's ladder in that harness's own display form, plus how the level is
actually set — an interactive picker on Copilot, and on Codex a per-run override
(`-c model_reasoning_effort=<level>`), which the card calls the one confirmed surface.
Omit that override and the configured default applies, which is the right choice for most
runs. Claude Code has no separate effort skill; effort there rides on the invocation, which is
why [escalate](../skills/claude/escalate.md) sets it on the frontier hop rather than
offering it as a standing control.

**One boundary:** effort is not a substitute for the right tier. A task the chosen model
genuinely cannot do does not become doable at a higher level — it gets slower and more
expensive at the same wrong answer. That is what the escalation gate is for.

## Context — how much you are carrying while it thinks

A long agentic session pays for its own history on every call. The three levers, in the
order the skill itself ranks them:

1. **Prevent — free and lossless.** Work that never enters the window costs nothing and
   loses nothing. Delegate bulk reading to a subagent that returns conclusions rather than
   file dumps.
2. **Prune — cheap but lossy.** Compaction reclaims room by replacing detail with a
   summary. Use it, but knowing what it costs.
3. **Measure — free.** Measuring changes nothing by itself; it tells you which of the
   other two to reach for, and when.

Measuring is what this repo actually gives you:

```bash
python3 bin/context_weight.py session
python3 bin/context_weight.py demo
```

`session` reads the latest session read-only and shows per-call weight, the growth curve,
and ranked contributors — what actually filled the window, not a guess. `--harness codex`
and `--harness copilot` answer the same question at those harnesses' honest, lower
fidelity, and the card says so rather than pretending to parity. `demo` runs the whole
thing on synthetic data if you would rather see the shape first.

The move worth internalizing: **checkpoint before you compact.** Write the decisions you
would hate to lose to disk *first*, because compaction is the one lever that costs
accuracy, and a file on disk survives a lossy step that a paraphrase does not.

## Related

- [effort on Copilot](../skills/copilot/effort.md) and
  [effort on Codex](../skills/codex/effort.md) — the per-harness cards.
- [context-weight](../skills/claude/context-weight.md) — what it can and cannot do,
  including the checkpoint procedure in full.
- [Billing modes](billing-modes.md) — why these dials matter more than model choice on a
  plan.
- [Deep dive: effort dial](../deep-dives/effort-dial.md) and
  [deep dive: context weight](../deep-dives/context-weight.md) — the long-form mechanics.
