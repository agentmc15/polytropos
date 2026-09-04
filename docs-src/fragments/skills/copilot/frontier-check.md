### What it does

Answers whether a task actually earns the frontier tier's spend, and if so, how to run it
well — the same judgment as Claude's fable-check, phrased in tier words because the model
behind "frontier" on this roster changes over time and the tier itself does not.

### When to reach for it

- Long-horizon autonomous work expected to finish without human correction.
- A strong-tier model already failed on this exact task — the single strongest signal;
  try strong first if you haven't.
- The deepest reasoning or multi-source synthesis, not routine lookup.
- **Not** for routine coding or anything a strong-tier model already handles well — route
  those to strong instead.

### Worked example

```bash
python3 bin/copilot_pricing.py est <PROFILE> <FRONTIER_MODEL_ID>
python3 bin/copilot_pricing.py est <PROFILE> <STRONG_MODEL_ID>
python3 bin/copilot_pricing.py est <PROFILE> <MID_MODEL_ID>
```

Run all three for this task's size so the actual cost ratio is grounded in today's data,
never a remembered number — then state plainly what makes this particular task worth the
frontier tier's spend, since it's the most expensive lane on the roster by design.

### Failure modes & fallbacks

- **The frontier model refuses.** Vendor safety classifiers can decline cyber/bio-adjacent
  requests — check the model's `notes` field, then fall back to a strong-tier rerun and
  say the classifier, not capability, blocked it.
- **The task looks frontier-worthy but hasn't been tried on strong yet.** Try strong
  first — a strong-tier failure is the strongest evidence for the upgrade.
- **A pin overrides the default frontier candidate.** Evaluate the pinned model's own
  rates directly rather than the roster's usual pick.

### Cost & safety

The frontier tier is the most AIC-expensive lane by design — every ratio here comes from
`copilot_pricing.py` at run time, never memory, and the recommendation must say what
specifically earns that spend. Check active pins and excludes with `copilot_pricing.py
prefs` before naming a candidate.

### Related

- [route](route.md) — which model overall, before frontier becomes the question.
- [escalate](escalate.md) — the verify-gated ladder for one task, frontier as its last
  rung.
- [architect](architect.md) — for multi-task frontier-class work, so the spend
  concentrates in planning rather than every task.
