# journal-augment — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `journal-augment` specifically: the journal's OFFLINE invariant is absolute — the
  ask-the-tools feature is PURE TEXT GENERATION (ready-to-paste prompts the user runs in
  their own Copilot Studio / Teams / Outlook, pasting bullet results into
  `journal/inbox.md`); no Graph/OAuth/MCP/network/secrets in any form and no
  `urllib`/`http.client`/`socket` import in any new or edited file; `bin/codex_usage.py`,
  `bin/codex_pricing.py`, `bin/copilot_pricing.py`, `bin/cost_report.py`,
  `bin/copilot_usage.py`, and `bin/copilot_execute.py` are reused read-only via importlib
  — never edited — with Codex tokens priced through `codex_usage.parse_rollout`/
  `match_model`/`price_tokens` and `PROXY_DISCLAIMER` referenced verbatim, never retyped
  or re-implemented; Codex proxy honesty is absolute — the codex report keeps
  `priced: false` and `usd: null` on every path, the proxy lives ONLY in
  `sources.codex_cli.extra.codex_proxy` with `billed_usd: null`, it never enters
  `totals.usd_priced` or any billed figure, `build_digest` stays untouched, and the frozen
  report/digest key sets stay exact (everything additive rides inside `extra` values,
  `notes`, and `signals` — `harness`/`harness_error` are the only new signals keys);
  `pricing_codex` is an OPTIONAL ctx key and `None` keeps `collect_codex` behavior
  test-identical; rollout reads touch ONLY the digest day's `sessions/YYYY/MM/DD` dir,
  JSONL only, never a `*.db`; the FOUR frozen journal test files
  (`tests/test_journal_{sources,collect,summarize,schedule}.py`) and
  `bin/journal_schedule.py` stay byte-untouched (new tests go ONLY in
  `tests/test_journal_codex_augment.py`, `tests/test_journal_askpack.py`, and
  `tests/test_journal_advisor.py`); the harness advisor is ADVISORY-ONLY — deterministic
  signals in `signals.harness`, nothing auto-executes, no auto-pin, no main-session model
  switching, command templates only from the repo-pinned dispatch shapes (never an
  invented CLI flag) — and the three pricing files never merge: the advisor may LOAD all
  three but never mixes rates across files, and no price or real model id is hardcoded
  anywhere new (GPT-5.6 ids NEVER appear as literals in code or tests — computed from
  `data/pricing.codex.json` at run time; tier/profile vocabulary, `MAX_ASK_BULLETS`,
  `ADVISOR_PROFILES`/`ADVISOR_CACHE_HIT`, the pinned command templates, pinned note text,
  and synthetic fixture ids are the sanctioned literals); every test/verify uses synthetic
  fixtures in temp dirs with every root flag overridden and `--utc`, zero `Path.home()`
  beyond the four pre-existing constants (none in `bin/journal_askpack.py`,
  `bin/journal_advisor.py`, or any new test), the summarizer dispatch stays
  injectable/mocked and `--dry-run` spawns nothing; sanctioned existing-file edits are
  ONLY `bin/journal_sources.py`, `bin/journal_collect.py`, `bin/journal_summarize.py`,
  `skills/journal/SKILL.md` (BODY-only, frontmatter byte-intact), `docs/DAILY-JOURNAL.md`,
  and one pinned sentence swap each in `docs/HOW-IT-WORKS.md` + `docs/how-it-works.html`,
  with new files `bin/journal_askpack.py`, `bin/journal_advisor.py`, and the three new
  test files — CLAUDE.md and README.md are NOT executor edit targets (the architect
  pre-made CLAUDE.md's insertions); no new skills, no edits to any pricing file, no
  Copilot-/Codex-harness changes, and the deferred set stays deferred (Graph/OAuth/MCP
  connectors, Cursor/VS Code adapters, weekly rollups, auto-execution of next-day tasks).
