# Run a kit

**Goal:** get a multi-day piece of work done at near-frontier quality without paying
frontier prices for the whole of it.

The shape is always the same: plan once, expensively; execute many times, cheaply; escalate
one task at a time when a step gets genuinely stuck. The reasoning is in
[architect, execute, measure](../concepts/architect-execute-measure.md) — this is the
walkthrough.

## Step 1 — Architect

Give it the whole problem, not a task. Scope it in a few sentences: what you want, what is
already there, and what "done" means.

**On Claude Code:** `/polytropos:architect review this codebase and plan the storage migration`

**On Copilot CLI:** ask for the `architect` skill in your prompt, or run
`copilot --agent architect --prompt "<the whole problem>"` to use the agent whose
frontmatter carries the frontier pin.

**On Codex CLI:** `$architect review this codebase and plan the storage migration`

Read [where the money lands](../concepts/billing-modes.md#where-the-money-lands-is-not-the-same-on-every-harness)
before you start: on Claude Code and Copilot, planning is a real frontier dispatch and the
card will tell you to switch tiers first. On Codex, writing the kit dispatches nothing —
the spend arrives at execution.

## Step 2 — Read the kit before running it

You now have a directory — `.claude/kits/<slug>/` on Claude Code, `tasks/kits/<slug>/` on
the other two. Spend five minutes on it; this is the cheapest possible moment to catch a
bad plan.

- **`PLAN.md`** — check the definition of "done" is actually checkable, and read the
  out-of-scope fence. A missing fence is how kits sprawl.
- **`TASKS.md`** — skim the model pins and the `verify` commands. A task whose acceptance
  cannot be proven mechanically is the task that will waste a day.

If something is wrong, fix it here. Editing a brief costs nothing; discovering the same
problem in task eleven costs eleven dispatches.

## Step 3 — Execute

**On Claude Code:** `/polytropos:execute <slug>`

**On Copilot CLI:** ask for the `execute` skill, which drives the kit through the Copilot
execution engine task by task.

**On Codex CLI:** `$execute` — it walks the kit through status, dry run, run, verify, and
review.

The driver dispatches each task to an agent pinned to that task's model, verifies the
result in fresh context rather than trusting the implementer's claim, retries once on
failure, and updates the task's status in place. Watch the status vocabulary: `pending`,
`in-progress`, `done`, `blocked` — nothing else is a real state.

## Step 4 — Handle a blocked task

A task that fails twice does not stop the run. By default the driver *offers* a targeted
frontier consult carrying just that task's brief and the failure evidence; it only acts on
its own, without asking, when the autonomy dial is set to `auto`, and either way it counts
against the kit's optional budget dial when one is declared. Execution then drops back to
the cheap models. If you find yourself consulting on task after task, the plan is wrong, not
the executor — go back to step 2.

## Step 5 — Close the loop

Do not skip this. [Measure the savings](measure-the-savings.md) turns the run into evidence
you can pin the next kit's models with.

## Boundaries

- **The plan is not up for re-litigation during execution.** The driver's job is faithful
  dispatch, verification, and state-keeping. If the plan is wrong, stop and re-plan.
- **The architect writes the plan and the tasks, never the run notes** — the execute driver
  owns that file.
- A verify command that cannot fail is not a verify command.

## Related

- [architect](../skills/claude/architect.md) · [on Copilot](../skills/copilot/architect.md)
  · [on Codex](../skills/codex/architect.md)
- [execute](../skills/claude/execute.md) · [on Copilot](../skills/copilot/execute.md) ·
  [on Codex](../skills/codex/execute.md)
- [escalate](../skills/claude/escalate.md) — the same valve for one task that never
  justified a kit.
- [Deep dive: guide & cookbook](../deep-dives/guide.md) — every skill in narrative form,
  with worked examples.
