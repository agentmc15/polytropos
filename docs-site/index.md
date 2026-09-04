# polytropos

*"of many ways" — Odysseus's epithet, and the fourth word of the Odyssey: many models, many paths, resourceful under constraint.*

polytropos is a plugin that picks the right model for the task in front of you, tells you what it will cost before you run it, and keeps the frontier model in reserve for work that actually needs it. It is not a single skill — it is a small set of routing, execution, and measurement tools sharing one philosophy across every harness they run in.

**New here?** [Pick your harness and install it](getting-started/index.md), then [route your first task](workflows/first-route.md).

## The idea, in one screen

Most sessions do not need the most expensive model available. They need the *cheapest model that will get the job done*, with a clear signal for when the job is bigger than that. polytropos operationalizes that as three moves:

- **[Route per task](skills/claude/route.md).** Estimate which tier the work needs and what it will cost before dispatching it, instead of defaulting to whatever model happens to be active.
- **[Escalate, don't default](concepts/architect-execute-measure.md).** A frontier model does the expensive meta-work once — a codebase review, a migration plan — and hands off an execution kit of task briefs, model-pinned subagents, and verification loops that a cheaper model runs to completion, [escalating back](skills/claude/escalate.md) only when a step gets stuck.
- **[See the spend](workflows/measure-the-savings.md).** Every recommendation is backed by a real number, computed at run time from a pricing file, never a hardcoded guess — and afterwards you can prove what the model mix actually saved.

Two things here are easy to get backwards: [the same routing question has opposite answers](concepts/billing-modes.md) depending on whether you pay per token or per subscription, and [nothing can switch your session's model for you](concepts/the-one-constraint.md) — which is why model choice lives in files that pin it.

## Three harnesses, one workflow

polytropos ships the same routing and cost-awareness into every agentic CLI it supports:

- **[Claude Code](getting-started/claude.md)** — the plugin's native home: skills, subagents, and the architect → execute → measure loop. [Skills](skills/claude/index.md).
- **[GitHub Copilot CLI](getting-started/copilot.md)** — the same routing logic, adapted to Copilot's AI-Credit pricing and agent shape. [Skills](skills/copilot/index.md).
- **[OpenAI Codex CLI](getting-started/codex.md)** — the same workflow again, adapted to Codex's own pricing and prompt conventions. [Skills](skills/codex/index.md).

Each gets a real, idiomatic integration rather than a lowest-common-denominator wrapper: the judgment is shared, the mechanics are not forced to match, and the rosters differ deliberately — the [parity matrix](skills/index.md) explains every gap.

## Where to go next

[Getting started](getting-started/index.md) installs it; [Concepts](concepts/index.md) explains the design in four short pages; [Workflows](workflows/index.md) are task-shaped walkthroughs. The [skills reference](skills/index.md) covers every skill on every harness — each page carries a practical guide above the skill card itself, the exact text the model reads at run time, generated from the source so it can never drift. The [deep dives](deep-dives/index.md) are the architecture end to end; the [GitHub repository](https://github.com/agentmc15/polytropos) has the code and pricing data behind it.
