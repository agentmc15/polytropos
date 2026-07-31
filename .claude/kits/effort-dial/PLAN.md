# PLAN — effort-dial

Make the GPT-5.6 reasoning-effort dial (`minimal → … → max`) a first-class, honest surface on
BOTH non-Claude harnesses. The Codex side already has the machinery (`knobs.reasoning_efforts`
in `data/pricing.codex.json`, `bin/codex_execute.py --effort` → `-c model_reasoning_effort=`,
effort prose in route/escalate/frontier-check) — there the work is a data correction, a `knobs`
derivation surface, and a dedicated `effort` prompt+skill. The Copilot side had NO effort
concept and no GPT-5.6 models; the user has now supplied authoritative captures (live `/model`
picker screenshots, the GPT-5.6 announcement PDF, the API pricing table, and GitHub's Copilot
"Models and pricing" doc — all 2026-07-18) that make it buildable: GPT-5.6 Sol/Terra/Luna are
in Copilot's `/model`, effort is Copilot's per-model "Reasoning" column set INTERACTIVELY with
the ←/→ arrow keys, and all three models' AI-Credit rates are confirmed. Everything not
directly captured stays labeled with a single correctable point — nothing is invented.

autonomy: advisory

## Goal

The effort dial exists on both harnesses to the extent each CLI truthfully supports it: the
level vocabulary lives ONLY in each pricing file's `knobs.reasoning_efforts` (derived at run
time via new `knobs` engine subcommands, never hardcoded), a new `effort` bundle capability
lands on each harness atomically with its test seams, the confirmed Copilot GPT-5.6 facts land
in `data/pricing.copilot.json` with unconfirmed remainders clearly labeled, and the stale
Codex ladder (`xhigh` missing) is corrected with dependent prose de-hardcoded.

**Done looks like:**

1. `data/pricing.codex.json` `knobs.reasoning_efforts` is exactly
   `["minimal","low","medium","high","xhigh","max"]` (the announcement-confirmed ladder), its
   notes reflect GA + the ultra-is-a-mode-not-a-level fact, and a `long_context_note` records
   the authoritative step-up rates WITHOUT schema modeling. No model rate value changed.
2. `data/pricing.copilot.json` carries a `knobs` block (display-form ladder
   `["Minimal","Low","Medium","High","Extra High","Max"]`, interactive-picker mechanism,
   headless-unconfirmed warning), a labeled `long_context_note`, and three appended GPT-5.6
   rows with CONFIRMED rates (Sol: picker panel + GitHub doc; Terra/Luna: the GitHub
   "Models and pricing" doc). `tests/test_copilot_pricing.py`'s live-structure tests stay
   green.
3. `bin/copilot_pricing.py knobs` and `bin/codex_pricing.py knobs` print each file's effort
   facts honestly (absent knobs → an honest line, exit 0), additively — every pre-existing
   flag, function signature, and output byte-stable; new tests in the two pricing test files.
4. `copilot/.github/agents/effort.agent.md` (+ manifest entry + `WORKFLOW_AGENT_TIERS` +
   `EffortAgentContractTests`) and `codex/prompts/effort.md` + `codex/skills/effort/SKILL.md`
   (+ the `EXPECTED_PROMPT_STEMS`/`EXPECTED_SKILL_STEMS` unions + contract classes) land
   atomically; suite green at every task boundary.
5. The literal enumeration `minimal\|low\|medium\|high\|max` is GONE from every file under
   `codex/` (`grep -rn "minimal" codex/` is empty) — the six pre-existing files that hardcoded
   it now say "levels from the data's `knobs.reasoning_efforts`".
6. No invented flag or id ships: no Copilot headless effort flag anywhere (`--effort` and
   `model_reasoning_effort` appear in NO file under `copilot/`), `bin/copilot_execute.py` and
   `bin/codex_execute.py` byte-untouched, no `ultra`/`fast` flag anywhere.
7. `python3 -m unittest discover -s tests -v` fully green;
   `git diff --quiet -- data/pricing.json skills .claude-plugin README.md bin/copilot_execute.py bin/codex_execute.py bin/harness_select.py` exits 0.
8. Subscription honesty preserved: Codex effort prose keeps the labeled API-equivalent-proxy
   framing (never a bill); Copilot prose keeps AIC-are-real-money framing.

## Ground truth (captured 2026-07-18; pinned so no executor needs the conversation)

**The confirmed effort ladder (GPT-5.6 announcement PDF, authoritative).** Ascending tokens:
`minimal | low | medium | high | xhigh | max`. `max` is the new deepest level — "gives GPT-5.6
even more time than `xhigh` to reason and explore alternatives"; `max` may need to be toggled
on in settings in ChatGPT Work and Codex. Effort is set per model. GPT-5.6 (Sol/Terra/Luna) is
GA across ChatGPT, Codex, and the API. `ultra` is a MODE, not an effort level: it coordinates
four agents in parallel by default (the API's multi-agent beta); its CLI surface is
unpublished — no flag exists to quote. Codex fast mode likewise unpublished.

**Copilot CLI live `/model` picker (user screenshots).** GPT-5.6 Sol / Terra / Luna ARE listed
(display names "GPT-5.6 Sol" etc. — the repo's 2026-07-01 roster capture is stale on this
point). The picker has a "Reasoning" column adjusted INTERACTIVELY with the ←/→ arrow keys on
the selected row (footer literally: "↑/↓ to navigate · ←/→ reasoning effort · tab context
window · enter to select · esc to cancel"). Reasoning is a BROAD per-model picker property,
not GPT-5.6-only — from the complete roster capture: rows showing "—" (NO reasoning control):
Auto, Claude Sonnet 4.5, Claude Haiku 4.5, Claude Opus 4.5, Kimi K2.7 Code; every other
observed row carries a Reasoning value defaulting to "Medium" — GPT-5.6 Sol (cycled up to
"Extra High"), GPT-5.6 Terra/Luna, GPT-5.5, GPT-5.4, GPT-5.3-Codex, GPT-5.4 mini, GPT-5 mini,
Gemini 3.1 Pro, Gemini 3.5 Flash, MAI-Code-1-Flash, Claude Sonnet 5/4.6, Opus 4.8 (+fast
mode)/4.7/4.6, Fable 5. So the user's targets (Sol/Terra/Luna) are all reasoning-capable, and
the effort agent must say the dial applies only to models showing a Reasoning value (not "—").
"Medium"/"Extra High" map to tokens `medium`/`xhigh`; the picker renders Title-Case display
forms of the token ladder (the other four display renderings are mapped, not yet directly
observed — labeled accordingly). NO headless surface (a `copilot -p` flag or settings key) is
confirmed — the screenshots show only the interactive mechanism. The full roster also surfaces
models NOT yet in `data/pricing.copilot.json` (e.g. Gemini 3.5 Flash-adjacent rows, Fable-5
row naming, fast-mode previews) — that reconciliation is explicitly NOT this kit (see
Deferred); only the three GPT-5.6 rows land.

**Copilot AIC pricing for GPT-5.6 — CONFIRMED (GitHub "Models and pricing" doc + Sol's picker
cost panel, both 2026-07-18).** The doc confirms 1 AI credit = $0.01 and quotes Copilot rates
in USD; for GPT-5.6 the Copilot USD equals OpenAI's API USD (pass-through). Default tier, USD
per 1M tokens (credits = ×100): Sol $5.00 in / $0.50 cached / $30.00 out (500/50/3,000
credits — matching Sol's picker panel exactly, incl. cache write 625 credits = 1.25× input);
Terra $2.50 / $0.25 / $15.00 (250/25/1,500); Luna $1.00 / $0.10 / $6.00 (100/10/600). Cache
writes bill at 1.25× uncached input (Sol's captured 6.25 $/mtok; not stored per-model on
Terra/Luna — the 1.25× fact lives in their notes). Copilot long-context step-up tiers for
GPT-5.6 exist (Sol/Terra >272K → $10/$1/$45 and $5/$0.50/$22.50; Luna >200K → $2/$0.20/$9) —
recorded as a labeled NOTE only, not modeled in this kit. Context windows (capability facts):
Sol 400K (tab toggles 1.1M), Terra 400K, Luna 328K.

**Authoritative API USD table (per 1M tokens, GA).** Sol $5.00/$0.50/$30.00 (in/cached/out),
Terra $2.50/$0.25/$15.00, Luna $1.00/$0.10/$6.00 — matching `data/pricing.codex.json`'s
existing default rates EXACTLY (no rate edits needed). Long-context step-up tiers now
published: Sol >272K → $10/$1/$45; Terra >272K → $5/$0.50/$22.50; Luna >200K → $2/$0.20/$9.
Cache: writes 1.25× uncached input, reads 0.1×, 30-min min life (already modeled).

**Repo mechanics (verified in-tree).** `tests/test_copilot_pricing.py`
`LiveDataStructureTests.test_every_model_has_required_positive_fields` requires POSITIVE
numeric `input_per_mtok`/`cached_input_per_mtok`/`output_per_mtok` and a four-vocabulary tier
on EVERY real model row — so Terra/Luna cannot land rate-less or null. Tier resolution and the
escalation ladder take the FIRST model in pricing-file order per tier
(`copilot_execute.escalation_ladder`, `codex_execute.resolve_tier`) — appending the GPT-5.6
rows at the END of the models object keeps every existing resolution byte-stable. Both pricing
engines' subcommands are `cmd_<name>(args, pricing)` functions registered in `build_parser`;
tests use synthetic fixture dicts plus real-file smoke tests that derive expectations
dynamically (adding models/knobs breaks nothing). All effort-related tests
(`test_codex_execute.py`, `test_codex_pricing.py`) use synthetic knobs fixtures — the `xhigh`
correction is invisible to them. The codex bundle tests sweep every file under `codex/` for
real model ids and the string "fable"; `PortedSkillContractTests` and `SkillFrontmatterTests`
iterate `EXPECTED_SKILL_STEMS`, so a new codex skill is auto-swept (placeholder, no-fable,
name/description/no-model frontmatter) once its stem is added. `bin/harness_select.py` globs
`*.agent.md` / `codex/prompts/*.md` / `codex/skills/*/` — new bundle files install with zero
installer changes. Six pre-existing codex bundle files hardcode the (now-wrong) enumeration
`<minimal\|low\|medium\|high\|max>`: `codex/prompts/{route,escalate,frontier-check}.md` and
`codex/skills/{route,escalate,frontier-check}/SKILL.md`.

## Decisions

- **D1 — The shared effort-dial contract: vocabulary is DATA, per harness, never mixed.** Each
  harness's ladder lives ONLY in its own pricing file's `knobs.reasoning_efforts`: Codex
  carries the lowercase API tokens (`minimal…xhigh…max`, used verbatim in
  `-c model_reasoning_effort=<level>`); Copilot carries the Title-Case DISPLAY forms
  (`Minimal…Extra High…Max`, what the picker shows). The two vocabularies never appear in the
  other harness's files. Bundle bodies and scripts derive the list at run time (via the new
  `knobs` subcommands) and never enumerate it as authoritative prose — the announcement facts
  ("max is deepest", "per-model") live in the data's notes, quoted from there. Default
  guidance everywhere: omit the dial for routine work (the harness default applies — observed
  "Medium" on Copilot), step UP only on failure evidence, never start at the top; deeper
  effort = more output tokens = more subscription-limit burn (Codex: labeled API-equivalent
  proxy, never a bill) or more AI Credits (Copilot: real money).
- **D2 — The Copilot-vs-Codex mechanism asymmetry is the load-bearing honesty line.** Codex:
  a confirmed headless flag (`-c model_reasoning_effort=<level>`; `codex_execute.py --effort`
  already validates against knobs at run time). Copilot: an INTERACTIVE, per-model picker
  setting (←/→ on the `/model` row) — no headless flag is confirmed, so the Copilot bundle
  teaches the picker mechanism, states the headless gap explicitly ("unconfirmed"), and
  `bin/copilot_execute.py` is BYTE-UNTOUCHED (wiring a dispatch flag that doesn't exist would
  be fabrication; if a headless surface ships, the knobs note is the single correctable point
  and a future kit extends the driver).
- **D3 — Codex data correction: add `xhigh`, relax to GA, record long-context as a note.**
  `knobs.reasoning_efforts` gains `xhigh` between `high` and `max` (announcement-confirmed —
  the current list is simply wrong), the notes gain the GA + max-toggle + ultra-is-four-agents
  facts, and the authoritative long-context step-up rates land in a new `long_context_note`
  string — NOT as schema (the codex estimator has no threshold-tier support; bolting a schema
  change onto this kit would couple two unrelated risks — deliberately out of scope, single
  correctable point recorded). No model rate values change (the table matched exactly).
- **D4 — Fixing the data obligates de-hardcoding the six stale enumerations.** Pricing files
  are the single source of truth; leaving `<minimal\|low\|medium\|high\|max>` in shipped codex
  bundle prose after the data says six levels would make prose contradict data. The six files
  get pinned, surgical swaps to `<level>` + "levels from the data's `knobs.reasoning_efforts`"
  — the ONE sanctioned edit to pre-existing bundle files, landed in the same task as the data
  fix so data and prose are never inconsistent at a task boundary. Post-condition:
  `grep -rn "minimal" codex/` is empty.
- **D5 — Copilot data: all three GPT-5.6 rows land CONFIRMED, appended at the end.**
  `gpt-5.6-sol` (tier `strong` — Fable 5 stays the sole Copilot frontier; Sol prices beside
  GPT-5.5) carries the doubly-confirmed rates (picker panel + GitHub doc), incl.
  `cache_write_per_mtok` 6.25. `gpt-5.6-terra` (mid, 2.5/0.25/15.0) and `gpt-5.6-luna`
  (cheap, 1.0/0.1/6.0) carry the GitHub-doc-confirmed rates — no UNCONFIRMED/derived label
  needed; their notes cite the doc and carry the 1.25×-input cache-write fact instead of a
  fractional per-model `cache_write_per_mtok` (3.125/1.25 are derived values the estimator
  never uses — the doc fact lives in prose). No `long_context` sub-objects: the GPT-5.6
  Copilot step-up tiers are recorded in a new top-level `long_context_note` (labeled, single
  correctable point) — modeling them is deliberately out of scope even though the schema
  could, to keep this kit's data change minimal and reviewable. All three rows append at the
  END of the models object so first-in-file-order tier resolution and every escalation ladder
  stay byte-stable. `model_ids_note` gains a "partial refresh 2026-07-18" sentence: ids are
  best-effort lowercase-dot (`gpt-5.6-sol`) per the `gpt-5.4` precedent, display names as
  shown, full roster re-verify still pending — `cached_date` stays 2026-07-01 because it dates
  the last FULL-roster verification (bumping it would falsely imply the other 19 rows were
  re-verified; the new rows carry their own capture dates in their notes, and README/docs
  snapshot tables stay honestly tied to the old date and untouched).
- **D6 — A `knobs` subcommand on both pricing engines is the runtime derivation surface.**
  Bundles must derive the ladder at run time; today nothing exposes `knobs` except raw JSON.
  Each engine gains `cmd_knobs(args, pricing)` + a `knobs [--json]` subparser (mirroring
  `plans`/`runway` registration): print `reasoning_efforts` in order plus every note string in
  the knobs block (Codex also its `modes` notes); knobs absent → one honest line
  ("no knobs recorded in <file>"), exit 0 — never a crash, never an invented list. Purely
  additive: no existing function, flag, or output changes.
- **D7 — The bundle capability is named `effort` on both harnesses.** Copilot: an AGENT
  (manifest `- effort` + `effort.agent.md` + `WORKFLOW_AGENT_TIERS` `"effort": "mid"` +
  `EffortAgentContractTests`, one atomic task — set-equality roster). Body leads with
  Copilot's own on-screen word ("Reasoning") and teaches the interactive mechanism; its
  frontmatter `model:` pin is the ONE sanctioned model-id literal (first mid-tier model in
  file order, read from the data at implementation time — never frontier). Codex: a PROMPT
  plus its desktop-app SKILL mirror (`codex/prompts/effort.md` + `codex/skills/effort/SKILL.md`
  + both stem-set unions + `EffortPromptContractTests`/`EffortSkillContractTests`, one atomic
  task). `effort` is deliberately NOT added to `PORTED_PROMPT_STEMS`/`PORTED_SKILL_STEMS` —
  those tuples mean "ported from a Claude skill", and no Claude `effort` skill exists (the
  Claude side manages effort in-model; a Claude-side port is out of scope). Union `{"effort"}`
  into the EXPECTED sets instead.
- **D8 — Honesty tripwires are contract-tested, not just prose.** Copilot:
  `EffortAgentContractTests` asserts the body mentions `bin/copilot_pricing.py` + `knobs` +
  `/model` + an arrow-keys reference, contains the word "unconfirmed" (the headless gap), and
  contains NEITHER `--effort` NOR `model_reasoning_effort` (no invented/borrowed flag). Codex:
  `EffortPromptContractTests`/`EffortSkillContractTests` assert `bin/codex_pricing.py` +
  `knobs` + `model_reasoning_effort` + `bin/codex_execute.py` + `--effort` + placeholder + no
  "fable"; the pre-existing roster/frontmatter/no-model-id/no-absolute-path sweeps cover the
  rest automatically once the stems are added.
- **D9 — Executor pins: sonnet authors, haiku for verbatim closeout; no opus task.** Routing
  history (16 kits, 79/80 first-try; haiku 14/14, sonnet 48/49, opus 17/17) shows pinned-brief
  authoring runs clean on sonnet — the hard judgment (the asymmetry, the labeling language,
  the exact JSON blocks and test seams) is pre-made and pinned verbatim in the briefs, which
  is exactly the shape harness-parity ran 10/10 first-try on. Haiku takes the pinned-verbatim
  instruction inserts (T7) and the final audit (T9). The per-task escalation valve and the
  opus phase reviewer cover surprises.
- **D10 — Instruction surfaces get one pinned sentence each, manifest-first; one doc.** The
  Copilot sentence lands in `copilot/aesop.yaml`'s instructions block AND verbatim in
  `copilot/.github/copilot-instructions.md`; the Codex paragraph in `codex/AGENTS.md`.
  Append-only; both doctrine sentences stay byte-intact. `docs/EFFORT-DIAL.md` records the
  cross-harness contract, the unit separation, and the open-items ledger (each with its single
  correctable point) so the remaining unknowns are findable without this kit's history.

## OUT-OF-SCOPE fence (do NOT build)

- **The dial is the reasoning-effort ladder ONLY.** No `ultra`/multi-agent or `fast` mode work
  — their CLI surfaces are unpublished; no flag, multiplier, or price invented (the data's
  `modes` notes are the only place they exist). No model-variant-selection-as-effort feature —
  the user chose the dial, not Sol/Terra/Luna picking (tier metadata may mention capability
  tiers; the capability never routes models).
- **No long-context threshold-tier modeling for GPT-5.6 in EITHER pricing file** — the
  authoritative numbers land in each file's `long_context_note` (a labeled string), never as
  new schema entries, and neither estimator is extended (the pre-existing `long_context`
  sub-objects on other Copilot rows are untouched).
- **No invented Copilot headless surface**: no `copilot -p` effort flag, no settings key, no
  `bin/copilot_execute.py` change of any kind (byte-untouched); nothing under `copilot/` may
  contain `--effort` or `model_reasoning_effort`. `bin/codex_execute.py` is also
  byte-untouched (its `--effort` already exists and already validates against knobs).
- **No rate value changes in `data/pricing.codex.json`** (the GA table matched exactly — edits
  are strings/knobs only) and **no edits to `data/pricing.json`** (Claude side untouched;
  `bin/sync_pricing_refs.py` never runs).
- **No Copilot roster refresh beyond the three GPT-5.6 rows** — other picker deltas (fast-mode
  previews, context-window columns, the tab context-window knob) are recorded nowhere or as
  notes only; a full re-verify is a future data task.
- **No edits to pre-existing bundle files EXCEPT the six pinned enumeration swaps** (D4); no
  edits to `skills/`, `.claude-plugin/`, `README.md`, `docs/` beyond the new
  `docs/EFFORT-DIAL.md`, `bin/harness_select.py`, `bin/*_execute.py`, `bin/*_usage.py`,
  `bin/journal_*.py`, `copilot/.github/skills/`, or any completed kit.
- **No `aesop compile`, no node/npm, no network, no web fetches** — every fact needed is
  pinned in this PLAN or readable in-repo.
- **Never invoke the real `copilot`, `codex`, or `claude` CLI** from any task, test, or verify
  command — they spend real credits/usage limits and hit the network. Command lines inside
  bundle bodies are runtime instructions this kit never executes. Every test uses synthetic
  fixtures in temp dirs; zero `Path.home()` in new code; nothing outside this repo
  (`~/.copilot`, `~/.codex`, `~/.claude` included).
- No commit, no push.

## Risks & tripwires

- **Roster set-equality tripwire**: a manifest entry without its `.agent.md`, or a
  prompt/skill without its stem-union edit, turns the suite red — the bundle tasks are atomic
  (T5, T6); verify at every boundary.
- **Positive-rates tripwire**: `LiveDataStructureTests` fails on any real model row lacking
  positive numeric rates — all three GPT-5.6 rows carry the confirmed numbers, never
  null/absent.
- **File-order tripwire**: inserting a GPT-5.6 row anywhere but the END of the models object
  silently changes first-in-file-order tier resolution and every escalation ladder. Append
  only; T9 audits ladder stability.
- **Vocabulary cross-contamination**: Codex tokens (`xhigh`, `model_reasoning_effort`) in a
  Copilot file, or Copilot display words presented as Codex flag values. Contract-tested on
  the Copilot side (D8); the reviewer hand-checks the codex side's prose direction.
- **Hardcoded-ladder relapse**: a new bundle body enumerating the levels as authoritative
  instead of deriving from `knobs` — the enumeration lives ONLY in the two pricing files
  (post-D4, `grep -rn "minimal" codex/` must stay empty; the Copilot agent body must not
  enumerate the display ladder either — it shells to `knobs`).
- **The "fable" sweep and the no-model-id sweep under `codex/`** — automatic once stems are
  added; new codex files must never name a real pricing id or Fable in any case.
- **Copilot body model-id leak**: `copilot/` has no automated body sweep — the verifier
  hand-audits `effort.agent.md`'s body for pricing-key ids (the frontmatter pin is the one
  sanctioned literal, mid-tier, never frontier).
- **Subscription-vs-bill framing drift**: Codex effort prose must keep the labeled
  API-equivalent-proxy framing; Copilot prose must keep AIC-are-real-money framing. Copy the
  house voice from `codex/prompts/route.md` / `route.agent.md` — never mix.
- **Doctrine-sentence breakage**: T7's appends are pure appends; the two byte-verbatim
  doctrine sentences are test-enforced.
- **Manifest indentation**: `copilot/aesop.yaml` is parsed line-oriented — `- effort` must
  match the existing entries' exact indentation, and the instructions sentence lands INSIDE
  the `content: |` block's indentation.
- **JSON validity**: the pricing edits are pinned blocks into hand-edited JSON — trailing
  commas or a misplaced brace break every engine; both verifies run `json.load` implicitly via
  the test files, and T1/T2 acceptance includes an explicit `json.load` check.

## Phases

- **Phase 1 — data (both files):** T1 Copilot pricing (knobs + GPT-5.6 rows), T2 Codex pricing
  (`xhigh` + GA/ultra/long-context notes) + the six enumeration swaps. Independent lanes.
- **Phase 2 — engine derivation surface:** T3 `copilot_pricing.py knobs`, T4
  `codex_pricing.py knobs`. Each depends only on its own lane's data task.
- **Phase 3 — bundles:** T5 Copilot `effort` agent (atomic), T6 Codex `effort` prompt+skill
  (atomic).
- **Phase 4 — closeout:** T7 instruction surfaces, T8 `docs/EFFORT-DIAL.md`, T9 full-suite +
  frozen-surface audit.

Two independent serial lanes run in parallel: the Copilot lane T1 → T3 → T5 (shared files
`data/pricing.copilot.json`, `bin/copilot_pricing.py` tests, `copilot/aesop.yaml`,
`tests/test_copilot_bundle.py`) and the Codex lane T2 → T4 → T6 (shared
`data/pricing.codex.json`, `tests/test_codex_*.py`, `tests/test_codex_bundle.py`). T7/T8 need
both lanes; T9 needs T7+T8.

## Deferred (recorded, not built — each with its correctable point)

- Copilot headless effort surface → `pricing.copilot.json` `knobs.reasoning_efforts_note`; a
  future kit may then extend `copilot_execute.py` additively.
- The four unobserved Copilot display renderings (Minimal/Low/High/Max) → the knobs note.
- GPT-5.6 long-context threshold-tier schema modeling (both harnesses) → each file's
  `long_context_note`.
- `ultra`/multi-agent + fast-mode CLI surfaces → the `modes` notes.
- `pricing.copilot.json` full roster refresh — the 2026-07-18 picker capture lists models the
  file lacks (a separate roster-reconciliation kit; this kit adds ONLY the three GPT-5.6 rows)
  — and the `cached_date` bump that comes with a full re-verify → `model_ids_note`.
- Exact GPT-5.6 id strings on both harnesses → each file's `model_ids_note`.
- A Claude-side `effort` skill (Claude manages effort differently) — out of scope here.
