### What it does

Describe one task and get a short candidate table, rationale, and recommendation. Nothing
changes on your machine until you accept what follows.

The first row in each pricing tier is the current default. Older rows support historical
costing and compatible explicit pins; their presence is not an availability guarantee.

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

The reply states the mode and why — `--sub` means API-equivalent burn, not money — then a
candidate table and one action. Accept *dispatch now* for a self-contained subagent brief,
or decline for the exact `/model sonnet` command; only you can switch the session model.

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
