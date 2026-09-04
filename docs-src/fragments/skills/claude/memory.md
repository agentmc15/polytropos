### What it does

Lets you tell it something worth remembering once, then pulls back only the handful of
facts relevant to whatever you're doing next — never the whole store. A save is durable
across sessions; a recall is small, budget-capped, and skipped entirely when nothing clears
the relevance bar.

### When to reach for it

- The user says "remember this," or corrects something you got wrong.
- Before relying on a preference or decision that might already be recorded.
- The user asks what you've been told to remember.
- **Not** a bulk-context dump — recall never pastes the whole store or its index; it always
  goes through the same budget-capped query path.

### Worked example

```bash
python3 bin/memory_store.py add --name "..." --type decision --description "..." \
  --tags a,b --body "..."
python3 bin/memory_recall.py --query "<keywords>"
```

Saving the same fact twice exits 2 with
`duplicate of [<slug>] — update it instead (or pass --force)` — update, don't force a
second copy. Recalling later with different phrasing still finds it if the tags were
meaningful; `no memory above the relevance gate for this query` is a **success**, not a
failure — proceed without memory rather than loosening the query to force a match.

### Failure modes & fallbacks

- **A recalled fact is flagged stale.** Its header line carries `— STALE, verify before
  relying` — re-check it against reality before acting on it, never trust it as-is.
- **`add` exits 2 on a duplicate.** Update the existing slug instead of forcing a second
  copy; an update also bumps its freshness.
- **The user asks what's stored.** `memory_store.py review` is a read-only staleness
  report; `list` shows every fact with its freshness state.

### Cost & safety

The store lives under the gitignored `memory/` directory at the plugin root — local-only,
never committed. Runtime code reaches it only through the explicit `--memory-dir` seam;
recall is capped at 5 facts / 4000 chars by default (`--max-facts`, `--budget-chars`
tighten it further), and expired facts are withheld outright rather than merely
down-ranked.

### Related

- [journal](journal.md) — a dated day's record, versus this skill's durable, cross-session
  facts.
- [Deep dive: memory skill](../../deep-dives/memory-skill.md) — the design behind the
  relevance gate and the budget.
- [Parity matrix](../index.md) — where this skill's Codex sibling differs and Copilot has
  none yet.
