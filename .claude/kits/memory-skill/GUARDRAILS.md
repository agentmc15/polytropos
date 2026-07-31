# memory-skill — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `memory-skill` specifically: the memory store is gitignored USER DATA — the
  root-anchored `/memory/` entry lands in `.gitignore` as its own independent task (the
  leading slash is load-bearing: an unanchored pattern would also ignore `skills/memory/`),
  no fact file is ever committed, and no test/verify ever reads or writes a real store
  (temp `--memory-dir` fixtures with an explicit `--now`, always; zero `Path.home()` in any
  new file — the runtime default store derives from the plugin root like `journal/`);
  recall is PULL-only and budget-capped — no hook, no settings wiring, no session-start or
  per-turn auto-injection, `bin/memory_recall.py` is strictly read-only over the store (its
  `--demo` writes only inside its own temp dir) and its output is capped by the pinned
  `MAX_FACTS`/`BUDGET_CHARS` constants with the relevance gate allowed to return nothing
  (empty recall exits 0 — never loosen a pinned gate/budget constant to make a test pass);
  ranking is pure-stdlib lexical (no embeddings, no vector store, no pip, no network, no
  model call — zero `subprocess` in either engine, no `urllib`/`http.client`/`socket`
  import, and `import yaml` is a fence violation: the flat `key: value` frontmatter grammar
  is the schema); the feature prices NOTHING — no pricing file is read, imported, or edited
  and no price or real model id appears in any new file; `memory_recall.py` reuses
  `memory_store.py` via importlib read-only, never re-implementing the schema functions,
  and no pre-existing `bin/` or `tests/` file is edited; `skills/memory/` is the ONE
  sanctioned addition under `skills/` (existing skills, the shared architect/execute kit
  contract, `.claude-plugin/`, `copilot/`, `codex/`, and the completed kits stay
  byte-untouched — cross-harness memory parity is a FUTURE kit, mirroring how
  `harness-parity` followed `codex-harness`); the personal memory system under
  `~/.claude-personal/` is reference-only and never read at runtime, written, or touched;
  sanctioned edit targets are ONLY `.gitignore` (the pinned two-line append) plus the six
  new files (`bin/memory_store.py`, `bin/memory_recall.py`, `tests/test_memory_store.py`,
  `tests/test_memory_recall.py`, `skills/memory/SKILL.md`, `docs/MEMORY-SKILL.md`) —
  CLAUDE.md and README.md are NOT executor edit targets (the architect pre-made CLAUDE.md's
  run-lines, the store invariant, and this fence); no commit, no push.
