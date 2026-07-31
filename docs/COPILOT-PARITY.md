# Copilot CLI parity — the Claude Code plugin experience, ported

This doc maps every user-invocable Claude Code plugin experience
(`/polytropos:<name>`) to its GitHub Copilot CLI twin, and records exactly how
Copilot's two capability surfaces — skills and agents — relate. Sourced from a 2026-07-18
capture of GitHub's official Copilot CLI docs (agent skills, custom agents, `/skills`);
see `copilot/aesop.yaml`'s Ground truth notes for the underlying research.

## 1. Two surfaces, one capability

- **Skills** (`copilot/.github/skills/<name>/SKILL.md`) are `/name`-invocable instruction
  files — type `/route`, `/usage`, etc. in the prompt, or Copilot auto-loads the matching
  skill when a request's wording matches its `description:`. A skill runs on whatever
  model the current session is already using; it carries no model pin of its own.
- **Agents** (`copilot/.github/agents/<name>.agent.md`) are personas Copilot switches
  into via the `/agent` picker or `copilot --agent <name> -p "<task>"`. An agent's
  frontmatter carries a `model:` pin, so dispatching through an agent is how you get an
  isolated run on a specific model (for example, the frontier tier for `architect`).
- Every capability below ships as BOTH a skill and a same-named agent (except `execute`,
  which has no agent — see the table). They are the same underlying capability on two
  surfaces, contract-tested to stay in sync.

## 2. The parity table

| Claude Code | Copilot CLI |
|---|---|
| `/polytropos:route` | `/route` skill, or `copilot --agent route` |
| `/polytropos:cost-report` | `/usage` skill, or `copilot --agent usage` |
| `/polytropos:journal` | `/journal` skill, or `copilot --agent journal` |
| `/polytropos:fable-check` | `/frontier-check` skill, or `copilot --agent frontier-check` |
| `/polytropos:escalate` | `/escalate` skill, or `copilot --agent escalate` |
| `/polytropos:architect` | `/architect` skill, or `copilot --agent architect` (carries the frontier pin) |
| `/polytropos:execute` | `/execute` skill driving `bin/copilot_execute.py` (serial; no parallel-subagent equivalent) |
| (no Claude twin) | `/effort` skill — Copilot's per-model Reasoning dial |
| `/polytropos:setup` (statusline) | already wired — settings.json `statusLine` → `bin/copilot_statusline.py`; no skill needed |
| memory skill | deferred — a future cross-harness kit |

Naming note: `usage` and `frontier-check` are the harness-parity names for what Claude
calls `cost-report` and `fable-check` — a non-Claude surface never carries the `fable*` or
`cost-report` name.

## 3. Install and refresh

```bash
python3 bin/harness_select.py install --harness copilot
```

This copies every file under `copilot/.github/agents/` to `~/.copilot/agents/` and every
file under `copilot/.github/skills/` to `~/.copilot/skills/`, resolving the
`{{POLYTROPOS_ROOT}}` placeholder to this repo's absolute path as it goes.

In a live Copilot CLI session:

- `/skills reload` — picks up newly installed or changed skills without restarting.
- `/skills` — lists every installed skill.
- `/skills info <name>` — shows one skill's frontmatter and source path.

## 4. Honest limits

- **True custom slash COMMANDS are not supported in Copilot CLI.** The VS Code-style
  `.prompt.md` custom-command surface, and the emerging extensions SDK that would add
  one, are open feature requests (github/copilot-cli #618, #1113) — out of scope here.
  Skill `/name` invocation is the honest parity mechanism for "slash commands," and that
  is what this bundle ships.
- **No headless reasoning-effort surface is confirmed.** Copilot's "Reasoning" dial is
  adjusted interactively in the `/model` picker only; no `copilot -p` flag or settings key
  for it is known to exist. The `/effort` skill teaches the interactive mechanism and says
  so plainly rather than inventing a flag.
- **Kit execution is serial.** `/execute` drives `bin/copilot_execute.py` one `run`
  invocation at a time. Copilot CLI has no equivalent to Claude Code's parallel Agent-tool
  fan-out or warm SendMessage clusters — a kit task marked `independent:` means "safe to
  run in any order," not "runs in parallel."

## 5. Where the numbers live

No price, AI Credit value, or model id is hardcoded in this doc or in any skill/agent
body. Every number is derived at run time from `data/pricing.copilot.json` via
`bin/copilot_pricing.py` (`models`, `est`, `runway`, `knobs`) — the AIC unit itself is
data (`billing_unit.usd_per_credit`). See `CLAUDE.md` and `copilot/aesop.yaml`'s
instructions block for the standing pricing invariant.
