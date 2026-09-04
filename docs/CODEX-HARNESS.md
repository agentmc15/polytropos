# The Codex harness

Polytropos packages twelve native Codex skills for routing, usage and context analysis, and
verified execution workflows. It also ships four optional agent roles. Skills, plugin installation,
and agent roles are separate surfaces: installing the plugin does not install the agents.

Use Python 3.11 or newer for setup and verification, so the standard-library TOML parser is
available. The examples assume `python3` selects that interpreter.

## Install a registered plugin

The setup planner validates package files and can install optional agent roles. It cannot register
or enable the plugin, prove activation, or refresh Codex's cached package. Use the host CLI for a
fresh plugin installation:

```bash
codex plugin marketplace add /path/to/polytropos
codex plugin add polytropos@polytropos-local
codex plugin list --marketplace polytropos-local --json
```

These commands describe the current supported Codex CLI interface. They are a manual live step,
not part of the automated test suite. The installed plugin is a registered cached package; do not
assume it reads a changed live checkout. Restart or begin a new session after installation.

In clients that expose `/plugins`, that command opens plugin management.
In Codex CLI and supported IDE clients, open `/skills` or invoke a workflow with `$route`.
Codex Desktop may offer a skill selector in versions that support it. Do not expect a custom bare
`/route` alias. Skill descriptions can also let Codex select a workflow implicitly.

## Package preparation and optional agents

The following is safe to preview and uses only the roots supplied on its command line. It reports
package **readiness** from the local manifest and marketplace, while runtime **activation** stays
`unknown` until the host provides evidence. It does not install or enable the plugin.

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project
python3 bin/harness_select.py doctor --harness codex --repo-root . --codex-home <codex-home>
```

Project roles are written to `.codex/agents/`; `--agent-scope user` instead uses the explicit
Codex home. They are optional delegated-work roles, separate from selecting a skill. The shipped
roles are `kit-implementer`, `kit-verifier`, `phase-reviewer`, and `repo-explorer`.

| Component | Canonical source | Purpose |
|---|---|---|
| Plugin skills | `codex/skills/*/SKILL.md` | `/skills`, `$name`, and description matching |
| Agent roles | `codex/agents/*.toml` | Optional delegated implementation and review |
| Prompt mirrors | `codex/prompts/*.md` | deprecated compatibility mirrors |
| Plugin metadata | `.codex-plugin/plugin.json` | Package content, not installation evidence |

`.agents/skills` is a documented standalone local-skill discovery location. `.codex/skills` is
observed compatibility behavior. This package does not install both trees or use either as a
second default skill source; `codex/skills` remains the canonical package content.

## Skills

| Skill | Purpose |
|---|---|
| `$architect` | Plan a complex change as `tasks/kits/<slug>` |
| `$bench-routing` | Compare benchmark priors with dispatchable role recommendations |
| `$context-weight` | Analyze context growth and resident-surface weight |
| `$doctor` | Diagnose package, agents, copies, ownership, and stale paths read-only |
| `$effort` | Choose runtime-derived reasoning effort for one run |
| `$escalate` | Try the cheapest sufficient tier behind a verification gate |
| `$execute` | Run an architected kit through verification and review |
| `$frontier-check` | Decide whether the frontier tier is justified |
| `$journal` | Build the cross-harness daily work journal |
| `$memory` | Recall a bounded, relevance-gated set of private facts |
| `$route` | Pick the cheapest sufficient Codex tier with honest billing framing |
| `$usage` | Analyze local Codex usage read-only |

Use `$architect` before `$execute`; `$route` and `$effort` have distinct jobs. Pricing, model
availability, and effort levels are derived at runtime from `data/pricing.codex.json`. Under a
ChatGPT plan, dollar figures are API-equivalent burn proxies, not bills.

## Legacy copied surfaces

Copying skills, prompts, or global guidance is opt-in compatibility behavior. It never overwrites
an unproven user edit:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components skills,prompts,guidance --legacy-copy --dry-run
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components skills,prompts,guidance --legacy-copy
```

`codex/prompts/` contains deprecated compatibility mirrors; native `$route`, not a bare `/route`, is canonical. The
ownership-aware updater refreshes unchanged managed copies and preserves conflicts. Default
installation prepares native package metadata and agents. Updates may also refresh existing owned
legacy copies, but do not recreate absent or retired copies.

For a previously managed legacy copy that is still unchanged, preview and then refresh it with
`--refresh-managed`; a differing file remains a conflict:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components prompts --legacy-copy --refresh-managed --dry-run
```

Retirement is preview-only by default. It accepts prompts and optionally skills, requires explicit
operator evidence that the native replacement works before mutation, backs up proven copies outside
the supplied discovery roots, and leaves edited or unknown files untouched:

```bash
python3 bin/harness_select.py retire-legacy --harness codex --repo-root . --codex-home <codex-home> --backup-root <backup-root> --components prompts,skills
python3 bin/harness_select.py retire-legacy --harness codex --repo-root . --codex-home <codex-home> --backup-root <backup-root> --components prompts,skills --native-skills-confirmed --apply
python3 bin/harness_select.py restore-legacy --harness codex --repo-root . --codex-home <codex-home> --backup-root <backup-root>
```

Restore requires the same repository, Codex-home, and backup roots. It refuses an occupied or
edited destination and tampered backups. A conflict blocks a retirement batch before any copy is
removed.

## Manual live smoke checklist

Automated verification uses temporary roots and cannot prove a client UI. After a separately
authorized live rollout, record:

1. Codex client and version.
2. The registered and enabled `polytropos@polytropos-local` plugin and its marketplace.
3. A `$route` selection in `/skills`, or the desktop selector when that version offers one.
4. The loaded package source path reported by the client.
5. The absence of duplicate same-named legacy skills or prompts.

This checklist has not been performed by automated verification.

## Good next Codex additions

- A Codex adapter for the existing repo-bench engine, with the same explicit spend ceiling.
- An optional trusted verify hook, opt-in because it changes runtime behavior.
- Automation templates for recurring doctor, journal, or telemetry checks.
- Plugin icons and richer presentation assets.
- Better context-fidelity analysis if Codex logs expose provenance.

Codex's built-in `/statusline` covers the interactive status surface and does not need to be ported.

## Official references

- [Build plugins](https://learn.chatgpt.com/docs/build-plugins)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Custom prompts (deprecated)](https://learn.chatgpt.com/docs/custom-prompts)
