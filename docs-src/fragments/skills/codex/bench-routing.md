### What it does

Ranks the published benchmark and recommends a Codex role assignment from it — but
says plainly, every time, that this repo's own measured ledger can't check that
recommendation here, because the ledger only carries Claude-harness implementer
outcomes.

### When to reach for it

- Deciding which Codex tier a role should run on, based on published capability data.
- You want the transcription and coverage caveats stated up front, not buried.
- Sanity-checking a role assignment before writing it into a kit's model pins.
- **Not** for a measured verdict — `compare` joins against a Claude-only ledger and
  has no `--harness` flag of its own; a Codex-specific measured check doesn't exist
  yet.

### Worked example

```bash
python3 bin/bench_routing.py roles --harness codex
python3 bin/bench_routing.py rank
python3 bin/bench_routing.py demo
```

`demo` is a fully synthetic smoke — no real data touched, useful for sanity-checking the
tool itself. Recommend a role assignment as a prior to verify, never as a guaranteed
winner: the benchmark is a general-capability composite transcribed from a screenshot,
not measured Codex task performance.

### Failure modes & fallbacks

- **A recommendation reads as measured.** It isn't — the ledger `compare` joins is
  Claude-harness evidence with no per-role Codex data; say so rather than borrowing it.
- **The benchmark's cost figure gets treated as a bill.** It's a workload-ranking
  estimate, never this repository's pricing and never a bill.
- **The plugin root can't be proven.** Stop and point at [doctor](doctor.md) rather
  than guessing a path.

### Cost & safety

Every subcommand here is read-only — no dispatch, nothing spent. Benchmark workload
cost estimates are not this repository's pricing; real Codex dollars and burn come
from [usage](usage.md) and [route](route.md) instead, priced from
`pricing.codex.json` at run time.

### Related

- [route](route.md) — the per-task version of this same tiering judgment, priced for
  Codex.
- [frontier-check](frontier-check.md) — the deeper go/no-go once a benchmark points at
  the top tier.
- [Parity matrix](../index.md) — the Claude sibling, where the ledger comparison
  actually applies.
