# TASKS — crossrepo-trend

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially Repo facts, decisions D1–D11, the
OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `crossrepo-trend-implementer` (the parameter overrides the
agent's frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. **Warm-cluster candidate: T1 → T2** — strictly
serial, same primary file (`bin/routing_scorecard.py`), same `opus` pin; execute may serve
both with one continued (warm) implementer. T3 is independent and fans out fresh; T5 ‖ T6 are
independent and fan out fresh. Dispatch `crossrepo-trend-reviewer` at each phase end. This
kit's PLAN.md declares `autonomy: advisory` — re-route recommendations during this run are
print-only.

Standing rules for every task:

- **NO skill is edited by this kit.** `skills/` stays byte-unchanged — every verify below runs
  `git diff --quiet -- … skills`; any diff there is a defect. If your brief seems to require a
  skill change, STOP and report (PLAN D10).
- **`bin/routing_scorecard.py` changes are ADDITIVE only, a FIFTH time** — existing flags,
  function signatures, output shapes, exit codes, and ALL FOUR prior demos' numbers (`--demo`,
  `--demo --live`, `--demo --history`, `--demo --by-task`) stay byte-stable; a lone
  `--kits-dir` (or none) keeps `--history` output byte-identical to today (kit names
  unprefixed, JSON key set exactly the eight pre-existing keys, no `kits_dirs`, no `- scanned`
  lines); the FOUR frozen test files `tests/test_routing_scorecard.py`,
  `tests/test_reroute_live.py`, `tests/test_routing_history.py`,
  `tests/test_per_task_dollars.py` are never edited (new tests go in
  `tests/test_crossrepo_trend.py`). Never edit `bin/cost_report.py`, `bin/session_cost.py`,
  `bin/copilot_execute.py`, any other existing `bin/`/`tests/` file, `data/` (either pricing
  file), `.claude-plugin/`, `copilot/`, `README.md`, or the completed kits and their agents.
  Never re-implement `scan_kits`/`history_tier_stats`/`tally_reroutes`/`build_history`/
  `kit_cost_summary`/`parse_tasks`/the `session_cost` pipeline — call them. Sanctioned
  existing-file edits: `bin/routing_scorecard.py` (T1/T2), `.gitignore` (T3),
  `docs/ROUTING-HISTORY.md` (T5), `CLAUDE.md` (T6) — pinned changes only.
- **The ONE sanctioned real write is `write_snapshot` under `--snapshot-dir`** (default the
  gitignored `trends/`). It validates its date grammar (`^\d{4}-\d{2}-\d{2}$`, ValueError
  otherwise — the traversal guard); every other mode stays read-only; `--snapshot` + `--demo`
  is rejected. Never write into a kit dir, NOTES.md, source, or the real `~/.claude`.
- **Never fabricate.** A trend needs ≥2 snapshots (one point → the pinned `no trend yet`
  note; zero → n/a); malformed/rogue snapshot files are skipped + noted; cross-repo dollars
  degrade exactly as today (missing transcripts noted + skipped, coverage labeled, one
  `collect()` per scope); duplicate labels get `-2` suffixes + notes, never a silent merge;
  zero-denominator rates render null/`n/a`.
- Never hardcode a price, price ratio, or real model id. Sanctioned exceptions: tier
  vocabulary (`frontier`/`opus`/`sonnet`/`haiku`, `LIVE_TIER_ORDER`), the alias map
  `TASK_MODEL_TIERS = {"fable": "frontier"}`, `TREND_SCHEMA_VERSION = 1`, the
  filename/date/label grammar regexes, `DEFAULT_SNAPSHOT_DIR = PLUGIN_ROOT / "trends"`, the
  pinned demo snapshot dates `2026-01-01`/`2026-01-02`, and synthetic fixture ids/values.
  Demo/test transcript model ids are computed from `data/pricing.json` at run time via
  `_first_model_of_tier`.
- Never read the real `~/.claude` from a test or verify command — every fixture lives in a
  temp dir handed over via `--kits-dir`/`--projects-dir`/`--snapshot-dir` or an explicit
  path. `Path.home()` count in `tests/test_crossrepo_trend.py` and in the
  `bin/routing_scorecard.py` diff: ZERO. Never write outside this repo and temp dirs. No
  network. No journal coupling (nothing under `journal/` read or written). Do not commit or
  push.
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests [-p '<file>.py']`
  (the dotted-module form is broken on this machine). Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` path in any deliverable.

---

## Phase 1 — The engine (additive scorecard extension)

### T1 — Repeatable --kits-dir: cross-repo --history
- status: done
- model: opus
- depends: (none)
- independent: no

**Brief.** Per PLAN.md D1/D2/D3/D4/D9. Extend `bin/routing_scorecard.py` ADDITIVELY: make
`--kits-dir` repeatable, add the label/namespacing machinery, and teach `run_history` the
multi-dir assembly — while keeping the plain single-dir path byte-identical. Extend the module
docstring with a short usage line for the repeatable form and one sentence: with more than one
`--kits-dir` (or any explicit `label=path` token), `--history` namespaces kit rows as
`<label>/<kit>`, aggregates tiers and re-route tallies globally, and prices dollars through
the same single `--projects-dir` with the unchanged degradation rules; with a lone plain dir
the output is byte-identical.

**New constants (pinned):**
- `_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")` — the explicit-label grammar
  (structural, same species as the ledger regexes).

**New pure functions (pinned signatures & behavior):**
- `parse_kits_dir_token(token) -> (label_or_None, path_str)` — if the token contains `=`,
  split on the FIRST `=`; when the prefix matches `_LABEL_RE` and contains no `os.sep` (or
  `os.altsep`), it is an explicit label and the remainder is the path; otherwise the WHOLE
  token is a path with label None (a path containing `=` keeps working).
- `derive_repo_label(path_str) -> str` — pure path logic, NO filesystem access: `p =
  Path(path_str)`; if `p.name == "kits"` and `p.parent.name == ".claude"` → return
  `p.parent.parent.name` (the repo basename — the conventional `<repo>/.claude/kits` case);
  otherwise return `p.name`; an empty result (degenerate roots) falls back to `"kits"`.
- `resolve_kits_dirs(tokens) -> (entries, notes)` — for each raw token in the GIVEN order:
  parse; derive the label when not explicit; entry `{"label", "path", "explicit"}` (path =
  the token's path part, unresolved, verbatim). Dedupe by best-effort `Path(path).resolve()`
  (OSError → the raw path): a repeated dir keeps the FIRST entry + a note naming it.
  Duplicate labels (after explicit/derived resolution) get deterministic suffixes `-2`, `-3`
  … in occurrence order + a note per rename (e.g.
  `duplicate kits-dir label 'aesop' — using 'aesop-2' for <path>`) — never a silent merge.
- **Namespaced mode ⇔ `len(entries) > 1` OR `any(e["explicit"] for e in entries)`** (PLAN
  D3 — an explicit label on a lone dir namespaces too, because that exact invocation errors
  today and is therefore not byte-frozen).

**CLI normalization (pinned — PLAN D2):** change the argparse line to
`ap.add_argument("--kits-dir", action="append", default=None, help=…)` (help: kits dir;
repeatable with --history, where each value may be `label=path`). Immediately after
`parse_args`, capture `kits_dir_passed = args.kits_dir is not None` (T2 needs it), then
normalize: `args.kits_dir = args.kits_dir or [str(DEFAULT_KITS_DIR)]`. New rejection,
inserted AFTER the existing `--by-task` guardrails and BEFORE the `--demo` block:
`if len(args.kits_dir) > 1 and not args.history: sys.exit("multiple --kits-dir values are a
--history affordance — pass one dir")`. Every non-history consumer of `args.kits_dir` uses
`args.kits_dir[0]` VERBATIM as the path (the `_resolve_kit_dir` call site — the function
itself is untouched; no `label=` parsing outside `--history`).

**`run_history` changes (appended logic only — PLAN D4):** at the top:
`entries, dir_notes = resolve_kits_dirs(args.kits_dir)`; check every entry's path is a dir,
else `sys.exit(f"kits dir not found: {path}")` (today's message, first missing wins);
compute namespaced mode.
- *Plain mode* (one dir, no explicit label): proceed through today's body using
  `entries[0]["path"]` — the only edit to the existing body is the line that read the old
  single-valued `args.kits_dir`. Kit names unprefixed; the card exactly today's (string
  `kits_dir`, eight keys); the existing `no kits with a TASKS.md found under …` note logic
  unchanged. `dir_notes` is empty by construction here (no dupes possible with one token) —
  do not add new notes on this path.
- *Namespaced mode*: for each entry in GIVEN order, `scan_kits(path)`; namespace each record
  `{**rec, "kit": f"{label}/{rec['kit']}"}`; re-emit that dir's scan notes as
  `f"{label}/{note}"`; a dir contributing zero records adds
  `f"{label}: no kits with a TASKS.md found under {path}"` (guard the existing GLOBAL
  empty-note so it fires only in plain mode); prepend `dir_notes` (dupe/rename notes) to the
  note stream. Then run the EXISTING dollars degradation ladder verbatim over the merged
  records (quality-only + no pricing load when zero `session:` lines anywhere; per-kit
  `kit_cost_summary` results keyed by the NAMESPACED kit name; ordered-unique union of
  session ids priced ONCE; shared-id note with namespaced names; coverage full/partial rule
  unchanged), then ONE `build_history(entries[0]["path"], records, kit_costs, dollars,
  notes)` call and post-process the returned dict: `card["kits_dir"] = None`,
  `card["kits_dirs"] = [{"label": e["label"], "path": e["path"]} for e in entries]`.
  (Implementation freedom: restructure run_history's interior as little as possible — the
  plain path must remain today's code path; a shared tail for build+print is fine.)

**Markdown hook (pinned, the ONLY `render_history_markdown` change):** immediately after the
Verdict bold line is appended, insert one guarded block —
`if card.get("kits_dirs"):` → for each entry append exactly `- scanned {label}: {path}`,
then append `""`. Old cards never carry the key, so every existing output is byte-identical.
Do NOT touch the H1, the five H2s, `MD_H2S`, or any existing line.

GOTCHAS: zero `Path.home()` in the diff; `scan_kits`/`build_history`/`kit_cost_summary` are
called, never modified; kit_costs MUST be keyed by the namespaced names (dollars silently
detach from kit rows otherwise); records merge in given-dir order (each dir's kits already
sorted by `scan_kits`); `--demo --history` passes one plain `--kits-dir` internally → plain
mode → byte-identical; the in-process `rs.main([...])` call in frozen
`tests/test_routing_history.py` must keep working (normalization lives in `main`, so it does).

**Acceptance.**
- All FOUR prior demos still yield their pinned numbers (see verify).
- A lone-`--kits-dir` `--history --json` run over a temp fixture has EXACTLY the eight
  pre-existing top-level keys, a string `kits_dir`, unprefixed kit names, and markdown with
  no `- scanned` line.
- A two-dir run over `<tmp>/repo-a/.claude/kits` + `<tmp>/repo-b/.claude/kits`, each
  containing a kit named `alpha`, yields TWO kit rows `repo-a/alpha` and `repo-b/alpha`,
  globally-summed tiers, `kits_dir` None, a two-entry `kits_dirs`, and `- scanned repo-a:` /
  `- scanned repo-b:` markdown lines.
- Cross-repo dollars: session ids recorded in kits of BOTH repos, with transcripts under TWO
  different project slugs of ONE temp projects dir, are both priced into the aggregate; a
  missing id is noted + skipped (coverage partial).
- An explicit `label=path` on a lone dir namespaces; multiple `--kits-dir` outside
  `--history` exits nonzero; label-collision suffixing and same-path dedupe note.
- Greps clean; the four frozen test files, reused scripts, `data/`, and `skills` unchanged;
  full suite + sync check green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && ! grep -n 'Path.home()' bin/routing_scorecard.py && ! grep -n 'sqlite' bin/routing_scorecard.py && ! grep -nE 'claude-(fable|opus|sonnet|haiku)' bin/routing_scorecard.py && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py tests/test_routing_history.py tests/test_per_task_dollars.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data skills && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T1 OK'
import json, subprocess, sys, tempfile
from pathlib import Path

def run(argv):
    return subprocess.run([sys.executable, "bin/routing_scorecard.py"] + argv,
                          capture_output=True, text=True)

# --- all four prior demos: pinned additive regressions ---
j = run(["--demo", "--json"]); assert j.returncode == 0, j.stderr
c = json.loads(j.stdout); q = c["quality"]
assert (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"], q["escalated_pass"], q["blocked"]) == (6, 6, 3, 1, 1, 1), q
assert c["model_mix"] == {"haiku": 1, "sonnet": 4, "fable": 1} and abs(c["review"]["survival_rate"] - 0.75) < 1e-9
l = run(["--demo", "--live", "--json"]); assert l.returncode == 0, l.stderr
d = json.loads(l.stdout)
assert d["autonomy"] == "advisory" and d["budget"] == {"cap": 2, "applied": 0, "remaining": 2}
assert [(r["from"], r["to"], r["task_ids"]) for r in d["recommendations"]] == [("sonnet", "opus", ["L5", "L6"])]
h = run(["--demo", "--history", "--json"]); assert h.returncode == 0, h.stderr
hc = json.loads(h.stdout)
K = ("pinned", "with_outcome", "first_try", "retry_pass", "escalated_pass", "blocked")
pick = lambda t: tuple(hc["tiers"][t][k] for k in K)
assert pick("haiku") == (3, 3, 2, 1, 0, 0) and pick("sonnet") == (6, 5, 2, 1, 1, 1)
assert pick("opus") == (2, 1, 1, 0, 0, 0) and pick("frontier") == (1, 0, 0, 0, 0, 0)
assert hc["reroutes"] == {"events": 1, "applied": 0, "advisory": 1} and hc["dollars"]["coverage"] == "partial"
assert set(hc) == {"schema_version", "generated_at", "kits_dir", "kits", "tiers", "reroutes", "dollars", "notes"}, "demo --history card must keep the eight keys"
assert isinstance(hc["kits_dir"], str)
assert [k["kit"] for k in hc["kits"]] == ["hist-alpha", "hist-beta", "hist-gamma"], "demo kit names must stay unprefixed"
b = run(["--demo", "--by-task", "--json"]); assert b.returncode == 0, b.stderr
bt = json.loads(b.stdout)["by_task"]
assert [r["id"] for r in bt["tasks"]] == ["P1", "P2", "P3", "P4", "P5"] and bt["coverage"] == "partial"
assert [(cl["agent_id"], cl["task_ids"]) for cl in bt["clusters"]] == [("ag-warm", ["P3", "P4"])]
assert bt["unattributed"]["agent_ids"] == ["ag-reviewer"]
hm = run(["--demo", "--history"]); assert hm.returncode == 0 and "- scanned" not in hm.stdout

# --- pure surface ---
import importlib.util
spec = importlib.util.spec_from_file_location("routing_scorecard", Path("bin/routing_scorecard.py").resolve())
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
assert rs.parse_kits_dir_token("/x/y") == (None, "/x/y")
assert rs.parse_kits_dir_token("aesop=/x/.claude/kits") == ("aesop", "/x/.claude/kits")
assert rs.parse_kits_dir_token("/x/a=b/kits") == (None, "/x/a=b/kits"), "separator-bearing prefix is not a label"
assert rs.parse_kits_dir_token("=x") == (None, "=x"), "empty label prefix is not a label"
assert rs.derive_repo_label("/w/polytropos/.claude/kits") == "polytropos"
assert rs.derive_repo_label("/w/somewhere/mykits") == "mykits"
ents, notes = rs.resolve_kits_dirs(["/a/r1/.claude/kits", "/b/r1/.claude/kits"])
assert [e["label"] for e in ents] == ["r1", "r1-2"], ents
assert any("duplicate kits-dir label" in n for n in notes), notes
ents2, notes2 = rs.resolve_kits_dirs(["/a/r1/.claude/kits", "/a/r1/.claude/kits"])
assert len(ents2) == 1 and notes2, "same dir twice must dedupe with a note"

TASKS = "# T\n\n## Phase 1 — p\n\n### {i} — a\n- status: done\n- model: sonnet\n"
NOTES = "outcome: {i} model=sonnet result=pass review=clean\nsession: {s}\n"

def write_kit(root, name, i, sess=None):
    kd = root / name; kd.mkdir(parents=True)
    (kd / "TASKS.md").write_text(TASKS.format(i=i))
    if sess:
        (kd / "NOTES.md").write_text(NOTES.format(i=i, s=sess))

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    ka = tmp / "repo-a" / ".claude" / "kits"; kb = tmp / "repo-b" / ".claude" / "kits"
    write_kit(ka, "alpha", "A1", "sess-a"); write_kit(kb, "alpha", "B1", "sess-b")
    # transcripts under TWO project slugs of ONE projects dir (the cross-repo dollars fact)
    prices = json.loads(Path("data/pricing.json").read_text())
    mid = next(k for k, v in prices["models"].items() if v.get("tier") == "sonnet")
    for slug, sess in (("-proj-a", "sess-a"), ("-proj-b", "sess-b")):
        pd = tmp / "projects" / slug; pd.mkdir(parents=True)
        (pd / f"{sess}.jsonl").write_text(json.dumps({
            "timestamp": "2026-07-01T12:00:00+00:00",
            "message": {"model": mid, "id": f"m-{sess}",
                        "usage": {"input_tokens": 1000, "output_tokens": 100}}}) + "\n")
    # single dir: byte-shape proof (eight keys, unprefixed, no scanned lines)
    r1 = run(["--history", "--kits-dir", str(ka), "--projects-dir", str(tmp / "projects"),
              "--no-subagents", "--json"])
    assert r1.returncode == 0, r1.stderr
    c1 = json.loads(r1.stdout)
    assert set(c1) == {"schema_version", "generated_at", "kits_dir", "kits", "tiers", "reroutes", "dollars", "notes"}
    assert c1["kits_dir"] == str(ka) and [k["kit"] for k in c1["kits"]] == ["alpha"]
    m1 = run(["--history", "--kits-dir", str(ka), "--projects-dir", str(tmp / "projects"), "--no-subagents"])
    assert "- scanned" not in m1.stdout
    # multi dir: namespaced same-named kits, global tiers, kits_dirs, dollars over both slugs
    r2 = run(["--history", "--kits-dir", str(ka), "--kits-dir", str(kb),
              "--projects-dir", str(tmp / "projects"), "--no-subagents", "--json"])
    assert r2.returncode == 0, r2.stderr
    c2 = json.loads(r2.stdout)
    assert [k["kit"] for k in c2["kits"]] == ["repo-a/alpha", "repo-b/alpha"], c2["kits"]
    assert c2["kits_dir"] is None and [e["label"] for e in c2["kits_dirs"]] == ["repo-a", "repo-b"]
    assert c2["tiers"]["sonnet"]["with_outcome"] == 2 and c2["tiers"]["sonnet"]["first_try"] == 2
    assert c2["dollars"] is not None and c2["dollars"]["sessions_priced"] == 2 and c2["dollars"]["coverage"] == "full"
    assert all(k["cost"] is not None for k in c2["kits"]), "kit_costs must be keyed by the NAMESPACED names"
    m2 = run(["--history", "--kits-dir", str(ka), "--kits-dir", str(kb),
              "--projects-dir", str(tmp / "projects"), "--no-subagents"])
    assert f"- scanned repo-a: {ka}" in m2.stdout and f"- scanned repo-b: {kb}" in m2.stdout
    assert "repo-a/alpha" in m2.stdout and "repo-b/alpha" in m2.stdout
    # explicit label on a lone dir namespaces
    r3 = run(["--history", "--kits-dir", f"mylabel={ka}",
              "--projects-dir", str(tmp / "projects"), "--no-subagents", "--json"])
    assert r3.returncode == 0, r3.stderr
    c3 = json.loads(r3.stdout)
    assert [k["kit"] for k in c3["kits"]] == ["mylabel/alpha"] and c3["kits_dirs"][0]["label"] == "mylabel"
    # missing id degrades: add a kit with an unpriceable session
    write_kit(kb, "beta", "B2", "sess-ghost")
    r4 = run(["--history", "--kits-dir", str(ka), "--kits-dir", str(kb),
              "--projects-dir", str(tmp / "projects"), "--no-subagents", "--json"])
    c4 = json.loads(r4.stdout)
    assert c4["dollars"]["coverage"] == "partial" and any("sess-ghost" in n for n in c4["notes"])
    # multiple --kits-dir outside --history rejected
    r5 = run(["alpha", "--kits-dir", str(ka), "--kits-dir", str(kb)])
    assert r5.returncode != 0 and "--history" in r5.stderr
    # nonexistent dir in a multi run dies with today's message
    r6 = run(["--history", "--kits-dir", str(ka), "--kits-dir", str(tmp / "nope")])
    assert r6.returncode != 0 and "kits dir not found" in r6.stderr
print("T1 cross-repo checks ok")
PY
```

---

### T2 — Snapshot store + trend view (+ the combined demo)
- status: done
- model: opus
- depends: T1
- independent: no

**Brief.** Per PLAN.md D1/D5/D6/D7/D8/D9. Extend `bin/routing_scorecard.py` ADDITIVELY with
the snapshot store and the trend view, plus the `--demo --history --trend` smoke. Extend the
module docstring with usage lines for `--snapshot`/`--trend` and one sentence: `--snapshot`
writes the history card as a dated JSON file into a gitignored snapshot store (the one
sanctioned write; every other mode stays read-only), and `--trend` renders per-tier first-try
rate over the stored snapshots as a text table — a trend needs at least two snapshots, and
with zero or one it says so instead of fabricating.

**New constants (pinned):**
- `TREND_SCHEMA_VERSION = 1` — same species as the other four schema versions.
- `SNAPSHOT_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")` and the date grammar
  `^\d{4}-\d{2}-\d{2}$` (module-level compiled regex or inline in `write_snapshot` — your
  call, but the grammar is pinned).
- `DEFAULT_SNAPSHOT_DIR = PLUGIN_ROOT / "trends"`.

**New pure functions (pinned signatures & behavior):**
- `write_snapshot(card, snapshot_dir, date_str=None) -> Path` — THE one sanctioned writer.
  `date_str` None → UTC today via `datetime.now(timezone.utc).strftime("%Y-%m-%d")`; a given
  `date_str` failing the date grammar raises `ValueError` (the traversal guard — nothing can
  escape the dir); `Path(snapshot_dir).mkdir(parents=True, exist_ok=True)`; writes
  `json.dumps(card, indent=2) + "\n"` to `<snapshot_dir>/<date>.json` (plain overwrite —
  latest-wins per day, deliberate); returns the Path.
- `read_snapshots(snapshot_dir) -> (dated_cards, notes)` — missing dir →
  `([], ["snapshot dir not found: <dir>"])`; else consider only `*.json` files, sorted by
  name; a name failing `SNAPSHOT_FILENAME_RE` → skip + `rogue snapshot file skipped: <name>`;
  unreadable/undecodable → skip + a note naming the file; decoded JSON that is not a dict or
  lacks a dict `tiers` → skip + note; survivors → `(date_str, card)` tuples ascending by date
  (ISO names sort lexicographically).
- `build_trend(snapshot_dir, dated_cards, notes) -> card` — pinned key set
  `{"schema_version", "generated_at", "snapshot_dir" (str), "points", "notes"}`. Each point:
  `{"date", "kits": len(card.get("kits") or []), "tiers": {tier: {"with_outcome",
  "first_try", "first_try_rate"} for tier in LIVE_TIER_ORDER}, "dollars"}` — tier cells read
  tolerantly from the stored card's `tiers` (absent tier → zeros + rate None, no note);
  `dollars` = `{"actual_usd", "delta_usd"}` when the stored card's `dollars` is a dict, else
  None — NEVER recomputed. Zero points → append
  `no snapshots found under <dir> — nothing to trend`; exactly one → append
  `one snapshot — no trend yet (a trend needs at least 2 points)` (the point still renders).
- `render_trend_markdown(card) -> str` — H1
  `# Routing trend — per-tier first-try rate over time`; zero points → the line
  `no snapshots — n/a`; otherwise ONE table, rows = dates ascending, header
  `| Date | haiku | sonnet | opus | frontier | Kits | Actual $ |` with tier columns generated
  from `LIVE_TIER_ORDER` (never retyped), tier cells
  `{first_try}/{with_outcome} ({_rate_pct(rate)})` or `n/a` when `with_outcome` is 0,
  `Actual $` cells `$x.xx` (two decimals, comma-grouped like the existing renderers) or `n/a`
  when dollars is None; then the `Notes:` block in the existing style.
- `run_trend(args, extra_notes=()) -> 0` — notes start from `list(extra_notes)`; append the
  existing `--tasks-dir/--include are ignored by --history (single-session affordances; use
  --session on the plain scorecard)` note when either is passed; append
  `--kits-dir is ignored by --trend without --snapshot (the trend reads stored snapshots)`
  when `--kits-dir` was explicitly passed AND `--snapshot` is absent (T1's
  `kits_dir_passed` capture); `read_snapshots` → `build_trend` → print markdown or
  `json.dumps(card, indent=2)`; return 0 for every degraded shape. Pure `--trend` NEVER calls
  `cr.load_pricing()` and never scans kits.

**CLI wiring (pinned — PLAN D6):** new flags `--snapshot` (store_true), `--trend`
(store_true), `--snapshot-dir` (default `str(DEFAULT_SNAPSHOT_DIR)`). Rejections, inserted
with T1's new rejection (after the `--by-task` guardrails, before the `--demo` block):
`--snapshot` without `--history` → `sys.exit("--snapshot rides --history — pass --history")`;
`--trend` without `--history` → `sys.exit("--trend rides --history — pass --history")`;
`--snapshot` with `--demo` → `sys.exit("--demo takes no --snapshot — the demo writes only to
its own temp dir")`. In the `--demo` block: `--demo --history --trend` dispatches
`run_trend_demo(args.json)` (check `args.trend` BEFORE the existing `run_history_demo`
dispatch; `--demo --history` alone is unchanged). Non-demo dispatch: `args.history and
args.trend and not args.snapshot` → `return run_trend(args)` (placed where the non-demo
`--history` branch dispatches today). `run_history` tail (after the card is fully assembled,
before printing): `if args.snapshot: path = write_snapshot(card, args.snapshot_dir)`; then
`if args.trend: return run_trend(args, extra_notes=[f"snapshot written: {path}"])`; else
`if args.snapshot: card["notes"].append(f"snapshot written: {path}")` and the normal print.
The STORED card therefore never contains the `snapshot written:` note.

**Demo (pinned — PLAN D8):** `run_trend_demo(as_json)` builds, in ONE
`tempfile.TemporaryDirectory`: `repo-a/.claude/kits/hist-alpha` (`DEMO_HIST_ALPHA_TASKS_MD` +
`DEMO_HIST_ALPHA_NOTES_MD`), `repo-a/.claude/kits/hist-beta` (beta constants),
`repo-b/.claude/kits/hist-gamma` (`DEMO_HIST_GAMMA_TASKS_MD`, NO NOTES.md), and
`projects/-demo/hist-alpha-session.jsonl` built exactly like `run_history_demo`'s transcript
block (one message per tier, ids `demo-hist-<tier>`, model ids via
`_first_model_of_tier(pricing, tier)` with the `if model_id is None: continue` guard, volumes
from `DEMO_VOLUMES` — reuse the constants read-only; do NOT modify them). Then capture two
history cards by calling `main([...])` in-process with stdout redirected
(`contextlib.redirect_stdout(io.StringIO())`), both with `--no-subagents --json`:
day 1 = `["--history", "--kits-dir", <repo-a kits>, "--projects-dir", <projects>,
"--no-subagents", "--json"]`; day 2 = the same plus `"--kits-dir", <repo-b kits>`.
`json.loads` each capture and `write_snapshot(card1, snap, "2026-01-01")` /
`write_snapshot(card2, snap, "2026-01-02")`. Finally
`return main(["--history", "--trend", "--snapshot-dir", str(snap)] + (["--json"] if as_json
else []))`. Expected (the verify asserts): exit 0; 2 points, dates
`["2026-01-01", "2026-01-02"]`; kits 2 then 3; both points haiku {3, 2}, sonnet {5, 2}, opus
{1, 1}, frontier {0, 0, rate None} (as with_outcome/first_try); both points
`dollars["actual_usd"] > 0` (values NOT pinned); no `no trend yet` note; markdown contains
the pinned H1, header, both date rows, `2/3 (67%)`, `2/5 (40%)`, `1/1 (100%)`.

GOTCHAS: zero `Path.home()`; the demo writes only inside its own temp dir (the pinned dates
are synthetic fixture dates, sanctioned); `io`/`contextlib` are stdlib; run_trend must not
consult `args.kits_dir`'s VALUE (only the passed/not-passed flag for the note); `--history
--snapshot` still prints the full history card (plus the note); `--history --snapshot
--trend` prints the TREND card only; every degraded trend shape exits 0; `MD_H2S` untouched.

**Acceptance.**
- `python3 bin/routing_scorecard.py --demo --history --trend [--json]` prints the pinned D8
  trend; `--demo --history` output is unchanged.
- On a temp fixture: `--history --kits-dir X --projects-dir P --no-subagents --snapshot
  --snapshot-dir S --json` exits 0, creates exactly ONE new file `S/<UTC-today>.json`, whose
  stored card has the history key set and NO `snapshot written:` note, while the printed
  card's notes include `snapshot written:`; nothing else in the fixture tree changed.
- `--history --trend --snapshot-dir <empty>` exits 0 with the `no snapshots` note; with one
  snapshot → the `no trend yet` note plus the single rendered point; malformed/rogue files
  skipped + noted; survivors still trend.
- Rejections: `--snapshot` without `--history`; `--trend` without `--history`;
  `--demo --history --snapshot`.
- `write_snapshot` raises ValueError on `"2026-1-1"`, `"../evil"`, `"2026-01-01x"`.
- All four prior demos pinned; greps clean; frozen files/skills unchanged; full suite + sync
  check green.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/routing_scorecard.py --demo --history --trend && python3 - <<'PY' && ! grep -n 'Path.home()' bin/routing_scorecard.py && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py tests/test_routing_history.py tests/test_per_task_dollars.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data skills && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T2 OK'
import importlib.util, json, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

def run(argv):
    return subprocess.run([sys.executable, "bin/routing_scorecard.py"] + argv,
                          capture_output=True, text=True)

# --- the trend demo: pinned D8 card ---
t = run(["--demo", "--history", "--trend", "--json"]); assert t.returncode == 0, t.stderr
tc = json.loads(t.stdout)
assert set(tc) == {"schema_version", "generated_at", "snapshot_dir", "points", "notes"}, set(tc)
assert tc["schema_version"] == 1 and len(tc["points"]) == 2
assert [p["date"] for p in tc["points"]] == ["2026-01-01", "2026-01-02"]
assert [p["kits"] for p in tc["points"]] == [2, 3]
for p in tc["points"]:
    g = lambda tier: (p["tiers"][tier]["with_outcome"], p["tiers"][tier]["first_try"])
    assert g("haiku") == (3, 2) and g("sonnet") == (5, 2) and g("opus") == (1, 1) and g("frontier") == (0, 0), p["tiers"]
    assert p["tiers"]["frontier"]["first_try_rate"] is None
    assert p["dollars"] is not None and p["dollars"]["actual_usd"] > 0
assert not any("no trend yet" in n for n in tc["notes"])
tm = run(["--demo", "--history", "--trend"]); assert tm.returncode == 0, tm.stderr
for needle in ("# Routing trend — per-tier first-try rate over time",
               "| Date | haiku | sonnet | opus | frontier | Kits | Actual $ |",
               "| 2026-01-01 |", "| 2026-01-02 |", "2/3 (67%)", "2/5 (40%)", "1/1 (100%)"):
    assert needle in tm.stdout, f"trend markdown missing: {needle!r}\n{tm.stdout}"
# --demo --history unchanged (no trend leak)
hm = run(["--demo", "--history"]); assert hm.returncode == 0
assert "# Routing history — cross-kit per-tier track record" in hm.stdout and "Routing trend" not in hm.stdout

# --- prior demos: pinned additive regressions ---
c = json.loads(run(["--demo", "--json"]).stdout); q = c["quality"]
assert (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"], q["escalated_pass"], q["blocked"]) == (6, 6, 3, 1, 1, 1)
assert c["model_mix"] == {"haiku": 1, "sonnet": 4, "fable": 1} and abs(c["review"]["survival_rate"] - 0.75) < 1e-9
d = json.loads(run(["--demo", "--live", "--json"]).stdout)
assert d["budget"] == {"cap": 2, "applied": 0, "remaining": 2} and len(d["recommendations"]) == 1
hc = json.loads(run(["--demo", "--history", "--json"]).stdout)
assert tuple(hc["tiers"]["sonnet"][k] for k in ("pinned", "with_outcome", "first_try")) == (6, 5, 2)
assert hc["reroutes"] == {"events": 1, "applied": 0, "advisory": 1}
bt = json.loads(run(["--demo", "--by-task", "--json"]).stdout)["by_task"]
assert [r["id"] for r in bt["tasks"]] == ["P1", "P2", "P3", "P4", "P5"] and bt["coverage"] == "partial"

# --- pure surface: write_snapshot grammar / traversal guard ---
spec = importlib.util.spec_from_file_location("routing_scorecard", Path("bin/routing_scorecard.py").resolve())
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
assert rs.TREND_SCHEMA_VERSION == 1
with tempfile.TemporaryDirectory() as tmp:
    for bad in ("2026-1-1", "../evil", "2026-01-01x", "20260101"):
        try:
            rs.write_snapshot({}, Path(tmp) / "s", bad)
            raise AssertionError(f"write_snapshot accepted {bad!r}")
        except ValueError:
            pass
    p = rs.write_snapshot({"tiers": {}}, Path(tmp) / "s", "2026-02-03")
    assert p.name == "2026-02-03.json" and p.parent == Path(tmp) / "s"
    assert json.loads(p.read_text()) == {"tiers": {}}

# --- CLI: snapshot writes exactly one dated file; stored card is pure ---
TASKS = "# T\n\n## Phase 1 — p\n\n### S1 — a\n- status: done\n- model: sonnet\n"
NOTES = "outcome: S1 model=sonnet result=pass review=clean\nsession: snap-sess\n"
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    kd = tmp / "kits" / "solo"; kd.mkdir(parents=True)
    (kd / "TASKS.md").write_text(TASKS); (kd / "NOTES.md").write_text(NOTES)
    pd = tmp / "projects" / "-t"; pd.mkdir(parents=True)
    prices = json.loads(Path("data/pricing.json").read_text())
    mid = next(k for k, v in prices["models"].items() if v.get("tier") == "sonnet")
    (pd / "snap-sess.jsonl").write_text(json.dumps({
        "timestamp": "2026-07-01T12:00:00+00:00",
        "message": {"model": mid, "id": "m1", "usage": {"input_tokens": 1000, "output_tokens": 100}}}) + "\n")
    snap = tmp / "store"
    def tree(root):
        return {str(f.relative_to(root)): f.read_bytes() for f in root.rglob("*") if f.is_file()}
    before = tree(tmp)
    r = run(["--history", "--kits-dir", str(tmp / "kits"), "--projects-dir", str(tmp / "projects"),
             "--no-subagents", "--snapshot", "--snapshot-dir", str(snap), "--json"])
    assert r.returncode == 0, r.stderr
    printed = json.loads(r.stdout)
    assert any(n.startswith("snapshot written: ") for n in printed["notes"])
    after = tree(tmp)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_files = set(after) - set(before)
    assert new_files == {str((snap / f"{today}.json").relative_to(tmp))}, new_files
    assert all(before[k] == after[k] for k in before), "existing files must be untouched"
    stored = json.loads((snap / f"{today}.json").read_text())
    assert set(stored) == {"schema_version", "generated_at", "kits_dir", "kits", "tiers", "reroutes", "dollars", "notes"}
    assert not any("snapshot written" in n for n in stored["notes"]), "stored card must be pure data"
    # trend over ONE snapshot: the no-trend-yet honesty
    r1 = run(["--history", "--trend", "--snapshot-dir", str(snap), "--json"])
    assert r1.returncode == 0, r1.stderr
    one = json.loads(r1.stdout)
    assert len(one["points"]) == 1 and any("no trend yet" in n for n in one["notes"])
    # rogue + malformed files skipped, survivors still render
    (snap / "rogue.json").write_text("{}"); (snap / "2026-01-05.json").write_text("not json")
    r2 = run(["--history", "--trend", "--snapshot-dir", str(snap), "--json"])
    two = json.loads(r2.stdout)
    assert len(two["points"]) == 1
    assert any("rogue snapshot file skipped" in n for n in two["notes"])
    assert any("2026-01-05" in n for n in two["notes"])
    # zero snapshots: n/a, exit 0
    r3 = run(["--history", "--trend", "--snapshot-dir", str(tmp / "empty-store")])
    assert r3.returncode == 0 and "no snapshots" in r3.stdout
# --- rejections ---
for argv, why in ((["--snapshot"], "--snapshot without --history"),
                  (["--trend"], "--trend without --history"),
                  (["--demo", "--history", "--snapshot"], "--demo with --snapshot")):
    r = run(argv)
    assert r.returncode != 0, f"must reject: {why}"
print("T2 snapshot/trend checks ok")
PY
```

---

### T3 — Gitignore the snapshot store
- status: done
- model: haiku
- depends: (none)
- independent: yes

**Brief.** ONE pinned append to `.gitignore`, nothing else. The file currently ends with the
line `/journal/` (preceded by its comment line). Append exactly these two lines at the end of
the file:

```
# routing-trend snapshot store (generated local data — never committed)
/trends/
```

Do not create the `trends/` dir, do not touch any other line.

**Acceptance.** `.gitignore` ends with the two pinned lines (each present exactly once);
`git check-ignore -q trends/2026-01-01.json` exits 0; the pre-existing five lines are
unchanged; no `trends/` dir was created.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && git check-ignore -q trends/2026-01-01.json && git check-ignore -q journal/x && test ! -e trends && echo 'T3 OK'
t = open('.gitignore').read()
assert t.count('/trends/\n') == 1, "trends entry missing/duplicated"
assert t.count('# routing-trend snapshot store (generated local data — never committed)\n') == 1
assert t.rstrip().endswith('/trends/'), ".gitignore must end with the trends entry"
for line in ('.claude/settings.local.json', '__pycache__/', '.DS_Store', '/journal/'):
    assert line in t, f"pre-existing line lost: {line}"
print('gitignore ok')
PY
```

---

*Phase 1 end — dispatch `crossrepo-trend-reviewer` before starting Phase 2.*

---

## Phase 2 — Regression tests

### T4 — Regression tests (tests/test_crossrepo_trend.py)
- status: done
- model: sonnet
- depends: T2, T3
- independent: no

**Brief.** Create `tests/test_crossrepo_trend.py`, stdlib `unittest`, loading
`bin/routing_scorecard.py` via the importlib convention off
`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` (copy the header pattern and
module-docstring safety contract from `tests/test_routing_history.py`: no test reads the real
Claude project store or calls the stdlib home helper; every fixture lives in a fresh
`tempfile.TemporaryDirectory()` handed over via `--kits-dir`/`--projects-dir`/
`--snapshot-dir` or explicit paths; synthetic ids/values only, tier vocabulary + the `fable`
alias as the only model tokens EXCEPT ids computed at run time from `rs.cr.load_pricing()` +
`rs._first_model_of_tier` for dollar fixtures — never a spelled model id). Do NOT edit any of
the four frozen scorecard test files — this is a new file.

Helpers: a kit fixture writer (spaced em-dash headings, `- status:`/`- model:` lines, pinned
`outcome:`/`session:` grammars); a transcript writer emitting
`{"timestamp", "message": {"model", "id", "usage": {…}}}` JSONL; a snapshot-card writer that
composes a minimal synthetic HISTORY card dict (`tiers` per `LIVE_TIER_ORDER`, `kits` list,
`dollars` dict or None) and a recursive `tree(root)` byte-snapshot helper for read-only
proofs. CLI runs via subprocess (`_run_cli` pattern from the frozen files); pure functions
in-process.

Minimum cases — include these EXACT method names (greps in the verify key on them), plus
whatever else you need:

1. `test_parse_kits_dir_token_grammar` — plain path → (None, path); `label=path` → split;
   a pre-`=` prefix containing a separator or failing the label charset → whole token is a
   path; `=x` (empty label) → path; first-`=` split only.
2. `test_derive_repo_label_conventional_and_fallback` — `<repo>/.claude/kits` → repo
   basename; any other dir → its own basename; trailing-slash tokens normalize (Path
   semantics); no filesystem access needed (nonexistent paths fine).
3. `test_resolve_kits_dirs_dedupe_and_collisions` — same resolved path twice → one entry +
   note; two dirs deriving the same label → `label`, `label-2` + note; explicit label wins
   over derivation; entries keep given order.
4. `test_single_dir_history_byte_shape` — one temp kits dir via CLI `--history --json`:
   top-level keys EXACTLY the eight pre-existing ones (no `kits_dirs`), `kits_dir` a string,
   kit names unprefixed; markdown has the five pinned H2s and NO `- scanned` line.
5. `test_multi_dir_namespaces_and_aggregates` — two conventional repo layouts each holding a
   kit named `alpha` (plus a second kit in one): kit rows `repo-a/alpha`, `repo-b/alpha`, …;
   per-tier aggregates equal the sums of the per-repo ledgers; re-route events from both
   repos tallied globally; `kits_dir` None; `kits_dirs` labels/paths in given order; markdown
   `- scanned` lines present.
6. `test_multi_dir_dollars_shared_projects_dir` — session ids from kits in BOTH repos with
   transcripts under two different project slugs of ONE temp projects dir: both priced,
   `sessions_priced == 2`, coverage full; then a third kit with an unpriceable id → coverage
   partial + a note naming the id; per-kit `cost` present under the NAMESPACED kit names;
   never a fabricated figure (the unpriceable kit's `cost` is None).
7. `test_explicit_label_lone_dir_namespaces` — `label=path` with a single dir → prefixed kit
   names + `kits_dirs` present.
8. `test_multi_kits_dir_rejected_outside_history` — the plain scorecard and `--live` with two
   `--kits-dir` values → nonzero exit naming `--history`.
9. `test_write_snapshot_grammar_and_traversal_guard` — valid date writes
   `<dir>/<date>.json` (mkdir -p, JSON round-trips, same-day overwrite = latest-wins);
   `"2026-1-1"`, `"../evil"`, `"2026-01-01x"`, `"20260101"` each raise ValueError; nothing is
   written on the ValueError paths.
10. `test_snapshot_cli_writes_only_dated_file` — full-tree byte snapshot before/after a
    `--history … --snapshot --snapshot-dir S --json` run: the ONLY delta is
    `S/<UTC-today>.json`; the printed card carries the `snapshot written:` note; the STORED
    card does not; the stored key set is the history card's.
11. `test_snapshot_and_trend_flag_rejections` — `--snapshot` without `--history`, `--trend`
    without `--history`, `--demo --history --snapshot` each exit nonzero.
12. `test_trend_zero_and_one_snapshot_degrade` — empty store dir and MISSING store dir → exit
    0, `points == []`, the `no snapshots` note, markdown `no snapshots — n/a`; one snapshot →
    exit 0, one rendered point, the `one snapshot — no trend yet (a trend needs at least 2
    points)` note.
13. `test_trend_two_snapshots_table` — two hand-written synthetic snapshot files: points
    ascend by date; rates match the stored `first_try/with_outcome`; a snapshot whose
    `dollars` is None renders `n/a` in the `Actual $` column while the other renders a
    dollar figure; the markdown header is the pinned
    `| Date | haiku | sonnet | opus | frontier | Kits | Actual $ |`.
14. `test_trend_skips_malformed_and_rogue` — a `rogue.json` (bad name), an unparseable
    `2026-01-03.json`, and a `2026-01-04.json` without a dict `tiers` → all skipped, one note
    each, remaining good snapshots still trend.
15. `test_trend_never_loads_pricing` — in-process: monkeypatch `rs.cr.load_pricing` to raise,
    call `rs.main(["--history", "--trend", "--snapshot-dir", <temp>])` (with ≥1 snapshot
    present) — succeeds, exit 0 (mirror the frozen pricing-free proof in
    `tests/test_routing_history.py`).
16. `test_readonly_non_snapshot_modes` — full-tree byte snapshots before/after (a) a
    multi-dir `--history` run and (b) a pure `--trend` run: identical trees (nothing written
    anywhere without `--snapshot`).
17. `test_prior_demos_regression` — `--demo --json`, `--demo --live --json`,
    `--demo --history --json`, `--demo --by-task --json` still yield their pinned numbers
    (the four tuples/dicts pinned in PLAN "Done looks like").
18. `test_trend_demo_pinned` — `--demo --history --trend --json` via subprocess: the D8
    pinned card (2 points, the dates, kits 2→3, the per-tier pairs, dollars > 0); markdown
    contains the pinned H1 + header + `2/3 (67%)`.
19. `test_default_snapshot_dir_gitignored` — `rs.DEFAULT_SNAPSHOT_DIR.name == "trends"` and
    `git -C <repo> check-ignore -q trends/2026-01-01.json` exits 0 (read-only git use).

**Acceptance.** All new tests pass; full suite green; the four frozen test files, the reused
scripts, `data/`, and `skills` untouched; safety greps clean; only this file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_crossrepo_trend.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py tests/test_routing_history.py tests/test_per_task_dollars.py bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data skills && echo 'T4 OK'
import re
text = open('tests/test_crossrepo_trend.py').read()
assert 'Path.home()' not in text
assert '~/.claude' not in text, "real home path in tests"
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
for name in ('test_parse_kits_dir_token_grammar', 'test_derive_repo_label_conventional_and_fallback',
             'test_resolve_kits_dirs_dedupe_and_collisions', 'test_single_dir_history_byte_shape',
             'test_multi_dir_namespaces_and_aggregates', 'test_multi_dir_dollars_shared_projects_dir',
             'test_explicit_label_lone_dir_namespaces', 'test_multi_kits_dir_rejected_outside_history',
             'test_write_snapshot_grammar_and_traversal_guard', 'test_snapshot_cli_writes_only_dated_file',
             'test_snapshot_and_trend_flag_rejections', 'test_trend_zero_and_one_snapshot_degrade',
             'test_trend_two_snapshots_table', 'test_trend_skips_malformed_and_rogue',
             'test_trend_never_loads_pricing', 'test_readonly_non_snapshot_modes',
             'test_prior_demos_regression', 'test_trend_demo_pinned',
             'test_default_snapshot_dir_gitignored'):
    assert f'def {name}' in text, f"missing case: {name}"
assert '--snapshot-dir' in text and '--projects-dir' in text and '--kits-dir' in text
print('safety greps ok')
PY
```

---

*Phase 2 end — dispatch `crossrepo-trend-reviewer` before starting Phase 3.*

---

## Phase 3 — Documentation and guardrails

### T5 — Write docs/ROUTING-TRENDS.md and point ROUTING-HISTORY.md's deferral at it
- status: done
- model: sonnet
- depends: T2
- independent: yes

**Brief.** Two pieces.

*Piece 1* — new file `docs/ROUTING-TRENDS.md` documenting what this kit built and what it
deliberately did not. Match the tone/format of `docs/ROUTING-HISTORY.md` (H1 + H2 sections,
concrete commands, no prices, no real model ids — tier names and the `fable` alias are fine,
no `/private/tmp/` paths, name constants instead of restating their values as prose facts).
Required structure — H1 `# Routing trends — cross-repo history and the snapshot time series`,
then EXACTLY these five H2s in order:

1. `## Cross-repo history — repeatable --kits-dir` — `--kits-dir` is repeatable on
   `--history`; with more than one dir (or any explicit `label=path` token) kit rows are
   namespaced `<label>/<kit>` so two repos' same-named kits don't collide; labels derive from
   the path (a conventional `<repo>/.claude/kits` dir → the repo directory's basename;
   anything else → the dir's basename, with `label=path` as the explicit override); duplicate
   labels are suffixed `-2`, `-3` + noted, never silently merged; tiers and re-route tallies
   aggregate globally; with a LONE plain `--kits-dir` (or none) the output is BYTE-IDENTICAL
   to before — unprefixed names, unchanged JSON key set. Cross-repo dollars ride the same
   single `--projects-dir` (the shared transcript store holds every repo's sessions and the
   lookup rglobs), with the degradation rules unchanged — missing transcripts noted +
   skipped, coverage labeled full/partial, never a fabricated figure. Example command:
   `python3 bin/routing_scorecard.py --history --kits-dir <repo-a>/.claude/kits --kits-dir
   <repo-b>/.claude/kits`.
2. `## The snapshot store` — `python3 bin/routing_scorecard.py --history --snapshot` writes
   the history card as `<YYYY-MM-DD>.json` (UTC date, latest-wins per day) under
   `--snapshot-dir` (default: the gitignored `trends/` dir at the repo root); this is the ONE
   sanctioned real write in the whole script — every other mode stays read-only, the write
   can only land inside the snapshot dir (the date grammar is validated), the stored card is
   pure history data, and `--snapshot` is rejected alongside `--demo`.
3. `## Reading the trend` — `python3 bin/routing_scorecard.py --history --trend [--json]`
   reads every stored snapshot and renders the per-tier first-try rate over time as a text table
   (rows = dates, columns = tiers, plus a kit count and an `Actual $` column filled only
   where a snapshot carried dollars); `--history --snapshot --trend` snapshots first, then
   renders the trend including today's point; the smoke is
   `python3 bin/routing_scorecard.py --demo --history --trend` (two synthetic repos, two
   dated snapshots); pure `--trend` scans no kits and loads no pricing.
4. `## The honesty rules` — a trend needs at least 2 snapshots: zero → n/a + note, one → the
   point plus a `no trend yet` note, never an extrapolation; malformed or rogue snapshot
   files are skipped + noted; dollars-over-time are surfaced only where snapshots carry them
   — never recomputed; a lone `--kits-dir` stays byte-identical; label collisions are
   suffixed + noted; every degraded shape exits 0.
5. `## Deliberately not built` — charts/plots of the trend (text table only; the snapshot
   store is the stable data contract for a future rendering layer); auto-snapshot scheduling
   (the user runs `--snapshot` when they choose); per-task/per-agent trend aggregation;
   auto-pin/auto-downgrade (unchanged, advisory by design); main-session model switching
   (still the upstream ask, tracked in `docs/FUSION-TIER1.md`).

*Piece 2* — in `docs/ROUTING-HISTORY.md`, append a new paragraph at the very end of the file.
The file currently ends with the per-task-dollars pointer paragraph whose final line is
exactly `cluster as a unit, never divided.` — if that anchor is not present verbatim, STOP
and report. Append (blank line before it):

```
Cross-repo and time-series aggregation have since shipped too — see
[ROUTING-TRENDS.md](ROUTING-TRENDS.md). `--kits-dir` is now repeatable on `--history` (kit
rows namespaced `<label>/<kit>`, tiers aggregated globally, dollars through the same single
projects dir under these same degradation rules), and `--history --snapshot` /
`--history --trend` store dated JSON snapshots in a gitignored `trends/` dir and render
per-tier first-try rate over time as a text table — a trend needs at least two snapshots,
and a lone `--kits-dir` still produces output byte-identical to this kit's.
```

Change nothing else in ROUTING-HISTORY.md — its five H2s and all prior text stay intact.

**Acceptance.** ROUTING-TRENDS.md exists with the H1 + exactly those five H2s in order;
mentions the repeatable `--kits-dir`, `label=path`, the namespacing rule, the byte-identical
lone-dir rule, `--snapshot`, `--trend`, `--demo --history --trend`, the `trends/` store, the
≥2-points rule, and the skipped-malformed rule; ROUTING-HISTORY.md gained exactly the pointer
paragraph and its H2 set is unchanged; greps clean; suite green; only ROUTING-TRENDS.md new.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && git diff --quiet -- skills && echo 'T5 OK'
import re
t = open('docs/ROUTING-TRENDS.md').read()
assert t.lstrip().startswith('# Routing trends — cross-repo history and the snapshot time series')
h2s = [l for l in t.splitlines() if l.startswith('## ')]
assert h2s == ['## Cross-repo history — repeatable --kits-dir', '## The snapshot store',
               '## Reading the trend', '## The honesty rules', '## Deliberately not built'], h2s
for s in ('--kits-dir', 'label=path', '<label>/<kit>', 'byte-identical', '--snapshot',
          '--trend', '--demo --history --trend', 'trends/', 'at least 2 snapshots',
          'no trend yet', 'skipped', 'routing_scorecard.py', 'read-only', 'first-try'):
    assert s in t, f'missing: {s}'
assert not re.search(r'claude-(fable|opus|sonnet|haiku)-?[0-9]', t), 'real model id in doc'
assert '/private/tmp' not in t
o = open('docs/ROUTING-HISTORY.md').read()
assert o.count('Cross-repo and time-series aggregation have since shipped') == 1, 'pointer missing/duplicated'
assert 'ROUTING-TRENDS.md' in o
assert o.count('Per-task dollar attribution has since shipped') == 1, 'prior pointer damaged'
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
- depends: T2
- independent: yes

**Brief.** ONE pinned insertion, nothing else. (The `For \`crossrepo-trend\` specifically:`
fence paragraph already exists in CLAUDE.md — the architect added it; do not touch it.) If
the anchor is not found verbatim, STOP and report.

*Insertion — CLAUDE.md, "## How to run things" code block.* Immediately AFTER the line:

```
python3 bin/routing_scorecard.py --demo --by-task # per-task dollars smoke (synthetic kit; shared warm agent + missing transcript honesty proofs)
```

insert this line into the same code block:

```
python3 bin/routing_scorecard.py --demo --history --trend # cross-repo + trend smoke (two synthetic repos, two dated snapshots, text trend table)
```

**Acceptance.** The insertion is present exactly once, directly after the `--demo --by-task`
line; the crossrepo-trend fence paragraph is present exactly once (pre-existing); no other
CLAUDE.md line changed by this task; suite green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && git diff --quiet -- skills && echo 'T6 OK'
c = open('CLAUDE.md').read()
line = 'python3 bin/routing_scorecard.py --demo --history --trend # cross-repo + trend smoke (two synthetic repos, two dated snapshots, text trend table)'
assert c.count(line) == 1, "run-line missing/duplicated"
i_bt = c.index('python3 bin/routing_scorecard.py --demo --by-task')
i_tr = c.index(line)
assert i_tr > i_bt and c[i_bt:i_tr].count('\n') == 1, "trend line not directly after the --demo --by-task line"
assert c.count('For `crossrepo-trend` specifically:') == 1, "fence paragraph missing/duplicated"
print('insertion ok')
PY
```

---

*Phase 3 end — dispatch `crossrepo-trend-reviewer`, then run PLAN.md's overall done-check.*
