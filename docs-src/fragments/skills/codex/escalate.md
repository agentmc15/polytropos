### What it does

Runs one task through a cost-ascending ladder of Codex tiers, climbing only when a
machine-checkable check fails — but this roster ships no populated `strong` tier
today, so asking for `strong` resolves straight up to frontier. A reader who misses
that thinks there's a rung that isn't there.

### When to reach for it

- One task with a checkable outcome — a test, a build, a lint, a script that exits
  non-zero on failure.
- You want "try cheap first, climb only on failure" without babysitting each attempt.
- A task lives outside any kit and isn't worth writing a whole kit for.
- **Not** for multi-task work — prefer `$architect` over calling this in a loop, and
  inside a kit prefer the driver's own escalation cap over dispatching by hand.

### Worked example

Pin the check first, then dispatch:

```bash
codex exec "<self-contained brief>" --model <model-id>
```

Verify the result yourself — the run's own claim is not evidence. On failure, retry
once on the same model with the exact failure output attached; a second failure
climbs one tier (empty tiers skipped, so `strong` skips straight to frontier),
carrying only the failure evidence forward. On the frontier hop, prefer `-c
model_reasoning_effort=medium` first and step up one level at a time only if it still
fails.

### Failure modes & fallbacks

- **No checkable outcome exists.** Say so plainly rather than pretending a vibe is a
  verify.
- **The frontier model declines the request** (vendor safety classifiers). Fall back
  to a mid-tier hop at higher effort instead and say why.
- **The top rung still fails.** Stop and report what each tier tried, the final check
  output, and whether the task looks mis-specified.

### Cost & safety

Under a ChatGPT plan, every hop draws down usage limits — a labeled API-equivalent
proxy, never a bill; under `OPENAI_API_KEY` auth the dollars are real. Either way,
always report which rung ultimately passed, so the ladder's savings are visible.
Never name a model id from memory — derive the ladder from `codex_pricing.py models
--json` at run time.

### Related

- [architect](architect.md) — for multi-task frontier-class work, so spend
  concentrates in planning.
- [frontier-check](frontier-check.md) — the judgment call for why the top rung earns
  its spend, before you reach it.
- [effort](effort.md) — the extra lever this ladder's frontier hop uses before it
  gives up.
