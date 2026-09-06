# Setup — working on this on a new machine

This repo (`polytropos`) is a Claude Code plugin for per-task model routing and cost
optimization. It is pushed to GitHub, so a fresh clone is complete and current — there's no
external fetch or secret to restore. The only things that don't transfer between machines are a few
**absolute paths**; you re-run the installers rather than copying `~/.claude` or `~/.copilot` over.

Its former companion **aesop** (the environment compiler) was **archived on 2026-09-05**. Aesop's
primitive model now lives here — `primitives/`, `bin/primitives.py`, and
[`docs/PRIMITIVES.md`](docs/PRIMITIVES.md) — so nothing in this setup needs an aesop checkout or a
node toolchain.

Prefer reading in a browser? The full manual lives at <https://agentmc15.github.io/polytropos/>, built from this repo by `.github/workflows/docs-site.yml`. Local preview: `python3 -m venv /tmp/ptdocs && /tmp/ptdocs/bin/pip install -r docs-src/requirements.txt && /tmp/ptdocs/bin/mkdocs serve` — the venv is throwaway, never a repo dependency.

## Prerequisites

| Need | For |
|---|---|
| `git` | cloning this repo |
| `python3` (3.11+) | polytropos — **stdlib-only**, nothing to `pip install`; 3.11 is the floor because the stdlib TOML parser (`tomllib`) arrived there |
| Claude Code CLI *(optional)* | to install/use the plugin |
| GitHub Copilot CLI *(optional)* | to use the Copilot harness |
| OpenAI Codex desktop or CLI *(optional)* | to use the Codex plugin skills and custom agents |
| `gh auth login` *(optional)* | to push to GitHub |

## 1. Clone

```bash
mkdir -p ~/Developer/reposV2 && cd ~/Developer/reposV2
git clone https://github.com/agentmc15/polytropos.git
```

> **Location matters:** this repo must live **outside any cloud-synced folder** — never under
> `~/Desktop`, `~/Documents`, or a Dropbox/Drive/OneDrive tree. The gitignored personal stores
> (`journal/`, `telemetry/`, `memory/`, `prefs/`) would otherwise sync to the cloud wholesale.
> See "The iCloud lesson" in `docs/PRIVACY.md`; the test suite fails if the repo sits in a
> synced location.

Nothing here requires an aesop checkout. `bin/aesop_bridge.py` computes its numbers from
`data/pricing.json`, and aesop's primitive model is vendored into `primitives/`. Clone the archived
repo only if you want the emitters as reference material:
`git clone https://github.com/agentmc15/aesop.git`.

## 2. polytropos (this repo) — no build, just verify

Stdlib-only, so there's nothing to install or compile. Prove it works:

```bash
cd polytropos
python3 -m unittest discover -s tests          # full suite should be green
```

Then, to get the live tooling on **this** machine — each step re-resolves absolute paths for this box:

```bash
# Claude Code plugin, via the local marketplace this repo provides
# (use this machine's absolute path — not the one from the old machine)
claude plugin marketplace add "$PWD"
claude plugin install polytropos@polytropos-local

# Copilot harness → materializes agents + skills into ~/.copilot,
# resolving the {{POLYTROPOS_ROOT}} placeholder to this repo's path
python3 bin/harness_select.py install --harness copilot

# Codex → register the local marketplace, install the plugin, then use /skills or
# $route in CLI/IDE clients. A desktop skill selector may be available by version.
# These Codex commands install a cached package; package preparation below does not.
codex plugin marketplace add "$PWD"
codex plugin add polytropos@polytropos-local
codex plugin list --marketplace polytropos-local --json

# Preview the managed Codex application policy before writing anything. It configures
# Astra as the parent orchestrator, Terra as the default worker, and Sol review roles;
# the execution driver keeps Astra reserved for evidence-gated recovery.
python3 bin/codex_app_policy.py plan --repo-root . --codex-home <codex-home> --backup-root <backup-root> --runtime-models <runtime-model-snapshot.json>
# See docs/CODEX-HARNESS.md "Application configuration" for snapshot and apply steps.

# Preview plugin and project-agent installation, then diagnose the combined setup:
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run
python3 bin/harness_select.py doctor --harness codex --repo-root . --codex-home <codex-home>

# Statusline → run this skill inside a Claude Code session (writes an absolute
# path into ~/.claude/settings.json, so it must be run here, not copied):
#   /polytropos:setup
```

Sanity-check a couple of the bin tools directly (no install required):

```bash
python3 bin/cost_report.py --days 30           # Claude-side spend report
python3 bin/session_cost.py                     # a session's cost + all-Fable counterfactual
python3 bin/copilot_ralph.py --demo             # Ralph goal-loop mock (no model, no network, no AIC)
```

## 3. aesop — archived, nothing to build

aesop was archived on 2026-09-05; there is no longer anything to install, build, or keep in sync.
Its primitive model lives here instead ([`docs/PRIMITIVES.md`](docs/PRIMITIVES.md)). If you clone
it for reference, reading the TypeScript needs no toolchain — and the part worth reading is the
emitters' `capabilities()` bodies, which `primitives/harness-matrix.json` already transcribes
verbatim, pinned to aesop's final commit.

## The one gotcha: absolute paths don't transfer

Do **not** copy `~/.claude/`, `~/.copilot/`, or a legacy copied Codex skill directory from another machine — they may contain hardcoded
`/Users/<you>/...` paths (the plugin root, the `{{POLYTROPOS_ROOT}}` placeholder resolved at
install time, and the statusline command). Re-run the relevant setup preview/doctor on the new
machine. Codex plugin installation creates a registered, cached package; it does not guarantee a
live checkout is read on every session. Only deliberate legacy copies need managed refresh.
Everything else — pricing data, kits, docs, tests — lives inside the repos.

## Using it vs. developing it

- **Just use it:** install the plugin (+ Copilot harness and statusline if you want them) and go.
- **Develop it:** run the test suites before claiming any change done — `python3 -m unittest
  discover -s tests` here, `npm test` (plus `compile --check` and `doctor`) in aesop. Both repos
  track `main` and are fully pushed, so `git pull` gets you current.
