# TASKS — journal-augment

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially Repo facts, decisions D1–D8, the
OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `journal-augment-implementer` (the parameter overrides the
agent's frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. **Warm-cluster candidates: T3 → T4** (same feature,
same `sonnet` pin, strictly serial — T4 tests the file T3 wrote) **and T6 → T7** (same
`sonnet` pin, strictly serial); execute may serve each pair with one continued (warm)
implementer. T1 and T6 both edit `bin/journal_collect.py` and must NEVER run in parallel.
Dispatch `journal-augment-reviewer` at each phase end. This kit's PLAN.md declares
`autonomy: advisory` — re-route recommendations during this run are print-only.

Standing rules for every task:

- **Offline is absolute.** No network, OAuth, MCP, tokens, or secrets in any form; no
  `urllib`/`http.client`/`socket` import in any new or edited file. The ask-the-tools
  feature is pure text generation.
- **Never read or write the real `~/.claude`, `~/.copilot`, or `~/.codex` from a test or
  verify command.** Every test/verify uses synthetic fixtures in temp dirs with every root
  flag overridden, and `--utc` wherever day membership matters. `Path.home()` stays at the
  four pre-existing constants (3 in `bin/journal_collect.py`, 1 in
  `bin/journal_schedule.py`) — ZERO in `bin/journal_askpack.py`, `bin/journal_advisor.py`,
  and every new test file. Never a `*.db` open or `sqlite3` import. Never a real
  `claude`/`copilot`/`codex` CLI or `launchctl`.
- **Reused scripts are imported read-only via the `_load` importlib pattern, never
  edited**: `bin/codex_usage.py`, `bin/codex_pricing.py`, `bin/copilot_pricing.py`,
  `bin/cost_report.py`, `bin/copilot_usage.py`, `bin/copilot_execute.py`. Never
  re-implement `parse_rollout`/`match_model`/`price_tokens`/`est_cost`/`resolve_tier` —
  call them. Never retype `PROXY_DISCLAIMER`/`UNPRICED_NOTE` — reference the constants.
- **The four frozen journal test files are never edited**:
  `tests/test_journal_sources.py`, `tests/test_journal_collect.py`,
  `tests/test_journal_summarize.py`, `tests/test_journal_schedule.py`. They stay green as
  the backward-compatibility proof. New tests go ONLY in
  `tests/test_journal_codex_augment.py`, `tests/test_journal_askpack.py`,
  `tests/test_journal_advisor.py`. `bin/journal_schedule.py` is never edited.
- **No new report or digest top-level key; `build_digest` untouched; `schema_version`
  stays 1.** Additions ride inside `extra` values, `notes`, `models`/`totals` values, and
  `signals` (`harness`, conditional `harness_error` only). The codex report keeps
  `priced: False` and `usd: None`; proxy dollars never enter `totals.usd_priced`.
- **Never hardcode a price, ratio, plan fact, or real model id.** GPT-5.6 ids NEVER appear
  as literals in code or tests — compute from `data/pricing.codex.json` at run time.
  Sanctioned literals: tier vocabulary (`haiku|sonnet|opus|frontier`,
  `cheap|mid|strong|frontier`), profile keys `"S"`/`"M"`, `MAX_ASK_BULLETS = 15`,
  `ADVISOR_PROFILES = ("S", "M")`, `ADVISOR_CACHE_HIT = 0.8`, the pinned command-template
  strings, pinned note/heading text, and synthetic fixture ids/values in tests.
- **Sanctioned existing-file edits ONLY**: `bin/journal_sources.py` (T1),
  `bin/journal_collect.py` (T1, T6), `bin/journal_summarize.py` (T6),
  `skills/journal/SKILL.md` (T8, BODY-only — frontmatter byte-intact),
  `docs/DAILY-JOURNAL.md` (T9), `docs/HOW-IT-WORKS.md` + `docs/how-it-works.html` (T10 —
  one pinned sentence swap each). CLAUDE.md and README.md are NOT edit targets (the
  architect already made CLAUDE.md's insertions). No new skills, no `data/` edits, nothing
  under `.claude-plugin/`, `copilot/`, `codex/`, or the completed kits.
- **Pinned content is verbatim.** Where a brief pins headings, note text, prompt
  replacement strings, or before/after sentences, reproduce them exactly. If a pinned
  anchor string is not found verbatim in the target file, STOP and report the discrepancy —
  do not approximate.
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests [-p '<file>.py']`
  (the dotted-module form is broken on this machine). Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` path in any deliverable. Do not commit or push.

---

## Phase 1 — Codex deepen + price (labeled proxy)

### T1 — Deepen collect_codex with day-scoped rollouts and the labeled proxy
- status: done
- model: opus
- depends: (none)
- independent: no

**Brief.** Per PLAN.md D2/D3. Edit `bin/journal_sources.py` and `bin/journal_collect.py`
(only these two files).

In `bin/journal_sources.py`:

1. Beside the existing `cr = _load("cost_report")` / `cu = _load("copilot_usage")` module
   loads, add `cxu = _load("codex_usage")   # Codex rollout reader + proxy pricing (read-only reuse)`.
2. Update the constant `CODEX_UNPRICED_NOTE` (its current text claims "no Codex pricing
   exists in data/ (by design)" — now stale) to exactly:
   `"Codex activity is counted but unpriced in this run — no Codex pricing was provided to the adapter."`
   The frozen test asserts membership via the CONSTANT (`js.CODEX_UNPRICED_NOTE`), so the
   text change is safe; keep the constant name.
3. Add a new constant directly below it:
   `CODEX_UNMATCHED_NOTE = ("Codex tokens found but no model matched pricing.codex.json — counted, unpriced.")`
4. Extend `collect_codex(ctx)` (keep its existing session_index/history loop byte-equivalent
   in behavior). New logic, after the existing file loop and before the final
   `sessions`/`projects` assembly:
   - `pricing = ctx.get("pricing_codex")` — the key is OPTIONAL; the frozen tests build ctx
     without it, and `None` must produce exactly today's behavior plus nothing (no new
     notes besides the updated-constant text, no `extra` keys beyond those you add
     unconditionally, no rollout pricing).
   - Rollout discovery (day-dir rule, PLAN D2): with `d = ctx["day_start"].date()`, the ONE
     directory scanned is `home / "sessions" / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"`.
     If it is a dir, iterate `sorted(p for p in day_dir.iterdir() if p.is_file() and
     p.suffix == ".jsonl")` (guard `iterdir` with try/except OSError → one entry in
     `report["errors"]`). Never touch any other dir under `sessions/`, never use mtime.
   - Per rollout file: `parsed = cxu.parse_rollout(text.splitlines())` (read via
     `path.read_text(errors="replace")`, OSError → `report["errors"]` entry, continue).
     Fold in: `report["extra"]["malformed_lines"] += parsed["malformed"]`;
     `report["extra"]["records"] += parsed["records"]`; union `parsed["session_ids"]` into
     the adapter's `session_ids` set; count the file in a new `rollouts_scanned` counter and,
     when `parsed["tokens"] is not None`, in `rollouts_with_tokens`.
   - Token bucketing (deepening happens with or without pricing): when
     `parsed["tokens"]` is not None, choose the bucket key — if `pricing` is a dict, map
     each of `parsed["models"]` through `cxu.match_model(m, pricing)`; use the LAST matched
     key (multi-match → set a local `approx = True`; mirrors `codex_usage.py` main). If
     nothing matched (or `pricing` is None), use the last raw model string from
     `parsed["models"]` (or `"unknown"` if the list is empty), and when `pricing` is a dict
     record every unmatched raw id into an `unpriced` list. Then, into
     `report["models"].setdefault(key, _model_bucket())`: add `parsed["tokens"]["input"]` /
     `["cache_read"]` / `["output"]` to the bucket AND `report["totals"]` fields of the
     same names (`cache_write` stays 0 — rollouts carry no observable cache writes),
     `b["messages"] += 1` (one per rollout). Bucket `usd` stays `None` ALWAYS (bill
     semantics — D3).
   - Proxy pricing (ONLY when `pricing` is a dict AND at least one rollout's tokens matched
     a pricing key): per matched rollout compute
     `usd = cxu.price_tokens(parsed["tokens"], key, pricing)`; accumulate a total and a
     `by_model` dict keyed by pricing key. After the loop set
     `report["extra"]["codex_proxy"] = {"billed_usd": None,
     "api_equivalent_usd_total": <total>, "by_model": <dict>,
     "approx_attribution": <bool: any multi-match rollout>,
     "disclaimer": cxu.PROXY_DISCLAIMER, "pricing_cached_date": pricing["cached_date"]}`
     and append `cxu.PROXY_DISCLAIMER` to `report["notes"]`.
   - Notes ladder (PLAN D3) — exactly one of these paths:
     pricing dict + priced tokens → `cxu.PROXY_DISCLAIMER` (above), and do NOT emit
     `CODEX_UNPRICED_NOTE` (move the existing unconditional
     `report["notes"].append(CODEX_UNPRICED_NOTE)` so it is decided AFTER rollout
     processing); pricing dict + rollout tokens found but none matched →
     `CODEX_UNMATCHED_NOTE`; pricing dict + no rollout tokens at all → `cxu.UNPRICED_NOTE`
     (the constant from codex_usage); `pricing is None` → `CODEX_UNPRICED_NOTE` (legacy).
     NOTE the frozen test `test_priced_false_usd_none_with_pinned_unpriced_note` runs with
     no `pricing_codex` and no sessions dir and asserts `CODEX_UNPRICED_NOTE` is present —
     the None path must always emit it.
   - Unconditional new `extra` keys (initialize with the other `extra` inits at the top of
     the function so the shape is stable): `report["extra"]["rollouts_scanned"] = 0`,
     `report["extra"]["rollouts_with_tokens"] = 0`,
     `report["extra"]["unpriced_models"] = []` (sorted at the end, matching the
     claude/copilot adapters). `report["priced"]` stays `False` and `report["usd"]` stays
     `None` on every path — do not touch them.
   - Keep `report["available"]`/`found_any` semantics for the two legacy files unchanged; a
     home with ONLY a sessions/ day dir (no index/history) should still set
     `available = True` when the day dir yields at least one rollout file — adjust
     `found_any` accordingly (set it True when rollout files were found) so the
     "no codex JSONL found" note stays truthful.
   - Update the `collect_codex` docstring: it currently claims the adapter reads ONLY the
     two legacy files and that no Codex pricing exists by design — rewrite those sentences
     to describe the day-dir rollout deepening, the optional `pricing_codex` ctx key
     (None ⇒ legacy behavior), and the D3 honesty rule (priced stays False, usd stays
     None, proxy only in `extra["codex_proxy"]`, never a bill). Also update the module
     docstring's ctx-keys line to include `pricing_codex` (dict or None).

In `bin/journal_collect.py`:

5. Beside the existing loads add `cxu = _load("codex_usage")  # Codex pricing loader (read-only reuse)`.
6. After `pricing_copilot = cu.load_pricing()` add `pricing_codex = cxu.load_pricing()`
   (unwrapped — parity with `cr`/`cu`; the file is committed in `data/`).
7. Add `"pricing_codex": pricing_codex,` to the `ctx` dict.
8. Do NOT touch `build_digest`, the signals assembly, `Path.home()` constants, or anything
   else in this file (T6 owns the advisor wiring). Extend the module docstring's read-only
   sentence to mention that `data/pricing.codex.json` is now loaded for the labeled Codex
   proxy (never a bill).

Gotchas: the frozen sources tests assert `frozenset(report) == REPORT_KEYS` — add NO new
report top-level key. `_base_ctx` there has no `pricing_codex` key — always use
`ctx.get("pricing_codex")`. The frozen collect end-to-end tests will now load the REAL
`data/pricing.codex.json` (sanctioned config reuse) against fixtures with no `sessions/`
dir — that path must land on `cxu.UNPRICED_NOTE` (pricing present, no tokens) and change
no asserted field. Never a `gpt-5.6-*` literal anywhere.

**Acceptance.**
- All four frozen journal test files pass byte-unmodified.
- With a synthetic day-partitioned rollout fixture and the real pricing dict passed as
  `pricing_codex`: tokens appear in `models`/`totals`, `extra["codex_proxy"]` has
  `billed_usd None`, a positive `api_equivalent_usd_total`, `by_model`, the verbatim
  `cxu.PROXY_DISCLAIMER`, and `pricing["cached_date"]`; `priced` is False, `usd` is None;
  `cxu.PROXY_DISCLAIMER` is in `notes`.
- Same fixture with `pricing_codex=None`: tokens still counted, NO `codex_proxy` key,
  `CODEX_UNPRICED_NOTE` in notes.
- Rollouts in a different day's dir are never read (day-dir rule).
- `git diff --name-only` shows only `bin/journal_sources.py` and `bin/journal_collect.py`.

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests -p 'test_journal_sources.py' && \
python3 -m unittest discover -s tests -p 'test_journal_collect.py' && \
python3 -m unittest discover -s tests -p 'test_journal_summarize.py' && \
python3 -m unittest discover -s tests -p 'test_journal_schedule.py' && \
python3 - <<'PY'
import importlib.util, json, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
root = Path('/path/to/polytropos')
spec = importlib.util.spec_from_file_location('js', root / 'bin' / 'journal_sources.py')
js = importlib.util.module_from_spec(spec); spec.loader.exec_module(js)
pricing = json.load(open(root / 'data' / 'pricing.codex.json'))
mid = next(iter(pricing['models']))  # model id computed at run time — never a literal
day = datetime(2026, 1, 15, tzinfo=timezone.utc)
with tempfile.TemporaryDirectory() as td:
    home = Path(td) / 'codex'
    day_dir = home / 'sessions' / '2026' / '01' / '15'; day_dir.mkdir(parents=True)
    other_dir = home / 'sessions' / '2026' / '01' / '14'; other_dir.mkdir(parents=True)
    (home / 'session_index.jsonl').write_text(json.dumps({'id': 's1', 'updated_at': '2026-01-15T10:00:00Z'}) + '\n')
    (day_dir / 'r1.jsonl').write_text(json.dumps({'timestamp': '2026-01-15T10:00:00Z', 'session_id': 's1', 'model': mid, 'total_token_usage': {'input_tokens': 1000, 'cached_input_tokens': 500, 'output_tokens': 200}}) + '\n')
    (other_dir / 'r0.jsonl').write_text(json.dumps({'model': mid, 'total_token_usage': {'input_tokens': 999999, 'output_tokens': 999999}}) + '\n')
    ctx = {'day_start': day, 'day_end': day + timedelta(days=1), 'claude_projects': None,
           'copilot_home': None, 'codex_home': home, 'repos': [],
           'pricing_claude': None, 'pricing_copilot': None, 'pricing_codex': pricing}
    rep = js.collect_codex(ctx)
    assert rep['priced'] is False and rep['usd'] is None, 'bill semantics broken'
    px = rep['extra']['codex_proxy']
    assert px['billed_usd'] is None and px['api_equivalent_usd_total'] > 0
    assert px['disclaimer'] == js.cxu.PROXY_DISCLAIMER and js.cxu.PROXY_DISCLAIMER in rep['notes']
    assert rep['totals']['input'] == 1000, 'other-day rollout leaked in'
    legacy = dict(ctx); legacy['pricing_codex'] = None
    rep2 = js.collect_codex(legacy)
    assert 'codex_proxy' not in rep2['extra'] and rep2['usd'] is None
    assert js.CODEX_UNPRICED_NOTE in rep2['notes']
print('T1 smoke OK')
PY
```

### T2 — New tests: tests/test_journal_codex_augment.py
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Per PLAN.md D2/D3/D7. Create `tests/test_journal_codex_augment.py` (a NEW file —
never touch the four frozen journal test files). Follow the house conventions of
`tests/test_journal_sources.py`: importlib-load `bin/journal_sources.py` and
`bin/journal_collect.py` by absolute path (`Path(__file__).resolve().parent.parent / "bin" /
…`), aware-UTC `DAY_START`/`DAY_END`, ctx built explicitly, all fixtures under
`tempfile.TemporaryDirectory()`, zero `Path.home()`, no `sqlite3`, no network imports.

Use a SYNTHETIC pricing dict for unit tests (e.g.
`{"cached_date": "2026-01-01", "cache_read_multiplier": 0.1, "models": {"fake-codex-a":
{"display": "Fake A", "tier": "mid", "input_per_mtok": 2.0, "output_per_mtok": 10.0}}}` —
synthetic ids/values are sanctioned). For the one collect-CLI end-to-end test, the real
`data/pricing.codex.json` is opened by the script itself (sanctioned config reuse); derive
any model id you plant in fixtures at RUN TIME via
`next(iter(json.load(open(...pricing.codex.json))["models"]))` — never a `gpt-5.6-*`
literal.

Cover at least:
1. **Legacy path frozen**: ctx WITHOUT `pricing_codex` (and separately with
   `pricing_codex=None`), fixture with only `session_index.jsonl`/`history.jsonl` → report
   has `priced False`, `usd None`, `js.CODEX_UNPRICED_NOTE` in notes, no `codex_proxy` key,
   `rollouts_scanned == 0`, and `frozenset(report)` equals the same 15-key report set the
   frozen tests pin.
2. **Deepening without pricing**: day-dir rollout with `total_token_usage`;
   `pricing_codex=None` → tokens in `models`/`totals`, `rollouts_with_tokens == 1`, still
   no proxy.
3. **Proxy happy path**: synthetic pricing + rollout whose `model` matches
   `"fake-codex-a"` → `extra["codex_proxy"]` exact shape (`billed_usd` None, total ==
   `js.cxu.price_tokens(tokens, "fake-codex-a", pricing)`, `by_model` keys, disclaimer IS
   `js.cxu.PROXY_DISCLAIMER`, `pricing_cached_date == "2026-01-01"`); `priced` still False,
   `usd` still None; bucket `usd` is None.
4. **Cumulative MAX honored via reuse**: one rollout file with TWO `total_token_usage`
   lines (growing totals) → tokens equal the max, not the sum (proves `parse_rollout` is
   driving).
5. **Day-dir isolation**: token-bearing rollouts in the previous/next day dirs are ignored;
   only the digest day's dir counts.
6. **Unmatched models**: pricing dict + rollout with an unknown model id → no
   `codex_proxy`, id in `extra["unpriced_models"]`, `js.CODEX_UNMATCHED_NOTE` in notes.
7. **No tokens, pricing present**: index-only fixture → `js.cxu.UNPRICED_NOTE` in notes.
8. **Read-only proof**: byte-snapshot the fixture codex home (every file's bytes + the
   file set) before/after a `collect_codex` run with rollouts + pricing → identical.
9. **Content hygiene**: plant a marker string (e.g. `"MARKER-NEVER-IN-DIGEST"`) as a
   message-like field (`"text"`) inside a rollout record → run the collect CLI end-to-end
   (`jc.main([...])` with `--date`, `--utc`, temp `--journal-dir`/`--claude-projects`/
   `--copilot-home`/`--codex-home`/`--kits-dir`) → the written digest.json text does NOT
   contain the marker, `sources.codex_cli.extra.codex_proxy` exists (plant a rollout whose
   model id is the run-time-derived real pricing id), `totals.usd_priced` does NOT include
   the proxy total, and `codex_cli` is still in `totals.unpriced_sources`.

**Acceptance.**
- The new file passes; the FULL suite passes; the four frozen journal test files are
  byte-unchanged (`git diff --quiet` each).
- No `Path.home()`, `sqlite`, `urllib`, `http.client`, `socket`, or `gpt-5` literal in the
  new file (`grep` clean).

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests -p 'test_journal_codex_augment.py' && \
python3 -m unittest discover -s tests && \
git diff --quiet -- tests/test_journal_sources.py tests/test_journal_collect.py tests/test_journal_summarize.py tests/test_journal_schedule.py && \
! grep -nE 'Path\.home|sqlite|urllib|http\.client|socket|gpt-5' tests/test_journal_codex_augment.py && \
echo T2 OK
```

---

## Phase 2 — Ask-the-tools pack (offline external sources)

### T3 — New script: bin/journal_askpack.py
- status: done
- model: sonnet
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D1. Create `bin/journal_askpack.py` (NEW file; nothing else). A
deterministic, offline, stdlib-only generator of ready-to-paste prompts for the user's OWN
Microsoft tools. No importlib loads needed; no subprocess; no network primitives; ZERO
`Path.home()` (derive defaults from `PLUGIN_ROOT = Path(__file__).resolve().parent.parent`
like `journal_summarize.py`).

Module contract (pin these names exactly — tests and the skill reference them):

- `MAX_ASK_BULLETS = 15` (module constant; 3 tools × 15 = 45 stays well under the inbox cap
  of 100).
- `TOOLS = ("copilot_studio", "teams", "outlook")` and
  `TOOL_TITLES = {"copilot_studio": "Copilot Studio", "teams": "Microsoft Teams",
  "outlook": "Outlook"}`.
- `build_ask_prompts(date_str, digest=None) -> dict` (pure; keys exactly `TOOLS`). Each
  prompt is ready-to-paste text that MUST contain: the literal date `date_str`; the phrase
  `at most {MAX_ASK_BULLETS} short bullet lines` (formatted number); the instruction that
  every line starts with `- `; the hygiene clause
  `subject-level only (titles, people, decisions, action items) — no message bodies, no
  attachments, no confidential excerpts`; and the closing sentence
  `I will paste these bullets into my daily journal's plain-text inbox.`
  Per-tool ask (one sentence each, own the wording): teams → that date's meetings AND chat
  threads; outlook → that date's sent/received email, flagged items, and action items;
  copilot_studio → that date's agent/copilot sessions: which agents, topics, and outcomes.
  When `digest` is a dict, compute the sorted union of `digest["sources"][*]["projects"]`
  (tolerant: missing keys → skip) and, when non-empty, append one line:
  `For context, today I worked on these projects: a, b, c.` Nothing else from the digest
  ever enters a prompt (hygiene — PLAN risk "Ask-pack bloat").
- `render_pack(date_str, prompts) -> str` (pure). Pinned document shape:
  H1 exactly `# Ask the tools — {date_str}`; then H2 `## How to use` describing the
  two-pass flow in 4 numbered steps (1. copy a prompt below into the matching tool's AI;
  2. paste the tool's bullet output into `journal/inbox.md`; 3. re-run the collector —
  `python3 bin/journal_collect.py` or `python3 bin/journal_schedule.py run` — so the inbox
  folds into the digest; 4. re-run/redo the summaries to get the enriched journal); then,
  for each tool in `TOOLS` order, H2 `## {TOOL_TITLES[tool]}` with the prompt inside a
  plain triple-backtick fence (easy copy). End with a one-line privacy note that pasted
  bullets become part of the digest and are later sent to a model by the summarizer.
- `main(argv=None)`: argparse with `--date` (YYYY-MM-DD, default today), `--utc` (resolve
  the default date in UTC — copy `_resolve_date_str` semantics from
  `bin/journal_summarize.py`), `--journal-dir` (default `str(PLUGIN_ROOT / "journal")`),
  `--digest PATH` (explicit digest path; DEFAULT behavior: use
  `<journal-dir>/<date>/digest.json` IF it exists, tolerating a missing or unparseable
  digest by passing `digest=None` — never crash over enrichment), and `--print` (echo the
  rendered pack to stdout). The ONLY write: `<journal-dir>/<date>/ask-the-tools.md`
  (`mkdir(parents=True, exist_ok=True)`; OSError → `sys.exit` with a useful message).
  Always print the written path (one line) like the collector does; exit 0.
- Module docstring: what it is (offline ask-the-tools pack, PLAN D1), the two-pass flow,
  the hard no-network/no-OAuth/no-MCP stance, the hygiene bounds, and that Graph/MCP stay
  deferred.

**Acceptance.**
- The smoke below passes: pinned H1 + three tool H2s + `## How to use` present, the file
  lands at `<tmp>/<date>/ask-the-tools.md`, `journal/inbox.md` and the bullet cap are
  mentioned, `--print` echoes.
- No `Path.home`, `subprocess`, `urllib`, `http.client`, `socket`, `sqlite` in the file —
  not even inside a comment or docstring (the audits grep the literal strings).
- `git status` shows only the new `bin/journal_askpack.py`.

**Verify.**
```bash
cd /path/to/polytropos && \
TMP=$(mktemp -d) && \
python3 bin/journal_askpack.py --date 2026-01-15 --utc --journal-dir "$TMP" --print > "$TMP/out.txt" && \
grep -q '^# Ask the tools — 2026-01-15' "$TMP/out.txt" && \
grep -q '^## How to use' "$TMP/out.txt" && \
grep -q '^## Copilot Studio' "$TMP/out.txt" && \
grep -q '^## Microsoft Teams' "$TMP/out.txt" && \
grep -q '^## Outlook' "$TMP/out.txt" && \
grep -q 'journal/inbox.md' "$TMP/out.txt" && \
grep -q 'at most 15 short bullet lines' "$TMP/out.txt" && \
test -f "$TMP/2026-01-15/ask-the-tools.md" && \
! grep -nE 'Path\.home|subprocess|urllib|http\.client|socket|sqlite' bin/journal_askpack.py && \
python3 -m unittest discover -s tests && \
echo T3 OK
```

### T4 — New tests: tests/test_journal_askpack.py
- status: done
- model: sonnet
- depends: T3
- independent: no

**Brief.** Per PLAN.md D1/D7. Create `tests/test_journal_askpack.py` (NEW file). House
conventions as in T2 (importlib-load `bin/journal_askpack.py` by absolute path, temp dirs,
zero `Path.home()`). Cover at least:

1. `build_ask_prompts` returns exactly the three keys; each prompt contains the date, the
   `at most 15 short bullet lines` phrase (via the constant — assert against
   `mod.MAX_ASK_BULLETS`, not a second literal), the `- ` line-start instruction, the
   hygiene clause (`no message bodies`), and the paste-back sentence.
2. Digest enrichment: a synthetic digest dict with two sources carrying `projects` lists →
   the sorted union appears once per prompt; a digest with no projects → no context line;
   `digest=None` → no context line.
3. Hygiene negative: plant a marker string in a digest field OTHER than `projects` (e.g. a
   commit subject under `sources.git.extra`) → the marker never appears in any prompt.
4. `render_pack` pinned shape: H1 first line, `## How to use` before the three tool H2s,
   tool H2s in `TOOLS` order, each prompt inside a triple-backtick fence.
5. CLI end-to-end in a temp `--journal-dir` with `--date`/`--utc`: writes ONLY
   `<dir>/<date>/ask-the-tools.md` (assert the journal tree's full file set afterward),
   exit code 0, `--print` echoes the pack; with an existing
   `<dir>/<date>/digest.json` fixture the project context line appears; with a CORRUPT
   digest.json (garbage bytes) it still succeeds with no context line.
6. Determinism: two runs over the same inputs produce identical file bytes.

**Acceptance.**
- New file green; full suite green; frozen journal test files byte-unchanged; grep-clean
  (`Path\.home|sqlite|urllib|http\.client|socket|subprocess` absent from the new test file
  except a permitted `subprocess`-free assertion — simplest: don't use subprocess at all;
  drive `main(argv)` in-process like `tests/test_journal_collect.py` does).

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests -p 'test_journal_askpack.py' && \
python3 -m unittest discover -s tests && \
! grep -nE 'Path\.home|sqlite|urllib|http\.client|socket|subprocess' tests/test_journal_askpack.py && \
echo T4 OK
```

---

## Phase 3 — Advisory harness routing

### T5 — New script: bin/journal_advisor.py
- status: done
- model: opus
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D5. Create `bin/journal_advisor.py` (NEW file; nothing else). A pure,
deterministic, ADVISORY-ONLY signal builder — it never spawns anything, never loads a
pricing FILE itself (dicts arrive as arguments), never invents a number.

Module scaffolding: the `_load(name)` importlib helper (copy the 6-line pattern from
`bin/journal_sources.py`), then `cp = _load("copilot_pricing")` and
`cxp = _load("codex_pricing")` — read-only reuse; NEVER load or import `data/` paths here.
ZERO `Path.home()`.

Pinned constants:
- `ADVISOR_PROFILES = ("S", "M")` and `ADVISOR_CACHE_HIT = 0.8` (matches the estimators'
  own defaults).
- `ADVISORY_NOTE = ("Advisory only — deterministic routing signals for a human decision; "
  "nothing here auto-executes.")`
- `COMMAND_TEMPLATES = {`
  `    "claude_code": 'claude -p --model {model} "<task>"',`
  `    "copilot_cli": 'copilot --model {model} -p "<task>"',`
  `    "codex_cli": 'codex exec --model {model} --full-auto "<task>"',`
  `}` — these are the repo-pinned dispatch shapes (journal_summarize.build_dispatch;
  CLAUDE.md's `copilot -p` invariant + copilot_execute's `--model` flag;
  codex_execute.build_dispatch). Never invent another flag.
- `CLAUDE_TIER_SLOTS = (("cheap", "haiku"), ("mid", "sonnet"))` — maps the advisor's two
  slots onto data/pricing.json's tier vocabulary. Copilot/codex slots use
  `(("cheap", "cheap"), ("mid", "mid"))` semantics via their own tier words.

Public API (pin the signature):

`build_harness_signal(reports, pricing_claude, pricing_copilot, pricing_codex,
profiles=ADVISOR_PROFILES, cache_hit=ADVISOR_CACHE_HIT) -> dict`

- `reports` is the digest's `sources` mapping (adapter reports, possibly missing keys —
  tolerate via `.get`). Pricing args are dicts or None.
- Returns exactly:
  `{"advisory": True, "note": ADVISORY_NOTE, "profiles": list(profiles),
  "cache_hit": cache_hit, "harnesses": {…}, "notes": [aggregate-level strings]}`
  with `harnesses` keyed exactly `claude_code`, `copilot_cli`, `codex_cli`. Each entry:
  - `available_today`: `bool(report.get("available"))` (False when the report is missing),
  - `sessions_today`: `report.get("sessions", 0)`,
  - `usd_today`: `report.get("usd")` (None stays None — for codex this is ALWAYS None),
  - `aic_today` (copilot_cli only): `report.get("extra", {}).get("aic")`,
  - `proxy_today` (codex_cli only):
    `report.get("extra", {}).get("codex_proxy", {}).get("api_equivalent_usd_total")` (None
    when absent) — label semantics ride on the key name and `billing` string,
  - `billing`: pinned per-harness structural strings —
    claude_code: `"priced from data/pricing.json (subscription or API)"`;
    copilot_cli: `"AIC credits — priced from data/pricing.copilot.json"`;
    codex_cli: `"subscription usage-limited; dollars are API-equivalent relative-burn
    proxies from data/pricing.codex.json — never a bill"`,
  - `command_template`: the harness's `COMMAND_TEMPLATES` string VERBATIM (leave the
    `{model}` placeholder in place — the prose fills it from `est` model ids),
  - `est`: `None` when the harness's pricing dict is None (append a note
    `"<harness>: pricing unavailable — no estimates"` to the top-level `notes`), else
    `{profile: {"cheap": <entry|None>, "mid": <entry|None>} for profile in profiles}`.
    Slot entries:
    - claude_code: resolve each slot to the FIRST model in `pricing_claude["models"]` file
      order whose `tier` equals the mapped word (`haiku`/`sonnet`); entry
      `{"model": <id>, "usd_est": <float>}` where the estimate is
      `p["input_tokens"] * ((1 - cache_hit) * rate_in + cache_hit * rate_in *
      pricing_claude["cache_read_multiplier"]) / 1e6 + p["output_tokens"] / 1e6 * rate_out`
      with `p = pricing_claude["task_profiles"][profile]` (documented parity with the
      sibling estimators — no claude-side estimator script exists to reuse). Unpopulated
      tier → slot `None` + a top-level note.
    - copilot_cli: slot model = first of tier `cheap`/`mid` in file order; entry
      `{"model": <id>, "usd_est": r["usd"], "aic_est": r["aic"]}` with
      `r = cp.est_cost(pricing_copilot, profile, model_id, cache_hit=cache_hit)`. Wrap the
      call in try/except KeyError → slot `None` + note (e.g. an unknown profile in a
      synthetic dict).
    - codex_cli: slot model = `cxp.resolve_tier(pricing_codex, "cheap"/"mid")` (KeyError →
      slot `None` + note); entry `{"model": <id>,
      "usd_api_equivalent": r["usd_api"], "billed_usd": None}` with
      `r = cxp.est_cost(pricing_codex, profile, model_id, cache_hit=cache_hit)`.
- Honesty rules: no fabricated numbers, no zeros standing in for unknowns — absent data is
  `None` plus a note. Never mix one pricing file's rates with another harness.
- Module docstring: advisory-only stance, the deterministic-signals-then-prose split, the
  reuse map, the not-a-bill codex framing, and why claude's formula is local (no existing
  claude-side estimator; formula parity documented).

**Acceptance.**
- The smoke below passes (structure, advisory flag, None degradation, no fabrication).
- No `Path.home`, `subprocess`, `urllib`, `http.client`, `socket`, `sqlite`, `open(` on a
  `data/` path, or `gpt-5` literal in the file — not even inside a comment or docstring
  (the audits grep the literal strings).
- Full suite still green; `git status` shows only the new file.

**Verify.**
```bash
cd /path/to/polytropos && \
! grep -nE 'Path\.home|subprocess|urllib|http\.client|socket|sqlite|gpt-5' bin/journal_advisor.py && \
python3 -m unittest discover -s tests && \
python3 - <<'PY'
import importlib.util, json
from pathlib import Path
root = Path('/path/to/polytropos')
spec = importlib.util.spec_from_file_location('ja', root / 'bin' / 'journal_advisor.py')
ja = importlib.util.module_from_spec(spec); spec.loader.exec_module(ja)
pc = json.load(open(root / 'data' / 'pricing.json'))
pco = json.load(open(root / 'data' / 'pricing.copilot.json'))
pcx = json.load(open(root / 'data' / 'pricing.codex.json'))
reports = {
    'claude_code': {'available': True, 'sessions': 3, 'usd': 1.25, 'extra': {}},
    'copilot_cli': {'available': True, 'sessions': 1, 'usd': 0.4, 'extra': {'aic': 40.0}},
    'codex_cli': {'available': True, 'sessions': 2, 'usd': None,
                  'extra': {'codex_proxy': {'billed_usd': None, 'api_equivalent_usd_total': 0.9}}},
}
sig = ja.build_harness_signal(reports, pc, pco, pcx)
assert sig['advisory'] is True and sig['note'] == ja.ADVISORY_NOTE
assert set(sig['harnesses']) == {'claude_code', 'copilot_cli', 'codex_cli'}
cx = sig['harnesses']['codex_cli']
assert cx['usd_today'] is None and cx['proxy_today'] == 0.9
for prof in ('S', 'M'):
    for h in sig['harnesses'].values():
        assert h['est'] is None or prof in h['est']
m = sig['harnesses']['codex_cli']['est']['S']['mid']
assert m is None or (m['billed_usd'] is None and m['usd_api_equivalent'] > 0)
assert '{model}' in sig['harnesses']['claude_code']['command_template']
deg = ja.build_harness_signal({}, pc, None, None)
assert deg['harnesses']['copilot_cli']['est'] is None
assert deg['harnesses']['codex_cli']['est'] is None
assert deg['harnesses']['claude_code']['available_today'] is False
assert any('pricing unavailable' in n for n in deg['notes'])
print('T5 smoke OK')
PY
```

### T6 — Wire signals.harness into the collector; revise the summarizer prompts
- status: done
- model: sonnet
- depends: T1, T5
- independent: no

**Brief.** Per PLAN.md D6. Edit `bin/journal_collect.py` and `bin/journal_summarize.py`
(only these two files). NOTE: T1 already edited `journal_collect.py` — build on its state.

In `bin/journal_collect.py`:
1. Beside the existing loads add `ja = _load("journal_advisor")  # harness routing signals (advisory-only)`.
2. After the line `signals = {"kit_tasks": kit_tasks, "inbox": inbox, "wip": wip}` and
   BEFORE the `kit_errors` conditional, insert:
   ```python
   try:
       signals["harness"] = ja.build_harness_signal(
           reports, pricing_claude, pricing_copilot, pricing_codex)
   except Exception as e:  # advisory must never break the nightly collect
       signals["harness_error"] = f"advisor failed: {e!r}"
   ```
3. Extend the module docstring's signals sentence to name the fourth signal family
   (`harness` — advisory routing signals; failure degrades to `harness_error`).

In `bin/journal_summarize.py`, inside `build_prompts` — TWO pinned string replacements
(exact old → exact new; if an old string is not found verbatim, STOP and report):

Replacement A (technical prompt). OLD:
```python
        "AI-assisted work from the digest below. Use ONLY the digest facts. Do NOT guess\n"
        "costs: sources marked unpriced (priced=false, e.g. Codex) MUST be labeled\n"
        "\"unpriced\" and never assigned a dollar figure.\n\n"
```
NEW:
```python
        "AI-assisted work from the digest below. Use ONLY the digest facts. Do NOT guess\n"
        "costs: sources marked unpriced (priced=false) MUST be labeled \"unpriced\" and\n"
        "never assigned a dollar figure — with ONE exception: when\n"
        "sources.codex_cli.extra.codex_proxy exists, report its api_equivalent_usd_total\n"
        "as an API-equivalent relative-burn proxy, explicitly labeled \"not a bill\", and\n"
        "never add it to any billed total.\n\n"
```

Replacement B (next-day prompt). OLD:
```python
        "## How to run\n"
        "  Concrete commands to resume the work (for example, resume a kit with\n"
        "  `/polytropos:execute <slug>`).\n\n"
        + digest_block + "\n\n"
```
NEW:
```python
        "## How to run\n"
        "  Concrete commands to resume the work (for example, resume a kit with\n"
        "  `/polytropos:execute <slug>`).\n\n"
        "When signals.harness exists (and only then), ALSO end the document with this H2\n"
        "section:\n"
        "## Harness plan\n"
        "  For each To-do above, recommend a harness (Claude Code / Copilot CLI / Codex\n"
        "  CLI), a model tier, a ready-to-paste command built from that harness's\n"
        "  command_template in signals.harness (fill {model} with the recommended model\n"
        "  id from its est entries), and a one-line WHY grounded in the signals.harness\n"
        "  estimates and today's usage. Advisory only — the user decides and runs it;\n"
        "  nothing auto-executes. Codex dollar figures are API-equivalent relative-burn\n"
        "  proxies, never bills.\n\n"
        + digest_block + "\n\n"
```

Nothing else in the summarizer changes: `DOCS`, H1s, the three pre-existing H2s per prompt,
`build_dispatch`, `summarize`, tiers, `--dry-run` semantics all stay byte-identical. The
narrative prompt is untouched. Update the module docstring with one sentence noting the
labeled-proxy exception and the conditional Harness plan section.

Gotchas: the frozen summarize tests locate `## Sessions & cost` / `## Models` /
`## Repos & commits` and `## Start here` / `## To-dos` / `## How to run` by `str.index` —
your insertions must not rename, remove, or reorder them (Replacement B adds AFTER
`## How to run`). The frozen collect tests assert `frozenset(digest) == DIGEST_TOP_KEYS` —
`signals` is one key, so adding `signals["harness"]` inside it is safe.

**Acceptance.**
- All four frozen journal test files pass byte-unmodified; full suite green.
- `journal_summarize.py --dry-run` output contains `## Harness plan`,
  `relative-burn proxy`, and `not a bill`.
- A collect run over temp fixtures yields a digest whose `signals.harness.advisory` is
  true and whose `signals.harness.harnesses` has the three pinned keys.
- `git diff --name-only` (beyond T1/T5's files) adds only `bin/journal_collect.py` and
  `bin/journal_summarize.py`.

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests -p 'test_journal_summarize.py' && \
python3 -m unittest discover -s tests -p 'test_journal_collect.py' && \
TMP=$(mktemp -d) && mkdir -p "$TMP/claude" "$TMP/copilot" "$TMP/codex" "$TMP/kits" && \
python3 bin/journal_collect.py --date 2026-01-15 --utc --journal-dir "$TMP/journal" \
  --claude-projects "$TMP/claude" --copilot-home "$TMP/copilot" --codex-home "$TMP/codex" \
  --kits-dir "$TMP/kits" && \
python3 -c "
import json
d = json.load(open('$TMP/journal/2026-01-15/digest.json'))
h = d['signals']['harness']
assert h['advisory'] is True and set(h['harnesses']) == {'claude_code', 'copilot_cli', 'codex_cli'}
assert d['schema_version'] == 1
print('harness signal OK')" && \
python3 bin/journal_summarize.py --date 2026-01-15 --utc --journal-dir "$TMP/journal" --dry-run > "$TMP/dry.txt" && \
grep -q '## Harness plan' "$TMP/dry.txt" && \
grep -q 'relative-burn proxy' "$TMP/dry.txt" && \
grep -q 'not a bill' "$TMP/dry.txt" && \
python3 -m unittest discover -s tests && \
echo T6 OK
```

### T7 — New tests: tests/test_journal_advisor.py
- status: done
- model: sonnet
- depends: T6
- independent: no

**Brief.** Per PLAN.md D5/D6/D7. Create `tests/test_journal_advisor.py` (NEW file). House
conventions as in T2/T4 (importlib-load `bin/journal_advisor.py`, `bin/journal_collect.py`,
`bin/journal_summarize.py` by absolute path; temp dirs; zero `Path.home()`; drive `main`
in-process). Use SYNTHETIC pricing dicts for advisor unit tests (fake ids like
`"fake-haiku-1"` with tiers matching each file's vocabulary — claude: `haiku`/`sonnet`;
copilot/codex: `cheap`/`mid`; include `task_profiles` with `"S"`/`"M"`,
`cache_read_multiplier`, copilot `billing_unit.usd_per_credit`, codex `cached_date`).
Cover at least:

1. **Shape**: `build_harness_signal` returns the pinned top-level keys, `advisory is
   True`, `note == ADVISORY_NOTE`, three harness keys, `command_template` values match
   `COMMAND_TEMPLATES` verbatim (placeholder intact).
2. **Estimate math reuse**: for the synthetic copilot dict, the `usd_est`/`aic_est` in a
   slot equal `cp.est_cost(...)['usd']/['aic']` called directly (load `copilot_pricing`
   yourself and compare); for codex, `usd_api_equivalent` equals
   `cxp.est_cost(...)['usd_api']` and `billed_usd` is None; for claude, `usd_est` matches
   the documented formula computed in the test from the synthetic dict.
3. **Slot resolution**: claude slots pick the FIRST model of tier `haiku`/`sonnet` in file
   order (put two haiku-tier fakes in the dict; assert the first wins); codex slots follow
   `resolve_tier`'s skip-up (a dict with no `cheap`-tier model → the slot resolves upward,
   exactly what `cxp.resolve_tier` returns).
4. **Degradation, never fabrication**: pricing None → `est is None` + a
   `pricing unavailable` note; missing report → `available_today False`,
   `sessions_today 0`, `usd_today None`; unpopulated tier → `None` slot + note; empty
   `reports` dict → all three entries present, nothing raises.
5. **Codex passthrough honesty**: a codex report with `extra.codex_proxy` → `proxy_today`
   equals its total while `usd_today` is None; without the proxy → `proxy_today` is None.
6. **Collector wiring**: end-to-end `jc.main([...])` over empty temp fixture homes (as in
   T6's verify) → digest carries `signals.harness` with `advisory True`; and the
   crash-degradation path: monkeypatch `jc.ja.build_harness_signal` to raise (via
   `unittest.mock.patch.object`) → digest carries `signals.harness_error` containing
   `advisor failed`, NO `harness` key, exit code 0.
7. **Prompt revisions**: `jsz.build_prompts(digest)` — technical prompt contains
   `api_equivalent_usd_total` and `not a bill`; next_day prompt contains `## Harness plan`
   AFTER `## How to run` (compare `str.index`), and the three legacy H2s in their pinned
   order; narrative prompt does NOT contain `Harness plan`.

**Acceptance.**
- New file green; full suite green; four frozen journal test files byte-unchanged;
  grep-clean (`Path\.home|sqlite|urllib|http\.client|socket|gpt-5` absent).

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests -p 'test_journal_advisor.py' && \
python3 -m unittest discover -s tests && \
git diff --quiet -- tests/test_journal_sources.py tests/test_journal_collect.py tests/test_journal_summarize.py tests/test_journal_schedule.py && \
! grep -nE 'Path\.home|sqlite|urllib|http\.client|socket|gpt-5' tests/test_journal_advisor.py && \
echo T7 OK
```

---

## Phase 4 — Surfaces, docs, closure

### T8 — Extend skills/journal/SKILL.md (BODY-only)
- status: done
- model: sonnet
- depends: T3, T6
- independent: no

**Brief.** Per PLAN.md D8. Edit `skills/journal/SKILL.md` ONLY. The plugin is LIVE — the
YAML frontmatter (lines 1–5: `---`, `name:`, `description:`, `allowed-tools:`, `---`) must
stay byte-identical to `git show HEAD:skills/journal/SKILL.md`. BODY changes only:

1. After the existing `## Inbox & schedule` section, add a new H2 section exactly titled
   `## External tools (Teams / Outlook / Copilot Studio)` describing the two-pass flow:
   generate the pack with
   ```bash
   python3 "$ROOT/bin/journal_askpack.py" --date <date> --print
   ```
   run each printed prompt inside the matching Microsoft tool's AI, paste the bullet
   results into `journal/inbox.md`, then re-run the collector and redo the summaries so
   the enriched inbox flows in. State explicitly: this is offline text generation — the
   journal never adds network, OAuth, Graph, or MCP; the pack asks for at most 15
   subject-level bullets per tool (no message bodies).
2. In the `## Collect the digest` section, append one sentence: the digest now also deepens
   Codex with the day's rollout files and, when tokens are found, carries a clearly-labeled
   API-equivalent relative-burn proxy under `sources.codex_cli.extra.codex_proxy` — never a
   bill (`billed_usd` stays null), never counted into `usd_priced`.
3. In the `## Write the summaries (in this session — default)` section, append one
   sentence: when `signals.harness` is present, follow the next-day prompt's `## Harness
   plan` section — per-task harness + model tier + ready-to-paste command + one-line WHY,
   advisory only.
4. Leave the `## Privacy` section's existing text intact; append one sentence noting that
   pasted ask-the-tools bullets are inbox text and therefore also travel to the model.

**Acceptance.**
- Frontmatter (first 5 lines) byte-identical to HEAD; the new H2 exists; the pinned
  phrases (`ask-the-tools`/`journal_askpack.py`, `relative-burn proxy`, `never a bill`,
  `Harness plan`, `advisory`) appear; existing H2s untouched.
- Full suite green (nothing imports the skill, but run it anyway); `git diff --name-only`
  shows only `skills/journal/SKILL.md`.

**Verify.**
```bash
cd /path/to/polytropos && \
diff <(git show HEAD:skills/journal/SKILL.md | head -5) <(head -5 skills/journal/SKILL.md) && \
grep -q '^## External tools (Teams / Outlook / Copilot Studio)' skills/journal/SKILL.md && \
grep -q 'journal_askpack.py' skills/journal/SKILL.md && \
grep -q 'relative-burn proxy' skills/journal/SKILL.md && \
grep -q 'Harness plan' skills/journal/SKILL.md && \
grep -qi 'advisory' skills/journal/SKILL.md && \
python3 -m unittest discover -s tests && \
echo T8 OK
```

### T9 — Extend docs/DAILY-JOURNAL.md
- status: done
- model: sonnet
- depends: T1, T3, T5
- independent: no

**Brief.** Per PLAN.md D4/D8. Edit `docs/DAILY-JOURNAL.md` ONLY.

1. In the `## Sources & the adapter contract` section, the first paragraph currently says
   Codex CLI is `(counted but unpriced by design — no Codex pricing exists anywhere under
   data/)`. Replace that parenthetical with `(counted, plus a clearly-labeled
   API-equivalent relative-burn proxy priced from data/pricing.codex.json — never a bill)`.
2. Add a new H2 section `## Codex: deeper logs, labeled proxy` (place it after `## The
   digest`): the adapter now also reads the day's rollout files
   (`~/.codex/sessions/YYYY/MM/DD/*.jsonl`) by reusing `bin/codex_usage.py` read-only; the
   day's directory name is the day-membership rule; when tokens are found and priced from
   `data/pricing.codex.json`, the digest carries
   `sources.codex_cli.extra.codex_proxy` with `billed_usd: null`, an
   `api_equivalent_usd_total`, per-model figures, and the verbatim disclaimer — the report
   stays `priced: false`/`usd: null` and the proxy is NEVER added to `totals.usd_priced`
   (a relative-burn proxy is not a bill; subscription Codex is usage-limited, not
   token-billed).
3. Add a new H2 section `## External tools: the ask-the-tools pack` (place it after
   `## Next-day planning & the inbox`): the two-pass flow, `bin/journal_askpack.py`, the
   `journal/<date>/ask-the-tools.md` output, the 15-bullet subject-level hygiene bound,
   and the explicit statement that this is offline text generation — Graph/OAuth/MCP stay
   deferred (update the `## Deferred` section's Teams/Outlook paragraph with one sentence
   noting the ask-the-tools pack is the shipped offline stand-in).
4. Add a new H2 section `## The harness plan (advisory)` (place it after the ask-the-tools
   section): `bin/journal_advisor.py` computes `signals.harness` — per-harness usage-today
   plus cheap/mid task estimates derived from the three pricing files at run time (files
   never merged, no rates hardcoded), plus ready-to-paste command templates; the next-day
   document's `## Harness plan` section turns exactly these signals into per-task
   recommendations (harness + tier + command + WHY). Advisory only — nothing
   auto-executes; Codex figures stay labeled proxies.

Use only facts from PLAN.md and the shipped code — no invented flags or numbers; never a
`gpt-5.6-*` id or a price literal in the doc.

**Acceptance.**
- The stale phrase `no Codex pricing exists anywhere under` is gone from the file; the
  three new H2s exist; the Deferred section notes the offline stand-in; no price/model-id
  literals added.
- `git diff --name-only` shows only `docs/DAILY-JOURNAL.md`; full suite green.

**Verify.**
```bash
cd /path/to/polytropos && \
! grep -q 'no Codex pricing exists anywhere under' docs/DAILY-JOURNAL.md && \
grep -q '^## Codex: deeper logs, labeled proxy' docs/DAILY-JOURNAL.md && \
grep -q '^## External tools: the ask-the-tools pack' docs/DAILY-JOURNAL.md && \
grep -q '^## The harness plan (advisory)' docs/DAILY-JOURNAL.md && \
grep -q 'never a bill' docs/DAILY-JOURNAL.md && \
! grep -nE 'gpt-5\.6' docs/DAILY-JOURNAL.md && \
python3 -m unittest discover -s tests && \
echo T9 OK
```

### T10 — Pinned stale-sentence swaps in HOW-IT-WORKS (md + html)
- status: done
- model: haiku
- depends: T1
- independent: no

**Brief.** Two surgical, pinned replacements — nothing else in either file.

In `docs/HOW-IT-WORKS.md`, find the exact sentence:
`Codex activity is counted but **never priced** (no Codex pricing exists under \`data/\`, by design).`
Replace it with:
`Codex activity is counted and, when the day's rollout logs carry tokens, shown as a clearly-labeled API-equivalent relative-burn proxy priced from \`data/pricing.codex.json\` — never a bill, never added to the priced total.`

In `docs/how-it-works.html`, find the exact fragment:
`Codex activity is counted but <strong>never priced</strong> (no Codex pricing exists under <code>data/</code>, by design).`
Replace it with:
`Codex activity is counted and, when the day's rollout logs carry tokens, shown as a clearly-labeled API-equivalent relative-burn proxy priced from <code>data/pricing.codex.json</code> — never a bill, never added to the priced total.`

If either exact string is not present verbatim, STOP and report — do not approximate.

**Acceptance.**
- Both old fragments gone, both new fragments present; `git diff --stat` shows exactly one
  changed line region per file and only these two files.

**Verify.**
```bash
cd /path/to/polytropos && \
! grep -q 'no Codex pricing exists under' docs/HOW-IT-WORKS.md && \
! grep -q 'no Codex pricing exists under' docs/how-it-works.html && \
grep -q 'relative-burn proxy' docs/HOW-IT-WORKS.md && \
grep -q 'relative-burn proxy' docs/how-it-works.html && \
git diff --name-only -- docs | grep -vE 'DAILY-JOURNAL\.md|HOW-IT-WORKS\.md|how-it-works\.html' | wc -l | grep -q '^ *0$' && \
echo T10 OK
```

### T11 — Final sweep: full suite + fence audit
- status: done
- model: haiku
- depends: T2, T4, T7, T8, T9, T10
- independent: no

**Brief.** No file changes (if any check fails, report — do not fix). Run the full audit:
frozen files byte-clean, reused scripts unedited, home/network/sqlite/model-id hygiene in
everything this kit added or touched, suite green.

**Acceptance.** Every command in the verify chain passes.

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests && \
git diff --quiet -- tests/test_journal_sources.py tests/test_journal_collect.py tests/test_journal_summarize.py tests/test_journal_schedule.py && \
git diff --quiet -- bin/journal_schedule.py bin/codex_usage.py bin/codex_pricing.py bin/copilot_pricing.py bin/cost_report.py bin/copilot_usage.py bin/copilot_execute.py bin/session_cost.py && \
git diff --quiet -- data README.md .claude-plugin copilot codex && \
! grep -nE 'gpt-5\.6' bin/journal_askpack.py bin/journal_advisor.py bin/journal_sources.py bin/journal_collect.py bin/journal_summarize.py tests/test_journal_codex_augment.py tests/test_journal_askpack.py tests/test_journal_advisor.py && \
! grep -nE 'urllib|http\.client|socket|sqlite' bin/journal_askpack.py bin/journal_advisor.py tests/test_journal_codex_augment.py tests/test_journal_askpack.py tests/test_journal_advisor.py && \
test "$(grep -c 'Path.home()' bin/journal_collect.py)" = "3" && \
test "$(grep -c 'Path.home()' bin/journal_askpack.py bin/journal_advisor.py | grep -c ':0$')" = "2" && \
git show HEAD:skills/journal/SKILL.md | head -5 | diff - <(head -5 skills/journal/SKILL.md) && \
echo T11 OK
```
