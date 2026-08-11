---
name: execute
description: Execute a prepared Codex kit task-by-task with dependency checks, independent verification, and phase review. Use after architect creates tasks/kits/<slug>, or when asked to run or continue a kit.
---

# Execute a Codex execution kit

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/execute/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and
`$POLYTROPOS_ROOT/bin/codex_execute.py` exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

Consume only a kit under `tasks/kits/<slug>/`. Read PLAN.md, TASKS.md, and any kit guardrails
before execution, especially constraints and out-of-scope fences. Honor task dependencies, the
exact `pending | in-progress | done | blocked` status vocabulary, and each task's runtime-resolved
model pin. Do not rewrite a brief to fit an unexpected repository state.

## Safe progression

Inspect without dispatching:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" status --kit tasks/kits/<slug>
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit tasks/kits/<slug> --dry-run
```

The dry run prints the next dispatch and verify plan; it does not launch Codex. A real run does:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" run --kit tasks/kits/<slug> --task <id>
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" review --kit tasks/kits/<slug> --phase <N>
```

A real `run` or non-dry `review` launches headless Codex and spends subscription usage or
API-metered funds. Obtain the user's authority before starting it. Never represent a dry run as a
real dispatch.

When interactive delegation is available, prefer the canonical `kit-implementer`,
`kit-verifier`, and `phase-reviewer` custom agents and keep their roles separate. Plugin install
does not install those agents; the headless driver remains the functional fallback. Regardless of
path, rerun the task verify command independently before accepting completion and review each
completed phase for plan drift.
