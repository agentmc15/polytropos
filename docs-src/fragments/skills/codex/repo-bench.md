### What it does

Plans a benchmark of Codex models against real work mined from your own repository — issue
fixes or mutation repairs — and prices the matrix without dispatching anything. On this
harness the skill stops there on purpose: ChatGPT-plan usage is not token-billed, so the
dollar ceiling that makes the live engine safe elsewhere has nothing to hold on to.

### When to reach for it

- Use it to see which tasks a benchmark would mine from a repository, and how heavy each
  candidate model would be on them.
- Use it to compare relative burn before deciding whether a live benchmark elsewhere is
  worth arranging.
- **Not** for a measured verdict or a re-tiering: `run` prints the plan and refuses without
  dispatching, and below-floor evidence cannot change routing.

### Worked example

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_repo_bench.py" plan --repo <path> --models <ids-or-tiers>
```

Read the burn index first; it is the comparison this harness can make honestly. Every
dollar beside it is an **API-equivalent proxy** — never a ChatGPT-plan bill and never a
quota conversion. Add `--json` for the same plan in machine-readable form.

| Label on the card | What it means here |
|---|---|
| `solved` | comes only from the tests oracle |
| `n/a` | the evidence is unavailable, not zero |
| similarity | closeness of a diff, never correctness |

### Failure modes & fallbacks

- **The engines or the pricing file are missing.** The skill stops and points at
  `python3 bin/harness_select.py doctor --harness codex` instead of guessing a root.
- **Someone asks for a live run.** It is refused structurally. The existing live engine
  enforces a ceiling in API dollars for another harness's models; it is not invoked for
  Codex models, and proxy dollars are not a safety ceiling.
- **A managed copy still holds the literal `{{POLYTROPOS_ROOT}}` placeholder.** Reject it
  and resolve the root from the skill's location.

### Cost & safety

Planning mines tasks and prices a matrix; it dispatches no model and spends nothing. A
target repository's tests are never run unless you supplied `--test-cmd` yourself and would
run that code by hand. Live execution stays unavailable until a port adds an explicit
dispatch-count ceiling and a Codex-native result ledger.

### Related

- [bench-routing](bench-routing.md) weighs published capability evidence for the same
  routing question.
- [route](route.md) is where a tier decision is applied to an actual task.
- [usage](usage.md) reports what Codex activity has already burned.
