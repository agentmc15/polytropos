# Fusion Tier 2 — dynamic mid-kit re-routing behind an autonomy dial

Tier 1 shipped a warm sidekick, a lean driver, and an outcome ledger that turns into an
end-of-run quality scorecard (`bin/routing_scorecard.py`). Tier 2 rides that same ledger as a
**live** data substrate: two features that let `/execute` notice a struggling model tier
mid-kit and correct it, without ever touching the shared architect/execute kit contract.

---

## The live signal

The outcome ledger doubles as a live routing signal. For each pricing tier, `--live` computes
the tier's first-try pass rate over this kit's ledger-so-far, and judges that rate only once a
minimum sample of the tier's finished tasks exists, against a strict-below threshold. Both
knobs are `bin/routing_scorecard.py` constants — `LIVE_RATE_THRESHOLD` and `LIVE_MIN_SAMPLE` —
and both are CLI-tunable via `--live-threshold` and `--live-min-sample`; the values live in one
place (the script), not restated here as prose facts.

Attribution matters: `pass`, `retry-pass`, and `blocked` outcomes count against the tier of the
ledger's `model=` field — that's what the task actually ran on. `escalated-pass` is different:
it counts against the **reconstructed dispatch tier** (the task's pin plus any prior applied
re-routes), never against frontier, because the ledger's `model=` on an escalated line names
the Fable fixer, not the tier whose attempt actually failed. Crediting frontier with a cheap
tier's failure would both pollute frontier's stats and hide the struggling tier's signal.

Usage:

```bash
python3 bin/routing_scorecard.py <slug> --live                 # markdown live-signal card
python3 bin/routing_scorecard.py <slug> --live --json          # same data, schema_version: 1
python3 bin/routing_scorecard.py <slug> --live \
    --live-threshold F --live-min-sample N --live-max-auto N   # tune the policy knobs
python3 bin/routing_scorecard.py --demo --live                 # synthetic mid-run smoke
```

The live path is quality-only: it never loads pricing and rejects `--session` outright — dollars
belong to the end-of-run scorecard, not the mid-run signal.

## Upgrade-only re-routing

A recommendation moves a struggling tier's remaining **pending** tasks up exactly one rung of
the ladder — haiku→sonnet, sonnet→opus — and stops before frontier. A struggling opus tier
never produces a recommendation; it yields the pinned note `frontier locked: escalation valve
only`. Fable is reached exclusively through the existing per-task, evidence-carrying escalation
valve, whose mechanism is unchanged by this kit. Re-routing never goes down, either:
over-provisioning (a tier passing comfortably above the threshold) is reported at end of run for
the human to re-pin the *next* kit, not corrected automatically mid-run.

A re-route is a **runtime dispatch override**: the TASKS.md `model` field is never rewritten,
the pin stays the dispatch default, and the shared architect/execute kit contract is untouched
(see **Contract safety**, below). Every recommendation — whether just printed or actually acted
on — is logged to NOTES.md with this grammar, reproduced here verbatim:

    reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>

Tier-1's `outcome:` parser (`OUTCOME_RE`) never matches a `reroute:` line — it's a different line
shape by construction, so old ledger consumers are unaffected and see nothing new.

## The autonomy dial

OFF by default = **advisory**: the loop only prints the recommendation (logging it once as
`mode=advisory`, so an unchanged signal isn't re-announced every task) and the human decides.
Nothing is auto-changed while the dial is off — every dispatch stays on the pin.

ON = **auto**: the loop applies upgrade-only recommendations itself, logging each as
`mode=applied`, behind a budget guardrail — applied events are capped per run, and the cap is
counted from the NOTES.md `reroute:` lines themselves so the count survives orchestrator
compaction. At zero remaining budget, the loop falls back to advisory printing. Auto mode also
changes the escalation valve's behavior in one way: a blocked task auto-consults Fable through
the existing valve without pausing to ask.

The dial is declared as an optional `autonomy: advisory|auto` line in the kit's PLAN.md; an
absent line means advisory. An explicit user instruction at invocation (for example, "execute
`<slug>` autonomously") overrides the PLAN.md posture for that run. It is not a task field, not
a TASKS.md marker, and not skill frontmatter.

## Contract safety

The shared contract's central rule — "the task's `model` field overrides the implementer
agent's frontmatter at dispatch" — stays true, verbatim, in both skills. The pin remains the
dispatch default and the field-beats-frontmatter precedence is untouched in every case; Tier 2
adds an explicit, opt-in, logged, upgrade-only orchestrator layer *on top* of that rule. With
the dial off — the default — the pin is always honored, full stop.

Nothing about the task-field shape changed: there is no new required task field, since
`autonomy:` is an optional PLAN.md line, and `copilot_execute.parse_tasks` needed no
modification. NOTES.md is already execute-owned, so adding the `reroute:` line format inside it
is not a contract change — the same precedent that let the Tier-1 `outcome:` line ship. And an
applied upgrade ends any warm cluster serving the affected tasks, because a model change always
ends a cluster — the warm-sidekick rule from Tier 1 is unmodified, just triggered by one more
kind of event.

## Still deferred

- **Scorecard-over-time / cross-kit aggregation** — turning per-kit outcome ledgers and
  re-route events into a routing track record that could inform the architect's *initial* model
  pins. The per-kit JSON (`--json`, `--live --json`) is the substrate this would consume;
  building the aggregation itself is explicitly out of scope for Tier 2.
- **Auto-downgrade** — never automatic, by design, not merely deferred. Over-provisioning is
  reported at end of run for a human to re-pin the next kit, on the theory that a mid-run
  downgrade risks quality on a small sample for a small saving.
- **Upstream — main-session model switching at compaction boundaries** — unchanged from Tier 1;
  still tracked in `docs/FUSION-TIER1.md`.

The scorecard-over-time aggregation has since shipped — see
[ROUTING-HISTORY.md](ROUTING-HISTORY.md) for the cross-kit `--history` view: the per-tier
track record, the optional NOTES.md `session:` line that attaches per-kit dollars, and the
advisory bullet that feeds the architect's initial pins.
