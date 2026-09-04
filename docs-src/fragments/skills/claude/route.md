### What it does

Most sessions run on whatever model you last picked, usually stronger than the task in
front of you needs. This turns that habit into a thirty-second decision: describe one
task, get back a short candidate table — a cost estimate and one line of rationale each —
and a single recommendation. Nothing changes on your machine until you accept what follows.

### When to reach for it

- Before anything expensive: a migration, a broad refactor, a long agentic loop.
- When a task might be big enough to deserve planning rather than one dispatch.
- When you are writing code that will call a model and need the tier plus API parameters.
- **Not** a tally of what you already spent — that is [cost-report](cost-report.md) — and
  not worth invoking for a one-line edit.

### Worked example

```
/polytropos:route --sub write unit tests for utils/date.py
```

Back comes, in order: **the mode and why** — `--sub` forced subscription framing, so every
figure is API-equivalent burn, not money spent; **a candidate table**, recommendation
bolded, the cheapest tier skipped entirely in that mode because effort is the burn lever
there; then **one action**. Accept *dispatch now* and a self-contained brief is written for
you (the subagent shares none of this conversation), run, and relayed back. Decline it and
you get the line to paste — `` `/model sonnet` `` — because only you can switch your
session's model.

### Failure modes & fallbacks

- **Prices are never recalled from memory.** The pricing file resolves through a fixed
  order, falling back last to the snapshot vendored beside the skill — and an old snapshot
  gets the estimate flagged as possibly stale.
- **Two tiers look equally plausible.** In `api` mode it picks the cheaper one and names
  the failure signal that would justify upgrading; hand that signal to
  [escalate](escalate.md) to make it a machine-checkable gate.
- **A frontier recommendation on a big task** becomes an offer of
  [architect](architect.md) instead — frontier rates once, for the planning, then cheap
  execution.
- **A measured tier map** from [repo-bench](repo-bench.md) overrides the defaults and is
  cited; one stale model id in it and route ignores the file and says so.

### Cost & safety

Routing itself is read-only and free. The only spend is a dispatch you explicitly accept,
on the model you accepted. Every number is read at run time from
[`data/pricing.json`](https://github.com/agentmc15/polytropos/blob/main/data/pricing.json).
In subscription mode the dollar column is labeled API-equivalent burn — a proxy for
rate-limit pressure, never a bill.

### Related

- [fable-check](fable-check.md) — the deeper go/no-go once route points at the frontier.
- [escalate](escalate.md) — the machine-checkable gate for that signal.
- [Deep dive: how it works](../../deep-dives/how-it-works.md) — the ladder, and the
  constraint behind that `/model` line.
