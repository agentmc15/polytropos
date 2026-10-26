# polytropos

*"of many ways" — Odysseus's epithet, and the fourth word of the Odyssey: many models, many paths, resourceful under constraint.*

polytropos is spec-driven development for coding agents, with the cost of every step in view. The frontier model writes the spec once; cheaper models, each pinned to its task, build against it; and every result is checked against the spec by something other than the model that produced it. Around that loop, it picks the cheapest model that will do each job and tells you what it will cost before you run it.

**New here?** [Pick your harness and install it](getting-started/index.md), then [route your first task](workflows/first-route.md) or [run a kit](workflows/run-a-kit.md).

## Spec-driven, end to end

A request becomes a kit: `PLAN.md` holds the spec and the design, and `TASKS.md` holds the tasks, each with its model pin, its acceptance criteria and a verify command that proves them. Each task is verified in fresh context rather than on the implementer's word. On Claude Code you approve the spec before any design is written, the kit is checked statically and its spec reviewed before the first dispatch, and a finished kit can be re-checked for drift.

- **[A guide to spec-driven development](sdd/guide.md)**: the practice, the tools that do it, and where polytropos sits among them.
- **[The two pipelines](sdd/pipelines.md)**: the usual pipeline stage by stage, then polytropos's, then the two side by side.
- **[Guardrails and hardening](sdd/guardrails.md)**: every control, with the code that implements it, the test that proves it, the stages where it acts, and what is not a boundary.

## Cheap where it can be

- **[Route per task](skills/claude/route.md).** Estimate the tier and the cost before dispatching, instead of defaulting to whatever model is active.
- **[Escalate, don't default](concepts/architect-execute-measure.md).** Plan once on the frontier, execute on pinned cheaper models, and [escalate](skills/claude/escalate.md) one stuck task at a time.
- **[See the spend](workflows/measure-the-savings.md).** Every figure is computed at run time from a pricing file, and afterwards you can measure what the model mix saved.

Two things are easy to get backwards: [the same routing question has opposite answers](concepts/billing-modes.md) under per-token and subscription billing, and [nothing can switch your session's model for you](concepts/the-one-constraint.md), which is why model choice lives in files that pin it.

## Three harnesses, one workflow

- **[Claude Code](getting-started/claude.md)**: the native home, with skills, subagents and the full architect → execute → measure loop. [Skills](skills/claude/index.md).
- **[GitHub Copilot CLI](getting-started/copilot.md)**: the same routing, adapted to Copilot's AI-Credit pricing and agent shape. [Skills](skills/copilot/index.md).
- **[OpenAI Codex CLI](getting-started/codex.md)**: the same workflow, adapted to Codex's own pricing and prompt conventions. [Skills](skills/codex/index.md).

The rosters differ deliberately; the [parity matrix](skills/index.md) explains every gap.

## Where to go next

[Getting started](getting-started/index.md) installs it; [spec-driven development](sdd/guide.md) is the method; [Concepts](concepts/index.md) explains the design; [Workflows](workflows/index.md) are task-shaped walkthroughs. The [skills reference](skills/index.md) covers every skill on every harness, generated from the source. The [deep dives](deep-dives/index.md) are the architecture end to end; the [GitHub repository](https://github.com/agentmc15/polytropos) has the code and pricing data behind it.
