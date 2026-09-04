### Installing

The Codex side is a repo-local plugin, so Codex loads it from the checkout rather than from
a copied install:

1. Open this repository in Codex and restart Codex so it discovers the repo marketplace at
   `.agents/plugins/marketplace.json`.
2. Open `/plugins`, find **Polytropos Local**, and install and enable **Polytropos**.
3. Open `/skills` and confirm the skills above appear.

If something does not show up, `$doctor` diagnoses the install read-only before you change
anything.

### Invoking a skill

Ask for one explicitly with `$name` — `$route`, `$execute`, `$doctor` — or simply describe
what you want and let Codex select a skill by matching your request against the skill
descriptions. Note the sigil: `$route` is the canonical form, **not** a bare `/route`.
Custom prompts under `codex/prompts/` are deprecated compatibility mirrors kept for older
CLI workflows; they are generated, never a workflow source.

### Agents are a separate, optional surface

Installing the plugin does not install the agents. The four optional role agents are
previewed and installed explicitly, and preview is byte-read-only:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project
```

Project-scoped agents land in this checkout's `.codex/agents/`; `--agent-scope user` puts
them under the Codex home you supply instead. Start a new task after changing agents, then
use `/agent` to select or inspect a role. The agents deliberately carry no model or
reasoning-effort pin — explicit delegation or the parent task chooses those.

Treat `/plugins`, `/skills`, and `/agent` in whichever Codex surface you are using
(desktop, CLI, or IDE) as authoritative; support for each can evolve independently.

### Where to go next

- [route](route.md) is the front door; [doctor](doctor.md) is what to run when the install
  looks wrong.
- [Deep dive: Codex harness](../../deep-dives/codex-harness.md) — what loads where, the
  install and refresh command set, and the ownership rules that keep your edits.
- [Parity matrix](../index.md) — why this roster differs from the other two.
