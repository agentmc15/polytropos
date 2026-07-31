# Fusion Tier 1 — multi-model orchestration borrows

Three learnings from Cognition's "Devin Fusion" multi-model orchestration write-up, adapted to
this plugin's execution loop — **Tier 1 only**: everything here lands inside the plugin itself,
no upstream changes required to ship it.

---

## The three borrows

Before this kit, `/execute` spawned a fresh, cold subagent per task, read every file itself
without delegating, and reported dollars without ever measuring whether the cheap models it
routed to actually held up under review. Each borrow closes one of those gaps and lands in its
own named section of `skills/execute/SKILL.md`.

### Warm sidekick

Fresh-per-task meant N cold prompt-cache starts for a kit's serial chain of same-file tasks —
every implementer re-read and re-cached the same files from scratch. Now, for a **cohesive
cluster** (a serial `depends:` chain within one phase, sharing a primary file, carrying the
SAME `model` pin), `/execute` keeps ONE continued implementer instead: spawn it for the
cluster's first task, then continue the same agent via `SendMessage` for each subsequent task
in the cluster, so the shared files are read and cached once. Fresh, parallel fan-out stays the
default for `independent:` tasks — this is opt-in, not a replacement. A warm agent accumulates
context toward compaction, so a sidekick is capped at ~4 tasks and ended early on degraded
replies or reported context pressure; the verifier agent is never warmed — it is always a fresh
spawn, because its value IS the adversarial fresh context. This lands in
`## Dispatch modes — fresh fan-out vs warm sidekick`.

### Lean driver

The orchestrator's own context is the single most expensive artifact of a run — it is priced,
cached, and re-sent on every subsequent turn, and every inline read brings compaction closer.
`/execute` now reads only kit state (`PLAN.md`, `TASKS.md`, `NOTES.md`) plus the output of
verify commands it runs itself, and delegates every exploratory read, grep, and "what does this
file look like now" question to a cheap `model: haiku` scout that returns a few-line
conclusion — never a file dump. Independent verification is delegated the same way: the driver
consumes the verifier's verdict, not its evidence. This lands in
`## Operating rule — lean driver`.

### Quality scorecard

The plugin used to measure only dollars and merely assert that routing to a cheaper model held
near-Fable quality — nothing checked that assertion. `/execute` now appends one machine-readable
`outcome:` line to NOTES.md every time a task reaches `done` or `blocked` (see **The outcome
ledger**, below — this lands in `## Outcome ledger — one line per finished task`), and
`bin/routing_scorecard.py` turns that ledger into a routing-quality scorecard: first-try pass
rate, escalation rate, model mix, and cheap-model review survival. The escalation valve records
`result=escalated-pass` when a Fable consult unblocks a task, and `## End of run` now offers the
scorecard command as the run's closing step.

## The outcome ledger

The grammar, pinned in `## Outcome ledger — one line per finished task` and reproduced exactly
in `bin/routing_scorecard.py`'s parser:

    outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>

- `model` — what the task actually ran on: its `model` pin, or the escalation target when a
  Fable consult did the fixing.
- `attempts` — implementer dispatches, counting retries and escalation (clean first try = 1).
- `result` — exactly one of `pass` (first dispatch, verify passed) | `retry-pass` (passed on
  the retry) | `escalated-pass` (passed only via the escalation valve) | `blocked`.
- `review` — exactly one of `clean` (verifier/reviewer accepted the work unchanged) |
  `revised` (changes were required after the implementer claimed done) | `none` (no independent
  review beyond the verify command).

Parsing is tolerant on purpose: an optional leading `-`/`*` bullet is stripped, unknown
`key=value` pairs are ignored (forward-compatible), an unrecognized `result` is skipped with a
note rather than rejected, and re-running a task just appends a fresh line — the scorecard takes
the **last line per task id**, never an average or a first match. Every kit executed before this
one has a plain-prose NOTES.md with no `outcome:` lines at all; the scorecard treats a
ledger-free (or missing) NOTES.md as normal input and degrades to TASKS.md-status-only output
with an explicit note, never a crash and never an invented number.

## The scorecard

```bash
python3 bin/routing_scorecard.py <slug>                    # markdown scorecard for a kit
python3 bin/routing_scorecard.py <slug> --json              # same data, schema_version: 1
python3 bin/routing_scorecard.py <slug> --session <id>      # + dollars vs an all-frontier counterfactual
python3 bin/routing_scorecard.py --demo                     # synthetic kit + transcript, no real files touched
```

`--session <id>` folds in one session's actual transcript dollars against a counterfactual
where every task ran on the frontier tier instead (via the same all-frontier counterfactual
math `bin/session_cost.py` already uses) — omit it and the scorecard still runs, with
`cost: null` and a note to pass `--session`. `--demo` builds a synthetic kit and a synthetic
transcript in its own temp dir, runs the real pipeline against them, prints the scorecard, and
cleans up — the sanctioned smoke test that needs no real kit or `~/.claude` history.

**Metric definitions** (over tasks with a recognized `outcome:` line): `first_try_rate` is the
share of `result=pass`; `escalation_rate` is the share of `result=escalated-pass`. Model mix
counts tasks per *effective model* — the outcome line's `model=` if present, else the task's
`model` pin, else `unspecified`. Cheap-model review survival is the Fusion "quality retained"
number: a task counts as CHEAP when its tier (via the alias map, where `fable` aliases the
`frontier` tier) is NOT one of the expensive tiers in `data/pricing.json`; among cheap tasks
that got any independent review, survival is the share reviewed `clean`.

**Reuse, never re-implementation.** `bin/routing_scorecard.py` is a read-only consumer: TASKS.md
parsing comes from `copilot_execute.parse_tasks` and transcript dollars come from the
`session_cost` module's functions (which themselves reuse `cost_report`) — both loaded
read-only via the same `importlib` `_load` pattern `bin/session_cost.py` already uses, and
neither is ever edited by this kit.

## Upstream limitation — main-session model switching

Nothing in a plugin can switch the **MAIN session's** model — only the user can, via `/model`.
Fusion's remaining structural trick is swapping the driver to a cheaper model right at a
context-compaction boundary, where the prompt cache is invalidated anyway and there is nothing
left to lose by switching. That trick needs Claude Code or the Agent SDK to expose main-session
model control to a plugin; it doesn't exist today, so it isn't built here. This is the upstream
ask. Until it lands, **warm sidekick** and **lean driver** are the in-plugin equivalents: warmth
gets the cache-reuse benefit for a sidekick instead of the driver, and the lean-driver operating
rule keeps the driver's own context (and therefore its compaction pressure) as small as
possible in the meantime.

## Deferred — Tier 2

Dynamic mid-kit re-routing — `/execute` consulting live scorecard numbers to re-pin later
tasks' models while a kit is still running — is explicitly out of scope for Tier 1. It would sit
behind an opt-in autonomy dial (never a default), since letting the loop change its own routing
decisions mid-run is a materially bigger trust step than the read-only reporting this kit ships.
Tier 2 is a planned follow-up kit; this kit's outcome ledger is exactly the data substrate it
would consume — the plumbing to record routing outcomes now exists, only the feedback loop that
acts on them is deferred.

Tier 2 has since shipped — see [FUSION-TIER2.md](FUSION-TIER2.md) for the live per-tier
signal, the upgrade-only re-route rule (one step, never to frontier), and the opt-in autonomy
dial (advisory by default).
