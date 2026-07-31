# NOTES — copilot-workflow execution

Cross-task learnings maintained by the execute orchestrator. Read before dispatching later tasks.

## THE #1 STANDING RULE
Never invoke the real `copilot` CLI (any subcommand/flag, `--help` included) — it spends the
user's real AI Credits and hits the network; the user has a live `~/.copilot`. All CLI facts are
pinned in PLAN.md/briefs. Tests mock/stub every dispatch; `--dry-run`/`--demo` are the only CLI
smoke paths and spawn nothing. Installs use temp `--copilot-home` only. The verifier audits for
real-copilot invocations on every code/test task.

## Baseline / conventions
- Suite baseline at run start: 83 tests green.
- `python3 -m unittest discover -s tests [-p '<file>.py']` — never dotted-module.
- Paths via `Path(__file__).resolve()`, never `$PWD` (Desktop/desktop case quirk).
- Never edit data/pricing.copilot.json, data/pricing.json, .claude-plugin/, skills/, completed
  kits, or any existing bin/ script except bin/harness_select.py (T8 only).

## Execution plan (dependency-aware)
- T1 / T3 / T5 are independent no-dep builders (disjoint files: copilot agents+manifest / 
  bin/copilot_execute.py / bin/copilot_ralph.py) → dispatched in PARALLEL.
- Then T2/T4/T6 (their test files, disjoint) → parallel. Then Phase 1/2/3 reviews.
- Phase 4 serial: T7 (needs T1) → T8 (needs T7). Phase 5 serial: T9 (needs all) → T10 (needs T3,T5).
- AIC-critical tasks (T3,T4,T5,T6 — the dispatch code + tests) get a fresh-context verifier
  (AIC audit); pinned-content tasks rely on my verify + phase review.

## Progress
- **T1 — done** (opus). Four workflow agents (architect→fable-5/frontier, implementer→sonnet-5/mid,
  verifier→haiku-4.5/cheap, reviewer→opus-4.8/strong) + manifest agents block. Verified.
- **T3 — done** (opus). `bin/copilot_execute.py` driver. AIC-audit verifier PASS (no real-copilot
  path except main's gated real run; build_dispatch returns argv list; set_status surgical incl.
  T1-vs-T10 collision test).
- **T5 — done** (opus). `bin/copilot_ralph.py`. AIC-audit verifier PASS (subprocess only in main's
  gated real path; --demo/--dry-run spawn nothing; PROFILES/DEFAULT_PROMPT/parse_cost pinned-exact).
- **T2 — done** (sonnet). bundle test +WorkflowAgentTier/Contract (tier via data lookup, no id
  literals). **T4 — done** (sonnet). test_copilot_execute.py, 22 tests, stub-cli not "copilot".
  **T6 — done** (sonnet). test_copilot_ralph.py, 19 tests, subprocess-patched-to-raise smoke.
- Suite: 129 green. AIC guard: no test invokes a real copilot binary.

- **Phase 1/2/3 reviews — all CLEAN** (AIC fence proven at source level in both drivers).
- **T7 — done** (haiku). lessons-loop skill vendored + manifest skills block + route reload section.
- **T8 — done** (sonnet). harness_select skills install + tests. Suite 138. Real ~/.copilot/skills
  confirmed absent (fence held).
- **Phase 4 review — CLEAN.**
- **T9 — done** (sonnet). docs/COPILOT-WORKFLOW.md (6 headings) + COPILOT-HARNESS roadmap +
  README link. (Orchestrator note: my first verify raced T9's mid-write and false-failed; re-ran
  clean = T9 OK.)
- **T10 — done** (haiku). CLAUDE.md AIC invariant + copilot_ralph.py --demo run line.
- ALL 10 TASKS DONE. Suite 138 green. Phase 5 reviewer + overall done-check running.
