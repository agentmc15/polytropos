# PLAN — context-weight

autonomy: auto

(Every deliverable is a NEW file except two pinned CLAUDE.md run-lines; the engine is
strictly read-only over harness homes; every task is verify-gated by the full suite. Nothing
here can spend money or mutate user data, so unattended execution is acceptable.)

## The reframe this kit is built on (binding context — do not re-litigate)

The user asked to "lower cache reads in claude, codex and copilot." Measured on the
motivating session: $74.90 API-equivalent, of which cache reads were 121.4M tokens = $60.70
(85%). Those same tokens uncached would have been ~$607 — **caching already saves 10×. Cache
reads are the cheap path working correctly, not a misconfiguration.** The real driver is
**resident context × number of API calls**: that session re-read ≈463K tokens per turn
across 262 Opus messages.

Second binding fact: this repo's always-loaded config surfaces are ALREADY lean —
CLAUDE.md ~10.7KB, codex/AGENTS.md ~2.3KB, copilot instructions ~1.9KB, skill listing
~0.6K tokens — together under 1% of the observed 463K/turn. An 80% CLAUDE.md cut moved only
~2.4% of per-turn mass. **The dominant mass is accumulated conversation: tool outputs, file
contents read into context, subagent returns, long transcripts.** Therefore this kit must
NOT re-optimize config files. It builds three things:

1. **MEASURE** — `bin/context_weight.py`: per-turn context weight, growth curve over a
   session, and a ranked list of what actually filled the window, per harness, at each
   harness's honest fidelity.
2. **AUDIT** — a resident-surface audit per harness (what's always loaded, in tokens,
   against a budget) that itself PRINTS the reframe so nobody mistakes config for the lever.
3. **GUIDE** — a `context-weight` skill encoding the practices that shrink the working set,
   each practice tied to a metric the tool reports.

Reusable on ANY project: the engine takes a project dir / harness homes as arguments; nothing
is hardwired to this repo.

## Goal

Ship, end to end, with the full suite green (1022 baseline + `tests/test_context_weight.py`):

1. **`bin/context_weight.py`** (new) — subcommands `session`, `overview`, `audit`, `demo`;
   markdown + `--json` output; strictly read-only; injectable `--projects-dir` /
   `--codex-home` / `--copilot-home` / `--project` seams; reuses the existing parsers via
   importlib (never re-implements them).
2. **`tests/test_context_weight.py`** (new) — synthetic fixtures in temp dirs for all three
   harnesses; pure-function coverage, CLI end-to-end, honesty-line proofs, read-only proof,
   demo pinned-number regression.
3. **`skills/context-weight/SKILL.md`** (new) — the guide skill.
4. **`docs/CONTEXT-WEIGHT.md`** (new) + two pinned run-lines appended to CLAUDE.md's
   "How to run things" block.

**Done looks like:** `python3 -m unittest discover -s tests` green (1022 baseline tests all
still passing, plus the new file); `python3 bin/context_weight.py demo` prints all three
harness cards plus the audit card with the D11 pinned numbers and exits 0;
`python3 bin/context_weight.py demo --json` round-trips through `json.loads`;
`python3 bin/sync_pricing_refs.py --check` exits 0; CLAUDE.md stays ≤ 16,000 bytes
(`tests/test_guardrails_layout.py` enforces this); `git status` shows changes ONLY to
sanctioned targets (new: `bin/context_weight.py`, `tests/test_context_weight.py`,
`bin/plugin_staleness.py`, `tests/test_plugin_staleness.py` (T12, added mid-flight),
`skills/context-weight/SKILL.md`, `docs/CONTEXT-WEIGHT.md`, this kit + its agents;
edited: `CLAUDE.md` pinned run-lines only); and
`git diff --quiet -- bin/cost_report.py bin/session_cost.py bin/codex_usage.py
bin/copilot_usage.py data skills/route skills/fable-check` stays clean throughout.

**Measurable target (for the tool's users, tracked by the tool itself, not a kit acceptance
criterion):** on the motivating workload profile (≈463K avg weight, 262 calls), the guide's
practices — compact near the 40%-of-window plateau, delegate bulk reads, cap tool output —
are expected to roughly halve avg per-call weight, i.e. ~$25–30 of that session's $60.70
cache-read mass. `overview` gives the before/after evidence across sessions.

## Repo facts (confirmed by the architect — trust these, do not re-derive)

- **Claude transcripts** (`~/.claude/projects/<slug>/<session>.jsonl`, one JSON object per
  line): assistant records carry `message.usage` with `input_tokens`,
  `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`;
  `bin/cost_report.py:extract_record(obj)` already returns `(model, usage_dict, msg_id,
  tool_uses)` with keys `input`/`output`/`cache_read`/`cache_write` — REUSE IT. Records also
  carry top-level `type` (`assistant` / `user` / `system` / `attachment` / others),
  `isSidechain` (bool, present on message records), `timestamp`, `sessionId`, `uuid`.
  Assistant `message.content` lists carry `tool_use` blocks (`id`, `name`, `input`); the
  FOLLOWING `user` records carry `tool_result` blocks (`tool_use_id`, `content`) and a
  top-level `toolUseResult` mirror. Verified live on a real transcript 2026-07-24. There is
  NO reliable compaction marker in every transcript (an `isCompactSummary` flag exists in
  some sessions; the verified session had none) — hence D6's inference rule.
- **Codex rollouts** (`<codex-home>/sessions/YYYY/MM/DD/*.jsonl`): tolerant candidate-key
  extraction already exists in `bin/codex_usage.py` — `_find_containers`,
  `_normalize_tokens`, `parse_rollout`, `iter_rollout_files`, `match_model`, `price_tokens`,
  `parse_timestamp`. Containers: `total_token_usage` is CUMULATIVE (element-wise MAX, never
  sum); `last_token_usage`/`usage`/`token_usage`/`tokens`/`token_counts` are per-turn
  (summed). Usage containers carry token COUNTS only — no content provenance. Fixture-shape
  reference: `tests/test_codex_usage.py` (`_tok_rec`, `_model_rec`, `_write_rollout`).
- **Copilot events** (`<copilot-home>/session-state/*/events.jsonl`): per-turn
  `assistant.message` events carry OUTPUT tokens only; the full
  input/cache_read/cache_write/output split exists ONLY as cumulative `session.shutdown`
  `tokenDetails` snapshots (aggregate by element-wise MAX). `bin/copilot_usage.py` provides
  `parse_events`, `effective_tokens`, `collect_sessions`, `match_model`, `price_tokens`,
  `parse_timestamp`. There is NO per-turn input/cache record — a Copilot growth curve is
  impossible to compute honestly. Fixture-shape reference: `tests/test_copilot_usage.py`
  (`_ev`, `_td`, `_iso`).
- **Importlib reuse pattern** (copy it, do not invent):
  `session_cost.py` lines 56–63 (`_load_cost_report` via
  `importlib.util.spec_from_file_location`) and `routing_scorecard.py`'s `_load(name)`.
- **Module conventions:** `#!/usr/bin/env python3`, substantial why-docstring,
  `main(argv=None) -> int`, argparse, `--json`, `PLUGIN_ROOT = Path(__file__).resolve()
  .parent.parent`, module-level `DEFAULT_*` dirs are the ONLY `Path.home()` uses and tests
  always override them (precedent: `codex_usage.py` line 71, `copilot_usage.py` line 50,
  `session_cost.py:_default_projects_dir` honoring `CLAUDE_CONFIG_DIR`).
- **Token-count knobs may be module constants** (precedent: `DOWNGRADE_TOKEN_CEILING =
  50_000` in cost_report.py) — prices, price ratios, and real model ids may NOT.
- **Test baseline:** `python3 -m unittest discover -s tests` → 1022 tests, OK (verified
  2026-07-24). Single file: `-p 'test_context_weight.py'`. The dotted-module form is broken
  on this machine — never use it.
- **CLAUDE.md is 10,668 bytes**; `tests/test_guardrails_layout.py` fails it at >16,000 and
  requires every kit dir with a PLAN.md to carry a GUARDRAILS.md ≥200 bytes (already written
  for this kit).
- **Skill conventions:** YAML frontmatter `name` / `description` / `allowed-tools`; body
  resolves scripts via `${CLAUDE_PLUGIN_ROOT}` with "relative to this SKILL.md" fallback
  (see `skills/cost-report/SKILL.md`). Plugin skills are auto-discovered from
  `skills/*/SKILL.md` — no manifest edit needed. The plugin is installed LIVE: a new SKILL.md
  becomes runtime behavior on next session start; never touch existing skills' frontmatter.

## Architecture & key decisions (each with rationale — executors inherit these verbatim)

**D1 — The unit of measurement is one priced API call, not one user turn.**
An "API call" = one record the harness recorded usage for (Claude: an assistant record with
`message.usage`; Codex: one per-turn usage container, or one cumulative snapshot point;
Copilot: one `assistant.message`). Rationale: the API call is the only unit all three
harnesses actually meter, and it is the unit that multiplies resident mass — a single user
turn with a 10-step tool loop re-submits the whole window 10 times. Everything downstream
(curve, averages, carry cost) is per-call.

**D2 — Context weight (Claude, Codex) = `input + cache_read + cache_write` of a call.**
That sum is the full prompt actually submitted; the three-way split is a cache-lifecycle
artifact, not a size difference. Output tokens are excluded from weight (they are generation,
not carried context) but are still reported. Copilot cannot compute this per call (D3).

**D3 — Per-harness fidelity ladder; never fabricate a number the logs don't carry.**
- *Claude — full fidelity:* per-call weights, growth curve, compaction inference, ranked
  contributors, sidechain split.
- *Codex — curve fidelity:* per-call weights and a growth curve where per-turn containers
  exist; where only cumulative `total_token_usage` snapshots exist, the curve plots
  `input + cache_read` per snapshot and is labeled `cumulative snapshots`. Contributor
  attribution is NOT possible from usage containers; the section prints the verbatim line
  `provenance not recorded in these logs — byte-share of rollout record types shown as a
  labeled estimate` and shows only a per-record-type byte-share table (est., D9).
- *Copilot — session-average fidelity:* one card per session: `session-average weight =
  (input + cache_read + cache_write) / assistant turns`, labeled `session-average`, plus the
  verbatim line `growth curve: not available — Copilot events do not record per-turn
  input/cache token splits`. No curve, no attribution, ever.
Rationale: mirrors the honesty ladder already load-bearing in `codex_usage.py` (its PLAN D8)
and `copilot_usage.py`'s ≈-flag; an invented per-turn split would be indistinguishable from
measurement and would poison decisions.

**D4 — Attribution (Claude) measures incremental additions and reconciles to measured
growth, with an explicit unattributed remainder.**
Mechanism: build `tool_use_id → (tool name, salient input)` from assistant `tool_use` blocks
(salient input = `input.file_path` for Read/Edit/Write, first ~60 chars of `input.command`
for Bash, `input.prompt`'s first ~60 chars for Agent, else nothing); size each `user`
record's `tool_result` content, each plain user text block, and each `attachment` record by
serialized character length → estimated tokens at `EST_CHARS_PER_TOKEN = 4`; rank by
estimated tokens, grouped by tool name (and by file path within Read). Reconciliation: sum
of attributed est. tokens vs the measured window growth (last weight − first weight +
recovered-by-compaction mass); the gap prints as an `unattributed growth` row (system
overhead and tool schemas — not measurable from the transcript). **[AMENDED BY T13: the
original text also listed `thinking` as unmeasurable. That was WRONG — thinking is inside
assistant output and is recorded exactly as `output_tokens`. T13 added an
`assistant output (measured)` row, labeled `measured` not `est.`, never priced, ranked
inline by magnitude. On real transcripts this moved 57-83% of the former gap out of the
unknown bucket (66.3% -> 11.4% unknown on a stable session). T8 and T11 write the guide
skill and docs FROM THIS PLAN — use the corrected statement, not the original.]** Every estimated figure
carries the label `est.`. Rationale: transcripts record token counts and content separately;
byte-derived numbers are honest as ranks and magnitudes, dishonest as exact tokens — so they
are labeled, never priced, and never mixed into measured-token columns.

**D5 — Dollars come ONLY from measured usage tokens priced through that harness's own
pricing file; estimated tokens are NEVER priced; harness dollars NEVER merge.**
`session`/`overview` show a "context carry cost": the session's measured usage priced with
OUTPUT ZEROED — Claude via `cr.price` per model from `data/pricing.json`; Codex via
`codex_usage.price_tokens` from `data/pricing.codex.json` (with its standing subscription
disclaimer, verbatim); Copilot via `copilot_usage.price_tokens` from
`data/pricing.copilot.json` (USD + AIC via `usd_to_aic`). Each harness's dollars stay inside
its own section; there is NO cross-harness dollar total anywhere in any output. The `audit`
subcommand shows tokens only — no dollars at all — because its inputs are byte-estimates,
not measured usage. Rationale: the three-pricing-files invariant, plus "estimates are ranks,
measurements are dollars."

**D6 — Compactions/clears are INFERRED, and labeled as such.**
Within one transcript's call sequence, a drop of ≥ `DROP_FRACTION = 0.5` from the previous
call's weight marks an inferred compaction/clear point on the curve (count + location
reported, curve annotated). If a record carries a truthy `isCompactSummary`, that is noted
opportunistically as a confirmed marker. Rationale: verified live that no reliable marker
exists in every transcript; a halving of submitted prompt size is the observable signature.
The word `inferred` appears in the output.

**D7 — Sidechain mass is split out, not mixed in.**
Claude records with truthy `isSidechain` are EXCLUDED from the main curve/averages and
aggregated into one line: calls + total weight + share of session mass. Rationale: the
driver's window is what grows turn over turn; subagent context is disposable by design.
This line is the delegation payoff made visible — it belongs next to the main curve, not
inside it.

**D8 — Strictly read-only, injectable seams, usage-reader `Path.home()` precedent.**
The engine opens `.jsonl` transcripts/rollouts/events and the audit's named text files for
READING only; never a `*.db`/SQLite open, never a write outside stdout, never a CLI
invocation. Module-level `DEFAULT_*` home constants are the only `Path.home()` uses
(Claude's honoring `CLAUDE_CONFIG_DIR` like `session_cost._default_projects_dir`); every
test and every verify command overrides them via flags. `Path.home()` count in
`tests/test_context_weight.py`: ZERO.

**D9 — Estimation constants are sanctioned, documented token knobs — never prices.**
`EST_CHARS_PER_TOKEN = 4` (chars→est-token heuristic; the docstring says it is a labeled
estimator, never priced), `DROP_FRACTION = 0.5` (D6), `DEFAULT_SURFACE_BUDGET_TOKENS =
5_000` (audit budget, overridable via `--budget-tokens`; chosen as ~1% of the ~500K observed
working set that motivated this kit), `CW_SCHEMA_VERSION = 1` (same species as the
scorecard's `SCHEMA_VERSION`). Same license as `DOWNGRADE_TOKEN_CEILING`: token counts and
ratios of tokens are data-design knobs; dollars and model ids are not.

**D10 — The audit measures the measurable and NAMES the unmeasurable.**
Pinned resident-surface lookup per harness, relative to `--project DIR` (default `.`):
claude → `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md`; codex → `AGENTS.md`;
copilot → `.github/copilot-instructions.md`, `AGENTS.md`. Missing files are listed `absent`,
never an error. `--surface PATH` (repeatable) adds project-specific extras. Each present
surface: bytes, est. tokens, % of budget; per harness a total plus a `per 100 calls: N
tokens re-submitted (est.)` line (total est. tokens × 100). A fixed closing line names what
is resident but NOT measurable from files: `system prompt, tool schemas, plugin skill
listings, MCP definitions — resident but not measurable here; measure their effect with the
session subcommand`. And whenever session data is supplied (`--session`/`--vs-session`) the
audit prints the reframe: resident surfaces = N% of measured per-call weight — the working
set, not config, is the lever. Rationale: the audit exists to STOP config-tweaking theater,
so it must carry its own counter-message.

**D11 — One `demo` subcommand, synthetic fixtures, pinned hand-checkable numbers.**
`context_weight.py demo [--json]` builds ALL fixtures in one
`tempfile.TemporaryDirectory()` (precedent: `routing_scorecard.run_demo`) — a synthetic
Claude projects dir, codex home, copilot home, and audit project dir — runs all four cards,
and prints them. Model ids in fixtures are computed AT RUN TIME as the first model key of a
chosen tier from the harness's own pricing file — never spelled out. Pinned demo numbers
(hand-derivable from the fixture content pinned in T7's brief):
- Claude: 4 main calls, weights `[10000, 20000, 30000, 8000]`, avg `17000`, peak `30000`,
  total submitted `68000`, 1 inferred compaction (30000→8000), sidechain line `1 call,
  5000 tokens`; attribution ranks Bash `5000 est.` then Read `/workspace/demo.txt`
  `2000 est.`, unattributed remainder `13000 est.`.
- Codex: 3 per-turn calls, weights `[3000, 8000, 13000]`, avg `8000`; the verbatim
  no-provenance line present.
- Copilot: 2 assistant turns, session-average weight `21000` (= (10000+30000+2000)/2); the
  verbatim no-curve line present.
- Audit (synthetic project): CLAUDE.md 2000 chars → `500` est. tokens (10% of budget),
  AGENTS.md 1200 → `300` (6%), `.github/copilot-instructions.md` 800 → `200` (4%).
Rationale: pinned demo numbers are this repo's standing regression idiom — they make drift
loud and give every future kit a safe smoke that touches zero real data.

**D12 — The guide is a skill whose every practice cites a metric the tool reports.**
`skills/context-weight/SKILL.md` teaches five practices — (1) delegate bulk reads to
subagents that return conclusions (metric: sidechain vs main mass, D7 line); (2) cap tool
output entering the main context (metric: top ranked contributor, D4); (3) compact or
clear when the curve plateaus above ~40% of the window (metric: curve + inferred compaction
points, D6); (4) prefer fewer, denser turns (metric: calls × avg weight = total
re-submitted); (5) keep resident surfaces lean but PROPORTIONATE (metric: audit %, with the
under-1% reframe stated). It opens with the reframe (cache reads are the cheap path; the
lever is working set × turns). Rationale: advice without a measurement decays into
superstition; every sentence in the skill must be checkable with one command it also gives.

**D13 — Pruning is a HARNESS capability, never a skill capability. The kit advises; it never
claims to delete.** A skill is instructions loaded INTO the window; it is read-only text and
cannot mutate the message array. Only the harness can (`/compact`, auto-compaction, and — for
API callers — context editing `clear_tool_uses_20250919` / `clear_thinking_20251015`). No task
in this kit may write, imply, or ship anything that purports to remove context itself, and the
guide skill must state this limitation in plain words rather than leaving a reader to infer a
power the skill does not have. Rationale: the single most likely misunderstanding of this kit
is "install the skill and context gets cleaned up." That is false, and a user who believes it
will skip the practices that actually work. Naming the limit is what makes the rest credible.

**D14 — Prevention outranks pruning, and the guide must say so in that order.** Three levers
exist and they are not equal: (1) PREVENT — subagents that return conclusions instead of file
dumps, capped tool output, deferred tool loading, progressive disclosure: free, and lossless
because the mass never enters; (2) PRUNE — compaction and context editing: cheap but LOSSY,
the only lever that can cost accuracy; (3) MEASURE — knowing when to act, free. A file never
read costs nothing and loses nothing; a file read and later compacted costs the read, the
write, AND the fidelity. Rationale: "only pull the relevant context" is not retrievable after
the fact — every call submits the whole array, so there is no selective re-read of a window
already filled. The retrieval-shaped answer exists only PROSPECTIVELY, as delegation. Ordering
the levers wrong sends a reader to the lossy one first.

**D15 — Prunability is a two-class judgment, and `watch` reports the classes rather than a
timer.** SAFE to drop: tool results already acted on and summarized, superseded file reads
(read v1 → edited → read v2), thinking from resolved steps, verbose output whose conclusion is
recorded elsewhere. DANGEROUS to drop: the original task statement, decisions and their
rationale, anything that would have to be re-derived, unresolved error evidence, and early
constraints that bind late ("never push to main"). Auto-compaction cannot tell these apart —
it is a timer, not a policy. So `watch` ranks the current window into prunable vs load-bearing
mass and pairs the threshold with the checkpoint practice (D16 in the guide: write decisions to
disk BEFORE compacting, so the summary has an anchor it cannot lose — the same move this repo
already makes with kit `NOTES.md`, applied to sessions). Rationale: this is the entire
"without sacrificing accuracy" half of the request; a threshold alone answers *when* and says
nothing about *what*, which is where fidelity is actually lost.

## Interfaces (pinned)

```
context_weight.py session  [--harness claude|codex|copilot] [--session ID] [--top N]
                           [--projects-dir DIR] [--tasks-dir DIR ...] [--no-subagents]
                           [--codex-home DIR] [--copilot-home DIR] [--json]
context_weight.py overview [--harness all|claude|codex|copilot] [--days N] [--top N]
                           [--projects-dir DIR] [--codex-home DIR] [--copilot-home DIR] [--json]
context_weight.py audit    [--project DIR] [--surface PATH ...] [--budget-tokens N]
                           [--session ID] [--projects-dir DIR] [--json]
context_weight.py watch    [--session ID] [--window-tokens N] [--projects-dir DIR]
                           [--tasks-dir DIR ...] [--json]
context_weight.py demo     [--json]
```
`watch` is Claude-only by design (D3's fidelity ladder: Codex has no per-call provenance and
Copilot has no growth curve, so neither can support a live threshold — `watch --harness` is
NOT offered; the guide gives those two session-level advice instead). `--window-tokens`
defaults to the model's context window resolved from `data/pricing.json` (never hardcoded).
Defaults: `session --harness claude` picks the most recently modified transcript when
`--session` is omitted (reuse `sc.find_main_transcript`); `overview --days 7 --top 10`;
`audit --project .`. Exit 0 with a clean "nothing found" card when a home/dir is absent
(codex_usage `_print_absent` precedent) — exit nonzero only for bad arguments.

Pure-function layer (so tests never need the CLI): `claude_call_weights(records)`,
`detect_drops(weights)`, `attribute_growth(records)`, `codex_curve(parsed_or_lines)`,
`copilot_session_card(parsed)`, `audit_surfaces(project_dir, extra, budget)`,
`build_session_card(...)`, `build_overview(...)`, `classify_prunable(records)` →
`(prunable, load_bearing, unknown)` per D15, `build_watch_card(...)`, plus `render_*_markdown` /
`build_*_json` pairs. Exact signatures are the implementer's call WITHIN these names;
tests import the module by path (importlib pattern from existing tests' `_load`).

## Risks & tripwires

- **Risk: attribution creep into fake precision.** Tripwire: any est.-token figure printed
  without the `est.` label, or any est. figure multiplied by a price → stop, re-read D4/D5.
- **Risk: re-implementing existing parsers.** Tripwire: any new code that walks
  `session.shutdown` snapshots, rollout wrapper keys, or `message.usage` extraction instead
  of calling `cr.extract_record` / `codex_usage.*` / `copilot_usage.*` → stop; importlib.
- **Risk: touching the real homes from tests.** Tripwire: any test or verify without an
  explicit `--projects-dir`/`--codex-home`/`--copilot-home`/`--project` temp override, or a
  `Path.home()` appearing in the new test file → stop.
- **Risk: CLAUDE.md bloat.** Tripwire: `tests/test_guardrails_layout.py` red, or the
  CLAUDE.md diff exceeding the two pinned run-lines → stop, revert to the pinned text.
- **Risk: demo numbers drifting from fixture edits.** Tripwire: T7's pinned table disagrees
  with `demo` output → fix the code or the fixture, never the pin, and say so in NOTES.md.
- **Risk: skill description bloating the resident skill listing** (ironic failure).
  Tripwire: frontmatter `description` > ~2 sentences → trim.

## OUT OF SCOPE (executors must NOT)

- Re-optimize, rewrite, or trim ANY config surface: CLAUDE.md (beyond the two pinned
  run-lines), `codex/AGENTS.md`, `copilot/.github/copilot-instructions.md`, any existing
  skill, any agent file of another kit. The audit MEASURES surfaces; it never edits them.
- Invoke the real `claude`, `codex`, or `copilot` CLI from any task, test, or verify
  command; open any `*.db`/SQLite file; write anything under `~/.claude`, `~/.codex`,
  `~/.copilot`, or anywhere outside this repo and temp dirs. No network.
- Edit `bin/cost_report.py`, `bin/session_cost.py`, `bin/codex_usage.py`,
  `bin/copilot_usage.py`, any other existing `bin/` or `tests/` file, `data/` (all three
  pricing files), `.claude-plugin/`, `copilot/`, `codex/`, `README.md`, the generated
  `skills/*/references/` mirrors, or completed kits and their agents.
- Hardcode prices, price ratios, cache multipliers, or real model ids (sanctioned literals:
  D9's four constants, tier vocabulary, synthetic fixture ids/values, the verbatim honesty
  lines). No pip, no pytest. Do not commit, push, or re-install the plugin.
- Build automation that compacts, clears, or dispatches anything automatically — this kit
  measures and advises; it never acts on a session.
- Add a cross-harness dollar total, or price estimated (byte-derived) tokens, anywhere.
