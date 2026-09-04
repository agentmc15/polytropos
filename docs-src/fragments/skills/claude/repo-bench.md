### What it does

A public leaderboard measures a model against someone else's tasks in someone else's
codebase; this repo has its own conventions and its own shape of hard problem, and a model
strong in general can still be a weak fit here. This skill measures candidates on real work
mined from the repo itself: what comes back is a re-tiered strong/mid/weak map and a
daily-driver pick for this codebase, not a general score.

### When to reach for it

- Deciding which model should implement or review in this specific repo.
- Re-tiering models once the ledger looks stale against enough finished kits.
- Finding a daily-driver pick backed by measurement on this repo's own tasks.
- **Not** a live spend by default — `plan` always prices the matrix and stops; only an
  explicit, confirmed `--live --max-usd` ceiling ever dispatches anything.

### Worked example

```bash
python3 bin/repo_bench.py plan --repo <path> --models <ids-or-tiers>
```

Run `plan` first, always, and relay its total exactly as printed — construct
`--live --max-usd <ceiling>` only after the user confirms a ceiling in this conversation,
never from a guess. Grading builds a fresh substrate per cell — base state, the candidate's
in-scope patch, the withheld test blobs, nothing else — across four separate,
never-blended oracles:

| Oracle | Answers | `n/a` when |
|---|---|---|
| Tests | did it work — `solved` means this, only this | no test coverage for the task |
| Similarity | how close the diff is, never correctness | reference unavailable — a tests-only fix, a binary-only change, or an unparseable diff |
| LLM judge | a blind, randomized subjective read | its output is unparseable |
| Cost & latency | wall-clock and priced dollars per cell | never dispatched, or unpriced |

### Failure modes & fallbacks

- **`BELOW EVIDENCE FLOOR`.** Too few objectively-scored tasks to be routing-grade — say it
  exactly that way, never "preliminary"; `apply` refuses it outright.
- **`partial (cost-ceiling)`.** A run stopped mid-matrix or mid-grading — `regrade` exists
  for exactly the stranded judge column this leaves.
- **`DISAGREEMENT — signal, not error`.** The published prior, the ledger, and this run's
  own measurement disagree — investigate and say so, never average it away.
- **A `not solved` cell reverted out-of-scope work.** A labeled false negative, not proof of
  failure — the full-patch diagnostic bounds it as an interval; only the lower bound is
  routing-grade, the upper bound is forgeable.

### Cost & safety

`plan`, `verdict`, `list`, and `demo` spend nothing; only `run`/`regrade` with both
`--live` and an explicit `--max-usd` dispatch anything, checked before every single cell so
a run that hits it stops cleanly. The target repo is read-only by construction — every
touch goes through one allowlisted git path, and candidates work in sandboxes with no
history to mine. Sizing a ceiling off the generic estimate alone has measured low by an
order of magnitude — read that number on the card below. `apply` is the only action that
changes routing, always its own explicit step.

### Related

- [route](route.md) — uses this skill's applied tier map ahead of its own defaults.
- [bench-routing](bench-routing.md) — the published-benchmark leg beside this skill's own
  measurement.
- [execute](execute.md) — the observed-outcomes leg, from kits this repo has run.
