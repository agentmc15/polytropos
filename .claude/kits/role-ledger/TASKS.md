# TASKS — role-ledger

Repo root: `/path/to/polytropos`. Run every verify command
from there. Read `PLAN.md` and `GUARDRAILS.md` (same directory) first — D1–D8 and the
OUT-OF-SCOPE fence are binding; R1–R5 are the tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch notes for the orchestrator: pass each task's `model` as the Agent tool's `model`
parameter when dispatching `role-ledger-implementer`. **Warm-cluster candidates:**
T1 → T2 → T3 → T4 are strictly serial, all `sonnet`, and share one primary file
(`bin/routing_scorecard.py` + `tests/test_role_ledger.py`) — serve them with ONE warm
implementer (that is the ~4-task cap; start T5 fresh even though it continues the same
file). T6 → T7 are serial, both `opus`, sharing the skill contract — a second warm pair.
T8 fans out fresh. This kit is `autonomy: advisory`. This repo is NOT a git repo — no
verify clause may rely on `git`; every check is a content assertion.

Standing rules for every task:

- Never touch `bin/bench_routing.py`, `tests/test_bench_routing.py`, or
  `skills/bench-routing/SKILL.md` (concurrent agent — GUARDRAILS absolute rule; PLAN R1).
- `bin/routing_scorecard.py` changes are ADDITIVE: no existing function signature changes
  (`build_history(kits_dir, records, kit_costs, dollars, notes)` is called positionally by
  the untouchable bench file — new data rides inside `records`), no flag changes, no exit
  code changes, no edits to the Tier-1 `--demo`, `--demo --live`, or `--demo --by-task`
  numbers. Never re-implement `parse_outcomes`/`parse_reroutes`/`parse_sessions`/
  `parse_agents`/`tier_for` — extend or call them.
- Existing-file edits sanctioned by this kit, and ONLY these: `bin/routing_scorecard.py`
  (T1–T5), `tests/test_routing_history.py` (T4, T5), `tests/test_crossrepo_trend.py` (T4),
  `skills/execute/SKILL.md` (T6, body only), `skills/architect/SKILL.md` (T7, body only).
  New file: `tests/test_role_ledger.py` (T1, extended T2–T5). Anything else diffed is a
  defect. Never edit any kit's NOTES.md by hand (execute owns this kit's; the other 21 are
  frozen evidence — PLAN D5).
- No prices, price ratios, or real model ids hardcoded. Sanctioned structural vocabulary
  for this kit: `AGENT_RESULTS = ("accepted", "revised", "blocked")`, the two new line
  regexes, `LIVE_TIER_ORDER` reuse, `HISTORY_SCHEMA_VERSION = 2`, and synthetic fixture
  values in tests/demo.
- Stdlib only; unittest via `python3 -m unittest discover -s tests [-p '<file>.py'] -q`.
  Tests use temp dirs via `--kits-dir`/`--projects-dir` or direct function args — never the
  real `~/.claude`. Do not commit or push.

## Phase 1 — Reader: routing_scorecard parses and reports role quality

### T1 — `agent:` lines gain optional quality fields (findings / confirmed / result)
- status: done
- model: sonnet
- (no dependencies — first task; the T1→T4 warm cluster starts here)

**Files:** `bin/routing_scorecard.py`; NEW `tests/test_role_ledger.py`.

**Why:** verifier precision (findings raised vs findings that survived scrutiny) and
per-dispatch result are the role-quality signals PLAN D1 puts on the existing `agent:` line
for per-task roles. The execute skill already declares unknown `key=value` pairs ignored, so
this is the anticipated extension point.

**Do:**
1. Next to `AGENT_ROLES` (≈ line 137), add `AGENT_RESULTS = ("accepted", "revised",
   "blocked")` with a comment in the same style (structural vocabulary, same species as
   `RESULTS`/`REVIEWS`; note it is shared by the D1 role-ledger extension). Do NOT change
   `AGENT_ROLES` or `AGENT_RE`.
2. Extend `parse_agents` (≈ line 1813). Keep/skip criteria for a line are UNCHANGED
   (`id=` present, `role=` in `AGENT_ROLES`; last-wins per `(task-id, agent-id)`, first
   position kept). Every kept event gains three NEW keys:
   - `result`: `pairs.get("result")`; a value outside `AGENT_RESULTS` degrades to `None`
     with note `f"agent {tid}: unknown result {value!r} — ignored"`.
   - `findings`, `confirmed`: both `None` unless BOTH pairs are present; exactly one present
     → both `None` + note (they must appear together); non-int, negative, or
     `confirmed > findings` → both `None` + one note (self-contradictory evidence is
     dropped, never repaired). A bad quality field NEVER drops the line itself.
   Update the docstring to the new grammar:
   `agent: <task-id> id=<agent-id> role=<...> model=<model> [findings=<n> confirmed=<n>] [result=<accepted|revised|blocked>]`.
3. Create `tests/test_role_ledger.py` (stdlib unittest; load the module with the
   `importlib.util.spec_from_file_location` pattern used by `tests/test_routing_history.py`).
   Cover at minimum: old-style line → new keys present and `None`; happy path; lone
   `findings=`; `confirmed > findings`; non-int; unknown `result=`; last-wins re-emission
   (bare line then enriched line for the same `(task, id)` → enriched values win); and that
   quality-field degradation never drops a line.
4. Confirm no existing test breaks: `tests/test_per_task_dollars.py` asserts field-level
   values and `assertNotIn("extra", ...)` — hand-built event dicts there lack the new keys
   and are consumed by `build_by_task`, which must keep reading only
   `task`/`agent_id`/`role`/`model` (do not change `build_by_task`).

**Accept:** new keys always present on kept events; all degradations are `None`+note; zero
behavior change for every pre-existing consumer; new test file green.

**Verify:**
```
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_role_ledger.py' -q && python3 -m unittest discover -s tests -p 'test_per_task_dollars.py' -q && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q && python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("rs", "bin/routing_scorecard.py")
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
ev, notes = rs.parse_agents(
    "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=1 result=accepted\n"
    "agent: T2 id=a2 role=implementer model=sonnet\n"
    "agent: T3 id=a3 role=verifier model=sonnet findings=2 confirmed=5\n"
    "agent: T4 id=a4 role=verifier model=sonnet result=chef\n")
assert len(ev) == 4, ev
assert ev[0]["findings"] == 3 and ev[0]["confirmed"] == 1 and ev[0]["result"] == "accepted", ev[0]
assert {"findings", "confirmed", "result"} <= set(ev[1]) and ev[1]["findings"] is None \
    and ev[1]["confirmed"] is None and ev[1]["result"] is None, ev[1]
assert ev[2]["findings"] is None and ev[2]["confirmed"] is None, ev[2]
assert ev[3]["result"] is None, ev[3]
assert len(notes) == 2, notes
assert rs.AGENT_RESULTS == ("accepted", "revised", "blocked")
print("T1 probe OK")
PY
```

### T2 — new line families: `reviewer:` and `defect:` parsers
- status: done
- model: sonnet
- depends: T1

**Files:** `bin/routing_scorecard.py`; `tests/test_role_ledger.py`.

**Why (PLAN D1):** phase reviewers are per-phase (the agent ledger deliberately excludes
them — per-task dollars must never split a per-phase transcript), and architect brief
defects are recorded by execute mid-run (PLAN D4). New line families are invisible to old
parsers — cleaner than overloading `agent:`.

**Do:**
1. Next to `AGENT_RE`, add (same comment style — structural grammars, disjoint by key from
   the four existing families):
   `REVIEWER_RE = re.compile(r"^\s*(?:[-*]\s+)?reviewer:\s+(\S+)\s+(.+)$")`
   `DEFECT_RE = re.compile(r"^\s*(?:[-*]\s+)?defect:\s+(\S+)\s+(.+)$")`
2. `parse_reviewers(text)` → `(events, notes)`. Grammar:
   `reviewer: <phase-token> model=<model> findings=<n> confirmed=<n> [result=<accepted|revised|blocked>]`.
   First token = phase label (free-form, e.g. `P1`). KEEP an event only when `model=` is
   present AND `findings=`/`confirmed=` both parse as ints ≥ 0 with `confirmed <= findings`;
   otherwise skip the whole line with note `f"unrecognized reviewer line: {line.strip()!r}"`
   (precision is mandatory here — a reviewer line exists only to record adjudicated
   findings). `result` optional; outside `AGENT_RESULTS` → `None` + note. Events in file
   order; last-wins per phase token, first position kept (mirror `parse_agents`). Event
   keys exactly: `{"phase", "model", "findings", "confirmed", "result"}`. Unknown pairs
   ignored.
3. `parse_defects(text)` → `(events, notes)`. Grammar: `defect: <task-id-or--> kind=<token>`.
   First token = task id, `-` sanctioned for kit-level defects. KEEP only when `kind=` is
   present; else skip + note `f"unrecognized defect line: {line.strip()!r}"`. A repeated
   `(task, kind)` pair keeps the FIRST and adds a note (re-runs must not double-count a
   defect; a genuinely second same-kind defect gets a suffixed kind, e.g. `stale-pin-2` —
   writer-side convention, T6). Event keys exactly: `{"task", "kind"}`. Unknown pairs
   ignored.
4. Tests in `tests/test_role_ledger.py`: happy paths, every skip/degrade rule above,
   last-wins / keep-first behavior, and family disjointness — feed a NOTES.md blob
   containing all SIX families (`outcome:`/`reroute:`/`session:`/`agent:`/`reviewer:`/
   `defect:`) through all six parsers and assert each sees only its own (extend the pattern
   of `test_per_task_dollars.py::ParserFamilyDisjointTests`).

**Accept:** both parsers pure, tolerant, note-on-degrade, never-guess; disjointness proven
in tests; no existing parser touched.

**Verify:**
```
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_role_ledger.py' -q && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q && python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("rs", "bin/routing_scorecard.py")
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
revs, rn = rs.parse_reviewers(
    "reviewer: P1 model=opus findings=2 confirmed=1 result=accepted\n"
    "- reviewer: P2 model=sonnet findings=0 confirmed=0\n"
    "reviewer: P3 findings=1 confirmed=1\n"
    "reviewer: P1 model=opus findings=3 confirmed=3\n"
    "reviewer: P4 model=opus findings=1 confirmed=2\n")
assert [e["phase"] for e in revs] == ["P1", "P2"], revs
assert revs[0]["findings"] == 3 and revs[0]["confirmed"] == 3 and revs[0]["result"] is None, revs[0]
assert revs[1]["findings"] == 0 and revs[1]["model"] == "sonnet", revs[1]
assert len(rn) == 2, rn
defs_, dn = rs.parse_defects(
    "defect: T3 kind=stale-pin\n"
    "defect: - kind=tautological-verify\n"
    "defect: T3 kind=stale-pin\n"
    "defect: T9 severity=high\n")
assert [(e["task"], e["kind"]) for e in defs_] == [("T3", "stale-pin"), ("-", "tautological-verify")], defs_
assert len(dn) == 2, dn
blob = ("outcome: T1 model=sonnet result=pass\nreroute: sonnet to=opus mode=advisory tasks=T1 rate=0/1\n"
        "session: s-1\nagent: T1 id=a1 role=verifier model=sonnet\n")
assert rs.parse_reviewers(blob)[0] == [] and rs.parse_defects(blob)[0] == []
assert rs.parse_outcomes("reviewer: P1 model=opus findings=1 confirmed=1\ndefect: T1 kind=x\n")[0] == {}
print("T2 probe OK")
PY
```

### T3 — `scan_kits` threads agents / reviewers / defects through each record
- status: done
- model: sonnet
- depends: T2

**Files:** `bin/routing_scorecard.py`; `tests/test_role_ledger.py`.

**Why:** `build_history`'s positional signature is frozen (the untouchable bench file calls
it) — role data must ride inside `records`, which `scan_kits` builds.

**Do:**
1. In `scan_kits` (≈ line 1195): the NOTES.md text is already read once — additionally feed
   it to `parse_agents`, `parse_reviewers`, `parse_defects`; carry their notes through
   kit-prefixed exactly like the existing three; records gain keys `"agents"`,
   `"reviewers"`, `"defects"` (empty lists when NOTES.md is missing). Update the docstring's
   record shape. Change nothing else in the function.
2. `run_history`'s namespaced mode merges records via `{**rec, "kit": ...}` — new keys ride
   along automatically; verify by reading, change nothing there in this task.
3. Tests: a temp-dir kit whose NOTES.md carries all six families → record fields populated
   as parsed; a TASKS.md-only kit → the three new keys are `[]` and the existing
   `status-only` note still appears; existing record keys byte-identical in meaning.
   (`tests/test_routing_history.py` asserts record fields individually, not key sets — it
   must stay green UNEDITED in this task.)

**Accept:** records carry the three new keys everywhere (including the missing-NOTES path);
no signature changes; `test_routing_history.py` green without edits.

**Verify:**
```
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_role_ledger.py' -q && python3 -m unittest discover -s tests -p 'test_routing_history.py' -q && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q && python3 - <<'PY'
import importlib.util, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("rs", "bin/routing_scorecard.py")
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
with tempfile.TemporaryDirectory() as td:
    k = Path(td) / "kit-x"; k.mkdir(parents=True)
    (k / "TASKS.md").write_text("# T\n\n## Phase 1 — p\n\n### X1 — t\n- status: done\n- model: sonnet\n")
    (k / "NOTES.md").write_text(
        "outcome: X1 model=sonnet result=pass review=clean\n"
        "agent: X1 id=a1 role=verifier model=sonnet findings=1 confirmed=1 result=accepted\n"
        "reviewer: P1 model=opus findings=2 confirmed=1\n"
        "defect: X1 kind=stale-pin\n"
        "session: s-1\n")
    k2 = Path(td) / "kit-bare"; k2.mkdir()
    (k2 / "TASKS.md").write_text("# T\n\n### Y1 — t\n- status: pending\n- model: haiku\n")
    records, notes = rs.scan_kits(td)
recs = {r["kit"]: r for r in records}
assert recs["kit-x"]["agents"][0]["findings"] == 1, recs["kit-x"]["agents"]
assert recs["kit-x"]["reviewers"][0]["phase"] == "P1"
assert recs["kit-x"]["defects"] == [{"task": "X1", "kind": "stale-pin"}]
assert recs["kit-bare"]["agents"] == [] and recs["kit-bare"]["reviewers"] == [] and recs["kit-bare"]["defects"] == []
real, _ = rs.scan_kits(".claude/kits")
assert any(r["agents"] for r in real), "real kits carry agent: lines — none parsed"
print("T3 probe OK")
PY
```

### T4 — `roles` on the history card: aggregation, schema v2, `## Role quality` markdown
- status: done
- model: sonnet
- depends: T3

**Files:** `bin/routing_scorecard.py`; `tests/test_role_ledger.py`;
`tests/test_routing_history.py`; `tests/test_crossrepo_trend.py`.

**Why (PLAN D6/D7):** the `--history` card is where cross-kit evidence lives and where
`bench_routing compare` reads (downstream, untouched). Zero evidence must render EXPLICITLY
— silent absence is the failure this kit exists to fix.

**Do:**
1. New pure function `role_quality_stats(records)` → `(roles, notes)`:
   - `roles["verifier"]`: over all records' `agents` events with `role == "verifier"` —
     keys exactly `{"events", "with_precision", "findings", "confirmed", "precision",
     "results", "by_tier"}`. `with_precision` counts events whose `findings` is not None;
     `findings`/`confirmed` are sums over those; `precision = confirmed / findings` when the
     findings sum > 0 else `None`; `results` tallies `event["result"]` into keys exactly
     `{"accepted", "revised", "blocked", "unrecorded"}` (None → `unrecorded`); `by_tier`
     ALWAYS maps every `LIVE_TIER_ORDER` tier to `{"events", "findings", "confirmed",
     "precision"}` (zeros / `None` when empty), attributing via `tier_for(model)`; an event
     whose model is None or off-ladder is counted top-level, excluded from `by_tier`, with
     ONE aggregate note.
   - `roles["escalation"]`: `{"events", "results"}`, same results tally, from
     `role == "escalation"` events.
   - `roles["reviewer"]`: from records' `reviewers` — keys exactly `{"events", "findings",
     "confirmed", "precision", "results", "by_tier"}` (every kept reviewer line carries
     precision, so no `with_precision`); same tally/attribution rules.
   - `roles["architect"]`: from records' `defects` — keys exactly `{"defects",
     "kits_recording", "by_kind", "by_kit"}`; `by_kit` maps `rec["kit"]` → count for kits
     with ≥ 1 defect; `kits_recording = len(by_kit)`; `by_kind` tallies `kind`.
   - IMPLEMENTER IS ABSENT by design (PLAN D7 — outcome ledger is its single home; a
     `result=` on an implementer event is ignored here). Say so in the docstring.
2. `build_history`: call `role_quality_stats(records)`, add top-level key `"roles"`, extend
   the returned notes; bump `HISTORY_SCHEMA_VERSION` to `2` (update its comment: v2 = the
   additive `roles` key). Docstring: "Top-level keys EXACTLY" list gains `roles`.
3. `run_history`'s comment near the namespaced post-processing says build_history is
   "frozen-by-policy ... no ninth key" — reword it (PLAN R4): schema v2 makes `roles` the
   ninth key; namespaced mode still post-processes `kits_dir`/`kits_dirs` only.
4. `render_history_markdown`: insert `## Role quality` between `## Per-tier track record`
   and `## Re-route history`, ALWAYS rendered:
   - Zero evidence everywhere (all three `events` == 0 and `defects` == 0) → exactly one
     body line: `no role-quality evidence recorded — verifier, reviewer, escalation, and
     architect quality not yet measurable (implementer-only history).`
   - Otherwise: a pointer line `Implementer quality: see the per-tier track record above
     (outcome ledger).`; a table with columns
     `| Role | Events | With precision | Findings | Confirmed | Precision | Accepted | Revised | Blocked | Unrecorded |`
     and rows verifier / reviewer / escalation (reviewer's With-precision cell = its Events;
     escalation's four precision-ish cells are `n/a`; use `_rate_pct` for Precision);
     per-tier detail lines only for tiers with events > 0
     (`- verifier sonnet: findings 3, confirmed 1, precision 33%`); and an architect line
     `- Architect: <defects> brief defects across <kits_recording> kits (floor — kits run
     before role-ledger adoption record none)` plus, when nonzero, a kinds line
     (`kinds: stale-pin 1, tautological-verify 1` — sorted by kind).
5. Update pinned tests (PLAN R3), in BOTH `tests/test_routing_history.py` and
   `tests/test_crossrepo_trend.py`: every `set(card)` pin of the HISTORY card gains
   `"roles"`; every `card["schema_version"] == 1` assert on the HISTORY card becomes `== 2`;
   every `h2s = [...]` H2-order list gains `"## Role quality"` after
   `"## Per-tier track record"`. Grep both files for `set(card)`, `schema_version`, and
   `h2s`; the TREND card pins (`TREND_SCHEMA_VERSION`, trend key sets) and per-kit/live card
   pins stay at 1 — touch none of them. `read_snapshots`/`build_trend` are `.get`-tolerant
   of old snapshots lacking `roles` — do not edit them; add a test proving an old-shape
   (v1, no roles) snapshot still trends.
6. Tests in `test_role_ledger.py`: aggregation happy path across two synthetic records;
   zero-evidence shape; off-ladder-model exclusion note; markdown section in both branches.

**Accept:** pinned JSON shape above exact; schema 2; markdown section always present; both
pinned test files updated; trend tolerance proven; bench file untouched.

**Verify:**
```
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_role_ledger.py' -q && python3 -m unittest discover -s tests -p 'test_routing_history.py' -q && python3 -m unittest discover -s tests -p 'test_crossrepo_trend.py' -q && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q && python3 bin/routing_scorecard.py --history --json | python3 - <<'PY'
import json, sys
card = json.load(sys.stdin)
assert card["schema_version"] == 2, card["schema_version"]
roles = card["roles"]
assert set(roles) == {"verifier", "escalation", "reviewer", "architect"}, set(roles)
assert set(roles["verifier"]) == {"events", "with_precision", "findings", "confirmed", "precision", "results", "by_tier"}
assert roles["verifier"]["events"] >= 1  # real kits already carry role=verifier agent: lines
assert set(roles["verifier"]["results"]) == {"accepted", "revised", "blocked", "unrecorded"}
assert set(roles["architect"]) == {"defects", "kits_recording", "by_kind", "by_kit"}
assert roles["architect"]["kits_recording"] == len(roles["architect"]["by_kit"])
print("T4 JSON probe OK")
PY
python3 bin/routing_scorecard.py --history | grep -q '^## Role quality'
```

### T5 — demo fixtures: `--demo --history` shows a populated Role quality section
- status: done
- model: sonnet
- depends: T4

**Files:** `bin/routing_scorecard.py` (the `DEMO_HIST_ALPHA_NOTES_MD` constant, ≈ line 318);
`tests/test_routing_history.py` (`test_demo_history_pinned_numbers`);
`tests/test_role_ledger.py` (optional extra pins).

**Why:** the demo is the sanctioned smoke path (CLAUDE.md runs `--demo --history`); it must
demonstrate the populated section, and its pinned numbers are the regression net.

**Do:**
1. Append to `DEMO_HIST_ALPHA_NOTES_MD`, before its `session:` line, EXACTLY these six
   lines (`A1`–`A5` are hist-alpha's real task ids):
   `agent: A1 id=ag-hist-v1 role=verifier model=haiku findings=2 confirmed=2 result=accepted`
   `agent: A2 id=ag-hist-v2 role=verifier model=sonnet findings=3 confirmed=1 result=revised`
   `agent: A4 id=ag-hist-esc role=escalation model=fable result=accepted`
   `reviewer: P1 model=opus findings=2 confirmed=1 result=accepted`
   `defect: A3 kind=stale-pin`
   `defect: - kind=tautological-verify`
2. The existing `--demo --history` pins (tier counts, reroutes, kit rows, dollars) must be
   UNCHANGED — the new families are invisible to the old parsers; that is itself the test.
3. Extend `test_demo_history_pinned_numbers`: roles asserts per the numbers in the verify
   probe below, plus `"## Role quality"` and `"stale-pin"` added to the markdown needles.

**Accept:** demo JSON pins below hold; all pre-existing demo pins hold unedited; markdown
demo shows the populated section.

**Verify:**
```
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_routing_history.py' -q && python3 -m unittest discover -s tests -p 'test_role_ledger.py' -q && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q && python3 bin/routing_scorecard.py --demo --history --json | python3 - <<'PY'
import json, sys
roles = json.load(sys.stdin)["roles"]
v = roles["verifier"]
assert (v["events"], v["with_precision"], v["findings"], v["confirmed"]) == (2, 2, 5, 3), v
assert abs(v["precision"] - 0.6) < 1e-9
assert v["results"] == {"accepted": 1, "revised": 1, "blocked": 0, "unrecorded": 0}
assert v["by_tier"]["haiku"]["precision"] == 1.0 and v["by_tier"]["sonnet"]["findings"] == 3
assert roles["escalation"] == {"events": 1, "results": {"accepted": 1, "revised": 0, "blocked": 0, "unrecorded": 0}}
r = roles["reviewer"]
assert (r["events"], r["findings"], r["confirmed"]) == (1, 2, 1) and abs(r["precision"] - 0.5) < 1e-9
a = roles["architect"]
assert a["defects"] == 2 and a["kits_recording"] == 1
assert a["by_kind"] == {"stale-pin": 1, "tautological-verify": 1} and a["by_kit"] == {"hist-alpha": 2}
print("T5 probe OK")
PY
python3 bin/routing_scorecard.py --demo --history | grep -q 'stale-pin'
```

### T5b — Phase-1 review remediation (orchestrator-added)
- status: done
- model: sonnet
- depends: T5

**Added by the orchestrator after the Phase-1 opus review**, not by the architect. Fixed review
findings F3 (`run_history` docstring still said "eight-key card"; nine since T4) and F4 (`by_tier`
lacked `with_precision`, so "recorded nothing" and "found nothing" rendered byte-identically —
a spec-level false zero, logged as `defect: T4 kind=false-zero-spec`).

**Verify:** `python3 -m unittest discover -s tests -p 'test_role_ledger.py' -q` and
`grep -c 'eight-key' bin/routing_scorecard.py` == 0, and the two per-tier render shapes differ.

## Phase 2 — Writer: the execute/architect contract records role outcomes

### T6 — execute SKILL.md: record role quality at the moment of adjudication

**[AMENDED BY THE ORCHESTRATOR AFTER THE PHASE-1 REVIEW — read this before writing any example.]**

*Finding F2 (opus reviewer, proven by probe).* Every example ledger line this task writes into
`skills/execute/SKILL.md` MUST be enclosed in backticks — inline `` `reviewer: ...` `` or inside
a fenced code block. Unbackticked, a line beginning `reviewer:` or `defect:` in column 1 parses
as **valid data** if it ever reaches a NOTES.md — plain, bulleted (`- `/`* `), or indented four
spaces all match. The result is a fabricated reviewer precision and a fabricated architect
defect, emitted with NO note and caught by NO test. Backticking is the only suppressor
(verified: `` `reviewer: ...` `` yields 0 events).

This already happened live: three lines of the orchestrator's own prose in this kit's NOTES.md
were parsed by the T2 parsers and emitted spurious notes into the real `--history` card (PLAN R2,
fixed). The skill you are editing is the document that TEACHES this grammar, so it is the single
most likely source of future collisions — every future orchestrator copies its examples.

Therefore, in addition to the brief below: the skill's own text must instruct the writer to
backtick any ledger grammar it quotes in prose, and state why (unbackticked grammar in NOTES.md
becomes fabricated evidence). One sentence, in the section that introduces the new line families.
- status: done
- model: opus
- depends: T5

**Files:** `skills/execute/SKILL.md` ONLY (body only — never the YAML frontmatter; skill
files are live runtime behavior).

**Why:** the reader (Phase 1) is worthless until runs WRITE the evidence. The execute skill
is the single writer of NOTES.md ledger lines. Honesty rules here decide whether the metric
means anything (PLAN D2/D4/D5).

**Do — four pinned edits:**
1. In **## Agent ledger — one line per per-task subagent**: extend the indented grammar line
   to
   `agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation> model=<model> [findings=<n> confirmed=<n>] [result=<accepted|revised|blocked>]`
   and add bullets covering, in your own words but with these facts exact:
   - The optional quality fields record the dispatch's ADJUDICATED outcome. `findings` =
     distinct defects the dispatch's verdict raised; `confirmed` = how many you, the
     orchestrator, adjudicated as real (they forced an actual change or an acknowledged
     defect). Adjudicate at the moment the verdict is resolved — when unsure whether a
     finding is real, it is NOT confirmed; never revisit or backfill later.
   - `result` = the fate of the dispatch's product under downstream scrutiny: `accepted`
     (stood as delivered) | `revised` (materially overturned/corrected) | `blocked`.
   - Timing: append the bare line the moment the dispatch returns (unchanged); when
     adjudication lands later, append a SECOND full line for the same task id + agent id
     with the quality fields — the scorecard keeps the last line per `(task-id, agent-id)`.
     Include this example line verbatim:
     `agent: T7 id=a1b2c3 role=verifier model=sonnet findings=3 confirmed=1 result=revised`
   - Implementer lines normally omit the quality fields: implementer quality already lives
     in the `outcome:` ledger, and the scorecard ignores an implementer `result=` to keep
     one number in one home.
2. NEW H2 section **## Role ledger — reviewer verdicts and brief defects** immediately after
   the Agent ledger section, specifying two more OPTIONAL, execute-owned line families
   (precedent: `outcome:`/`reroute:`/`session:`/`agent:`; unknown `key=value` pairs are
   ignored; old kits never rewritten):
   - Phase reviewers (which stay OUT of the `agent:` ledger — per-task dollars must never
     split a per-phase transcript): after the step-6 reviewer returns and you adjudicate its
     findings, append ONE line per phase:
     `reviewer: <phase> model=<model> findings=<n> confirmed=<n> [result=<accepted|revised|blocked>]`
     — include this example verbatim:
     `reviewer: P1 model=opus findings=2 confirmed=1 result=accepted`
     Re-running a phase review appends a fresh line; last per phase token wins.
   - Architect brief defects: the moment a task brief's defect is CONFIRMED against repo
     reality (an implementer stop-and-report you verified; a verify clause that could never
     fail or contradicts its own acceptance; a pinned anchor/line number proven stale; a
     helper invoked that no task creates; an escalation consult forced to rewrite the
     brief), append
     `defect: <task-id> kind=<kebab-case-token>`
     — include this example verbatim: `defect: T3 kind=stale-pin`
     Use task token `-` for kit-level defects (e.g. a stale PLAN decision). Suggested kinds:
     `stale-pin`, `tautological-verify`, `missing-helper`, `unspecified-path`,
     `contradictory-acceptance`, `stale-plan-decision`. A second same-kind defect in the
     same task gets a suffixed kind (`stale-pin-2`) — the scorecard dedupes exact repeats.
     This ledger measures the ARCHITECT: you, the executor, are its honest recorder — log
     the defect even when (especially when) the fix was easy.
3. In loop step 6 (phase boundaries), after "…check the phase against PLAN.md before
   continuing", append: ", then adjudicate its findings and append the phase's `reviewer:`
   line (see **Role ledger — reviewer verdicts and brief defects**)".
4. In **## End of run**, extend the `--history` offer clause to mention that it now also
   reports per-role quality: verifier/reviewer precision, escalation results, and the
   architect brief-defect floor.
Keep the section lean — this skill is re-read every run. Do NOT touch any other section,
any task-field contract text, the status vocabulary, or `skills/architect/SKILL.md` (that
is T7).

**Accept:** all four edits present; the three example lines appear verbatim and round-trip
through the shipped parsers (the seam probe below); no frontmatter or contract drift.

**Verify:**
```
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q && python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("rs", "bin/routing_scorecard.py")
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
text = open("skills/execute/SKILL.md").read()
assert "## Role ledger — reviewer verdicts and brief defects" in text
ex_agent = "agent: T7 id=a1b2c3 role=verifier model=sonnet findings=3 confirmed=1 result=revised"
ex_rev = "reviewer: P1 model=opus findings=2 confirmed=1 result=accepted"
ex_def = "defect: T3 kind=stale-pin"
for ex in (ex_agent, ex_rev, ex_def):
    assert ex in text, f"missing example line: {ex}"
ags, _ = rs.parse_agents(ex_agent)
assert ags and ags[0]["findings"] == 3 and ags[0]["confirmed"] == 1 and ags[0]["result"] == "revised"
revs, _ = rs.parse_reviewers(ex_rev)
assert revs and revs[0]["findings"] == 2 and revs[0]["confirmed"] == 1 and revs[0]["result"] == "accepted"
defs_, _ = rs.parse_defects(ex_def)
assert defs_ and defs_[0] == {"task": "T3", "kind": "stale-pin"}
assert "NOT confirmed" in text            # the when-unsure honesty rule survived editing
assert "[findings=<n> confirmed=<n>] [result=<accepted|revised|blocked>]" in text  # extended grammar line
assert text.count("## Outcome ledger") == 1 and text.count("## Agent ledger") == 1  # no section duplication
print("T6 seam probe OK — writer grammar parses with the shipped reader")
PY
```

### T7 — architect SKILL.md: consume the evidence; re-sync the shared contract
- status: done
- model: opus
- depends: T6

**Files:** `skills/architect/SKILL.md` ONLY (body only). Read `skills/execute/SKILL.md` and
the CLAUDE.md invariant list (read-only) for the sync check.

**Why:** the CLAUDE.md invariant — one kit contract across both skills, re-checked in sync
whenever either is touched. And the architect must be told to READ its own defect ledger:
the metric measures the architect, so the loop closes only if the next architect consults it.

**Do:**
1. In the Step-2 bullet that says to consult
   `python3 bin/routing_scorecard.py --history` when choosing model pins, extend it: the
   history card now carries a **Role quality** section — verifier/reviewer precision,
   escalation results, and the architect **brief-defect floor** (`defect:` lines recorded by
   execute when a brief defect was confirmed mid-run). Recurring defect kinds (e.g.
   `stale-pin`, `tautological-verify`, `missing-helper`) are the ARCHITECT'S OWN failure
   modes — read them as evidence about your briefs and write the next kit against them
   (prefer content assertions over anchors that go stale, counts over line numbers, verify
   commands that can fail, helpers that some task actually creates).
2. Extend the bullet noting that execute maintains NOTES.md (`outcome:` lines, "the
   architect does not create it"): execute also records role-quality lines — optional
   `findings=`/`confirmed=`/`result=` on `agent:` lines, one `reviewer:` line per phase, and
   `defect:` brief-defect lines — all execute-owned and OPTIONAL; the architect creates none
   of them.
3. Sync re-check (report the result explicitly): confirm both skills still agree on the
   FULL kit contract — layout (PLAN/TASKS/GUARDRAILS + execute-owned NOTES), task fields
   (`id`,`title`,`status`,`model`, brief, acceptance, verify), status vocabulary
   `pending | in-progress | done | blocked`, phase headings, `depends:`/`independent:`,
   model-field-overrides-frontmatter dispatch rule — and that this kit changed NONE of
   them (only execute-owned NOTES.md line families grew). If any contract element is
   missing from either file, STOP and report — do not repair beyond this kit's scope.

**Accept:** both bullets extended; sync check performed and reported; no frontmatter edits;
no contract drift.

**Verify:**
```
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q && python3 - <<'PY'
a = open("skills/architect/SKILL.md").read()
e = open("skills/execute/SKILL.md").read()
assert "Role quality" in a and "defect:" in a and "brief-defect" in a
assert "reviewer:" in a and "findings=" in a
for token in ("pending/in-progress/done/blocked", "depends: <ids>", "independent: yes", "GUARDRAILS.md"):
    assert token in a, f"architect contract token lost: {token}"
for token in ("depends:", "GUARDRAILS.md",
              "## Role ledger — reviewer verdicts and brief defects"):
    # note: execute states the status vocabulary in prose, not the pipe-form literal —
    # the pipe form lives in CLAUDE.md and the architect file only; do not "fix" that.
    assert token in e, f"execute contract token lost: {token}"
assert "does not create" in a   # architect still disclaims NOTES.md ownership
print("T7 sync probe OK")
PY
```

### T7b — Phase-2 review remediation (orchestrator-added)
- status: done
- model: opus
- depends: T7

Added by the orchestrator after the Phase-2 opus review returned 6 findings (2 major). Pinned
`reviewer:` `result=` semantics (F1); generalized the backtick rule to all six line families and
hoisted it before the first grammar block (F2); narrowed quality fields to `role=verifier` (F3);
replaced the unfalsifiable "acknowledged" confirmation branch with an artifact test and added a
`findings` counting rule (F4); abolished suffixed kinds that defeated recurrence (F5); documented
the `reviewer:` all-or-nothing drop (F6). Cut ~250 B of restatement.

**Verify:** all six families named in `skills/execute/SKILL.md`; both skills yield 0 events under
all six parsers; 0 accidental collisions across every kit's NOTES.md.

## Phase 3 — Proof

### T8 — full-suite sweep, real-card smoke, collision proof
- status: done
- model: haiku
- depends: T7
- (mechanical run-and-report; fix NOTHING yourself — report faithfully)

**Do:** run the three checks below from the repo root and report each result verbatim.
Known tripwire (PLAN R1): if — and only if — the suite fails inside
`tests/test_bench_routing.py` on its pinned real-ledger aggregate counts (this kit's own
fresh `outcome:` lines legitimately grew them), report that exact failure as the known
cross-kit seam, quote PLAN R1, and DO NOT edit anything. Any other failure is also
report-only at this task.

**Accept:** all three commands' outputs reported verbatim; zero edits made by this task.

**Verify:**
```
cd /path/to/polytropos && python3 -m unittest discover -s tests -q && python3 bin/routing_scorecard.py --history | grep -q '^## Role quality' && python3 - <<'PYCHK'
# COLLISION PROOF (orchestrator-rewritten twice — see NOTES).
# v1 grepped every kit EXCEPT role-ledger: it excluded the only kit where a collision had ever
#    occurred, so it could not fail (GUARDRAILS: a check that cannot fail is decoration).
# v2 (grep all kits for the patterns) was ALSO wrong: role-ledger's NOTES.md now legitimately
#    carries reviewer:/defect: lines, so pattern-presence fails for a CORRECT reason.
# The real question is not "do these patterns appear" but "does any prose parse as data by
# ACCIDENT". Accidental collisions surface as tolerance notes; intentional lines parse cleanly.
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("rs", "bin/routing_scorecard.py")
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
bad = []
for n in sorted(pathlib.Path(".claude/kits").glob("*/NOTES.md")):
    t = n.read_text()
    for fn in ("parse_outcomes", "parse_agents", "parse_reroutes", "parse_sessions", "parse_reviewers", "parse_defects"):
        # v4: ALL SIX families. v3 checked only the two new ones and could not have caught
        # the live collision that actually occurred — a bare `agent:` line in prose (Phase-2
        # review F2). The hazard is the grammar, not the family.
        res = getattr(rs, fn)(t); notes = res[1] if isinstance(res, tuple) else []
        bad += [f"{n.parent.name}: {x}" for x in notes]
assert not bad, "ACCIDENTAL ledger-grammar collisions (prose parsing as data):\n  " + "\n  ".join(bad)
revs = sum(len(rs.parse_reviewers(n.read_text())[0]) for n in pathlib.Path(".claude/kits").glob("*/NOTES.md"))
defs_ = sum(len(rs.parse_defects(n.read_text())[0]) for n in pathlib.Path(".claude/kits").glob("*/NOTES.md"))
print(f"collision proof OK — 0 accidental collisions; {revs} intentional reviewer + {defs_} defect line(s) parse cleanly")
PYCHK && echo 'T8 sweep OK'
```
(The third clause proves no PRE-EXISTING kit's prose collides with the new grammars —
`role-ledger`'s own NOTES.md is the one sanctioned writer this run.)
