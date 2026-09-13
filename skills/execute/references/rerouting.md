# Live re-routing — upgrade-only, autonomy-gated

Detail moved out of `skills/execute/SKILL.md` by roadmap step 22 so the entry point carries the mandatory loop; the text below is the binding grammar it points at, unchanged.

The outcome ledger doubles as a live routing signal. The moment any `outcome:` line lands
(step 4 or 5), consult the kit's running per-tier first-try rate:

    python3 bin/routing_scorecard.py <slug> --live

`--live` reads TASKS.md plus the NOTES.md ledger so far (read-only — it never writes) and
recommends an upgrade only when a tier's live first-try rate falls below its threshold over a
minimum sample of that tier's finished tasks. Recommendations are UPGRADE-ONLY and move
exactly one step up the tier ladder (haiku→sonnet, sonnet→opus) — never down, never skipping
a rung, and NEVER to frontier/Fable: Fable is reached exclusively through the per-task,
evidence-carrying escalation valve below. When the struggling tier sits one rung under
frontier, `--live` reports the signal but locks the recommendation — the valve is the only
path up from there.

A re-route is a **runtime dispatch override, never a TASKS.md rewrite**. The task's `model`
field stays the dispatch default and is never edited; an applied upgrade changes only the
alias you pass as the Agent tool's `model` parameter for the remaining PENDING tasks it
names (never an in-progress task), and it ends any warm cluster serving those tasks — a
model change always ends a cluster. Every recommendation you act on or announce is logged to
NOTES.md as one machine-readable line (the budget below is counted from these):

    `reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>`

The autonomy dial decides what you may do with a recommendation:

- **advisory (the default)** — PRINT the recommendation to the user and change nothing:
  every task keeps dispatching on its pinned `model`. Log the printed recommendation once
  (`mode=advisory`) so an unchanged signal is not re-announced. The human decides.
- **auto** — apply it yourself: dispatch the named pending tasks on the upgraded alias, log
  `mode=applied`, and say so in your report. Respect the `budget` block in the `--live`
  output — `mode=applied` events are capped per run, and when `remaining` hits 0 you fall
  back to advisory printing. Auto also arms the escalation valve: a task `blocked` after
  retry goes straight to the Fable consult without pausing to ask.

Downgrades are never automatic in either mode — if a tier looks over-provisioned, say so in
the end-of-run report and let the human re-pin the next kit.
