---
name: escalate
description: Run verification-gated Codex recovery through the central execution driver.
metadata:
  short-description: Recover only from recorded machine failure
---

# Verification-gated recovery

## Resolve the plugin root before running commands

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder. Confirm pricing data, `bin/codex_policy.py`, and `bin/codex_execute.py` exist. If proof fails, use `python3 bin/harness_select.py doctor --harness codex`.

Use `$execute` for kit work. The central driver is the only recovery path: it records prior worker attempts, dispatch exits, independent verification, and bounded correction scope. Do not run a private escalation loop or invoke a reserved recovery target based on a subjective assessment.

Recovery opens only after machine-visible evidence: a nonzero verify exit, an unresolved named integration conflict, or a failed lower-tier correction. Each attempt record names the task and dispatched worker. The driver creates the reserved Astra target for that correction only; there is no warm pool. It independently verifies correction and returns subsequent work to workers.

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit tasks/kits/<slug> --task <id> --dry-run
```

Do not call `prepare --role recovery`: caller-supplied evidence cannot unlock recovery. Report planned, dispatched, and observed model-role records separately; unknown observed identity stays `unknown`.
