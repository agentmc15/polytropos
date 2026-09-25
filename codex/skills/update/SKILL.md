---
name: update
description: Check and refresh Polytropos harness installs and generated mirrors with the repository's updater. Use for install freshness, bundle drift, or an explicitly requested refresh; checking is read-only and always comes first.
---

# Check and refresh Polytropos installs

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`; reject the literal placeholder. Confirm `$POLYTROPOS_ROOT/bin/harness_update.py` exists before running it.

Always begin with the read-only check and report its card:

```bash
python3 "$POLYTROPOS_ROOT/bin/harness_update.py" check --repo-root "$POLYTROPOS_ROOT"
```

Exit 3 means drift was found, not that the checker crashed. “not installed” is absence, `unmanaged` is a warning, and Codex `conflict` or `managed-update` entries are actionable drift.

## Write boundary

Run `apply` only when the user explicitly requested a refresh in the current conversation. A freshness question is not authorization to write. If intent is unclear, show the dry-run instead:

```bash
python3 "$POLYTROPOS_ROOT/bin/harness_update.py" apply --repo-root "$POLYTROPOS_ROOT" --dry-run
```

After explicit authorization, run:

```bash
python3 "$POLYTROPOS_ROOT/bin/harness_update.py" apply --repo-root "$POLYTROPOS_ROOT"
```

Stop and report an `error` result; do not retry a writer blindly.

## Interpret apply accurately

- Copilot bundle-owned files may be overwritten; unknown files remain untouched. A `preserved` entry is intentional and needs a separate user decision.
- Codex generated compatibility prompts may be overwritten and are listed when they differ. User-editable `AGENTS.md` and skill destinations are no-clobber: differing copies are reported as `skip-differs` and preserved.
- Project `.codex/agents/*.toml` files and the modern Codex plugin are outside this updater's apply scope. Use the repository's Codex installer workflow separately when the user requests those surfaces.
- Generated repository mirrors are refreshed by their existing sync tools. Pricing values and documentation snapshot tables still require the repository's documented human refresh procedure.
- The updater never writes `~/.claude`. It may print a conditional stale-cache remedy; run that remedy only after separate explicit approval.

The check and apply JSON modes have different shapes, and JSON plus the human apply card can contain absolute home paths. Scrub local paths before sharing output outside the machine.

Finish with what was observed, what changed, any preserved/conflicting paths described without leaking the home directory, and remaining limitations.
