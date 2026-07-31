# TASKS — fusion-tier2

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially Repo facts, decisions D1–D10, the
OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `fusion-tier2-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. **No warm-cluster candidates in this kit:** T1 → T2
and T3 → T4 are serial but cross model pins (opus→sonnet, sonnet→opus), and a model-pin change
always ends a cluster; T5 ‖ T6 are independent and fan out fresh. Dispatch
`fusion-tier2-reviewer` at each phase end. This kit's PLAN.md declares `autonomy: advisory` —
re-route recommendations during this run are print-only.

Standing rules for every task:

- **The architect/execute shared kit contract is the #1 invariant.** Skill edits are BODY-only
  — never touch the YAML frontmatter of any `skills/*/SKILL.md` (the plugin is installed LIVE;
  skill files are runtime behavior). Every pinned contract element must survive in BOTH skills
  after every task. If a brief's anchor text is not found verbatim, STOP and report the
  discrepancy — never fuzzy-match, never improvise.
- **Re-routing semantics are non-negotiable:** UPGRADE-ONLY, exactly one tier step
  (haiku→sonnet, sonnet→opus), NEVER to frontier/Fable (the escalation valve stays the only
  Fable path, mechanism unchanged), NEVER a TASKS.md `model`-field rewrite (runtime dispatch
  override, logged as `reroute:` lines in NOTES.md by the ORCHESTRATOR — `--live` never
  writes), and the autonomy dial defaults to ADVISORY (print-only; nothing auto-changes when
  off).
- **`bin/routing_scorecard.py` changes are ADDITIVE only** — existing flags, function
  signatures, output shapes, exit codes, and the Tier-1 `--demo` numbers stay byte-stable, and
  `tests/test_routing_scorecard.py` is never edited. Never edit `bin/cost_report.py`,
  `bin/session_cost.py`, `bin/copilot_execute.py`, any other existing `bin/`/`tests/` file,
  `data/` (either pricing file), `.claude-plugin/`, `copilot/`, `README.md`, the generated
  `skills/*/references/` mirrors, or the completed kits and their agents. Sanctioned
  existing-file edits: `bin/routing_scorecard.py` (T1), `skills/execute/SKILL.md` (T3),
  `skills/architect/SKILL.md` (T4), `docs/FUSION-TIER1.md` (T5), `CLAUDE.md` (T6) — pinned
  changes only.
- Never hardcode a price, price ratio, or real model id. Sanctioned exceptions: tier vocabulary
  (`frontier`/`opus`/`sonnet`/`haiku`, `LIVE_TIER_ORDER`), the alias map
  `TASK_MODEL_TIERS = {"fable": "frontier"}`, the pinned live-policy constants
  (threshold 0.5, min-sample 3, auto-upgrade cap 2, schema version 1), and synthetic fixture
  ids/values in tests and the demos. The `--live` path never loads `data/pricing.json`.
- Never read the real `~/.claude` from a test or verify command — every test kit lives in a
  temp dir handed over via `--kits-dir` or an explicit kit path. `Path.home()` count in
  `tests/test_reroute_live.py` and in the `bin/routing_scorecard.py` diff: ZERO. Never write
  outside this repo and temp dirs. No network. Do not commit or push.
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests [-p '<file>.py']`
  (the dotted-module form is broken on this machine). Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` path in any deliverable.

---

## Phase 1 — The live decision logic (additive scorecard extension)

### T1 — Extend bin/routing_scorecard.py with the live re-route signal (--live)
- status: done
- model: opus
- depends: (none)
- independent: no

**Brief.** Per PLAN.md D1/D2/D4/D5/D6/D8/D9/D10. Extend `bin/routing_scorecard.py` ADDITIVELY:
new constants, new pure functions, a `--live` CLI mode, and a `--demo --live` synthetic smoke.
Zero changes to existing function signatures, outputs, exit codes, or the Tier-1 demo numbers.
Extend the module docstring with a short `--live` usage line and one sentence: the live mode is
quality-only (no pricing load), read-only (the orchestrator writes `reroute:` lines, never this
script), and its recommendations are upgrade-only and never target frontier.

**New constants (pinned):**
- `LIVE_SCHEMA_VERSION = 1`
- `LIVE_TIER_ORDER = ("haiku", "sonnet", "opus", "frontier")` — comment: cheap→expensive ladder;
  an upgrade moves exactly one rung right and never lands on `frontier`.
- `LIVE_RATE_THRESHOLD = 0.5` — a tier is struggling when its live first-try rate is strictly
  below this.
- `LIVE_MIN_SAMPLE = 3` — completed tasks of a tier before its rate is judged.
- `LIVE_MAX_AUTO_UPGRADES = 2` — budget guardrail: max `mode=applied` re-route events per run.
- `REROUTE_MODES = ("advisory", "applied")`
- `REROUTE_RE = re.compile(r"^\s*(?:[-*]\s+)?reroute:\s+(\S+)\s+(.+)$")` (reuses `PAIR_RE` for
  the pairs; `tasks=` values are split on commas).
- `AUTONOMY_RE = re.compile(r"^\s*autonomy:\s*(advisory|auto)\s*$", re.MULTILINE)`
- `DEMO_LIVE_TASKS_MD`, `DEMO_LIVE_NOTES_MD` — see Demo below.

**New pure functions (pinned signatures & behavior):**
- `parse_reroutes(text) -> (events, notes)` — scan lines with `REROUTE_RE`: first token is the
  from-tier, then `PAIR_RE` pairs. An event needs from-tier and `to=` both in `LIVE_TIER_ORDER`
  and `mode=` in `REROUTE_MODES`, else the line is skipped with a note (mirror
  `parse_outcomes`' `unrecognized …` phrasing). `tasks=` is comma-split into a list (missing →
  `[]`); `rate=` kept as the raw string (informational, no math; missing → None); unknown keys
  ignored. Events returned in file order (chronology matters for `effective_alias`). A parsed
  `to=frontier` event is kept (honest state reconstruction) but appends the note
  `reroute line targets frontier — out of policy`.
- `parse_autonomy(text) -> (posture, notes)` — `text` is PLAN.md's content or None. None →
  `("advisory", ["no PLAN.md — autonomy defaults to advisory"])`. First `AUTONOMY_RE` match
  wins. If no match but `re.search(r"^\s*autonomy:\s*(\S+)", text, re.MULTILINE)` hits, note
  the unrecognized value and return `"advisory"`. No `autonomy:` line at all → `("advisory",
  [])`.
- `effective_alias(task, applied_events) -> alias_or_None` — the task's `model` pin, overridden
  by the LAST event in `applied_events` whose `tasks` list contains the task's id (use that
  event's `to`; legal upgrade targets are non-frontier tiers, which are their own Agent-tool
  aliases — no translation). No pin and no covering event → None.
- `live_tier_stats(tasks, outcomes, applied_events) -> (stats, notes)` — `stats` maps EVERY
  tier in `LIVE_TIER_ORDER` to `{"completed": int, "first_try": int, "rate": float|None}`
  (zeros and rate None when empty). Join outcomes to tasks by id; an outcome whose id is not a
  task id is skipped with a note. **Attribution (PLAN D1):** results `pass` / `retry-pass` /
  `blocked` attribute to `tier_for(outcome["model"])`; `escalated-pass` attributes to
  `tier_for(effective_alias(task, applied_events))` — the ledger's `model=` on an escalated
  line names the Fable fixer, so the failure evidence goes to the reconstructed dispatch tier
  instead. `escalated-pass` with `effective_alias` None → skipped with a note. All four results
  count in `completed`; only `pass` counts in `first_try`; `rate = first_try / completed`
  (None when completed is 0). A tier outside `LIVE_TIER_ORDER` (garbage alias) → skip + note.
- `upgrade_decision(tasks, outcomes, events, *, threshold=LIVE_RATE_THRESHOLD,
  min_sample=LIVE_MIN_SAMPLE, max_auto=LIVE_MAX_AUTO_UPGRADES) -> dict` — reads only `id`,
  `status`, `model` from each task dict (via `.get`, so tests may pass minimal dicts). Filters
  `applied = [e for e in events if e["mode"] == "applied"]`, computes `live_tier_stats`, and
  returns:
  `{"signals": {tier: {completed, first_try, rate, below_threshold, at_ceiling}},
  "recommendations": [...], "budget": {"cap", "applied", "remaining"}, "notes": [...]}`.
  `below_threshold` = `completed >= min_sample and rate is not None and rate < threshold`
  (STRICTLY below — a tier exactly at the threshold is not struggling). `at_ceiling` = the
  tier's next rung in `LIVE_TIER_ORDER` is `"frontier"`, or the tier IS `"frontier"`. A
  recommendation `{"from": tier, "to": next_rung, "task_ids": [...], "rate": rate,
  "completed": n, "first_try": p}` is emitted iff `below_threshold` and NOT `at_ceiling` and
  `task_ids` is non-empty, where `task_ids` = ids of `status == "pending"` tasks whose
  `tier_for(effective_alias(task, applied))` equals the struggling tier, in TASKS.md order.
  Recommendations are ordered by ladder position and NEVER contain `to == "frontier"`
  (structural: the ceiling check runs first). Notes: `below_threshold` + `at_ceiling` →
  `frontier locked: escalation valve only (<tier> first-try <p>/<n> below threshold)`;
  `below_threshold` + empty `task_ids` → `no pending <tier> tasks to upgrade`;
  `remaining == 0` → `auto-upgrade budget exhausted — advisory only`. `budget`:
  `applied = len(applied)`, `remaining = max(0, max_auto - applied)`. Recommendations are
  STILL listed when the budget is exhausted (advisory printing must keep working); the skill
  owns the apply-only-while-remaining rule.
- `build_live_card(kit_name, decision, autonomy, notes) -> dict` — top-level keys EXACTLY
  `schema_version` (`LIVE_SCHEMA_VERSION`), `kit`, `generated_at` (same style as
  `build_scorecard`), `autonomy`, `signals`, `recommendations`, `budget`, `notes` (decision
  notes + caller notes).
- `render_live_markdown(card) -> str` — H1 `# Live re-route signal — <kit>`; a line
  `autonomy: <posture>`; one line per tier in ladder order —
  `- <tier>: first-try <first_try>/<completed>` with ` — below threshold` appended when
  flagged and `- <tier>: no finished tasks` when completed is 0; then either one
  `recommend: <from> → <to> — tasks <id, id> (first-try <p>/<n>)` line per recommendation or
  exactly `no re-route recommended`; then
  `budget: <applied>/<cap> auto-upgrades applied (<remaining> remaining)`; then a `Notes:`
  bullet list when notes exist (mirror `render_markdown`).

**CLI wiring (pinned):** new argparse flags `--live` (store_true), `--live-threshold` (float,
default `LIVE_RATE_THRESHOLD`), `--live-min-sample` (int, default `LIVE_MIN_SAMPLE`),
`--live-max-auto` (int, default `LIVE_MAX_AUTO_UPGRADES`). Rules: `--live` with `--session` →
`sys.exit("--live takes no --session")`. `--demo --live` → the live demo (below). Kit flow with
`--live`: resolve kit dir and parse TASKS.md exactly as today; read NOTES.md text once into a
local variable feeding BOTH `parse_outcomes` and `parse_reroutes` (missing NOTES.md → empty
outcomes/events plus the existing degradation note); read `PLAN.md` from the kit dir if present
and feed `parse_autonomy` (missing → its None path); compute `upgrade_decision` with the three
knob values; `build_live_card`; print markdown or `json.dumps(card, indent=2)`; `return 0` —
ALL BEFORE the existing `cr.load_pricing()` line, which the live branch must never reach (T2
proves this by stubbing `load_pricing` to raise). Non-live paths behave byte-identically to
today.

**Demo (pinned):** `--demo --live` builds a synthetic MID-RUN kit in a
`tempfile.TemporaryDirectory` (TASKS.md + NOTES.md, NO PLAN.md) and runs the normal live path
against it (same functions, same render), printing markdown or `--json`, exit 0.
- `DEMO_LIVE_TASKS_MD`: nine task blocks (headings `### L1 — <title>` … `### L9 — <title>`,
  spaced em dash, each with `- status:` and `- model:` lines): L1 haiku done; L2 sonnet done;
  L3 sonnet done; L4 sonnet blocked; L5 sonnet pending; L6 sonnet pending; L7 opus pending;
  L8 haiku pending; L9 fable pending.
- `DEMO_LIVE_NOTES_MD`: brief prose (the advisory line below was logged earlier in the run and
  consumes no budget), then exactly:
  `outcome: L1 model=haiku attempts=1 result=pass review=clean`
  `outcome: L2 model=sonnet attempts=1 result=pass review=clean`
  `outcome: L3 model=sonnet attempts=2 result=retry-pass review=revised`
  `outcome: L4 model=sonnet attempts=2 result=blocked review=none`
  `reroute: sonnet to=opus mode=advisory tasks=L5,L6 rate=1/3`
- Expected (the verify asserts): signals.sonnet `{completed 3, first_try 1, rate 1/3,
  below_threshold true}`; signals.haiku `{completed 1}` (sample below 3 → no recommendation);
  signals.opus `{completed 0}`; EXACTLY one recommendation
  `{from: sonnet, to: opus, task_ids: [L5, L6]}` — L7/L8/L9 in no recommendation; budget
  `{cap 2, applied 0, remaining 2}`; autonomy `advisory` with the no-PLAN.md note.

GOTCHAS: zero `Path.home()` (still); no real model ids (tier names + `fable` alias only); the
`--live` branch returns before any pricing load; `parse_tasks` needs the spaced em dash in demo
headings; rates None (never 0) on zero denominators; `to` values in recommendations are tier
names that double as Agent-tool aliases (upgrades never target frontier, so no `fable`
translation exists anywhere on the upgrade path).

**Acceptance.**
- `python3 bin/routing_scorecard.py --demo --json` still yields the Tier-1 pinned numbers
  (quality 6/6/3/1/1/1, mix {haiku 1, sonnet 4, fable 1}, survival 0.75) — additive proof.
- `python3 bin/routing_scorecard.py --demo --live` prints the pinned markdown shape;
  `--demo --live --json` parses with exactly the D9 key set and the pinned demo numbers.
- The pure functions exist with the pinned names/behaviors; a struggling-opus fixture yields NO
  recommendation, `at_ceiling` true, and the `frontier locked` note.
- `--live` + `--session` exits nonzero; a completed real kit (`fusion-tier1`) under
  `--live --json` exits 0 with empty recommendations.
- Greps: no `Path.home()`, no `sqlite`, no real model ids in the file; reused scripts,
  `data/`, and `tests/test_routing_scorecard.py` unchanged; full suite + sync check green.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/routing_scorecard.py --demo --live && python3 - <<'PY' && ! grep -n 'Path.home()' bin/routing_scorecard.py && ! grep -n 'sqlite' bin/routing_scorecard.py && ! grep -nE 'claude-(fable|opus|sonnet|haiku)' bin/routing_scorecard.py && git diff --quiet -- tests/test_routing_scorecard.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T1 OK'
import importlib.util, json, subprocess, sys
from pathlib import Path
# --- Tier-1 additive regression: the old demo numbers are byte-stable ---
j = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--json"], capture_output=True, text=True)
assert j.returncode == 0, j.stderr
c = json.loads(j.stdout)
assert set(c) == {"schema_version", "kit", "generated_at", "tasks", "quality", "model_mix", "review", "cost", "notes"}, set(c)
q = c["quality"]
assert (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"], q["escalated_pass"], q["blocked"]) == (6, 6, 3, 1, 1, 1), q
assert c["model_mix"] == {"haiku": 1, "sonnet": 4, "fable": 1}, c["model_mix"]
assert abs(c["review"]["survival_rate"] - 0.75) < 1e-9, c["review"]
# --- the live demo: pinned Tier-2 numbers ---
l = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--live", "--json"], capture_output=True, text=True)
assert l.returncode == 0, l.stderr
d = json.loads(l.stdout)
assert set(d) == {"schema_version", "kit", "generated_at", "autonomy", "signals", "recommendations", "budget", "notes"}, set(d)
assert d["schema_version"] == 1 and d["autonomy"] == "advisory", (d["schema_version"], d["autonomy"])
s = d["signals"]["sonnet"]
assert (s["completed"], s["first_try"]) == (3, 1) and s["below_threshold"] is True, s
assert abs(s["rate"] - 1/3) < 1e-9, s
recs = d["recommendations"]
assert len(recs) == 1 and recs[0]["from"] == "sonnet" and recs[0]["to"] == "opus", recs
assert recs[0]["task_ids"] == ["L5", "L6"], recs
assert not any(r["to"] == "frontier" for r in recs)
assert d["budget"] == {"cap": 2, "applied": 0, "remaining": 2}, d["budget"]
assert d["signals"]["haiku"]["completed"] == 1 and d["signals"]["opus"]["completed"] == 0, d["signals"]
ids = [tid for r in recs for tid in r["task_ids"]]
assert "L7" not in ids and "L8" not in ids and "L9" not in ids, ids
m = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--live"], capture_output=True, text=True)
assert m.returncode == 0, m.stderr
for needle in ("# Live re-route signal —", "autonomy: advisory", "- sonnet: first-try 1/3",
               "recommend: sonnet → opus — tasks L5, L6", "budget: 0/2 auto-upgrades applied"):
    assert needle in m.stdout, f"markdown missing: {needle!r}\n{m.stdout}"
# --- pure-function checks: constants, callables, never-frontier at the ceiling ---
spec = importlib.util.spec_from_file_location("routing_scorecard", Path("bin/routing_scorecard.py").resolve())
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
assert rs.LIVE_TIER_ORDER == ("haiku", "sonnet", "opus", "frontier")
assert rs.LIVE_RATE_THRESHOLD == 0.5 and rs.LIVE_MIN_SAMPLE == 3 and rs.LIVE_MAX_AUTO_UPGRADES == 2
for fn in ("parse_reroutes", "parse_autonomy", "effective_alias", "live_tier_stats",
           "upgrade_decision", "build_live_card", "render_live_markdown"):
    assert callable(getattr(rs, fn)), fn
tasks = [{"id": f"X{i}", "status": "done" if i < 4 else "pending", "model": "opus"} for i in range(6)]
outs = {f"X{i}": {"model": "opus", "attempts": 2, "result": "blocked", "review": "none"} for i in range(4)}
dec = rs.upgrade_decision(tasks, outs, [])
assert dec["recommendations"] == [], dec["recommendations"]
sig = dec["signals"]["opus"]
assert sig["below_threshold"] is True and sig["at_ceiling"] is True, sig
assert any(n.startswith("frontier locked: escalation valve only") for n in dec["notes"]), dec["notes"]
# --- CLI guardrails + real-kit degradation ---
x = subprocess.run([sys.executable, "bin/routing_scorecard.py", "fusion-tier1", "--live", "--session", "nope"], capture_output=True, text=True)
assert x.returncode != 0, "--live must reject --session"
g = subprocess.run([sys.executable, "bin/routing_scorecard.py", "fusion-tier1", "--live", "--json"], capture_output=True, text=True)
assert g.returncode == 0, g.stderr
gd = json.loads(g.stdout)
assert gd["recommendations"] == [], gd["recommendations"]
print("T1 live checks ok")
PY
```

---

### T2 — Regression tests (tests/test_reroute_live.py)
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Create `tests/test_reroute_live.py`, stdlib `unittest`, loading
`bin/routing_scorecard.py` via the importlib `_load` convention off
`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` (copy the header pattern and
module-docstring safety contract from `tests/test_routing_scorecard.py`: no test reads the real
`~` project store or calls the stdlib home helper; every kit fixture lives in a fresh
`tempfile.TemporaryDirectory()` handed over via `--kits-dir` or an explicit kit path; this file
never opens `data/pricing.json` directly and additionally proves the live path never loads it).
Do NOT edit `tests/test_routing_scorecard.py` — this is a new file.

Helper: `write_kit(tmp, tasks_md, notes_md=None, plan_md=None) -> Path` writing a kit dir under
a temp `kits` root. Task fixtures use the spaced em dash headings (`### K1 — x`) with
`- status:` / `- model:` lines; ledger fixtures use the pinned `outcome:` / `reroute:`
grammars. All ids/values synthetic.

Minimum cases — include these EXACT method names (greps in the verify key on them), plus
whatever else you need:

1. `test_parse_reroutes_happy_and_tolerant` — happy path; leading `- `/`* ` bullets; unknown
   `key=value` ignored; missing `tasks=` → `[]`; malformed mode/tier lines skipped + note;
   `to=frontier` parsed but adds the out-of-policy note; file order preserved.
2. `test_parse_autonomy_defaults_and_override` — `autonomy: auto` and `autonomy: advisory`
   lines; absent line → advisory with no note; None text → advisory + note; unrecognized value
   (e.g. `autonomy: yolo`) → advisory + note; first match wins when duplicated.
3. `test_attribution_matrix` — `pass`/`retry-pass`/`blocked` attribute to the outcome
   `model=`'s tier; `escalated-pass` on a sonnet-pinned task with `model=fable` attributes to
   SONNET (never frontier); a `fable`-pinned task's `pass` lands in the frontier bucket;
   unknown outcome ids skipped + note; all four `LIVE_TIER_ORDER` tiers always present with
   zeros.
4. `test_escalated_attribution_follows_applied_upgrade` — a haiku-pinned task covered by a
   `mode=applied` haiku→sonnet event that later records `result=escalated-pass model=fable`
   counts against SONNET's stats (effective-pin reconstruction).
5. `test_never_frontier_sweep` — across a sweep of adversarial fixtures (struggling opus,
   struggling frontier/`fable` pins, mixed struggling tiers, tiny thresholds/min_sample=1 via
   kwargs), NO output of `upgrade_decision` ever contains a recommendation with
   `to == "frontier"`; struggling opus sets `at_ceiling` and the
   `frontier locked: escalation valve only` note.
6. `test_min_sample_gate` — a tier with `min_sample - 1` completed failures produces no
   recommendation; the same fixture with one more completed failure produces one.
7. `test_threshold_boundary` — rate exactly AT the threshold does not trigger (strictly
   below); just under does; `rate is None` (zero completed) never triggers.
8. `test_upgrade_is_one_step_and_pending_only` — recommendations target exactly the next rung;
   `task_ids` contain only `status == "pending"` tasks of the struggling tier, in TASKS.md
   order (never `done`/`in-progress`/`blocked` ids).
9. `test_effective_pin_shift` — after a `mode=applied` haiku→sonnet event, a pending
   haiku-pinned task appears in a subsequent sonnet→opus recommendation's `task_ids`, and no
   haiku recommendation re-fires for it (convergence to no-op).
10. `test_budget_counting` — `mode=advisory` events consume nothing; N `mode=applied` events
    give `applied == N` and `remaining == max(0, cap - N)`; with the budget exhausted,
    recommendations are STILL listed and the `auto-upgrade budget exhausted` note appears.
11. `test_cli_live_json_keys` — a temp kit with ledger + `--live --json`: top-level keys
    exactly `{schema_version, kit, generated_at, autonomy, signals, recommendations, budget,
    notes}`, expected numbers for the fixture; markdown mode contains the H1, the
    `autonomy:` line, a `budget:` line, and `recommend:`-or-`no re-route recommended`.
12. `test_cli_live_missing_notes_and_plan` — kit with TASKS.md only → exit 0, empty
    recommendations, degradation note, autonomy `advisory`; a kit whose PLAN.md carries
    `autonomy: auto` → JSON `autonomy == "auto"`.
13. `test_cli_live_rejects_session` — `--live` + `--session x` → nonzero exit, message
    mentions `--session`.
14. `test_cli_live_knob_flags` — `--live-min-sample 1` triggers a recommendation a
    default-knob run does not; `--live-max-auto 0` reports remaining 0 + the exhausted note.
15. `test_demo_live_pinned_numbers` — `--demo --live --json` via subprocess: the T1-pinned
    demo expectations (sonnet 3/1 below threshold, one sonnet→opus rec for L5+L6, budget
    0/2/2, autonomy advisory); `--demo --live` markdown contains the pinned lines.
16. `test_tier1_demo_regression` — `--demo --json` via subprocess still yields the Tier-1
    pinned quality/mix/survival numbers (additive proof).
17. `test_pricing_free_live_path` — stub `rs.cr.load_pricing` with a function that raises,
    then call `rs.main(["<kit>", "--live", "--kits-dir", <tmp>, "--json"])` (capture stdout)
    — it must succeed, proving the live branch never loads pricing (restore the stub in
    `finally`).
18. `test_readonly_live_run` — byte-snapshot the temp kit dir before/after a full `--live`
    CLI run — identical (`--live` never writes; `reroute:` lines are orchestrator-owned).

**Acceptance.** All new tests pass; full suite green; `tests/test_routing_scorecard.py` and the
reused scripts untouched; safety greps clean; only this file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_reroute_live.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && git diff --quiet -- tests/test_routing_scorecard.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && echo 'T2 OK'
import re
text = open('tests/test_reroute_live.py').read()
assert 'Path.home()' not in text
assert '~/.claude' not in text, "real home path in tests"
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
for name in ('test_parse_reroutes_happy_and_tolerant', 'test_parse_autonomy_defaults_and_override',
             'test_attribution_matrix', 'test_escalated_attribution_follows_applied_upgrade',
             'test_never_frontier_sweep', 'test_min_sample_gate', 'test_threshold_boundary',
             'test_upgrade_is_one_step_and_pending_only', 'test_effective_pin_shift',
             'test_budget_counting', 'test_cli_live_json_keys',
             'test_cli_live_missing_notes_and_plan', 'test_cli_live_rejects_session',
             'test_cli_live_knob_flags', 'test_demo_live_pinned_numbers',
             'test_tier1_demo_regression', 'test_pricing_free_live_path',
             'test_readonly_live_run'):
    assert f'def {name}' in text, f"missing case: {name}"
assert '--kits-dir' in text and 'load_pricing' in text
print('safety greps ok')
PY
```

---

*Phase 1 end — dispatch `fusion-tier2-reviewer` before starting Phase 2.*

---

## Phase 2 — The skills (the contract-sensitive phase)

### T3 — Add live re-routing + the autonomy dial to skills/execute/SKILL.md
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Per PLAN.md D1–D7. Five edits to `skills/execute/SKILL.md`, BODY only (frontmatter
untouched — the plugin is live). If any anchor below is not found verbatim, STOP and report.

*Edit 1* — in "## Setup", replace the exact line:

```
2. Read `PLAN.md` (goal, constraints, tripwires) and `TASKS.md`.
```

with:

```
2. Read `PLAN.md` (goal, constraints, tripwires) and `TASKS.md`. Read the autonomy dial once here: an explicit user instruction at invocation ("execute <slug> autonomously" / "advisory") wins for this run, else PLAN.md's optional `autonomy:` line (`advisory` or `auto`), else `advisory` (see **Live re-routing — upgrade-only, autonomy-gated** below).
```

*Edit 2* — in "## The loop" step 2, replace the exact sentence:

```
Choose the dispatch mode per **Dispatch modes — fresh fan-out vs warm sidekick** below.
```

with:

```
Choose the dispatch mode per **Dispatch modes — fresh fan-out vs warm sidekick** below. When a logged `mode=applied` re-route covers this task, pass the upgraded alias as the `model` parameter instead — the task's `model` field stays the dispatch default and is never rewritten (see **Live re-routing — upgrade-only, autonomy-gated** below).
```

*Edit 3* — in "## The loop" step 4, replace the exact text:

```
and append the task's `outcome:` line (see **Outcome ledger** below).
```

with:

```
and append the task's `outcome:` line (see **Outcome ledger** below). A fresh outcome line is a fresh signal — consult **Live re-routing — upgrade-only, autonomy-gated** below before the next dispatch.
```

*Edit 4* — insert a new section between the end of the "## Outcome ledger — one line per
finished task" section (i.e. after the paragraph ending `fresh line — the scorecard takes the
LAST line per task id.`) and the heading `## Escalation valve — blocked tasks go back to
Fable, one at a time`. Insert verbatim (blank line before and after):

```markdown
## Live re-routing — upgrade-only, autonomy-gated

The outcome ledger doubles as a live routing signal. The moment any `outcome:` line lands
(step 4 or 5), consult the kit's running per-tier first-try rate:

    python3 bin/routing_scorecard.py <slug> --live

`--live` reads TASKS.md plus the NOTES.md ledger so far (read-only — it never writes) and
recommends an upgrade only when a tier's live first-try rate falls below its threshold over a
minimum sample of that tier's finished tasks. Recommendations are UPGRADE-ONLY and move
exactly one step up the tier ladder (haiku→sonnet, sonnet→opus) — never down, never skipping
a rung, and NEVER to frontier/Fable: Fable is reached exclusively through the per-task,
evidence-carrying escalation valve below. When the struggling tier sits one rung under
frontier, `--live` reports the signal but locks the recommendation — the valve is the only
path up from there.

A re-route is a **runtime dispatch override, never a TASKS.md rewrite**. The task's `model`
field stays the dispatch default and is never edited; an applied upgrade changes only the
alias you pass as the Agent tool's `model` parameter for the remaining PENDING tasks it
names (never an in-progress task), and it ends any warm cluster serving those tasks — a
model change always ends a cluster. Every recommendation you act on or announce is logged to
NOTES.md as one machine-readable line (the budget below is counted from these):

    reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>

The autonomy dial decides what you may do with a recommendation:

- **advisory (the default)** — PRINT the recommendation to the user and change nothing:
  every task keeps dispatching on its pinned `model`. Log the printed recommendation once
  (`mode=advisory`) so an unchanged signal is not re-announced. The human decides.
- **auto** — apply it yourself: dispatch the named pending tasks on the upgraded alias, log
  `mode=applied`, and say so in your report. Respect the `budget` block in the `--live`
  output — `mode=applied` events are capped per run, and when `remaining` hits 0 you fall
  back to advisory printing. Auto also arms the escalation valve: a task `blocked` after
  retry goes straight to the Fable consult without pausing to ask.

Downgrades are never automatic in either mode — if a tier looks over-provisioned, say so in
the end-of-run report and let the human re-pin the next kit.
```

*Edit 5* — in "## Escalation valve", replace the exact text:

```
offer (or if running autonomously, do) a **targeted Fable consult**:
```

with:

```
offer (or, when the autonomy dial is `auto`, do without pausing to ask — see **Live re-routing — upgrade-only, autonomy-gated**) a **targeted Fable consult**:
```

Change nothing else — in particular do not touch the frontmatter, the lean-driver or
dispatch-modes sections, the outcome-ledger grammar, the rest of the valve (mechanism
unchanged), or "## End of run".

**Acceptance.** All five edits landed exactly once; section order Setup → Operating rule → The
loop → Dispatch modes → Outcome ledger → Live re-routing → Escalation valve → End of run;
every pre-existing contract element intact (verify's grep list); the dial text defaults to
advisory (print-only) and never permits frontier; frontmatter untouched; suite + sync green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T3 OK'
t = open('skills/execute/SKILL.md').read()
assert t.startswith('---\nname: execute\n'), "frontmatter touched"
# --- Tier-1 contract elements: all must survive ---
for s in [
    "## Setup", "## Operating rule — lean driver", "## The loop",
    "## Dispatch modes — fresh fan-out vs warm sidekick",
    "## Outcome ledger — one line per finished task",
    "`in-progress` in TASKS.md", "mark `done`", "mark `blocked`",
    "skip `done`, stop at `blocked` deps",
    "passing the task's `model` value as the Agent tool's `model` parameter",
    "overrides the agent's frontmatter default", "Phase boundaries", "reviewer agent",
    "independent — one message, multiple Agent calls", "## Escalation valve",
    "`model: fable`", "## End of run",
    "outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>",
    "SAME `model` value", "always a fresh spawn", "the LAST line per task id",
    "`result=escalated-pass`", "bin/routing_scorecard.py",
]:
    assert s in t, f"contract element lost: {s!r}"
# --- Tier-2 elements: present exactly once where counted ---
assert t.count("## Live re-routing — upgrade-only, autonomy-gated") == 1, "new H2 missing/duplicated"
for s in [
    "runtime dispatch override, never a TASKS.md rewrite",
    "NEVER to frontier/Fable",
    "one step up the tier ladder (haiku→sonnet, sonnet→opus)",
    "reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>",
    "**advisory (the default)**", "change nothing", "The human decides",
    "`mode=applied` events are capped", "ends any warm cluster",
    "never an in-progress task", "Downgrades are never automatic",
    "--live", "Read the autonomy dial once here",
    "pass the upgraded alias as the `model` parameter instead",
    "A fresh outcome line is a fresh signal",
    "when the autonomy dial is `auto`, do without pausing to ask",
]:
    assert s in t, f"tier-2 element missing: {s!r}"
assert "offer (or if running autonomously, do)" not in t, "old valve parenthetical should be replaced"
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

### T4 — Sync skills/architect/SKILL.md and re-check the shared contract in BOTH skills
- status: done
- model: opus
- depends: T3
- independent: no

**Brief.** Per PLAN.md D3/D5 and the CLAUDE.md invariant ("if you touch either skill you MUST
re-check both"). Two pinned edits to `skills/architect/SKILL.md` (BODY only), then the
dual-file contract audit.

*Edit 1* — in "## Step 1 — The plan", insert a new bullet immediately after the exact bullet
line:

```
- **Risks and their tripwires** — what an executor should watch for and what to do when hit
```

New bullet (verbatim):

```
- **Autonomy posture (optional)** — a single `autonomy: advisory` or `autonomy: auto` line anywhere in PLAN.md (absent = advisory). Execute reads it as the kit's dial for live re-routing and auto-escalation; the user can override it per run at invocation. An optional PLAN.md line, not a task field — the task-field contract is unchanged.
```

*Edit 2* — in the "### `TASKS.md` (same kit directory)" section, replace the exact bullet:

```
- The task's `model` field is authoritative at dispatch time: execute passes it as the Agent tool's `model` parameter, which overrides the implementer agent's frontmatter default.
```

with:

```
- The task's `model` field is authoritative at dispatch time: execute passes it as the Agent tool's `model` parameter, which overrides the implementer agent's frontmatter default. When a kit runs with the autonomy dial on `auto`, execute may layer a logged, upgrade-only runtime override on top at dispatch (one tier step, never to frontier) — the field itself is never rewritten and stays the dispatch default.
```

Change nothing else in the file.

*The audit* — after editing, re-check BOTH `skills/architect/SKILL.md` and
`skills/execute/SKILL.md` against the full shared contract (the verify below encodes it): kit
layout (`PLAN.md`, `TASKS.md`, `NOTES.md` owned by execute); task fields `id`, `title`,
`status`, `model`, brief, acceptance, verify; status vocabulary exactly
`pending | in-progress | done | blocked`; `## Phase N — <name>` headings;
`depends:`/`independent:`; the model-override-at-dispatch rule stated in both files AND still
true under re-routing (the pin is the dispatch default; the override is runtime, logged,
upgrade-only, opt-in — never a field rewrite); the dial defaulting to advisory in both files'
wording; the never-frontier rule stated wherever re-routing is described; the `reroute:`
grammar in execute matching `bin/routing_scorecard.py`'s `parse_reroutes`. If ANY element is
missing or contradicted, STOP and report — that is a T1/T3 defect to fix via the orchestrator,
not something to patch ad hoc here.

**Acceptance.** Both architect edits landed exactly once; the dual-file grep audit passes;
architect frontmatter untouched; no other file changed by this task; suite + sync green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && git diff --quiet -- tests/test_routing_scorecard.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && echo 'T4 OK'
a = open('skills/architect/SKILL.md').read()
e = open('skills/execute/SKILL.md').read()
assert a.startswith('---\nname: architect\n'), "architect frontmatter touched"
assert e.startswith('---\nname: execute\n'), "execute frontmatter touched"
# --- architect contract elements (Tier-1 list, all must survive) ---
for s in [
    "`id`, `title`, `status` (pending/in-progress/done/blocked), `model`",
    "Self-contained brief", "Acceptance criteria", "Verify command",
    "`## Phase N — <name>` headings",
    "`depends: <ids>` or `independent: yes`",
    "overrides the implementer agent's frontmatter default",
    "NOTES.md", "-implementer.md", "-verifier.md", "-reviewer.md",
    "## Step 1", "## Step 2", "## Step 3",
]:
    assert s in a, f"architect element lost: {s!r}"
assert a.count("warm-cluster candidates") == 1, "tier-1 warm-cluster bullet lost/duplicated"
assert a.count("`outcome:` line per finished task") == 1, "tier-1 ledger mention lost/duplicated"
# --- architect Tier-2 additions: exactly once ---
assert a.count("**Autonomy posture (optional)**") == 1, "autonomy bullet missing/duplicated"
assert "not a task field — the task-field contract is unchanged" in a
assert a.count("upgrade-only runtime override") == 1, "model-bullet extension missing/duplicated"
assert "one tier step, never to frontier" in a
assert "never rewritten and stays the dispatch default" in a
# --- execute contract elements (full final state) ---
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
]:
    assert s in e, f"execute element lost: {s!r}"
print("dual-file contract audit ok")
PY
```

---

*Phase 2 end — dispatch `fusion-tier2-reviewer` before starting Phase 3.*

---

## Phase 3 — Documentation and guardrails

### T5 — Write docs/FUSION-TIER2.md and point Tier 1's Deferred section at it
- status: done
- model: sonnet
- depends: T4
- independent: yes

**Brief.** Two pieces.

*Piece 1* — new file `docs/FUSION-TIER2.md` documenting what this kit built and what it
deliberately did not. Match the tone/format of `docs/FUSION-TIER1.md` (H1 + H2 sections,
concrete commands, no prices, no real model ids — tier names and the `fable` alias are fine,
no `/private/tmp/` paths). Required structure — H1
`# Fusion Tier 2 — dynamic mid-kit re-routing behind an autonomy dial`, then EXACTLY these
five H2s in order:

1. `## The live signal` — the outcome ledger doubles as a live routing signal: per-tier
   first-try rate over the ledger-so-far, judged only past a minimum sample and against a
   strict-below threshold (both are `bin/routing_scorecard.py` constants, CLI-tunable via
   `--live-threshold`/`--live-min-sample`/`--live-max-auto` — do not restate the numbers as
   prose facts, name the constants). Attribution: `pass`/`retry-pass`/`blocked` count against
   the tier of the ledger's `model=`; `escalated-pass` counts against the reconstructed
   DISPATCH tier (pin plus applied re-routes), never against frontier — the ledger's `model=`
   on an escalated line names the Fable fixer, not the failing tier. Usage:
   `python3 bin/routing_scorecard.py <slug> --live` (+ `--json`), and
   `python3 bin/routing_scorecard.py --demo --live` as the synthetic mid-run smoke. The live
   path is quality-only: it never loads pricing and rejects `--session`.
2. `## Upgrade-only re-routing` — recommendations move exactly one rung up
   haiku→sonnet→opus and STOP before frontier: a struggling opus tier yields
   `frontier locked: escalation valve only`, never a recommendation — Fable is reached
   exclusively through the per-task, evidence-carrying escalation valve, whose mechanism is
   unchanged. Never down: over-provisioning is reported at end of run for the human. A
   re-route is a runtime dispatch override — the TASKS.md `model` field is never rewritten,
   the pin stays the dispatch default, and the shared architect/execute kit contract is
   untouched. Every acted-on or announced recommendation is logged to NOTES.md; include the
   grammar line verbatim:
   `reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>`
   — and note that Tier-1's `outcome:` parser ignores these lines by construction (unknown
   line shapes never match `OUTCOME_RE`).
3. `## The autonomy dial` — OFF by default = advisory: the loop only PRINTS the
   recommendation (logged once as `mode=advisory` so an unchanged signal is not re-announced)
   and the human decides; nothing is auto-changed. ON = `auto`: the loop applies upgrade-only
   recommendations itself (logged as `mode=applied`) behind the budget guardrail — applied
   events are capped per run, counted from the NOTES.md `reroute:` lines so the state survives
   compaction, and at 0 remaining the loop falls back to advisory printing — AND a blocked
   task auto-consults Fable through the existing valve without pausing to ask. Declared as an
   optional `autonomy: advisory|auto` line in the kit's PLAN.md (absent = advisory); an
   explicit user instruction at invocation ("execute <slug> autonomously") overrides it per
   run. Not a task field.
4. `## Contract safety` — why the shared contract survives byte-intact: "the task's `model`
   field overrides the implementer agent's frontmatter at dispatch" stays true — the pin
   remains the dispatch default and the field-beats-frontmatter precedence is untouched; the
   dial adds an explicit, opt-in, logged, upgrade-only layer on top, and with the dial off the
   pin is always honored. No new required task field (`autonomy:` is an optional PLAN.md
   line); `parse_tasks` needed no change; NOTES.md is execute-owned so the `reroute:` line is
   not a contract change (precedent: the `outcome:` ledger); an applied upgrade ends any warm
   cluster serving those tasks (a model change always ends a cluster).
5. `## Still deferred` — scorecard-over-time / cross-kit aggregation (the per-kit JSON is the
   substrate); auto-downgrade (never automatic by DESIGN, not merely deferred); main-session
   model switching (still the upstream ask, tracked in `docs/FUSION-TIER1.md`).

*Piece 2* — in `docs/FUSION-TIER1.md`, append a new paragraph at the very end of the file
(the `## Deferred — Tier 2` section currently ends with the line `acts on them is deferred.`).
Append (blank line before it):

```
Tier 2 has since shipped — see [FUSION-TIER2.md](FUSION-TIER2.md) for the live per-tier
signal, the upgrade-only re-route rule (one step, never to frontier), and the opt-in autonomy
dial (advisory by default).
```

Change nothing else in FUSION-TIER1.md — its five H2s and all prior text stay intact.

**Acceptance.** FUSION-TIER2.md exists with the H1 + exactly those five H2s in order; the
`reroute:` grammar line verbatim; mentions `--live`, `--demo --live`, `autonomy:`, the budget
guardrail, and the escalation valve; FUSION-TIER1.md gained exactly the pointer paragraph and
its H2 set is unchanged; greps clean; suite green; only FUSION-TIER2.md new.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T5 OK'
import re
t = open('docs/FUSION-TIER2.md').read()
assert t.lstrip().startswith('# Fusion Tier 2 — dynamic mid-kit re-routing behind an autonomy dial')
h2s = [l for l in t.splitlines() if l.startswith('## ')]
assert h2s == ['## The live signal', '## Upgrade-only re-routing', '## The autonomy dial',
               '## Contract safety', '## Still deferred'], h2s
assert 'reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>' in t
for s in ('--live', '--demo --live', 'autonomy:', 'advisory', 'escalation valve', 'budget',
          'never rewritten', 'routing_scorecard.py', 'frontier locked'):
    assert s in t, f'missing: {s}'
assert not re.search(r'claude-(fable|opus|sonnet|haiku)-?[0-9]', t), 'real model id in doc'
assert '/private/tmp' not in t
o = open('docs/FUSION-TIER1.md').read()
assert o.count('Tier 2 has since shipped') == 1, 'pointer missing/duplicated'
assert 'FUSION-TIER2.md' in o
h2s1 = [l for l in o.splitlines() if l.startswith('## ')]
assert h2s1 == ['## The three borrows', '## The outcome ledger', '## The scorecard',
                '## Upstream limitation — main-session model switching', '## Deferred — Tier 2'], h2s1
print('doc structure ok')
PY
```

---

### T6 — Pinned CLAUDE.md run-line
- status: done
- model: haiku
- depends: T1
- independent: yes

**Brief.** ONE pinned insertion, nothing else. (The `For \`fusion-tier2\` specifically:` fence
paragraph already exists in CLAUDE.md — the architect added it; do not touch it.) If the
anchor is not found verbatim, STOP and report.

*Insertion — CLAUDE.md, "## How to run things" code block.* Immediately AFTER the line:

```
python3 bin/routing_scorecard.py --demo           # routing-quality scorecard smoke (synthetic kit, no real data)
```

insert this line into the same code block:

```
python3 bin/routing_scorecard.py --demo --live    # live re-route signal smoke (synthetic mid-run kit, upgrade-only, never frontier)
```

**Acceptance.** The insertion is present exactly once, directly after the `--demo` line; the
fusion-tier2 fence paragraph is present exactly once (pre-existing); no other CLAUDE.md line
changed by this task; suite green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T6 OK'
c = open('CLAUDE.md').read()
line = 'python3 bin/routing_scorecard.py --demo --live    # live re-route signal smoke (synthetic mid-run kit, upgrade-only, never frontier)'
assert c.count(line) == 1, "run-line missing/duplicated"
i_demo = c.index('python3 bin/routing_scorecard.py --demo  ')
i_live = c.index(line)
assert i_live > i_demo and c[i_demo:i_live].count('\n') == 1, "live line not directly after the --demo line"
assert c.count('For `fusion-tier2` specifically:') == 1, "fence paragraph missing/duplicated"
print('insertion ok')
PY
```

---

*Phase 3 end — dispatch `fusion-tier2-reviewer`, then run PLAN.md's overall done-check.*
