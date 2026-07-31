# TASKS — copilot-harness

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the OUT-OF-SCOPE fence, decisions
D1–D8, and the risks/tripwires. Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `copilot-harness-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in parallel;
`depends:` lists hard ordering. Dispatch `copilot-harness-reviewer` at each phase end.

Standing rules for every task: never write outside this repo (that includes `~/.copilot` — any
install run uses `--copilot-home` pointing at a temp dir); never run node/npm/`aesop compile`;
never edit `data/pricing.json`, `.claude-plugin/`, `skills/`, or the completed kits; verify
commands use `python3 -m unittest discover -s tests [-p '<file>.py']` (the dotted-module form is
broken on this machine).

---

## Phase 1 — Copilot pricing data + shared cost engine

### T1 — Create data/pricing.copilot.json
- status: done
- model: haiku
- depends: (none)
- independent: yes

**Brief.** Create `data/pricing.copilot.json` with EXACTLY the content below (byte-for-byte; it
is the architect-pinned transcription of GitHub's models-and-pricing page as of 2026-07-01, with
routing `tier`s pre-assigned per PLAN.md D4). This file becomes the Copilot-side single numeric
source of truth — the sibling of `data/pricing.json`, which you must NOT touch. Do not
reformat, reorder keys, or "fix" values; if anything below looks wrong to you, stop and report
instead of improvising.

```json
{
  "cached_date": "2026-07-01",
  "update_from": "https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing",
  "model_ids_note": "Model ids follow the pattern GitHub's CLI docs show (claude-haiku-4.5, gpt-5.3-codex): lowercase, dots for versions. Only those two ids are doc-confirmed; confirm the rest against /model in Copilot CLI and correct them HERE (only here) if the CLI disagrees.",
  "billing_unit": {
    "name": "AIC",
    "usd_per_credit": 0.01,
    "note": "GitHub AI Credit. All model usage is token-metered (input, cached input, output; Anthropic models also bill cache writes) and settled in AIC. Code completions and next-edit suggestions are not billed in AIC."
  },
  "plans": {
    "free": { "usd_per_month": 0, "included_aic_per_month": null, "note": "Small allowance that varies; see the plans page." },
    "pro": { "usd_per_month": 10, "included_aic_per_month": 1500 },
    "pro-plus": { "usd_per_month": 39, "included_aic_per_month": 7000 },
    "max": { "usd_per_month": 100, "included_aic_per_month": 20000 },
    "business": { "usd_per_month": null, "included_aic_per_month": null, "note": "AIC pooled at the org level; per-seat allowance not fixed here." },
    "enterprise": { "usd_per_month": null, "included_aic_per_month": null, "note": "AIC pooled at the org level; per-seat allowance not fixed here." }
  },
  "plans_note": "Individual paid plans = base credits matched 1:1 to the subscription price plus a flex allotment GitHub can rebalance as model economics change.",
  "models": {
    "claude-fable-5": {
      "display": "Claude Fable 5",
      "vendor": "anthropic",
      "tier": "frontier",
      "input_per_mtok": 10.0,
      "cached_input_per_mtok": 1.0,
      "cache_write_per_mtok": 12.5,
      "output_per_mtok": 50.0,
      "notes": "Most capable Anthropic model on the roster."
    },
    "gpt-5.5": {
      "display": "GPT-5.5",
      "vendor": "openai",
      "tier": "frontier",
      "input_per_mtok": 5.0,
      "cached_input_per_mtok": 0.5,
      "output_per_mtok": 30.0,
      "long_context": { "threshold_tokens": 272000, "input_per_mtok": 10.0, "cached_input_per_mtok": 1.0, "output_per_mtok": 45.0 },
      "notes": "OpenAI flagship; step-up rates above 272K input tokens."
    },
    "claude-opus-4.8": {
      "display": "Claude Opus 4.8",
      "vendor": "anthropic",
      "tier": "strong",
      "input_per_mtok": 5.0,
      "cached_input_per_mtok": 0.5,
      "cache_write_per_mtok": 6.25,
      "output_per_mtok": 25.0,
      "notes": "Same published rate applies to Opus 4.5 / 4.6 / 4.7."
    },
    "claude-opus-4.8-fast": {
      "display": "Claude Opus 4.8 (fast mode)",
      "vendor": "anthropic",
      "tier": "strong",
      "input_per_mtok": 10.0,
      "cached_input_per_mtok": 1.0,
      "cache_write_per_mtok": 12.5,
      "output_per_mtok": 50.0,
      "notes": "Preview fast mode: Opus capability at Fable-level prices — you pay 2x for speed, not capability."
    },
    "gpt-5.3-codex": {
      "display": "GPT-5.3-Codex",
      "vendor": "openai",
      "tier": "strong",
      "input_per_mtok": 1.75,
      "cached_input_per_mtok": 0.175,
      "output_per_mtok": 14.0,
      "notes": "Coding-focused reasoning model; id doc-confirmed."
    },
    "gemini-3.1-pro": {
      "display": "Gemini 3.1 Pro",
      "vendor": "google",
      "tier": "strong",
      "input_per_mtok": 2.0,
      "cached_input_per_mtok": 0.2,
      "output_per_mtok": 12.0,
      "long_context": { "threshold_tokens": 200000, "input_per_mtok": 4.0, "cached_input_per_mtok": 0.4, "output_per_mtok": 18.0 },
      "notes": "Step-up rates above 200K input tokens."
    },
    "claude-sonnet-5": {
      "display": "Claude Sonnet 5",
      "vendor": "anthropic",
      "tier": "mid",
      "input_per_mtok": 2.0,
      "cached_input_per_mtok": 0.2,
      "cache_write_per_mtok": 2.5,
      "output_per_mtok": 10.0,
      "promo": { "until": "2026-08-31", "note": "Promotional pricing; the post-promo rate is not yet published — re-check update_from after this date." },
      "notes": "The cross-vendor workhorse at promo pricing."
    },
    "claude-sonnet-4.6": {
      "display": "Claude Sonnet 4.6",
      "vendor": "anthropic",
      "tier": "mid",
      "input_per_mtok": 3.0,
      "cached_input_per_mtok": 0.3,
      "cache_write_per_mtok": 3.75,
      "output_per_mtok": 15.0,
      "notes": "Same published rate applies to Sonnet 4 / 4.5. Superseded by promo-priced Sonnet 5 for new work."
    },
    "gpt-5.4": {
      "display": "GPT-5.4",
      "vendor": "openai",
      "tier": "mid",
      "input_per_mtok": 2.5,
      "cached_input_per_mtok": 0.25,
      "output_per_mtok": 15.0,
      "long_context": { "threshold_tokens": 272000, "input_per_mtok": 5.0, "cached_input_per_mtok": 0.5, "output_per_mtok": 22.5 },
      "notes": "OpenAI workhorse; step-up rates above 272K input tokens."
    },
    "gemini-2.5-pro": {
      "display": "Gemini 2.5 Pro",
      "vendor": "google",
      "tier": "mid",
      "input_per_mtok": 1.25,
      "cached_input_per_mtok": 0.125,
      "output_per_mtok": 10.0,
      "notes": ""
    },
    "gemini-3.5-flash": {
      "display": "Gemini 3.5 Flash",
      "vendor": "google",
      "tier": "mid",
      "input_per_mtok": 1.5,
      "cached_input_per_mtok": 0.15,
      "output_per_mtok": 9.0,
      "notes": "Newer-generation Flash; priced above the cheap lane, routed as mid."
    },
    "kimi-k2.7-code": {
      "display": "Kimi K2.7 Code",
      "vendor": "moonshot",
      "tier": "mid",
      "input_per_mtok": 0.95,
      "cached_input_per_mtok": 0.19,
      "output_per_mtok": 4.0,
      "notes": "Budget coding model; mid capability at near-cheap prices."
    },
    "claude-haiku-4.5": {
      "display": "Claude Haiku 4.5",
      "vendor": "anthropic",
      "tier": "cheap",
      "input_per_mtok": 1.0,
      "cached_input_per_mtok": 0.1,
      "cache_write_per_mtok": 1.25,
      "output_per_mtok": 5.0,
      "notes": "id doc-confirmed."
    },
    "gpt-5-mini": {
      "display": "GPT-5 mini",
      "vendor": "openai",
      "tier": "cheap",
      "input_per_mtok": 0.25,
      "cached_input_per_mtok": 0.025,
      "output_per_mtok": 2.0,
      "notes": ""
    },
    "gpt-5.4-mini": {
      "display": "GPT-5.4 mini",
      "vendor": "openai",
      "tier": "cheap",
      "input_per_mtok": 0.75,
      "cached_input_per_mtok": 0.075,
      "output_per_mtok": 4.5,
      "notes": ""
    },
    "gpt-5.4-nano": {
      "display": "GPT-5.4 nano",
      "vendor": "openai",
      "tier": "cheap",
      "input_per_mtok": 0.2,
      "cached_input_per_mtok": 0.02,
      "output_per_mtok": 1.25,
      "notes": "Cheapest on the roster."
    },
    "gemini-3-flash": {
      "display": "Gemini 3 Flash",
      "vendor": "google",
      "tier": "cheap",
      "input_per_mtok": 0.5,
      "cached_input_per_mtok": 0.05,
      "output_per_mtok": 3.0,
      "notes": ""
    },
    "raptor-mini": {
      "display": "Raptor mini",
      "vendor": "github",
      "tier": "cheap",
      "input_per_mtok": 0.25,
      "cached_input_per_mtok": 0.025,
      "output_per_mtok": 2.0,
      "notes": "GitHub fine-tuned model."
    },
    "mai-code-1-flash": {
      "display": "MAI-Code-1-Flash",
      "vendor": "microsoft",
      "tier": "cheap",
      "input_per_mtok": 0.75,
      "cached_input_per_mtok": 0.075,
      "output_per_mtok": 4.5,
      "notes": "Microsoft coding model."
    }
  },
  "task_profiles": {
    "XS": { "label": "Quick Q&A / one-liner fix", "input_tokens": 10000, "output_tokens": 1000 },
    "S": { "label": "Single-file change / small script", "input_tokens": 40000, "output_tokens": 4000 },
    "M": { "label": "Feature across a few files", "input_tokens": 150000, "output_tokens": 15000 },
    "L": { "label": "Multi-file refactor / large feature", "input_tokens": 400000, "output_tokens": 40000 },
    "XL": { "label": "Long-horizon agentic run / migration", "input_tokens": 1500000, "output_tokens": 100000 }
  }
}
```

WHY: models are grouped by tier (frontier → cheap) in file order for readability; per-model
`cached_input_per_mtok` is absolute because GitHub publishes absolute cached rates (not one
global multiplier like the Claude file); `task_profiles` duplicates pricing.json's token counts
because they are task-size conventions, not prices, and each file must be self-contained.

**Acceptance.**
- File exists with exactly the pinned content (valid JSON, 19 models, tiers only from
  `frontier|strong|mid|cheap`).
- `data/pricing.json` and everything else in the repo untouched.

**Verify.**
```bash
cd /path/to/polytropos && python3 -c "import json; p=json.load(open('data/pricing.copilot.json')); assert p['billing_unit']['name']=='AIC' and 0<p['billing_unit']['usd_per_credit']<1; ms=p['models']; assert len(ms)==19 and all(m.get('tier') in ('frontier','strong','mid','cheap') and m['input_per_mtok']>0 and m['cached_input_per_mtok']>0 and m['output_per_mtok']>0 and m.get('vendor') for m in ms.values()); assert {'claude-fable-5','gpt-5.5','gemini-3.1-pro','claude-haiku-4.5','kimi-k2.7-code'} <= set(ms); assert set(p['task_profiles'])=={'XS','S','M','L','XL'}; assert p['plans']['pro']['included_aic_per_month']==1500; assert 'promo' in ms['claude-sonnet-5'] and 'long_context' in ms['gpt-5.4']; print('json ok')" && git diff --quiet data/pricing.json && python3 -m unittest discover -s tests && echo 'T1 OK'
```

---

### T2 — Create bin/copilot_pricing.py (shared-core cost engine)
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Per PLAN.md D3/D8: a stdlib-only CLI that turns `data/pricing.copilot.json` into the
numbers the Copilot route agent (T5) and the user need — cost per task in USD **and AIC**, the
cross-vendor roster, and plan runway. Follow the conventions of `bin/aesop_bridge.py` (module
docstring, pure functions that take the pricing dict, `main(argv=None)`, argparse subcommands,
`--json` flags, `KeyError` → stderr message + exit 2). Load the data like the other `bin/`
scripts: path computed from `Path(__file__)` → `data/pricing.copilot.json` (NOT pricing.json).
Nothing in this script may hardcode a price, credit value, plan allowance, or model id — every
number comes from the loaded dict (the AIC conversion uses `billing_unit.usd_per_credit`).

Pure functions (unit-testable; no I/O besides the pricing dict passed in):

- `effective_rates(model, input_tokens) -> tuple[dict, str]` — returns the applicable rate dict
  and which was used: if the model has `long_context` and `input_tokens >
  long_context["threshold_tokens"]`, return the long_context rates and `"long_context"`;
  otherwise the base rates and `"base"`. Rule pinned by PLAN.md (Risks): the step-up applies to
  the WHOLE estimate when the profile crosses the threshold — a deliberate conservative
  simplification; say so in the docstring.
- `est_cost(pricing, profile, model_id, cache_hit=0.8, today=None) -> dict` — returns
  `{"usd": float, "aic": float, "rates_used": "base"|"long_context", "warnings": [str, ...]}`.
  Math: `usd = input_tokens × ((1 − cache_hit) × input_per_mtok + cache_hit ×
  cached_input_per_mtok) / 1e6 + output_tokens / 1e6 × output_per_mtok`, using the effective
  rates; `aic = usd / pricing["billing_unit"]["usd_per_credit"]`. Cache WRITE rates are excluded
  from the estimate (writes are a small fraction of an agentic loop's traffic; parity with the
  Claude-side formula) — docstring must say so. `today` is a `datetime.date` defaulting to
  `date.today()`; if the model has `promo` and `today > promo["until"]`, append warning
  `"promo pricing ended <until> — rates may be stale; re-check update_from"`. Unknown profile or
  model id → `KeyError` whose message lists the valid choices.
- `plan_runway(pricing, plan_id, profile, model_id, cache_hit=0.8, today=None) -> dict` —
  `{"est_aic_per_task": …, "tasks_per_month": floor(included / est_aic),
  "pct_of_allowance": est_aic / included × 100}`. Unknown plan → `KeyError` listing valid plans;
  a plan whose `included_aic_per_month` is null → `KeyError` with message
  `"plan '<id>' has no fixed AIC allowance — see its note in pricing.copilot.json"`.
- `models_table(pricing, profile=None, cache_hit=0.8, today=None) -> list[dict]` — one dict per
  model in file order: `id`, `display`, `vendor`, `tier`, base `input_per_mtok`/
  `cached_input_per_mtok`/`output_per_mtok`, and — when `profile` is given — `est_usd`/`est_aic`
  via `est_cost`.

CLI (subcommands; JSON floats rounded to 4 decimals; human mode prints USD to 4 decimals and AIC
to 1 decimal):

- `models [--profile P] [--cache-hit F] [--json]` — the roster, one aligned line per model
  (tier, id, display, $in/$out per MTok; plus est columns when `--profile` given).
- `est PROFILE MODEL_ID [--cache-hit F] [--json]` — prints the estimate: USD, AIC, a
  `rates: base` or `rates: long_context` line, and any warnings.
- `runway PLAN PROFILE MODEL_ID [--cache-hit F] [--json]` — prints est AIC per task, tasks per
  month the plan's allowance buys, and % of monthly allowance per task.
- Any `KeyError` from the pure functions → its message on stderr, exit 2.

Docstring must state: purpose (Copilot-side cost math for the polytropos monorepo);
`data/pricing.copilot.json` is the single Copilot-side numeric source of truth;
the whole-estimate long-context rule; the cache-write exclusion; nothing here hardcodes a price,
credit value, or model id.

**Acceptance.**
- `python3 bin/copilot_pricing.py models --json` emits a JSON list covering every model key in
  the data file, in file order.
- `python3 bin/copilot_pricing.py est M claude-fable-5` prints positive USD and AIC figures and
  `rates: base`; `est XL gpt-5.5` prints `rates: long_context` (XL input 1.5M > 272K threshold).
- `python3 bin/copilot_pricing.py runway pro M gpt-5-mini` prints tasks-per-month and %.
- Unknown model/profile/plan exits 2 with a message listing valid choices.
- Full suite green; `data/pricing.json` and `data/pricing.copilot.json` untouched.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/copilot_pricing.py models --json | python3 -c "import json,sys; rows=json.load(sys.stdin); p=json.load(open('data/pricing.copilot.json'))['models']; assert [r['id'] for r in rows]==list(p) and all(r['tier'] in ('frontier','strong','mid','cheap') for r in rows); print('models ok')" && python3 bin/copilot_pricing.py est M claude-fable-5 | grep -q 'rates: base' && python3 bin/copilot_pricing.py est XL gpt-5.5 | grep -q 'rates: long_context' && python3 bin/copilot_pricing.py runway pro M gpt-5-mini && ! python3 bin/copilot_pricing.py est M not-a-model 2>/dev/null && python3 -m unittest discover -s tests && git diff --quiet data/pricing.json data/pricing.copilot.json && echo 'T2 OK'
```

---

### T3 — Regression tests for the cost engine
- status: done
- model: sonnet
- depends: T2
- independent: no

**Brief.** Create `tests/test_copilot_pricing.py`, stdlib `unittest` only, following
`tests/test_aesop_bridge.py` conventions: module docstring; `bin/copilot_pricing.py` loaded via
`importlib.util.spec_from_file_location` off a `BIN_DIR` computed from `Path(__file__)`; no
pytest; no wall-clock assertions (always pass `today` explicitly where promo logic is involved).

Build a **synthetic pricing fixture dict** in the module — deliberately fake round numbers so it
never needs updating when real prices change and can't be mistaken for real prices. Include:
`billing_unit` with `usd_per_credit: 0.5` (NOT the real value — proves the code derives the
conversion from data); one plain model (e.g. input 1.0 / cached 0.1 / output 2.0, tier `cheap`);
one model with `long_context` (`threshold_tokens: 100000`, doubled rates) tier `strong`; one
model with `promo` (`until: "2030-01-01"`) and a `cache_write_per_mtok` (which must NOT affect
the estimate); `plans` with one fixed allowance (e.g. 1000) and one `null` allowance; a
`task_profiles` with round counts (e.g. `T`: 100000 in / 10000 out, and a small one below the
long-context threshold).

Test cases (minimum):

1. `est_cost` exact math on the plain model: hand-computed `assertAlmostEqual` for
   `cache_hit=0.8` and `cache_hit=0`; `aic == usd / 0.5` (the fixture's unit, proving no
   hardcoded 0.01).
2. Long-context boundary: profile input exactly at the threshold uses `base`; above it uses
   `long_context` rates for the whole estimate (assert both the number and `rates_used`).
3. `cache_write_per_mtok` present has zero effect on the estimate.
4. Promo warning: `today` after `until` appends the warning; `today` on/before `until` does not.
5. `plan_runway`: `tasks_per_month` is the floor; `pct_of_allowance` matches; null-allowance plan
   raises `KeyError` mentioning the plan id; unknown plan raises `KeyError` listing valid plans.
6. Unknown model and unknown profile raise `KeyError` whose message lists valid choices.
7. `models_table` preserves file order and includes est columns only when `profile` is given.
8. Live-data validation (real `data/pricing.copilot.json`, structure only — NO price literals):
   parses; required top-level keys (`cached_date`, `billing_unit`, `plans`, `models`,
   `task_profiles`) present; every model has `display`, `vendor`, positive `input_per_mtok`/
   `cached_input_per_mtok`/`output_per_mtok`, and `tier` in the four-value vocabulary; every
   `long_context` has a positive `threshold_tokens`; profiles are exactly XS/S/M/L/XL.
9. One CLI smoke test: `main(["models", "--json"])` against the real file, stdout parses as JSON.

**Acceptance.** All new tests pass; full suite green; no real price/credit literals asserted
anywhere; no network; no writes outside temp dirs.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_copilot_pricing.py' -v && python3 -m unittest discover -s tests && echo 'T3 OK'
```

---

*Phase 1 end — dispatch `copilot-harness-reviewer` before starting Phase 2.*

---

## Phase 2 — Copilot config bundle (aesop-manifest-first)

### T4 — Create copilot/aesop.yaml (the manifest source of truth)
- status: done
- model: haiku
- depends: (none)
- independent: yes

**Brief.** Create `copilot/aesop.yaml` with EXACTLY the content below. Per PLAN.md D2 this
manifest is the declarative source of truth for the Copilot harness bundle; the `.github/` files
(T5) are its hand-emitted output pinned to aesop@5506617 formats, and `tests/test_copilot_bundle.py`
(T6) enforces manifest ↔ bundle consistency in place of `aesop compile` (which is never run
here). Create the `copilot/` directory as part of this task. Do not reformat or "improve" the
YAML.

```yaml
# aesop.yaml — source of truth for the polytropos GitHub Copilot harness bundle.
#
# aesop (github:agentmc15/aesop) is the harness-engineering backbone for this side of the
# monorepo. The sibling .github/ tree is this manifest's emitted output, hand-authored in the
# formats aesop's copilot emitter produces as of commit 5506617 (one pinned divergence: agents
# use the .agent.md extension Copilot CLI documents; aesop emits .md — both are accepted by
# GitHub's config reference; reconciling the emitter is a Phase-2 proposal for the aesop repo).
# `aesop compile` is NOT run in this repo; tests/test_copilot_bundle.py enforces that this
# manifest and .github/ stay consistent. Edit the manifest first, then the bundle, then rerun
# the tests.
version: 1
project:
  name: polytropos-copilot
  stack:
    - python3-stdlib
  commands:
    test: python3 -m unittest discover -s tests   # run from the repo root, one level up
  invariants:
    - "Derive every number from `data/pricing.copilot.json` at run time — it is the single source of truth for Copilot-side pricing; never quote prices, credit values, or model ids from memory."
    - "The AIC unit is data (billing_unit.usd_per_credit), not prose."
    - "The Claude Code plugin at the repo root is a separate harness surface: never mix ${CLAUDE_PLUGIN_ROOT} paths into .github/ content, and never point Copilot files at data/pricing.json."
    - "Bundle files reference {{POLYTROPOS_ROOT}}; bin/harness_select.py resolves it to an absolute path at install time. No absolute paths inside copilot/.github/."
harnesses:
  - copilot
pathway:
  profile: token-lean
registries:
  - builtin
primitives:
  instructions:
    blocks:
      - scope: project
        content: |
          ## polytropos (Copilot harness)
          Derive every number from `data/pricing.copilot.json` at run time — it is the single source of truth for Copilot-side pricing; never quote prices, credit values, or model ids from memory.
          Before any expensive run, use the `route` agent to pick the model tier and estimate cost in AIC.
  agents:
    - route
state:
  dir: tasks/
```

**Acceptance.** File exists byte-for-byte as pinned; nothing else changed.

**Verify.**
```bash
cd /path/to/polytropos && grep -q '^version: 1' copilot/aesop.yaml && grep -q '^  - copilot' copilot/aesop.yaml && grep -q '^    - route' copilot/aesop.yaml && grep -qF 'single source of truth for Copilot-side pricing' copilot/aesop.yaml && grep -q '5506617' copilot/aesop.yaml && ! grep -q 'claude-code' copilot/aesop.yaml && echo 'T4 OK'
```

---

### T5 — Author the Copilot bundle: route agent + instructions
- status: done
- model: opus
- depends: T1
- independent: yes

**Brief.** Create two files. They are **runtime behavior for Copilot CLI** (the Copilot
equivalent of this plugin's `route` skill), not documentation — write them as operating
instructions for the model that will execute them. Everything below marked "pinned" must appear
as specified; prose around it is yours, but keep the agent ≤ 90 lines and the instructions file
≤ 25 lines. Neither file may contain an absolute path, a price, a credit value, or a plan
allowance — numbers live in `data/pricing.copilot.json` and are fetched at run time (a gloss
directly beside a field name is acceptable; a standalone literal is not).

**(1) `copilot/.github/agents/route.agent.md`** — frontmatter pinned exactly:

```yaml
---
name: route
description: Pick the right Copilot model for a task and estimate its cost in AI Credits before running it. Use when the user asks which model to use, what a task will cost, whether a cheaper model would do, or how much of their plan allowance a job will burn.
model: claude-sonnet-5
---
```

Body requirements:

- **Data resolution (pinned mechanism):** the agent reads pricing from
  `{{POLYTROPOS_ROOT}}/data/pricing.copilot.json` and prefers shelling to the cost engine:
  `python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py est <PROFILE> <MODEL_ID>` (also
  `models --profile <P>` and `runway <PLAN> <PROFILE> <MODEL_ID>`). State that
  `{{POLYTROPOS_ROOT}}` is resolved to an absolute path when this agent is installed by
  `bin/harness_select.py`; if the placeholder is still literal, tell the user to run the
  installer. Never quote prices, ratios, or the AIC/USD rate from memory — the unit is
  `billing_unit.usd_per_credit` in the data.
- **Classify the task into a tier** (the four-value vocabulary from the data file):
  `cheap` — classification, extraction, formatting, lookups, bulk/boilerplate;
  `mid` — the workhorse lane: day-to-day coding, tests, docs, refactors;
  `strong` — multi-file features, hard debugging, architecture, code review;
  `frontier` — long-horizon agentic runs, large migrations, problems a strong-tier model failed
  on. When in doubt between two tiers, pick the cheaper and name the failure signal that would
  justify upgrading. Within a tier, compare candidates across vendors using the data (the
  `models --profile` table), not vendor loyalty; mention promo/long-context notes the data
  carries (e.g. a `promo.until` date, `long_context` step-up thresholds).
- **Estimate:** pick the closest `task_profiles` size (XS–XL), run the engine for 2–3 candidate
  models, and present USD + AIC per candidate; when the user's plan is known or asked, add
  `runway` output (% of monthly allowance per task). AIC framing: credits are money —
  `usd_per_credit` each.
- **Recommend and tell the user exactly how to act** — pinned action table (these are Copilot
  CLI's real control surfaces; present model ids "as listed by `/model`" since some ids in the
  data are best-effort):
  - one-shot dispatch: `copilot -p "<task>" --model <model-id>`
  - interactive switch: `/model` (policy-disabled models prompt to enable)
  - session default: `COPILOT_MODEL=<model-id>` env var
  - persistent default: `"model"` key in `~/.copilot/settings.json` (or `$COPILOT_HOME/settings.json`)
  - per-agent pin: `model:` frontmatter in a `.github/agents/*.agent.md` / `~/.copilot/agents/*.agent.md` file
- **Output shape:** a short table (candidates, USD, AIC, one-line rationale each, recommendation
  bolded), then the single action command to run. Compact — a decision aid, not a report.

**(2) `copilot/.github/copilot-instructions.md`** — plain markdown, no frontmatter (aesop's
emitted format for Copilot instructions). Must contain, verbatim (backticks included), the
doctrine sentence pinned in T4's manifest block:

```
Derive every number from `data/pricing.copilot.json` at run time — it is the single source of truth for Copilot-side pricing; never quote prices, credit values, or model ids from memory.
```

Plus: one short paragraph saying what this bundle is (the Copilot
harness of the polytropos monorepo; the Claude Code plugin at the repo root is a separate
surface) and one saying to use the `route` agent before expensive runs.

GOTCHAS: the `model: claude-sonnet-5` pin must remain a key in `data/pricing.copilot.json` —
T6's test enforces it; if Copilot CLI later rejects the id string, the fix is coordinated (data
file + this frontmatter), never silent. Do not create any other files (no skills/, no prompts/,
no mcp config — Phase 2 territory).

**Acceptance.**
- Both files exist at the exact paths; frontmatter matches the pin; `{{POLYTROPOS_ROOT}}`
  appears in the agent (data path AND engine command); the five action-table mechanisms all
  present; the doctrine sentence verbatim in copilot-instructions.md; no absolute paths, no
  price/credit literals in either file; agent ≤ 90 lines, instructions ≤ 25 lines.

**Verify.**
```bash
cd /path/to/polytropos && test -f copilot/.github/agents/route.agent.md && test -f copilot/.github/copilot-instructions.md && grep -q '{{POLYTROPOS_ROOT}}/data/pricing.copilot.json' copilot/.github/agents/route.agent.md && grep -q '{{POLYTROPOS_ROOT}}/bin/copilot_pricing.py' copilot/.github/agents/route.agent.md && grep -q 'copilot -p' copilot/.github/agents/route.agent.md && grep -q 'COPILOT_MODEL' copilot/.github/agents/route.agent.md && grep -q '/model' copilot/.github/agents/route.agent.md && grep -q 'settings.json' copilot/.github/agents/route.agent.md && ! grep -rq '/Users/' copilot/.github && python3 -c "import json,re; fm=open('copilot/.github/agents/route.agent.md').read().split('---')[1]; mid=re.search(r'^model:\s*(\S+)',fm,re.M).group(1); assert mid in json.load(open('data/pricing.copilot.json'))['models'], mid; print('model pin ok:', mid)" && grep -qF 'single source of truth for Copilot-side pricing' copilot/.github/copilot-instructions.md && echo 'T5 OK'
```

---

### T6 — Bundle consistency test (the stand-in for `aesop compile`)
- status: done
- model: sonnet
- depends: T1, T4, T5
- independent: no

**Brief.** Create `tests/test_copilot_bundle.py`, stdlib `unittest`. Per PLAN.md D2, this test
IS the enforcement mechanism that `copilot/aesop.yaml` (manifest) and `copilot/.github/`
(bundle) stay consistent, since `aesop compile` is never run here. Parse the YAML as TEXT with a
small helper (stdlib has no YAML parser — do not add one): extract the agent names as the
`- <name>` items following the `agents:` line at its indentation block.

Test cases (minimum):

1. **Manifest sanity:** `copilot/aesop.yaml` exists; contains a `version: 1` line; the
   `harnesses:` block contains `copilot` and nothing else.
2. **Manifest ↔ agents:** the set of agent names extracted from the manifest equals the set of
   `*.agent.md` stems in `copilot/.github/agents/` (stem = filename minus `.agent.md`).
3. **Doctrine sentence sync:** the exact sentence below (backticks included) appears in BOTH
   `copilot/aesop.yaml` and `copilot/.github/copilot-instructions.md` — define it once as a
   module constant:

   ```
   Derive every number from `data/pricing.copilot.json` at run time — it is the single source of truth for Copilot-side pricing; never quote prices, credit values, or model ids from memory.
   ```
4. **Model pin is live:** every `model:` value found in any bundle agent's frontmatter is a key
   of `data/pricing.copilot.json`'s `models`.
5. **Placeholder discipline:** `{{POLYTROPOS_ROOT}}` appears in
   `copilot/.github/agents/route.agent.md`; NO file under `copilot/.github/` contains an
   absolute path (`/Users/` or `/home/`).
6. **Harness separation:** no file under `copilot/.github/` mentions `CLAUDE_PLUGIN_ROOT` or
   `data/pricing.json` (a plain substring check works — `data/pricing.json` is not a substring
   of `data/pricing.copilot.json`).

**Acceptance.** All new tests pass; full suite green; the test reads files only (no writes, no
network); breaking any of the six contracts above by hand-editing a bundle file makes the suite
fail.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v && python3 -m unittest discover -s tests && echo 'T6 OK'
```

---

*Phase 2 end — dispatch `copilot-harness-reviewer` before starting Phase 3.*

---

## Phase 3 — Harness selection

### T7 — Create bin/harness_select.py (detect + install)
- status: done
- model: sonnet
- depends: T5
- independent: no

**Brief.** Per PLAN.md D7: each harness auto-loads its native config, so "selecting the harness"
means detecting what's on PATH and materializing the right bundle. Stdlib only; `bin/`
conventions (docstring, pure functions with injectable roots, `main(argv=None)`, argparse
subcommands, exit 2 on errors).

Module constants: `REPO_ROOT = Path(__file__).resolve().parent.parent`;
`BUNDLE_AGENTS = REPO_ROOT / "copilot" / ".github" / "agents"`;
`PLACEHOLDER = "{{POLYTROPOS_ROOT}}"`.

Functions:

- `detect() -> dict` — `{"claude-code": bool, "copilot": bool}` via
  `shutil.which("claude")` / `shutil.which("copilot")`. No filesystem writes, no reads under
  `~`.
- `install_copilot(home, repo_root=None, dry_run=False) -> list` — `repo_root` defaults to
  `REPO_ROOT`; for every `*.agent.md` under `<repo_root>/copilot/.github/agents/`, read the
  text, replace ALL occurrences of `PLACEHOLDER` with `str(repo_root)`, and write it to
  `<home>/agents/<same filename>` (creating dirs). Returns the list of destination paths (also
  in dry-run, which must write nothing). Missing/empty bundle dir → raise `FileNotFoundError`
  with a message naming the expected path.

CLI:

- `detect [--json]` — human mode prints one line per harness: found/not found plus the action:
  claude-code → `installed live from this repo via the local marketplace — nothing to install`;
  copilot → `run: python3 bin/harness_select.py install --harness copilot` (append
  `--copilot-home <dir>` note: defaults to `~/.copilot`).
- `install --harness {claude-code,copilot} [--copilot-home PATH] [--dry-run]` —
  `claude-code`: print the marketplace message above, write NOTHING, exit 0.
  `copilot`: call `install_copilot` with `--copilot-home` (default `Path.home() / ".copilot"`);
  print one `installed <path>` line per file (or `would install <path>` under `--dry-run`).
- Errors (missing bundle) → message on stderr, exit 2.

Docstring must state: what installing does (copies bundle agents into a Copilot home, resolving
`{{POLYTROPOS_ROOT}}` to this repo's absolute path — the Copilot analogue of the
statusline's absolute-path exception, since Copilot has no `${CLAUDE_PLUGIN_ROOT}`); that
Claude Code needs no install step; and the home-dir precedence gotcha (a `~/.copilot/agents/`
agent overrides a same-named repo-level agent).

EXECUTION GUARDRAIL (repeat of the standing rule — it binds YOU): while implementing and
verifying, only ever run `install --harness copilot` with `--copilot-home` pointing at a fresh
temp directory. Never let it default to the real `~/.copilot`.

**Acceptance.**
- `detect` runs cleanly on this machine and reports both harnesses without writing anything.
- Installing into a temp home materializes `agents/route.agent.md` with every placeholder
  replaced by the absolute repo root; `--dry-run` writes nothing; `--harness claude-code` writes
  nothing and mentions the marketplace.
- Full suite green; no repo files modified.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/harness_select.py detect && H="$(mktemp -d)" && python3 bin/harness_select.py install --harness copilot --dry-run --copilot-home "$H" && test ! -e "$H/agents" && python3 bin/harness_select.py install --harness copilot --copilot-home "$H" && test -f "$H/agents/route.agent.md" && ! grep -q '{{POLYTROPOS_ROOT}}' "$H/agents/route.agent.md" && grep -q "$PWD/data/pricing.copilot.json" "$H/agents/route.agent.md" && python3 bin/harness_select.py install --harness claude-code | grep -qi 'marketplace' && rm -rf "$H" && python3 -m unittest discover -s tests && git diff --quiet -- data && echo 'T7 OK'
```

---

### T8 — Regression tests for harness selection
- status: done
- model: sonnet
- depends: T7
- independent: no

**Brief.** Create `tests/test_harness_select.py`, stdlib `unittest` + `unittest.mock`, loading
`bin/harness_select.py` via the importlib `_load` convention. All installs go to
`tempfile.TemporaryDirectory` homes; nothing may touch the real `~`.

Test cases (minimum):

1. **Placeholder resolution:** build a temp repo_root containing
   `copilot/.github/agents/route.agent.md` with fake content that includes the placeholder twice;
   `install_copilot(home=tmp_home, repo_root=tmp_root)` writes `agents/route.agent.md` under the
   temp home with BOTH occurrences replaced by `str(tmp_root)` and everything else byte-identical.
2. **Dry-run:** returns the same destination list but creates no files/dirs.
3. **Idempotence:** running install twice leaves the same content (overwrite, not append/fail).
4. **Missing bundle:** an empty temp repo_root raises `FileNotFoundError` naming the expected
   bundle path.
5. **detect():** with `mock.patch.object` on the loaded module's `shutil.which` (present/absent
   combinations), the returned dict has exactly the keys `claude-code` and `copilot` with the
   right booleans.
6. **claude-code install path:** `main(["install", "--harness", "claude-code"])` returns/exits
   zero and creates nothing (run it with a temp cwd-independent check: capture stdout, assert
   the marketplace message, and assert a fresh temp home passed via `--copilot-home` stays
   untouched).
7. **Live-tree check:** the REAL `copilot/.github/agents/` contains at least `route.agent.md`
   and its text contains the placeholder (guards against someone committing a resolved bundle).

**Acceptance.** All new tests pass; full suite green; no writes outside temp dirs; the real
`~/.copilot` never read or written.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_harness_select.py' -v && python3 -m unittest discover -s tests && echo 'T8 OK'
```

---

*Phase 3 end — dispatch `copilot-harness-reviewer` before starting Phase 4.*

---

## Phase 4 — Docs + guardrails

### T9 — Write docs/COPILOT-HARNESS.md + README cross-link
- status: done
- model: sonnet
- depends: T1, T5, T7
- independent: yes

**Brief.** Two changes.

**(1) Create `docs/COPILOT-HARNESS.md`** — the user-facing guide for the Copilot side. Tone and
format of `docs/HOW-IT-WORKS.md` (plain markdown, tables where they earn it); 90–150 lines.
Required H2 headings, exactly these six:

1. `## What this is` — the monorepo shape: repo root = the live-installed Claude Code plugin
   (unchanged); `copilot/` = the Copilot harness bundle (`aesop.yaml` manifest +
   `.github/` native files, formats pinned to aesop commit `5506617`); shared core = `data/`
   (two pricing files that never merge) + `bin/copilot_pricing.py` + `bin/harness_select.py`.
2. `## Install into Copilot CLI` — `python3 bin/harness_select.py detect`, then
   `python3 bin/harness_select.py install --harness copilot` (default home `~/.copilot`,
   override `--copilot-home`); what install does (placeholder → absolute path); the home-dir
   precedence gotcha (a `~/.copilot/agents/` agent overrides a same-named repo-level agent);
   note that a repo can instead adopt the bundle by copying `copilot/.github/` into itself.
3. `## Route a task` — invoking the agent (`/agent` in interactive mode, or
   `copilot --agent route --prompt "..."`), what it returns, and the five ways to act on a
   recommendation (one-shot `--model`, `/model`, `COPILOT_MODEL`, settings.json `model` key,
   per-agent `model:` frontmatter).
4. `## Pricing: AI Credits` — the AIC model (unit encoded as
   `billing_unit.usd_per_credit` in the data), token-metered input/cached/output, plan
   allowances, and a compact per-model snapshot table generated from `data/pricing.copilot.json`
   (columns: tier, model, vendor, $ in, $ cached in, $ out per MTok) — the table MUST be labeled
   as a snapshot tied to the file's `cached_date` (2026-07-01), per the repo invariant on
   labeled doc snapshots. Include the model-ids caveat from the data file's `model_ids_note`
   (ids are best-effort; `/model` is authoritative; correct them in the data file only).
5. `## Updating Copilot prices` — edit `data/pricing.copilot.json` only (from its `update_from`
   URL), bump its `cached_date`, refresh this doc's snapshot table in the same change, rerun
   `python3 -m unittest discover -s tests`. Note the Sonnet 5 `promo.until` (2026-08-31)
   re-check.
6. `## Phase 2 roadmap` — 5 one-liners pointing at `.claude/kits/copilot-harness/PLAN.md`'s
   "Phase 2" section: architect/execute port, Ralph goal loop, lessons-loop, aesop compile
   round-trip, cost visibility.

**(2) `README.md`** — the paragraph beginning `**Aesop integration:**` currently ends that
intro block. Insert directly after it, as its own paragraph:
> **GitHub Copilot harness:** [docs/COPILOT-HARNESS.md](docs/COPILOT-HARNESS.md) — the same routing workflow for GitHub Copilot CLI: AI-Credit pricing data in `data/pricing.copilot.json`, a cross-vendor `route` agent in `copilot/`, installed via `bin/harness_select.py`.

If the `**Aesop integration:**` anchor paragraph is not present verbatim, STOP and report.
Change nothing else in README.md.

**Acceptance.** Doc exists with exactly the six H2 headings; snapshot table present and labeled
with the cached date; `5506617` appears; README paragraph inserted verbatim at the anchor; git
diff shows only these two files.

**Verify.**
```bash
cd /path/to/polytropos && grep -q '^## What this is' docs/COPILOT-HARNESS.md && grep -q '^## Install into Copilot CLI' docs/COPILOT-HARNESS.md && grep -q '^## Route a task' docs/COPILOT-HARNESS.md && grep -q '^## Pricing: AI Credits' docs/COPILOT-HARNESS.md && grep -q '^## Updating Copilot prices' docs/COPILOT-HARNESS.md && grep -q '^## Phase 2 roadmap' docs/COPILOT-HARNESS.md && grep -q '2026-07-01' docs/COPILOT-HARNESS.md && grep -q '5506617' docs/COPILOT-HARNESS.md && grep -q 'COPILOT-HARNESS.md' README.md && grep -q 'harness_select.py' README.md && echo 'T9 OK'
```

---

### T10 — CLAUDE.md: Copilot-side invariants
- status: done
- model: haiku
- depends: T1
- independent: yes

**Brief.** Two pinned insertions into the hand-authored `CLAUDE.md` (which must stay
hand-authored — never aesop-compiled). Change nothing else.

**(1)** In `## Invariants`, the first bullet ends with the sentence:
> (`tests/test_pricing_refs.py` fails on drift).

Insert immediately AFTER that bullet, as a NEW top-level bullet:
> - **`data/pricing.copilot.json` is the Copilot-side numeric source of truth** — same rules as pricing.json: never hardcode Copilot prices, credit values, plan allowances, or model IDs into `copilot/` content or scripts; derive them at run time (the AIC unit itself is data: `billing_unit.usd_per_credit`). README/docs Copilot tables are labeled snapshots tied to its `cached_date`. The two pricing files never merge, and neither harness's config reads the other's file; bundle files under `copilot/.github/` reference `{{POLYTROPOS_ROOT}}`, resolved to an absolute path only by `bin/harness_select.py` at install time.

**(2)** In the `## How to run things` code block, insert immediately after the
`python3 bin/cost_report.py --days 30 ...` line this single line (into the EXISTING code block,
comment aligned with the others — do not create a new code block):

```
python3 bin/copilot_pricing.py est M claude-fable-5   # Copilot-side cost estimate (USD + AIC)
```

**Acceptance.** Both insertions present verbatim at the specified anchors; git diff shows only
these two additions in CLAUDE.md.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'pricing.copilot.json` is the Copilot-side numeric source of truth' CLAUDE.md && grep -q 'copilot_pricing.py est M claude-fable-5' CLAUDE.md && grep -q 'POLYTROPOS_ROOT' CLAUDE.md && python3 -m unittest discover -s tests && echo 'T10 OK'
```

---

*Phase 4 end — dispatch `copilot-harness-reviewer` for the final review, then run the overall
"done" check from PLAN.md.*
