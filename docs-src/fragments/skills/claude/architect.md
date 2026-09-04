### What it does

Planning a big task well takes real judgment; running it well mostly doesn't. This skill
spends the expensive judgment exactly once — Fable 5 reasons through the hard calls and
writes them down — so everything afterward can run on a cheaper model without re-deciding
anything Fable already settled. Nothing gets executed here: what comes out is a folder of
files, not a chat reply, ready for a separate skill to run.

### When to reach for it

- A task large enough that one wrong early decision would compound across many later steps.
- Reviewing an unfamiliar codebase before committing to an approach.
- A migration or greenfield project you want to run mostly on Opus or Sonnet afterward.
- **Not** for one task with a clear, checkable outcome — that's [escalate](escalate.md),
  which needs no kit at all.

### Worked example

Dispatch mode is the normal path: the session stays on its daily driver and spawns the
architecture work as a Fable subagent, carrying the full brief and conversation context the
subagent otherwise never sees. Native mode (`/model fable` in-session) exists for steering
interactively, at the cost of tying up a Fable session to do it. Before pinning models or
declaring roles in the plan, consult the evidence rather than guessing:

```bash
python3 bin/routing_scorecard.py --history   # per-tier track record across prior kits
python3 bin/routing_scorecard.py --roles     # per-role marginal value before declaring one
```

The kit itself lands as:

| File | Owner | Holds |
|---|---|---|
| `PLAN.md` | architect | goal, constraints, decisions with rationale, optional dials |
| `TASKS.md` | architect | ordered, self-contained tasks |
| `GUARDRAILS.md` | architect | kit-scoped fences, read by execute at setup |
| `NOTES.md` | execute | outcomes, ledger lines, cross-task learnings |

### Failure modes & fallbacks

- **The task is ambiguous.** Scoping questions come before Fable time is spent — a
  well-specified brief up front is what its long-horizon coherence depends on.
- **A budget or role dial gets guessed instead of measured.** The evidence is the two
  commands above; a kit built without consulting them repeats the last kit's mistakes.
- **A dial is written onto a task instead of the plan.** `autonomy:`, `budget:`, and
  `roles:` are PLAN.md lines only — writing one onto a task breaks nothing but also
  measures nothing.

### Cost & safety

Fable time is the one resource this skill exists to spend once instead of repeatedly.
Every task afterward dispatches on whatever model its own kit entry pins — the mix is
enforced automatically, so nobody has to remember to downgrade mid-run. No figure is ever
quoted here; the commands above read current numbers at run time.

### Related

- [execute](execute.md) — the other half of the contract: runs the kit this skill writes.
- [repo-bench](repo-bench.md) — measures which model to pin, on this repo's own work,
  before a kit is even built.
- [graphify](graphify.md) — grounds planning against an unfamiliar repo before PLAN.md
  is written.
