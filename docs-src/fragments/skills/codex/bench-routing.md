### What it does

Uses benchmark evidence as a prior for Codex worker roles. It does not establish model availability, price, runtime identity, or recovery evidence, and it never overrides the central orchestration policy.

### When to reach for it

- Compare broad capability evidence before assigning a kind of work to Luna, Terra, or Sol.
- Inspect whether historical Claude-harness outcomes challenge a benchmark recommendation.
- **Not** for choosing Astra as an ordinary implementer or proving that a particular model ran.

### Worked example

```bash
python3 bin/bench_routing.py roles --harness codex
python3 bin/bench_routing.py compare
```

`roles` has a harness selector, while `compare` is intentionally cross-harness.
It has no `--harness` flag. The comparison joins the benchmark prior to available cross-harness evidence rather than inventing Codex outcomes.

### Failure modes & fallbacks

When there is no per-role outcome data for Codex, say so and let the benchmark recommendation stand unchallenged. Do not translate screenshot rankings into certainty or use a preference as Astra recovery evidence. If the runtime roster differs, central policy and pricing data win.

### Cost & safety

These commands analyze local data and do not dispatch models. The Intelligence Index is a screenshot-derived general capability composite, not this repository's pricing, a bill, or routing certainty. Subscription guidance still leads with burn index, while dollar estimates remain labeled API-equivalent proxies.

### Related

- [route](route.md) converts task characteristics into a policy-safe worker preview.
- [execute](execute.md) records planned, dispatched, and observed use separately.
- [frontier check](frontier-check.md) explains Astra's reserved role.
