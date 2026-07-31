# Per-task dollars — attributing delegated cost by task and role

`docs/ROUTING-HISTORY.md`'s `## Deliberately not built` section named per-task dollar
attribution and refused it, on the grounds that transcripts price sessions, not tasks, and
splitting a session's cost across the tasks it covered would be an estimate presented as a measurement.
This kit changes the DATA, not that honesty rule: `session_cost` already
partitions a session into the MAIN transcript (the orchestrator/driver) and per-subagent
`*.output` transcripts (one per dispatched agent). Once a new NOTES.md line records which
agent served which task, a task's DELEGATED cost is exactly the standalone price of that
agent's transcript — cleanly attributable, no splitting required — while the orchestrator's
own share stays what it always was: interleaved across every task, and never divided.

## The partition

`session_cost` separates a session into two kinds of transcript: the MAIN transcript (the
orchestrator/driver run, interleaved across all tasks in the kit) and one `*.output` file per
dispatched subagent, filename stem equal to the agent id. That partition is the whole
foundation here. A task's delegated cost is defined as the sum of the standalone prices of the
subagent transcript(s) that served it — each `*.output` file priced on its own, independent of
every other file. The orchestrator's own share is reported as ONE explicitly un-attributable
line, `orchestrator (main session): $Y — interleaved across all tasks; never split per task`
— no heuristic (message counts, timestamps, task markers) may ever divide that line across
tasks, because any such split would be exactly the kind of estimate presented as a measurement
that the routing-history kit refused to build.

Phase reviewers and ad-hoc scouts are dispatched per phase or per run, not per task — they are
deliberately never recorded against a task, and their transcripts land in an honest
`unattributed subagents` line instead of being guessed onto whichever task happened to be
active.

## The agent: line

The recorded datum is a fourth OPTIONAL, execute-owned NOTES.md line — grammar verbatim:

```
agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation> model=<model>
```

It follows the precedent already set by `outcome:`, `reroute:`, and `session:`: NOTES.md is
execute-owned, so a new line shape inside it is not a contract change, and it is never a task
field — `parse_tasks` is untouched. The `/execute` orchestrator appends one `agent:` line the
moment a per-task dispatch returns (the Agent tool reports an agent id on every dispatch, and
that id is the transcript filename stem under the tasks scratch dir). A retry-implementer, a
verifier, and a Fable escalation consult on the same task each get their own line with their
own agent id. A warm sidekick — one continued agent serving several tasks — puts the SAME
agent id on every task it serves; that repetition is exactly what lets the breakdown recognize
a shared transcript and attribute it to the cluster instead of guessing a split. No script
ever writes this line; it is read-only input to `--by-task`, same as `outcome:`/`reroute:`/
`session:` are read-only input to the other modes.

## Reading the breakdown

Usage:

```bash
python3 bin/routing_scorecard.py <kit-slug|kit-dir> --session <id> --by-task
python3 bin/routing_scorecard.py <kit-slug|kit-dir> --session <id> --by-task --json
python3 bin/routing_scorecard.py <kit-slug|kit-dir> --session <id> --by-task --tasks-dir <dir>
python3 bin/routing_scorecard.py --demo --by-task           # synthetic smoke, no real data
```

`--by-task` requires `--session` — per-task dollars attribute one session's transcripts, and
without the flag the scorecard's output is byte-identical to before. `--tasks-dir` overrides
where the `*.output` transcripts are discovered, for when the tasks scratch dir has moved.

The markdown card adds a `## Per-task dollars` section with:

- **The role table** — one row per task, columns Implementer $ / Verifier $ / Escalation $ /
  Total $. A cell is `—` when that role recorded no agent for the task, `n/a` when it recorded
  one but nothing priced, and a dollar figure when at least one agent's transcript priced. A
  task also served by a shared warm agent carries a `*` marker — its total deliberately
  excludes the shared transcript, which is priced on the cluster line instead.
- **The cluster lines** — one per shared warm agent, rendered
  `` shared warm agent `<agent-id>` across <task-id>, <task-id> (<roles>): $X (not split) ``.
  A shared transcript is ONE continued agent serving MULTIPLE tasks, and it is attributed to
  the cluster as a unit — never divided among the tasks it served.
- **The orchestrator line** — the main transcript's standalone price, always reported
  separately from every task, worded `interleaved across all tasks; never split per task` (or
  `n/a (main transcript not found)` when the main transcript is missing).
- **The unattributed line** — `unattributed subagents (phase reviewers, scouts, unrecorded
  dispatches): <n> transcript(s), $Z`, printed only when there is at least one such transcript.
- **The `coverage` label** — `full` when every referenced agent id priced and the main
  transcript priced, `partial` when some didn't, `null`/n/a when there are no kept `agent:`
  events at all.
- **The parts-vs-whole reconciliation note** — the whole-session Dollars block stays the
  authoritative total, computed with one global message-id dedupe across every transcript in
  the session. The per-task breakdown prices each file standalone, so a message id shared
  across transcripts counts once in the whole but per-transcript in the parts. When the parts'
  sum differs from the whole by more than the reconciliation epsilon, a note names the
  difference and its two causes (shared message ids; `--include`d files outside the
  attribution) — the note explains the gap, it never adjusts either figure.

The JSON form gains a top-level `by_task` key (only when `--by-task` is passed) carrying
`schema_version`, `coverage`, `tasks`, `clusters`, `orchestrator`, `unattributed`, and `notes`
— nested here, never appended to the card's top-level `notes`, so a card built without the
flag stays byte-identical to before this kit shipped.

## The honesty rules

- The main transcript is never split per task. It is always reported as one explicit,
  un-attributable orchestrator line.
- A shared warm-cluster transcript is never divided among the tasks it served. It is
  attributed to the cluster as a unit, on its own line, excluded from every served task's
  role table and total.
- A recorded agent id whose `*.output` transcript is gone (the tasks scratch dir is
  session-scoped tmp and may be cleaned after the run) prices as `null` plus a note naming the
  id — never a zero, never a guess.
- A per-task or per-cluster total is only ever the sum of transcripts that actually exist. A
  role or task with agents but nothing priced renders `n/a`, not `$0.00`.
- With no `agent:` lines recorded anywhere in NOTES.md, the breakdown is n/a end to end —
  `coverage: null`, empty tasks/clusters, a null orchestrator figure, an empty unattributed
  line — and the existing whole-kit `--session` dollars print completely unchanged.
- The parts-vs-whole reconciliation is always a note, never an adjustment of any figure — the
  whole-session total and the per-task sum are allowed to differ by a small, explained amount;
  nothing silently reconciles them into agreement.

## Deliberately not built

- **Estimated splitting of the orchestrator or a shared transcript** — refused by design, not
  merely deferred. No heuristic (message counts, timestamps, task markers) is ever acceptable
  here; the whole point of this kit is measuring only what the `agent:` ledger actually
  attributes, and reporting everything else honestly as unattributable.
- **Per-task dollars inside `--history`** — the cross-kit view stays per-kit. Folding per-task
  granularity into the cross-kit aggregate is a possible future kit, not this one.
- **Auto-pin or auto-downgrade** — unchanged from every prior kit in this series; the routing
  signal (live or historical) stays advisory by design, and per-task dollars add evidence, not
  automation.
- **Main-session model switching** — still the upstream ask, still tracked in
  `docs/FUSION-TIER1.md`.
