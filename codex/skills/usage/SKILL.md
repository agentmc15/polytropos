---
name: usage
description: Analyze historical Codex CLI activity from local session logs, read-only — honestly unpriced or labeled-proxy. Use when the user asks what they've used, burned, or spent in Codex.
metadata:
  short-description: Report historical Codex usage from local logs (read-only)
---

# Codex usage report

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/usage/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and every referenced
`$POLYTROPOS_ROOT/bin/` engine exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

You report historical Codex CLI usage from this machine's own local logs. You are a read-only
analyst, not a report generator that invents numbers.

## Run the engine — never invoke `codex` to gather usage

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_usage.py" --days 30
```

Flags (the real argparse surface — do not invent others): `--days N` (lookback window, default
30), `--top N` (how many top rollouts to list, default 10), `--codex-home DIR` (override the
Codex home), `--json` (machine-readable output).

The engine walks `~/.codex/session_index.jsonl`, `~/.codex/history.jsonl`, and
`~/.codex/sessions/YYYY/MM/DD/*.jsonl` strictly read-only — JSONL only, it never opens a
`*.db` file and never invokes the `codex` CLI. It prices only the tokens it actually finds,
against `$POLYTROPOS_ROOT/data/pricing.codex.json`. Never quote a price, a model id,
or a plan limit from memory — everything comes from that file at run time.

## Determine the billing mode FIRST

How the user pays decides which framing leads — establish it before presenting any figure:

- **ChatGPT sign-in ⇒ subscription framing.** Codex draws down opaque usage limits, not
  dollars. Any dollar figure the engine prints is a labeled API-equivalent relative-burn
  proxy — a routing aid, never a bill. Lead with the burn shape (which model dominated, how
  concentrated the spend is), and always relay the engine's proxy disclaimer verbatim.
- **`OPENAI_API_KEY` auth ⇒ API framing.** The token-metered dollars the engine reports are
  real and authoritative.
- If unsure which mode applies, ask before presenting figures as either.

## Relay the honesty ladder faithfully

The engine reports one of three branches — present exactly the branch it returns, never
upgrade or downgrade it:

1. **Tokens found** → a per-model table (rollouts, input/cache-read/output tokens, USD) plus
   the standing disclaimer the engine prints: figures are API-equivalent dollars, a
   relative-burn proxy; subscription usage is usage-limited, not token-billed. Multi-model
   rollouts are flagged `≈` — the whole token count is attributed to the last model seen in
   that file; never fabricate a per-model split.
2. **Activity but no tokens anywhere** → counts only (sessions, records, models seen),
   unpriced, and say so plainly — no dollar figure at all.
3. **Nothing found** (no `session_index.jsonl`, `history.jsonl`, or `sessions/` dir) → say the
   logs are empty. Never fabricate or zero-fill a dollar figure in any branch.

Malformed lines and unpriced models (not in the pricing data) are called out, never silently
dropped.

## Summarize, don't dump

1. **Headline**: total priced estimate (or the unpriced-activity count) over the window, and
   which model dominated.
2. **By-model table**: as emitted by the engine.
3. **One actionable recommendation** — e.g. a tier or effort change — grounded in what the
   table actually shows (which model burned the most, whether cheap-tier work is running on a
   pricier model).

Present real dollars as a bill only under `OPENAI_API_KEY`-metered use; under a ChatGPT plan,
every dollar figure stays labeled as the proxy it is.

The root proof above applies before the usage command.
