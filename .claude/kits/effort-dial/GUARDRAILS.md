# effort-dial — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `effort-dial` specifically: the dial is the GPT-5.6 reasoning-effort ladder ONLY — no
  `ultra`/`fast`/multi-agent mode work (CLI surfaces unpublished; no flag or multiplier
  invented), no long-context threshold-tier SCHEMA modeling in either pricing file (the
  authoritative step-up rates live in each file's labeled `long_context_note`), and no
  model-variant-selection-as-effort feature; effort level vocabularies are DATA — each
  harness's `knobs.reasoning_efforts` in its OWN pricing file, derived at run time via the
  new `knobs` subcommands, never hardcoded in scripts or bundle bodies (Codex lowercase
  tokens incl. `xhigh`; Copilot Title-Case display forms incl. 'Extra High' — the two
  vocabularies never mix, `grep -rn "minimal" codex/` stays empty post-T2, and new bundle
  bodies never enumerate the ladder); the Copilot mechanism is the INTERACTIVE `/model`-picker
  arrow-key "Reasoning" setting (per-model; rows showing '—' have no dial) — NO headless flag
  is confirmed, so `bin/copilot_execute.py` is byte-untouched and nothing under `copilot/`
  may contain `--effort` or `model_reasoning_effort` (Codex keeps its confirmed
  `-c model_reasoning_effort=<level>` / `codex_execute.py --effort`, and `bin/codex_execute.py`
  is also byte-untouched); every live CLI fact is a pinned 2026-07-18 capture in the kit's
  PLAN.md — NEVER invoke the real `copilot`/`codex`/`claude` CLI from any task, test, or
  verify command to "check"; still-unconfirmed items (headless surface, the four unobserved
  display renderings, best-effort ids) stay labeled with a single correctable point in the
  relevant pricing file; `data/pricing.codex.json` gets NO rate-value changes (the `xhigh`
  correction + GA/ultra/long-context notes only) and the three Copilot GPT-5.6 rows land
  CONFIRMED (GitHub Models-and-pricing doc + Sol's picker panel), appended at the END of the
  models object with `cached_date` unchanged; test edits are additive at pinned seams only
  (`WORKFLOW_AGENT_TIERS` + `EffortAgentContractTests`; the `EXPECTED_PROMPT_STEMS`/
  `EXPECTED_SKILL_STEMS` unions — `PORTED_*` tuples untouched — +
  `EffortPromptContractTests`/`EffortSkillContractTests`; one `KnobsCmdTests` class per
  pricing test file); sanctioned edit targets are ONLY `data/pricing.copilot.json` and
  `data/pricing.codex.json` (pinned blocks), `bin/copilot_pricing.py` + `bin/codex_pricing.py`
  (additive `knobs` subcommand each), the four test files above, `copilot/aesop.yaml`,
  `copilot/.github/copilot-instructions.md`, `codex/AGENTS.md`, and the six pinned
  enumeration-swap lines in `codex/prompts/{route,escalate,frontier-check}.md` +
  `codex/skills/{route,escalate,frontier-check}/SKILL.md`, with new files
  `copilot/.github/agents/effort.agent.md`, `codex/prompts/effort.md`,
  `codex/skills/effort/SKILL.md`, and `docs/EFFORT-DIAL.md` — `data/pricing.json`, `skills/`,
  `.claude-plugin/`, README.md, `bin/harness_select.py`, all other pre-existing bundle files,
  and the completed kits stay byte-untouched (CLAUDE.md and README.md are NOT executor edit
  targets; the architect pre-made the run-lines and this fence); no commit, no push.
