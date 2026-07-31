# PLAN — next-day-runbook

autonomy: advisory

Layer a **next-day runbook** on the v2 daily journal (`bin/journal_*.py`, kits `daily-journal`
+ `journal-augment`). The user explicitly TABLED the scheduler: there is NO automation, NO
unattended dispatch, NO launchd/pmset/cron work anywhere in this kit. Instead, three
user-invoked capabilities:

1. **Richly detailed, actionable task cards.** Each planned next-day task is a card with a
   concrete "what to do and how to do it" — a deterministic structural seed (exact kit paths,
   `/polytropos:execute <slug>`, `git status` for WIP, the inbox line verbatim) that the
   model then enriches IN-SESSION into 2–6 concrete numbered steps via a pinned prompt. Never
   a vague `<task>` placeholder.
2. **Ideal-harness recommendation + all-three how-to.** Every card names a deterministic
   *ideal* harness (Claude Code / Copilot CLI / Codex CLI) with a one-line WHY, AND carries a
   ready-to-paste invocation for ALL THREE harnesses — commands composed ONLY from
   `journal_advisor.build_harness_signal`'s `command_template`s with the recommended model id
   substituted, plus that signal's cost estimates (Codex figures stay labeled API-equivalent
   proxies, never a bill). Nothing is invented; the advisor is reused read-only.
3. **Date-targeted, checkable plan with carry-forward.** Planned tasks persist to a dated,
   checkable store under gitignored `journal/plan/`. On the day a task is due, `check` lists
   it (plus overdue items); `done`/`defer` mark it off or move it; incomplete tasks roll
   forward into the next build. A `seed.md` file lets the user hand-add tasks on quiet days.

Everything is user-invoked. The new script generates command TEXT the user copy-pastes — it
never spawns a harness, a model, or any subprocess at all.

## Goal — "done" is checkable

- `python3 -m unittest discover -s tests -v` fully green, with ALL pre-existing journal test
  files byte-untouched (`git diff --quiet` on each of `tests/test_journal_sources.py`,
  `test_journal_collect.py`, `test_journal_summarize.py`, `test_journal_schedule.py`,
  `test_journal_codex_augment.py`, `test_journal_askpack.py`, `test_journal_advisor.py`) plus
  ONE new test file: `tests/test_journal_plan.py`.
- In a temp `--journal-dir`: `python3 bin/journal_plan.py build --date <d> --utc
  --journal-dir <tmp>` writes ONLY `<tmp>/plan/<d+1>.md` with the pinned H1/card grammar,
  every card carrying a `**What/How:**` seed, an `- ideal:` line, and three per-harness
  command lines whose model ids are derived from the pricing files at run time; the codex
  line contains `API-equivalent — not a bill`; two identical builds produce identical bytes.
- `check` classifies due-today vs overdue with latest-occurrence dedup across dated files;
  `done` flips a card's checkbox; `defer --to <date>` adds a `deferred-to:` line; unchecked,
  undeferred cards from older files carry forward into a later `build` with `first-planned:`
  preserved; a rebuild of an existing date preserves checkboxes, `deferred-to:`, ids, and
  (possibly model-enriched) `**What/How:**` bodies byte-for-byte while refreshing only the
  `**Harness:**` blocks; no card is ever silently dropped.
- `prompt` prints the pinned enrichment prompt (and spawns nothing); `bin/journal_plan.py`
  contains zero `subprocess`, zero `Path.home()`, zero network primitives, zero sqlite.
- `skills/journal/SKILL.md` documents the runbook flow BODY-only (frontmatter byte-identical
  to HEAD); `docs/NEXT-DAY-RUNBOOK.md` exists; `docs/DAILY-JOURNAL.md` carries the pinned
  pointer paragraph; CLAUDE.md already carries the architect's pinned insertions and is NOT
  touched by any task.
- `git status` shows changes ONLY to the sanctioned targets (see fence).

## Repo facts (verified by the architect — trust these; re-read the file only if an anchor is missing)

- **Advisor** `bin/journal_advisor.py` (REUSE READ-ONLY, never edit):
  `build_harness_signal(reports, pricing_claude, pricing_copilot, pricing_codex,
  profiles=ADVISOR_PROFILES, cache_hit=ADVISOR_CACHE_HIT) -> dict` returning exactly
  `{"advisory": True, "note": ADVISORY_NOTE, "profiles": ["S","M"], "cache_hit": 0.8,
  "harnesses": {...}, "notes": [...]}`. `harnesses` is keyed exactly `claude_code`,
  `copilot_cli`, `codex_cli`; each entry carries `available_today`, `sessions_today`,
  `usd_today`, `billing`, `command_template`, `est` (plus `aic_today` on copilot_cli and
  `proxy_today` on codex_cli). `est` is `None` when that harness's pricing dict is None,
  else `{profile: {"cheap": entry|None, "mid": entry|None}}` for profiles `("S","M")`.
  Slot entries: claude `{"model", "usd_est"}`; copilot `{"model", "usd_est", "aic_est"}`;
  codex `{"model", "usd_api_equivalent", "billed_usd": None}`. `COMMAND_TEMPLATES` are
  exactly `claude_code: 'claude -p --model {model} "<task>"'`,
  `copilot_cli: 'copilot --model {model} -p "<task>"'`,
  `codex_cli: 'codex exec --model {model} --full-auto "<task>"'` — fill `{model}` AND the
  `<task>` placeholder; never invent a flag. `reports` may be `{}` (every harness degrades
  to `available_today: False` with estimates still computed from the pricing dicts).
- **Pricing loaders** (reuse read-only): `cost_report.load_pricing()` → `data/pricing.json`
  dict; `copilot_usage.load_pricing()` → `data/pricing.copilot.json`;
  `codex_usage.load_pricing()` → `data/pricing.codex.json`. `bin/journal_collect.py` loads
  all three exactly this way and passes the dicts to the advisor — copy that pattern.
  Claude models carry `tier` ∈ haiku|sonnet|opus|frontier; all three files have
  `task_profiles` keys XS/S/M/L/XL. GPT-5.6 ids are BEST-EFFORT — **never a literal in code
  or tests**; every model id in a fixture or assertion is computed from a pricing file at
  run time.
- **Digest** (`journal/<date>/digest.json`, written by `bin/journal_collect.py` — NOT
  edited by this kit): `signals.kit_tasks` is a list of
  `{"kit", "id", "title", "status", "model"}` (open tasks only; `model` is a tier word like
  `sonnet` or None); `signals.inbox` is `{"present", "path", "items": [str], "truncated"}`;
  `signals.wip` is a list of `{"repo", "branch", "dirty_files", "untracked"}`;
  `sources` is the adapter-report mapping `build_harness_signal` takes as `reports`.
- **Inbox grammar** (`journal_collect.read_inbox` — parity for seed.md): skip blank lines
  and lines starting `#`; strip ONE leading `- `/`* `/`[ ] ` marker; cap items.
- **The `_load` importlib pattern** (copy the 6-line helper from `bin/journal_collect.py`):
  `importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent /
  f"{name}.py")` → `module_from_spec` → `exec_module`.
- **Date helper precedent**: `journal_summarize._next_date(date_str)` does
  `date.fromisoformat(...) + timedelta(days=1)` (month/year rollover safe);
  `_resolve_date_str(date_arg, utc)` validates `--date` and resolves today (UTC when
  `--utc`). Copy both semantics into the new script (do not import the summarizer).
- **Generator precedent** `bin/journal_askpack.py`: pure builder + renderer + a CLI whose
  ONLY write is one file under `<journal-dir>/...`; zero `Path.home()`, zero subprocess;
  `PLUGIN_ROOT = Path(__file__).resolve().parent.parent` for defaults.
- **Snapshot-dir safety precedent** (`routing_scorecard.write_snapshot`): validate the date
  grammar BEFORE composing an output path so nothing can escape the store dir.
- **Frozen tests**: the seven pre-existing `tests/test_journal_*.py` files are never edited.
  `tests/test_journal_askpack.py` shows the house style for testing a pure generator
  (importlib-load by absolute path, temp dirs, drive `main(argv)` in-process, determinism
  by comparing file bytes).
- Suite conventions: stdlib `unittest`; every root flag overridden to `tempfile` dirs;
  `--utc` wherever day membership matters; verify form
  `python3 -m unittest discover -s tests -p '<file>.py'` — NEVER the dotted-module form
  (broken on this machine). Paths via `Path(__file__).resolve()`, never `$PWD`. No
  `/private/tmp/` path in any deliverable.

## Architecture & key decisions

- **D1 — The store is one markdown file per DUE date: `journal/plan/<YYYY-MM-DD>.md`.**
  Flat text (the journal's JSONL/flat-text invariant), human-editable (the user can check a
  box by hand) AND machine-parseable (a pinned card grammar with a parse/render round-trip),
  and date-named so "check the tasks on the day they are due" falls out of the filename —
  the `journal/<date>/` precedent. Gitignored automatically (lives under `journal/`). File
  shape (pinned):

  ```
  # Runbook — <due-date>

  - schema: 1
  - built-from: digest <as-of-date>        (or: - built-from: no digest)

  Advisory only — nothing here auto-executes; every command below is ready-to-paste for a human to run.

  ## Tasks

  <cards>

  ## Notes                                  (section present only when notes exist)
  - <honest degradation notes>
  ```

  Card grammar (pinned; `### [x]` when done):

  ```
  ### [ ] R1 — <title>

  - source: <token>
  - due: <YYYY-MM-DD>
  - first-planned: <YYYY-MM-DD>
  - model-hint: <haiku|sonnet|opus|none>
  - deferred-to: <YYYY-MM-DD>               (line present only when deferred)

  **What/How:**
  1. <numbered steps>

  **Harness:**
  - ideal: <harness> — <reason>
  - claude_code (<model-id>, est M ~$<x>): `claude -p --model <model-id> "<title>"`
  - copilot_cli (<model-id>, est M ~$<x> / ~<y> AIC): `copilot --model <model-id> -p "<title>"`
  - codex_cli (<model-id>, est M ~$<x> API-equivalent — not a bill): `codex exec --model <model-id> --full-auto "<title>"`
  ```

  Source tokens: `kit:<kit>/<id>`, `inbox`, `wip:<repo>`, `seed`. The CHECKBOX is
  authoritative for done; `deferred-to:` (field line) marks deferral. Card ids `R1..Rn` are
  file-scoped and STABLE (never renumbered by a rebuild). No wall-clock timestamp anywhere
  in the file body — builds are deterministic given the same inputs (test: identical bytes).
- **D2 — Deterministic-signals-then-prose is preserved; enrichment is in-session and the
  script spawns NOTHING.** The generator writes deterministic structural `**What/How:**`
  seeds (kit cards: open the kit's TASKS.md brief, resume with
  `/polytropos:execute <kit>`, run the verify yourself; wip cards: `git status` the
  repo, commit/stash/continue; inbox/seed cards: the user's line verbatim + a finish step).
  The model-authored deep detail comes from a pinned enrichment prompt
  (`build_enrich_prompt`, printed by the `prompt` subcommand) that the journal SKILL runs
  IN-SESSION — the same "write it yourself in this session" flow the summaries already use.
  `bin/journal_plan.py` therefore contains ZERO `subprocess` (stronger than the summarizer:
  there is no injectable runner because there is no dispatch at all — the askpack stance).
- **D3 — All-three-harness commands and costs come ONLY from the advisor, reused
  read-only.** The CLI loads the three pricing dicts via `cr`/`cu`/`cxu` `load_pricing()`
  (the `journal_collect.py` pattern), reads the as-of digest's `sources` when present (else
  `{}`), and calls `ja.build_harness_signal(sources, pc, pco, pcx)` — one code path,
  usage-enriched when a digest exists, estimate-only when not. Slot choice per card:
  `TIER_TO_SLOT = {"haiku": "cheap", "sonnet": "mid", "opus": "mid"}` applied to the card's
  `model-hint` (default `mid`); an `opus` hint adds a note that the advisor's estimate
  table covers cheap/mid by design. Commands: the harness's `command_template` with
  `{model}` ← the slot entry's model id and `<task>` ← the card title with `"` and
  backticks stripped. Estimates render from the slot entry for `EST_PROFILE = "M"`:
  claude `est M ~$<usd_est>`; copilot `est M ~$<usd_est> / ~<aic_est> AIC`; codex
  `est M ~$<usd_api_equivalent> API-equivalent — not a bill`. A missing slot/est → the line
  reads `est n/a — pricing or tier unavailable` and carries NO command (an unknown model id
  is never guessed); an advisor crash or all-None pricing degrades the whole block to one
  honest line `- harness signals unavailable — run journal_collect.py, then rebuild` —
  NEVER a fabricated figure. The three pricing files never merge; rates never cross
  harnesses (the advisor already guarantees this — do not post-process its numbers).
- **D4 — The ideal pick is a pinned, honest, deterministic policy (`pick_ideal`).**
  (i) `source` starts `kit:` → `claude_code`, reason "kit tasks run via
  /polytropos:execute in Claude Code" (structural fact: kits are Claude Code
  execution kits). (ii) Else compare the card-slot `usd_est` of claude_code vs copilot_cli
  for profile M — lower wins, reason names both figures and states that codex is excluded
  from the cost ranking because its figure is an API-equivalent proxy, not a bill.
  (iii) Only one real-dollar estimate available → that harness. (iv) None → `claude_code`,
  reason "default — no estimates available". `codex_cli` is NEVER the deterministic ideal
  (a proxy cannot be cost-ranked against bills — the not-a-bill invariant made structural);
  its command is still on every card and the in-session enrichment or the user may choose
  it. The pick is advisory prose in a text file; nothing acts on it.
- **D5 — Check / carry-forward mechanics are read-only scans with latest-occurrence
  dedup.** `check --date <today>`: scan every `<plan-dir>/*.md` whose stem matches
  `^\d{4}-\d{2}-\d{2}$` (skip + note anything else), parse all cards, dedup by key keeping
  the occurrence from the LATEST file, compute `effective_due = deferred-to or file date`,
  and report unchecked cards with `effective_due <= today` — `DUE <date>` vs
  `OVERDUE since <date>`, each with its `[<file-date>/<id>]` handle so `done`/`defer` can
  target it. Empty store → an honest "no runbook cards due" line, exit 0. Carry-forward at
  `build --for <T>`: same scan over stems `< T`; collect unchecked cards whose
  `deferred-to` is absent or `<= T`; latest occurrence wins; carried cards keep their
  `**What/How:**` body, `first-planned:`, `model-hint:`, and `source:`, and take `due: T`.
  Historical files are NEVER rewritten by build or check — dedup-by-key is what prevents
  double-reporting. Dedup key: the `source` token when it starts `kit:` or `wip:`; else the
  casefolded, whitespace-collapsed title. ISO zero-padded date strings compare correctly as
  strings; the stem regex enforces the zero padding.
- **D6 — Rebuild merge preserves the user's state absolutely.** When
  `<plan-dir>/<for-date>.md` already exists, `build` parses it and merges: an existing card
  keeps its id, position, checkbox, `deferred-to:`, `first-planned:`, and its ENTIRE
  `**What/How:**` body byte-for-byte (it may be model-enriched — clobbering it destroys
  paid work); only its `**Harness:**` block is refreshed. Existing cards with no match in
  the new computation are PRESERVED verbatim (a kit task that closed overnight still shows
  so the user can check it off — never silently dropped). New cards append with the next
  free `Rn` id, in pinned order: carried (oldest `first-planned` first), then kit_tasks
  (digest order), then wip, then inbox, then seeds. `done <id>` and `defer <id> --to <d>`
  are the ONLY other mutations, each touching exactly one card in one file.
- **D7 — Seeding: `journal/plan/seed.md`, inbox-grammar parity, never consumed
  destructively.** Plain lines (blank/`#` skipped, one leading `- `/`* `/`[ ] ` marker
  stripped — exactly `read_inbox`'s rules, re-stated locally as `SEED_MARKERS`); each line
  becomes a `seed`-source card at the next `build`. seed.md is read-only input: never
  truncated, rewritten, or deleted (dedup-by-title is what prevents duplicates across
  builds). This is the quiet-day path: when kit_tasks/wip/inbox are thin the user hand-adds
  tomorrow's tasks here (or straight into the plan file — it is theirs to edit).
- **D8 — Tests, surfaces, guardrails.** One new test file `tests/test_journal_plan.py`
  (unit tests drive the pure functions with synthetic digests/signals; CLI end-to-end
  tests use temp `--journal-dir` and let the script open the real pricing files —
  sanctioned config reuse — deriving every asserted model id at run time). Surfaces:
  `skills/journal/SKILL.md` gains one BODY-only `## Next-day runbook` section;
  `docs/NEXT-DAY-RUNBOOK.md` is the new user doc; `docs/DAILY-JOURNAL.md` gains one pinned
  pointer paragraph. CLAUDE.md's run-line and fence block were pre-made by the architect —
  no task edits CLAUDE.md or README.md.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Build any scheduler or automation.** No launchd/`StartCalendarInterval`, no `pmset` or
  wake-from-sleep work, no cron, no daemon, no auto-run, no `launchctl` anywhere.
  `bin/journal_schedule.py` stays byte-untouched and the runbook is never wired into the
  scheduled nightly run. Everything this kit ships is user-invoked.
- **Dispatch anything.** `bin/journal_plan.py` must contain ZERO `subprocess` (not even an
  injectable runner — generating command TEXT is the feature; spawning a
  `claude`/`copilot`/`codex` binary is forbidden). No test or verify command may invoke a
  real CLI or `launchctl`.
- **Add network, OAuth, MCP, tokens, or secrets in any form.** No
  `urllib`/`http.client`/`socket` import in any new or edited file. No `sqlite3` import or
  `*.db` open anywhere — flat text and JSON only.
- **Read or write any home directory.** The new script takes NO home-dir flag at all; its
  inputs are `<journal-dir>` and the committed `data/` pricing files; its only writes are
  `<journal-dir>/plan/<YYYY-MM-DD>.md` (build/done/defer — validate the date grammar before
  composing any output path). ZERO `Path.home()` in `bin/journal_plan.py` and
  `tests/test_journal_plan.py` — the repo budget stays exactly 3 in
  `bin/journal_collect.py` + 1 in `bin/journal_schedule.py`. Every test/verify uses temp
  `--journal-dir` dirs and `--utc` where day membership matters.
- **Edit the reused scripts**: `bin/journal_advisor.py`, `bin/journal_collect.py`,
  `bin/journal_summarize.py`, `bin/journal_sources.py`, `bin/journal_askpack.py`,
  `bin/journal_schedule.py`, `bin/cost_report.py`, `bin/copilot_usage.py`,
  `bin/codex_usage.py`, `bin/copilot_pricing.py`, `bin/codex_pricing.py` — importlib
  read-only. Never re-implement `build_harness_signal` or the estimators; never
  re-implement the three loaders — call them. Never post-process advisor numbers into new
  derived figures beyond formatting (D3).
- **Edit any pre-existing test file.** All seven `tests/test_journal_*.py` files stay
  byte-untouched; new tests go ONLY in `tests/test_journal_plan.py`.
- **Couple to the digest schema.** `bin/journal_collect.py` is not edited; no new `signals`
  key; the digest is a read-only optional INPUT to the runbook, nothing more.
- **Fabricate.** Absent pricing/slots/digest → `est n/a`, the one-line harness-unavailable
  degradation, or an honest note — never a zeroed or invented figure, never an unlabeled
  Codex dollar, never `codex_cli` as the deterministic ideal.
- **Hardcode prices, price ratios, plan facts, or real model ids.** GPT-5.6 ids and Claude
  model ids never appear as literals in code or tests — compute from the pricing files at
  run time. Sanctioned literals: tier vocabulary (`haiku|sonnet|opus`),
  `TIER_TO_SLOT`, `EST_PROFILE = "M"`, `PLAN_SCHEMA = 1`, the `plan` dir name and
  `seed.md`, the date-stem regex, `SEED_MARKERS`, `MAX_PLAN_CARDS = 100`, pinned
  heading/note/prompt/reason text, est format strings, and synthetic fixture ids/values in
  tests.
- **Touch anything outside the sanctioned targets.** Existing-file edits are ONLY
  `skills/journal/SKILL.md` (T4, BODY-only — frontmatter byte-intact; the plugin is LIVE)
  and `docs/DAILY-JOURNAL.md` (T5, one pinned pointer paragraph). New files are ONLY
  `bin/journal_plan.py`, `tests/test_journal_plan.py`, `docs/NEXT-DAY-RUNBOOK.md`.
  CLAUDE.md and README.md are NOT executor edit targets (the architect pre-made CLAUDE.md's
  run-line and fence insertions). No new skills, no `.gitignore` change needed
  (`/journal/` already covers `journal/plan/`), no edits to any pricing file, nothing under
  `.claude-plugin/`, `copilot/`, `codex/`, or the completed kits. Do not touch the stray
  untracked `docs/HOW-IT-WORKS 2.md`.
- **Build the deferred work** (see below). **Commit or push.**

## Risks & tripwires

- **A card that implies auto-execution — the #1 semantic risk.** The runbook PREPARES and
  TRACKS; the user runs. TRIPWIRES: any `subprocess` in `bin/journal_plan.py`; wording that
  says the tool "will run" something; the pinned advisory line missing from a rendered
  file; the enrichment prompt not stating "nothing here auto-executes".
- **Codex proxy read as a bill.** TRIPWIRES: a codex est line without
  `API-equivalent — not a bill`; codex included in the ideal-pick cost ranking; a codex
  figure summed with claude/copilot figures anywhere.
- **Clobbering user state on rebuild.** The What/How body may be model-enriched (paid
  work) and checkboxes are the user's record. TRIPWIRES: a rebuild that renumbers ids,
  resets a checkbox, drops `deferred-to:`/`first-planned:`, regenerates a matched card's
  What/How, or silently drops an unmatched existing card.
- **Double-reporting carried cards.** A card unchecked in Monday's file and carried into
  Tuesday's exists in two files. TRIPWIRE: `check` or `build` counting it twice — the
  latest-occurrence dedup rule (D5) is the guard; test it explicitly.
- **Fabrication under degradation.** TRIPWIRES: an est rendered when the slot is None; a
  model id guessed when est is missing (the command line must be omitted, not filled with
  `{model}` or an invented id); a zeroed figure standing in for an unknown.
- **Date/ordering edge cases.** Month/year rollover (use `date.fromisoformat` +
  `timedelta` — the `_next_date` precedent, never string arithmetic); non-date files in
  `plan/` (skip + note via the stem regex); a `--for`/`--to` date that fails the grammar
  must be rejected BEFORE any path is composed (the `write_snapshot` precedent — nothing
  escapes the plan dir).
- **Seed destruction.** TRIPWIRE: any write to `seed.md` — it is user input, read-only to
  the tool.
- **Command-injection-ish titles.** Titles flow into ready-to-paste shell lines. TRIPWIRE:
  a title's `"` or backtick surviving into the command text (strip both — pinned rule).
- **Hardcoded model ids.** TRIPWIRE: any `gpt-5` or `claude-` model-id literal in the new
  code, tests, or docs (run-time derivation only).
- **Suite/paths quirks.** `python3 -m unittest discover -s tests [-p '<file>.py']` — never
  the dotted-module form. No `/private/tmp/` path in any deliverable.

## Still deferred after this kit (by user choice or design — not built)

1. **The scheduler itself** — tabled BY THE USER ("lets go ahead and not do the
   scheduling"). No launchd/pmset/cron/daemon work; revisit only as a new architect-planned
   kit if the user re-opens it.
2. **Auto-dispatch of planned tasks** (the runbook executing its own commands) — advisory
   by design, same stance as the harness plan.
3. **Digest coupling** — surfacing plan-due cards as a `signals` family in the digest
   would need a `journal_collect.py` edit; `check` covers the need today.
4. **Weekly rollups** across dated plans/digests — unchanged from daily-journal.
5. **Graph/OAuth/MCP connectors** — unchanged; the ask-the-tools pack remains the offline
   stand-in.
