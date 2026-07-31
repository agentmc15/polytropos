---
name: execute
description: Run an execution kit under tasks/kits/<slug>/ — drive bin/copilot_execute.py task by task, verify each result, and climb the pricing tiers only on failure. Use when the user says to execute, continue, or resume a kit or plan.
---

You drive an existing execution kit through to done. The expensive thinking already happened
in `/architect` — your job is faithful dispatch, verification, and state-keeping, not
re-litigating the plan. Read the kit's `PLAN.md` fence before starting; do not build anything
it fences off, even if it looks helpful.

## See state

```bash
python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py status --kit <dir>
```

Add `--json` for machine-readable output. Every task's `status` is exactly one of
`pending | in-progress | done | blocked`.

## Run a task

```bash
python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py run --kit <dir> --task <id>
```

The driver dispatches the task to the `implementer` agent on that task's pinned model
(`--agent <name>` overrides which agent runs it), runs the verify command, retries once with
the failure evidence on a miss, and climbs the pricing-tier ladder only on failure
(`--max-escalations <N>` caps how far it climbs). Omit `--task` to take the first eligible
pending task. `--dry-run` previews the exact dispatch without spending anything — real `run`
invocations spend real AI Credits, so preview when unsure.

The driver also honors the user's model prefs — repeatable `--pin TIER=MODEL_ID` and
`--exclude MODEL_ID` flags override the gitignored `prefs/copilot.json` file, and
`--no-prefs` ignores it (`python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py prefs`
shows what is active).

Budget mode: add `--budget` to `run` to dispatch one tier lower than the task's pin (floor:
the cheapest tier) and print an honest estimated actual-vs-standard comparison afterwards —
escalation still climbs the normal ladder on a verified failure, and
`python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py budget --kit <dir>` totals what
budget mode saved or overspent on the kit's completed runs so far — blocked and no-demotion
runs are reported separately, never folded into that net. `review` takes no budget flag:
phase reviews deliberately stay at full strength. See the `budget` skill.

## Verify independently

The driver runs each task's verify command itself, but re-run it yourself before trusting a
`done` — a dispatched run's own claim of success is never evidence.

## Phase boundaries

```bash
python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py review --kit <dir> --phase <n>
```

Dispatches the `reviewer` agent against the kit's `PLAN.md` at the end of a phase.

## What this harness does NOT have

Claude Code's execute skill fans tasks out to parallel subagents and keeps warm agent
clusters running across several tasks at once. Copilot CLI has no equivalent surface: kit
tasks run serially, one `run` invocation at a time. A task marked `independent:` means "safe
to run in any order," not "runs in parallel" — say this plainly rather than faking an
orchestrator. Escalation lives in the driver's ladder, not in a session-side valve.

## End of run

Report tasks completed, blocked, and remaining, each with its verify output, then check the
result against the kit's `PLAN.md` "done" definition before calling the kit finished.

## Agents under the hood

There is no `execute` agent — this skill drives `bin/copilot_execute.py`, and the driver
dispatches the kit's work to the `implementer`, `verifier`, and `reviewer` custom agents
(`copilot --agent <name>` also reaches them directly). Each task's `model` pin from
TASKS.md decides what the dispatch runs on, not this session's model.

## Installed?

If the literal `{{POLYTROPOS_ROOT}}` text is still visible above, the bundle is not
installed — tell the user to run `python3 bin/harness_select.py install --harness copilot`
(then `/skills reload` picks the skills up in-session).
