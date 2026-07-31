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
Snapshot: `data/pricing.copilot.json` (cached_date 2026-07-25) — pricing sha256 `0e787ee9bdb2a76d74689ab5bbba7d8efea12054b6643c764932564f57b67bb1`, roster sha256 `774e2d66ae13ff6a869f7915c264790802b15be56bb03d9e5355aa0d58363b71`.

- Prefs source: `(none — defaults)`

- No pins active.

- No excludes active.

| Tier | Resolves to | Via |
|---|---|---|
| mid | `claude-sonnet-5` | roster-default |
| strong | `claude-opus-4.8` | roster-default |
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
Snapshot: `data/pricing.copilot.json` (cached_date 2026-07-25) — pricing sha256 `0e787ee9bdb2a76d74689ab5bbba7d8efea12054b6643c764932564f57b67bb1`, roster sha256 `774e2d66ae13ff6a869f7915c264790802b15be56bb03d9e5355aa0d58363b71`.

| Model | Display | Vendor | Tier | Input $/MTok | Cached input $/MTok | Output $/MTok | Notes | Preference |
|---|---|---|---|---|---|---|---|---|
| `claude-fable-5` | Claude Fable 5 | anthropic | frontier | 10.0 | 1.0 | 50.0 | The standout model on this roster — the best available, and not close. Sole frontier tier. Reserve it for the hardest work: long-horizon agentic runs, large migrations, and problems a strong-tier model already failed on. Worth its AIC precisely when a strong-tier model would fail. | eligible |
| `claude-opus-4.8` | Claude Opus 4.8 | anthropic | strong | 5.0 | 0.5 | 25.0 | Strongest non-Fable Anthropic model; the default strong-tier pick for multi-file features, hard debugging, architecture, and review. | eligible |
| `claude-opus-4.7` | Claude Opus 4.7 | anthropic | strong | 5.0 | 0.5 | 25.0 | Same published rate as Opus 4.8; kept selectable because /model lists it. Prefer 4.8 for new work. | eligible |
| `claude-opus-4.6` | Claude Opus 4.6 | anthropic | strong | 5.0 | 0.5 | 25.0 | Same published rate as Opus 4.8; kept selectable because /model lists it. Prefer 4.8 for new work. | eligible |
| `claude-opus-4.5` | Claude Opus 4.5 | anthropic | strong | 5.0 | 0.5 | 25.0 | Same published rate as Opus 4.8; kept selectable because /model lists it. Prefer 4.8 for new work. | eligible |
| `gpt-5.5` | GPT-5.5 | openai | strong | 5.0 | 0.5 | 30.0 | OpenAI flagship (Powerful); step-up rates above 272K input tokens. Strong tier — Fable 5 is the sole frontier pick. | eligible |
| `gpt-5.3-codex` | GPT-5.3-Codex | openai | strong | 1.75 | 0.175 | 14.0 | Coding-focused reasoning model; id doc-confirmed. Best value in the strong tier for code work. | eligible |
| `gemini-3.1-pro` | Gemini 3.1 Pro | google | strong | 2.0 | 0.2 | 12.0 | Public preview; step-up rates above 200K input tokens. | eligible |
| `claude-opus-4.8-fast` | Claude Opus 4.8 (fast mode) | anthropic | strong | 10.0 | 1.0 | 50.0 | Preview fast mode: Opus capability at Fable-level prices — you pay 2x for speed, not capability. Pick plain Opus 4.8 unless latency is the constraint. | eligible |
| `claude-sonnet-5` | Claude Sonnet 5 | anthropic | mid | 2.0 | 0.2 | 10.0 | The default mid-tier workhorse and best value on the roster at promo pricing: day-to-day coding, tests, docs, refactors. | eligible |
| `claude-sonnet-4.6` | Claude Sonnet 4.6 | anthropic | mid | 3.0 | 0.3 | 15.0 | Same published rate as Sonnet 4.5. Superseded by promo-priced Sonnet 5 for new work. | eligible |
| `claude-sonnet-4.5` | Claude Sonnet 4.5 | anthropic | mid | 3.0 | 0.3 | 15.0 | Same published rate as Sonnet 4.6. Superseded by promo-priced Sonnet 5 for new work. | eligible |
| `gpt-5.4` | GPT-5.4 | openai | mid | 2.5 | 0.25 | 15.0 | OpenAI workhorse; step-up rates above 272K input tokens. | eligible |
| `gemini-3.5-flash` | Gemini 3.5 Flash | google | mid | 1.5 | 0.15 | 9.0 | Lightweight-class but priced above the cheap lane; routed as mid. | eligible |
| `kimi-k2.7-code` | Kimi K2.7 Code | moonshot | mid | 0.95 | 0.19 | 4.0 | Budget coding model; mid capability at near-cheap prices. | eligible |
| `claude-haiku-4.5` | Claude Haiku 4.5 | anthropic | cheap | 1.0 | 0.1 | 5.0 | id doc-confirmed. Cheapest Anthropic model; classification, extraction, formatting, bulk. | eligible |
| `gpt-5-mini` | GPT-5 mini | openai | cheap | 0.25 | 0.025 | 2.0 | Cheapest input rate on the roster; lightweight lookups and bulk. | eligible |
| `gpt-5.4-mini` | GPT-5.4 mini | openai | cheap | 0.75 | 0.075 | 4.5 | Lightweight OpenAI model. | eligible |
| `mai-code-1-flash` | MAI-Code-1-Flash | microsoft | cheap | 0.75 | 0.075 | 4.5 | Microsoft lightweight coding model. | eligible |
| `gpt-5.6-sol` | GPT-5.6 Sol | openai | strong | 5.0 | 0.5 | 30.0 | OpenAI flagship durable tier (Powerful), GA. Rates captured 2026-07-18 from the /model picker's cost panel ('High cost' — Credits Per 1M Tokens: input 500, output 3,000, cache read 50, cache write 625; converted via billing_unit.usd_per_credit) and re-confirmed 2026-07-25 against the models-and-pricing doc, which adds the >272K long-context step-up recorded above. Caveat: that doc's OpenAI table carries NO cache-write column — the 6.25 above comes from the picker's cost panel only, and is the one figure here the doc does not corroborate. Reasoning adjustable in the picker (default Medium; observed up to Extra High). Picker shows 400K context, tab-toggled 1.1M — capability facts, not prices. | eligible |
| `gpt-5.6-terra` | GPT-5.6 Terra | openai | mid | 2.5 | 0.25 | 15.0 | Balanced everyday tier (Versatile), GA; confirmed present in /model 2026-07-18. Rates confirmed from GitHub's Models and pricing doc (captured 2026-07-18; Copilot USD is API pass-through for GPT-5.6 — 250/25/1,500 credits per 1M tokens) and re-confirmed 2026-07-25, which adds the >272K long-context step-up recorded above. Cache writes bill at 1.25x uncached input per the doc (not stored per-model here). Reasoning adjustable in the picker (default Medium); 400K context per the picker. | eligible |
| `gpt-5.6-luna` | GPT-5.6 Luna | openai | cheap | 1.0 | 0.1 | 6.0 | Fast & affordable tier (Lightweight), GA; confirmed present in /model 2026-07-18. Rates confirmed from GitHub's Models and pricing doc (captured 2026-07-18; Copilot USD is API pass-through for GPT-5.6 — 100/10/600 credits per 1M tokens) and re-confirmed 2026-07-25, which adds the >200K long-context step-up recorded above — note the 200K threshold is LOWER than the 272K used by the other GPT-5.6 rows, so long-context rates kick in sooner here. Cache writes bill at 1.25x uncached input per the doc (not stored per-model here). Reasoning adjustable in the picker (default Medium); 328K context per the picker. | eligible |
| `claude-opus-5` | Claude Opus 5 | anthropic | strong | 5.0 | 0.5 | 25.0 | Added 2026-07-25 from the models-and-pricing doc (GA, Powerful). Same published rates as Opus 4.5/4.6/4.7/4.8, so it is a strong-tier peer on price. NOT yet confirmed present in the /model picker — if the picker does not list it, remove it here (this file's roster rule is what /model actually offers). | eligible |
| `gemini-3.6-flash` | Gemini 3.6 Flash | google | mid | 1.5 | 0.15 | 7.5 | Added 2026-07-25 from the models-and-pricing doc (GA, Versatile). Same input/cached rates as Gemini 3.5 Flash but cheaper output, so it strictly dominates 3.5 Flash on price — prefer it where both are available. NOT yet confirmed present in the /model picker; remove here if the picker does not list it. | eligible |
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
Snapshot: `data/pricing.copilot.json` (cached_date 2026-07-25) — pricing sha256 `0e787ee9bdb2a76d74689ab5bbba7d8efea12054b6643c764932564f57b67bb1`, roster sha256 `774e2d66ae13ff6a869f7915c264790802b15be56bb03d9e5355aa0d58363b71`.

| Reasoning effort |
|---|
| Minimal |
| Low |
| Medium |
| High |
| Extra High |
| Max |

Display-form ladder, ascending. Ground truth: the GPT-5.6 announcement (2026-07-18 capture) confirms the token ladder minimal/low/medium/high/xhigh/max ('max' is the new deepest — even more reasoning time than 'xhigh'); Copilot CLI's /model picker renders Title-Case display forms, of which 'Medium' and 'Extra High' were directly observed (2026-07-18 screenshots), mapping to medium and xhigh. The other four display renderings are Title-Case mappings of the confirmed token ladder, not yet observed in the picker — if the picker renders any differently, correct the list HERE (only here). Mechanism: reasoning effort is set INTERACTIVELY in the /model picker with the left/right arrow keys on the selected model row (picker footer: '←/→ reasoning effort'); it is a per-model property — rows showing '—' have no reasoning control (observed: Auto, Claude Sonnet 4.5, Claude Haiku 4.5, Claude Opus 4.5, Kimi K2.7 Code), while every other observed row (GPT-5.6 Sol/Terra/Luna, GPT-5.5, GPT-5.4, GPT-5.3-Codex, GPT-5.4 mini, GPT-5 mini, Gemini 3.1 Pro, Gemini 3.5 Flash, MAI-Code-1-Flash, Claude Sonnet 5/4.6, Claude Opus 4.8/4.7/4.6 incl. fast mode, Claude Fable 5) defaults to 'Medium'; GPT-5.6 Sol was observed cycled up to 'Extra High'. A headless surface is UNCONFIRMED — no copilot -p flag or settings key for reasoning effort is known to exist; do not invent one. If one ships, record it here (only here).
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
Snapshot: `data/pricing.copilot.json` (cached_date 2026-07-25) — pricing sha256 `0e787ee9bdb2a76d74689ab5bbba7d8efea12054b6643c764932564f57b67bb1`, roster sha256 `774e2d66ae13ff6a869f7915c264790802b15be56bb03d9e5355aa0d58363b71`.

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
