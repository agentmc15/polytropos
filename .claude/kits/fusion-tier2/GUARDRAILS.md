# fusion-tier2 — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `fusion-tier2` specifically: the architect/execute shared kit contract stays byte-intact
  — skill edits BODY-only (frontmatter untouched; the plugin is live), every pinned contract
  element survives in BOTH `skills/architect/SKILL.md` and `skills/execute/SKILL.md`, no new
  REQUIRED task field anywhere (`autonomy:` is an OPTIONAL PLAN.md line; `parse_tasks` needs
  no change); mid-kit re-routing is UPGRADE-ONLY, exactly one tier step (haiku→sonnet,
  sonnet→opus), NEVER auto-routes to frontier/Fable (the per-task evidence-carrying escalation
  valve stays the only path to Fable, its mechanism unchanged), and NEVER rewrites a TASKS.md
  `model` field — it is a runtime dispatch override logged as `reroute:` lines in NOTES.md
  (appended by the orchestrator, never by a script); the autonomy dial defaults to ADVISORY
  (print-only — nothing is auto-changed when off) and `mode=applied` auto-upgrades are capped
  by the budget guardrail; `bin/routing_scorecard.py` is extended ADDITIVELY only — existing
  flags, output shapes, the Tier-1 `--demo` numbers, and `tests/test_routing_scorecard.py`
  stay untouched and green (new tests go in `tests/test_reroute_live.py`);
  `bin/cost_report.py`, `bin/session_cost.py`, and `bin/copilot_execute.py` stay reuse-only
  via importlib, never edited; every test/verify uses synthetic kits in temp dirs
  (`--kits-dir` always overridden), never the real `~/.claude`, zero `Path.home()` in
  new/edited Python, and the `--live` path never loads pricing and rejects `--session`; no
  hardcoded prices or real model ids (tier vocabulary, the `fable`→`frontier` alias, the
  pinned live-policy constants — threshold, min-sample, budget cap — and synthetic fixtures
  are the sanctioned literals); sanctioned edit targets are ONLY the two skills,
  `bin/routing_scorecard.py`, `docs/FUSION-TIER1.md`'s Deferred pointer, and CLAUDE.md's
  pinned run-line, with new files `tests/test_reroute_live.py` and `docs/FUSION-TIER2.md`; no
  README changes, no new skills, no Copilot-side changes, no changes to
  `/route`/`/escalate`/`/fable-check`, no auto-downgrade, no scorecard-over-time aggregation,
  no main-session model switching.
