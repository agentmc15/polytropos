# Measure the savings

**Goal:** replace "the cheap models were probably fine" with a number, and use that number
to pin the next kit's models.

Everything upstream of this page *routes* work to cheaper models on a belief. This is where
the belief becomes evidence. Every command here is read-only, and every one of them assumes
your shell is in a polytropos checkout — see
[where you stand matters](../getting-started/index.md#where-you-stand-matters).

## After a kit finishes: the scorecard

```bash
python3 bin/routing_scorecard.py <slug> --session <id>
python3 bin/routing_scorecard.py --demo
```

The plain form gives the per-kit verdict: what share of tasks passed verification first
try, the per-task outcomes, the model mix, and how much cheap-model work survived
independent review unchanged. With a session id it folds in the real transcript dollars —
the main loop plus every subagent — and shows them against an all-frontier counterfactual.
`--demo` runs the whole pipeline on a synthetic kit if you want to see the shape before you
have a real one.

Four more modes, all additive:

| Mode | Answers |
|---|---|
| `--live` | mid-run: is a tier struggling badly enough to justify an upgrade now? |
| `--history` | across every kit: what is each tier's track record? `--kits-dir` repeats for cross-repo |
| `--by-task` | where did the dollars actually go, per task and per role (needs `--session`) |
| `--snapshot` / `--trend` | write a dated history card, then render first-try rate over time as text |

## For one session, kit or not

```bash
python3 bin/session_cost.py
```

Prices a single session end to end — main transcript plus every subagent, deduped — and
reprices the same work under an all-one-model counterfactual, so you can see what the model
mix actually saved.

## Historical spend, per harness

```bash
python3 bin/cost_report.py --days 30
python3 bin/copilot_usage.py --days 30
python3 bin/codex_usage.py --days 30
```

The Claude-side report breaks spend down by model, names the most expensive sessions, and
flags sessions where a cheaper model would have sufficed — with the delta attached. The
Copilot and Codex reports read their own harness's local session logs, strictly read-only,
and price only what their logs actually support.

## The honesty rules that make the numbers worth reading

These are not disclaimers; they are why you can act on the output.

- **Missing data renders as null or `n/a`** — never a zero, never a guess.
- **A per-task figure is only ever the sum of transcripts that actually exist.** The
  orchestrator's own session stays one un-split line; a warm agent shared across tasks is
  attributed to the cluster as a unit rather than divided; a recorded agent whose transcript
  is gone prices as null with a note.
- **Coverage is labeled.** Cross-kit dollars aggregate only over runs that recorded a
  session, and say `partial` when that is what they are.
- **A subscription figure is a proxy, not a bill.** On Codex in particular, plan runs are
  usage-limited rather than token-billed: any dollar amount shown for them is a labeled
  API-equivalent relative-burn figure and never enters a priced total.

## Boundaries

- The scorecard reads the ledger the execute driver wrote. **A kit that was never run
  through the driver has nothing to score** — this measures runs, not plans.
- Routing changes are never automatic. `--live` recommends; upgrading is one step, upward
  only, and a separate decision.
- These are measurement commands. None of them dispatches a model or spends anything.

## Related

- [Architect, execute, measure](../concepts/architect-execute-measure.md) — why measurement
  is part of the loop rather than a postscript.
- [cost-report](../skills/claude/cost-report.md) · [usage on Copilot](../skills/copilot/usage.md)
  · [usage on Codex](../skills/codex/usage.md)
- [repo-bench](../skills/claude/repo-bench.md) — when you want measurement on *this* repo's
  own work rather than a kit's outcomes.
- [bench-routing](../skills/claude/bench-routing.md) — published benchmarks, checked against
  the outcomes above; measured results beat benchmark priors.
- [Deep dive: how it works](../deep-dives/how-it-works.md) — the measurement layer and the
  ledger-line specification in full.
