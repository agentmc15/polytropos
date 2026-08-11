---
name: doctor
description: Diagnose Polytropos Codex plugin, agent, skill, prompt, and managed-install state without changing it. Use for setup, upgrades, stale paths, missing skills, or install conflicts.
---

# Diagnose Codex setup safely

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/doctor/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and
`$POLYTROPOS_ROOT/bin/harness_select.py` exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

Run the read-only doctor with an explicit Codex home when one is known:

```bash
python3 "$POLYTROPOS_ROOT/bin/harness_select.py" doctor --harness codex --repo-root "$POLYTROPOS_ROOT" --codex-home <codex-home>
python3 "$POLYTROPOS_ROOT/bin/harness_select.py" doctor --harness codex --repo-root "$POLYTROPOS_ROOT" --codex-home <codex-home> --json
```

You may also preview an intended install with `install ... --dry-run`; preview and doctor must
remain byte-read-only. Summarize each component state (`install`, `up-to-date`,
`managed-update`, `conflict`, `unmanaged`, or `skip`) and give the exact remedy printed by the
engine. Never suggest `--force`, deleting the Codex home, or overwriting config.toml.

An actual `install` or `--refresh-managed` is a write. Show the plan and obtain explicit user
authority before running it. Managed refresh is allowed only for unchanged recorded copies;
user-edited or unrelated destinations remain conflicts. Remind the user to restart Codex or
start a new task after enabling a plugin or changing agents.
