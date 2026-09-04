### Installing

The Copilot side ships as a bundle materialized into a Copilot home. From a checkout:

```bash
python3 bin/harness_select.py detect
python3 bin/harness_select.py install --harness copilot
```

`detect` reports which harness CLIs are on your `PATH` and prints the right next step for
each. The install defaults to `~/.copilot`; override it with `--copilot-home <dir>`, and add
`--dry-run` first to see every destination path without writing anything. A project can
also adopt the bundle by copying `copilot/.github/` into itself directly, if you would
rather have the configuration checked into the repo than materialized into a personal home.

**Precedence gotcha:** an agent under `~/.copilot/agents/` overrides a same-named agent
defined at the repo level, so a stale installed copy silently shadows an updated one until
you reinstall.

### Skills and agents are different surfaces

This bundle ships both, and they are not interchangeable:

- A **skill** steers the session you are already in. You can request one explicitly by
  typing `/name` in a prompt, and Copilot may also auto-load one on its own when your
  wording matches its `description:` closely enough. This is **not** a custom
  slash-command registry — there is no user-defined command grammar underneath, only a
  description being matched or a name being recognized. A skill carries no model pin, so it
  runs on whatever model the session already has selected, and the same skill reads very
  differently on a cheap model than on a strong one.
- An **agent** is an isolated persona you switch into — through the `/agent` picker, or a
  one-shot `copilot --agent <name> --prompt "<task>"` — and it *can* carry its own model
  pin in frontmatter.

### Managing installed skills in a session

- `/skills reload` — pick up newly installed or changed skills without restarting.
- `/skills` — open the management view to toggle skills on or off.
- `/skills list` — list every installed skill.
- `/skills info NAME` — show one skill's frontmatter and source path.

### Where to go next

- [route](route.md) is the front door; [budget](budget.md) is the one to know when credits
  are tight.
- [Deep dive: Copilot harness](../../deep-dives/copilot-harness.md) — install, model
  mechanics, and how AI Credits are accounted.
- The [Copilot documentation center](https://github.com/agentmc15/polytropos/blob/main/copilot-docs/README.md)
  — a task-oriented user guide with its own install, safety, and skills references.
- [Parity matrix](../index.md) — why this roster differs from the other two.
