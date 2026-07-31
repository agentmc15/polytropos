# daily-journal — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `daily-journal` specifically: ingestion is STRICTLY read-only — the journal scripts
  target `~/.claude/projects`, `~/.copilot/session-state`, and `~/.codex` at runtime only;
  during execution every test/verify uses synthetic fixtures in temp dirs
  (`--claude-projects`/`--copilot-home`/`--codex-home`/`--journal-dir`/`--launch-agents-dir`
  always overridden; `Path.home()` only in the four pinned runtime-default constants, never
  tests); never open a `*.db`/SQLite file (JSONL only — Cursor/VS Code are deferred stubs);
  never invoke a real `claude`/`copilot`/`codex` CLI or `launchctl` from tests or verify
  commands — the summarizer's `claude -p` dispatch is injectable, mocked in tests, and
  `--dry-run` prints prompts and spawns nothing; journal output + inbox live under gitignored
  `journal/` and tests write journals only to temp dirs; no Codex prices invented (counted,
  unpriced); existing bin scripts are imported read-only, never edited; no edits to either
  pricing file; `skills/journal/` is the ONE sanctioned addition under `skills/`; no
  Graph/MCP/OAuth/network work (deferred by design).
