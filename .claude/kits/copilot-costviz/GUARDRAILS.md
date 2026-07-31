# copilot-costviz — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `copilot-costviz` specifically: NEVER invoke the real `copilot` CLI in any form — the
  events.jsonl usage surface is pinned in that kit's PLAN.md (observed on Copilot CLI
  v1.0.68); during execution nothing reads OR writes the real `~/.copilot` —
  `bin/copilot_usage.py` targets it read-only at runtime only, and every test/verify uses
  synthetic `events.jsonl` fixtures in temp `--copilot-home`/`--session-dir` dirs; never open
  the `*.db` session stores; `bin/copilot_pricing.py` is the one existing script that kit may
  extend (`--pool-aic`, additive so `bin/copilot_ralph.py` stays untouched) and
  `tests/test_copilot_pricing.py` the one existing test file; `bin/cost_report.py` is a
  read-only model; the aesop compile round-trip is a proposal doc only
  (`docs/AESOP-COMPILE-PROPOSAL.md`, facts pinned at aesop@5506617) — no aesop-repo work, no
  node, no Ralph per-tick live-cost scraper; no edits to either pricing file, no new skills.
