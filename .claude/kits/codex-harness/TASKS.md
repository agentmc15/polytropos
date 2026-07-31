# TASKS — codex-harness

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the OUT-OF-SCOPE fence, decisions
D1–D10, and the risks/tripwires. Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `codex-harness-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. Dispatch `codex-harness-reviewer` at each phase end.

Warm-cluster hints: T3 → T4 are strictly serial and share the cost-engine surface (both
`model: sonnet` — one warm implementer may serve both); likewise T11 → T12 (usage reader +
its tests, both `model: sonnet`). T9 → T10 are serial but pinned on different models — do not
warm-cluster them.

Standing rules for every task: NEVER invoke the real `codex` CLI (it spends the user's real
subscription quota / API dollars and hits the network); never read or write the real `~/.codex`
(T1's bounded read-only peek is the ONE exception, for T1 only); any install or usage run
during implementation/verification uses `--codex-home` pointing at a fresh temp dir; never
touch `~/.claude` or `~/.copilot`; never edit `data/pricing.json`, `data/pricing.copilot.json`,
`bin/journal_*.py`, `skills/`, `.claude-plugin/`, the completed kits, or any pre-existing test
file (single sanctioned exception pinned in T7); verify commands use
`python3 -m unittest discover -s tests [-p '<file>.py']` (the dotted-module form is broken on
this machine). Bundle files under `codex/` carry `{{POLYTROPOS_ROOT}}`, never an absolute
path.

---

## Phase 1 — Ground truth: research peek + pricing data + cost engine

### T1 — Sanctioned read-only peek at the real ~/.codex → RESEARCH.md
- status: done
- model: sonnet
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D9 you perform this kit's ONE sanctioned read-only research peek at the
real `~/.codex` and record the findings in `.claude/kits/codex-harness/RESEARCH.md` (a new,
task-owned kit file — NOT `NOTES.md`, which the execute orchestrator owns). Precedent: the
daily-journal kit's D1-sanctioned peek documented in `bin/journal_sources.py` (read lines
~307–336 first — it pins what `session_index.jsonl` and `history.jsonl` exposed on this
machine as of that kit).

Allowed commands — this exact bounded set, nothing more (each read-only; if a path is absent,
record "absent" and move on):

```bash
ls -la ~/.codex | head -40
ls -R ~/.codex/sessions 2>/dev/null | head -60
head -c 2000 ~/.codex/config.toml 2>/dev/null
head -c 2000 ~/.codex/session_index.jsonl 2>/dev/null
head -c 2000 ~/.codex/history.jsonl 2>/dev/null
# newest rollout file only, ONE file, bounded:
F="$(find ~/.codex/sessions -name '*.jsonl' -type f 2>/dev/null | sort | tail -1)"; [ -n "$F" ] && head -c 4000 "$F"
```

HARD LIMITS: never open a `*.db`/SQLite file; never write anything under `~/.codex`; never run
the `codex` binary (not even `codex --help` or `codex login status` — the fence forbids ANY
invocation); do not read more than the byte-bounds above.

Write `RESEARCH.md` with EXACTLY these five H2 sections, recording key NAMES, shapes, and
model-id strings only — journal-style content hygiene: NO prompt text, NO transcript text, NO
thread titles copied into the file (describe fields as e.g. `"text": <free text — not
harvested>`):

1. `## Files present` — what exists directly under `~/.codex` and the `sessions/` layout
   (does it match `YYYY/MM/DD/rollout-*.jsonl`?).
2. `## config.toml` — which top-level keys exist (e.g. `model`, `model_reasoning_effort`,
   `[profiles.*]`) and the literal `model` value string if present (it is a model id, not
   content).
3. `## Rollout record shapes` — for the one sampled rollout file: the record `type` values
   seen (e.g. `session_meta`, `turn_context`, `event_msg`, `response_item`), the wrapper keys
   (`payload`?), and — the key question — whether any token-usage structure exists (e.g.
   `token_count` events carrying `info.total_token_usage` / `last_token_usage` with
   `input_tokens` / `cached_input_tokens` / `output_tokens` / `reasoning_output_tokens`).
   Record the exact key names found; record "no usage fields observed" if none.
4. `## Model ids observed` — every distinct model-id string seen in config.toml or rollout
   records, verbatim. Explicitly state whether any GPT-5.6 id appears and its exact spelling.
5. `## Implications` — 3–6 bullets: which pinned candidates in PLAN.md's "medium confidence"
   list were confirmed/contradicted; whether `codex_usage.py` (T11) will have token data or
   must lean on the honesty ladder's activity branch; whether T2's pinned model ids need the
   substitution (T2 brief explains it).

WHY: T2 (ids), T9 (dispatch-surface notes), and T11 (usage keys) consume this file so the rest
of the kit runs on synthetic fixtures only, and the real `~/.codex` is never touched again.

**Acceptance.**
- `RESEARCH.md` exists with exactly the five H2 sections above; findings are key names/shapes/
  ids only (no prompt/transcript/title text); absences recorded honestly.
- No writes anywhere under `~/.codex`; no `codex` invocation; no `*.db` opened; nothing else
  in the repo changed.

**Verify.**
```bash
cd /path/to/polytropos && test -f .claude/kits/codex-harness/RESEARCH.md && for h in 'Files present' 'config.toml' 'Rollout record shapes' 'Model ids observed' 'Implications'; do grep -q "^## $h" .claude/kits/codex-harness/RESEARCH.md || { echo "missing: $h"; exit 1; }; done && [ "$(grep -c '^## ' .claude/kits/codex-harness/RESEARCH.md)" -eq 5 ] && [ "$(wc -c < .claude/kits/codex-harness/RESEARCH.md)" -lt 12000 ] && git diff --quiet -- data bin tests copilot skills && echo 'T1 OK'
```

---

### T2 — Create data/pricing.codex.json
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Create `data/pricing.codex.json` with EXACTLY the content below, subject to ONE
sanctioned substitution: if T1's `RESEARCH.md` section `## Model ids observed` records
confirmed GPT-5.6 id strings whose spelling differs from the pinned `gpt-5.6-sol` /
`gpt-5.6-terra` / `gpt-5.6-luna`, use the observed spellings as the model keys instead and
rewrite the first sentence of `model_ids_note` to say the ids were confirmed from the local
`~/.codex` on 2026-07-06; report the substitution explicitly. If RESEARCH.md shows no GPT-5.6
ids, use the pinned content byte-for-byte. Do not reformat, reorder keys, or "fix" values —
the per-token rates, cache multipliers, and knob facts are the architect's verbatim
transcription of OpenAI's "Previewing GPT-5.6 Sol" post (2026-06-26); if anything looks wrong,
stop and report instead of improvising.

This file becomes the THIRD numeric source of truth (sibling of `data/pricing.json` and
`data/pricing.copilot.json`, which you must NOT touch). It is for the codex harness only —
never wire it into `bin/journal_*.py` (the journal counts Codex but never prices it, by
design).

```json
{
  "cached_date": "2026-07-06",
  "update_from": "API rates: OpenAI 'Previewing GPT-5.6 Sol' post (2026-06-26); re-check https://platform.openai.com/docs/pricing once GA. Plan prices: https://openai.com/chatgpt/pricing.",
  "model_ids_note": "UNCONFIRMED ids: the article names capability tiers (Sol/Terra/Luna), not id strings. These ids follow the lowercase-dot-version convention precedented by the doc-confirmed gpt-5.3-codex id on the Copilot side. Confirm against Codex CLI's /model picker (or ~/.codex/config.toml / rollout turn_context records) and correct them HERE (only here) if the CLI disagrees. Roster minimal by design: only GPT-5.6 rates are authoritative from the article; add other Codex-selectable models only with captured authoritative rates.",
  "billing_modes": {
    "api": {
      "unit": "USD",
      "note": "Token-metered API pricing (OPENAI_API_KEY auth). The per-model rates below are authoritative for this mode."
    },
    "subscription": {
      "unit": null,
      "usage_limited": true,
      "note": "Codex CLI under a ChatGPT plan (ChatGPT sign-in) draws down opaque usage/rate limits, not dollars. OpenAI publishes no token-to-quota conversion: any dollar figure shown for a subscription run is an API-equivalent relative-burn proxy and must be labeled as such — never presented as a bill. GPT-5.6 plan inclusion is UNCONFIRMED during the limited preview (trusted partners only; broader ChatGPT/Codex/API availability 'soon' per the 2026-06-26 post)."
    }
  },
  "cache_read_multiplier": 0.1,
  "cache_write_multiplier": 1.25,
  "cache_min_life_minutes": 30,
  "cache_note": "GPT-5.6 and later: explicit cache breakpoints with a 30-minute minimum cache life. Cache writes bill at 1.25x the uncached input rate; cache reads get the 90% cached-input discount (0.1x). Cached rates are computed from these multipliers at run time — never stored per model.",
  "plans": {
    "plus": { "usd_per_month": 20, "included_usage": null, "note": "Usage-limited; no published token allowance exists — never fabricate one." },
    "pro": { "usd_per_month": 200, "included_usage": null, "note": "Higher limits than Plus; still no published token allowance." },
    "business": { "usd_per_month": null, "included_usage": null, "note": "Per-seat pricing varies; org-managed limits." },
    "enterprise": { "usd_per_month": null, "included_usage": null, "note": "Custom pricing; org-managed limits." }
  },
  "knobs": {
    "reasoning_efforts": ["minimal", "low", "medium", "high", "max"],
    "reasoning_efforts_note": "'max' (deepest reasoning) is new with GPT-5.6.",
    "modes": {
      "ultra": { "note": "New with GPT-5.6: uses subagents to accelerate complex work. CLI surface and pricing unpublished as of cached_date — no flag or multiplier invented." },
      "fast": { "note": "Codex fast mode: priority processing for time-sensitive work — the published speed lever. CLI surface and pricing impact unpublished as of cached_date — no flag or multiplier invented." }
    }
  },
  "models": {
    "gpt-5.6-sol": {
      "display": "GPT-5.6 Sol",
      "vendor": "openai",
      "tier": "frontier",
      "input_per_mtok": 5.0,
      "output_per_mtok": 30.0,
      "notes": "Flagship / most capable durable tier. Reach for it deliberately: long-horizon agentic runs, hard architecture/debugging, work a mid-tier model failed on. Also launching on Cerebras at up to 750 tokens/sec (a speed fact, not a price)."
    },
    "gpt-5.6-terra": {
      "display": "GPT-5.6 Terra",
      "vendor": "openai",
      "tier": "mid",
      "input_per_mtok": 2.5,
      "output_per_mtok": 15.0,
      "notes": "Balanced everyday tier — competitive with GPT-5.5 at 2x cheaper. The default workhorse: day-to-day coding, tests, docs, refactors."
    },
    "gpt-5.6-luna": {
      "display": "GPT-5.6 Luna",
      "vendor": "openai",
      "tier": "cheap",
      "input_per_mtok": 1.0,
      "output_per_mtok": 6.0,
      "notes": "Fast & affordable tier, lowest cost: classification, extraction, formatting, lookups, bulk — and the cheap speed lever."
    }
  },
  "tier_note": "Tier vocabulary is shared across all three harnesses (cheap|mid|strong|frontier). OpenAI ships three durable tiers, so 'strong' is unpopulated on this roster: tier resolution takes the first model in file order carrying the tier, skipping upward past empty tiers (strong resolves to the frontier model today).",
  "task_profiles": {
    "XS": { "label": "Quick Q&A / one-liner fix", "input_tokens": 10000, "output_tokens": 1000 },
    "S": { "label": "Single-file change / small script", "input_tokens": 40000, "output_tokens": 4000 },
    "M": { "label": "Feature across a few files", "input_tokens": 150000, "output_tokens": 15000 },
    "L": { "label": "Multi-file refactor / large feature", "input_tokens": 400000, "output_tokens": 40000 },
    "XL": { "label": "Long-horizon agentic run / migration", "input_tokens": 1500000, "output_tokens": 100000 }
  }
}
```

WHY the divergences from `pricing.copilot.json` (PLAN.md D2): `billing_modes` replaces
`billing_unit` because OpenAI has two disjoint payment realities and no published conversion;
cache is global multipliers (the article publishes multipliers, not absolute cached rates —
the `pricing.json` style); `plans` allowances are honestly null (usage limits, not token
budgets); `knobs` carries the new capability facts as data so prose never hardcodes them;
`task_profiles` duplicates the XS–XL conventions so the file is self-contained.

**Acceptance.**
- File exists (pinned content, or pinned content + the sanctioned id substitution, reported);
  valid JSON; exactly 3 models; tier set exactly `{frontier, mid, cheap}`; rate pairs by tier:
  frontier 5.0/30.0, mid 2.5/15.0, cheap 1.0/6.0; multipliers 0.1/1.25; min cache life 30;
  all four plans have `included_usage: null`.
- `data/pricing.json`, `data/pricing.copilot.json`, and everything else untouched.

**Verify.**
```bash
cd /path/to/polytropos && python3 -c "
import json; p=json.load(open('data/pricing.codex.json'))
ms=p['models']; assert len(ms)==3
by_tier={m['tier']:(m['input_per_mtok'],m['output_per_mtok']) for m in ms.values()}
assert by_tier=={'frontier':(5.0,30.0),'mid':(2.5,15.0),'cheap':(1.0,6.0)}, by_tier
assert p['cache_read_multiplier']==0.1 and p['cache_write_multiplier']==1.25 and p['cache_min_life_minutes']==30
assert p['billing_modes']['subscription']['unit'] is None and p['billing_modes']['api']['unit']=='USD'
assert all(v['included_usage'] is None for v in p['plans'].values())
assert p['plans']['plus']['usd_per_month']==20 and p['plans']['pro']['usd_per_month']==200
assert set(p['task_profiles'])=={'XS','S','M','L','XL'}
assert 'max' in p['knobs']['reasoning_efforts'] and 'fast' in p['knobs']['modes']
assert all(m['vendor']=='openai' for m in ms.values())
print('json ok')" && git diff --quiet data/pricing.json data/pricing.copilot.json && python3 -m unittest discover -s tests && echo 'T2 OK'
```

---

### T3 — Create bin/codex_pricing.py (cost engine, dual-framing)
- status: done
- model: sonnet
- depends: T2
- independent: no

**Brief.** Per PLAN.md D3/D4/D10: a stdlib-only CLI turning `data/pricing.codex.json` into
routing numbers. Template: `bin/copilot_pricing.py` (read it first — module docstring style,
pure functions taking the pricing dict, `main(argv=None)`, argparse subcommands, `--json`,
`KeyError` → stderr + exit 2). Load via `PRICING_PATH = Path(__file__).resolve().parent.parent
/ "data" / "pricing.codex.json"`. Nothing may hardcode a price, multiplier, plan fact, or
model id — every number comes from the loaded dict. The four-value tier vocabulary
`("cheap", "mid", "strong", "frontier")` is a sanctioned module constant `TIER_ORDER`.

Pure functions:

- `resolve_tier(pricing, tier) -> str` — the D4 rule, pinned: unknown tier word → `KeyError`
  listing `TIER_ORDER`; otherwise return the id of the FIRST model in pricing-file order whose
  `tier` equals the requested tier; if the tier is unpopulated, retry with the next tier UP in
  `TIER_ORDER` (cheap→mid→strong→frontier), repeating as needed; if no populated tier at or
  above the request exists → `KeyError` saying the roster has no model at or above that tier.
  Docstring states this is the shared skip-up rule also implemented by `codex_execute.py`.
- `resolve_model(pricing, model_or_tier) -> str` — if the argument is a key of
  `pricing["models"]` return it; elif it is in `TIER_ORDER` return `resolve_tier(...)`; else
  `KeyError` listing valid model ids and tier words.
- `est_cost(pricing, profile, model_or_tier, cache_hit=0.8) -> dict` — math:
  `usd_api = input_tokens × ((1 − cache_hit) × input_per_mtok + cache_hit × input_per_mtok ×
  cache_read_multiplier) / 1e6 + output_tokens / 1e6 × output_per_mtok`. Cache WRITE costs are
  excluded from estimates (parity with both sibling engines; writes are a small fraction of an
  agentic loop's traffic) — docstring must say so, and must note the write multiplier exists
  in the data for observed-usage pricing (`codex_usage.py`). Returns
  `{"model_id": <resolved>, "usd_api": float, "subscription": {"billed_usd": None,
  "api_equivalent_usd": <same float>, "burn_index_vs_cheapest": float,
  "cheapest_model_id": str}}` where the burn index divides by the minimum same-profile
  `usd_api` across the whole roster (computed here, from data — with today's data the divisor
  is the cheap-tier model, but NEVER reference an id literal in code). Unknown profile →
  `KeyError` listing valid profiles.
- `models_table(pricing, profile=None, cache_hit=0.8) -> list[dict]` — one dict per model in
  file order: `id`, `display`, `vendor`, `tier`, `input_per_mtok`, `output_per_mtok`,
  `cached_input_per_mtok` (COMPUTED: `input_per_mtok × cache_read_multiplier`), and — when
  `profile` given — `est_usd_api` and `burn_index` via `est_cost`.
- `plans_table(pricing) -> list[dict]` — one dict per plan in file order: `id`,
  `usd_per_month`, `included_usage`, `note` (may be absent → None).

CLI (JSON floats rounded to 4 decimals; human mode USD to 4 decimals, burn index to 1):

- `models [--profile P] [--cache-hit F] [--json]` — aligned roster lines (tier, id, display,
  $in/$out per MTok, cached-in in parentheses; est + burn columns when `--profile` given).
- `est PROFILE MODEL_OR_TIER [--cache-hit F] [--json]` — the DUAL FRAMING is mandatory and has
  no mode flag (PLAN.md D3). Human output, pinned shape (three lines + any notes):

  ```
  profile M on gpt-5.6-terra (tier mid), cache_hit=0.8
    api:          $0.5150 (token-metered API billing)
    subscription: not token-billed (usage-limited) — API-equivalent $0.5150 is a relative-burn proxy, not a bill; 2.5x cheapest (gpt-5.6-luna)
  ```

  (Numbers illustrative — compute from data.) JSON output mirrors the `est_cost` dict plus
  `profile` and `cache_hit`. The words "not a bill" and "not token-billed" must appear
  verbatim in the human subscription line.
- `plans [--json]` — plan facts + notes, one line per plan; must not print any invented
  allowance (null renders as `usage-limited (no published allowance)`).
- Any `KeyError` → its message on stderr, exit 2.

Docstring must state: purpose; `data/pricing.codex.json` is the Codex-side single numeric
source of truth (the three pricing files never merge); the D3 dual-framing rule (why
`billed_usd` is null for subscription); the cache-write exclusion; the D4 skip-up tier rule;
that nothing here hardcodes a price, multiplier, or model id; and that this script NEVER
invokes the `codex` CLI.

**Acceptance.**
- `python3 bin/codex_pricing.py models --json` lists every model key in file order with a
  computed `cached_input_per_mtok`.
- `est M <mid-tier-id>` prints the pinned three-line dual framing; `est M strong` resolves via
  the skip-up rule to the frontier model and says so via the resolved id in line 1;
  `est M cheap` shows burn index 1.0.
- `plans` prints four plans, no invented numbers.
- Unknown model/tier/profile exits 2 listing valid choices.
- Full suite green; no pricing file modified.

**Verify.**
```bash
cd /path/to/polytropos && python3 -c "
import json,subprocess,sys
p=json.load(open('data/pricing.codex.json')); ids=list(p['models'])
rows=json.loads(subprocess.run([sys.executable,'bin/codex_pricing.py','models','--json'],capture_output=True,text=True,check=True).stdout)
assert [r['id'] for r in rows]==ids and all(abs(r['cached_input_per_mtok']-r['input_per_mtok']*p['cache_read_multiplier'])<1e-9 for r in rows)
mid=[i for i in ids if p['models'][i]['tier']=='mid'][0]; cheap=[i for i in ids if p['models'][i]['tier']=='cheap'][0]; front=[i for i in ids if p['models'][i]['tier']=='frontier'][0]
out=subprocess.run([sys.executable,'bin/codex_pricing.py','est','M',mid],capture_output=True,text=True,check=True).stdout
assert 'not a bill' in out and 'not token-billed' in out and mid in out
outs=subprocess.run([sys.executable,'bin/codex_pricing.py','est','M','strong'],capture_output=True,text=True,check=True).stdout
assert front in outs, 'skip-up rule failed'
j=json.loads(subprocess.run([sys.executable,'bin/codex_pricing.py','est','M',cheap,'--json'],capture_output=True,text=True,check=True).stdout)
assert j['subscription']['billed_usd'] is None and abs(j['subscription']['burn_index_vs_cheapest']-1.0)<1e-9
print('engine ok')" && python3 bin/codex_pricing.py plans && ! python3 bin/codex_pricing.py est M not-a-model 2>/dev/null && python3 -m unittest discover -s tests && git diff --quiet -- data && echo 'T3 OK'
```

---

### T4 — Regression tests for the cost engine
- status: done
- model: sonnet
- depends: T3
- independent: no

**Brief.** Create `tests/test_codex_pricing.py`, stdlib `unittest` only, following
`tests/test_copilot_pricing.py` conventions: module docstring; `bin/codex_pricing.py` loaded
via `importlib.util.spec_from_file_location` off a `BIN_DIR` from `Path(__file__)`; no
pytest; no network; no writes outside temp dirs.

Build a **synthetic pricing fixture dict** in the module with deliberately fake round numbers
that can never be mistaken for real prices AND that prove nothing is hardcoded:
`cache_read_multiplier: 0.5` and `cache_write_multiplier: 3.0` (NOT the real 0.1/1.25);
four models — one `cheap` (in 2.0 / out 4.0), one `mid` (in 8.0 / out 16.0), one `frontier`
(in 20.0 / out 40.0), and NO `strong` model, PLUS a variant fixture with an empty `mid` tier
(cheap + strong + frontier) to prove the skip-up rule generalizes beyond "strong is empty";
`billing_modes` with subscription unit null; `plans` with one priced plan and one null-priced;
`task_profiles` with round counts (e.g. `T`: 100000 in / 10000 out).

Test cases (minimum):

1. `est_cost` exact math on the cheap model: hand-computed `assertAlmostEqual` for
   `cache_hit=0.8` and `cache_hit=0` — the cached term must use `input × 0.5` (the fixture
   multiplier), proving the real 0.1 is nowhere in code.
2. Cache writes: the fixture's `cache_write_multiplier: 3.0` has zero effect on any estimate.
3. Burn index: cheap model → exactly 1.0; frontier → hand-computed ratio vs cheap;
   `billed_usd` is None in every result; `cheapest_model_id` is the fixture's cheap model.
4. `resolve_tier` skip-up rule on BOTH fixtures: `strong` → frontier id (fixture 1); `mid` →
   strong id (fixture 2); populated tiers resolve to the FIRST file-order model of that tier;
   unknown tier word raises `KeyError` listing the vocabulary; a roster with nothing at or
   above the request raises `KeyError`.
5. `resolve_model` accepts a model id verbatim, a tier word via resolve_tier, and raises
   `KeyError` (message lists both ids and tier words) otherwise.
6. Unknown profile raises `KeyError` listing valid profiles.
7. `models_table` preserves file order; `cached_input_per_mtok` is computed
   (input × fixture multiplier); est columns appear only when `profile` given.
8. `plans_table` returns file order and never invents an allowance (null stays None).
9. Live-data validation (real `data/pricing.codex.json`, STRUCTURE only — no price literals
   beyond none): parses; required top-level keys (`cached_date`, `update_from`,
   `billing_modes`, `cache_read_multiplier`, `cache_write_multiplier`, `plans`, `models`,
   `knobs`, `task_profiles`) present; every model has `display`/`vendor`/positive rates and a
   tier from the four-value vocabulary; `billing_modes.subscription.unit` is null; profiles
   exactly XS/S/M/L/XL.
10. CLI smokes: `main(["models","--json"])` parses as JSON; `main(["est", <profile>,
    <tier word>])` (against the real file, using a tier word so no id literal appears in the
    test) prints the "not a bill" phrase; unknown id exits 2.

**Acceptance.** All new tests pass; full suite green; no real price/multiplier literals
asserted anywhere except structure; every pre-existing test file byte-untouched.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_codex_pricing.py' -v && python3 -m unittest discover -s tests && git diff --quiet -- tests/test_copilot_pricing.py && echo 'T4 OK'
```

---

*Phase 1 end — dispatch `codex-harness-reviewer` before starting Phase 2.*

---

## Phase 2 — Codex config bundle + installer

### T5 — Author codex/AGENTS.md + codex/prompts/route.md
- status: done
- model: opus
- depends: T2
- independent: no

**Brief.** Create the two doctrine-bearing bundle files. They are **runtime behavior for Codex
CLI** (the Codex equivalents of `copilot/.github/copilot-instructions.md` and
`copilot/.github/agents/route.agent.md` — read both as templates), not documentation. Neither
file may contain an absolute path, a price, a multiplier, a plan fact, or a model id — numbers
and ids come from `data/pricing.codex.json` at run time via the engine (a gloss directly
beside a field name is acceptable; a standalone literal is not). Codex reads `AGENTS.md` as
instructions and `prompts/*.md` as custom prompts invoked `/route` in the TUI (PLAN.md config
surface). Placeholder discipline: reference `{{POLYTROPOS_ROOT}}`, resolved only at
install time by `bin/harness_select.py` (T7).

**(1) `codex/AGENTS.md`** — plain markdown, no frontmatter, ≤ 30 lines. Must contain, verbatim
(backticks included), the Codex doctrine sentence:

```
Derive every number from `data/pricing.codex.json` at run time — it is the single source of truth for Codex-side pricing; never quote prices, plan limits, or model ids from memory.
```

Plus: one short paragraph on what this is (the OpenAI Codex harness of the polytropos
monorepo; the Claude Code plugin at the repo root and the Copilot bundle are separate surfaces
with their own pricing files — the three never mix); one paragraph saying to run `/route`
before any expensive run; and one honesty paragraph: under a ChatGPT plan Codex is
usage-limited, not token-billed — dollar figures for subscription runs are labeled
API-equivalent proxies, never bills.

**(2) `codex/prompts/route.md`** — frontmatter EXACTLY this (nothing else in it — Codex custom
prompts have no model pin; PLAN.md D5):

```yaml
---
description: Pick the right Codex model for a task and estimate its burn before running it. Use when unsure which GPT-5.6 tier a task needs, what it will cost (API) or burn (subscription), or how to run it fast.
---
```

Body ≤ 90 lines, requirements:

- **Data resolution (pinned mechanism):** pricing lives at
  `{{POLYTROPOS_ROOT}}/data/pricing.codex.json`; prefer shelling to the engine:
  `python3 {{POLYTROPOS_ROOT}}/bin/codex_pricing.py est <PROFILE> <MODEL_OR_TIER>`
  (also `models --profile <P>` and `plans`). State that `{{POLYTROPOS_ROOT}}` is
  resolved at install time by `bin/harness_select.py`; if the literal placeholder is still
  visible, tell the user to run
  `python3 bin/harness_select.py install --harness codex`. Never quote prices, plan limits,
  or ids from memory.
- **Determine the billing mode FIRST** (PLAN.md D3): ChatGPT sign-in ⇒ subscription framing
  (usage limits — lead with the burn index and the labeled API-equivalent proxy; never present
  a dollar figure as a bill); `OPENAI_API_KEY` auth ⇒ API framing (the dollars are real). If
  unsure, ask. Also: if `/model` does not list a GPT-5.6 model, the plan doesn't have it yet
  (limited preview) — route among what `/model` actually lists and say so.
- **Classify into a tier** (four-value vocabulary): cheap — classification/extraction/
  formatting/lookups/bulk; mid — the workhorse lane: day-to-day coding, tests, docs,
  refactors; strong — multi-file features, hard debugging, architecture, review; frontier —
  long-horizon agentic runs, large migrations, work a lesser tier failed on. Note from the
  data's `tier_note`: this roster ships three durable tiers, `strong` resolves upward. When in
  doubt pick the cheaper tier and name the failure signal that would justify upgrading.
- **Speed guidance** (the user's stated goal — draw facts from the data's `knobs` and model
  notes, never invent): the cheap tier is the low-latency lane; the frontier model's Cerebras
  availability is a speed fact in its notes; Codex **fast mode** exists (priority processing)
  but its CLI surface is unpublished as of the data's `cached_date` — check release notes,
  never invent a flag; `max` reasoning effort and `ultra` mode trade speed for depth — say so
  when recommending them.
- **Estimate:** map to a `task_profiles` size (XS–XL); run the engine for 2–3 candidates
  (and one lane cheaper as sanity check); present per candidate the mode-appropriate framing
  (API $ / burn index + labeled proxy).
- **Action table** (pinned mechanisms; present ids "as listed by `/model`" — data ids are
  best-effort):

  | goal | how |
  | --- | --- |
  | one-shot dispatch | `codex exec "<task>" --model <model-id>` (add `--full-auto` when it must edit files) |
  | interactive switch | `/model` picker in the Codex TUI |
  | session start | `codex --model <model-id>` |
  | persistent default | `model = "<model-id>"` in `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`) |
  | named profile | `[profiles.<name>]` in config.toml, used via `codex --profile <name>` |
  | reasoning effort | `-c model_reasoning_effort=<minimal\|low\|medium\|high\|max>` (`max` is new with GPT-5.6) |

- **Output shape:** a short table (candidates, mode-appropriate figures, one-line rationale,
  recommended row bold), then the single action command. A decision aid, not a report.

GOTCHAS: do not create other files (workflow prompts are T6); do not add `model:` frontmatter
(Codex prompts have none); do not write any absolute path; T8's bundle test will enforce the
doctrine sentence verbatim in AGENTS.md and the placeholder + no-absolute-path rules.

**Acceptance.**
- Both files at exact paths; frontmatter exactly as pinned (route.md) / absent (AGENTS.md);
  doctrine sentence verbatim in AGENTS.md; placeholder appears in route.md (data path AND
  engine command); all six action-table mechanisms present; billing-mode-first and
  "not a bill"-style subscription honesty present; no absolute paths; no price/plan/id
  literals; AGENTS.md ≤ 30 lines, route.md ≤ 100 lines total.

**Verify.**
```bash
cd /path/to/polytropos && test -f codex/AGENTS.md && test -f codex/prompts/route.md && grep -qF 'single source of truth for Codex-side pricing' codex/AGENTS.md && grep -q '{{POLYTROPOS_ROOT}}/data/pricing.codex.json' codex/prompts/route.md && grep -q '{{POLYTROPOS_ROOT}}/bin/codex_pricing.py' codex/prompts/route.md && grep -q 'codex exec' codex/prompts/route.md && grep -q '/model' codex/prompts/route.md && grep -q 'config.toml' codex/prompts/route.md && grep -q 'profiles' codex/prompts/route.md && grep -q 'model_reasoning_effort' codex/prompts/route.md && grep -qi 'not a bill' codex/prompts/route.md && ! grep -rq '/Users/' codex/ && ! grep -q 'gpt-5.6' codex/prompts/route.md && ! grep -q 'model:' codex/prompts/route.md && [ "$(grep -c '' codex/AGENTS.md)" -le 30 ] && [ "$(grep -c '' codex/prompts/route.md)" -le 100 ] && echo 'T5 OK'
```

---

### T6 — Author the workflow prompts (architect / implementer / verifier / reviewer)
- status: done
- model: sonnet
- depends: T5
- independent: no

**Brief.** Create four custom-prompt files so execution kits can run on Codex (PLAN.md D5/D7):
`codex/prompts/architect.md`, `codex/prompts/implementer.md`, `codex/prompts/verifier.md`,
`codex/prompts/reviewer.md`. Templates: the four Copilot agents in
`copilot/.github/agents/{architect,implementer,verifier,reviewer}.agent.md` — port each BODY's
role doctrine, adapted for Codex. Each file: frontmatter with ONLY a one-line `description:`
(no `model:` — Codex prompts cannot pin models); body ≤ 60 lines; no absolute paths, no
prices, no model ids, no plan facts.

Codex adaptations that must appear (they differ from the Copilot originals):

- **Model selection language:** each prompt states that when dispatched non-interactively by
  the execute driver (`bin/codex_execute.py`), the driver chose the model via `--model` from
  the kit's task pin (a model id or a tier word resolved from
  `{{POLYTROPOS_ROOT}}/data/pricing.codex.json`); the prompt does not re-route.
- **implementer:** executes exactly ONE task brief from a kit's TASKS.md under
  `tasks/kits/<slug>/`; the brief is authoritative — on conflict with repo reality beyond
  shifted line numbers, STOP and report; minimum surgical change; run the task's verify
  command itself and include verbatim output (a claim without output counts as failure); the
  driver owns status writeback (`pending | in-progress | done | blocked`) and `NOTES.md` — the
  prompt owns neither; respect the kit PLAN.md's out-of-scope fence.
- **verifier:** fresh-context adversarial check of one task; never trust the implementer;
  rerun the verify command exactly as written; check each acceptance bullet against actual
  files; sweep `git status --porcelain` for out-of-fence damage; PASS/FAIL with verbatim
  output, no partial credit, fix nothing.
- **reviewer:** review one completed PHASE against the kit's PLAN.md for fence violations,
  invariant breakage, pinned-content drift, and plan drift; verdict + findings
  most-severe-first with file:line; edit nothing.
- **architect:** build an execution kit at `tasks/kits/<slug>/` (PLAN.md + TASKS.md) under the
  shared kit contract, pinned verbatim in the prompt: task fields `id`, `title`, `status`,
  `model`, brief, acceptance, verify; status vocabulary exactly
  `pending | in-progress | done | blocked`; `## Phase N — <name>` headings;
  `depends:`/`independent:` marking; task headings `### <ID> — <title>` (the driver parses the
  spaced em dash); the `model` field may be a model id from the pricing file OR a tier word
  (`cheap|mid|strong|frontier`); derive any cost numbers by shelling to
  `python3 {{POLYTROPOS_ROOT}}/bin/codex_pricing.py …`, never memory.

The placeholder `{{POLYTROPOS_ROOT}}` must appear in `architect.md` (engine + data
references) and in each prompt that references the pricing file; every file must survive T8's
bundle test (no absolute paths anywhere under `codex/`).

**Acceptance.**
- Four files at exact paths; each has description-only frontmatter; implementer/verifier/
  reviewer/architect requirements above present; architect pins the kit contract verbatim
  (fields, vocabulary, phases, depends/independent, em-dash headings); no absolute paths,
  prices, plan facts, or model ids anywhere; each body ≤ 60 lines (file ≤ 65 with
  frontmatter).

**Verify.**
```bash
cd /path/to/polytropos && for f in architect implementer verifier reviewer; do test -f "codex/prompts/$f.md" && grep -q '^description:' "codex/prompts/$f.md" && ! grep -q '^model:' "codex/prompts/$f.md" && [ "$(grep -c '' codex/prompts/$f.md)" -le 65 ] || { echo "bad $f"; exit 1; }; done && grep -q 'pending | in-progress | done | blocked' codex/prompts/architect.md && grep -q 'tasks/kits/' codex/prompts/architect.md && grep -q '{{POLYTROPOS_ROOT}}' codex/prompts/architect.md && grep -q 'tasks/kits/' codex/prompts/implementer.md && grep -qi 'verify command' codex/prompts/implementer.md && grep -qi 'never trust' codex/prompts/verifier.md && grep -qi 'fence' codex/prompts/reviewer.md && ! grep -rq '/Users/' codex/ && ! grep -rq 'gpt-5.6' codex/prompts/ && echo 'T6 OK'
```

---

### T7 — Extend bin/harness_select.py with the codex harness
- status: done
- model: opus
- depends: T5, T6
- independent: no

**Brief.** Per PLAN.md D6, extend `bin/harness_select.py` (read it fully first) ADDITIVELY:
existing claude-code/copilot behavior must stay byte-identical in output and code path.

Changes:

1. **Constants:** add `BUNDLE_CODEX_PROMPTS = REPO_ROOT / "codex" / "prompts"` and
   `BUNDLE_CODEX_AGENTS_MD = REPO_ROOT / "codex" / "AGENTS.md"`.
2. **`detect()`** gains a third key: `"codex": shutil.which("codex") is not None`. Human
   `detect` output appends a codex line after the copilot line: found/not found plus
   `run: python3 bin/harness_select.py install --harness codex (--codex-home <dir> to
   override; defaults to ~/.codex)`.
3. **`install_codex(home, repo_root=None, dry_run=False) -> list`** — mirrors
   `install_copilot`'s shape (repo_root defaulting, placeholder resolution via
   `text.replace(PLACEHOLDER, str(repo_root))`, returns destination paths including under
   dry-run which writes NOTHING):
   - every `*.md` under `<repo_root>/codex/prompts/` → `<home>/prompts/<same name>`
     (placeholder resolved; dirs created). Missing/empty prompts dir → `FileNotFoundError`
     naming the expected path.
   - `<repo_root>/codex/AGENTS.md` → `<home>/AGENTS.md` under the **no-clobber rule** (PLAN.md
     D6, mandatory): destination absent → write the resolved text; destination present and
     byte-identical to the resolved text → do not write, note `up to date`; destination
     present and DIFFERENT → **never overwrite**: skip it and print a warning telling the user
     to merge `<repo_root>/codex/AGENTS.md` manually (the returned path list still includes it
     so callers see the full intent; the printed verb distinguishes `skipped (exists,
     differs)`). Rationale in the docstring: `~/.codex/AGENTS.md` is a single shared file that
     may hold the user's own global instructions — unlike Copilot's namespaced `agents/` dir,
     overwriting is destructive.
   - NEVER touch `config.toml` — state this in the docstring.
4. **CLI:** `install --harness` choices become `{claude-code, copilot, codex}`; add
   `--codex-home PATH` (default `Path.home() / ".codex"`); codex install prints one
   `installed <path>` / `would install <path>` / `up to date <path>` / `skipped (exists,
   differs) <path>` line per file. Errors → stderr, exit 2.
5. **Docstring:** extend with what the codex install does, the AGENTS.md no-clobber rule, and
   that `~/.codex` is only ever written at the user's explicit request via this installer —
   tests always use a temp `--codex-home`.
6. **The ONE sanctioned pre-existing-test edit** (standing rule exception): in
   `tests/test_harness_select.py`, `test_detect_key_and_boolean_combinations` hardcodes
   two-key expectations and would fail. Surgically update ONLY that method: each combo's
   expected dict gains `"codex": False` (none of the existing combos map `codex`), add one new
   combo `({"codex": "/usr/local/bin/codex"}, {"claude-code": False, "copilot": False,
   "codex": True})`, and the set assertion becomes
   `{"claude-code", "copilot", "codex"}`. Change NOTHING else in that file — every other test
   must remain byte-identical.

EXECUTION GUARDRAIL (binds YOU): only ever run `install --harness codex` with `--codex-home`
pointing at a fresh temp directory. Never let it default to the real `~/.codex`. Never run the
`codex` binary.

**Acceptance.**
- `detect` reports three harnesses; claude-code/copilot install paths behave exactly as
  before.
- Codex install into a temp home materializes 5 prompts + AGENTS.md with every placeholder
  replaced by the absolute repo root; `--dry-run` writes nothing; a pre-seeded DIFFERING
  `<home>/AGENTS.md` survives an install byte-identical with a `skipped` line; an identical
  one reports `up to date`.
- Full suite green; only `bin/harness_select.py` and the single test method changed.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/harness_select.py detect | grep -qi codex && H="$(mktemp -d)" && python3 bin/harness_select.py install --harness codex --dry-run --codex-home "$H" && test ! -e "$H/prompts" && test ! -e "$H/AGENTS.md" && python3 bin/harness_select.py install --harness codex --codex-home "$H" && test -f "$H/prompts/route.md" && test -f "$H/prompts/architect.md" && test -f "$H/AGENTS.md" && ! grep -rq '{{POLYTROPOS_ROOT}}' "$H" && grep -q "$PWD/bin/codex_pricing.py" "$H/prompts/route.md" && H2="$(mktemp -d)" && mkdir -p "$H2" && echo 'MY OWN INSTRUCTIONS' > "$H2/AGENTS.md" && python3 bin/harness_select.py install --harness codex --codex-home "$H2" | grep -qi 'skip' && [ "$(cat "$H2/AGENTS.md")" = 'MY OWN INSTRUCTIONS' ] && rm -rf "$H" "$H2" && python3 -m unittest discover -s tests && git diff --quiet -- copilot data/pricing.json data/pricing.copilot.json tests/test_copilot_bundle.py && echo 'T7 OK'
```

---

### T8 — Bundle + installer consistency tests
- status: done
- model: sonnet
- depends: T7
- independent: no

**Brief.** Create `tests/test_codex_bundle.py`, stdlib `unittest` + `unittest.mock`, importlib
`_load` convention (load `bin/harness_select.py`). This test file carries BOTH the bundle
consistency contract (the role `tests/test_copilot_bundle.py` plays for the copilot bundle —
read it as a template; note there is deliberately NO `codex/aesop.yaml`, PLAN.md D5) and the
codex installer tests (kept out of the frozen `tests/test_harness_select.py`). All installs go
to `tempfile.TemporaryDirectory` homes; nothing may touch the real `~`.

Bundle contract cases (read files only):

1. **Doctrine:** the exact sentence (module constant, backticks included)
   `Derive every number from `data/pricing.codex.json` at run time — it is the single source
   of truth for Codex-side pricing; never quote prices, plan limits, or model ids from
   memory.` appears in `codex/AGENTS.md`.
2. **Prompt roster:** `codex/prompts/` contains exactly
   `{route, architect, implementer, verifier, reviewer}.md`.
3. **Frontmatter discipline:** every prompt has a `description:` line and NO `model:` line in
   its frontmatter block.
4. **Placeholder discipline:** `{{POLYTROPOS_ROOT}}` appears in `route.md` and
   `architect.md`; NO file under `codex/` contains `/Users/` or `/home/`.
5. **Harness separation:** no file under `codex/` mentions `CLAUDE_PLUGIN_ROOT`,
   `data/pricing.json`, or `data/pricing.copilot.json` (plain substring checks —
   `data/pricing.json` is not a substring of `data/pricing.codex.json`).
6. **No hardcoded roster:** no file under `codex/` contains any model id key from the real
   `data/pricing.codex.json` (loaded at test run time — ids never appear as literals in the
   test either).

Installer cases (mirror `tests/test_harness_select.py`'s style):

7. **Placeholder resolution:** temp repo_root with `codex/prompts/route.md` containing the
   placeholder twice + a `codex/AGENTS.md`; `install_codex(home, repo_root=tmp_root)` writes
   both with all occurrences replaced and everything else byte-identical.
8. **Dry-run:** same destination list, no files/dirs created.
9. **Idempotence:** two installs → same content; AGENTS.md second pass reports up-to-date
   (assert file unchanged).
10. **No-clobber:** pre-seeded differing `<home>/AGENTS.md` is byte-identical after install;
    prompts still installed.
11. **Missing bundle:** empty temp repo_root raises `FileNotFoundError` naming the prompts
    path.
12. **detect():** with mocked `shutil.which`, the dict has exactly
    `{"claude-code", "copilot", "codex"}` keys and correct booleans for a codex-present combo.
13. **Live-tree guard:** the REAL `codex/prompts/route.md` exists and still contains the
    placeholder (guards against committing a resolved bundle).

**Acceptance.** All new tests pass; full suite green; no writes outside temp dirs; the real
`~/.codex` never read or written; breaking any bundle contract by hand-editing a `codex/` file
makes the suite fail.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v && python3 -m unittest discover -s tests && echo 'T8 OK'
```

---

*Phase 2 end — dispatch `codex-harness-reviewer` before starting Phase 3.*

---

## Phase 3 — Execute driver + usage reader

### T9 — Create bin/codex_execute.py (kit-dispatch driver)
- status: done
- model: opus
- depends: T3, T6
- independent: yes

**Brief.** Port `bin/copilot_execute.py` to Codex (read it FULLY first — it is the template
for structure, parsing, statuses, writeback, and the safety banner; reuse its TASKS.md grammar
verbatim: `### <ID> — <title>` with the spaced em dash, `**Brief.**`/`**Acceptance.**`/
`**Verify.**` markers, ```` ```bash ```` verify fences, `- status:`/`- model:`/`- depends:`/
`- independent:` fields, `pending | in-progress | done | blocked`). Kits live at
`tasks/kits/<slug>/` in consumer repos. Also read `.claude/kits/codex-harness/RESEARCH.md` —
if its findings contradict any pinned flag below, STOP and report (PLAN.md tripwire).

The module docstring must carry a QUOTA/NETWORK safety banner equivalent to
copilot_execute.py's: a real (non-`--dry-run`) `run`/`review` shells out to the `codex` CLI,
which CALLS A MODEL — it spends the user's real subscription usage limits (or API dollars) and
hits the network, and the user has a live `~/.codex`. NEVER invoke the real `codex` binary
during development or verification. `--dry-run` prints the exact dispatch argv and spawns
nothing; every dispatch and verify goes through injectable runner callables; tests inject
fakes or temp stub executables via `--codex-bin`; `build_dispatch` returns an argv LIST, never
`shell=True`.

Codex adaptations (PLAN.md D7 — everything else mirrors the template):

1. **Pricing/tiers:** `PRICING_PATH` → `data/pricing.codex.json`; `TIER_ORDER = ("cheap",
   "mid", "strong", "frontier")`; `DEFAULT_ESCALATION_START = "mid"`. A task's `model` field
   may be a model id from the pricing file OR a tier word — resolve tier words via the D4
   skip-up rule (first model in file order carrying the tier; unpopulated tier → next tier
   up). Implement the rule locally against the loaded dict (this driver does not import
   codex_pricing, mirroring how copilot_execute does not import copilot_pricing) — but the
   docstring must name D4 as the shared rule and `codex_pricing.resolve_tier` as its sibling.
   The escalation ladder walks tiers strictly above the resolved model's tier, SKIPPING empty
   tiers, first model in file order per tier, appending the verify-failure evidence (command,
   exit code, output tail) to the re-dispatched brief; ladder exhausted ⇒ `blocked`.
2. **Dispatch anatomy** (best-effort, NOT live-verified — say so in the docstring exactly as
   copilot_execute flags its `--model` precedence note):
   `build_dispatch(codex_bin, model_id, prompt, effort=None, extra_args=()) ->`
   `[codex_bin, "exec", "--model", <model_id>, "--full-auto"]
   + (["-c", "model_reasoning_effort=" + effort] if effort else [])
   + list(extra_args) + [prompt]`.
   A task whose `model` field is absent dispatches WITHOUT `--model` (the user's configured
   Codex default applies — the kit-contract override rule's carry-over). `--full-auto` is the
   non-interactive permission grant (the `--allow-all-tools` analogue). CLI flags: `--effort`
   (choices from nothing hardcoded — validate against `pricing["knobs"]["reasoning_efforts"]`
   at run time), repeatable `--extra-arg` (covers `--sandbox`, `--skip-git-repo-check`, and
   any future fast-mode surface — NO fast/ultra flag is invented here).
3. **Role preambles replace `--agent`:** `load_preamble(role, repo_root=None)` reads
   `<repo_root>/codex/prompts/<role>.md` (repo_root defaults to this repo), strips the
   frontmatter block, and resolves `{{POLYTROPOS_ROOT}}` → `str(repo_root)` IN MEMORY
   (never writing the bundle). `run` composes `preamble + "\n\n---\n\n" + brief` with the
   `implementer` role (a `--role` flag overrides); `review` uses the `reviewer` role with the
   phase's task list in the prompt.
4. Subcommands, mirrored: `status --kit DIR [--json]`; `run --kit DIR [--task ID]
   [--role NAME] [--codex-bin BIN] [--effort E] [--max-escalations N] [--extra-arg X ...]
   [--dry-run]`; `review --kit DIR --phase N [--codex-bin BIN] [--extra-arg X ...]
   [--dry-run]`. Status writeback is the surgical single-line replacement; NOTES.md appended
   by the driver only (escalation notes), exactly as the template does.

Nothing here hardcodes a model id or a price; the tier vocabulary and flag strings are the
sanctioned literals.

**Acceptance.**
- `status` parses a fixture kit; `run --dry-run` prints a `codex exec … --full-auto …` argv
  (with `--model` when pinned, without when absent, with `-c model_reasoning_effort=…` when
  `--effort` given) and mutates NOTHING (no status change, no NOTES.md).
- A tier-word `model:` field resolves via the skip-up rule (a fixture task pinned
  `strong` dispatches the frontier model's id with today's data).
- The safety banner, the not-live-verified note, and the D4 reference are in the docstring.
- Full suite green; no real `codex` invocation anywhere.

**Verify.**
```bash
cd /path/to/polytropos && K="$(mktemp -d)/kit" && mkdir -p "$K" && printf '# PLAN — fixture\n' > "$K/PLAN.md" && printf '# TASKS\n\n## Phase 1 — demo\n\n### T1 — fixture task\n- status: pending\n- model: strong\n- depends: (none)\n- independent: yes\n\n**Brief.** Do nothing.\n\n**Acceptance.** n/a\n\n**Verify.**\n```bash\ntrue\n```\n' > "$K/TASKS.md" && python3 bin/codex_execute.py status --kit "$K" | grep -q 'T1' && OUT="$(python3 bin/codex_execute.py run --kit "$K" --task T1 --dry-run)" && echo "$OUT" | grep -q 'exec' && echo "$OUT" | grep -q -- '--full-auto' && echo "$OUT" | grep -q -- '--model' && FRONT="$(python3 -c "import json; p=json.load(open('data/pricing.codex.json')); print(next(k for k,v in p['models'].items() if v['tier']=='frontier'))")" && echo "$OUT" | grep -q "$FRONT" && grep -q 'status: pending' "$K/TASKS.md" && test ! -f "$K/NOTES.md" && python3 -m unittest discover -s tests && echo 'T9 OK'
```

---

### T10 — Regression tests for the execute driver
- status: done
- model: sonnet
- depends: T9
- independent: no

**Brief.** Create `tests/test_codex_execute.py`, stdlib `unittest` + `unittest.mock`,
importlib `_load` convention. Template: `tests/test_copilot_execute.py` (read it first; mirror
its fixture-kit builder approach — synthetic kits in temp dirs, fake runners, NEVER a real
binary). Use a synthetic pricing dict injected/patched into the loaded module (fake round
numbers, four tiers with one EMPTY tier that is NOT `strong`, so the skip-up rule is proven
general — mirror T4's fixture philosophy).

Test cases (minimum):

1. **Parsing:** a fixture TASKS.md with two phases parses ids/titles/status/model/depends/
   independent/brief/verify correctly (spaced em dash headings; `(none)` depends).
2. **build_dispatch anatomy:** exact argv equality for: model id pinned; tier word pinned
   (resolves through the synthetic roster's skip-up path); no model field (no `--model` pair);
   `effort` given (`-c model_reasoning_effort=…` present, validated against the synthetic
   knobs list — invalid effort rejected before dispatch); extra args positioned before the
   prompt; prompt is the LAST element; never any `shell=True` (assert dispatch is a list).
3. **Preamble composition:** `load_preamble` strips frontmatter, resolves the placeholder
   in memory against a temp repo_root fixture bundle, and the composed run prompt is
   `preamble + separator + brief`; the on-disk bundle file still contains the placeholder
   afterward.
4. **Run happy path:** fake runner returns success, fake verify_runner exit 0 → status
   rewritten to `done` surgically (rest of TASKS.md byte-identical).
5. **Escalation:** verify fails at the pinned tier → re-dispatch at each strictly-higher
   populated tier (empty tier skipped — assert the skipped tier's absence from the dispatch
   sequence), evidence (exit code + output tail) appended to the re-dispatched prompt; ladder
   exhausted → status `blocked` and a NOTES.md line written.
6. **Dry-run:** prints argv, spawns nothing (runner asserted uncalled), mutates nothing
   (TASKS.md byte-identical, no NOTES.md).
7. **Safety:** no test anywhere invokes a real binary — any subprocess-level test uses a temp
   stub executable created by the test and passed via `--codex-bin`.

**Acceptance.** All new tests pass; full suite green; no writes outside temp dirs; every
pre-existing test file byte-untouched.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_codex_execute.py' -v && python3 -m unittest discover -s tests && git diff --quiet -- tests/test_copilot_execute.py && echo 'T10 OK'
```

---

### T11 — Create bin/codex_usage.py (read-only usage report)
- status: done
- model: sonnet
- depends: T2
- independent: yes

**Brief.** Per PLAN.md D8: the Codex analogue of `bin/copilot_usage.py` (read its docstring
and honesty conventions first) with an honesty ladder for Codex's thin logs. Also read
`.claude/kits/codex-harness/RESEARCH.md` (T1's findings) and `bin/journal_sources.py` lines
~307–360 (the `CODEX_*` candidate-key philosophy) — but do NOT import or edit any journal
script: this reader owns its own constants (deliberate, documented duplication — the journal's
"Codex counted, never priced" invariant stays frozen; THIS script is the one sanctioned place
Codex tokens may be priced, and only against `data/pricing.codex.json`).

STRICTLY READ-ONLY, docstring-pinned: never writes under the target home; opens ONLY `.jsonl`
files (`session_index.jsonl`, `history.jsonl`, and rollout `*.jsonl` under `sessions/`) plus
nothing else — NEVER a `*.db`/SQLite file, NEVER a `codex` invocation. Runtime default
`DEFAULT_CODEX_HOME = Path.home() / ".codex"` is the ONLY `Path.home()` use; tests always
override via `--codex-home`.

Mechanics:

- CLI: `codex_usage.py [--days N] [--top N] [--codex-home DIR] [--json]` (defaults 30 / 10).
- **Scan:** `session_index.jsonl` + `history.jsonl` for activity (session ids, timestamps —
  reuse the tolerant-timestamp approach: ISO strings or epoch seconds/millis). Rollouts:
  walk `sessions/`; when the relative path matches `YYYY/MM/DD/…`, prune date-dirs outside
  the window BEFORE opening anything; non-date layouts fall back to file mtime for pruning.
- **Extraction constants** (module-level, extend-never-shrink, seeded from RESEARCH.md —
  update the candidate lists if T1 recorded different key names, never remove these):
  timestamp keys `("timestamp","ts","created_at","updated_at","time","datetime")`; session
  keys `("session_id","sessionId","conversation_id","id")`; model keys
  `("model","model_id","model_slug")`; wrapper keys for one-level descent
  `("payload","data","info","turn_context")`; usage container keys
  `("total_token_usage","last_token_usage","usage","token_usage","tokens","token_counts")`;
  token field map `input_tokens/prompt_tokens → input`,
  `cached_input_tokens/cache_read_input_tokens/cached_tokens → cache_read`,
  `output_tokens/completion_tokens → output` (`reasoning_output_tokens` is deliberately NOT
  mapped — OpenAI includes reasoning in `output_tokens`; mapping it would double-count.
  Docstring must say so).
- **Cumulative-vs-per-turn rule** (the honesty-critical subtlety, pinned): within one rollout
  file, `total_token_usage` containers are cumulative snapshots → aggregate by element-wise
  MAX; other containers are per-turn → sum. If a file yields BOTH, the cumulative MAX wins for
  that file (never add the two). Docstring must state this mirrors copilot_usage's
  shutdown-snapshot MAX rule.
- **Pricing** (observed counts): per model matched against `pricing["models"]` keys
  (copilot_usage's `match_model` prefix approach), `usd_api = (input × input_per_mtok +
  cache_read × input_per_mtok × cache_read_multiplier + output × output_per_mtok) / 1e6`.
  Cache writes are not observable in these logs → not priced (docstring notes the asymmetry
  vs the write multiplier in the data). Unmatched model strings land in an `unpriced models`
  list — never guessed.
- **Honesty ladder → markdown report:** (a) tokens found → per-model table (tokens by class,
  est API-USD) + totals + this standing disclaimer line, pinned verbatim:
  `Figures are API-equivalent dollars — a relative-burn proxy. Subscription (ChatGPT-plan) usage is usage-limited, not token-billed.`
  (b) activity but no tokens → sessions/records/models-seen counts + pinned line:
  `no token usage found in these logs — activity counted, unpriced`.
  (c) home or files absent → say which, cleanly, exit 0. Never a fabricated or zeroed dollar
  stand-in; malformed lines counted, skipped.

**Acceptance.**
- Against a synthetic `--codex-home` with rollout token data: table + API-USD + the verbatim
  proxy disclaimer. Against one with only index/history files: the verbatim unpriced line.
  Against an empty temp dir: clean absence message, exit 0.
- No writes under any target home; no `*.db` opened; full suite green; `bin/journal_*.py`
  byte-untouched.

**Verify.**
```bash
cd /path/to/polytropos && H="$(mktemp -d)" && python3 - "$H" <<'EOF'
import json,sys,datetime
from pathlib import Path
home=Path(sys.argv[1]); day=datetime.datetime.now(datetime.timezone.utc)
d=home/'sessions'/f"{day:%Y}"/f"{day:%m}"/f"{day:%d}"; d.mkdir(parents=True)
mid=next(k for k,v in json.load(open('data/pricing.codex.json'))['models'].items() if v['tier']=='mid')
recs=[{"timestamp":day.isoformat(),"type":"turn_context","payload":{"model":mid}},
      {"timestamp":day.isoformat(),"type":"event_msg","payload":{"info":{"total_token_usage":{"input_tokens":100000,"cached_input_tokens":50000,"output_tokens":20000}}}}]
(d/'rollout-test.jsonl').write_text("\n".join(json.dumps(r) for r in recs)+"\n")
(home/'history.jsonl').write_text(json.dumps({"session_id":"s1","ts":int(day.timestamp()),"text":"x"})+"\n")
EOF
python3 bin/codex_usage.py --days 2 --codex-home "$H" | tee /tmp/cu.out | grep -qF 'relative-burn proxy' && grep -q '\$' /tmp/cu.out && H2="$(mktemp -d)" && printf '{"session_id":"s2","ts":%s,"text":"y"}\n' "$(date +%s)" > "$H2/history.jsonl" && python3 bin/codex_usage.py --days 2 --codex-home "$H2" | grep -qF 'activity counted, unpriced' && H3="$(mktemp -d)" && python3 bin/codex_usage.py --codex-home "$H3" && rm -rf "$H" "$H2" "$H3" && python3 -m unittest discover -s tests && git diff --quiet -- bin/journal_sources.py bin/journal_collect.py bin/journal_summarize.py && echo 'T11 OK'
```

---

### T12 — Regression tests for the usage reader
- status: done
- model: sonnet
- depends: T11
- independent: no

**Brief.** Create `tests/test_codex_usage.py`, stdlib `unittest`, importlib `_load`
convention. Template: `tests/test_copilot_usage.py`. All fixtures are synthetic JSONL in temp
`--codex-home` dirs; the real `~/.codex` is never read or written; use a synthetic pricing
dict with fake round numbers (e.g. `cache_read_multiplier: 0.5`) patched/injected so no real
price appears, plus targeted runs against the real pricing file for structure-level smokes
only.

Test cases (minimum):

1. **Cumulative MAX rule:** a rollout with three `total_token_usage` snapshots (rising, then
   repeated) prices exactly the element-wise MAX, never the sum.
2. **Per-turn SUM rule:** a rollout with only per-turn `usage` containers sums them; a rollout
   with BOTH kinds uses the cumulative MAX only.
3. **Reasoning tokens:** `reasoning_output_tokens` present alongside `output_tokens` does NOT
   inflate output counts.
4. **Pricing math:** hand-computed `assertAlmostEqual` including the cache-read term at the
   fixture multiplier 0.5 (proves 0.1 is nowhere in code); unmatched model string lands in
   the unpriced list with no dollars.
5. **Date pruning:** a rollout under an out-of-window `YYYY/MM/DD` dir is never opened
   (create it unreadable or assert via record counts).
6. **Honesty branches:** tokens branch prints the verbatim proxy disclaimer; activity-only
   branch prints the verbatim `activity counted, unpriced` line; empty home exits 0 with the
   absence message.
7. **Robustness:** malformed JSON lines and non-dict records are counted and skipped; epoch-
   millis and ISO timestamps both parse.
8. **Read-only:** after any run, the temp home's file tree (paths + contents) is byte-
   identical to the fixture as written.

**Acceptance.** All new tests pass; full suite green; no writes outside temp dirs; every
pre-existing test file byte-untouched.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_codex_usage.py' -v && python3 -m unittest discover -s tests && echo 'T12 OK'
```

---

*Phase 3 end — dispatch `codex-harness-reviewer` before starting Phase 4.*

---

## Phase 4 — Docs + guardrails

### T13 — Write docs/CODEX-HARNESS.md + README cross-link
- status: done
- model: sonnet
- depends: T3, T7, T9, T11
- independent: yes

**Brief.** Two changes.

**(1) Create `docs/CODEX-HARNESS.md`** — the user-facing guide for the Codex side. Tone and
format of `docs/COPILOT-HARNESS.md` (read it as the template); 90–160 lines. Required H2
headings, exactly these seven:

1. `## What this is` — the three-harness monorepo shape: repo root = the live Claude Code
   plugin; `copilot/` = the Copilot bundle; `codex/` = the Codex bundle (`AGENTS.md` +
   `prompts/`); three pricing files that never merge; shared installer
   `bin/harness_select.py`.
2. `## Install into Codex CLI` — `detect`, then
   `python3 bin/harness_select.py install --harness codex` (default home `~/.codex`, override
   `--codex-home`); what install does (placeholder → absolute path; prompts become `/route`
   etc. in the TUI); the AGENTS.md no-clobber rule and how to merge manually; the fact that
   `config.toml` is never touched.
3. `## Route a task` — `/route` interactively; the billing-mode-first rule; the six action
   mechanisms from the route prompt's table; the speed levers (cheap tier, Cerebras note,
   fast mode existence + unpublished surface, effort/ultra trade-offs).
4. `## Pricing: API dollars vs subscription limits` — the D3 story in user terms: API mode =
   real dollars; subscription mode = usage limits, `billed_usd: null`, the labeled
   API-equivalent proxy + burn index; GPT-5.6 preview availability caveat. Include a compact
   snapshot table generated from `data/pricing.codex.json` (columns: tier, model, $ in/MTok,
   $ cached-in/MTok (computed 0.1×), $ out/MTok) — MUST be labeled a snapshot tied to
   `cached_date` (2026-07-06), with the cache multipliers (reads 0.1×, writes 1.25×, 30-min
   min life) and the `model_ids_note` caveat (ids best-effort; `/model` authoritative;
   correct in the data file only).
5. `## Run kits on Codex` — `bin/codex_execute.py` status/run/review; kits at
   `tasks/kits/<slug>/`; the model-id-or-tier-word rule; escalation ladder + empty-tier skip;
   the dry-run-first discipline; the QUOTA warning (a real run spends subscription
   limits/API dollars).
6. `## Usage report` — `bin/codex_usage.py`; strictly read-only; the honesty ladder (what you
   get when logs carry tokens vs not); the proxy disclaimer.
7. `## Updating Codex prices` — edit `data/pricing.codex.json` only (from `update_from`),
   bump `cached_date`, refresh this doc's snapshot table in the same change, rerun the suite;
   re-check when GPT-5.6 goes GA (ids, plan inclusion, fast/ultra surfaces).

**(2) `README.md`** — the paragraph beginning `**GitHub Copilot harness:**` ends with
`installed via \`bin/harness_select.py\`.` Insert directly after that paragraph, as its own
paragraph:
> **OpenAI Codex harness:** [docs/CODEX-HARNESS.md](docs/CODEX-HARNESS.md) — the same routing workflow for OpenAI Codex CLI: GPT-5.6 (Sol/Terra/Luna) pricing data in `data/pricing.codex.json` with honest subscription-vs-API framing, a `/route` custom prompt and workflow prompts in `codex/`, a kit-dispatch driver (`bin/codex_execute.py`), and a read-only usage report (`bin/codex_usage.py`), installed via `bin/harness_select.py`.

If the `**GitHub Copilot harness:**` anchor paragraph is not present, STOP and report. Change
nothing else in README.md.

**Acceptance.** Doc exists with exactly the seven H2 headings; snapshot table labeled with
2026-07-06; the words "not a bill" (or "never presented as a bill") and the preview caveat
appear; README paragraph inserted verbatim at the anchor; git diff shows only these two files.

**Verify.**
```bash
cd /path/to/polytropos && for h in 'What this is' 'Install into Codex CLI' 'Route a task' 'Pricing: API dollars vs subscription limits' 'Run kits on Codex' 'Usage report' 'Updating Codex prices'; do grep -q "^## $h" docs/CODEX-HARNESS.md || { echo "missing: $h"; exit 1; }; done && [ "$(grep -c '^## ' docs/CODEX-HARNESS.md)" -eq 7 ] && grep -q '2026-07-06' docs/CODEX-HARNESS.md && grep -qi 'bill' docs/CODEX-HARNESS.md && grep -q 'CODEX-HARNESS.md' README.md && grep -q 'codex_execute.py' README.md && python3 -m unittest discover -s tests && echo 'T13 OK'
```

---

### T14 — CLAUDE.md: Codex-side invariant + usage run-line
- status: done
- model: haiku
- depends: T2
- independent: yes

**Brief.** Two pinned insertions into the hand-authored `CLAUDE.md`. Change nothing else.
(The codex-harness out-of-scope fence paragraph and the `codex_pricing.py models` run-line
were added by the architect and already exist — do NOT duplicate or edit them.)

**(1)** In `## Invariants`, the bullet beginning
`- **\`data/pricing.copilot.json\` is the Copilot-side numeric source of truth**` ends with
`resolved to an absolute path only by \`bin/harness_select.py\` at install time.` Insert
immediately AFTER that bullet, as a NEW top-level bullet:
> - **`data/pricing.codex.json` is the Codex-side numeric source of truth** — same rules: never hardcode Codex prices, cache multipliers, plan facts, or model IDs into `codex/` content or scripts; derive them at run time. Its GPT-5.6 model ids are best-effort (see its `model_ids_note`) — corrections land there and only there. Subscription (ChatGPT-plan) Codex runs are usage-limited, not token-billed: every dollar figure shown for them is a labeled API-equivalent relative-burn proxy, never a bill (`billed_usd` stays null). The three pricing files never merge and no harness reads another's; the daily journal keeps counting Codex WITHOUT pricing it — `pricing.codex.json` is never wired into `bin/journal_*.py`. Bundle files under `codex/` carry `{{POLYTROPOS_ROOT}}`, resolved only by `bin/harness_select.py` at install time, which never writes `config.toml` and never overwrites a differing `AGENTS.md`.

**(2)** In the `## How to run things` code block, insert immediately after the
`python3 bin/codex_pricing.py models --profile M` line this single line (into the EXISTING
code block, comment aligned with the others — do not create a new code block):

```
python3 bin/codex_usage.py --days 30                  # Codex usage report (reads ~/.codex read-only; honest unpriced fallback)
```

**Acceptance.** Both insertions present verbatim at the specified anchors; git diff shows only
these two additions in CLAUDE.md.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'pricing.codex.json` is the Codex-side numeric source of truth' CLAUDE.md && grep -q 'codex_usage.py --days 30' CLAUDE.md && grep -q 'never wired into `bin/journal_' CLAUDE.md && python3 -m unittest discover -s tests && echo 'T14 OK'
```

---

*Phase 4 end — dispatch `codex-harness-reviewer` for the final review, then run the overall
"done" check from PLAN.md.*
