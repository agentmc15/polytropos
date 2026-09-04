### What it does

When someone proposes moving a role onto a stronger or newer model, this skill answers with
three separate pieces of evidence instead of one: what a published benchmark says, what
this repo's own execution ledger has actually measured, and whether the two agree. Its
`compare` subcommand exists specifically to stop a plausible-sounding upgrade the ledger
doesn't actually support.

### When to reach for it

- Someone proposes upgrading an implementer, verifier, or orchestrator role to a higher tier.
- You want a routing recommendation checked against outcomes, not just a bigger model's
  reputation.
- Sanity-checking a routing change before it goes into a kit's `PLAN.md`.
- **Not** for a role this repo has never run a kit task on — `compare` reports
  `no_role_evidence` rather than inventing a verdict for it.

### Worked example

```bash
python3 bin/bench_routing.py compare
```

The card joins each ranking pick against the measured first-try rate per tier. A
nominally-positive gain — one tier already clearing nearly every task against another a few
points behind — reads `not_supported`: a few points don't justify a routing change, and the
card says so instead of dressing it up as "worth considering." Where a tier has too few
finished tasks, it prints "insufficient sample" rather than guessing one.

### Failure modes & fallbacks

- **A role has no ledger evidence** — architect, reviewer, orchestrator, and verifier all
  read `no_role_evidence`; the benchmark pick stands unchallenged, and it should be relayed
  that way rather than paraphrased as support either direction.
- **The recommended model is measured at fewer effort points than its tier-mate.** The tool
  computes and reports this coverage gap; repeat the caveat instead of dropping it.
- **The benchmark snapshot looks stale.** It's screenshot-transcribed, not an API export —
  flag it as re-verify-worthy against its own recorded date rather than treating it as live.

### Cost & safety

Every subcommand here is read-only: no dispatch, no spend, nothing written. `rank`,
`roles`, and `compare` all resolve numbers from the pricing files and the benchmark
snapshot at run time rather than from memory. The benchmark's own cost ratio is a ranking
figure inside its workload, never this repo's real spend — never add it to what
[cost-report](cost-report.md) or `execute`'s scorecard already report.

### Related

- [route](route.md) — the same tiering judgment, applied per task instead of per role.
- [repo-bench](repo-bench.md) — the third leg: measured on this repo's own work, not a
  published index.
- [execute](execute.md) — the loop whose ledger `compare` reuses as its evidence.
