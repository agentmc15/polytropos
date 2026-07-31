---
name: lessons-loop
description: Capture a durable lesson every time the human corrects the agent — or a task escalates models — so the same mistake doesn't recur. Use immediately after any user correction and after any model escalation. Also use at session start to load relevant past lessons.
---
# lessons-loop

Vendored from aesop (github:agentmc15/aesop) `registry/skills/lessons-loop` at commit 5506617,
with a Copilot-harness routing category added. A prompted-Reflexion pattern: the model forgets
between runs, so lessons live on disk. After a correction, write down the pattern and a rule
that prevents it; review lessons at session start. Iterate until the mistake rate drops.

## Steps
1. **On correction:** append to `tasks/lessons.md` an entry with: the failure pattern, the
   lesson (a rule for next time), and the contexts it applies to.
2. **On session start:** read `tasks/lessons.md`; surface the lessons relevant to the current
   task.
3. **Hygiene:** deduplicate, keep entries concise, add a date, and prune stale/contradicted
   ones so bad lessons don't pollute future behavior.

## Routing lessons (Copilot-harness category)
A misroute is a correction too. Record an entry with `"applies_to": ["routing"]` whenever:
- a task escalated — its pinned model failed the verify command and a higher tier had to
  finish it (the execute driver marks these as `lesson-candidate (routing):` lines in the
  kit's NOTES.md); or
- a tier was grossly overprovisioned (frontier spent on work a mid model does routinely).
State the rule in routing terms — task shape → tier — so the `route` agent can apply it at
session start. Tiers and model ids come from `data/pricing.copilot.json` at run time; never
bake a price or a model ranking into a lesson.

## Example entry
```json
{"date": "2026-07-01", "failure_pattern": "pinned a cheap-tier model for a multi-file refactor; verify failed twice and the task escalated to strong", "lesson": "multi-file refactors start at the strong tier", "applies_to": ["routing"]}
```

## Notes
- Keep lessons project-scoped to avoid leaking one project's quirks into another.
- This is the same trick the eval harness uses: every production failure becomes a durable
  test/rule.
