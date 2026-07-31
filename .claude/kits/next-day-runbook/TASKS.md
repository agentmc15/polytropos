# TASKS — next-day-runbook

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially Repo facts, decisions D1–D8, the
OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `next-day-runbook-implementer` (the parameter overrides the
agent's frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. **Warm-cluster candidate: T2 → T3** (same `sonnet`
pin, strictly serial — T3 tests the file T2 finished); execute may serve the pair with one
continued (warm) implementer. T1 and T2 both edit `bin/journal_plan.py` and must NEVER run in
parallel. T4 and T5 touch disjoint files and may fan out fresh in parallel. Dispatch
`next-day-runbook-reviewer` at each phase end. This kit's PLAN.md declares
`autonomy: advisory` — re-route recommendations during this run are print-only.

Standing rules for every task:

- **No scheduler, no dispatch, ever.** No launchd/`StartCalendarInterval`, `pmset`, cron,
  daemon, `launchctl`, or auto-run work anywhere; `bin/journal_schedule.py` stays
  byte-untouched. `bin/journal_plan.py` contains ZERO `subprocess` — it generates
  ready-to-paste command TEXT; it never spawns a harness, a model, or anything else. No
  test or verify command invokes a real `claude`/`copilot`/`codex` CLI or `launchctl`.
- **Offline is absolute.** No network, OAuth, MCP, tokens, or secrets in any form; no
  `urllib`/`http.client`/`socket` import and no `sqlite3`/`*.db` anywhere new or edited.
- **No home-directory access.** The new script takes NO home-dir flag; inputs are
  `--journal-dir` and the committed `data/` pricing files; the ONLY writes are
  `<journal-dir>/plan/<YYYY-MM-DD>.md`. ZERO `Path.home()` in `bin/journal_plan.py` and
  `tests/test_journal_plan.py` (the repo budget stays 3 in `bin/journal_collect.py` + 1 in
  `bin/journal_schedule.py`). Every test/verify uses temp `--journal-dir` dirs, `--utc`
  wherever day membership matters.
- **Reused scripts are imported read-only via the `_load` importlib pattern, never
  edited**: `bin/journal_advisor.py`, `bin/cost_report.py`, `bin/copilot_usage.py`,
  `bin/codex_usage.py` (and never touch `bin/journal_collect.py`,
  `bin/journal_summarize.py`, `bin/journal_sources.py`, `bin/journal_askpack.py`,
  `bin/journal_schedule.py`, `bin/copilot_pricing.py`, `bin/codex_pricing.py`). Never
  re-implement `build_harness_signal` or the `load_pricing` loaders — call them.
- **All seven pre-existing `tests/test_journal_*.py` files stay byte-untouched.** New tests
  go ONLY in `tests/test_journal_plan.py`.
- **Never fabricate.** Absent pricing/slot/digest data renders `est n/a — pricing or tier
  unavailable`, the pinned one-line harness-unavailable degradation, or an honest note —
  never a zeroed or invented figure. Codex estimates always carry
  `API-equivalent — not a bill` and codex_cli is NEVER the deterministic ideal pick.
- **Never hardcode a price, ratio, plan fact, or real model id.** GPT-5.6 and `claude-*`
  model ids never appear as literals in code or tests — compute from the pricing files at
  run time. Sanctioned literals: tier vocabulary (`haiku|sonnet|opus`), `TIER_TO_SLOT`,
  `EST_PROFILE = "M"`, `PLAN_SCHEMA = 1`, the `plan` dir name and `seed.md`, the date-stem
  regex, `SEED_MARKERS`, `MAX_PLAN_CARDS = 100`, pinned heading/note/prompt/reason text,
  est format strings, and synthetic fixture ids/values in tests.
- **Sanctioned existing-file edits ONLY**: `skills/journal/SKILL.md` (T4, BODY-only —
  frontmatter byte-intact; the plugin is LIVE) and `docs/DAILY-JOURNAL.md` (T5, one pinned
  pointer paragraph). New files ONLY: `bin/journal_plan.py`, `tests/test_journal_plan.py`,
  `docs/NEXT-DAY-RUNBOOK.md`. CLAUDE.md and README.md are NOT edit targets (the architect
  pre-made CLAUDE.md's run-line and fence insertions). No `.gitignore` change (`/journal/`
  already covers the store). Do not touch the stray untracked `docs/HOW-IT-WORKS 2.md`.
- **Pinned content is verbatim.** Where a brief pins grammar, headings, note text, or
  prompt text, reproduce it exactly. If a pinned anchor is not found verbatim in a target
  file, STOP and report the discrepancy — do not approximate.
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests [-p '<file>.py']`
  (the dotted-module form is broken on this machine). Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` path in any deliverable. Do not commit or push.

---

## Phase 1 — The plan store + generator

### T1 — New script bin/journal_plan.py: pure core (store grammar, build/merge/carry, harness composition)
- status: done
- model: opus
- depends: (none)
- independent: no

**Brief.** Per PLAN.md D1/D3–D7. Create `bin/journal_plan.py` (NEW file; nothing else). This
task builds the PURE core only — module constants, parsers, builders, renderers, and text
mutators. NO CLI, NO argparse, NO importlib loads, NO file I/O helpers beyond what the pure
functions need (T2 adds the CLI; functions here take paths/dicts/strings and return values).
ZERO `Path.home()`, ZERO `subprocess`, ZERO network/sqlite — not even in a comment or
docstring (audits grep the literals).

Module scaffolding: `PLUGIN_ROOT = Path(__file__).resolve().parent.parent` and a module
docstring covering: what the runbook is (dated, checkable next-day plan under gitignored
`journal/plan/`), the advisory stance (nothing auto-executes; the script NEVER spawns
anything — no scheduler, no dispatch, by user decision), the deterministic-signals-then-prose
split (structural What/How seeds here; model enrichment happens in-session via the pinned
prompt), and the honesty rules (absent data → `est n/a`/notes, codex figures labeled
API-equivalent never-a-bill, user state never clobbered on rebuild).

Pinned constants (exact names and values):

```python
PLAN_SCHEMA = 1
PLAN_DIRNAME = "plan"
SEED_FILENAME = "seed.md"
PLAN_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEED_MARKERS = ("- ", "* ", "[ ] ")   # read_inbox parity (journal_collect.py)
MAX_PLAN_CARDS = 100
EST_PROFILE = "M"
TIER_TO_SLOT = {"haiku": "cheap", "sonnet": "mid", "opus": "mid"}
HARNESS_ORDER = ("claude_code", "copilot_cli", "codex_cli")
ADVISORY_LINE = ("Advisory only — nothing here auto-executes; every command below is "
                 "ready-to-paste for a human to run.")
NO_SIGNAL_LINE = "- harness signals unavailable — run journal_collect.py, then rebuild"
EST_NA = "est n/a — pricing or tier unavailable"
OPUS_SLOT_NOTE = ("- note: task pinned opus — estimates show the mid slot (the advisor's "
                  "table covers cheap/mid by design)")
```

File and card grammar — implement EXACTLY the shapes pinned in PLAN.md D1 (H1
`# Runbook — <due-date>`; `- schema: 1`; `- built-from: digest <as-of-date>` or
`- built-from: no digest`; the ADVISORY_LINE as its own paragraph; `## Tasks`; cards; a
`## Notes` section only when notes exist). Card: H3 `### [ ] R<n> — <title>` (`[x]` when
done), field lines `- source:`, `- due:`, `- first-planned:`, `- model-hint:` (value
`haiku|sonnet|opus|none`), optional `- deferred-to:`; then `**What/How:**` with its body;
then `**Harness:**` with its body. Card ids are file-scoped `R1..Rn` and STABLE.

Public API (pin these signatures — T3's tests call them):

- `sanitize_title(title) -> str` — strip every `"` and backtick, collapse internal
  whitespace runs to single spaces, strip ends.
- `dedup_key(card) -> str` — the card's `source` when it starts `kit:` or `wip:`; else the
  casefolded, whitespace-collapsed title.
- `parse_plan(text) -> dict` — `{"date": str|None, "cards": [card...], "notes": [str]}`.
  Card dict keys exactly: `id`, `checked` (bool), `title`, `source`, `due`,
  `first_planned`, `model_hint` (str, `"none"` when absent), `deferred_to` (str|None),
  `how` (the raw What/How body text), `harness` (the raw Harness body text). Tolerant: a
  malformed card is skipped with one entry in `notes` — never an exception. Round-trip
  property: `render` of parsed cards reproduces the file (T3 asserts it).
- `parse_seeds(text) -> list[str]` — inbox grammar: skip blank lines and lines starting
  `#`; strip ONE leading `SEED_MARKERS` marker; strip whitespace.
- `cards_from_digest(digest, for_date) -> list[card]` — new cards (id `None`), order:
  `signals.kit_tasks` (digest order), then `signals.wip`, then `signals.inbox.items`.
  Kit card: title `<kit>/<id> — <task title>`, source `kit:<kit>/<id>`, model_hint = the
  task's `model` when it is one of `TIER_TO_SLOT` else `"none"`. Wip card: title
  `Resume uncommitted work in <repo> (<branch>)`, source `wip:<repo>`, model_hint `none`.
  Inbox card: title = the item line, source `inbox`, model_hint `none`. All cards:
  `due = for_date`, `first_planned = for_date`, `checked False`, `deferred_to None`.
  What/How seeds (pinned verbatim, with fields substituted):
  - kit:
    ```
    1. Open `.claude/kits/<kit>/TASKS.md` and read the <id> brief — it is authoritative.
    2. Resume the kit: `/polytropos:execute <kit>` (Claude Code), or paste a harness command from below.
    3. Run the task's verify command from the repo root before calling it done.
    ```
  - wip:
    ```
    1. Open the <repo> repo (branch <branch>) — <dirty_files> dirty and <untracked> untracked files await.
    2. Review with `git status`; commit, stash, or continue the work.
    ```
  - inbox (and seed cards):
    ```
    1. <the line, verbatim>
    2. Refine this card during enrichment, then check it off once finished.
    ```
  A missing/None digest or missing signals keys → `[]` (tolerant `.get` all the way).
- `card_from_seed(line, for_date) -> card` — like an inbox card but source `seed`.
- `collect_carry(plan_dir, for_date) -> (list[card], list[str])` — scan
  `Path(plan_dir).glob("*.md")` keeping only stems matching `PLAN_STEM_RE` AND
  `stem < for_date` (ISO strings compare correctly; non-matching stems other than
  `seed.md` get one note each); parse each file (unreadable/malformed → note, continue);
  collect cards with `checked False` and (`deferred_to` None or `deferred_to <= for_date`);
  dedup by `dedup_key` keeping the occurrence from the LATEST (lexicographically greatest)
  stem; carried cards keep `title`, `source`, `model_hint`, `first_planned`, `how` and take
  `due = for_date`, `deferred_to = None`, `checked False`, `id None`. Return
  `(cards sorted by (first_planned, title), notes)`. Historical files are NEVER written.
- `assemble_cards(digest, seeds, carried, for_date) -> (list[card], list[str])` — combine
  in pinned order: carried first, then `cards_from_digest`, then seed cards; dedup by
  `dedup_key` (FIRST occurrence wins — carried therefore beats a digest duplicate,
  preserving its How and first-planned); cap at `MAX_PLAN_CARDS` with a note when exceeded.
- `merge_cards(existing, new) -> (list[card], set[str])` — D6 exactly: existing cards keep
  their id, order, `checked`, `deferred_to`, `first_planned`, `model_hint`, and `how`
  BYTE-INTACT; a new card whose key matches an existing card contributes nothing except
  marking that existing card for a Harness refresh; existing cards with no new match are
  preserved (marked NOT-for-refresh — their old `harness` text is kept verbatim);
  unmatched new cards append in order with the next free `R<n>` ids (n = 1 + the highest
  existing numeric id) and are marked for refresh. Returns the ordered card list and the
  set of card ids to refresh.
- `pick_slot(card) -> str` — `TIER_TO_SLOT.get(card["model_hint"], "mid")`.
- `pick_ideal(card, slot_entries) -> (harness, reason)` — PLAN.md D4 verbatim policy:
  `slot_entries` maps harness name → est slot entry (dict or None) for this card's slot at
  `EST_PROFILE`. (i) source starts `kit:` → `("claude_code", "kit tasks run via
  /polytropos:execute in Claude Code")`. (ii) both claude and copilot entries carry
  `usd_est` → the lower wins with reason
  `f"cheapest real-dollar est for profile {EST_PROFILE} (${a:.4f} vs ${b:.4f}); codex
  excluded from cost ranking (API-equivalent proxy, not a bill)"` (a = the winner's
  figure, b = the loser's). (iii) exactly one of the two has `usd_est` → it, reason
  `"only harness with a real-dollar estimate"`. (iv) neither → `("claude_code",
  "default — no estimates available")`. `codex_cli` is NEVER returned.
- `compose_harness_block(card, signal) -> str` — `signal` is a
  `journal_advisor.build_harness_signal` result dict or None. None (or a signal whose three
  `est` values are all None) → exactly `NO_SIGNAL_LINE` as the whole block. Else: line 1
  `- ideal: <harness> — <reason>` from `pick_ideal`; then one line per harness in
  `HARNESS_ORDER`. Per-harness: slot entry =
  `signal["harnesses"][h]["est"][EST_PROFILE][pick_slot(card)]` (any missing level →
  None). Entry present → render per the D1 grammar: model id from `entry["model"]`,
  command = `signal["harnesses"][h]["command_template"]` with `{model}` replaced by the
  model id and `<task>` replaced by `sanitize_title(card["title"])`, est text: claude
  `est M ~${usd_est:.4f}`; copilot `est M ~${usd_est:.4f} / ~{aic_est:.1f} AIC`; codex
  `est M ~${usd_api_equivalent:.4f} API-equivalent — not a bill`. Entry None → the line is
  `- <harness>: <EST_NA>` with NO command and NO model id (never guess). When
  `card["model_hint"] == "opus"`, append `OPUS_SLOT_NOTE` as the block's last line.
  (`EST_PROFILE` is `"M"` — build the `est M` label from the constant, not a second
  literal.)
- `render_plan(for_date, as_of, cards, notes, signal, refresh_ids=None) -> str` — the D1
  file shape. `as_of` None → `- built-from: no digest`. Cards whose `id` is None get
  sequential ids `R1..Rn` in list order, continuing after the highest existing numeric id
  (a fresh build therefore starts at `R1`); cards with ids keep them. For each card:
  recompose the Harness block via `compose_harness_block` when the card's id was None
  (new) or `refresh_ids` is None (refresh ALL) or its id is in `refresh_ids` — but only
  when `signal` is not None; otherwise keep the card's existing `harness` text verbatim
  (a None signal never downgrades an existing block; a new card under a None signal gets
  `NO_SIGNAL_LINE`). `## Notes` renders only when `notes` is non-empty. NO timestamp
  anywhere — identical inputs must render identical bytes.
- `mark_done(text, card_id) -> str` — flip exactly that card's `### [ ]` to `### [x]`;
  unknown id or already-done → raise `ValueError` with a message naming the id.
- `set_deferred(text, card_id, to_date) -> str` — add or update that card's
  `- deferred-to: <to_date>` line (immediately after the last field line of the card);
  unknown id → `ValueError`.
- `check_cards(plan_dir, today) -> (list[dict], list[str])` — D5: scan valid-stem files
  (ALL dates, not just past), parse, dedup by key keeping the latest-stem occurrence,
  `effective_due = deferred_to or file-stem date`; keep unchecked cards with
  `effective_due <= today`; return dicts
  `{"handle": "<file-stem>/<id>", "title", "effective_due", "overdue": bool
  (effective_due < today), "ideal": str|None}` sorted by (effective_due, handle), plus
  notes. `ideal` is parsed from the card's harness text: the text after `- ideal: ` up to
  the ` — ` separator when that line exists, else None.

Gotchas: keep every function pure over its arguments (only `collect_carry`/`check_cards`
read the filesystem, read-only, under the given `plan_dir` only). Dates are handled as ISO
strings plus `date.fromisoformat` where arithmetic is needed — never string slicing math.
The file must end with nothing after the constants/functions (no `main`, no
`if __name__` yet — T2 adds them; the file need not be executable until T2).

**Acceptance.**
- The heredoc smoke below passes (grammar round-trip, carry/dedup, merge preservation,
  ideal policy, codex labeling, degradation honesty).
- `! grep -nE 'Path\.home|subprocess|urllib|http\.client|socket|sqlite|launchctl|launchd|pmset|crontab'
  bin/journal_plan.py` is clean; no `claude-`/`gpt-5` model-id literal anywhere in it.
- Full suite still green; the only new/changed file this task produces is
  `bin/journal_plan.py` (the architect's CLAUDE.md edit and the kit/agent files pre-date
  execution and are not yours).

**Verify.**
```bash
cd /path/to/polytropos && \
! grep -nE 'Path\.home|subprocess|urllib|http\.client|socket|sqlite|launchctl|launchd|pmset|crontab' bin/journal_plan.py && \
! grep -nE 'claude-|gpt-5' bin/journal_plan.py && \
python3 -m unittest discover -s tests && \
python3 - <<'PY'
import importlib.util, tempfile
from pathlib import Path
root = Path('/path/to/polytropos')
spec = importlib.util.spec_from_file_location('jp', root / 'bin' / 'journal_plan.py')
jp = importlib.util.module_from_spec(spec); spec.loader.exec_module(jp)
sig = {"advisory": True, "harnesses": {
  "claude_code": {"command_template": 'claude -p --model {model} "<task>"',
    "est": {"M": {"cheap": {"model": "fake-haiku-1", "usd_est": 0.01},
                  "mid": {"model": "fake-sonnet-1", "usd_est": 0.05}}}},
  "copilot_cli": {"command_template": 'copilot --model {model} -p "<task>"',
    "est": {"M": {"cheap": None,
                  "mid": {"model": "fake-cop-1", "usd_est": 0.03, "aic_est": 3.0}}}},
  "codex_cli": {"command_template": 'codex exec --model {model} --full-auto "<task>"',
    "est": {"M": {"cheap": None,
                  "mid": {"model": "fake-cx-1", "usd_api_equivalent": 0.02, "billed_usd": None}}}}}}
digest = {"signals": {"kit_tasks": [{"kit": "demo-kit", "id": "T9", "title": "Wire the widget",
                                     "status": "pending", "model": "sonnet"}],
                      "wip": [{"repo": "demo", "branch": "main", "dirty_files": 2, "untracked": 1}],
                      "inbox": {"items": ['Email Sam re: "budget"']}}}
cards, notes = jp.assemble_cards(digest, ["seed line one"], [], "2026-01-16")
assert [c["source"] for c in cards] == ["kit:demo-kit/T9", "wip:demo", "inbox", "seed"]
text = jp.render_plan("2026-01-16", "2026-01-15", cards, notes, sig)
assert text.startswith("# Runbook — 2026-01-16") and jp.ADVISORY_LINE in text
assert "API-equivalent — not a bill" in text and "fake-cx-1" in text
assert 'Email Sam re: budget' in text  # quotes stripped in the command line
ideal_line = [l for l in text.splitlines() if l.startswith("- ideal:")][0]
assert "claude_code" in ideal_line  # kit card -> structural pick
parsed = jp.parse_plan(text)
assert len(parsed["cards"]) == 4 and parsed["cards"][0]["id"] == "R1"
# ideal cost policy: non-kit card, copilot mid ($0.03) beats claude mid ($0.05)
h, why = jp.pick_ideal(cards[2], {"claude_code": {"model": "x", "usd_est": 0.05},
                                  "copilot_cli": {"model": "y", "usd_est": 0.03},
                                  "codex_cli": {"model": "z", "usd_api_equivalent": 0.001}})
assert h == "copilot_cli" and "not a bill" in why
# degradation: no signal -> the pinned single line, never a figure
blk = jp.compose_harness_block(cards[0], None)
assert blk == jp.NO_SIGNAL_LINE
with tempfile.TemporaryDirectory() as td:
    pd = Path(td) / "plan"; pd.mkdir()
    (pd / "2026-01-16.md").write_text(text)
    done = jp.mark_done(text, "R1"); (pd / "2026-01-16.md").write_text(done)
    assert "### [x] R1" in done
    carried, cn = jp.collect_carry(pd, "2026-01-17")
    keys = {jp.dedup_key(c) for c in carried}
    assert "kit:demo-kit/T9" not in keys and "wip:demo" in keys  # done not carried
    assert all(c["first_planned"] == "2026-01-16" for c in carried)
    # merge preserves user state, refreshes only matched harness blocks
    existing = jp.parse_plan(done)["cards"]
    existing[1]["how"] = "1. ENRICHED BY MODEL\n2. keep me"
    new_cards, _ = jp.assemble_cards(digest, [], [], "2026-01-16")
    merged, refresh = jp.merge_cards(existing, new_cards)
    assert [c["id"] for c in merged][:4] == ["R1", "R2", "R3", "R4"]
    assert merged[0]["checked"] is True and merged[1]["how"].startswith("1. ENRICHED")
    d2 = jp.set_deferred(done, "R3", "2026-01-20")
    assert "- deferred-to: 2026-01-20" in d2
    (pd / "2026-01-16.md").write_text(d2)
    due, _ = jp.check_cards(pd, "2026-01-17")
    handles = {r["handle"] for r in due}
    assert "2026-01-16/R3" not in handles and "2026-01-16/R2" in handles
    assert all(r["overdue"] for r in due)
print('T1 smoke OK')
PY
```

### T2 — journal_plan.py CLI (build/check/done/defer/prompt) + the pinned enrichment prompt
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Per PLAN.md D2/D3/D5. Edit `bin/journal_plan.py` ONLY (extend T1's file — never
run in parallel with T1). Add the reuse loads, the enrichment prompt, and the CLI. Still
ZERO `subprocess`, ZERO `Path.home()`, no network/sqlite anywhere — not even in comments.

1. Module loads (top of file, after the constants): copy the 6-line `_load(name)` importlib
   helper from `bin/journal_collect.py` verbatim, then:
   ```python
   cr = _load("cost_report")      # data/pricing.json loader (read-only reuse)
   cu = _load("copilot_usage")    # data/pricing.copilot.json loader (read-only reuse)
   cxu = _load("codex_usage")     # data/pricing.codex.json loader (read-only reuse)
   ja = _load("journal_advisor")  # harness routing signals (advisory-only, read-only reuse)
   ```
2. Date helpers: copy `_resolve_date_str(date_arg, utc)` and `_next_date(date_str)`
   semantics from `bin/journal_summarize.py` (re-stated locally — do not import the
   summarizer).
3. `build_enrich_prompt(plan_text, digest) -> str` (pure). Pinned text — reproduce exactly:
   ```python
   ENRICH_HEADER = (
       "You are enriching a next-day runbook for a human operator. Rewrite ONLY the content\n"
       "under each open card's **What/How:** heading into 2-6 concrete, numbered steps: what\n"
       "to do, which file or path to start in, the exact command to run first, and how to\n"
       "verify it worked. Use ONLY facts present in the runbook and digest below — do not\n"
       "invent files, flags, model ids, or costs; where a fact is absent, keep the step\n"
       "general rather than guessing. Reproduce every other line byte-identical: the H1, all\n"
       "headings, checkboxes, field lines (source/due/first-planned/model-hint/deferred-to),\n"
       "and every **Harness:** block including its commands and estimates. Do not add,\n"
       "remove, or reorder cards. Nothing here auto-executes — the runbook is instructions a\n"
       "human chooses to run.\n"
   )
   ```
   The function returns `ENRICH_HEADER` + `"\nRunbook:\n```markdown\n" + plan_text +
   "\n```\n\n"` + (when `digest` is a dict: `"Digest (JSON):\n```json\n" + compact-json +
   "\n```\n\n"` with `json.dumps(digest, indent=None, separators=(",", ":"))` — the
   `build_prompts` precedent; else the line `"No digest is available for extra context.\n\n"`)
   + `"Respond with ONLY the full revised markdown document.\n"`.
4. `main(argv=None)` with argparse SUBCOMMANDS (`build` is the default help focus):
   - Shared flags on every subcommand: `--journal-dir` (default
     `str(PLUGIN_ROOT / "journal")`), `--date` (YYYY-MM-DD; default today), `--utc`
     (resolve the default date in UTC — tests/verifies use it).
   - `build [--for YYYY-MM-DD] [--print]`: `as_of = _resolve_date_str(--date, --utc)`;
     `for_date = --for or _next_date(as_of)`; validate `--for` with `date.fromisoformat`
     AND `PLAN_STEM_RE` BEFORE composing any path (reject → `sys.exit` message; nothing may
     escape the plan dir). Read `<journal-dir>/<as_of>/digest.json` when present (tolerant:
     unreadable/unparseable → `digest = None` + a note `no digest for <as_of> — kit/inbox/
     wip signals unavailable; run journal_collect.py first`). Harness signal: load the
     three pricing dicts via `cr.load_pricing()` / `cu.load_pricing()` /
     `cxu.load_pricing()` and call
     `ja.build_harness_signal((digest or {}).get("sources") or {}, pc, pco, pcx)` wrapped
     in try/except Exception → `signal = None` + note `advisor failed: <e!r>` (the
     collector's degradation precedent). Seeds: read
     `<journal-dir>/plan/seed.md` via `parse_seeds` when present (READ-ONLY — never write,
     truncate, or delete it). Carried: `collect_carry(plan_dir, for_date)`. Assemble via
     `assemble_cards`; when `<plan-dir>/<for_date>.md` exists parse it and `merge_cards`,
     rendering with the returned refresh-id set; else render all-fresh. Write ONLY
     `<journal-dir>/plan/<for_date>.md` (`mkdir(parents=True, exist_ok=True)`; OSError →
     `sys.exit`). Print exactly one status line:
     `runbook written: <path> — <open> open (<carried> carried), <done> done` (open =
     unchecked cards, carried = carried count, done = checked cards in the final file).
     `--print` additionally echoes the full file. Idempotence is contract: an immediate
     second `build` with identical inputs writes identical bytes.
   - `check`: `today = _resolve_date_str(--date, --utc)`; `check_cards(plan_dir, today)`.
     Output: header line `# Runbook check — <today>`, blank line, then one line per due
     card: `OVERDUE since <effective_due>  [<handle>]  <title>  (ideal: <harness-or-n/a>)`
     for overdue rows and `DUE <effective_due>  [<handle>]  <title>  (ideal: <...>)` for
     due-today rows; then a blank line and the counts line
     `<n> due today, <m> overdue`; then
     `mark done: python3 bin/journal_plan.py done <id> --date <file-date>`. When nothing
     is due: `no runbook cards due for <today> — build one: python3 bin/journal_plan.py
     build`. Notes (if any) print one per line prefixed `note: `. ALWAYS exit 0 (a missing
     plan dir is just the empty message).
   - `done <id>`: target file `<plan-dir>/<--date>.md` (default today — the file DATE
     addresses the card, matching check's `[<file-date>/<id>]` handles); missing file or
     unknown id → `sys.exit` with a message that names the file/id and lists the plan
     files that do exist. On success rewrite the file via `mark_done` and print
     `done: [<date>/<id>] <title>`.
   - `defer <id> --to YYYY-MM-DD`: same addressing; validate `--to` (fromisoformat +
     `PLAN_STEM_RE`); rewrite via `set_deferred`; print
     `deferred to <to>: [<date>/<id>] <title>`.
   - `prompt [--for YYYY-MM-DD]`: `for_date = --for or _next_date(as_of)`; read
     `<plan-dir>/<for_date>.md` (missing → `sys.exit` telling the user to `build` first)
     and the as-of digest when present; print `build_enrich_prompt(plan_text, digest)` to
     stdout. Spawns NOTHING, writes NOTHING.
   - `if __name__ == "__main__": sys.exit(main())`.
5. Extend the module docstring with a Usage block listing the five subcommands and the
   statement that `build`/`done`/`defer` write ONLY under `<journal-dir>/plan/` and that
   `prompt` is how the journal skill enriches the What/How steps in-session.

**Acceptance.**
- The verify chain below passes end-to-end in a temp `--journal-dir` (build writes only
  `plan/<d+1>.md`; card grammar + advisory line + not-a-bill labeling present; model ids in
  the file are real pricing-file ids derived at run time by the script; build is
  idempotent byte-for-byte; check/done/defer round-trip; prompt prints the pinned header
  and spawns nothing).
- `bin/journal_plan.py` still grep-clean for
  `Path\.home|subprocess|urllib|http\.client|socket|sqlite|launchctl|launchd|pmset|crontab`
  and for `claude-|gpt-5` model-id literals.
- Full suite green; the only new/changed file this task produces is `bin/journal_plan.py`
  (the architect's CLAUDE.md edit and the kit/agent files pre-date execution and are not
  yours).

**Verify.**
```bash
cd /path/to/polytropos && \
! grep -nE 'Path\.home|subprocess|urllib|http\.client|socket|sqlite|launchctl|launchd|pmset|crontab' bin/journal_plan.py && \
! grep -nE 'claude-|gpt-5' bin/journal_plan.py && \
export TMP=$(mktemp -d) && \
mkdir -p "$TMP/plan" && printf '# seeds\n- refill the demo fixtures\n' > "$TMP/plan/seed.md" && \
python3 bin/journal_plan.py build --date 2026-01-15 --utc --journal-dir "$TMP" && \
test -f "$TMP/plan/2026-01-16.md" && \
grep -q '^# Runbook — 2026-01-16' "$TMP/plan/2026-01-16.md" && \
grep -q 'Advisory only — nothing here auto-executes' "$TMP/plan/2026-01-16.md" && \
grep -q 'API-equivalent — not a bill' "$TMP/plan/2026-01-16.md" && \
grep -q '^### \[ \] R1 — refill the demo fixtures' "$TMP/plan/2026-01-16.md" && \
grep -q -- '- ideal: ' "$TMP/plan/2026-01-16.md" && \
python3 bin/journal_plan.py build --date 2026-01-15 --utc --journal-dir "$TMP" && \
cp "$TMP/plan/2026-01-16.md" "$TMP/second.md" && \
python3 bin/journal_plan.py build --date 2026-01-15 --utc --journal-dir "$TMP" && \
cmp "$TMP/plan/2026-01-16.md" "$TMP/second.md" && \
python3 bin/journal_plan.py check --date 2026-01-16 --utc --journal-dir "$TMP" | grep -q 'DUE 2026-01-16' && \
python3 bin/journal_plan.py done R1 --date 2026-01-16 --utc --journal-dir "$TMP" && \
grep -q '^### \[x\] R1' "$TMP/plan/2026-01-16.md" && \
python3 bin/journal_plan.py check --date 2026-01-17 --utc --journal-dir "$TMP" | grep -q 'no runbook cards due' && \
python3 bin/journal_plan.py prompt --date 2026-01-15 --utc --journal-dir "$TMP" | grep -q 'You are enriching a next-day runbook' && \
grep -q 'refill the demo fixtures' "$TMP/plan/seed.md" && \
python3 -m unittest discover -s tests && \
python3 - <<'PY'
import json, os
from pathlib import Path
tmp = Path(os.environ['TMP'])
text = (tmp / 'plan' / '2026-01-16.md').read_text()
pricing = json.load(open('data/pricing.json'))
mid = next(m for m, s in pricing['models'].items()
           if isinstance(s, dict) and s.get('tier') == 'sonnet')
assert mid in text, 'claude mid-slot model id (derived at run time) missing from commands'
assert 'no digest for 2026-01-15' in text, 'missing honest no-digest note'
print('T2 smoke OK')
PY
```

### T3 — New tests: tests/test_journal_plan.py
- status: done
- model: sonnet
- depends: T2
- independent: no

**Brief.** Per PLAN.md D8. Create `tests/test_journal_plan.py` (NEW file — never touch the
seven pre-existing journal test files). House conventions of
`tests/test_journal_askpack.py`: importlib-load `bin/journal_plan.py` by absolute path
(`Path(__file__).resolve().parent.parent / "bin" / "journal_plan.py"`), all fixtures under
`tempfile.TemporaryDirectory()`, drive `main(argv)` in-process (capture stdout via
`contextlib.redirect_stdout`, catch `SystemExit` for error paths), zero `Path.home()`, no
`subprocess`, no network/sqlite imports, `--utc` on every CLI call. Unit tests feed the pure
functions synthetic digests and a synthetic advisor-signal dict (fake ids like
`"fake-haiku-1"` are sanctioned); CLI end-to-end tests let the script load the real pricing
files (sanctioned config reuse) and derive every asserted model id at RUN TIME (e.g. first
model of tier `sonnet` in `data/pricing.json` file order) — never a `claude-*`/`gpt-5*`
literal.

Cover at least:

1. **Grammar round-trip**: `render_plan` → `parse_plan` → re-render reproduces identical
   bytes; card field lines, checkbox states, deferred-to, What/How and Harness bodies all
   survive.
2. **Card building**: kit/wip/inbox/seed cards get the pinned titles, source tokens,
   model hints, and What/How seeds; a None digest → no cards + no crash; the
   `MAX_PLAN_CARDS` cap adds a note.
3. **Slot + command composition**: model-hint `haiku` → cheap-slot model in all three
   commands; `sonnet`/`opus`/`none` → mid slot; `opus` adds `OPUS_SLOT_NOTE`; the
   `<task>` substitution strips `"` and backticks from the title; the codex line always
   contains `API-equivalent — not a bill`.
4. **Ideal policy**: kit source → claude_code (structural reason); cheaper copilot →
   copilot_cli with both figures in the reason; only-claude-est → claude_code; no ests →
   the pinned default; codex_cli NEVER returned even when its number is smallest.
5. **Degradation honesty**: signal None → block is exactly `NO_SIGNAL_LINE`; a None slot →
   `EST_NA` line with no command and no model id; no fabricated figures anywhere (assert
   the rendered file contains no `$` outside composed est/reason text for the None cases).
6. **Carry-forward**: unchecked card in `<plan>/2026-01-10.md` appears in a build for
   2026-01-12 with `first-planned: 2026-01-10` preserved and `due: 2026-01-12`; a checked
   card does not carry; `deferred-to: 2026-01-20` keeps a card out of the 01-12 build but
   in a 2026-01-20 build; the historical file's bytes are untouched by build and check
   (byte-snapshot proof).
7. **Latest-occurrence dedup**: the same key unchecked in two dated files → carried once,
   with the LATER file's What/How; `check` reports it once.
8. **Merge preservation**: build a date, mark a card done, hand-replace another card's
   What/How body with a marker, add a new kit task to the digest, rebuild the SAME date →
   checkbox preserved, marker body preserved byte-identical, ids stable, new card appended
   with the next id, no duplicates; unmatched old card still present.
9. **Seeds**: `seed.md` lines become `seed` cards; a rebuild does not duplicate them;
   `seed.md` bytes are identical before/after (read-only proof).
10. **check classification**: due-today vs overdue vs future vs deferred-to-today, exit
    0 with empty store, the `[<file-date>/<id>]` handle format, notes for a rogue
    non-date `.md` file in the plan dir.
11. **done/defer via main()**: happy paths rewrite only the addressed file; unknown id and
    missing file exit nonzero with a useful message; an invalid `--to`/`--for` date is
    rejected BEFORE any path is composed (assert no stray file appears).
12. **Enrichment prompt**: contains the pinned header phrases (`You are enriching a
    next-day runbook`, `byte-identical`, `Nothing here auto-executes`, `Respond with ONLY
    the full revised markdown document.`), embeds the plan text, includes the digest JSON
    when present and the `No digest is available for extra context.` line when not.
13. **CLI end-to-end + determinism + write-isolation**: `build` in a temp journal tree
    (with a digest fixture written by hand carrying one kit task) writes ONLY
    `plan/<for>.md` (assert the journal tree's full file set before/after); two identical
    builds → identical bytes; the commands in the file carry pricing-file model ids
    derived at run time.

**Acceptance.**
- New file green; FULL suite green; all seven pre-existing journal test files
  byte-unchanged (`git diff --quiet` each); grep-clean
  (`Path\.home|sqlite|urllib|http\.client|socket|subprocess|launchctl|gpt-5|claude-`
  absent from the new test file).

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests -p 'test_journal_plan.py' && \
python3 -m unittest discover -s tests && \
git diff --quiet -- tests/test_journal_sources.py tests/test_journal_collect.py tests/test_journal_summarize.py tests/test_journal_schedule.py tests/test_journal_codex_augment.py tests/test_journal_askpack.py tests/test_journal_advisor.py && \
! grep -nE 'Path\.home|sqlite|urllib|http\.client|socket|subprocess|launchctl|gpt-5|claude-' tests/test_journal_plan.py && \
echo T3 OK
```

---

## Phase 2 — Surfaces

### T4 — Extend skills/journal/SKILL.md with the runbook flow (BODY-only)
- status: done
- model: sonnet
- depends: T2
- independent: yes

**Brief.** Per PLAN.md D8. Edit `skills/journal/SKILL.md` ONLY. The plugin is LIVE — the
YAML frontmatter (lines 1–5: `---`, `name:`, `description:`, `allowed-tools:`, `---`) must
stay byte-identical to `git show HEAD:skills/journal/SKILL.md`. BODY changes only: add ONE
new H2 section exactly titled `## Next-day runbook` immediately AFTER the existing
`## Inbox & schedule` section (before `## External tools (Teams / Outlook / Copilot
Studio)`). Content (own the wording; keep the skill's existing voice and `$ROOT` command
style):

1. Build tomorrow's runbook after the digest exists:
   ```bash
   python3 "$ROOT/bin/journal_plan.py" build
   ```
   It writes `journal/plan/<date>.md` — one dated, checkable card per planned task
   (drawn from open kit tasks, WIP repos, the inbox, and `journal/plan/seed.md`), each
   with a What/How, an ideal-harness line, and ready-to-paste commands for Claude Code,
   Copilot CLI, and Codex CLI with cost estimates from the pricing files (Codex figures
   are API-equivalent proxies, never a bill). State that unchecked cards from earlier
   days carry forward automatically.
2. Enrich the What/How steps IN THIS SESSION (the current session is already paid for —
   the summaries precedent): run
   ```bash
   python3 "$ROOT/bin/journal_plan.py" prompt
   ```
   follow the printed prompt exactly (rewrite ONLY the What/How bodies, keep every other
   line byte-identical), and save the revised document back over the same
   `journal/plan/<date>.md` path.
3. On the day tasks are due:
   ```bash
   python3 "$ROOT/bin/journal_plan.py" check
   python3 "$ROOT/bin/journal_plan.py" done <id> --date <file-date>
   python3 "$ROOT/bin/journal_plan.py" defer <id> --to <date> --date <file-date>
   ```
   (or just edit the checkboxes in the markdown by hand — the file is yours).
4. Quiet days: hand-add lines to `journal/plan/seed.md` (same plain-line format as the
   inbox) and rebuild.
5. Close the section with an explicit advisory sentence: the runbook prepares and tracks —
   it NEVER schedules or executes anything; every command is text you choose to run, and
   there is no scheduler by design (the user tabled it).

**Acceptance.**
- Frontmatter (first 5 lines) byte-identical to HEAD; the new H2 exists in the pinned
  position; the pinned phrases (`journal_plan.py`, `journal/plan/`, `seed.md`,
  `never a bill`, `carry`, an advisory/no-scheduler sentence) appear; every pre-existing
  H2 is untouched and in its original order.
- Full suite green; `git diff --name-only` shows only `skills/journal/SKILL.md`.

**Verify.**
```bash
cd /path/to/polytropos && \
diff <(git show HEAD:skills/journal/SKILL.md | head -5) <(head -5 skills/journal/SKILL.md) && \
grep -q '^## Next-day runbook' skills/journal/SKILL.md && \
grep -q 'journal_plan.py' skills/journal/SKILL.md && \
grep -q 'journal/plan/' skills/journal/SKILL.md && \
grep -q 'seed.md' skills/journal/SKILL.md && \
grep -q 'never a bill' skills/journal/SKILL.md && \
grep -qi 'carr' skills/journal/SKILL.md && \
grep -q '^## Inbox & schedule' skills/journal/SKILL.md && \
grep -q '^## External tools (Teams / Outlook / Copilot Studio)' skills/journal/SKILL.md && \
awk '/^## Next-day runbook/{a=NR} /^## External tools/{b=NR} END{exit !(a<b)}' skills/journal/SKILL.md && \
python3 -m unittest discover -s tests && \
git diff --name-only | grep -v -e '^skills/journal/SKILL.md$' -e '^docs/DAILY-JOURNAL.md$' -e '^CLAUDE.md$' | wc -l | grep -q '^ *0$' && \
echo T4 OK
```

### T5 — New docs/NEXT-DAY-RUNBOOK.md + the pinned pointer in docs/DAILY-JOURNAL.md
- status: done
- model: sonnet
- depends: T2
- independent: yes

**Brief.** Per PLAN.md D8. Two targets: create `docs/NEXT-DAY-RUNBOOK.md` (NEW) and make
ONE pinned insertion in `docs/DAILY-JOURNAL.md`. Facts come from PLAN.md and the shipped
`bin/journal_plan.py` — no invented flags, no price or model-id literals (never a
`claude-*`/`gpt-5*` id in either doc).

`docs/NEXT-DAY-RUNBOOK.md` — H1 `# Next-day runbook`, then H2 sections (own the wording,
match `docs/DAILY-JOURNAL.md`'s voice):
- `## What this is` — a dated, checkable plan for tomorrow layered on the daily journal;
  explicitly: there is NO scheduler and NO auto-execution by design (the user tabled
  scheduling) — everything is user-invoked, and `journal_plan.py` never spawns anything.
- `## The flow` — collect the digest → `build` (default target: the next day) → enrich the
  What/How steps in-session via `prompt` → on the due day `check`, then `done`/`defer` or
  hand-edit the checkboxes; unchecked cards carry forward into later builds.
- `## The store` — `journal/plan/<YYYY-MM-DD>.md` (gitignored, one file per due date), the
  card grammar with a short example card (use placeholder model ids like `<model-id>` in
  the example — not real ids), `seed.md` as the hand-seeding path (inbox line format,
  never modified by the tool), and the rule that rebuilds preserve checkboxes,
  deferrals, ids, and enriched What/How bodies while refreshing only the Harness blocks.
- `## Harness recommendations` — every card carries commands for all three harnesses
  composed from the journal advisor's pinned command templates with the recommended model
  substituted at run time, plus profile-M cost estimates from the three pricing files
  (never merged); the deterministic ideal pick and its policy, including that codex_cli is
  never cost-ranked because its figures are API-equivalent relative-burn proxies, never a
  bill; absent data renders `est n/a` or an honest note — never a fabricated figure.
- `## Check & carry-forward` — due-today vs overdue, the `[<file-date>/<id>]` handles,
  latest-occurrence dedup so a carried card is never counted twice, deferral semantics.
- `## What it never does` — no launchd/pmset/cron/daemon, no unattended dispatch, no
  network/OAuth/MCP, no SQLite, no home-directory reads; writes only under
  `journal/plan/`.

`docs/DAILY-JOURNAL.md` — in the `## Next-day planning & the inbox` section, find the
existing paragraph that begins exactly:
```
`next-day.md` turns exactly these signals into prose:
```
and append AFTER that paragraph (as a new paragraph) exactly:
```
The same signals also feed the **next-day runbook** — a dated, checkable plan under
`journal/plan/` with per-task harness commands, carry-forward, and a check-off surface,
built on demand by `bin/journal_plan.py` (no scheduler, no auto-execution — see
[NEXT-DAY-RUNBOOK.md](NEXT-DAY-RUNBOOK.md)).
```
If the anchor paragraph is not found verbatim, STOP and report.

**Acceptance.**
- `docs/NEXT-DAY-RUNBOOK.md` exists with the six pinned H2s; states no-scheduler /
  no-auto-execution; contains `never a bill` and `est n/a`; no real model-id or price
  literals.
- `docs/DAILY-JOURNAL.md` carries the pinned pointer paragraph; nothing else in it
  changed.
- `git diff --name-only` shows only `docs/DAILY-JOURNAL.md` (plus the new untracked doc);
  full suite green.

**Verify.**
```bash
cd /path/to/polytropos && \
grep -q '^# Next-day runbook' docs/NEXT-DAY-RUNBOOK.md && \
grep -q '^## What this is' docs/NEXT-DAY-RUNBOOK.md && \
grep -q '^## The flow' docs/NEXT-DAY-RUNBOOK.md && \
grep -q '^## The store' docs/NEXT-DAY-RUNBOOK.md && \
grep -q '^## Harness recommendations' docs/NEXT-DAY-RUNBOOK.md && \
grep -q '^## Check & carry-forward' docs/NEXT-DAY-RUNBOOK.md && \
grep -q '^## What it never does' docs/NEXT-DAY-RUNBOOK.md && \
grep -q 'never a bill' docs/NEXT-DAY-RUNBOOK.md && \
grep -q 'est n/a' docs/NEXT-DAY-RUNBOOK.md && \
! grep -nE 'claude-|gpt-5' docs/NEXT-DAY-RUNBOOK.md && \
grep -q 'NEXT-DAY-RUNBOOK.md' docs/DAILY-JOURNAL.md && \
grep -q 'next-day runbook' docs/DAILY-JOURNAL.md && \
git diff --name-only | grep -v -e '^docs/DAILY-JOURNAL.md$' -e '^skills/journal/SKILL.md$' -e '^CLAUDE.md$' | wc -l | grep -q '^ *0$' && \
python3 -m unittest discover -s tests && \
echo T5 OK
```
(The `skills/journal/SKILL.md` and `CLAUDE.md` exclusions in the diff check tolerate T4
having already landed in parallel and the architect's pre-made CLAUDE.md insertions.)

---

## Phase 3 — Closure

### T6 — Final sweep: full suite + fence audit
- status: done
- model: haiku
- depends: T3, T4, T5
- independent: no

**Brief.** No file changes (if any check fails, report — do not fix). Run the full audit:
suite green; the seven pre-existing journal test files and every reused script
byte-untouched; the new/edited files clean of scheduler/dispatch/home/network/sqlite
primitives and of real model-id literals; CLAUDE.md untouched by executors (the
architect's insertions are already in the working tree).

**Acceptance.** Every command in the verify chain passes.

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests && \
git diff --quiet -- tests/test_journal_sources.py tests/test_journal_collect.py tests/test_journal_summarize.py tests/test_journal_schedule.py tests/test_journal_codex_augment.py tests/test_journal_askpack.py tests/test_journal_advisor.py && \
git diff --quiet -- bin/journal_advisor.py bin/journal_collect.py bin/journal_summarize.py bin/journal_sources.py bin/journal_askpack.py bin/journal_schedule.py bin/cost_report.py bin/copilot_usage.py bin/codex_usage.py bin/copilot_pricing.py bin/codex_pricing.py && \
git diff --quiet -- data README.md .claude-plugin copilot codex && \
! grep -nE 'Path\.home|subprocess|urllib|http\.client|socket|sqlite|launchctl|launchd|pmset|crontab' bin/journal_plan.py && \
! grep -nE 'Path\.home|sqlite|urllib|http\.client|socket|subprocess|launchctl' tests/test_journal_plan.py && \
! grep -nE 'claude-|gpt-5' bin/journal_plan.py tests/test_journal_plan.py docs/NEXT-DAY-RUNBOOK.md && \
test "$(grep -c 'Path.home()' bin/journal_collect.py)" = "3" && \
git show HEAD:skills/journal/SKILL.md | head -5 | diff - <(head -5 skills/journal/SKILL.md) && \
test -f docs/NEXT-DAY-RUNBOOK.md && \
echo T6 OK
```
