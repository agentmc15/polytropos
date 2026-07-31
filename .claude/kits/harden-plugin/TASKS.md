# TASKS — harden-plugin

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the OUT-OF-SCOPE fence and decisions
D1–D7. Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `harden-plugin-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in parallel;
`depends:` lists hard ordering. Dispatch `harden-plugin-reviewer` at each phase end.

---

## Phase 1 — Script correctness + regression tests

### T1 — Fix naive-timestamp crash in cost_report.py
- status: done
- model: sonnet
- depends: (none)
- independent: no (T2 edits the same file; keep serialized)

**Brief.** `bin/cost_report.py` crashes with `TypeError: can't compare offset-naive and
offset-aware datetimes` if any transcript line carries a timezone-naive `timestamp` (e.g.
`"2026-06-01T12:00:00"` with no `Z`/offset). `parse_timestamp()` (currently lines 67–72) returns
whatever `datetime.fromisoformat` gives; naive results later hit `when < cutoff` (cutoff is
aware UTC) and `when > s["last_seen"]`, killing the entire report on one bad line. Per PLAN.md
D4, coerce naive to UTC (Claude Code's own timestamps are UTC) rather than dropping the record.

Replace the body of `parse_timestamp` with exactly this logic:

```python
def parse_timestamp(raw):
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts
```

Do not change anything else in the file. `timezone` is already imported.

**Acceptance.**
- `parse_timestamp('2026-06-01T12:00:00')` returns an aware datetime (tzinfo = UTC).
- `parse_timestamp('2026-06-01T12:00:00Z')` still returns an aware datetime.
- `parse_timestamp('garbage')` and `parse_timestamp(None)` still return `None`.
- Comparing the result against an aware datetime raises nothing.

**Verify.**
```bash
cd /path/to/polytropos && python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('cr','bin/cost_report.py')
cr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr)
from datetime import datetime, timezone, timedelta
w = cr.parse_timestamp('2026-06-01T12:00:00')
assert w is not None and w.tzinfo is not None, w
cutoff = datetime.now(timezone.utc) - timedelta(days=30)
_ = (w < cutoff)  # must not raise
w2 = cr.parse_timestamp('2026-06-01T12:00:00Z')
assert w2.tzinfo is not None
assert cr.parse_timestamp('garbage') is None
assert cr.parse_timestamp(None) is None
print('T1 OK')"
```

---

### T2 — Tighten match_model and quiet synthetic models in cost_report.py
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Two pinned fixes in `bin/cost_report.py`, per PLAN.md D3.

(1) `match_model()` (currently lines 33–41): the condition
`base == key or base.startswith(key + "-") or base.startswith(key)` has a bare
`startswith(key)` that both subsumes the other clauses (dead code) and silently mis-prices
unknown future IDs — confirmed: `claude-sonnet-50` and `claude-sonnet-5x-beta` currently match
`claude-sonnet-5`. Unknowns must be surfaced in the "Unpriced models" section, never guessed.
Change the loop condition to exactly:

```python
if base == key or base.startswith(key + "-"):
```

This keeps working: exact IDs, `[1m]` suffixes (stripped before the loop), and date-suffixed IDs
like `claude-sonnet-5-20260203` (dash-delimited). It stops matching `claude-sonnet-50`.

(2) In `main()`, the unknown-model tally (currently around line 164–167):
```python
key = match_model(model, pricing)
if key is None:
    unknown_models[model] += sum(u.values())
    continue
```
`match_model` deliberately returns `None` for synthetic pseudo-models (IDs starting with `<`,
e.g. `<synthetic>`), but the tally then reports them under "Unpriced models (not in
pricing.json)", which is noise — they are not real models. Guard the tally:

```python
key = match_model(model, pricing)
if key is None:
    if not model.startswith("<"):
        unknown_models[model] += sum(u.values())
    continue
```

(3) One comment, for future readers: immediately above the `if when is not None and when < cutoff:`
line in `main()`, add:
```python
# Records with no parseable timestamp can't be age-filtered: they are kept
# regardless of --days and priced at base (non-intro) rates.
```

Nothing else changes. Do not touch pricing.json (OUT OF SCOPE fence in PLAN.md).

**Acceptance.**
- `match_model` maps: all 6 pricing.json keys to themselves; `claude-fable-5[1m]` →
  `claude-fable-5`; `claude-sonnet-5-20260203` → `claude-sonnet-5`; `claude-opus-4-7-20250601` →
  `claude-opus-4-7`.
- `match_model` returns `None` for: `claude-sonnet-50`, `claude-sonnet-5x-beta`, `<synthetic>`,
  `''`, `None`, `us.anthropic.claude-opus-4-8-v1:0`.
- A run over a synthetic-containing transcript shows no `<synthetic>` under "Unpriced models",
  while a genuinely unknown model still appears there.

**Verify.**
```bash
cd /path/to/polytropos && python3 -c "
import importlib.util, json, sys, io, tempfile, contextlib
from pathlib import Path
spec = importlib.util.spec_from_file_location('cr','bin/cost_report.py')
cr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr)
p = cr.load_pricing()
for k in p['models']: assert cr.match_model(k, p) == k, k
assert cr.match_model('claude-fable-5[1m]', p) == 'claude-fable-5'
assert cr.match_model('claude-sonnet-5-20260203', p) == 'claude-sonnet-5'
assert cr.match_model('claude-opus-4-7-20250601', p) == 'claude-opus-4-7'
for bad in ['claude-sonnet-50','claude-sonnet-5x-beta','<synthetic>','', None,'us.anthropic.claude-opus-4-8-v1:0']:
    assert cr.match_model(bad, p) is None, bad
with tempfile.TemporaryDirectory() as td:
    d = Path(td)/'proj'; d.mkdir()
    def line(model, mid):
        return json.dumps({'timestamp':'2026-06-30T12:00:00Z','sessionId':'s1','message':{'id':mid,'model':model,'usage':{'input_tokens':100,'output_tokens':10}}})
    (d/'s1.jsonl').write_text(line('<synthetic>','m1')+'\n'+line('claude-sonnet-50','m2')+'\n'+line('claude-fable-5','m3')+'\n')
    cr.PROJECTS_DIR = Path(td); sys.argv = ['cost_report.py','--days','3650']
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): cr.main()
    out = buf.getvalue()
assert '<synthetic>' not in out, 'synthetic leaked into report'
assert 'claude-sonnet-50' in out, 'unknown model not surfaced'
assert 'Fable 5' in out
print('T2 OK')"
```

---

### T3 — Add stdlib unittest regression suite for both scripts
- status: done
- model: sonnet
- depends: T1, T2
- independent: no

**Brief.** Create `tests/test_cost_report.py` and `tests/test_statusline.py`. Python 3 stdlib
ONLY — no pytest, no new deps (PLAN.md D2; the docs advertise "stdlib only" and this repo has no
packaging files). `bin/` is not a package: load `cost_report.py` via
`importlib.util.spec_from_file_location`, computing the path from the test file itself:
`Path(__file__).resolve().parent.parent / "bin" / "cost_report.py"`. Do NOT create
`tests/__init__.py` (discover doesn't need it) and do NOT add a test runner script.

`tests/test_cost_report.py` — required cases (grouped as you see fit; subtests fine):
- **match_model** (use the real pricing dict from `load_pricing()`): each of the 6 pricing keys
  maps to itself; `claude-fable-5[1m]` → `claude-fable-5`; `claude-sonnet-5-20260203` →
  `claude-sonnet-5`; `claude-opus-4-7-20250601` → `claude-opus-4-7`; `None`, `''`,
  `'<synthetic>'`, `'claude-sonnet-50'`, `'claude-sonnet-5x-beta'`,
  `'us.anthropic.claude-opus-4-8-v1:0'` all → `None`.
- **rates_for** (build `when` as aware datetimes): `claude-sonnet-5` at 2026-07-15 → intro rates
  `(2.0, 10.0)`; at 2026-08-31 (boundary, inclusive) → intro; at 2026-09-01 → base `(3.0, 15.0)`;
  `when=None` → base; `claude-fable-5` any date → `(10.0, 50.0)`.
- **price**: for `claude-fable-5`, `u = {"input": 1_000_000, "output": 100_000,
  "cache_read": 1_000_000, "cache_write": 100_000}`, `when=None`:
  expected `10.0 + 5.0 + 1.0 + 1.25 = 17.25` (assertAlmostEqual). This pins the cache-read 0.1×
  and cache-write 1.25× multipliers from pricing.json.
- **parse_timestamp**: `'...Z'` → aware; `'...+00:00'` → aware; naive `'2026-06-01T12:00:00'` →
  aware UTC (regression guard for T1); `'garbage'` → None; `None` → None; `''` → None.
- **extract_record**: nested `{"message": {...}}` form with a content list containing two
  `tool_use` blocks → returns `(model, usage, id, 2)` with correct token fields; top-level
  `{"usage": ..., "model": ...}` fallback form works; all-zero usage → `None`; missing model →
  `None`; usage fields set to `null` in JSON (i.e. `None`) coerce to 0.
- **main() end-to-end**: in a `tempfile.TemporaryDirectory`, write `proj/s1.jsonl` containing:
  a fable message id `m1` with a recent `Z` timestamp; an exact duplicate of `m1` (dedupe: must
  count once); a `claude-sonnet-4-6` message (historical model must price); a `claude-sonnet-50`
  message with usage (must appear under "Unpriced models"); a `<synthetic>` message with usage
  (must NOT appear anywhere in output); a record with a timestamp older than the `--days` window
  (must be excluded); a record with a naive timestamp (must be included without crashing).
  Monkeypatch `cr.PROJECTS_DIR = Path(tmpdir)` and `sys.argv = ['cost_report.py', '--days', '30']`
  (use recent timestamps relative to `datetime.now(timezone.utc)` so the window math is stable),
  capture stdout with `contextlib.redirect_stdout`, then assert: output contains `Fable 5`,
  `Sonnet 4.6`, `claude-sonnet-50`; does not contain `<synthetic>`; and the Fable row shows
  exactly 1 message (assert `'| Fable 5 | 1 |'` in output).

`tests/test_statusline.py` — run the script via
`subprocess.run([sys.executable, str(BIN / "statusline.py")], input=..., capture_output=True,
text=True)`. Add an ANSI-strip helper: `re.sub(r'\x1b\[[0-9;]*m', '', s)`. Required cases:
- Full payload `{"model":{"id":"claude-opus-4-8","display_name":"Opus 4.8"},"effort":{"level":"high"},"cost":{"total_cost_usd":0.5},"context_window":{"used_percentage":85},"rate_limits":{"five_hour":{"used_percentage":63},"seven_day":{"used_percentage":22}}}`
  → stripped output contains `Opus 4.8`, `high`, `$0.50`, `ctx 85%`, `5h 63%`, `7d 22%`.
- The setup-skill sample payload `{"model":{"id":"claude-fable-5","display_name":"Fable 5"},"cost":{"total_cost_usd":1.23},"context_window":{"used_percentage":42}}`
  → stripped output is exactly `⬢ Fable 5 | $1.23 | ctx 42%`.
- Empty stdin → output line is `polytropos: no status data`.
- Invalid JSON (`not json`) → same fallback line.
- Model-only payload → output contains the model name and no `$`.

**Acceptance.** Both test files exist; suite is stdlib-only (no third-party imports); at least 18
test methods/subtests total; `python3 -m unittest discover -s tests -v` exits 0.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -v 2>&1 | tail -5 && python3 -m unittest discover -s tests 2>&1 | grep -q '^OK' && ! grep -rE '^\s*(import|from)\s+(pytest|requests|numpy)' tests/ && echo 'T3 OK'
```

---

*Phase 1 end — dispatch `harden-plugin-reviewer` before starting Phase 2.*

---

## Phase 2 — Skill consistency (three disjoint file pairs; T4/T5/T6 may run in parallel)

### T4 — Align the architect⇄execute kit contract
- status: done
- model: opus
- depends: (none)
- independent: yes

**Brief.** `skills/execute/SKILL.md` consumes three things `skills/architect/SKILL.md` never
tells Fable to produce, and leaves one dispatch ambiguity (PLAN.md F3/D5):
(a) execute's loop step 6 triggers a reviewer at "phase boundaries" — architect's TASKS.md spec
has no phase concept; (b) execute parallelizes "tasks TASKS.md marks as independent" — no
independence marking exists in the producer spec; (c) execute appends learnings to `NOTES.md` —
architect never mentions it; (d) a task pinned `model: opus` dispatched to the kit's
sonnet-pinned implementer agent would silently run on sonnet, because nothing says the task's
`model` field wins at dispatch time.

Make these pinned edits (wording may be lightly adapted to fit each file's voice, but every
contract element below must appear in BOTH files' descriptions of the kit, stated identically in
substance):

In `skills/architect/SKILL.md`, `### TASKS.md` section — extend the bullet list with:
- Tasks are grouped under `## Phase N — <name>` headings; the execute loop dispatches the
  reviewer agent at each phase end.
- Each task marks ordering explicitly: `depends: <ids>` or `independent: yes` — execute
  parallelizes only tasks marked independent.
- The task's `model` field is authoritative at dispatch time: execute passes it as the Agent
  tool's `model` parameter, which overrides the implementer agent's frontmatter default.
- Note that execute maintains a `NOTES.md` alongside PLAN.md/TASKS.md for cross-task learnings —
  the architect does not create it.

In `skills/execute/SKILL.md`, loop step 2 — replace the parenthetical dispatch instruction so it
reads in substance: dispatch to the kit's implementer agent, **passing the task's `model` value
as the Agent tool's `model` parameter (the parameter overrides the agent's frontmatter default —
the task's pin wins)**; if the kit has no implementer agent, use the Agent tool directly with
that model. Keep the existing "brief verbatim plus nothing else" instruction intact.

Keep both files' status vocabulary as `pending/in-progress/done/blocked` (already consistent —
do not reword it). Do not restructure either skill; total change should be a handful of lines.
Do NOT touch README.md or docs/ (they already describe phase-boundary reviews; nothing there
becomes false).

**Acceptance.** Both skills describe the same kit contract: layout, task fields, four-status
vocabulary, phase grouping, dependency/independence marking, model-override dispatch rule,
NOTES.md ownership (execute). No other content changed.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'Phase' skills/architect/SKILL.md && grep -qi 'independent' skills/architect/SKILL.md && grep -q 'NOTES.md' skills/architect/SKILL.md && grep -qi 'overrides the' skills/architect/SKILL.md && grep -qi 'overrides the' skills/execute/SKILL.md && grep -q 'NOTES.md' skills/execute/SKILL.md && grep -q 'pending/in-progress/done/blocked' skills/architect/SKILL.md && echo 'T4 OK'
```

---

### T5 — Robust paths in cost-report + setup skills; exercise rate_limits in the setup smoke test
- status: done
- model: sonnet
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D6/F4/F7. Claude Code sets `${CLAUDE_PLUGIN_ROOT}` to the installed
plugin's root for plugin-executed content; a `../../` path in a bash block resolves against the
CWD and fails verbatim. Three pinned edits:

(1) `skills/cost-report/SKILL.md`: change the command block to
`python3 "${CLAUDE_PLUGIN_ROOT}/bin/cost_report.py" --days 30` and adjust the surrounding
sentence to say the path uses the plugin-root env var, falling back to resolving
`../../bin/cost_report.py` relative to this SKILL.md to an absolute path if the var is unset.
Update the `--mode` flag line's pricing.json reference the same way
(`${CLAUDE_PLUGIN_ROOT}/data/pricing.json`).

(2) `skills/setup/SKILL.md` step 1: resolve the script path as
`"${CLAUDE_PLUGIN_ROOT}/bin/statusline.py"` (fallback: `../../bin/statusline.py` relative to this
SKILL.md, resolved to absolute). Extend the smoke-test sample JSON to include
`"rate_limits":{"five_hour":{"used_percentage":12},"seven_day":{"used_percentage":34}}` so the
rate-limit rendering the skill's description promises is actually exercised, and state the
expected output shape (model | cost | ctx | `5h 12% · 7d 34%`).

(3) `skills/setup/SKILL.md` steps 1–3: define `<abs-path>` unambiguously as the resolved
absolute path to the plugin's `bin` directory, and add one sentence to step 3: the command
written into `~/.claude/settings.json` must be a literal absolute path — never
`${CLAUDE_PLUGIN_ROOT}`, because the statusline command runs outside plugin context where that
variable is not set.

Do not change the skills' step structure, the confirmation flow, or the frontmatter.

**Acceptance.** Both skills reference `${CLAUDE_PLUGIN_ROOT}` with the relative fallback; setup's
sample JSON includes both rate-limit fields; setup explicitly forbids the env var inside
settings.json; the sample payload actually renders `5h`/`7d` through the real script.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'CLAUDE_PLUGIN_ROOT' skills/cost-report/SKILL.md && grep -q 'CLAUDE_PLUGIN_ROOT' skills/setup/SKILL.md && grep -q 'rate_limits' skills/setup/SKILL.md && grep -q 'literal absolute path' skills/setup/SKILL.md && echo '{"model":{"id":"claude-fable-5","display_name":"Fable 5"},"cost":{"total_cost_usd":1.23},"context_window":{"used_percentage":42},"rate_limits":{"five_hour":{"used_percentage":12},"seven_day":{"used_percentage":34}}}' | python3 bin/statusline.py | grep -q '5h' && echo 'T5 OK'
```

---

### T6 — De-drift literals in route + fable-check skills
- status: done
- model: haiku
- depends: (none)
- independent: yes

**Brief.** Per PLAN.md D1/F6: skill instructions must derive numbers from `data/pricing.json` at
run time, never state them as standing facts. Four pinned text replacements — make exactly
these, nothing else:

(1) `skills/route/SKILL.md` — the pricing-source sentence near the top currently reads:
> Read `../../data/pricing.json` (relative to this SKILL.md — the plugin's `data/pricing.json`) for all prices, model notes, and task-size profiles.

Replace with:
> Read the plugin's `data/pricing.json` (`${CLAUDE_PLUGIN_ROOT}/data/pricing.json`; if that variable is unset, resolve `../../data/pricing.json` relative to this SKILL.md) for all prices, model notes, and task-size profiles.

(2) `skills/route/SKILL.md` — in the api-mode routing table, the Sonnet 5 row currently ends:
> Intro pricing until 2026-08-31.

Replace that sentence with:
> Intro pricing until the `intro_pricing.until` date in pricing.json.

(3) `skills/fable-check/SKILL.md` — the opening line currently reads:
> Read `../../data/pricing.json` for current prices. Fable 5 costs 2× Opus 4.8 and ~3.3× Sonnet 5 per token.

Replace with:
> Read the plugin's `data/pricing.json` (`${CLAUDE_PLUGIN_ROOT}/data/pricing.json`; if that variable is unset, resolve `../../data/pricing.json` relative to this SKILL.md) for current prices, and derive the Fable-vs-Opus and Fable-vs-Sonnet cost ratios from those rates — never quote ratios from memory.

(4) `skills/fable-check/SKILL.md` — in "Standing recommendation", the line:
> Global default in `~/.claude/settings.json` should be `opus` (currently `claude-fable-5[1m]` at `xhigh` — offer to change it if asked). Drop the standing `xhigh` effort; set effort per task.

Replace with:
> Global default in `~/.claude/settings.json` should be `opus`; if it is still pinned to a Fable model with a standing `xhigh` effort, offer to change it. Set effort per task, not globally.

WHY: the date literal goes stale silently when pricing.json changes; the ratios go stale when any
price changes; the "currently ..." claim describes the user's live settings at authoring time and
will silently become false. README.md and docs/ keep their literals — they are labeled snapshots
(PLAN.md D1) — so do NOT edit those files.

**Acceptance.** The four replacements applied verbatim; no other lines changed in either file;
no price/ratio/date literals remain in either skill.

**Verify.**
```bash
cd /path/to/polytropos && ! grep -q '2026-08-31' skills/route/SKILL.md && ! grep -qE '2×|3\.3×' skills/fable-check/SKILL.md && ! grep -q 'currently `claude-fable-5' skills/fable-check/SKILL.md && grep -q 'CLAUDE_PLUGIN_ROOT' skills/route/SKILL.md && grep -q 'CLAUDE_PLUGIN_ROOT' skills/fable-check/SKILL.md && echo 'T6 OK'
```

---

*Phase 2 end — dispatch `harden-plugin-reviewer` before starting Phase 3.*

---

## Phase 3 — Docs + final sweep

### T7 — Update README install section for the local marketplace
- status: done
- model: sonnet
- depends: (none)
- independent: yes

**Brief.** `.claude-plugin/marketplace.json` (marketplace name `polytropos-local`, plugin
source `./`) makes this repo directly installable as a local marketplace, but `README.md`'s
Install section predates it: it leads with `claude --plugin-dir ...` and says "(or install from a
marketplace once published)". `--plugin-dir` is a real flag (confirmed via `claude --help`:
"Load a plugin from a directory or .zip", repeatable) but is session-scoped, not an install.

Rewrite ONLY the `## Install` section of `README.md` to:
1. Lead with the persistent marketplace install. In-session commands (these are the known-good
   fallback truth):
   - `/plugin marketplace add /path/to/polytropos`
   - `/plugin install polytropos@polytropos-local`
   Before writing any *non-interactive CLI* equivalent (e.g. `claude plugin marketplace add ...`),
   run `claude plugin --help` and subcommand help to confirm exact syntax; include the CLI form
   only if the help output confirms it, and match what the help actually shows.
2. Keep `claude --plugin-dir <repo-path>` as a secondary "one-off session (dev/testing, not a
   persistent install)" option.
3. Drop the "(or install from a marketplace once published)" line — the marketplace exists.

Keep the section short (comparable length to now). Do not touch any other README section. The
hardcoded `~/...` path is correct for this machine and stays (PLAN.md
out-of-scope fence).

**Acceptance.** Install section documents marketplace add + install as primary, `--plugin-dir`
as session-only secondary; any CLI syntax shown was confirmed against `claude plugin --help`;
no other README changes.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'marketplace add' README.md && grep -q 'polytropos@polytropos-local' README.md && grep -q -- '--plugin-dir' README.md && ! grep -q 'once published' README.md && echo 'T7 OK'
```

---

### T8 — Final consistency sweep and full verification
- status: done
- model: sonnet
- depends: T1, T2, T3, T4, T5, T6, T7
- independent: no

**Brief.** Adversarial final pass over the whole tree. Steps:

1. Run the full test suite; must be green.
2. Enforce the D1 invariant greps (skills must carry no standalone price/date literals):
   `grep -rE '\$[0-9]' skills/` and `grep -r '2026-08-31' skills/` must both return nothing.
3. Sanity-check `data/pricing.json` still parses and is structurally intact (it must NOT have
   been edited by any task): `billing_mode`, `cache_read_multiplier`,
   `cache_write_multiplier_5m`, `batch_discount`, `task_profiles` with XS–XL, and exactly these
   6 model keys: claude-fable-5, claude-opus-4-8, claude-opus-4-7, claude-sonnet-5,
   claude-sonnet-4-6, claude-haiku-4-5. `git diff --stat data/pricing.json` must be empty.
4. Cross-read `README.md` and `docs/HOW-IT-WORKS.md` price tables against pricing.json values
   (Fable 10/50, Opus 5/25, Sonnet 3/15 intro 2/10 until 2026-08-31, Haiku 1/5) — these labeled
   snapshots must still match. Report (don't silently fix) anything else that looks drifted;
   fix only outright factual mismatches, and mirror any docs/HOW-IT-WORKS.md fix into
   docs/how-it-works.html if the same claim appears there.
5. Run both scripts on sample input end-to-end (commands below).
6. Confirm scope: `git status --porcelain` shows changes only under `bin/`, `tests/`, `skills/`,
   `README.md`, `CLAUDE.md`, `.claude/kits/harden-plugin/`, `.claude/agents/`.

**Acceptance.** All six steps pass; any drift found in step 4 is listed in the task report with
what was done about it.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests 2>&1 | grep -q '^OK' && [ -z "$(grep -rE '\$[0-9]' skills/)" ] && [ -z "$(grep -r '2026-08-31' skills/)" ] && [ -z "$(git diff --stat data/pricing.json)" ] && python3 -c "
import json
p = json.load(open('data/pricing.json'))
assert set(p['models']) == {'claude-fable-5','claude-opus-4-8','claude-opus-4-7','claude-sonnet-5','claude-sonnet-4-6','claude-haiku-4-5'}
assert set(p['task_profiles']) == {'XS','S','M','L','XL'}
for k in ('billing_mode','cache_read_multiplier','cache_write_multiplier_5m','batch_discount'): assert k in p
" && python3 bin/cost_report.py --days 7 > /dev/null && echo '{"model":{"id":"claude-sonnet-5","display_name":"Sonnet 5"},"cost":{"total_cost_usd":0.1},"context_window":{"used_percentage":10}}' | python3 bin/statusline.py > /dev/null && echo 'T8 OK'
```
