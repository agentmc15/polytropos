# Models and preferences

Vendor names, tier labels, model ids, prices, per-model notes, promotional or long-context
facts, and the reasoning-effort vocabulary are all **data**, not prose. This guide never types
one of those values by hand: every fact you read below comes from `data/pricing.copilot.json`
and the active preference file, rendered fresh into the generated blocks each time this center
is rebuilt. If you find yourself wanting to quote a model id or a price from this page, quote
the generated table instead — the table is the source of truth, this paragraph is not.

## Current preferences

The block below shows the repository's active preference snapshot as of the last `build`: where
a preference file was read from, which tiers carry a pin, which model ids are excluded, and what
each symbolic tier (`cheap`, `mid`, `strong`, `frontier`) currently resolves to and why.

<!-- BEGIN GENERATED: model-preferences -->
Snapshot: `data/pricing.copilot.json` (cached_date 2026-09-24) — pricing sha256 `f29eb145cfcdd05fb649caff9b02acda832bdb20e880342d7e3c0fa3308ba6b4`, roster sha256 `51b4cbb450cc300e151098004ff738ff651882c40bddd867a5a90295ad7465c2`.

- Prefs source: `(none — defaults)`

- No pins active.

- No excludes active.

| Tier | Resolves to | Via |
|---|---|---|
| mid | `gemini-3.8-flash` | roster-default |
| strong | `gpt-6-sol` | roster-default |
<!-- END GENERATED: model-preferences -->

## How tier resolution works

Every skill, agent, and kit task in this bundle refers to a model only by a symbolic tier, never
by a literal model id. A tier resolves to an actual model id through the preference engine in
this order: an explicit pin for that tier wins first; otherwise the tier's own default roster
entry is used, as long as that entry is not on the exclude list; if the tier's only candidate is
excluded, that tier has no resolution and any attempt to use it is a hard configuration error
rather than a silent fallback to a different tier.

A **pin** forces one tier to resolve to a specific model id regardless of that tier's default —
this is how a "cross-tier override" works: nothing stops a pin from pointing a tier at a model
that would otherwise be classified under a different tier elsewhere in the roster. An **exclude**
is different in kind: it does not choose a replacement for anything, it only removes a model id
from eligibility everywhere tier resolution happens. An excluded model id can still appear as a
labeled, data-derived row in the roster table below — that is disclosure, not a recommendation.
**Excluded rows are informational only and are never eligible to be selected, recommended, or
pinned by anything in this repository.**

## Model roster

Every model currently defined in the pricing data, in file order, with its vendor, tier, base
per-million-token rates, any notes the pricing data itself carries, and whether it is currently
eligible or excluded under active preferences.

<!-- BEGIN GENERATED: model-roster -->
Snapshot: `data/pricing.copilot.json` (cached_date 2026-09-24) — pricing sha256 `f29eb145cfcdd05fb649caff9b02acda832bdb20e880342d7e3c0fa3308ba6b4`, roster sha256 `51b4cbb450cc300e151098004ff738ff651882c40bddd867a5a90295ad7465c2`.

| Model | Display | Vendor | Tier | Input $/MTok | Cached input $/MTok | Output $/MTok | Notes | Preference |
|---|---|---|---|---|---|---|---|---|
| `gpt-6-astra` | GPT-6 Astra | openai | frontier | 10.0 | 1.0 | 50.0 | Current default frontier lane. Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. GitHub lists base and >272K single-request rates. | eligible |
| `claude-fable-5.1` | Claude Fable 5.1 | anthropic | frontier | 10.0 | 0.25 | 50.0 | Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. GitHub documents default Anthropic retention for Fable requests, so it is an opt-in frontier alternative rather than the no-preference default. | eligible |
| `claude-fable-5` | Claude Fable 5 | anthropic | frontier | 10.0 | 1.0 | 50.0 | Earlier Fable frontier alternative. GitHub documents default Anthropic retention for Fable requests; use only when that policy is acceptable. GPT-6 Astra leads the no-preference frontier lane. | eligible |
| `gpt-6-sol` | GPT-6 Sol | openai | strong | 2.0 | 0.2 | 10.0 | Current default strong lane. Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. GitHub lists base and >272K single-request rates. | eligible |
| `claude-opus-5.5` | Claude Opus 5.5 | anthropic | strong | 4.0 | 0.2 | 20.0 | Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. Current Anthropic strong alternative at lower published rates than prior Opus entries. | eligible |
| `claude-opus-4.8` | Claude Opus 4.8 | anthropic | strong | 5.0 | 0.5 | 25.0 | GitHub-listed Anthropic strong alternative. The active strong default is GPT-6 Sol; route by the current tier order and account availability. | eligible |
| `claude-opus-4.7` | Claude Opus 4.7 | anthropic | strong | 5.0 | 0.5 | 25.0 | Scheduled to retire 2026-10-02; GitHub recommends Claude Opus 5. Keep only for compatibility while the provider still lists it. | eligible |
| `gpt-5.5` | GPT-5.5 | openai | strong | 5.0 | 0.5 | 30.0 | OpenAI powerful alternative; step-up rates above 272K input tokens. GPT-6 Sol is the current strong default. | eligible |
| `gpt-5.3-codex` | GPT-5.3-Codex | openai | strong | 1.75 | 0.175 | 14.0 | Coding-focused OpenAI strong alternative; its active status and pricing are confirmed by GitHub's current catalog. | eligible |
| `claude-opus-4.8-fast` | Claude Opus 4.8 (fast mode) | anthropic | strong | 10.0 | 1.0 | 50.0 | Preview fast mode with GitHub-listed $10/$1/$12.50/$50 per-MTok rates. Select it only when its latency tradeoff is appropriate for the task. | eligible |
| `gemini-3.8-flash` | Gemini 3.8 Flash | google | mid | 0.75 | 0.075 | 3.75 | Current default mid lane. Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. | eligible |
| `claude-sonnet-5` | Claude Sonnet 5 | anthropic | mid | 2.0 | 0.2 | 10.0 | Current Anthropic versatile alternative for day-to-day coding, tests, docs, and refactors. | eligible |
| `gpt-5.4` | GPT-5.4 | openai | mid | 2.5 | 0.25 | 15.0 | OpenAI workhorse; step-up rates above 272K input tokens. | eligible |
| `gemini-3.5-flash` | Gemini 3.5 Flash | google | mid | 1.5 | 0.15 | 9.0 | Scheduled to retire 2026-10-02; GitHub recommends Gemini 3.8 Flash. Retained only while the provider still lists it. | eligible |
| `kimi-k2.7-code` | Kimi K2.7 Code | moonshot | mid | 0.95 | 0.19 | 4.0 | Scheduled to retire 2026-10-02; GitHub recommends Kimi K3. Retained only while the provider still lists it. | eligible |
| `gpt-6-luna` | GPT-6 Luna | openai | cheap | 0.1 | 0.01 | 0.5 | Current default cheap lane. Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. GitHub lists base and >272K single-request rates. | eligible |
| `mai-code-1.1-flash` | MAI-Code-1.1-Flash | microsoft | cheap | 0.2 | 0.02 | 1.2 | Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. Replaces retired MAI-Code-1-Flash. | eligible |
| `claude-haiku-4.5` | Claude Haiku 4.5 | anthropic | cheap | 1.0 | 0.1 | 5.0 | GitHub-listed Anthropic lightweight alternative for classification, extraction, formatting, and bulk work. | eligible |
| `gpt-5-mini` | GPT-5 mini | openai | cheap | 0.25 | 0.025 | 2.0 | GitHub-listed OpenAI lightweight alternative for lookups and bulk work. GPT-6 Luna currently has the lowest active input rate. | eligible |
| `gpt-5.4-mini` | GPT-5.4 mini | openai | cheap | 0.75 | 0.075 | 4.5 | Lightweight OpenAI model. | eligible |
| `gpt-5.6-sol` | GPT-5.6 Sol | openai | strong | 4.0 | 0.4 | 20.0 | OpenAI powerful alternative. GitHub's current pricing page confirms base and >272K single-request rates. | eligible |
| `gpt-5.6-terra` | GPT-5.6 Terra | openai | mid | 2.0 | 0.2 | 12.0 | Balanced OpenAI mid-tier alternative. GitHub's current pricing page confirms base and >272K single-request rates. | eligible |
| `gpt-5.6-luna` | GPT-5.6 Luna | openai | cheap | 0.2 | 0.02 | 1.2 | Affordable OpenAI alternative. GitHub's current pricing page confirms base and >200K single-request rates; the lower threshold applies to one request, not cumulative session totals. | eligible |
| `claude-opus-5` | Claude Opus 5 | anthropic | strong | 5.0 | 0.5 | 25.0 | GitHub-listed strong Anthropic alternative. Current official pricing confirms this row. | eligible |
| `gemini-3.6-flash` | Gemini 3.6 Flash | google | mid | 0.75 | 0.075 | 3.75 | Scheduled to retire 2026-10-02; GitHub recommends Gemini 3.8 Flash. GitHub's current promotional pricing is published through 2026-12-31; retain this row only while the provider still lists it. | eligible |
| `grok-4.6` | Grok 4.6 | xai | strong | 2.0 | 0.5 | 6.0 | GitHub's current pricing page confirms base and >200K single-request rates. Grok 4.7 is the newer current alternative. | eligible |
| `gemini-3.7-flash` | Gemini 3.7 Flash | google | mid | 0.75 | 0.075 | 3.75 | GitHub's current pricing page confirms this promotional row; Gemini 3.8 Flash is the newer current alternative. | eligible |
| `grok-4.7` | Grok 4.7 | xai | mid | 2.0 | 0.5 | 6.0 | Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. GitHub lists base and >200K single-request rates. | eligible |
| `kimi-k3` | Kimi K3 | moonshot | strong | 3.0 | 0.3 | 15.0 | Account /model picker and a zero-prompt CLI check confirmed this slug on 2026-09-24. GitHub classifies it as Powerful. | eligible |
<!-- END GENERATED: model-roster -->

## Reading tiers and task fit

Treat the tier column as a coarse difficulty/cost dial, cheapest to most expensive: a lower tier
is the right default for small, mechanical, or well-specified work, and a higher tier earns its
keep only when a task genuinely needs deeper reasoning, broader context synthesis, or judgment
calls that a cheaper model would plausibly get wrong. Do not memorize which literal model id sits
at which tier from this prose — that mapping can and does change as the pricing data is updated.
The **Notes** column in the roster above is the authoritative, runtime source for task fit and any
model-specific caveats (promotional pricing windows, long-context behavior, or anything else the
pricing data itself flags); if this guide's general tier language ever seems to disagree with a
roster row's note, the note wins.

## Reasoning-effort knobs

Some models expose a configurable reasoning-effort control; others do not. The table below is
read directly from the pricing data's own knob facts.

<!-- BEGIN GENERATED: reasoning-knobs -->
Snapshot: `data/pricing.copilot.json` (cached_date 2026-09-24) — pricing sha256 `f29eb145cfcdd05fb649caff9b02acda832bdb20e880342d7e3c0fa3308ba6b4`, roster sha256 `51b4cbb450cc300e151098004ff738ff651882c40bddd867a5a90295ad7465c2`.

| Reasoning effort |
|---|
| Low |
| Medium |
| High |
| Extra High |
| Max |

Display-form ladder, ascending. Copilot CLI v1.0.83 --help and GitHub's CLI command reference confirm headless `--effort=LEVEL` and `--reasoning-effort=LEVEL` flags with low/medium/high/xhigh/max values; this list renders those values in the picker-style display form. The /model picker also supports per-model interactive adjustment with left/right arrows. This repository's copilot_execute.py does NOT yet forward either effort flag, so execution-kit runs cannot select effort through the driver; use a direct Copilot CLI invocation or the picker when effort control is required. Do not infer a model's effort support merely from its appearance in this list.
<!-- END GENERATED: reasoning-knobs -->

Reasoning effort, where it exists, is a **per-model** setting, not a bundle-wide one — two models
at the same tier are not guaranteed to expose the same control or the same vocabulary. In today's
Copilot CLI, the only confirmed way to change it is interactive: open the `/model` picker and use
its arrow-key **Reasoning** setting for the currently selected model. A model whose row above
carries no reasoning-effort entry is one the pricing data itself has identified as offering no
such control — that is a data-driven fact, not a guess. As of this writing, no headless
command-line flag or Copilot settings key for setting reasoning effort is confirmed; do not
script around one that hasn't been verified to exist.

## Task profiles

Cost estimates throughout this center (and the `est`/`models --profile` commands below) are
expressed against a small set of named task-size profiles, each carrying an assumed input- and
output-token count. These are convenience buckets for estimation, not measured telemetry from any
particular task.

<!-- BEGIN GENERATED: task-profiles -->
Snapshot: `data/pricing.copilot.json` (cached_date 2026-09-24) — pricing sha256 `f29eb145cfcdd05fb649caff9b02acda832bdb20e880342d7e3c0fa3308ba6b4`, roster sha256 `51b4cbb450cc300e151098004ff738ff651882c40bddd867a5a90295ad7465c2`.

| Profile | Label | Input tokens | Output tokens |
|---|---|---|---|
| XS | Quick Q&A / one-liner fix | 10000 | 1000 |
| S | Single-file change / small script | 40000 | 4000 |
| M | Feature across a few files | 150000 | 15000 |
| L | Multi-file refactor / large feature | 400000 | 40000 |
| XL | Long-horizon agentic run / migration | 1500000 | 100000 |
<!-- END GENERATED: task-profiles -->

## Runtime commands

Everything above is a rendering of what these commands already report. Run them directly for a
live, personalized view instead of trusting a stale copy of this page:

```bash
python3 bin/copilot_pricing.py prefs
python3 bin/copilot_pricing.py models --json
python3 bin/copilot_pricing.py models --profile <PROFILE>
python3 bin/copilot_pricing.py est <PROFILE> <MODEL_ID>
python3 bin/copilot_pricing.py knobs
```

Replace `<PROFILE>` with one of the profile keys from the task-profiles table above and
`<MODEL_ID>` with one of the model ids from the roster table above.

## Pricing and AIC implications

A model's **output** rate (and, where applicable, its reasoning-token behavior) typically
dominates total cost far more than its input rate does — a task with a small prompt but a long,
reasoning-heavy response can cost more than a task with a large prompt and a short response.
Long-context step-ups and promotional-pricing windows are never asserted in this guide's prose;
they are evaluated by the pricing engine itself from the pricing data, and any such warning that
applies to a given estimate is surfaced by the engine at estimate time, not predicted here.
Pinning a tier to a particular model id changes *which* model that tier dispatches — it does not
change that model's own rates. A pinned tier is always priced at the pinned model's own rates in
the pricing data, exactly like any other selection of that same model id.

## Refresh and drift

This page's generated blocks, and every number in them, come from `data/pricing.copilot.json`
and the active preference file at the moment `bin/copilot_docs.py build` last ran. If a model's
rate, tier, notes, or roster order change, or the pricing file's own cached date moves, edit
`data/pricing.copilot.json` — and only that file — as the single numeric source of truth, bump
its cached date there, then rebuild this center and re-verify:

```bash
python3 bin/copilot_docs.py build
python3 bin/copilot_docs.py check
python3 -m unittest discover -s tests
```

Never hand-edit the generated tables above to "fix" a stale value — a hand-edit does not survive
the next `build`, and `check` will detect the resulting drift and fail on purpose. The generated
blocks are the only place a live model id, rate, date, or ratio may legitimately appear on this
page.
