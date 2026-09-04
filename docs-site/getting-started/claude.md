# Getting started on Claude Code

Claude Code is where polytropos originates: it ships as a plugin, served from a local
marketplace the repository itself provides. Nothing is fetched from a registry and nothing
is copied into a hidden location — the plugin is your checkout, registered by path.

## Prerequisites

- The Claude Code CLI, on your `PATH`.
- `git` and `python3` 3.8 or newer. Nothing to `pip install`.
- A clone of the repository — see [Getting started](index.md#start-with-a-checkout).

## Install

Persistent install, from inside a Claude Code session:

```
/plugin marketplace add /path/to/polytropos
/plugin install polytropos@polytropos-local
```

The non-interactive equivalents, from a shell:

```bash
claude plugin marketplace add /path/to/polytropos
claude plugin install polytropos@polytropos-local
```

For a throwaway session — testing a change without a persistent install — start Claude
Code with the directory instead:

```bash
claude --plugin-dir /path/to/polytropos
```

Use this machine's real absolute path. The marketplace records where the checkout lives,
so a path from another machine will not resolve.

## Where you stand matters

Skills resolve the plugin's own files through `${CLAUDE_PLUGIN_ROOT}`, so a skill works
from any project you happen to have open — you do not need to be inside the polytropos
checkout to type `/polytropos:route`.

**Your shell is a different story.** The `python3 bin/…` commands throughout this manual
run the engines directly, and they assume your working directory is a polytropos checkout.
Installing the plugin does not put `bin/` on your `PATH`. From another directory, spell the
path out: `python3 /path/to/polytropos/bin/cost_report.py --days 30`.

## Your first invocation

```
/polytropos:route add input validation to the signup handler
```

What comes back, in order: a short table of candidate models with an estimated cost — or
an API-equivalent burn figure, if you are on a subscription — and a one-line rationale
each, with the recommendation in bold. Then the actions. You can accept a dispatch, in
which case the work runs on a subagent pinned to the recommended model with a
self-contained brief written for it, or you can take the exact `/model` line it prints and
switch your own session. If the task is big enough to deserve frontier planning, route
hands you off to [architect](../skills/claude/architect.md) instead of offering a plain
dispatch.

That is what success looks like: a decision aid, compact, with a cost attached before
anything runs.

## Two optional extras

- **The statusline.** `/polytropos:setup` writes an absolute path into your Claude Code
  settings so every session shows the current model, live session cost, context usage, and
  rate-limit burn. It asks before it writes, and it must be run on the machine it
  configures — see [setup](../skills/claude/setup.md).
- **A freshness check.** `/polytropos:update` reports whether your installs and generated
  mirrors have drifted from the checkout after you pull. Checking is read-only; refreshing
  is a separate, explicit step.

## Next

- [Route your first task](../workflows/first-route.md) — the same invocation, with the
  output read line by line.
- [Claude Code skills](../skills/claude/index.md) — the full roster, how each is invoked,
  and what a skill can and cannot do.
- [The one constraint](../concepts/the-one-constraint.md) — why the router prints a
  `/model` line instead of switching for you.
- [Deep dive: how it works](../deep-dives/how-it-works.md) — the architecture behind the
  roster.
