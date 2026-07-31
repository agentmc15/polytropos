# TASKS — per-task-dollars

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially Repo facts, decisions D1–D10, the
OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `per-task-dollars-implementer` (the parameter overrides the
agent's frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. **No warm-cluster candidates in this kit:** T1 → T2
and T3 → T4 are serial but cross model pins (opus→sonnet, sonnet→opus), and a model-pin change
always ends a cluster; T5 ‖ T6 are independent and fan out fresh. Dispatch
`per-task-dollars-reviewer` at each phase end. This kit's PLAN.md declares `autonomy: advisory`
— re-route recommendations during this run are print-only.

Standing rules for every task:

- **The architect/execute shared kit contract is the #1 invariant.** Skill edits are BODY-only
  — never touch the YAML frontmatter of any `skills/*/SKILL.md` (the plugin is installed LIVE;
  skill files are runtime behavior). Every pinned contract element must survive in BOTH skills
  after every task — including the Tier-2 runtime-override clause, verbatim.
  `skills/architect/SKILL.md` is NOT edited by this kit at all (PLAN D8) — any diff in it is a
  defect. If a brief's anchor text is not found verbatim, STOP and report the discrepancy —
  never fuzzy-match, never improvise.
- **Never split the orchestrator; never fabricate or divide a per-task figure.** The main
  transcript is ONE un-attributable line; a warm-cluster shared transcript is attributed to
  the cluster as a unit; a recorded agent id with no transcript prices `null` + note (never a
  zero or a guess); a per-task figure is only ever the sum of transcripts that actually
  exist; coverage is labeled `full`/`partial`/null; the parts-vs-whole reconciliation is a
  NOTE, never an adjustment. Phase reviewers/scouts ride the unattributed line by design.
- **`bin/routing_scorecard.py` changes are ADDITIVE only** — existing flags, function
  signatures, output shapes, exit codes, the Tier-1 `--demo` numbers, the Tier-2
  `--demo --live` numbers, AND the `--demo --history` numbers stay byte-stable, and
  `tests/test_routing_scorecard.py` + `tests/test_reroute_live.py` +
  `tests/test_routing_history.py` are never edited. `--by-task` requires `--session`; without
  the flag the `--session` output is byte-identical to today (`build_scorecard` and `MD_H2S`
  untouched; by-task notes nest inside `by_task`, never in the card's top-level `notes`).
  Never edit `bin/cost_report.py`, `bin/session_cost.py`, `bin/copilot_execute.py`, any other
  existing `bin/`/`tests/` file, `data/` (either pricing file), `.claude-plugin/`, `copilot/`,
  `README.md`, the generated `skills/*/references/` mirrors, or the completed kits and their
  agents. Never re-implement `parse_tasks`/`parse_outcomes`/`parse_reroutes`/`parse_sessions`/
  `tier_for`/`effective_alias`/the `session_cost` pipeline — call them. Sanctioned
  existing-file edits: `bin/routing_scorecard.py` (T1), `skills/execute/SKILL.md` (T3),
  `docs/ROUTING-HISTORY.md` (T5), `CLAUDE.md` (T6) — pinned changes only.
- Never hardcode a price, price ratio, or real model id. Sanctioned exceptions: tier
  vocabulary (`frontier`/`opus`/`sonnet`/`haiku`, `LIVE_TIER_ORDER`), the alias map
  `TASK_MODEL_TIERS = {"fable": "frontier"}`, `BYTASK_SCHEMA_VERSION = 1`,
  `AGENT_ROLES = ("implementer", "verifier", "escalation")`, the `DEMO_BYTASK_VOLUMES` token
  counts, the half-cent reconciliation epsilon, and synthetic fixture ids/values in tests and
  the demo. Demo/test transcript model ids are computed from `data/pricing.json` at run time
  via `_first_model_of_tier`.
- Never read the real `~/.claude` or the real tmp tasks scratch from a test or verify command
  — every fixture lives in a temp dir handed over via `--kits-dir`/`--projects-dir`/
  `--tasks-dir` or an explicit path. `Path.home()` count in `tests/test_per_task_dollars.py`
  and in the `bin/routing_scorecard.py` diff: ZERO. Never write outside this repo and temp
  dirs. No network. Do not commit or push.
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests [-p '<file>.py']`
  (the dotted-module form is broken on this machine). Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` path in any deliverable.

---

## Phase 1 — The attribution engine (additive scorecard extension)

### T1 — Extend bin/routing_scorecard.py with per-task dollars (--by-task)
- status: done
- model: opus
- depends: (none)
- independent: no

**Brief.** Per PLAN.md D1/D2/D3/D4/D5/D6/D7/D9/D10. Extend `bin/routing_scorecard.py`
ADDITIVELY a fourth time: new constants, new pure functions, a `--by-task` CLI flag on the
plain `--session` path, one guarded two-line hook in `render_markdown`, and a
`--demo --by-task` synthetic smoke. Zero changes to existing function signatures, outputs,
exit codes, or any of the THREE prior demos' numbers. Extend the module docstring with a short
`--by-task` usage line and one sentence: the by-task mode prices each recorded subagent's
`*.output` transcript per task and role from NOTES.md `agent:` lines, reports the main
transcript as one un-split orchestrator line, attributes a warm cluster's shared transcript
to the cluster as a unit, and degrades to n/a (whole-kit dollars unchanged) when no `agent:`
lines exist.

**New constants (pinned):**
- `BYTASK_SCHEMA_VERSION = 1` — same species as the other three schema versions.
- `AGENT_ROLES = ("implementer", "verifier", "escalation")` — grammar vocabulary, same
  species as `RESULTS`/`REVIEWS`.
- `AGENT_RE = re.compile(r"^\s*(?:[-*]\s+)?agent:\s+(\S+)\s+(.+)$")` — optional `-`/`*`
  bullet like the other three line formats; first token = task id; remaining `key=value`
  pairs read with the existing `PAIR_RE`.
- `DEMO_BYTASK_TASKS_MD` / `DEMO_BYTASK_NOTES_MD` / `DEMO_BYTASK_VOLUMES` fixture constants —
  see Demo below (exact content pinned in PLAN D9; do NOT modify the existing `DEMO_*`
  constants — the prior demos consume them).

**New pure functions (pinned signatures & behavior):**
- `parse_agents(text) -> (events, notes)` — scan lines with `AGENT_RE`. An event
  `{"task", "agent_id", "role", "model"}` is kept only when `id=` is present and `role=` is
  in `AGENT_ROLES`; otherwise the whole line is skipped with an
  `unrecognized agent line: <line>` note (mirror `parse_outcomes`' phrasing). `model` =
  `pairs.get("model")` — informational, `None` when absent, never validated. Unknown pairs
  ignored. Events in FILE ORDER; a repeated (task-id, agent-id) pair REPLACES the earlier
  event (last wins — re-runs append; keep the first occurrence's position). No id-format
  validation — the agent id's shape is harness-owned. The `agent:` key is disjoint from
  `outcome:`/`reroute:`/`session:` — none of the four parsers may match another's lines.
- `discover_agent_outputs(task_dirs) -> (mapping, notes)` — for each dir in the given order,
  `sorted(Path(d).glob("*.output"))`; `mapping` is `{filename stem: Path}`; a stem already
  seen (same agent id in two dirs) keeps the FIRST file + a note. Missing/empty dirs are
  simply skipped (no note needed — `discover_task_dirs` already returns existing dirs only,
  and an explicit `--tasks-dir` that doesn't exist should note once).
- `build_by_task(tasks, agent_events, output_map, main_transcript, whole_cost, pricing) ->
  by_task` — the D3–D6 assembly. Join: drop events naming an id not in
  `{t["id"] for t in tasks}` with an `agent line for unknown task id <id> ignored` note.
  Group: an agent id referenced by MORE THAN ONE distinct known task → a cluster; else it
  belongs to its single task's role bucket. Price: each referenced output file and each
  unattributed file with ONE `sc.collect([str(path)], pricing)` per file — cost =
  `sum(b["cost"] for b in data["by_model"].values())`; `files_read == 0` → cost `None` +
  note; a referenced agent id absent from `output_map` → cost `None` + a note naming the id
  (the session-scoped tmp may have been cleaned — expected, not an error). The main
  transcript (may be `None`) prices the same standalone way → `orchestrator: {"cost_usd":
  float|None}` (+ note when None). Unattributed = files in `output_map` referenced by NO
  kept event → `{"count", "cost_usd" (sum of priced, None when none priced or count 0),
  "agent_ids" (sorted)}` — on the zero-events rung do NOT enumerate output files at all
  (PLAN D6: that would be a de-facto breakdown). Task rows per PLAN D4 (`{"id", "roles",
  "total_usd", "missing_agents", "shared_agent_ids"}`, TASKS.md order, roles only when
  populated, sums over PRICED agents only, `None` never `0` for unknown); cluster rows per
  PLAN D5 (`{"agent_id", "task_ids" (TASKS.md order), "roles" (sorted unique), "cost_usd"}`,
  ordered by first task position). Coverage: `"full"` iff ≥1 kept event AND every referenced
  agent id priced AND the main transcript priced; `"partial"` when ≥1 kept event otherwise;
  `None` with zero kept events (+ the `no agent: lines recorded — per-task dollars n/a`
  note). Reconciliation: when `whole_cost` is not None, compare
  `orchestrator + Σ task-agent costs + Σ cluster costs + unattributed` against
  `whole_cost["actual_usd"]`; differ by more than half a cent → append ONE note explaining
  the two causes (message ids shared across transcripts count once in the session total but
  per-transcript in the breakdown; `--include`d transcripts are outside the attribution) —
  a note, NEVER an adjustment of any figure. Returns the pinned key set
  `{"schema_version", "coverage", "tasks", "clusters", "orchestrator", "unattributed",
  "notes"}` — by-task notes stay NESTED here.
- `render_by_task_lines(bt) -> list[str]` — the PLAN D7 markdown: H2 `## Per-task dollars`;
  on the zero-events rung exactly the sentence `n/a — no agent: lines recorded in NOTES.md
  (the /execute agent ledger); the whole-kit dollars above are unaffected.`; otherwise the
  table `| Task | Implementer $ | Verifier $ | Escalation $ | Total $ |` (cells: `$x.xx`
  subtotals, `—` absent role, `n/a` present-but-unpriced role or total; `*` suffix on the
  Task cell for rows with `shared_agent_ids`, footnoted `\* also served by a shared warm
  agent — see the cluster line; the shared transcript is not split into this row.`); one
  bullet per cluster: ``shared warm agent `<agent-id>` across <id>, <id> (<roles>): $X (not
  split)`` (or `n/a (transcript missing)`); the orchestrator bullet `orchestrator (main
  session): $Y — interleaved across all tasks; never split per task` (or `n/a (main
  transcript not found)`); the unattributed bullet `unattributed subagents (phase reviewers,
  scouts, unrecorded dispatches): <n> transcript(s), $Z` (only when count > 0); the coverage
  bullet `coverage: <full|partial> (<n>/<m> recorded agent transcripts priced)`; then the
  nested notes as `- <note>` lines.

**Render hook (pinned, the ONLY `render_markdown` change):** between the Dollars block and
the Notes block insert exactly one guarded block —
`if card.get("by_task") is not None: out.extend(render_by_task_lines(card["by_task"]))`
(an empty separator line before the H2 is fine — match the existing section spacing). Old
cards never carry the key, so every existing output is byte-identical. Do NOT touch
`MD_H2S`, `build_scorecard`, or any existing function's signature.

**CLI wiring (pinned):** new argparse flag `--by-task` (store_true; help: per-task dollar
breakdown from NOTES.md `agent:` lines — requires `--session`). Rejections, inserted AFTER
the existing `--history` guardrails and BEFORE the `--demo` block:
`--by-task` + `--live` → `sys.exit("--live takes no --by-task")`;
`--by-task` + `--history` → `sys.exit("--history takes no --by-task — per-task dollars are
per-session")`; `--by-task` + `--no-subagents` → `sys.exit("--by-task needs subagent
transcripts — drop --no-subagents")`; `--by-task` without `--session` and without `--demo` →
`sys.exit("--by-task requires --session — per-task dollars attribute one session's
transcripts")`. In the `--demo` block, `--demo --by-task` dispatches
`run_by_task_demo(args.json)` (the `--demo --live --by-task` combo already dies on the
earlier rejection). In the plain path, AFTER the existing `session_cost_summary` block and
AFTER `card = build_scorecard(...)`: `if args.by_task:` → re-read NOTES.md if it exists (a
SECOND `read_text` — leave the existing read untouched; missing NOTES.md → empty text) →
`parse_agents` → `task_dirs = args.tasks_dir or sc.discover_task_dirs(args.session)` →
`discover_agent_outputs(task_dirs)` → `build_by_task(tasks, events, output_map,
<the session's main transcript or None>, cost, pricing)` → `card["by_task"] = bt`. For the
main transcript reuse `sc.find_main_transcript(args.session, args.projects_dir)` (cheap
rglob; `session_cost_summary` doesn't return the path — calling it again is fine and keeps
the existing function untouched). `--include` stays a whole-session affordance (feeds the
Dollars block as today; attribution reads task dirs only). Print via the existing
markdown/JSON lines — no other changes. `return 0` on every degraded shape. Non-by-task
paths behave byte-identically to today.

**Demo (pinned — PLAN D9):** `run_by_task_demo(as_json)` builds, in ONE
`tempfile.TemporaryDirectory`: the kit dir with `DEMO_BYTASK_TASKS_MD` (P1 haiku done, P2
sonnet done, P3 sonnet done, P4 sonnet done, P5 sonnet done — spaced em-dash headings,
`- status:`/`- model:` lines) and `DEMO_BYTASK_NOTES_MD` (outcome lines P1–P5: P1
`model=haiku result=pass review=clean`, P2 `model=fable attempts=3 result=escalated-pass
review=clean`, P3/P4/P5 `model=sonnet result=pass review=clean`; then the agent ledger and
one malformed line, all exactly as PLAN D9 pins them — including
`agent: P3 id=ag-warm role=implementer model=sonnet` +
`agent: P4 id=ag-warm role=implementer model=sonnet` (the shared warm agent),
`agent: P5 id=ag-ghost role=implementer model=sonnet` (the missing transcript), and
`agent: P9 id=ag-bad role=chef model=sonnet` (skipped + note)); the
`projects/-demo/per-task-demo.jsonl` main transcript (one message per tier, ids
`demo-bt-main-<tier>`, model ids via `_first_model_of_tier(pricing, tier)` with the
`if model_id is None: continue` guard, volumes from the existing `DEMO_VOLUMES`); and a
`tasks/` dir with one single-message `<agent-id>.output` per PLAN D9 agent (ids
`demo-bt-<agent-id>`, tier + token volumes from `DEMO_BYTASK_VOLUMES`, model ids computed),
plus `ag-reviewer.output` (referenced by no line) and NO `ag-ghost.output`. Then
`main([str(kit_dir), "--session", "per-task-demo", "--projects-dir", str(tmp / "projects"),
"--tasks-dir", str(tmp / "tasks"), "--by-task"] + (["--json"] if as_json else []))` — the
`run_live_demo` pattern; the explicit `--tasks-dir` keeps it hermetic (no tmp discovery).
Expected card (the verify asserts): task ids exactly `[P1, P2, P3, P4, P5]`; P1 roles
{implementer 1 agent, verifier 1}, total > 0, empty missing/shared; P2 implementer 2 agents
+ escalation 1, total > 0; P3 `shared_agent_ids == ["ag-warm"]`, no roles, total None; P4
`shared_agent_ids == ["ag-warm"]`, verifier subtotal > 0, total > 0; P5 `missing_agents ==
["ag-ghost"]`, total None; exactly one cluster {ag-warm, [P3, P4], [implementer],
cost > 0}; orchestrator cost > 0; unattributed {count 1, ["ag-reviewer"], cost > 0};
coverage "partial"; notes include one naming `ag-ghost` and one `unrecognized agent line`;
whole-card Dollars still present (`actual_usd > 0`) and quality `with_outcome == 5`;
markdown contains the pinned phrases. Dollar VALUES computed from pricing.json at run time —
structure and relationships asserted, values NOT pinned.

GOTCHAS: zero `Path.home()` (borrow the argparse defaults already present); no real model
ids (tier names + the `fable` alias + computed demo ids only); `parse_tasks` needs the
spaced em dash in demo headings; `None` (never 0) for every unknown figure; task rows sum
PRICED agents only; the shared agent must appear in NO task row's roles/total; the
zero-events rung must not enumerate output files; `MD_H2S` untouched; by-task notes nested,
top-level card `notes` untouched by the flag.

**Acceptance.**
- `python3 bin/routing_scorecard.py --demo --json` still yields the Tier-1 pinned numbers
  (quality 6/6/3/1/1/1, mix {haiku 1, sonnet 4, fable 1}, survival 0.75);
  `--demo --live --json` the Tier-2 pinned numbers (one sonnet→opus rec for L5+L6, budget
  0/2/2, autonomy advisory); `--demo --history --json` the routing-history pinned numbers
  (haiku (3,3,2,1,0,0), sonnet (6,5,2,1,1,1), opus (2,1,1,0,0,0), frontier (1,0,0,0,0,0),
  reroutes {1,0,1}, coverage "partial") — additive proof for all three.
- `python3 bin/routing_scorecard.py --demo --by-task [--json]` prints the pinned card; the
  JSON `by_task` has exactly the D7 key set and the D9 numbers/relationships.
- The pinned pure functions exist and behave; `--by-task` rejects missing `--session`,
  `--live`, `--history`, and `--no-subagents`; a `--session` run WITHOUT `--by-task` yields
  a card with NO `by_task` key and markdown without `## Per-task dollars`.
- Greps: no `Path.home()`, no `sqlite`, no real model ids in the file; the three frozen test
  files, the reused scripts, `data/`, and `skills/architect/SKILL.md` unchanged; full suite
  + sync check green.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/routing_scorecard.py --demo --by-task && python3 - <<'PY' && ! grep -n 'Path.home()' bin/routing_scorecard.py && ! grep -n 'sqlite' bin/routing_scorecard.py && ! grep -nE 'claude-(fable|opus|sonnet|haiku)' bin/routing_scorecard.py && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py tests/test_routing_history.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data skills/architect && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T1 OK'
import importlib.util, json, subprocess, sys, tempfile
from pathlib import Path
# --- Tier-1 additive regression ---
j = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--json"], capture_output=True, text=True)
assert j.returncode == 0, j.stderr
c = json.loads(j.stdout)
q = c["quality"]
assert (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"], q["escalated_pass"], q["blocked"]) == (6, 6, 3, 1, 1, 1), q
assert c["model_mix"] == {"haiku": 1, "sonnet": 4, "fable": 1}, c["model_mix"]
assert abs(c["review"]["survival_rate"] - 0.75) < 1e-9, c["review"]
assert "by_task" not in c, "flag-off card must not carry by_task"
# --- Tier-2 additive regression ---
l = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--live", "--json"], capture_output=True, text=True)
assert l.returncode == 0, l.stderr
d = json.loads(l.stdout)
assert d["autonomy"] == "advisory" and d["budget"] == {"cap": 2, "applied": 0, "remaining": 2}, d
recs = d["recommendations"]
assert len(recs) == 1 and (recs[0]["from"], recs[0]["to"], recs[0]["task_ids"]) == ("sonnet", "opus", ["L5", "L6"]), recs
# --- routing-history additive regression ---
h = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--history", "--json"], capture_output=True, text=True)
assert h.returncode == 0, h.stderr
hc = json.loads(h.stdout)
K = ("pinned", "with_outcome", "first_try", "retry_pass", "escalated_pass", "blocked")
pick = lambda tier: tuple(hc["tiers"][tier][k] for k in K)
assert pick("haiku") == (3, 3, 2, 1, 0, 0) and pick("sonnet") == (6, 5, 2, 1, 1, 1), hc["tiers"]
assert pick("opus") == (2, 1, 1, 0, 0, 0) and pick("frontier") == (1, 0, 0, 0, 0, 0), hc["tiers"]
assert hc["reroutes"] == {"events": 1, "applied": 0, "advisory": 1}
assert hc["dollars"]["coverage"] == "partial"
# --- the by-task demo: pinned D9 card ---
b = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--by-task", "--json"], capture_output=True, text=True)
assert b.returncode == 0, b.stderr
card = json.loads(b.stdout)
bt = card["by_task"]
assert set(bt) == {"schema_version", "coverage", "tasks", "clusters", "orchestrator", "unattributed", "notes"}, set(bt)
assert bt["schema_version"] == 1 and bt["coverage"] == "partial"
rows = {r["id"]: r for r in bt["tasks"]}
assert list(rows) == ["P1", "P2", "P3", "P4", "P5"], list(rows)
p1 = rows["P1"]
assert set(p1["roles"]) == {"implementer", "verifier"} and p1["total_usd"] > 0
assert len(p1["roles"]["implementer"]["agents"]) == 1 and len(p1["roles"]["verifier"]["agents"]) == 1
assert p1["missing_agents"] == [] and p1["shared_agent_ids"] == []
p2 = rows["P2"]
assert len(p2["roles"]["implementer"]["agents"]) == 2 and len(p2["roles"]["escalation"]["agents"]) == 1
assert p2["total_usd"] > 0
p3 = rows["P3"]
assert p3["shared_agent_ids"] == ["ag-warm"] and p3["roles"] == {} and p3["total_usd"] is None
p4 = rows["P4"]
assert p4["shared_agent_ids"] == ["ag-warm"] and p4["roles"]["verifier"]["subtotal_usd"] > 0 and p4["total_usd"] > 0
p5 = rows["P5"]
assert p5["missing_agents"] == ["ag-ghost"] and p5["total_usd"] is None
cl = bt["clusters"]
assert len(cl) == 1 and cl[0]["agent_id"] == "ag-warm" and cl[0]["task_ids"] == ["P3", "P4"], cl
assert cl[0]["roles"] == ["implementer"] and cl[0]["cost_usd"] > 0
assert bt["orchestrator"]["cost_usd"] > 0
ua = bt["unattributed"]
assert (ua["count"], ua["agent_ids"]) == (1, ["ag-reviewer"]) and ua["cost_usd"] > 0
assert any("ag-ghost" in n for n in bt["notes"]), bt["notes"]
assert any("unrecognized agent line" in n for n in bt["notes"]), bt["notes"]
assert card["cost"] and card["cost"]["actual_usd"] > 0
assert card["quality"]["with_outcome"] == 5
m = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--by-task"], capture_output=True, text=True)
assert m.returncode == 0, m.stderr
for needle in ("## Per-task dollars", "not split", "never split per task",
               "unattributed subagents", "coverage: partial", "ag-warm", "## Dollars"):
    assert needle in m.stdout, f"markdown missing: {needle!r}\n{m.stdout}"
i_dol = m.stdout.index("## Dollars"); i_bt = m.stdout.index("## Per-task dollars")
assert i_bt > i_dol, "by-task section must follow the Dollars section"
# --- pure surface ---
spec = importlib.util.spec_from_file_location("routing_scorecard", Path("bin/routing_scorecard.py").resolve())
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
assert rs.BYTASK_SCHEMA_VERSION == 1
assert rs.AGENT_ROLES == ("implementer", "verifier", "escalation")
for fn in ("parse_agents", "discover_agent_outputs", "build_by_task",
           "render_by_task_lines", "run_by_task_demo"):
    assert callable(getattr(rs, fn)), fn
ev, notes = rs.parse_agents("agent: T1 id=a1 role=implementer model=sonnet\n- agent: T1 id=a2 role=verifier\nagent: T2 id=a1 role=implementer model=sonnet\nagent: T3 id=a3 role=chef\nagent: T4 role=implementer\n")
assert [(e["task"], e["agent_id"], e["role"]) for e in ev] == [("T1", "a1", "implementer"), ("T1", "a2", "verifier"), ("T2", "a1", "implementer")], ev
assert ev[1]["model"] is None
assert len(notes) == 2, notes
# last-wins on a repeated (task, agent) pair
ev2, _ = rs.parse_agents("agent: T1 id=a1 role=implementer model=sonnet\nagent: T1 id=a1 role=implementer model=opus\n")
assert len(ev2) == 1 and ev2[0]["model"] == "opus", ev2
# family disjointness
assert rs.parse_outcomes("agent: T1 id=a1 role=implementer model=sonnet\n")[0] == {}
assert rs.parse_reroutes("agent: T1 id=a1 role=implementer model=sonnet\n")[0] == []
assert rs.parse_sessions("agent: T1 id=a1 role=implementer model=sonnet\n")[0] == []
assert rs.parse_agents("outcome: T1 model=sonnet result=pass\nreroute: sonnet to=opus mode=advisory\nsession: abc\n")[0] == []
assert rs.MD_H2S == ("## Verdict", "## Task outcomes", "## Model mix", "## Review survival", "## Dollars"), "MD_H2S must stay frozen"
# --- CLI guardrails ---
for argv, why in ((["fusion-tier1", "--by-task"], "missing --session"),
                  (["fusion-tier1", "--by-task", "--session", "x", "--live"], "--live"),
                  (["--history", "--by-task"], "--history"),
                  (["fusion-tier1", "--by-task", "--session", "x", "--no-subagents"], "--no-subagents")):
    r = subprocess.run([sys.executable, "bin/routing_scorecard.py"] + argv, capture_output=True, text=True)
    assert r.returncode != 0, f"--by-task must reject {why}"
# --- degradation: no agent: lines -> n/a section, whole-kit dollars unaffected ---
with tempfile.TemporaryDirectory() as tmp:
    kd = Path(tmp) / "kits" / "solo"; kd.mkdir(parents=True)
    (kd / "TASKS.md").write_text("# T\n\n## Phase 1 — p\n\n### S1 — a\n- status: done\n- model: sonnet\n")
    (kd / "NOTES.md").write_text("outcome: S1 model=sonnet attempts=1 result=pass review=clean\n")
    pd = Path(tmp) / "projects" / "-t"; pd.mkdir(parents=True)
    prices = json.loads(Path("data/pricing.json").read_text())
    mid = next(k for k, v in prices["models"].items() if v.get("tier") == "sonnet")
    (pd / "solo-sess.jsonl").write_text(json.dumps({"timestamp": "2026-07-01T12:00:00+00:00", "message": {"model": mid, "id": "m1", "usage": {"input_tokens": 1000, "output_tokens": 100}}}) + "\n")
    td = Path(tmp) / "tasks"; td.mkdir()
    r = subprocess.run([sys.executable, "bin/routing_scorecard.py", str(kd), "--session", "solo-sess",
                        "--projects-dir", str(Path(tmp) / "projects"), "--tasks-dir", str(td),
                        "--by-task", "--json"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    g = json.loads(r.stdout)
    assert g["by_task"]["coverage"] is None and g["by_task"]["tasks"] == [] and g["by_task"]["clusters"] == []
    assert g["by_task"]["orchestrator"]["cost_usd"] is None
    assert g["by_task"]["unattributed"] == {"count": 0, "cost_usd": None, "agent_ids": []}
    assert any("no agent: lines recorded" in n for n in g["by_task"]["notes"])
    assert g["cost"] and g["cost"]["actual_usd"] > 0, "whole-kit dollars must be unaffected"
    # and WITHOUT the flag: no by_task key, no section
    r2 = subprocess.run([sys.executable, "bin/routing_scorecard.py", str(kd), "--session", "solo-sess",
                         "--projects-dir", str(Path(tmp) / "projects"), "--json"], capture_output=True, text=True)
    assert r2.returncode == 0 and "by_task" not in json.loads(r2.stdout)
    r3 = subprocess.run([sys.executable, "bin/routing_scorecard.py", str(kd), "--session", "solo-sess",
                         "--projects-dir", str(Path(tmp) / "projects")], capture_output=True, text=True)
    assert "## Per-task dollars" not in r3.stdout
print("T1 by-task checks ok")
PY
```

---

### T2 — Regression tests (tests/test_per_task_dollars.py)
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Create `tests/test_per_task_dollars.py`, stdlib `unittest`, loading
`bin/routing_scorecard.py` via the importlib convention off
`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` (copy the header pattern and
module-docstring safety contract from `tests/test_routing_history.py`: no test reads the real
Claude project store or calls the stdlib home helper; every fixture lives in a fresh
`tempfile.TemporaryDirectory()` handed over via `--kits-dir`/`--projects-dir`/`--tasks-dir`
or explicit paths; synthetic ids/values only, tier vocabulary + the `fable` alias as the only
model tokens EXCEPT ids computed at run time from `rs.cr.load_pricing()` +
`rs._first_model_of_tier` for the dollar fixtures — never a spelled model id). Do NOT edit
`tests/test_routing_scorecard.py`, `tests/test_reroute_live.py`, or
`tests/test_routing_history.py` — this is a new file.

Helpers: a `write_kit(kits_root, name, tasks_md, notes_md=None)` fixture writer (spaced
em-dash headings, `- status:`/`- model:` lines, pinned `outcome:`/`agent:` grammars); a
`write_transcript(path, messages)` writer emitting
`{"timestamp", "message": {"model", "id", "usage": {"input_tokens", "output_tokens"}}}`
JSONL lines (used both for `projects/<slug>/<session>.jsonl` mains and for
`tasks/<agent-id>.output` files — same shape); and a `price_of(files)` helper that computes a
reference price via `rs.sc.collect([...], pricing)` (the reused pipeline — the tests compare
against IT, never against hand-computed dollars).

Minimum cases — include these EXACT method names (greps in the verify key on them), plus
whatever else you need:

1. `test_parse_agents_happy_and_tolerant` — happy path; leading `- `/`* ` bullets; unknown
   `key=value` pairs ignored; missing `id=` or a role outside
   `("implementer", "verifier", "escalation")` → line skipped + note; `model=` absent →
   `None`, no validation; events in file order.
2. `test_parse_agents_last_wins_per_pair` — a repeated (task-id, agent-id) pair keeps only
   the LAST line's values; distinct agent ids on the same task all survive (the
   retry/verifier/escalation case: several lines, one task).
3. `test_parser_family_disjoint` — a NOTES.md containing all FOUR line formats: each of
   `parse_outcomes`/`parse_reroutes`/`parse_sessions` sees no `agent:` lines, and
   `parse_agents` sees none of theirs (the contract-safety proof).
4. `test_discover_agent_outputs_stem_mapping` — `*.output` stems become agent ids; sorted
   deterministic; a duplicate stem across two dirs keeps the first + note.
5. `test_by_task_prices_each_output_standalone` — synthetic outputs with distinct
   tiers/volumes: each agent's `cost_usd` equals the reused pipeline's single-file price
   (via `price_of`, within 1e-9); role subtotals and task totals are sums of their PRICED
   agents.
6. `test_missing_transcript_null_never_zero` — an `agent:` line with no `*.output` → that
   agent `cost_usd` None; a task whose ONLY agent is missing → `total_usd` None (never 0.0);
   a note names the id; coverage `partial`; no `0.0` stand-in anywhere in the by-task JSON.
7. `test_shared_warm_agent_not_split` — one transcript, same agent id on two tasks: exactly
   one cluster row carrying the FULL single-file price; NEITHER task row includes any share
   of it (`shared_agent_ids` set, roles/total exclude it); the sum
   orchestrator + task agents + cluster + unattributed equals the sum of all standalone
   file prices (within 1e-9) — nothing lost, nothing divided.
8. `test_orchestrator_never_split` — the main transcript's price appears ONLY in
   `orchestrator.cost_usd`; no task row or cluster row contains it; with the main transcript
   absent from the projects dir the field is None + note (and the whole-kit Dollars block
   degrades exactly as it does today, unchanged by the flag).
9. `test_unattributed_and_unknown_task_lines` — a `*.output` referenced by no line lands in
   `unattributed` (count/ids/cost), never on a task; an `agent:` line naming an unknown task
   id is dropped with a note and its transcript (referenced by no known task) lands in
   `unattributed`.
10. `test_no_agent_lines_degrades_na` — kit with outcomes but zero `agent:` lines →
    `coverage` None, empty tasks/clusters, unattributed count 0 WITHOUT enumerating the
    output files present in the tasks dir, the `no agent: lines recorded` note, markdown
    carrying the pinned n/a sentence — and the whole-kit `cost` block untouched.
11. `test_reconciliation_note_on_overlap` — a message id duplicated between the main
    transcript and one agent's `*.output`: the whole-session `cost.actual_usd` counts it
    ONCE (global dedupe) while the breakdown prices it per-transcript; the parts-vs-whole
    difference produces the reconciliation NOTE and no figure is adjusted.
12. `test_cli_by_task_requires_session_and_rejections` — `--by-task` without `--session`,
    `--by-task --live --session x`, `--history --by-task`, and
    `--by-task --session x --no-subagents` each exit nonzero with a message naming the
    offender.
13. `test_without_flag_byte_stable_shape` — the same fixture run WITHOUT `--by-task`: JSON
    top-level keys exactly `{schema_version, kit, generated_at, tasks, quality, model_mix,
    review, cost, notes}` (no `by_task`), markdown contains exactly the five pre-existing
    H2s and NOT `## Per-task dollars`; top-level `notes` contain no agent-related note.
14. `test_by_task_json_shape` — with the flag: `by_task` key set exactly
    `{schema_version, coverage, tasks, clusters, orchestrator, unattributed, notes}`; task
    row key set `{id, roles, total_usd, missing_agents, shared_agent_ids}`; cluster row key
    set `{agent_id, task_ids, roles, cost_usd}`.
15. `test_demo_by_task_pinned_shape` — `--demo --by-task --json` via subprocess: the T1
    pinned D9 expectations (task ids, P3/P5 nulls, the ag-warm cluster, unattributed
    ag-reviewer, coverage partial); `--demo --by-task` markdown contains the pinned
    phrases (`## Per-task dollars`, `not split`, `never split per task`,
    `coverage: partial`).
16. `test_prior_demos_regression` — `--demo --json` still yields the Tier-1 pinned numbers,
    `--demo --live --json` the Tier-2 pinned numbers, AND `--demo --history --json` the
    routing-history pinned tier tuples/reroutes/coverage (additive proof for all three
    prior modes).
17. `test_readonly_by_task_run` — byte-snapshot the temp kit dir, projects dir, AND tasks
    dir before/after a full `--by-task` CLI run — identical (`--by-task` never writes; the
    `agent:` line is orchestrator-owned).

**Acceptance.** All new tests pass; full suite green; the three frozen test files, the
reused scripts, and `skills/architect/SKILL.md` untouched; safety greps clean; only this
file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_per_task_dollars.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py tests/test_routing_history.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data skills/architect && echo 'T2 OK'
import re
text = open('tests/test_per_task_dollars.py').read()
assert 'Path.home()' not in text
assert '~/.claude' not in text, "real home path in tests"
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
for name in ('test_parse_agents_happy_and_tolerant', 'test_parse_agents_last_wins_per_pair',
             'test_parser_family_disjoint', 'test_discover_agent_outputs_stem_mapping',
             'test_by_task_prices_each_output_standalone', 'test_missing_transcript_null_never_zero',
             'test_shared_warm_agent_not_split', 'test_orchestrator_never_split',
             'test_unattributed_and_unknown_task_lines', 'test_no_agent_lines_degrades_na',
             'test_reconciliation_note_on_overlap', 'test_cli_by_task_requires_session_and_rejections',
             'test_without_flag_byte_stable_shape', 'test_by_task_json_shape',
             'test_demo_by_task_pinned_shape', 'test_prior_demos_regression',
             'test_readonly_by_task_run'):
    assert f'def {name}' in text, f"missing case: {name}"
assert '--projects-dir' in text and '--tasks-dir' in text and '--by-task' in text
print('safety greps ok')
PY
```

---

*Phase 1 end — dispatch `per-task-dollars-reviewer` before starting Phase 2.*

---

## Phase 2 — The skill (the contract-sensitive phase)

### T3 — Teach /execute the agent ledger (two pinned edits)
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Per PLAN.md D2/D8. TWO pinned edits in `skills/execute/SKILL.md`, BODY only
(frontmatter untouched — the plugin is live). If either anchor below is not found verbatim,
STOP and report. Touch NOTHING else — in particular not `skills/architect/SKILL.md` (this
kit never edits it) and not the Setup/lean-driver/loop/dispatch-modes/outcome-ledger/
live-re-routing/escalation-valve sections beyond the pinned insertions.

*Edit 1 — the new section.* Insert the following block, followed by a blank line,
immediately BEFORE the exact heading line:

```
## Live re-routing — upgrade-only, autonomy-gated
```

Inserted block (verbatim):

```
## Agent ledger — one line per per-task subagent

Per-task dollar attribution rides on knowing which subagent transcript served which task. The moment any per-task dispatch returns — the implementer (step 2), a retry, the verifier (step 3), or the Fable escalation consult — append ONE machine-readable line to NOTES.md recording the agent id the Agent tool reported:

    agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation> model=<model>

- `id` — the agent id from the Agent tool's result. The subagent's transcript is the `<agent-id>.output` file in the session's tasks scratch dir — the file `--by-task` prices.
- `role` — exactly one of `implementer` (retries included — each retry dispatch appends its own line with its own agent id) | `verifier` | `escalation` (the Fable consult).
- `model` — the alias the dispatch actually ran on: the task's pin, an applied re-route's upgraded alias, or the escalation target.
- A warm sidekick serving a cluster gets one line PER TASK it serves, all carrying the SAME agent id — the shared id is what lets the scorecard attribute the one shared transcript to the cluster as a unit instead of faking a per-task split.
- Do NOT record phase reviewers or ad-hoc scouts: they are per-phase/per-run, not per-task, and their transcripts deliberately land in the breakdown's unattributed line — never split per task.
- The line is OPTIONAL and execute-owned (precedent: `outcome:`/`reroute:`/`session:` — a NOTES.md line format, not a task field). Unknown `key=value` pairs are ignored, a repeated task-id + agent-id pair takes the LAST line, and a kit with no `agent:` lines simply degrades to whole-kit dollars — never record a guessed agent id.
```

*Edit 2 — the End-of-run offer.* Replace the exact fragment (currently the end of the final
End-of-run sentence):

```
and the cross-kit track record: `python3 bin/routing_scorecard.py --history` (per-tier quality across every kit, plus aggregate dollars over the kits that carry a `session:` line).
```

with:

```
and the cross-kit track record: `python3 bin/routing_scorecard.py --history` (per-tier quality across every kit, plus aggregate dollars over the kits that carry a `session:` line), and — when this run recorded `agent:` lines — the per-task dollar breakdown: `python3 bin/routing_scorecard.py <slug> --session <session-id> --by-task` (delegated cost per task by role — implementer/verifier/escalation; a warm cluster's shared transcript is attributed to the cluster as a unit, and the orchestrator's own share is one un-split line, never divided per task).
```

The `agent:` grammar in the new text must match `AGENT_RE`/`AGENT_ROLES` in
`bin/routing_scorecard.py` — it does by construction; the verify confirms via the parser.

**Acceptance.** Both edits landed exactly once; section order is Setup → Operating rule →
The loop → Dispatch modes → Outcome ledger → Agent ledger → Live re-routing → Escalation
valve → End of run; every pre-existing contract element intact (verify's grep list); the
agent line described as OPTIONAL, execute-owned, recorded at dispatch return, never guessed;
phase reviewers/scouts explicitly excluded; frontmatter untouched;
`skills/architect/SKILL.md` untouched; suite + sync green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && git diff --quiet -- skills/architect && echo 'T3 OK'
t = open('skills/execute/SKILL.md').read()
assert t.startswith('---\nname: execute\n'), "frontmatter touched"
# --- Tier-1 + Tier-2 + Tier-3 contract elements: all must survive ---
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
    "session: <session-id>", "never record a guessed id",
    "python3 bin/routing_scorecard.py --history",
]:
    assert s in t, f"contract element lost: {s!r}"
# --- agent-ledger elements: present exactly once where counted ---
assert t.count("agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation> model=<model>") == 1, "agent grammar missing/duplicated"
assert t.count("## Agent ledger — one line per per-task subagent") == 1
for s in [
    "The moment any per-task dispatch returns",
    "Do NOT record phase reviewers or ad-hoc scouts",
    "attribute the one shared transcript to the cluster as a unit",
    "never record a guessed agent id",
    "per-task dollar breakdown",
    "--session <session-id> --by-task",
    "the orchestrator's own share is one un-split line, never divided per task",
]:
    assert s in t, f"agent-ledger element missing: {s!r}"
assert t.count("--by-task") == 2, "expected exactly two --by-task mentions (section + end-of-run)"
assert t.count("per-task dollar breakdown") == 1
order = ["## Setup", "## Operating rule — lean driver", "## The loop",
         "## Dispatch modes — fresh fan-out vs warm sidekick",
         "## Outcome ledger — one line per finished task",
         "## Agent ledger — one line per per-task subagent",
         "## Live re-routing — upgrade-only, autonomy-gated",
         "## Escalation valve", "## End of run"]
idx = [t.index(h) for h in order]
assert idx == sorted(idx), "section order wrong"
# --- the documented grammar parses with the shipped parser ---
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("routing_scorecard", Path("bin/routing_scorecard.py").resolve())
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
ev, _ = rs.parse_agents("agent: T1 id=sample-agent role=implementer model=sonnet\n")
assert [(e["task"], e["agent_id"], e["role"], e["model"]) for e in ev] == [("T1", "sample-agent", "implementer", "sonnet")], "AGENT_RE does not accept the skill's documented grammar"
print("T3 structural checks ok")
PY
```

---

### T4 — Dual-file contract audit (architect deliberately unchanged)
- status: done
- model: opus
- depends: T3
- independent: no

**Brief.** Per PLAN.md D8 and the CLAUDE.md invariant ("if you touch either skill you MUST
re-check both"). This task makes NO edit — it AUDITS. This kit's design keeps
`skills/architect/SKILL.md` untouched (the agent ledger is execute-runtime mechanics; the
architect's NOTES.md bullet names only the `outcome:` line and was never extended for
`reroute:`/`session:` either — the same precedent applies). Your job: prove BOTH skills still
express the full shared contract, prove architect is byte-unchanged, and READ the edited
execute sections for SEMANTIC drift beyond what greps catch — the `agent:` line must be
OPTIONAL and execute-owned (never a required field, never a TASKS.md marker); recording must
happen at dispatch return, never guessed; phase reviewers/scouts must be excluded from
recording; the warm-cluster text must attribute the shared transcript to the cluster as a
unit (no text anywhere may describe splitting it, splitting the main session per task, or
any estimated division); no text may weaken the model-override rule, the Tier-2
runtime-override clause, the upgrade-only/never-frontier re-routing, the advisory default,
or the escalation valve. If ANY element is missing or contradicted, STOP and report — that
is a T1/T3 defect to fix via the orchestrator, not something to patch ad hoc here.

**Acceptance.** The dual-file grep audit passes; `git diff --quiet -- skills/architect`
clean (byte-unchanged); both frontmatters intact; no auto-anything or split-the-overhead
language anywhere in either skill; suite + sync green; your report states the semantic-drift
reading was done and what it found.

**Verify.**
```bash
cd /path/to/polytropos && git diff --quiet -- skills/architect && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py tests/test_routing_history.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && echo 'T4 OK'
a = open('skills/architect/SKILL.md').read()
e = open('skills/execute/SKILL.md').read()
assert a.startswith('---\nname: architect\n'), "architect frontmatter touched"
assert e.startswith('---\nname: execute\n'), "execute frontmatter touched"
# --- architect contract elements (Tier-1 + Tier-2 + Tier-3 lists, all must survive) ---
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
assert a.count("**Consult the routing history when choosing the initial `model` pins:**") == 1, "tier-3 history bullet lost/duplicated"
assert "not an auto-pin-setter" in a and "the architect weighs it and decides" in a
assert "agent:" not in a, "architect must not gain agent-ledger text (this kit leaves it untouched; zero 'agent:' occurrences today)"
# --- execute contract elements (full final state, incl. T3's additions) ---
for s in [
    "## Setup", "## Operating rule — lean driver", "## The loop",
    "## Dispatch modes — fresh fan-out vs warm sidekick",
    "## Outcome ledger — one line per finished task",
    "## Agent ledger — one line per per-task subagent",
    "## Live re-routing — upgrade-only, autonomy-gated",
    "`in-progress` in TASKS.md", "mark `done`", "mark `blocked`",
    "skip `done`, stop at `blocked` deps",
    "passing the task's `model` value as the Agent tool's `model` parameter",
    "overrides the agent's frontmatter default", "Phase boundaries", "reviewer agent",
    "independent — one message, multiple Agent calls", "## Escalation valve",
    "`model: fable`", "## End of run",
    "outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>",
    "reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>",
    "agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation> model=<model>",
    "SAME `model` value", "always a fresh spawn",
    "runtime dispatch override, never a TASKS.md rewrite",
    "NEVER to frontier/Fable", "**advisory (the default)**",
    "session: <session-id>", "never record a guessed id",
    "python3 bin/routing_scorecard.py --history",
    "Do NOT record phase reviewers or ad-hoc scouts",
    "never record a guessed agent id",
    "--session <session-id> --by-task",
]:
    assert s in e, f"execute element lost: {s!r}"
# --- no auto-pin language anywhere; the never-split framing survives ---
for f, txt in (("architect", a), ("execute", e)):
    assert "auto-pin" not in txt.replace("not an auto-pin-setter", ""), f"auto-pin language in {f}"
assert "un-split line" in e and "never divided per task" in e
# --- grammar/parser consistency for all four execute-owned line formats ---
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("routing_scorecard", Path("bin/routing_scorecard.py").resolve())
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
assert rs.parse_agents("agent: T9 id=abc role=verifier model=haiku\n")[0][0]["role"] == "verifier"
assert rs.parse_outcomes("outcome: T9 model=haiku attempts=1 result=pass review=clean\n")[0]["T9"]["result"] == "pass"
assert rs.parse_sessions("session: sample-id-1\n")[0] == ["sample-id-1"]
print("dual-file contract audit ok")
PY
```

---

*Phase 2 end — dispatch `per-task-dollars-reviewer` before starting Phase 3.*

---

## Phase 3 — Documentation and guardrails

### T5 — Write docs/PER-TASK-DOLLARS.md and point ROUTING-HISTORY.md's deferral at it
- status: done
- model: sonnet
- depends: T4
- independent: yes

**Brief.** Two pieces.

*Piece 1* — new file `docs/PER-TASK-DOLLARS.md` documenting what this kit built and what it
deliberately did not. Match the tone/format of `docs/ROUTING-HISTORY.md` (H1 + H2 sections,
concrete commands, no prices, no real model ids — tier names and the `fable` alias are fine,
no `/private/tmp/` paths, name constants instead of restating their values as prose facts).
Required structure — H1 `# Per-task dollars — attributing delegated cost by task and role`,
then EXACTLY these five H2s in order:

1. `## The partition` — `session_cost` already separates a session into the MAIN transcript
   (the orchestrator/driver, interleaved across all tasks) and per-subagent `*.output`
   transcripts (one per dispatched agent, filename stem = agent id). Delegated cost is
   therefore cleanly attributable per task — each task's cost is the standalone price of
   the subagent transcript(s) that served it — while the orchestrator's own share is
   reported as ONE explicitly un-attributable line and is NEVER split per task (any split
   would be an estimate presented as a measurement). Phase reviewers and scouts are
   per-phase/per-run and deliberately land in an honest `unattributed subagents` line.
2. `## The agent: line` — the recorded datum: grammar verbatim
   `agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation> model=<model>` —
   a fourth OPTIONAL, execute-owned NOTES.md line (precedent: `outcome:`, `reroute:`,
   `session:`), appended by the `/execute` orchestrator the moment a per-task dispatch
   returns; retries and escalations each get their own line; a warm sidekick puts the SAME
   agent id on every task it serves; never a task field, never written by any script,
   `parse_tasks` unchanged.
3. `## Reading the breakdown` — usage:
   `python3 bin/routing_scorecard.py <slug> --session <id> --by-task` (+ `--json`,
   `--tasks-dir` when the scratch dir moved) and
   `python3 bin/routing_scorecard.py --demo --by-task` as the synthetic smoke. Describe the
   role table (implementer/verifier/escalation + total), the cluster lines
   (`shared warm agent … (not split)`), the orchestrator line, the unattributed line, the
   `coverage: full|partial` label, and the parts-vs-whole reconciliation note (shared
   message ids count once in the session total but per-transcript in the breakdown).
   `--by-task` requires `--session`; without the flag the scorecard output is byte-identical
   to before.
4. `## The honesty rules` — never split the main transcript; never divide a shared
   warm-cluster transcript (attributed to the cluster as a unit); a recorded agent id whose
   `*.output` is gone (the tasks scratch is session-scoped tmp) prices as null + note,
   never a zero or a guess; a per-task figure is only ever the sum of transcripts that
   actually exist; no `agent:` lines → the breakdown is n/a and the whole-kit dollars print
   unchanged; the reconciliation is a note, never an adjustment.
5. `## Deliberately not built` — estimated splitting of the orchestrator or a shared
   transcript (refused by design, not deferred); per-task dollars in `--history` (the
   cross-kit view stays per-kit — a possible future kit); auto-pin/auto-downgrade
   (unchanged, advisory by design); main-session model switching (still the upstream ask,
   tracked in `docs/FUSION-TIER1.md`).

*Piece 2* — in `docs/ROUTING-HISTORY.md`, append a new paragraph at the very end of the file
(the `## Deliberately not built` section currently ends with the line
`still tracked in `docs/FUSION-TIER1.md`.`). Append (blank line before it):

```
Per-task dollar attribution has since shipped — see
[PER-TASK-DOLLARS.md](PER-TASK-DOLLARS.md). The premise of the deferral bullet above still
holds for the orchestrator's own share (the main transcript is never split per task); what
changed is the data: the execute-owned NOTES.md `agent:` ledger records which subagent
transcript served which task, so DELEGATED cost is now measured per task — via `--by-task`
on the per-kit scorecard — with a warm cluster's shared transcript attributed to the
cluster as a unit, never divided.
```

Change nothing else in ROUTING-HISTORY.md — its five H2s and all prior text stay intact.

**Acceptance.** PER-TASK-DOLLARS.md exists with the H1 + exactly those five H2s in order;
the `agent:` grammar verbatim; mentions `--by-task`, `--demo --by-task`, `requires
--session`, coverage labeling, the not-split cluster rule, the never-split orchestrator
rule, and the n/a degradation; ROUTING-HISTORY.md gained exactly the pointer paragraph and
its H2 set is unchanged; greps clean; suite green; only PER-TASK-DOLLARS.md new.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T5 OK'
import re
t = open('docs/PER-TASK-DOLLARS.md').read()
assert t.lstrip().startswith('# Per-task dollars — attributing delegated cost by task and role')
h2s = [l for l in t.splitlines() if l.startswith('## ')]
assert h2s == ['## The partition', '## The agent: line', '## Reading the breakdown',
               '## The honesty rules', '## Deliberately not built'], h2s
assert 'agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation> model=<model>' in t
for s in ('--by-task', '--demo --by-task', '--session', 'coverage', 'not split',
          'never split', 'unattributed', 'routing_scorecard.py', 'n/a', 'cluster',
          'estimate presented as a measurement'):
    assert s in t, f'missing: {s}'
assert not re.search(r'claude-(fable|opus|sonnet|haiku)-?[0-9]', t), 'real model id in doc'
assert '/private/tmp' not in t
o = open('docs/ROUTING-HISTORY.md').read()
assert o.count('Per-task dollar attribution has since shipped') == 1, 'pointer missing/duplicated'
assert 'PER-TASK-DOLLARS.md' in o
h2s2 = [l for l in o.splitlines() if l.startswith('## ')]
assert h2s2 == ['## What it aggregates', '## Dollars — the optional session: line',
                '## Feeding the architect', '## Contract safety',
                '## Deliberately not built'], h2s2
print('doc structure ok')
PY
```

---

### T6 — Pinned CLAUDE.md run-line
- status: done
- model: haiku
- depends: T1
- independent: yes

**Brief.** ONE pinned insertion, nothing else. (The `For \`per-task-dollars\` specifically:`
fence paragraph already exists in CLAUDE.md — the architect added it; do not touch it.) If
the anchor is not found verbatim, STOP and report.

*Insertion — CLAUDE.md, "## How to run things" code block.* Immediately AFTER the line:

```
python3 bin/routing_scorecard.py --demo --history # cross-kit routing-history smoke (synthetic kits, dollars labeled partial)
```

insert this line into the same code block:

```
python3 bin/routing_scorecard.py --demo --by-task # per-task dollars smoke (synthetic kit; shared warm agent + missing transcript honesty proofs)
```

**Acceptance.** The insertion is present exactly once, directly after the `--demo --history`
line; the per-task-dollars fence paragraph is present exactly once (pre-existing); no other
CLAUDE.md line changed by this task; suite green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T6 OK'
c = open('CLAUDE.md').read()
line = 'python3 bin/routing_scorecard.py --demo --by-task # per-task dollars smoke (synthetic kit; shared warm agent + missing transcript honesty proofs)'
assert c.count(line) == 1, "run-line missing/duplicated"
i_hist = c.index('python3 bin/routing_scorecard.py --demo --history')
i_bt = c.index(line)
assert i_bt > i_hist and c[i_hist:i_bt].count('\n') == 1, "by-task line not directly after the --demo --history line"
assert c.count('For `per-task-dollars` specifically:') == 1, "fence paragraph missing/duplicated"
print('insertion ok')
PY
```

---

*Phase 3 end — dispatch `per-task-dollars-reviewer`, then run PLAN.md's overall done-check.*
