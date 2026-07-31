# next-day-runbook — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `next-day-runbook` specifically: NO scheduler and NO unattended dispatch in any form
  — the user tabled scheduling, so no launchd/`StartCalendarInterval`, `pmset`, cron,
  daemon, `launchctl`, or auto-run work anywhere (`bin/journal_schedule.py` stays
  byte-untouched and the runbook is never wired into the scheduled run);
  `bin/journal_plan.py` contains ZERO `subprocess` — generating ready-to-paste command
  TEXT is the feature, spawning a harness is forbidden, and the What/How enrichment is
  in-session via the pinned `prompt` output, never a dispatch; the journal's offline
  invariant is absolute (no network/OAuth/MCP/secrets, no `urllib`/`http.client`/`socket`
  import, flat text/JSON only, never a `*.db`/`sqlite3`); the script takes NO home-dir
  flag — its inputs are `--journal-dir` and the committed pricing files, its ONLY writes
  are `<journal-dir>/plan/<YYYY-MM-DD>.md` (date grammar validated before any output path
  is composed) under gitignored `journal/`, and `journal/plan/seed.md` is user input read
  with the inbox grammar and NEVER truncated or rewritten; harness commands and estimates
  come ONLY from `journal_advisor.build_harness_signal` with pricing dicts from the
  `cost_report`/`copilot_usage`/`codex_usage` loaders (all reused read-only via importlib
  — the advisor, the collectors/summarizer, and the three pricing files are never edited
  and rates never cross harnesses); Codex figures stay labeled API-equivalent proxies,
  never a bill, and codex_cli is NEVER cost-ranked into the deterministic ideal pick;
  absent data degrades to `est n/a`/the pinned unavailable line/an honest note — never a
  fabricated or zeroed figure, never a guessed model id; rebuilds preserve user state
  (checkboxes, `deferred-to:`, `first-planned:`, ids, enriched What/How bodies) while
  refreshing only Harness blocks, never silently drop a card, never rewrite historical
  plan files, and are byte-idempotent (no timestamps in rendered bodies); every
  test/verify uses temp `--journal-dir` dirs with `--utc` where day membership matters
  (never a real home dir), zero `Path.home()` in the new files (the budget stays 3 in
  `journal_collect.py` + 1 in `journal_schedule.py`); no hardcoded prices or real model
  ids — `claude-*`/GPT-5.6 ids never appear as literals in code, tests, or the new doc
  (tier vocabulary, `TIER_TO_SLOT`, `EST_PROFILE = "M"`, `PLAN_SCHEMA = 1`, the `plan`
  dir name and `seed.md`, the date-stem regex, `SEED_MARKERS`, `MAX_PLAN_CARDS`, pinned
  heading/note/prompt/reason text, est format strings, and synthetic fixture ids in tests
  are the sanctioned literals); ALL seven pre-existing `tests/test_journal_*.py` files
  stay byte-untouched — new tests go ONLY in `tests/test_journal_plan.py`; sanctioned
  edit targets are ONLY `skills/journal/SKILL.md` (BODY-only, frontmatter byte-intact —
  the plugin is live) and `docs/DAILY-JOURNAL.md`'s pinned pointer paragraph, with new
  files `bin/journal_plan.py`, `tests/test_journal_plan.py`, and
  `docs/NEXT-DAY-RUNBOOK.md` — CLAUDE.md and README.md are NOT executor edit targets (the
  architect pre-made CLAUDE.md's run-line and this fence); no digest/schema coupling (no
  new `signals` key, `journal_collect.py` untouched), no `.gitignore` change, no new
  skills, no Copilot-/Codex-side changes, no changes to `/route`/`/escalate`/
  `/fable-check`, and the deferred set stays deferred (the scheduler itself — tabled by
  the user, auto-dispatch of planned tasks, plan-due signals in the digest, weekly
  rollups, Graph/OAuth/MCP connectors).
