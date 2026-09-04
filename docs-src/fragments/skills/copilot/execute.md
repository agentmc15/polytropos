### What it does

Drives an execution kit through to done, task by task — but with a real, named limit
worth stating up front: this harness has no parallel fan-out and no warm agent clusters.
Kit tasks run serially, one `run` invocation at a time, even ones marked `independent:`
(that marking means "safe in any order," not "runs at once").

### When to reach for it

- The user says execute, continue, or resume a kit `/architect` already wrote.
- You want state (`status`), one dispatch (`run`), or a phase check (`review`) on an
  existing kit.
- Deciding whether budget mode is worth turning on for this kit's implementer dispatches.
- **Not** for parallel dispatch or a session-side escalation valve — this harness has
  neither; escalation lives entirely in the driver's own ladder.

### Worked example

```bash
python3 bin/copilot_execute.py status --kit <dir>
python3 bin/copilot_execute.py run --kit <dir> --task <id> --dry-run
python3 bin/copilot_execute.py run --kit <dir> --task <id>
```

`status` is free — it only reads `TASKS.md`. `--dry-run` previews the exact dispatch
without spending anything. A real `run` dispatches the task's pinned model, retries once
on failure with the evidence attached, and climbs the pricing-tier ladder only on a second
failure (`--max-escalations <N>` caps how far). `review --kit <dir> --phase <n>`
dispatches the reviewer agent against `PLAN.md` at a phase boundary.

### Failure modes & fallbacks

- **A task reports `done`.** Re-run its verify command yourself before trusting that — a
  dispatched run's own success claim is never evidence.
- **A tier keeps needing escalation.** That's the ladder working as designed, not a
  defect; report which rung ultimately passed.
- **Expecting parallel tasks to run at once.** They won't — `independent:` on this
  harness means safe-in-any-order, never concurrent.

### Cost & safety

`status` is read-only and free; `--dry-run` previews and spends nothing; a real `run`
spends real AI Credits on whatever model the task's `model:` pin (or an active prefs pin)
resolves to. Add `--budget` to dispatch one tier lower — see [budget](budget.md) — and
note that `review` deliberately takes no budget flag, because phase reviews stay at full
strength by design.

### Related

- [architect](architect.md) — writes the kit this skill runs.
- [budget](budget.md) — the cheaper-dispatch variant of the same driver.
- [escalate](escalate.md) — the same ladder, for a single task outside any kit.
