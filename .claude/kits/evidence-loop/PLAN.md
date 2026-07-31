# PLAN — evidence-loop

Kit directory: `.claude/kits/evidence-loop/` in the polytropos repo.
`autonomy: advisory`

**Precondition:** the `graph-convergence` kit has executed — this kit's analysis surfaces
(U3, U4) consume the `run=`/`parent=`/`failure=` ledger fields it introduces. U1/U2 have no
precondition.

## Goal

Close three loops the July 2026 research wave identified, without changing any routing
behavior:

1. **Constraints survive compaction** — GUARDRAILS.md content is re-asserted after
   compaction and its residency is auditable (governance-decay / constraint-pinning line of
   work).
2. **Lessons promote into scaffolding, gated** — recurring ledger defects and lessons.md
   entries become *drafted* guardrail/skill candidates for human review, never auto-applied
   (skill-library literature: experience does not automatically become a good skill).
3. **The escalation ladder is tested against evidence** — a pairwise-envelope analysis mode
   answers, from ledger history, whether the cheap→mid→strong→frontier walk beats a tuned
   two-model cascade per task class (decision-theoretic cascade result).

**Done looks like:** full suite green; a compaction-simulating fixture shows GUARDRAILS
re-assertion; `lessons_promote.py --print` drafts candidates from synthetic ledgers and
writes nothing outside gitignored output; `routing_scorecard --envelope` renders the
two-model counterfactual with honest partial-data labels; zero changes to dispatch,
escalation, or pin behavior anywhere.

## Constraints & out-of-scope

- Python stdlib-only. Never invoke the real `claude`/`copilot`/`codex` CLI. Read-only over
  all ledgers, transcripts, and home dirs; temp fixtures in every test.
- **Analysis never becomes behavior.** Nothing in this kit changes what any driver or skill
  dispatches, pins, or escalates. Evidence in, drafts and reports out.
- **No auto-application of promoted lessons.** `lessons_promote.py` output is a draft for
  the user; it never edits GUARDRAILS.md, skills, CLAUDE.md, or agent files.
- All pricing files untouched; no hardcoded prices, model ids, tiers, or thresholds.
- OUT OF SCOPE: a PreCompact hook install (compaction re-assertion stays instruction-level
  in the execute skill this kit; a consent-gated hook is future work); any knowledge-graph
  layer; changing the ladder based on U4's findings (that is a human decision fed by the
  report).

## Architecture & key decisions

- **E1 — Constraint re-assertion is instruction-level, residency is measured.** The execute
  skill instructs a GUARDRAILS.md re-read after any compaction; `context_weight` gains a
  constraint-residency audit that reports whether guardrails content is resident and at
  what weight. *Rationale:* compaction research shows governance constraints are exactly
  the content that decays silently under rewrite; the repo cannot hook compaction without
  consent-gated `~/.claude` writes, so measure + instruct now, hook later.
- **E2 — Promotion is draft-only with a two-gate shape.** Candidates require (gate 1)
  recurrence across ≥2 distinct kits and (gate 2) human acceptance; the tool implements
  gate 1 and prints for gate 2. *Rationale:* the skill-library literature's consistent
  warning — a useful skill must be specific, transferable, and stable; unvalidated
  promotion pollutes the scaffolding every future kit runs on.
- **E3 — The envelope report is counterfactual accounting, priced like session_cost.** Per
  task class (derived from ledger evidence, e.g. failure class + tier + phase shape), U4
  computes resolution rates per tier and the cost of the observed ladder vs the best
  two-model threshold cascade over the same tasks, priced at run time from pricing.json.
  *Rationale:* the cascade result says multi-stage ladders often don't beat the pairwise
  envelope — the repo has the ledger data to check locally instead of assuming either way.
- **E4 — Honesty labels everywhere.** Residency figures derived from estimates carry
  `est.`; envelope rows over kits lacking `run=`/`failure=` fields are labeled partial;
  sparse-history modes print their friendly insufficient-data line rather than a number.

## Risks & tripwires

- **Compaction is not directly observable from a skill.** If the execute-skill re-read
  instruction cannot be anchored to a detectable compaction signal, anchor it to phase
  boundaries instead (re-read at every phase start) and say so in the skill text — an
  honest coarser guarantee beats a claimed finer one.
- **Task-class derivation may be too sparse.** If ledger history can't support per-class
  envelope rows, U4 degrades to a whole-history single row with the partial label — never
  invent classes.
- **Promotion clustering drift.** If defect-kind vocabularies differ across kits (free-text
  drift), cluster on exact kind tokens only and report unclustered residue verbatim; no
  fuzzy matching in v1.
