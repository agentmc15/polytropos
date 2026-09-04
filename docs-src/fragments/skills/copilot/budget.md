### What it does

Your AI-Credit balance, not time or quality, is what decides whether a kit finishes. Budget
mode makes the run cheaper in exactly two places — the planner you pick yourself, the
implementer the driver dispatches — then measures whether that helped. Scope, verification
and review are untouched; each run records a labeled estimate you can total later.

### When to reach for it

- Credits are the binding constraint on a kit of routine tasks, each with a verify command
  strong enough to catch a cheaper model getting it wrong.
- **Not** when verify commands are weak: a cheap implementer behind a soft gate moves cost
  into escalation rather than saving it.
- **Not** alongside `--max-escalations 0` — a demoted task that fails verify would go
  straight to `blocked` instead of getting its one escalation.
- **Not** on the other two harnesses, and that is what the matrix's dashes mean: only
  Copilot meters every call against a finite balance that can run out mid-kit.

### Worked example

Preview first; this writes and spawns nothing (the installer resolves
`{{POLYTROPOS_ROOT}}`):

```bash
python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py run --kit <dir> --task <id> --budget --dry-run
```

A `budget:` line reads `demoted <tier> -> <tier>` beside the usual `task:`, `dispatch:` and
`verify:` lines. Drop `--dry-run` and the real run adds one more — `budget est.:` — reading
a saving, `BACKFIRED`, `unpriced`, or `no demotion this run`. Total the kit later with
`budget --kit <dir>` — no dispatch, no spend, ending in a `verdict:` line.

### Failure modes & fallbacks

- **`BACKFIRED`** — escalations cost more than the demotion saved. With only two roles
  downgraded, one escalation can erase a run's saving.
- **A LOSING verdict** — drop `--budget` for the rest of the kit; believe the ledger, not
  the theory.
- **`unpriced`** — the estimate could not be computed, so no dollars are invented; the run
  is excluded rather than counted as zero.
- **Blocked runs never fold into the headline net** — a saving beside a blocked overspend
  prints as both halves.

### Cost & safety

`--dry-run` writes and spawns nothing; a real run spends real AI Credits. The `budget est.:`
line is a labeled estimate — a named task profile, a single-dispatch first-try
counterfactual — never a bill. Demotion is exactly one tier, floored at the cheapest: it
never fabricates a rung. Reviews are exempt by design — a phase review is *more* worth
running here, not less. Candidates come from
[`data/pricing.copilot.json`](https://github.com/agentmc15/polytropos/blob/main/data/pricing.copilot.json)
at run time; pick your planner from `copilot_pricing.py models`, never from memory.

### Related

- [execute](execute.md) — the standard, undemoted run.
- [usage](usage.md) — what you actually spent afterwards.
- [Parity matrix](../index.md) — why it has no sibling elsewhere.
