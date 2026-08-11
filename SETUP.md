# Setup — working on this on a new machine

This repo (`polytropos`) is a Claude Code plugin for per-task model routing and cost
optimization. Its companion is **aesop** (the environment compiler) in a separate repo. Both are
pushed to GitHub, so a fresh clone is complete and current — there's no external fetch or secret to
restore. The only things that don't transfer between machines are a few **absolute paths**; you
re-run the installers rather than copying `~/.claude` or `~/.copilot` over.

## Prerequisites

| Need | For |
|---|---|
| `git` | cloning both repos |
| `python3` (3.8+) | polytropos — **stdlib-only**, nothing to `pip install` |
| `node` 20+ and `npm` | aesop (TypeScript) |
| Claude Code CLI *(optional)* | to install/use the plugin |
| GitHub Copilot CLI *(optional)* | to use the Copilot harness |
| OpenAI Codex desktop or CLI *(optional)* | to use the Codex plugin skills and custom agents |
| `gh auth login` *(optional)* | to push to GitHub |

## 1. Clone both, side by side

```bash
mkdir -p ~/Developer/reposV2 && cd ~/Developer/reposV2
git clone https://github.com/agentmc15/polytropos.git
git clone https://github.com/agentmc15/aesop.git
```

> **Location matters:** this repo must live **outside any cloud-synced folder** — never under
> `~/Desktop`, `~/Documents`, or a Dropbox/Drive/OneDrive tree. The gitignored personal stores
> (`journal/`, `telemetry/`, `memory/`, `prefs/`) would otherwise sync to the cloud wholesale.
> See "The iCloud lesson" in `docs/PRIVACY.md`; the test suite fails if the repo sits in a
> synced location.

Nothing at runtime requires aesop to be a sibling of this repo — `bin/aesop_bridge.py` computes its
numbers from `data/pricing.json`, not from the aesop checkout. The side-by-side layout is convention
only (this repo's docs reference the aesop path as reference material).

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

# Codex → restart Codex with this repo open, use /plugins to install and enable
# Polytropos, then verify the twelve skills with /skills. Preview optional
# project-agent installation before writing anything:
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

## 3. aesop (companion) — install deps + build

TypeScript on node 20:

```bash
cd ../aesop
npm ci                          # installs deps; the `prepare` script builds dist/
npm run build                   # belt-and-suspenders — produces dist/index.js
npm test                        # unit suite
node dist/index.js compile --check && node dist/index.js doctor   # self-dogfood; should be clean
npm link                        # optional: put the `aesop` command on PATH
```

## The one gotcha: absolute paths don't transfer

Do **not** copy `~/.claude/`, `~/.copilot/`, or a legacy copied Codex skill directory from another machine — they may contain hardcoded
`/Users/<you>/...` paths (the plugin root, the `{{POLYTROPOS_ROOT}}` placeholder resolved at
install time, and the statusline command). Re-run the relevant setup preview/doctor on the new
machine. Codex plugin skills resolve from the relocated repo itself; only deliberate legacy copies
need managed refresh. Everything else — pricing data, kits, docs, tests — lives inside the repos.

## Using it vs. developing it

- **Just use it:** install the plugin (+ Copilot harness and statusline if you want them) and go.
- **Develop it:** run the test suites before claiming any change done — `python3 -m unittest
  discover -s tests` here, `npm test` (plus `compile --check` and `doctor`) in aesop. Both repos
  track `main` and are fully pushed, so `git pull` gets you current.
