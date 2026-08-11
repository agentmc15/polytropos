---
name: context-weight
description: Analyze how Codex context grows, what resident instructions cost, and where fidelity stops. Use for context-window pressure, growth curves, loaded-surface audits, or compaction questions.
---

# Analyze Codex context weight honestly

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/context-weight/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and
`$POLYTROPOS_ROOT/bin/context_weight.py` exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

Use only the engine's real Codex surfaces:

```bash
python3 "$POLYTROPOS_ROOT/bin/context_weight.py" session --harness codex --codex-home <codex-home>
python3 "$POLYTROPOS_ROOT/bin/context_weight.py" overview --harness codex --codex-home <codex-home>
python3 "$POLYTROPOS_ROOT/bin/context_weight.py" audit --project <repo>
python3 "$POLYTROPOS_ROOT/bin/context_weight.py" demo
```

Codex rollout logs provide token-count growth curves and record-type byte shares, not content
provenance. Never turn those byte shares into claims about which prompt, instruction, or tool
filled the window. `watch` is Claude-only, and `constraints --harness codex` can only return the
engine's explicit fidelity-limit line; Codex cannot answer live pruning or GUARDRAILS.md residency.

Relay the engine's estimated-token and unpriced labels. The audit is about resident tokens, never
dollars, and no context estimate is a billing statement.
