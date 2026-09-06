# Getting started on OpenAI Codex CLI

Polytropos routes Codex execution through central policy. Astra plans, coordinates, recovers from recorded failures, and accepts phases; Luna, Terra, and Sol perform worker roles appropriate to the task. Model availability and prices are read from policy data at runtime.

Use a current Codex client, Git, and Python 3.11 or newer.

## Install

```bash
codex plugin marketplace add /path/to/polytropos
codex plugin add polytropos@polytropos-local
codex plugin list --marketplace polytropos-local --json
```

Start a new task after installation. Use `/skills` or `$route`; a Desktop skill selector is available only when that client exposes one. Preview optional agent setup without changing it:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run
python3 bin/harness_select.py doctor --harness codex --repo-root . --codex-home <codex-home>
```

## First routed kit

Use `$architect` for multi-task work. Then inspect the policy's assignment before authorizing a real dispatch:

```bash
python3 bin/codex_execute.py status --kit tasks/kits/<slug> --json
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id> --dry-run
```

Run implementation, independent review, and Astra acceptance through the driver. Do not write a private dispatch loop. Planned pins, dispatched assignments, and observed runtime model use are separate; absent observation is `unknown`. Recovery is reserved for driver-recorded machine failure and does not create a warm pool.

For an existing application configuration, preview the exact changes first:

```bash
python3 bin/codex_app_policy.py plan --repo-root . --codex-home <codex-home> --backup-root <new-empty-dir> --runtime-models <model-list.json>
```

Use `apply` only after reviewing the plan. It needs the same explicit roots and availability snapshot, preserves unrelated settings, and refuses unmanaged agent-role files.
