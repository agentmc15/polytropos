---
name: effort
description: Choose a data-derived reasoning effort for a policy-routed Codex run.
metadata:
  short-description: Choose effort through the central driver
---

# Reasoning effort

## Resolve the plugin root before running commands

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder. Confirm pricing data and `bin/codex_execute.py` exist. If not, use `python3 bin/harness_select.py doctor --harness codex`.

Derive the complete effort ladder and mode notes at runtime. Do not enumerate levels, model support, or prices in prose:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" knobs
```

Omit an override for routine work. Increase one data-reported rung only after concrete machine evidence says the current worker's reasoning was insufficient. A worker-tier change addresses capability; effort addresses thinking time. For a kit, carry the validated selection through the central driver:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit tasks/kits/<slug> --task <id> --effort <level>
```

The driver applies the validated selection through its `model_reasoning_effort` configuration while preserving the policy-selected worker and planned/dispatched/observed records. For subscription use, explain increased burn before any API-equivalent proxy; for API-key runs, use the engine when a token-metered estimate is needed.
