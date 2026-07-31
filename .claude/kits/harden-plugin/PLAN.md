# PLAN — harden-plugin

Harden the `polytropos` Claude Code plugin: fix confirmed correctness bugs in the two
Python scripts, close the architect⇄execute kit-contract drift, scrub drift-prone literals out
of skill instructions, refresh the README install section, and add a stdlib test suite as a
durable regression guard.

Architected by Fable 5 on 2026-07-01. Every finding below was **empirically confirmed** (repro
commands were run) before being listed. Executors: do not re-diagnose; implement the pinned fixes.

---

## Goal and definition of done

**Goal:** every confirmed finding fixed in the working tree, guarded by automated tests, with
zero scope creep.

**Done means ALL of the following are true (checkable, run from the repo root):**

1. Every task in `TASKS.md` has `status: done`.
2. `python3 -m unittest discover -s tests -v` exits 0 with at least 18 test methods/subtests.
3. `python3 bin/cost_report.py --days 30` runs to completion with no traceback.
4. This pipe renders model, cost, ctx, AND both rate-limit fields:
   `echo '{"model":{"id":"claude-fable-5","display_name":"Fable 5"},"cost":{"total_cost_usd":1.23},"context_window":{"used_percentage":42},"rate_limits":{"five_hour":{"used_percentage":12},"seven_day":{"used_percentage":34}}}' | python3 bin/statusline.py`
5. `grep -rE '\$[0-9]' skills/` returns nothing and `grep -r '2026-08-31' skills/` returns nothing
   (no standalone price/date literals in skill instructions).
6. `skills/architect/SKILL.md` and `skills/execute/SKILL.md` both state the same kit contract:
   phase grouping, dependency/independence marking, the four-word status vocabulary, and the
   task-`model`-overrides-agent-frontmatter dispatch rule.
7. `git status` shows changes ONLY under: `bin/`, `tests/`, `skills/`, `README.md`, `CLAUDE.md`,
   `.claude/kits/harden-plugin/`, `.claude/agents/`.

---

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Do any open-source packaging work.** No LICENSE file, no version bump in
  `.claude-plugin/plugin.json`, no git tags, no release ceremony.
- **Refactor away hardcoded `~` paths.** This is a personal plugin; the absolute
  paths in `README.md` are correct for this machine and are NOT bugs. (Path work IS in scope only
  where a command is broken as written — see finding F4.)
- **Redesign the plugin's concept, add skills, remove skills, or rename anything.**
- **Touch anything outside the repo.** `~/.claude/settings.json` and the installed plugin copy
  under `~/.claude` are strictly off-limits. Do not re-install or refresh the plugin.
- **Add dependencies.** The scripts and tests are Python 3 stdlib only. No pip, no requirements
  file, no pytest (decision D2 below).
- **Commit or push.** Fix mode is working-tree only; the user reviews and commits.
- **Edit `data/pricing.json` values.** It was audited and found coherent (see non-issues). Prices,
  multipliers, dates, and model entries stay exactly as they are.

---

## Architecture & key decisions (with rationale — read before improvising anything)

**D1 — `data/pricing.json` is the single numeric source of truth.**
Skill instruction files must never contain standalone price figures, price ratios, or pricing
dates — they must instruct the executing model to read pricing.json and derive values at run
time. A fix that hardcodes a number is wrong *even if the number is currently right*, because the
whole design premise is that a price change is a one-file edit. Exception: `README.md` and
`docs/` tables are labeled snapshots ("cached 2026-07-01") refreshed together with
`cached_date` — literals are allowed there. Glosses immediately adjacent to their pricing.json
field name (e.g. "`cache_read_multiplier` (0.1×)") are acceptable in skills because the field
reference travels with the value; standalone literals are not.

**D2 — Tests use stdlib `unittest`, zero new dependencies.**
`docs/HOW-IT-WORKS.md` §4 advertises the scripts as "python3, stdlib only" and the repo has no
Python packaging files at all. Adding pytest would create the plugin's first dependency for no
capability we need. Tests live in `tests/`, load `bin/*.py` via `importlib` by file path (bin/ is
not a package), and run with `python3 -m unittest discover -s tests -v`.

**D3 — `match_model` policy: exact match or dash-delimited suffix only; unknowns are surfaced,
never guessed.**
The current bare `base.startswith(key)` clause silently mis-prices future model IDs
(`claude-sonnet-50`, `claude-sonnet-5x-beta` both matched `claude-sonnet-5` — confirmed by repro).
Silent misattribution corrupts the report invisibly; the "Unpriced models" section exists exactly
so unknowns are loud. Synthetic pseudo-models (IDs starting with `<`) are deliberately skipped
and must not pollute the Unpriced section.

**D4 — Naive timestamps are coerced to UTC, not dropped.**
Dropping a record loses cost data; crashing (current behavior — confirmed TypeError) loses the
whole report. Claude Code's own timestamps are UTC (`Z`-suffixed), so assuming UTC for the rare
naive one is the least-wrong choice. Records with *no parseable timestamp at all* stay included
regardless of `--days` and are priced at base (non-intro) rates — can't age-filter what has no age.

**D5 — The kit contract is defined once and mirrored in both skills.**
`architect` is the producer spec, `execute` is the consumer. Canonical contract:
- Layout: `.claude/kits/<slug>/PLAN.md` + `TASKS.md`; `NOTES.md` is created/maintained by execute.
- Task fields: `id`, `title`, `status`, `model`, self-contained brief, acceptance criteria,
  verify command.
- Status vocabulary: `pending | in-progress | done | blocked` (exactly these four).
- Tasks are grouped under phase headings; each task marks dependencies or independence explicitly.
- **Dispatch rule:** the task's `model` field is authoritative — execute passes it as the Agent
  tool's `model` parameter, which overrides the implementer agent's frontmatter default.
Rationale: execute currently references phase boundaries and independence markers that architect
never instructs Fable to produce, and an `opus`-pinned task dispatched to the sonnet-pinned
implementer would silently run on sonnet. A lesser model executing a kit trips exactly here.

**D6 — `${CLAUDE_PLUGIN_ROOT}` is the primary path mechanism in skills that shell out or read
plugin files.**
A bash command with a `../../` relative path resolves against the CWD, not the SKILL.md location —
`python3 ../../bin/cost_report.py` fails verbatim from any normal working directory. Claude Code
sets `${CLAUDE_PLUGIN_ROOT}` to the installed plugin root for plugin content; use it, keeping the
"relative to this SKILL.md" phrasing as the human-readable fallback for when the var is unset.
Exception (pin this): the `statusLine` command written into `~/.claude/settings.json` by the setup
skill runs OUTSIDE plugin context, so it must be a resolved literal absolute path, never the
env var.

**D7 — Docs churn is minimized.**
`docs/HOW-IT-WORKS.md` and `docs/how-it-works.html` were audited against the fixes: nothing in
them becomes false after this kit (they already describe phases/verification the way D5 pins
them, and their price tables are labeled snapshots per D1). Only `README.md`'s Install section
needs updating (F5). Do not restyle or rewrite the docs.

---

## Confirmed findings

| ID | Sev | Finding (confirmed how) | Fix direction | Task |
|---|---|---|---|---|
| F1 | HIGH | `bin/cost_report.py` crashes with `TypeError: can't compare offset-naive and offset-aware datetimes` if any transcript line has a tz-naive `timestamp` — one bad line kills the entire report. Repro: `parse_timestamp('2026-06-01T12:00:00')` returns naive dt; comparison with aware `cutoff` raised. | Coerce naive → UTC in `parse_timestamp` (D4). | T1 |
| F2 | MED | `match_model` bare `startswith(key)` mis-prices unknown IDs: `claude-sonnet-50` and `claude-sonnet-5x-beta` both matched `claude-sonnet-5` (repro). Also: the `key + "-"` clause is dead code (subsumed), and `<synthetic>`-style models with nonzero usage get tallied into "Unpriced models" noise. | Exact-or-dash-suffix matching; skip `<...>` models in the unknown tally (D3). | T2 |
| F3 | MED | architect⇄execute contract drift: execute's loop consumes phase-end markers and independence markers that architect's TASKS.md spec never tells Fable to emit; and the task `model` field vs. the sonnet-pinned implementer agent is unresolved — an `opus` task dispatched to the implementer would silently run on sonnet. Confirmed by reading both SKILL.md files side by side. | Mirror the D5 contract into both skills. | T4 |
| F4 | LOW | `skills/cost-report/SKILL.md`'s command `python3 ../../bin/cost_report.py` is not runnable verbatim (relative to CWD, not SKILL.md); `skills/setup/SKILL.md`'s `<abs-path>` is ambiguously defined (used both as script path and as its parent dir). | `${CLAUDE_PLUGIN_ROOT}` per D6; define `<abs-path>` precisely; keep settings.json literal-path rule. | T5 |
| F5 | LOW | `README.md` Install section predates `.claude-plugin/marketplace.json` (added this session): it leads with `claude --plugin-dir` (a real flag — confirmed via `claude --help` — but session-scoped) and says "or install from a marketplace once published", when the repo already IS a local marketplace. | Document the marketplace install as primary; keep `--plugin-dir` as the session-only dev option. | T7 |
| F6 | LOW | Drift-prone standalone literals in skills (violates D1): `skills/route/SKILL.md` hardcodes "Intro pricing until 2026-08-31"; `skills/fable-check/SKILL.md` hardcodes "2× Opus 4.8 and ~3.3× Sonnet 5" ratios and a "currently `claude-fable-5[1m]` at `xhigh`" claim about the user's live settings that will silently go stale. | Rephrase to derive from pricing.json / make the settings claim conditional; also apply D6 paths to these two skills. | T6 |
| F7 | LOW | Setup skill's smoke test (step 1) uses a sample payload without `rate_limits`, so the one field the skill's own description headlines ("rate-limit burn") is never exercised at setup time. | Extend the sample JSON with `rate_limits`. | T5 |

## Non-issues (investigated and dismissed — do NOT "fix" these)

- **Statusline rate-limit rendering**: `bin/statusline.py` DOES render 5h/7d burn when
  `rate_limits.five_hour/seven_day.used_percentage` are present in stdin (confirmed by piping a
  payload with those fields: output included `5h 63% · 7d 22%`). Script and docs agree; the
  original suspicion came from testing with a payload lacking the fields.
- **Historical model pricing**: `claude-opus-4-7` and `claude-sonnet-4-6` match and price
  correctly; genuinely unknown models are tallied and reported under "Unpriced models", never
  silently dropped. Tests pin this behavior (T3).
- **pricing.json coherence**: intro-pricing window applied by record date (boundary-inclusive) in
  `rates_for`; cache multipliers and batch discount used as intended; `cache_write_multiplier_1h`
  is intentionally present-but-unused by scripts (it is estimation data for the route skill).
  No changes.
- **`--plugin-dir`**: real flag (confirmed in `claude --help`), so README isn't *wrong*, just
  incomplete → F5 is docs polish, not a bug.
- **`"mythos"` entry in `TIER_COLORS`** in statusline.py: harmless forward-compat alias; leave it.
- **Downgrade-candidate token measure** excludes cache reads by design (footprint = new
  input + output + cache writes, with the tool-call ceiling as backstop); leave it.

---

## Risks and tripwires

- **Skill files are live behavior.** Editing SKILL.md wording changes what the installed plugin
  does. Make ONLY the pinned edits in each brief. If a change appears to require restructuring a
  skill beyond its brief, STOP and mark the task blocked — do not improvise.
- **T1 and T2 touch the same file** (`bin/cost_report.py`). They are serialized (T2 depends on
  T1). Never run them in parallel.
- **Test import mechanics**: `bin/` is not a package; tests must importlib-load by absolute path
  computed from the test file's own location. If importing executes report output, something is
  wrong (main is `__main__`-guarded) — stop and report rather than papering over.
- **`${CLAUDE_PLUGIN_ROOT}` boundary**: it exists for plugin-executed content, NOT inside the
  user's `~/.claude/settings.json` statusLine command. If an executor is tempted to put the env
  var into the settings block in the setup skill, that is the tripwire for re-reading D6.
- **Live install lag**: the plugin is installed at user scope from this repo; repo edits may not
  affect the running install until the marketplace copy refreshes. Do NOT attempt any refresh —
  just note it in the final report.
- **Verify commands assume repo root**: run them from
  `/path/to/polytropos`.
- **T7 CLI syntax**: if `claude plugin --help` shows different subcommand syntax than the brief
  expects, trust the CLI's own help text and write what it actually shows; the in-session
  `/plugin` commands are the fallback truth.
