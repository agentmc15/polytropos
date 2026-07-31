# context-weight — kit guardrails

Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md;
the full fence with rationale is PLAN.md's OUT-OF-SCOPE section — read both before any task.

  For `context-weight` specifically: NEVER invoke the real `copilot`/`codex`/`claude` CLI
  from any task, test, or verify command, and every ingestion path is STRICTLY read-only —
  `.jsonl` and named text files only, never a `*.db`/SQLite open, never a write under
  `~/.claude`/`~/.codex`/`~/.copilot` or anywhere outside this repo and temp dirs; every
  test/verify overrides the home seams (`--projects-dir`/`--codex-home`/`--copilot-home`/
  `--project`) with temp fixtures and `Path.home()` count in `tests/test_context_weight.py`
  is ZERO (module-level `DEFAULT_*` in the engine are the only sanctioned uses). Dollars come
  ONLY from measured usage tokens priced through that harness's own pricing file via the
  reused `cr.price` / `codex_usage.price_tokens` / `copilot_usage.price_tokens` — estimated
  (byte-derived) tokens are NEVER priced, every estimate carries the `est.` label, the three
  harnesses' dollars NEVER merge into one total, and the `audit` subcommand shows tokens
  only. Fidelity is a ladder, never a fabrication: Copilot gets NO growth curve and Codex
  gets NO content attribution — their verbatim not-available lines are pinned in PLAN.md D3
  and must appear exactly. Existing parsers are reused via importlib, never re-implemented
  and never edited (`bin/cost_report.py`, `bin/session_cost.py`, `bin/codex_usage.py`,
  `bin/copilot_usage.py` are off-limits for edits); no config surface is ever re-optimized —
  the ONLY sanctioned existing-file edit in this kit is CLAUDE.md's two pinned run-lines
  (T8), and CLAUDE.md stays ≤ 16,000 bytes. Sanctioned literals: `EST_CHARS_PER_TOKEN = 4`,
  `DROP_FRACTION = 0.5`, `DEFAULT_SURFACE_BUDGET_TOKENS = 5_000`, `CW_SCHEMA_VERSION = 1`,
  tier vocabulary, and synthetic fixture values — never a price, price ratio, cache
  multiplier, or real model id (demo fixture model ids are resolved from the pricing files
  at run time). No automation that compacts/clears/dispatches; measure and advise only.
