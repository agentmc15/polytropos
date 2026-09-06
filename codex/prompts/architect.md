---
description: "Plan complex Codex work as a policy-routed execution kit."
---

> Deprecated compatibility prompt; prefer `$architect`.

# Architect a Codex execution kit

## Resolve the plugin root before running commands

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder. Confirm pricing data, `bin/codex_pricing.py`, `bin/codex_policy.py`, and `bin/codex_execute.py` exist. Otherwise run `python3 bin/harness_select.py doctor --harness codex` rather than guessing a path. Never invoke the real Codex CLI from a kit verify command.

Plan only. Write `PLAN.md` and `TASKS.md` beneath `tasks/kits/<slug>/`; do not dispatch implementation. Every task is self-contained, has a machine-checkable verify command, and uses exactly `pending | in-progress | done | blocked`.

This skill carries no `model:` pin: the desktop app supplies its own model, which application policy configures as Astra for orchestration. The model remains app-controlled while the kit is written.

Use worker intent in each task's `model` field: `cheap` for mechanical work, `mid` for routine work, and `strong` for hard implementation, security, integration, or independent verification. Do not pin the reserved orchestration tier or an orchestration model. Central policy resolves workers at dispatch time, migrates an unpinned legacy task to the configured default worker, and maps a legacy reserved-tier pin to the maximum worker. Availability, model identities, effort support, and cost facts come only from data and policy.

Plan Astra as coordinator: it owns decomposition, dependencies, recovery decisions, and final acceptance. It is not an ordinary worker and the CLI has no warm pool. A recovery target is created only after recorded worker attempts and a machine-checkable failure; vague dissatisfaction never unlocks it. After correction, schedule remaining work back to workers.

Use Luna for cheap mechanical work, Terra for routine implementation, and Sol for hard, security, integration, or independent verification work. Keep final acceptance separate from independent verification. Record a per-request size assumption for long-context work; do not use aggregate session tokens as a request-size estimate.

Preview assignments before handoff:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" status --kit tasks/kits/<slug> --json
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit tasks/kits/<slug> --task <id> --dry-run
```

Planned, dispatched, and observed model-role facts are different records. An unobserved runtime identity remains `unknown`.
Later, `bin/codex_execute.py` resolves each worker task and passes the selected id as `codex exec --model <id>`; that execution step is separate from planning.
