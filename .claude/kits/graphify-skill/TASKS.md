# graphify-skill — tasks

Dispatch preamble: T1 → T2 are strictly serial (same primary file, `bin/graph_brief.py`,
both sonnet) — a warm-cluster candidate. T3 depends on T1 (it quotes the engine's real
flags) but not T2. T4 and T5 are independent of each other; both wait for T3 so the
surfaces they wire/point at exist. Statuses: pending | in-progress | done | blocked.

## Phase 1 — The stdlib reader

### T1 — bin/graph_brief.py core + tests
- id: T1
- title: graph_brief engine — load, brief, hubs, honesty features
- status: done
- model: sonnet
- independent: yes

Create `bin/graph_brief.py` (new) and `tests/test_graph_brief.py` (new). Nothing else.

Engine contract (argparse, stdlib only, `main(argv=None)` → int, ending
`if __name__ == "__main__": raise SystemExit(main())`; module docstring states: reads a
graphify graph.json READ-ONLY; never invokes the graphify binary; graphify is an external
user-installed tool this repo never vendors):

- Subcommand `brief` with `--graph PATH` (default `graphify-out/graph.json` relative to
  cwd), `--top N` (default 8), `--json`. Later task adds `demo`; keep the parser
  extensible.
- Input shape (MEASURED from graphifyy 0.9.41 output — tolerate absence of any key via
  `.get`, and accept a top-level `edges` list as an alias when `links` is missing):
  top-level `nodes` (list) + `links` (list) + optional `directed`/`multigraph`/`graph`/
  `hyperedges`. Node keys: `id`, `label`, `norm_label`, `community`, `community_name`,
  `file_type`, `source_file` (relative path), `source_location` (e.g. "L122"),
  `_callable`, `_callable_class`, `_origin`. Link keys: `source`, `target`, `relation`
  (seen: `calls`, `contains`, `extends`, `references`), `context`, `confidence` (seen:
  `EXTRACTED`), `confidence_score`, `source_file`, `source_location`, `weight`, `_origin`.
- The brief card (human; `--json` mirrors the same data):
  1. counts: nodes, links, communities (distinct `community` values), files (distinct
     `source_file`).
  2. relation mix: count per `relation` value, descending.
  3. per-directory mass: node count per top-level directory of `source_file` (files with
     no `source_file` grouped as `(none)`).
  4. hubs twice: top `--top` nodes by degree over ALL links, then top `--top` recomputed
     EXCLUDING nodes whose `source_file` starts with `tests/` — labeled exactly
     "hubs excluding tests/ (fixture dominance is real: measured on this repo,
     all top-8 all-files hubs were test helpers)". Each hub line: label, degree,
     source_file:source_location.
     AMENDED at P1 review (architect `defect:` T1 stale-pin — the original label
     overclaimed beyond the Evidence: the real graph's all-files top-8 is 4/8 test
     helpers, not 8/8; graphify's own god-nodes centrality, not graph_brief's degree
     ranking, produced the original 8/8 observation). The label is now exactly:
     "hubs excluding tests/ (test fixtures can dominate raw degree -- on the repo this
     tool was calibrated against, tests/ held 54% of node mass and topped the all-files
     hub list)". The remediation task updates engine + tests to this string.
  5. confidence mix: count per `confidence` value.
  6. cross-file call ratio: among links with `relation == "calls"` whose BOTH endpoint
     nodes carry a `source_file`, the share where the two files differ. When the ratio is
     below 0.05 (or there are zero cross-file calls), print the verbatim warning:
     "LOW CROSS-FILE VISIBILITY -- dynamic loaders (importlib, plugin registries) are
     invisible to AST extraction; this graph under-represents cross-module coupling.
     Verify dependencies by reading the code, not by absence of edges." The warning is
     informational; it never changes the exit code.
- Failure honesty: absent graph file → print "no graph at <path> -- run `graphify update
  <repo>` first (graphify is an external, user-installed tool; this repo never installs
  or invokes it)" and exit 0 (absence is not failure). Unparseable JSON or a parseable
  file missing BOTH `nodes` and `links`/`edges` → one-line message naming what was
  expected and exit 2 — never a traceback.
- Zero `Path.home()`/`expanduser` anywhere in this engine (it has no home-dir business);
  no `subprocess`, no `urllib`. Add the source-introspection test enforcing all three
  over every function (the `tests/test_codex_setup.py` idiom).

Tests (`tests/test_harness_select.py` conventions: `BIN_DIR`/`_load` importlib loader,
`tempfile.TemporaryDirectory` fixtures, no real files): a synthetic graph.json builder
covering ≥2 directories + tests/-dominated hubs + a cross-file call and a same-file call;
assertions for every card section; the tests/-exclusion actually changing the hub list;
the low-ratio warning appearing exactly when constructed; absent-file exit 0 with the
message; corrupt-file exit 2; `--json` round-trips with the same counts; introspection
guard.

Acceptance: all card sections present and test-pinned; both failure modes honest; no
graphify invocation anywhere (grep proves the string `graphify` appears in
bin/graph_brief.py only inside messages/docstrings, never in an exec/subprocess call —
which is doubly true because subprocess itself is banned).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_graph_brief.py' -v
```

### T2 — demo subcommand + edge-case honesty
- id: T2
- title: graph_brief demo + drift-tolerance tests
- status: done
- model: sonnet
- depends: T1

Edit only `bin/graph_brief.py` and `tests/test_graph_brief.py`.

1. `demo`: builds a synthetic graph.json in a `tempfile.mkdtemp` tree it removes in a
   `finally`, renders the full brief card on it (including a seeded low-cross-file-ratio
   variant so the warning is demonstrated), prints both cards, always exits 0, takes no
   path arguments (cannot receive real files by construction). This is the CLAUDE.md
   run-line smoke.
2. Drift tolerance, test-pinned: a graph.json whose links live under `edges` instead of
   `links` parses identically; nodes missing `community`/`source_file`/`label` degrade
   per-section (counted under `(none)` or skipped) without crashing; an empty nodes list
   renders a card with zeros rather than erroring.
3. A test asserting demo's default paths never resolve into the real cwd repo (the demo
   subparser accepts no `--graph`).

Acceptance: `python3 bin/graph_brief.py demo` exits 0 and prints both cards; drift cases
pinned; suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_graph_brief.py' -v && python3 bin/graph_brief.py demo >/dev/null && echo demo-ok && python3 -m unittest discover -s tests -q
```

## Phase 2 — Surface and wiring

### T3 — skills/graphify/SKILL.md
- id: T3
- title: The /polytropos:graphify skill
- status: done
- model: sonnet
- depends: T1

Create `skills/graphify/SKILL.md` only. Frontmatter exactly (no `model:` pin):

```yaml
---
name: graphify
description: Build and read a local knowledge graph of a repo with the external graphify CLI — symbol lookup with file:line precision, call structure, impact analysis, and an architect-grounding brief, all offline. Use when the user wants repo structure analyzed or mapped, asks what calls or depends on something, wants impact analysis for a change, or before architecting against an unfamiliar repo. Args: optional repo path (default: the current repo).
allowed-tools: Bash, Read
---
```

Body, in order:

1. **Availability gate:** check `command -v graphify`; absent → print
   `uv tool install graphifyy` as the USER'S command (never run an installer) and stop.
   Absence is not failure.
2. **Local-only law (PLAN out-of-scope, binding):** only `update`, `cluster-only
   --no-label --no-viz`, `explain`, `god-nodes`, `affected`, `path`, `query`, `tree`,
   `diagnose` may be prescribed or run — all offline. `label`, any `--backend`/`--model`,
   `add`, `clone`, `watch`, `install`/`uninstall`, and the MCP server are network/spend/
   daemon/config surfaces: only on the user's explicit opt-in in this conversation.
3. **Extraction recipe:** for a repo with heavy gitignored stores (this one: 903MB of
   benchruns), extract a clean tree first — `git archive HEAD | tar -x -C <tmpdir>` —
   and run `graphify update <tmpdir> --no-cluster && graphify cluster-only <tmpdir>
   --no-label --no-viz` there; outputs land in `<dir>/graphify-out/`. In-place runs are
   fine for normal repos; `/graphify-out/` is gitignored here.
4. **Reading order:** `python3 bin/graph_brief.py brief --graph <dir>/graphify-out/
   graph.json` first (resolve the engine via `${CLAUDE_PLUGIN_ROOT}/bin/graph_brief.py`,
   falling back to `../../bin/graph_brief.py` relative to this SKILL.md resolved to an
   absolute path — bash cwd is not the skill dir); then `explain "<symbol>"` for
   specifics; `god-nodes` for hubs; `affected "<exact label>"` for impact (labels must be
   exact — get them from the brief or explain first); `path "A" "B"` (add `--undirected`
   before concluding no path); `query "<question>" --budget N` LAST, labeled: fuzzy BFS
   without LLM labels — adjacency, not answers.
5. **Measured limits (2026-08-12 eval on this repo, verbatim spirit):** dynamic loaders
   (importlib sibling-loading, plugin registries) are invisible to AST extraction — this
   repo's bin/ cross-module spine is absent from its own graph, and graph_brief's
   low-cross-file-ratio warning names exactly this; god-nodes/query skew toward test
   fixtures on test-heavy repos (use the brief's tests/-excluded hub list); absence of an
   edge is never evidence of absence of a dependency.
6. **Hygiene:** graph.json measured relative-path-clean on this repo — still scan any
   graph output before pasting it outward; GRAPH_REPORT.md and graph.html are NOT
   certified clean, treat as local-only. Never commit graphify-out/.

Acceptance: frontmatter exactly `name`,`description`,`allowed-tools`; body covers 1–6 in
order; every strength/limit claim traces to PLAN.md's Evidence section; no absolute home
paths, no prices, no model ids; suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -c "
import re; t=open('skills/graphify/SKILL.md').read()
fm=re.match(r'---\n(.*?)\n---\n', t, re.S); assert fm, 'no frontmatter'
keys=[l.split(':')[0] for l in fm.group(1).splitlines() if ':' in l]
assert keys==['name','description','allowed-tools'], keys
assert 'command -v graphify' in t and 'graph_brief' in t and '--no-label' in t
assert 'uv tool install graphifyy' in t
assert '/Users/' not in t, 'home path leak'
print('skill shape ok')" && python3 -m unittest discover -s tests -q
```

### T4 — gitignore, CLAUDE.md, KIT_SENTINELS
- id: T4
- title: Wire graphify-skill into the repo's law
- status: done
- model: haiku
- depends: T3

Three edits, nothing else:

1. `.gitignore` — append (root-anchored, matching the file's commented-block style):
   `# graphify knowledge-graph output (local analysis artifacts, never committed)`
   `/graphify-out/`
2. `CLAUDE.md` "How to run things" — one line, matching the block's comment style:
   `python3 bin/graph_brief.py demo                # architect-grounding brief from a graphify graph.json — synthetic smoke, no graphify binary (lands with the graphify-skill kit)`
   and CLAUDE.md Invariants — one bullet, verbatim:
   `**graphify is an external, user-installed CLI (\`uv tool install graphifyy\`) — never vendored, never auto-installed, and never invoked by tests, verify commands, or kit execution.** \`bin/graph_brief.py\` only ever READS a graph.json; skill-sanctioned graphify subcommands are the offline set only (no \`label\`/backends/\`add\`/\`clone\`/\`watch\`/MCP without explicit user opt-in). \`/graphify-out/\` stays gitignored.`
   Budget: CLAUDE.md was 13,881 bytes before this kit; stay ≤ 16,000
   (`ClaudeMdBudgetTests` enforces). If tight, shorten the run-line comment only.
3. `tests/test_guardrails_layout.py` `KIT_SENTINELS` — add:
   `"graphify-skill": "never invoked by tests, verify commands, or kit execution",`
   That exact substring exists on ONE PHYSICAL LINE in
   `.claude/kits/graphify-skill/GUARDRAILS.md` (verified at kit-authoring time — do not
   edit GUARDRAILS.md; if the substring does not match, STOP and report rather than
   adapting).

Acceptance: `wc -c CLAUDE.md` ≤ 16000; `git check-ignore graphify-out/` matches;
full suite green (proves sentinel + budget).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && git check-ignore -q graphify-out/ && grep -q 'graphify-skill' tests/test_guardrails_layout.py && grep -c "graph_brief.py" CLAUDE.md | grep -qx 2 && python3 -m unittest discover -s tests -q
```

### T5 — architect skill graft (additive-only)
- id: T5
- title: Point the architect at graph grounding
- status: done
- model: sonnet
- depends: T3

Edit only `skills/architect/SKILL.md`. Add ONE self-contained paragraph (placement: inside
Step 1 or beside the scoping guidance — wherever the file's flow reads naturally), in the
file's own voice, saying in substance: before dispatching wide exploratory reads over an
unfamiliar target repo, check for `graphify-out/graph.json` (or offer the user
`/polytropos:graphify` to build one — external tool, availability-gated); when a graph
exists, `python3 bin/graph_brief.py brief --graph ...` plus targeted `graphify explain`
calls can ground the plan at near-zero context cost — but the graph's limits bind
(dynamic loaders invisible, absence of an edge proves nothing), so treat it as a first
map, never as the sole evidence for a contract or dependency claim.

HARD FENCE: this file is half of the architect/execute shared kit contract. The paragraph
is ADDITIVE ONLY — zero changes to any existing line, and nothing that touches the kit
contract (layout, task fields, status vocabulary, phase headings, depends/independent,
model-field authority, NOTES.md line families). After editing, re-check BOTH
`skills/architect/SKILL.md` and `skills/execute/SKILL.md` against the contract per
CLAUDE.md's invariant and state in your report that both still agree.

Acceptance: `git diff skills/architect/SKILL.md` shows only added lines (no deletions,
no modified existing lines); the paragraph names both graph_brief and the
availability-gated skill; suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && git diff --numstat skills/architect/SKILL.md | awk '{exit ($2!=0)}' && grep -q 'graph_brief' skills/architect/SKILL.md && python3 -m unittest discover -s tests -q
```
