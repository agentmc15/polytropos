### What it does

Gives the model a memory it wouldn't otherwise have between runs: after any correction, it
writes the failure pattern and the rule that prevents it to a plain file on disk, then
reads that file back at the start of the next session — no engine behind it, just a
convention this repo also uses to catch its own routing mistakes.

### When to reach for it

- Immediately after the user corrects something you did.
- Immediately after a task escalates to a higher-tier model than it was pinned to.
- At the very start of a session, to load lessons relevant to what you're about to do.
- **Not** a place to bake in a price or a specific model id — lessons state the rule in
  tier and task-shape terms; the roster resolves at run time.

### Worked example

```json
{"date": "2026-07-01", "failure_pattern": "pinned a cheap-tier model for a multi-file refactor; verify failed twice and the task escalated to strong", "lesson": "multi-file refactors start at the strong tier", "applies_to": ["routing"]}
```

Two triggers are worth a routing-category entry: a task escalated because its pinned model
failed verify (the execute driver marks these `lesson-candidate (routing):` in a kit's
`NOTES.md` — that line is the machine signal a lesson is owed), or a tier was grossly
overprovisioned for what the task actually needed.

### Failure modes & fallbacks

- **Lessons pile up unread.** Dedupe, date each entry, and prune stale or contradicted
  ones — a stale lesson pollutes future behavior as much as a missing one.
- **A lesson leaks between projects.** Keep entries project-scoped; one project's quirks
  don't belong in another's file.
- **No engine exists to enforce any of this.** It's a plain file convention — if
  `tasks/lessons.md` is never read at session start, the loop simply doesn't close.

### Cost & safety

Nothing here spends anything — it's a read/write against a plain project file, never a
model dispatch of its own. Vendored from aesop (`registry/skills/lessons-loop` at commit
5506617), with this repo's own addition layered on top: the Copilot-harness routing
category, which [route](route.md) reads at session start.

### Related

- [route](route.md) — applies a routing-category lesson before its own default tier
  heuristics.
- [budget](budget.md) and [goliath](goliath.md) — the other two Copilot-only skills with
  no Claude or Codex sibling.
- [Parity matrix](../index.md) — why this page has no equivalent elsewhere.
