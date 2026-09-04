# The one constraint that shapes everything

**Nothing in Claude Code can programmatically switch the main session's model.** Not a
hook, not a skill, not a settings write mid-session — only the user typing `/model`.

That sentence looks like a limitation and is really an architecture. Once you accept it,
every apparently odd choice in this repository stops being odd.

## Two things *are* programmable

1. **Subagents can pin models.** An agent file's frontmatter can declare a model — the
   aliases `haiku` / `sonnet` / `opus` / `fable`, or a full id — and the dispatch tool
   accepts a per-invocation model parameter that overrides it. So delegated work can run on
   a different model than the one you are sitting on.
2. **Skills can orchestrate.** A skill cannot change the model it is running on, but it can
   *dispatch* work to subagents on any model it likes.

## What follows from it

The router is therefore **advisory for your own session and operational for everything it
can delegate**. When it recommends a switch, it prints the exact command for you to paste;
when it recommends dispatching, it can simply do it, with a self-contained brief written
for a subagent that does not share your conversation.

And the whole architect → execute design is built on lever one. Model choice is not a
runtime decision made by a clever skill; it is **embedded in files** — the kit's task
briefs each carry a model, and the agents they dispatch to carry their own pins. A task's
own model field overrides the agent's frontmatter at dispatch. That is why the model mix
enforces itself while a kit runs for hours: nobody has to remember to stay cheap, because
the cheapness is written down.

It is also why a skill is not a slash-command registry. A skill is instructions loaded into
the session you already have, running on the model you already chose. The same skill reads
very differently on a cheap model than on a strong one — which is exactly why the
[architect card tells you to switch first](billing-modes.md#where-the-money-lands-is-not-the-same-on-every-harness)
rather than promising quality it cannot deliver on its own.

## The same constraint, three shapes

- **Claude Code** — as stated above; the router prints a `/model` line and dispatches
  through subagents. See [Claude Code skills](../skills/claude/index.md).
- **Copilot CLI** — skills carry no model pin and run on the session's current model;
  **agents** can pin one in frontmatter, and are the surface to reach for when the model
  matters. See [Copilot CLI skills](../skills/copilot/index.md).
- **Codex CLI** — skills carry no model pin either. When the execute driver dispatches a
  kit task non-interactively, it has already resolved that task's model field and passes it
  explicitly on the command line — so the model that runs a dispatched task was chosen by
  the kit, not by a skill re-routing itself mid-flight. The four optional Codex agents
  deliberately carry no model or effort pin at all, leaving that to the caller. See
  [Codex CLI skills](../skills/codex/index.md).

Three harnesses, one honest position: *tell the human what to switch to, and pin the model
anywhere a file can carry it.*

## Related

- [Architect, execute, measure](architect-execute-measure.md) — the loop that lever one
  makes possible.
- [route](../skills/claude/route.md) — the advisory half, in practice.
- [execute](../skills/claude/execute.md) — the operational half.
- [Deep dive: how it works](../deep-dives/how-it-works.md) — the constraint in its original
  context, with the component architecture around it.
