# NOTES — graph-convergence

Execute-owned. Cross-task learnings plus the machine-read ledger lines the routing scorecard
consumes. Kit dial: `autonomy: advisory` (PLAN.md) — re-route recommendations are printed,
never applied, and the escalation valve asks before spending frontier tokens.

Run id for this invocation: `2026-07-26-0431` (content-free per PLAN D8 — UTC date plus four
hex, no hostname, username, or path fragment).

## Setup notes

- The kit arrived as three drafted files with no agent trio. Execute created
  `.claude/agents/graph-convergence-{implementer,verifier,reviewer}.md` at setup. The agent
  registry is fixed at session start, so T1 dispatched through a direct Agent call on the
  task's pin, reading the implementer agent file as its instructions; the trio registered
  afterwards and served every later task normally.
- Both read-only roles carry an explicit non-destruction clause. This kit's verifier and
  reviewer are pinned to Bash/Read/Grep/Glob — no Write or Edit — but Bash alone is enough to
  delete a tracked file, which is how the copilot-budget-mode run lost an authored docs
  section to a verifier doing mutation testing. PLAN D4's rationale ("a verifier that cannot
  patch cannot be talked into fixing it") is therefore weaker than it reads; the clause
  requiring mutation on temp copies, byte-for-byte restore, and a closing
  `git status --porcelain` is what actually closes that gap. Worth carrying into T3's
  template wording.
- Warm-cluster hint vs phase gate: TASKS.md flags T1→T3 as a warm cluster, but T1 is Phase 1
  and T3 is Phase 2 with a reviewer boundary between them. The phase gate wins — T3 spawned
  fresh after the Phase 1 review. Warming across a review boundary puts unreviewed work in
  the tree while the reviewer reads it.

## Ledger

agent: T1 id=a452edd12ffcabce1 role=implementer model=opus
agent: T1 id=a64a989a7868ab131 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T1 model=opus attempts=1 result=pass review=clean run=2026-07-26-0431
agent: T2 id=a944987553d3b33ec role=implementer model=sonnet
agent: T2 id=a4d2f5f813b723008 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T2 model=sonnet attempts=1 result=pass review=clean run=2026-07-26-0431

agent: T2 id=a1bdd8a57396fef8d role=implementer model=sonnet
outcome: T2 model=sonnet attempts=1 result=pass review=revised run=2026-07-26-0431
reviewer: P1 model=opus findings=8 confirmed=6 result=accepted
agent: T3 id=a1a5cd25248c19064 role=implementer model=opus
agent: T3 id=aa62f6d984ef8afcd role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T3 model=opus attempts=1 result=pass review=clean run=2026-07-26-0431
agent: T4 id=af03e3bb1f5d444a3 role=implementer model=sonnet
defect: T4 kind=underivable-requirement
agent: T4 id=aad2875fe54494487 role=verifier model=haiku findings=1 confirmed=1 result=revised
agent: T4 id=aaed8925ff8f1cb53 role=implementer model=sonnet
agent: T4 id=a3b69734d2e7eece3 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T4 model=sonnet attempts=2 result=retry-pass review=revised run=2026-07-26-0431
agent: T5 id=a42f1882a5e5a4d99 role=implementer model=sonnet
agent: T5 id=a477e7549aac5b77b role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T5 model=sonnet attempts=1 result=pass review=clean run=2026-07-26-0431
defect: T5 kind=contradictory-acceptance
defect: - kind=contradictory-acceptance
reviewer: P2 model=opus findings=6 confirmed=6 result=accepted
agent: P2fix id=aff693267a61801f2 role=implementer model=opus
outcome: T3 model=opus attempts=1 result=pass review=revised run=2026-07-26-0431
outcome: T5 model=sonnet attempts=1 result=pass review=revised run=2026-07-26-0431
agent: T6 id=a4d3e903e7e4ad653 role=implementer model=sonnet
agent: T6 id=a0b5588f8df3801e8 role=implementer model=sonnet
agent: T6 id=a5dc2e8c5ef397337 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T6 model=sonnet attempts=2 result=retry-pass review=clean run=2026-07-26-0431
agent: T7 id=aecebbadc6d928c1e role=implementer model=sonnet
defect: - kind=stale-plan-decision
agent: T7 id=aa098744464a10f67 role=verifier model=haiku findings=1 confirmed=0 result=revised
outcome: T7 model=sonnet attempts=1 result=pass review=clean run=2026-07-26-0431
agent: T8 id=a1aed1e6f7c04d91e role=implementer model=sonnet
agent: T8 id=a88fb76ecd6f93e0e role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T8 model=sonnet attempts=1 result=pass review=clean run=2026-07-26-0431
reviewer: P34 model=opus findings=8 confirmed=5 result=accepted
defect: T9 kind=contradictory-acceptance
agent: P34fix id=a0f73859a9a9008e3 role=implementer model=opus
reroute: sonnet to=opus mode=advisory tasks=T9 rate=2/5
defect: T10 kind=underivable-requirement
agent: T9 id=a117932b48e15133e role=implementer model=sonnet
agent: T9 id=a8f70464f54c9379e role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T9 model=sonnet attempts=1 result=pass review=clean run=2026-07-26-0431
defect: T12 kind=unspecified-path
defect: - kind=stale-pin
agent: T10 id=a3e87787baa9f5a3a role=implementer model=sonnet
agent: T10 id=af042d30bf434ee7f role=implementer model=sonnet
agent: T10 id=a24b6bb2e7307b594 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T10 model=sonnet attempts=1 result=pass review=clean run=2026-07-26-0431
agent: T11 id=a16ab5c6ea96420f0 role=implementer model=sonnet
agent: T11 id=ab9643991e7c99791 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T11 model=sonnet attempts=1 result=pass review=clean run=2026-07-26-0431
agent: T12 id=a7db816e3c3d0e37d role=implementer model=haiku
outcome: T12 model=haiku attempts=3 result=retry-pass review=revised run=2026-07-26-0431
reviewer: P5 model=opus findings=12 confirmed=8 result=accepted
agent: P5fix id=aa5267f842b193a99 role=implementer model=opus

## Phase 1 review — adjudication

The reviewer returned `revised` with eight findings; six were confirmed. Its D6 check went
well past the orchestrator's: ten CLI surface pairs (`--demo`, `--json`, `--history`,
`--live`, `--by-task`, `--trend` and combinations) plus a hand-built field-less legacy kit,
all byte-identical between the pre-T2 and post-T2 engines. It also re-derived the goldens
from the git-HEAD engine rather than the current one.

Confirmed and fixed before Phase 2 (F1–F4), with the orchestrator's adjudication of each:

- **F1 — the spec contradicted itself on `run=`.** "Stamped on every outcome line" vs "a
  clean pass carries none of the three". Resolved toward the first reading: `run=` is
  invocation provenance and belongs on EVERY outcome line; only `parent=` and `failure=` are
  restricted to escalation/blocked outcomes. This mattered because T5/T7/T8 implement their
  ledger writeback from this sentence.
- **F3 — the failure breakdown inverted D9's signal.** An escalation consult pinned at the
  rescuing tier had its `failure=` attributed to that tier, so the tier that FIXED the
  problem read as having a verification defect — the opposite of the inference D9 exists to
  support. Rule adopted: a failure class is attributed to the tier that FAILED, never the
  tier that resolved it, and an outcome carrying `parent=` contributes nothing to the tier
  breakdown (its parent already carries the failure).
- **F4 — placement was not enforced.** `failure=` was counted on any result and `parent=`
  counted as an escalation on any outcome, though the spec restricts both. Rule adopted: an
  out-of-grammar placement is dropped with a note, matching this file's existing "ignore and
  note" precedent for an unknown failure class — tolerant parsing here means ignore, never
  count.
- **F2 — a line was counted and called ignored at once.** Lineage did not validate the child
  task id while the failure breakdown did. Invariant adopted: no line may be simultaneously
  counted into a headline figure and reported as ignored.

Carried forward, not fixed here:

- **F5 (confirmed, split across T3 and T11)** — two halves. The architect half (the
  routing-history bullet in `skills/architect/SKILL.md`, the actual consumer of this
  evidence, does not mention the new sections) folds into T3, which already edits that file.
  The rendering half (the Failure breakdown table ships without the caption its neighbours
  carry, so nothing tells a reader the tier key is the IMPLEMENTER's dispatch tier) is
  assigned to T11, which already edits the scorecard's rendering — keeping T3 inside the
  architect skill rather than reopening the scorecard for one caption. Nothing reads that
  table before T11.
- **F8 (confirmed, folded into T5)** — nothing asserts D8's content-free run-id format on the
  reader side; the generators (T5/T7/T8) are where a format assertion belongs.
- **F6 (not confirmed)** — `render_markdown` raises on a `status: None` card where the old
  code rendered `None`. Unreachable from the CLI (`parse_tasks` rejects a status-less task)
  and no caller exists; recorded, not changed.
- **F7 (not confirmed)** — the new sections have no `--demo` path, because the byte-stability
  goldens forbid changing the demo fixtures. That is the correct trade; T11 needs a synthetic
  multi-kit demo anyway and should carry one.

## Per-task dollars are unavailable for this run, and the tool said so instead of guessing

`routing_scorecard <kit> --session <id> --by-task` resolves nothing for this run: all 28 agent
transcripts report `no *.output transcript found`. The cause is an id mismatch, worth recording
because it will recur:

- the session TRANSCRIPT id (what `session:` records, resolved by write recency) is
  `2a5f26f8-85b6-4863-91df-45e7899e096e`
- this session's agent `.output` files actually live under a DIFFERENT id, `374b277e-...`

`--by-task` assumes the tasks scratch directory is keyed by the session transcript id. In this
session it is not, so the join finds nothing. Whole-kit dollars via `--session` are unaffected;
only the per-task/per-role split is lost.

The important part is what the tool did about it: it printed `cost n/a` per agent with the
specific reason, and fell back to whole-kit attribution — it did not divide a session total across
tasks, and it did not guess. That is the never-fabricate rule holding under precisely the
condition it exists for, and it is worth pointing at the next time someone argues an estimate is
better than an absence.

Cosmetic artifact of this kit's own bookkeeping, recorded so a future reader is not alarmed by it:
two `agent:` lines use pseudo-task-ids (`P34fix`, `P5fix`) for the review-fix implementers, which
were not kit tasks. The parser reports "agent line for unknown task id ... ignored" for both. They
are ignored EVERYWHERE and counted nowhere, so the counted-and-ignored invariant is not violated —
they are inert audit records. A future kit wanting fix-round attribution in the dollar breakdown
should give the fix round a real task id instead.

## Closing review and fix round — the kit's two most serious defects were found LAST

The final review returned `revised` with twelve findings, eight confirmed. Two were blocking and
both had survived every prior gate:

**F1 — `budget_stop` broke D6 on the `--json` surface for 26 of 26 legacy kits.** T9 added the key
unconditionally where every T2 sibling is conditional (`if run:`, `if lineage:`,
`if failure_breakdown:`). This violated PLAN's own headline done-criterion. It survived twelve
tasks, five fix rounds and four phase reviews because **the D6 tripwire goldens cover markdown
`--demo` only** — and the orchestrator's own done-check repeated that same narrow comparison and
reported the criterion met. It was not. Fixed, and the tripwire now covers `--json` too, with key
ORDER pinned by re-serializing the parsed card.

**F2 — a `budget-stop` could erase a recorded verdict.** `parse_outcomes` is last-wins, and
`budget-stop` is the first result value that is not a verdict yet still overwrote one. Reproduced:
a task recorded `result=blocked ... failure=verification`, then one budget-exhausted resume, and
`with_outcome 1→0, blocked 1→0` — the failure and its class gone from the kit card and from
`--history`. No unusual flag needed; resuming a blocked task once the budget is spent is the
natural gesture. Fixed at BOTH ends: the reader keeps the verdict and drops the stop with a note
(protecting ledgers already on disk), and all three drivers decline the append (this repo's
precedent is to reject at the writer rather than leave a line for the reader to ignore).

Also fixed: seven false behavioral sentences in `docs/GRAPH-ENGINEERING.md` — including a
fabricated `budget: ceiling: <amount>, mode: api/subscription` contract that does not exist
anywhere in the code, invented in the same phase that shipped the real count-based dial; the
convergence table's collapse of three per-harness "today" columns into Claude's; and the `parent=`
wording in both SKILL.md files, which P34-F2 adjudicated toward the code and Phase 5 then edited
both skills without correcting.

**The pattern, stated once for the architect.** Every serious defect this run — F-D's inert
dialect check, F-C's inverted attribution wording, T6's frontmatter pollution, P34-F2's
`parent=`-on-blocked, the doc's two fabricated contracts, and now F1 and F2 — is the same thing:
**a claim about the surrounding system that nobody checked against the surrounding system.** Tests
were never weak; they asserted what the author was already thinking. What caught all of them was
running the code against the real corpus, the real parser, the real reader, the real prior state.

**Open gap flagged by the fix round, deliberately not fixed:** the three drivers parse only ONE of
the three verify dialects the repo's own kits use, so five kits — `context-weight`, `role-ledger`,
`telemetry-store`, `evidence-loop`, and `graph-convergence` itself — are undriveable by any driver
today. Same family as F-D. It is a driver behavior change rather than one of the four blocking
items, so it is documented honestly in the positioning doc and left for a future kit. Note the
irony worth keeping: the headless-driver property converged on all three harnesses, and none of
the three can currently run the kit that built them.

## HANDOFF — read this first if you are picking the kit up

**State at handoff.** All twelve tasks `done`. Suite 1753 (from 1497). Nothing committed: the
whole run — twelve tasks plus five fix rounds — sits in ONE uncommitted working tree, ~22 modified
and ~9 untracked paths. HEAD is the pre-kit commit. That is why `git diff` cannot attribute work
to a task anywhere in this run, and why the per-task file lists below matter.

**Per-task authorized file sets** (this file previously told verifiers they must be given these,
then never recorded them — the gap is closed here):

| Task | Files |
|---|---|
| T1 | `skills/execute/SKILL.md`, `skills/architect/SKILL.md` |
| T2 | `bin/routing_scorecard.py`, `tests/test_routing_scorecard.py` |
| T3 | `skills/architect/SKILL.md` |
| T4 | `bin/kit_verify_hook.py`, `tests/test_kit_verify_hook.py`, `.gitignore`, `skills/setup/SKILL.md` |
| T5 | `bin/claude_execute.py`, `tests/test_claude_execute.py` |
| T6 | `copilot/.github/agents/{verifier,reviewer}.agent.md`, `bin/copilot_docs.py`, `tests/test_copilot_docs.py`, `copilot-docs/aic-report.json` |
| T7 | `bin/copilot_execute.py`, `tests/test_copilot_execute.py` |
| T8 | `bin/codex_execute.py`, `tests/test_codex_execute.py` |
| T9 | `bin/routing_scorecard.py`, all three `bin/*_execute.py`, both SKILL.md, four test files |
| T10 | `bin/copilot_usage.py`, `bin/codex_usage.py`, their two test files |
| T11 | `bin/routing_scorecard.py`, `bin/statusline.py`, their two test files |
| T12 | `docs/GRAPH-ENGINEERING.md` (new), `README.md`, `copilot-docs/aic-report.json` |

**Convergence, honestly stated** (the doc's table overstates this; trust these numbers):

- Lineage (`parent=`), headless drivers, declared budget: **3 of 3**, genuinely met.
- Ledger id-stamping (`run=`): **3 of 3**.
- Tool scoping: **2 of 3**, as designed — Codex has no agent surface and PLAN fences it out.
- Node attribution AT DISPATCH: **2 of 3** — `claude_execute` stamps ids in the ledger but not
  into the dispatch prompt. Cause recorded as `defect: - kind=contradictory-acceptance`.
- **D3/D10 verify enforcement: 1 of 3.** The marker plus red→green precheck is Claude-only;
  `kit_verify_hook` is referenced 18× in `claude_execute.py`, once in `copilot_execute.py` (a
  comment saying wiring it "would be new scope"), and zero times in `codex_execute.py`. Copilot
  and Codex run a verify in driver code, which is what PLAN listed as their state BEFORE the kit.
  The property converged only by lifting Claude to their baseline. PLAN's table claims "enforced
  on all three" — it is not, and that is the largest gap between the plan and what shipped.

**Harness traps that cost time in this run** — don't rediscover them:

- Extracting `bin/routing_scorecard.py` from git into a temp dir does NOT run: it sibling-imports
  `copilot_execute` from its own directory. Run the extracted copy from inside `bin/` under a temp
  name, or copy `bin/` and `data/` wholesale.
- The D6 goldens cover MARKDOWN `--demo` only. A change can pass every golden and still break
  byte-identity on `--json` — that is exactly how the closing review's F1 escaped twelve tasks,
  four fix rounds and four phase reviews. Check `--json` on real kits, not just the demos.
- `python3 -m unittest tests.test_x` (dotted form) is broken on this machine; use
  `discover -s tests -p 'test_x.py'`.

**Open items at handoff** (the closing fix round addresses the first four; verify before trusting):
F1 `budget_stop` unconditional in `--json`; F2 `budget-stop` erasing a recorded verdict;
`docs/GRAPH-ENGINEERING.md`'s seven false behavioral sentences; the `parent=` wording in both
SKILL.md files. Not addressed: the `retry-pass` cannot carry `failure=` grammar gap; the
`--dry-run` dependency-filter gap; `claude_execute._extract_verify`'s narrower dialect support;
the "including this one" miscount in all three drivers' budget-stop message.

## LEDGER CORRECTION: T5 was mis-kinded, and the recurrence claim was overstated

The final review challenged this file's own defect labelling, and it was right. T5's line has been
changed from `underivable-requirement` to `contradictory-acceptance`. The reasoning, recorded so
the correction is auditable rather than silent:

`underivable-requirement` was coined for "the brief demands a comparison against data the pinned
format does not record" (T4: a marker newer than a status flip, with no status timestamps; T10: a
time-window overlap, with no clock in the ledger). T5's defect is a different animal: its
acceptance bullet "escalation outcomes carry `parent=`" is unsatisfiable by the design the SAME
brief pins, because the ladder escalates within one task id so no second id exists to name. That
is not missing data — it is an acceptance criterion no execution path can produce, which is
exactly what `contradictory-acceptance` names.

Worse, the justification originally written here was "reusing T4's kind rather than coining, which
is the point of having coined it deliberately". That defends reuse as a virtue without ever
testing the fit against the coined definition — the labelling habit made visible. This file then
asserted that `underivable-requirement` ×3 was "the dominant recurring kind" and that "all three
share one shape". Two shared it. The corrected reading:

- `underivable-requirement` ×2 (T4, T10) — a real, sound signal, and its architect lesson stands:
  check a brief's DATA DEPENDENCIES against the format before the kit ships.
- `contradictory-acceptance` ×3 (T5, T9, and the new kit-level line below) — the larger cluster,
  with a different lesson: check that every acceptance bullet is SATISFIABLE by the design the
  brief itself pins.

Folding T5 under the first kind lost the second lesson entirely. That is the precise harm the
"reuse whenever one fits, coin only when none does" rule is meant to prevent, inverted: reuse
applied where it did not fit. An honesty-erosion instance inside the honesty ledger, caught by an
independent reviewer rather than by the orchestrator who wrote it.

**Newly recorded — `defect: - kind=contradictory-acceptance` (kit level).** The review found this
under-recorded, and it is the reason the kit's headline attribution property lands at 2-of-3:
T5's brief asked only for `run=`/`parent=` in the LEDGER, while T7's and T8's asked additionally
for ids in the DISPATCH PREAMBLE. Three briefs for one convergence property, disagreeing about
what the property is. `bin/claude_execute.py` therefore stamps ids in the ledger but not into the
dispatch prompt — verified by dry-run: codex and copilot emit `[kit=... run=... task=...]`,
claude emits the bare brief. This file recorded that as an "architect-side brief inconsistency"
in prose and then never gave it a `defect:` line, which is the exact omission P34-F6 warned about
one section earlier.

## PLAN's four "Done looks like" criteria — checked by running, all four met

1. **Full suite green** — 1753 tests, OK (started at 1497; +256 over the run).
2. **A demo kit under each driver emits `outcome:` lines carrying `run=`** — verified by running
   all three drivers against stub binaries in temp kits:

       claude   - outcome: P1 model=claude-haiku-4-5 attempts=1 result=pass review=none run=2026-07-27-fc3c
       codex    - outcome: P1 model=gpt-5.6-luna     attempts=1 result=pass review=none run=2026-07-27-2e62
       copilot  - outcome: P1 model=cheap            attempts=1 result=pass review=none run=2026-07-27-6431

3. **`--history` groups escalations under their parent tasks** — confirmed via the new
   `--demo --alarm --history` path, which renders the Escalation lineage section with children
   grouped under `spike-3/SP1 (pinned sonnet)`.
4. **Field-less legacy output is byte-identical** — the pre-kit engine (git HEAD) and the current
   engine produce identical `--demo` and `--demo --history` output (md5-compared, 1225 and 2100
   bytes).

Two things worth recording about HOW criterion 2 was checked, because the first two attempts
failed and both failures were the ORCHESTRATOR's fixtures, not the drivers:

- The Claude driver exited 2 with "no kit agent at .../probe-implementer.md" because the temp kit
  was named `probe` and the driver resolves its agent by kit-dir basename. Correct defensive
  behavior — it refused to dispatch blind rather than guessing an agent.
- It then rejected `model: cheap` and printed the valid ids and tiers. `cheap` is Copilot/Codex
  tier vocabulary; the Claude ladder uses haiku/sonnet/opus/frontier. Also correct — and a live
  demonstration of P34-F1's root cause from the other direction: the three harnesses genuinely do
  not share a model vocabulary.
- The corrected run also exercised D3/D10 end to end: the verify (`test -f marker.txt`) FAILED
  pre-task, the stub created the file, the verify passed, and `record` wrote the marker. Red to
  green, proven by a real run rather than a fixture.

## The orchestrator's concurrency rule, broken at the last task — and why the reasoning failed

I serialized every task in this run to avoid one hazard: an implementer's edits reddening the
suite while another task's verification reads it, so the failure lands on the wrong task. At the
very last task I made an exception, reasoning that T12 "only creates a markdown file and adds one
README line, so it cannot redden the suite", and dispatched it alongside T11's verifier.

The reasoning was wrong. `README.md` is a manifest source for the copilot-docs build, so editing
it changes a source-set hash and fails `test_in_process_check_reports_no_drift_and_is_read_only`.
A prose-only task CAN break the suite when the prose is itself a build input. T11's verifier
happened to report green, so nothing was actually misattributed — the outcome was luck, not
soundness.

The general lesson is the one this run keeps relearning from a new angle: **"this change is
harmless" is a claim about a dependency graph, not about the change.** The same shape as F-D (a
dialect check inert on the real corpus), F-C (a caption matching the heading but not the code),
T6's frontmatter (valid YAML, invalid to this repo's hand-rolled parser), and P34-F2 (`parent=`
tested only where it was legal). Every one of them was an assumption about the surrounding system
that nobody checked against the surrounding system.

Worth noting the Phases 3-4 reviewer PREDICTED this exact failure in its carry-forward notes:
"anyone editing skills or README in Phase 5 (T9, T12) must regenerate it again." The warning was
in this file before T12 was dispatched, and the dispatch brief did not carry it. Reading forward
into your own carry-forward notes before each dispatch is the cheap fix.

## T10's first dispatch stalled — a harness fault, deliberately NOT counted as an attempt

T10's first implementer dispatch died to a stream watchdog ("no progress for 600s"), not to a
task failure. Tree state checked immediately afterwards: zero edits, no partial writes,
`--kits-dir` absent from both usage scripts, suite still green at 1712. Nothing to clean up, so
the re-dispatch is a clean start rather than a recovery.

Ledger decision, recorded because it is a judgment call someone could reasonably make
differently: the stalled dispatch gets an `agent:` line (it happened, and the transcript exists)
but the re-dispatch that produces the work records `attempts=1`, not 2. The `attempts` field
feeds the per-tier first-try rate, which exists to measure whether a TIER can do a kind of work.
A watchdog timeout is evidence about the harness, not about sonnet, and folding it in would
understate the tier for a reason that has nothing to do with its output. The same logic in
reverse is why a genuine retry — T4's, T6's — must be counted: those produced work that failed
verification.

If stalls become frequent this reasoning should be revisited, since a tier whose dispatches
routinely stall IS a routing cost even when the cause is mechanical. One stall in twelve tasks
is not that.

## T12 pre-flight: two defects that would each have produced fabrication

**Defect 1 — "the four graph types" is undefined.** The phrase occurs exactly once in the whole
kit: in T12's own brief (TASKS.md:220). PLAN supplies SIX properties in its convergence table —
node isolation/tool scoping, deterministic verify edge, node attribution, lineage, declared
budget, headless kit driver — and never a four-way taxonomy of graph types. An executor told to
map "the four graph types vs repo components" must either import an outside taxonomy it cannot
check against this kit, or invent one and present it as the kit's own framing. Recorded as
`defect: T12 kind=unspecified-path`: the brief requires content the kit never supplies.

**Defect 2 — PLAN's rejection rationale points at a document that does not exist.** PLAN.md:33
fences out the knowledge-graph layer "(deliberately rejected — see docs analysis)". There is no
such analysis in `docs/`, and nothing else in the kit records WHY the knowledge graph was
rejected. T12's brief requires documenting "what was deliberately rejected ... and why", so the
reason for the headline rejection is a dangling pointer. Recorded as `defect: - kind=stale-pin`
at kit level — a pinned reference proven not to resolve. This is a second kit-level defect of a
DIFFERENT kind from the earlier `stale-plan-decision`, so the two aggregate separately, as
intended.

Resolution at dispatch, and the honesty rule that governs it:

- T12 uses the kit's OWN vocabulary — the six convergence-table properties — rather than an
  unsourced external taxonomy. The kit's evidence is what the doc can stand on.
- T12 states the rejection rationales that ARE recorded: D5's reasoning on driver fan-out (it
  multiplies real AIC/quota spend for a wall-clock gain only), and PLAN's out-of-scope list.
- For the knowledge-graph rejection, T12 must say plainly that the kit records the decision but
  not its rationale, and must NOT invent one. A fabricated rationale in a positioning doc is the
  worst possible place for one: it reads as settled history and every later reader inherits it.
  This is the same discipline as T10's label — an honest gap beats a confident fiction.

That is three pre-flighted tasks in Phase 5 (T9, T10, T12) each carrying a real brief defect, plus
T11 carrying a performance trap. Every one was cheaper to catch before dispatch than after.

## T11 pre-flight: the statusline alarm must READ a snapshot, never recompute

Not a brief defect — the brief is ambiguous rather than wrong, and inflating the defect count
would distort the recurrence signal the same way under-recording does. But it needs deciding
before dispatch, because the literal reading produces an unusable statusline.

Measured:

    bin/statusline.py today     143 lines, two small file reads, renders in ~15 ms
    a live cross-kit baseline   27 kit dirs, 3,775 NOTES.md lines to parse
    snapshot store              exists already (`--history --snapshot` -> dated JSON under
                                the gitignored trends/), but trends/ is ABSENT on this machine

T11 says the statusline alarm segment is "sourced from the same computation" as
`--trend`'s baseline. Taken literally that means recomputing a cross-kit escalation-rate
baseline on every prompt render — thousands of lines parsed, per keystroke-ish, against a
current 15 ms budget. The statusline is the most frequently executed code in this repo and the
only piece whose cost the user feels directly.

Decided for dispatch:

- The statusline READS the most recent snapshot under the gitignored snapshot dir and does no
  cross-kit computation of its own. `--trend` remains the thing that computes and writes.
- The store is absent right now, so the segment must degrade to printing NOTHING when there is
  no snapshot — matching the telemetry-store precedent that readers degrade with a note when the
  store is absent, and never fabricate.
- Because the segment is only as fresh as the last snapshot, the alarm must not imply live
  measurement. A stale snapshot showing a stale alarm is a dishonest figure of exactly the kind
  this kit keeps catching.
- The statusline stays read-only over the store and must not write, create, or refresh it.

Also standing (CLAUDE.md): a statusline command written into `~/.claude/settings.json` must be a
literal absolute path, because `${CLAUDE_PLUGIN_ROOT}` does not exist outside plugin context.
T11 changes the script, not the installed command, so nothing in it may touch `~/.claude`.

## T10 brief defect, also found by pre-flight — and it would have shipped a FALSE label

T10 asks `copilot_usage.py`/`codex_usage.py` to annotate a session row "where a session's time
window overlaps a ledger `run=` id's outcomes", labelled verbatim `(ledger join, time-window
match)`. That join cannot be built, because the ledger has no clock:

- No line family carries a timestamp. `outcome:`, `agent:`, `reviewer:`, `defect:`, `reroute:`
  and `session:` are all timeless by construction.
- A `run=` id's only temporal content is its DATE. The four hex characters are random per PLAN
  D8's content-free rule — deliberately not a clock. Making them one would violate D8.
- The usage scripts DO have per-session timestamps, so the asymmetry is real: one side has
  times, the other has a date.

The best join the data supports is date-level, and it is coarse: today's run wrote ONE run id
across twelve tasks, so a date-level match would annotate every session from today
indiscriminately. Implementing the brief as written would then stamp the words "time-window
match" on a same-day guess — the brief's own acceptance criterion ("labels present verbatim")
mandates a label that misdescribes the evidence. This is the honesty contract being broken BY
the brief, which is why it had to be caught before dispatch rather than argued about after.

Recorded as `defect: T10 kind=underivable-requirement`, reusing the kind coined for T4 rather
than minting a synonym for the false-label consequence. The root is the same: the brief demands a
comparison against data the pinned format does not record.

**That makes three `underivable-requirement` defects in one kit — T4, T5, T10 — and that is the
signal the architect should take away from this run.** It is now the dominant recurring kind here,
and all three share one shape: a brief specifying a join, comparison, or lineage link against
information the ledger grammar was deliberately designed not to carry. The fix is not more careful
executors; it is checking a brief's data dependencies against the format before the kit ships.

Resolution at dispatch: implement the DATE-level join, label it honestly for what it is (a
same-day run-id match, explicitly not a time-window match), and state the coarseness where a
reader will see it. The brief's verbatim label is overridden — an honest label that contradicts
the brief beats a verbatim one that lies, and PLAN/GUARDRAILS both rank honesty labels as
deliverables rather than decoration.

## T9 brief defect, found by PRE-FLIGHT rather than by a failed task

Checked T9's anchors while the Phases 3-4 fix round was still running, before dispatching it.
T9 requires the drivers to write `outcome: ... result=budget-stop` on budget exhaustion. That is
a FIFTH value in a closed vocabulary:

    bin/routing_scorecard.py:88   RESULTS = ("pass", "retry-pass", "escalated-pass", "blocked")
    skills/execute/SKILL.md:95    "`result` — exactly one of" those same four

So T9 is an outcome-line GRAMMAR change, and GUARDRAILS' travel-in-threes fence binds it:
`skills/execute/SKILL.md`, `skills/architect/SKILL.md`, and `bin/routing_scorecard.py` must move
in the same task. T9's acceptance names only the two SKILL.md files, and its verify command
(`-p 'test_*_execute.py'`) never runs `test_routing_scorecard.py`, so the third leg would be
neither implemented nor checked. As written the brief cannot be satisfied without the phase
reviewer rejecting it for a split grammar change — the acceptance and the fence contradict.

Recorded as `defect: T9 kind=contradictory-acceptance`, reusing an existing kind rather than
coining. The fit is not perfect — the acceptance is not self-contradictory, it is incomplete
against a standing fence — but `contradictory-acceptance` is the nearest of the six sanctioned
kinds and the ledger's rule is to reuse whenever one fits, because a coined synonym aggregates
with nothing. If "brief specifies a grammar change but names an incomplete file set" recurs, that
is when it earns its own kind.

Resolution at dispatch: the third leg (`bin/routing_scorecard.py` + its tests) is authorized as
in-scope for T9, and T9's verify is extended to run `test_routing_scorecard.py` as well. The
byte-stability goldens still bind — a new result value must not change field-less legacy output.

Worth noting for the architect: this is the first defect this run caught BEFORE the task ran.
The three earlier ones each cost a task round or a review round. Pre-flighting a brief's pinned
vocabulary against the code that consumes it is cheap; the ledger's recurring kinds are mostly
things a five-minute read would have caught.

## Phases 3-4 review — adjudication

Verdict `revised`, eight findings. The reviewer verified across all three drivers by running
them against stub binaries, and its two headline findings were independently re-confirmed by the
orchestrator before any fix was ordered.

Finding labels in this file are PHASE-SCOPED and collide across phases: Phase 1 used bare
`F1`-`F8`, Phase 2 used `F-A`-`F-F`, and Phases 3-4 below are prefixed `P34-` for exactly that
reason. A bare `F1` elsewhere in this file means Phase 1's.

**P34-F1 (confirmed, RECORDED not repaired — architect decision needed).** The ledger's `model=`
slot holds an Agent-tool alias (`haiku|sonnet|opus|fable`), and `tier_for` maps anything else to
itself, which then falls outside `LIVE_TIER_ORDER` and is skipped. All three drivers write the
concrete PRICING model id. Confirmed directly:

    tier_for('claude-opus-4.8') -> outside ladder -> skipped
    tier_for('gpt-5.6-luna')    -> outside ladder -> skipped
    tier_for('cheap'/'mid'/'strong') -> outside ladder -> skipped

So every outcome line any driver writes contributes nothing to the per-tier track record, while
the Escalation lineage section groups the same line correctly — Phase 1's F2 invariant again,
from the writer side. For Copilot and Codex this is not a typo but a vocabulary gap: their tier
names have no home in a Claude-only ladder, so D1's "one grammar propagates everywhere" is only
true for the Claude harness today.

Adjudicated as a PLAN-level gap, recorded as `defect: - kind=stale-plan-decision` and NOT
repaired in this kit, for two reasons. First, PLAN's own "Done looks like" is satisfied —
drivers emit `run=`/`parent=` and `--history` groups escalations under their parents, both
verified. Second, any real repair (extend the ladder vocabulary, or add a `tier=` field) is a
grammar change travelling in threes with T2's byte-stability goldens already set; doing that
mid-kit is precisely how the F1 contradiction of Phase 1 happened. What IS fixed here is the
honesty: the skip note reads as though the whole outcome was discarded when only tier
attribution was.

**Consequence T11 must respect:** D11's escalation-rate baseline is computed from history that is
structurally empty for driver-executed kits. T11 must print its honest insufficient-history line
rather than a confident zero. An alarm that reads "no escalations" because it cannot see any is
worse than one that says it has no data.

**P34-F2 (confirmed, FIXED).** All three drivers pass `parent` unconditionally into `append_note`,
so a BLOCKED consult gets `parent=`, which the scorecard rejects as out of grammar — while all
three help texts promise `parent=` is added "on success". The drivers contradict their own
documentation, and their own docstrings state the very principle this breaks. Both new test
suites exercised `--parent` only on a passing run: the F-D lesson recurring — verified against
the writer's assumptions, never against the reader. This is the FOURTH instance this run of
"passes every existing test while being wrong".

Sub-finding, adjudicated with it: the grammar triple disagrees. Both SKILL.md files say `parent=`
is set on "escalation/consult" outcomes; the scorecard enforces `result == escalated-pass`. A
blocked consult is in-grammar by the skills and out-of-grammar by the code. Resolved toward the
CODE (escalation results only), because that is what the reader actually enforces and what T2's
tests pin; the skills' wording is the thing that will be corrected if this is ever widened.
Related to the already-recorded `retry-pass`/`failure=` placement gap — same family, both for
the architect.

**P34-F3 (confirmed, FIXED).** `bin/copilot_execute.py:31` still asserts the driver does not import
`copilot_pricing` while line 559 calls `est_cost`. T8 was authorized to correct exactly this
sentence in the file IT was editing; the identical authorization applied to T7 and was not
given. The repo shipped a docstring in one driver calling its neighbour's docstring false while
the false one stood. Nothing tests a docstring.

**P34-F5 — the orchestrator's own sequencing error, already resolved.** The reviewer reported T8's
status still `in-progress` with no ledger lines. It was right about the tree it read: the phase
reviewer was dispatched CONCURRENTLY with T8's verifier, so it snapshotted before T8's
bookkeeping was closed. The lesson is the mirror of the one this run has been careful about all
along — do not review a phase before the phase is closed, not merely "do not dispatch work
during a review". Concurrency between a verifier and a phase reviewer is not free just because
neither writes.

**P34-F6 — a correction to this file's own earlier reasoning.** The Phase 2 entry claimed "T7 and T8
carry identical acceptance bullets" to T5. They do not: T5's bullet is the unsatisfiable POSITIVE
("escalation outcomes carry `parent=`"); T7's and T8's are the satisfiable NEGATIVE ("`parent=`
only on escalations"). Recording the defect once, under T5, is therefore correct — but because
T7's and T8's briefs are not defective, NOT because one root cause earns one line. The reason
matters: as originally written it would teach a future executor to under-record genuinely
repeated defects, which is exactly the distortion the recurrence signal cannot survive.

Carried as notes: convergence is 2-of-3 at DISPATCH (`claude_execute` stamps ids in the ledger
but not into the dispatch prompt — T5's brief asked only for the ledger, T7's and T8's asked for
the preamble, an architect-side brief inconsistency); `parse_frontmatter`'s `#`-skip is now
exercised by nothing since the shipped pins use HTML comments below the fence (keep it as
YAML-correctness hardening, but say so); D4's tool pins are asymmetric across harnesses
(Copilot verifier lacks `search` where the Claude template grants it — both implementers followed
their briefs, so architect-side, and `execute` provides grep anyway); and the suite still leaks
`recorded pass marker for T2` to stdout from Phase 2 test hygiene.

## `git diff` cannot attribute work to a task in an uncommitted kit run — brief your verifiers

T7's verifier reported a scope violation: that T7 had edited `skills/execute/SKILL.md`,
`skills/architect/SKILL.md`, and `bin/routing_scorecard.py` outside its remit. The finding was
rejected — `findings=1 confirmed=0 result=revised`, the run's first overturned verdict.

The cause is structural, not carelessness. This kit correctly never commits mid-run, so HEAD
stays at the pre-kit commit and `git diff` shows the UNION of every task's changes — 13 files
by T7's turn. A verifier handed "check T7's scope" and reaching for `git diff` sees T1's spec,
T2's parser, and T3's pins sitting in the tree and attributes all of it to the task in front of
it. The changes it flagged were verified by the orchestrator at T1's, T2's and T3's own
completion times, hours earlier in the run.

Two things follow, both worth carrying into future kits:

- **A verifier brief must state that the working tree contains every prior task's changes**, and
  that per-task attribution is not available from git. The orchestrator's own task-completion
  records are the only attribution channel in a no-commit run.
- **Give the verifier the file list the task was authorized to touch** when scope is part of what
  it should check. "Confirm only these two files changed" is checkable; "confirm the task stayed
  in scope" invites the git-diff mistake.

Worth noting the verifier was right to look, and its other eight checks were sound and useful —
the failure was an unavailable baseline, not a lack of rigour. A verifier that never questions
scope is worse than one that questions it wrongly.

## PLAN D5's pricing-import precedent is stale (kit-level defect)

D5 ends by saying the design "preserves the standing precedent that the drivers never import
`copilot_pricing`". That precedent no longer holds, and had already stopped holding before this
kit was drafted. `bin/copilot_execute.py:559` calls `_load_pricing_module()` and uses
`est_cost(...)` — budget mode needed cost math, added the loader, and left the older prose
behind. Two docstrings still assert the dead fact:

- `bin/copilot_execute.py:31` claims the driver does not import `copilot_pricing`, contradicted
  by line 559 of the same file.
- `bin/codex_execute.py:39` claims it does not import `codex_pricing` "mirroring how
  `copilot_execute` does not import `copilot_pricing`" — the codex half is TRUE (verified: it
  uses a plain `json.load`), but the copilot half it appeals to is false, so a true statement
  now rests on a false premise.

Recorded as `defect: - kind=stale-plan-decision` (kit-level task token `-`, reusing an existing
kind). Discovered by the orchestrator checking a fence rather than by any task failing — the
kind of drift nothing tests, because no test asserts a docstring.

Scoped fix: T8 edits `bin/codex_execute.py`, so it corrects the false mirror clause in the file
it is already touching. That is a factual correction to a sentence in its own file, explicitly
authorized here, NOT the "improve the sibling in passing" that GUARDRAILS forbids. The
`copilot_execute.py:31` line and PLAN D5's own sentence are left alone: PLAN.md is the
architect's artifact and this ledger is the channel for telling the architect it drifted.

## Phase 2 review — adjudication

Six findings, all six confirmed. The reviewer verified every factual claim by running it, and
the orchestrator independently re-confirmed the two most consequential before ordering fixes.

- **F-A** — `bin/claude_execute.py` discarded `record`'s refusal AND `precheck`'s result, so a
  task whose verify command could never fail wrote `result=pass review=none` with no marker:
  in the ledger, indistinguishable from a genuine red→green first-try pass. The harm is not
  the `done` write, it is the dishonest evidence line, because NOTES.md is what the scorecard
  and the next architect read. Fix: record `defect: <task-id> kind=tautological-verify`
  in-grammar, refusal to stderr, nonzero exit — and deliberately do NOT block the `done`
  write, because blocking would strand a possibly-fine task and let an analysis signal change
  routing state, the shape PLAN D11 forbids.
- **F-B** — the hook's own defect line was UNPARSEABLE. It printed
  `defect: tautological-verify task=<id>` where the grammar is `defect: <id> kind=<token>`.
  Confirmed directly: the emitted line returns `unrecognized defect line` from
  `parse_defects`, the correct form parses. A line that looks like ledger data, sits in a
  machine-read family, and is silently dropped — the exact failure the backtick rule guards
  against, arriving from the writer side instead of from prose.
- **F-C** — T3 shipped the wrong one of two candidate wordings for F5 and inverted an
  inference. The architect doc said the failure breakdown keys on "the tier the FAILING task
  was pinned to"; the code keys on the IMPLEMENTER's dispatch tier, deliberately not the raw
  pin. An architect following that sentence mis-attributes every failure where an escalation
  or re-route moved the model — precisely the case D9 exists to reason about. Worth noting
  that T3's own verifier checked the section NAMES matched the code and passed it; a matching
  heading with wrong semantics is the harder defect and needs the code read, not grepped.
- **F-D — the most important finding of the run.** T4's command-match enforcement parses only
  the `- Verify: \`cmd\`` dialect. The orchestrator counted the repo: 2 of 27 kits use it, and
  those two are `graph-convergence` and `evidence-loop` — the pair drafted today. The other 25
  use `**Verify:**` plus a fenced block. So the headline half of T4's retry fix, the part that
  closes "verify command rewritten after the marker was earned", is INERT on every kit this
  repo has ever executed. It passed two verifications and a phase review before anyone asked
  whether real kits match the format it parses. The lesson is not about dialects: a fix
  verified only against fixtures written in the fix's own assumed format will always pass.
- **F-E** — `--parent` had no self-reference guard, so `--parent W1` on task `W1` wrote
  `parent=W1`, which the scorecard drops with a note while the `escalated-pass` it caused
  still counts in the tier stats. That is Phase 1's F2 invariant — no line simultaneously
  counted and reported as ignored — reintroduced from the writer side.
- **F-F** — T5's acceptance bullet "escalation outcomes carry `parent=`" is unsatisfiable by
  any of the three drivers: their ladders escalate WITHIN one task id, so there is no second
  id to name. T5 solved it by inventing `--parent`, but recorded no brief defect. Recorded now
  as `defect: T5 kind=underivable-requirement` — SUPERSEDED, see "LEDGER CORRECTION" below; the
  kind was wrong and the line now reads `contradictory-acceptance` — reusing T4's kind rather than coining, which
  is the point of having coined it deliberately. T7 and T8 carry identical acceptance bullets,
  so without this line the architect would re-issue the same defect twice more.

Judged clean by the reviewer and worth keeping: D4's guidance is coherent (the pin and the
practice do different jobs and the skill says which); the consent flow is a structural clone
of the statusline step with confirmation and merge-not-replace; all three of T5's sibling
divergences are justified (the kit-dir difference is docstring prose only — `--kit` is
required in all three drivers); D8 is clean on the generator side; D6's goldens verified
byte-stable again at 1225 and 2100 bytes.

Carried forward, not fixed: `--dry-run` previews pending tasks without a dependency filter, so
it can show dispatches the real `run` would refuse; the setup skill's frontmatter description
still advertises only the statusline, so "install the kit verify hook" will not route there; a
docstring at `bin/claude_execute.py:85-86` claims an injected `verify_runner` where `cmd_run`
hardwires the default; and a task with no parsable verify reaches
`subprocess.run(None, shell=True)` and raises outside `main()`'s caught set — pre-dispatch, so
no money is spent, and `bin/codex_execute.py` has the same hole post-dispatch.

## Grammar gap found by dogfooding: a `retry-pass` cannot record its failure class

Writing T4's own ledger line exposed a hole in the grammar this kit just built. T4 failed its
first verification for a textbook `verification`-class reason — work was reported done that
was not — then passed on retry. But F4's adjudicated rule restricts `failure=` to `blocked`
and escalated outcomes, so a `retry-pass` has nowhere to record WHY it needed the retry. The
orchestrator wrote `failure=verification` on T4's line, then removed it: keeping it would have
written an out-of-grammar placement into the kit's own ledger, which the scorecard now
correctly drops with a note.

The cost is real. Every retry that a verifier catches is precisely the evidence D9 exists to
collect — "a tier failing on `verification` argues for a stronger verifier pin" — and the
retry case is the most common form of that failure, yet it is exactly the case the grammar
cannot express. As written, D9's evidence base is limited to failures severe enough to block.

Deliberately NOT fixed here: widening the placement rule is a grammar change, and a grammar
change travels in threes across two skills and the scorecard (GUARDRAILS). Doing it mid-kit,
after T2's byte-stability goldens are set and with three drivers in Phases 3-5 about to
implement the current rule, is how the F1 contradiction happened in the first place. Recorded
for the architect: either widen `failure=` to any non-`pass` result, or state in the spec that
retry-level failure classes live in NOTES prose by design. This is the kit's own evidence
about its own contract — the best kind.

## T4 — the brief defect was real, but it was used to justify too much

The verifier caught the important thing here, and the shape of the error is worth keeping.
T4's first attempt reasoned: the brief wants a marker newer than the `in-progress` flip →
TASKS.md carries no per-status timestamp → the comparison is underivable → therefore check
only that a marker EXISTS. The first two steps are correct (and the brief defect below is
genuine). The conclusion is not: existence-only lets a marker from an earlier run certify any
later `done` flip, and lets a verify command be rewritten after its marker was earned. The
enforcement's entire purpose is defeated by a marker that never expires. Tell-tale left in
the code: `read_marker_time()` was defined and never called — an unused function whose name
is exactly the missing check, which reads to the next maintainer as though the check exists.

**A true premise about a format limitation was carried into a false conclusion about what is
achievable.** Freshness did not need a status timestamp; it needed an attempt boundary, and
the kit workflow already has one. `precheck` is the analogue of the `in-progress` flip, so
making `precheck` invalidate any prior marker makes "a marker exists" mean "record ran after
the most recent precheck" — the property the brief asked for, derived from what the format
does carry. Pairing the marker with the verify command it certified closes the second path,
which no ordering rule can catch.

Generalizable: when a brief turns out to be underivable as literally written, record the
defect (below) and then ask what the requirement was FOR, not just what it said. The
underivable literal reading is a reason to find another derivation, not a licence to ship the
weakest thing that passes.

## T4 — brief defect, and why a new kind was coined

T4's brief requires the hook to block a `done` flip "unless a marker newer than the task's
`in-progress` flip exists". The kit TASKS.md grammar carries no per-status timestamp, so that
comparison is not derivable from the format the brief itself pins — the requirement cannot be
implemented as written without inventing a fourth subcommand outside the sanctioned three.
Recorded as a brief defect against the architect, per the rule that the executor logs these
even when the fix is easy.

None of the six existing kinds fits, so a new one was coined rather than stretched. It is
worth stating the reasoning, because a coined synonym aggregates with nothing and the kinds
are read for RECURRENCE: `missing-helper` is the nearest neighbour (a brief depending on
something that does not exist), but it names an uncreated helper — an architect reading a
recurrence of it would go looking for a function or script that no task creates, not for a
requirement that reads data the pinned format never carries. Those are different failure
modes and different fixes. The new kind is `underivable-requirement`: the brief demands a
comparison against data the format it pins does not record. Reuse it if it recurs; do not
coin a third synonym.

## Phase 1 learnings

- **D6 was proved twice, once by accident.** Before T2 landed, the unmodified engine read
  T1's outcome line carrying a `run=` field it had never heard of and scored it correctly
  (`opus: first-try 1/1`) — forward-compat demonstrated on real ledger data, not just
  asserted in a spec. After T2, the orchestrator diffed the pre-T2 engine (extracted from
  git HEAD) against the post-T2 engine: `--demo` and `--demo --history` are byte-identical,
  1225 and 2100 bytes. The goldens in the test file are the same strings, asserted against
  real subprocess stdout.
- **Extracting the engine to a temp dir does not work** — it sibling-imports
  `copilot_execute` from its own directory, so a copy outside `bin/` dies on import before
  printing anything. Run the extracted copy from inside `bin/` under a temp name and delete
  it. A future task re-checking byte-stability should not read the resulting traceback as a
  regression; it is a harness error.
- **The goldens are escaped single-line strings**, not triple-quoted blocks. Grep for
  `GOLDEN` when looking for them; a triple-quote regex finds nothing and looks like absence.
- `build_history` grew `expensive_tiers=None` as a trailing optional keyword because
  `bin/bench_routing.py` and two test modules call it positionally. The positional signature
  is effectively frozen by those callers — later tasks must extend it the same way.
