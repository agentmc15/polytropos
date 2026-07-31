# The Copilot harness

A guide to the GitHub Copilot CLI side of this monorepo: the same per-task model routing and
cost-awareness this plugin gives Claude Code, ported to Copilot's own agent/model mechanics.

See [../copilot-docs/README.md](../copilot-docs/README.md) ([HTML](../copilot-docs/index.html)) for the task-oriented user guide to this harness.

---

## What this is

This repo now has two independent surfaces:

- **Repo root** — the Claude Code plugin (`.claude-plugin/`, `skills/`, `bin/`), live-installed
  via the local marketplace. Unchanged by this work.
- **`copilot/`** — the Copilot harness bundle: `aesop.yaml` (the manifest, source of truth for
  what the bundle contains) plus a `.github/` tree of native Copilot config files. Both are
  hand-authored in the formats aesop's (`github:agentmc15/aesop`) Copilot emitter produces as of
  commit `5506617` — `aesop compile` is never run in this repo; `tests/test_copilot_bundle.py`
  enforces that the manifest and the bundle stay consistent by hand.
- **Shared core** — `data/` holds two pricing files that never merge (`pricing.json` for Claude
  Code, `pricing.copilot.json` for Copilot); `bin/copilot_pricing.py` is the cost engine both the
  bundle's agent and this doc read; `bin/harness_select.py` detects which harness(es) are on
  `PATH` and materializes the Copilot bundle into a Copilot home.

## Install into Copilot CLI

```bash
python3 bin/harness_select.py detect
python3 bin/harness_select.py install --harness copilot
```

`detect` reports whether `claude` and `copilot` are on `PATH` and prints the right next step for
each. `install --harness copilot` copies every `copilot/.github/agents/*.agent.md` file into
`<home>/agents/`, rewriting every `{{POLYTROPOS_ROOT}}` placeholder to this repo's absolute
path along the way — Copilot has no `${CLAUDE_PLUGIN_ROOT}`-style runtime variable, so the
placeholder has to be resolved at install time instead of read at run time. The default home is
`~/.copilot`; override it with `--copilot-home <dir>`. Add `--dry-run` to see the destination
paths without writing anything.

**Precedence gotcha:** an agent under `~/.copilot/agents/` overrides a same-named agent defined
at the repo level, so a stale installed copy of `route.agent.md` silently shadows an updated one
in `copilot/.github/agents/` until you reinstall.

A repo can also adopt the bundle without the installer, by copying `copilot/.github/` into itself
directly — useful if you want the config checked into a project rather than materialized into a
personal Copilot home.

## Route a task

Ask the `route` agent before an expensive run, the same way you'd ask this plugin's `/route`
skill. Two ways to invoke it:

- Interactive: `/agent` inside a Copilot CLI session, then pick `route`.
- One-shot: `copilot --agent route --prompt "<task description>"`.

It classifies the task into a tier (`cheap` / `mid` / `strong` / `frontier`), estimates cost for
2-3 candidate models across vendors, and returns a compact table — candidates, USD, AI Credits,
one-line rationale each, the recommendation bolded — followed by the single command to act on it.

There are five ways to act on a recommendation:

| Mechanism | How |
|---|---|
| One-shot dispatch | `copilot -p "<task>" --model <model-id>` |
| Interactive switch | `/model` inside a session (policy-disabled models prompt to enable) |
| Session default | `COPILOT_MODEL=<model-id>` environment variable |
| Persistent default | `"model"` key in `~/.copilot/settings.json` (or `$COPILOT_HOME/settings.json`) |
| Per-agent pin | `model:` frontmatter in a `.github/agents/*.agent.md` or `~/.copilot/agents/*.agent.md` file |

## Pricing: AI Credits

Copilot bills all model usage — input, cached input, output; Anthropic models also bill cache
writes — in **AI Credits (AIC)**, at a fixed USD rate encoded as `billing_unit.usd_per_credit`
in `data/pricing.copilot.json`. Code completions and next-edit suggestions are not billed in AIC.

Paid individual plans match their subscription price to a base AIC allowance 1:1, plus a flex
allotment GitHub can rebalance: `pro` ($10/mo → 1,500 AIC), `pro-plus` ($39/mo → 7,000 AIC),
`max` ($200/mo → 20,000 AIC) each carry a fixed `included_aic_per_month` in the data file; `free`
has a small variable allowance; `business` and `enterprise` pool AIC at the org level instead of a
fixed per-seat number. (Recall 1 AIC = `usd_per_credit`, i.e. one cent.)

The table below is a **snapshot of `data/pricing.copilot.json`, cached `2026-07-25`** — treat it
as a labeled point-in-time reference, not a live source; the file itself is authoritative. Prices
are USD per million tokens (MTok).

**24 rows, re-verified 2026-07-25** against GitHub's models-and-pricing doc: every rate already in
the file matched the doc exactly, and the re-verify added the three GPT-5.6 long-context step-ups
plus two newly-priced models. **Claude Fable 5 remains the sole `frontier` tier.** Four models
GitHub prices but the picker did not list as of the 2026-07-01 check (Gemini 2.5 Pro, Gemini 3
Flash, GPT-5.4 nano, Raptor mini) stay intentionally excluded, as does a plain `Claude Sonnet 4`
the doc prices — picker presence unverified for all five.

> **Read the `picker-unconfirmed` flag literally.** `claude-opus-5` and `gemini-3.6-flash` are
> PRICE-confirmed from the doc but were NOT checked against Copilot CLI's `/model` picker, which
> is this roster's actual membership rule. If `/model` does not offer them, delete them from
> `data/pricing.copilot.json`.

| Tier | Model | Vendor | $ in | $ cached in | $ out | flags |
|---|---|---|---:|---:|---:|---|
| frontier | `claude-fable-5` | anthropic | $10.00 | $1.00 | $50.00 | — |
| strong | `claude-opus-4.8-fast` | anthropic | $10.00 | $1.00 | $50.00 | — |
| strong | `claude-opus-4.5` | anthropic | $5.00 | $0.50 | $25.00 | — |
| strong | `claude-opus-4.6` | anthropic | $5.00 | $0.50 | $25.00 | — |
| strong | `claude-opus-4.7` | anthropic | $5.00 | $0.50 | $25.00 | — |
| strong | `claude-opus-4.8` | anthropic | $5.00 | $0.50 | $25.00 | — |
| strong | `claude-opus-5` | anthropic | $5.00 | $0.50 | $25.00 | **picker-unconfirmed** |
| strong | `gpt-5.5` | openai | $5.00 | $0.50 | $30.00 | long-ctx >272K |
| strong | `gpt-5.6-sol` | openai | $5.00 | $0.50 | $30.00 | long-ctx >272K |
| strong | `gemini-3.1-pro` | google | $2.00 | $0.20 | $12.00 | long-ctx >200K |
| strong | `gpt-5.3-codex` | openai | $1.75 | $0.175 | $14.00 | — |
| mid | `claude-sonnet-4.5` | anthropic | $3.00 | $0.30 | $15.00 | — |
| mid | `claude-sonnet-4.6` | anthropic | $3.00 | $0.30 | $15.00 | — |
| mid | `gpt-5.4` | openai | $2.50 | $0.25 | $15.00 | long-ctx >272K |
| mid | `gpt-5.6-terra` | openai | $2.50 | $0.25 | $15.00 | long-ctx >272K |
| mid | `claude-sonnet-5` | anthropic | $2.00 | $0.20 | $10.00 | promo→2026-08-31 |
| mid | `gemini-3.5-flash` | google | $1.50 | $0.15 | $9.00 | — |
| mid | `gemini-3.6-flash` | google | $1.50 | $0.15 | $7.50 | **picker-unconfirmed** |
| mid | `kimi-k2.7-code` | moonshot | $0.95 | $0.19 | $4.00 | — |
| cheap | `claude-haiku-4.5` | anthropic | $1.00 | $0.10 | $5.00 | — |
| cheap | `gpt-5.6-luna` | openai | $1.00 | $0.10 | $6.00 | long-ctx >200K |
| cheap | `gpt-5.4-mini` | openai | $0.75 | $0.075 | $4.50 | — |
| cheap | `mai-code-1-flash` | microsoft | $0.75 | $0.075 | $4.50 | — |
| cheap | `gpt-5-mini` | openai | $0.25 | $0.025 | $2.00 | — |

Some rows carry caveats the table only flags: `claude-sonnet-5` is at promotional pricing until
its `promo.until` date (the post-promo rate is unpublished); six rows carry `long_context`
step-up rates where **every token above the threshold costs more**, and `gpt-5.6-luna`'s
threshold is 200K — lower than its GPT-5.6 siblings' 272K, so it steps up sooner. `gpt-5.6-sol`'s
cache-write figure comes from the picker's cost panel only; the doc's OpenAI table has no
cache-write column and does not corroborate it. Read the raw file for any of these — this
snapshot does not update itself.

**Model ids:** the roster was last verified against `/model` in Copilot CLI on **2026-07-01** —
the 2026-07-25 refresh re-verified PRICES against the doc but did NOT re-check the picker, so the ids
here are what the CLI actually calls each model. Treat `/model` as authoritative if a future
release disagrees, and correct ids in `data/pricing.copilot.json` only — never anywhere else.

## Updating Copilot prices

1. Edit `data/pricing.copilot.json` only — pull fresh numbers from the URL in its own
   `update_from` field.
2. Bump its `cached_date`.
3. Refresh this doc's snapshot table in the *same* change (it's hand-maintained, not generated).
4. Rerun `python3 -m unittest discover -s tests` — `tests/test_copilot_bundle.py` and the cost
   engine's regression tests both read this file.

Watch the Sonnet 5 `promo.until` date (`2026-08-31`): the post-promo rate isn't published yet, so
that entry needs a deliberate re-check once the promo window closes, not just a rate copy-over.

## Statusline (experimental)

Copilot CLI (added ~May 2026, modeled on Claude Code's statusline) can run a command that
renders a live status line, the Copilot-side parity twin of this plugin's own Claude Code
statusline (`bin/statusline.py`). **Treat this integration as experimental** — Copilot's
payload schema is only partly documented publicly, so `bin/copilot_statusline.py` parses every
field defensively and degrades to a plain fallback line rather than ever crashing.

Enable it inside a Copilot CLI session, then apply the change:

```
/statusline
/restart
```

`/statusline` walks you through pointing Copilot at a command; give it this repo's script by
absolute path. The resulting block in `~/.copilot/settings.json` looks like:

```json
{
  "experimental": true,
  "statusLine": {
    "type": "command",
    "command": "python3 /absolute/path/to/polytropos/bin/copilot_statusline.py"
  }
}
```

(`experimental: true` is Copilot's own gate for this still-evolving feature, not something this
repo adds.) Copilot pipes a JSON payload to the command's stdin on each render; the script
prints one line back, e.g. (a real capture, Copilot CLI v1.0.70):

```
claude-sonnet-5 | 17.7 AIC (~$0.18) | ctx 3% | 25m45s
```

Model name (`model.id`, falling back to a trimmed `model.display_name`), AI Credits (`ai_used.total_nano_aiu / 1e9` — the nano scale
is confirmed, so the USD gloss computed from `data/pricing.copilot.json`'s
`billing_unit.usd_per_credit` is always shown alongside it, never a hardcoded rate),
context-window percentage (`context_window.current_context_used_percentage`), session duration
(`cost.total_duration_ms`), and cache/premium-request counts each render only when the payload
actually carries that field; an empty, invalid, or field-free payload prints a minimal fallback
line instead of crashing. Older/flatter top-level field names are still tried as fallbacks for
schema-drift tolerance.

### `--compact`: complementing Copilot's built-in footer

Copilot CLI also has its own **built-in** statusline footer, toggled independently via
`showCustom`-style widgets in its settings — and that built-in footer already renders model
name, context %, and `Session: N AIC used`. If you run this script's default (full) line
*alongside* that built-in footer, three of its four segments just repeat what Copilot already
shows you.

`--compact` (alias `--slim`) fixes that by printing **only** the segments the built-in footer
doesn't have: the USD value of the session's AIC, and session duration — joined by ` · `, e.g.:

```
~$0.18 · 25m45s
```

It derives both figures via the exact same helpers the full line uses (no re-derivation, no
new pricing lookup path). Degradation is honest, never a placeholder: if the USD figure isn't
derivable but duration is, it prints duration alone; if neither is available, it prints an
**empty line** — the point being that this widget should contribute nothing when it has
nothing to add, rather than a dash or "n/a". The default (no `--compact`) mode is completely
unchanged.

Point `~/.copilot/settings.json`'s command at the `--compact` form to run it alongside the
built-in footer:

```json
{
  "experimental": true,
  "statusLine": {
    "type": "command",
    "command": "python3 /absolute/path/to/polytropos/bin/copilot_statusline.py --compact",
    "showCustom": true
  }
}
```

(Omit `--compact` — i.e. use the plain command from the block above — if you'd rather run this
script standalone, without Copilot's built-in footer, and want the full model/AIC/ctx/duration
line.)

The real payload schema is now pinned from a live capture, but the script still supports the
capture affordance in case it ever drifts:

```bash
python3 bin/copilot_statusline.py --capture /tmp/copilot-statusline-payload.json
# or: --debug   (writes the raw payload to stderr instead of a file)
```

Point `~/.copilot/settings.json`'s command at this form temporarily, trigger a render, then
inspect the captured file to confirm or correct the field names this script assumes — see the
docstring atop `bin/copilot_statusline.py` for the exact key list.

## Phase 2 roadmap

Items 1–3 of the original roadmap are now built — see
[COPILOT-WORKFLOW.md](COPILOT-WORKFLOW.md) for the architect → execute → verify → escalate
workflow (`bin/copilot_execute.py` + the `architect`/`implementer`/`verifier`/`reviewer`
agents), the budget-capped Ralph goal loop (`bin/copilot_ralph.py`), and the vendored
`lessons-loop` skill.

Phase 3 (cost visibility) is now built — see [COPILOT-COSTVIZ.md](COPILOT-COSTVIZ.md) for
`bin/copilot_usage.py` and the pooled-AIC `runway --pool-aic` extension. The aesop compile
round-trip has a written spec ([AESOP-COMPILE-PROPOSAL.md](AESOP-COMPILE-PROPOSAL.md)) to be
executed in aesop's own repo; Ralph per-tick real-cost feedback remains deferred
(`.claude/kits/copilot-costviz/PLAN.md`).
