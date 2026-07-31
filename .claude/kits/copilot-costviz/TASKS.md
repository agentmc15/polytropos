# TASKS — copilot-costviz

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the Research findings (the pinned
events.jsonl surface), decisions D1–D9, the OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `copilot-costviz-implementer` (the parameter overrides the
agent's frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. Dispatch `copilot-costviz-reviewer` at each phase
end.

Standing rules for every task — the #1 one first:

- **NEVER invoke the real `copilot` CLI** (any subcommand, any flag — `--help` included). It
  spends real AI Credits and hits the network. Every usage-surface fact needed is pinned in
  PLAN.md's Research findings (observed on Copilot CLI v1.0.68) and restated in these briefs.
- **Never read OR write the real `~/.copilot` during execution.** `bin/copilot_usage.py`
  targets it read-only at runtime only (when the USER runs the finished tool); every test and
  verify command here uses synthetic `events.jsonl` fixtures in temp `--copilot-home` /
  `--session-dir` dirs. `Path.home()` may appear only in that script's one runtime default
  constant, never in tests. Never open a `*.db` file anywhere (PLAN.md D1).
- Never write outside this repo (`~/.claude` included). The aesop clone is reference-only,
  session-scoped, and may not exist — no task reads it; cite provenance only as
  `aesop@5506617`. No `/private/tmp/` path in any deliverable.
- Never run node/npm/`aesop compile`; never edit `data/pricing.json`,
  `data/pricing.copilot.json`, `.claude-plugin/`, `skills/`, `copilot/`, the completed kits,
  or any existing `bin/`/`tests/` file except `bin/copilot_pricing.py` (T1 only) and
  `tests/test_copilot_pricing.py` (T2 only). `bin/cost_report.py` is a read-only model.
- Never hardcode a price, credit value, plan allowance, or model id — derive from
  `data/pricing.copilot.json` at run time (synthetic fixture ids/values in tests are fine).
- Verify commands use `python3 -m unittest discover -s tests [-p '<file>.py']` (the
  dotted-module form is broken on this machine).

---

## Phase 1 — Pooled-AIC runway

### T1 — Extend plan_runway with a user-supplied pool (`--pool-aic`)
- status: done
- model: sonnet
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D8, this is the kit's ONE sanctioned edit to an existing `bin/` script.
Today `plan_runway` in `bin/copilot_pricing.py` raises `KeyError` for plans whose
`included_aic_per_month` is null (`business`/`enterprise` — their AIC is pooled at the org
level, so the data file cannot know a per-seat number). Give it a user-supplied pool:

**(1) `plan_runway`** — new keyword-only-style trailing parameter, additive signature:
`plan_runway(pricing, plan_id, profile, model_id, cache_hit=0.8, today=None, pool_aic=None)`.
Semantics:
- `plan_id` must still be a key of `pricing["plans"]` (unknown → the existing `KeyError`),
  with or without a pool.
- `pool_aic` given: it must be a number `> 0`, else `ValueError` (message says the pool must
  be a positive AIC count). The allowance used is `pool_aic`, REGARDLESS of the plan's own
  `included_aic_per_month` (an org admin may know the real pool; override is deliberate —
  document it in the docstring).
- `pool_aic` absent and the plan's `included_aic_per_month` is null: keep raising `KeyError`,
  but extend the message so it also tells the caller to supply the org pool via
  `--pool-aic` / `pool_aic` (the message must still contain the plan id — an existing test
  asserts that).
- Return dict: the three existing keys (`est_aic_per_task`, `tasks_per_month`,
  `pct_of_allowance`) keep their exact meaning and math against the effective allowance; ADD
  `allowance_aic` (the number used) and `allowance_source` (`"plan"` or `"pool"`).
  `bin/copilot_ralph.py`'s `_print_plan_runway` reads only the three original keys — it must
  keep working with ZERO changes (do not touch that file).

**(2) CLI** — the `runway` subcommand gains `--pool-aic` (`type=float`, `default=None`,
help text explaining it is for org/Business pooled plans or to override a fixed allowance).
Wire it through `cmd_runway`; a `ValueError` from the pool validation is handled like the
existing `KeyError`s (message to stderr, exit 2). Text output gains one line after the header:
`  allowance:        <N:,.0f> AIC (plan)` or `(user-supplied pool)`; JSON output gains
`allowance_aic` and `allowance_source` keys (append-only — existing keys unchanged).

**(3) Docstrings** — update the module docstring's `runway` usage line to show
`[--pool-aic N]`, and `plan_runway`'s docstring for the new parameter/keys and the override
semantics. Change nothing else in the file: `est_cost`, `effective_rates`, `models_table`,
the other subcommands, and all existing behavior stay byte-identical.

GOTCHAS: no plan/price/model-id literals anywhere in the diff; `math.floor` stays the
tasks-per-month rule; do not "fix" the existing KeyError-for-unknown-plan behavior.

**Acceptance.**
- Fixture-dict math: null-allowance plan + `pool_aic` returns pool-based runway with
  `allowance_source == "pool"`; fixed plan without pool returns `allowance_source == "plan"`
  and its own allowance; pool overrides a fixed allowance; null plan without pool still
  raises `KeyError` naming the plan AND mentioning the pool option; `pool_aic <= 0` raises
  `ValueError`.
- CLI: `runway business M <live id> --pool-aic 50000 --json` prints JSON with
  `"allowance_source": "pool"`; `runway pro M <live id> --json` prints
  `"allowance_source": "plan"`; `bin/copilot_ralph.py --demo` still completes `verified`.
- Full suite green; this task's edits touch ONLY `bin/copilot_pricing.py` (the working tree
  carries unrelated pre-existing modifications — do not "clean them up");
  `git diff --quiet -- data` clean.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && M="$(python3 -c "import json; print(next(iter(json.load(open('data/pricing.copilot.json'))['models'])))")" && python3 bin/copilot_pricing.py runway business M "$M" --pool-aic 50000 --json | grep -q '"allowance_source": "pool"' && python3 bin/copilot_pricing.py runway pro M "$M" --json | grep -q '"allowance_source": "plan"' && python3 bin/copilot_ralph.py --demo | grep -q 'halt: verified' && git diff --quiet -- bin/copilot_ralph.py bin/cost_report.py data && python3 -m unittest discover -s tests && echo 'T1 OK'
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('cp', pathlib.Path('bin/copilot_pricing.py').resolve())
cp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
FIX = {
    "billing_unit": {"name": "AIC", "usd_per_credit": 0.5},
    "plans": {"fixed": {"included_aic_per_month": 1000}, "nullp": {"included_aic_per_month": None}},
    "models": {"fake-cheap": {"tier": "cheap", "input_per_mtok": 1.0, "cached_input_per_mtok": 0.1, "output_per_mtok": 2.0}},
    "task_profiles": {"S": {"input_tokens": 100000, "output_tokens": 10000}},
}
# est: 100000*(0.2*1.0 + 0.8*0.1)/1e6 + 10000/1e6*2.0 = 0.028 + 0.02 = 0.048 usd -> 0.096 AIC
r = cp.plan_runway(FIX, "nullp", "S", "fake-cheap", cache_hit=0.8, pool_aic=1000.0)
assert r["allowance_source"] == "pool" and r["allowance_aic"] == 1000.0, r
assert r["tasks_per_month"] == 10416, r
assert abs(r["pct_of_allowance"] - 0.0096) < 1e-9, r
r2 = cp.plan_runway(FIX, "fixed", "S", "fake-cheap", cache_hit=0.8)
assert r2["allowance_source"] == "plan" and r2["allowance_aic"] == 1000, r2
r3 = cp.plan_runway(FIX, "fixed", "S", "fake-cheap", cache_hit=0.8, pool_aic=2000)
assert r3["allowance_source"] == "pool" and r3["allowance_aic"] == 2000, r3
try:
    cp.plan_runway(FIX, "nullp", "S", "fake-cheap", cache_hit=0.8)
    raise SystemExit("expected KeyError")
except KeyError as e:
    assert "nullp" in str(e) and "pool" in str(e).lower(), e
try:
    cp.plan_runway(FIX, "nullp", "S", "fake-cheap", cache_hit=0.8, pool_aic=0)
    raise SystemExit("expected ValueError")
except ValueError:
    pass
print("pool runway math ok")
PY
```

---

### T2 — Regression tests for the pooled-AIC runway
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Extend `tests/test_copilot_pricing.py` following the file's own conventions
(importlib `_load` off `BIN_DIR`, the synthetic `FIXTURE` dict with fake round numbers and
`billing_unit.usd_per_credit: 0.5`, `planA` fixed allowance 1000 / `planB` null allowance, no
wall-clock assertions, no real prices/ids). This is the kit's ONE sanctioned edit to an
existing `tests/` file. Append ONE new test class `PlanRunwayPoolTests`; change none of the
existing classes (in particular `test_null_allowance_plan_raises_keyerror_naming_plan` must
keep passing untouched — T1 only extended that error's message).

Test cases (minimum):

1. `planB` (null allowance) + `pool_aic=500` → result has `allowance_source == "pool"`,
   `allowance_aic == 500`, `tasks_per_month == math.floor(500 / est_aic)` and
   `pct_of_allowance == est_aic / 500 * 100`, where `est_aic` comes from calling
   `cp.est_cost` on the same fixture/profile/model (derive, don't re-hardcode the math).
2. `planB` + no pool → `KeyError` whose message contains both `planB` and (case-insensitive)
   `pool`.
3. `planA` (fixed 1000) + `pool_aic=2000` → pool overrides: `allowance_aic == 2000`,
   `allowance_source == "pool"`.
4. `planA` + no pool → `allowance_source == "plan"`, `allowance_aic == 1000`, and the three
   original keys are all present (backward compatibility).
5. `pool_aic == 0` and a negative pool each raise `ValueError`.
6. Unknown plan id + a pool still raises `KeyError` (a pool never legitimizes a bad plan id).
7. CLI: with `unittest.mock.patch.object(cp, "load_pricing", return_value=FIXTURE)`, run
   `cp.main(["runway", "planB", "S", "fake-cheap", "--pool-aic", "500", "--json"])` capturing
   stdout; parse the JSON; assert `allowance_source == "pool"` and `allowance_aic == 500`.
   Also assert the no-pool `planB` CLI call exits 2 (SystemExit) with a stderr message
   mentioning the pool option.

GOTCHAS: use the module-level `FIXTURE` (deep-copy if a test mutates); no `Path.home()`; no
real model ids; the fixture profile/model names in the file may differ from the sketch above —
reuse whatever the file's FIXTURE actually defines (e.g. its cheap model and `S` profile) and
compute expectations from `cp.est_cost`, not by hand-copying rates.

**Acceptance.** New tests pass and would fail if the pool override, the new result keys, the
extended error message, or the positive-pool validation regressed; full suite green; grep
shows no `Path.home()` and no real Claude model ids in the file; only
`tests/test_copilot_pricing.py` modified.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_copilot_pricing.py' -v 2>&1 | grep -q 'PlanRunwayPool' && ! grep -nE 'claude-(fable|opus|sonnet|haiku)' tests/test_copilot_pricing.py && ! grep -n 'Path.home()' tests/test_copilot_pricing.py && python3 -m unittest discover -s tests && echo 'T2 OK'
```

---

*Phase 1 end — dispatch `copilot-costviz-reviewer` before starting Phase 2.*

---

## Phase 2 — The usage report

### T3 — Create bin/copilot_usage.py (the Copilot usage report)
- status: done
- model: opus
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D1–D7: a stdlib usage report over Copilot CLI's session event logs,
mirroring `bin/cost_report.py`'s SHAPE (read that script first as the model — walk → extract →
dedupe → price → markdown to stdout; do NOT edit it). Follow `bin/` conventions: module
docstring, pure functions, `main(argv=None)`, errors → stderr/exit non-zero,
`Path(__file__).resolve()` for repo paths.

The module docstring MUST state: what it reads
(`<copilot-home>/session-state/*/events.jsonl` plus sibling `workspace.yaml`), that it is
STRICTLY READ-ONLY (never writes under the target home, never opens the `*.db` session stores
— they read empty without a WAL checkpoint and opening SQLite can create `-wal`/`-shm` side
files), that it never invokes the `copilot` CLI, that the event format was observed on Copilot
CLI v1.0.68, and the AIU caveat (below).

**The pinned event surface (from PLAN.md Research findings — trust it, do not inspect the real
`~/.copilot`):** each `events.jsonl` line is `{"type": ..., "timestamp": ..., "data": {...}}`.
- `session.shutdown` data: `totalNanoAiu` (int nano-AI-Units; ÷ 1e9 = AIU),
  `totalPremiumRequests` (int), `currentModel`, and `tokenDetails` =
  `{"input": {"tokenCount": N}, "cache_read": {"tokenCount": N},
  "cache_write": {"tokenCount": N}, "output": {"tokenCount": N}}` (any sub-key may be
  missing → 0). A session may have MULTIPLE shutdowns across resumes.
- `assistant.message` data: `model`, `outputTokens`, `apiCallId` (dedupe key when present).
- `session.start` / `session.resume` data: `selectedModel`.
- `session.model_change` data: `previousModel`, `newModel`.
- `workspace.yaml`: flat `key: value` lines (`id`, `name`, `cwd`, ...) — parse with a
  tolerant line splitter (first `:` splits; strip; ignore lines that don't fit; NO YAML
  parser exists in stdlib and none may be added).

Module constants: `PLUGIN_ROOT = Path(__file__).resolve().parent.parent`;
`PRICING_PATH = PLUGIN_ROOT / "data" / "pricing.copilot.json"`;
`DEFAULT_COPILOT_HOME = Path.home() / ".copilot"` (the ONLY `Path.home()` use — runtime
default, always overridden in tests); `EXPENSIVE_TIERS = {"strong", "frontier"}`;
`DOWNGRADE_TOKEN_CEILING = 50_000`; `DOWNGRADE_TURN_CEILING = 15` (both commented as report
knobs — token/turn counts, not prices; turns replace cost_report's tool-call ceiling because
Copilot events carry no tool counter).

Pure functions (unit-testable; I/O only where stated):

- `load_pricing()` — `json.load` of `PRICING_PATH`.
- `match_model(model_id, pricing) -> key|None` — mirror cost_report's matcher: strip anything
  from `"["`, exact key match, else `base.startswith(key + "-")`, else None.
- `price_tokens(u, key, pricing) -> float` — PLAN.md D5:
  `(u["input"] * m["input_per_mtok"] + u["cache_read"] * m["cached_input_per_mtok"] +
  u["cache_write"] * m.get("cache_write_per_mtok", 0) + u["output"] * m["output_per_mtok"])
  / 1e6`. Cache writes ARE priced when the row carries a rate (observed usage, unlike
  `est_cost`'s forecast convention — note this in the docstring).
- `usd_to_aic(usd, pricing) -> float` — `usd / pricing["billing_unit"]["usd_per_credit"]`.
- `parse_timestamp(raw)` — as in cost_report (ISO, `Z` → `+00:00`, naive → UTC, None on
  failure).
- `parse_events(lines) -> dict` — one session's lines →
  `{"tokens": {input, cache_read, cache_write, output},  # element-wise MAX over shutdown
    "nano_aiu": int, "premium_requests": int,            # MAX over shutdowns (D3)
    "shutdowns": int, "has_token_details": bool,
    "models": [...],          # ordered, deduped, from selectedModel / previousModel /
                              # newModel / assistant.message model / currentModel
    "last_model": str|None,   # the LAST model signal in stream order
    "per_turn_output": {model: {"turns": int, "output_tokens": int}},  # assistant.message,
                              # deduped by apiCallId when present
    "first_seen": dt|None, "last_seen": dt|None}`.
  Robustness: skip blank/malformed JSON lines and non-dict objects; ignore unknown event
  types; every `data` field access uses `.get` with a default. MAX aggregation per PLAN.md
  D3: shutdown totals are cumulative snapshots — element-wise max is exact for cumulative
  snapshots and never double-counts; summing would.
- `effective_tokens(parsed) -> (tokens_dict, output_only: bool)` — when
  `has_token_details`: the parsed tokens, `False`. Otherwise input/cache_read/cache_write 0
  and output = the summed per-turn outputTokens, `True` (D4's `†` fallback).
- `parse_workspace(text) -> dict` — the tolerant flat parser above.
- `collect_sessions(session_dir: Path) -> (list[dict], errors: list[str])` — for each sorted
  subdirectory containing an `events.jsonl`: `read_text(errors="replace")`, `parse_events`,
  attach `parse_workspace` of a sibling `workspace.yaml` when present (missing/unreadable →
  `{}`), session id = the subdirectory name. ONLY those two filenames are ever opened —
  never glob or open anything else (no `*.db`). OSErrors collected into `errors`, not raised.

`main(argv=None)`: argparse with `--days` (int, default 30), `--top` (int, default 10),
`--copilot-home` (default `str(DEFAULT_COPILOT_HOME)`), `--session-dir` (default None —
overrides `<copilot-home>/session-state` when given). Missing session dir →
`sys.exit(f"No session-state directory at {dir}")`. Age filter mirrors cost_report: sessions
whose `last_seen` is older than the cutoff are dropped; sessions with NO parseable timestamp
are kept regardless of `--days` (comment this, as cost_report does).

Attribution per session (D4): match every seen model via `match_model`; attribution model =
the sole matched model (single-model session, exact) or the matched `last_model` (multi-model
→ flag `approx`); a session with no matched model goes to the unpriced bucket. Session USD =
`price_tokens(effective_tokens(...), attribution_key, ...)`; output-only sessions flag `†`.

Report sections (markdown, pinned headings, cost_report's table style):

1. `# Copilot CLI usage — last {days} days` then
   `**Total priced estimate: ${usd:,.2f} ({aic:,.1f} AIC) across N sessions.**` and a second
   line `Copilot-reported: {aiu:,.2f} AIU, {n} premium requests (cross-check below).`
2. `## Spend by model` — table `| Model | Sessions | Input | Cache read | Cache write |
   Output | USD | AIC |`, aggregated by attribution model, sorted by USD desc; token cells
   comma-formatted (`{:,}`, cost_report style), USD `${:,.2f}`, AIC `{:,.1f}`; a `≈` suffix
   on the Sessions cell of rows containing multi-model sessions. Footnote (MUST contain the
   substring `multi-model`): `≈ includes N multi-model session(s) whose whole token split is
   attributed to the session's last model — events.jsonl does not record per-model
   input/cache splits; see the exact per-turn table below.`
3. `## Output tokens by model (per-turn, exact)` — table `| Model | Turns | Output tokens |`
   from the merged `per_turn_output` of ALL sessions (raw model strings matched to pricing
   displays where possible, raw id otherwise) — exact but output-only, say so in one line.
4. `## Top {top} sessions by estimated cost` — table `| Session | Project | Models | Tokens |
   USD | AIC | Copilot AIU |`; Session = first 12 chars of the dir name + `…`; Project =
   workspace `cwd` tail or `name` or blank; Models = display names joined `, `; `≈` marker on
   multi-model rows, `†` on output-only rows; Tokens = input + output + cache_write (the
   cost_report footprint convention). Footnote defining `≈` and `†` (`† no shutdown token
   details — output tokens only; input/cache unpriced (undercount)`).
5. `## Downgrade candidates` — sessions whose matched models are ALL in `EXPENSIVE_TIERS`,
   footprint `< DOWNGRADE_TOKEN_CEILING`, total assistant turns `< DOWNGRADE_TURN_CEILING`.
   Target = FIRST model in pricing-file order with `tier == "mid"` (computed — no id
   literal). Table `| Session | Project | Tokens | Turns | USD | On {target display} |
   Delta |` + a totals line `**Estimated savings on {display}: ${x:,.2f} ({y:,.1f} AIC)**`;
   empty → `None found in this window.`
6. `## Copilot-reported AIU cross-check` — total AIU (`nano_aiu / 1e9`, `:,.2f`) and premium
   requests next to the tool's totals, plus this caveat verbatim: `AIU is Copilot's own
   reported consumption unit; it is NOT assumed equal to the AIC billing unit in
   data/pricing.copilot.json. The authoritative estimate above is token counts × per-MTok
   rates → USD → AIC via billing_unit.usd_per_credit. AIU is never converted to USD or AIC
   here.`
7. `## Unpriced models (not in pricing.copilot.json)` — only when present: raw model strings
   with per-turn output-token counts (never crash on unknown models).
8. `## Read errors` — only when present.
9. Footer: `*Prices cached {cached_date} from pricing.copilot.json; costs are token-priced
   estimates, not bills. Event format observed on Copilot CLI v1.0.68.*`

EXECUTION GUARDRAIL (binds YOU): never run `copilot`; never point the script at the real
`~/.copilot` — exercise it ONLY against synthetic fixtures in temp dirs you create; run the
full suite before claiming done.

**Acceptance.**
- Against a synthetic two-session fixture home (single-model session; multi-model session
  with resume + two cumulative shutdowns), the report shows: max-rule token totals (not
  sums), the `≈` multi-model marker + `multi-model` footnote, the exact per-turn output
  table, the AIU cross-check with `:,.2f` AIU values, a downgrade-candidates section, and
  the v1.0.68 footer — and the fixture home is byte-identical after the run (file set and
  contents unchanged; `session.db` present in the fixture and never opened/modified).
- No model id, price, credit value, or plan allowance literal in the script; the downgrade
  target and USD→AIC conversion are computed from the pricing dict.
- `Path.home()` appears exactly once (the `DEFAULT_COPILOT_HOME` constant).
- Full suite green; this task creates ONLY `bin/copilot_usage.py` (other tasks' in-flight
  changes may coexist in the working tree); `git diff --quiet -- data` clean.

**Verify.**
```bash
cd /path/to/polytropos && H="$(mktemp -d)" && O="$(mktemp)" && python3 - "$H" <<'PY'
import json, pathlib, sys
home = pathlib.Path(sys.argv[1])
models = json.load(open('data/pricing.copilot.json'))['models']
mid = next(k for k, v in models.items() if v['tier'] == 'mid')
strong = next(k for k, v in models.items() if v['tier'] == 'strong')
def ev(t, ts, **data):
    return json.dumps({"type": t, "timestamp": ts, "data": data})
def td(i, cr, cw, o):
    return {"input": {"tokenCount": i}, "cache_read": {"tokenCount": cr},
            "cache_write": {"tokenCount": cw}, "output": {"tokenCount": o}}
s1 = home / "session-state" / "11111111-aaaa-bbbb-cccc-000000000001"
s1.mkdir(parents=True)
(s1 / "workspace.yaml").write_text("id: s1\nname: fixture-one\ncwd: /tmp/proj-one\n")
(s1 / "events.jsonl").write_text("\n".join([
    ev("session.start", "2026-06-30T10:00:00Z", selectedModel=strong),
    ev("assistant.message", "2026-06-30T10:01:00Z", model=strong, outputTokens=200, apiCallId="a1"),
    ev("assistant.message", "2026-06-30T10:02:00Z", model=strong, outputTokens=300, apiCallId="a2"),
    "not json at all", "{\"type\": \"weird.unknown\"}",
    ev("session.shutdown", "2026-06-30T10:03:00Z", totalNanoAiu=2500000000,
       totalPremiumRequests=1, currentModel=strong, tokenDetails=td(9000, 4500, 500, 500)),
]) + "\n")
(s1 / "session.db").write_bytes(b"NOT-USAGE-DO-NOT-OPEN")
s2 = home / "session-state" / "22222222-aaaa-bbbb-cccc-000000000002"
s2.mkdir(parents=True)
(s2 / "workspace.yaml").write_text("id: s2\nname: fixture-two\ncwd: /tmp/proj-two\n")
(s2 / "events.jsonl").write_text("\n".join([
    ev("session.start", "2026-06-30T11:00:00Z", selectedModel=mid),
    ev("assistant.message", "2026-06-30T11:01:00Z", model=mid, outputTokens=100, apiCallId="b1"),
    ev("session.shutdown", "2026-06-30T11:02:00Z", totalNanoAiu=1000000000,
       totalPremiumRequests=1, currentModel=mid, tokenDetails=td(1000, 0, 0, 100)),
    ev("session.resume", "2026-06-30T12:00:00Z", selectedModel=mid),
    ev("session.model_change", "2026-06-30T12:01:00Z", previousModel=mid, newModel=strong),
    ev("assistant.message", "2026-06-30T12:02:00Z", model=strong, outputTokens=400, apiCallId="b2"),
    ev("session.shutdown", "2026-06-30T12:03:00Z", totalNanoAiu=3000000000,
       totalPremiumRequests=2, currentModel=strong, tokenDetails=td(3000, 2000, 100, 500)),
]) + "\n")
PY
find "$H" -type f | sort > "$O.files" && cat $(find "$H" -type f | sort) | md5 > "$O.sum" && \
python3 bin/copilot_usage.py --copilot-home "$H" --days 36500 > "$O" && \
find "$H" -type f | sort | diff -q - "$O.files" >/dev/null && cat $(find "$H" -type f | sort) | md5 | diff -q - "$O.sum" >/dev/null && \
python3 - "$O" <<'PY2'
import sys
out = open(sys.argv[1]).read()
for needle in [
    "## Spend by model",
    "## Output tokens by model (per-turn, exact)",
    "## Downgrade candidates",
    "## Copilot-reported AIU cross-check",
    "multi-model",            # honesty footnote
    "≈",                      # the multi-model approx marker
    "2.50",                   # S1 AIU 2500000000 / 1e9
    "5.50",                   # total AIU 2.5 + max(1.0, 3.0) — MAX rule on nano_aiu
    "12,000",                 # by-model input 9000 + max(1000, 3000) — MAX rule on tokens
    "not bills",
    "v1.0.68",
]:
    assert needle in out, f"missing {needle!r} in report"
assert "13,000" not in out, "13,000 implies S2's shutdown totals were SUMMED, not MAXed"
assert "None found in this window." not in out, "S1 should be a downgrade candidate"
print("report ok")
PY2
rm -rf "$H" "$O" "$O.files" "$O.sum" && test "$(grep -c 'Path.home()' bin/copilot_usage.py)" -eq 1 && ! grep -nE 'claude-(fable|opus|sonnet|haiku)' bin/copilot_usage.py && python3 -m unittest discover -s tests && git diff --quiet -- data && echo 'T3 OK'
```

---

### T4 — Regression tests for the usage report
- status: done
- model: sonnet
- depends: T3
- independent: no

**Brief.** Create `tests/test_copilot_usage.py`, stdlib `unittest` + `unittest.mock`, loading
`bin/copilot_usage.py` via the importlib `_load` convention off
`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` (copy the pattern from
`tests/test_copilot_pricing.py`). Module docstring MUST state the safety contract: **no test
in this file ever invokes the `copilot` CLI, reads or writes the real `~/.copilot`, or uses
`Path.home()`** — every run goes against synthetic `events.jsonl` fixtures in
`tempfile.TemporaryDirectory` homes, and pricing is a synthetic fixture patched over
`load_pricing`.

Fixtures (module constants): a synthetic pricing dict with FAKE ids and round numbers —
`billing_unit.usd_per_credit: 0.5` (proves derivation), models in file order
`fake-front` (tier `frontier`), `fake-strong` (tier `strong`, WITH
`cache_write_per_mtok`), `fake-mid` (tier `mid` — the expected downgrade target),
`fake-mid-b` (tier `mid`), `fake-cheap` (tier `cheap`, NO `cache_write_per_mtok`), each with
round `input_per_mtok`/`cached_input_per_mtok`/`output_per_mtok`; a `cached_date`; plus
helper functions building event lines (`_ev(type, ts, **data)`) and `tokenDetails` dicts.

Test cases (minimum):

1. `parse_events` on a single-model session (start + 2 assistant.messages + 1 shutdown):
   models `["fake-strong"]`, tokens from tokenDetails, `nano_aiu`, `shutdowns == 1`,
   `per_turn_output` turns/outputs, `has_token_details` True.
2. Multi-model session (start on A, model_change A→B, messages on both, shutdown
   currentModel B): `models` contains both in order, `last_model == B`.
3. Resume + MULTIPLE shutdowns aggregate element-wise MAX, not sum: shutdown-1 tokenDetails
   `{input: 100, output: 500}`, shutdown-2 `{input: 300, output: 400}` → tokens
   `input == 300` AND `output == 500` (proves per-field max); `nano_aiu` and
   `premium_requests` also max; `shutdowns == 2`.
4. Missing tokenDetails: `has_token_details` False; `effective_tokens` returns zeros for
   input/cache and the summed per-turn output, with `output_only True`.
5. Robustness: blank lines, non-JSON garbage, a JSON array line, unknown event types, and an
   `assistant.message` with no `outputTokens` — no exception, sane result.
6. `apiCallId` dedupe: two `assistant.message` events with the SAME `apiCallId` count once.
7. `price_tokens` hand math on the fixture: a row WITH `cache_write_per_mtok` includes the
   cache-write term; a row WITHOUT prices cache writes at 0. `usd_to_aic` divides by the
   fixture's 0.5.
8. `match_model`: exact id; suffixed id (`fake-strong-20260701` → `fake-strong`); unknown →
   None.
9. `parse_workspace`: flat lines parsed; junk lines ignored; empty text → `{}`.
10. End-to-end `main` with `mock.patch.object(cu, "load_pricing", return_value=FIXTURE)` and
    a temp home holding: a single-model `fake-strong` session under the downgrade ceilings
    (→ downgrade candidate), a multi-model session, and a session whose model is not in the
    fixture (→ unpriced section). Capture stdout; assert: the pinned section headings, the
    `≈` marker and a `multi-model` footnote, the downgrade table names the FIRST mid model's
    display (`fake-mid`, not `fake-mid-b` — file-order rule), the unpriced section lists the
    unknown id, and the AIU cross-check line appears.
11. READ-ONLY proof: in the e2e test, place a `session.db` with junk bytes in a session dir;
    snapshot every file's bytes under the home before `main`, compare after — identical, and
    no new files/dirs appeared.
12. `--days` filter: a session whose events are all older than the cutoff is excluded; a
    session with NO parseable timestamps is kept.
13. Missing session dir → `SystemExit`.

**Acceptance.** All new tests pass; full suite green; no real model ids, prices, or plan
allowances anywhere in the file; no `Path.home()`; no bare `"copilot"` string literal (the
grep below enforces it); no writes outside temp dirs.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_copilot_usage.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T4 OK'
import re
text = open('tests/test_copilot_usage.py').read()
assert 'Path.home()' not in text, "tests must never resolve the real home"
bad = [l for l in text.splitlines() if re.search(r'''["']copilot["']''', l)]
assert not bad, f"bare 'copilot' string literal(s): {bad}"
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
print('safety greps ok')
PY
```

---

*Phase 2 end — dispatch `copilot-costviz-reviewer` before starting Phase 3.*

---

## Phase 3 — The aesop proposal (a document, not an execution)

### T5 — Write docs/AESOP-COMPILE-PROPOSAL.md
- status: done
- model: opus
- depends: (none)
- independent: yes

**Brief.** Write the specification a FUTURE `/polytropos:architect` run — executed
INSIDE the aesop repo, under aesop's own process — will take as input. This task produces ONE
new file and touches nothing else. You must NOT look for an aesop clone (it may not exist),
run node/npm/`aesop compile`, or touch the aesop repo — every aesop fact you need is pinned
below at commit `5506617` (full: `55066175a5268887acad39bc859584d13fab09db`). You MAY read
this repo's own files for context: `docs/AESOP-INTEGRATION.md`, `docs/COPILOT-HARNESS.md`,
`.claude/kits/copilot-harness/PLAN.md` (D2), `copilot/aesop.yaml`, and the bundle tree
listing under `copilot/.github/`.

**Pinned aesop facts (cite each claim as `aesop@5506617`; the future run must re-verify them
against aesop HEAD):**
- aesop is the env compiler at `github:agentmc15/aesop`: one manifest (`aesop.yaml`)
  compiled → many harness config bundles via per-harness emitters.
- The copilot emitter at 5506617 emits agents as `<name>.md`, while Copilot CLI's how-to
  documents `<name>.agent.md`; GitHub's config reference accepts both. This repo deliberately
  pinned `.agent.md` (the CLI-documented form) in `copilot/.github/agents/` — the divergence
  was recorded in the copilot-harness kit (PLAN.md D2) with emitter reconciliation explicitly
  deferred to aesop's repo.
- Registry lookup: `importPrimitive` (`src/federation.ts`) resolves a SKILL at
  `registry/skills/<name>`, `skills/<name>`, or `skills/*/<name>` relative to a source root;
  AGENTS are looked up analogously at `agents/<name>.md` / `registry/agents/<name>.md` at a
  source root. This repo's TOP-LEVEL `skills/route` and `skills/fable-check` already qualify
  (that is the existing Claude-side export documented in `docs/AESOP-INTEGRATION.md`); the
  COPILOT bundle does not — its agents live at `copilot/.github/agents/*.agent.md` (wrong
  root AND wrong extension for the lookup) and its skills at
  `copilot/.github/skills/<name>/SKILL.md` (wrong root).
- Vendoring semantics: `aesop add skill <name> --from <source>` copies the whole primitive
  directory into the consumer's `.aesop/vendor/…` with the upstream SHA pinned in the
  lockfile; `aesop update` / `aesop update --apply` is the refresh flow.
- Guardrails on the aesop side: `src/types.ts` and the schema are **LOCKED** (any change
  needs explicit approval there); aesop uses a doc-first harness-matrix process and a
  golden-fixture process for emitter output.
- This repo's side of the contract: `copilot/aesop.yaml` is the manifest;
  `tests/test_copilot_bundle.py` enforces manifest ↔ bundle consistency by unittest instead
  of by running the compiler; agent `model:` pins are enforced by TIER against
  `data/pricing.copilot.json`; bundle files carry the `{{POLYTROPOS_ROOT}}`
  placeholder, resolved only by `bin/harness_select.py` at install.

Required structure — exactly these seven H2 headings, in this order:

1. `## Why this document exists` — Phase 3 scope decision: the compile round-trip belongs to
   aesop's repo (LOCKED schema, doc-first + golden-fixture process, node toolchain), so this
   repo ships the spec, not the change; one paragraph on what "done" would mean end-to-end.
2. `## Current state (pinned at aesop@5506617 and this repo's HEAD)` — both sides of the
   fence as bulleted facts (from the pins above): what the emitter emits, what the lookup
   resolves, what this repo's bundle/manifest/tests already provide.
3. `## The divergence to reconcile` — the `.agent.md` vs `.md` extension question and the
   bundle-location question, stated precisely, with this repo's position: `.agent.md` is the
   CLI-documented form and should win; the emitter (and any lookup) should follow it, not
   the other way around.
4. `## Registry exposure — the options` — lay out at minimum: **(A)** a registry-shaped
   mirror in THIS repo (e.g. a generated top-level `agents/`-style tree the lookup already
   understands) — pros: zero aesop change; cons: duplicated content needing a sync
   mechanism, still fights the `.agent.md` extension, adds a second source of truth this
   repo's invariants dislike; **(B)** an aesop-side change — teach the copilot emitter to
   emit `.agent.md` and/or the lookup to accept configurable source roots + the `.agent.md`
   form — pros: fixes it for every consumer at the root; cons: touches LOCKED-adjacent code,
   needs aesop's approval flow and golden-fixture updates; **(C)** a hybrid (minimal
   manifest-declared source-root mapping). Give a recommendation (B, with C as fallback) and
   the reasoning; note explicitly that validating ANY option requires `aesop compile` runs
   only the aesop-side effort can perform — which is why this repo built nothing.
5. `## The compile round-trip, specified` — acceptance criteria for the future effort:
   register this repo as a registry source; `aesop compile` against `copilot/aesop.yaml`
   emits a `.github/` bundle that matches this repo's hand-authored
   `copilot/.github/` (agents with `.agent.md`, frontmatter `model:` pins intact,
   `{{POLYTROPOS_ROOT}}` placeholder preserved, skills under `skills/<name>/SKILL.md`)
   closely enough that a documented diff is empty or deliberate; golden fixtures added on
   the aesop side for the copilot emitter; BOTH repos' test suites green afterward; this
   repo's `tests/test_copilot_bundle.py` remains the harness-side enforcement (the compiler
   never becomes a test dependency here).
6. `## Guardrails the aesop-side effort must honor` — LOCKED `src/types.ts`/schema;
   doc-first harness matrix; golden fixtures; and THIS repo's invariants restated: both
   pricing files are numeric sources of truth that never merge and are never edited by
   tooling work; the bundle stays under `copilot/.github/` with the placeholder; the
   hand-authored `CLAUDE.md` and Claude-side `skills/` are never aesop-compiled; nothing in
   this repo ever invokes the real `copilot` CLI from tests or verify commands.
7. `## Execution: a future architect run inside the aesop repo` — close with: this document
   is the INPUT to a future `/polytropos:architect` run executed in the aesop repo,
   through aesop's own phase-gated process; every `aesop@5506617` claim above must be
   re-verified against aesop HEAD at that time; nothing in this document was executed here.

Length 110–220 lines. No absolute paths (`/Users/...`), no `/private/tmp/`, no prices, no
credit values, no plan allowances. Model ids may appear ONLY as illustrative frontmatter
examples if clearly labeled — prefer `<id>` placeholders. Cite `aesop@5506617` at least five
times (each load-bearing aesop claim carries the pin).

**Acceptance.**
- File exists with exactly the seven pinned H2 headings in order and nothing outside
  110–220 lines; the four content greps below pass (`importPrimitive`, `.agent.md`, LOCKED,
  golden); `aesop@5506617` pins ≥ 5; the closing section names the architect run in the
  aesop repo; no absolute or scratchpad paths; git shows only this new file.

**Verify.**
```bash
cd /path/to/polytropos && F=docs/AESOP-COMPILE-PROPOSAL.md && test -f "$F" && python3 - "$F" <<'PY' && ! grep -q '/Users/' "$F" && ! grep -q '/private/tmp' "$F" && L=$(wc -l < "$F") && test "$L" -ge 110 && test "$L" -le 220 && python3 -m unittest discover -s tests && echo 'T5 OK'
import re, sys
text = open(sys.argv[1]).read()
heads = re.findall(r'^## .*$', text, re.M)
want = [
    "## Why this document exists",
    "## Current state (pinned at aesop@5506617 and this repo's HEAD)",
    "## The divergence to reconcile",
    "## Registry exposure — the options",
    "## The compile round-trip, specified",
    "## Guardrails the aesop-side effort must honor",
    "## Execution: a future architect run inside the aesop repo",
]
assert heads == want, f"H2 headings drifted:\n{heads}"
assert text.count("aesop@5506617") >= 5, "pin count"
for needle in ("importPrimitive", ".agent.md", "LOCKED", "golden", "architect"):
    assert needle in text, f"missing {needle!r}"
print("proposal shape ok")
PY
```

---

*Phase 3 end — dispatch `copilot-costviz-reviewer` before starting Phase 4.*

---

## Phase 4 — Docs + guardrails

### T6 — Write docs/COPILOT-COSTVIZ.md + roadmap updates + README cross-link
- status: done
- model: sonnet
- depends: T1, T3, T5
- independent: no

**Brief.** Four changes.

**(1) Create `docs/COPILOT-COSTVIZ.md`** — the user-facing guide for the cost-visibility
layer. Tone/format of `docs/COPILOT-WORKFLOW.md`; 90–150 lines. Required H2 headings, exactly
these seven, in this order:

1. `## What this is` — Phase 3 of the Copilot harness: a usage report over Copilot CLI's own
   session logs (`bin/copilot_usage.py`), pooled-AIC runway math
   (`bin/copilot_pricing.py runway --pool-aic`), and the aesop compile round-trip written up
   as a proposal ([AESOP-COMPILE-PROPOSAL.md](AESOP-COMPILE-PROPOSAL.md)) for a future run in
   aesop's repo.
2. `## The usage report` — what it reads (`~/.copilot/session-state/<uuid>/events.jsonl`,
   read-only; the SQLite stores are ignored by design); the command
   (`python3 bin/copilot_usage.py --days 30`, plus `--top`, `--copilot-home`,
   `--session-dir`); what each report section shows; note the event format was observed on
   Copilot CLI v1.0.68 and the parser tolerates drift by surfacing, not guessing.
3. `## Granularity honesty` — full token splits exist per SESSION (`session.shutdown`
   `tokenDetails`); per-model splits are exact only for single-model sessions; multi-model
   sessions are attributed to their last model and marked `≈`; the per-turn output table is
   the exact cross-model view (output-only); sessions without shutdown token details are `†`
   output-only undercounts; the report never fabricates a per-model input/cache split.
4. `## AIU vs AIC` — Copilot's `totalNanoAiu` is its own reported unit; the tool never
   assumes AIU == AIC and never converts AIU to money; the authoritative estimate is token
   counts × `data/pricing.copilot.json` rates → USD → AIC via `billing_unit.usd_per_credit`;
   the AIU figure is printed as a labeled cross-check.
5. `## Pooled-AIC runway` — `business`/`enterprise` have org-pooled AIC with no fixed
   per-seat allowance in the data file; show
   `python3 bin/copilot_pricing.py runway business M <id> --pool-aic 50000` and explain the
   override semantics for fixed plans and the `allowance_source` output field.
6. `## Cost safety` — the report spends nothing: it never invokes the `copilot` CLI, reads
   the two text files only, writes nothing under `~/.copilot`; this repo's tests exercise it
   exclusively against synthetic fixtures in temp dirs.
7. `## Still deferred` — Ralph per-tick real-cost feedback (events.jsonl is written at
   session shutdown, not per tick — the pricing-fed estimate in `bin/copilot_ralph.py`
   remains by design) and the aesop-side execution of the proposal; point at
   `.claude/kits/copilot-costviz/PLAN.md`.

No prices, credit values, or plan allowances anywhere; model ids only as `<id>` placeholders;
the pricing file's `cached_date` may be referenced by name, not value.

**(2) `docs/COPILOT-WORKFLOW.md`** — the file ends with the `## Deferred to Phase 3` section
(heading + a numbered 2-item list). KEEP the heading; replace everything after it (to end of
file) with exactly:

```markdown

Phase 3 landed with the copilot-costviz kit — see [COPILOT-COSTVIZ.md](COPILOT-COSTVIZ.md) for
the usage report (`bin/copilot_usage.py`) and the pooled-AIC runway
(`bin/copilot_pricing.py runway --pool-aic`). The aesop compile round-trip is written up as a
proposal for a future architect run inside the aesop repo
([AESOP-COMPILE-PROPOSAL.md](AESOP-COMPILE-PROPOSAL.md)); feeding real per-tick costs back
into the Ralph loop remains deferred — events.jsonl is written at session shutdown, not per
tick (see `.claude/kits/copilot-costviz/PLAN.md`).
```

**(3) `docs/COPILOT-HARNESS.md`** — the file currently ends with a block that begins with the
line `Still deferred (Phase 3 — designed in `.claude/kits/copilot-workflow/PLAN.md`, not
built):` followed by a numbered 2-item list. Replace that block (from that line to end of
file) with exactly:

```markdown
Phase 3 (cost visibility) is now built — see [COPILOT-COSTVIZ.md](COPILOT-COSTVIZ.md) for
`bin/copilot_usage.py` and the pooled-AIC `runway --pool-aic` extension. The aesop compile
round-trip has a written spec ([AESOP-COMPILE-PROPOSAL.md](AESOP-COMPILE-PROPOSAL.md)) to be
executed in aesop's own repo; Ralph per-tick real-cost feedback remains deferred
(`.claude/kits/copilot-costviz/PLAN.md`).
```

**(4) `README.md`** — the paragraph beginning `**Copilot workflow (Phase 2):**` sits in the
intro link block. Insert directly after it, as its own paragraph:

> **Copilot cost visibility (Phase 3):** [docs/COPILOT-COSTVIZ.md](docs/COPILOT-COSTVIZ.md) — a usage report over Copilot CLI's session logs (`bin/copilot_usage.py`, read-only, priced from `data/pricing.copilot.json` in USD + AIC), pooled-AIC runway for org plans (`bin/copilot_pricing.py runway --pool-aic`), and the aesop compile round-trip proposal ([docs/AESOP-COMPILE-PROPOSAL.md](docs/AESOP-COMPILE-PROPOSAL.md)).

If any anchor above is not present verbatim (the `## Deferred to Phase 3` heading, the
`Still deferred (Phase 3` line, the `**Copilot workflow (Phase 2):**` paragraph), STOP and
report. Change nothing else in those three files.

**Acceptance.** New doc exists with exactly the seven H2 headings in order;
COPILOT-WORKFLOW.md keeps six `## ` headings with the pinned tail; COPILOT-HARNESS.md keeps
six `## ` headings with the pinned tail; README paragraph inserted verbatim; git diff shows
only these four files.

**Verify.**
```bash
cd /path/to/polytropos && for h in '^## What this is$' '^## The usage report$' '^## Granularity honesty$' '^## AIU vs AIC$' '^## Pooled-AIC runway$' '^## Cost safety$' '^## Still deferred$'; do grep -q "$h" docs/COPILOT-COSTVIZ.md || { echo "missing: $h"; exit 1; }; done && test "$(grep -c '^## ' docs/COPILOT-COSTVIZ.md)" -eq 7 && L=$(wc -l < docs/COPILOT-COSTVIZ.md) && test "$L" -ge 90 && test "$L" -le 150 && grep -q 'v1.0.68' docs/COPILOT-COSTVIZ.md && grep -q 'COPILOT-COSTVIZ.md' docs/COPILOT-WORKFLOW.md && grep -q 'AESOP-COMPILE-PROPOSAL.md' docs/COPILOT-WORKFLOW.md && test "$(grep -c '^## ' docs/COPILOT-WORKFLOW.md)" -eq 6 && grep -q 'COPILOT-COSTVIZ.md' docs/COPILOT-HARNESS.md && ! grep -q 'Still deferred (Phase 3' docs/COPILOT-HARNESS.md && test "$(grep -c '^## ' docs/COPILOT-HARNESS.md)" -eq 6 && grep -q 'Copilot cost visibility (Phase 3)' README.md && python3 -m unittest discover -s tests && echo 'T6 OK'
```

---

### T7 — CLAUDE.md: read-only usage guardrail + runnable report line
- status: done
- model: haiku
- depends: T1, T3
- independent: no

**Brief.** Two pinned insertions into the hand-authored `CLAUDE.md` (which must stay
hand-authored — never aesop-compiled). Change nothing else. If an anchor is not present
verbatim, STOP and report. (The `copilot-costviz` executor-section bullet already exists — it
was written with the kit; do not touch it.)

**(1)** In `## Invariants`, the bullet that begins
`- **Never invoke the real \`copilot\` CLI from tests, kit verify commands, or anything run
during execution**` is a single long line ending with the sentence
`` and `--dry-run` / `--demo` are the only sanctioned CLI smoke paths. `` Append to that same
line (same bullet, one space after the period) exactly:

> `bin/copilot_usage.py` reads `~/.copilot/session-state/*/events.jsonl` strictly read-only at run time (never the `*.db` stores, never a write, never a `copilot` invocation); its tests use synthetic fixtures in temp `--copilot-home` dirs and never touch the real `~/.copilot`.

**(2)** In the `## How to run things` code block, insert immediately after the
`python3 bin/copilot_ralph.py --demo               # Ralph goal-loop mock (no model, no network, no AIC)`
line this single line (into the EXISTING code block, comment aligned with the others — do not
create a new code block):

```
python3 bin/copilot_usage.py --days 30            # Copilot usage report (reads ~/.copilot read-only)
```

**Acceptance.** Both insertions present verbatim at the specified anchors; git diff shows
only these two additions in CLAUDE.md.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'strictly read-only at run time' CLAUDE.md && grep -q 'copilot_usage.py --days 30' CLAUDE.md && D="$(git diff --numstat -- CLAUDE.md | awk '{print $2}')" && { test -z "$D" || test "$D" -le 1; } && python3 -m unittest discover -s tests && echo 'T7 OK'
```

---

*Phase 4 end — dispatch `copilot-costviz-reviewer` for the final review, then run the overall
"done" check from PLAN.md.*
