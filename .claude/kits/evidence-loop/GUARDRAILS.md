# GUARDRAILS — evidence-loop

Kit-scoped fences. Execute reads this at setup; these load only when this kit runs.

- **Analysis never becomes behavior.** No task in this kit may change what any skill or
  driver dispatches, pins, escalates, or budgets. The envelope report (U4) and promotion
  drafts (U3) are inputs to a human decision; wiring them into routing logic is a different
  kit that does not exist yet. The reviewer rejects any diff that touches a dispatch path.
- **Draft-only means zero writes to scaffolding.** `lessons_promote.py` never edits
  GUARDRAILS.md files, `skills/`, `CLAUDE.md`, agent files, or anything tracked — output
  goes to stdout or the gitignored `journal/promotions/` path only. Add the gitignore entry
  in the same task that first writes there.
- **Live-CLI fence is absolute** (repeated from CLAUDE.md because U2/U4 read real-format
  fixtures): never invoke the real `claude`/`copilot`/`codex` binary; synthetic fixtures in
  temp dirs; read-only over every home dir and ledger.
- **Honesty labels are deliverables, not decoration.** `est.` on byte-derived residency,
  `partial` on envelope rows lacking ledger fields, and the sparse-history friendly line
  are acceptance criteria; removing one to make output look cleaner is a wrong change.
- **No fuzzy matching in promotion clustering.** Exact defect-kind tokens only; residue is
  reported, not guessed into clusters. Fuzzy grouping is future work behind its own review.
- **Thresholds come from data or don't exist.** No hardcoded recurrence counts beyond the
  pinned ≥2-kit gate, no hardcoded alarm or class cutoffs; where data can't support a
  figure, print the honest fallback instead.
