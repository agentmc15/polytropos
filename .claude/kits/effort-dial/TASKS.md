# TASKS — effort-dial

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the ground-truth captures (they
replace any live verification: NEVER invoke a real CLI to "check"), decisions D1–D10, the
OUT-OF-SCOPE fence, and the risks/tripwires. Status vocabulary:
`pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `effort-dial-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. Dispatch `effort-dial-reviewer` at each phase end.

Warm-cluster hints: the **Copilot lane** T1 → T3 → T5 is strictly serial and shares
`data/pricing.copilot.json`, `tests/test_copilot_pricing.py`, and `tests/test_copilot_bundle.py`
(all `model: sonnet` — one warm implementer may serve the chain). The **Codex lane**
T2 → T4 → T6 is strictly serial and shares `data/pricing.codex.json`, `tests/test_codex_pricing.py`,
and `tests/test_codex_bundle.py` (all `model: sonnet` — a second warm implementer). The two
lanes are mutually independent and may run in parallel with each other. The verifier is always
a fresh spawn.

Standing rules for every task: NEVER invoke the real `copilot`, `codex`, or `claude` CLI in
any form (they spend real credits/usage limits and hit the network — every fact you'd want
from them is already captured in PLAN.md's ground truth; command lines you WRITE into bundle
bodies are runtime instructions, not commands you run); nothing outside this repo —
`~/.copilot`, `~/.codex`, `~/.claude` included; never edit `data/pricing.json`, `skills/`,
`.claude-plugin/`, `README.md`, `bin/copilot_execute.py`, `bin/codex_execute.py`,
`bin/harness_select.py`, any `bin/*_usage.py` or `bin/journal_*.py`, `copilot/.github/skills/`,
any pre-existing bundle file except T2's six pinned swaps, or any completed kit; no
node/npm/`aesop compile`; test edits are ADDITIVE at the seams each brief pins — every other
test class/method/constant stays byte-intact; bundle files carry `{{POLYTROPOS_ROOT}}`,
never an absolute path, never `${CLAUDE_PLUGIN_ROOT}`, never another harness's pricing path;
effort vocabularies never cross harnesses (Codex lowercase tokens; Copilot Title-Case display
forms); verify commands use `python3 -m unittest discover -s tests [-p '<file>.py']` (the
dotted-module form is broken on this machine). Where a brief pins content verbatim, reproduce
it exactly; if a pinned anchor is not present verbatim in the target file, STOP and report the
discrepancy.

---

## Phase 1 — Data (both pricing files)

### T1 — Copilot pricing data: knobs block + the three GPT-5.6 rows
- status: done
- model: sonnet
- depends: (none)
- independent: yes (Copilot-lane head; parallel with T2)

**Brief.** Land the confirmed 2026-07-18 Copilot captures in `data/pricing.copilot.json`:
a `knobs` block (the reasoning-effort ladder in Copilot DISPLAY form + the interactive
mechanism + the headless-unconfirmed warning), a labeled `long_context_note`, and three
GPT-5.6 model rows appended at the END of the `models` object — all three with CONFIRMED
rates (Sol: picker cost panel + GitHub's "Models and pricing" doc, which agree exactly;
Terra/Luna: the GitHub doc — Copilot USD is API pass-through for GPT-5.6, 1 credit = $0.01) —
PLAN.md D5. Read first: `data/pricing.copilot.json` in full, PLAN.md's Ground truth, and
`tests/test_copilot_pricing.py`'s `LiveDataStructureTests` (every real model row must carry
positive numeric rates and a `cheap|mid|strong|frontier` tier).

Four edits, all in `data/pricing.copilot.json` (valid JSON throughout — no trailing commas):

1. **`knobs` block** — insert as a new top-level key between the `"plans_note": …` line and
   `"models": {`, verbatim:

```json
  "knobs": {
    "reasoning_efforts": ["Minimal", "Low", "Medium", "High", "Extra High", "Max"],
    "reasoning_efforts_note": "Display-form ladder, ascending. Ground truth: the GPT-5.6 announcement (2026-07-18 capture) confirms the token ladder minimal|low|medium|high|xhigh|max ('max' is the new deepest — even more reasoning time than 'xhigh'); Copilot CLI's /model picker renders Title-Case display forms, of which 'Medium' and 'Extra High' were directly observed (2026-07-18 screenshots), mapping to medium and xhigh. The other four display renderings are Title-Case mappings of the confirmed token ladder, not yet observed in the picker — if the picker renders any differently, correct the list HERE (only here). Mechanism: reasoning effort is set INTERACTIVELY in the /model picker with the left/right arrow keys on the selected model row (picker footer: '←/→ reasoning effort'); it is a per-model property — rows showing '—' have no reasoning control (observed: Auto, Claude Sonnet 4.5, Claude Haiku 4.5, Claude Opus 4.5, Kimi K2.7 Code), while every other observed row (GPT-5.6 Sol/Terra/Luna, GPT-5.5, GPT-5.4, GPT-5.3-Codex, GPT-5.4 mini, GPT-5 mini, Gemini 3.1 Pro, Gemini 3.5 Flash, MAI-Code-1-Flash, Claude Sonnet 5/4.6, Claude Opus 4.8/4.7/4.6 incl. fast mode, Claude Fable 5) defaults to 'Medium'; GPT-5.6 Sol was observed cycled up to 'Extra High'. A headless surface is UNCONFIRMED — no copilot -p flag or settings key for reasoning effort is known to exist; do not invent one. If one ships, record it here (only here)."
  },
```

2. **`long_context_note`** — insert as a new top-level key directly AFTER the closing `},` of
   the `knobs` block you just added (still before `"models": {`), verbatim:

```json
  "long_context_note": "GPT-5.6 long-context step-up rates on Copilot (GitHub Models and pricing doc, captured 2026-07-18), NOT modeled as long_context sub-objects on the GPT-5.6 rows in this kit — a deliberate scope fence; the pre-existing long_context sub-objects on other rows are unrelated and untouched. Single correctable point if ever modeled: GPT-5.6 Sol >272K input → $10.00/$1.00/$45.00; Terra >272K → $5.00/$0.50/$22.50; Luna >200K → $2.00/$0.20/$9.00 (input/cached-input/output per 1M tokens, USD).",
```

3. **Three model rows** — append at the very END of the `models` object (after the
   `mai-code-1-flash` entry, whose closing `    }` gains a comma), verbatim:

```json
    "gpt-5.6-sol": {
      "display": "GPT-5.6 Sol",
      "vendor": "openai",
      "tier": "strong",
      "input_per_mtok": 5.0,
      "cached_input_per_mtok": 0.5,
      "cache_write_per_mtok": 6.25,
      "output_per_mtok": 30.0,
      "notes": "OpenAI flagship durable tier (Powerful), GA. Rates captured 2026-07-18 from the /model picker's cost panel ('High cost' — Credits Per 1M Tokens: input 500, output 3,000, cache read 50, cache write 625; converted via billing_unit.usd_per_credit). Reasoning adjustable in the picker (default Medium; observed up to Extra High). Picker shows 400K context, tab-toggled 1.1M — capability facts, not prices. Strong tier: Claude Fable 5 remains the sole frontier pick on this roster."
    },
    "gpt-5.6-terra": {
      "display": "GPT-5.6 Terra",
      "vendor": "openai",
      "tier": "mid",
      "input_per_mtok": 2.5,
      "cached_input_per_mtok": 0.25,
      "output_per_mtok": 15.0,
      "notes": "Balanced everyday tier (Versatile), GA; confirmed present in /model 2026-07-18. Rates confirmed from GitHub's Models and pricing doc (captured 2026-07-18; Copilot USD is API pass-through for GPT-5.6 — 250/25/1,500 credits per 1M tokens). Cache writes bill at 1.25x uncached input per the doc (not stored per-model here). Reasoning adjustable in the picker (default Medium); 400K context per the picker."
    },
    "gpt-5.6-luna": {
      "display": "GPT-5.6 Luna",
      "vendor": "openai",
      "tier": "cheap",
      "input_per_mtok": 1.0,
      "cached_input_per_mtok": 0.1,
      "output_per_mtok": 6.0,
      "notes": "Fast & affordable tier (Lightweight), GA; confirmed present in /model 2026-07-18. Rates confirmed from GitHub's Models and pricing doc (captured 2026-07-18; Copilot USD is API pass-through for GPT-5.6 — 100/10/600 credits per 1M tokens). Cache writes bill at 1.25x uncached input per the doc (not stored per-model here). Reasoning adjustable in the picker (default Medium); 328K context per the picker."
    }
```

   Deliberate absences (do NOT add): no `long_context` sub-objects on the GPT-5.6 rows (the
   step-up rates live in the `long_context_note` — PLAN.md fence), no `cache_write_per_mtok`
   on Terra/Luna (the 1.25×-input doc fact lives in their notes; the estimator never uses
   cache-write rates), no other roster rows (PLAN.md scope guard — the GitHub doc lists many
   models this file lacks; that reconciliation is a deferred, separate kit).

4. **`model_ids_note` append** — inside the existing `"model_ids_note"` string, immediately
   after its final sentence `If \`/model\` ever disagrees, correct ids HERE (only here).`,
   append (same string, one space before `Partial`):

   `Partial refresh 2026-07-18: the /model picker now ALSO lists GPT-5.6 Sol/Terra/Luna (display names as shown; the gpt-5.6-* ids below are best-effort lowercase-dot per the gpt-5.4 precedent — if /model metadata or logs disagree, correct ids HERE only), with rates confirmed from GitHub's Models and pricing doc. Only the three GPT-5.6 rows were added in that refresh; the picker and doc also show models this file does not yet carry, and a full roster re-verify (with a cached_date bump) remains deliberately pending — the 2026-07-01 sentence above still dates the other 19 rows.`

`cached_date` stays `"2026-07-01"` (PLAN.md D5 — it dates the last FULL-roster verification).
Nothing else in the file changes.

**Acceptance.**
- `python3 -c "import json; p=json.load(open('data/pricing.copilot.json')); assert p['knobs']['reasoning_efforts']==['Minimal','Low','Medium','High','Extra High','Max']; assert 'long_context_note' in p; assert list(p['models'])[-3:]==['gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna']; assert p['cached_date']=='2026-07-01'; print('T1-DATA-OK')"`
  prints `T1-DATA-OK` (run it).
- The three new rows are the LAST three keys of `models` (file-order/ladder stability); Sol's
  rates are exactly 5.0/0.5/6.25/30.0; Terra 2.5/0.25/15.0 and Luna 1.0/0.1/6.0 with no
  `cache_write_per_mtok` and no `long_context` sub-object; existing rows and
  `plans`/`billing_unit`/`task_profiles` byte-intact.
- Verify command green (live-structure + bundle ModelPinLive tests pass over the larger roster).

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_pricing.py' -v && python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v && python3 bin/copilot_pricing.py est M gpt-5.6-sol
```

### T2 — Codex pricing data: `xhigh` correction + GA/ultra/long-context notes + the six enumeration swaps
- status: done
- model: sonnet
- depends: (none)
- independent: yes (Codex-lane head; parallel with T1)

**Brief.** Correct `data/pricing.codex.json` against the authoritative 2026-07-18 captures
(PLAN.md D3) and de-hardcode the now-wrong effort enumeration from the six pre-existing codex
bundle files (PLAN.md D4 — data and prose must not contradict at any task boundary). NO model
rate value changes anywhere (the GA table matched the file exactly). Read first:
`data/pricing.codex.json` in full and the six bundle files listed in edit 5.

Edits 1–4, all in `data/pricing.codex.json` (valid JSON throughout):

1. **`knobs.reasoning_efforts`** — replace the two lines
   `"reasoning_efforts": ["minimal", "low", "medium", "high", "max"],` and
   `"reasoning_efforts_note": "'max' (deepest reasoning) is new with GPT-5.6.",` with:

```json
    "reasoning_efforts": ["minimal", "low", "medium", "high", "xhigh", "max"],
    "reasoning_efforts_note": "Ascending API tokens (GPT-5.6 announcement, 2026-07-18 capture). 'max' is the new deepest level with GPT-5.6 — it gives even more reasoning time than 'xhigh' — and may need to be toggled on in settings in ChatGPT Work and Codex. Effort is set per model.",
```

2. **`knobs.modes.ultra` note** — replace the `"ultra": { "note": …` line's value with:

```json
      "ultra": { "note": "New with GPT-5.6: coordinates four agents in parallel by default to accelerate complex work (the API's multi-agent beta). A MODE, not a rung on the reasoning-effort ladder. CLI surface and pricing unpublished as of the 2026-07-18 capture — no flag or multiplier invented." },
```

3. **GA relaxation** — in `billing_modes.subscription.note`, replace the final sentence
   `GPT-5.6 plan inclusion is UNCONFIRMED during the limited preview (trusted partners only; broader ChatGPT/Codex/API availability 'soon' per the 2026-06-26 post).`
   with
   `GPT-5.6 is GA across ChatGPT, Codex, and the API (announcement, 2026-07-18 capture); plan-level limits remain unpublished — never fabricate an allowance.`
   And append to the END of the `"update_from"` string (one space after its final `.`):
   `GA re-confirmed 2026-07-18 against the announcement + API pricing table (Sol/Terra/Luna default rates match this file exactly; long-context step-up tiers now published — recorded in long_context_note, deliberately not yet modeled).`

4. **`long_context_note`** — insert as a new top-level key directly after the
   `"cache_note": …` line, verbatim:

```json
  "long_context_note": "Authoritative long-context step-up rates (GA API pricing table, captured 2026-07-18), NOT modeled in this file's schema — the codex estimator prices default-tier rates only, and threshold-tier modeling is a separate kit's concern. Single correctable point: GPT-5.6 Sol >272K input → $10.00/$1.00/$45.00; Terra >272K → $5.00/$0.50/$22.50; Luna >200K → $2.00/$0.20/$9.00 (input/cached-input/output per 1M tokens).",
```

Edit 5 — **the six enumeration swaps** (the ONE sanctioned edit to pre-existing bundle files;
surgical — nothing else in these files changes, `{{POLYTROPOS_ROOT}}` and all other
lines byte-intact). In BOTH `codex/prompts/route.md` AND `codex/skills/route/SKILL.md`,
replace the table row

   `| reasoning effort | \`-c model_reasoning_effort=<minimal\|low\|medium\|high\|max>\` (\`max\` is new with GPT-5.6) |`

   with

   `| reasoning effort | \`-c model_reasoning_effort=<level>\` — levels from the data's \`knobs.reasoning_efforts\` (\`max\` is the new deepest with GPT-5.6) |`

In BOTH `codex/prompts/escalate.md` AND `codex/skills/escalate/SKILL.md`, replace the phrase
(it wraps across lines — reflow the paragraph to ≤100 cols)

   `step up to \`high\`, then \`max\`, only if the check still fails — don't start at \`max\`.`

   with

   `step upward through the data's \`knobs.reasoning_efforts\` ladder one level at a time, only if the check still fails — don't start at the deepest level.`

In BOTH `codex/prompts/frontier-check.md` AND `codex/skills/frontier-check/SKILL.md`, replace
(a) the body phrase `` `-c model_reasoning_effort=<minimal|low|medium|high|max>` `` with
`` `-c model_reasoning_effort=<level>` (levels from the data's `knobs.reasoning_efforts`) ``
and (b) the table row
`| reasoning effort | \`-c model_reasoning_effort=<minimal\|low\|medium\|high\|max>\` |` with
`| reasoning effort | \`-c model_reasoning_effort=<level>\` (levels from the data's \`knobs.reasoning_efforts\`) |`.
(In the frontier-check files the enumeration may appear with or without backslash-escaped
pipes depending on table vs prose context — swap every occurrence of the literal enumeration;
after this task `grep -rn "minimal" codex/` must be EMPTY.)

**Acceptance.**
- `python3 -c "import json; p=json.load(open('data/pricing.codex.json')); assert p['knobs']['reasoning_efforts']==['minimal','low','medium','high','xhigh','max']; assert 'long_context_note' in p; assert 'GA' in p['billing_modes']['subscription']['note']; print('T2-DATA-OK')"`
  prints `T2-DATA-OK` (run it).
- No model rate value changed: `git diff data/pricing.codex.json | grep -E '^[-+].*per_mtok'`
  is empty (run it).
- `grep -rn "minimal" codex/` produces no output; `grep -rn "model_reasoning_effort" codex/`
  still matches the six edited files (the flag itself survives, only the enumeration is gone).
- Only the six named bundle files changed under `codex/` (`git status --porcelain codex/`).
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_codex_pricing.py' -v && python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v && ! grep -rn "minimal" codex/
```

---

## Phase 2 — Engine derivation surface (`knobs` subcommands)

### T3 — `bin/copilot_pricing.py knobs` subcommand + tests
- status: done
- model: sonnet
- depends: T1
- independent: no (Copilot lane)

**Brief.** Give Copilot-side consumers a runtime derivation surface for the effort ladder
(PLAN.md D6): a new `knobs [--json]` subcommand on `bin/copilot_pricing.py`, purely additive —
every existing function, signature, flag, and output stays byte-stable. Read first:
`bin/copilot_pricing.py` in full (`cmd_models`/`cmd_est`/`cmd_runway` all take
`(args, pricing)`; `build_parser` registers subparsers with `set_defaults(func=…)`; `main`
loads the real pricing and dispatches) and `tests/test_copilot_pricing.py` (fixture-dict
style; classes end before `LiveDataStructureTests`).

1. **`bin/copilot_pricing.py`** — add `cmd_knobs(args, pricing)` (docstring: prints the
   reasoning-effort facts from the pricing dict's `knobs` block; the vocabulary is DATA —
   this function never hardcodes a level list) with behavior:
   - `knobs` key absent or empty → print exactly
     `no knobs recorded in data/pricing.copilot.json` and return (exit 0) — honest, never
     invented. With `--json` → print `{}`.
   - Otherwise (text mode): print `reasoning_efforts: <v1> | <v2> | …` (file order, joined
     with ` | `), then one line per `*_note` string key in the knobs block as
     `<key>: <value>`. With `--json` → `json.dumps` the raw knobs object, indent 2.
   - Register in `build_parser`: `p_knobs = sub.add_parser("knobs", help="reasoning-effort facts from the pricing data (the level vocabulary is data, not code)")`,
     a `--json` store_true flag, `p_knobs.set_defaults(func=cmd_knobs)` — mirroring the
     existing subparsers exactly.
2. **`tests/test_copilot_pricing.py`** — ONE new class `KnobsCmdTests(unittest.TestCase)`
   appended after the last existing non-live class (before `LiveDataStructureTests`), using
   synthetic fixture dicts only (copy the house style):
   - `test_knobs_prints_efforts_and_notes`: a fixture dict with
     `{"knobs": {"reasoning_efforts": ["Alpha", "Beta"], "reasoning_efforts_note": "fake note"}}`
     → captured stdout contains `Alpha | Beta` and `fake note`.
   - `test_knobs_absent_is_honest_and_exit_0`: a fixture dict with NO `knobs` key → stdout
     contains `no knobs recorded` and no exception.
   - `test_knobs_json_round_trips`: `--json` output parses back to the fixture's knobs object.
   - Plus one live smoke in the same class: `test_knobs_real_file_smoke` calling
     `cp.main(["knobs"])` — asserts stdout contains `Extra High` (the T1-landed data) and the
     word `unconfirmed` appears case-insensitively (the headless warning survives to output).
   Every pre-existing class/method byte-intact.

**Acceptance.**
- `python3 bin/copilot_pricing.py knobs` prints the display ladder + notes;
  `python3 bin/copilot_pricing.py knobs --json` parses as JSON; `models`/`est`/`runway`
  output unchanged (`python3 bin/copilot_pricing.py est M claude-fable-5` still works).
- No hardcoded level list, price, or model id in the new code — everything from the pricing
  dict at run time.
- Only `cmd_knobs` + parser registration added to the engine; only the one new test class
  added to the test file.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_pricing.py' -v && python3 bin/copilot_pricing.py knobs
```

### T4 — `bin/codex_pricing.py knobs` subcommand + tests
- status: done
- model: sonnet
- depends: T2
- independent: no (Codex lane; parallel with T3)

**Brief.** Mirror of T3 on the Codex side, plus the `modes` notes (PLAN.md D6). Read first:
`bin/codex_pricing.py` in full (same `cmd_<name>(args, pricing)` + `build_parser` shape) and
`tests/test_codex_pricing.py` (synthetic fixture style; its fixture already carries a
`knobs.reasoning_efforts` — do not change it).

1. **`bin/codex_pricing.py`** — add `cmd_knobs(args, pricing)`:
   - Absent/empty `knobs` → print exactly `no knobs recorded in data/pricing.codex.json`,
     exit 0 (`--json` → `{}`).
   - Text mode: `reasoning_efforts: <v1> | <v2> | …` (file order), then every `*_note` string
     key in the knobs block as `<key>: <value>`, then — if a `modes` object exists — one line
     per mode as `mode <name>: <its note>` (never a flag; the notes say the surfaces are
     unpublished, relay them verbatim). `--json` → the raw knobs object, indent 2.
   - Register `knobs` in `build_parser` with `--json`, mirroring `plans`.
2. **`tests/test_codex_pricing.py`** — ONE new class `KnobsCmdTests(unittest.TestCase)`
   appended after the last non-live class, synthetic fixtures only:
   - `test_knobs_prints_efforts_notes_and_modes`: fixture
     `{"knobs": {"reasoning_efforts": ["aa", "bb"], "reasoning_efforts_note": "fake note", "modes": {"fakemode": {"note": "fake mode note"}}}}`
     → stdout contains `aa | bb`, `fake note`, and `mode fakemode: fake mode note`.
   - `test_knobs_absent_is_honest_and_exit_0`: no `knobs` key → stdout contains
     `no knobs recorded`, no exception.
   - `test_knobs_json_round_trips`: `--json` round-trips the fixture knobs object.
   - `test_knobs_real_file_smoke`: `cx.main(["knobs"])` → stdout contains `xhigh` (the
     T2-landed correction) and `ultra` (the mode note is relayed).
   Every pre-existing class/method byte-intact.

**Acceptance.**
- `python3 bin/codex_pricing.py knobs` prints the six-token ladder + notes + both mode lines;
  `--json` parses; `models`/`est`/`plans` output unchanged.
- No hardcoded level list, price, or model id in new code; only the additive engine + test
  edits.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_codex_pricing.py' -v && python3 bin/codex_pricing.py knobs
```

---

## Phase 3 — Bundles (atomic per harness)

### T5 — Copilot `effort` agent (manifest + bundle + tests, atomic)
- status: done
- model: sonnet
- depends: T1, T3
- independent: no (Copilot lane)

**Brief.** The user-facing Copilot surface for the dial (PLAN.md D2/D7/D8): a custom agent
named `effort` that teaches Copilot's REAL mechanism — the interactive per-model "Reasoning"
setting — and is honest about what does not exist (no headless flag). Read first:
`tests/test_copilot_bundle.py` (seams + sweeps), `copilot/.github/agents/route.agent.md`
(house format/voice + the AIC-are-money framing), PLAN.md's Ground truth (the picker facts
you will teach), and `bin/copilot_pricing.py`'s argparse surface (`knobs`, `models`, `est`,
`runway` — quote no other flags).

Three files, one atomic change (the roster test is set equality):

1. **`copilot/aesop.yaml`** — in `primitives:` → `agents:`, append `- effort` after
   `- escalate`, matching the existing entries' exact indentation. Nothing else.
2. **`copilot/.github/agents/effort.agent.md`** — new file, house format (frontmatter `name`,
   `description`, `model`, then body):
   - `name: effort`.
   - `description:` one sentence: control the reasoning-effort dial for Copilot models —
     Copilot's per-model "Reasoning" setting: see which models have it, set it, and decide
     when to turn it up or down; use when the user asks to raise/lower reasoning effort, run
     at extra-high, or make a model think harder or cheaper.
   - `model:` a LIVE **mid-tier** model id — open `data/pricing.copilot.json` and take the
     FIRST model in file order whose `tier` is `"mid"`. Copy the id from the data at
     implementation time (the ONE sanctioned model-id literal; never frontier).
   - Body (~50–80 lines, route.agent.md's voice):
     - **Get the ladder from data — never from memory**: run
       `python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py knobs` for the confirmed
       level names and mechanism notes (the vocabulary lives in the data's
       `knobs.reasoning_efforts` — Copilot uses Title-Case display words, and they are NOT
       the lowercase tokens other CLIs use; never enumerate the ladder from memory in your
       answer — relay what `knobs` prints).
     - **The mechanism (the only confirmed one)**: reasoning effort is set INTERACTIVELY in
       the `/model` picker — select the model row, then use the left/right arrow keys (the
       picker footer says `←/→ reasoning effort`); it is per-model, and models showing `—`
       in the Reasoning column have no dial (the knobs note lists the observed sets — GPT-5.6
       Sol/Terra/Luna all have it, defaulting to Medium). State plainly: NO headless surface
       (a `copilot -p` flag or settings key) is unconfirmed-to-exist — if the user needs
       effort in a scripted run, say the limitation honestly and point at the correctable
       point in the pricing data's knobs note; NEVER quote a flag for it.
     - **When to turn it up/down** (D1 guidance): leave the default for routine work; step UP
       one level at a time only on concrete failure evidence (a wrong answer, a missed
       constraint) — don't start at the top; step DOWN for bulk/latency-sensitive work.
       Higher effort makes the model think longer and emit more tokens, and AIC are money —
       each credit costs `billing_unit.usd_per_credit`; estimate the stakes with
       `python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py est <PROFILE> <MODEL_ID>`
       and note the estimate is per-run token volume, which effort inflates.
     - **Relationship to model choice**: the dial is orthogonal to picking a model — for
       "which model" use the `route` agent; for verify-gated tier climbing use `escalate`.
       Turning effort up on the current model is often cheaper than jumping a tier; a tier
       jump is for capability gaps, not thinking-time gaps.
     - Close with the placeholder paragraph mirroring route.agent.md's (if the literal
       `{{POLYTROPOS_ROOT}}` text is visible, run
       `python3 bin/harness_select.py install --harness copilot`).
   - The body must NOT contain: any key of `data/pricing.copilot.json`'s `models` (hand-check
     — frontmatter pin excepted), the strings `--effort` or `model_reasoning_effort` (Codex's
     surface — test-enforced absent), any absolute path, `CLAUDE_PLUGIN_ROOT`, or
     `data/pricing.json`/`data/pricing.codex.json` mentions.
3. **`tests/test_copilot_bundle.py`** — two additive edits, nothing else changed:
   - Add `"effort": "mid",` to the `WORKFLOW_AGENT_TIERS` dict.
   - Add a NEW class `EffortAgentContractTests(unittest.TestCase)` after
     `PortedAgentContractTests`, with the same `_text(self, stem)` helper shape and four
     methods:
     - `test_effort_derives_ladder_from_knobs`: asserts `"bin/copilot_pricing.py"` and
       `"knobs"` in `self._text("effort")`.
     - `test_effort_teaches_interactive_picker`: asserts `"/model"` in the text and
       `"arrow"` in `self._text("effort").lower()`.
     - `test_effort_headless_honesty`: asserts `"unconfirmed"` in
       `self._text("effort").lower()`.
     - `test_effort_no_borrowed_or_invented_flag`: asserts `"--effort"` NOT in the text and
       `"model_reasoning_effort"` NOT in the text.

**Acceptance.**
- Manifest agents block lists exactly ten names ending `- effort`; agent file in house format;
  frontmatter `model:` is a live mid-tier pricing key; all four new contract methods pass; the
  pre-existing sweeps (placeholder, absolute-path, harness separation, ModelPinLive) pass over
  the new file; only the pinned dict entry + new class added to the test file.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T6 — Codex `effort` prompt + skill (bundle + both roster seams, atomic)
- status: done
- model: sonnet
- depends: T2, T4
- independent: no (Codex lane; parallel with T5)

**Brief.** The Codex-side first-class surface (PLAN.md D7/D8): a prompt
`codex/prompts/effort.md` plus its desktop-app skill mirror `codex/skills/effort/SKILL.md` —
Codex already HAS the dial (`-c model_reasoning_effort=`, `codex_execute.py --effort`), so
these files SURFACE it; they re-implement nothing. Read first: `tests/test_codex_bundle.py`
(both stem sets + which sweeps iterate them), `codex/prompts/route.md` (voice +
billing-mode-first honesty), `codex/prompts/escalate.md` post-T2 (the ladder-stepping prose
you must stay consistent with), and `bin/codex_pricing.py` (`knobs`) + `bin/codex_execute.py`
(`--effort` validates against the data's knobs at run time) argparse surfaces.

Three files + one test file, one atomic change:

1. **`codex/prompts/effort.md`** — new file, description-only frontmatter (NO `model:` line —
   test-enforced). `description:` one sentence: control the GPT-5.6 reasoning-effort dial per
   run — pick the right level, apply it, and step it up only on failure evidence; use when the
   user asks to raise/lower reasoning effort, run at max, or make a run think harder or
   cheaper. Body (~50–80 lines, route.md's voice):
   - **Billing mode FIRST** (mirror route.md): effort drives usage-limit burn under a ChatGPT
     plan — any dollar figure is a labeled API-equivalent proxy, never a bill; real dollars
     only under `OPENAI_API_KEY`. Deeper effort = more reasoning tokens = faster burn either way.
   - **Get the ladder from data**: run
     `python3 {{POLYTROPOS_ROOT}}/bin/codex_pricing.py knobs` — the vocabulary lives in
     the data's `knobs.reasoning_efforts` (ascending; the note carries which level is newest
     and any settings toggle) — never enumerate levels from memory; relay what `knobs` prints.
     The `mode` lines it prints (`ultra`, `fast`) are MODES with unpublished CLI surfaces —
     relay their notes, never invent a flag for them.
   - **Apply it**: per run, `-c model_reasoning_effort=<level>` on `codex exec` (the one
     confirmed surface — copy the form from the route prompt's mechanism table); for kit
     tasks, `python3 {{POLYTROPOS_ROOT}}/bin/codex_execute.py run --kit <dir> --task <id> --effort <level>`
     — the driver validates the level against the data's knobs at run time and rejects
     unknown words.
   - **Choose the level** (D1 guidance): omit the override for routine work (the configured
     default applies); the low end is for bulk/extraction/latency-sensitive work; step UP one
     level at a time only on concrete failure evidence — don't start at the deepest level
     (consistent with the escalate prompt's ladder-stepping rule). Effort is per-model and
     orthogonal to model choice: tier jumps are for capability gaps (`/route`, `/escalate`),
     effort for thinking-time gaps — turning effort up on the current model is usually the
     cheaper first move.
   - Placeholder paragraph (`install --harness codex`).
   - Must NOT contain: any real `data/pricing.codex.json` model id, "fable" in any case, an
     enumeration of the level tokens (the word `minimal` must not appear — T2's sweep stays
     clean), absolute paths, or another harness's pricing path (all swept by existing tests).
2. **`codex/skills/effort/SKILL.md`** — new dir + file: frontmatter exactly `name: effort`,
   `description:` (same sentence), NO `model:` line; body mirrors the prompt's sections
   (the skill sweeps — placeholder, no-fable, frontmatter — iterate `EXPECTED_SKILL_STEMS`
   and will cover it automatically).
3. **`tests/test_codex_bundle.py`** — additive edits at pinned seams, nothing else changed:
   - `EXPECTED_PROMPT_STEMS = {"route", "architect", "implementer", "verifier", "reviewer"} | set(PORTED_PROMPT_STEMS)`
     → append ` | {"effort"}` (do NOT touch `PORTED_PROMPT_STEMS` — effort is not a port;
     PLAN.md D7).
   - `EXPECTED_SKILL_STEMS = set(PORTED_SKILL_STEMS) | set(WORKFLOW_SKILL_STEMS)` → append
     ` | {"effort"}` (do NOT touch the two skill-stem tuples).
   - Add TWO new classes after `PortedPromptContractTests` /
     `WorkflowSkillContractTests` respectively:
     - `EffortPromptContractTests(unittest.TestCase)` with `_text` reading
       `CODEX_PROMPTS_DIR / "effort.md"` and three methods:
       `test_effort_derives_ladder_from_knobs` (asserts `"bin/codex_pricing.py"` and
       `"knobs"` in the text), `test_effort_quotes_real_flag_and_driver` (asserts
       `"model_reasoning_effort"`, `"bin/codex_execute.py"`, and `"--effort"` in the text),
       and `test_effort_no_level_enumeration` (asserts `"minimal"` NOT in the text).
     - `EffortSkillContractTests(unittest.TestCase)` with `_text` reading
       `CODEX_SKILLS_DIR / "effort" / "SKILL.md"` and the same three methods against the
       skill text.

**Acceptance.**
- Prompt + skill exist in house format; roster tests pass over the ten-stem prompt set and
  seven-stem skill set; `FrontmatterDisciplineTests`/`SkillFrontmatterTests`,
  `NoHardcodedRosterTests`, the placeholder and no-fable sweeps, and `HarnessSeparationTests`
  all green over the new files; `grep -rn "minimal" codex/` still empty; only the pinned seam
  edits in the test file.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v && ! grep -rn "minimal" codex/
```

---

## Phase 4 — Closeout

### T7 — Instruction surfaces: one pinned sentence per harness (manifest-first)
- status: done
- model: haiku
- depends: T5, T6
- independent: no

**Brief.** Make the effort surface discoverable from each harness's instructions. Three
append-only edits with PINNED content — reproduce each verbatim; if an anchor is absent, STOP
and report.

1. **`copilot/aesop.yaml`** — inside `primitives.instructions.blocks[0].content: |`, after
   the existing line beginning `Beyond routing, four ported agents`, append this line at the
   SAME indentation as the block's other content lines:

   `The effort agent controls the reasoning-effort dial: Copilot's "Reasoning" setting is adjusted interactively in the /model picker with the left/right arrow keys (a per-model property — rows showing a dash have no dial; no headless flag is confirmed), and the level names are derived at run time from the pricing data's knobs, never from memory.`

2. **`copilot/.github/copilot-instructions.md`** — append the SAME sentence verbatim as a new
   final paragraph (blank line before it).
3. **`codex/AGENTS.md`** — append this paragraph verbatim as a new final paragraph (blank
   line before it):

   `The /effort prompt makes the reasoning-effort dial a first-class surface: levels come at run time from the pricing data's knobs.reasoning_efforts (never from memory), are applied per run via the -c model_reasoning_effort=<level> override (or --effort on bin/codex_execute.py kit runs), and are stepped up one level at a time only on failure evidence — deeper effort burns subscription usage faster, and any dollar figure shown for it is a labeled API-equivalent proxy, never a bill.`

The two doctrine sentences (one per harness, byte-verbatim test-enforced) must be untouched —
these are pure appends changing no existing line.

**Acceptance.** All three surfaces carry their pinned text exactly once; every pre-existing
line byte-identical; both bundle test files green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_co*_bundle.py' -v
```

### T8 — `docs/EFFORT-DIAL.md`
- status: done
- model: sonnet
- depends: T5, T6
- independent: yes (parallel with T7)

**Brief.** One new doc recording the cross-harness contract and the open-items ledger, so the
remaining unknowns are findable without this kit's history. New file `docs/EFFORT-DIAL.md`
(~60–100 lines), sections:

1. **The contract** — the effort dial is the GPT-5.6 reasoning ladder; each harness's
   vocabulary lives ONLY in its own pricing file's `knobs.reasoning_efforts`, derived at run
   time (`copilot_pricing.py knobs` / `codex_pricing.py knobs`), never hardcoded; the two
   vocabularies (Codex lowercase tokens vs Copilot Title-Case display forms) never mix.
2. **Per-harness mechanism table** — Codex: `-c model_reasoning_effort=<level>` on
   `codex exec` + `codex_execute.py run --effort <level>` (validated against knobs), confirmed.
   Copilot: interactive `/model` picker, ←/→ on the selected row, per-model (rows showing `—`
   have no dial), headless surface UNCONFIRMED — no flag exists to quote. Claude Code: out of
   scope here (managed in-model).
3. **Guidance** — omit the dial for routine work; step up one level at a time on failure
   evidence only; low end for bulk/latency; effort is orthogonal to model choice (tier jumps =
   capability gaps). Burn honesty: Codex subscription figures are labeled API-equivalent
   proxies, never bills; Copilot AIC are real money.
4. **Data provenance (2026-07-18 captures)** — announcement PDF (token ladder incl. `xhigh`,
   `max` deepest, ultra = a four-agent MODE not a level, GA), Copilot picker screenshots
   (Reasoning column mechanism, Sol cost panel 500/3,000/50/625 credits per 1M), API pricing
   table (default rates match `pricing.codex.json`; long-context tiers recorded as a note only).
5. **Open items ledger** — mirror PLAN.md's Deferred list: each open item + its single
   correctable point (Copilot headless surface → the copilot knobs note; Terra/Luna AIC →
   their `rates_assumed_note`s; unobserved display renderings → the knobs note; long-context
   schema modeling → `long_context_note`; ultra/fast CLI surfaces → the `modes` notes; the
   Copilot roster refresh; best-effort ids → each `model_ids_note`).

House doc voice (see `docs/ROUTING-HISTORY.md` for tone). The doc may name the two confirmed
picker display words and the token ladder AS PROVENANCE FACTS tied to the 2026-07-18 capture
(a labeled snapshot, like README pricing tables) but must state the pricing files are the
live source. No other file changes.

**Acceptance.** Doc exists with all five sections; names both `knobs` run-lines; labels every
open item with its correctable point; no edits to any other file.

**Verify.**
```bash
test -f docs/EFFORT-DIAL.md && grep -q "knobs.reasoning_efforts" docs/EFFORT-DIAL.md && grep -q "model_reasoning_effort" docs/EFFORT-DIAL.md && grep -qi "unconfirmed" docs/EFFORT-DIAL.md && echo DOC-OK
```

### T9 — Full-suite + frozen-surface audit
- status: done
- model: haiku
- depends: T7, T8
- independent: no

**Brief.** Final gate. Run and report, in order:

1. `python3 -m unittest discover -s tests -v` — fully green.
2. `git diff --quiet -- data/pricing.json skills .claude-plugin README.md bin/copilot_execute.py bin/codex_execute.py bin/harness_select.py && echo FROZEN-CLEAN`
   — must print `FROZEN-CLEAN`.
3. `git status --porcelain` — the changed/untracked set must be EXACTLY:
   `data/pricing.copilot.json`, `data/pricing.codex.json`, `bin/copilot_pricing.py`,
   `bin/codex_pricing.py`, `tests/test_copilot_pricing.py`, `tests/test_codex_pricing.py`,
   `tests/test_copilot_bundle.py`, `tests/test_codex_bundle.py`, `copilot/aesop.yaml`,
   `copilot/.github/copilot-instructions.md`, `codex/AGENTS.md`, the six T2-swapped bundle
   files, the four new files (`copilot/.github/agents/effort.agent.md`,
   `codex/prompts/effort.md`, `codex/skills/effort/SKILL.md`, `docs/EFFORT-DIAL.md`), and
   this kit's own files (`.claude/kits/effort-dial/`, `.claude/agents/effort-dial-*.md`, the
   CLAUDE.md append). Flag ANYTHING else.
4. Leak/honesty sweeps (each must produce NO matches):
   - `grep -rn "/Users/\|/home/" copilot/.github codex`
   - `grep -rn "CLAUDE_PLUGIN_ROOT" copilot/.github codex`
   - `grep -rni "fable" codex`
   - `grep -rn "minimal" codex/`
   - `grep -rn "model_reasoning_effort\|--effort" copilot/`
   - `grep -rn "Extra High\|xhigh" copilot/.github/agents/effort.agent.md codex/prompts/effort.md codex/skills/effort/SKILL.md`
     (the new bundle bodies derive the ladder — they must not enumerate it)
5. Ladder-stability probe (file-order invariant, PLAN.md D5):
   `python3 -c "import json; m=json.load(open('data/pricing.copilot.json'))['models']; first=lambda t: next(k for k,v in m.items() if v['tier']==t); print(first('cheap'), first('mid'), first('strong'), first('frontier'))"`
   — must print `claude-haiku-4.5 claude-sonnet-5 claude-opus-4.8 claude-fable-5`.
6. Confirm `python3 bin/copilot_pricing.py knobs` and `python3 bin/codex_pricing.py knobs`
   both run clean, and the Copilot manifest agents block and `.agent.md` stems both list ten
   names.

Report each command's actual output. Any failure, unexplained file, or sweep hit means
`blocked` with the evidence — do not fix things yourself.

**Acceptance.** All six checks pass with outputs shown verbatim.

**Verify.**
```bash
python3 -m unittest discover -s tests -v
```
