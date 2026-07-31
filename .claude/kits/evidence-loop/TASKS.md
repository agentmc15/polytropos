# TASKS — evidence-loop

Repo root: the polytropos checkout. Run all verify commands from there.
Read `PLAN.md` (same directory) first — decisions E1–E4, the precondition note, the
out-of-scope fence, and `GUARDRAILS.md`. Status vocabulary:
`pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's
`model` parameter. `depends:` lists hard ordering. **Warm-cluster candidates:** U2→U3 share
no files — all tasks fan out fresh except the serial U4→U5 docs pair.

Standing rules for every task:

- Read-only over ledgers, transcripts, `~/.claude`, `~/.copilot`, `~/.codex`; never invoke
  the real `claude`/`copilot`/`codex` CLI; temp `--kits-dir`/fixture dirs in every test.
- **Analysis never becomes behavior (PLAN out-of-scope).** No task changes dispatch,
  escalation, or pin logic anywhere.
- No hardcoded prices, model ids, tiers, or alarm thresholds — pricing from pricing.json at
  run time; thresholds derived from data or absent.
- Python stdlib-only. Full-suite verify: `python3 -m unittest discover -s tests -v` must
  pass before any task is claimed done, in addition to the task's own verify command.
- If a brief's pinned anchor disagrees with repo reality, STOP and report — never improvise.

---

## Phase 1 — Constraints survive compaction

### U1 — GUARDRAILS re-assertion in the execute skill
- status: done
- model: opus
- depends: (none)
- Brief: Per PLAN E1 and its tripwire: `skills/execute/SKILL.md` gains an explicit
  re-read-GUARDRAILS rule anchored to every phase start and to any point the orchestrator
  observes its context was compacted (state both anchors; the phase-boundary one is the
  guarantee, the compaction one is best-effort). One sentence of rationale in the skill
  (constraints are the content compaction erases first). Re-check the architect/execute
  kit-contract sync per CLAUDE.md — GUARDRAILS.md stays architect-owned, read semantics
  only change on the execute side.
- Acceptance: execute SKILL.md states both re-read anchors and the rationale; no change to
  GUARDRAILS.md ownership or file layout; architect SKILL.md untouched unless the sync
  check requires a mention.
- Verify: `grep -qi 'GUARDRAILS' skills/execute/SKILL.md && grep -qi 'phase' skills/execute/SKILL.md && python3 -m unittest discover -s tests`

### U2 — Constraint-residency audit in context_weight
- status: done
- model: sonnet
- depends: (none)
- Brief: `bin/context_weight.py` gains a `constraints` mode (and a section in the existing
  resident-surface audit): given a kit dir, report whether GUARDRAILS.md content is
  resident in the reconstructed window, at what estimated weight, and how that weight
  trends across the session's growth curve. Byte-derived figures carry `est.` (PLAN E4);
  Copilot/Codex fidelity limits keep their existing verbatim not-available lines. Synthetic
  fixtures only; follow the engine's existing seam pattern (`--projects-dir`, explicit
  `--kit`).
- Acceptance: demo mode shows a residency section on a synthetic session containing and
  lacking guardrails content respectively; `est.` labels present; harness fidelity lines
  unchanged; zero `Path.home()` additions.
- Verify: `python3 -m unittest discover -s tests -p 'test_context_weight.py' -v`

---

## Phase 2 — Lessons promote, gated

### U3 — bin/lessons_promote.py (draft-only)
- status: done
- model: sonnet
- depends: (none)
- Brief: New stdlib-only tool per PLAN E2: scan a `--kits-dir` for NOTES.md `defect:` lines
  and the repo's `tasks/lessons.md`; cluster on exact defect-kind tokens (no fuzzy matching
  — PLAN tripwire); a candidate requires recurrence across ≥2 distinct kits (gate 1); emit
  drafted guardrail/skill-note candidates with their evidence lines (kit, task, kind) to
  stdout with `--print` and to a gitignored `journal/promotions/<date>.md` otherwise.
  NEVER edits GUARDRAILS.md, skills, CLAUDE.md, or agent files (gate 2 is the human).
  Unclustered residue is listed verbatim at the end.
- Acceptance: synthetic multi-kit fixtures produce a candidate only at ≥2-kit recurrence;
  single-kit kinds land in residue; no writes outside the gitignored path; `--print`
  writes nothing; the tool imports nothing that dispatches.
- Verify: `python3 -m unittest discover -s tests -p 'test_lessons_promote.py' -v`

---

## Phase 3 — Test the ladder against evidence

### U4 — routing_scorecard --envelope analysis mode
- status: done
- model: sonnet
- depends: (none)
- Brief: Per PLAN E3: over `--history` ledgers, derive task classes from available evidence
  (tier pin × failure class where `failure=` exists; degrade to whole-history with the
  partial label where it doesn't — PLAN tripwire), compute per-class per-tier resolution
  rates, then price (from pricing.json at run time, reusing session_cost seams where they
  fit) the observed ladder cost vs the best two-model threshold cascade over the same
  outcomes. Output is a labeled counterfactual report; it changes no routing behavior and
  writes nothing. `--json` mirrors the table.
- Acceptance: synthetic histories where the middle tier rarely resolves show the two-model
  counterfactual cheaper, and vice versa; partial/sparse labels render per PLAN E4; no
  behavior surface touched; `--demo --envelope` runs on synthetic kits with no real data.
- Verify: `python3 -m unittest discover -s tests -p 'test_routing_scorecard.py' -v`

### U5 — docs: research notes + envelope interpretation
- status: done
- model: haiku
- depends: U4
- Brief: `docs/EVIDENCE-LOOP.md`: what each surface measures (residency, promotion,
  envelope), how to read the envelope report (it is evidence for a human ladder decision,
  never an auto-change), and the research grounding in one short section (governance decay
  under compaction; skill-promotion validation; pairwise cascade envelope) — plain
  citations, no prices, no model ids. README pointer added beside the other doc links; one
  cross-link from docs/GRAPH-ENGINEERING.md's rejected/accepted list if that doc exists by
  execution time (skip silently if not — it lands with graph-convergence T12).
- Acceptance: doc exists and covers the three surfaces + reading guidance; README links
  it; conditional cross-link handled as specified.
- Verify: `test -f docs/EVIDENCE-LOOP.md && grep -q 'EVIDENCE-LOOP' README.md && python3 -m unittest discover -s tests`
