### What it does

Runs an execution kit end to end: works through `TASKS.md` in order, dispatching each task
to the kit's model-pinned subagents, verifying every result independently, and updating
state as it goes. The orchestrator itself never re-litigates the plan — Fable already made
the expensive calls when [architect](architect.md) built the kit; this skill's job is
faithful dispatch, verification, and record-keeping, one task at a time: mark
`in-progress`, dispatch, verify yourself (never trust the subagent's own claim), then mark
`done` or `blocked` and log one outcome line. A phase boundary dispatches the reviewer
before the next phase's first task begins.

### When to reach for it

- The user says execute, continue, or resume a kit `/polytropos:architect` already built.
- Several tasks need dispatching and verifying in sequence, not just one.
- You want a routing-quality record (`NOTES.md`) that later measures the kit's own model
  mix.
- **Not** for a single ad-hoc task with no kit behind it — that's [escalate](escalate.md),
  which needs no `PLAN.md`/`TASKS.md` at all.

### Worked example

Every finished task appends one `outcome:` line, and the same file carries five more
machine-read families a later report reads back:

| Line family | Records | Read by |
|---|---|---|
| `outcome:` | model, attempts, pass/fail/blocked | `routing_scorecard.py <slug>` |
| `agent:` | which subagent id served which task | `--by-task` (per-task dollars) |
| `reviewer:` | a phase review's findings, adjudicated | `--history`'s role-quality section |
| `defect:` | a confirmed brief defect, by kind | `--history`'s brief-defect floor |
| `reroute:` | a live upgrade recommendation | `--live` (this run) |
| `session:` | the transcript id for cross-kit history | `--history` |

`python3 bin/routing_scorecard.py <slug>` renders the finished kit's own scorecard;
`--history` aggregates every kit's ledger into a cross-kit track record.

### Failure modes & fallbacks

- **A task fails verify twice.** It's marked `blocked`, logged with a `failure=` class
  (`execution`/`coherence`/`verification`), and offered to a Fable consult carrying only
  that task's evidence — never a blank re-attempt.
- **The declared roster's `attempts=` climbs.** A `test-author`/`red-team` role catching a
  defect before `done` structurally costs a retry — that dip is the roster working, not the
  implementer regressing; never re-pin a tier down because of it.
- **A `budget:` cap is reached mid-run.** The run stops cleanly, leaves the task's status
  untouched, and logs `result=budget-stop` — a stop, never a verdict on the task.

### Cost & safety

The orchestrator itself dispatches nothing directly — every dollar spent is a subagent
running at whatever tier its task is pinned to, or an escalation running on Fable through
the one-at-a-time consult valve. Live re-routing is upgrade-only, one tier step, and never
reaches frontier on its own — Fable is reached only through the escalation valve, never a
live-routing recommendation. A warm implementer serves only a same-file, same-pin cluster
before a fresh spawn starts the next one; the verifier is never warmed.

### Related

- [architect](architect.md) — writes the kit this skill runs.
- [bench-routing](bench-routing.md) — checks a routing change against exactly this ledger.
- [repo-bench](repo-bench.md) — measures which model to pin before the next kit is even
  built.
