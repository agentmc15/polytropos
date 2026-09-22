# The Copilot harness

A guide to the GitHub Copilot CLI side of this monorepo: the same per-task model routing and
cost-awareness this plugin gives Claude Code, ported to Copilot's own agent/model mechanics.

See [../copilot-docs/README.md](../copilot-docs/README.md) ([HTML](../copilot-docs/index.html)) for the task-oriented user guide to this harness.

---

## What this is

This repo now has two independent surfaces:

- **Repo root** — the Claude Code plugin (`.claude-plugin/`, `skills/`, `bin/`), live-installed
  via the local marketplace. Unchanged by this work.
- **`copilot/`** — the Copilot harness bundle: `aesop.toml` (the manifest, source of truth for
  what the bundle contains, in the TOML dialect of aesop's v1 schema) plus a `.github/` tree of
  native Copilot config files. Both are
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

**The installer will not overwrite what it does not own.** Each destination is classified before
anything is written: absent (installed), already identical (left alone), written by this
installer and unchanged since (refreshed — the routine upgrade, no flag needed), or *anything
else*. That last case — a same-named agent you wrote yourself, or your edits to one of ours — is
**preserved**, printed with its reason, and the command exits 2. It used to be overwritten
silently. To take those destinations over anyway, rerun with `--adopt-existing`, which writes
the bundle's version and keeps your prior bytes beside it as `<name>.polytropos-bak`. Ownership
is recorded in `<home>/polytropos/install-manifest.json`; delete it and every destination
becomes unowned again.

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

The table below is a **snapshot of `data/pricing.copilot.json`, cached `2026-09-05`** — treat it
as a labeled point-in-time reference, not a live source; the file itself is authoritative. Prices
are USD per million tokens (MTok).

**26 rows, every cell re-derived from the file at `cached_date` 2026-09-05:** the GPT-5.6 Sol,
Terra, and Luna rows use the values in a user-supplied Codex pricing screenshot. That screenshot
records provenance for the supplied values; it is not independent validation against GitHub's
Copilot pricing page.
**Claude Fable 5 remains the sole `frontier` tier.** Four models
GitHub prices but the picker did not list as of the 2026-07-01 check (Gemini 2.5 Pro, Gemini 3
Flash, GPT-5.4 nano, Raptor mini) stay intentionally excluded, as does a plain `Claude Sonnet 4`
the doc prices — picker presence unverified for all five.

> **Read the `picker-unconfirmed` flag literally.** `claude-opus-5` and `gemini-3.6-flash` are
> PRICE-confirmed from the doc but were NOT checked against Copilot CLI's `/model` picker, which
> is this roster's actual membership rule. If `/model` does not offer them, delete them from
> `data/pricing.copilot.json`.
>
> **`price-unverified` is the mirror image of that.** `grok-4.6` and `gemini-3.7-flash` were added
> to the file for the `goliath` skill from the user's own confirmed `/model` availability, so
> membership is the *confirmed* half for these two; each row's own `notes` field says its pricing
> still needs re-verification against the `update_from` source, so the rates are the unconfirmed
> half. Neither row is named in `model_ids_note` or `pricing_refresh_note` — their provenance
> lives only in their own `notes`, and that is also the only place to correct it.

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
| strong | `gpt-5.6-sol` | openai | $4.00 | $0.40 | $20.00 | long-ctx >272K |
| strong | `gemini-3.1-pro` | google | $2.00 | $0.20 | $12.00 | long-ctx >200K |
| strong | `grok-4.6` | xai | $2.00 | $0.20 | $6.00 | **price-unverified** |
| strong | `gpt-5.3-codex` | openai | $1.75 | $0.175 | $14.00 | — |
| mid | `claude-sonnet-4.5` | anthropic | $3.00 | $0.30 | $15.00 | — |
| mid | `claude-sonnet-4.6` | anthropic | $3.00 | $0.30 | $15.00 | — |
| mid | `gpt-5.4` | openai | $2.50 | $0.25 | $15.00 | long-ctx >272K |
| mid | `gpt-5.6-terra` | openai | $2.00 | $0.20 | $12.00 | long-ctx >272K |
| mid | `claude-sonnet-5` | anthropic | $2.00 | $0.20 | $10.00 | promo→2026-08-31 |
| mid | `gemini-3.5-flash` | google | $1.50 | $0.15 | $9.00 | — |
| mid | `gemini-3.6-flash` | google | $1.50 | $0.15 | $7.50 | **picker-unconfirmed** |
| mid | `kimi-k2.7-code` | moonshot | $0.95 | $0.19 | $4.00 | — |
| mid | `gemini-3.7-flash` | google | $0.75 | $0.075 | $3.75 | **price-unverified** |
| cheap | `claude-haiku-4.5` | anthropic | $1.00 | $0.10 | $5.00 | — |
| cheap | `gpt-5.4-mini` | openai | $0.75 | $0.075 | $4.50 | — |
| cheap | `mai-code-1-flash` | microsoft | $0.75 | $0.075 | $4.50 | — |
| cheap | `gpt-5-mini` | openai | $0.25 | $0.025 | $2.00 | — |
| cheap | `gpt-5.6-luna` | openai | $0.20 | $0.02 | $1.20 | long-ctx >200K |

Some rows carry caveats the table only flags: `claude-sonnet-5`'s rates are promotional and its
`promo.until` date has already passed, with no published post-promo rate behind it (see
[Updating Copilot prices](#updating-copilot-prices)); six rows carry `long_context`
step-up rates where **every token above the threshold costs more**, and `gpt-5.6-luna`'s
threshold is 200K — lower than its GPT-5.6 siblings' 272K, so it steps up sooner. `gpt-5.6-sol`'s
cache-write figure comes from the picker's cost panel only; the doc's OpenAI table has no
cache-write column and does not corroborate it. Read the raw file for any of these — this
snapshot does not update itself.

**Model ids:** the roster was last verified against `/model` in Copilot CLI on **2026-07-01** —
the 2026-07-25 and 2026-09-05 refreshes did NOT re-check the picker, so the ids
here are what the CLI actually calls each model. Treat `/model` as authoritative if a future
release disagrees, and correct ids in `data/pricing.copilot.json` only — never anywhere else.

## Updating Copilot prices

1. Edit `data/pricing.copilot.json` only — pull fresh numbers from the URL in its own
   `update_from` field.
2. Bump its `cached_date`.
3. Refresh this doc's snapshot table in the *same* change (it's hand-maintained, not generated).
4. Rerun `python3 -m unittest discover -s tests` — `tests/test_copilot_bundle.py` and the cost
   engine's regression tests both read this file.

**The Sonnet 5 promo re-check is OWED, not upcoming.** In `data/pricing.copilot.json`,
`models["claude-sonnet-5"].promo.until` is `2026-08-31`, and the `promo.note` beside it still says
the post-promo rate is not yet published and to re-check `update_from` after that date. The file's
own `cached_date` (`2026-09-05`) already postdates the window, so the rates carried for that model
are promotional rates held past their stated end, with the re-check still outstanding — not a
future task. Discharging it means reading `update_from`, then writing the outcome into
`data/pricing.copilot.json`: the rate fields, plus that `promo` block itself (drop it if the
promotion ended, restate `until` if it was extended). Only then is the snapshot table above
re-derived. The correction never lands in this doc on its own — a table edit without a file edit
would be inventing a price.

## Beyond routing: budget mode and `goliath`

Two bundle capabilities are neither routing nor part of the original Phase-2 workflow narrative in
[COPILOT-WORKFLOW.md](COPILOT-WORKFLOW.md). Both are **skill-only** — a
`copilot/.github/skills/<name>/SKILL.md` with no same-named `.agent.md` — so each is invoked as
`/budget` or `/goliath` in a prompt (or auto-loaded when a request matches its `description:`),
never through `copilot --agent`.

### Budget mode — `/budget`, and `run --budget`

Budget mode runs an *existing* kit on a lower dispatch ladder when AI Credits are tight. It moves
where the execute driver dispatches and nothing else — not the kit's scope, not how it verifies,
not how it reviews. The driver surface:

```bash
python3 bin/copilot_execute.py run --kit <dir> --task <id> --budget --dry-run
python3 bin/copilot_execute.py run --kit <dir> --task <id> --budget [--budget-profile M]
python3 bin/copilot_execute.py budget --kit <dir>
```

`--budget` dispatches one tier below the task's pin, with the cheapest tier as the floor — one
rung, never two, and never a rung it invented. `--budget-profile` names which task profile the
cost estimate is figured at; the accepted values are the `task_profiles` keys in
`data/pricing.copilot.json`, and an unknown one exits 2 before anything is dispatched. The
separate `budget --kit <dir>` subcommand reads that kit's `NOTES.md` and totals the runs recorded
there into a ledger plus a verdict; it dispatches nothing and spends nothing.

What budget mode deliberately leaves alone: the verifier, which is already at the floor tier, and
`review`, which takes no budget flag at all and always dispatches the reviewer at its standard
tier. The architect drop is **taught, not enforced** — the driver never dispatches the architect,
so the skill tells you to pick that tier yourself from `python3 bin/copilot_pricing.py models`
rather than from memory, because the roster and its tiers can change underneath you.

The measurement is a labeled estimate over a named task profile, never a bill, and it is allowed
to come back negative: `BACKFIRED` is the driver's own word for a run whose escalations cost more
than its demotion saved. At kit level the headline net covers only `done` runs — blocked runs, and
runs where no demotion was possible, are reported on their own labeled lines instead of being
folded into it. `tests/test_copilot_budget.py` is the enforcement: it pins the
one-tier/floor-cheapest demotion, the rung a demoted task escalates back to, the `NOTES.md` line
shape, and the not-counted and `BACKFIRED` reporting paths.

How the demotion interacts with the escalation ladder inside one `run` is described where that
ladder is: [COPILOT-WORKFLOW.md](COPILOT-WORKFLOW.md#budget-mode).

### `goliath` — a five-role pipeline policy

`copilot/.github/skills/goliath/SKILL.md` is a Copilot-CLI-only orchestration *policy*. The
architect plans first, then five execution roles run — implementer, test-author, verifier,
orchestrator/reviewer, and a mandatory red-team pass — and the work is accepted only when all five
report success against the architect's plan; on failure the exact evidence goes back to the
responsible role and only the failed stage reruns. It ships no driver and no agent of its own: it
is instructions for sequencing dispatches (`copilot -p "<role brief>" --model <resolved-id>`) plus
a reporting contract — a closing ledger naming each role, the model actually used, any fallback
taken, files changed, verify commands and their results, the reviewer decision, and the red-team
findings, and no success claim when a required role could not run.

Its per-role model table lives in the skill as a primary plus an ordered fallback per role, by
display name only; the skill requires resolving each row against
`python3 bin/copilot_pricing.py models` and the live `/model` picker before dispatch, and if every
candidate for a role is unavailable the run stops and names the missing role rather than
substituting another role's model. Two roster rows exist because of this skill: `grok-4.6` and
`gemini-3.7-flash` were added to `data/pricing.copilot.json` for it, which is why both carry the
`price-unverified` caveat in the table above.

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
