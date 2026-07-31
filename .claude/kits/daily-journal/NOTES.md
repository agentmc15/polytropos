# NOTES — daily-journal execution

Cross-task learnings maintained by the execute orchestrator. Read before dispatching later tasks.

## THE STANDING RULES (safety-critical kit)
1. Never read/write the real `~/.claude`, `~/.copilot`, `~/.codex` from a test/verify. Runtime
   defaults may point there; tests use synthetic fixtures in temp dirs with all `--*-dir`/`--*-home`
   overridden. `Path.home()` ONLY in the pinned runtime-default constants (3 in journal_collect.py,
   1 in journal_schedule.py, 0 elsewhere). Sole exception: T3's read-only ~/.codex peek.
2. Never invoke a real `claude`/`copilot`/`codex` CLI or `launchctl`. Summarizer dispatch is
   injectable; tests use fake runners / temp stubs NEVER named `claude`; `--dry-run` spawns nothing.
3. Never open a `*.db`/SQLite file; no `import sqlite3` anywhere. JSONL + flat text only.
4. Gitignore output (T1 first). Digest is metadata-only (no transcript text). Never invent Codex prices.

## Conventions
- Suite baseline at run start: 186 tests green.
- `python3 -m unittest discover -s tests [-p '<file>.py']` — never dotted-module.
- Reuse existing parsers read-only via importlib (cost_report/copilot_usage/copilot_execute) — never edit them.
- Sanctioned existing-file edits: `.gitignore` (T1), `README.md` (T13), `CLAUDE.md` (T14). Nothing else.
- Derive from data/pricing*.json; no price/model-id literals in new bin/ files (tier names ok).

## Execution plan (dependency-aware)
- Phase 1: T1 (gitignore) ‖ T2 (engine) — disjoint. Then T3→T4 STRICTLY SERIAL (same file
  journal_sources.py). Then T5 (tests). Phase 1 review.
- Phase 2: T6 (collector) → T7 (tests). Phase 2 review.
- Phase 3: T8 (summarizer) → T9 (tests). Phase 3 review.
- Phase 4: T10 (scheduler) → T11 (tests) ‖ T12 (skill) — disjoint. Phase 4 review.
- Phase 5: T13 (docs) ‖ T14 (CLAUDE.md) — disjoint. Final review + done-check.
- Adversarial safety-audit verifier on the home-touching/model/scheduler pieces: T2, T4, T6, T8, T10.

## Progress
- **T1 done** (haiku): journal/ gitignored.
- **T2 done** (opus): journal_sources.py engine + claude/copilot adapters. Read-only, greps clean.
- **T3 done** (sonnet): codex adapter (tolerant, unpriced). Read-only ~/.codex peek confirmed pinned
  fields; text/thread_name excluded per content-hygiene.
- **T4 done** (sonnet): git adapter (subprocess only here) + cursor/vscode deferred stubs. Full-file
  ADVERSARIAL VERIFIER PASS — planted secret markers never leaked into reports; tree byte-identical;
  no writes at all; module doesn't even import os.
- **T5 done** (sonnet): tests/test_journal_sources.py, 37 tests. Caught a match_model date-suffix
  fixture collision. Suite 186→223.
- **PHASE 1 REVIEW: CLEAN** (all tiers). sync_pricing_refs ok. Fence intact.
- Reuse pattern working: journal_sources loads cost_report(cr)/copilot_usage(cu) via importlib.
- T6 (collector, opus) building. Remaining: T7 tests, P2 review; T8/T9 summarizer + P3; T10/T11/T12
  scheduler+skill + P4; T13/T14 docs + P5. Safety verifier still to run on T6, T8, T10.

## COMPLETION
- ALL 14 TASKS DONE. Suite 186→300 (114 new tests). Phases 1–4 all reviewer-CLEAN.
- Adversarial safety verifiers PASS: T4 (whole journal_sources.py, secret-marker leak test),
  T6 (collector), T8 (summarizer dispatch seam), T10 (scheduler). Every home-touching/model/
  launchctl-adjacent piece audited clean.
- **BUG FOUND + FIXED (orchestrator):** T1's `journal/` gitignore was unanchored → also hid the
  new `skills/journal/` (un-committable). Fixed to `/journal/` (repo-root only). T1's original
  `^journal/$` verify line is superseded by this correctness fix. journal/ output still ignored;
  skills/journal/ trackable.
- Accepted non-blocking: journal_collect signals["config_notes"] (additive, outside frozen key set).
- Overall done-check (orchestrator): collector writes digest against temp fixture with REAL
  ~/.claude+~/.copilot+~/.codex byte-identical; summarize --dry-run spawns/writes nothing; schedule
  install→temp launch-agents (real ~/Library/LaunchAgents untouched); pricing byte-identical; no
  real CLI in journal code/tests. Path.home budget: collect 3 / schedule 1 / sources 0 / summarize 0.
- Phase 5 final reviewer dispatched. NOT committed.
