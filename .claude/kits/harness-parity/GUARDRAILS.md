# harness-parity — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `harness-parity` specifically: `aesop compile`/node/npm are NEVER run — the Copilot
  bundle stays manifest↔hand-authored↔test-consistent, and every Copilot capability lands
  as ONE atomic task editing `copilot/aesop.yaml` `primitives.agents`, the hand-authored
  `copilot/.github/agents/<name>.agent.md`, and the additive `tests/test_copilot_bundle.py`
  seam together (the roster test is set equality — the suite is green at every task
  boundary); the Codex rule is the same atomicity minus the manifest
  (`codex/prompts/<name>.md` + the `PORTED_PROMPT_STEMS` seam in
  `tests/test_codex_bundle.py`; `codex/AGENTS.md` is touched only by the pinned T9
  paragraph); the ported capability names are exactly `usage`, `journal`, `frontier-check`,
  `escalate` on BOTH harnesses — never `fable*` or `cost-report` on a non-Claude harness,
  and `grep -rni fable codex` must stay empty; the THREE pricing files stay byte-untouched
  and no new file hardcodes a price, ratio, allowance, or model id — frontier ids are
  DERIVED at run time via each harness's own engine (`copilot_pricing.py models --json` /
  `codex_pricing.py models --json`), the ONE sanctioned model-id literal is the Copilot
  `.agent.md` frontmatter `model:` pin (non-frontier, read from `data/pricing.copilot.json`
  at implementation time, kept live by the bundle tests' pricing-key + tier checks), Codex
  prompts carry NO `model:` line, and no file under `codex/` contains a real
  `pricing.codex.json` model id; the bin engines (`copilot_usage.py`, `codex_usage.py`,
  `journal_*.py`, `copilot_execute.py`, `codex_execute.py`, `copilot_pricing.py`,
  `codex_pricing.py`, `harness_select.py`) are wrapped read-only and NEVER edited, and
  bundle bodies quote only flags that exist on the real argparse surfaces; the ported
  journal instructs the in-session `--dry-run` two-pass flow ONLY (headless
  `journal_summarize.py` dispatches the Claude CLI — never recommended from a non-Claude
  bundle file), and the ported escalate mirrors the execute drivers' ladder
  (strictly-above tiers, first model in file order, skip empty) with Codex subscription
  dollars always a labeled API-equivalent proxy, never a bill; NEVER invoke the real
  `copilot`/`codex`/`claude` CLI from any task, test, or verify command — the
  `copilot -p`/`codex exec` lines inside bundle bodies are runtime instructions the kit
  never executes; bundle files carry `{{POLYTROPOS_ROOT}}`, never an absolute path,
  never `${CLAUDE_PLUGIN_ROOT}`, never another harness's pricing path; test edits are
  ADDITIVE at the pinned seams only (`WORKFLOW_AGENT_TIERS` entries +
  `PortedAgentContractTests`; `PORTED_PROMPT_STEMS`/the `EXPECTED_PROMPT_STEMS` union + the
  single pinned T2 roster-test rename + `PortedPromptContractTests`) with every other test
  class/method byte-intact; sanctioned edit targets are ONLY `copilot/aesop.yaml`,
  `copilot/.github/copilot-instructions.md`, `codex/AGENTS.md`,
  `tests/test_copilot_bundle.py`, and `tests/test_codex_bundle.py`, with new files the
  eight ported bundle files
  (`copilot/.github/agents/{usage,journal,frontier-check,escalate}.agent.md`,
  `codex/prompts/{usage,journal,frontier-check,escalate}.md`); the ten pre-existing bundle
  files (five agents + five prompts), `copilot/.github/skills/`, `skills/`, `bin/`,
  `data/`, `.claude-plugin/`, `docs/`, `README.md`, and the completed kits stay
  byte-untouched; no new Copilot skills (agents only — `lessons-loop` stays the lone
  skill), no Ralph-loop work, no `bin/harness_select.py` changes (its globs already
  install new files), no new bin scripts or engines, no Claude-side skill changes, no
  commit or push.
