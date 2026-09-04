# Two billing modes with opposite goals

The same routing question gets opposite answers depending on how the tokens are paid for.
Every routing skill here reads the mode before it reads the task, because a
recommendation that ignores it is not merely imprecise — it is wrong in the other
direction.

## `api` — optimize dollars

Any pay-per-token usage: an application you are building, or an agentic CLI running on
API-key billing. Every request has a real marginal cost, so the **cheapest sufficient
model wins**, and the cheap tier genuinely earns its keep on classification, extraction,
and bulk calls. Cache discounts and batch processing pull the same direction, which is why
the estimate accounts for them rather than quoting a headline rate.

## `subscription` — optimize rate-limit burn

A plan-billed session. The marginal dollar cost of any request is zero and the only scarce
resource is the rate-limit window. That inverts the advice:

- **Downgrading to the cheap tier is pointless.** It saves nothing that matters and costs
  you capability.
- Your daily driver should be the best model you can sustain, not the cheapest one that
  would do.
- Burn is managed with [effort levels](effort-and-context.md), not model downgrades.
- Dollar figures still appear, but labeled as *API-equivalent burn* — a proxy for how hard
  a task hits the window, never a bill.

## The mode attaches to the question, not to you

"Which model should my app call?" is an `api`-mode question even when you ask it from a
plan-billed session, because the thing being priced is your application's traffic, not this
conversation. The routers handle that distinction on their own and let you force it per
invocation when they get it wrong.

## The same idea on three harnesses

| Harness | What is actually scarce | How a figure is labeled |
|---|---|---|
| Claude Code | Dollars on API billing; the rate-limit windows on a plan | Real dollars, or API-equivalent burn |
| Copilot CLI | AI Credits, drawn against a plan allowance | Dollars **and** credits, side by side |
| Codex CLI | Dollars under an API key; usage limits under a ChatGPT plan | Real dollars, or a labeled API-equivalent proxy with a burn index |

No number in this manual is a snapshot: each harness has its own pricing file
([Claude](https://github.com/agentmc15/polytropos/blob/main/data/pricing.json),
[Copilot](https://github.com/agentmc15/polytropos/blob/main/data/pricing.copilot.json),
[Codex](https://github.com/agentmc15/polytropos/blob/main/data/pricing.codex.json)), the
files never merge, no harness reads another's, and every skill derives its figures from
them at run time.

## Where the money lands is not the same on every harness

This one catches careful readers, because two true statements look like a contradiction.

On **Claude Code** and **Copilot CLI**, planning is the expensive part by design. The
architect skill carries no model pin, so its quality tracks whatever model is driving the
session — and the Copilot card therefore tells you to switch the session to the frontier
tier before architecting anything nontrivial, or to hand the whole job to the `architect`
agent, whose frontmatter carries the frontier pin for you. Either way, producing the kit
*is* a paid frontier dispatch, and that is the point: you pay it once, and cheaper models
inherit the judgment.

On **Codex**, the architect skill carries the same "no model pin" sentence and no switch
instruction at all, plus an explicit rule that it must never invoke the `codex` CLI itself.
Writing the kit there is text on disk. The spend arrives later, when the execute driver
dispatches each task as an explicit `codex exec --model` run.

So "planning is the expensive part" and "writing the kit dispatches nothing" are **both
true, on different harnesses, for a real reason** — and it is not a ranking. Frontier work
is not cheaper on Codex; it is located at a different command. Budget for a plan by reading
that harness's own card, not by analogy to another one.

## Related

- [Architect, execute, measure](architect-execute-measure.md) — the loop this asymmetry
  sits inside.
- [architect on Copilot](../skills/copilot/architect.md) and
  [architect on Codex](../skills/codex/architect.md) — the two cards, side by side.
- [Deep dive: how it works](../deep-dives/how-it-works.md) — the full treatment, including
  what each mode does to a cost estimate.
