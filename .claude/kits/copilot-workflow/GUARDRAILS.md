# copilot-workflow — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `copilot-workflow` specifically: NEVER invoke the real `copilot` CLI in any form — it
  spends real AI Credits and hits the network (every CLI flag needed is pinned in that kit's
  PLAN.md); tests stub or mock every dispatch and `--dry-run`/`--demo` are the only CLI smoke
  paths; installs go only to temp `--copilot-home` dirs; the aesop clone is session-scoped
  reference material that may be absent — every aesop fact is pinned in the briefs (commit
  5506617); `bin/harness_select.py` is the one existing script that kit may extend; no edits
  to either pricing file, no new Claude Code skills, no Phase-3 items (aesop compile
  round-trip, cost visibility).
