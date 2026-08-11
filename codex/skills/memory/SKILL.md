---
name: memory
description: Recall a small, relevance-gated set of private local facts and review their staleness. Use when durable project context may help but context quality and privacy must stay bounded.
---

# Bounded private memory for Codex

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/memory/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json`,
`$POLYTROPOS_ROOT/bin/memory_recall.py`, and `$POLYTROPOS_ROOT/bin/memory_store.py` exist. If proof
fails, stop and direct the user to `python3 bin/harness_select.py doctor --harness codex`; never
run a guessed or stale path.

Memory is pull-only. Derive a short task query of salient keywords, then ask the recall engine for
gated, budget-capped winners:

```bash
python3 "$POLYTROPOS_ROOT/bin/memory_recall.py" --query "<5-15 salient keywords>" --memory-dir <memory-dir>
python3 "$POLYTROPOS_ROOT/bin/memory_recall.py" --demo
python3 "$POLYTROPOS_ROOT/bin/memory_store.py" review --memory-dir <memory-dir> --now <YYYY-MM-DD>
```

Inject only the facts returned by recall. Never dump or bulk-read the store/index, bypass the
relevance gate, or expand the engine's context budget. Preserve each winner's source, confidence,
expiry, contradiction, and staleness semantics. Store operations always require an explicit
`--memory-dir`; deterministic examples and tests also pass `--now` or use the synthetic demo.

There is no automatic write, background watcher, network sync, or pricing coupling. Adding,
updating, verifying, or removing a fact is a separate user-authorized store operation; ordinary
recall and review remain read-only.
