### What it does

Grepping a large codebase for "what calls this" means reading past false positives and
still not being sure you found every caller. Building a graph replaces that with one exact
lookup: a one-time, offline extraction pass writes a `graph.json` under `graphify-out/`,
and afterward, questions about how the repo actually fits together stop costing a wide
exploratory read and start costing a single targeted query.

### When to reach for it

- Repo-structure questions — what calls this, what depends on it, what would an edit affect.
- Before architecting against an unfamiliar codebase, to ground the plan cheaply.
- After a change, to check impact analysis on the symbols it touches.
- **Not** installed or invoked automatically — it's an external, user-installed CLI (`uv
  tool install graphifyy`), the same posture as `gh`, and its absence is not a failure.

### Worked example

```bash
git archive HEAD | tar -x -C <tmpdir>
graphify update <tmpdir> --no-cluster
graphify cluster-only <tmpdir> --no-label --no-viz
python3 bin/graph_brief.py brief --graph <tmpdir>/graphify-out/graph.json
```

Read in that order: the brief first, always; then `graphify explain "<symbol>"` for one
symbol's exact callers; `god-nodes` for hubs by centrality; `affected "<exact label>"` for
impact analysis; `path "A" "B"` for a route between two symbols. `query` comes last and is
labeled honestly when shown to a user: without LLM community labels it's fuzzy graph
search — adjacency, not answers.

### Failure modes & fallbacks

- **Dynamic loaders are invisible to AST extraction.** This repo's own cross-module loading
  is absent from its own graph — a missing edge is never proof a dependency doesn't exist;
  verify by reading the code instead.
- **The "excluding tests/" hub filter is a top-level-prefix match only.** A `test/`,
  `spec/`, or nested `src/tests/` layout gets no benefit from it even though the label still
  claims exclusion — don't over-trust it on a repo you haven't checked the layout of.
- **The binary is absent.** Print the install command for the user to run themselves and
  stop; never install it on their behalf.

### Cost & safety

Only offline, no-network, no-daemon subcommands are ever prescribed:

| Excluded surface | Why |
|---|---|
| `extract`, `label`, any `--backend`/`--model` flag | network + spend (LLM extraction) |
| `add <url>`, `clone` | network fetch, writes outside the repo |
| `global add/remove/list/path` | writes outside the repo entirely |
| `watch` | daemon-like watcher |
| per-platform `install`/`hook install` | rewrites host config, installs hooks |

Reading the graph is free; the allowed extraction commands write only under the gitignored
`graphify-out/`, never committed.

### Related

- [architect](architect.md) — the skill this brief is built to ground before Fable plans.
- [context-weight](context-weight.md) — the token-compression case for reaching here
  before a wide read.
- [Deep dive: how it works](../../deep-dives/how-it-works.md) — where this fits beside the
  other planning tools.
