# The effort dial — cross-harness contract

The effort dial is the GPT-5.6 reasoning-effort ladder (`minimal → … → max`), surfaced honestly
on each non-Claude harness to the extent its CLI actually supports it. This doc records the
contract, the mechanism per harness, house guidance, where the facts came from, and the open
items still deferred — so none of it depends on this kit's conversation history.

## 1. The contract

The dial is DATA, not prose. Each harness's vocabulary lives ONLY in its own pricing file's
`knobs.reasoning_efforts` block, and is derived at run time — never hardcoded in a skill, prompt,
agent body, or script:

```bash
python3 bin/codex_pricing.py knobs      # Codex: lowercase API tokens
python3 bin/copilot_pricing.py knobs    # Copilot: Title-Case display forms
```

The two vocabularies never mix. Codex's `knobs.reasoning_efforts` in `data/pricing.codex.json`
is `["minimal","low","medium","high","xhigh","max"]` — the literal tokens passed to
`-c model_reasoning_effort=<level>`. Copilot's `knobs.reasoning_efforts` in
`data/pricing.copilot.json` is `["Minimal","Low","Medium","High","Extra High","Max"]` — what the
`/model` picker renders on screen. A Codex token never appears in a Copilot file or bundle body,
and a Copilot display word never stands in for a Codex flag value.

## 2. Per-harness mechanism table

| Harness | Mechanism | Status |
|---|---|---|
| Codex | `-c model_reasoning_effort=<level>` on `codex exec`, and `codex_execute.py run --effort <level>` (validated against `knobs.reasoning_efforts` at run time — an unknown level errors before dispatch) | Confirmed |
| Copilot | Interactive `/model` picker; ←/→ arrow keys adjust the "Reasoning" column on the selected row. Per-model: rows showing `—` (Auto, Claude Sonnet 4.5, Claude Haiku 4.5, Claude Opus 4.5, Kimi K2.7 Code) have no dial; every other row defaults to "Medium" | Interactive mechanism confirmed; headless surface UNCONFIRMED — no `copilot -p` flag or settings key is known to exist |
| Claude Code | — | Out of scope here; effort is managed in-model, not by a CLI dial |

Because no headless Copilot flag is confirmed, `bin/copilot_execute.py` is byte-untouched and
nothing under `copilot/` names `--effort` or `model_reasoning_effort` — inventing either would be
fabrication. Codex's flag is already live in `bin/codex_execute.py` and needed no change.

## 3. Guidance

- Omit the dial for routine work — the harness default applies (Copilot's observed default is
  "Medium"; Codex has no forced default).
- Step up ONE level at a time, only on failure evidence — never start at the top.
- Reach for the low end of the ladder for bulk or latency-sensitive work.
- Effort is orthogonal to model choice: a deeper effort level does not substitute for a tier
  jump. If a model fails at `max`/`Max`, that is a capability gap, not an effort problem.
- Burn honesty differs by harness. Codex under a ChatGPT subscription draws down opaque
  usage/rate limits, not dollars — any dollar figure shown for a subscription run is a labeled
  API-equivalent relative-burn proxy, never a bill (`billed_usd` stays null). Copilot AI Credits
  are real money, settled at `billing_unit.usd_per_credit` ($0.01/credit).

## 4. Data provenance (2026-07-18 captures)

- **GPT-5.6 announcement PDF (authoritative).** Confirms the ascending token ladder
  `minimal | low | medium | high | xhigh | max` — `max` is the new deepest level, giving more
  reasoning time than `xhigh`. `ultra` is a MODE, not a rung on the ladder: it coordinates four
  agents in parallel by default (the API's multi-agent beta), CLI surface unpublished. GPT-5.6
  (Sol/Terra/Luna) is GA across ChatGPT, Codex, and the API.
- **Copilot `/model` picker screenshots (user-supplied).** The Reasoning column is the
  mechanism — footer literally reads "←/→ reasoning effort". Two display words were directly
  observed: "Medium" (default) and "Extra High" (Sol cycled up). Sol's picker cost panel shows
  500 / 3,000 / 50 / 625 credits per 1M tokens (input / output / cached input / cache write) —
  matching `gpt-5.6-sol`'s rates in `data/pricing.copilot.json` exactly.
- **API pricing table (GA, captured 2026-07-18).** Default-tier USD/1M for Sol/Terra/Luna
  matches `data/pricing.codex.json`'s existing rates exactly — no rate value changed in that
  file this kit. Long-context step-up tiers are recorded as a note only in both pricing files'
  `long_context_note` (re-captured 2026-08-11 after OpenAI's 2026-07-30 cut, Terra -20% / Luna -80%:
  Sol >272K → $10/$1/$45, Terra >272K → $4/$0.40/$18, Luna >200K → $0.40/$0.04/$1.80) — never modeled as schema.

The pricing files are the live source of truth for all of the above; this section names the
provenance as a labeled 2026-07-18 snapshot, not a substitute for reading the data.

## 5. Open items ledger

| Open item | Single correctable point |
|---|---|
| Copilot headless effort surface (no confirmed `copilot -p` flag or settings key) | `pricing.copilot.json` → `knobs.reasoning_efforts_note` |
| The four unobserved Copilot display renderings (Minimal/Low/High/Max) | `pricing.copilot.json` → `knobs.reasoning_efforts_note` |
| GPT-5.6 long-context threshold-tier schema modeling (both harnesses) | each file's `long_context_note` |
| `ultra` (multi-agent mode) and `fast` mode CLI surfaces | `pricing.codex.json` → `knobs.modes` notes |
| Copilot full roster refresh (picker lists models `pricing.copilot.json` doesn't yet carry) + the `cached_date` bump that comes with a full re-verify | `pricing.copilot.json` → `model_ids_note` |
| Exact GPT-5.6 id strings on both harnesses (best-effort lowercase-dot pattern) | each file's `model_ids_note` |

A Claude-side `effort` skill is out of scope: Claude Code manages effort in-model, not through a
CLI dial, so there is no Claude-side counterpart to port.
