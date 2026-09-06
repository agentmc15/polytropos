---
name: execute
description: Run a prepared Codex kit through central policy, worker verification, and Astra acceptance.
---

# Execute a Codex execution kit

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`; reject the literal placeholder. Confirm pricing data, `bin/codex_policy.py`, and `bin/codex_execute.py` exist. Otherwise stop and use `python3 bin/harness_select.py doctor --harness codex`.

Read the kit's `PLAN.md`, `TASKS.md`, and guardrails. The only task states are `pending | in-progress | done | blocked`. Use the central driver; do not replace it with a freehand dispatch loop or select workers from prose.

Start with read-only previews:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" status --kit tasks/kits/<slug> --json
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit tasks/kits/<slug> --task <id> --dry-run
```

A real run spends subscription usage or API funds, so obtain authority before it. When interactive delegation is available, `kit-implementer`, `kit-verifier`, and `phase-reviewer` provide separate roles; plugin installation does not install them. The headless driver remains the functional fallback. Dispatch implementation, independent review, and final acceptance through the driver:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit tasks/kits/<slug> --task <id>
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" review --kit tasks/kits/<slug> --phase <N>
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" accept --kit tasks/kits/<slug> --phase <N>
```

The driver uses workers for ordinary work and reserves Astra for final acceptance or a bounded correction. It creates no warm pool. Recovery needs recorded lower-tier attempts and a real nonzero verification result, unresolved integration conflict, or failed lower-tier correction. Rerun verification independently before acceptance. Treat planned, dispatched, and observed model-role records as different facts, leaving unavailable observations `unknown`.
