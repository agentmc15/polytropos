# fusion-tier1 — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `fusion-tier1` specifically: the architect/execute shared kit contract is the #1
  invariant — skill edits are BODY-only (YAML frontmatter untouched; the plugin is live) and
  every pinned contract element must survive in BOTH `skills/architect/SKILL.md` and
  `skills/execute/SKILL.md` (kit layout, task fields, status vocabulary, phase headings,
  `depends:`/`independent:`, the model-override rule) — no new required task field anywhere
  (warm clusters ride on existing fields plus free-text preamble hints); warm-sidekick
  guidance stays OPT-IN (`independent:` disjoint-file tasks still fan out fresh, warm
  clusters require the SAME `model` pin, the verifier is always a fresh spawn); the
  lean-driver rule never removes the run-the-verify-command-yourself invariant;
  `bin/cost_report.py`, `bin/session_cost.py`, and `bin/copilot_execute.py` are reused
  read-only via importlib — never edited; `bin/routing_scorecard.py` is read-only (`--demo`
  writes only to its own temp dir, never into a kit dir or NOTES.md) and its tests use
  synthetic fixtures in temp dirs with `--projects-dir`/`--kits-dir` always overridden —
  never the real `~/.claude`; zero `Path.home()` in the two new Python files; missing
  NOTES.md or ledger-free notes degrade to status-only output with a note, and
  zero-denominator rates render null/`n/a` — never fabricated; no edits to either pricing
  file and no hardcoded prices or model ids (tier vocabulary, the `fable`→`frontier` alias
  map, synthetic fixture values in tests, and pinned demo token VOLUMES are the sanctioned
  exceptions — demo model ids are computed from `data/pricing.json` at run time); sanctioned
  existing-file edits are ONLY the two skills, `README.md`, and CLAUDE.md's pinned T8
  run-line; no Tier-2 features (dynamic mid-kit re-routing, autonomy dial) and no
  main-session model-switch implementation (upstream-only, documented in
  `docs/FUSION-TIER1.md`); no Copilot-side changes.
