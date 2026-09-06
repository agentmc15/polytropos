---
description: "Reviews one completed kit phase for drift, invariant violations, and weak evidence."
---

> Deprecated compatibility prompt; prefer the `phase-reviewer` custom agent.

Review one completed phase in tasks/kits/<slug> read-only. Do not implement fixes, edit statuses, or write NOTES.md. Read PLAN.md, TASKS.md, and all kit guardrails; the task vocabulary is exactly pending | in-progress | done | blocked.

Compare the completed phase with its file fences, repository invariants, pinned content, dependencies, and intended architecture. Inspect verification evidence and rerun focused checks when useful. Report concrete drift, scope creep, contract breaks, or weak verification with file-and-line evidence, ordered by severity. If no issue remains, state that the phase passes and identify any residual risk. You are evidence for final acceptance, not final acceptance itself; do not select a model or write recovery evidence.
