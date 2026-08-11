# The Codex harness

Polytropos is a repo-local Codex skills plugin for model routing, usage/context analysis, and
verified execution workflows. It also ships four optional custom-agent definitions. Skills and
agents are separate Codex surfaces: installing the plugin does not install the agents.

## Quickstart from a fresh clone

1. Open this repository in Codex and restart Codex so it discovers the repo marketplace at
   `.agents/plugins/marketplace.json`.
2. Open `/plugins`, find **Polytropos Local**, and install/enable **Polytropos**.
3. Open `/skills` and confirm the twelve skills below appear. Invoke one explicitly with `$route`,
   or let Codex select a skill from its description when your request matches.
4. Optionally preview and install project agents:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project
```

Project agents land in this checkout's `.codex/agents/`. For user-scoped agents, choose
`--agent-scope user`; they land beneath the explicitly supplied Codex home. Start a new task after
changing agents, then use `/agent` to select or inspect the available role.

## What loads where

| Component | Source | Codex surface | Scope and lifecycle |
|---|---|---|---|
| Repository guidance | root `AGENTS.md` | desktop, CLI, IDE | Loaded as repository instructions; never installed by the plugin |
| Plugin skills | `codex/skills/*/SKILL.md` | `/skills`, explicit `$name`, implicit matching | Canonical workflows, loaded from this repo plugin |
| Custom agents | `codex/agents/*.toml` | `/agent` | Optional project or user copies; separate from plugin install |
| Custom prompts | `codex/prompts/*.md` | legacy CLI prompt palette | Deprecated generated compatibility mirrors, not workflow sources |
| Ownership data | `<codex-home>/polytropos/install-manifest.json` | setup/doctor only | Hashes and metadata for deliberate copied installs; no prompt content or credentials |
| Plugin catalog | `.agents/plugins/marketplace.json` | `/plugins` | Repo marketplace pointing to the root `.codex-plugin/plugin.json` |

Codex desktop, CLI, and IDE support can evolve independently. Treat `/plugins`, `/skills`, and
`/agent` in the Codex surface you are using as authoritative; the compatibility prompts exist for
older CLI workflows only.

## Skills

| Skill | Purpose |
|---|---|
| `$architect` | Plan a complex change once as `tasks/kits/<slug>` |
| `$bench-routing` | Inspect benchmark priors and Codex-dispatchable role recommendations |
| `$context-weight` | Analyze rollout growth and resident-surface weight at honest Codex fidelity |
| `$doctor` | Diagnose plugin, agent, copied-surface, ownership, and stale-path state read-only |
| `$effort` | Choose the runtime-derived reasoning-effort level for one run |
| `$escalate` | Try the cheapest sufficient tier behind a verify gate |
| `$execute` | Continue an architected kit through status, dry-run, run, verify, and review |
| `$frontier-check` | Decide whether the runtime frontier tier is justified |
| `$journal` | Build the cross-harness daily work journal with dry-run safeguards |
| `$memory` | Pull a bounded, relevance-gated set of private local facts |
| `$route` | Pick the cheapest sufficient Codex tier and frame API cost or subscription burn honestly |
| `$usage` | Analyze local Codex usage read-only, priced only when logs support it |

The four optional agents are `kit-implementer`, `kit-verifier`, `phase-reviewer`, and
`repo-explorer`. They deliberately carry no model or reasoning-effort pin; explicit delegation or
the parent task chooses those values.

## Preview, diagnose, install, and update

Doctor and dry-run are byte-read-only:

```bash
python3 bin/harness_select.py doctor --harness codex --repo-root . --codex-home <codex-home>
python3 bin/harness_select.py doctor --harness codex --repo-root . --codex-home <codex-home> --json
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run --json
```

The action states are `install`, `up-to-date`, `managed-update`, `conflict`, `unmanaged`, and
`skip`. The plugin action never calls Codex; it validates the checked-in marketplace and tells you
to restart, open `/plugins`, and enable Polytropos.

For a previously managed copy whose destination is still byte-identical to the recorded install,
preview and then request a refresh:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components agents --agent-scope user --refresh-managed --dry-run
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components agents --agent-scope user --refresh-managed
```

There is no force mode. A user-edited managed file or unrelated collision is a conflict and is
preserved. Merge or rename it manually, rerun doctor, and start a new task after the state is
clean. The installer never overwrites `config.toml` and no recovery step deletes an entire Codex
home.

## Architect to execute

Use `$architect` to create a kit, then inspect it without spending model usage:

```bash
python3 bin/codex_execute.py status --kit tasks/kits/<slug>
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --dry-run
```

Continue with `$execute` or a real driver run only after approving the dispatch. A non-dry
`run`/`review` launches headless Codex and spends subscription usage or API-metered funds. The
generic agents are convenient for interactive delegation but are not required by the driver.

Routing, effort, usage, and journal values are derived at runtime from
`data/pricing.codex.json`; subscription dollar figures remain labeled API-equivalent relative-burn
proxies, never bills. `$context-weight` preserves Codex's no-content-provenance limit,
`$bench-routing` preserves benchmark transcription limitations, and `$memory` injects only
relevance-gated budget winners.

## Legacy copied installs and custom prompts

The old command remains compatible:

```bash
python3 bin/harness_select.py install --harness codex --codex-home <codex-home> --dry-run
```

It copies prompts, guidance, and skills under no-clobber rules. New installations should prefer
the root plugin. To retain copied surfaces deliberately under ownership tracking, opt in:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components skills,prompts,guidance --legacy-copy --dry-run
```

Prompts are deprecated compatibility mirrors generated by `bin/sync_codex_surfaces.py`; `$route`
is canonical, not bare `/route`. `python3 bin/sync_codex_surfaces.py check` detects drift without
writing. A known old absolute repo path can be adopted only when normalization proves it matches a
current source. Unknown content stays unmanaged/conflicted and is never overwritten.

## Official Codex references

- [Build plugins](https://developers.openai.com/plugins/build/plugins)
- [Custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Custom prompts (deprecated)](https://learn.chatgpt.com/docs/custom-prompts)

## Good next Codex additions

- A Codex adapter for the existing repo-bench engine, with the same explicit spend ceiling.
- An optional trusted verify hook; opt-in only, because hooks are runtime behavior.
- Automation templates for recurring doctor, journal, or telemetry checks.
- Plugin icons/screenshots and richer presentation assets.
- Better context-fidelity analysis if Codex logs eventually expose provenance.

Codex's built-in `/statusline` already covers the interactive status surface, so Claude's custom
statusline setup does not need to be ported.
