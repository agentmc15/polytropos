# The role experiment — does adding roles pay?

## The question

The kit execution loop's trio (implementer / verifier / reviewer) can grow to ten roles
(the role-roster kit added scout, test-author, second-verifier, red-team,
security-auditor, docs-editor, synthesizer as OPTIONAL, per-kit declared roles). Adding
a role costs real dispatches. The question this protocol answers, kit by kit, is: **does
each extra role catch anything a cheaper roster would have missed, for a cost you'd pay
again?** Never answered by vibes — answered by measurement.

## The method: marginal-catch on real kits

The unit of evidence is a **marginal catch**: when a role's findings are adjudicated,
the orchestrator also decides how many CONFIRMED findings were NEW — caught by no
earlier layer of the pipeline on that task (or phase, for phase-scoped roles). That
adjudication rides the existing `agent:` ledger line as an optional `marginal=` field,
alongside the existing `findings=`/`confirmed=`.

The canonical pipeline order (a finding raised by an earlier layer is never marginal for
a later one that raises it too):

```
scout → implementer → test-author → verifier → second-verifier → red-team → reviewer →
security-auditor → docs-editor → synthesizer
```

Two parallel pairs get a stated tiebreak: a finding raised by both verifier and
second-verifier belongs to the verifier (not marginal for second-verifier); one raised
by both reviewer and security-auditor belongs to the reviewer (not marginal for
security-auditor). A finding is never counted marginal twice.

### Why marginal-catch on real kits, not a cross-kit A/B

The alternative this repo considered and rejected is a paid A/B: run the same kit twice,
once at a smaller roster and once at a larger one, and compare outcomes. Marginal-catch
wins for this repo on two grounds:

- **Self-controlled, no duplicate spend.** Each task or phase is compared against
  itself — the same implementer output, the same verifier pass, judged by whether the
  NEXT role added anything. An A/B would need to run every kit twice to hold the task
  constant, doubling spend on every kit forever just to keep measuring.
- **It rides the ledger that already exists.** `agent:` lines, `findings=`/`confirmed=`,
  and (now) `marginal=` are recorded as part of normal kit execution — the experiment is
  a read of data every kit run already produces, not a separate harness.

### Its honest limits

- **Kits differ in difficulty.** A kit with subtle contract edits will show different
  marginal rates than a mechanical wiring kit — the comparison is never apples-to-apples
  across kits, only within a kit's own pipeline order.
- **Adjudication is human.** `marginal=` is only as honest as the orchestrator deciding
  it at review time. There is no automated ground truth for "would an earlier layer have
  caught this."
- **Sample accrues slowly.** One kit run yields a handful of dispatches per role. Reading
  a role's marginal rate as settled before it clears the sample floor is exactly the
  mistake the honesty labels below exist to prevent.

## The tier ladder

Roster size is DERIVED from the role tokens actually observed in a kit's ledger (which
roles actually ran), never from a declaration promise. The scorecard labels a kit `R<n>`
for `<n>` distinct roles observed. Four tiers make "3 to 10 and everything in between"
comparable across kits:

| Tier | Roles | Adds over the previous tier |
|---|---|---|
| **R3** | implementer, verifier, reviewer | — (today's default; absent `roles:` line) |
| **R5** | + test-author, red-team | test-author, red-team |
| **R7** | + scout, second-verifier | scout, second-verifier |
| **R10** | + security-auditor, docs-editor, synthesizer | security-auditor, docs-editor, synthesizer |

A kit may declare any subset of the seven optional roles via its PLAN.md `roles:` line —
tiers are the recommended comparison ladder, not a constraint. Absent `roles:` is R3,
today's behavior, on every kit ever written; nothing about running this experiment
changes that default.

### Suggested cadence

Run the next few kits at ascending tiers — an R3 kit, then an R5 kit, then an R7 kit,
then an R10 kit — so each tier accrues its own dispatch sample under real work, not a
synthetic one. After each kit (or after a few), read the aggregate card:

```bash
python3 bin/routing_scorecard.py --roles
```

Add `--session <id>` and a kit slug for one kit's dollar figures (routed through the
same `--by-task` transcript-pricing machinery `--roles` already reuses); bare `--roles`
or `--roles --kits-dir <dir>` gives the cross-kit aggregate with dollars `n/a`.

## How to read the card, column by column

Run it yourself before trusting a summary of it — `python3 bin/routing_scorecard.py
--demo --roles` renders the same columns against a synthetic kit, safe to explore.

- **Dispatches.** How many times the role ran. Below `MIN_ROLE_DISPATCHES` (5) the row
  is tagged **"insufficient sample"** — its other columns are printed but should not be
  read as a settled verdict yet. A role with zero dispatches anywhere does not appear as
  a zero row at all; it is simply absent from the card.
- **Findings / Confirmed.** Summed only over dispatches that recorded a precision pair.
- **Precision.** Confirmed ÷ findings. Renders `n/a`, never a fabricated `0%`, when no
  dispatch recorded findings — **None-not-zero**: absence of data is not evidence of
  zero.
- **Marginal.** The summed `marginal=` count. Renders `n/a` (never a fabricated `0`)
  when zero dispatches carried a measured `marginal=` field at all. When at least one
  dispatch WAS measured, this can legitimately read `0` — that is a real, measured
  finding (every confirmed catch was something an earlier layer already caught), not a
  missing-data gap. Legacy ledger lines written before this kit landed carry no
  `marginal=` field; those dispatches count as **"marginal unmeasured,"** never as
  `marginal=0`.
- **Marginal unmeasured.** The count of dispatches beside the Marginal cell that carried
  no `marginal=` at all — read it next to Marginal rate as a coverage figure: a role
  with a high measured rate but a high unmeasured count has thinner evidence than the
  rate alone suggests.
- **Marginal rate.** `marginal ÷ marginal-measured` — the MEASURED-dispatch denominator
  only, never divided by every dispatch. Dividing by every dispatch would dilute the
  rate with dispatches that recorded no `marginal=` at all and understate a role whose
  measured sample is small but consistent.
- **Dollars.** `n/a` everywhere unless a kit is priced with `--session`. Bases are never
  summed across kits: an aggregate row's dollars render only when every kit
  contributing to that role's aggregate is priced on the same basis; otherwise it is
  `n/a` with a note, never a blended figure.
- **Reviewer marginal: unmeasured.** The `reviewer:` family (phase-end review, its own
  NOTES.md line family) carries no `marginal=` field at all — every reviewer row reads
  "marginal unmeasured" structurally, not as a gap that will fill in with more runs.
  Reviewer catches are real evidence (see the worked example below); they are just not
  yet wired into the `marginal=` field the way `agent:` role dispatches are.
- **Escalation is excluded from every row.** It delivers fixes, not verdicts (existing
  law from the routing-history kit) — it never counts toward roster size and never
  appears in the value table.

## Four structural limits (read these before drawing any conclusion)

These were pinned during this kit's own P1 review and are load-bearing, not incidental:

1. **Phase/run-scoped roles can never carry per-task dollars.** `security-auditor`,
   `docs-editor`, and `synthesizer` run at phase or run boundaries, not per task — the
   never-split law (an orchestrator's or a shared agent's cost is never divided across
   the tasks or phases it touched) means their cost side is structurally unmeasurable
   today, by design, not by omission. "Does it pay?" for these three rests on marginal
   catches weighed against a cost YOU estimate from dispatch counts (how many times the
   role ran, at roughly what a dispatch on its pinned model costs) — never a number the
   card itself invents.
2. **The marginal rate's denominator is MEASURED dispatches only.** Read the Marginal
   rate cell beside the Marginal-unmeasured count, always together — a rate is only as
   trustworthy as the fraction of dispatches that actually recorded a `marginal=`
   adjudication. The rate is catches per measured dispatch, not a share of dispatches
   that caught something — a single measured dispatch can carry `marginal=2` (two
   confirmed findings on that one dispatch, each caught by no earlier layer), so the
   rate can legitimately read over 100% (4 marginal catches over 2 measured dispatches
   renders 200%). Read an over-100% rate as "this role is a prolific catcher — several
   of its dispatches each turned up more than one marginal finding," never as a
   rendering error or a sign the card is miscounting.
3. **Marginal is ORDER-DEPENDENT, not role-intrinsic.** The pipeline order above means
   earlier layers are structurally advantaged: they see the work first and get first
   claim on every catch. A late role's low (or zero) marginal rate never proves the role
   is worthless — it proves the earlier layers caught things first. Do not read a
   reviewer's low marginal rate as "drop the verifier," and do not read a
   security-auditor's low marginal rate as "drop the reviewer." Reordering the pipeline
   would change which role gets credit for the same catches.
4. **Some roles produce no adjudicable findings by design.** `scout`, `docs-editor`, and
   `synthesizer` do grounding, docs-freshness, and distilled-learnings work respectively
   — none of it is a "finding" in the confirmed/marginal sense. Their rows are
   dispatch-cost with indirect value, judged qualitatively (did the scout's grounding
   brief save the implementer a wrong turn? did the docs stay current? did the
   synthesized NOTES prose actually get reused?), never by precision or marginal rate.
   The card's own legend states this in words so a blank cell there reads as "by
   design," not "missing data."

## Decision guidance (judgment, not law)

This is where the card informs a human call — it does not automate one:

- A role earns a **standing place** in future kits' `roles:` lines when its marginal
  rate is materially non-zero over at least `MIN_ROLE_DISPATCHES` dispatches, at a cost
  per marginal catch you would pay again.
- **Drop** roles that measure zero-marginal over a real sample (past the insufficient-
  sample floor, not on one or two dispatches).
- **Re-test after model-generation changes** — a role's marginal rate is a property of
  the model doing the work as much as the role's mission; a generation upgrade can move
  it.

### Worked example: this week's three reviewer marginal catches

Three reviewer catches this week are the closest thing to a worked example the ledger
currently has, each one a finding the phase reviewer confirmed over a verifier pass that
had already reported clean:

- **harness-update, P2 review.** The task's own verifier had reported `findings=0` and
  `result=accepted` (clean). The phase reviewer caught that `install_codex`'s prompts
  loop was an unconditional overwrite — the verifier's probe only exercised one file
  class and never saw the write path. NOTES.md records the lesson directly: "an
  adversarial verifier inherits the brief's blind spots — the reviewer's value was
  reading the REUSED module's write loop, not the new code."
- **graphify-skill, P1 review.** Verifier passes for the covered tasks read clean; the
  phase reviewer's findings included a `UnicodeDecodeError` escape path reachable
  through graph link `context` fields that no verifier probe exercised.
  Mutation-testing the guard on a copy afterward confirmed it fired.
  (`.claude/kits/graphify-skill/NOTES.md`)
- **graphify-skill, P2 review.** A second, later-phase reviewer catch: a deny-list
  surface claim named a phantom command that does not exist in the tool's measured
  `--help`, while omitting the three largest real surfaces — caught only at phase
  review, not by the task-level verifier passes that preceded it.
  (`.claude/kits/graphify-skill/NOTES.md`)

No dollars are invented for these three — the harness-update and graphify-skill kits
predate `marginal=` and were not priced with `--session` for this purpose, so they are
cited as qualitative proof-of-concept for the METHOD, not as rows on a priced card. Kits
executed from here on carry `marginal=` on their `agent:` lines directly, so future
worked examples come straight off `python3 bin/routing_scorecard.py --roles`.

## Where the facts live

This doc describes how to read the card, not what today's numbers are — those change
every time a kit runs. For the current numbers, run the engine:

```bash
python3 bin/routing_scorecard.py --roles              # cross-kit aggregate, dollars n/a
python3 bin/routing_scorecard.py <kit> --session ID --roles   # one kit's dollars
python3 bin/routing_scorecard.py --demo --roles        # synthetic smoke, safe to explore
```

The tier ladder, the honesty rules, and the seven role templates themselves live in
`.claude/kits/role-roster/PLAN.md` and `skills/architect/references/roles/`; the ledger
grammar (`agent:` line fields, including `marginal=`) is specified in the `execute`
skill. This doc is a reading guide to the measurement, not a second source of truth for
either.
