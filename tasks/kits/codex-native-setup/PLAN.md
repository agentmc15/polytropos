# PLAN — codex-native-setup

## Goal

Make the Codex side of polytropos feel native, safe, and easy to install from a clone. A new
user should be able to discover the repository's Codex plugin, install its skills, optionally
materialize its custom agents at project or user scope, diagnose drift, and understand the next
step without copying files by hand or editing `config.toml`.

This kit plans the work only. It does not install into a real Codex home, invoke the real
`codex` CLI, publish a plugin, or implement an MCP service.

## Current-state findings

1. `codex/skills/` contains seven useful Codex skills, but the installer copies them into a
   Codex home with install-time absolute-path substitution. A moved clone or an older install can
   retain a stale repository path indefinitely.
2. `bin/harness_select.py install --harness codex` safely skips a differing skill directory, but
   its output does not distinguish a user-modified conflict from an older polytropos-managed
   install. The command therefore cannot refresh the stale installed skills observed during this
   planning run.
3. `codex/prompts/` remains the installer's required core even though official OpenAI
   documentation now marks custom prompts deprecated and recommends skills for reusable
   workflows.
4. The repository has no `.codex-plugin/plugin.json` and no Codex repo marketplace, so it is not
   installable through Codex's plugin browser. The existing `.claude-plugin/` files are
   Claude-specific and must remain independent.
5. The local `.codex/agents/` directory contains 84 untracked, kit-specific conversions of the
   84 Claude agents. They reference `.Codex/kits/...`, while this checkout has no such kit tree.
   They are useful migration evidence, not a distributable Codex agent catalog.
6. The committed Codex docs still say Codex has no custom-agent files and describe `/route`
   custom-prompt invocation. Current Codex supports project agents in `.codex/agents/*.toml`,
   user agents in `~/.codex/agents/*.toml`, `$skill` invocation, `/skills`, and `/plugins`.
7. Useful engines already support Codex but are not exposed as Codex skills: kit execution,
   context-weight analysis, benchmark-based routing, and the harness-neutral memory workflow.

## Official product basis

- OpenAI's plugin packaging contract requires `.codex-plugin/plugin.json`; a plugin can package
  skills, hooks, and MCP configuration, but custom agent TOML files are a separate Codex config
  surface.
- Repo marketplaces live at `.agents/plugins/marketplace.json`; Codex CLI and the desktop app
  expose plugins through `/plugins` or the Plugins directory.
- Project custom agents live at `.codex/agents/*.toml`; user agents live at
  `~/.codex/agents/*.toml`. Each agent requires `name`, `description`, and
  `developer_instructions`.
- Repo-local skills are discovered under `.agents/skills`; distributable groups of skills should
  be packaged as plugins. Custom prompts are deprecated compatibility surfaces.
- Repository-wide durable instructions belong in the root `AGENTS.md`; global guidance should
  not be written merely to configure one repository.

Primary references:

- <https://developers.openai.com/plugins/build/plugins>
- <https://learn.chatgpt.com/docs/agent-configuration/subagents>
- <https://learn.chatgpt.com/docs/build-skills>
- <https://learn.chatgpt.com/docs/agent-configuration/agents-md>
- <https://learn.chatgpt.com/docs/custom-prompts>

## Definition of done

1. The repository root is a valid skills-only Codex plugin through
   `.codex-plugin/plugin.json`, pointing at `./codex/skills/`, without changing the independent
   Claude plugin manifest or mixing harness pricing.
2. `.agents/plugins/marketplace.json` exposes that plugin from this repository using a
   repo-contained relative source path. A fresh Codex session can discover it after restart.
3. `codex/agents/` contains a small, generic Codex agent bundle for kit implementation,
   verification, phase review, and read-only exploration. The files omit hardcoded model ids and
   operate on any `tasks/kits/<slug>` kit rather than naming historical kits.
4. The installer supports explicit component and scope selection for Codex agents, skills,
   deprecated prompts, and guidance while preserving the old no-flags command's compatibility.
   It never writes `config.toml` or runs `codex`.
5. A read-only Codex doctor/plan command reports plugin readiness, marketplace validity, agent
   schema, skill inventory, legacy prompt state, stale path substitutions, managed-vs-user
   conflicts, exact proposed actions, and the required restart/new-session step.
6. Future copied installs carry a deterministic ownership manifest with source hashes. A refresh
   updates only unchanged polytropos-managed files; user-modified files remain untouched. Legacy
   unmarked installs can be adopted only when normalized content proves they came from this
   bundle. No force-overwrite path exists.
7. The seven current Codex skills work both from the plugin tree and through the legacy copied
   install. Literal placeholders and moved-clone paths fail with a clear doctor/remedy message,
   not a misleading command against an obsolete repository.
8. `execute` and `doctor` are first-class Codex skills. `architect`, `execute`, the generic agents,
   `bin/codex_execute.py`, and the docs agree on `tasks/kits/<slug>` and the exact status/task
   grammar.
9. Codex gets thin, harness-honest ports of `context-weight`, `bench-routing`, and `memory` that
   reuse the existing engines. Unsupported fidelity or live behavior remains explicitly
   unsupported rather than being simulated.
10. `codex/prompts/` is retained as deprecated CLI compatibility, is no longer presented as the
    primary or required core, and is opt-in for new installs. Prompt content does not drift from
    the corresponding canonical skills.
11. `README.md`, `SETUP.md`, and `docs/CODEX-HARNESS.md` provide one current quickstart, component
    matrix, update/doctor workflow, conflict recovery, plugin/agent/skill discovery instructions,
    and a legacy-install migration path.
12. Dedicated stdlib-only tests validate plugin paths, marketplace resolution, agent schema,
    installer planning and ownership behavior, path portability, skill parity, documentation
    commands, and absence of real-CLI/real-home access. The full unittest suite passes.

## Architecture decisions

### D1 — Use each native Codex surface for one job

- Root `AGENTS.md`: repository rules only.
- `.codex-plugin/plugin.json` + `codex/skills/`: reusable distributable workflows.
- `codex/agents/`: canonical source bundle for optional project/user agent materialization.
- `.codex/agents/`: installation destination only, never the canonical source in this kit.
- `codex/prompts/`: deprecated compatibility only.
- `bin/harness_select.py`: deterministic installer, plan, and doctor; never the policy source.

This avoids global guidance leakage and avoids claiming that plugin packaging installs custom
agents when the official plugin manifest has no agent component.

### D2 — Make the repository root the Codex plugin root

Add `.codex-plugin/plugin.json` at the repository root and point `skills` to
`./codex/skills/`. The repo marketplace may therefore point at `./` without duplicating skills,
scripts, or pricing data into a second plugin tree. All manifest paths stay repo-contained and
relative.

### D3 — Preserve the existing command, add explicit modern modes

`python3 bin/harness_select.py install --harness codex` remains accepted and retains safe
no-clobber behavior. New flags expose intent rather than changing hidden defaults:

- `--components plugin,agents,skills,prompts,guidance`
- `--agent-scope project|user`
- `--legacy-copy` for copied skills/prompts/guidance
- `--refresh-managed` for hash-proven polytropos-owned files only
- `--dry-run` and `--json`

Add a read-only `doctor --harness codex` command. The documented recommended path is the repo
marketplace/plugin plus project agents; legacy copied skills/prompts remain supported for CLI
compatibility and migration.

### D4 — Ownership-aware refresh, never blind overwrite

Write a small manifest under the explicitly selected Codex home only after a successful copied
install. It records relative destination, component, bundle version, normalized source digest,
and installed digest—never personal content. Refresh is allowed only when the current destination
still matches the recorded installed digest. An unmarked legacy skill may be adopted only if
placeholder-normalized bytes match a known bundle source. Otherwise report a conflict and leave it
untouched.

Updates are planned completely before writes, use temporary sibling files plus atomic replace,
and leave the ownership manifest unchanged if any write fails. Tests use temporary homes only.

### D5 — Generic agents instead of one agent family per historical kit

Ship four narrow roles: `kit-implementer`, `kit-verifier`, `phase-reviewer`, and
`repo-explorer`. They name no model id, pricing fact, historical slug, absolute path, or Claude
surface. Task briefs and explicit spawn parameters own model selection. The installer can copy
them to either `<repo>/.codex/agents/` or `<codex-home>/agents/` with the same ownership/no-clobber
rules.

The existing 84 untracked `.codex/agents` files are user-owned state. No task may delete, move,
or overwrite them silently. Doctor reports them as unmanaged/orphan-prone; project-scope install
must stop on name collisions and provide a precise manual archival/removal remedy.

### D6 — Plugin-native skills must also survive legacy copying

Canonical skill text must not depend on one machine's absolute repository path. Each skill states
one deterministic root-resolution procedure: use its plugin context when available; otherwise use
the installer-substituted root; otherwise stop and direct the user to doctor. Tests exercise a
repo plugin path, a moved plugin path, a copied managed skill, a stale copied skill, and a literal
placeholder.

Do not duplicate pricing data or calculation logic inside skills. All numeric/model facts remain
runtime-derived from `data/pricing.codex.json` through existing engines.

### D7 — Skills first; prompts are generated compatibility mirrors

The canonical reusable workflow is `codex/skills/<name>/SKILL.md`. Where a deprecated custom
prompt remains, a deterministic sync/check helper derives its body from the skill while adapting
frontmatter and skill-only metadata. No prompt becomes an independent source of behavior.

### D8 — Port only functionality with an honest Codex substrate

Include now:

- `execute`: the driver already exists and uses Codex pricing/tier resolution.
- `doctor`: directly improves installation, updates, and discoverability.
- `context-weight`: the engine already has an explicit Codex fidelity ladder.
- `bench-routing`: the engine already reads `pricing.codex.json` and reports Codex availability.
- `memory`: the engine is harness-neutral, gated, local-only, and budget-capped.

Do not port Claude's custom statusline setup: Codex has a built-in `/statusline`. Do not present
Claude-only context watch/constraint fidelity as available on Codex.

### D9 — Documentation and tests are part of the install contract

Every command shown in docs is asserted by parser tests or safe temp-root integration tests.
Docs distinguish desktop app, CLI, and IDE availability; restart/new-session expectations; plugin
installation versus agent materialization; and explicit invocation (`$skill`) versus implicit
skill matching.

## Out of scope

- Publishing or submitting polytropos to the public universal plugin directory.
- Adding an MCP server, connector, OAuth flow, hosted service, or custom UI.
- Automatically invoking `codex plugin ...`, `/plugins`, or any real model dispatch.
- Editing a real `~/.codex`, `~/.agents`, `config.toml`, or real installed plugin during tests or
  kit verification.
- Deleting or rewriting the current untracked `.codex/agents/` imports without separate user
  authorization.
- Changing Claude Code or Copilot bundle behavior, manifests, pricing, agents, or installation.
- Merging any of the three pricing files or hardcoding model ids, prices, ratios, plan facts, or
  reasoning ladders.
- A Codex adapter for `repo_bench.py`; that engine currently dispatches Claude candidates and
  requires its own spend-gated design.
- Plugin hooks that block or rewrite shell commands. Hooks require a separate trust and threat
  model.
- Replacing Codex's built-in statusline, memory, plugin browser, or agent UI.

## Risks and tripwires

### R1 — User-state loss

If an installer code path can overwrite a differing unproven destination, stop. There is no
`--force` escape hatch in this kit. Refresh requires hash-proven ownership; migration conflicts
remain manual.

### R2 — Real Codex spend or home access in tests

If a verify command can invoke `codex`, open a real home, or hit the network, stop. All CLI
behavior is parser/pure-function tested with temporary roots and injected PATH fixtures.

### R3 — Plugin/agent conflation

If docs or output claim installing the plugin also installs custom agents, stop. Plugin skills
and agent TOML files are separate native mechanisms and must be reported separately.

### R4 — Cross-harness leakage

If Codex content reads `data/pricing.json` or `data/pricing.copilot.json`, contains Claude model
aliases, or changes `.claude-plugin/`/`copilot/`, stop.

### R5 — Placeholder or moved-clone regression

If any installed skill can silently run an old absolute repository path, stop. Root resolution
must either prove the current plugin/copied root or fail with doctor instructions.

### R6 — Agent catalog bloat

If the distributable agent bundle grows per historical kit or injects all 84 legacy agent
descriptions into every session, stop. Keep four generic roles and let active kit briefs carry
specifics.

### R7 — Prompt resurrection

If a new workflow is implemented only as a custom prompt or docs again describe `/route` as the
primary invocation, stop. Skills are canonical; prompts are opt-in compatibility.

## Recommended follow-on functionality

These are good Codex additions after this kit, but are deliberately not bundled into the core
installation work:

1. **Codex-native repo benchmark adapter.** Extend `repo_bench.py` behind the existing
   `--live` plus `--max-usd` gates with an injected Codex runner and Codex-only pricing. This
   needs an independent leak/spend review.
2. **Optional trusted verification hook.** Package a disabled-by-default Codex lifecycle hook
   that records whether a kit task's verify command actually ran. Do not block commands until the
   hook trust and bypass model has been reviewed.
3. **Plugin presentation assets.** Add icon, screenshots, starter prompts, homepage, and legal
   metadata when the plugin is ready for team or public distribution.
4. **Automation templates.** Offer daily journal collection and stale-install checks as opt-in
   Codex automations; keep private stores gitignored and never transmit transcript text.
5. **Codex fidelity upgrades for context analysis.** Improve `context_weight.py` only when local
   Codex logs expose reliable attribution/compaction events; preserve the current honesty ladder
   until then.
6. **One unified harness doctor.** Once the Codex doctor proves useful, generalize its pure
   inventory/report model across Claude, Copilot, and Codex without merging their install or
   pricing semantics.

## Overall verification

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 bin/harness_select.py doctor --harness codex --repo-root . --codex-home /tmp/polytropos-codex-doctor --json
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home /tmp/polytropos-codex-install --dry-run --json
```

The two CLI smokes must be read-only and must not require a real Codex executable or account.
