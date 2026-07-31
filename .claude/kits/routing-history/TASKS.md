# TASKS — routing-history

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially Repo facts, decisions D1–D10, the
OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `routing-history-implementer` (the parameter overrides the
agent's frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. **No warm-cluster candidates in this kit:** T1 → T2
and T3 → T4 are serial but cross model pins (opus→sonnet, sonnet→opus), and a model-pin change
always ends a cluster; T5 ‖ T6 are independent and fan out fresh. Dispatch
`routing-history-reviewer` at each phase end. This kit's PLAN.md declares `autonomy: advisory`
— re-route recommendations during this run are print-only.

Standing rules for every task:

- **The architect/execute shared kit contract is the #1 invariant.** Skill edits are BODY-only
  — never touch the YAML frontmatter of any `skills/*/SKILL.md` (the plugin is installed LIVE;
  skill files are runtime behavior). Every pinned contract element must survive in BOTH skills
  after every task — including the Tier-2 runtime-override clause, verbatim. If a brief's
  anchor text is not found verbatim, STOP and report the discrepancy — never fuzzy-match,
  never improvise.
- **No auto-pin-setting, anywhere.** The /architect change is ONE advisory bullet (consult the
  history, then decide). The `session:` line is an OPTIONAL, execute-owned NOTES.md line —
  no new required task field; `copilot_execute.parse_tasks` needs no change.
- **Dollars are optional, labeled, and never fabricated.** Kits without `session:` lines are
  quality-only; a missing transcript is a note and a skipped id, never an invented figure;
  the aggregate is labeled `partial`/`full`; zero-denominator rates render None/`n/a`, never
  0%; with zero `session:` lines anywhere, `--history` never calls `cr.load_pricing()`.
- **`bin/routing_scorecard.py` changes are ADDITIVE only** — existing flags, function
  signatures, output shapes, exit codes, the Tier-1 `--demo` numbers, and the Tier-2
  `--demo --live` numbers stay byte-stable, and `tests/test_routing_scorecard.py` +
  `tests/test_reroute_live.py` are never edited. Never edit `bin/cost_report.py`,
  `bin/session_cost.py`, `bin/copilot_execute.py`, any other existing `bin/`/`tests/` file,
  `data/` (either pricing file), `.claude-plugin/`, `copilot/`, `README.md`, the generated
  `skills/*/references/` mirrors, or the completed kits and their agents. Never re-implement
  `parse_tasks`/`parse_outcomes`/`parse_reroutes`/`tier_for`/`effective_alias`/the
  `session_cost` pipeline — call them. Sanctioned existing-file edits:
  `bin/routing_scorecard.py` (T1), `skills/execute/SKILL.md` (T3),
  `skills/architect/SKILL.md` (T4), `docs/FUSION-TIER2.md` (T5), `CLAUDE.md` (T6) — pinned
  changes only.
- Never hardcode a price, price ratio, or real model id. Sanctioned exceptions: tier
  vocabulary (`frontier`/`opus`/`sonnet`/`haiku`, `LIVE_TIER_ORDER`), the alias map
  `TASK_MODEL_TIERS = {"fable": "frontier"}`, `HISTORY_SCHEMA_VERSION = 1`, and synthetic
  fixture ids/values in tests and the demo. Demo transcript model ids are computed from
  `data/pricing.json` at run time via `_first_model_of_tier`.
- Never read the real `~/.claude` from a test or verify command — every test fixture lives in
  a temp dir handed over via `--kits-dir`/`--projects-dir` or an explicit path. `Path.home()`
  count in `tests/test_routing_history.py` and in the `bin/routing_scorecard.py` diff: ZERO.
  Never write outside this repo and temp dirs. No network. Do not commit or push.
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests [-p '<file>.py']`
  (the dotted-module form is broken on this machine). Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` path in any deliverable.

---

## Phase 1 — The history engine (additive scorecard extension)

### T1 — Extend bin/routing_scorecard.py with the cross-kit history (--history)
- status: done
- model: opus
- depends: (none)
- independent: no

**Brief.** Per PLAN.md D1/D2/D3/D5/D6/D7/D9/D10. Extend `bin/routing_scorecard.py` ADDITIVELY
a third time: new constants, new pure functions, a `--history` CLI mode, and a
`--demo --history` synthetic smoke. Zero changes to existing function signatures, outputs,
exit codes, or either prior demo's numbers. Extend the module docstring with a short
`--history` usage line and one sentence: the history mode aggregates every kit's TASKS.md +
NOTES.md ledger into a per-tier track record, folds in transcript dollars only for kits whose
NOTES.md carries optional `session:` lines (labeled partial otherwise), and — like `--live` —
is read-only and loads no pricing when there are no `session:` lines.

**New constants (pinned):**
- `HISTORY_SCHEMA_VERSION = 1` — same species as `SCHEMA_VERSION`/`LIVE_SCHEMA_VERSION`.
- `SESSION_RE = re.compile(r"^\s*(?:[-*]\s+)?session:\s+(\S+)\s*$")` — one whitespace-free
  token, nothing else on the line; optional `-`/`*` bullet like `OUTCOME_RE`/`REROUTE_RE`.
- `DEMO_HIST_*` fixture constants — see Demo below (exact organization is yours; the fixture
  CONTENT is pinned).

**New pure functions (pinned signatures & behavior):**
- `parse_sessions(text) -> (session_ids, notes)` — scan lines with `SESSION_RE`; ids returned
  in file order, deduped preserving first occurrence. A line starting `session:` (after an
  optional bullet) that does NOT match the full grammar (e.g. two tokens) is noted as an
  unrecognized session line (mirror `parse_outcomes`' phrasing), never guessed at. No
  id-format validation — the id's shape is harness-owned.
- `history_tier_stats(tasks, outcomes, applied_events) -> (stats, notes)` — `stats` maps
  EVERY tier in `LIVE_TIER_ORDER` to `{"pinned": int, "with_outcome": int, "first_try": int,
  "retry_pass": int, "escalated_pass": int, "blocked": int, "first_try_rate": float|None,
  "escalation_rate": float|None}`. `pinned` counts tasks by `tier_for(task.get("model"))` —
  the RAW pin, never shifted by re-routes (pins-vs-outcomes is the comparison; a task with no
  pin or an off-ladder pin is excluded from `pinned` and counted in ONE note per call, e.g.
  `2 tasks without a recognized tier pin`). Outcomes are joined to tasks by id; an outcome
  whose id is not a task id is skipped with a note. **Attribution (PLAN D2 = fusion-tier2
  D1, reused verbatim):** `pass`/`retry-pass`/`blocked` attribute to
  `tier_for(outcome["model"])`; `escalated-pass` attributes to
  `tier_for(effective_alias(task, applied_events))` (CALL `effective_alias` — never
  re-implement); an `escalated-pass` with no reconstructable dispatch alias, or any outcome
  whose tier is outside `LIVE_TIER_ORDER`, is skipped with a note. All four results count in
  `with_outcome`; `first_try_rate = first_try / with_outcome` and
  `escalation_rate = escalated_pass / with_outcome`, both None when `with_outcome` is 0.
  Reads only `id`/`model`/`status` off task dicts via `.get` (tests may pass minimal dicts).
- `tally_reroutes(events) -> dict` — counts EVENTS (one event = one logged decision):
  `{"events": len(events), "applied": n, "advisory": n, "by_tier": {tier: {"applied_from",
  "applied_to", "advisory_from", "advisory_to"}}}` with every `LIVE_TIER_ORDER` tier present
  (zeros when untouched). Only tiers on the ladder are tallied (parse_reroutes already
  guarantees `from`/`to` are ladder tiers).
- `scan_kits(kits_dir) -> (records, notes)` — iterate `sorted` subdirectories of `kits_dir`;
  a subdir with no TASKS.md → skipped + note (`<name>: no TASKS.md — skipped`); a TASKS.md
  raising ValueError in `ce.parse_tasks` → kit skipped + note; otherwise read NOTES.md ONCE
  (if present) and feed `parse_outcomes` + `parse_reroutes` + `parse_sessions`, carrying
  their notes prefixed `<kit>: `; missing NOTES.md → empty outcomes/events/sessions + note
  `<kit>: no outcome ledger — status-only`. Each record:
  `{"kit", "tasks", "outcomes", "events", "sessions", "notes"}` (record notes may live in
  the returned notes list instead — your call, but the card's top-level `notes` must carry
  them prefixed with the kit name).
- `kit_cost_summary(session_ids, projects_dir, no_subagents, vs, pricing) ->
  (cost_or_None, transcripts, notes)` — resolve each id via `sc.find_main_transcript`
  (missing → note naming the id, id skipped); dedupe transcripts preserving order; task dirs
  = union of `sc.discover_task_dirs(sid)` per found id unless `no_subagents`; files =
  `sc.gather_files(None, task_dirs, [str(t) for t in transcripts])`; ONE
  `sc.collect(files, pricing)` (the global message-id dedupe is the D5 double-count guard);
  `cf = sc.resolve_counterfactual_model(vs, pricing)` (ValueError propagates);
  `rep = sc.build_report(data, cf, pricing, pricing.get("billing_mode", "api"))`. Returns
  cost `{"actual_usd", "counterfactual_usd", "delta_usd", "ratio", "sessions_priced",
  "files_scanned"}` — or None (with notes) when no transcript was found; NEVER a zeroed
  figure standing in for missing data.
- `build_history(kits_dir, records, kit_costs, dollars, notes) -> card` — assemble the D7
  card: top-level keys EXACTLY `schema_version` (`HISTORY_SCHEMA_VERSION`), `generated_at`
  (same style as `build_scorecard`), `kits_dir` (string), `kits`, `tiers`, `reroutes`
  (`{events, applied, advisory}` totals), `dollars` (dict or None), `notes`. `tiers` merges
  the per-kit `history_tier_stats` sums with `tally_reroutes`' `by_tier` (under each tier's
  `"reroutes"` key), computing rates over the MERGED denominators (None on zero).
  `applied_events` fed to `history_tier_stats` for each kit =
  `[e for e in record["events"] if e["mode"] == "applied"]` (that kit's own events only).
  Each `kits` row: `{"kit", "tasks" (count), "with_outcome", "first_try_pass", "retry_pass",
  "escalated_pass", "blocked", "sessions" (the id list), "cost"}` (`kit_costs[kit]` or
  None). `dollars` is passed through as built by the CLI flow (below).
- `render_history_markdown(card) -> str` — H1
  `# Routing history — cross-kit per-tier track record`, then EXACTLY these five H2s in
  order: `## Verdict` (one bold line: `<K> kits`, overall first-try `<p>/<n>` or
  `first-try n/a (no outcome ledgers)`, and a dollars segment — the aggregate with its
  coverage label, or `dollars n/a (no session: lines)`); `## Per-tier track record` (a table,
  one row per ladder tier: Pinned / With outcome / First-try / Retry / Escalated / Blocked /
  First-try rate / Escalation rate — rates via `_rate_pct`, so None renders `n/a`);
  `## Re-route history` (the totals line plus one line per tier with any nonzero tally, or
  exactly `no re-route events recorded`); `## Kits` (a table, one row per kit: tasks,
  with-outcome, first-try, sessions count, actual `$` or `n/a`); `## Dollars` (the aggregate:
  actual, counterfactual vs the resolved model display, delta, ratio, coverage line
  `over <kits_with_sessions>/<kits_total> kits (<coverage>)`, `Prices cached <date>` — or
  the n/a sentence when `dollars` is None); then `Notes:` bullets when notes exist (mirror
  `render_markdown`).

**CLI wiring (pinned):** new argparse flag `--history` (store_true) with help text saying
cross-kit aggregation, read-only. Checks, inserted AFTER the existing
`--live`+`--session` rejection and BEFORE the `--demo` block: `--history` + `--live` →
`sys.exit("--history and --live are mutually exclusive")`; `--history` + `--session` →
`sys.exit("--history takes no --session — dollars come from NOTES.md session: lines")`;
`--history` + a kit positional → `sys.exit("--history takes no kit argument")`. In the
`--demo` block, `--demo --history` dispatches `run_history_demo(args.json)` (place the check
before the `--live` demo branch or alongside — either way `--demo --live --history` dies on
the mutual-exclusion check first). The non-demo history branch runs BEFORE the existing
`if not args.kit:` check: resolve `kits_dir` (missing dir → `sys.exit(f"kits dir not found:
{...}")`), `scan_kits`, then dollars: gather the ordered-unique union of all records'
session ids; if EMPTY → `dollars = None`, per-kit costs all None, append the note
`no session: lines found — dollars n/a (quality-only history)`, and NEVER call
`cr.load_pricing()`; otherwise load pricing once, call `kit_cost_summary` per kit (its own
ids) for the per-kit rows and ONCE with the unique union for the aggregate — a session id
recorded by more than one kit is priced once in the aggregate and flagged with a note; if
the union priced ZERO transcripts → `dollars = None` + note (pricing loaded, nothing
priced — still no invented number). When dollars exist:
`{"kits_with_sessions", "kits_total", "sessions_found" (unique ids), "sessions_priced",
"actual_usd", "counterfactual_usd", "delta_usd", "ratio", "counterfactual_model":
{"key", "display"}, "coverage" ("full" iff every kit has ≥1 session id AND every unique id
priced, else "partial"), "pricing_cached"}`. `--tasks-dir`/`--include` are IGNORED by
`--history` (single-session affordances; folding one dir into N sessions double-counts) —
when passed, append a note saying so. `--history` honors `--kits-dir`, `--projects-dir`,
`--no-subagents`, `--vs`, `--json`. Print markdown or `json.dumps(card, indent=2)`;
`return 0` — including every degraded shape (empty kits dir with zero records → empty card
+ note). Non-history paths behave byte-identically to today.

**Demo (pinned — PLAN D9):** `run_history_demo(as_json)` builds, in ONE
`tempfile.TemporaryDirectory`, a `kits` root with `hist-alpha`, `hist-beta`, `hist-gamma`,
and `not-a-kit`, plus a `projects/-demo` dir, then calls
`main(["--history", "--kits-dir", …, "--projects-dir", …, "--no-subagents"] + (["--json"]
if as_json else []))` (the `run_live_demo` pattern; `--no-subagents` keeps it hermetic).
Fixtures exactly as PLAN D9 pins them: hist-alpha (A1 haiku/A2 sonnet/A3 sonnet/A4 opus/A5
sonnet, all done; ledger A1 pass, A2 pass, A3 retry-pass, A4 pass, A5
`model=fable … result=escalated-pass`; `session: hist-alpha-session`) with the transcript
`projects/-demo/hist-alpha-session.jsonl` built like `run_demo`'s (one message per tier,
model ids via `_first_model_of_tier(pricing, tier)`, volumes from the existing
`DEMO_VOLUMES`); hist-beta (B1/B2 haiku done, B3 sonnet done, B4 sonnet blocked; ledger B1
pass, B2 retry-pass, B3 pass, B4 blocked; `reroute: haiku to=sonnet mode=advisory tasks=B2
rate=1/2`; NO session line); hist-gamma (C1 sonnet done, C2 opus done, C3 fable pending; NO
NOTES.md); `not-a-kit` (any file, no TASKS.md). Task headings use the spaced em dash
(`### A1 — <title>`) with `- status:` / `- model:` lines. Expected numbers (the verify
asserts): tiers haiku `(pinned, with_outcome, first_try, retry_pass, escalated_pass,
blocked) = (3, 3, 2, 1, 0, 0)`; sonnet `(6, 5, 2, 1, 1, 1)` (first_try_rate 0.4,
escalation_rate 0.2 — A5's escalated-pass lands on SONNET, its dispatch tier, never
frontier); opus `(2, 1, 1, 0, 0, 0)`; frontier `(1, 0, 0, 0, 0, 0)` with both rates None;
reroutes `{events 1, applied 0, advisory 1}`; kits rows alpha 5/5, beta 4/4, gamma 3/0;
dollars `kits_total 3, kits_with_sessions 1, sessions_found 1, sessions_priced 1,
coverage "partial"`, `actual_usd > 0` (values computed from pricing.json — structure
asserted, dollar values NOT pinned).

GOTCHAS: zero `Path.home()` (still — borrow the argparse defaults already present); no real
model ids (tier names + the `fable` alias + computed demo ids only); the zero-session-lines
path returns before any pricing load; `parse_tasks` needs the spaced em dash in demo
headings; rates None (never 0) on zero denominators; `gather_files`' first arg may be None;
`hist-gamma` has no NOTES.md at all (that IS the fixture); sort kit records by name.

**Acceptance.**
- `python3 bin/routing_scorecard.py --demo --json` still yields the Tier-1 pinned numbers
  (quality 6/6/3/1/1/1, mix {haiku 1, sonnet 4, fable 1}, survival 0.75) and
  `--demo --live --json` the Tier-2 pinned numbers (sonnet 3/1 below threshold, one
  sonnet→opus rec for L5+L6, budget 0/2/2, autonomy advisory) — additive proof.
- `python3 bin/routing_scorecard.py --demo --history [--json]` prints the pinned card;
  the JSON has exactly the D7 key set and the D9 numbers.
- The pinned pure functions exist and behave; `--history` rejects a kit positional,
  `--session`, and `--live`; a `session:` line with no transcript yields `dollars: null` +
  a note, never a figure; a bare `--history` against the repo's own kits dir with a temp
  `--projects-dir` exits 0.
- Greps: no `Path.home()`, no `sqlite`, no real model ids in the file; the two frozen test
  files, the reused scripts, and `data/` unchanged; full suite + sync check green.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/routing_scorecard.py --demo --history && python3 - <<'PY' && T1TMP=$(mktemp -d) && python3 bin/routing_scorecard.py --history --projects-dir "$T1TMP" > /dev/null && ! grep -n 'Path.home()' bin/routing_scorecard.py && ! grep -n 'sqlite' bin/routing_scorecard.py && ! grep -nE 'claude-(fable|opus|sonnet|haiku)' bin/routing_scorecard.py && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T1 OK'
import importlib.util, json, subprocess, sys, tempfile
from pathlib import Path
# --- Tier-1 additive regression: the old demo numbers are byte-stable ---
j = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--json"], capture_output=True, text=True)
assert j.returncode == 0, j.stderr
c = json.loads(j.stdout)
q = c["quality"]
assert (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"], q["escalated_pass"], q["blocked"]) == (6, 6, 3, 1, 1, 1), q
assert c["model_mix"] == {"haiku": 1, "sonnet": 4, "fable": 1}, c["model_mix"]
assert abs(c["review"]["survival_rate"] - 0.75) < 1e-9, c["review"]
# --- Tier-2 additive regression: the live demo numbers are byte-stable ---
l = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--live", "--json"], capture_output=True, text=True)
assert l.returncode == 0, l.stderr
d = json.loads(l.stdout)
assert d["autonomy"] == "advisory" and d["budget"] == {"cap": 2, "applied": 0, "remaining": 2}, d
recs = d["recommendations"]
assert len(recs) == 1 and (recs[0]["from"], recs[0]["to"], recs[0]["task_ids"]) == ("sonnet", "opus", ["L5", "L6"]), recs
# --- the history demo: pinned D9 numbers ---
h = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--history", "--json"], capture_output=True, text=True)
assert h.returncode == 0, h.stderr
card = json.loads(h.stdout)
assert set(card) == {"schema_version", "generated_at", "kits_dir", "kits", "tiers", "reroutes", "dollars", "notes"}, set(card)
assert card["schema_version"] == 1
t = card["tiers"]
K = ("pinned", "with_outcome", "first_try", "retry_pass", "escalated_pass", "blocked")
pick = lambda tier: tuple(t[tier][k] for k in K)
assert pick("haiku") == (3, 3, 2, 1, 0, 0), t["haiku"]
assert pick("sonnet") == (6, 5, 2, 1, 1, 1), t["sonnet"]
assert pick("opus") == (2, 1, 1, 0, 0, 0), t["opus"]
assert pick("frontier") == (1, 0, 0, 0, 0, 0), t["frontier"]
assert abs(t["haiku"]["first_try_rate"] - 2/3) < 1e-9 and abs(t["sonnet"]["first_try_rate"] - 0.4) < 1e-9
assert abs(t["sonnet"]["escalation_rate"] - 0.2) < 1e-9
assert t["frontier"]["first_try_rate"] is None and t["frontier"]["escalation_rate"] is None
assert card["reroutes"] == {"events": 1, "applied": 0, "advisory": 1}, card["reroutes"]
assert t["haiku"]["reroutes"]["advisory_from"] == 1 and t["sonnet"]["reroutes"]["advisory_to"] == 1
rows = {k["kit"]: k for k in card["kits"]}
assert list(rows) == ["hist-alpha", "hist-beta", "hist-gamma"], list(rows)
assert (rows["hist-alpha"]["tasks"], rows["hist-alpha"]["with_outcome"]) == (5, 5)
assert (rows["hist-beta"]["tasks"], rows["hist-beta"]["with_outcome"]) == (4, 4)
assert (rows["hist-gamma"]["tasks"], rows["hist-gamma"]["with_outcome"]) == (3, 0)
assert rows["hist-beta"]["cost"] is None and rows["hist-gamma"]["cost"] is None
assert rows["hist-alpha"]["cost"] and rows["hist-alpha"]["cost"]["actual_usd"] > 0
dol = card["dollars"]
assert dol and (dol["kits_total"], dol["kits_with_sessions"], dol["sessions_found"], dol["sessions_priced"]) == (3, 1, 1, 1), dol
assert dol["coverage"] == "partial" and dol["actual_usd"] > 0
assert any("no outcome ledger" in n for n in card["notes"]), card["notes"]
assert any("not-a-kit" in n for n in card["notes"]), card["notes"]
m = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--history"], capture_output=True, text=True)
assert m.returncode == 0, m.stderr
for needle in ("# Routing history — cross-kit per-tier track record", "## Verdict",
               "## Per-tier track record", "## Re-route history", "## Kits", "## Dollars",
               "partial", "n/a", "hist-alpha", "hist-gamma"):
    assert needle in m.stdout, f"markdown missing: {needle!r}\n{m.stdout}"
# --- pure surface ---
spec = importlib.util.spec_from_file_location("routing_scorecard", Path("bin/routing_scorecard.py").resolve())
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
assert rs.HISTORY_SCHEMA_VERSION == 1
for fn in ("parse_sessions", "history_tier_stats", "tally_reroutes", "scan_kits",
           "kit_cost_summary", "build_history", "render_history_markdown", "run_history_demo"):
    assert callable(getattr(rs, fn)), fn
ids, notes = rs.parse_sessions("session: abc\n- session: abc\nsession: def\nsession: two tokens\n")
assert ids == ["abc", "def"], ids
assert notes, "malformed session line must be noted"
# --- CLI guardrails ---
for argv, why in ((["fusion-tier1", "--history"], "kit positional"),
                  (["--history", "--session", "x"], "--session"),
                  (["--history", "--live"], "--live")):
    r = subprocess.run([sys.executable, "bin/routing_scorecard.py"] + argv, capture_output=True, text=True)
    assert r.returncode != 0, f"--history must reject {why}"
# --- never-fabricate: a session line with no transcript -> dollars None, id noted ---
with tempfile.TemporaryDirectory() as tmp:
    kd = Path(tmp) / "kits" / "solo"; kd.mkdir(parents=True)
    (kd / "TASKS.md").write_text("# T\n\n## Phase 1 — p\n\n### S1 — a\n- status: done\n- model: sonnet\n")
    (kd / "NOTES.md").write_text("outcome: S1 model=sonnet attempts=1 result=pass review=clean\nsession: ghost-session\n")
    pd = Path(tmp) / "projects"; pd.mkdir()
    r = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--history",
                        "--kits-dir", str(Path(tmp) / "kits"), "--projects-dir", str(pd),
                        "--no-subagents", "--json"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    g = json.loads(r.stdout)
    assert g["dollars"] is None, g["dollars"]
    assert g["kits"][0]["cost"] is None
    assert any("ghost-session" in n for n in g["notes"]), g["notes"]
print("T1 history checks ok")
PY
```

---

### T2 — Regression tests (tests/test_routing_history.py)
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Create `tests/test_routing_history.py`, stdlib `unittest`, loading
`bin/routing_scorecard.py` via the importlib `_load` convention off
`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` (copy the header pattern and
module-docstring safety contract from `tests/test_reroute_live.py`: no test reads the real
Claude project store or calls the stdlib home helper; every fixture lives in a fresh
`tempfile.TemporaryDirectory()` handed over via `--kits-dir`/`--projects-dir` or explicit
paths — never a bare run against real dirs; synthetic ids/values only, tier vocabulary + the
`fable` alias as the only model tokens EXCEPT ids computed at run time from
`rs.cr.load_pricing()` + `rs._first_model_of_tier` for the dollar fixtures — never a spelled
model id). Do NOT edit `tests/test_routing_scorecard.py` or `tests/test_reroute_live.py` —
this is a new file.

Helpers: a `write_kit(kits_root, name, tasks_md, notes_md=None)` fixture writer (spaced
em-dash headings, `- status:`/`- model:` lines, pinned `outcome:`/`reroute:`/`session:`
grammars) and a `write_transcript(projects_root, session_id, messages)` writer emitting
`{"timestamp", "message": {"model", "id", "usage": {"input_tokens", "output_tokens"}}}`
JSONL lines (mirror `run_demo`'s transcript shape; slug subdir name synthetic, e.g. `-t`).

Minimum cases — include these EXACT method names (greps in the verify key on them), plus
whatever else you need:

1. `test_parse_sessions_happy_and_tolerant` — happy path; leading `- `/`* ` bullets; dedupe
   preserving first-seen order; a `session:` line with extra tokens → skipped + note; no
   format validation of the id itself.
2. `test_history_tier_stats_attribution_matrix` — `pass`/`retry-pass`/`blocked` attribute to
   the outcome `model=`'s tier; `escalated-pass` on a sonnet-pinned task with `model=fable`
   attributes to SONNET (never frontier); a `fable`-pinned task's `pass` lands in frontier's
   `with_outcome`; an `escalated-pass` on a haiku-pinned task covered by a `mode=applied`
   haiku→sonnet event attributes to SONNET (effective-pin reconstruction via
   `effective_alias`); unknown outcome ids skipped + note; all four tiers always present.
3. `test_history_tier_stats_pinned_and_unpinned` — `pinned` counts follow the RAW pin (an
   applied re-route never shifts the `pinned` column); tasks with no `model` or a garbage
   pin are excluded from every tier and produce one note.
4. `test_tally_reroutes_modes_and_tiers` — advisory vs applied totals; per-tier
   `applied_from`/`applied_to`/`advisory_from`/`advisory_to`; every ladder tier present with
   zeros; events counted, not task ids.
5. `test_scan_kits_tolerant_and_sorted` — records sorted by kit name; a no-TASKS.md subdir
   skipped + note; a malformed-status TASKS.md (ValueError) skips the kit + note; NOTES.md
   parsed once feeding outcomes + events + sessions; notes prefixed with the kit name.
6. `test_ledger_free_kit_status_only` — a kit with TASKS.md only contributes `pinned` counts
   and zero outcome counters, with the status-only note; nothing invented.
7. `test_zero_denominator_rates_null` — a tier with `with_outcome == 0` has both rates None
   in JSON and renders `n/a` in markdown, never `0%`.
8. `test_history_pricing_free_without_sessions` — stub `rs.cr.load_pricing` with a function
   that raises, call `rs.main(["--history", "--kits-dir", <tmp with session-line-free
   kits>, "--projects-dir", <tmp>, "--json"])` capturing stdout — it must succeed with
   `dollars: null` and the quality-only note, proving the zero-lines path never loads
   pricing (restore the stub in `finally`).
9. `test_dollars_partial_and_labeled` — two kits, one with a `session:` line backed by a
   synthetic transcript in a temp projects dir, one without: per-kit cost present/None
   respectively, aggregate `coverage == "partial"`, `kits_with_sessions == 1`,
   `actual_usd > 0`, and the no-session kit's markdown row shows `n/a`.
10. `test_multi_session_kit_single_collect` — a kit with TWO `session:` lines whose
    transcripts share one duplicated message id (the resume case): the kit's
    `sessions_priced == 2` and its `actual_usd` counts the duplicated message ONCE (equal,
    within 1e-9, to the same-files single-collect price computed via the reused pipeline).
11. `test_missing_transcript_never_fabricates` — session ids without transcripts → per-kit
    cost None, aggregate `dollars` None when NOTHING priced, notes name the missing ids; no
    `$0.00`-style stand-in anywhere in the JSON.
12. `test_shared_session_priced_once_in_aggregate` — two kits both carrying the SAME
    `session:` id: the aggregate `actual_usd` equals ONE session's cost (not 2×), a note
    flags the shared id, and each per-kit row still carries its own full figure.
13. `test_cli_history_json_keys` — a temp multi-kit fixture through the CLI: top-level keys
    exactly `{schema_version, generated_at, kits_dir, kits, tiers, reroutes, dollars,
    notes}`; every ladder tier present under `tiers` with the pinned per-tier key set
    (including `reroutes`); markdown mode contains the H1 and the five pinned H2s in order.
14. `test_cli_history_rejects_kit_live_session` — `--history <kit>`, `--history --live`,
    and `--history --session x` each exit nonzero with a message naming the offender.
15. `test_cli_history_empty_kits_dir` — an existing kits dir with no kit subdirs → exit 0,
    empty `kits`, a note; a NONEXISTENT kits dir → nonzero exit naming the path.
16. `test_demo_history_pinned_numbers` — `--demo --history --json` via subprocess: the T1
    pinned D9 expectations (tier tuples, reroute tallies, kit rows, dollars structure with
    `coverage == "partial"`); `--demo --history` markdown contains the pinned H1/H2 lines.
17. `test_prior_demos_regression` — `--demo --json` still yields the Tier-1 pinned
    quality/mix/survival numbers AND `--demo --live --json` still yields the Tier-2 pinned
    signal/recommendation/budget numbers (additive proof for both prior modes).
18. `test_readonly_history_run` — byte-snapshot the temp kits dir AND the temp projects dir
    before/after a full `--history` CLI run — identical (`--history` never writes; the
    `session:` line is orchestrator-owned).

**Acceptance.** All new tests pass; full suite green; the two frozen test files and the
reused scripts untouched; safety greps clean; only this file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_routing_history.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && echo 'T2 OK'
import re
text = open('tests/test_routing_history.py').read()
assert 'Path.home()' not in text
assert '~/.claude' not in text, "real home path in tests"
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
for name in ('test_parse_sessions_happy_and_tolerant', 'test_history_tier_stats_attribution_matrix',
             'test_history_tier_stats_pinned_and_unpinned', 'test_tally_reroutes_modes_and_tiers',
             'test_scan_kits_tolerant_and_sorted', 'test_ledger_free_kit_status_only',
             'test_zero_denominator_rates_null', 'test_history_pricing_free_without_sessions',
             'test_dollars_partial_and_labeled', 'test_multi_session_kit_single_collect',
             'test_missing_transcript_never_fabricates', 'test_shared_session_priced_once_in_aggregate',
             'test_cli_history_json_keys', 'test_cli_history_rejects_kit_live_session',
             'test_cli_history_empty_kits_dir', 'test_demo_history_pinned_numbers',
             'test_prior_demos_regression', 'test_readonly_history_run'):
    assert f'def {name}' in text, f"missing case: {name}"
assert '--kits-dir' in text and '--projects-dir' in text and 'load_pricing' in text
print('safety greps ok')
PY
```

---

*Phase 1 end — dispatch `routing-history-reviewer` before starting Phase 2.*

---

## Phase 2 — The skills (the contract-sensitive phase)

### T3 — Teach /execute to record the optional session: line (End of run)
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Per PLAN.md D3/D4. ONE pinned replacement in `skills/execute/SKILL.md`, BODY only
(frontmatter untouched — the plugin is live). If the anchor below is not found verbatim, STOP
and report.

*The edit* — in "## End of run", replace the exact final sentence:

```
Then offer the routing-quality scorecard: `python3 bin/routing_scorecard.py <slug>` (first-try pass rate, model mix, cheap-model review survival, and — with `--session` — dollars vs an all-frontier counterfactual).
```

with:

```
Then record this run's session id for the cross-kit routing history: append ONE `session: <session-id>` line to NOTES.md, where `<session-id>` is the filename stem of this session's transcript — the most recently modified `*.jsonl` under the Claude projects dir for this project (project slug = the project's absolute path with every non-alphanumeric character replaced by `-`), e.g. `ls -t "$HOME/.claude/projects/$(pwd | sed 's|[^A-Za-z0-9]|-|g')"/*.jsonl | head -1`. The lookup is read-only and best-effort, and the line is OPTIONAL: if the lookup finds nothing, or a concurrent session in this project makes the answer ambiguous, skip it — the history degrades to quality-only for this kit; never record a guessed id. A resumed kit appends one `session:` line per run (the history sums a kit's sessions and dedupes ids shared across kits). Finally, offer the routing-quality scorecard: `python3 bin/routing_scorecard.py <slug>` (first-try pass rate, model mix, cheap-model review survival, and — with `--session` — dollars vs an all-frontier counterfactual) and the cross-kit track record: `python3 bin/routing_scorecard.py --history` (per-tier quality across every kit, plus aggregate dollars over the kits that carry a `session:` line).
```

Change nothing else — in particular do not touch the frontmatter, Setup, the lean-driver,
loop, dispatch-modes, outcome-ledger, or live-re-routing sections, or the escalation valve.
The `session:` grammar in the new text (`session: <session-id>`, one token) must match
`SESSION_RE` in `bin/routing_scorecard.py` — it does by construction; verify confirms.

**Acceptance.** The replacement landed exactly once; section order unchanged (Setup →
Operating rule → The loop → Dispatch modes → Outcome ledger → Live re-routing → Escalation
valve → End of run); every pre-existing contract element intact (verify's grep list); the
session line described as OPTIONAL, read-only, best-effort, end-of-run, never guessed;
frontmatter untouched; suite + sync green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T3 OK'
t = open('skills/execute/SKILL.md').read()
assert t.startswith('---\nname: execute\n'), "frontmatter touched"
# --- Tier-1 + Tier-2 contract elements: all must survive ---
for s in [
    "## Setup", "## Operating rule — lean driver", "## The loop",
    "## Dispatch modes — fresh fan-out vs warm sidekick",
    "## Outcome ledger — one line per finished task",
    "## Live re-routing — upgrade-only, autonomy-gated",
    "`in-progress` in TASKS.md", "mark `done`", "mark `blocked`",
    "skip `done`, stop at `blocked` deps",
    "passing the task's `model` value as the Agent tool's `model` parameter",
    "overrides the agent's frontmatter default", "Phase boundaries", "reviewer agent",
    "independent — one message, multiple Agent calls", "## Escalation valve",
    "`model: fable`", "## End of run",
    "outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>",
    "reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>",
    "SAME `model` value", "always a fresh spawn", "the LAST line per task id",
    "`result=escalated-pass`", "runtime dispatch override, never a TASKS.md rewrite",
    "NEVER to frontier/Fable", "**advisory (the default)**",
    "Read the autonomy dial once here",
]:
    assert s in t, f"contract element lost: {s!r}"
# --- routing-history elements: present exactly once where counted ---
assert t.count("session: <session-id>") == 1, "session grammar missing/duplicated"
for s in [
    "cross-kit routing history",
    "the most recently modified `*.jsonl`",
    "every non-alphanumeric character replaced by `-`",
    "read-only and best-effort", "OPTIONAL", "never record a guessed id",
    "one `session:` line per run",
    "python3 bin/routing_scorecard.py --history",
]:
    assert s in t, f"routing-history element missing: {s!r}"
assert t.count("python3 bin/routing_scorecard.py --history") == 1
assert "Then offer the routing-quality scorecard:" not in t, "old sentence should be replaced"
assert "(first-try pass rate, model mix, cheap-model review survival, and — with `--session` — dollars vs an all-frontier counterfactual)" in t
order = ["## Setup", "## Operating rule — lean driver", "## The loop",
         "## Dispatch modes — fresh fan-out vs warm sidekick",
         "## Outcome ledger — one line per finished task",
         "## Live re-routing — upgrade-only, autonomy-gated",
         "## Escalation valve", "## End of run"]
idx = [t.index(h) for h in order]
assert idx == sorted(idx), "section order wrong"
print("T3 structural checks ok")
PY
```

---

### T4 — Add the advisory history bullet to skills/architect/SKILL.md and re-check the shared contract in BOTH skills
- status: done
- model: opus
- depends: T3
- independent: no

**Brief.** Per PLAN.md D8 and the CLAUDE.md invariant ("if you touch either skill you MUST
re-check both"). ONE pinned insertion in `skills/architect/SKILL.md` (BODY only), then the
dual-file contract audit.

*The edit* — in the "### `TASKS.md` (same kit directory)" section of Step 2, insert a new
bullet immediately AFTER the exact bullet line:

```
- The task's `model` field is authoritative at dispatch time: execute passes it as the Agent tool's `model` parameter, which overrides the implementer agent's frontmatter default. When a kit runs with the autonomy dial on `auto`, execute may layer a logged, upgrade-only runtime override on top at dispatch (one tier step, never to frontier) — the field itself is never rewritten and stays the dispatch default.
```

New bullet (verbatim):

```
- **Consult the routing history when choosing the initial `model` pins:** run `python3 bin/routing_scorecard.py --history` — the cross-kit per-tier track record aggregated from every prior kit's outcome ledger and re-route events (first-try rate, escalation rate, upgrade frequency, plus dollars where kits recorded a `session:` line). It is EVIDENCE, not an auto-pin-setter: the architect weighs it and decides — a tier that keeps needing upgrades on similar work argues for pinning one tier up front; a tier passing cleanly argues the cheap pin is safe.
```

Change nothing else in the file.

*The audit* — after editing, re-check BOTH `skills/architect/SKILL.md` and
`skills/execute/SKILL.md` against the full shared contract (the verify below encodes it): kit
layout (`PLAN.md`, `TASKS.md`, `NOTES.md` owned by execute); task fields `id`, `title`,
`status`, `model`, brief, acceptance, verify; status vocabulary exactly
`pending | in-progress | done | blocked`; `## Phase N — <name>` headings;
`depends:`/`independent:`; the model-override-at-dispatch rule stated in both files INCLUDING
the Tier-2 runtime-override clause verbatim; the Tier-2 autonomy bullet and warm-cluster hint
intact in architect; the `reroute:` and `outcome:` grammars intact in execute; the new
`session:` recording described as OPTIONAL and execute-owned in execute; the new architect
bullet advisory-only (no text anywhere permitting automatic pin adjustment from history). If
ANY element is missing or contradicted, STOP and report — that is a T1/T3 defect to fix via
the orchestrator, not something to patch ad hoc here.

**Acceptance.** The architect bullet landed exactly once, immediately after the
model-authoritative bullet; the dual-file grep audit passes; architect frontmatter untouched;
no other file changed by this task; suite + sync green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && echo 'T4 OK'
a = open('skills/architect/SKILL.md').read()
e = open('skills/execute/SKILL.md').read()
assert a.startswith('---\nname: architect\n'), "architect frontmatter touched"
assert e.startswith('---\nname: execute\n'), "execute frontmatter touched"
# --- architect contract elements (Tier-1 + Tier-2 lists, all must survive) ---
for s in [
    "`id`, `title`, `status` (pending/in-progress/done/blocked), `model`",
    "Self-contained brief", "Acceptance criteria", "Verify command",
    "`## Phase N — <name>` headings",
    "`depends: <ids>` or `independent: yes`",
    "overrides the implementer agent's frontmatter default",
    "NOTES.md", "-implementer.md", "-verifier.md", "-reviewer.md",
    "## Step 1", "## Step 2", "## Step 3",
    "one tier step, never to frontier",
    "never rewritten and stays the dispatch default",
    "not a task field — the task-field contract is unchanged",
]:
    assert s in a, f"architect element lost: {s!r}"
assert a.count("warm-cluster candidates") == 1, "tier-1 warm-cluster bullet lost/duplicated"
assert a.count("`outcome:` line per finished task") == 1, "tier-1 ledger mention lost/duplicated"
assert a.count("**Autonomy posture (optional)**") == 1, "tier-2 autonomy bullet lost/duplicated"
assert a.count("upgrade-only runtime override") == 1, "tier-2 model-bullet clause lost/duplicated"
# --- the new advisory bullet: exactly once, right after the model-authoritative bullet ---
assert a.count("**Consult the routing history when choosing the initial `model` pins:**") == 1, "history bullet missing/duplicated"
assert a.count("python3 bin/routing_scorecard.py --history") == 1
assert "not an auto-pin-setter" in a and "the architect weighs it and decides" in a
i_model = a.index("never rewritten and stays the dispatch default")
i_hist = a.index("**Consult the routing history when choosing the initial `model` pins:**")
between = a[i_model:i_hist]
assert 0 < between.count("\n") <= 2 and i_hist > i_model, "history bullet not directly after the model bullet"
# --- execute contract elements (full final state, incl. T3's additions) ---
for s in [
    "## Setup", "## Operating rule — lean driver", "## The loop",
    "## Dispatch modes — fresh fan-out vs warm sidekick",
    "## Outcome ledger — one line per finished task",
    "## Live re-routing — upgrade-only, autonomy-gated",
    "`in-progress` in TASKS.md", "mark `done`", "mark `blocked`",
    "skip `done`, stop at `blocked` deps",
    "passing the task's `model` value as the Agent tool's `model` parameter",
    "overrides the agent's frontmatter default", "Phase boundaries", "reviewer agent",
    "independent — one message, multiple Agent calls", "## Escalation valve",
    "`model: fable`", "## End of run",
    "outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>",
    "reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>",
    "SAME `model` value", "always a fresh spawn",
    "runtime dispatch override, never a TASKS.md rewrite",
    "NEVER to frontier/Fable", "**advisory (the default)**",
    "session: <session-id>", "never record a guessed id",
    "python3 bin/routing_scorecard.py --history",
]:
    assert s in e, f"execute element lost: {s!r}"
# --- no auto-pin-setting language anywhere ---
for f, txt in (("architect", a), ("execute", e)):
    assert "auto-pin" not in txt.replace("not an auto-pin-setter", ""), f"auto-pin language in {f}"
# --- session grammar consistency with the parser ---
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("routing_scorecard", Path("bin/routing_scorecard.py").resolve())
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
ids, _ = rs.parse_sessions("session: sample-id-1\n")
assert ids == ["sample-id-1"], "SESSION_RE does not accept the skill's documented grammar"
print("dual-file contract audit ok")
PY
```

---

*Phase 2 end — dispatch `routing-history-reviewer` before starting Phase 3.*

---

## Phase 3 — Documentation and guardrails

### T5 — Write docs/ROUTING-HISTORY.md and point Tier 2's Still-deferred section at it
- status: done
- model: sonnet
- depends: T4
- independent: yes

**Brief.** Two pieces.

*Piece 1* — new file `docs/ROUTING-HISTORY.md` documenting what this kit built and what it
deliberately did not. Match the tone/format of `docs/FUSION-TIER2.md` (H1 + H2 sections,
concrete commands, no prices, no real model ids — tier names and the `fable` alias are fine,
no `/private/tmp/` paths, name constants instead of restating their values as prose facts).
Required structure — H1 `# Routing history — the cross-kit per-tier track record`, then
EXACTLY these five H2s in order:

1. `## What it aggregates` — `--history` scans every kit under the kits dir, parses TASKS.md
   (reused `parse_tasks`) + the NOTES.md ledger (`outcome:` + `reroute:` lines, reused
   parsers), and aggregates per pricing tier: pinned tasks, outcomes (first-try / retry /
   escalated / blocked), first-try + escalation rates, and per-tier re-route from/to tallies.
   Attribution follows Tier 2: `escalated-pass` counts against the reconstructed DISPATCH
   tier, never frontier. Usage: `python3 bin/routing_scorecard.py --history` (+ `--json`),
   and `python3 bin/routing_scorecard.py --demo --history` as the synthetic smoke. Read-only,
   like `--live` — the script never writes a kit file.
2. `## Dollars — the optional session: line` — per-kit dollars need a kit→session mapping;
   the channel is an OPTIONAL, execute-owned NOTES.md line, grammar verbatim:
   `session: <session-id>` — appended by the /execute orchestrator at end of run via a
   read-only transcript-stem lookup (most recently modified transcript for the project;
   skipped when ambiguous — never guessed). Kits carrying it get transcript dollars vs the
   all-frontier counterfactual (computed from pricing.json at run time); a kit may carry
   several lines (one per run — summed with message-level dedupe); ids shared across kits
   are priced once in the aggregate; the aggregate is LABELED with its coverage
   (`partial`/`full`, `over <n>/<m> kits`). With zero `session:` lines the history is
   quality-only and never loads pricing.
3. `## Feeding the architect` — /architect Step 2 now carries one ADVISORY bullet: consult
   `--history` when choosing initial `model` pins. It is evidence, not an auto-pin-setter —
   the architect (human or Fable) weighs the track record and decides; no automation ever
   rewrites a pin from history data.
4. `## Contract safety` — why the shared architect/execute contract survives byte-intact: the
   `session:` line is a third execute-owned NOTES.md line format (precedent: `outcome:`,
   `reroute:` — neither `OUTCOME_RE` nor `REROUTE_RE` matches it); no new required task
   field; `parse_tasks` needed no change; the architect addition is one advisory bullet; the
   model-override-at-dispatch rule and the Tier-2 runtime-override clause are untouched.
5. `## Deliberately not built` — auto-pin adjustment (advisory by design); cross-repo or
   time-series trend aggregation; per-task dollar attribution (transcripts price sessions,
   not tasks — a per-task split would be an estimate presented as a measurement); main-session
   model switching (still the upstream ask, tracked in `docs/FUSION-TIER1.md`).

*Piece 2* — in `docs/FUSION-TIER2.md`, append a new paragraph at the very end of the file
(the `## Still deferred` section currently ends with the line
`still tracked in `docs/FUSION-TIER1.md`.`). Append (blank line before it):

```
The scorecard-over-time aggregation has since shipped — see
[ROUTING-HISTORY.md](ROUTING-HISTORY.md) for the cross-kit `--history` view: the per-tier
track record, the optional NOTES.md `session:` line that attaches per-kit dollars, and the
advisory bullet that feeds the architect's initial pins.
```

Change nothing else in FUSION-TIER2.md — its five H2s and all prior text stay intact.

**Acceptance.** ROUTING-HISTORY.md exists with the H1 + exactly those five H2s in order; the
`session: <session-id>` grammar verbatim; mentions `--history`, `--demo --history`,
coverage labeling, quality-only degradation, and the not-an-auto-pin-setter rule;
FUSION-TIER2.md gained exactly the pointer paragraph and its H2 set is unchanged; greps
clean; suite green; only ROUTING-HISTORY.md new.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T5 OK'
import re
t = open('docs/ROUTING-HISTORY.md').read()
assert t.lstrip().startswith('# Routing history — the cross-kit per-tier track record')
h2s = [l for l in t.splitlines() if l.startswith('## ')]
assert h2s == ['## What it aggregates', '## Dollars — the optional session: line',
               '## Feeding the architect', '## Contract safety',
               '## Deliberately not built'], h2s
assert 'session: <session-id>' in t
for s in ('--history', '--demo --history', 'partial', 'quality-only', 'auto-pin-setter',
          'routing_scorecard.py', 'escalat', 'first-try', 'never', 'coverage'):
    assert s in t, f'missing: {s}'
assert not re.search(r'claude-(fable|opus|sonnet|haiku)-?[0-9]', t), 'real model id in doc'
assert '/private/tmp' not in t
o = open('docs/FUSION-TIER2.md').read()
assert o.count('The scorecard-over-time aggregation has since shipped') == 1, 'pointer missing/duplicated'
assert 'ROUTING-HISTORY.md' in o
h2s2 = [l for l in o.splitlines() if l.startswith('## ')]
assert h2s2 == ['## The live signal', '## Upgrade-only re-routing', '## The autonomy dial',
                '## Contract safety', '## Still deferred'], h2s2
print('doc structure ok')
PY
```

---

### T6 — Pinned CLAUDE.md run-line
- status: done
- model: haiku
- depends: T1
- independent: yes

**Brief.** ONE pinned insertion, nothing else. (The `For \`routing-history\` specifically:`
fence paragraph already exists in CLAUDE.md — the architect added it; do not touch it.) If
the anchor is not found verbatim, STOP and report.

*Insertion — CLAUDE.md, "## How to run things" code block.* Immediately AFTER the line:

```
python3 bin/routing_scorecard.py --demo --live    # live re-route signal smoke (synthetic mid-run kit, upgrade-only, never frontier)
```

insert this line into the same code block:

```
python3 bin/routing_scorecard.py --demo --history # cross-kit routing-history smoke (synthetic kits, dollars labeled partial)
```

**Acceptance.** The insertion is present exactly once, directly after the `--demo --live`
line; the routing-history fence paragraph is present exactly once (pre-existing); no other
CLAUDE.md line changed by this task; suite green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T6 OK'
c = open('CLAUDE.md').read()
line = 'python3 bin/routing_scorecard.py --demo --history # cross-kit routing-history smoke (synthetic kits, dollars labeled partial)'
assert c.count(line) == 1, "run-line missing/duplicated"
i_live = c.index('python3 bin/routing_scorecard.py --demo --live')
i_hist = c.index(line)
assert i_hist > i_live and c[i_live:i_hist].count('\n') == 1, "history line not directly after the --demo --live line"
assert c.count('For `routing-history` specifically:') == 1, "fence paragraph missing/duplicated"
print('insertion ok')
PY
```

---

*Phase 3 end — dispatch `routing-history-reviewer`, then run PLAN.md's overall done-check.*
