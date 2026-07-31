# copilot-harness — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `copilot-harness` specifically: nothing outside this repo — `~/.copilot` included
  (`bin/harness_select.py install` runs only against a temp `--copilot-home` during this kit);
  no node/npm/`aesop compile`; no edits to `data/pricing.json`, `.claude-plugin/`, `skills/`,
  or the completed kits; `data/pricing.copilot.json` is created/edited only by its own tasks;
  bundle files under `copilot/.github/` carry the `{{POLYTROPOS_ROOT}}` placeholder, never
  an absolute path; no Phase-2 features (architect/execute port, Ralph loop, lessons-loop).
