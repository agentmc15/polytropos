# TASKS — daily-journal

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the Research findings (pinned data
surfaces + reuse functions), decisions D1–D13, the OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `daily-journal-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. **T2 → T3 → T4 are strictly serial (same file).**
Dispatch `daily-journal-reviewer` at each phase end.

Standing rules for every task — the #1 one first:

- **Never read or write the real `~/.claude`, `~/.copilot`, or `~/.codex` from a test or
  verify command.** Runtime defaults may point there; execution never does — every run goes
  against synthetic fixtures in temp dirs with `--claude-projects` / `--copilot-home` /
  `--codex-home` / `--journal-dir` / `--launch-agents-dir` overridden. `Path.home()` appears
  ONLY in the four pinned runtime-default constants (3 in `bin/journal_collect.py`, 1 in
  `bin/journal_schedule.py`), never in tests. Sole exception: T3's sanctioned read-only peek
  (its brief).
- **Never invoke a real `claude`, `copilot`, or `codex` CLI, and never execute `launchctl`.**
  The summarizer's dispatch is injectable; tests use fake runners or temp stub executables
  never named `claude`; `--dry-run` spawns nothing.
- **Never open a `*.db`/SQLite file; no `import sqlite3` in any new file.** JSONL + flat text
  only (PLAN.md D1).
- Never write outside this repo and test temp dirs (`~/.claude`, `~/Library/LaunchAgents`
  included). No network, no OAuth, no tokens, no secrets. No `/private/tmp/` path in any
  deliverable.
- Never edit `data/pricing.json`, `data/pricing.copilot.json`, `.claude-plugin/`, existing
  `skills/*` (or mirrors), `copilot/`, the completed kits, or any existing `bin/`/`tests/`
  file. Existing bin scripts are imported read-only via importlib. Sanctioned existing-file
  edits: `.gitignore` (T1), `README.md` (T13), `CLAUDE.md` (T14) — pinned insertions only.
- Never hardcode a price, credit value, allowance, or model id — derive from the pricing
  files at run time (tier-vocabulary strings and synthetic fixture ids/values in tests are
  fine). Never invent a Codex price.
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests [-p '<file>.py']`
  (the dotted-module form is broken on this machine). Paths via `Path(__file__).resolve()`,
  never `$PWD`.

---

## Phase 1 — Gitignore + the source-adapter engine

### T1 — Gitignore the journal tree
- status: done
- model: haiku
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D11, all journal output and the inbox live under one gitignored
personal-data root. Append to `.gitignore` (which currently contains exactly three lines:
`.claude/settings.local.json`, `__pycache__/`, `.DS_Store`) these two lines at the end of the
file:

```
# daily-journal output + inbox (personal data — never committed)
journal/
```

Change nothing else. Do NOT create the `journal/` directory itself — the collector creates it
at runtime.

**Acceptance.** `.gitignore` has the two new lines appended; `git check-ignore` confirms
`journal/x` and `journal/2026-01-01/digest.json` are ignored; no `journal/` directory exists in
the repo; git shows only `.gitignore` modified by this task.

**Verify.**
```bash
cd /path/to/polytropos && git check-ignore -q journal/x && git check-ignore -q journal/2026-01-01/digest.json && test ! -e journal && tail -2 .gitignore | grep -q '^journal/$' && python3 -m unittest discover -s tests && echo 'T1 OK'
```

---

### T2 — Create bin/journal_sources.py: engine + claude_code + copilot_cli adapters
- status: done
- model: opus
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D1–D5: the adapter engine and the two priced adapters. New file
`bin/journal_sources.py`, stdlib-only, module docstring stating: what it is (the daily-journal
source-adapter engine), that ingestion is STRICTLY READ-ONLY (never writes under a source
root, never opens `*.db`/SQLite, never invokes a CLI to gather), that adapters take an explicit
`ctx` (no `Path.home()` anywhere in this module), and that the per-source report shape is
schema_version 1. Follow `bin/` conventions: pure functions, no `main` needed (this module is a
library; a tiny `if __name__ == "__main__":` demo is NOT wanted).

**Reuse via importlib (the `bin/session_cost.py` pattern — read that file first):**
`_load(name)` helper using `spec_from_file_location(name, Path(__file__).resolve().parent /
f"{name}.py")`; module-level `cr = _load("cost_report")` and `cu = _load("copilot_usage")`.
Never edit those files.

**Pinned building blocks:**

- `ISO = "%Y-%m-%d"`-style helpers are optional; timestamps in reports are emitted with
  `dt.isoformat()`.
- `day_window(date_str=None, utc=False) -> (day_start, day_end)` — aware datetimes. `date_str`
  is `YYYY-MM-DD` (ValueError propagates on garbage; the CLI catches it later); None → today.
  `utc=False`: local midnight via
  `datetime.combine(d, time.min).astimezone()`; `utc=True`:
  `datetime.combine(d, time.min, tzinfo=timezone.utc)`. `day_end = day_start +
  timedelta(days=1)`.
- `empty_report(source, priced) -> dict` — exactly the PLAN.md D4 report keys:
  `source, available (False), priced, deferred (False), sessions (0), first_ts (None),
  last_ts (None), models ({}), totals ({"input": 0, "output": 0, "cache_read": 0,
  "cache_write": 0}), usd (None), projects ([]), tool_uses (0), errors ([]), notes ([]),
  extra ({})`.
- `_span(report, when)` helper — fold an aware datetime into `first_ts`/`last_ts` (stored as
  ISO strings).
- `run_adapters(ctx) -> dict` — `{name: collect_fn(ctx)}` over the ordered `ADAPTERS`
  registry; each call wrapped in try/except Exception → `empty_report(name, False)` with
  `errors = [f"adapter crashed: {e!r}"]`. The registry at module bottom:
  `ADAPTERS = (("claude_code", collect_claude), ("copilot_cli", collect_copilot))` — T3 and
  T4 will extend this tuple; leave a one-line comment saying codex/git/cursor/vscode rows are
  added by later tasks.

**`collect_claude(ctx)`** — `ctx["claude_projects"]` (Path|None), `ctx["pricing_claude"]`
(dict|None), `ctx["day_start"]`, `ctx["day_end"]`. Report `priced=True`. If the root is None or
not a directory → `available=False`, note `"claude projects dir not found"`, return. Else
`available=True`; walk `sorted(root.rglob("*.jsonl"))`, `read_text(errors="replace")`
(OSError → `errors`, continue), per non-blank line `json.loads` (failures skipped), then
`rec = cr.extract_record(obj)`; skip None. Dedupe `msg_id` GLOBALLY across all files (subagent
turns are woven into main transcripts — PLAN.md Research findings). `when =
cr.parse_timestamp(obj.get("timestamp"))`; `when is None` → increment
`extra["untimestamped_records"]`, skip (D5 divergence from cost_report — comment it). Require
`day_start <= when < day_end` else skip. For in-window records: `key = cr.match_model(model,
pricing)` — matched: accumulate into `models[key]` (input/output/cache_read/cache_write/
messages and `usd += cr.price(key, u, when, pricing)`) and `totals`; unmatched (and model not
starting `<`): accumulate tokens into `models[model]` with `usd=None` and add the raw id to
`extra["unpriced_models"]` (sorted unique list). Track sessions = distinct
`obj.get("sessionId") or path.stem` among in-window records; `tool_uses` summed from
extract_record; projects = sorted unique labels — `Path(obj["cwd"]).name` when a record
carries a non-empty `cwd`, else the project slug (`path.relative_to(root).parts[0]`);
`_span` per record. Report `usd` = sum of priced model usd (float, 0.0 if none);
`extra["messages"]` = in-window deduped record count. If `pricing_claude` is None, treat every
model as unmatched (usd stays None → set report `usd=None`, note `"no pricing provided"`).

**`collect_copilot(ctx)`** — `ctx["copilot_home"]` (Path|None), `ctx["pricing_copilot"]`.
Report `priced=True`. Root None or `<home>/session-state` not a dir → `available=False` +
note. Else `sessions, errors = cu.collect_sessions(home / "session-state")`; extend report
errors. Per session dict `s` (keys from `cu.parse_events` + `"workspace"` + `"id"` — see
PLAN.md Research findings): membership rule (D5): `last = s.get("last_seen")`; `last is None`
→ increment `extra["untimestamped_sessions"]`, skip; require `day_start <= last < day_end`
else skip. For member sessions: `tokens, output_only = cu.effective_tokens(s)`; seen models =
`s["models"]`; matched = `[cu.match_model(m, pricing) for m in seen if
cu.match_model(m, pricing)]` deduped in order; attribution = the sole matched model when
exactly one distinct match (exact) else the matched `s["last_model"]` (approx — append a note
`"<id>: multi-model session attributed to last model"` once per such session) else None →
tokens accumulate under the raw last model (or `"unknown"`) with `usd=None` +
`extra["unpriced_models"]`. Priced sessions: `usd_s = cu.price_tokens(tokens, key, pricing)`;
accumulate `models[key]` (token fields + `messages` += 1 meaning sessions here — name the
field `messages` anyway for report-shape uniformity) and `totals` and report `usd`.
`extra["aic"] = cu.usd_to_aic(report_usd, pricing)` (only when pricing present),
`extra["aiu_reported"]` = sum of `s["nano_aiu"]`/1e9 over member sessions,
`extra["turns"]` = summed per-turn output turns, `report["tool_uses"]` stays 0 (Copilot events
carry no tool counter — note it). `sessions` = member count; projects from
`cu.parse_workspace` result: `Path(ws["cwd"]).name` or `ws["name"]` when present; `_span` with
`first_seen`/`last_seen`. Output-only sessions (no tokenDetails) get a note
`"<session id>: output tokens only (no shutdown tokenDetails)"`.

GOTCHAS: no `Path.home()` in this module; no model-id/price literals (pricing comes in via
ctx; tests pass synthetic dicts); every `dict.get` defensive; floats summed then left raw
(rendering is the summarizer's problem); do NOT add codex/git here (T3/T4 own them, same
file, serial).

**Acceptance.**
- Heredoc fixture run (below): claude adapter dedupes by message id, day-filters, excludes
  untimestamped records with a count, prices from a SYNTHETIC pricing dict, buckets an
  unmatched model as unpriced; copilot adapter attributes a single-model session exactly,
  applies the last-event-day membership rule, and reports `aiu_reported`; both reports carry
  every pinned D4 key; `run_adapters` survives an adapter exception (probed by a broken ctx).
- Fixture homes byte-identical after the run (read-only proof).
- `Path.home()` count in `bin/journal_sources.py` is 0; no `sqlite` in the file (and no
  `subprocess` YET — T4's git adapter adds the sole sanctioned use, so the verify below
  deliberately greps only `sqlite`); no real model ids (grep below).
- Full suite green; only `bin/journal_sources.py` is new.

**Verify.**
```bash
cd /path/to/polytropos && H="$(mktemp -d)" && python3 - "$H" <<'PY' && rm -rf "$H" && ! grep -n 'Path.home()' bin/journal_sources.py && ! grep -n 'sqlite' bin/journal_sources.py && ! grep -nE 'claude-(fable|opus|sonnet|haiku)' bin/journal_sources.py && python3 -m unittest discover -s tests && echo 'T2 OK'
import hashlib, importlib.util, json, pathlib, sys
from datetime import datetime, timedelta, timezone
root = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("js", pathlib.Path("bin/journal_sources.py").resolve())
js = importlib.util.module_from_spec(spec); spec.loader.exec_module(js)
P_CL = {"cached_date": "2020-01-01", "cache_read_multiplier": 0.1, "cache_write_multiplier_5m": 1.25,
        "models": {"fake-big": {"display": "Fake Big", "tier": "opus", "input_per_mtok": 10.0, "output_per_mtok": 50.0}}}
P_CO = {"cached_date": "2020-01-01", "billing_unit": {"name": "FIC", "usd_per_credit": 0.5},
        "models": {"fake-co": {"display": "Fake Co", "tier": "mid", "input_per_mtok": 2.0,
                                "cached_input_per_mtok": 0.2, "output_per_mtok": 8.0}}}
day = datetime(2026, 6, 30, tzinfo=timezone.utc)
ctx = {"day_start": day, "day_end": day + timedelta(days=1),
       "claude_projects": root / "projects", "copilot_home": root / "cohome",
       "codex_home": None, "repos": [], "pricing_claude": P_CL, "pricing_copilot": P_CO}
proj = root / "projects" / "-tmp-projA"; proj.mkdir(parents=True)
def crec(model, ts, mid, inp=1000, out=100, cwd=None):
    o = {"timestamp": ts, "sessionId": "sess-1",
         "message": {"model": model, "id": mid, "usage": {"input_tokens": inp, "output_tokens": out}}}
    if cwd: o["cwd"] = cwd
    return json.dumps(o)
(proj / "sess-1.jsonl").write_text("\n".join([
    crec("fake-big-20260101", "2026-06-30T10:00:00Z", "m1", cwd="/tmp/projA"),
    crec("fake-big-20260101", "2026-06-30T11:00:00Z", "m1"),          # dup id -> dedupe
    crec("fake-big-20260101", "2026-06-29T10:00:00Z", "m2"),          # out of window
    crec("mystery-model", "2026-06-30T12:00:00Z", "m3"),              # unpriced
    json.dumps({"message": {"model": "fake-big", "id": "m4", "usage": {"input_tokens": 5, "output_tokens": 5}}}),  # no ts
    "garbage not json",
]) + "\n")
ss = root / "cohome" / "session-state" / "aaaa-1111"; ss.mkdir(parents=True)
(ss / "workspace.yaml").write_text("id: aaaa-1111\nname: fixt\ncwd: /tmp/projB\n")
def ev(t, ts, **data): return json.dumps({"type": t, "timestamp": ts, "data": data})
(ss / "events.jsonl").write_text("\n".join([
    ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-co"),
    ev("assistant.message", "2026-06-30T09:01:00Z", model="fake-co", outputTokens=50, apiCallId="a1"),
    ev("session.shutdown", "2026-06-30T09:02:00Z", totalNanoAiu=1500000000, totalPremiumRequests=1,
       currentModel="fake-co", tokenDetails={"input": {"tokenCount": 1000}, "cache_read": {"tokenCount": 0},
       "cache_write": {"tokenCount": 0}, "output": {"tokenCount": 50}}),
]) + "\n")
(ss / "session.db").write_bytes(b"NEVER-OPEN")
def snap(p):
    return {str(f): hashlib.md5(f.read_bytes()).hexdigest() for f in sorted(p.rglob("*")) if f.is_file()}
before = snap(root)
reports = js.run_adapters(ctx)
assert snap(root) == before, "fixture tree mutated — read-only contract broken"
cl = reports["claude_code"]; co = reports["copilot_cli"]
KEYS = {"source", "available", "priced", "deferred", "sessions", "first_ts", "last_ts", "models",
        "totals", "usd", "projects", "tool_uses", "errors", "notes", "extra"}
assert KEYS <= set(cl) and KEYS <= set(co), (set(cl), set(co))
assert cl["available"] and cl["sessions"] == 1 and cl["extra"]["untimestamped_records"] == 1, cl
assert cl["models"]["fake-big"]["messages"] == 1 and cl["models"]["fake-big"]["input"] == 1000, cl["models"]
assert "mystery-model" in cl["extra"]["unpriced_models"] and cl["models"]["mystery-model"]["usd"] is None, cl
exp = (1000 * 10.0 + 100 * 50.0) / 1e6
assert abs(cl["usd"] - exp) < 1e-9, (cl["usd"], exp)
assert "projA" in cl["projects"], cl["projects"]
assert co["available"] and co["sessions"] == 1 and abs(co["extra"]["aiu_reported"] - 1.5) < 1e-9, co
exp_co = (1000 * 2.0 + 50 * 8.0) / 1e6
assert abs(co["usd"] - exp_co) < 1e-9 and abs(co["extra"]["aic"] - exp_co / 0.5) < 1e-9, co
bad = dict(ctx); bad["claude_projects"] = 123  # provoke an adapter crash
rep2 = js.run_adapters(bad)
assert rep2["claude_code"]["errors"], "engine must catch adapter exceptions"
print("engine + claude + copilot adapters ok")
PY
```

---

### T3 — Add the codex_cli adapter (tolerant, unpriced) to bin/journal_sources.py
- status: done
- model: sonnet
- depends: T2
- independent: no

**Brief.** Per PLAN.md D6. Extend `bin/journal_sources.py` (T2's file — serial, same file)
with `collect_codex(ctx)` and register `("codex_cli", collect_codex)` in `ADAPTERS` after
`copilot_cli`. Codex CLI's JSONL is NOT format-pinned; build a tolerant extractor.

**Your ONE sanctioned research step (D1 exception):** you MAY read a few lines of the REAL
`~/.codex/session_index.jsonl` and `~/.codex/history.jsonl` strictly read-only (e.g.
`head -c 4000 ~/.codex/session_index.jsonl`) to learn actual field names — never write there,
never list or touch `~/.codex/sqlite/`, never read `~/.claude` or `~/.copilot`. If the files
are absent, proceed with the candidate lists below unchanged. Record what you observed in one
comment block above the constants. Tests (T5) still use ONLY synthetic fixtures.

Pinned candidate-key constants (extend from observation, never shrink):
- `CODEX_TS_KEYS = ("timestamp", "ts", "created_at", "updated_at", "time", "datetime")`
- `CODEX_SESSION_KEYS = ("session_id", "sessionId", "conversation_id", "id")`
- `CODEX_MODEL_KEYS = ("model", "model_id", "model_slug")`
- `CODEX_CWD_KEYS = ("cwd", "workdir", "working_directory", "dir", "path")`
- `CODEX_USAGE_KEYS = ("usage", "token_usage", "tokens", "token_counts")`
- token field mapping: `input_tokens`/`prompt_tokens` → input; `output_tokens`/
  `completion_tokens` → output; `cached_tokens`/`cache_read_input_tokens` → cache_read.

Helpers: `_codex_get(obj, keys)` — first present key at the top level, else one level down
under `"payload"`/`"data"`/`"info"` (depth ≤ 2, defensive). `_codex_ts(raw)` — None-safe:
try `cr.parse_timestamp` (ISO); else numeric epoch (int/float or digit-string; values
`> 1e12` are milliseconds → divide by 1000) → aware UTC datetime; else None.

`collect_codex(ctx)`: `ctx["codex_home"]` None or not a dir → `available=False` + note.
Report `priced=False`, `usd=None`, pinned note (verbatim):
`"Codex activity is counted but unpriced — no Codex pricing exists in data/ (by design)."`
Read ONLY the two filenames `session_index.jsonl` and `history.jsonl` directly under the home
(each optional; OSError → errors). Stream line by line (`errors="replace"`), `json.loads`
per line (failures/non-dicts skipped and counted in `extra["malformed_lines"]`). Per record:
`when = _codex_ts(_codex_get(obj, CODEX_TS_KEYS))`; `when is None` → count in
`extra["untimestamped_records"]`, skip; window-filter on `[day_start, day_end)`. In-window:
`extra["records"] += 1`; session ids collected from `CODEX_SESSION_KEYS` → `sessions` =
distinct count; model from `CODEX_MODEL_KEYS` (default `"unknown"`) → `models[model]` token
fields accumulated from the usage mapping when present (all zero otherwise), `messages` += 1,
`usd` stays None; `totals` accumulated the same way; cwd → `projects` (basename, sorted
unique); `_span`. `tool_uses` stays 0. Never look at any other file under the home.

GOTCHAS: no `sqlite3`, no writes, no `Path.home()`; per-field `.get` everywhere; both files
missing but home present → `available=True`, `sessions=0`, note `"no codex JSONL found"`;
never fabricate token counts.

**Acceptance.** Heredoc run: mixed ISO/epoch-seconds/epoch-ms timestamps parsed; out-of-window
and untimestamped records excluded with counts; malformed lines counted, no crash; sessions
deduped across both files; token counts accumulated where present, zeros where absent;
`priced` False and `usd` None with the pinned note; fixture tree byte-identical; the sqlite
subdir present in the fixture and never opened. Registry order now
`claude_code, copilot_cli, codex_cli`. Full suite green; still no `Path.home()` or `sqlite`
in the file (`subprocess` arrives only with T4's git adapter).

**Verify.**
```bash
cd /path/to/polytropos && H="$(mktemp -d)" && python3 - "$H" <<'PY' && rm -rf "$H" && ! grep -n 'Path.home()' bin/journal_sources.py && ! grep -n 'sqlite' bin/journal_sources.py && python3 -m unittest discover -s tests && echo 'T3 OK'
import hashlib, importlib.util, json, pathlib, sys
from datetime import datetime, timedelta, timezone
root = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("js", pathlib.Path("bin/journal_sources.py").resolve())
js = importlib.util.module_from_spec(spec); spec.loader.exec_module(js)
day = datetime(2026, 6, 30, tzinfo=timezone.utc)
epoch_in = int(datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc).timestamp())
epoch_out = int(datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc).timestamp())
home = root / "codex"; (home / "sqlite").mkdir(parents=True)
(home / "sqlite" / "codex-dev.db").write_bytes(b"NEVER-OPEN")
(home / "session_index.jsonl").write_text("\n".join([
    json.dumps({"id": "s1", "created_at": "2026-06-30T09:00:00Z", "cwd": "/tmp/projC", "model": "codex-fake-1"}),
    json.dumps({"id": "s2", "created_at": "2026-06-29T09:00:00Z"}),   # out of window
    "NOT JSON",
]) + "\n")
(home / "history.jsonl").write_text("\n".join([
    json.dumps({"session_id": "s1", "ts": epoch_in, "usage": {"input_tokens": 200, "output_tokens": 30}}),
    json.dumps({"session_id": "s1", "ts": epoch_in * 1000 + 500, "model": "codex-fake-1"}),  # ms epoch, no usage
    json.dumps({"session_id": "s3", "ts": epoch_out}),                # out of window
    json.dumps({"session_id": "s4"}),                                  # no timestamp
    json.dumps([1, 2, 3]),                                             # non-dict
]) + "\n")
ctx = {"day_start": day, "day_end": day + timedelta(days=1), "claude_projects": None,
       "copilot_home": None, "codex_home": home, "repos": [], "pricing_claude": None, "pricing_copilot": None}
def snap(p):
    return {str(f): hashlib.md5(f.read_bytes()).hexdigest() for f in sorted(p.rglob("*")) if f.is_file()}
before = snap(root)
reports = js.run_adapters(ctx)
assert snap(root) == before, "fixture tree mutated"
names = [n for n, _ in js.ADAPTERS]
assert names[:3] == ["claude_code", "copilot_cli", "codex_cli"], names
cx = reports["codex_cli"]
assert cx["available"] and cx["priced"] is False and cx["usd"] is None, cx
assert cx["extra"]["records"] == 3 and cx["sessions"] == 1, cx["extra"]
assert cx["extra"]["untimestamped_records"] == 1 and cx["extra"]["malformed_lines"] >= 2, cx["extra"]
assert cx["totals"]["input"] == 200 and cx["totals"]["output"] == 30, cx["totals"]
assert any("unpriced" in n for n in cx["notes"]), cx["notes"]
assert "projC" in cx["projects"], cx["projects"]
print("codex adapter ok")
PY
```

---

### T4 — Add the git adapter + cursor/vscode deferred stubs to bin/journal_sources.py
- status: done
- model: sonnet
- depends: T3
- independent: no

**Brief.** Per PLAN.md D7 and D2. Extend `bin/journal_sources.py` (serial, same file) with
`collect_git(ctx)`, `collect_cursor(ctx)`, `collect_vscode(ctx)`; final registry order:
`claude_code, copilot_cli, codex_cli, git, cursor, vscode`.

**`collect_git(ctx)`** — the ONLY subprocess use in this module (`import subprocess` becomes
sanctioned here — update T2's grep expectations accordingly: `subprocess` may now appear, but
ONLY inside `collect_git`/its helper). Report `priced=False`, `usd=None`, `available=True`
(git activity is config-driven, not home-dir-driven). `ctx["repos"]` empty → note
`"no repos configured — set journal/config.json \"repos\" or pass --repo"`, return. Per repo
root (Path): not a dir or no `.git` entry inside → note `"<root>: not a git repo"`, continue.
Helper `_git(root, *args)` → `subprocess.run(["git", "-C", str(root), *args],
capture_output=True, text=True, timeout=20)`; nonzero/OSError/TimeoutExpired → raise-to-catch
or return None with an `errors` entry `"<root>: <detail>"`. Commands (pinned):
1. `log --since <day_start.isoformat()> --until <day_end.isoformat()>
   --pretty=format:%h%x1f%aI%x1f%an%x1f%s%x1e --no-show-signature` — split records on
   `\x1e`, fields on `\x1f` → `{"sha", "date", "author", "subject"}`; cap 50 per repo with a
   note when truncated.
2. `status --porcelain` — `dirty_files` = lines not starting `??`, `untracked` = lines
   starting `??`.
3. `rev-parse --abbrev-ref HEAD` → `branch` (strip; failures → `""`).
Accumulate `extra["repos"]` = list of `{"root": str(root), "branch", "commits",
"commit_count", "dirty_files", "untracked"}`; report `projects` = sorted repo basenames with
`commit_count > 0` or dirty/untracked > 0; `sessions` stays 0; `_span` folds each commit's
`%aI` date (via `cr.parse_timestamp`).

**`collect_cursor` / `collect_vscode`** — pure stubs: `empty_report(name, False)` with
`deferred=True` and one pinned note each (verbatim):
- cursor: `"Deferred: Cursor usage lives in state.vscdb (SQLite, undocumented schema); v1 is JSONL-only — see docs/DAILY-JOURNAL.md."`
- vscode: `"Deferred: VS Code Copilot chat usage lives in state.vscdb (SQLite, undocumented schema); v1 is JSONL-only — see docs/DAILY-JOURNAL.md."`

GOTCHAS: git commands are read-only plumbing — never `add`/`commit`/`fetch`/anything that
writes; no `Path.home()`; `git` binary missing (FileNotFoundError) → one report-level error,
not a crash.

**Acceptance.** Heredoc run against a temp git repo with one in-window commit (committer AND
author dates pinned via env), one out-of-window commit, a dirty file and an untracked file:
commit list has exactly the in-window commit with sha/author/subject; dirty/untracked counts
right; branch nonempty; a non-repo path produces a note, not a crash; stubs report
`deferred=True, available=False` with the pinned notes; registry order pinned; full suite
green.

**Verify.**
```bash
cd /path/to/polytropos && H="$(mktemp -d)" && R="$H/repoA" && mkdir -p "$R" && git -C "$R" init -q -b main && echo base > "$R/tracked.txt" && git -C "$R" add tracked.txt && GIT_COMMITTER_DATE="2026-06-01T10:00:00+00:00" git -C "$R" -c user.email=t@t -c user.name=T commit -q -m "old commit" --date "2026-06-01T10:00:00+00:00" && GIT_COMMITTER_DATE="2026-06-30T10:00:00+00:00" git -C "$R" -c user.email=t@t -c user.name=T commit -q --allow-empty -m "in-window work" --date "2026-06-30T10:00:00+00:00" && echo change >> "$R/tracked.txt" && echo new > "$R/untracked.txt" && python3 - "$H" "$R" <<'PY' && rm -rf "$H" && ! grep -n 'Path.home()' bin/journal_sources.py && ! grep -n 'sqlite' bin/journal_sources.py && python3 -m unittest discover -s tests && echo 'T4 OK'
import importlib.util, pathlib, sys
from datetime import datetime, timedelta, timezone
H, R = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("js", pathlib.Path("bin/journal_sources.py").resolve())
js = importlib.util.module_from_spec(spec); spec.loader.exec_module(js)
names = [n for n, _ in js.ADAPTERS]
assert names == ["claude_code", "copilot_cli", "codex_cli", "git", "cursor", "vscode"], names
day = datetime(2026, 6, 30, tzinfo=timezone.utc)
ctx = {"day_start": day, "day_end": day + timedelta(days=1), "claude_projects": None,
       "copilot_home": None, "codex_home": None, "repos": [R, H / "not-a-repo"],
       "pricing_claude": None, "pricing_copilot": None}
reports = js.run_adapters(ctx)
g = reports["git"]
assert g["available"] and g["priced"] is False and g["usd"] is None, g
repo = g["extra"]["repos"][0]
assert repo["commit_count"] == 1 and repo["commits"][0]["subject"] == "in-window work", repo
assert repo["dirty_files"] >= 1 and repo["untracked"] >= 1 and repo["branch"] == "main", repo
assert any("not-a-repo" in n for n in g["notes"]), g["notes"]
assert "repoA" in g["projects"], g["projects"]
for name in ("cursor", "vscode"):
    st = reports[name]
    assert st["deferred"] is True and st["available"] is False and "state.vscdb" in st["notes"][0], st
print("git adapter + stubs ok")
PY
```

---

### T5 — Regression tests for the adapter engine (tests/test_journal_sources.py)
- status: done
- model: sonnet
- depends: T2, T3, T4
- independent: no

**Brief.** Create `tests/test_journal_sources.py`, stdlib `unittest`, loading
`bin/journal_sources.py` via the importlib `_load` convention off
`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` (copy the header pattern from
`tests/test_copilot_usage.py`, including a module docstring stating the safety contract: no
test reads/writes the real `~/.claude`/`~/.copilot`/`~/.codex`, no `Path.home()`, no CLI
invocation, every fixture synthetic in `tempfile.TemporaryDirectory`, both pricing dicts
synthetic module constants — the real pricing files are never opened).

Fixtures: synthetic `P_CLAUDE` (one fake model with `intro_pricing` ABSENT, round rates,
`cache_read_multiplier` 0.1 / `cache_write_multiplier_5m` 1.25) and `P_COPILOT`
(`billing_unit.usd_per_credit` 0.5, one `mid` model), helper builders for claude transcript
lines, copilot event lines, codex lines, and a `_mkrepo(tmp)` helper that shells `git init` +
env-dated commits (mirroring T4's verify — git in tests is offline and sanctioned; `skipTest`
if `git` is missing). All windows passed as explicit aware UTC datetimes (never machine-local).

Minimum cases:
1. `day_window("2026-06-30", utc=True)` spans exactly 24h starting at UTC midnight;
   `day_window` with a garbage string raises ValueError; local mode returns aware datetimes
   spanning 24h (no wall-clock date assertions).
2. `empty_report` carries exactly the D4 key set (assert as a frozen set — schema lock).
3. Claude: message-id dedupe across TWO files (same id in both counts once); day filter;
   untimestamped exclusion + count; unmatched-model bucketing (`usd` None +
   `extra["unpriced_models"]`); hand-math usd check against `P_CLAUDE` incl. cache fields;
   projects from `cwd` basename with slug fallback; `pricing_claude=None` → `usd` None + note.
4. Copilot: last-event-day membership (session with `last_seen` outside window excluded;
   inside included); single-model exact attribution vs multi-model last-model attribution
   (note appended); `aiu_reported` and `aic` math against 0.5; output-only session flagged in
   notes; missing `session-state` → `available` False.
5. Codex: ISO + epoch-seconds + epoch-ms parsing; malformed/non-dict counting; both-files
   session dedupe; zero-usage records still counted; `priced` False/`usd` None + pinned
   `unpriced` note; sqlite subdir present and untouched.
6. Git: in/out-of-window commits; dirty/untracked counts; non-repo note; empty repos note;
   subject containing `|` and unicode survives (the \x1f/\x1e format).
7. Stubs: `deferred` True, pinned `state.vscdb` note.
8. Engine: `run_adapters` returns all six sources in registry order; a crashing ctx value
   yields an `errors` entry for that source and intact reports for the rest.
9. READ-ONLY proof: byte-snapshot a combined fixture tree (claude+copilot+codex homes incl. a
   junk `session.db` and `sqlite/codex-dev.db`) before/after `run_adapters` — identical, no
   new files.

**Acceptance.** All new tests pass; full suite green; grep clean: no `Path.home()`, no real
model ids, no bare `"claude"`/`"copilot"`/`"codex"` single-word subprocess targets (git is the
only allowed binary); file loads `journal_sources` via `BIN_DIR`.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_journal_sources.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T5 OK'
import re
text = open('tests/test_journal_sources.py').read()
assert 'Path.home()' not in text
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
assert re.search(r'''subprocess\.run\(\[?["']git["']''', text) or "_git" in text, "git helper expected"
for bad in ('~/.claude', '~/.copilot', '~/.codex'):
    assert bad not in text, f"real home path {bad} in tests"
print('safety greps ok')
PY
```

---

*Phase 1 end — dispatch `daily-journal-reviewer` before starting Phase 2.*

---

## Phase 2 — The deterministic collector

### T6 — Create bin/journal_collect.py (digest CLI + signals)
- status: done
- model: opus
- depends: T4
- independent: no

**Brief.** Per PLAN.md D4/D5/D10/D11: the deterministic collector CLI. New file
`bin/journal_collect.py`; module docstring states: what it does (assembles the daily digest
from the journal_sources adapters + next-day signals), STRICTLY READ-ONLY ingestion (writes
ONLY under the journal dir), no model / no network / no CLI invocation ever, and the D4
content-hygiene rule (metadata only — no transcript text; free text limited to commit
subjects, kit task titles, inbox lines, names, errors).

Module constants: `PLUGIN_ROOT = Path(__file__).resolve().parent.parent`;
`DEFAULT_JOURNAL_DIR = PLUGIN_ROOT / "journal"`;
`DEFAULT_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"`;
`DEFAULT_COPILOT_HOME = Path.home() / ".copilot"`;
`DEFAULT_CODEX_HOME = Path.home() / ".codex"` (these three are the ONLY `Path.home()` uses in
this file — runtime defaults, always overridden in tests; comment this);
`DEFAULT_KITS_DIR = PLUGIN_ROOT / ".claude" / "kits"`; caps `MAX_KIT_TASKS = 100`,
`MAX_INBOX_ITEMS = 100`, `SCHEMA_VERSION = 1`. Importlib-load `journal_sources` (as `js`),
`cost_report` (as `cr`), `copilot_usage` (as `cu`), `copilot_execute` (as `ce`) via the
`_load` pattern.

`main(argv=None)` argparse: `--date` (YYYY-MM-DD; default None → today), `--utc`
(store_true — compute the day window in UTC; tests/verifies always use it), `--journal-dir`,
`--claude-projects`, `--copilot-home`, `--codex-home` (all default to the constants),
`--repo` (action=append, default []), `--config` (default None → `<journal-dir>/config.json`),
`--inbox` (default None → `<journal-dir>/inbox.md`), `--kits-dir` (default
`DEFAULT_KITS_DIR`), `--print` (dump the digest JSON to stdout too). Invalid `--date` →
`sys.exit("invalid --date (want YYYY-MM-DD): ...")`.

Pure functions (unit-testable):
- `load_config(path) -> (dict, notes)` — missing → `({}, [])`; invalid JSON or non-dict →
  `({}, ["config unreadable: ..."])`; recognized key: `"repos"` (list of strings → Paths);
  unknown keys ignored.
- `read_inbox(path) -> dict` — `{"present": bool, "path": str(path), "items": [...],
  "truncated": bool}`. Missing file → present False, items []. Lines: strip; skip empty and
  lines starting `#`; strip one leading `- `, `* `, or `[ ] ` marker; cap `MAX_INBOX_ITEMS`
  (truncated True + stop).
- `scan_kit_tasks(kits_dir) -> (items, errors)` — for each sorted `<kits_dir>/*/TASKS.md`:
  `ce.parse_tasks(text)` in try/except (ValueError/OSError → errors entry naming the kit,
  continue); keep tasks with status `pending` or `in-progress` as `{"kit": <dir name>,
  "id", "title", "status", "model"}`; cap `MAX_KIT_TASKS` total.
- `build_wip(git_report) -> list` — from `git_report["extra"].get("repos", [])`: entries with
  `dirty_files + untracked > 0` → `{"repo": basename, "branch", "dirty_files", "untracked"}`.
- `build_digest(reports, day_start, day_end, date_str, signals) -> dict` — the pinned D4
  digest: `schema_version, date, generated_at` (now, isoformat), `day_start`/`day_end`
  (isoformat), `timezone` (`str(day_start.tzinfo)`), `sources` (the reports dict), `totals`
  (`usd_priced` = sum of non-None source `usd`; `sessions` = summed; `sources_active` =
  names with `available` and (`sessions > 0` or git commit_count > 0 across repos);
  `unpriced_sources` = names with `available` and `priced` False), `signals`
  (`kit_tasks`, `inbox`, `wip`, plus `kit_errors` when nonempty).

Flow in `main`: window = `js.day_window(args.date, utc=args.utc)`; pricing =
`cr.load_pricing()` / `cu.load_pricing()`; config; repos = config repos + `--repo` values
(deduped, order preserved); ctx per D2; `reports = js.run_adapters(ctx)`; signals; digest;
write to `<journal-dir>/<date>/digest.json` (mkdir parents, `json.dumps(..., indent=2)`,
overwrite deterministically — rerunning a day regenerates it); print one summary line:
`digest written: <path> — N/M sources active, $X.XX priced, K kit tasks open, J inbox items`
(USD with `:,.2f`); `--print` additionally dumps the JSON. Exit 0 even when sources carry
errors (they are IN the digest); exit nonzero only for bad args or an unwritable journal dir
(`sys.exit` with message).

GOTCHAS: exactly 3 `Path.home()` in this file and none anywhere else it touches; never write
under any source root; kit-task briefs are NOT copied into the digest (titles only — content
hygiene); do not read `.claude/kits/*/NOTES.md` or PLAN.md; the digest write is the only
filesystem write.

**Acceptance.**
- Heredoc e2e (below): full fixture run writes `digest.json` with schema_version 1, the six
  sources, correct totals (`usd_priced` sums claude+copilot only), kit_tasks filtered to
  pending/in-progress across two fixture kits, inbox parsed with markers stripped, wip from
  the dirty repo; source fixture trees byte-identical; rerun overwrites cleanly (same path,
  parseable).
- `grep -c 'Path.home()' bin/journal_collect.py` == 3; no `sqlite` in the file; full suite
  green; only this file new.

**Verify.**
```bash
cd /path/to/polytropos && H="$(mktemp -d)" && R="$H/repoW" && mkdir -p "$R" && git -C "$R" init -q -b work && GIT_COMMITTER_DATE="2026-06-30T10:00:00+00:00" git -C "$R" -c user.email=t@t -c user.name=T commit -q --allow-empty -m "ship it" --date "2026-06-30T10:00:00+00:00" && echo x > "$R/wip.txt" && python3 - "$H" "$R" <<'PY' && test "$(grep -c 'Path.home()' bin/journal_collect.py)" -eq 3 && ! grep -n 'sqlite' bin/journal_collect.py && python3 -m unittest discover -s tests && rm -rf "$H" && echo 'T6 OK'
import hashlib, importlib.util, json, pathlib, subprocess, sys
H, R = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
# --- fixture homes ---
proj = H / "projects" / "-tmp-projA"; proj.mkdir(parents=True)
(proj / "s1.jsonl").write_text(json.dumps({
    "timestamp": "2026-06-30T10:00:00Z", "sessionId": "s1", "cwd": "/tmp/projA",
    "message": {"model": "any-model-x", "id": "m1", "usage": {"input_tokens": 100, "output_tokens": 10}}}) + "\n")
co = H / "cohome" / "session-state" / "u1"; co.mkdir(parents=True)
(co / "workspace.yaml").write_text("id: u1\ncwd: /tmp/projB\n")
(co / "events.jsonl").write_text(json.dumps({"type": "session.shutdown", "timestamp": "2026-06-30T11:00:00Z",
    "data": {"totalNanoAiu": 1000000000, "currentModel": "any-co-model", "tokenDetails":
    {"input": {"tokenCount": 10}, "output": {"tokenCount": 5}}}}) + "\n")
cx = H / "codex"; cx.mkdir()
(cx / "history.jsonl").write_text(json.dumps({"session_id": "c1", "ts": "2026-06-30T12:00:00Z"}) + "\n")
kits = H / "kits" / "demo-kit"; kits.mkdir(parents=True)
(kits / "TASKS.md").write_text("# TASKS\n\n### K1 — Do a thing\n- status: pending\n- model: sonnet\n\n"
                               "### K2 — Done thing\n- status: done\n- model: haiku\n")
jd = H / "journal"; jd.mkdir()
(jd / "inbox.md").write_text("# notes\n\n- follow up with Sam\n* review PR 42\n[ ] book room\nplain line\n")
(jd / "config.json").write_text(json.dumps({"repos": [str(R)], "unknown_key": True}))
def snap(p):
    return {str(f): hashlib.md5(f.read_bytes()).hexdigest() for f in sorted(p.rglob("*")) if f.is_file() and "journal" not in f.parts}
before = snap(H)
argv = [sys.executable, "bin/journal_collect.py", "--date", "2026-06-30", "--utc",
        "--journal-dir", str(jd), "--claude-projects", str(H / "projects"),
        "--copilot-home", str(H / "cohome"), "--codex-home", str(cx), "--kits-dir", str(H / "kits")]
r = subprocess.run(argv, capture_output=True, text=True)
assert r.returncode == 0, r.stderr
assert "digest written" in r.stdout, r.stdout
assert snap(H) == before, "source fixtures mutated"
d = json.loads((jd / "2026-06-30" / "digest.json").read_text())
assert d["schema_version"] == 1 and d["date"] == "2026-06-30", d.keys()
assert set(d["sources"]) == {"claude_code", "copilot_cli", "codex_cli", "git", "cursor", "vscode"}
assert d["signals"]["kit_tasks"] == [{"kit": "demo-kit", "id": "K1", "title": "Do a thing",
                                      "status": "pending", "model": "sonnet"}], d["signals"]["kit_tasks"]
items = d["signals"]["inbox"]["items"]
assert items == ["follow up with Sam", "review PR 42", "book room", "plain line"], items
assert d["signals"]["wip"] and d["signals"]["wip"][0]["repo"] == "repoW", d["signals"]["wip"]
assert d["sources"]["git"]["extra"]["repos"][0]["commit_count"] == 1
assert "codex_cli" in d["totals"]["unpriced_sources"], d["totals"]
r2 = subprocess.run(argv, capture_output=True, text=True)
assert r2.returncode == 0 and json.loads((jd / "2026-06-30" / "digest.json").read_text())["date"] == "2026-06-30"
print("collector e2e ok")
PY
```

---

### T7 — Regression tests for the collector (tests/test_journal_collect.py)
- status: done
- model: sonnet
- depends: T6
- independent: no

**Brief.** Create `tests/test_journal_collect.py`, same conventions and safety-contract
docstring as T5 (importlib `_load` off `BIN_DIR`; `tempfile` everywhere; no `Path.home()`; no
real home paths; no CLI invocations — `subprocess` allowed ONLY for `git` fixture setup and
for running `bin/journal_collect.py` itself via `sys.executable`).

Minimum cases:
1. `load_config`: missing → `({}, [])`; invalid JSON → note; non-dict JSON → note; repos
   parsed to Paths; unknown keys ignored.
2. `read_inbox`: missing file; marker stripping (`- `, `* `, `[ ] `); `#` and blank lines
   skipped; truncation at `MAX_INBOX_ITEMS` sets `truncated`.
3. `scan_kit_tasks`: two fixture kits — pending + in-progress kept with kit/id/title/status/
   model, done/blocked dropped; a malformed TASKS.md (bad status) lands in errors without
   killing the other kit; cap respected.
4. `build_wip`: dirty repos in, clean repos out.
5. `build_digest`: totals math (`usd_priced` ignores None), `sources_active` includes a
   git-only-activity day, `unpriced_sources` lists available+unpriced sources; pinned
   top-level key set asserted as a frozen set (schema lock).
6. End-to-end `main` via in-process call (`jc.main([...])` with stdout captured) against a
   combined fixture: digest file written where expected; `--print` dumps parseable JSON;
   rerun overwrites; exit 0 with a crashing source root (error recorded in digest, run
   completes).
7. `--date garbage` → SystemExit with a message; unwritable journal dir (a FILE at the
   journal-dir path) → SystemExit.
8. READ-ONLY proof: byte-snapshot the source fixture trees around a full `main` run —
   identical; the only new files appear under the temp journal dir.
9. Content hygiene: build a claude fixture whose message includes a `content` field with a
   distinctive marker string (e.g. `"SECRET-TRANSCRIPT-TEXT"`); assert the marker does NOT
   appear anywhere in the written digest.

**Acceptance.** All new tests pass; full suite green; safety greps clean (below); only this
file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_journal_collect.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T7 OK'
import re
text = open('tests/test_journal_collect.py').read()
assert 'Path.home()' not in text
for bad in ('~/.claude', '~/.copilot', '~/.codex'):
    assert bad not in text, f"real home path {bad} in tests"
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
assert 'SECRET-TRANSCRIPT-TEXT' in text, "content-hygiene test missing"
print('safety greps ok')
PY
```

---

*Phase 2 end — dispatch `daily-journal-reviewer` before starting Phase 3.*

---

## Phase 3 — The model summarizer

### T8 — Create bin/journal_summarize.py (routed, injectable, dry-runnable)
- status: done
- model: opus
- depends: T6
- independent: no

**Brief.** Per PLAN.md D8/D9/D10: the summarizer. New file `bin/journal_summarize.py`; module
docstring MUST state: reads `journal/<date>/digest.json` and writes the three documents +
`summary-meta.json` next to it; the dispatch is an injectable `runner(argv, prompt) ->
(rc, text)` whose default shells `claude -p --model <id>` with the prompt on STDIN (reusing
the user's Claude Code auth — no API key, no new deps); `--dry-run` prints and spawns/writes
NOTHING; and the DISCLOSED PRIVACY NOTE (verbatim): `"Privacy: this step sends the digest —
project/repo names, commit subjects, kit task titles, and inbox text — to the model via the
claude CLI."` Tests never invoke a real `claude`.

Constants: `PLUGIN_ROOT`; `PRICING_PATH = PLUGIN_ROOT / "data" / "pricing.json"`;
`TIER_LADDER = ("haiku", "sonnet", "opus")` (structural tier vocabulary — commented as such;
never model ids); `DEFAULT_START_TIER = "sonnet"`; `DEFAULT_CLAUDE_BIN = "claude"`;
`MIN_OK_CHARS = 200`; `DOCS = ("narrative", "technical", "next_day")`;
`FILENAMES = {"narrative": "narrative.md", "technical": "technical.md",
"next_day": "next-day.md"}`. No `Path.home()` in this file. Importlib-load nothing except
stdlib + `json.load` of `PRICING_PATH` via a `load_pricing()` mirroring `cost_report.py`.

Pure functions:
- `pick_models(pricing, start_tier) -> [model_id, ...]` — for each tier in `TIER_LADDER`
  from `start_tier`'s index onward: the FIRST model in `pricing["models"]` file order whose
  `tier == t` (missing tiers skipped); truncate to 2 (primary + ONE escalation, capped at
  the ladder's end — never frontier); empty → `ValueError`. `start_tier` not in ladder →
  `ValueError`.
- `output_ok(text) -> bool` — `text` truthy, `len(text.strip()) >= MIN_OK_CHARS`, and
  `text.lstrip().startswith("#")`.
- `build_prompts(digest) -> {"narrative": str, "technical": str, "next_day": str}` — each
  prompt: a role/instruction header, the REQUIRED output contract, then
  `json.dumps(digest, indent=None, separators=(",", ":"))` in a fenced block. Required
  contracts (pin these headings in the prompts):
  * narrative → begins `# Work journal — {date}`; a readable story of the day (which
    projects, which tools/models, what shipped); prose, no invented facts, explicitly told
    "use only what is in the digest".
  * technical → begins `# Technical summary — {date}`; REQUIRED H2s `## Sessions & cost`
    (per-source sessions/tokens/USD; unpriced sources labeled unpriced, never guessed),
    `## Models` and `## Repos & commits`.
  * next_day → begins `# Plan for {next_date}` (next calendar date); REQUIRED H2s
    `## Start here` (top 1–3 items with WHY), `## To-dos` (from kit_tasks + inbox + wip),
    `## How to run` (concrete commands, e.g. resuming a kit via
    `/polytropos:execute <slug>`); built from `signals` + source summaries.
  * every prompt ends: `"Respond with ONLY the markdown document."`
- `build_dispatch(model_id, claude_bin=DEFAULT_CLAUDE_BIN) -> argv` — exactly
  `[claude_bin, "-p", "--model", model_id]` (prompt goes on stdin, never in argv).
- `default_runner(argv, prompt) -> (rc, text)` — `subprocess.run(argv, input=prompt,
  capture_output=True, text=True, timeout=600)`; `FileNotFoundError` → `(127, "<claude bin
  not found: ...>")`; `TimeoutExpired` → `(124, "...")`.
- `summarize(digest, models, runner, claude_bin=...) -> (docs, meta)` — per doc in `DOCS`:
  walk `models` (≤ 2); `rc, out = runner(build_dispatch(m, claude_bin), prompt)`; accept when
  `rc == 0 and output_ok(out)`; record every attempt in
  `meta["docs"][doc]["attempts"] = [{"model": m, "rc": rc, "ok": bool}]`; on acceptance store
  text + `meta["docs"][doc]["model"] = m`, `"escalated": bool`; all attempts failed →
  doc omitted from `docs`, `meta["docs"][doc]["failed"] = True`. `meta` also carries
  `generated_at` and `start_models = models`.

`main(argv=None)`: args `--date`, `--utc` (both forwarded to window/dir resolution — the
digest dir is `<journal-dir>/<date>`; default date = today local, matching the collector),
`--journal-dir` (default `PLUGIN_ROOT / "journal"`), `--digest` (explicit digest path
override), `--model` (explicit id — must be a key of or match into `pricing["models"]` via a
tolerant startswith match mirroring `cost_report.match_model`, else `sys.exit`; when given,
`models = [that id]`, no escalation), `--start-tier` (choices=TIER_LADDER, default sonnet),
`--claude-bin` (default `DEFAULT_CLAUDE_BIN` — tests point it at stubs), `--dry-run`.
Missing digest → `sys.exit(f"no digest at {path} — run journal_collect.py first")`.
`--dry-run`: print the privacy note, the model list, the argv for the primary model, then
each prompt under a `=== PROMPT: <doc> ===` header; write NOTHING, spawn NOTHING, exit 0.
Real run: `summarize(...)` with `default_runner`; write accepted docs to
`FILENAMES[doc]` in the digest's directory + `summary-meta.json` (indent=2); print one line
per doc (`written narrative.md (model <id>)` / `FAILED narrative` to stderr); exit 0 when all
three accepted, else 3.

GOTCHAS: no model id literals anywhere (the ladder is computed; tests use synthetic pricing);
`--dry-run` must not even construct a subprocess; prompts embed the digest verbatim — no
additional file reads; `sys.exit` codes pinned (0 ok / 3 partial-failure / nonzero usage
errors via sys.exit(str)).

**Acceptance.**
- Heredoc run (below): with a synthetic pricing dict (via a temp `data`-shaped file? NO —
  patch by passing `--model`? ALSO no): the verify uses the REAL `data/pricing.json` ONLY
  through `pick_models` semantics — it asserts structure (2 models, tiers sonnet→opus in
  file order), never asserts ids in the kit files; the dispatched fake runner proves
  escalation and stdin-prompt plumbing; `--dry-run` against a fixture digest prints three
  `=== PROMPT:` headers + the privacy note and creates no files; a fake-runner full run
  writes `narrative.md`/`technical.md`/`next-day.md`/`summary-meta.json` into the temp day
  dir with escalation recorded.
- No `Path.home()` in the file; `subprocess` appears only in `default_runner`; full suite
  green; only this file new.

**Verify.**
```bash
cd /path/to/polytropos && H="$(mktemp -d)" && python3 - "$H" <<'PY' && rm -rf "$H" && ! grep -n 'Path.home()' bin/journal_summarize.py && test "$(grep -c 'subprocess' bin/journal_summarize.py)" -le 6 && ! grep -nE '"claude-(fable|opus|sonnet|haiku)' bin/journal_summarize.py && python3 -m unittest discover -s tests && echo 'T8 OK'
import contextlib, importlib.util, io, json, pathlib, sys
H = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("jsz", pathlib.Path("bin/journal_summarize.py").resolve())
jsz = importlib.util.module_from_spec(spec); spec.loader.exec_module(jsz)
# pick_models: synthetic pricing proves order + cap, no real ids involved
P = {"models": {"m-h": {"tier": "haiku"}, "m-s1": {"tier": "sonnet"}, "m-s2": {"tier": "sonnet"},
                "m-o": {"tier": "opus"}, "m-f": {"tier": "frontier"}}}
assert jsz.pick_models(P, "sonnet") == ["m-s1", "m-o"], jsz.pick_models(P, "sonnet")
assert jsz.pick_models(P, "opus") == ["m-o"]
assert jsz.pick_models(P, "haiku") == ["m-h", "m-s1"]
try:
    jsz.pick_models({"models": {}}, "sonnet"); raise SystemExit("expected ValueError")
except ValueError: pass
assert not jsz.output_ok("short"); assert not jsz.output_ok("x" * 300)
assert jsz.output_ok("# Title\n" + "y" * 300)
digest = {"schema_version": 1, "date": "2026-06-30",
          "sources": {"git": {"extra": {"repos": []}}},
          "totals": {"usd_priced": 0.0}, "signals": {"kit_tasks": [], "inbox": {"items": []}, "wip": []}}
day = H / "j" / "2026-06-30"; day.mkdir(parents=True)
(day / "digest.json").write_text(json.dumps(digest))
prompts = jsz.build_prompts(digest)
assert set(prompts) == {"narrative", "technical", "next_day"}
assert "# Work journal — 2026-06-30" in prompts["narrative"]
assert "## Start here" in prompts["next_day"] and "2026-07-01" in prompts["next_day"]
assert "ONLY the markdown document" in prompts["technical"]
assert jsz.build_dispatch("model-x", "stub-bin") == ["stub-bin", "-p", "--model", "model-x"]
# dry-run: prints, writes nothing, spawns nothing
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = jsz.main(["--digest", str(day / "digest.json"), "--dry-run"]) or 0
out = buf.getvalue()
assert out.count("=== PROMPT:") == 3 and "Privacy:" in out, out[:300]
assert sorted(p.name for p in day.iterdir()) == ["digest.json"], "dry-run wrote files"
# fake runner: first model fails rc=1, escalation succeeds
calls = []
def fake_runner(argv, prompt):
    calls.append((list(argv), prompt[:40]))
    if len([c for c in calls if c[0] == argv]) == 1 and argv[3] == "m-s1":
        return (1, "boom")
    return (0, "# Doc\n" + "z" * 300)
docs, meta = jsz.summarize(digest, ["m-s1", "m-o"], fake_runner, claude_bin="stub-bin")
assert set(docs) == {"narrative", "technical", "next_day"}
assert meta["docs"]["narrative"]["attempts"][0]["rc"] == 1
assert meta["docs"]["narrative"]["model"] == "m-o" and meta["docs"]["narrative"]["escalated"] is True
assert all(c[0][0] == "stub-bin" and c[0][1] == "-p" for c in calls)
print("summarizer seams ok")
PY
```

---

### T9 — Regression tests for the summarizer (tests/test_journal_summarize.py)
- status: done
- model: sonnet
- depends: T8
- independent: no

**Brief.** Create `tests/test_journal_summarize.py`, T5/T7 conventions + safety docstring:
**no test ever invokes a real `claude`** — every dispatch is a fake runner or a temp STUB
executable (a tiny `#!/bin/sh` script named `stub-model.sh`, never `claude`), pricing is a
synthetic dict patched over `load_pricing` via `mock.patch.object`, digests are synthetic.

Minimum cases:
1. `pick_models`: order within tier = pricing file order; start tiers haiku/sonnet/opus;
   cap at 2; skipped missing tiers; ValueError on empty/bad start tier.
2. `output_ok` edge cases (empty, short, no-heading, exactly-min-length heading doc).
3. `build_prompts`: three prompts; date + next-date arithmetic (incl. month rollover, e.g.
   2026-06-30 → 2026-07-01 and 2026-12-31 → 2027-01-01); required headings pinned; the
   compact digest JSON embedded; the `ONLY the markdown document` tail.
4. `build_dispatch` argv shape; prompt NOT in argv.
5. `summarize`: acceptance on first model; escalation on `rc != 0`; escalation on
   short/heading-less output; both-fail → doc omitted + `failed` True; meta attempts
   recorded; at most 2 attempts per doc even with a longer models list passed.
6. `default_runner` against the stub executable (writes argv/stdin to a file, echoes a valid
   doc): rc 0, prompt arrived via stdin; a nonexistent bin path → rc 127 (FileNotFoundError
   branch) — never resolving a bare `claude`.
7. `main` e2e with `mock.patch.object(jsz, "default_runner", fake)` + patched pricing: writes
   the three files + `summary-meta.json`; exit 0; a doc that always fails → exit 3 and that
   file absent; `--dry-run` → no files, three prompt headers, privacy note, and the fake
   runner NOT called (patch it with a bomb that raises).
8. `--model` explicit id (synthetic, via patched pricing) → single-model list, no
   escalation; unknown `--model` → SystemExit; missing digest → SystemExit naming the path.

**Acceptance.** All new tests pass; full suite green; greps: no `Path.home()`, no real model
ids, no stub named `claude`, no real home paths; only this file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_journal_summarize.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T9 OK'
import re
text = open('tests/test_journal_summarize.py').read()
assert 'Path.home()' not in text
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
bad = [l for l in text.splitlines() if re.search(r'''["']claude["']''', l)]
assert not bad, f"bare 'claude' literal(s): {bad}"
assert 'stub' in text and 'dry-run' in text.replace('_', '-'), "stub/dry-run coverage expected"
print('safety greps ok')
PY
```

---

*Phase 3 end — dispatch `daily-journal-reviewer` before starting Phase 4.*

---

## Phase 4 — Scheduling + the skill

### T10 — Create bin/journal_schedule.py (install/uninstall/status/run — no subprocess)
- status: done
- model: sonnet
- depends: T6, T8
- independent: no

**Brief.** Per PLAN.md D12. New file `bin/journal_schedule.py`; module docstring states: it
WRITES a launchd plist and prints the `launchctl` commands for the USER to run — it never
executes `launchctl` (or any process: **this module must not import `subprocess`**); `run` is
the manual one-shot path calling the collector and summarizer in-process; during development
and tests the installer only ever targets a temp `--launch-agents-dir`.

Constants: `PLUGIN_ROOT`; `LABEL = "com.polytropos.daily-journal"`;
`DEFAULT_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"` (the ONLY
`Path.home()` here — runtime default, always overridden in tests; comment it);
`DEFAULT_HOUR = 22`, `DEFAULT_MINUTE = 0`.

Functions:
- `render_plist(python_bin, script_path, hour, minute, journal_dir, plugin_root) -> bytes` —
  `plistlib.dumps` of `{"Label": LABEL, "ProgramArguments": [str(python_bin),
  str(script_path), "run"], "StartCalendarInterval": {"Hour": hour, "Minute": minute},
  "WorkingDirectory": str(plugin_root), "StandardOutPath":
  str(journal_dir / "logs" / "launchd.out.log"), "StandardErrorPath":
  str(journal_dir / "logs" / "launchd.err.log"), "RunAtLoad": False}`. Validate
  `0 <= hour <= 23`, `0 <= minute <= 59` → ValueError.
- `plist_path(launch_agents_dir) -> Path` — `<dir>/<LABEL>.plist`.
- `cmd_install(args)` — mkdir the launch-agents dir (parents ok), write the rendered plist
  (`python_bin = sys.executable`, `script_path = Path(__file__).resolve()`), print: the
  written path, then (pinned, as INSTRUCTIONS ONLY): `To activate:  launchctl bootstrap
  gui/$(id -u) <path>` and `To deactivate: launchctl bootout gui/$(id -u)/<LABEL>`. Returns 0.
- `cmd_uninstall(args)` — unlink the plist if present (print removed + the bootout
  instruction), else print `nothing installed at <path>`; returns 0 either way.
- `cmd_status(args)` — plist present → parse with `plistlib.load`, print label, hour:minute
  (zero-padded), program path; absent → print `not installed (<path>)`. Returns 0.
- `cmd_run(args, collect_main=None, summarize_main=None)` — injectable mains for tests; when
  None, importlib-load `journal_collect`/`journal_summarize` (the `_load` pattern) and use
  their `main`. Build collector argv from passthrough flags (`--date`, `--utc`,
  `--journal-dir` when given); run collector (SystemExit caught → its code); if nonzero,
  return it (the digest matters most). Then, unless `--collect-only`: summarizer argv
  (same passthroughs + `--dry-run` when given) → run, return its code (0 when all fine).
- `main(argv=None)` — subcommands `install` (`--launch-agents-dir`, `--hour`, `--minute`,
  `--journal-dir` defaulting to `PLUGIN_ROOT / "journal"`), `uninstall`
  (`--launch-agents-dir`), `status` (`--launch-agents-dir`), `run` (`--date`, `--utc`,
  `--journal-dir`, `--collect-only`, `--dry-run`). Invalid hour/minute → exit 2 with message.

GOTCHAS: no `subprocess` import ANYWHERE in this file (grep-enforced); exactly 1
`Path.home()`; the plist's absolute paths are computed, never hardcoded literals of
`/Users/...` (grep-enforced: the string `/Users/` must not appear in the file); `run` must
not swallow the summarizer's exit 3.

**Acceptance.**
- Heredoc run: `install --launch-agents-dir <tmp> --hour 21 --minute 30 --journal-dir <tmp>/j`
  writes `<tmp>/com.polytropos.daily-journal.plist`; `plistlib.load` shows the pinned
  keys, ProgramArguments ending `["...journal_schedule.py", "run"]`, Hour 21/Minute 30, log
  paths under `<tmp>/j/logs/`; stdout contains `launchctl bootstrap` as instruction text;
  `status` prints `21:30`; `uninstall` removes the file; hour 24 exits nonzero; `cmd_run`
  with injected fake mains passes through `--date`/`--utc`/`--dry-run` and propagates a
  nonzero collector code without calling the summarizer.
- Greps: zero `subprocess`, one `Path.home()`, zero `/Users/` in the file; full suite green.

**Verify.**
```bash
cd /path/to/polytropos && H="$(mktemp -d)" && python3 - "$H" <<'PY' && rm -rf "$H" && ! grep -n 'subprocess' bin/journal_schedule.py && test "$(grep -c 'Path.home()' bin/journal_schedule.py)" -eq 1 && ! grep -n '/Users/' bin/journal_schedule.py && python3 -m unittest discover -s tests && echo 'T10 OK'
import contextlib, importlib.util, io, pathlib, plistlib, sys
H = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("jsch", pathlib.Path("bin/journal_schedule.py").resolve())
jsch = importlib.util.module_from_spec(spec); spec.loader.exec_module(jsch)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = jsch.main(["install", "--launch-agents-dir", str(H), "--hour", "21", "--minute", "30",
                    "--journal-dir", str(H / "j")]) or 0
assert rc == 0 and "launchctl bootstrap" in buf.getvalue(), buf.getvalue()
pl = H / "com.polytropos.daily-journal.plist"
assert pl.is_file()
d = plistlib.load(open(pl, "rb"))
assert d["Label"] == "com.polytropos.daily-journal"
assert d["ProgramArguments"][-2:] == [str(pathlib.Path("bin/journal_schedule.py").resolve()), "run"], d["ProgramArguments"]
assert d["StartCalendarInterval"] == {"Hour": 21, "Minute": 30}
assert d["StandardOutPath"].startswith(str(H / "j")) and d["RunAtLoad"] is False
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    jsch.main(["status", "--launch-agents-dir", str(H)])
assert "21:30" in buf2.getvalue(), buf2.getvalue()
try:
    jsch.main(["install", "--launch-agents-dir", str(H), "--hour", "24"]); raise AssertionError("hour 24 accepted")
except SystemExit as e:
    assert e.code not in (0, None)
calls = []
def fake_collect(argv): calls.append(("c", argv)); return 0
def fake_summ(argv): calls.append(("s", argv)); return 0
class A: date="2026-06-30"; utc=True; journal_dir=str(H/"j"); collect_only=False; dry_run=True
rc = jsch.cmd_run(A(), collect_main=fake_collect, summarize_main=fake_summ)
assert rc == 0 and calls[0][0] == "c" and "--utc" in calls[0][1] and "--dry-run" in calls[1][1], calls
calls.clear()
def bad_collect(argv): calls.append(("c", argv)); return 7
rc = jsch.cmd_run(A(), collect_main=bad_collect, summarize_main=fake_summ)
assert rc == 7 and len(calls) == 1, (rc, calls)
with contextlib.redirect_stdout(io.StringIO()):
    jsch.main(["uninstall", "--launch-agents-dir", str(H)])
assert not pl.exists()
print("schedule ok")
PY
```

---

### T11 — Regression tests for the scheduler (tests/test_journal_schedule.py)
- status: done
- model: sonnet
- depends: T10
- independent: yes

**Brief.** Create `tests/test_journal_schedule.py`, T5/T7 conventions + safety docstring: no
test touches `~/Library/LaunchAgents` or any real home path; every install goes to a
`tempfile` dir; `launchctl` is never executed (assert the module has no `subprocess`);
`cmd_run` is tested ONLY with injected fake mains.

Minimum cases: `render_plist` validation (hour 24 / minute 60 / negative → ValueError) and
pinned key set; install→status→uninstall lifecycle against a temp dir (plist parse checks,
zero-padded `HH:MM` in status output, uninstall idempotent — second call still exits 0);
install stdout contains `launchctl bootstrap` and `launchctl bootout` as text; `cmd_run`
passthrough matrix (`--collect-only` skips the summarizer; collector failure short-circuits;
summarizer exit 3 propagates; `--dry-run` forwarded); module-level greps as tests: the
loaded module file contains no `subprocess` and exactly one `Path.home()`.

**Acceptance.** All new tests pass; full suite green; greps below clean; only this file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_journal_schedule.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T11 OK'
text = open('tests/test_journal_schedule.py').read()
assert 'Path.home()' not in text
assert 'LaunchAgents' not in text or 'launch_agents' in text.lower(), "no real LaunchAgents path"
assert 'subprocess' not in text or 'no subprocess' in text or 'not in' in text, "tests must not spawn processes"
print('safety greps ok')
PY
```

---

### T12 — Create skills/journal/SKILL.md (/polytropos:journal)
- status: done
- model: sonnet
- depends: T6, T8, T10
- independent: yes

**Brief.** Per PLAN.md D13 — the ONE sanctioned addition under `skills/` (a NEW directory;
touch nothing else there; no `references/` mirror is needed and none may be created). The
plugin is installed live: this file is runtime behavior. Frontmatter exactly:

```yaml
---
name: journal
description: Generate the daily work journal — collect today's AI usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into a digest, then write the narrative, technical, and next-day-plan summaries. Use when the user asks for their work journal, daily summary, "what did I do today", or to plan tomorrow.
allowed-tools: Bash, Read, Write
---
```

Body sections (H1 `# Daily work journal`, then H2s in this order — pinned):

1. `## Collect the digest` — resolve the plugin root per the repo convention
   (`${CLAUDE_PLUGIN_ROOT}`, fallback: resolve `../..` relative to this SKILL.md to an
   ABSOLUTE path before shelling out), then run
   `python3 "${CLAUDE_PLUGIN_ROOT}/bin/journal_collect.py"` (optionally `--date YYYY-MM-DD`;
   flags `--repo`, `--print` mentioned; note the collector is deterministic, read-only over
   `~/.claude` / `~/.copilot` / `~/.codex`, and writes only under the gitignored `journal/`).
2. `## Write the summaries (in this session — default)` — read
   `journal/<date>/digest.json`; run `python3 ".../bin/journal_summarize.py" --date <date>
   --dry-run` to get the exact three prompts; then WRITE `narrative.md`, `technical.md`, and
   `next-day.md` into the same day directory yourself following those prompts (no nested
   model dispatch — the session is already paid for). Follow each prompt's required headings
   exactly; use only digest facts.
3. `## Or run it headless` — `python3 ".../bin/journal_summarize.py" --date <date>` shells
   `claude -p` on a routed cheap/mid model with one escalation; mention `--start-tier`,
   `--model`, and exit code 3 on partial failure.
4. `## Inbox & schedule` — drop meeting notes / email to-dos into `journal/inbox.md` (they
   become next-day to-dos); install the nightly run with `python3
   ".../bin/journal_schedule.py" install` (defaults 22:00; prints the `launchctl` command to
   activate — the script never runs `launchctl` itself); `uninstall` / `status` / `run` for
   manual one-shots.
5. `## Privacy` — the summary step sends the digest (project/repo names, commit subjects,
   kit task titles, inbox text) to a model; the digest itself is metadata-only (no transcript
   text) and everything stays under gitignored `journal/`.

Constraints: no price/model-id literals (tier names ok); no absolute `/Users/` paths; no
`/private/tmp/`; 60–120 lines; presenting-results guidance short (summarize the three docs,
link paths).

**Acceptance.** File exists with the pinned frontmatter fields (name `journal`,
`allowed-tools: Bash, Read, Write`), the five pinned H2s in order, the `${CLAUDE_PLUGIN_ROOT}`
convention with the absolute-path fallback sentence, and passes the greps; git shows only
this new file; full suite (incl. any skill-shape tests already in the repo) green.

**Verify.**
```bash
cd /path/to/polytropos && F=skills/journal/SKILL.md && test -f "$F" && python3 - "$F" <<'PY' && ! grep -n '/Users/' "$F" && ! grep -n '/private/tmp' "$F" && ! grep -nE 'claude-(fable|opus|sonnet|haiku)-' "$F" && L=$(wc -l < "$F") && test "$L" -ge 60 && test "$L" -le 120 && python3 -m unittest discover -s tests && echo 'T12 OK'
import re, sys
text = open(sys.argv[1]).read()
assert text.startswith('---\nname: journal\n'), "frontmatter must open with name: journal"
assert 'allowed-tools: Bash, Read, Write' in text
heads = re.findall(r'^## .*$', text, re.M)
want = ["## Collect the digest", "## Write the summaries (in this session — default)",
        "## Or run it headless", "## Inbox & schedule", "## Privacy"]
assert heads == want, heads
assert 'CLAUDE_PLUGIN_ROOT' in text and 'journal_collect.py' in text and 'journal_summarize.py' in text
assert 'inbox.md' in text and 'journal_schedule.py' in text and 'launchctl' in text
assert '--dry-run' in text
print("skill shape ok")
PY
```

---

*Phase 4 end — dispatch `daily-journal-reviewer` before starting Phase 5.*

---

## Phase 5 — Docs + guardrails

### T13 — Write docs/DAILY-JOURNAL.md + README cross-link
- status: done
- model: sonnet
- depends: T12
- independent: yes

**Brief.** Two changes.

**(1) Create `docs/DAILY-JOURNAL.md`** — the user-facing guide, tone/format of
`docs/COPILOT-COSTVIZ.md`; 110–180 lines. Required H2 headings, exactly these eight, in this
order:

1. `## What this is` — the nightly work journal: deterministic collector + scheduled model
   summarizer; the `journal/<date>/` outputs; everything under gitignored `journal/`.
2. `## The pipeline` — `journal_collect.py` (digest, always runs, no model) →
   `journal_summarize.py` (narrative/technical/next-day via a routed cheap/mid model with one
   escalation) → `journal_schedule.py` (launchd, ~22:00, configurable); the digest file as
   the seam; rerunnable per day.
3. `## Sources & the adapter contract` — v1 sources (Claude Code, Copilot CLI, Codex CLI
   (unpriced by design — no Codex pricing exists in `data/`), git activity); the
   `collect_<name>(ctx) -> report` contract + registry in `bin/journal_sources.py`; read-only
   JSONL-only ingestion (never SQLite, never a CLI invocation); how a new source slots in
   (one function + one registry row).
4. `## The digest` — schema_version 1 shape at a glance; day scoping rules (`--date`,
   local-midnight window, `--utc`; per-source membership honesty incl. the
   untimestamped-exclusion divergence from cost_report); content hygiene (metadata only — the
   free-text allowlist).
5. `## Next-day planning & the inbox` — the three signal families (kit tasks, `journal/
   inbox.md`, WIP); how to use the inbox (drop meeting notes/email to-dos; markers stripped);
   what `next-day.md` contains (start-here, to-dos, how-to-run).
6. `## Scheduling` — install/uninstall/status/run commands; the installer writes the plist
   and PRINTS the `launchctl bootstrap` command (never executes it); logs under
   `journal/logs/`; the manual paths (`run`, the `/polytropos:journal` skill).
7. `## Privacy & safety` — read-only ingestion contract; the disclosed model-send; nothing
   secret written; `journal/` gitignored; tests never touch real homes.
8. `## Deferred` — Cursor/VS Code adapters (state.vscdb SQLite; the safe-copy read strategy
   sketch from PLAN.md "Still deferred"); Teams/Outlook augmentation (the Graph path and the
   MCP path, both feeding the same inbox signal); weekly rollups; point at
   `.claude/kits/daily-journal/PLAN.md`.

No prices, credit values, or real model ids (tier names and `<id>` placeholders fine); no
absolute `/Users/` or `/private/tmp/` paths.

**(2) `README.md`** — the intro link block contains the paragraph beginning
`**Copilot cost visibility (Phase 3):**`. Insert directly after it, as its own paragraph:

> **Daily work journal:** [docs/DAILY-JOURNAL.md](docs/DAILY-JOURNAL.md) — a nightly, scheduled work journal: a deterministic collector ingests the day's usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into a gitignored `journal/<date>/digest.json`, then a routed cheap/mid model writes `narrative.md`, `technical.md`, and `next-day.md` (fed by open kit tasks, a local `journal/inbox.md`, and uncommitted work).

If the anchor paragraph is not present verbatim, STOP and report. Change nothing else in
README.md.

**Acceptance.** New doc exists with exactly the eight pinned H2s in order and the length
bounds; README paragraph inserted verbatim after the anchor; git shows only these two files
changed; full suite green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && ! grep -n '/Users/' docs/DAILY-JOURNAL.md && ! grep -n '/private/tmp' docs/DAILY-JOURNAL.md && L=$(wc -l < docs/DAILY-JOURNAL.md) && test "$L" -ge 110 && test "$L" -le 180 && grep -q 'Daily work journal:' README.md && grep -q 'docs/DAILY-JOURNAL.md' README.md && python3 -m unittest discover -s tests && echo 'T13 OK'
import re
text = open('docs/DAILY-JOURNAL.md').read()
heads = re.findall(r'^## .*$', text, re.M)
want = ["## What this is", "## The pipeline", "## Sources & the adapter contract",
        "## The digest", "## Next-day planning & the inbox", "## Scheduling",
        "## Privacy & safety", "## Deferred"]
assert heads == want, heads
for needle in ("journal_collect.py", "journal_summarize.py", "journal_schedule.py",
               "inbox.md", "state.vscdb", "unpriced", "launchctl", "read-only"):
    assert needle in text, f"missing {needle!r}"
rd = open('README.md').read()
i = rd.find('**Copilot cost visibility (Phase 3):**'); j = rd.find('**Daily work journal:**')
assert -1 < i < j, "README paragraph missing or misplaced"
print("docs shape ok")
PY
```

---

### T14 — CLAUDE.md: journal guardrail bullet + runnable lines
- status: done
- model: haiku
- depends: T6, T8, T10
- independent: yes

**Brief.** Two pinned insertions into the hand-authored `CLAUDE.md` (which stays
hand-authored). Change nothing else. If an anchor is not present verbatim, STOP and report.
(The `daily-journal` executor-section paragraph already exists — it was written with the kit;
do not touch it.)

**(1)** In `## Invariants`, insert as a NEW bullet immediately after the bullet that begins
`- **Never invoke the real \`copilot\` CLI from tests, kit verify commands, or anything run
during execution**` (a single long line — insert after that whole line), exactly:

> - **The daily journal is read-only ingestion with gitignored output.** `bin/journal_*.py` read `~/.claude/projects`, `~/.copilot/session-state`, and `~/.codex` strictly read-only at run time (JSONL only — never a `*.db`/SQLite open, never a CLI invocation to gather); output, inbox, and config live under gitignored `journal/`; the digest carries metadata only (no transcript text); the summarizer's `claude -p` dispatch is injectable, mocked in every test, and `--dry-run` prints the prompts and spawns nothing; Codex activity is counted but never priced (no Codex pricing exists in `data/` by design).

**(2)** In the `## How to run things` code block, insert immediately after the
`python3 bin/copilot_usage.py --days 30            # Copilot usage report (reads ~/.copilot read-only)`
line these two lines (into the EXISTING code block, comments aligned with the others — do not
create a new code block):

```
python3 bin/journal_collect.py --print            # today's work-journal digest (reads ~/.claude, ~/.copilot, ~/.codex read-only; writes journal/)
python3 bin/journal_summarize.py --dry-run        # show the journal prompts + routed model (spawns nothing)
```

**Acceptance.** Both insertions present verbatim at the specified anchors; git diff for
CLAUDE.md shows only these additions.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'read-only ingestion with gitignored output' CLAUDE.md && grep -q 'journal_collect.py --print' CLAUDE.md && grep -q 'journal_summarize.py --dry-run' CLAUDE.md && D="$(git diff --numstat -- CLAUDE.md | awk '{print $2}')" && { test -z "$D" || test "$D" -le 1; } && python3 -m unittest discover -s tests && echo 'T14 OK'
```

---

*Phase 5 end — dispatch `daily-journal-reviewer` for the final review, then run the overall
"done" check from PLAN.md.*
