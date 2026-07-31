# NOTES — evidence-loop

Execute-owned. Cross-task learnings plus the machine-read ledger lines the routing scorecard
consumes. Kit dial: `autonomy: advisory` (PLAN.md) — re-route recommendations are printed,
never applied, and the escalation valve asks before spending frontier tokens.

Run id for this invocation: `2026-07-27-83cf` (content-free per the D8 format graph-convergence
established — UTC date plus four hex, no hostname, username, or path fragment).

## Precondition satisfied

PLAN declares graph-convergence a precondition for U3/U4. That kit completed and merged as
`4129ace` before this run started: the `run=`/`parent=`/`failure=` ledger fields U4 consumes
exist, `parse_defects` reads the `defect:` lines U3 clusters, and 33 defect events across 5
kits are already on disk as real input.

**One caveat U4 must respect, inherited from graph-convergence's P34-F1:** all three drivers
write concrete pricing model ids into `outcome:` `model=`, while `tier_for` resolves only
Claude Agent-tool aliases, so driver-executed kits do not enter the per-tier track record.
U4's envelope analysis therefore reasons over interactive-kit history only. That is a real
coverage limit, not a bug to fix here — it must be LABELLED, not silently absorbed into a
confident per-class number.

## Setup notes

- The kit arrived as three drafted files with no agent trio; execute created
  `.claude/agents/evidence-loop-{implementer,verifier,reviewer}.md` at setup. Both read-only
  roles carry the non-destruction clause (mutate temp copies, restore byte-for-byte, close with
  `git status --porcelain`) — the `tools:` pin removes Write/Edit but Bash alone can still
  delete a tracked file, which is how a prior kit lost an authored docs section.
- Pre-flight found no brief defects in this kit — a notable contrast with graph-convergence,
  which carried eight. Every anchor resolves, all three to-be-created files are absent, and
  `journal/promotions/` is already covered by the root-anchored `/journal/` gitignore rule, so
  U3 needs no gitignore change.
- **Gate 1 has real data, not just fixtures.** Across the repo's kits today: `unspecified-path`
  4 kits, `stale-plan-decision` 3, `contradictory-acceptance` 3, `unrunnable-verify` 2,
  `false-zero-spec` 2, `tautological-verify` 2 — six genuine ≥2-kit candidates. Single-kit
  residue: `verifier-destructive-restore`, `unsafe-parallel-marking`, `underivable-requirement`,
  `stale-pin`. U3 can be checked against this, not only synthetic input.
- **U5 will trigger a copilot-docs rebuild; U1 will not.** `copilot-docs/manifest.json`
  references `copilot/.github/skills` and `README.md` as source sets, but NOT `skills/execute/`
  or `skills/architect/`. So U1's edit to the execute skill causes no drift, while U5's README
  pointer does — exactly the trap that failed graph-convergence's T12, which reported a red
  suite as "pre-existing" when its own README edit had caused it. U5's brief carries the
  `python3 bin/copilot_docs.py build` step.

## PLAN E3's premise is false: the repo does NOT have the data U4 is meant to analyse

E3 justifies the whole envelope task with: "the cascade result says multi-stage ladders often
don't beat the pairwise envelope — **the repo has the ledger data to check locally** instead of
assuming either way." Measured, that premise fails on both inputs U4 needs:

    CLASS DERIVATION
      outcome lines across all kits            184
      carrying failure=                          0
      blocked / escalated-pass outcomes          0   (so failure= was never even legal)

    PRICING
      kits with a NOTES.md                      27
      kits carrying a session: line             13   (priceable at all)
      kits carrying agent: lines                18   (per-task capable in principle)
      sessions the history card actually prices  2   (coverage: partial)

So U4 cannot test the cascade hypothesis against this repo. Per-class rows have no class
evidence, and a ladder-vs-cascade cost comparison rests on two priced sessions out of
twenty-seven kits. Recorded as `defect: - kind=stale-plan-decision` — a PLAN decision whose
stated rationale repo reality contradicts. Kit-level, because it is E3 itself rather than U4's
brief; U4's brief is careful and already specifies the degraded path.

**This does not cancel U4 — it fixes what U4 delivers.** The honest deliverable is a report that
names its own evidence base and declines to recommend: how many outcomes carried `failure=`
(zero), how many sessions priced (two of twenty-seven kits), and therefore that the envelope
question is UNANSWERABLE from this repo's history today. That is a genuinely useful result — it
tells the architect the ledger needs to accumulate blocked/escalated outcomes and `session:` lines
before the cascade question can be asked at all, which is actionable in a way a fabricated
comparison would not be.

The failure mode to prevent is precise: a per-class table rendered from an empty class set, or a
cascade "saving" computed from two sessions and presented as a finding. Both would pass tests and
look like analysis. PLAN E4 already demands `partial` labels and the sparse-history fallback —
here they are not edge cases, they are the entire output on real data.

## U5 brief defect: it asks for citations the kit never supplies

U5 must write "the research grounding in one short section (governance decay under compaction;
skill-promotion validation; pairwise cascade envelope) — **plain citations**". The kit names that
research by nickname only:

    "July 2026 research wave"            PLAN.md:12
    "skill-library literature"           PLAN.md:20, :55
    "decision-theoretic cascade result"  PLAN.md:23, :62
    "AgentRx-style trajectory-failure taxonomy"   (graph-convergence PLAN.md:75)

A grep for any actual reference — author, year, title, URL, arXiv id — across the whole kit
returns nothing. So the task is required to produce citations for work the kit never identifies,
and it is pinned to `haiku`, the cheapest tier, on a doc that will read as settled reference
material.

Recorded as `defect: U5 kind=unspecified-path` — the same kind as graph-convergence's T12, whose
brief likewise demanded content ("the four graph types") that the kit never defined. **This
instance is more dangerous than T12's.** A fabricated config format is greppable and was caught;
a fabricated citation looks authoritative, is not greppable, and propagates as scholarship. And
the irony is worth stating: this is the kit whose entire purpose is preventing figures and claims
from outrunning their evidence.

Resolution at dispatch — U5 must:

- State the three research CLAIMS in plain language, exactly as scoped by the kit (constraints
  decay under compaction; experience does not automatically make a good skill; a multi-stage
  ladder often fails to beat a tuned pairwise cascade).
- Attribute them honestly: the kit's PLAN cites this work by description rather than by
  reference, and the doc says so.
- **Invent no author, year, title, venue, or URL.** If a reader wants the sources, the honest
  answer is that this repo does not record them — not a plausible-looking list.

Same discipline T12 eventually applied to the knowledge-graph rejection it could not source: an
honest gap beats a confident fiction, and a positioning doc is the worst possible place for one.

Also pre-resolved for U5: its conditional cross-link is REQUIRED, not skipped —
`docs/GRAPH-ENGINEERING.md` exists (it landed with graph-convergence T12) and carries a
`## What Was Deliberately Rejected` section at line 64, which is the anchor to link.

## U2 and U3 pre-flight: two anchors that read as stale but are not

Neither is a brief defect; both would have produced a stop-and-report or a mis-parse if dispatched
verbatim, so both are pre-resolved here.

**U2 — `--kit` does not exist yet.** The brief says to "follow the engine's existing seam pattern
(`--projects-dir`, explicit `--kit`)". `bin/context_weight.py` has `--projects-dir` (and
`--project`, `--surface`, `--session`, `--budget-tokens`); it has ZERO occurrences of `--kit`. An
implementer reading the parenthetical as a list of existing flags would correctly stop and report
a stale anchor. The intended reading: `--projects-dir` is the existing seam whose STYLE to mirror,
and `--kit` is the new flag U2 adds in that style. Dispatch says so explicitly.

**U3 — `tasks/lessons.md` is JSONL, not markdown.** The `.md` extension is misleading: the file is
four newline-delimited JSON objects with the schema
`{date, failure_pattern, lesson, applies_to[]}`. A tool written to scan it as prose finds nothing
and would silently contribute zero lessons while appearing to work — the quiet-failure shape this
repo keeps hitting. Dispatch pins the real format and schema.

## U4 pre-flight: its primary class-derivation path has NO real data, and structurally cannot

U4 derives task classes from "tier pin × failure class where `failure=` exists". Counted across
every kit in the repo:

    outcome lines total            184
    carrying failure=                0
    result=pass                    176
    result=retry-pass                8
    result=blocked / escalated-pass  0

`failure=` is legal ONLY on `blocked` or escalated outcomes (T1's grammar, tightened by
graph-convergence's P34-F4). This repo has recorded **zero** of either, in 184 outcomes. So the
field has never been legal on a single line ever written here, and U4's primary path will ALWAYS
take the degraded whole-history branch on real input.

The brief anticipates degradation — PLAN's tripwire says to fall back to a whole-history row with
the partial label — so this is not a brief defect. But it changes what U4 IS: the per-class
analysis is exercisable only against synthetic fixtures, and every real invocation on this repo
produces the degraded form. That must be stated where a reader sees it, not treated as a
transient edge case.

**The deeper cause is a gap this repo already recorded.** graph-convergence's NOTES logged that a
`retry-pass` cannot carry `failure=`, and noted the cost: retries caught by a verifier are the
most common form of the exact evidence D9 exists to collect. Here is that cost measured — the 8
`retry-pass` outcomes are the ONLY failures this repo has ever recorded, and they are precisely
the ones the grammar forbids from carrying a class. The field is restricted to cases that do not
occur, so the evidence base for per-class analysis is empty by construction rather than by
accident.

U4's brief must therefore require: the report names how many outcomes carried `failure=` (zero,
today) as the stated reason for degrading, rather than silently rendering a whole-history row that
looks like a considered choice. An empty evidence base reported as a partial label is honest; the
same emptiness reported as a class analysis would be the exact failure this kit exists to prevent.

## Second harness stall of the session — the condition I named has partially triggered

U4's first dispatch died to the same stream watchdog ("no progress for 600s") that killed
graph-convergence's T10. Tree checked immediately: zero edits, no `envelope` code, suite green at
1848, goldens intact at 1225/2100. Clean re-dispatch, not a recovery.

graph-convergence's NOTES recorded the rule and its own overturn condition: a stalled dispatch
gets an `agent:` line but does NOT count as an `attempts=` retry, because `attempts` feeds the
per-tier first-try rate and a watchdog timeout is evidence about the harness, not the tier — "if
stalls become frequent this reasoning should be revisited, since a tier whose dispatches routinely
stall IS a routing cost even when the cause is mechanical. One stall in twelve tasks is not that."

Two stalls in roughly seventeen dispatches now. Still not counting them as attempts, for the same
reason, but the pattern is worth naming precisely because it is not random: BOTH stalls hit the
largest task in their phase (T10's two-driver usage join, U4's envelope analysis), and both left
zero bytes behind. The signal is about task SIZE against a fixed watchdog, not about sonnet. The
practical mitigation, which worked on T10's re-dispatch, is to tell the implementer to finish and
report rather than polish, and to order the work so the honest-degraded path lands before the
synthetic-fixture arithmetic.

If a third stall lands on a large task, the right response is to split the task rather than
re-dispatch it whole.

## Ledger

defect: U5 kind=unspecified-path
defect: - kind=stale-plan-decision
agent: U1 id=a373fb1eadc31a9a9 role=implementer model=opus
agent: U1 id=af296e66d59c3a4f6 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: U1 model=opus attempts=1 result=pass review=clean run=2026-07-27-83cf
agent: U2 id=a1a43d0c100cc1978 role=implementer model=sonnet
agent: U2 id=ac928dc28b964dbcc role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: U2 model=sonnet attempts=1 result=pass review=clean run=2026-07-27-83cf
reviewer: P1 model=opus findings=11 confirmed=6 result=accepted
agent: P1fix id=ad30368f7db3950ee role=implementer model=opus
agent: P1fix id=a658fa3a9449f8cc1 role=implementer model=sonnet
outcome: U2 model=sonnet attempts=1 result=pass review=revised run=2026-07-27-83cf
agent: U3 id=aea4df3ff04e46af2 role=implementer model=sonnet
agent: U3 id=ae69d4658f9b23a55 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: U3 model=sonnet attempts=1 result=pass review=clean run=2026-07-27-83cf
reviewer: P2 model=opus findings=9 confirmed=6 result=accepted
agent: P2fix id=a71eec27e3a71d08e role=implementer model=opus
outcome: U3 model=sonnet attempts=1 result=pass review=revised run=2026-07-27-83cf
agent: U4 id=a420da88a49696408 role=implementer model=sonnet
agent: U4 id=a6297cff1886d7e19 role=implementer model=sonnet
agent: U4 id=a2b601f58e29f3d62 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: U4 model=sonnet attempts=1 result=pass review=clean run=2026-07-27-83cf
agent: U5 id=acd268e2aa13f0a76 role=implementer model=haiku
agent: U5 id=af8690c8b1f5ffaf9 role=verifier model=haiku findings=2 confirmed=2 result=revised
agent: U5 id=a588812437c5355dc role=implementer model=sonnet
outcome: U5 model=haiku attempts=2 result=retry-pass review=revised run=2026-07-27-83cf
defect: U2 kind=stale-pin
reviewer: P3 model=opus findings=12 confirmed=9 result=accepted
