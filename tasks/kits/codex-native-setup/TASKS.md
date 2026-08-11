# TASKS — codex-native-setup

Repository root: `/path/to/polytropos`.
Run every verify command from that directory. Read this kit's `PLAN.md` before changing files.

Status vocabulary is exactly:
`pending | in-progress | done | blocked`.

Standing rules for every task:

- Never invoke a real `codex`, `claude`, or `copilot` executable. Documentation may show commands;
  tests and verify commands must not execute them.
- Never read or write a real `~/.codex`, `~/.agents`, `~/.claude`, or `~/.copilot`. Every installer
  and doctor test passes explicit temporary roots.
- Never edit `config.toml`, install/enable a real plugin, connect an MCP server, access the network,
  or publish anything.
- Python under `bin/` and `tests/` is stdlib-only. No pip, requirements file, pytest, Node, or npm.
- `data/pricing.codex.json` is the only Codex numeric/model authority. Do not edit it in this kit
  and never hardcode its model ids, prices, ratios, plan facts, cached date, or reasoning ladder.
- Do not read the Claude or Copilot pricing files from Codex runtime content. Do not edit
  `.claude-plugin/`, `copilot/`, Claude skills/agents, or their tests.
- Preserve all unrelated dirty-worktree changes. In particular, the existing repo-bench and
  `copilot-docs/` edits are outside this kit.
- The current root `AGENTS.md` and `.codex/agents/` are untracked user-owned files. Do not delete,
  replace, move, or normalize them. Canonical installable agent sources belong in
  `codex/agents/`; tests use temp destinations.
- If a pinned file, function, parser seam, or anchor is absent beyond a shifted line number, stop
  and report the discrepancy rather than inventing a substitute.

## Phase 1 — Native packaging and agent contract

### T1 — Package the repository as a Codex skills plugin

- id: `codex-plugin-package`
- title: Add the Codex plugin manifest, repo marketplace, and structural validation
- status: done
- model: mid
- depends: (none)
- independent: yes

**Brief.**

Make the repository root a valid skills-only Codex plugin without changing the existing Claude
plugin. Add a repo marketplace that exposes the root plugin and prove every declared path is
relative, contained, and resolvable.

**Sanctioned files**

- `.codex-plugin/plugin.json` (new)
- `.agents/plugins/marketplace.json` (new)
- `tests/test_codex_plugin.py` (new)

**Frozen files**

Everything else, especially `.claude-plugin/`, `codex/skills/`, `codex/prompts/`, `.codex/`,
`AGENTS.md`, installers, docs, and pricing files.

**Pinned behavior**

1. `.codex-plugin/plugin.json` uses the stable plugin name `polytropos`, a semver version, an
   accurate Codex-focused description, existing repository/license/author facts, and
   `"skills": "./codex/skills/"`.
2. Do not declare agents, MCP servers, apps, hooks, or capabilities that do not exist.
3. `.agents/plugins/marketplace.json` is a repo marketplace whose one entry points at `./` as a
   local source and gives the plugin a human-readable display name and description.
4. Every path begins `./`, stays within the repository root after resolution, and exists.
5. Tests parse JSON with stdlib, validate required manifest fields, semver shape, marketplace
   identity/source, skill directory existence, and absence of Claude/Copilot pricing references.
6. Tests assert the Claude manifest and marketplace still parse and were not repurposed as Codex
   manifests.
7. No test reads a home directory or runs a command.

**Acceptance.**

- Both Codex metadata files exist and resolve the repository's existing Codex skill tree without
  copying it.
- The plugin declares only implemented components.
- Structural, containment, and harness-separation tests pass.
- No pre-existing file changed.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_plugin.py' -v
```

### T2 — Create a small generic Codex agent bundle

- id: `codex-agent-bundle`
- title: Add reusable kit agents and strict schema tests
- status: done
- model: mid
- depends: (none)
- independent: yes

**Brief.**

Create the canonical source bundle for four optional Codex custom agents. These are generic roles
for current `tasks/kits/<slug>` execution, not conversions of historical Claude kit agents.

**Sanctioned files**

- `codex/agents/kit-implementer.toml` (new)
- `codex/agents/kit-verifier.toml` (new)
- `codex/agents/phase-reviewer.toml` (new)
- `codex/agents/repo-explorer.toml` (new)
- `tests/test_codex_agents.py` (new)

**Frozen files**

Everything else. Do not touch the current `.codex/agents/` destination or `.claude/agents/`.

**Pinned behavior**

1. Each TOML file has `name`, `description`, and multiline `developer_instructions` and parses
   with `tomllib` when available; tests may use a small stdlib fallback assertion on older Python.
2. Names are exactly `kit-implementer`, `kit-verifier`, `phase-reviewer`, and `repo-explorer` and
   match their filenames.
3. No file pins `model`, `model_reasoning_effort`, a price, a model id, or a home/repository
   absolute path. Explicit spawn values or the parent session own model/effort.
4. `kit-implementer` executes exactly one self-contained task, respects PLAN fences, runs the
   task's verify command, does not write status/NOTES, and stops on a real brief/repo conflict.
5. `kit-verifier` is read-only, reruns verify independently, checks every acceptance bullet and
   out-of-fence changes, and reports PASS/FAIL without fixing.
6. `phase-reviewer` is read-only and reviews one completed phase for fence, invariant, pinned
   content, plan drift, and weak verification.
7. `repo-explorer` is read-only, bounded, evidence-first, and returns concise file/symbol findings
   without editing or proposing a fix unless asked.
8. Every kit role uses `tasks/kits/<slug>` and the exact status vocabulary
   `pending | in-progress | done | blocked`.
9. Tests reject `.Codex/kits`, `.claude/kits`, `/path/to/polytropos`, another harness's agent
   vocabulary, agent count drift, or any model/config pin.

**Acceptance.**

- Exactly four canonical agent source files exist and satisfy the official required schema.
- The agents are reusable across kits and carry no stale kit slug or model pin.
- The current untracked `.codex/agents/` tree is byte-untouched.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_agents.py' -v
```

## Phase 2 — Safe installer, doctor, and portable surfaces

### T3 — Build component-aware planning, doctor, and managed refresh

- id: `codex-setup-engine`
- title: Extend the installer with scopes, ownership, doctor, JSON, and atomic refresh
- status: done
- model: strong
- depends: T1, T2
- independent: no

**Brief.**

Extend `bin/harness_select.py` rather than creating a second installer. Preserve existing
Claude/Copilot behavior and the old no-flags Codex install contract, then add explicit modern
Codex component/scope selection, a read-only doctor, and ownership-aware refresh. All behavior
must be testable through pure functions with temporary roots and injected PATH state.

**Sanctioned files**

- `bin/harness_select.py`
- `tests/test_codex_setup.py` (new)
- `tests/test_codex_bundle.py` (only assertions needed to preserve or clarify existing Codex
  compatibility)
- `tests/test_harness_select.py` (only regression coverage for unchanged non-Codex behavior)

**Frozen files**

Everything else, including manifests, bundle content, agents, docs, pricing, and real homes.

**CLI contract**

1. Preserve:
   `python3 bin/harness_select.py install --harness codex [--codex-home PATH] [--dry-run]`.
   With no new flags it must retain current safe legacy-copy behavior and output compatibility.
2. Add to Codex install only:
   - `--repo-root PATH` (default production repository root; tests pass temp roots),
   - `--components` as a comma-separated subset of
     `plugin,agents,skills,prompts,guidance`,
   - `--agent-scope project|user`,
   - `--legacy-copy`,
   - `--refresh-managed`,
   - `--json`.
3. Add:
   `python3 bin/harness_select.py doctor --harness codex [--repo-root PATH]
   [--codex-home PATH] [--json]`.
4. Reject nonsensical combinations before any write: project agents without a repo root, copied
   skills/prompts/guidance without `--legacy-copy`, refresh without a destination home, unknown or
   duplicate components, and non-Codex-only flags on other harnesses.

**Planning and doctor behavior**

5. Build one pure action plan before writing. Each action records component, source, destination,
   state (`install`, `up-to-date`, `managed-update`, `conflict`, `unmanaged`, `skip`), reason, and
   source/destination digest where applicable.
6. Doctor validates plugin manifest/marketplace resolution, canonical agent schema, skill roster,
   deprecated prompt roster, ownership manifest, stale absolute repo references, literal
   placeholders, managed drift, unmanaged collisions, and restart/new-session requirements.
7. Plugin component setup never calls `codex`: it validates the checked-in repo marketplace and
   reports the human next step (`restart`, open `/plugins`, install/enable Polytropos).
8. Agent destinations are `<repo-root>/.codex/agents/` for project scope and
   `<codex-home>/agents/` for user scope. Existing differing files are conflicts unless ownership
   rules prove a managed update.

**Ownership and write safety**

9. A copied install writes a versioned JSON ownership manifest beneath the explicitly passed
   Codex home. It contains component/relative destination, bundle version, normalized source hash,
   and installed hash only—no file contents, transcript data, or credentials.
10. `--refresh-managed` updates only when the current destination hash matches the recorded
    installed hash. If a user edited a managed file, report conflict and preserve it.
11. Legacy unmarked polytropos files may be adopted only when a normalization function can replace
    the embedded repository root with the canonical placeholder and prove byte equivalence to a
    current/recognized source. Ambiguity is a conflict.
12. There is no `--force`. No differing unproven destination is overwritten or deleted.
13. Writes use temporary sibling files and `Path.replace`; the ownership manifest is written last.
    A simulated mid-write failure leaves pre-existing destinations and the prior ownership
    manifest unchanged.
14. `--dry-run`, doctor, and JSON rendering are byte-read-only. Stable ordering makes JSON and
    text deterministic.

**Tests**

- parser compatibility and every new option/invalid combination;
- plugin/marketplace ready, missing, malformed, and escaping-path states;
- project/user agent destinations and collisions;
- clean install, idempotent reinstall, managed refresh, user-modified managed conflict;
- recognized legacy adoption, stale-root detection, ambiguous/unrelated conflict;
- atomic failure rollback and manifest-last behavior;
- text/JSON stable ordering and no secrets/content in ownership records;
- doctor/dry-run before/after tree snapshots proving no writes;
- static/runtime guards proving no real CLI, network, `Path.home()` in pure seams, or implicit
  real-home access;
- all existing Claude, Copilot, and Codex installer tests remain green.

**Acceptance.**

- The existing command remains safe and compatible.
- New users get a deterministic plan/doctor; managed installs can update without clobbering user
  changes; stale/unmanaged installs receive an exact remedy.
- No test or verify path touches real user state or launches a harness CLI.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_setup.py' -v && python3 -m unittest discover -s tests -p 'test_harness_select.py' -v && python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v
```

### T4 — Make skills canonical and prompts generated compatibility mirrors

- id: `codex-portable-skills`
- title: Remove silent path staleness and enforce skill-first prompt parity
- status: done
- model: mid
- depends: T1, T3
- independent: no

**Brief.**

Make the existing seven Codex skills work from the root plugin and from a managed legacy copied
install without silently using an obsolete absolute repository path. Make deprecated prompts
generated/checkable compatibility mirrors rather than independent workflow sources.

**Sanctioned files**

- `codex/skills/architect/SKILL.md`
- `codex/skills/effort/SKILL.md`
- `codex/skills/escalate/SKILL.md`
- `codex/skills/frontier-check/SKILL.md`
- `codex/skills/journal/SKILL.md`
- `codex/skills/route/SKILL.md`
- `codex/skills/usage/SKILL.md`
- `codex/prompts/*.md`
- `bin/sync_codex_surfaces.py` (new)
- `tests/test_codex_surfaces.py` (new)
- `tests/test_codex_bundle.py` (update only superseded prompt/placeholder assertions)

**Frozen files**

Everything else. Do not change engines, manifests, agents, docs, installers, or pricing.

**Pinned behavior**

1. Each skill carries one shared, concise root-resolution contract. In plugin mode, resolve the
   repository/plugin root from the actual `SKILL.md` location and verify required sentinels
   (`data/pricing.codex.json` plus the referenced `bin/` engine) before shelling out. In a managed
   copied install, use the installer-resolved root recorded in the installed text/ownership data
   and verify the same sentinels.
2. If root proof fails, stop and direct the user to
   `python3 bin/harness_select.py doctor --harness codex`; never run a literal placeholder or a
   missing/stale path.
3. All shell examples quote the resolved absolute root. No skill gains a hardcoded model id,
   price, plan fact, or duplicated engine logic.
4. `architect` uses `tasks/kits/<slug>` and names `bin/codex_execute.py`; all seven skills retain
   valid frontmatter and current trigger descriptions.
5. `bin/sync_codex_surfaces.py` is stdlib-only and exposes `build` and `check`. It derives the
   seven same-named deprecated prompts from the canonical skill bodies/frontmatter and derives
   `implementer`, `verifier`, and `reviewer` prompt mirrors from the corresponding canonical agent
   source content. A small explicit stem mapping is allowed; behavior text is not duplicated in
   the script.
6. Generated prompt frontmatter uses `description`/`argument-hint` only as supported and labels
   the prompt deprecated in favor of `$<skill>` or the named custom agent.
7. `check` computes expected prompt bytes in memory and writes nothing. `build` writes only
   `codex/prompts/*.md`. Both reject unknown prompt files, malformed source frontmatter/TOML, and
   an absent anchor instead of approximating.
8. Tests cover a plugin tree relocated to two temp roots, a managed copied tree, a stale root, a
   literal placeholder, missing sentinels, prompt drift, build determinism, check read-only
   behavior, and no cross-harness/model-id leakage.

**Acceptance.**

- A moved plugin tree resolves its current root; a stale copied install fails with a doctor remedy.
- Skills are canonical and prompt drift is mechanically detectable.
- `python3 bin/sync_codex_surfaces.py check` passes without writing.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_surfaces.py' -v && python3 bin/sync_codex_surfaces.py check && python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v
```

## Phase 3 — Codex workflow parity with honest limits

### T5 — Add execute and doctor skills

- id: `codex-core-workflow-skills`
- title: Complete architect-to-execute and onboarding workflows
- status: done
- model: mid
- depends: T2, T3, T4
- independent: no

**Brief.**

Add the two highest-value missing Codex skills: a kit execution workflow over the existing driver
and a read-only onboarding/update doctor. Integrate them into the plugin/installer inventories and
surface sync without changing the driver itself.

**Sanctioned files**

- `codex/skills/execute/SKILL.md` (new)
- `codex/skills/doctor/SKILL.md` (new)
- `bin/sync_codex_surfaces.py`
- `bin/harness_select.py` (inventory wiring only; no installer semantic rewrite)
- `.codex-plugin/plugin.json` (version bump only if the manifest policy requires it)
- `tests/test_codex_core_skills.py` (new)
- `tests/test_codex_plugin.py`
- `tests/test_codex_setup.py`
- `tests/test_codex_surfaces.py`
- `tests/test_codex_bundle.py` (skill roster/parity updates only)

**Frozen files**

Everything else, especially `bin/codex_execute.py`, generic agent TOML, prompts unrelated to the
sync output, pricing, other harnesses, and docs.

**Pinned behavior**

1. `execute` consumes `tasks/kits/<slug>/PLAN.md` and `TASKS.md`, never `.Codex` or `.claude` kit
   paths. It explains safe `status`, `run --dry-run`, real `run`, and `review` modes of
   `bin/codex_execute.py` without itself launching an unapproved real run.
2. It requires reading PLAN constraints/out-of-scope before execution, respects exact task status
   vocabulary/model pins/dependencies, independently verifies, and distinguishes a dry-run from a
   real dispatch that spends usage/API funds.
3. It prefers the canonical generic agents for interactive delegation when available but remains
   functional through the headless driver when they are not installed. It never claims plugin
   install supplied the agents.
4. `doctor` runs only the read-only doctor/plan commands from T3, summarizes component state and
   exact remedies, and requires explicit user authority before any install/refresh command.
5. Both skills use the T4 root-resolution contract, valid frontmatter, no model pin, and runtime
   pricing/roster derivation.
6. Inventories now expect nine skills. Deprecated prompts are not required for these new skills;
   do not create `/execute` or `/doctor` prompt mirrors unless the T4 generator's compatibility
   policy explicitly opts them in.
7. Tests assert command accuracy against the real argparse parser through imported pure parser
   construction, no real process invocation, correct safety labels, plugin discoverability, and
   installer inventory inclusion.

**Acceptance.**

- `$architect` has a complete `$execute` continuation and users have a safe `$doctor` entry point.
- The nine-skill plugin/installer inventory is consistent and tested.
- No real harness command or home path is touched.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_core_skills.py' -v && python3 bin/sync_codex_surfaces.py check
```

### T6 — Port context-weight and benchmark routing skills

- id: `codex-analysis-skills`
- title: Expose existing Codex-aware analysis engines without overstating fidelity
- status: done
- model: mid
- depends: T4
- independent: yes

**Brief.**

Add thin Codex skills for two engines that already understand the Codex harness. Reuse their
actual CLI surfaces and honesty labels; do not port Claude-only behavior or reproduce algorithms.

**Sanctioned files**

- `codex/skills/context-weight/SKILL.md` (new)
- `codex/skills/bench-routing/SKILL.md` (new)
- `.codex-plugin/plugin.json` (version bump only if required)
- `tests/test_codex_analysis_skills.py` (new)
- `tests/test_codex_plugin.py` (roster update only)
- `tests/test_codex_setup.py` (inventory update only)
- `tests/test_codex_bundle.py` (skill roster/frontmatter update only)

**Frozen files**

Everything else, especially `bin/context_weight.py`, `bin/bench_routing.py`, pricing/benchmark
data, prompts, agents, and other harness skills.

**Pinned behavior**

1. `context-weight` documents and uses only real engine commands. Codex session/overview/audit
   fidelity must match the engine; Claude-only live watch and constraint attribution remain
   explicitly unavailable on Codex.
2. `bench-routing` uses the engine's `roles --harness codex`, rank, and demo surfaces; it states
   the Intelligence Index and screenshot-transcription limitations already enforced by the
   engine. It never converts benchmark estimates into bills or routing certainty.
3. Both use T4 root resolution, valid frontmatter, no model pin/id/price literal, and no copied
   engine implementation.
4. Tests parse the real argparse builders or run only sanctioned synthetic `demo` commands through
   injected subprocess seams; they never read real homes, network, or invoke a harness CLI.
5. Inventories expect eleven skills after this task and preserve plugin/install ordering.

**Acceptance.**

- Both existing Codex-aware engines are discoverable as skills.
- Unsupported fidelity stays visible and no cross-harness claim is upgraded.
- Targeted tests and safe demos pass.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_analysis_skills.py' -v && python3 bin/context_weight.py demo && python3 bin/bench_routing.py demo
```

### T7 — Port the bounded local memory skill

- id: `codex-memory-skill`
- title: Add harness-neutral memory recall and review to the Codex plugin
- status: done
- model: mid
- depends: T4
- independent: yes

**Brief.**

Expose the existing memory engines to Codex without changing their privacy, gating, or context
budget contracts. This is a workflow port only.

**Sanctioned files**

- `codex/skills/memory/SKILL.md` (new)
- `.codex-plugin/plugin.json` (version bump only if required)
- `tests/test_codex_memory_skill.py` (new)
- `tests/test_codex_plugin.py` (roster update only)
- `tests/test_codex_setup.py` (inventory update only)
- `tests/test_codex_bundle.py` (skill roster/frontmatter update only)

**Frozen files**

Everything else, especially `bin/memory_recall.py`, `bin/memory_store.py`, the real gitignored
`memory/` store, constants/tests governing recall budgets, and Claude/Copilot skills.

**Pinned behavior**

1. The skill is pull-only: derive a short task query, call `memory_recall.py`, and inject only the
   returned gated/budget-capped winners. Never bulk-read or dump the store/index.
2. Store/review operations use only explicit `--memory-dir`; tests and examples use temp/demo
   paths and explicit `--now` where determinism matters.
3. Preserve expiry, confidence, source, contradiction, and staleness semantics from the existing
   engines. Do not invent an automatic memory write, background watcher, or pricing coupling.
4. Use T4 root resolution, valid frontmatter, and no model/path/price literal.
5. Tests assert the skill's commands against parser surfaces, required privacy language, absence
   of `Path.home`/network/CLI instructions, and a successful synthetic demo.
6. Inventories expect twelve skills after this task.

**Acceptance.**

- Memory is available to Codex with the same conservative gates and private-store contract.
- No runtime engine, store, gate, or budget constant changes.
- The demo and targeted tests pass without real data.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_memory_skill.py' -v && python3 bin/memory_recall.py --demo
```

## Phase 4 — Documentation, migration, and end-to-end proof

### T8 — Rewrite Codex onboarding around plugins, skills, and agents

- id: `codex-onboarding-docs`
- title: Add one current quickstart and correct obsolete Codex claims
- status: done
- model: mid
- depends: T3, T5, T6, T7
- independent: no

**Brief.**

Update the user-facing documentation to match the implemented Codex-native surfaces. Keep the
edits focused on Codex discoverability/install/update/migration; do not rewrite unrelated Claude
or Copilot guides or hand-edit generated HTML.

**Sanctioned files**

- `README.md` (Codex summary/quickstart links only)
- `SETUP.md` (Codex prerequisite/install/update step only)
- `docs/CODEX-HARNESS.md`
- `docs/CODEX-QUICKSTART.md` (new, only if the harness guide would otherwise become unwieldy)
- `tests/test_codex_docs.py` (new)

**Frozen files**

Everything else, including generated `copilot-docs/`, other docs, runtime code, bundle content,
pricing tables, and plugin/agent metadata.

**Required documentation**

1. A shortest-path fresh-clone flow: open repo, restart Codex, find the repo marketplace in
   `/plugins`, install/enable Polytropos, verify skills in `/skills`, then optionally materialize
   project/user agents with the installer.
2. A component matrix distinguishing root `AGENTS.md`, plugin skills, custom agents, deprecated
   prompts, installer ownership data, and which Codex surfaces (desktop, CLI, IDE) support each.
3. Explicit invocation with `$route`, implicit skill matching, `/skills`, `/plugins`, and `/agent`;
   do not present `/route` as the primary custom command.
4. A safe preview/doctor/update flow with exact implemented commands, JSON mode, restart/new-task
   expectations, and no promise that plugin install includes agents.
5. Conflict recovery for unmanaged/user-modified files and the existing stale absolute-path case.
   No instruction tells users to delete a whole Codex home or overwrite `config.toml`.
6. Legacy copied-install and custom-prompt migration, including their deprecated/compatibility
   status and how to retain them deliberately.
7. An accurate twelve-skill inventory and four-agent inventory derived by tests from source
   frontmatter/TOML rather than duplicated hardcoded model/pricing facts.
8. Architect → execute, doctor, routing/effort, usage/journal, context-weight, benchmark routing,
   and memory examples. Real kit dispatch examples clearly warn about subscription/API spend.
9. Official OpenAI documentation links from PLAN's research basis. Product availability claims
   remain bounded to the cited surfaces.
10. A “Good next Codex additions” section summarizing follow-ons from PLAN without claiming they
    exist: Codex repo-bench adapter, optional trusted verify hook, automation templates, plugin
    assets, and future context-fidelity improvements. State that Codex's built-in `/statusline`
    replaces the need to port Claude's custom statusline setup.

**Tests**

- every shown `python3 bin/harness_select.py ...` command parses through the real parser without
  executing its action;
- documented skill/agent inventory equals disk discovery;
- docs contain current invocation/install terms and reject obsolete primary claims
  (`Codex has no custom-agent files`, bare `/route` as primary, plugin installs agents);
- local Markdown links resolve;
- no live model id/price/plan allowance is introduced outside existing labeled snapshot sections;
- no other documentation file changed.

**Acceptance.**

- A new user has one accurate path from clone to plugin skills and optional agents.
- Update/conflict/migration behavior matches code and tests exactly.
- The Codex harness guide no longer contradicts current official Codex behavior.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_docs.py' -v
```

### T9 — Add the end-to-end temp-root onboarding proof

- id: `codex-onboarding-e2e`
- title: Prove fresh install, update, conflict, portability, and suite health
- status: done
- model: strong
- depends: T8
- independent: no

**Brief.**

Add one end-to-end stdlib integration test module that composes the real plugin metadata,
installer/doctor pure seams, canonical agents, canonical skills, and docs contract entirely under
temporary roots. Fix integration defects only in files already sanctioned by prior tasks; do not
widen functionality.

**Sanctioned files**

- `tests/test_codex_onboarding_e2e.py` (new)
- `bin/harness_select.py` (integration fixes only)
- `bin/sync_codex_surfaces.py` (integration fixes only)
- `.codex-plugin/plugin.json`
- `.agents/plugins/marketplace.json`
- `codex/agents/*.toml`
- `codex/skills/*/SKILL.md`
- `codex/prompts/*.md`
- `README.md`
- `SETUP.md`
- `docs/CODEX-HARNESS.md`
- `docs/CODEX-QUICKSTART.md` if T8 created it
- Codex-specific tests created/edited by T1–T8

**Frozen files**

All pricing files, real homes, root `AGENTS.md`, current `.codex/`, Claude/Copilot surfaces,
execution/analysis/memory engines, repo-bench work, generated docs, and unrelated tests.

**End-to-end scenarios**

1. Fresh relocated clone fixture: plugin and marketplace validate, all twelve skills discover,
   four agents parse, doctor reports ready, and dry-run project-agent plus legacy-copy plans are
   deterministic.
2. First managed copy: skills/prompts/guidance land only under the temp Codex home, project agents
   only under the temp repo, and ownership records contain hashes/metadata but no content/secrets.
3. Idempotent rerun: every component is up-to-date and no bytes/mtimes change.
4. Source update with untouched install: `--refresh-managed` updates atomically and advances the
   ownership manifest.
5. User edit after install: refresh reports conflict and preserves the edited destination and
   previous manifest.
6. Legacy stale-root install: doctor identifies the old path; normalized known content is
   adoptable, unrelated content is not.
7. Agent collision with the current-style 84-file legacy import fixture: installer does not prune
   or overwrite; doctor reports unmanaged/orphan-prone entries and a manual remedy.
8. Prompt drift: surface check fails read-only; build repairs only prompt mirrors in the fixture.
9. Moved plugin root after setup: plugin skills resolve the new root while a copied stale skill
   fails closed with doctor guidance.
10. Static safety sweep: production setup/sync code contains no `subprocess` call to a harness,
    network module, destructive removal, implicit real-home mutation, model id, or price literal.

**Acceptance.**

- All ten scenarios pass under temporary roots and would fail on clobbering, stale path use,
  plugin/agent conflation, or real-state access.
- Every targeted Codex test passes, then the complete repository unittest suite passes.
- `git status --short` shows only this kit's sanctioned changes plus the user changes that were
  already present before execution.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_onboarding_e2e.py' -v && python3 bin/sync_codex_surfaces.py check && python3 -m unittest discover -s tests -v
```
