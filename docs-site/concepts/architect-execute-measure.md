# Architect, execute, measure

The routing skills answer "which model for this task?" one task at a time. This is the
answer for work too big to be one task: **spend frontier-model time once, on thinking, and
write the thinking down in a form cheaper models can execute faithfully.**

## The loop

1. **Architect.** A frontier-tier run interrogates the scope once and emits an execution
   kit — not a document you read, but scaffolding the next phase runs on.
2. **Execute.** A cheaper driver loops the kit's tasks, dispatching each to a model-pinned
   agent, verifying every result in fresh context, retrying once, and moving state forward.
3. **Escalate, narrowly.** A task that fails twice gets a single-task frontier consult
   carrying the failure evidence — one brief, not the whole project — and execution drops
   back to cheap.
4. **Measure.** The run leaves machine-readable ledger lines behind, and reading them turns
   "the cheap models were probably fine" into a number.

The frontier model's involvement is a short phase near the beginning plus the occasional
consult. Execution quality is bounded below by the kit rather than by the executor's
unaided judgment — which is the whole bet.

## What a kit actually is

A directory, in the project being worked on, with a fixed shape:

- **`PLAN.md`** — the durable thinking: the goal with a checkable definition of "done",
  constraints and an explicit out-of-scope fence, architecture decisions each with their
  rationale, and the risks implementers must avoid.
- **`TASKS.md`** — ordered work under phase headings. Every task carries an `id`, `title`,
  `status`, `model`, and a dependency marking, plus a **self-contained brief** (the
  implementer sees only that brief, so every fact it needs is pinned into it), concrete
  acceptance criteria, and a verify command that proves them mechanically.
- **`GUARDRAILS.md`** on Claude Code — the kit-scoped fences, which load only while that
  kit runs and never tax other sessions.
- **`NOTES.md`** — owned by the execute driver, never written by the architect.

Status vocabulary is exactly `pending`, `in-progress`, `done`, `blocked`. The location
differs by harness — `.claude/kits/<slug>/` on Claude Code, `tasks/kits/<slug>/` on Copilot
and Codex — but the contract does not, which is why the two skills are kept in sync
deliberately.

## Why measurement is part of the loop, not a postscript

Because the execute driver records per-task outcomes as it goes, the run ends with an
auditable trail: which model ran each task, how many attempts it took, whether the result
passed first try or after a retry or only after escalation, and whether independent review
left it unchanged. Reading that trail back is what makes the *next* kit's model pins a
data-driven choice instead of a hunch.

The honesty rule that governs it is worth stating once: **missing data renders as null or
`n/a`, never as a zero and never as a guess.** A per-task dollar figure is only ever the
sum of transcripts that actually exist; a shared transcript is attributed to its cluster as
a unit rather than divided; the orchestrator's own session stays one un-split line. See
[measure the savings](../workflows/measure-the-savings.md) for how to read it.

## Related

- [Run a kit](../workflows/run-a-kit.md) — the walkthrough, harness by harness.
- [architect](../skills/claude/architect.md) and [execute](../skills/claude/execute.md) —
  the two cards that share this contract.
- [escalate](../skills/claude/escalate.md) — the same escalation valve, for a single task
  that never needed a kit.
- [Deep dive: how it works](../deep-dives/how-it-works.md) — the workflow end to end, with
  a worked example and the full ledger-line specification.
