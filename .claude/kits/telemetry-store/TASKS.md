# TASKS — telemetry-store

Repo root: `/path/to/polytropos`. Run every verify command
from there. Read `PLAN.md` and `GUARDRAILS.md` (same directory) first — D1–D8 and the
OUT-OF-SCOPE fence are binding.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch notes for the orchestrator: pass each task's `model` as the Agent tool's `model`
parameter when dispatching `telemetry-store-implementer`. **Warm-cluster hints:** T1, T2,
T3, T4 are `independent:` with disjoint primary files — fresh parallel fan-out, one message,
multiple Agent calls (T4 is the lone `opus` pin in the fan-out). T5 → T6 share
`bin/telemetry_snapshot.py` + `tests/test_telemetry_snapshot.py` but change model pin
(opus → sonnet), so NO warm cluster spans them — dispatch T6 fresh. T7 and T8 are
independent of each other; T9 is the finale and depends on T5, T6, T7. When quoting ledger
grammar in NOTES.md prose, always backtick the tokens (`outcome:`, `agent:`, `reroute:`,
`session:`, `reviewer:`, `defect:`) — unbackticked column-1 grammar parses as data.

Standing rules for every task:

- Stdlib only; unittest via `python3 -m unittest discover -s tests [-p '<file>.py'] -q`.
  Tests use temp dirs through the injectable seams — never the real
  `~/.claude`/`~/.codex`/`~/.copilot`, never the real `telemetry/` (T9's verify is the one
  sanctioned real-store exception).
- Additive only in the four touched tools: no existing flag, exit code, or output byte
  changes for existing invocations. Untouchable files are listed in GUARDRAILS.md.
- No prices, price ratios, or real model ids hardcoded. Sanctioned structural vocabulary
  for this kit: `STORE_SCHEMA_VERSION = 1`, `TELEMETRY_FILENAME_RE` (grammar
  `^\d{4}-\d{2}-\d{2}\.json$`), the source-name tuple `("cost_report", "codex_usage",
  "copilot_usage", "context_overview", "routing_history")`, envelope statuses
  `("ok", "error")`, and synthetic fixture values in tests.
- Every verify block ends with the layout test:
  `python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q` — it enforces
  this kit's GUARDRAILS.md presence/size and the CLAUDE.md ceiling, and it can fail.
- Do not commit or push.

## Phase 1 — Builder seams: every source tool exposes an importable pure builder

### T1 — `cost_report.py`: extract `build_report_payload`, add `--json` and `--projects-dir`
- status: done
- model: sonnet
- independent: yes (disjoint files from T2/T3/T4)

**Files:** `bin/cost_report.py`; `tests/test_cost_report.py` (extend only).

**Why:** `cost_report` is the Claude-side rotating source — markdown-only today, everything
inline in `main()`. The telemetry snapshot (T5) needs a pure builder; `--json` closes the
tool's machine-readability gap.

**Do:**
1. Extract the scan/aggregate body of `main()` (dedupe by message id, age filter, per-model
   buckets, per-session table, downgrade-candidate math, unknown models, parse errors) into
   `build_report_payload(projects_dir, days=30, top=10, mode=None) -> dict`. Signature is
   pinned by PLAN D3. `mode=None` resolves from pricing exactly as `main` does today
   (`pricing.get("billing_mode", "api")`). Missing `projects_dir` → return a payload with
   `"found": False` and a label `f"transcript directory absent: {projects_dir}"` — the
   builder never exits.
2. Payload keys (superset allowed, these required): `schema_version` (1), `found`, `days`,
   `top`, `mode`, `projects_dir` (str), `pricing_cached_date`, `totals` (dict with at least
   `usd`, `sessions`, `tokens`), `by_model` (list of dicts, one per model, each with at
   least `model`, `usd`, and the token-bucket fields `main` tallies today),
   `sessions` (list, top-N per current sort, each with at least `session_id`, `project`,
   `usd`, `models`), `downgrade_candidates` (list), `unknown_models` (list),
   `parse_errors` (count int), `labels` (list of str). `labels` must include
   `f"billing mode: {mode}"` and, when `unknown_models` is non-empty,
   `"unpriced models present"`. Numbers are the SAME numbers the markdown prints — computed
   once, rendered twice.
3. Rework `main()` to: accept `argv=None` and pass it to `parse_args` (additive — the
   existing test patches `sys.argv` and calls `cr.main()` bare, which still works); parse
   args (add `--json`, and `--projects-dir` with default `None`);
   resolve the projects dir as `Path(args.projects_dir) if args.projects_dir else
   PROJECTS_DIR` **inside `main`, at call time** — existing tests monkeypatch the
   `PROJECTS_DIR` global (see `tests/test_cost_report.py` ≈ line 240) and MUST keep working
   (PLAN R1). Then call the builder once; `--json` → `print(json.dumps(payload, indent=2))`;
   otherwise render the markdown FROM the payload. Markdown for existing invocations stays
   byte-identical, including the absent-dir `sys.exit(f"No transcript directory at ...")`
   behavior when `--json` is not passed; with `--json`, absent dir prints the
   `found: false` payload and exits 0 (new flag, new honest shape — mirrors
   `codex_usage`'s absent JSON).
4. Extend `tests/test_cost_report.py`: builder happy path over the existing synthetic
   fixture (assert required keys, `schema_version == 1`, totals match the markdown path),
   absent-dir payload (`found` False + absence label, no exception), `--json` CLI path via
   `main()` with patched stdout, and markdown-unchanged regression (run `main()` twice on
   the same fixture, once pre-existing-style — the existing
   `test_main_report_dedupes_ages_and_prices_correctly` must pass unmodified).

**Acceptance:** builder importable and pure (no `sys.exit`, no printing); all pinned keys
present; existing tests pass unmodified; new tests cover found/absent/CLI-json.

**Verify:**
```bash
cd /path/to/polytropos
python3 -m unittest discover -s tests -p 'test_cost_report.py' -q
python3 - <<'PY'
import importlib.util, inspect, json, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("cost_report", "bin/cost_report.py")
cr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr)
sig = inspect.signature(cr.build_report_payload)
assert list(sig.parameters) == ["projects_dir", "days", "top", "mode"], sig
with tempfile.TemporaryDirectory() as td:
    p = cr.build_report_payload(Path(td) / "nope")
assert p["schema_version"] == 1 and p["found"] is False, p
assert any("absent" in l for l in p["labels"]), p["labels"]
for k in ("found","days","top","mode","totals","by_model","sessions","labels"):
    assert k in p, k
json.dumps(p)  # payload must be JSON-serializable
print("T1 probe OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T2 — `copilot_usage.py`: extract `build_usage_payload`, add `--json`
- status: done
- model: sonnet
- independent: yes

**Files:** `bin/copilot_usage.py`; `tests/test_copilot_usage.py` (extend only).

**Why:** the Copilot-side rotating source; markdown-only today, everything inline in
`main()` (≈ line 302 onward). T5 needs the pure builder.

**Do:**
1. Extract the aggregation body of `main()` (session collection via `collect_sessions`,
   age filter, per-model buckets, per-turn merged table, per-session rows, totals for USD /
   AIU / premium requests / AIC) into `build_usage_payload(session_dir, days=30, top=10) ->
   dict` (signature pinned by PLAN D3; it loads pricing itself like `main` does). Missing
   `session_dir` → payload with `"found": False` plus label
   `f"session-state directory absent: {session_dir}"` — the builder never exits.
2. Payload keys (superset allowed, these required): `schema_version` (1), `found`, `days`,
   `top`, `session_dir` (str), `totals` (dict with at least `usd`, `aic`, `aiu`,
   `premium_requests`, `sessions`), `by_model` (list of per-model dicts with at least
   `model`, `usd`, `aic`, `sessions`, token fields), `per_turn_output` (list),
   `top_sessions` (list, each with at least `session_id`, `usd`, `models`),
   `multi_model_sessions` (int), `read_errors` (count int), `labels` (list). `labels` must
   include `"token-priced estimate (est.) — Copilot bills in premium requests/AIC"` and,
   when `multi_model_sessions > 0`, `"multi-model sessions attributed to last model (≈)"`.
3. `main()` gains `--json`: print the payload; without it, render the EXACT current
   markdown from the payload (existing invocations byte-identical, including the
   absent-dir `sys.exit(f"No session-state directory at ...")` when `--json` absent; with
   `--json`, absent dir prints the `found: false` payload, exit 0). `--copilot-home` and
   `--session-dir` flags keep their exact current semantics feeding `session_dir`.
4. Extend `tests/test_copilot_usage.py` using its existing synthetic fixtures: builder
   happy path (required keys, totals equal the markdown path's numbers), absent-dir
   payload, `--json` CLI path, and an unmodified pass of every pre-existing test.

**Acceptance:** builder pure and importable; markdown byte-identical for existing
invocations; the est./≈ honesty labels present in `labels`; suite green.

**Verify:**
```bash
cd /path/to/polytropos
python3 -m unittest discover -s tests -p 'test_copilot_usage.py' -q
python3 - <<'PY'
import importlib.util, inspect, json, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("copilot_usage", "bin/copilot_usage.py")
cp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
sig = inspect.signature(cp.build_usage_payload)
assert list(sig.parameters) == ["session_dir", "days", "top"], sig
with tempfile.TemporaryDirectory() as td:
    p = cp.build_usage_payload(Path(td) / "nope")
assert p["schema_version"] == 1 and p["found"] is False, p
assert any("absent" in l for l in p["labels"]), p["labels"]
for k in ("found","days","totals","by_model","labels"):
    assert k in p, k
json.dumps(p)
print("T2 probe OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T3 — `codex_usage.py`: extract a unified `build_usage_payload` behind the existing CLI
- status: done
- model: sonnet
- independent: yes

**Files:** `bin/codex_usage.py`; `tests/test_codex_usage.py` (extend only).

**Why:** `codex_usage` already has `--json`, but its output is three DIFFERENT branch
shapes (`absent` / `activity_only` / `priced` — see `_print_absent`,
`_print_activity_only`, `_print_priced` ≈ lines 440–540) printed from state interleaved
through `main()`. T5 needs ONE unified payload from one scan pass.

**Do:**
1. Extract `main()`'s scan/aggregate body (activity files, rollout iteration, per-model
   pricing buckets, honesty-ladder branch choice) into `build_usage_payload(codex_home,
   days=30, top=10) -> dict` (signature pinned by PLAN D3). One scan pass; the builder
   never prints, never exits.
2. Unified payload keys (superset allowed, these required): `schema_version` (1), `found`
   (False only for the absent branch), `priced` (True only for the priced branch),
   `branch` (`"absent" | "activity_only" | "priced"` — same vocabulary the JSON already
   uses), `days`, `codex_home` (str), `labels` (list), plus every field the corresponding
   existing `--json` branch dict carries today (same names, same values). `labels` must
   include: absent → `f"codex home absent: {codex_home}"`; activity_only → `"activity
   counted, unpriced"`; priced → `"API-price estimate from found tokens (est.) — never a
   bill"`.
3. `main()` calls the builder once, then routes to the three existing print helpers,
   passing what they need FROM the payload (refactor their parameters as needed — they are
   private helpers). Existing CLI output — markdown AND all three `--json` branch shapes —
   stays byte-identical for existing invocations: the printed JSON keeps exactly its
   current keys (do NOT add `schema_version`/`found`/`labels` to the printed shapes; the
   unified payload is the importable seam, not the CLI contract).
4. Extend `tests/test_codex_usage.py` with builder tests over the existing fixtures: one
   per branch asserting `branch`, `found`, `priced`, `labels`, and value-equality between
   the payload and the corresponding printed `--json` dict for the branch's shared keys.
   Every pre-existing test passes unmodified.

**Acceptance:** one scan path feeds builder and CLI; three branches unified; CLI output
byte-identical; suite green.

**Verify:**
```bash
cd /path/to/polytropos
python3 -m unittest discover -s tests -p 'test_codex_usage.py' -q
python3 - <<'PY'
import importlib.util, inspect, json, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("codex_usage", "bin/codex_usage.py")
cx = importlib.util.module_from_spec(spec); spec.loader.exec_module(cx)
sig = inspect.signature(cx.build_usage_payload)
assert list(sig.parameters) == ["codex_home", "days", "top"], sig
with tempfile.TemporaryDirectory() as td:
    p = cx.build_usage_payload(Path(td) / "nope")
assert p["schema_version"] == 1 and p["found"] is False and p["branch"] == "absent", p
assert p["priced"] is False and any("absent" in l for l in p["labels"]), p
json.dumps(p)
print("T3 probe OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T4 — `routing_scorecard.py`: extract pure `assemble_history_card` from `run_history`
- status: done
- model: opus
- independent: yes

**Files:** `bin/routing_scorecard.py`; `tests/test_routing_history.py` (extend only).

**Why:** the `--history` card carries the cross-kit dollar verdict — the single most
evaporation-exposed number in the repo. Its assembly today lives inside `run_history(args)`
(≈ line 2699), which prints and `sys.exit`s. T5 needs the card as a return value. This is
the highest-blast-radius task (PLAN R2): ~3000-line module, `bench_routing` imports it,
`build_history(kits_dir, records, kit_costs, dollars, notes)` is called positionally by the
untouchable bench file.

**Do:**
1. Add `assemble_history_card(kits_dirs, projects_dir=None, tasks_dir=(), include=(),
   no_subagents=False, vs=None) -> card` (signature pinned by PLAN D3). Move `run_history`'s
   assembly into it VERBATIM: `resolve_kits_dirs` → dir existence check → namespaced vs
   plain scan → the `--tasks-dir/--include` ignored-note → session-id union → the dollars
   degradation ladder (`kit_cost_summary`, shared-session note, aggregate, coverage) →
   `build_history(primary_dir, records, kit_costs, dollars, notes)` → the namespaced
   `kits_dir`/`kits_dirs` fixups. Two behavior translations ONLY: `sys.exit(f"kits dir not
   found: ...")` and `sys.exit(str(e))` (counterfactual resolution) become
   `raise ValueError(<same message>)`; `projects_dir=None` resolves to
   `str(sc.DEFAULT_PROJECTS_DIR)` exactly as the `--projects-dir` argparse default does
   today (≈ line 2861). The function never prints and returns the card BEFORE any
   `--snapshot` tail note.
2. Rework `run_history(args)` to call it inside `try/except ValueError as e:
   sys.exit(str(e))` and keep ONLY the CLI tail: `--snapshot` write, `--trend` handoff,
   the `snapshot written:` note, and the final print. Byte-identical stdout and identical
   exit codes/messages for every existing invocation.
3. Nothing else in the module changes: no signature, flag, exit-code, or demo-number edits;
   `build_history`, `scan_kits`, `kit_cost_summary`, `resolve_kits_dirs`,
   `write_snapshot`/`read_snapshots`/`build_trend` untouched.
4. Extend `tests/test_routing_history.py` (importlib pattern already used there): a
   temp-kits-dir fixture asserting `assemble_history_card` returns the same card dict that
   `--history --json` prints for the same dirs (build both, `assertEqual`), a missing-dir
   `ValueError` with the exact message, and a `projects_dir=None` default-resolution check
   (assert it equals `str(<loaded session_cost>.DEFAULT_PROJECTS_DIR)` — compare against
   the module constant, never a hardcoded home path).

**Acceptance:** pure function returns the identical card; CLI byte-identical;
`tests/test_routing_history.py`, `tests/test_crossrepo_trend.py`,
`tests/test_bench_routing.py`, `tests/test_role_ledger.py`, `tests/test_per_task_dollars.py`
all pass unmodified except the sanctioned additions to `test_routing_history.py`.

**Verify:**
```bash
cd /path/to/polytropos
python3 -m unittest discover -s tests -p 'test_routing_history.py' -q
python3 -m unittest discover -s tests -p 'test_bench_routing.py' -q
python3 -m unittest discover -s tests -p 'test_crossrepo_trend.py' -q
python3 bin/routing_scorecard.py --demo --history > /tmp/telemetry_t4_demo.md
grep -q "Routing history" /tmp/telemetry_t4_demo.md
python3 - <<'PY'
import importlib.util, inspect, tempfile
spec = importlib.util.spec_from_file_location("routing_scorecard", "bin/routing_scorecard.py")
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
sig = inspect.signature(rs.assemble_history_card)
assert list(sig.parameters) == ["kits_dirs","projects_dir","tasks_dir","include","no_subagents","vs"], sig
try:
    rs.assemble_history_card(["/nonexistent/kits/dir"])
    raise AssertionError("expected ValueError for missing kits dir")
except ValueError as e:
    assert "kits dir not found" in str(e), e
with tempfile.TemporaryDirectory() as td:  # empty projects dir — no real ~/.claude read
    card = rs.assemble_history_card([".claude/kits"], projects_dir=td)
assert isinstance(card, dict) and "tiers" in card and "kits" in card, sorted(card)
assert not any(str(n).startswith("snapshot written") for n in card.get("notes", []))
print("T4 probe OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T4b — Phase-1 review remediation (orchestrator-added)
- status: done
- model: opus
- depends: T1, T2, T3, T4

Added after the Phase-1 opus review confirmed 6 findings (F6 resolved via T5 brief amendment).
Fixed: F1 `assemble_history_card([])` → ValueError; F2 `found` = evidence present with
`no transcripts in window` label (+ additive `dir_present` gate keeping CLI byte-identical);
F3 est. caveat into cost_report labels on every branch; F4 codex transport under one `_render`
key, rows capped at `top`; F5 copilot `session_rows` → `_render`. New
`tests/test_builder_uniformity.py` — the four builders diffed against EACH OTHER.

**Verify:** uniformity suite green; 76-scenario git-HEAD byte-identity harness, 0 mismatches;
two mutations observed failing (incl. one that proved the harness itself can fail).

## Phase 2 — The store: capture engine, then read side

### T5 — NEW `bin/telemetry_snapshot.py`: registry, envelope, capture

**[AMENDED BY THE ORCHESTRATOR AFTER THE PHASE-1 REVIEW — three binding additions.]**
1. **Strip render transport at capture:** the envelope `payload` is the builder's dict MINUS
   every top-level key starting with `_` (builders carry render-only scratch under a single
   `_render` key after T4b). Assert in tests that no stored envelope contains a `_`-prefixed
   top-level payload key.
2. **Dollars-state labels (review F6):** `card["dollars"] is None` has TWO distinct states,
   discriminated by exact note strings. Rule: if any note equals/starts
   `"no session: lines found"` → label `"dollars n/a (quality-only history)"`; if any note
   contains `"session: lines found but no transcript priced"` → label
   `"dollars n/a — sessions recorded but transcripts already evaporated/unpriced"`. NEVER
   emit the quality-only label for the second state: that state is the evaporation this kit
   exists to record, and mislabeling it is fabricated honesty. Cover both in tests with
   synthetic kits dirs.
3. After T4b, `build_report_payload` reports a present-but-EMPTY window as `found: False`
   with a no-evidence label — the T5 probe/tests expecting an "absent"-style label on an
   empty temp projects dir are correct as written and must key on `found` + label presence,
   not on directory existence.
- status: done
- model: opus
- depends: T1, T2, T3, T4

**Files:** NEW `bin/telemetry_snapshot.py`; NEW `tests/test_telemetry_snapshot.py`.

**Why:** the keystone. One tool, the only writer under a telemetry store, capturing five
sources through import-and-call (PLAN D2/D3/D5).

**Do:**
1. Module preamble: docstring stating the store law (only writer; capture-date is always
   the run date; late capture sanctioned, reconstruction forbidden — cite PLAN D5);
   constants `STORE_SCHEMA_VERSION = 1`, `TELEMETRY_FILENAME_RE =
   re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")` (comment: same grammar as
   `routing_scorecard.SNAPSHOT_FILENAME_RE`), `_DATE_RE` for `^\d{4}-\d{2}-\d{2}$`,
   `PLUGIN_ROOT = Path(__file__).resolve().parents[1]`, `DEFAULT_STORE_DIR = PLUGIN_ROOT /
   "telemetry"`, `SOURCES = ("cost_report", "codex_usage", "copilot_usage",
   "context_overview", "routing_history")`. Sibling modules load lazily via the house
   importlib helper (copy the `_load` pattern from `bin/bench_routing.py` ≈ line 118);
   zero `Path.home()` anywhere in this module — home-dir defaults come from the LOADED
   modules' own `DEFAULT_*` constants, resolved only when a flag was not passed.
2. Five collector functions, each returning `(payload_or_None, period_dict, labels, notes)`:
   - `cost_report`: `cr.build_report_payload(projects_dir, days=days)`; period
     `{"days": days}`; labels = `payload["labels"]`.
   - `codex_usage`: `cx.build_usage_payload(codex_home, days=days)`; period
     `{"days": days}`; labels = `payload["labels"]`.
   - `copilot_usage`: `cp.build_usage_payload(copilot_home / "session-state", days=days)`;
     period `{"days": days}`; labels = `payload["labels"]`.
   - `context_overview`: `cw.build_overview("all", overview_days, 10, projects_dir,
     codex_home, copilot_home)`; period `{"days": overview_days}`; labels derived
     mechanically: for each section with `found` False (or absent), append
     `f"{name} section absent"`.
   - `routing_history`: `rs.assemble_history_card([kits_dir] if kits_dir else [],
     projects_dir=projects_dir)`; period `{"description": "cumulative kit ledger as of
     capture"}`; labels derived: `dollars` None → `"dollars n/a (quality-only history)"`,
     else `f"dollars coverage: {dollars['coverage']} ({dollars['kits_with_sessions']}/
     {dollars['kits_total']} kits)"`. A `ValueError` from assembly propagates to the
     error-envelope path like any collector exception.
   Labels are LIFTED, never authored beyond these mechanical rules (PLAN D2).
3. `capture(store_dir, date_str, opts) -> summary`: for each source in `SOURCES`, run the
   collector under `try/except Exception`; success → envelope `status "ok"` with the
   payload verbatim, `source_schema_version = payload.get("schema_version")` (None when
   absent — e.g. the routing card's own versioning lives inside the card); exception →
   envelope `status "error"`, `payload` None, `notes` gaining `f"collector failed:
   {e!r}"`. Envelope keys EXACTLY per PLAN D2: `store_schema_version`, `source`,
   `source_schema_version`, `captured_at` (UTC ISO seconds), `capture_date`, `period`,
   `status`, `labels`, `notes`, `payload`. Write to
   `<store_dir>/<source>/<date_str>.json` (`mkdir(parents=True, exist_ok=True)`,
   `json.dumps(..., indent=2) + "\n"`, plain overwrite = latest-wins). `date_str` defaults
   to UTC today and is validated against `_DATE_RE` FIRST, raising `ValueError` otherwise
   (path-traversal guard, `write_snapshot` precedent). There is NO flag or parameter that
   sets a filename date different from the run date — the only `--date` override exists for
   tests via a `capture(...)` argument, and the CLI does NOT expose it (D5: no backdating
   flag).
4. `main(argv=None)`: flags `--store-dir` (default `str(DEFAULT_STORE_DIR)`),
   `--projects-dir`, `--codex-home`, `--copilot-home` (all default `None` → the loaded
   modules' `DEFAULT_*`), `--kits-dir` (default `None` → scorecard default),
   `--days` (30), `--overview-days` (7), `--json`. Default action: capture, then print a
   per-source summary — one line per source: name, status, label count, path written —
   as markdown, or a summary dict with `--json`. Exit 0 when every envelope wrote and ≥ 1
   source has `status "ok"`; exit 1 when all five errored (envelopes still written); exit
   2 on an unwritable store dir. Never invokes any CLI, never prints payload contents
   (metadata only — keep stdout small).
5. NEW `tests/test_telemetry_snapshot.py` (importlib load pattern from
   `tests/test_cost_report.py`): all fixtures in temp dirs. Cover at minimum: five files
   written with empty temp homes and a synthetic kits dir (statuses all `"ok"`, absence
   labels present — e.g. cost_report envelope labels contain "absent"); envelope key set
   EXACTLY the ten pinned keys (`set(...)` compare); `capture_date` equals filename stem
   equals the passed date; bad date (`"2026-7-1"`, `"../evil"`) raises `ValueError` before
   any write; same-day re-run overwrites (file count stable, `captured_at` changes); a
   collector forced to raise (monkeypatch one collector) → `status "error"`, `payload`
   None, note present, exit path still writes the other four; `routing_history` envelope
   over a synthetic kits dir with a `TASKS.md`+`NOTES.md` kit carries the quality-only
   dollars label; JSON serializability of every envelope.

**Acceptance:** five envelopes, pinned key set, honest labels, no shelling out and no
`Path.home()` — and because the verify greps for the tokens themselves, the strings
`subprocess`, `os.system`, and `Path.home()` must not appear ANYWHERE in
`bin/telemetry_snapshot.py`, comments and docstrings included (phrase the docstring as
"spawns no processes"); tests green.

**Verify:**
```bash
cd /path/to/polytropos
python3 -m unittest discover -s tests -p 'test_telemetry_snapshot.py' -q
grep -cE "subprocess|os\.system" bin/telemetry_snapshot.py | grep -qx 0
grep -cF "Path.home()" bin/telemetry_snapshot.py | grep -qx 0
python3 - <<'PY'
import json, tempfile, subprocess, sys, re
from pathlib import Path
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    for d in ("store","proj","codex","copilot","kits"): (td/d).mkdir()
    r = subprocess.run([sys.executable, "bin/telemetry_snapshot.py",
        "--store-dir", str(td/"store"), "--projects-dir", str(td/"proj"),
        "--codex-home", str(td/"codex"), "--copilot-home", str(td/"copilot"),
        "--kits-dir", str(td/"kits")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    files = sorted(p.relative_to(td/"store").as_posix() for p in (td/"store").rglob("*.json"))
    assert len(files) == 5, files
    srcs = sorted(f.split("/")[0] for f in files)
    assert srcs == sorted(("cost_report","codex_usage","copilot_usage","context_overview","routing_history")), srcs
    env = json.loads((td/"store"/files[0]).read_text())
    assert set(env) == {"store_schema_version","source","source_schema_version","captured_at",
                        "capture_date","period","status","labels","notes","payload"}, sorted(env)
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", env["capture_date"])
    assert env["capture_date"] == Path(files[0]).stem
print("T5 probe OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```
(The probe's `subprocess.run` launches `python3 bin/telemetry_snapshot.py` itself against
temp dirs — the sanctioned smoke of OUR OWN tool, not a harness CLI; the grep clauses prove
the tool itself spawns nothing.)

### T6 — Read side: `--list`, tolerant `read_source_snapshots`, `--demo`
- status: done
- model: sonnet
- depends: T5

**Files:** `bin/telemetry_snapshot.py`; `tests/test_telemetry_snapshot.py` (extend).

**Why:** the store needs an honest read surface (Done-means 2) and a future trend kit needs
the tolerant reader seam (PLAN D6); the repo's house style gives every tool a synthetic
`--demo` smoke.

**Do:**
1. `read_source_snapshots(store_dir, source) -> (dated_envelopes, notes)` modeled directly
   on `routing_scorecard.read_snapshots` (≈ line 1819): missing dir → `([], [f"no
   snapshots for source {source!r} under {store_dir}"])`; only `*.json` considered, sorted
   by name (dates ascend); a name failing `TELEMETRY_FILENAME_RE` → skip +
   `f"rogue snapshot file skipped: {source}/{name}"`; unreadable/undecodable → skip +
   note; decoded JSON not a dict or missing a dict-or-null `payload` key → skip + note.
   Survivors are `(date_str, envelope)` tuples. Unknown envelope keys are IGNORED (R5
   forward-tolerance).
2. `--list [--json]`: enumerate subdirs of the store dir; for each registry source AND any
   unknown subdir (flagged `f"unregistered source dir: {name}"` in notes, still listed),
   show snapshot count, first date, last date, latest status, latest labels. Missing store
   dir → the friendly line `f"no telemetry store at {store_dir} — run a capture first"`
   and exit 0 (degrade with a note, never a crash — nothing existing may break when the
   store is absent). No dollar figures in `--list` output at all (GUARDRAILS: dollars never
   merge — the listing shows counts/dates/labels only).
3. `--demo`: fully synthetic, no real data — create a temp dir, run `capture` against
   empty synthetic homes plus a tiny synthetic kits dir built in-place (one kit, two
   `outcome:` lines — same species as `run_history_demo`'s synthetic kits), then render
   the capture summary and the `--list` view of the temp store, then clean up. Everything
   inside the tool's own temp dir; deterministic enough to smoke-test (statuses, source
   names, label presence — not timestamps).
4. Extend tests: reader tolerance matrix (missing dir, rogue name, undecodable file,
   non-dict, missing `payload`, unknown-key envelope kept), ascending date order,
   `--list` over a fixture store with two dates + one rogue file (assert the note and
   both dates render), `--list` on a missing store dir exits 0 with the friendly line,
   `--demo` exits 0 and its stdout names all five sources.

**Acceptance:** reader never crashes and never guesses; `--list` honest on absent store;
`--demo` self-contained; suite green.

**Verify:**
```bash
cd /path/to/polytropos
python3 -m unittest discover -s tests -p 'test_telemetry_snapshot.py' -q
python3 bin/telemetry_snapshot.py --demo > /tmp/telemetry_t6_demo.txt
grep -q "routing_history" /tmp/telemetry_t6_demo.txt
grep -q "context_overview" /tmp/telemetry_t6_demo.txt
python3 - <<'PY'
import importlib.util, json, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("telemetry_snapshot", "bin/telemetry_snapshot.py")
ts = importlib.util.module_from_spec(spec); spec.loader.exec_module(ts)
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    (td / "cost_report").mkdir(parents=True)
    (td / "cost_report" / "2026-07-24.json").write_text(json.dumps(
        {"payload": None, "status": "ok", "unknown_future_key": 1}))
    (td / "cost_report" / "rogue.json").write_text("{}")
    (td / "cost_report" / "2026-07-25.json").write_text("NOT JSON")
    cards, notes = ts.read_source_snapshots(td, "cost_report")
    assert [d for d, _ in cards] == ["2026-07-24"], cards
    assert any("rogue" in n for n in notes) and any("2026-07-25" in n for n in notes), notes
    empty, enotes = ts.read_source_snapshots(td, "codex_usage")
    assert empty == [] and enotes, enotes
print("T6 probe OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

## Phase 3 — Wiring, law, and the first real capture

### T7 — `.gitignore` and `CLAUDE.md`: the store becomes repo law
- status: done
- model: haiku
- depends: T5
- independent: of T6 and T8

**Files:** `.gitignore`; `CLAUDE.md`.

**Why:** D1 (gitignored store) must be in force BEFORE T9's real capture ever writes a
file, and the store law belongs beside the journal/memory invariants.

**Do:**
1. Append to `.gitignore`, after the `/prefs/` block, exactly:

   ```
   # telemetry snapshot store (personal cost data — never committed)
   /telemetry/
   ```

   The leading slash is load-bearing (root-anchored — precedent: `/memory/`).
2. In `CLAUDE.md`, append this bullet to the end of the `## Invariants` list, verbatim:

   ```
   - **The telemetry store (`telemetry/` at the repo root) is gitignored personal data,
     written by `bin/telemetry_snapshot.py` ONLY.** It captures other tools' JSON output
     into dated envelopes (`telemetry/<source>/<YYYY-MM-DD>.json`); the filename date is
     always the capture date, honesty labels (est., unpriced, partial coverage) ride
     inside every envelope, and no envelope is ever hand-authored, backdated, or
     reconstructed from prose — late capture of a still-existing source is fine,
     fabricating an evaporated one never is. Readers degrade with a note when the store
     is absent, tests use temp `--store-dir` fixtures only, and nothing bulk-injects the
     store into a session's context.
   ```

3. In `CLAUDE.md`'s `## How to run things` code block, after the `context_weight.py
   session` line, add exactly:

   ```
   python3 bin/telemetry_snapshot.py               # capture today's telemetry snapshots (reads home dirs read-only; writes only gitignored telemetry/; lands with the telemetry-store kit)
   python3 bin/telemetry_snapshot.py --list        # what the telemetry store holds per source (tolerant of an absent store)
   ```

4. Change nothing else in either file.

**Acceptance:** both files carry the exact text; CLAUDE.md ≤ 16000 bytes; layout test
green.

**Verify:**
```bash
cd /path/to/polytropos
grep -qx '/telemetry/' .gitignore
grep -q 'telemetry snapshot store' .gitignore
grep -q 'written by `bin/telemetry_snapshot.py` ONLY' CLAUDE.md
grep -q 'bin/telemetry_snapshot.py --list' CLAUDE.md
python3 - <<'PY'
from pathlib import Path
size = Path("CLAUDE.md").stat().st_size
assert size <= 16000, f"CLAUDE.md is {size} bytes"
text = Path("CLAUDE.md").read_text()
assert text.count("telemetry_snapshot.py") >= 3
print("T7 probe OK")
PY
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T8 — `skills/journal/SKILL.md`: the daily flow runs the snapshot
- status: done
- model: sonnet
- depends: T5
- independent: of T6 and T7

**Files:** `skills/journal/SKILL.md` (body only — YAML frontmatter untouched).

**Why:** D4 — the journal is the one flow that already runs daily; a skill-body step gives
the store its cadence with zero code change and zero new writers.

**Do:**
1. Directly after the `## Collect the digest` section's closing paragraph (the one ending
   "never counted into `usd_priced`.") and BEFORE `## Write the summaries (in this session
   — default)`, insert a new H2 section:

   ```
   ## Persist today's telemetry (right after collecting)

   Capture the day's analytics into the durable store — the transcript dirs the digest
   reads from ROTATE, and this snapshot is what survives:

   ```bash
   python3 "$ROOT/bin/telemetry_snapshot.py"
   ```

   It imports the analytics modules and calls their builders directly — read-only over
   `~/.claude`, `~/.codex`, and `~/.copilot`, spawning no CLI and writing only under the
   gitignored `telemetry/` (dated envelopes, one per source per day; same-day re-runs
   overwrite). Best-effort: if it fails, note the failure and continue with the journal —
   the snapshot never blocks the summaries.
   ```

   (Adjust the inner code fence nesting as needed so the document renders — the outer
   fence above is quotation, not content.)
2. Change nothing else in the file; the frontmatter and every other section stay
   byte-identical.

**Acceptance:** new section present between the two existing sections, frontmatter
untouched, no `journal_*.py` diff anywhere in this task.

**Verify:**
```bash
cd /path/to/polytropos
python3 - <<'PY'
from pathlib import Path
text = Path("skills/journal/SKILL.md").read_text()
i_collect = text.index("## Collect the digest")
i_new = text.index("## Persist today's telemetry")
i_write = text.index("## Write the summaries")
assert i_collect < i_new < i_write, (i_collect, i_new, i_write)
assert 'telemetry_snapshot.py"' in text
assert "never blocks the summaries" in text
head = text.split("---")[1]
assert "name: journal" in head and "telemetry" not in head  # frontmatter untouched
print("T8 probe OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T9b — Final-review remediation (orchestrator-added)
- status: done
- model: opus
- depends: T9

Added after the final opus review confirmed 6 findings. Fixed: F3 an error envelope never
replaces an ok envelope (kept-note on the receipt); F5 filename date now LOCAL (journal-day
aligned), `captured_at` stays UTC; F1 carry-cost caveats lifted per-harness into
context_overview labels; F2 found-but-empty gets its own label (extended to codex
`rollouts_scanned` — disclosed deviation); F4 the `--list` claim corrected to the real
contract (no payload reads = no cross-source aggregation); F6 demo-safety test made hermetic
and proven failable. Both mutation tests observed failing; real store refreshed through fixed
code.

**Verify:** orchestrator re-ran the exact F3 destruction repro → preservation; real
context_overview envelope carries 3 per-harness caveats; `--list` shows 0 label-less
envelopes; suite 1419.

### T9 — First real capture: today's still-derivable history stops evaporating
- status: done
- model: sonnet
- depends: T5, T6, T7

**Files:** none edited — this task RUNS the tool. The ONLY writes are under the real,
gitignored `telemetry/` (sanctioned for this task alone — GUARDRAILS).

**Why:** PLAN D5's urgent half. The cross-kit dollars are priceable from exactly one
surviving transcript; every day of delay is data lost. This is late capture of real,
still-existing sources — the opposite of reconstruction.

**Do:**
1. From the repo root run `python3 bin/telemetry_snapshot.py` with NO dir overrides (real
   defaults: real home dirs read-only, real `.claude/kits`, store at `telemetry/`).
2. Run `python3 bin/telemetry_snapshot.py --list` and read it. Confirm honesty: any source
   whose home dir is absent on this machine must show its absence label — do not "fix"
   that by hand-editing an envelope (forbidden forever).
3. Confirm git hygiene: `git status --porcelain` shows NOTHING under `telemetry/` (the T7
   ignore line is doing its job).
4. Report, faithfully: which sources captured `status "ok"`, which labels appeared
   (especially the `routing_history` dollars-coverage label), and the store's total size.

**Acceptance:** five envelopes exist under the real `telemetry/` dated today (UTC);
`cost_report`'s payload has `found` true (45 Claude transcripts existed at kit-authoring
time — if THIS fails, transcripts have rotated to zero; report it, do not fake it);
`routing_history`'s envelope carries a dollars label; nothing under `telemetry/` is
committable.

**Verify:**
```bash
cd /path/to/polytropos
python3 - <<'PY'
import json, re
from datetime import datetime, timezone
from pathlib import Path
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
store = Path("telemetry")
sources = ("cost_report","codex_usage","copilot_usage","context_overview","routing_history")
for s in sources:
    p = store / s / f"{today}.json"
    assert p.is_file(), f"missing {p}"
    env = json.loads(p.read_text())
    assert env["capture_date"] == today and env["source"] == s, (s, env["capture_date"])
    assert env["status"] in ("ok","error"), env["status"]
    assert p.stat().st_size < 1_000_000, f"{p} exceeds the 1 MB envelope tripwire (PLAN D7)"
cr_env = json.loads((store / "cost_report" / f"{today}.json").read_text())
assert cr_env["status"] == "ok" and cr_env["payload"]["found"] is True, "cost_report capture not ok"
rh_env = json.loads((store / "routing_history" / f"{today}.json").read_text())
assert any("dollars" in l for l in rh_env["labels"]), rh_env["labels"]
print("T9 probe OK — history persisted:", today)
PY
git status --porcelain > /tmp/telemetry_t9_git.txt
grep -c "telemetry/" /tmp/telemetry_t9_git.txt | grep -qx 0
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```
