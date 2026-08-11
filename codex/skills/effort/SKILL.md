---
name: effort
description: Control the GPT-5.6 reasoning-effort dial per run — pick the right level, apply it, and step it up only on failure evidence. Use when the user asks to raise/lower reasoning effort, run at the deepest level, or make a run think harder or cheaper.
metadata:
  short-description: Pick and apply the right GPT-5.6 reasoning-effort level
---

# Effort — the reasoning-effort dial

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/effort/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and every referenced
`$POLYTROPOS_ROOT/bin/` engine exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

You control HOW HARD a Codex run thinks, independent of which model it runs on. You are a
decision aid, not a report.

## Determine the billing mode FIRST

How the user pays decides which framing leads — establish it before recommending anything:

- **ChatGPT sign-in ⇒ subscription framing.** Effort drives usage-limit burn, not dollars.
  Any dollar figure you show is a labeled API-equivalent proxy — never present it as a bill.
- **`OPENAI_API_KEY` auth ⇒ API framing.** The token-metered dollars are real and authoritative.
- If you are unsure which mode applies, ask before recommending a level.

Deeper effort means more reasoning tokens, which means faster burn either way — a subscription
run at the top of the ladder draws down usage limits fastest of anything on the roster, and an
API run at the top of the ladder is the most expensive per task.

## Get the ladder from data — never from memory

The level vocabulary lives ONLY in `$POLYTROPOS_ROOT/data/pricing.codex.json`'s
`knobs.reasoning_efforts`. Never enumerate the levels yourself — run

`python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" knobs`

and relay what it prints: the ladder in ascending order plus its notes, which name which level
is newest and whether it needs a settings toggle. The same command also prints `mode` lines
(`ultra`, `fast`) — these are MODES, not rungs on the effort ladder, and their CLI surfaces are
unpublished as of the data's `cached_date`: relay the note verbatim, never invent a flag for
them.

## Apply it

- **One-shot dispatch**: `-c model_reasoning_effort=<level>` on `codex exec` — the one confirmed
  surface (same form as the `route` skill's mechanism table), where `<level>` is a value taken
  verbatim from `knobs` output, never guessed.
- **Kit tasks**: `python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit <dir> --task <id> --effort <level>`
  — the driver validates `<level>` against the data's knobs at run time and rejects an unknown
  word; it never accepts an invented one.

## Choose the level

- **Omit the override for routine work.** The configured default applies, and that is correct
  for most runs.
- **The low end of the ladder** is for bulk, extraction, formatting, and other latency-sensitive
  work — deliberately shallow thinking is the point there.
- **Step UP one level at a time, only on concrete failure evidence** — a run that got it wrong,
  not a hunch. Don't start at the deepest level; that mirrors the `escalate` skill's
  ladder-stepping rule exactly, and for the same reason: the expensive end of the ladder should
  be earned, not assumed.
- **Effort is per-model and orthogonal to model choice.** A tier jump (`route`, `escalate`)
  fixes a capability gap; turning effort up on the CURRENT model fixes a thinking-time gap.
  When a run underperforms, try the cheaper move first — more effort on the same model — before
  reaching for a stronger tier.

## Output shape

Keep it compact: the recommended level (or "omit the override"), the one-line reason, and the
exact command to run. If the task is routine, say so and stop — don't manufacture a reason to
turn the dial up.

The root proof above applies before every driver or pricing command.
