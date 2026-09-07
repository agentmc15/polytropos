# The Codex harness

Polytropos uses central policy for Codex execution. Astra owns planning, dependency coordination, bounded recovery, and final acceptance. Luna handles cheap mechanical work, Terra routine work, and Sol hard, security, integration, and independent-verification work. The policy derives model identity, availability, effort support, and pricing from `data/pricing.codex.json` at runtime.

Use Python 3.11 or newer. The examples assume `python3` selects that interpreter.

## Install a registered plugin

```bash
codex plugin marketplace add /path/to/polytropos
codex plugin add polytropos@polytropos-local
codex plugin list --marketplace polytropos-local --json
```

The installed plugin is cached. Start a new task after installation. In clients that expose `/plugins`, that command opens plugin management. In Codex CLI and supported IDE clients, open `/skills` or invoke `$route`; do not rely on a bare `/route` alias.

## Package preparation and optional agents

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project
python3 bin/harness_select.py doctor --harness codex --repo-root . --codex-home <codex-home>
```

installing the plugin does not install the agents. Project roles are written to `.codex/agents/`; `--agent-scope user` uses the supplied Codex home. The roles are `kit-implementer`, `kit-verifier`, `phase-reviewer`, and `repo-explorer`.

The planner reports package **readiness** while runtime activation remains observed or `unknown`; the plugin is a cached package. `.agents/skills` and `.codex/skills` are compatibility discovery locations, not a second workflow source.

## Policy-routed execution

Start with a policy preview, then use the driver for every dispatch. A real run spends plan usage or API funds; a dry run does neither.

```bash
python3 bin/codex_execute.py status --kit tasks/kits/<slug> --json
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id> --dry-run
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id>
python3 bin/codex_execute.py review --kit tasks/kits/<slug> --phase <N>
python3 bin/codex_execute.py accept --kit tasks/kits/<slug> --phase <N>
```

The driver instantiates no warm pool. Its recovery path requires driver-recorded lower-tier attempts plus a nonzero verification result, unresolved named integration conflict, or failed lower-tier correction. It records planned intent, dispatched assignment, and observed runtime use separately; observed model or role remains `unknown` without independent telemetry. Direct host tools and user-selected models outside this driver are outside the policy boundary.

Legacy kits need no rewrite: an unpinned task is assigned the configured default worker, and a legacy frontier pin maps to the maximum worker at dispatch. For an explicit preview:

```bash
python3 bin/codex_execute.py prepare --role implementer
python3 bin/codex_execute.py prepare --role implementer --model frontier
```

For callers migrating from the earlier driver, `status --json` now returns an object whose
`tasks` key contains the task list alongside orchestration and acceptance state. Phase review
and acceptance require a Git workspace and a fingerprint of the current plan, phase, attempts,
commit, and working tree. Existing free-form review notes are not accepted as evidence; run a
fresh Sol review before requesting Astra acceptance. Review and acceptance records are written
as typed JSON lines to `<kit>/role-use.jsonl`, which the gates read; `NOTES.md` remains the
human-readable view and is no longer consulted for evidence. Final acceptance is read only from
a correlated terminal assistant message in a completed turn on stdout -- a tool event, a
diagnostic on stderr, an interrupted turn, or a message naming both verdicts yields no verdict
and the run stops with the reason.

## Application configuration

Application policy changes require explicit repository, Codex-home, backup, and runtime-model snapshot roots. `plan` and `status` are read-only; `apply` refuses missing required models and backs up only managed changes.

```bash
python3 bin/codex_app_policy.py plan --repo-root . --codex-home <codex-home> --backup-root <new-empty-dir> --runtime-models <model-list.json>
python3 bin/codex_app_policy.py status --repo-root . --codex-home <codex-home> --backup-root <new-empty-dir> --runtime-models <model-list.json> --json
python3 bin/codex_app_policy.py apply --repo-root . --codex-home <codex-home> --backup-root <new-empty-dir> --runtime-models <model-list.json>
```

For an existing application configuration, use the same three commands: `plan` shows surgical top-level and agent-default changes, `status` reports ownership conflicts, and `apply` preserves unrelated TOML while materializing managed roles. Never overwrite an unmanaged or edited role file. The configuration prevents accidental parent-model inheritance within its scope; it cannot globally sandbox arbitrary app actions.

## Skills and legacy copies

`$architect` plans kits, `$bench-routing` reads benchmark priors, `$context-weight` measures context, `$doctor` diagnoses setup, `$effort` selects effort, `$escalate` explains recovery, `$execute` dispatches kits, `$frontier-check` checks reserved orchestration, `$journal` prepares the work journal, `$memory` recalls bounded context, `$route` estimates assignments, and `$usage` reports local use. Under a ChatGPT plan, dollars are API-equivalent burn proxies; API-key runs are token-metered.

When usage logs expose nested cache-write counts, `$usage` retains the inclusive raw input total and prices the read, write, and uncached portions separately. Missing write counts are not inferred; observed writes without a configured rate are reported unpriced.

`codex/prompts/` contains deprecated compatibility mirrors. Refresh them only through the ownership-aware legacy path:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components skills,prompts,guidance --legacy-copy --dry-run
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components prompts --legacy-copy --refresh-managed --dry-run
python3 bin/harness_select.py retire-legacy --harness codex --repo-root . --codex-home <codex-home> --backup-root <backup-root> --components prompts,skills
python3 bin/harness_select.py restore-legacy --harness codex --repo-root . --codex-home <codex-home> --backup-root <backup-root>
```

## Manual live smoke checklist

After separately authorized rollout, record the client version, installed plugin, `$route` availability in `/skills`, loaded package path, runtime-model snapshot, and absence of duplicate legacy skills or prompts. Automated tests cannot prove client UI activation.

Retirement requires `--native-skills-confirmed`; edited files remain a conflict. This smoke checklist has not been performed by automated verification.

## Good next Codex additions

Future work may add a repo-bench adapter, an opt-in verify hook, Automation templates, Plugin icons, and context-fidelity reporting. Codex's built-in `/statusline` does not need to be ported.
