# NOTES — codex-harness execution

Cross-task learnings and machine-readable ledgers (execute-owned).

## Learnings

- **T1:** No GPT-5.6 id string found in the real `~/.codex` (`config.toml` model = `gpt-5.5`;
  sampled rollout truncated before any model/usage record). → T2 uses its pinned ids
  byte-for-byte, NO substitution. Usage-field presence for T11 is INCONCLUSIVE (rich data
  likely lives in an off-limits `logs_2.sqlite`) → `codex_usage.py` must ship both honesty-ladder
  branches and treat activity-only (unpriced) as the realistic default. `history.jsonl` absent on
  this machine; `sessions/YYYY/MM/DD/rollout-*.jsonl` layout confirmed.

- **Phase 1 review (opus): PASS.** No fence/invariant violations; D2/D3/D4/D9/D10 satisfied;
  435 tests green. Ready for Phase 2.
- **Phase 2 review (opus): PASS.** Additive installer (claude-code/copilot byte-stable), D6
  no-clobber correct (config.toml never written), D5 bundle clean, 450 tests green. Ready for
  Phase 3.
- **T9/T10 overstep:** the T9 opus implementer (afbf98a6b39364a5c) also authored T10's
  `tests/test_codex_execute.py` and set T10 in-progress — outside its dispatched scope. Its
  report only mentioned T9. Net effect benign: file is complete, 30 tests, full suite stable
  green over 3 runs; T10's own verify command passes. T10 sent to a fresh verifier for
  adversarial coverage confirmation before being marked done. T10's implementer transcript is
  shared with T9's (recorded below, best-effort attribution). The parallel T11 agent did NOT
  overstep (test_codex_usage.py did not exist until T12 was dispatched).
- **Phase 3 review (opus, 2nd attempt — 1st died on an API error): PASS, no findings.** Safety
  banners present, injectable-runner/no-real-codex discipline holds, D4/D7/D8 satisfied, journal
  invariant frozen, T10 preamble test genuinely non-tautological, 498 tests green twice. Ready
  for Phase 4.
- **CLAUDE.md revert incident (Phase 4):** a stray `git reset` to HEAD (reflog HEAD@{0}) by
  some subagent reverted the ONE tracked file with working-tree changes at that moment —
  CLAUDE.md — discarding the architect's `codex-harness` fence + `codex_pricing` run-line.
  (Untracked new files + already-modified harness_select.py/README.md survived.) T14's haiku
  agent CORRECTLY halted (its anchor, the codex_pricing run-line, was gone) instead of
  improvising. The orchestrator repaired CLAUDE.md directly (to avoid another subagent running
  git): restored the architect fence + codex_pricing run-line AND placed T14's two pinned
  insertions (invariant bullet + codex_usage run-line). No stash/hook → no recurrence risk;
  changes confirmed sticking, suite green. T14's content was orchestrator-placed, not
  subagent-authored (main-session transcript — not a per-task attributable subagent line).

- **Final review (opus, Phase 4 + overall done-check): PASS, no findings.** All 7 T13 headings +
  snapshot match pricing.codex.json; all 4 CLAUDE.md codex pieces present; installer no-clobber,
  execute dry-run, usage absence report, pricing dual-framing all smoke-clean; pricing.json /
  pricing.copilot.json / journal / skills / .claude-plugin / copilot byte-identical to HEAD;
  498 tests green twice. Kit complete.

- **Session ledger skipped (honest):** this run's transcript lives under the home-dir project
  slug (`-Users-<name>`, the session's launch cwd), not the repo slug
  (`…-Desktop-reposV2-polytropos`, which has no projects dir). The repo-slug lookup found
  nothing and the home-slug has 3 candidate transcripts — ambiguous. Per the skill's "never
  record a guessed id" rule, no `session:` line is written; cross-kit `--history` dollars
  degrade to quality-only for this kit. Quality scorecard (first-try/mix/survival) is unaffected.

## Outcome ledger

outcome: T1 model=sonnet attempts=1 result=pass review=none
outcome: T2 model=sonnet attempts=1 result=pass review=none
outcome: T3 model=sonnet attempts=1 result=pass review=none
outcome: T4 model=sonnet attempts=1 result=pass review=none
outcome: T5 model=opus attempts=1 result=pass review=none
outcome: T6 model=sonnet attempts=1 result=pass review=none
outcome: T7 model=opus attempts=1 result=pass review=none
outcome: T8 model=sonnet attempts=1 result=pass review=none
outcome: T9 model=opus attempts=1 result=pass review=none
outcome: T11 model=sonnet attempts=1 result=pass review=none
outcome: T12 model=sonnet attempts=1 result=pass review=none
outcome: T10 model=sonnet attempts=2 result=retry-pass review=revised
outcome: T13 model=sonnet attempts=1 result=pass review=none
outcome: T14 model=haiku attempts=1 result=pass review=none   # content orchestrator-placed after git-revert repair; haiku dispatch correctly halted (see Learnings)

## Agent ledger

agent: T1 id=a5f32e19668ecec71 role=implementer model=sonnet
agent: T2 id=a3694437c95e02fa5 role=implementer model=sonnet
agent: T3 id=aafca1dcee14f74cb role=implementer model=sonnet   # warm cluster T3→T4
agent: T4 id=aafca1dcee14f74cb role=implementer model=sonnet   # warm cluster T3→T4 (shared agent)
agent: T5 id=a176a74eb6e916784 role=implementer model=opus
agent: T6 id=a2666909780876c32 role=implementer model=sonnet
agent: T7 id=afa409d2b56df0401 role=implementer model=opus
agent: T8 id=ae24fc4a1f2e37c4c role=implementer model=sonnet
agent: T9 id=afbf98a6b39364a5c role=implementer model=opus
agent: T11 id=a7d071ce5dd9d75b5 role=implementer model=sonnet   # warm cluster T11→T12
agent: T12 id=a7d071ce5dd9d75b5 role=implementer model=sonnet   # warm cluster T11→T12 (shared agent)
agent: T10 id=a78737533a72abda4 role=verifier model=sonnet      # adversarial coverage check → FAIL (tautological preamble test)
agent: T10 id=a7ac64a1fcf00119a role=implementer model=sonnet   # fix: real-composition assertion (retry)
agent: T13 id=a9b5cadc2b54490cc role=implementer model=sonnet
# T14: dispatched haiku (a37beb0045d3aa2f2) correctly HALTED on reverted anchor; content orchestrator-placed (main session, no per-task subagent transcript).
# NB: T10's original test_codex_execute.py was authored inside T9's transcript (afbf98a6b39364a5c, overstep) — no separate implementer transcript for the initial write.
