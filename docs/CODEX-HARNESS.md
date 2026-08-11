# The Codex harness

A guide to the OpenAI Codex CLI side of this monorepo: the same per-task model routing and
cost-awareness this plugin gives Claude Code, ported to Codex's own prompt/config mechanics.

---

## What this is

This repo now has three independent surfaces:

- **Repo root** — the Claude Code plugin (`.claude-plugin/`, `skills/`, `bin/`), live-installed
  via the local marketplace. Unchanged by this work.
- **`copilot/`** — the GitHub Copilot harness bundle (see
  [docs/COPILOT-HARNESS.md](COPILOT-HARNESS.md)).
- **`codex/`** — the Codex harness bundle: `AGENTS.md` (Codex's global instructions surface) plus
  a `prompts/` directory of custom prompts (`route`, `architect`, `implementer`, `verifier`,
  `reviewer`), invoked as `/name` inside the Codex TUI. Codex has no per-prompt model pin and no
  custom-agent files, so role→model mapping lives in data and in the execute driver instead of in
  the prompt bodies.
- **Shared core** — `data/` holds three pricing files that never merge (`pricing.json` for Claude
  Code, `pricing.copilot.json` for Copilot, `pricing.codex.json` for Codex); `bin/codex_pricing.py`
  is the Codex-side cost engine; `bin/harness_select.py` detects which harness(es) are on `PATH`
  and materializes the right bundle into the right home.

## Install into Codex CLI

```bash
python3 bin/harness_select.py detect
python3 bin/harness_select.py install --harness codex
```

`detect` reports whether `claude`, `copilot`, and `codex` are on `PATH` and prints the right next
step for each. `install --harness codex` copies every `codex/prompts/*.md` file into
`<home>/prompts/<same name>`, rewriting every `{{POLYTROPOS_ROOT}}` placeholder to this
repo's absolute path — Codex prompts are read as plain files, so the placeholder is resolved at
install time, the same mechanism the Copilot side uses. The default home is `~/.codex`; override
it with `--codex-home <dir>`. Add `--dry-run` to see the destination paths without writing
anything.

**AGENTS.md no-clobber rule:** `codex/AGENTS.md` installs to `<home>/AGENTS.md`, but that file may
already hold the user's own global Codex instructions — unlike Copilot's per-file `agents/`
directory, Codex's `AGENTS.md` is a single shared file. The installer writes it if absent, reports
"up to date" if an existing copy is byte-identical, and — if a differing copy already exists —
**never overwrites it**; it skips the file and prints an instruction to merge
`codex/AGENTS.md` in by hand. The installer never touches `config.toml`; if you want a persistent
`model =` default or a `[profiles.*]` pin, add those lines yourself using the ids/rates from
`codex_pricing.py models`.

## Route a task

Ask the `route` prompt before an expensive run, the same way you'd ask this plugin's `/route`
skill or the Copilot bundle's `route` agent: `/route` inside a Codex CLI session.

The prompt's first job is figuring out **which billing mode you're in** — ChatGPT sign-in
(usage-limited, not token-billed) or `OPENAI_API_KEY` (real dollars) — because the two framings
read very differently. It then classifies the task into a tier (`cheap` / `mid` / `strong` /
`frontier`; `strong` is currently unpopulated and resolves up to `frontier`), estimates cost or
burn for 2-3 candidates, and returns a compact table plus the one command to act on it.

There are six ways to act on a recommendation:

| Mechanism | How |
|---|---|
| One-shot dispatch | `codex exec "<task>" --model <model-id>` (add `--full-auto` when it must edit files) |
| Interactive switch | `/model` picker in the Codex TUI |
| Session start | `codex --model <model-id>` |
| Persistent default | `model = "<model-id>"` in `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`) |
| Named profile | `[profiles.<name>]` in `config.toml`, used via `codex --profile <name>` |
| Reasoning effort | `-c model_reasoning_effort=<minimal\|low\|medium\|high\|max>` (`max` is new with GPT-5.6) |

Speed levers worth knowing about: the cheap tier (Luna) is the low-latency lane; Sol also launches
on Cerebras at up to 750 tokens/sec (a speed fact, not a price); Codex **fast mode** exists for
priority processing but its CLI flag is unpublished as of this doc's `cached_date` — check release
notes, nothing here invents one; `max` reasoning effort and `ultra` mode trade speed for depth.

## Pricing: API dollars vs subscription limits

Codex has two disjoint ways to pay, and `codex_pricing.py est` always prints **both**, because
there is no published conversion between them:

- **API mode** (`OPENAI_API_KEY`): the dollar figures below are real and authoritative.
- **Subscription mode** (ChatGPT sign-in): Codex draws down opaque usage/rate limits, not
  dollars. `billed_usd` is always `null`; the same dollar figure appears again labeled
  **"API-equivalent (relative-burn proxy, not a bill)"**, alongside a burn index against the
  cheapest same-profile model on the roster. This is never presented as a bill — it's the only
  published proxy for "how much of my limits did that burn."

GPT-5.6 availability is a **limited preview to a select group of trusted partners** as of the
article this data is transcribed from; whether your ChatGPT plan includes it at all is
unconfirmed. If `/model` doesn't list a GPT-5.6 model, route among what it lists instead.

The table below is a **snapshot of `data/pricing.codex.json`, cached `2026-07-10`** — a
labeled point-in-time reference, not a live source; the file itself is authoritative. Prices are
USD per million tokens (MTok); the cached-in column is computed as input × the cache-read
multiplier (0.1×), not stored separately.

| Tier | Model | $ in/MTok | $ cached-in/MTok | $ out/MTok |
|---|---|---:|---:|---:|
| frontier | `gpt-5.6-sol` | $5.00 | $0.50 | $30.00 |
| mid | `gpt-5.6-terra` | $2.00 | $0.20 | $12.00 |
| cheap | `gpt-5.6-luna` | $0.20 | $0.02 | $1.20 |
| non-routing † | `codex-auto-review` | $1.75 | $0.175 | $14.00 |

† `codex-auto-review` is Codex Desktop's built-in auto-review feature — an observed, non-selectable
id (rollout originator "Codex Desktop") with **no backing model exposed** in the logs. Its rate is
an **assumed** best-effort equal to GPT-5.3-Codex (per the OpenAI pricing table captured
`2026-07-10`), added only so `codex_usage.py` / the daily journal can price it as a labeled
API-equivalent proxy. It is not a routing target — its `non-routing` tier is outside the
`cheap|mid|strong|frontier` vocabulary and is skipped by `resolve_tier`. Correct or remove it if
the true backing model surfaces.

Cache facts (GPT-5.6 and later, generation-wide, not per model): explicit cache breakpoints with a
30-minute minimum cache life; cache **reads** get the 90% discount (0.1× the uncached input rate,
the column above); cache **writes** bill at 1.25× the uncached input rate (an estimate-time
exclusion — `codex_pricing.py est` leaves writes out of its projections, same as the sibling
engines; `codex_usage.py` can't observe writes in the logs either, so it doesn't price them).

**Model ids:** `model_ids_note` in the data file flags the three GPT-5.6 ids as best-effort — the
source article names capability tiers (Sol/Terra/Luna), not id strings. Treat Codex CLI's
`/model` picker as authoritative if it disagrees, and correct ids in `data/pricing.codex.json`
only — never anywhere else.

## Run kits on Codex

`bin/codex_execute.py status|run|review --kit tasks/kits/<slug>` dispatches a kit's tasks to the
Codex CLI, mirroring `bin/copilot_execute.py`'s shape. A task's `model` field may be a concrete
model id from `data/pricing.codex.json` or a tier word (`cheap|mid|strong|frontier`); tier words
resolve to the first model in file order carrying that tier, skipping upward past any empty tier
(today, `strong` resolves to Sol). A failed verify escalates to the next strictly-higher populated
tier, carrying the failure evidence into the re-dispatch; an exhausted ladder marks the task
`blocked`.

Always dry-run first: `run --dry-run` prints the exact `codex exec ... --full-auto ...` argv and
spawns nothing. **A real (non-dry-run) `run`/`review` shells out to the actual `codex` binary,
which calls a model** — it spends the user's real subscription usage limits or API dollars and
hits the network. Treat it with the same care as a real Copilot or Claude dispatch.

## Usage report

`bin/codex_usage.py --days 30 [--codex-home DIR]` reads `~/.codex` strictly read-only —
`session_index.jsonl`, `history.jsonl`, and date-pruned rollout JSONL files under `sessions/`;
never a `*.db`, never a write, never a `codex` invocation.

It follows an honesty ladder: if rollout records carry token-usage fields, it prices them against
`data/pricing.codex.json` and prints a per-model table plus the standing disclaimer, "Figures are
API-equivalent dollars — a relative-burn proxy. Subscription (ChatGPT-plan) usage is usage-limited,
not token-billed." If only session/history activity is present, it reports counts plus the line
"no token usage found in these logs — activity counted, unpriced." If the home or its files are
absent, it says so and exits cleanly. It never fabricates or zeroes a dollar figure to fill a gap.

## Updating Codex prices

1. Edit `data/pricing.codex.json` only — pull fresh numbers from the URL in its own
   `update_from` field.
2. Bump its `cached_date`.
3. Refresh this doc's snapshot table in the *same* change (it's hand-maintained, not generated).
4. Rerun `python3 -m unittest discover -s tests` — `tests/test_codex_bundle.py` and the cost
   engine's regression tests both read this file.

Re-check deliberately once GPT-5.6 exits limited preview: confirm the model ids against `/model`,
confirm whether ChatGPT plans actually include it, and check whether fast mode or `ultra` have
published CLI surfaces or price impacts yet — none of that is guessed here.
