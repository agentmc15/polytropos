# NOTES — role-ledger

Run started 2026-07-25. Autonomy dial: **advisory** (PLAN.md line 3) — re-route
recommendations are PRINTED, never applied; every task dispatches on its pinned `model`.

Warm clusters declared by the architect: **T1→T4** (all sonnet, both on
`bin/routing_scorecard.py` + `tests/test_role_ledger.py`) served by ONE warm implementer;
**T6→T7** (both opus, shared skill contract) a second warm pair. T5 and T8 dispatch fresh.

## Pre-T1 baseline (recorded BEFORE dispatch — makes T1's claim falsifiable)

    parse_agents kept-event keys ...... ['agent_id', 'model', 'role', 'task']
    findings/confirmed/result present . False
    AGENT_RESULTS defined ............. False
    notes on a quality-bearing line ... []   (fields silently ignored today)
    suite ............................. 1225 tests

T1 must add exactly three keys, define AGENT_RESULTS, and start emitting degradation notes.
Anything less and its claim of done is false.

## Standing context inherited from the context-weight run (same orchestrator)

- **Verify at the interface, not by grepping source.** That run produced 8 false findings
  from hand-rolled greps against 1 real defect found by reading actual output. GUARDRAILS
  encodes the same rule for implementers ("verify commands must be able to fail").
- **Mutation-test any test that claims to catch a defect** — revert the fix, observe the
  failure, restore, checksum. A test never seen failing is not evidence.
- **`git diff` guards are vacuous for files a kit CREATES** — they are untracked, so the
  diff is empty and the check passes unconditionally. This kit's briefs use content
  assertions throughout, which is correct. (The architect's summary gave a false reason for
  this — it claimed the repo is not a git repo; it demonstrably is, with commits from today.
  The false premise did NOT reach any kit file. Right practice, wrong justification.)

## T1 — done (first try, clean)

`AGENT_RESULTS` + three optional quality keys on `agent:` events. Suite 1225 → **1244** (+19).
Verified at the interface against the pre-recorded baseline — every number moved as required:

    keys ................ +confirmed, +findings, +result   (was 4 keys, now 7)
    AGENT_RESULTS ....... ('accepted','revised','blocked')  (was undefined)
    happy path .......... findings=3 confirmed=1 result='accepted'
    confirmed>findings .. both None — DROPPED, not repaired
    unknown result ...... None
    lines kept .......... 4/4 — a bad quality field never drops its line
    notes ............... exactly 2, both naming the offending value

The degradation style matches the guardrail exactly: `self-contradictory findings/confirmed
(2/5) — ignored`. No `or 0`, no fabricated default.

**Mutation-tested the contradiction guard** (`c_val > f_val` disabled) → 2 tests fail. The
rule is genuinely covered, not merely present.

**ORCHESTRATOR INSTRUMENT ERROR #9 (carried over from the context-weight run's tally).** My
FIRST mutation attempt replaced `confirmed > findings` — which exists ONLY in the docstring at
line 1836. The live guard is `c_val > f_val` at line ~1883. The mutation "passed", which read
as "the tests don't cover this", and I nearly recorded a false gap. Third instance of the same
trap: **prose contains the strings code is described by.** Rule, now thrice-earned: before
trusting a mutation, confirm the anchor you replaced is executable code, not documentation.

outcome: T1 model=sonnet attempts=1 result=pass review=clean
agent: T1 id=aa78c556681b9aec1 role=implementer model=sonnet

## PLAN R1 FIRED — the predicted cross-kit seam is now real (reported, NOT edited)

Writing T1's `outcome:` line moved the cross-kit sonnet sample from 86 finished tasks to 87.
`tests/test_bench_routing.py` pins the old number, so it now fails:

    AssertionError: 87 != 86        (tests/test_bench_routing.py, 43 tests, 1 failure)

Handled per GUARDRAILS: those three bench files are untouchable in every circumstance, and a
reddened untouchable file is a REPORT, never an edit. No edit made. Task verifies are scoped
(T1 ran only test_role_ledger / test_per_task_dollars / test_guardrails_layout) so tasks are
unaffected; T8's full-suite sweep will see it and must report it as the known seam.

**Orchestrator's assessment, recorded for whoever fixes it:** the bench assertion pins counts
derived from `.claude/kits`, a directory that GROWS every time any kit executes. It was going
to fail on the next kit run regardless of this one — `role-ledger` merely got there first.
That is a defect in the bench test, not in this kit, and repinning it to the new literal only
resets the timer. The durable fix is to assert a property that survives growth (monotonic
non-decrease, or a synthetic `--kits-dir` fixture like the rest of that file already uses for
everything except `ReadOnlyProofTests`). Raised with the user twice; execution continued per
the guardrail rather than blocking on the answer.

**Consequence to hold in mind for the rest of the run:** "full suite green" is no longer a
clean signal — it is now "green except one known failure", which is exactly the state in which
a real regression gets waved through. Every remaining full-suite check must confirm the failure
count is EXACTLY 1 and that its file is test_bench_routing.py, never merely "some failures".

## T2 — done (first try, clean). Warm cluster: same agent as T1.

`REVIEWER_RE`/`DEFECT_RE` + `parse_reviewers`/`parse_defects`. Suite 1244 → **1264** (+20).
Suite state confirmed by the orchestrator's seam-aware checker: 1264 tests, exactly ONE
failure, and it is the known R1 seam — no regression.

**Six-way parser disjointness verified independently**, not taken from the implementer's
claim: one blob carrying all six families fed through all six parsers, each sees exactly 1.
Baseline for the four pre-existing families was recorded before dispatch and is unchanged.

**The asymmetric tolerance is real and correct** — same contradictory payload
(`findings=2 confirmed=5`), opposite handling:

    `agent:`    line KEPT, fields degraded to None   (the line also carries dollar
                                                    attribution, which must survive)
    `reviewer:` line DROPPED whole                 (the line exists ONLY to record
                                                    adjudicated findings — without them
                                                    it has no purpose)

Two families, opposite strictness, each correct for what its line is FOR. This is the kind of
distinction that gets flattened into "be tolerant everywhere" by an implementer working
without the rationale, and it is the clearest evidence so far that the architect pass earned
its cost. Duplicate `defect:` keeps the FIRST (re-runs must not double-count) + note.

**ORCHESTRATOR INSTRUMENT ERROR #10.** My pre-dispatch disjointness baseline reported
`parse_reroutes sees 2` and `parse_sessions sees 2` — apparent leakage. Cause: all four
parsers return `(events, notes)`; I unpacked two of them and called `len()` on the raw
2-tuple for the other two. Measured the tuple, not the events. Corrected before reporting.

Running tally of my own false findings this session: **10, against 2 real defects found.**
Every one is the same shape — a proxy measured and reported as the thing itself (string in a
docstring, status after a pipe, bytes vs characters, an unconditional check on a conditional
feature, PYTHONPATH against an absolute-path loader, len() on a tuple). None were domain
mistakes; all were mechanical mis-measurement, and each died within one command of being
checked. The lesson is not "be more careful" — it is **verify the instrument before
reporting the result**, which is exactly what this kit's GUARDRAILS demand of implementers.

outcome: T2 model=sonnet attempts=1 result=pass review=clean
agent: T2 id=aa78c556681b9aec1 role=implementer model=sonnet   # warm cluster T1→T2, shared id

## Pre-commitment: what CORRECT looks like for T4's real-data card

Recorded BEFORE T4 runs, so a predicted-empty result is not mistaken for a defect (this
orchestrator has produced 10 false findings this session; pre-committing to the expected
shape is the cheapest available guard against an eleventh).

Ledger census right now:

    `agent:`    119 lines across 13 kits   <- parsed since T1, quality fields all absent
    `reviewer:`   0 lines                (nothing writes them until T6)
    `defect:`     0 lines                (nothing writes them until T6)

Therefore, when T4 renders `## Role quality` against the REAL kits dir, the correct output is
**empty / "no role evidence recorded"** — not populated. Reasons, both intended:

1. All 119 existing `agent:` lines predate the quality fields, so `findings`/`confirmed`/
   `result` are `None` on every one of them. Precision is uncomputable and must report as
   absent, never as 0% (GUARDRAILS: "if you find yourself writing `or 0` on a quality figure,
   you are fabricating evidence").
2. `reviewer:`/`defect:` families have zero instances repo-wide because the writer contract
   arrives in T6. Readers first, writers second, by design.

This is PLAN D5 (retroactive capture rejected) made visible: **the 21 pre-existing kits
contribute zero role evidence forever, and the card must SAY so** rather than inventing a
number. An empty card here is the feature. A populated one would mean something fabricated
evidence — that is the failure to look for, and it is the exact defect `bench_routing
compare` shipped with before its `no_role_evidence` gate.

Only the T5 demo fixtures (synthetic) and future runs recording under the T6 contract will
ever populate it.

## T3 — done (first try, clean). Warm cluster: same agent as T1→T2 (3rd task).

`scan_kits` threads `agents`/`reviewers`/`defects` into every record. Suite 1264 → **1268**.
Seam-aware checker: 1268 tests, exactly one failure, the known R1 seam — no regression.

Verified against REAL data, and every figure matched the pre-commitment recorded before T4:

    kits scanned ....................... 22
    agents threaded .................... 119  == the raw `grep -c '^agent:'` count
    reviewers / defects ................ 0 / 0   (no writer until T6 — as predicted)
    records missing the 3 new keys ..... none    (incl. the TASKS.md-only path)
    agent events carrying quality data . 0       (all 119 predate the fields — as predicted)

The 119-vs-119 match matters: it is an INDEPENDENT cross-check (raw grep vs threaded parse),
not the implementer's own count echoed back.

**The R1 seam literal drifted 87 → 88** as T2/T3 outcome lines landed, exactly as expected.
The orchestrator's seam-aware suite checker matched the assertion's SHAPE (`\d+ != \d+`)
rather than its literal, so it survived the drift without edits. Pinning the literal would
have repeated the bench test's original mistake one level up — the same defect, in the tool
built to monitor that defect.

outcome: T3 model=sonnet attempts=1 result=pass review=clean
agent: T3 id=aa78c556681b9aec1 role=implementer model=sonnet   # warm cluster T1→T3, shared id

## CORRECTION to my own pre-commitment (made BEFORE T4's result arrived)

I predicted the real `## Role quality` card would render EMPTY. That is wrong, and I am
correcting it before the output exists rather than rationalising afterwards.

Real ledger census, measured:

    role=implementer .... 108 lines
    role=verifier ....... 12 lines   (model=sonnet x10, model=haiku x2)
    role=escalation ..... 0 lines

The zero-evidence branch requires ALL THREE role event counts == 0 AND defects == 0. Verifier
events = 12, so the card takes the **populated** branch. The correct rendering is therefore:

    verifier: events 12, with_precision 0, findings/confirmed 0, precision ABSENT (None)
    reviewer / escalation: 0 events
    architect: 0 defects across 0 kits

So "empty" was the wrong prediction; "populated with events but precision absent" is right.
The invariant I actually care about is unchanged and is the thing to check: **precision must
render as absent, never as 0%.** 12 events with no quality data is not 0% precision — it is
*unmeasured*, and collapsing the two is the exact fabrication D5/GUARDRAILS forbid.

Worth recording that this is the more interesting case to have landed on. An empty card only
proves the zero-branch works. A populated card carrying events with absent precision is the
harder honesty test — it is where a naive implementation writes `precision: 0%` and silently
converts "we never measured" into "they were wrong every time".

## T4 — done (first try, clean). Warm cluster CLOSED: T1→T4 on one agent, 4 tasks = Fable's cap.

`role_quality_stats` + schema v2 + the always-rendered `## Role quality` card. Suite 1268 →
**1277**. Seam-aware checker: exactly one failure, the known R1 seam (now `89 != 86`).

**The trap I flagged pre-dispatch was handled better than the brief asked.**
`tests/test_crossrepo_trend.py` carries 5 `schema_version` sites belonging to different cards;
a blanket swap would have gone green while silently corrupting the trend contract. Actual result
— three different treatments for three different reasons:

    line 116  rs.HISTORY_SCHEMA_VERSION    symbolic — tracks the bump automatically
    line 768  literal 1 + comment "deliberately NOT rs.HISTORY_SCHEMA_VERSION"
                                           the old-shape (pre-role-ledger) tolerance test
    line 940  literal 1, TrendDemoPinnedTests (--trend --json)   the TREND card, untouched

Engine confirms `HISTORY_SCHEMA_VERSION = 2`, `TREND_SCHEMA_VERSION = 1`.

**The honesty invariant holds on real data** — this was the whole point of the task:

    | verifier | 12 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 12 |
    - Architect: 0 brief defects across 0 kits (floor — kits run before role-ledger
      adoption record none)

Precision renders **n/a**, never 0%. Twelve verifier events with zero quality data are reported
as UNMEASURED, not as "wrong every time" — opposite claims that a naive `or 0` would have
collapsed. The architect zero is explicitly labelled a **floor**, i.e. a lower bound produced by
non-recording rather than an assertion that no defects occurred. That single word is the
difference between an honest card and a fabricated one.

My earlier prediction that the card would render EMPTY was wrong and was corrected in NOTES
BEFORE this result arrived, not after.

**Implementer independently hit and correctly diagnosed the heredoc/stdin collision** in the
brief's verify (`cmd | python3 - <<'PY'` — the pipe and the heredoc both claim stdin, so the
JSON lands concatenated onto the script body). It reproduced it in isolation, called it a shell
artifact rather than a code bug, and ran the identical assertions via file redirect. The
orchestrator made the same mistake earlier today; the brief inherited it. **Fix for future
kits: never write `producer | python3 - <<'PY'` in a verify — redirect to a file first.**

outcome: T4 model=sonnet attempts=1 result=pass review=clean
agent: T4 id=aa78c556681b9aec1 role=implementer model=sonnet   # warm cluster T1→T4, shared id

## T5 — done (first try, clean). PHASE 1 COMPLETE (T1–T5).

Demo fixtures populate `## Role quality`. Suite 1277, exactly the known R1 seam (`90 != 86`).
All pre-existing demo pins (tiers, reroutes, kit rows, dollars) unchanged — the new families
being invisible to the four old parsers IS the additive test, and it passed unedited.

The demo card is the first render of the feature actually fed:

    | verifier   | 2 | 2 | 5 | 3 | 60% | 1 | 1 | 0 | 0 |
    | reviewer   | 1 | 1 | 2 | 1 | 50% | 1 | 0 | 0 | 0 |
    | escalation | 1 | n/a | n/a | n/a | n/a | 1 | 0 | 0 | 0 |
    - verifier haiku:  findings 2, confirmed 2, precision 100%
    - verifier sonnet: findings 3, confirmed 1, precision  33%

**What this kit would say about its own orchestrator.** My record across this session is
**12 findings raised, 2 confirmed — 17% precision** (10 false: docstring greps x3, `$?` after
a pipe, an empty regex read as absence, a doc quoting a claim in order to correct it, awk
bytes-vs-characters, an unconditional check on a conditional feature, PYTHONPATH against an
absolute-path loader, `len()` on a 2-tuple). A verifier at 17% is one whose findings should be
distrusted on sight. That number existed nowhere in this system until now — I only know it
because I happened to keep count in prose, which is exactly the fragility D4 identifies.

Implementer used the file-redirect probe form per the orchestrator's pre-flag, with assertions
byte-identical to the brief. Verify-form defect confirmed contained to T4/T5 only (the two
tasks that consume CLI JSON); T1/T2/T3/T6/T7 use the safe heredoc-only form. My earlier claim
that it would propagate through all eight briefs was wrong — checked, corrected.

outcome: T5 model=sonnet attempts=1 result=pass review=clean
agent: T5 id=affb1de407d0a8686 role=implementer model=sonnet

## PHASE 1 REVIEW (opus) — substantially sound, D1–D8 held, 4 findings

Reviewer confirmed by independent probe, not assumption: `AGENT_ROLES`/`AGENT_RE` unchanged;
degradations all `None`+note and never drop a line (and `PAIR_RE` really does capture `-1`, so
the negative guard is reachable); **zero** enriched events across the 21 pre-existing kits with
every NOTES.md mtime untouched (D5 honored); no implementer rate computable from `roles` (D7);
all three precision paths guard the denominator → `None`, `_rate_pct(None)` → `n/a`, verified
across six degenerate shapes in BOTH json and markdown; six families disjoint under an
exhaustive 6x6 cross-parse including `- `/`* `/indented forms; `build_history`'s 5-positional
signature identical at all four call sites, and `bench_routing.py:500` reads only
`history["tiers"]` with no key-set or schema assert — so schema v2 does not break it.

**F1 — PLAN R2 fired live, and I caused it. FIXED.** Three lines of MY OWN prose in this
NOTES.md (a census table and a design note) began with `reviewer:` / `defect:` in column 1 and
were matched by the parsers shipped in T2, emitting three spurious `unrecognized ... line`
notes into the REAL `--history` card. Benign — skipped, never turned into data (reviewer
events 0, architect defects 0 confirmed after) — but the collision guard is proven
non-theoretical. Fixed by backticking; spurious notes now 0.
The irony is exact: **I wrote prose ABOUT the reviewer:/defect: grammar, and the parser I had
just shipped read my prose as data.** Same species as instrument errors #1/#9 (grep matching a
docstring) — a file that documents a grammar contains strings in that grammar.

**F2 — the Phase-2 landmine. AMENDED INTO T6 BEFORE DISPATCH.** T6 requires
`skills/execute/SKILL.md` to carry verbatim example lines
(`reviewer: P1 model=opus findings=2 confirmed=1 result=accepted`, `defect: T3 kind=stale-pin`).
The reviewer proved by probe that either string landing in a NOTES.md — plain, bulleted, or
indented — parses as VALID DATA: a fabricated 50% reviewer precision and a fabricated architect
defect, with no note and no test to catch it. Only backticking suppresses it. Nothing in PLAN,
GUARDRAILS or T6's brief said so, and this orchestrator had already quoted grammar into NOTES.md
five times. This is the highest-value finding of the review: it is fabricated evidence entering
through the documentation of the anti-fabrication feature.

**F3 — stale docstring (PLAN R4 violation).** `bin/routing_scorecard.py:2677` still says
`run_history` yields "the eight-key card"; it is nine since T4. The inline comment at :2798 was
updated, this sibling sentence was missed — exactly the species R4 exists to prevent.

**F4 — false-zero in the per-tier detail lines (ARCHITECT drift, not implementer drift).**
`by_tier` carries no `with_precision`, so "verifiers ran and recorded nothing" and "verifiers
ran and genuinely found nothing" render byte-identically:
`- verifier haiku: findings 0, confirmed 0, precision n/a`. The top-level row disambiguates via
`With precision 0`; the tier lines cannot. T4 implemented its brief exactly — the brief pinned
`by_tier`'s keys and gated the lines on `events > 0`. Also: an off-ladder event's findings count
into the top-level sum but no tier bucket, so `sum(by_tier.findings) < findings` with only a
trailing note as disclosure.

**T8's collision check is decoration and must be fixed (F1's second half).** `TASKS.md:550`
greps `.claude/kits/*/NOTES.md | grep -v 'role-ledger'` — excluding the ONLY kit where the
collision has ever occurred. Per GUARDRAILS ("verify commands must be able to fail") that clause
cannot fail. A `tautological-verify` defect in the kit that coined the term.

## T5b — done (orchestrator-added Phase-1 remediation; first try, clean)

F3 + F4 from the opus review. Suite 1277 → **1281**. Exactly the known R1 seam (`91 != 86`).

F3: `run_history`'s "eight-key card" → nine-key; swept the file for sibling stale prose
(`-key card`, `keys exactly`, `Top-level keys`, `schema v1`) — T4 had already updated the rest,
so the single missed sentence was the whole of it. `eight-key` hits now 0.

F4: `by_tier` buckets gain `with_precision`; the per-tier line now renders two distinguishable
shapes, verified on real AND demo data:

    real  - verifier sonnet: 10 event(s), 0 with recorded precision — not measured
    demo  - verifier sonnet:  1 event(s), 1 with recorded precision, findings 3, confirmed 1, precision 33%

Ten sonnet verifiers that RECORDED nothing no longer read as ten that FOUND nothing. Plus a
computed (never hardcoded) off-ladder disclosure line, correctly silent here because the gap is
genuinely zero. `tests/test_routing_history.py` needed no edit — its demo pins assert individual
`by_tier` sub-keys rather than whole-dict equality, so the added key did not disturb them; the
implementer checked and reported that rather than editing defensively.

**What F4 really was.** T4 implemented its brief exactly; the brief pinned `by_tier`'s key set
and gated the tier lines on `events > 0`. The defect was in the SPECIFICATION — architect drift,
not implementer drift. That distinction is the whole point of the kit being built: a per-tier
first-try rate would have scored T4's implementer as flawless (it was) and said nothing about the
brief that mis-specified it. `defect:` lines exist precisely to catch this class, and this kit
has now produced a live instance of the thing it measures.

outcome: T5b model=sonnet attempts=1 result=pass review=clean
agent: T5b id=adc66a5d6371aee9c role=implementer model=sonnet

## T6 — done (first try, clean). The writer contract now exists.

Four pinned edits to `skills/execute/SKILL.md` (body only). Seam probe passed: the three
example lines round-trip through the SHIPPED parsers, so writer grammar and reader grammar are
proven to agree rather than assumed to.

**F2 defense verified independently and it holds completely.** Parsing the entire edited skill
as if it were a NOTES.md:

    parse_reviewers  events=0  notes=0
    parse_defects    events=0  notes=0

Zero events AND zero notes — the backticking suppresses even the benign note. Contrast this
kit's own NOTES.md before I fixed it: three spurious notes from three prose lines. The skill
that teaches the grammar is now inert under that grammar, which was the entire point of F2.
The implementer went past its brief to run this proof unprompted, including checking all five
parsers; the three remaining benign notes come from pre-existing indented angle-bracket
templates that degrade to a note, never to data.

**Contract sync holds:** frontmatter untouched, task fields / status vocabulary / phase
headings / `depends:`/`independent:` / model-override rule all unchanged — only execute-owned
NOTES.md line families grew, exactly as the CLAUDE.md shared-contract invariant requires.

**Stated cost, not hidden:** `skills/execute/SKILL.md` 14,663 → 18,374 B, i.e. **+927 est.
tokens resident on every execute run, forever**. This kit buys role-quality measurement at that
recurring price. It is a defensible trade — you learn whether verifiers and reviewers earn
their pins — but it is a trade, and naming it is the same discipline `docs/CONTEXT-WEIGHT.md`
applied to itself ("measurement has mass"). Note the tier difference that makes it acceptable:
CLAUDE.md is resident on EVERY call in EVERY session (which is why the context-weight reviewer
refused to add a run-line there); this skill is resident only while a kit is executing.

outcome: T6 model=opus attempts=1 result=pass review=clean
agent: T6 id=ae033b33db3ff39ab role=implementer model=opus

## T7 — done (first try, clean). PHASE 2 COMPLETE. The loop is closed.

`skills/architect/SKILL.md` now tells the next architect to READ its own defect ledger and
treat recurring kinds as its own failure modes. T6 taught execute to WRITE the evidence; T7
teaches architect to CONSUME it. Without both halves the ledger accumulates data nobody reads.

F2 defense verified independently on BOTH skills — `parse_reviewers` and `parse_defects` each
return **0 events, 0 notes** from either file. The two documents that teach the grammar are
completely inert under it.

Contract sync re-checked per the CLAUDE.md invariant and reported element-by-element by the
implementer: layout, all seven task fields, status vocabulary, phase headings,
`depends:`/`independent:`, and the model-overrides-frontmatter dispatch rule all agree across
both skills. Frontmatter lines changed in either file: **0**. Only execute-owned NOTES.md line
families grew, which is exactly what the invariant permits.

## FIRST REAL USE OF THE CONTRACT THIS KIT JUST BUILT

The ledger lines below are written under the T6 rules, adjudicated at the moment the verdict
resolved, not backfilled. This kit's first act after shipping the writer contract is to record
its own architect's defects — including the ones in its own briefs.

Phase 1 review (opus): 4 findings raised, 4 adjudicated real. F1 (my prose parsed as data),
F2 (the fabrication landmine in the skill examples), F3 (stale "eight-key" docstring), F4
(false-zero per-tier lines). All four forced an actual change. Result `revised`: the phase's
product was materially corrected — T5b exists because of it.

reviewer: P1 model=opus findings=4 confirmed=4 result=accepted

Architect brief defects confirmed against repo reality during this run:
- T8's collision check grepped every kit EXCEPT role-ledger, the only one where a collision has
  ever occurred — a clause incapable of failing, in the kit that coined the term.
- T4 and T5's verify used `producer | python3 - <<'PY'`, unrunnable in this shell (pipe and
  heredoc both claim stdin); confirmed independently by two implementers.
- T4's brief pinned `by_tier` without `with_precision`, so "recorded nothing" and "found
  nothing" rendered identically — a spec-level false zero, confirmed by the opus reviewer as
  architect drift rather than implementer drift.

defect: T8 kind=tautological-verify
defect: T4 kind=unrunnable-verify
defect: T4 kind=false-zero-spec

## Bookkeeping correction — caught by the kit's own scorecard

Running `routing_scorecard role-ledger` showed T7 as `done` with an empty Result column: I wrote
T7's NOTES section and the dogfooded `reviewer:`/`defect:` lines but omitted its own `outcome:`
and `agent:` lines. The tool this kit extends caught the orchestrator's lapse in its own ledger —
which is the argument for machine-readable evidence over prose in one line.

Also recorded: T5b (the orchestrator-added Phase-1 remediation for review findings F3/F4) carries
an `outcome:` line but has no `### T5b` entry in TASKS.md, so the scorecard cannot see it. Adding
the entry below rather than leaving the ledger and the task list disagreeing.

outcome: T7 model=opus attempts=1 result=pass review=clean
agent: T7 id=ae033b33db3ff39ab role=implementer model=opus   # warm pair T6→T7, shared id

## T8's collision check, rewritten TWICE — the second version was my own defect

**v1 (architect's).** `grep -l ... .claude/kits/*/NOTES.md | grep -v 'role-ledger'` — excluded
the only kit where a collision had ever occurred, so it could never fail. Logged as
`defect: T8 kind=tautological-verify`.

**v2 (mine).** I removed the exclusion so it would scan all kits. That made it WORSE: this kit's
NOTES.md now legitimately carries 4 `reviewer:`/`defect:` lines I wrote while dogfooding the T6
contract, so a pattern-presence check fails for a CORRECT reason. I traded a check that could
never fail for one that always would.

**v3 (correct).** The question was never "do these patterns appear" — it is "does any prose parse
as data BY ACCIDENT". Accidental collisions surface as parser tolerance notes; intentional lines
parse cleanly into events. So the check asserts zero notes across every kit's NOTES.md, and
reports the intentional event counts:

    collision proof: 0 accidental | 1 intentional reviewer + 3 defect line(s)

It can fail (any prose collision produces a note) and does not fire on legitimate data.

**The lesson, which is the kit's own thesis pointed at me.** I diagnosed the architect's
tautological verify correctly and then wrote a broken replacement, because I fixed the symptom
(the exclusion) without re-deriving what the check was FOR. Same failure shape as the
`avoidable mass` denominator this morning: patch the instance, miss the intent. No `defect:` line
for this one — the `defect:` family measures the ARCHITECT's briefs, and v2 was an orchestrator
error, not a brief defect. It belongs in prose exactly here.

Also recorded: I initially suspected my v2 amendment had broken the shell syntax (a `#` comment
inside `$(...)` swallowing the closing paren). `bash -n` says it parses fine — the suspicion was
unfounded, and I checked before asserting it rather than after.

## PHASE 2 REVIEW (opus) — NOT a pass. 2 major + 4 lesser findings. Two were mine.

**F2 was live and I had claimed it verified.** Two indented prose lines in this NOTES.md began
with a bare `agent:` — I had backticked `` `reviewer:` `` and `` `defect:` `` in the same blocks and
left `agent:` alone — and they were emitting `unrecognized agent line` notes into the REAL
`--history` card. My "F2 defense verified independently on BOTH skills" claim was narrow on two
axes at once: it ran only `parse_reviewers`/`parse_defects` (not `parse_agents`), and only over
the two SKILL.md files (not the NOTES.md the card actually reads). FIXED; the correct check —
all six parsers over all 22 kits' NOTES.md — now reports **0 accidental collisions**.
This is the second time this session the same class got me: fix the instance, miss the class.
The backtick rule in `skills/execute/SKILL.md:118-121` has the identical defect — it names only
`reviewer:`/`defect:` while `outcome:`/`agent:`/`reroute:` carry the same hazard with no warning.

**F1: `result=` on a `reviewer:` line is genuinely ambiguous, and I applied the wrong reading.**
`SKILL.md:107` defines `result` as "the fate of the dispatch's product under downstream
scrutiny". On a `reviewer:` line the DISPATCH IS THE REVIEWER, so `result=revised` means *the
review was overturned*. I wrote `result=revised` meaning *the phase was revised* — the opposite —
and the shipped card consequently read `precision 100% | Revised 1`: "a reviewer whose every
finding was confirmed was nonetheless overturned." Nonsense on its face.
CORRECTED to `result=accepted`: all four findings were confirmed, so the review stood entirely.
Note this is NOT a backfill in the sense T6 forbids — the adjudication (4/4) is unchanged; only
the token written under a misread definition is fixed. The skill still needs the clause that
pins which reading is authoritative; that is remediation work, below.

Remaining findings for remediation (T7b): F3 the skill teaches `findings=`/`confirmed=` on
`role=escalation` but `role_quality_stats` drops them and the card hardcodes `n/a`; F4 the
"or you acknowledged the defect" clause is an unfalsifiable confirmation branch and `findings`
has no counting rule, leaving the denominator writer-controlled; F5 suffixed kinds
(`stale-pin-2`) defeat the same-task recurrence signal T7 tells the architect to read, and the
"suggested kinds" nudge is too weak — I coined `unrunnable-verify` and `false-zero-spec` within
one session, so 2 of 3 real defects use unsuggested kinds; F6 the `reviewer:` all-or-nothing drop
(vs `agent:`'s degrade-in-place) is documented in these NOTES but taught nowhere in the skill,
where the writer needs it more.

Shared-contract invariant: PASS, no drift. Cost: proportionate, ~110 tokens of concrete fat
identified with line numbers.

**The reviewer's parting shot, which is the sharpest thing in the review:** the verifier
`findings=`/`confirmed=` path — T6's headline claim — is *completely unexercised end to end*.
This kit wrote 8 `agent:` lines, all `role=implementer`, zero verifier lines. The card still says
"verifier: 12 events, 0 with recorded precision" across all 22 kits. Only `reviewer:`/`defect:`
were ever dogfooded. The feature's main path has been proven by synthetic probe alone.

## I destroyed this kit's own ledger while fixing F2, and caught it by accident

My F2 fix backticked bare `agent:` prose lines using the predicate
`l.lstrip().startswith("agent:")`. That matched the indented prose I meant to fix AND the
**column-1 real ledger lines** — all 8 `agent: T… id=… role=implementer` records — turning them
into `` `agent:` T1 … `` which no longer parses. The kit's per-task agent attribution was silently
zeroed. `parse_agents` over this NOTES.md returned **0 events** where it should return 8.

I did not catch it by verifying the fix. I caught it minutes later while running an unrelated
census for the reviewer's parting gap, when `grep -c '^agent:'` printed 0 and the number was
absurd. Restored (column-1 lines only; indented prose stays backticked): 8 events, 0 notes,
0 collisions across all 22 kits under all 6 parsers.

**The predicate was blind to the exact distinction it was fixing.** F2 is entirely about
*column-1 grammar is data, indented prose is not*. My fix used `lstrip()`, which erases that
distinction before testing it. I wrote a repair for a data/prose confusion that could not itself
tell data from prose.

Third instance today of the same shape — fix the instance, damage the neighbourhood:
1. `avoidable mass` denominator fixed on the `session` card; `watch` shipped with the identical
   conflation and was only caught by the tool's first real use.
2. T8's collision check: diagnosed the tautology correctly, replaced it with a check that always
   fails, because I patched the symptom without re-deriving the intent.
3. This one: fixed a collision by mangling the data the collision check exists to protect.

Standing rule earned, and it is not "be careful": **after any mechanical edit to the ledger, re-run
the parsers and assert the EVENT COUNT, not just the note count.** Zero notes looked like success;
zero events was the actual state. I checked the half of the invariant that was easy to check.

## T7b — done (first try, clean). All 6 Phase-2 findings remediated.

`skills/execute/SKILL.md` 18,374 → 20,139 B; `skills/architect/SKILL.md` byte-identical
(already consistent with the F3 reading). Suite 1281, only the known R1 seam.

Verified independently:

    F2  all six families named in the hoisted rule ...... outcome/agent/reroute/session/reviewer/defect
    F1  shipped reviewer example now coherent .......... findings=2 confirmed=2 result=accepted
    both skills inert under ALL six parsers ............ 0 events each
    accidental collisions across all 22 kits .......... 0

**F3's reasoning is better than the choice I offered.** I framed it as "narrow the skill (matches
the reader) vs extend the aggregation (faithful to PLAN D1)". The implementer chose (a) and gave
a substantive reason rather than a convenience one: **an escalation consult delivers a FIX, not a
VERDICT — it raises no findings for the orchestrator to adjudicate, so precision has no referent.**
The reader's shape is not an oversight; PLAN D1's phrasing was the loose end. Route (b) would have
manufactured a metric with no honest input. That is the correct call and I had it backwards.

**F1's fix chose numbers over token, and the reasoning matters:** the incoherent example
(`findings=2 confirmed=1 result=accepted`) was repaired to `findings=2 confirmed=2` rather than
flipping the token to `revised`, because `accepted` is the far more common reviewer case and
**the example is what gets copied**. Fixing an example is not just making it true — it is choosing
which truth future writers will imitate.

**Writer/reader divergence caught by the implementer and closed by the orchestrator.**
`parse_defects`' docstring still taught the `stale-pin-2` suffix that F5 had just abolished in the
skill. The implementer flagged it as outside its write fence rather than reaching for it — the
correct move — and I fixed the one line. Behavior was never affected (keep-first dedupe is
identical either way); the divergence was purely in what the two documents TAUGHT. Exactly the
class R4 exists to prevent, caught this time at the seam between a skill and the engine it feeds.

outcome: T7b model=opus attempts=1 result=pass review=clean
agent: T7b id=ac1da2c51c1be0eaa role=implementer model=opus

## Pre-commitment: how I will adjudicate the T7b verifier's findings

Recorded BEFORE the verdict arrives, because I am the interested party. A low `confirmed` count
flatters the verifier's precision; a high one indicts briefs I wrote. Deciding the rule after
seeing the findings is exactly the motivated reasoning F4 was written to prevent — so the rule is
fixed here, quoted from the skill T7b just shipped (`skills/execute/SKILL.md:113`):

> a finding is real only when it produced a concrete artifact: a code or doc change, a claim
> reverted, a `defect:` line recorded, a task blocked. A finding you acknowledged but changed
> nothing for is NOT confirmed, and when you are unsure whether a finding is real it is NOT
> confirmed.

Applied literally, this means:
- A finding I agree with but do not act on → **NOT confirmed**. Agreement is not an artifact.
- A finding that is true but cosmetic, where I choose not to change anything → **NOT confirmed**.
- A finding I am uncertain about → **NOT confirmed**. The tie goes against the verifier.
- Only a finding that moves a byte, reverts a claim, records a `defect:`, or blocks a task counts.

`findings` = the verifier's own distinct claims as IT presented them. I will not re-bundle
several into one to raise precision, nor split one into several to lower it. The verifier was
told this counting rule at dispatch, before it knew its count would be recorded.

This is the first genuine verifier-precision datum in the repo. It is also self-referential: the
verifier is auditing the skill that defines how its own precision is recorded, and I am scoring
it using that skill's rule. If the number comes out flattering, that is worth less than if it
comes out ugly — an ugly number I could have massaged and did not is the only evidence that the
rule binds.

## Ground truth for T8, recorded BEFORE dispatching it

T8 is a mechanical run-and-report on haiku. Its value is an independent record — which is worth
nothing if I simply believe whatever it reports. Pre-running the same three checks makes its
report falsifiable:

    1. suite ............... 1281 tests, exactly 1 failure: test_bench_routing, `92 != 86`
    2. `## Role quality` ... 1 section rendered on the real card
    3. collision proof ..... 0 accidental | 1 intentional reviewer + 3 defect

If T8 reports anything materially different from these, one of us is wrong and the discrepancy
is the finding. Note the seam literal will have climbed past 92 by the time T8 runs — every
`outcome:` line this kit adds moves it — so a DIFFERENT number there is expected and correct;
a different failure COUNT or a different file is not.

## Two standing defects outside this kit's scope, one root cause

Both pin a value derived from something that MOVES, so both were doomed when written:

1. **`tests/test_bench_routing.py:457`** pins `tiers["sonnet"]["with_outcome"] == 86` — a count
   derived from `.claude/kits/`, a directory that grows every time any kit executes. Red all
   afternoon (`92 != 86` and still climbing). Repinning the literal only resets the timer; the
   durable fix is to assert a property that survives growth (monotonic non-decrease, or a
   synthetic `--kits-dir` fixture, which that file already uses for everything except its
   read-only proof). Fenced as untouchable for this kit — correctly, since I committed it hours
   ago and should not quietly rewrite its assertions to accommodate a kit I am running.

2. **`skills/execute/SKILL.md`'s session-id recipe** resolves the projects dir from `pwd`, which
   is wrong whenever a session STARTED in a different directory. Reproduced again at close-out:
   the recipe returns `a1a5c610…` (1,343 B, last written 22:37 yesterday, a different session)
   while this run's transcript is `fc6c2eb3…` (11.4 MB, written 14 seconds ago). It does not
   fail — it returns a confident wrong answer no guard catches, and would have attributed this
   entire run to an unrelated session in the cross-kit history. Found during the context-weight
   close-out, recorded then, still unfixed. This kit's Phase 2 edited that very file twice
   without touching it, correctly, because it was out of scope.

Neither belongs in the `defect:` ledger: that family records defects in a RUN'S BRIEFS, found
while executing them. These are standing defects in shipped artifacts. The distinction is worth
preserving — contaminating the architect's defect count with unrelated engine bugs would make the
number useless for the thing it exists to inform. But it does expose a gap: **nothing in this
system records a standing defect found in passing.** Prose in a kit's NOTES.md is where they go
today, which is exactly the fragility that motivated this kit in the first place.

## T8 — done (first try, clean). Independent sweep matches ground truth exactly.

haiku, mechanical run-and-report, zero edits. Its report matched the ground truth recorded
BEFORE dispatch on every figure:

    check 1  suite ......... 1281 tests, exactly 1 failure: test_bench_routing `92 != 86`
    check 2  Role quality .. 1 section on the real card
    check 3  collision v4 .. 0 accidental across all six parsers; 1 reviewer + 3 defect intentional

That agreement is the point: pre-recording ground truth turned an independent report from
something to be trusted into something checkable, and it checked out.

**Collision proof shipped as v4, not v3 — caught in the last minute before dispatch.** v3 checked
only `parse_reviewers`/`parse_defects`, so it could NOT have detected the collision that actually
occurred this run (a bare `agent:` line in prose). The Phase-2 reviewer stated this explicitly as
"the single weakest point T8 should check"; I acknowledged it, then nearly dispatched the narrow
version anyway. **Fourth instance today of fixing the instance and missing the class — and the
worst of them, because I had been told the general rule in writing and still shipped the narrow
fix.** Knowing a lesson and applying it are separate acts.

**Two benign strings in T8's output, verified rather than waved past:** `FAILED next_day` and
`unknown role 'bogus' in --floor` are stdout PRINTED BY CODE UNDER TEST exercising its error
paths, not test failures. Exactly one real `FAIL:` header exists. A scan-for-the-word-FAILED
habit would have flagged both — which is why the orchestrator's seam-aware checker parses
`^(?:FAIL|ERROR): ` headers rather than grepping for the word.

outcome: T8 model=haiku attempts=1 result=pass review=clean
agent: T8 id=a8e7fdd143e74c77c role=implementer model=haiku

## Verifier adjudication (T7b) — the run's first real verifier-precision datum

The verifier raised **2 distinct findings**. Both were verified against the live repo before
adjudication, and both were **CONFIRMED** — each produced a concrete artifact, which is the
test the pre-committed rule requires (agreement alone would not have counted):

1. **F2's rule was stated but not APPLIED to the skill's own grammar lines.** T7b rewrote the
   backtick rule to claim all six families, but left `outcome:` (`:90`), `agent:` (`:108`) and
   `reroute:` (`:187`) as bare 4-space-indented spec lines. Running the parsers over the file
   produced **3 tolerance notes**. Artifact: 3 lines backticked.
   *This is the fifth time today the same narrow check got me.* My own verification asserted
   `events == 0` across both skills and never looked at `notes`. Zero events was true; zero
   notes was not. I checked the half of the invariant that was easy to check — the identical
   error I recorded two hours ago after mangling the ledger, written down and then repeated.
2. **My own docstring repair left broken prose.** Fixing the stale `stale-pin-2` teaching in
   `parse_defects` produced "re-runs must never kind verbatim on its own line" and a dangling
   "disjoint from the ..." with no subject. Functionally harmless, genuinely incoherent.
   Artifact: docstring rewritten. A one-line fix that broke two sentences — and I never re-read
   the result.

Post-fix: **events + notes across both skills, all six parsers = 0.**

agent: T7b id=a43ffa70bffc9052e role=verifier model=sonnet
agent: T7b id=a43ffa70bffc9052e role=verifier model=sonnet findings=2 confirmed=2 result=accepted

Two lines deliberately: the bare line as it should have been written the moment the dispatch
returned, then the enriched line once adjudication landed. That is T6's late-adjudication
mechanism (last line per `(task-id, agent-id)` wins) exercised on real data for the first time —
possible only because T8 ran before the adjudication.

`result=accepted`: the verdict stood as delivered. Both findings were real and neither was
overturned — which under the F1 rule pinned an hour ago describes the REVIEW's fate, not the
phase's.

**Precision: 2/2 = 100%.** Recorded with the caveat that a flattering number proves little; the
rule's binding force would only be demonstrated by an ugly one I declined to massage. What can be
said is that the tie-breaks were pre-committed against the verifier, both findings were
independently reproduced before being confirmed, and neither was mine to dismiss cheaply — both
were defects I had personally introduced and personally failed to catch.

**The seam moved to a different assertion:** `21 != 20` (haiku 20→21 after T8's outcome line),
not `92 != 86`. Same file, same single failure, different assert tripping first. The orchestrator's
checker passed correctly because it matches the assertion SHAPE and the file, never the literal —
the third distinct drift that design has now survived.

## END OF RUN — role-ledger complete, 10/10 first-try


Session id resolved by WRITE RECENCY (11.4 MB, written seconds before close), not by the execute
skill's `pwd`-derived recipe — which returns `a1a5c610…`, a 1,343 B transcript from 22:37
yesterday belonging to a different session. That recipe does not fail; it returns a confident
wrong answer no guard catches, and would have attributed this entire run to an unrelated session.
Recorded as a standing defect above; still unfixed.
