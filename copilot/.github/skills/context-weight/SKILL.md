---
name: context-weight
description: Reach for this when your context is huge, cache reads are high, you're asking should I compact, or you want to know what filled the window — it explains what this skill can and cannot do, ranks prevent/prune/measure in priority order, and gives the checkpoint move before you compact.
---

# Context weight

## What this skill cannot do

This skill cannot remove anything from your context window. It is text loaded INTO the window —
read-only instructions the model follows — with no mechanism to mutate the message array a call
submits. Only the harness can do that (compaction, or clearing). This skill's job is to tell you
*when* to act and *what* to act on; it never acts for you.

## Run the engine

```bash
python3 {{POLYTROPOS_ROOT}}/bin/context_weight.py session --harness copilot    # this session's per-call weight
python3 {{POLYTROPOS_ROOT}}/bin/context_weight.py overview --harness copilot   # cross-session working-set table
python3 {{POLYTROPOS_ROOT}}/bin/context_weight.py audit                        # resident config surfaces (incl. copilot-instructions.md) vs a token budget
python3 {{POLYTROPOS_ROOT}}/bin/context_weight.py demo                         # synthetic cross-harness smoke, no real data touched
```

All four take `--json`. This is the real argparse surface — confirm against
`python3 bin/context_weight.py --help` before assuming any other flag exists; do not invent one.

## Copilot's honest fidelity

Copilot's session logs record no per-turn input/cache split, so there is **no growth curve** on
this harness — `session --harness copilot` reports a **session-average** weight
(`(input + cache_read + cache_write) / assistant turns`) instead, and that is the honest
substitute, not a curve in disguise. `watch` is Claude-only: it has no `--harness` flag, and
passing `copilot` to it prints an honest refusal line rather than a fabricated live number. That
means there is no live threshold to watch here — apply the three levers below on a schedule
(e.g. once per session, or before a long task), not on a threshold crossing.

## The three levers, in priority order

1. **PREVENT — free and lossless.** Delegate bulk reads to subagents that return conclusions,
   cap tool output before it enters the window, defer loading a file until it's needed. Nothing
   here ever costs anything to reverse, because the mass never enters the window.
2. **PRUNE — cheap but lossy.** Compaction. The only lever that can cost accuracy — a compacted
   summary is not the original. Before compacting, write decisions, constraints, and open
   questions to a notes file — that anchor survives even after the transcript behind it is
   folded away.
3. **MEASURE — free.** `session`, `overview`, and `audit` tell you which of the first two is the
   move right now; measurement changes nothing by itself.

## Honesty rules

Every estimated figure is labeled `est.` — a rank or magnitude, never an exact token count and
never priced. That holds for the attribution and audit figures. The `session`/`overview` cards
are different: they also print a `context carry cost` line in USD and AIC, carrying the
mandatory label `API-equivalent dollars — an estimate, not a bill.` Always relay that figure
WITH its label — never strip it, and never add it to real spend figures (that's what the
`usage` skill reports). Each harness is reported at its own honest fidelity: Copilot gets
session-average, never a fabricated Claude-style curve.

## Same-named agent

For persona-isolated runs — a separate dispatch that should carry its own model pin
instead of this session's model — use the `context-weight` custom agent: pick it in the
`/agent` picker, or run `copilot --agent context-weight -p "<task>"`. This skill and that
agent are the same capability on two surfaces; the agent's frontmatter carries the model
pin, this skill runs on whatever model the session already uses.

## Installed?

If the literal `{{POLYTROPOS_ROOT}}` text is still visible above, the bundle is not
installed — tell the user to run `python3 bin/harness_select.py install --harness copilot`
(then `/skills reload` picks the skills up in-session).
