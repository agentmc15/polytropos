# Copilot CLI parity — the Claude Code plugin experience, ported

This doc maps every user-invocable Claude Code plugin experience
(`/polytropos:<name>`) to its GitHub Copilot CLI twin, and records exactly how
Copilot's two capability surfaces — skills and agents — relate. The underlying research is a
2026-07-18 capture of GitHub's official Copilot CLI docs (agent skills, custom agents,
`/skills`), pinned in `.claude/kits/copilot-skills-parity/PLAN.md` under "Ground truth". The
model-selection mechanisms in the table come from `.claude/kits/copilot-harness/PLAN.md`
("Copilot CLI model selection — CONFIRMED"), and the bundle-enforcement facts from
`.claude/kits/harness-parity/PLAN.md` ("Ground truth"). `copilot/aesop.toml` carries the manifest
and the standing pricing instruction — not those citations.

## 1. Two surfaces, one capability

- **Skills** (`copilot/.github/skills/<name>/SKILL.md`) are `/name`-invocable instruction
  files — type `/route`, `/usage`, etc. in the prompt, or Copilot auto-loads the matching
  skill when a request's wording matches its `description:`. A skill runs on whatever
  model the current session is already using; it carries no model pin of its own.
- **Agents** (`copilot/.github/agents/<name>.agent.md`) are personas Copilot switches
  into via the `/agent` picker or `copilot --agent <name> -p "<task>"`. An agent's
  frontmatter carries a `model:` pin, so dispatching through an agent is how you get an
  isolated run on a specific model (for example, the frontier tier for `architect`).
- Most capabilities below ship as BOTH a skill and a same-named agent, and where they do they
  are the same underlying capability on two surfaces. The exceptions run both ways, and the
  table names whichever surfaces actually exist: four skills have no agent (`execute`,
  `budget`, `goliath`, `lessons-loop`), and three agents have no same-named skill because they
  are dispatch targets rather than things you invoke — `implementer`, `verifier`, `reviewer`.
  `tests/test_copilot_bundle.py` holds the roster to the manifest in both directions: the
  `skills` block must equal the directory names under `copilot/.github/skills/`, and the
  `primitives.agents` block the `*.agent.md` stems.

## 2. The parity table

Derived from the two skill trees themselves — `skills/` (Claude) and
`copilot/.github/skills/` (Copilot) — plus `copilot/.github/agents/`, so a skill that ships on
one side and not the other shows up as a gap rather than silently matching.

| Claude Code | Copilot CLI |
|---|---|
| `/polytropos:route` | `/route` skill, or `copilot --agent route` |
| `/polytropos:cost-report` | `/usage` skill, or `copilot --agent usage` |
| `/polytropos:journal` | `/journal` skill, or `copilot --agent journal` |
| `/polytropos:fable-check` | `/frontier-check` skill, or `copilot --agent frontier-check` |
| `/polytropos:escalate` | `/escalate` skill, or `copilot --agent escalate` |
| `/polytropos:bench-routing` | `/bench-routing` skill, or `copilot --agent bench-routing` |
| `/polytropos:context-weight` | `/context-weight` skill, or `copilot --agent context-weight` |
| `/polytropos:architect` | `/architect` skill, or `copilot --agent architect` (carries the frontier pin) |
| `/polytropos:execute` | `/execute` skill driving `bin/copilot_execute.py` (skill only, no agent; serial — no parallel-subagent equivalent) |
| `/polytropos:setup` (statusline) | already wired — settings.json `statusLine` → `bin/copilot_statusline.py`; no skill needed |
| `/polytropos:memory` | no Copilot twin — the bundle ships no `memory` skill or agent (Codex has one: `codex/skills/memory/`) |
| `/polytropos:graphify`, `/polytropos:repo-bench`, `/polytropos:update`, `/polytropos:assess-improvement` | no Copilot twin; all four now ship as Codex-native skills, and `assess-improvement` also ships for Cursor. Codex `$repo-bench` is planning-only and refuses live dispatch. |
| (no Claude twin) | `/effort` skill, or `copilot --agent effort` — Copilot's per-model Reasoning dial |
| (no Claude twin) | `/budget` skill (skill only) — one-tier-lower dispatch, the `/budget` half of `bin/copilot_execute.py run --budget` |
| (no Claude twin) | `/goliath` skill (skill only) — the Copilot-CLI-only five-role pipeline policy |
| (no Claude twin) | `/lessons-loop` skill (skill only) — scoped lessons with provenance and expiry, over `bin/lessons_store.py` |

Naming note: `usage` and `frontier-check` are the harness-parity names for what Claude
calls `cost-report` and `fable-check` — a non-Claude surface never carries the `fable*` or
`cost-report` name.

The four Copilot-only rows are Copilot-only for different reasons. `effort` has no Claude
counterpart to port (see §5's closing note in [EFFORT-DIAL.md](EFFORT-DIAL.md)); `budget` and
`goliath` are dispatch policies for Copilot's own driver and picker, documented in
[COPILOT-HARNESS.md](COPILOT-HARNESS.md#beyond-routing-budget-mode-and-goliath); `lessons-loop`
is vendored from aesop and described in [COPILOT-WORKFLOW.md](COPILOT-WORKFLOW.md#lessons-loop).

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
data (`billing_unit.usd_per_credit`). See `CLAUDE.md` and `copilot/aesop.toml`'s
instructions block for the standing pricing invariant.

Two places carry model *identity* rather than a number, and both are held to the data file.
An agent's frontmatter `model:` pin is a literal id, and `tests/test_copilot_bundle.py`'s
`ModelPinLiveTests` asserts every one of them is a key of that file's `models` — a roster change
fails the suite instead of leaving a dead pin. The `goliath` skill's role table names models by
display name only and instructs resolving each to its current id through
`bin/copilot_pricing.py models` before dispatch. Neither is a price, and neither is a licence to
quote one from memory.
