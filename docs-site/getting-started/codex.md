# Getting started on OpenAI Codex CLI

Polytropos ships native Codex skills in a plugin package. Package preparation validates the local
bundle; it does not show that Codex has installed, enabled, or loaded the package.

Use a current Codex client, Git, and Python 3.11 or newer. For the setup commands below,
`python3` must select that interpreter.

## Install

From a checkout, register the marketplace and install the package with the current Codex CLI:

```bash
codex plugin marketplace add /path/to/polytropos
codex plugin add polytropos@polytropos-local
codex plugin list --marketplace polytropos-local --json
```

The plugin is registered as a cached package, so installation does not promise that it rereads a
live checkout. Start a new session after installation. In CLI and supported IDE clients, use
`/skills` or `$route`; a Desktop skill selector is available only in versions that expose it.

Preview optional agent-role setup separately. It does not call Codex or register the plugin:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run
python3 bin/harness_select.py doctor --harness codex --repo-root . --codex-home <codex-home>
```

The report distinguishes a ready package from runtime activation, which remains `unknown` without
host evidence. See the [Codex harness deep dive](../deep-dives/codex-harness.md) for agents,
legacy migration, and the manual smoke checklist.

## Your first invocation

Use the native skill sigil:

```
$route add input validation to the signup handler
```

Do not rely on a bare `/route` alias. Codex may also select a skill from its description.
`codex/prompts/` is a deprecated compatibility namespace.

Pricing and effort choices come from `data/pricing.codex.json` at runtime. Plan runs are
usage-limited; any dollar figure there is an API-equivalent burn proxy. API-key runs are
token-metered dollars.
