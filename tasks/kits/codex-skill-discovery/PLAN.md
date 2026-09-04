# Codex native skill discovery

## Goal and scope

Make Polytropos discoverable as native Codex skills and stop normal installation and
updates from bringing back deprecated `prompts:<name>` entries. This is a follow-up to
the implemented `codex-native-setup` kit, not a replacement architecture. Planning used
the user-requested Astra planner. Implementation is not authorized by this planning run.

## Audit evidence — 2026-09-04

- Baseline: `main` at `6e25a38`, synchronized with `origin/main` before this audit.
- The repository already contains `.codex-plugin/plugin.json`, a local marketplace,
  twelve `codex/skills/*/SKILL.md` workflows and four generic `codex/agents/*.toml` roles.
  None of the twelve skills has `agents/openai.yaml` presentation metadata.
- Native skills are loaded in this conversation from the personal Codex skills directory.
  The user's `architect` skill is present; the reported prompt entry is not proof of
  missing native skills. No visual inspection of the picker was performed.
- Read-only doctor found twelve copied skills (eight matching, four differing), ten
  copied prompts (seven matching, three differing), four matching project agents, and
  differing global guidance. Differing files are conflicts, not proven obsolete copies.
  Private file contents and absolute home paths are intentionally omitted here.
- `harness_select.cmd_install` falls back to `install_codex` when modern flags are absent.
  That legacy copier installs prompt files and writes their contents unconditionally.
- `harness_update.apply_codex_target` also uses that legacy copier. Updating can therefore
  recreate prompt entries and overwrite differing prompt content.
- `plan_codex_setup` reports plugin `up-to-date` when repository metadata validates;
  `doctor_codex` does not establish actual installation, enablement, or loaded skills.
- `codex/AGENTS.md` still describes `/route` and other workflows as prompts, despite the
  skills-first quickstart. Some installer docstrings claim prompts are required core.

## Supported product behavior

Official sources fetched during this audit:

- [Build skills](https://learn.chatgpt.com/docs/build-skills): Codex CLI/IDE support
  `/skills` and `$` selection; implicit matching uses descriptions. Optional
  `agents/openai.yaml` supplies presentation and invocation policy. Documented local
  discovery includes repository/user `.agents/skills`; this session also demonstrates
  compatibility loading from `.codex/skills`. Duplicate names are not merged.
- [Custom prompts](https://learn.chatgpt.com/docs/custom-prompts): deprecated; skills
  are the supported replacement for reusable workflows.
- [Build plugins](https://learn.chatgpt.com/docs/build-plugins): package related skills
  in a plugin; install from a local marketplace and test in a fresh conversation.
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents): delegated
  agent work is a separate capability; `/agent` inspects running CLI agent conversations.

The recommended experience is skill selection and native invocation, distributed by the
existing plugin. Do not promise a custom bare `/architect` command or identical selectors
across desktop, CLI, and IDE. Skill UI metadata is not a custom-agent definition. Native
agent roles remain useful for delegated implementation/review; converting every skill
into an agent would not fix prompt discovery.

## Architecture decisions

1. Keep `codex/skills` canonical and the existing plugin package. Do not create another
   skill tree, MCP wrapper, alias layer, or custom command framework. Local `.agents/skills`
   is a documented alternative for authoring, not an additional default install here.
2. Report package readiness separately from runtime activation. Add explicit diagnostic
   fields for package readiness and activation=`unknown` unless supported evidence is
   available. Do not infer installed/enabled status from a valid manifest or a config default.
   Inventory known copies and report potential duplicate exposure, without guessing precedence.
3. Route all normal Codex installer/update paths through the ownership-aware planner.
   Native default remains plugin preparation plus the existing optional agent component
   selection. Copying skills, prompts, or global guidance requires explicit legacy intent.
   Ordinary updates may refresh unchanged owned copies, but cannot recreate retired copies.
4. Provide an explicit reversible retirement command for proven legacy prompts and, when
   a replacement is confirmed, copied skills. Use the existing ownership hashes or exact
   current-source normalization as evidence. Names and deprecation banners are insufficient.
   Backup outside discovery paths, retain a restoration manifest, and never alter conflicts.
5. Add concise UI names, descriptions and starter prompts to every skill. Keep workflow
   behavior and model choice in existing skills/kit dispatch; do not pin models in UI YAML.
6. Update current guidance and generated documentation together. Retain historical kits and
   generated compatibility prompts as explicitly deprecated sources; do not rewrite history.

## Definition of done

- Default CLI install and update do not write prompt files or global guidance. Explicit
  legacy installation remains supported and cannot overwrite unproven edits.
- Doctor distinguishes valid package metadata, unknown activation, copied skills/prompts,
  conflicts, and possible duplicate surfaces. Missing optional legacy copies are not failures.
- Explicit retirement has byte-read-only preview, digest revalidation, backup/restore,
  conflict preservation, containment checks, failure rollback, and repeat-run idempotence.
- Every shipped skill has valid presentation metadata, a native starter invocation, and
  a useful description. Generated prompt mirrors remain consistent with canonical skills.
- Documentation explains selection by client, installation versus activation, refresh versus
  cleanup, and the separate purpose of agent roles. Tests exercise all installation modes
  with temporary homes and synthetic bundles, including update after retirement.
- A documented live smoke procedure records the client/version, plugin source, selected skill
  and loaded path. Automated tests cannot prove UI appearance. Actual live installation and
  UI verification remain a separately authorized rollout, clearly reported as unperformed.

## Boundaries and tripwires

Plan delivery changes only this kit's PLAN.md and TASKS.md. Execution changes Codex-specific
installer/updater behavior, metadata, docs, and their tests. Do not modify pricing, Claude or
Copilot behavior, real home directories, local config, installed plugins, user-owned agents,
or global AGENTS.md. No publishing, real model dispatch, new dependency, or invented slash alias.

Use stdlib Python tests, temporary explicit roots, and mocked external operations. Never run a
real `codex`, `claude`, or `copilot` in verification. A valid package is not proof of a working
replacement: skill retirement requires explicit recorded confirmation. Unknown ownership,
symlinks, path escapes, changed digests, or backup failures must preserve originals. Keep
retirement records distinct from task `status`, whose vocabulary remains unchanged.

## Routing

Authentication observed: ChatGPT sign-in. Astra is absent from the repository pricing roster,
so its burn is unpriced; do not substitute Sol pricing for Astra or modify pricing in this kit.
For implementation, the pricing engine's M-profile comparisons are: mid 10x cheapest with
$0.2640 API-equivalent proxy; strong resolves upward to frontier at 25x with $0.6600 proxy.
These are relative-burn aids, not subscription bills or quota estimates, and not a kit total.
Recompute from data at dispatch. T1/T2/T3 use strong for cross-component state and migration
reasoning; T4/T5 use mid for bounded metadata/docs/integration work. No direct frontier pin.

The execute driver chooses implementation models. A standalone repeat of this planning request
can use `codex exec --model gpt-6-astra 'Use $architect to audit Codex skill discovery and write a follow-up kit only.'`;
this command is documentation, was not executed, and is not a verify command.
