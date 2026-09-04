### What it does

Answers two questions about one specific task before you commit a model to it: is Fable 5
actually worth it here, and if so, how should it be run for the best result. Cost ratios
are derived from the pricing file at call time rather than quoted from memory, so the
answer never goes stale even after prices change.

### When to reach for it

- Before spending Fable time on a task you're not sure clears its bar.
- Opus 4.8 already failed at something and you're deciding whether to escalate further.
- You want effort-level and framing advice for a Fable dispatch, not just a yes/no.
- **Not** for security-analysis-heavy work — Fable's own classifiers refuse much of it, and
  Opus 4.8 is the better tool there regardless of what the ratio says.

### Worked example

```
/polytropos:fable-check should this overnight migration run on Fable?
```

The answer opens with a verdict grounded in what Fable is actually better at — long-horizon
autonomous runs, a problem a prior model already failed on, deepest reasoning, heavy
sub-agent orchestration — then, if worth it, how to run it: full spec up front, effort
swept rather than defaulted to max, steps de-prescribed rather than spelled out, and a
memory surface for anything spanning multiple sessions.

### Failure modes & fallbacks

- **The task is routine or security-analysis-heavy.** Say plainly that Sonnet 5 at high
  effort likely suffices, or that Opus 4.8 is the better fit because Fable's classifiers
  decline much cyber/bio-adjacent work outright.
- **A refusal happens anyway** (`stop_reason: "refusal"`). The fallback is an Opus 4.8
  rerun, not a retried prompt on the same model.
- **Long single turns.** Plan for timeouts and streaming rather than blocking a UI on one
  request — a property of the model, not a dispatch bug.

### Cost & safety

Prices resolve in a fixed order — the live pricing file first, falling back to a vendored
snapshot only when neither the plugin path nor a relative one resolves — and that
snapshot's own recorded date gates a staleness warning past a set threshold. No ratio or
date is ever printed on this page; the skill's own resolution shows current numbers from
[`data/pricing.json`](https://github.com/agentmc15/polytropos/blob/main/data/pricing.json).

### Related

- [route](route.md) — picks which model for a task; this is the deeper go/no-go once route
  points at the frontier.
- [escalate](escalate.md) — the verify-gated ladder that reaches Fable automatically instead
  of by upfront judgment.
- [architect](architect.md) — the default escalation path for anything with an execution
  phase, not a single session switch.
