# copilot-skills-parity — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `copilot-skills-parity` specifically: NEVER invoke the real `copilot`/`codex`/`claude`
  CLI from any task, test, or verify command (command lines WRITTEN into skill bodies are
  runtime instructions the kit never executes — verify commands are unittest discovery and
  greps only), and every Copilot CLI skills fact is a pinned 2026-07-18 capture in the kit's
  PLAN.md — no re-research, no network; every skill lands ATOMICALLY — `copilot/aesop.yaml`
  `primitives.skills` entry + `copilot/.github/skills/<name>/SKILL.md` + its additive
  `tests/test_copilot_bundle.py` seam in ONE task (the skills roster test is set equality,
  the manifest parser is line-oriented so entries match `- lessons-loop`'s exact indentation,
  and the suite is green at every task boundary); skill frontmatter is `name` + `description`
  ONLY (a `model:` line in a skill is a defect — the same-named agents keep the pins; skills
  run on the session's model) and NO frontmatter value contains an unquoted `: ` (breaks
  Copilot's real YAML loader — sweep-tested on agents, and this kit adds the skills twin);
  skill bodies are condensed operative twins of the same-named agents (never bare pointers,
  never verbatim copies), shell to the engines via `{{POLYTROPOS_ROOT}}` (never an
  absolute path, never `${CLAUDE_PLUGIN_ROOT}`, never another harness's pricing path), derive
  every vocabulary/number at run time (never enumerate the effort ladder, never a
  `data/pricing.copilot.json` models key in any skill file), keep the AIC-are-real-money
  framing, and quote ONLY flags on the PLAN-pinned argparse surfaces; the effort skill
  teaches the interactive `/model` picker only ("unconfirmed" for headless — nothing under
  `copilot/` may contain `--effort` or `model_reasoning_effort`) and the execute skill is
  HONEST about orchestration (it drives `bin/copilot_execute.py` status/run/review plus
  `--agent` dispatches serially — never a faked parallel-subagent equivalent); the ported
  capability names stay `usage`/`frontier-check` — never `cost-report` or `fable*` as a
  Copilot skill name; `bin/harness_select.py` is BYTE-UNTOUCHED (its skills glob already
  installs `copilot/.github/skills/*` — verified in-tree) as is every other `bin/` engine;
  test edits are additive at the pinned seams only (the T1 generic skill sweeps + one
  contract class per skill; `FrontmatterYamlSafetyTests` and every other pre-existing
  class/method byte-intact); sanctioned edit targets are ONLY `copilot/aesop.yaml`,
  `copilot/.github/copilot-instructions.md` (append-only; both doctrine sentences stay
  byte-verbatim), and `tests/test_copilot_bundle.py`, with new files the eight
  `copilot/.github/skills/{route,usage,journal,frontier-check,escalate,effort,architect,execute}/SKILL.md`
  dirs and `docs/COPILOT-PARITY.md` — `skills/`, `codex/`, `bin/`, `data/` (all three
  pricing files), `.claude-plugin/`, README.md, the ten `*.agent.md` files,
  `copilot/.github/skills/lessons-loop/`, and the completed kits stay byte-untouched
  (CLAUDE.md and README.md are NOT executor edit targets; the architect pre-made this
  fence); no extension-SDK slash commands or VS Code `.prompt.md` work, no new agents, no
  memory/setup skill port, no Claude-side skill changes; no commit, no push.
