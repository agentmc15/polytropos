### What it does

Runs one task through a cost-ascending ladder of Copilot models, climbing to the next tier
only when a machine-checkable check actually fails — so the frontier tier gets spent on
genuine difficulty, never routine work. You dispatch each attempt yourself and verify it
independently; a dispatched run's own claim of success proves nothing.

### When to reach for it

- One task with a checkable outcome — a test, a build, a lint, a script that exits
  non-zero on failure.
- You want "try cheap first, climb only on failure" without babysitting each attempt.
- A task lives outside any kit and isn't worth writing a whole kit for.
- **Not** for multi-task work — prefer `/architect` + `/execute` over calling this in a
  loop, and inside a kit prefer the driver's own `--max-escalations` over dispatching by
  hand.

### Worked example

Pin the check first, then dispatch:

```bash
copilot -p "<self-contained brief>" --model <model-id>
```

Verify the result YOURSELF — the dispatched run's claim is not evidence. On failure,
retry once on the same model with the exact failure output attached; a second failure
climbs one tier — `cheap → mid → strong → frontier` — taking the first model in
pricing-file order at that tier, carrying only the failure evidence forward, never a
blank re-attempt.

### Failure modes & fallbacks

- **No checkable outcome exists.** Say so plainly rather than pretending a vibe is a
  verify.
- **The frontier tier declines the request** (vendor safety classifiers). Fall back to a
  strong-tier hop instead and say why the classifier, not capability, blocked it.
- **The top rung still fails.** Stop and report what each tier tried and the final verify
  output — never keep climbing past frontier.
- **A pin or exclude empties a tier.** The ladder skips it and tops out lower — report
  that honestly, never invent a rung to fill the gap.

### Cost & safety

AI Credits are money, so always report which rung ultimately passed — that's what makes
the ladder's savings visible. Check active pins and excludes first with `python3
bin/copilot_pricing.py prefs`; inside a kit, `bin/copilot_execute.py run --kit --task
--max-escalations <N>` (plus `--pin`/`--exclude`/`--no-prefs`) implements this same ladder
without hand-dispatching.

### Related

- [frontier-check](frontier-check.md) — the judgment call for why the top rung earns its
  spend, before you reach it.
- [execute](execute.md) — runs this same ladder for kit tasks, with statuses and a cap.
- [budget](budget.md) — a cheaper starting tier for kit work, with this ladder as its
  safety net.
