### What it does

On Codex, this card is deliberately recall-only — it documents pulling a small,
relevance-gated set of private local facts and checking their staleness, not adding,
updating, or removing them, which stays a capability on the Claude harness for now.
That's a scope decision, not a missing port.

### When to reach for it

- Durable project context might help and you want it bounded and private, not dumped
  wholesale.
- Checking whether stored facts have gone stale before relying on them.
- Seeing the shape of a recall without touching a real store.
- **Not** for adding, updating, or removing a fact from this harness — the card
  documents recall and review only.

### Worked example

```bash
python3 bin/memory_recall.py --query "<5-15 salient keywords>" --memory-dir <memory-dir>
python3 bin/memory_store.py review --memory-dir <memory-dir> --now <YYYY-MM-DD>
```

Inject only the facts recall actually returns — never the whole store or its index,
and never past the relevance gate or the engine's own context budget. `--demo` shows
the same shape without touching a real store, useful for a first look.

### Failure modes & fallbacks

- **Recall returns nothing.** That's the gate working as designed, not a failure —
  proceed without memory rather than loosening the query.
- **A fact's freshness looks doubtful.** `review` is exactly the read-only check for
  that; it never writes anything on its own.
- **The plugin root can't be proven.** Stop and point at [doctor](doctor.md) rather
  than guessing a path.

### Cost & safety

Recall and review are read-only. There's no automatic write, no background watcher,
and no network sync anywhere in this skill; adding, updating, or removing a fact is a
separate, user-authorized operation that lives on a different harness's card today.
Every store operation here requires an explicit memory directory — deterministic
examples pin a fixed date too, so nothing here ever touches a real store by accident.

### Related

- [Deep dive: memory skill](../../deep-dives/memory-skill.md) — the design behind the
  relevance gate and budget, and where the fuller add/update/remove surface lives.
- [journal](journal.md) — a dated day's record, versus this skill's durable,
  cross-session facts.
- [Parity matrix](../index.md) — where this skill's Claude sibling adds more, and
  Copilot has none yet.
