# graphify-skill — repo-graph analysis as an optional external tool

autonomy: advisory

## Goal

Adopt graphify (github.com/Graphify-Labs/graphify, installed as the `graphifyy` uv tool)
as an OPTIONAL, availability-gated repo-analysis capability: one skill
(`skills/graphify/SKILL.md`) that teaches when and how to use the external CLI locally,
plus one stdlib engine (`bin/graph_brief.py`) that reads the `graph.json` it produces and
prints an architect-grounding brief. "Done" looks like:

- `python3 bin/graph_brief.py demo` runs a synthetic smoke (no graphify binary, no real
  files) and is a CLAUDE.md run-line.
- `python3 bin/graph_brief.py brief --graph <path>` renders a repo-shape card from any
  graphify graph.json: counts, relation mix, per-directory mass, hubs (with and without
  test files), community count, confidence mix, and a cross-file call-edge ratio with an
  honest dynamic-loader-blindness warning when it is low.
- `/polytropos:graphify` gates on the binary's presence, prescribes the LOCAL-ONLY
  subcommand set, and carries this eval's measured strengths and limits.
- `/graphify-out/` is gitignored; tests never invoke the real binary; the full suite is
  green.

## Evidence (hands-on eval, 2026-08-12, graphifyy 0.9.41 on this repo's clean tree)

- `graphify update . --no-cluster`: 414 files → 8,072 nodes / 12,742 edges (CLI banner;
  the written graph.json holds 12,000 links after its own dedup — both are true, of
  different stages) in 8.4s, fully
  local (tree-sitter AST, "no LLM needed" is its own banner). `cluster-only --no-label
  --no-viz`: 682 communities in 2s. graph.json = 8.2MB networkx node-link JSON.
- **Strong:** `explain <symbol>` returned exact file:line, callers, and a `rationale_for`
  edge extracted from a docstring — instant and precise. `god-nodes`, `affected`, `path`,
  and `query --budget N` (token-capped output!) all exist and run offline.
- **Weak, measured:** `query` without LLM community labels is fuzzy-BFS — the
  "what reads pricing.json" probe surfaced test classes and doc-manifest nodes, not the
  bin/ readers. `god-nodes` on this repo is dominated by test fixtures. And
  `path harness_update → plugin_staleness` found NOTHING: this repo's
  `importlib.spec_from_file_location` sibling-loader is invisible to AST import analysis,
  so bin/'s cross-file dependency spine is absent from the graph. On normal-import repos
  (repo-bench targets) those edges are exactly what tree-sitter extracts.
- **Hygiene, measured:** graph.json carries RELATIVE paths only (0 `/Users/` hits).
  Extraction against a `git archive` clean tree keeps gitignored personal stores
  structurally out of the graph.

## Constraints and out-of-scope

- **The real `graphify` binary is NEVER invoked by tests, verify commands, or kit
  execution.** It is a user-installed external tool (the `gh` precedent): the skill checks
  availability and degrades honestly; `bin/graph_brief.py` only ever reads a graph.json
  file; every test uses synthetic fixtures in temp dirs.
- **Local-only subcommand law:** the skill may prescribe `update`, `cluster-only
  --no-label --no-viz`, `explain`, `god-nodes`, `affected`, `path`, `query`, `tree`, and
  `diagnose` — all offline. It must NOT prescribe `label`, any `--backend`/`--model`
  flag, `add <url>`, `clone`, `watch`, `install`/`uninstall`, or the MCP server without
  the user's explicit opt-in in that conversation: those are network, spend, daemon, or
  config-writing surfaces.
- **Out of scope:** vendoring graphify or any dependency (stdlib-only law is absolute);
  auto-installing it (`uv tool install` is the user's command, printed never executed);
  running extraction inside this kit's tasks; shipping the skill into copilot/codex
  bundles (Claude-side only, the harness-update precedent — no roster/manifest churn);
  committing any graphify-out/ artifact; wiring graph output into repo-bench (a future
  kit may; this one only mentions the affinity in the skill's prose).
- Stdlib-only Python, unittest only; no network anywhere.

## Architecture & key decisions

- **D1 — External-binary posture (the `gh` precedent).** graphify stays a user-installed
  CLI. Skill gates on `command -v graphify`; absence prints the install command
  (`uv tool install graphifyy`) and stops — absence is not failure. *Why:* the stdlib-only
  invariant cannot bend, and the tool's value doesn't require vendoring.
- **D2 — One stdlib reader, `bin/graph_brief.py`.** Consumes the pinned graph.json shape:
  top-level `nodes` + `links` (networkx node-link, `directed` false by default); node keys
  `id,label,norm_label,community,community_name,file_type,source_file,source_location,
  _callable,_callable_class,_origin`; link keys `source,target,relation,context,
  confidence,confidence_score,source_file,source_location,weight,_origin`; relations seen:
  `calls,contains,extends,references`. Tolerate absent keys (`.get` everywhere — the tool
  is v0.9, format may drift) and accept `edges` as an alias for `links` if present. *Why a
  reader at all:* raw graph.json is 8MB — the brief is the delegation-shaped summary that
  keeps bulk out of a session's window (context-weight PREVENT lever).
- **D3 — The brief's honesty features are the product.** Hubs are reported twice — all
  files, and excluding `source_file` under `tests/` — because the eval showed fixture
  dominance. The cross-file call-edge ratio (calls whose endpoints live in different
  source_files ÷ all calls) is computed and, when low, printed with the verbatim warning
  that dynamic loaders (importlib, plugin registries) are invisible to AST extraction and
  the graph under-represents cross-module coupling. Confidence mix (EXTRACTED vs anything
  else) is always shown. *Why:* a summary that hides the graph's blind spots would launder
  static-analysis gaps into architect briefs.
- **D4 — Skill teaches the eval's playbook, not the vendor's.** Clean-tree extraction via
  `git archive HEAD | tar -x -C <tmp>` for repos with heavy gitignored stores (this repo:
  903MB of benchruns would otherwise be crawled); `explain`/`god-nodes`/`affected`/`path`
  as the precise tools; `query --budget` labeled fuzzy-without-labels; exact node labels
  for `affected` (fuzzy match refuses ambiguity); graph_brief as the first read.
- **D5 — Hygiene stance.** graph.json measured relative-path-clean on this repo, but the
  skill still requires a scrub check before pasting graph output outward, and
  `/graphify-out/` is root-anchored gitignored (the memory/journal precedent). GRAPH_REPORT
  and graph.html are not certified clean — treat as local-only.
- **D6 — Kit slug `graphify-skill`, skill name `graphify`, no Claude-side manifest entry
  needed** (skills are directory-discovered; harness-update precedent). KIT_SENTINELS
  gets one contiguous single-line entry (T8-of-harness-update lesson: quote anchors from
  file bytes; keep the sentinel phrase on one physical line in GUARDRAILS.md).
- **D7 — Architect graft is additive-only.** One paragraph in
  `skills/architect/SKILL.md` offering graph_brief as an optional grounding source when a
  target repo carries a graph. Touching that file triggers the architect/execute shared
  kit-contract recheck — the graft must not alter any contract line. *Why include it:*
  the whole value thesis is cheaper architect grounding; without the pointer the tool
  won't be reached for.

## Model pins (routing history 2026-08-12)

sonnet 94% first-try / opus 100% / haiku 93%; verifier precision haiku 60% vs sonnet 100%.
All tasks sonnet except T4 wiring (haiku). Verifier sonnet, reviewer opus. Brief-defect
floor lessons applied: schema facts quoted from measured bytes (see Evidence), no line
anchors, sentinel single-line, verify commands that can fail.

## Risks and tripwires

- **Format drift (v0.9 tool).** graph_brief treats missing keys as absent-not-error and
  its tests pin only the keys D2 lists. Tripwire: if a real graph.json fails to parse,
  the brief prints which expected key vanished, never a traceback.
- **The skill overselling.** Tripwire for reviewer: every strength claim in SKILL.md must
  trace to the Evidence section above or be cut.
- **A future task invoking the binary "just to test".** The sentinel + GUARDRAILS forbid
  it; the verifier greps for `graphify` invocations in tests/verify.
- **Fuzzy multi-word node labels.** `affected` needs exact labels; the skill says get the
  label from graph_brief/`explain` first.
