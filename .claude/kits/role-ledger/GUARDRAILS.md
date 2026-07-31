# GUARDRAILS — role-ledger (kit-scoped fences; read with PLAN.md before any task)

Absolute rules (money / live tooling / other agents' work — no judgment calls):

- **The three concurrently-owned files are untouchable in every circumstance:**
  `bin/bench_routing.py`, `tests/test_bench_routing.py`, `skills/bench-routing/SKILL.md`.
  Not to fix a red test, not to update a stale comment, not "just an import". If the suite
  reddens inside `tests/test_bench_routing.py`, apply PLAN R1: report the failure as the
  known cross-kit seam and stop — a reddened untouchable file is a REPORT, never an edit.
- **Never backfill ledger lines into any pre-existing kit's NOTES.md** (PLAN D5). Evidence
  is written at the moment of the event by the run that witnessed it; a reconstructed
  `findings=`/`confirmed=`/`defect:` line is fabricated evidence wearing the ledger's
  authority. This kit only teaches FUTURE runs to record.
- Never invoke the real `copilot`/`codex`/`claude` CLI from any task, test, or verify
  command; never read or write the real `~/.claude`/`~/.copilot`/`~/.codex` from tests
  (fixtures live in temp dirs passed via `--kits-dir`/`--projects-dir`). Do not commit
  or push.

Principles with the signal to read (judgment expected, drift is the failure mode):

- **Parsers degrade, they never guess.** The signal: every degraded path ends in `None`
  plus a note, never a fabricated 0, 0%, or default vocabulary value — match the exact
  style of `parse_outcomes`/`parse_agents` tolerance notes. If you find yourself writing
  `or 0` on a quality figure, you are fabricating evidence.
- **Additive means a pre-change artifact is undisturbed in meaning.** The signal: run the
  old inputs through the new code — every old NOTES.md line must produce the same parsed
  meaning as before, with new keys present-but-`None`. New line families must be invisible
  to the four existing parser families and vice versa (regex prefix disjointness).
- **One number, one home.** Implementer quality lives in the outcome ledger / per-tier
  track record only (PLAN D7); per-task dollars semantics and `AGENT_ROLES` are frozen.
  The signal that you've drifted: the same rate computable from two different card keys.
- **The two skills are one contract.** Any edit to `skills/execute/SKILL.md` or
  `skills/architect/SKILL.md` ends with re-reading BOTH against the CLAUDE.md invariant
  (layout, task fields, status vocabulary, `depends:`/`independent:`, model-override rule)
  and confirming this kit changed none of them — only execute-owned NOTES.md line families
  grew. Skill edits are body-only; YAML frontmatter is never touched.
- **Verify commands must be able to fail.** The signal: before claiming done, ask what
  concrete repo state would make this command exit non-zero; if the answer is "none", the
  clause is decoration — replace it with a content assertion (this kit's briefs carry
  `python3 -` probes for exactly this reason; run them as written).
