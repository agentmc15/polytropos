# GUARDRAILS — graph-convergence

Kit-scoped fences. Execute reads this at setup; these load only when this kit runs.

- **Live-CLI fence is absolute.** No task, test, or verify command may invoke the real
  `claude`, `copilot`, or `codex` binary — dispatches spend real money/credits/quota. The
  injectable-runner seam and `--dry-run` are the only sanctioned execution paths; stub
  binaries and temp fixture dirs only. This repeats CLAUDE.md deliberately because five of
  twelve tasks touch dispatch code.
- **Grammar changes travel in threes.** Any edit to the outcome-line grammar updates
  `skills/architect/SKILL.md`, `skills/execute/SKILL.md`, and `bin/routing_scorecard.py`
  in the same task or an explicit `depends:` chain — never one without the others. The
  reviewer rejects the phase otherwise.
- **Optionality is load-bearing.** Every new field, block, and flag introduced by this kit
  is optional with absent-means-today semantics. The golden-output tests in T2 are the
  tripwire; do not weaken or regenerate them to make a diff pass.
- **`~/.claude` writes are consent-gated, always.** T4's hook installation goes through the
  setup skill's confirmation pattern. Nothing in this kit auto-registers a hook, edits
  settings, or refreshes the plugin.
- **Confidence labels are not decoration.** Where a flag surface or frontmatter field is
  pinned without live verification (T5 dispatch flags, T6 tool pins), the MEDIUM-confidence
  provenance comment ships in the file. Removing the label without live evidence is a wrong
  change even if the code works.
- **Run ids stay content-free** (PLAN D8): date + 4 hex. No hostname, username, transcript
  text, or path fragments in any ledger line — NOTES.md is committed in consumer repos.
- **Match the sibling, don't improve it in passing.** T5 and T9 port structure from the
  existing drivers; stylistic "improvements" to the shared shape belong in their own kit.
  If the template itself looks wrong, STOP and report with a `defect:` line.
