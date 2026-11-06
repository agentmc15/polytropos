### What it does

Turns "what calls this, and what would this edit touch?" from a wide read into a targeted
lookup. An optional, user-installed `graphify` CLI extracts a local graph of the
repository; two repository engines then stamp that graph with its provenance and read it
back with a freshness verdict, so you know whether an edge is evidence or only a hint.

### When to reach for it

- Use it for symbol lookup, call structure, and dependency or impact analysis.
- Use it before architecture work in an unfamiliar codebase, to ground the plan cheaply.
- Use it after a change, starting from the files you touched.
- **Not** when the CLI is absent: the skill names `uv tool install graphifyy` and stops. It
  never runs the installer for you, and absence is not a task failure.

### Worked example

```bash
git archive HEAD | tar -x -C <tmpdir>
graphify update <tmpdir> --no-cluster
graphify cluster-only <tmpdir> --no-label --no-viz
python3 "$POLYTROPOS_ROOT/bin/graph_ground.py" stamp --repo <repo> --graph <tmpdir>/graphify-out/graph.json --extraction commit-only
python3 "$POLYTROPOS_ROOT/bin/graph_ground.py" ground --repo <repo> --graph <graph.json> --changed
```

The first three lines build from a clean tracked snapshot, so ignored and personal files
are structurally excluded; `stamp` records revision, covered-file fingerprints, and the
graph hash. Read `ground` before anything broader: it reports one of four verdicts and
falls back to a bounded code search when the graph cannot answer.

| Verdict | Read the graph as |
|---|---|
| `fresh`, `partial` | evidence, within the bounds printed |
| `stale`, `unknown` | navigation hints only |

After that, `graph_brief.py brief` gives a bounded architecture summary, and `graphify
explain`, `god-nodes`, `affected`, and `path` answer one question each. `query` comes last:
without inference-generated labels it is fuzzy traversal, not an answer.

### Failure modes & fallbacks

- A graph without its sidecar has `unknown` freshness; do not infer the extraction label or
  manufacture a revision.
- Static extraction misses dynamic loaders and imports, so a missing edge never proves a
  dependency is absent. Verify important negative claims in source.
- Centrality can be dominated by tests or fixtures; pass explicit `--exclude <prefix>`
  arguments rather than trusting a hub list.
- Resolve an exact label before `graphify affected`; do not guess through fuzzy matching.

### Cost & safety

Only offline surfaces run without explicit authorization in the current conversation. The
skill does not run or recommend `extract`, `label`, backend or model flags, `add <url>`,
`clone`, `global` mutations, `watch`, installers, hooks, servers, or daemons, because they
can introduce network use, inference spend, background processes, or configuration changes.
Output belongs under `graphify-out/` and is never committed. A graph fact grants no write,
alters no acceptance criterion, and does not prove concurrent edits safe.

### Related

- [architect](architect.md) is the planning step this grounding serves.
- [context-weight](context-weight.md) shows where a session's context went, which is the
  cost a targeted lookup avoids.
- [Deep dive: graph engineering](../../deep-dives/graph-engineering.md) covers the graph
  readers and their limits.
