# routing-history — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `routing-history` specifically: the architect/execute shared kit contract stays
  byte-intact — skill edits BODY-only (frontmatter untouched; the plugin is live), every
  pinned contract element survives in BOTH `skills/architect/SKILL.md` and
  `skills/execute/SKILL.md` including the Tier-2 runtime-override clause verbatim, and no new
  REQUIRED task field anywhere (the `session:` line is an OPTIONAL, execute-owned NOTES.md
  line — precedent `outcome:`/`reroute:`; `parse_tasks` needs no change; the orchestrator
  records it at END of run via a READ-ONLY best-effort transcript-stem lookup and SKIPS it
  when ambiguous — never a guessed id, never a write under `~/.claude`); the /architect
  addition is ONE ADVISORY bullet (consult `--history` when choosing initial pins) — NO
  auto-pin-setting, no auto-downgrade, and the fusion re-routing/escalation semantics are
  untouched; `bin/routing_scorecard.py` is extended ADDITIVELY only — existing flags, output
  shapes, exit codes, the Tier-1 `--demo` numbers, AND the Tier-2 `--demo --live` numbers
  stay byte-stable, and `tests/test_routing_scorecard.py` + `tests/test_reroute_live.py` stay
  byte-untouched (new tests go in `tests/test_routing_history.py`); `bin/cost_report.py`,
  `bin/session_cost.py`, and `bin/copilot_execute.py` stay reuse-only via importlib, never
  edited, and history parsing/attribution reuses
  `parse_tasks`/`parse_outcomes`/`parse_reroutes`/`tier_for`/`effective_alias`/the
  `session_cost` pipeline — never re-implemented; dollars are fully OPTIONAL and degrading —
  aggregated only over kits carrying `session:` lines with a LABELED `partial`/`full`
  coverage, one `collect()` per scope (shared session ids priced once in the aggregate),
  missing transcripts noted and skipped, NEVER a fabricated or zeroed stand-in figure,
  ledger-free kits degrade to status-only, zero-denominator rates render null/`n/a`, and
  with zero `session:` lines `--history` never loads pricing; every test/verify uses
  synthetic kits and transcripts in temp dirs (`--kits-dir`/`--projects-dir` always
  overridden — never the real `~/.claude`), zero `Path.home()` in new/edited Python; no
  hardcoded prices or real model ids (tier vocabulary, the `fable`→`frontier` alias,
  `HISTORY_SCHEMA_VERSION`, and synthetic fixtures are the sanctioned literals — demo/test
  transcript ids are computed from `data/pricing.json` at run time); sanctioned edit targets
  are ONLY `bin/routing_scorecard.py`, the two skills, `docs/FUSION-TIER2.md`'s
  Still-deferred pointer, and CLAUDE.md's pinned T6 run-line, with new files
  `tests/test_routing_history.py` and `docs/ROUTING-HISTORY.md`; no README changes, no new
  skills, no Copilot-side changes, no changes to `/route`/`/escalate`/`/fable-check`, no
  per-task dollar attribution, no cross-repo or time-series aggregation, no main-session
  model switching.
