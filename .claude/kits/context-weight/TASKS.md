# TASKS — context-weight

Repo root: `/path/to/polytropos`. Run all verify commands
from there. Read `PLAN.md` (same directory) first — especially the reframe, Repo facts,
decisions D1–D12, the OUT-OF-SCOPE fence, and `GUARDRAILS.md`.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's
`model` parameter when dispatching to `context-weight-implementer` (the parameter overrides
the agent's frontmatter default). `depends:` lists hard ordering. **Warm-cluster
candidates:** T1→T2 (both sonnet, both centered on `bin/context_weight.py` +
`tests/test_context_weight.py`), T3→T4→T5 (same pair of files, all sonnet), and T6→T7
(same pair, both sonnet) are serial same-model chains sharing a primary file — each chain
may run as one warm sidekick; the sidekick ends at each phase boundary so the
`context-weight-reviewer` can be dispatched between phases. T8 fans out fresh (different
primary files); T9 is a fresh haiku sweep. This kit's PLAN.md declares `autonomy: auto`.

Standing rules for every task:

- **Honesty ladder is law (PLAN D3/D4/D5).** Copilot never gets a growth curve; Codex never
  gets content attribution; their verbatim not-available lines must appear exactly as pinned.
  Every byte-derived figure carries the `est.` label; estimated tokens are NEVER priced; the
  three harnesses' dollars never merge into one total; `audit` shows tokens only.
- **Reuse, never re-implement (PLAN D5/Repo facts).** Load `bin/cost_report.py`,
  `bin/session_cost.py`, `bin/codex_usage.py`, `bin/copilot_usage.py` via the importlib
  pattern in `session_cost.py` lines 56–63 and call their functions (`extract_record`,
  `price`, `find_main_transcript`, `discover_task_dirs`, `parse_rollout`,
  `iter_rollout_files`, `_find_containers`, `_normalize_tokens`, `parse_events`,
  `effective_tokens`, `collect_sessions`, both `match_model`s, both `price_tokens`,
  `usd_to_aic`). Those four files are NEVER edited. Neither is any other existing `bin/` or
  `tests/` file, `data/` (all three pricing files), `.claude-plugin/`, `copilot/`, `codex/`,
  `README.md`, the `skills/*/references/` mirrors, or completed kits/agents. Sanctioned
  edit to an existing file in this whole kit: CLAUDE.md's pinned run-lines (T8) only.
- **Strictly read-only, temp fixtures only.** Never invoke the real
  `copilot`/`codex`/`claude` CLI; never open a `*.db`; never write under `~/.claude`,
  `~/.codex`, `~/.copilot`, or outside this repo + temp dirs; no network. Every test/verify
  overrides the home seams (`--projects-dir`/`--codex-home`/`--copilot-home`/`--project`)
  with `tempfile` fixtures. `Path.home()` count in `tests/test_context_weight.py`: ZERO
  (the engine's module-level `DEFAULT_*` constants are the only sanctioned uses, per the
  usage-reader precedent).
- **No hardcoded prices, price ratios, cache multipliers, or real model ids.** Sanctioned
  literals: `EST_CHARS_PER_TOKEN = 4`, `DROP_FRACTION = 0.5`,
  `DEFAULT_SURFACE_BUDGET_TOKENS = 5_000`, `CW_SCHEMA_VERSION = 1`, tier vocabulary,
  synthetic fixture ids/values, and the pinned verbatim honesty lines. Demo/test model ids
  are resolved at run time from the pricing files (first model key of a tier / first model
  key in the file).
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests
  [-p 'test_context_weight.py']` (the dotted-module form is broken on this machine). Paths
  via `Path(__file__).resolve()`, never `$PWD`. No `/private/tmp/` path in any deliverable.
  Do not commit or push. If a brief's pinned anchor/number disagrees with repo reality,
  STOP and report — never improvise.

---

## Phase 1 — Claude engine (full fidelity)

### T1 — bin/context_weight.py skeleton + Claude session curve
- status: done
- model: sonnet
- depends: (none)
- independent: no

**Brief.** Create `bin/context_weight.py` per PLAN D1/D2/D6/D7/D8/D9 and the pinned
Interfaces section, plus `tests/test_context_weight.py`. This task ships the module skeleton
(docstring explaining the reframe and the honesty ladder; constants
`CW_SCHEMA_VERSION = 1`, `EST_CHARS_PER_TOKEN = 4`, `DROP_FRACTION = 0.5`,
`DEFAULT_SURFACE_BUDGET_TOKENS = 5_000`; importlib loaders `cr` (cost_report), `sc`
(session_cost), `cx` (codex_usage), `cp` (copilot_usage); `DEFAULT_PROJECTS_DIR` mirroring
`session_cost._default_projects_dir()` including `CLAUDE_CONFIG_DIR`; `DEFAULT_CODEX_HOME` /
`DEFAULT_COPILOT_HOME` as module-level `Path.home()` defaults; argparse with subparsers
`session`/`overview`/`audit`/`demo` where only `session --harness claude` works after this
task — the other paths print a one-line "lands in a later task" placeholder and exit 0) and
the Claude `session` mode WITHOUT attribution (that is T2):

- `claude_call_weights(objs) -> (calls, sidechain, notes)`: iterate parsed JSONL objects in
  file order; for each with a `cr.extract_record` hit, weight = `input + cache_read +
  cache_write`; records with truthy top-level `isSidechain` go to the sidechain aggregate
  (`{"calls": n, "weight": total}`), the rest append
  `{"weight", "input", "cache_read", "cache_write", "output", "timestamp", "model"}` to
  `calls`. Dedupe by message id like `sc.collect` does (a message seen twice counts once).
- `detect_drops(weights) -> [ {"index", "before", "after"} ]`: an inferred compaction at i
  when `weights[i] < weights[i-1] * (1 - DROP_FRACTION)` — i.e. a ≥50% drop. Also
  opportunistically note records with truthy `isCompactSummary` (separate list, "confirmed").
- `build_session_card(...)` + `render_session_markdown(...)` + JSON builder: session id,
  files scanned, calls, avg/peak weight, total submitted (sum of weights), the growth curve
  as a text sparkline plus a compact table (call #, input, cache_read, cache_write, weight;
  cap rows at `--top`, default 20, first+last always shown), inferred compactions annotated
  with the word `inferred`, the sidechain line (D7) when sidechain calls exist, and the
  context carry cost: measured usage per model priced with OUTPUT ZEROED via `cr.price`
  against `data/pricing.json` (`cr.load_pricing()`), shown as `context carry cost: $X of $Y
  session total (Z%)` — dollars labeled `API-equivalent dollars — an estimate, not a bill.`
- Session resolution: `--session`/default-latest via `sc.find_main_transcript`; subagent
  transcripts via `sc.discover_task_dirs` + `sc.gather_files` unless `--no-subagents`
  (subagent `*.output` records are counted in the SIDECHAIN aggregate, not the main curve).
- Absent projects dir or no transcript → clean "nothing found" card, exit 0.

**Tests (same task, in `tests/test_context_weight.py`):** load the module by path with the
`_load` idiom from `tests/test_codex_usage.py`; build a synthetic transcript in a temp
projects dir using the EXACT fixture pinned below (it is also T7's demo fixture — write a
module-level helper `_claude_fixture_lines(model_id)` so demo tests reuse it); model id =
first sonnet-tier key of `data/pricing.json` computed at run time. Cover: weights
`[10000, 20000, 30000, 8000]`, avg `17000`, peak `30000`, total `68000`; exactly one
inferred drop at index 3 (30000→8000); sidechain `{"calls": 1, "weight": 5000}`; message-id
dedupe (duplicate line counts once); carry-cost equals a hand computation with
`cr.price(key, usage_with_output_zeroed, None, pricing)`; CLI end-to-end via
`main(["session", "--harness", "claude", "--projects-dir", tmp, "--json"])` capturing
stdout; absent-dir exit 0; and a read-only proof (snapshot the fixture tree's paths+mtimes
before/after a run and assert unchanged).

**Pinned Claude fixture** (one `<tmp>/projects/demo-proj/demo-claude.jsonl`; MODEL resolved
at run time; every assistant record non-sidechain unless said; give each a distinct
`message.id` m1–m5 and ISO timestamps one minute apart):
1. assistant m1 — usage in=9000 cache_read=0 cache_write=1000 out=200; content has one
   `tool_use` `{id: "toolu_d1", name: "Bash", input: {"command": "ls -la"}}`.
2. user — `tool_result` `tool_use_id: "toolu_d1"`, content = `"x" * 20000`.
3. assistant m2 — usage in=1000 cache_read=10000 cache_write=9000 out=300; `tool_use`
   `{id: "toolu_d2", name: "Read", input: {"file_path": "/workspace/demo.txt"}}`.
4. user — `tool_result` `tool_use_id: "toolu_d2"`, content = `"y" * 8000`.
5. assistant m3 — usage in=1000 cache_read=20000 cache_write=9000 out=150.
6. assistant m4 — usage in=8000 cache_read=0 cache_write=0 out=100.
7. assistant m5 — `isSidechain: true`, usage in=4000 cache_read=1000 cache_write=0 out=50.

**Acceptance:** module + tests land; all new tests pass; full suite stays green at 1022 +
new; `python3 bin/context_weight.py session --harness claude --projects-dir <tmp>` renders
the card; no edits outside `bin/context_weight.py` + `tests/test_context_weight.py`.

**Verify:**
`python3 -m unittest discover -s tests -p 'test_context_weight.py' && python3 -m unittest discover -s tests 2>&1 | tail -2`

### T2 — Claude attribution: ranked contributors + reconciliation
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Per PLAN D4. Extend `bin/context_weight.py` (additively — T1's outputs and test
numbers must not change except where this brief adds sections):

- `attribute_growth(objs) -> (entries, notes)`: first pass builds `tool_use_id → (tool_name,
  salient)` from assistant `tool_use` blocks — salient = `input["file_path"]` for
  Read/Edit/Write, `input["command"][:60]` for Bash, `input["prompt"][:60]` for Agent, else
  `""`. Second pass sizes additions: each `user` record's `tool_result` blocks (serialize
  non-str content with `json.dumps`; chars → `round(chars / EST_CHARS_PER_TOKEN)` est.
  tokens, attributed to the mapped tool via `tool_use_id`, unmapped ids → tool `(unknown)`),
  each plain user text block (attributed to `user input`), each `attachment` record's
  serialized `attachment` payload (attributed to `attachment`). Sidechain records are
  skipped (their content never entered the main window). Entries aggregate by
  `(tool_name, salient-or-empty)`; ranked descending by est. tokens.
- Reconciliation (pinned formula): `measured_growth = last_weight - first_weight +
  sum(before - after for each inferred drop)`; `unattributed = measured_growth -
  sum(attributed est. tokens)` (floor at 0 with a note if attribution exceeds growth —
  possible because estimates are estimates; say so honestly).
- Render into the session card: a `## What filled the window (est.)` table — rank, tool,
  salient, est. tokens (each labeled `est.`), capped at `--top` — followed by an
  `unattributed growth` row and one line explaining it (`system overhead, thinking, and
  tool schemas are not measurable from the transcript`). JSON mirror under
  `"attribution"` with `"basis": "bytes/4 heuristic — never priced"`.

**Tests (extend the file):** on the T1 fixture — Bash entry `5000` est. (20000 chars / 4),
Read `/workspace/demo.txt` `2000` est.; measured growth `8000 - 10000 + 22000 = 20000`;
unattributed `13000` **[SUPERSEDED BY T13 → now `12250`; T2's tests were updated
accordingly. Left here as the historical brief — do NOT verify T2 against this figure]**;
ranking order Bash > Read; an unmapped `tool_use_id` lands in
`(unknown)`; a dict-content tool_result is sized via its JSON serialization; sidechain
content excluded; the string `est.` present in rendered output; and a guard test asserting
the attribution section contains NO `$` character (est. tokens are never priced).

**Acceptance:** T1's pinned numbers unchanged; new attribution numbers as pinned; full
suite green.

**Verify:**
`python3 -m unittest discover -s tests -p 'test_context_weight.py' && python3 -m unittest discover -s tests 2>&1 | tail -2`

## Phase 2 — Codex + Copilot (honest fidelity) and the overview

### T3 — Codex session mode: curve where per-turn data exists
- status: done
- model: sonnet
- depends: T2
- independent: no

**Brief.** Per PLAN D3 (Codex rung) and Repo facts. Wire `session --harness codex
[--codex-home DIR] [--session ID]`:

- Locate rollout files via `cx.iter_rollout_files(home / "sessions", cutoff=None-or-days)`;
  `--session ID` filters to rollouts whose extracted session id (reuse `cx._first` with
  `cx.SESSION_KEYS`) or filename stem matches; default = the most recently modified rollout.
- `codex_curve(lines) -> (points, kind, notes)`: scan records in file order with
  `cx._find_containers(obj, cx.USAGE_CONTAINER_KEYS)` + `cx._normalize_tokens`. If any
  PER-TURN container exists (container key not in `cx.CUMULATIVE_CONTAINER_KEYS`), points =
  per-turn weights `input + cache_read` in order, `kind = "per-turn"`. Else if cumulative
  `total_token_usage` snapshots exist, points = `input + cache_read` per snapshot in order,
  `kind = "cumulative snapshots"` (and the card labels the curve with that exact phrase).
  Else no-token rollout → the codex_usage honesty line `no token usage found in these logs —
  activity counted, unpriced` and no curve. Never mix the two kinds in one curve (mirror
  `parse_rollout`'s cumulative-wins rule for totals).
- Card: calls/points, avg/peak weight, sparkline + table, model line via `cx.match_model`
  against `data/pricing.codex.json`, carry cost = totals from `cx.parse_rollout(lines)`
  priced with OUTPUT ZEROED via `cx.price_tokens` (only when the model matched — unmatched
  → tokens shown, `unpriced`), always followed by the verbatim subscription disclaimer from
  codex_usage: `Figures are API-equivalent dollars — a relative-burn proxy. Subscription
  (ChatGPT-plan) usage is usage-limited, not token-billed.`
- Attribution section prints EXACTLY: `provenance not recorded in these logs — byte-share
  of rollout record types shown as a labeled estimate`, then a per-record-`type` byte-share
  table (serialized line length per record type, % of file bytes, labeled `est.`). No
  content claims, no file paths, no dollars in this table.
- Absent home / empty sessions dir → clean card, exit 0.

**Tests:** temp codex home built with the `_tok_rec`/`_model_rec`/`_write_rollout` idioms
from `tests/test_codex_usage.py` (reproduce the small helpers locally — do NOT import that
test file). Pinned fixture (also T7's demo fixture; helper `_codex_fixture_records(model)`):
one `turn_context` record with model = first model key of `data/pricing.codex.json`, then
three `last_token_usage` containers: (in=3000, cached=0, out=100), (in=2000, cached=6000,
out=200), (in=1000, cached=12000, out=300) → weights `[3000, 8000, 13000]`, avg `8000`,
kind `per-turn`. Cover: the pinned weights; cumulative-only fixture yields kind
`cumulative snapshots`; mixed fixture uses per-turn only; the verbatim no-provenance line;
the byte-share table carries `est.` and no `$`; carry cost matches a hand computation via
`cx.price_tokens` with output zeroed; no-token rollout renders the activity-only line;
absent home exits 0; read-only proof over the temp home.

**Acceptance:** pinned numbers; Claude paths untouched (T1/T2 tests still pass); full suite
green.

**Verify:**
`python3 -m unittest discover -s tests -p 'test_context_weight.py' && python3 -m unittest discover -s tests 2>&1 | tail -2`

### T4 — Copilot session mode: session-average card, no curve, ever
- status: done
- model: sonnet
- depends: T3
- independent: no

**Brief.** Per PLAN D3 (Copilot rung). Wire `session --harness copilot
[--copilot-home DIR] [--session ID]`:

- Sessions live at `<copilot-home>/session-state/<id>/events.jsonl`; `--session` picks the
  dir name; default = most recently modified events.jsonl. Parse with `cp.parse_events`
  (read the file's lines; never a `*.db`).
- `copilot_session_card(parsed) -> card`: assistant turns = sum of
  `parsed["per_turn_output"][model]["turns"]`; when `parsed["has_token_details"]` and
  turns > 0: `session-average weight = (tokens.input + tokens.cache_read +
  tokens.cache_write) // turns`, labeled `session-average`; per-model output-turns table
  from `per_turn_output`. The card ALWAYS prints the verbatim line: `growth curve: not
  available — Copilot events do not record per-turn input/cache token splits`. No
  attribution section at all. Carry cost: `parsed["tokens"]` with OUTPUT ZEROED priced via
  `cp.price_tokens` against the LAST model (multi-model sessions flagged `≈` exactly like
  copilot_usage does) → USD + AIC via `cp.usd_to_aic`, from `data/pricing.copilot.json`,
  labeled `API-equivalent dollars — an estimate, not a bill.`; no tokenDetails → tokens
  `not recorded`, no dollars (never zeros).
- Absent home / no sessions → clean card, exit 0.

**Tests:** temp copilot home with the `_ev`/`_td` idioms from `tests/test_copilot_usage.py`
(local helpers). Pinned fixture (also T7's demo; helper `_copilot_fixture_lines(model)`,
model = first model key of `data/pricing.copilot.json`): two `assistant.message` events
(outputTokens 100 and 200, distinct apiCallIds) + one `session.shutdown` with
`tokenDetails = _td(10000, 30000, 2000, 300)` → turns `2`, session-average weight `21000`.
Cover: the pinned average; the verbatim no-curve line byte-exact; carry cost matches a hand
computation (output zeroed) and appears with both USD and AIC; a no-shutdown fixture prices
nothing and fabricates nothing; JSON mode round-trips; read-only proof; absent home exit 0.

**Acceptance:** pinned numbers; T1–T3 tests untouched and green; full suite green.

**Verify:**
`python3 -m unittest discover -s tests -p 'test_context_weight.py' && python3 -m unittest discover -s tests 2>&1 | tail -2`

### T5 — overview: the cross-session working-set table
- status: done
- model: sonnet
- depends: T4
- independent: no

**Brief.** Per PLAN Interfaces. `overview [--harness all|claude|codex|copilot] [--days N=7]
[--top N=10]` renders ONE SECTION PER HARNESS (never a merged table, never a cross-harness
dollar total):

- Claude: walk `--projects-dir` `*.jsonl` with mtime ≥ cutoff; per session (by file):
  calls, avg weight, peak, total submitted, inferred compactions count, sidechain share —
  reusing T1's pure functions per file. Rank by total submitted, cap `--top`.
- Codex: `cx.iter_rollout_files` with the cutoff; per rollout: points, avg weight, kind
  (per-turn / cumulative snapshots / no tokens).
- Copilot: `cp.collect_sessions(session_dir)`; per session: assistant turns,
  session-average weight (or `n/a` without tokenDetails — never 0).
- Each section ends with that harness's carry-cost line for the window (measured tokens,
  output zeroed, its own pricing file — same labels as T1/T3/T4). A harness whose home is
  absent prints one clean line and the other sections still render; exit 0.

**Tests:** one temp tree holding all three fixture homes (reuse the three `_*_fixture_*`
helpers); `main(["overview", "--harness", "all", ...overrides..., "--json"])` → three
sections with the pinned per-session numbers (Claude avg 17000/4 calls/1 compaction; Codex
avg 8000/3 points; Copilot 21000/2 turns); absent codex home → its clean line while Claude
and Copilot still render; `--days` filtering (an old-mtime Claude transcript excluded);
JSON has three top-level harness keys and NO combined dollar field (assert absence);
`--harness claude` renders only that section.

**Acceptance:** pinned numbers; no merged totals; full suite green.

**Verify:**
`python3 -m unittest discover -s tests -p 'test_context_weight.py' && python3 -m unittest discover -s tests 2>&1 | tail -2`

## Phase 3 — Audit + demo

### T6 — audit: resident surfaces vs budget, tokens only
- status: done
- model: sonnet
- depends: T5
- independent: no

**Brief.** Per PLAN D10. `audit [--project DIR=.] [--surface PATH ...]
[--budget-tokens N=DEFAULT_SURFACE_BUDGET_TOKENS] [--session ID] [--projects-dir DIR]
[--json]`:

- `audit_surfaces(project_dir, extra_surfaces, budget) -> (sections, notes)` over the
  pinned lookup: claude → `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md`; codex →
  `AGENTS.md`; copilot → `.github/copilot-instructions.md`, `AGENTS.md`. Per surface:
  `present`/`absent`; when present: bytes, est. tokens = `round(chars /
  EST_CHARS_PER_TOKEN)` (labeled `est.`), % of budget. `--surface` extras land in an
  `extra` section (path relative to the project dir; a missing extra is a note, not an
  error). Per harness section: total est. tokens, total % of budget, and `per 100 calls:
  N tokens re-submitted (est.)` = total × 100. NO dollars anywhere in audit output (tokens
  are byte-estimates — D5).
- Fixed closing line, verbatim: `system prompt, tool schemas, plugin skill listings, MCP
  definitions — resident but not measurable here; measure their effect with the session
  subcommand`.
- With `--session` (+ `--projects-dir` seam): compute the session's avg call weight via
  T1's functions and print the reframe line: `resident surfaces ≈ N% of this session's
  avg per-call weight (X of Y tokens) — the working set, not config, is the lever.`
  (N = combined est. tokens of all DISTINCT present surfaces / avg weight; a surface listed
  under two harnesses counts once here.) Without `--session`, the line is omitted.
- Read-only over the project dir; text files only.

**Tests:** temp project dir fixture (also T7's demo; helper `_audit_fixture(dir)`):
`CLAUDE.md` = 2000 chars, `AGENTS.md` = 1200 chars, `.github/copilot-instructions.md` =
800 chars → est. `500`/`300`/`200` tokens = `10%`/`6%`/`4%` of the 5000 default budget;
copilot section totals 500 est. (200 + shared AGENTS.md 300); per-100-calls lines (claude
`50000`); absent `CLAUDE.local.md` listed `absent`; `--surface` extra counted; custom
`--budget-tokens 1000` → CLAUDE.md `50%`; the verbatim closing line; NO `$` in audit
output (assert); with `--session` against the Claude fixture → reframe line with
`500 + 300 + 200 = 1000` distinct-surface tokens over avg weight 17000 → `≈ 6%`; JSON
round-trip; read-only proof.

**Acceptance:** pinned numbers; audit is dollar-free; full suite green.

**Verify:**
`python3 -m unittest discover -s tests -p 'test_context_weight.py' && python3 -m unittest discover -s tests 2>&1 | tail -2`

### T7 — demo: one command, four cards, pinned numbers
- status: done
- model: sonnet
- depends: T6
- independent: no

**Brief.** Per PLAN D11. `demo [--json]` builds, inside ONE
`tempfile.TemporaryDirectory()` (precedent: `routing_scorecard.run_demo`), the four pinned
fixtures via the shared helpers the earlier tasks placed in the TEST file — which the
ENGINE cannot import; therefore MOVE the four fixture builders
(`_claude_fixture_lines`, `_codex_fixture_records`, `_copilot_fixture_lines`,
`_audit_fixture`) into `bin/context_weight.py` as `demo_*` functions in this task and
re-point the tests at the engine's copies (the one sanctioned test-file refactor; fixture
CONTENT stays byte-identical, all pinned numbers unchanged). Then run all four cards
against the temp homes and print them in order: Claude session, Codex session, Copilot
session, audit (with `--session` wired to the Claude fixture so the reframe line shows).
Model ids resolved at run time: first sonnet-tier key of `data/pricing.json`, first model
key of `data/pricing.codex.json`, first model key of `data/pricing.copilot.json`. Header
line names it a synthetic smoke touching no real data.

**Pinned demo output facts (regression surface):** Claude weights
`[10000, 20000, 30000, 8000]`, avg `17000`, 1 inferred compaction, sidechain `5000`,
Bash `5000 est.` > Read `2000 est.` > `assistant output (measured)` `750 measured`
   (rank 3 — sorted by MAGNITUDE, not by category; the orchestrator's earlier correction
   said "ranked #1", over-generalizing from T13's REAL sessions where assistant output is
   the largest contributor. In this synthetic fixture it is 750, so rank 3 is correct.
   T7's implementer flagged the conflict rather than inflating the fixture or special-casing
   the sort — the right call), `unattributed growth` `12250` unranked `—` but positioned
   FIRST by magnitude (NOT 13000 — T13 subtracted the measured assistant output; the
   original pin predates T13); Codex weights
`[3000, 8000, 13000]`, avg `8000`, the verbatim no-provenance line; Copilot session-average
`21000`, 2 turns, the verbatim no-curve line; audit `500`/`300`/`200` est. tokens =
`10%`/`6%`/`4%`, reframe `≈ 6%`. All four honesty labels present (`est.`, `inferred`,
both verbatim not-available lines, the not-measurable closing line).

**Tests:** run `main(["demo"])` and `main(["demo", "--json"])` capturing stdout — assert
every pinned fact above; assert the temp dir is gone afterwards; assert demo touched
neither `~/.claude` nor any real home (it never references them — assert no `Path.home()`
call happens on the demo path by asserting the printed card contains no home path);
`json.loads` round-trip.

**Acceptance:** `python3 bin/context_weight.py demo` prints all four cards, exits 0, pinned
facts hold; every earlier test still green after the fixture-helper relocation; full suite
green.

**Verify:**
`python3 bin/context_weight.py demo >/dev/null && python3 -m unittest discover -s tests 2>&1 | tail -2`

## Phase 4 — Guide skill + wiring

### T8 — skills/context-weight/SKILL.md + docs + pinned CLAUDE.md run-lines
- status: done
- model: sonnet
- depends: T7
- independent: no

**Brief.** Per PLAN D12. Three deliverables, no others:

1. **`skills/context-weight/SKILL.md`** (new file; frontmatter conventions from
   `skills/cost-report/SKILL.md` — the plugin is LIVE, so this becomes runtime behavior;
   keep the description tight, it is itself resident context). Frontmatter (verbatim):
   ```yaml
   ---
   name: context-weight
   description: Measure what fills the context window each turn — per-call token weight, growth curve, ranked contributors, and a resident-surface audit across Claude Code, Codex CLI, and Copilot CLI — then apply the practices that shrink the working set. Use when the user asks why cache reads are high, what is filling context, or how to lower per-turn cost.
   allowed-tools: Bash, Read
   ---
   ```
   Body: (a) the reframe, stated plainly (cache reads are the discounted path working; the
   cost driver is resident context × API calls; config surfaces are usually under 1% —
   measure before optimizing); (b) how to run — `${CLAUDE_PLUGIN_ROOT}` invocations of
   `session` / `overview` / `audit` / `demo` with the relative-to-SKILL.md fallback, and
   what each column means (weight, est., inferred, session-average); (c) the five practices,
   EACH tied to its metric exactly as pinned in PLAN D12 (delegation ↔ sidechain split;
   output caps ↔ top contributor; compaction near a ~40%-of-window plateau ↔ curve +
   inferred points; fewer denser turns ↔ calls × avg weight; proportionate config ↔ audit %
   + reframe); (d) honesty rules the skill must repeat: estimates are labeled `est.` and
   never priced, Copilot has no curve, Codex has no attribution, dollar figures are
   API-equivalent estimates, never bills, and per-harness only. No prices, ratios, or model
   ids anywhere in the skill.
2. **`docs/CONTEXT-WEIGHT.md`** (new, short): what the tool measures per harness (the D3
   ladder as a table), the D4 attribution method and its limits, the D10 audit lookup, and
   the pinned demo facts as the regression reference.
3. **CLAUDE.md** — append EXACTLY these two lines to the run-block in "How to run things"
   (after the `memory_store.py review` line, before the `copilot_pricing.py knobs` line;
   nothing else in the file changes):
   ```
   python3 bin/context_weight.py demo                # context-weight smoke: per-call weight curves, ranked contributors, resident-surface audit — all synthetic, no real data (lands with the context-weight kit)
   python3 bin/context_weight.py session             # what filled this window: latest Claude session's per-call weight, growth curve, ranked contributors (reads ~/.claude read-only; --harness codex|copilot at their honest fidelity)
   ```

**Acceptance:** three deliverables exactly; CLAUDE.md ≤ 16,000 bytes and
`tests/test_guardrails_layout.py` green (all sentinels intact); full suite green; `git
status` shows no other modified file.

**Verify:**
`python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' && python3 -m unittest discover -s tests 2>&1 | tail -2 && git status --porcelain`

## Phase 5 — Act on the measurement: live threshold + accuracy policy

*Added after the architect pass, from a design exchange with the user. The kit as built MEASURES
but never tells you what to DO at 700K of a 1M window. These two tasks close that loop. Read
PLAN.md **D13, D14, D15** before starting either — they are binding and were written for exactly
this phase. Warm-cluster candidate: T10 → T11 is a serial sonnet chain (T11 documents what T10
ships), but they touch different files, so a fresh spawn for T11 is equally fine.*

### T10 — `watch`: live weight, distance to threshold, and what is safely prunable
- status: done
- model: sonnet
- depends: T2
- independent: no

**Brief.** Add the `watch` subcommand to `bin/context_weight.py` and its tests to
`tests/test_context_weight.py`. Touch no other file. This is the ONLY new engine surface in
Phase 5.

Why (PLAN.md D15): `session` answers "what filled this window" after the fact. `watch` answers
the live question — *I am deep into a session, what is my weight, how close am I to the point
where I should act, and what can I drop without losing anything load-bearing?* A threshold alone
says only WHEN; the two-class split says WHAT, and that is the entire "without sacrificing
accuracy" half of the request.

Reuse, do not re-derive: `claude_call_weights` and `attribute_growth` from T1/T2 already give
per-call weight and provenance. `watch` is a new **view** over them plus one new classifier.

Ship `classify_prunable(records) -> (prunable, load_bearing, unknown)`, a pure function, per
D15's two classes:
- **prunable** — tool results whose call is followed by a later assistant message that acted on
  them; superseded file reads (same path read more than once — every read but the last);
  thinking blocks from calls that completed; large command output whose bytes exceed the
  ranked-contributor threshold from T2.
- **load-bearing** — the first user message of the session; any message containing a decision or
  constraint marker (the classifier's marker list is the implementer's call, but it MUST be a
  documented module-level constant, not inline regex literals scattered through the function);
  tool results whose `is_error` is true and which have no later successful retry of the same
  tool; the most recent read of any path.
- **unknown** — everything else. Report it as its own row. Do NOT force a binary; an honest
  third bucket beats a confident wrong one, and the same honesty rule governs the rest of this
  kit (D3, D10).

Card shows: current weight, `--window-tokens` (default resolved from `data/pricing.json`'s
`context_window` for the session's model — NEVER hardcode 1000000), percent of window, the
three-class mass split with est. labels per D9, and a one-line recommendation keyed to the D14
ladder — below 40%: "no action"; 40–60%: "delegate new bulk reads, do not inline"; above 60%:
"checkpoint decisions to disk, then compact".

Hard constraints: `watch` is **Claude-only** — do not add `--harness`; a Codex/Copilot invocation
must exit 0 with the pinned line `watch: Claude sessions only — Codex has no per-call provenance
and Copilot has no growth curve (see audit/session for their honest fidelity)`. Read-only, no
`Path.home()` in the engine, injectable `--projects-dir`/`--tasks-dir`. Est. figures carry `est.`
and are NEVER priced (D5/D9). The command must never claim to delete anything (D13).

**Additions from the Phase 2-3 review (opus) — all on this task's surface:**

1. **`session` lacks the sidechain guard that `overview` has.** The Phase-1 fix landed only in
   `build_claude_overview_section()` (`bin/context_weight.py:1240`); `find_main_transcript`, which
   only `session` uses, has none. When the newest transcript is sidechain-only (subagents hit this;
   the reviewer reproduced it running as one), `session` renders `0 call(s)`, avg 0, `$0.00`, and —
   post-T13 — zero-valued attribution rows that read as measurements, beside a large sidechain
   figure. Add the same note to the `session` path. Frequency caveat: 0 of 8 transcripts are
   `agent-*.jsonl` in the main session, so this is rarer than the review's "70%" — real, not common.
   **[CORRECTED mid-run — the caveat above is WRONG, kept for the record.]** That check globbed the
   PROJECTS dir; subagent transcripts live in the session's TASKS dir. Reproduced live: running
   `session` while a dispatched implementer was working returned a card for
   `agent-a49523d4cfd5e71c9` — `0 call(s)`, avg 0, and a `0 measured` attribution row. Dispatching
   any subagent triggers this for a concurrent `session` run, so during kit execution it is close
   to the COMMON case, not a rare one. The code requirement is unchanged; only the priority rises.

2. **Put `% of window` on the `session` card.** The metric that answers "at 700K, what do I do?" is
   percent-of-window, and NO shipped command reports it — yet D12 practice #3 tells users to compact
   "when the curve plateaus above ~40% of the window". The kit currently states a threshold it
   cannot measure. One division against `context_window` already in `data/pricing.json` (never
   hardcode 1000000 — the existing `--window-tokens` resolution rule applies).

3. **Add one derived `avoidable mass` line above the attribution table.** Post-T13 the ranked table
   leads with rows nobody can act on — on a real session: assistant output 364,235 (can't not-reply),
   unattributed 240,639 (unknown by definition), user input 237,634 (can't not-ask) — so a reader
   scanning the top concludes there is nothing to do, while the ~34,000 of tool-ingested mass that IS
   avoidable sits below the fold. Emit e.g.
   `avoidable (tool-ingested) mass: 34,333 est. of 905,000 (4%) — top source: Bash`.
   Computable from data already in the card; converts a census into a decision. Keep the `est.` label
   and do not price it.

4. **Downsample the sparkline to ~60 chars.** At 373 calls it is 373 chars wide, wraps, and destroys
   the plateau read — and the plateau shape is precisely the signal practice #3 cites.

**Acceptance:** `watch` present with the pinned flags; `classify_prunable` is pure and unit-
tested across all three classes including the superseded-read and unresolved-error cases; the
Codex/Copilot refusal line is byte-exact; `--json` validates; window size comes from
pricing.json; no other file modified; full suite green.

**Verify:**
`cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_context_weight.py' 2>&1 | tail -3 && python3 bin/context_weight.py watch --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'prunable' in d and 'load_bearing' in d and 'unknown' in d; print('watch json ok')" && grep -c 'Claude sessions only' bin/context_weight.py && ! grep -n '1000000' bin/context_weight.py && python3 -m unittest discover -s tests 2>&1 | tail -2 && git status --porcelain`

### T11 — Guide skill: the three levers, the checkpoint practice, and what a skill CANNOT do
- status: done
- model: sonnet
- depends: T8, T10
- independent: no

**Brief.** Extend `skills/context-weight/SKILL.md` (created in T8) with three sections. Edit that
file and `docs/CONTEXT-WEIGHT.md` only — no engine change, no CLAUDE.md change (T8 already
pinned its run-lines; add none).

Why (PLAN.md D13/D14): the kit's most likely misreading is "install the skill and context gets
cleaned up." A skill is text loaded INTO the window — it cannot mutate the message array. Saying
so plainly is what makes the rest of the advice credible, and a reader who believes the false
version will skip the practices that actually work.

Add, in this order:

1. **"What this skill cannot do"** — near the top, not buried. State that skills and agents
   cannot remove context; only the harness can (`/compact`, auto-compaction; API callers also
   have context editing). This skill tells you when and what; the harness does it.
2. **The three levers, in priority order** (D14) — PREVENT (delegation, capped output, deferred
   loading, progressive disclosure: free and lossless) > PRUNE (compaction, context editing:
   cheap but lossy — the only lever that costs accuracy) > MEASURE. Include the reason
   prevention wins: a file never read costs nothing and loses nothing; a file read then
   compacted costs the read, the write, and the fidelity. State that "only pull the relevant
   context" is not available retrospectively — every call submits the whole array — and that the
   retrieval-shaped answer exists prospectively, as delegation.
3. **Checkpoint before compacting** — the accuracy protection. Write decisions, constraints, and
   open questions to a file (`NOTES.md`, `tasks/todo.md`) BEFORE compaction runs, so the summary
   has an anchor it cannot lose and the detail stays re-readable on demand. Note that this repo
   already does exactly this with kit `NOTES.md`; this is the same move applied to sessions.
   Pair it with D15's two classes so the reader knows what compaction may safely discard.

**Condition attached by the Phase 2-3 reviewer to its `watch` ruling (in scope, not a fence
amendment):** it ruled `watch` should stay skill-only rather than gain a CLAUDE.md run-line —
because CLAUDE.md is itself a resident surface re-submitted on every call forever, so spending
permanent resident tokens to advertise the command whose purpose is reducing resident mass is
self-refuting. That ruling only holds **if the skill actually fires**. The entire discovery cost
therefore lands on the frontmatter `description`, which is what sits in the always-loaded skill
listing. Write that description around the motivating TRIGGER — "my context is huge", "I'm at
700K", "should I compact?" — not a feature summary. Hold PLAN's ~2-sentence cap.

Every practice keeps T8's rule: cite the metric and the command that shows it — here,
`python3 bin/context_weight.py watch`. Add one Codex/Copilot line: no live threshold is possible
there (D3), so use `session`/`overview` after the fact and apply the same practices by habit.

**[AMENDED BY THE ORCHESTRATOR BEFORE DISPATCH — two defects in this task's own acceptance.]**

*Defect A — the acceptance contradicted the reviewer's condition.* It said "SKILL.md frontmatter
byte-unchanged from T8", but `description` IS frontmatter and the reviewer's condition (above)
requires rewriting it. T8's shipped description opens `Measure what fills the context window each
turn — per-call token weight, growth curve, ranked contributors, and a resident-surface audit
across...` — a FEATURE SUMMARY, precisely what the condition forbids. Both could not be satisfied.
Resolution: the reviewer's condition is later and substantive; the byte-unchanged clause was stale.

*Defect B — the guard was inert.* `skills/context-weight/SKILL.md` is UNTRACKED
(`git status` shows `?? skills/context-weight/`), so `git diff -- <that path>` emits nothing,
`grep -q` exits 1, and the leading `!` inverts that to a PASS. The check could never fail — it
would have waved through any frontmatter edit, including the one it existed to forbid. Verified
empirically before amending. Same family as the T9 grep defect: a check that cannot fail is not a check.

**Acceptance (amended):** all three sections present; the cannot-do statement appears before any
practice; levers are in PREVENT > PRUNE > MEASURE order; the checkpoint section names a concrete
file; `watch` is cited with a runnable command; **`name:` and `allowed-tools:` unchanged
(`context-weight` / `Bash, Read`), and `description:` REWRITTEN to lead with the motivating
trigger — it must contain at least two of the user-phrasings the reviewer named ("context is
huge", "700K", "should I compact", "why are my cache reads high") and stay within PLAN's
~2-sentence cap**; full suite green; only the two named files modified.

**Verify (amended — works on an untracked file):**
`cd /path/to/polytropos && grep -c 'cannot' skills/context-weight/SKILL.md && grep -c 'context_weight.py watch' skills/context-weight/SKILL.md && python3 - <<'PY'
import re,pathlib
fm=pathlib.Path("skills/context-weight/SKILL.md").read_text().split("---")[1]
d=re.search(r"description:\s*(.+)",fm).group(1)
assert re.search(r"name:\s*context-weight",fm), "name: changed"
assert re.search(r"allowed-tools:\s*Bash, Read",fm), "allowed-tools: changed"
trig=sum(p in d.lower() for p in ["context is huge","700k","should i compact","cache reads"])
assert trig>=2, f"description lacks motivating triggers (found {trig}, need 2+): {d}"
assert d.count(".")<=3, f"description exceeds the ~2-sentence cap: {d}"
print(f"frontmatter ok — {trig} triggers present")
PY
&& git status --porcelain && python3 -m unittest discover -s tests 2>&1 | tail -2`

### T12 — `bin/plugin_staleness.py`: is the INSTALLED plugin what the repo says?
- status: done
- model: sonnet
- depends: (none)
- independent: yes

**Brief.** New file `bin/plugin_staleness.py` plus `tests/test_plugin_staleness.py`. Touch no
other file. This is deliberately a SEPARATE script, not a `context_weight.py` subcommand —
context weight is about what fills a window; this is about whether the code answering you is the
code you wrote. Adjacent concern, co-located in this kit only because it is small and shares the
"installed artifact silently diverged from source" theme. Do not fold it into `context_weight.py`.

Why (observed 2026-07-24, the incident that motivated this task): the plugin installed at user
scope was **18 days and 22 commits behind** the repo. `claude plugin update` reported "already at
the latest version" — correctly, because it compares `plugin.json`'s **version string**, and
content is not hashed. So the repo's `architect` skill said "write fences to the kit dir" while
the *running* skill still said "append to the target project's CLAUDE.md" — the exact instruction
whose removal was the point of the `context-rules` kit. `data/pricing.json` in the install had no
`claude-opus-5` and a `cached_date` of 2026-07-01, so every `/route` and `/fable-check` answer
came from a stale model table. Nothing warned at the point of use. This is the third instance of
one pattern in a single day (stale `dist/` → false `aesop sync` drift; stale lockfile → `fast-uri`
looked patched; stale plugin cache → 18-day-old skills), and the only one with no guard.

Resolve the install path the way the product does — read
`~/.claude/plugins/installed_plugins.json`, take `plugins["<name>@<marketplace>"][0].installPath`.
Do NOT hardcode a cache path or a version directory (the version dir changes on every bump —
`0.1.0` became `0.2.0` during the incident).

Compare, and report per file: `skills/*/SKILL.md`, `data/pricing*.json`, `CLAUDE.md`, `bin/*.py`.
For each, `identical` / `DIFFERS` / `missing`. Report the installed `version` vs `plugin.json`'s,
and the recorded `gitCommitSha` vs the repo's `git rev-parse HEAD` **only when a `.git` directory
is present** — the installed copy has none, so this must degrade gracefully rather than crash.
Exit **0 when in sync**, **3 when drifted** (`doctor`/`sync` exit-3 precedent in this repo), 0
with a clean "not installed" card when the plugin is absent — never a traceback.

Print the actionable remedy verbatim when drifted, because the non-obvious part is that content
alone will not trigger an update:
`stale install — bump "version" in .claude-plugin/plugin.json, then: claude plugin marketplace update <marketplace> && claude plugin update <name>@<marketplace> (restart to apply)`

Hard constraints: **read-only** — never write to `~/.claude`, never invoke `claude plugin update`
or any real CLI from the script or its tests (the script PRINTS the commands; the human runs
them). Engine code has ZERO `Path.home()`: take `--installed-manifest PATH` and `--repo DIR`
seams so tests drive it entirely from temp fixtures. Stdlib only. `--json` mode. Match `bin/`
conventions (`main(argv) -> int`, argparse, module docstring explaining the why).

**Acceptance:** script + tests exist; exit 0 in-sync / 3 drifted / 0 not-installed, each covered
by a test using temp fixtures; zero `Path.home()` in the engine; the remedy string is byte-exact
and includes the version-bump step; no real CLI invoked anywhere; `--json` validates; full suite
green.

**Verify:**
`cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_plugin_staleness.py' 2>&1 | tail -3 && ! grep -n 'Path.home()' bin/plugin_staleness.py && ! grep -nE 'subprocess|claude plugin (update|install)' bin/plugin_staleness.py | grep -v '^\s*#' && python3 bin/plugin_staleness.py --json | python3 -c "import json,sys; json.load(sys.stdin); print('json ok')" && python3 -m unittest discover -s tests 2>&1 | tail -2 && git status --porcelain`

### T13 — Attribute assistant output: the majority of "unattributed" is measured, not unknown
- status: done
- model: sonnet
- depends: T2
- independent: no

**Brief.** Extend `bin/context_weight.py` + `tests/test_context_weight.py`. No other file.

Why — the Phase-1 reviewer decomposed the `unattributed growth` gap on three REAL transcripts
and found the majority of it is not unmeasurable at all:

| session | measured growth | attributed | unattributed | of which assistant output |
|---|---:|---:|---:|---:|
| 35-call | 37,942 | 12,787 (34%) | 25,155 (66%) | 20,836 = **83% of the gap** |
| 298-call | 815,598 | 321,337 (39%) | 494,261 (61%) | 282,498 = **57% of the gap** |

Every assistant reply — text, thinking, and the `tool_use` JSON — is appended to the message
array and re-submitted on the next call, so by D2's own definition it IS context growth. D4
sizes only USER-side additions (tool_result / text / attachment) and dumps the assistant side
into the unknown bucket. That mass is already in the transcript as an exact `output_tokens`
count: it needs **no `est.` label and no byte heuristic** — it is measured.

Consequences to fix:
1. Add an `assistant output (measured)` row to the attribution table, sourced from the summed
   `output` of the main (non-sidechain) calls `claude_call_weights` already returns. Label it
   `measured`, NOT `est.` — it is the one row in that table that is exact. Rank it inline with
   the est. rows (largest first) rather than appending it, and subtract it from `unattributed`.
2. **Rank the `unattributed growth` row inline too.** The reviewer found it would place #1 in
   every real session tested, yet it prints below the ranked list — so a reader scans 1..N,
   then meets a larger unknown, and reasonably concludes the tool does not know what filled the
   window. Keep it visually distinct (the `—` rank marker is fine) but position it by size.
3. **The pinned explanation line is now partly inaccurate** and must change. It currently reads
   `system overhead, thinking, and tool schemas are not measurable from the transcript **[SUPERSEDED BY T13 — see the corrected line in D4; left as the historical brief, do NOT verify T2 against it]**.`
   Thinking is inside assistant output and IS measured. Replace with:
   `system overhead and tool schemas are not measurable from the transcript; assistant output
   (including thinking) is measured exactly and shown above.`
   This line was pinned verbatim in T2's brief, so T2's implementer had no latitude — the
   correction belongs here.

Expected effect (state the before/after in your report): unknown share falls from ~61% to ~26%
on the 298-call profile and from 66% to ~11% on the 35-call profile.

Do NOT price the new row, do not merge harness dollars, and do not touch the Codex/Copilot
paths — this is Claude-only, and D3's ladder is unchanged. T1's pinned fixture numbers
(calls=4, avg 17000, peak 30000, total 68000, sidechain 1/5000) must be unchanged; only the
attribution section moves.

**Acceptance:** `assistant output (measured)` row present and labeled `measured` not `est.`;
`unattributed` reduced by exactly that amount; both it and the unattributed row ranked inline
by size; the corrected explanation line present verbatim and the old one gone; no `$` in the
attribution section; T1's pinned numbers unchanged; full suite green.

**Verify:**
`cd /path/to/polytropos && grep -c 'assistant output (measured)' bin/context_weight.py && grep -c 'assistant output (including thinking) is measured exactly' bin/context_weight.py && ! grep -q 'thinking, and tool schemas are not measurable' bin/context_weight.py && python3 -m unittest discover -s tests -p 'test_context_weight.py' 2>&1 | tail -3 && python3 -m unittest discover -s tests 2>&1 | tail -2`

## Phase 6 — Close-out

### T9 — Final verification sweep
- status: done
- model: haiku
- depends: T11, T12, T13
- independent: no

**Brief.** Mechanical close-out; change NOTHING unless a check fails (then mark blocked and
report — do not fix beyond trivial self-inflicted misses). Run, in order, from the repo
root, and paste all output:
1. `python3 -m unittest discover -s tests 2>&1 | tail -3` — expect OK, ≥ 1022 tests.
2. `python3 bin/context_weight.py demo | head -40` — four cards, pinned facts spot-checked
   (Claude avg 17000, Codex avg 8000, Copilot 21000, audit 10%/6%/4%).
3. `python3 bin/context_weight.py demo --json | python3 -c "import json,sys; json.load(sys.stdin); print('json ok')"`.
4. `python3 bin/sync_pricing_refs.py --check`.
5. `wc -c CLAUDE.md` — ≤ 16000.
6. `git status --porcelain` — only sanctioned paths (new: `bin/context_weight.py`, `bin/plugin_staleness.py`, `tests/test_plugin_staleness.py`,
   `tests/test_context_weight.py`, `skills/context-weight/`, `docs/CONTEXT-WEIGHT.md`,
   `.claude/kits/context-weight/`, `.claude/agents/context-weight-*.md`; modified:
   `CLAUDE.md` only).
7. `git diff --quiet -- bin/cost_report.py bin/session_cost.py bin/codex_usage.py bin/copilot_usage.py data && echo "reuse-only surfaces clean"`.
8. Path.home() guardrail — use the AST, NOT grep. `grep -c` returns 1 because the test
   file's own docstring documents the zero-count contract in prose; the Phase-1 review
   confirmed this yields a FALSE failure. Run instead:
   `python3 .claude/kits/context-weight/_home_check.py tests/test_context_weight.py`

   **[ORCHESTRATOR NOTE — read before running check 8.]** That helper did NOT exist when this
   brief was written; no task created it. It has since been written (kit-local, read-only) so this
   check is now runnable — do NOT hand-roll an AST parser, and do NOT fall back to `grep`.
   Usage: `python3 .claude/kits/context-weight/_home_check.py FILE [FILE ...]` (expects 0), or
   `--expect 3 bin/context_weight.py` for the engine's sanctioned calls.
   **Ignore every LINE NUMBER in this brief.** The engine's sanctioned calls have moved twice
   during this run (~148/153/154 → 191/196/197 → **229/234/235** as of now) because later tasks
   grew the file. The COUNT is the contract, never the location; the helper counts and is immune.
   Expected: engine **3**, `tests/test_context_weight.py` **0**, `tests/test_plugin_staleness.py` **0**.
   — or inline: parse with `ast`, count `Call(func=Attribute(value=Name("Path"), attr="home"))`,
   expect `0`. Repeat for `tests/test_plugin_staleness.py` (also 0). The engine's 3 calls in
   `bin/context_weight.py` are SANCTIONED (module-level `DEFAULT_*` plus
   `_default_projects_dir()` called once at import) — do not flag them.

**Acceptance:** all eight checks pass with output shown.

**Verify:** the eight commands above, run in order.

9. **Plugin-install staleness — run the guard this kit ships, and expect DRIFT.**
   `python3 bin/plugin_staleness.py; echo "exit=$?"` (capture the code directly — never after a
   pipe). **Exit 3 is the EXPECTED and PASSING result here**, not a failure: this kit adds
   `bin/context_weight.py`, `bin/plugin_staleness.py`, `skills/context-weight/SKILL.md`,
   `docs/CONTEXT-WEIGHT.md` and edits `CLAUDE.md`, none of which exist in the installed 0.2.0
   snapshot. A report of `in sync` here would mean the guard is broken, since the drift is
   certain. Confirm the report NAMES the new files under `missing` and does NOT blame the
   version (repo and installed should both read `0.2.0` — content changed, the version string
   did not, which is precisely the trap that made the pre-run install 18 days stale).
   Then SURFACE the printed remedy in your final report so the human knows the new
   `context-weight` skill is not invocable until they bump `version` in
   `.claude-plugin/plugin.json` and refresh the install. Do not run the refresh yourself —
   `plugin_staleness.py` prints the commands; a human runs them.
