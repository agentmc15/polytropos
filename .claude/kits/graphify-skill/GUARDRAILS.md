# graphify-skill — kit-scoped fences

These bind only while graphify-skill tasks run. The repo Invariants in CLAUDE.md apply on
top, always.

- **The real `graphify` binary is never invoked by tests, verify commands, or kit execution.**
  It is an external, user-installed tool (the `gh` precedent). `bin/graph_brief.py` only
  ever READS a graph.json handed to it; every test builds synthetic graph fixtures in
  `tempfile.TemporaryDirectory()` dirs; no task runs an extraction. The one sanctioned
  human-run path is the skill at user invocation, and even there the local-only subcommand
  law below applies.
- **Local-only subcommand law.** The skill may prescribe only the offline set: `update`,
  `cluster-only --no-label --no-viz`, `explain`, `god-nodes`, `affected`, `path`, `query`,
  `tree`, `diagnose`. It must never prescribe `label`, any `--backend`/`--model` flag,
  `add`, `clone`, `watch`, `install`/`uninstall`, or the MCP server without the user's
  explicit opt-in in that conversation — those are network, spend, daemon, or
  config-writing surfaces.
- **Never vendor, never auto-install.** No graphify code, no dependency, no requirements
  file enters this repo (stdlib-only law is absolute). `uv tool install graphifyy` is
  printed as the user's command, never executed by any task, script, or skill.
- **No network anywhere in this kit** — engine, tests, demo, and verify commands are all
  offline by construction; the source-introspection test pins `subprocess` and `urllib`
  out of the engine entirely.
- **Honesty features are load-bearing, not decoration.** The tests/-excluded hub list, the
  low-cross-file-ratio warning (dynamic loaders invisible to AST extraction), the
  confidence mix, and the absence-is-not-failure exit-0 path are the product — softening,
  hiding, or dropping any of them is a defect even with green tests. Every strength claim
  in the skill must trace to PLAN.md's measured Evidence section.
- **Format-drift posture.** graphifyy is v0.9: graph_brief tolerates missing keys
  (`.get`, `(none)` buckets, `edges` alias for `links`) and fails with a one-line
  named-expectation message, never a traceback. Tests pin only the keys PLAN D2 lists.
- **`/graphify-out/` and every graph artifact stay out of git** (root-anchored ignore,
  T4). graph.json measured relative-path-clean on this repo; GRAPH_REPORT.md and
  graph.html are NOT certified clean — local-only, and anything graph-derived gets a scrub
  check before leaving this machine.
- **T5's architect edit is additive-only** — zero deletions or modifications to existing
  lines in `skills/architect/SKILL.md`, and the architect/execute shared kit contract must
  be re-checked in BOTH files after the edit.
