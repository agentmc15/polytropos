# PLAN — copilot-costviz

Phase 3 of the Copilot harness, with the scope FIXED by the user: **build** the cost-visibility
work in this repo (a Copilot usage-report analogue to `/polytropos:cost-report` in
`bin/copilot_usage.py`, plus org/Business pooled-AIC awareness in `bin/copilot_pricing.py
runway`), and **write** the aesop-compile round-trip up as a proposal document
(`docs/AESOP-COMPILE-PROPOSAL.md`) for a FUTURE architect run executed inside the aesop repo —
nothing aesop-side is executed here. Builds on the completed copilot-harness and
copilot-workflow kits; duplicates nothing. All aesop behavior claims are pinned to commit
`5506617` (full: `55066175a5268887acad39bc859584d13fab09db`); no task reads an aesop clone
(it is session-scoped reference material that may be absent).

The third Phase-3 clause — feeding real per-tick costs back into the Ralph loop — stays
**deferred by design** (see "Still deferred after this kit").

## Goal

Ship three things, end-to-end verified without ever calling the real `copilot` CLI and without
any task reading or writing the real `~/.copilot`:

1. **`bin/copilot_usage.py`** — a stdlib usage report mirroring `bin/cost_report.py`'s shape
   (that script is a read-only model, never edited): walk
   `<copilot-home>/session-state/*/events.jsonl` READ-ONLY, parse the pinned event surface
   below, attribute usage per session/model with honest granularity, price it from
   `data/pricing.copilot.json` (USD + AIC, derived — never hardcoded), and print a markdown
   report: spend by model, an exact per-turn output-tokens-by-model table, top sessions,
   downgrade candidates, and a clearly labeled Copilot-reported-AIU cross-check.
2. **Pooled-AIC runway** — `plan_runway` in `bin/copilot_pricing.py` (today it KeyErrors on
   null-allowance plans like `business`/`enterprise`) grows a user-supplied pool size
   (`--pool-aic N`) so org plans get runway math. This is the ONE sanctioned edit to an
   existing `bin/` script in this kit.
3. **`docs/AESOP-COMPILE-PROPOSAL.md`** — the written spec for reconciling aesop's copilot
   emitter (`.agent.md` vs `.md`), exposing this repo's Copilot bundle to aesop's registry
   lookup, and running the compile round-trip — explicitly framed as the input to a future
   `/polytropos:architect` run INSIDE the aesop repo.

**Done looks like:** `python3 -m unittest discover -s tests -v` green with
`tests/test_copilot_usage.py` new and `tests/test_copilot_pricing.py` extended;
`python3 bin/copilot_usage.py --copilot-home <temp fixture>` prints the full report (by-model,
exact output table, top sessions, downgrade candidates, AIU cross-check, honest-granularity
footnotes) and provably mutates nothing under the fixture home;
`python3 bin/copilot_pricing.py runway business M <id> --pool-aic 50000` prints runway math
instead of erroring, while every existing `runway` call and `bin/copilot_ralph.py --plan` are
byte-for-byte unaffected; `docs/AESOP-COMPILE-PROPOSAL.md` and `docs/COPILOT-COSTVIZ.md` exist;
the two "deferred to Phase 3" doc tails and README are updated with pinned text; CLAUDE.md
carries the pinned read-only-usage insertions; no file anywhere invokes the real `copilot`; and
`data/pricing.json`, `data/pricing.copilot.json`, `.claude-plugin/`, `skills/`, `copilot/`, and
the completed kits are byte-identical to git HEAD.

## Research findings — the usage surface (CONFIRMED; executors must NOT re-inspect `~/.copilot`)

Recorded per the kit mandate. Confirmed by the architect against the live install, Copilot CLI
**v1.0.68**, 2026-07-01. Executors need not and must not open the real `~/.copilot` to
re-verify any of this — every fact a task needs is restated in its brief.

- **Location:** `~/.copilot/session-state/<session-uuid>/events.jsonl` — one JSON object per
  line: `{"type": ..., "timestamp": ..., "data": {...}}`. A sibling `workspace.yaml` in the
  same dir carries session `id`, `name`, `cwd`, `client_name`, `created_at`, `updated_at`
  (flat `key: value` lines). A sibling `session.db` holds only `todos`/`todo_deps`/
  `inbox_entries` — NOT usage; ignore it.
- **The top-level `~/.copilot/data.db` and `session-store.db` read as EMPTY** under an
  immutable/read-only open — their data sits uncheckpointed in `-wal` files. Do NOT rely on
  them; `events.jsonl` is the surface.
- **Cost-bearing event:** `type == "session.shutdown"`, whose `data` carries `totalNanoAiu`
  (integer nano-AI-Units — Copilot's own reported consumption; ÷ 1e9 for AIU),
  `totalPremiumRequests` (int), `tokenDetails` =
  `{"input": {"tokenCount": N}, "cache_read": {"tokenCount": N},
  "cache_write": {"tokenCount": N}, "output": {"tokenCount": N}}`, plus `currentModel`,
  `modelMetrics`, `conversationTokens`, `codeChanges`, `sessionStartTime`. A
  `session.resume` + later `session.shutdown` can appear — a session may have MULTIPLE
  shutdowns across resumes.
- **Per-turn events:** `type == "assistant.message"` with `data.model` (e.g.
  `claude-sonnet-5`), `data.outputTokens`, `data.apiCallId`, `data.turnId`,
  `data.interactionId`. `type == "session.start"` / `"session.resume"` carry
  `data.selectedModel` / `data.contextTier`. `type == "session.model_change"` carries
  `previousModel` / `newModel` — a single session can span multiple models.
- **CRITICAL granularity nuance:** the full token breakdown (input/cache_read/cache_write/
  output) exists at SESSION granularity only (`session.shutdown`). Per-MODEL attribution
  within a multi-model session is only partially recoverable (`assistant.message` gives
  per-turn model + outputTokens, but not per-turn input/cache splits). The report must be
  HONEST: attribute cleanly per session, exactly per model only where a session is
  single-model, and never fabricate a per-model input/cache split the events don't support.
- **AIU vs AIC caveat:** `totalNanoAiu` is Copilot's own reported figure in "AI Units", which
  may or may not equal the AIC billing unit in `data/pricing.copilot.json`. Never assume
  AIU == AIC. The tool's AUTHORITATIVE cost = token counts × per-MTok rates from
  `data/pricing.copilot.json` → USD → AIC via `billing_unit.usd_per_credit` (derived at run
  time). Copilot's reported AIU appears alongside only as a labeled cross-check.

## Architecture & key decisions

- **D1 — Read surface: `events.jsonl` (+ `workspace.yaml`) only; the SQLite stores are never
  opened.** Rationale: the DBs read empty without a WAL checkpoint, and opening a live SQLite
  file — even "read-only" — can create/modify `-wal`/`-shm` side files, which would violate the
  read-only contract against the user's live home. `events.jsonl` is append-only text;
  `workspace.yaml` is flat `key: value` text parsed with a tolerant line splitter (stdlib has
  no YAML parser; nesting is ignored). The tool reads with
  `read_text(errors="replace")` and never writes anything anywhere under the target home.
- **D2 — Script shape mirrors `bin/cost_report.py`, which is a read-only MODEL, not an edit
  target.** Same skeleton: walk → extract → dedupe → price → markdown to stdout; same knobs
  (`--days`, `--top`); same "no parseable timestamp ⇒ kept regardless of `--days`" rule; same
  unpriced-models and read-errors sections; same closing "estimates, not bills" footer. New
  knobs: `--copilot-home` (default `Path.home() / ".copilot"` — the ONLY place `Path.home()`
  may appear, mirroring cost_report's `PROJECTS_DIR`; tests always override it) and
  `--session-dir` (points directly at a `session-state`-shaped directory, overriding
  `<home>/session-state`). Parsing/pricing live in pure functions with `main(argv=None)` so
  tests exercise everything against synthetic fixtures in temp dirs.
- **D3 — Multiple shutdowns aggregate by element-wise MAX, not sum.** The shutdown fields are
  named `total*` and a resumed session appends to the SAME events.jsonl — so each
  `session.shutdown` is naturally read as a cumulative snapshot, and the last/largest snapshot
  is the session total. Element-wise max over all shutdown snapshots (per token field, and for
  `totalNanoAiu`/`totalPremiumRequests`) is exactly right when snapshots are cumulative, and
  strictly conservative (never double-counts) if a Copilot version ever emits per-segment
  totals. Summing would double-count the cumulative case — the worse failure. The report
  surfaces the shutdown count per session so a multi-resume session is visible.
- **D4 — Attribution honesty is a structural feature, not a footnote.** Per session: the model
  set is collected from `session.start`/`session.resume` `selectedModel`,
  `session.model_change` `previousModel`/`newModel`, `assistant.message` `model`, and
  `session.shutdown` `currentModel`, in stream order. A single-model session attributes its
  full token split to that model — exact. A multi-model session attributes its full split to
  its LAST model and is flagged (`≈` in tables, counted in a loud footnote) — approximate by
  construction, because events.jsonl does not record per-model input/cache splits.
  Sessions with no `tokenDetails` at all (crash/still-open) fall back to per-turn output
  tokens only (`effective_tokens`: input/cache = 0, output = summed `assistant.message`
  outputTokens), flagged `†` as an output-only undercount. The one EXACT cross-model view —
  a per-turn "Output tokens by model" table built from `assistant.message` events (deduped by
  `apiCallId` when present) — is printed for all sessions. The report never invents a
  per-model input/cache split, and the limitation is stated in the output itself.
- **D5 — Pricing observed usage: absolute per-MTok rates from `data/pricing.copilot.json`,
  cache writes included where the row prices them.** `usd = (input × input_per_mtok +
  cache_read × cached_input_per_mtok + cache_write × cache_write_per_mtok + output ×
  output_per_mtok) / 1e6`, where a row without `cache_write_per_mtok` contributes 0 for cache
  writes. This deliberately diverges from `copilot_pricing.est_cost`, which EXCLUDES cache
  writes: `est_cost` is a forecast convention over coarse task profiles, while this report
  prices OBSERVED counts and the data carries real cache-write rates for Anthropic rows —
  dropping a measured, priced quantity would understate real spend. `aic = usd /
  pricing["billing_unit"]["usd_per_credit"]` — derived, never hardcoded. Model matching
  mirrors cost_report's tolerant matcher (exact key, else `base.startswith(key + "-")` after
  stripping any `[...]` suffix); unmatched models land in an "Unpriced models" section instead
  of crashing or being silently dropped.
- **D6 — AIU is a labeled cross-check, never a price.** The report sums `totalNanoAiu / 1e9`
  per session and prints it in the totals line, the top-sessions table, and a dedicated
  "Copilot-reported AIU cross-check" section that states the caveat verbatim: AIU is Copilot's
  own reported consumption unit and is NOT assumed equal to the AIC billing unit; the tool's
  authoritative estimate is the token-priced USD → AIC figure. AIU is never converted to USD
  or AIC anywhere in the code.
- **D7 — Downgrade candidates stay data-driven.** A candidate session's matched models are all
  in `EXPENSIVE_TIERS = {"strong", "frontier"}` (the Copilot file's tier vocabulary) with a
  footprint under `DOWNGRADE_TOKEN_CEILING = 50_000` tokens and under
  `DOWNGRADE_TURN_CEILING = 15` assistant turns (Copilot events carry no tool-use counter, so
  turns replace cost_report's tool-call ceiling). The ceilings are commented report knobs
  (token/turn counts, not prices). The downgrade TARGET is computed, not named: the first
  model in `data/pricing.copilot.json` file order whose `tier == "mid"` — no model-id literal
  anywhere in the script, honoring the Copilot-side source-of-truth invariant.
- **D8 — Pooled-AIC runway: an additive keyword, not a signature break.**
  `plan_runway(pricing, plan_id, profile, model_id, cache_hit=0.8, today=None,
  pool_aic=None)`. When `pool_aic` is given (a number > 0, else `ValueError`) it supplies the
  allowance — for null-allowance plans (`business`/`enterprise`, whose pools are org-level
  facts the data file cannot know) AND as an override for fixed plans (an org admin may know
  the real pool). When absent, behavior is exactly today's, except the null-allowance
  `KeyError` message additionally points at `--pool-aic`. The result dict keeps its three
  existing keys untouched and gains `allowance_aic` + `allowance_source`
  (`"plan"` | `"pool"`) — so `bin/copilot_ralph.py`'s `_print_plan_runway` (which reads only
  the original keys) needs and receives zero changes. CLI: `runway` gains `--pool-aic`
  (float); text output gains one `allowance:` line; JSON output gains the two new keys.
- **D9 — The aesop compile round-trip is a DOCUMENT because executing it here would be wrong
  four ways.** (1) The reconciliation lives in aesop's emitter/federation code, and aesop's
  `src/types.ts`/schema are LOCKED with a doc-first harness-matrix + golden-fixture process —
  changes go through aesop's own phase-gated flow, in aesop's repo. (2) This repo forbids
  node/npm/`aesop compile`, so a round-trip could not even be verified here. (3) Choosing
  between the exposure options (a registry-shaped path in this repo vs. an emitter/lookup
  change in aesop) requires compile-side validation only the aesop repo can run — building
  either half early would ossify an unvalidated choice. (4) The aesop clone is session-scoped
  and may not exist. So T5 writes `docs/AESOP-COMPILE-PROPOSAL.md` from facts pinned in its
  brief (`aesop@5506617`), laying out the divergence, the exposure options with a
  recommendation, the round-trip acceptance criteria, and the guardrails the future aesop-side
  architect run must honor. No `copilot/` file changes in this kit.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Invoke the real `copilot` CLI, EVER — not even `--help`.** It calls a model, spends the
  user's real AI Credits, and hits the network; the user has a live `~/.copilot`. Nothing this
  kit builds needs the CLI: the usage surface is pinned above, and `bin/copilot_usage.py` is a
  pure log reader.
- **Read OR write the real `~/.copilot` during execution.** `bin/copilot_usage.py` targets it
  read-only at RUNTIME (the finished tool, run by the user); every task, test, and verify
  command in this kit uses synthetic `events.jsonl` fixtures in temp `--copilot-home` /
  `--session-dir` dirs. `Path.home()` may appear only in the script's runtime default
  (D2), never in tests. Never open a `*.db` file anywhere (D1).
- **Touch anything else outside this repo** — `~/.claude` included; no plugin re-install.
- **Edit `data/pricing.json` or `data/pricing.copilot.json`** (values, keys, anything), or
  hardcode any price, credit value, plan allowance, or model id into scripts — derive from the
  data at run time (D5/D7/D8). The downgrade token/turn ceilings and the report's section
  headings are sanctioned report knobs/copy, not prices.
- **Edit existing `bin/` scripts other than `bin/copilot_pricing.py`** (T1's sanctioned
  `--pool-aic` extension). `bin/cost_report.py` is read as a model, never edited;
  `bin/copilot_execute.py`, `bin/copilot_ralph.py`, `bin/harness_select.py`,
  `bin/aesop_bridge.py`, `bin/statusline.py`, `bin/sync_pricing_refs.py`,
  `bin/agent_tracker.py` stay untouched. In `tests/`, only `tests/test_copilot_pricing.py` may
  be extended (T2); other existing test files stay untouched.
- **Touch `.claude-plugin/`, `skills/` (or its generated mirrors), `copilot/`** — this kit
  adds NO bundle content and NO new Claude Code skills; the registry-shaped exposure of the
  bundle is proposal-only (D9).
- **Touch the completed kits** (`harden-plugin`, `aesop-bridge`, `copilot-harness`,
  `copilot-workflow`) or their agents beyond reading them.
- **Run node/npm/`aesop compile`**, or add any dependency/tooling. Python stays stdlib-only;
  no pytest; no requirements files. The aesop clone is reference-only and may not exist — no
  task reads it; provenance is cited as `aesop@5506617` only.
- **Build the Ralph per-tick real-cost feedback** (Phase-3 clause 3) — it stays deferred; do
  not bolt a live log-scraper onto `bin/copilot_ralph.py` (see "Still deferred").
- **Commit or push.**

## Risks & tripwires

- **AIC / network safety — THE #1 RISK.** Any code path that reaches a real `copilot`
  invocation spends real money and hits the network. TRIPWIRE: if a task, test, or verify
  command would invoke `copilot` (any subcommand, any flag), STOP — that is a wrong change
  even if it works. This kit's scripts spawn NO subprocesses at all; the verifier
  adversarially audits for this on every task.
- **Live-home safety — the #2 risk, specific to this kit.** `bin/copilot_usage.py`'s runtime
  default points at the user's real `~/.copilot`. TRIPWIRES: a test or verify command that
  runs the script without `--copilot-home`/`--session-dir` pointing at a temp fixture; any
  `Path.home()` outside the script's single default constant; any code that OPENS a `*.db`
  file (even read-only — SQLite can create `-wal`/`-shm` side files); any `open(..., "w")`,
  `write_text`, `mkdir`, or similar aimed under the target home. Tests prove the negative by
  inventorying the fixture home (file set + content hashes) before and after a full run.
- **events.jsonl format drift across Copilot versions.** The surface above was observed on
  Copilot CLI v1.0.68. TRIPWIRE: the parser must tolerate unknown event types, missing
  `data` fields, and malformed lines (skip, never crash), and must surface what it cannot
  price (unpriced models, sessions without tokenDetails) instead of guessing. The version pin
  is stated in the module docstring and the report footer.
- **Multi-model attribution fabrication.** TRIPWIRE: any code or output that presents a
  per-model input/cache split for a multi-model session is a wrong change even if the numbers
  look plausible — the events do not support it (D4). The approximation flag and footnote are
  contract, enforced by tests.
- **AIU/AIC conflation.** TRIPWIRE: converting `totalNanoAiu` to USD or AIC anywhere, or
  presenting AIU as the tool's estimate, violates D6. AIU appears only under its own label.
- **Hardcoding creep.** The downgrade target, tier walks, and USD↔AIC conversion are computed
  from the pricing dict at run time. TRIPWIRE: a real model id, price, credit value, or plan
  allowance literal in `bin/copilot_usage.py`, the `copilot_pricing.py` diff, or any test
  assertion (synthetic fixture ids/values in tests are fine and expected).
- **Sanctioned-edit scope.** Only `bin/copilot_pricing.py` (T1) and
  `tests/test_copilot_pricing.py` (T2) among existing files under `bin/`+`tests/` may change,
  and T1 must be purely additive to `plan_runway`'s result keys so `bin/copilot_ralph.py`
  keeps working unmodified. TRIPWIRE: `git status` showing any other existing `bin/`/`tests/`
  file modified.
- **Site-packages `tests` shadowing / path quirks.** Verify commands use
  `python3 -m unittest discover -s tests [-p '<file>.py']` — never the dotted-module form.
  Path resolution uses `Path(__file__).resolve()`, never `$PWD` (Desktop/desktop case quirk).
  No `/private/tmp/` session-scratchpad path may appear in any deliverable.

## Still deferred after this kit

1. **Ralph per-tick real-cost feedback** (Phase-3 clause 3, deferred by design here):
   Copilot's per-tick cost is not cleanly exposed to a live `copilot -p` tick —
   `events.jsonl` is written at session shutdown, not per turn in a scriptable way — so
   `bin/copilot_ralph.py`'s pricing-fed estimate fallback remains the steady state. Bolting a
   live log-scraper onto the loop would be fragile (shutdown-time writes, format drift) and is
   explicitly out of scope. Revisit only if a future Copilot CLI emits per-turn cost on
   stdout, which `parse_cost` already knows how to read.
2. **Executing `docs/AESOP-COMPILE-PROPOSAL.md`** — a future `/polytropos:architect`
   run INSIDE the aesop repo, under aesop's own phase-gated process (LOCKED schema, doc-first
   harness matrix, golden fixtures), re-verifying every `aesop@5506617` fact against aesop
   HEAD at that time. Never from here.
