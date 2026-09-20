# NOTES — decision-improvement-v1

Execute-owned. Outcome/agent/defect/reviewer lines below are machine-read by
`bin/routing_scorecard.py`; prose quoting that grammar backticks the tokens.

## Run 2026-09-16-aa6e

Pre-flight, before D01. The branch was reconciled onto `origin/main`, which had advanced six
commits past the kit's `aab7553` baseline, by a `--no-ff` merge (`e6cf4bd`) — not a rebase, so
no existing commit was rewritten. Uncommitted planning work was committed first (`4ba7560`),
nothing discarded. Baseline suite on the merged tree: 4214 tests, 1 failure, 2 skipped.

Two blockers were cleared by the orchestrator, both outside any task's scope, both recorded as
`defect:` lines below:

- **BL3, the docs census.** D01's brief and its verify command both mandate a new `docs/*.md`,
  and this repo pins the docs-file count in six test assertions. `HANDOFF.md` entry 14 documents
  the maintenance exactly: move all six in one edit, dated, naming the file that moved them.
  Applied: 29/31/73 -> 30/32/74, "one more doc" targets -> 31/33/75, across
  `tests/test_docs_build_adversarial.py`, `tests/test_docs_build_cli.py` and
  `tests/test_primitives_doc_adversarial.py`, with `HANDOFF.md` entry 28 recording it. The
  tripwires are re-armed at the new counts, never disabled. This is a brief defect because the
  task's acceptance says "no code changes" while its mandated deliverable forces this edit.
  D03 then added a second `docs/*.md` and the pins moved again, 30/32/74 -> 31/33/75 with the
  "one more" targets at 32/34/76 (`HANDOFF.md` entry 29, which also records that
  `docs_build build` does NOT update `mkdocs.yml` — its nav is hand-maintained and a new
  deep-dive page needs a nav line or `test_docs_site.NavCoverageTests` fails as a seventh
  failure beyond the six pins).
- **BL1, inherited from `origin/main`.** `test_lessons_promote` hardcoded
  `REPO_ROOT/journal/promotions`, but `bin/lessons_promote.py:93` resolves that store through
  `runtime_data`, which returns the in-tree path only when it exists and has content. A fresh
  worktree has none, so the test asserted a checkout shape the product does not promise. Fixed
  by resolving the expected dir through the product's own `runtime_data.store_path` with
  `POLYTROPOS_DATA_HOME` pinned to a temp dir — the seam `tests/test_attempt_ledger.py` already
  uses, so the test can never reach a real store. Mutation-proven: with `DEFAULT_OUTPUT_DIR`
  mutated the test fails; restored, it passes, and `bin/lessons_promote.py` is byte-identical to
  HEAD. The empty-fixture workaround was deliberately NOT re-applied: it hides the defect and
  writes into a real store.

Suite after both: 4214 tests, 0 failures, 2 skipped. All five drift gates exit 0. That green
baseline did not exist at the start of this run.

### D01 — Reconcile and ADR

Verified twice by the orchestrator (exit 0 both times) plus an independent verifier. The
verifier returned FAIL/revise with three real findings, all confirmed against the tree before
acting: a "traced" import list naming `bin/kit_contract.py`, which only mentions
`routing_policy` in a prose comment at line 831; an ADR headline of "eight implemented, two
partial" contradicting its own JSON's 7/3; and an off-by-one line citation. A fourth correction
was orchestrator-supplied — BL1 had been repaired after hand-off, so the document's "the full
suite's single failure" claim had gone stale.

On the revision the implementer corrected the ORCHESTRATOR in turn, and was right:
`bin/codex_execute.py` is not a direct loader either (its line 228 is also a prose comment).
Re-derived independently: three direct loaders — `bin/codex_policy.py:279`,
`bin/workflow_eval.py:197`, `bin/release_gate.py:143` (CONTRACT_VERSION only) — with
`codex_execute` reaching routing transitively via `codex_policy` (line 218), and
`bin/claude_execute.py` and `bin/copilot_execute.py` reaching it by neither path: zero
occurrences of `routing_policy`, `codex_policy` or `_sibling` in either. Only the Codex driver
dispatches under a routing decision. That is load-bearing for D13 and for F3's arm design.

Carry-forward for later tasks:
- **D05**: no duration fix has landed anywhere, so there is nothing to deduplicate.
- **D16/D17**: `bin/graph_ground.py` is loaded by `bin/release_gate.py` alone (lines 144-145,
  633); no driver calls it and no `--grounding` flag exists. The seam D16 needs must be built,
  not assumed present.
- **D20/D23**: `prefs/routing-policy.json` is read only by `bin/workflow_eval.py`. Pull-only
  holds at this HEAD.
- **D24/D28**: `concurrent_dispatch` is `verified: supported` for the STUB dispatcher only;
  `bin/kit_scheduler.py` defines exactly two dispatchers (`StubDispatcher` 375,
  `CursorDispatcher` 399). No live model has ever run in parallel — step 24 is `unverified`.
- **Cursor, never downgrade**: six cursor rows moved `unknown` -> `verified: supported` at this
  HEAD (baseline had all 19 unknown). D28/D29 must not relabel them.
- **`SECURITY.md` is stale in three places** (lines 183, 219, 283) and D01 correctly did not
  edit it, since it is not D01's file. Its owner should reconcile: 183 and 283 are falsified by
  `8d1b7be`, and 219's CLI clause by `fd80734`. IDE and cloud Cursor modes genuinely remain
  unrun, as do escalation and dead-run resume.
- **Routing vocabulary — CORRECTED by the phase 1 review; the earlier note here was wrong.**
  An unknown `routing:` word does NOT drift silently: `codex_execute.py:1401-1405` checks
  `policy` and `preference` against `POLICIES`/`PREFERENCES` bound from `routing_policy`
  (`codex_execute.py:232-233`) and `sys.exit(2)`s before anything dispatches. The comment at
  `kit_contract.py:919-920` says exactly that, and the earlier note cited its existence without
  reading it — the same defect this file warns about below. The REAL hazard is different and
  narrower: `kit_contract.parse_plan_routing` silently IGNORES an unrecognised token, so a
  fourth routing dimension added to `routing_policy` would be dropped without a word.

outcome: D01 model=opus attempts=2 result=retry-pass review=revised run=2026-09-16-aa6e
agent: D01 id=a4a14bf role=implementer model=opus
agent: D01 id=ab236ea role=verifier model=sonnet findings=3 confirmed=3 result=revised
defect: D01 kind=contradictory-acceptance

### D02 — Legacy goldens

`tests/test_decision_legacy.py:LegacyDecisionGoldenTests`, 25 tests, verify exit 0, zero edits
under `bin/`. Regression evidence by design: this task pins EXISTING behavior, which the kit
PLAN sanctions ("reconciliation and release-only checks may explicitly use regression
evidence"). Before the task the module did not exist, so the verify command could still fail.

The verifier mutation-tested rather than re-running, which is the only way a golden earns
trust: 6/6 plausible product mutations tripped their golden, 4 of them driver-behavior tests.
Confirmed not hollow.

Two frozen asymmetries that constrain later tasks:
- **Codex escalates on unknown-class dispatch failures; Claude, Copilot and Cursor stop on ANY
  dispatch failure.** D18's arm A is "the actual frozen current recovery policy" — and that
  policy is NOT uniform across harnesses. An arm A defined once, harness-agnostically, would be
  fiction. D16/D17/D18 must treat this as four behaviors, not one.
- **Codex's `run_task` RAISES `_BudgetRefused` where the other three return a `budget_stop`
  dict** (`codex_execute.py:533` vs `kit_contract._budget_stop`). Safe today because
  `codex_execute.cmd_run` is the only caller and catches it; a direct caller would crash where
  the other three degrade to `blocked`. Pinned as-is, not fixed — D04 and D05 touch these call
  sites and must not silently "harmonize" it without saying so.

### D03 — Authority inventory

`docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md`, verify exit 0, zero edits under `bin/`,
`tests/`, `data/`, `primitives/`. A 17-row owner table with callers listed separately and never
as owners.

Carry-forward that later tasks depend on:
- **D05 has FOUR boundaries, not one — CORRECTED by the phase 1 review.** An earlier note here
  said "one function"; that was a lossy compression of D03's inventory, which is the accurate
  source. Cite symbols, not the line numbers below, which have already moved once:
  1. `kit_contract.provider_runner`'s `default_runner` returns `(rc, output)` and discards
     `proc_runner`'s `duration_s`/`outcome`/`timed_out`. Bound by `claude_execute.py:544` and
     `copilot_execute.py:244`.
  2. **`codex_execute.default_runner` has its OWN runner** — it calls `pr.run(...)` and returns
     `result["rc"], output, telemetry`, discarding `duration_s` in the same function that
     measured it. Widening `provider_runner` alone does NOT reach Codex.
  3. `cursor_execute.default_runner` returns the whole result dict and `run_task` drops it,
     passing only `proc_outcome` — a pure call-site omission, the cheapest of the four.
  4. **`attempt_history` has no duration field at all** — `RECORD_FIELDS` has no slot and
     `observe` raises `KeyError` on an unknown key, so even a recorded duration cannot reach a
     report. D05's acceptance ("report separates latency/wall") depends on closing this one.
  Two traps a naive "just widen `default_runner`" fix hits immediately: `kit_contract.
  dispatch_status` unpacks `rc, output = value` (a 3-tuple raises `ValueError`), and
  `claude_execute.py:1144` / `copilot_execute.py:1461` each unpack `rc, output =
  default_runner(argv)` directly.
- **`bin/proc_runner.py` is already correct** — it emits `duration_s`, `outcome`, `terminal` and
  `timed_out`. D05's brief says "change only `bin/proc_runner.py` result plumbing"; that aims at
  the wrong file. The consumers are what drop the values.
- **"null everywhere" is loose.** `workflow_eval.py:850`/`:859` and `copilot_ralph.py:383` each
  DO pass a `duration_s` from their own clock. It is the four native drivers that drop it.
- A third zero-coercion beyond the two named above: `workflow_eval.py:1016` is a SECOND
  `"wall_seconds": 0.0` seed, on the implement stage.
- **D04's seam is narrower than it looks.** `AttemptLedger.record_started` takes `**extra` but
  `TaskRun.attempt_started` (~1854) does not forward it, and `record_projected` (~372) has no
  `**extra` at all. Both are serial shared-module edits.
- **`attempt_history.observe()` raises `KeyError` on an unknown key**, so a ledger field not
  added to `RECORD_FIELDS` cannot be projected at all. Its `unknown` counter covers only
  `harness`, `tier`, `observed_model`, `cost` — a new ref's absence would be invisible rather
  than disclosed, which is the opposite of this repo's honesty rule.
- **The `LEDGER_VERSION` trap, the most consequential constraint in this kit.**
  `AttemptLedger.events()` skips and counts as corrupt every line whose `v` != `LEDGER_VERSION`.
  Bumping it for additive fields would silently make every historical event in every user's
  store unreadable. Additive optional fields therefore KEEP `polytropos.attempts/1`; a genuinely
  new version belongs on the referenced object's contract and in `release_gate.VERSION_SOURCES`.
  Read-time only, no backfill.
- **Two zero-coercions D05 must not preserve**: `copilot_ralph._prior_state` sums
  `float(fin.get("cost_usd") or 0.0)` at line 226 and
  `float(fin.get("duration_s") or 0.0)` at line 227, and `workflow_eval` accumulates
  `wall_seconds` from a field initialized to `0.0` rather than `None` (899, 931, 943, 1170).
  Both turn "unknown" into "zero". (An earlier version of this note put `duration_s` on 226 and
  said cost was the line above; it is the line below. Corrected from D03's verification.)
- **A routing decision has no id, no hash and no durable home.** Its only durable trace anywhere
  is `rp.explain(decision)` — the RENDERED PROSE (`routing_policy.explain`, line 472, returns a
  joined string, not a dict) — in the eval trial record. D11/D13 cannot assume a decision
  identity exists to reference.
- **The event `kind` vocabulary is undeclared and has 26 members**, enumerated by AST walk over
  every `append`/`_record` call in `bin/`. Nothing registers a kind and nothing fails if two
  callers pick the same word. A task adding a kind adds it to no registry.
- **`HISTORY_VERSION` is a stamp with no reader** — unlike `LEDGER_VERSION`, `EVAL_VERSION` and
  `PROPOSAL_VERSION`, nothing gates a read on it, so it carries no migration hazard. Do not
  reason about it as though it does.

Method note that later tasks should copy. Three separate false claims in this phase came from
citing a grep hit without reading the line: D01's import list (two of five "hits" were prose
comments), D01's `duration_ms` claim (withdrawn — the only `duration_ms` in the tree is
Copilot's statusline), and D03's reversed `copilot_ralph` citation. D03's revision replaced
grep with an AST walk and immediately found three MORE missing event kinds
(`roster.checked`, `scheduler.cancelled`, `security.violation`) whose literals sit on the line
after `append(` and are invisible to the obvious grep. Cite from `cat -n`, or derive
structurally; never from a grep offset.

outcome: D02 model=sonnet attempts=1 result=pass review=clean run=2026-09-16-aa6e
agent: D02 id=a5372c8 role=implementer model=sonnet
agent: D02 id=af513de role=verifier model=sonnet findings=0 confirmed=0 result=accepted

outcome: D03 model=opus attempts=2 result=retry-pass review=revised run=2026-09-16-aa6e
agent: D03 id=a3f1cd5 role=implementer model=opus
agent: D03 id=a1de6a2 role=verifier model=sonnet findings=3 confirmed=3 result=revised
defect: D03 kind=unspecified-path

### D04 — Attempt provenance

Four optional refs (`acceptance_ref`, `policy_ref`, `decision_ref`, `admission_ref`) on
`attempt.started`, plus `acceptance_ref` on `task.projected`. Six files: `attempt_ledger`,
`attempt_history`, `kit_contract`, and ONE line each in three drivers
(`lifecycle.bind_admission(admission)` at `claude_execute.py:958`, `codex_execute.py:1507`,
`copilot_execute.py:1135`); Cursor gets it through the shared `budget_gate`
(`kit_contract.py:1783`). 26 tests. Verify exit 0, suite 4265/0/2, all gates 0.

**The LEDGER_VERSION trap was avoided, and the mechanism is worth reusing.** The constant stays
`polytropos.attempts/1` — the diff adds only comment lines near it. What makes that safe is
`validated_refs` OMITTING a `None` ref rather than writing an explicit null, so a line written
today without provenance is BYTE-IDENTICAL to one written before the feature existed. Nothing
ever has to distinguish "written without one" from "written before there were any". The verifier
confirmed this by writing an event both ways and diffing the bytes, and confirmed read-time-only
behavior with its own hand-seeded pre-D04 stream (not the implementer's fixture): bytes unchanged
after `events`/`task_history`/`usage`/`unprojected`, all four refs reading `None`.

A ref is `{"id", "sha", "v"}` where `v` is the REFERENCED contract's version, never the ledger's.
Acceptance and admission refs carry `kit_contract.CONTRACT_VERSION`, which already has a
`release_gate.VERSION_SOURCES` row — **no new version constant, so `docs/RELEASE.md` needed no
regeneration.** Later tasks adding a ref should follow that: version the referenced object, never
the envelope.

Carry-forward:
- **`policy_ref` and `decision_ref` have NO producer** and every attempt records them unknown,
  because D09's decision contract and D11's bundle contract do not exist. The seam accepts one
  when they arrive. D04 deliberately did NOT wire `prefs/routing-policy.json` as a policy ref —
  GUARDRAILS forbids a preference file silently becoming a bundle, and that is exactly how it
  would have begun. D11/D13 must supply a real bundle identity, not reuse the prefs file.
- **`ref_for` consumes its grant: one grant funds one operation.** No path today admits once and
  dispatches twice — the verifier traced every `admit`/`attempt_started` pairing in all four
  drivers. A future caller that does will get `None`, which is the honest answer rather than a
  fabricated correlation. Do not "fix" that into reuse.
- **Four `BudgetAdmission` builders remain unbound**: `kit_scheduler.py:524` and `:627`,
  `workflow_eval.py:1013`, `copilot_ralph.py:314`. Their attempts read admission unknown. Each is
  a one-line `bind_admission` when a later task needs it. D18/D20 touch `workflow_eval` and may.
- **`record_role_dispatch` (`kit_contract.py:2097`) attaches no refs** — review and acceptance
  dispatches have no `TaskRun` and no admission. Pre-existing since step 17, left alone on
  purpose: the brief says preserve review overhead, not re-scope it.
- **The acceptance ref's `id` is content-derived (`sha[:16]`)** unlike run/attempt/grant ids,
  which stay content-free. Safe only because no ref reaches a committed surface — independently
  traced: `build_outcome_line` has no ref parameter, `append_run_note` builds from `result` keys
  none of which is a ref name, and zero hits for the four names in any driver's `append_note`.
  **If a later task ever puts a ref on a NOTES.md line, that rule breaks.**

outcome: D04 model=opus attempts=1 result=pass review=clean run=2026-09-16-aa6e
agent: D04 id=a5bc6b8 role=implementer model=opus
agent: D04 id=a88799a role=verifier model=sonnet findings=0 confirmed=0 result=accepted

## Phase 1 review

Verdict: accepted with findings. No `done` status reversed; no architecture drift, no authority
duplication, no downgrade of completed work. Extension boundaries clean — no new module under
`bin/`, `runtime_data.STORES` untouched, `primitives/harness-capabilities.json` not in the phase
diff at all, so the six Cursor rows could not have been downgraded. The reviewer independently
mutation-proved both load-bearing guards (bumping `LEDGER_VERSION` → 3 failures; dropping a name
from `PROVENANCE_FIELDS` → 1 failure + 1 error).

It also adjudicated the two pieces of maintenance the ORCHESTRATOR did outside any task, which
the orchestrator should not certify itself:
- **Census pins re-armed, not weakened.** All six assertions are still `assertEqual`; adding one
  `docs/*.md` to a temp copy fails 5 of 7 census tests. Both bumps recorded in `HANDOFF.md`
  entries 28 and 29 per entry 14's precedent.
- **The `test_lessons_promote` repair made the guard STRICTLY STRONGER.** Three product
  mutations trip it, including `_store_default("journal")` → `PLUGIN_ROOT / "journal"` — writing
  inside the tree, an invariant violation that the OLD assertion would have PASSED. The repair
  also stops the test reaching the user's real journal store, which the old version could.

Four findings were corrected before Phase 2 dispatch; all were prose, no code:
1. **The routing-drift claim was FALSE** and stood in three places (both D01 documents and this
   file). `codex_execute.py:1401-1405` validates `policy`/`preference` against `POLICIES`/
   `PREFERENCES` and exits 2 before dispatch. The document cited a `kit_contract` comment as
   evidence whose own text says exactly that — cited for its existence, not read. FOURTH
   instance of this kit's recurring defect, and the first one the orchestrator committed itself.
2. **Two plan documents still said BL1 "is the full suite's single failure"** in the present
   tense, after it had been repaired. Every task is handed those documents, so a Phase 2
   implementer would have read the false version first. Now past-tense with an explicit
   correction.
3. **The withdrawn `duration_ms` claim still stood in `REPO-ASSESSMENT.md`** — the one document
   D05 reads. Withdrawn there too. `HANDOFF.md:306` carries the same unqualified claim and is
   INHERITED, not this phase's: two tracked documents at this HEAD disagree, and HANDOFF's owner
   should reconcile.
4. **"D05's real target is one function" was wrong** — an orchestrator over-compression of D03's
   inventory, which correctly names four boundaries. Corrected above. This one mattered most: a
   D05 implementer acting on it would have widened `provider_runner`, watched Claude and Copilot
   start reporting duration, and shipped believing Codex was fixed when it was not.

Carried, not fixed: line-citation rot across the inventory (eight citations into files D04 later
modified are stale at HEAD — mitigated because the document stamps its revision, and the fix is
to cite symbols); `SECURITY.md:225` says IDE/cloud "remain `unsupported`" where the registry's
`verified` axis reads `unknown`; `cursor_adapter.py:283-285` still says the CLI "documents no
usage or cost output", which the live run falsified — inherited, belongs to that adapter's owner.

reviewer: P1 model=opus findings=10 confirmed=4 result=accepted
defect: D01 kind=stale-plan-decision

## Phase 2

### D05 — Duration coverage

17 tests, verify exit 0, suite 4282/0/2, all gates 0. D02's 25 goldens and D04's 26 provenance
tests pass UNMODIFIED (`git diff --stat` on both test files empty). `bin/proc_runner.py` and
`bin/attempt_ledger.py` byte-identical to HEAD — the brief's "change only `bin/proc_runner.py`"
instruction aimed at the wrong file and was correctly not followed literally.
`attempt_ledger.record_finished` already had a `duration_s` parameter with no caller filling it.

**A FIFTH boundary existed.** D05 checked the corrected four-boundary claim structurally instead
of trusting it, and found `kit_scheduler._work` dropping `duration_s` although
`StubDispatcher` (line 396) and `CursorDispatcher` (line 426) both already return the full
`proc_runner` result as their third element. One additive kwarg on an existing call. The lesson
generalizes: a corrected claim is still a claim, and this kit's corrections have themselves been
wrong twice. Verify counts structurally.

**The ranking change is a FIX, not a regression — the opposite of what it looked like.** Before
D05, an un-dispatched stage's `wall_seconds` was coerced to `0.0`, which made a variant that was
never timed sort FIRST in the tie-break — it read as the *fastest*. `_accrue_wall` leaves the
total `None` until something real accrues, and `build_card` sorts `None` as `float("inf")`, i.e.
last. Existing MEASURED data is unaffected: primary (`-rate`) and secondary
(`incorrect_acceptance`) keys are untouched and a measured total's value is identical to before.
The convention is already in use at `repo_bench.py:5186`; `workflow_eval.py:1253` now matches it.
`tests/test_workflow_eval.py` (52 tests, three of them ranking-specific) pass unmodified.

**`codex_execute.default_runner` merges into a COPY** — `dict(attest_runtime_model(...))` then
two keys added — so `attest_runtime_model`'s own pinned contract (`{}` or
`{"actual_model","provenance"}`) is provably unchanged and `test_codex_execute_policy.py`'s 34
tests pass unmodified. Mutation-proven load-bearing: reverting the merge yields
`KeyError: 'duration_s'`.

**`dispatch_status` now normalises 2-tuple, 3-tuple AND `None`**, returning `(rc, output, timing)`
with `timing={}` when unmeasured — so an older or external runner returning a 2-tuple still
works. All four call sites updated (`claude_execute.py:636,672`, `copilot_execute.py:716,766`),
plus the two direct-unpack sites (`claude_execute.py:1149`, `copilot_execute.py:1466`). An AST
scan for any other two-name unpack of a `*runner(...)` call found only `verify_runner` calls,
which are a structurally distinct `exec_policy` contract and untouched.

**Carry-forward — a D03 directive is only HALF met, recorded rather than resolved in a test
docstring.** D03's inventory says "two zero-coercions D05 must not preserve". The `workflow_eval`
half is fixed. The `copilot_ralph.py:226-227` half is NOT, and the deferral is technically sound
but leaves the directive open: those values feed real arithmetic and formatting —
`copilot_ralph.py:351` computes `prior["elapsed_s"] + (clock() - started_at) >= max_elapsed`, and
lines 318/337/457/458/466 format with `:.4f` — so a bare `None` would raise `TypeError` the
moment a `--max-elapsed-seconds` run resumes or a status line prints. Making them `None`-safe
restructures Ralph's stop-condition and runway logic, which is spend-limiting code and a
different task from "own attempt projection". D05 correctly did NOT write a test asserting the
coercions are right, because that would bless them. **Whoever takes this must treat it as
financial-safety code, not a formatting fix.**

**`DURATION_BASES` forward-declares three bases where only `process-wall` has a producer** —
the same idiom D04 used for `policy_ref`/`decision_ref`. `duration_totals()` never sums across
bases, and `summarize`'s `unknown["duration"]` counts an unmeasured duration rather than hiding
it. A never-measured duration reads `None` end-to-end, including through a crash-closed
`reconcile_open` attempt, which passes no `duration_s` at all.

Process note: D05 declined to claim a full-suite result it had not seen finish, and separately
caught its own collateral damage — a blanket `sed` fixing its citations also rewrote an unrelated
pre-existing `PLAN D5` line in `bin/codex_execute.py` belonging to a DIFFERENT kit, which it
found by diffing against HEAD before finalizing and restored. Verified: that token sequence is
identical to HEAD in all eight changed `bin/` files. `PLAN D<n>` is an ambiguous token across
kits — cite `decision-improvement D05`, never a bare `PLAN D5`.

outcome: D05 model=sonnet attempts=1 result=pass review=clean run=2026-09-16-aa6e
agent: D05 id=a592177 role=implementer model=sonnet
agent: D05 id=aecc920 role=verifier model=sonnet findings=1 confirmed=1 result=accepted
defect: D05 kind=contradictory-acceptance

### D06 — Immutable manifests

47 tests, verify exit 0, suite 4329/0/2, all gates 0. `bin/workflow_eval.py` +1097, one
`VERSION_SOURCES` row, one GENERATED line each in `docs/RELEASE.md` and its mirror (rebuild is
idempotent — proven by re-running both generators on a temp copy: "up to date", "written 0").
The four prior test modules pass BYTE-IDENTICAL to HEAD (52+17+25+26 = 120). 6/6 mutations
tripped, including emptying the enforcement disclaimer.

**THE PRODUCT FINDING — confirmed REAL by independent re-derivation, and it constrains D18/D19.**
`repo_bench.mine_issue_tasks` falls back to `statement = subject + body` with
`statement_source = "commit-message"` whenever `gh` was not used — and `use_gh` defaults to
FALSE everywhere (`--with-gh` is `action="store_true"`, off by default), while `--mode auto`
resolves to `issue-replay` in the ordinary case. So the default mining path builds a problem
statement that literally IS the fix commit message. D06's screen flags that as
`future-fix-message`, quarantine is contagious within a defect group, and the promotion
partition ends up EMPTY. **An evaluation run in the default mode yields ZERO held-out evidence.**
This was checked against the real pipeline, not a fixture: `test_workflow_eval._Case.plan()`
calls the real `build_plan(mode="issue-replay")` against a real temp git repo, and a full
`Evaluation.run()` over that pool asserts `partitions["promotion"] == 0`.
The screen is NOT over-aggressive — pools with `statement_source="issue"` fill every partition
cleanly, and `repo_bench` already self-labels this path "weaker than issue text". **D18 must not
plan a trial on default-mined tasks and call the result held-out. Either pass `--with-gh` or
state plainly that the cohort carries no held-out evidence.**

**D03's inventory was internally inconsistent, and D06 was right to deviate.** Its table row
assigned manifest refs to `EVAL_VERSION`; the same document two sections later states the rule
that contradicts it. `list_runs` gates envelope reads on `EVAL_VERSION`
(`workflow_eval.py:2445`), so stamping the manifest with it would force a future manifest-shape
change to either bump `EVAL_VERSION` — making every stored `results.json` unreadable, D04's
trap — or lie. D06 added `MANIFEST_VERSION` on the referenced object, per D04's precedent. The
table row is now corrected and the correction recorded in the document.

**Integrity vs tamper-evidence, which is the point of the task.** Move one audit variant into
development by hand and `verify_manifest` reports `digest` + `group-split`; recompute the digest
and `digest` goes quiet while **`group-split` still fires** and `require_held_out` still refuses.
`partition_for` is a pure function of the defect key and the allocation — never of the revision,
run, clock or mining order, because a reshuffle on a new commit would turn yesterday's audit
material into today's development material. Digest excludes `created_at`/`created_by`, so the
same pool built twice by two people is the same manifest; verified across four interpreters under
different `PYTHONHASHSEED` values, which a same-process assertion cannot see.

**Post-hoc cohort selection is refused on log POSITION, not a clock.** `select_cohort(items=[...])`
is refused outright; `declare_cohort` refuses once results exist; and the order check is
re-applied AT READ TIME, so a `cohort.declared` line appended out of band — even with a backdated
`at` timestamp claiming to precede the result — is still refused, citing positions. A clock can
be lied to; an append position cannot, short of rewriting the whole log, which the test says it
does not survive.

**`NOT_ENFORCEMENT_LABEL` rides INSIDE the digest** (`content.rules.enforcement` and
`content.labels`), so "a hash is not enforcement" cannot be stripped without changing the
manifest id. Nothing in D06 presumes D07 succeeds — D07 may legitimately conclude the profile is
`unavailable`.

Carry-forward:
- **The four-way allocator is only exercised on synthetic pools.** `Evaluation._record_manifest`
  hardcodes `allocation={self.partition: 1}` — the real evaluator puts the whole pool in ONE
  partition (`promotion` by default). Grouping logic does run on the genuine mined pool; it is
  the partition SPACE that is degenerate. Same disclosed-but-unbound shape as D04's four
  unbound `BudgetAdmission` builders. Whoever wires a persistent cross-run pool (D23/D33) owns
  it. The storage functions already take their root as an argument, so that is a different
  LOCATION, never a different writer.
- **`Evaluation` writes with `on_leak="quarantine"`, not `"reject"`** — by the time `run()`'s
  `finally` executes the tasks were already dispatched, so refusing would destroy the record
  rather than prevent the exposure. Judged sound: quarantined items are never members of any
  partition, `require_held_out` raises once quarantine empties the target, and the label is loud.
- **The screen cannot prove absence** — a paraphrase of the fix passes it, and a test
  deliberately demonstrates that so no reader treats an empty finding list as "clean". Same
  caveat `bin/redact.py` carries.
- **Manifests live in `<run_dir>/manifests/`, not the store root.** D06's first attempt put them
  at the root and broke `test_workflow_eval.py:988` (`iterdir()[0]`) nondeterministically, 1 in 6
  under load. Verified fixed: 18/18 clean runs. Anything later that adds a second entry at the
  evals-store root will reintroduce that flake.

outcome: D06 model=opus attempts=1 result=pass review=clean run=2026-09-16-aa6e
agent: D06 id=af52e46 role=implementer model=opus
agent: D06 id=ae5a126 role=verifier model=sonnet findings=2 confirmed=2 result=accepted
defect: D03 kind=contradictory-acceptance

### D07 — Protected profile sentinels

**This host CERTIFIES: `darwin-seatbelt`, 21/21 sentinels, 19 denied + 2 allowed.** That is the
honest outcome, not a hedge — and the task was explicitly allowed to answer `unavailable`.
38 tests, verify exit 0, suite 4367/0/2, all gates 0, `LEDGER_VERSION` unmoved, no census move.
Six prior test modules byte-identical (197 tests). 6/6 mutations tripped.

**What makes the certification trustworthy is the attribution, not the pass.** Every denial
requires TWO witnesses, both enforced by `certify_profile` rather than merely reported:
1. **A control leg** — the identical command against a fresh per-sentinel mirror tree with NO
   boundary, which must SUCCEED. If it does not, the sentinel is `inconclusive` and certifies
   nothing. This is not decoration: D07's first implementation shared one control tree, an
   earlier leg deleted a file a later leg needed, and two sentinels correctly came back
   `inconclusive` and BLOCKED certification. The mechanism caught its own bug first.
2. **A permission-class signal** (`EPERM`/`EACCES`/`operation-not-permitted`). `ENOENT` arrives
   as `ENOENT` and is explicitly NOT a denial — a live-path test drives a nonexistent file and
   asserts `inconclusive`. Adding `ENOENT` to `PERMISSION_SIGNALS` trips that test.

The verifier reproduced kernel refusals **outside the module entirely**, with hand-written
Seatbelt profiles: hidden-file read, controller write, loopback connect, and hardlink-into-
workspace all succeed unconfined and fail `EPERM` confined; and a confined process calling
`sandbox-exec` again gets `sandbox_apply: Operation not permitted` (exit 71). So
`sandbox-renest-escape` is a real mechanism, not a label.

**The 2 `allowed` legs are the positive control and are load-bearing.** Without them a suite
that passes because NOTHING can execute is indistinguishable from one that passes because the
boundary works.

**`trusted-host` is absent, not defended.** `ProtectedProfile.run`/`run_shell` have no `mode`
parameter, no `**kwargs`, no env override; `run()` hardcodes `mode="enforced"`. The only
`trusted-host` in the new code is the CONTROL leg, which by definition runs against the separate
control tree. `run_confined`'s own opt-out for ordinary verification is untouched and still
self-reports.

**"A worktree is not isolation" is now machine-enforced.** `ProtectedLayout` validates six
pairwise-disjoint realpaths and refuses a candidate workspace containing the controller/hidden/
accepted roots — **including when a root is a symlink into another**, which is the case a naive
`startswith` misses. `_real()` uses `os.path.realpath`. Removing the disjointness loop trips the
symlink-specific test.

**Skips cannot certify — reproduced.** With `detect_backend` patched to return `None` on a temp
copy: 38 tests OK, 7 skipped, exit 0 — while `certify_profile` returned `certified: False`,
`mode: None`, all 21 sentinels present by name with `outcome: "unavailable"`. A green suite on a
host with no boundary never reads as certified.

**What `certified: true` licenses, and what it does NOT.** It licenses OS-enforced separation of
the four confined roles from the controller's rules/labels/accepted-state and from each other's
workspaces, on THIS darwin/sandbox-exec host, for the 21 named operations only.
`SENTINEL_NOT_PROVEN` rides in every report and is accurate — independently confirmed:
- general filesystem confidentiality is NOT proven (reads stay broadly allowed outside `deny_read`);
- **`stat(2)` on a denied path still SUCCEEDS** — existence, size and mode leak;
- `mach-lookup` is allowed, so a system daemon could act on a confined process's behalf;
- **the model dispatch is not confined at all**;
- nothing is claimed about any other host.

Carry-forward:
- **NOTHING IS WIRED.** No driver, `repo_bench` or `workflow_eval` call reaches
  `ProtectedProfile` — grep across the repo finds it only in `exec_policy.py` and its own test.
  This is an AVAILABLE boundary, not an invoked one. **`certified: true` licenses no live
  experiment.** D08 must consume `certified: False` without reading `trusted-host` as a fallback
  — there is no parameter that offers one. D23 owns activation.
- `certify_profile` certifies HOST+PROFILE, never a particular experiment's tree. The sentinels
  build their own synthetic tree; a certification says this host enforces these operations, not
  that some specific run was isolated. D28/D29 must cite a sentinel report, never this prose.
- A production caller must create `ProtectedLayout.REQUIRED_DIRS` itself — `exec_policy` creates
  and deletes nothing outside its own tempfile trees, by design.
- `linux-bubblewrap` and `container` are declared, permanently `not-implemented`, with their
  prerequisites named. No installation was performed or is authorized.
- No row was added to `primitives/harness-capabilities.json` and no release-gate contract claims
  protected live experiments. That is D28/D29's call, on sentinel evidence.
- `bin/harness_update.py check` exits 3 — PRE-EXISTING installed-home staleness, proven by
  running it against a clean `git archive HEAD` extract (identical exit 3). Not this kit's.

outcome: D07 model=opus attempts=1 result=pass review=clean run=2026-09-16-aa6e
agent: D07 id=a641cf9 role=implementer model=opus
agent: D07 id=ab0d1bd role=verifier model=sonnet findings=0 confirmed=0 result=accepted

## D08 — Offline-only fence (sonnet, depends D07)

Four module-level gate functions in `bin/workflow_eval.py:1780-1903`
(`protected_trial_evidence`, `require_protected_trial`, `carry_protected_evidence`,
`run_protected_dispatch`) plus `UnavailableProfileTests` (16 tests) beside D07's class.
Both files purely additive: `git diff --numstat` = 126/0 and 251/0, so D07's
`ProtectedProfileSentinelTests` is byte-identical.

Proven both ways, as the brief required. Runtime: `_RaisingRunner` raises if invoked, so a
refusal that leaked would surface as a loud AssertionError, not a silently-ignored return
value. Structural: an AST walk of the whole module. I re-derived the structural claim myself
rather than trusting the test — the only bare `runner(...)` call in `bin/workflow_eval.py` is
line 1902 inside `run_protected_dispatch`, and the gate call at 1895 precedes it. No `mode`
parameter on any of the four, carrying D07's precedent forward.

**Carry-forward for D18 and D23 — the gate has ZERO production callers.** The four functions
are called only by each other; nothing in `Evaluation`, `cmd_run`, or `repo_bench` reaches
them. That is correct scope for D08, but it means D08's guarantees hold at the function level
and have never executed inside a real `Evaluation.run()`. D18 (protected live trial) and D23
(activation) each own their integration and must wire this chokepoint themselves; neither may
treat D08's green suite as evidence that a protected path is actually gated in production.
This is also why `SECURITY.md:198-199` ("Nothing dispatches through it yet") is still true and
was correctly left unedited — verified by call-graph derivation, not by reading the prose.

**Carry-forward for any task importing both modules.** The test file's own `ep` (spec name
`exec_policy_boundary`) and `wf._ep()` (spec name `polytropos_exec_policy`) load the same
source as two DISTINCT module objects, so their `SandboxUnavailable` / `ProfileStatus` classes
are not the same class object and `isinstance` fails across them. Build and catch through one
loader only.

`protected_trial_evidence` deliberately leaves `certified`/`sentinel_outcomes` as `None` on the
enforced path — it does not re-run D07's sentinel battery per dispatch, so it never manufactures
a certification it did not earn. A caller wanting fresh certification calls D07's
`run_sentinels`/`certify_profile` itself.

Nothing in the new section opens a file, touches a store, or persists anything, so D06's
evals-store-root flake cannot recur and `bin/workflow_eval.py` stays the one persister.

The vacuous-AST hole was the specific risk I asked the verifier to attack: an AST test that
loops over collected nodes and asserts each one passes trivially if the collection is ever
empty, reporting green while constraining nothing. It is closed by one line —
`assertTrue(finder.hits, ...)` before the loop. The verifier constructed the empty case
(renaming the bare `runner(...)` call so the walk finds zero nodes) and confirmed the guard
fails loudly, while the same test without that line would PASS on empty hits. Any later task
adding an AST-derived structural check must carry the same non-empty guard.

Verification: verify command 16/16; the seven prior modules 235/235 unmodified; full suite
4383 (baseline 4367 + 16), 2 skipped; `docs_build`/`copilot_docs`/`sync_codex_surfaces`/
`release_gate` exit 0; `harness_update` exit 3, pre-existing. Independent verifier: ACCEPT,
six of six claims CONFIRMED, no REFUTED findings.

Process defect, mine: I briefed the verifier to mutation-prove by editing tracked sources in
place and restoring afterwards. GUARDRAILS requires verifier mutation checks to use temporary
copies. It had already mutated `bin/workflow_eval.py` before my correction reached it; it
restored from backup and reported the mutation rather than concealing it, and I confirmed the
tree byte-identical myself (`git diff --numstat` = 126/0, 251/0, 1/1; 106 tests green). Future
verifier briefs must say "temporary copies only" explicitly.
outcome: D08 model=sonnet attempts=1 result=pass review=clean run=2026-09-16-aa6e
defect: D08 kind=process-guardrail verifier brief told a verifier to mutate tracked sources in place; GUARDRAILS requires temporary copies. Tree restored and confirmed byte-identical.

## Carry-forward for Phase 3 — four repo-wide sweeps will capture the new `bin/` modules

D04-D08 only added functions to files that already existed. D09 (`bin/decision_contract.py`),
D11 (`bin/decision_policy.py`) and D12 (`bin/decision_provider.py`) are the kit's first NEW
`bin/` files, and four existing tests glob `bin/*.py` and will sweep them in automatically. All
four are real invariants; none may be weakened to make a new module pass.

1. `tests/test_decision_evaluation_manifest.py:733` — THE TRAP. It filters on a raw substring of
   the whole file text (`'"evals"' in p.read_text()`), comments and docstrings included, then
   asserts exact equality with `["runtime_data.py", "workflow_eval.py"]`. A new `bin/` module
   that merely writes the word "evals" in a DOCSTRING breaks it, with no code involved. Verified:
   the string `# ... persisted into the "evals" store` matches the filter. Say "the evaluation
   store" in prose instead. If this goes red during Phase 3, the cause is almost certainly a
   comment, not a second writer — do not relax the assertion, which is the one-writer guard.
2. `tests/test_workflow_eval.py:944` — no `bin/*.py` except `workflow_eval.py` may contain the
   `POLICY_FILE` literal, which is `"routing-policy.json"`. D11 and D13 both own
   `bin/decision_policy.py`; naming that file even in a comment explaining that it is NOT read
   trips this. D13's "no active pointer consumption before D23" already points the right way.
3. `tests/test_decision_provenance.py:557` — every `ATTEMPT_KINDS` literal must be appended from
   exactly one module. A new module passing a colliding string constant to `append(...)` or
   `_record(...)` registers as a second writer.
4. `tests/test_proc_runner_wiring.py:52` — no `subprocess.run/Popen/call/check_output` anywhere
   in `bin/*.py` outside `proc_runner.py` without an EXEMPT_SPAWNS entry. Phase 3 is pure
   contract/policy code and should spawn nothing.

Found by derivation before Phase 3 dispatched, not by a red suite afterwards.

## Phase 2 review — accepted with findings, three corrected in-phase

Six findings. No `done` status reversed: the phase is architecturally sound, the four tasks
compose, no shared authority was duplicated, and the reviewer independently reproduced D07's
central claim on this host (`exec_policy.py sentinels` exit 0, 19 kernel denials each attributed
by an unconfined control leg plus a permission-class errno, 2 allowed legs as positive control,
controller trees byte-intact). It also mutation-proved the version precedent load-bearing:
bumping `MANIFEST_VERSION` on a `git archive HEAD` copy moved `release_gate check` from exit 0
to exit 3. `bin/attempt_ledger.py` is byte-identical across 7e0c823..c9ea1a3, so `LEDGER_VERSION`
was never endangered.

Two HIGH findings were real overclaims in exactly the surface the D08 carry-forward aims D18 and
D23 at. I re-derived both from source before acting, because acting on an unre-derived claim is
this kit's documented recurring defect:

- **F1 — the gate applies no confinement.** `run_protected_dispatch` calls `runner(argv, cwd)`
  with argv verbatim; it never builds a `ProtectedProfile` or `ProtectedLayout` and never calls
  `wrap_argv`. `ProtectedProfile` appears in `bin/workflow_eval.py` only in the comment at 1783.
  Its docstring nonetheless read as though passing through it confined the dispatch. Wiring it
  as-written on a certified host yields a real unconfined money-spending dispatch labelled
  certified. It is an availability gate, and must say so.
- **F2 — the enforced-path label claimed "certified" over evidence saying otherwise.** The label
  at 1873 said `certified (...)` on the `mode is not None` branch while 1830 sets `certified=None`
  on that same branch, so the envelope asserted and denied certification in adjacent fields.
  "Enforced" is not "certified": only `certify_profile` earns the word and this path never calls
  it. The reviewer mutation-proved the text unconstrained — replacing it with `SAFE-AND-PROTECTED`
  left 54/54 and 52/52 green. `labels` reaches a user-facing card through `render_card_markdown`.
- **F3 (MEDIUM) — evidence carry fails open across module loaders.** `require_protected_trial`
  catches `_ep().SandboxUnavailable`, but a status built by a different loader raises a different
  class object, so the refusal escapes the handler: no purpose prefix, no `.evidence`, no label,
  no note. Fail-closed on safety (nothing dispatches) but silent on D08's own acceptance. Three
  modules already build their own `exec_policy` object via `spec_from_file_location`.

Carried forward, not fixed: F4, D06's held-out controller and D08's isolation gate never compose
and nothing names the pairing, so a D18 wiring only the gate gets a "certified" envelope over a
cohort with zero held-out evidence; F5, `results.json` carries partition counts without the
enforcement disclaimer reaching the envelope; F6, one stale present-tense item at
`docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md:189-193` with a citation off by ~1200 lines.

Also confirmed by the reviewer and worth acting on in Phase 3: `attempt_history.DURATION_BASES`
already reserves `"decision-latency"` for the decision record — produce that basis through
`_duration(...)` rather than inventing a second duration field. And `bin/routing_policy.py` has
exactly three direct loaders, with only the Codex driver dispatching under a routing decision,
so D13's "wrap the native driver selection seams" is NOT four symmetric seams: Claude and Copilot
reach routing by neither path.
reviewer: P2 model=opus findings=6 confirmed=3 result=accepted

### Phase 2 corrections applied (F1, F2, F3, F6)

`run_protected_dispatch` is now `gate_protected_dispatch`, and its docstring leads with
`THIS APPLIES NO CONFINEMENT.` Two paired tests keep prose and code from drifting apart: one
asserts the required disclaimer phrases, the other walks the function's AST and asserts it
references none of `wrap_argv`/`ProtectedProfile`/`ProtectedLayout`/`run_confined` and that the
bare runner call's positional args are exactly `["argv", "cwd"]`. So wiring real confinement here
later forces the docstring to be rewritten in the same edit — the pairing is the point.

The enforced-path label now reads `enforced (...) -- NOT certified by this gate; certification is
exec_policy.certify_profile's over a sentinel report, and this path ran none`, constrained by
`assertEqual` on the exact text plus `assertNotRegex` on the old defective shape and an
`assertIn("certified=None", ...)` tying label and note together. Mutation-proven twice, including
against the reviewer's own `SAFE-AND-PROTECTED` substitution.

F3's cross-loader fix resolves the class the bound method will actually raise out of
`type(status).require_enforced.__globals__`, because `spec_from_file_location` modules are never
registered in `sys.modules` and that closure is the only reliable handle. The catch widened to
exactly that class, not to `Exception`: a companion test passes a status-shaped object whose
`require_enforced` raises `TypeError` and asserts the `TypeError` surfaces as itself rather than
being redressed as a profile refusal.

**Carry-forward for D18/D23, now the binding one.** `gate_protected_dispatch` performs a dispatch
through the supplied runner and ledgers NOTHING. The repo invariant requires every dispatch to be
recorded in `bin/attempt_ledger.py` before and after it runs. Whichever task wires this gate owes
both: open the ledger entry before the call and close it after, AND supply a runner that actually
confines, because the gate does not. Deliberately not added here — nothing calls the gate, so
there is no dispatch to record, and speculative ledger calls in an uncalled function are the
wrong fix.

F6 closed: `docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md` item 10 carries a dated correction
in D06's established convention rather than a rewrite, since the document is an inventory of a
stamped revision (`71bb3ae`) and not a live description. Mirror regenerated. The census pin at
`tests/test_docs_build_adversarial.py:750` counts FILES (31) and was untouched, because this added
content and no file.

F4 and F5 remain carried forward for D18 and the assessment phase.

## D09 — Strict contract parser (opus, depends D04, D06)

New `bin/decision_contract.py` (the kit's first new `bin/` file) and
`tests/test_decision_contract.py:DecisionRequestValidationTests`, 51 tests. Four frozen
dataclasses — `QuestionSpec`, `DecisionRequest`, `DecisionResult`, `DecisionRecord` — under one
`CONTRACT_VERSION = "polytropos.decision/1"`, on the referenced object per D04's precedent,
registered in `release_gate.VERSION_SOURCES` with `docs/RELEASE.md` regenerated by its generator.
Red-green proven by the orchestrator, not just the implementer: I captured exit 1 at HEAD 1b801de
before dispatch and exit 0 after.

Reuse rather than reinvention, verified: refs go through `attempt_ledger.read_ref`/`make_ref`,
duration through `attempt_history._duration` on the reserved `"decision-latency"` basis and no
other, and `resource_policy.operation_scope` must be a key of `kit_contract.OPERATION_CAPS`.
`decision_ref(record)` carries `CONTRACT_VERSION`, never `LEDGER_VERSION`, and
`attempt_ledger.validated_refs(decision_ref=...)` accepts it with no ledger-side change.

**Independent verification returned REVISE and found two real defects, both since fixed.**

A period evaded the banned-field sweep. `_normalised` mapped `-` to `_` and stripped wrapping
underscores but left periods alone, and `_ID_RE` permits periods, so `approve.`, `grant.`,
`budget.x`, `trusted_host.` and `max_dispatches.` were ACCEPTED where `approve` was refused —
including inside `_distribution`, which parses provider-controlled answer data. I reproduced it
before acting. Fixed by matching the whole key AND each period-delimited component against
`_BANNED_ALNUM`, both sides reduced from one source so the two cannot drift apart.

Two traps inside that fix, worth keeping: the naive version (`_alnum(key) in set(BANNED_FIELDS)`)
silently stops banning `max_dispatches`, because only one side gets reduced — three tests now
catch that. And splitting on `_` or `-` as well would be stricter but wrong: it makes `exit_code`,
`error_code`, `patch_sha`, `script_path` and `command_line` unparseable, and `exit_code` is a key
the module's own docstring names as canonical snapshot data. That is the documented
"ban makes a legitimate object unparseable, so someone shrinks the ban" failure, avoided by
measurement rather than taste.

**My brief for that fix contained a contradiction the implementer caught.** I required
`budget.x` be rejected AND prescribed `_alnum`; `_alnum("budget.x")` is `budgetx`, so the two are
incompatible. It flagged the conflict rather than silently satisfying half of it. A brief is not
automatically consistent just because the executor wrote it.

The second defect was a vacuous AST guard, and the exhaustive audit found FOUR, not one. A walk
that builds a set and then asserts over it passes trivially when the set is empty:
`test_the_module_is_stdlib_only_and_starts_nothing` (proven by an import-free mutant that
smuggled `os` in dynamically and stayed green), plus
`test_no_field_this_contract_defines_is_one_it_bans` (vacuous from the `BANNED_FIELDS` side),
`test_a_resource_scope_is_one_the_task_contract_already_defines`, and
`test_a_terminal_status_is_still_checked_against_the_request_it_answers`. All four now carry
non-empty guards; I independently re-proved two by emptying the collection in memory.

**This hole is recorded in the D08 carry-forward above AND was passed to D09 in its dispatch
brief, and it recurred anyway.** The lesson is not to warn harder. A ledger note is advisory and
an AST guard is only real when a test enforces it, so every future task adding a structural check
should expect the guard to be audited rather than assumed. All 19 iteration sites in the module
were enumerated by AST scan, not by eye.

Open and deliberately not closed, so nobody reads the fix as more than it is:
- Homoglyph evasion. A Cyrillic look-alike still passes the sweep. Stated as a non-guarantee in
  the module docstring and in `_is_banned_key`. Nothing else in this repo attempts unicode
  normalisation.
- The ban sweeps MAPPING KEYS ONLY, via `_object`. List items (`alternatives`, `outcomes`,
  `reason_codes`) are not swept. True before this fix as well; recorded so the boundary is known.
- The stdlib-only test is static. The non-empty guard closes the zero-imports hole, but a module
  keeping one real import and smuggling the rest dynamically would still pass.
- `decision_contract.py` calls `attempt_history._duration` and `._cost`, both private, with no
  public equivalent, and no other `bin/*.py` reaches across a module boundary that way. Correct
  today, but nothing marks that return shape as a cross-module contract, so a refactor of
  `attempt_history` would break D09 silently. A candidate for a public seam later.
- `parse_request` does not cross-check `task_ref.id` against the `task` label. Possibly
  intentional; not scored, but do not assume it is enforced here.
- `DecisionRecord.__init__` is reachable with unvalidated fields, as with every frozen dataclass
  in this repo. It needs first-party code, not a provider payload, so it is not a D09 hole.

For Phase 3's remaining tasks: D10 extends `_distribution`, `_answer`'s numeric slots and
`vendor_confidence` in this same file and should need no `CONTRACT_VERSION` bump, since the answer
key set is already final; the fixture builders are module-level and reusable. D11 should reuse
`BANNED_FIELDS` as its proposal-diff allowlist and register its own bundle/proposal versions
SEPARATELY rather than overloading `polytropos.decision/1`; `"diff"` was deliberately left out of
the ban so D11's data-only diff is legal. D12's replay key needs the policy bundle and calibrator
added on top of `DecisionRequest.sha()`, which already covers project/provider eligibility, task
and acceptance identity, complete state, alternatives and the question set.

One unexplained event, recorded rather than resolved: a single mid-task full-suite run reported
`FAILED (failures=1)` and the test name was not captured. Nine subsequent full-suite runs are
green — six by the implementer, two by the verifier, and my own two independent runs at 4439.
Not attributed to the PLAN's known unreproduced scheduler race without evidence. If it recurs,
capture the name.
outcome: D09 model=opus attempts=2 result=retry-pass review=revised run=2026-09-16-aa6e
defect: D09 kind=unspecified-path executor brief required rejecting budget.x while prescribing _alnum; the two are incompatible and the implementer flagged it

## D10 — Value validation (sonnet, depends D09)

Value semantics above D09's structural floor, in the same file: exact category coverage against
the question's own `outcomes` (new reason code `category-mismatch`), a per-entry probability
bound, a documented `DISTRIBUTION_SUM_TOLERANCE = 1e-6`, and refusal of two outcomes whose rubric
text reduces to the same string under the `_alnum` reduction `_is_banned_key` already uses.
Nothing renormalizes; every malformed payload is refused outright. 11 tests in a new
`DecisionValueValidationTests`. No `CONTRACT_VERSION` bump — no key set changed shape, which is
exactly what D09 reserved the empty numeric slots for.

D09's class is untouched: AST-identical, 55 methods. I checked this by comparing the parsed class
node, after a naive line-slice comparison reported a false difference — D09's class used to be
last in the file, so the trailing `if __name__` block fell inside the slice and moved out when
D10's class was appended. Measure the class, not the text between two markers.

**The best thing in this task is a test D10 caught being redundant against its own product.**
Mutation-testing the per-entry `>1` branch showed the original two cases did NOT detect its
removal: with `minimum=0` checked separately and the sum tolerance active, any entry above 1
necessarily breaks the sum too, so the sum check was catching both cases and the per-entry bound
was never isolated. It added `1.0 + tolerance/2`, which is over 1 but leaves the SUM inside
tolerance, and the mutant then fails correctly. I confirmed the arithmetic independently:
1.0000005 sums to |s-1| = 5e-7 < 1e-6, so the sum check alone would pass it.

The general lesson, which applies to every remaining task: a test can be non-vacuous, pass, and
still prove nothing, because a DIFFERENT guard is catching its input first. Guard non-emptiness
is necessary and not sufficient — the only way to know a branch is tested is to remove that
branch and watch the test fail. Three guards here were audited by emptying the collection; all
three failed as they should, and I re-derived the guard-to-loop correspondence myself.

Deliberately not done, and worth a reviewer's eye: rubric ambiguity reuses `incomplete-question`
rather than taking its own reason code, on the grounds that it is the same defect class D09 filed
there. Defensible, and a one-line change plus two test retags if the phase review prefers a
dedicated code for machine branching. "Do not infer independence or multiply probabilities" is
enforced by construction rather than by a runtime check — no path in this module ever reads a
second question's answer while validating one — so test 11 demonstrates the property instead of
asserting a negative about code that does not exist. The tolerance is sized for IEEE-754
summation error only, never a provider's own rounding; do not loosen it to accept a malformed
payload.
outcome: D10 model=sonnet attempts=1 result=pass review=revised run=2026-09-16-aa6e

### D10 verification — REVISE, and the masking pattern found a second time

I wrote `review=clean` on D10's outcome line before its verifier had run; that was premature and
the line is now `review=revised`. Verifying my own work is not independent review, and D09 is the
standing proof: my checks passed it and the independent verifier found an authority bypass.

The verdict was REVISE on one coverage gap, no product defect. D10's `_probability` gained
`minimum=0` — brand new, correct production code — and NOTHING in the repo isolated it. Both
negative-entry cases paired the negative with a partner above 1, so the upper bound refused them
first. I reproduced it: deleting `minimum=0` in a `git archive HEAD` copy left the whole module
green, and the verifier confirmed the same against all 4450 tests.

**Why it was hard to see, and the generalisable part.** The boolean question has exactly two
outcomes, and with two entries summing to 1 a negative entry FORCES its partner above 1. On a
two-outcome question the lower bound is mathematically unreachable on its own. Isolating it needs
three outcomes, where a negative entry can sit beside partners that are each in range and still
sum to 1.0. So this was not carelessness: the obvious fixture could not express the test. When a
branch resists isolation, check whether the fixture's own arity is what makes it unreachable
before concluding the branch is redundant.

Closed with one case on `ordinal_question` (three outcomes): `{"none": -0.1, "some": 0.6,
"all": 0.5}`, asserting in-test that the sum is exactly 1.0 and no entry exceeds 1, so neither
sibling check can be what refuses it. Mutation-proven both directions — fails against the
`minimum=0`-deleted mutant, passes against real code. Suite 4450 -> 4451.

This is the THIRD instance of the same pattern in Phase 3 (D09's four vacuous guards, D10's
upper-bound redundancy found by the implementer, D10's lower-bound gap found by the verifier).
Standing instruction for every remaining task in this kit: after writing a guard, delete it and
watch a test go red. A guard that survives its own deletion is decoration. Add that to the
implementer brief rather than trusting it to be remembered.

## D11 — Bundles and proposals (opus, depends D09)

`PolicyBundle` and `CandidateProposal` as record types in `bin/decision_contract.py` under their
own `BUNDLE_VERSION` and `CANDIDATE_VERSION`, registered SEPARATELY in
`release_gate.VERSION_SOURCES` rather than overloading `CONTRACT_VERSION`, which did not move.
New `bin/decision_policy.py` (500 lines, pure library, persists nothing) holds resolution;
`workflow_eval.py` was not touched and stays the persistence owner. New
`tests/test_decision_policy_bundle.py:PolicyBundleContractTests`, 52 tests. Suite 4451 -> 4503.

**The standing delete-the-guard instruction was followed exhaustively and it paid: 65 branches
deleted one at a time, and FOUR initially survived** — instances four through seven of this
phase's masking pattern, all found by the implementer rather than by verification.
Each was masked by a sibling guard: a hypothesis-restates-the-id case refused first by the
32-char floor; the character floor refused first by the word floor; a catalog type guard reachable
only by a non-iterable, since a dict or string falls through to the per-entry guard; and a source
vocabulary check masked by the bundle/source coherence check. All four isolated, and the report
names which test catches each of the 65 deletions.

Two structural choices make masking harder here rather than relying on vigilance. `_unmet`
collects ALL unmet reasons instead of short-circuiting, so one requirement's test cannot be
satisfied by a different check refusing the input first. And there is an explicit positive
control, `test_a_bundle_that_meets_every_requirement_is_selected`, without which every
"ends at legacy" assertion would pass against a resolver that always returned legacy. **I proved
that control real: stubbing `resolve_bundle` to always return legacy fails 27 of the 52 tests**
(28 if the stub also drops the argument validation, which is a less faithful stub because those
extra failures are callers-passed-garbage tests, not always-legacy tests).

Verified myself: both new/edited `bin/` files are clean of all four repo sweeps; `CONTRACT_VERSION`
unmoved; D09's and D10's test classes byte-untouched (`git diff --numstat` empty on that file);
zero production callers of `decision_policy` — the only two matches outside its own file are
comments in `decision_contract.py`, not imports.

Note how the policy-file sweep was threaded: `LEGACY_PREFERENCE_VERSION` is
`"polytropos.routing-policy/1"`, which names the legacy shape WITHOUT containing the
`routing-policy.json` literal `tests/test_workflow_eval.py` forbids in any `bin/*.py` but
`workflow_eval.py`. A test pins it equal to `workflow_eval.POLICY_VERSION` so the two cannot
drift. `describe_legacy_preferences` LOADS the historical shape into an inert view reporting its
keys as `unmapped`; nothing converts a legacy preference file into an active bundle.

Carry-forward, stated by the implementer rather than discovered later:
- Nothing in production calls `bin/decision_policy.py`. The chain to a runtime is D12/D13 and
  D20/D23. A green suite says the unit works, not that anything invokes it.
- The ban still sweeps mapping KEYS only. It is closed for the diff by construction — every
  parameter value is a scalar, so there is no list for the sweep to miss — but `scope.task_classes`,
  `requirements.capabilities`/`providers` and the evidence lists ARE lists, and an entry spelled
  `approve` parses. Inert today (membership comparison only) and now written into the module's own
  header rather than left silent.
- `approval_ref` presence is necessary and explicitly NOT sufficient. A JSON pointer is not
  authentication. D22 binds reviewer, scope and exact hashes.
- Label parameter values are not checked against any vocabulary; whether a label names a workflow
  the evaluator knows is D20's question.
- `MAX_FALLBACK_DEPTH = 8`, `MIN_EVIDENCE_REFS = 2`, `MIN_STATEMENT_CHARS/WORDS = 32/6` and
  `MAX_PARAMETER_VALUE = 64` are chosen bounds, not measured ones.
- A true content-addressed fallback cycle cannot be constructed, since each link's digest depends
  on the next. The cycle guard covers the realistic case — a tail pinning a stale ancestor digest —
  and if deleted, that input terminates via content-mismatch rather than hanging.
- `decision_policy` reaches no private name of `decision_contract` (AST-proven), so D09's
  `attempt_history._duration` private-reach smell was not extended.
outcome: D11 model=opus attempts=1 result=pass review=clean run=2026-09-16-aa6e

### D11 verification — ACCEPT, and both findings were mine

The verifier ran 12 mutations rather than the 8 asked for, including all four branches the
implementer said initially survived, and found NO branch deletable with the suite green. It could
not force a hash collision: numeric-form ambiguity is structurally impossible because `_integer`
refuses `float` and `bool` outright and no other numeric field exists; duplicate keys cannot
survive `to_payload()` rebuilding a fresh dict; unicode is `ensure_ascii` escaped injectively;
present-with-null and missing are different refusals, never silently equal. D02's goldens are
green and untouched.

Both findings were defects in MY OWN records, not the implementer's work.

1. I wrote "570 lines" for `bin/decision_policy.py`. It is 500. I copied that figure from the
   implementer's report without measuring it — a number that rots, and not even my own.
2. I put "fails 30 of the 52 tests" in commit e2cc9d6's body for the always-legacy stub. The
   verifier got 26/27/25 depending on the stub and flagged that it could not reproduce mine.
   Diagnosed rather than merely corrected: my temp copy was `git archive HEAD` at 0eff7c8 —
   BEFORE D11's own commit — with only three files overlaid, so `bin/release_gate.py` and
   `docs/RELEASE.md` were stale and `test_both_new_versions_are_declared_on_the_release_surface`
   failed on its own. I reproduced that: with an UNMUTATED resolver, that tree fails 2 tests. So
   30 = 28 stub failures + 2 artifacts of my own fixture.

   The faithful figure is 27: keep the `_runtime`/`_catalog` argument validation, then always
   return legacy. 28 comes from also deleting the validation, which is the worse stub, because
   the extra failure is a caller-passed-garbage test rather than an always-legacy test.

**The lesson is the one this phase keeps re-teaching, now applied to me.** A mutation result is
only evidence if the tree differs from the real one in exactly ONE way. Mine differed in three:
the stub, plus two files I forgot to overlay. Build the temp tree from the commit under test, not
from an earlier HEAD, and confirm it is green BEFORE mutating — an unmutated baseline run is the
control that would have caught this in one command.

Also carried forward from the verifier for D13, which extends this same file: D11's
`RESOLUTION_SOURCES` and `RESOLUTION_REASONS` are closed vocabularies with their own
mutation-proven tests. D13's `select_action` baseline/recommendation/selection reason codes are a
DIFFERENT concern and need their own vocabulary rather than reusing or shadowing D11's names.

One limitation the verifier confirmed as correctly disclosed rather than hidden: a label
parameter's VALUE may legitimately be an authority-sounding string, because the ban sweeps mapping
keys only. Nothing downstream reads such a value as a grant; it is inert today and stated in the
module's own header.

## D12 — Rules and replay (sonnet, depends D10, D11)

New `bin/decision_provider.py`: one `evaluate(request, *, mode, provider, ...)` interface over two
private implementations, plus `record_result` and `replay_key`. New
`tests/test_decision_provider.py:RulesReplayProviderTests`, 38 tests. Suite 4503 -> 4541. New
`REPLAY_VERSION = "polytropos.decision-replay/1"`, registered separately; `CONTRACT_VERSION`,
`BUNDLE_VERSION`, `CANDIDATE_VERSION` and `LEDGER_VERSION` all untouched.

`replay_key` is `request.sha()` plus provider, model, bundle_sha and calibrator_ref layered on
top — the last two being exactly what D09 noted `DecisionRequest.sha()` does NOT cover.
Cross-project miss is structural rather than a separate check: project is already inside
`request.sha()`, so a different project is a different key and there is no second guard that
could drift out of agreement with the first.

Three semantic claims I verified functionally myself, not from the report:
- **Replay makes no call.** A runner that RAISES is never invoked — on replay miss, on replay hit,
  and in rules mode. Proved the D08 way, plus an AST assertion that neither implementation's body
  names `runner`.
- **Unknown is None, never zero.** A replay hit forces `dispatched_provider`, `observed_provider`,
  `dispatched_model`, `observed_model`, `duration` and `usage` all to `None`. I printed all six.
  This is the GUARDRAILS rule "missing duration/usage/model identity is unknown, not zero" holding
  at the one place it would be most tempting to write 0.
- **Historical cost stays on its original record.** `record_result` is create-once, mirroring
  `workflow_eval.write_manifest`: same identity and same content is a no-op, same identity and
  different content is REFUSED. I confirmed the refusal by re-recording altered content under the
  same key. It also refuses to record a result whose note already carries `REPLAY_NOTE_PREFIX`, so
  a replay cannot be laundered into a fresh observation.

33 mutations, zero survivors, and for the first time in this phase NO masked guard was found. The
implementer attributes that to applying D10's fixture-arity lesson up front — building the two
whole-abstain triggers (`decided_any`, `blocked`) against deliberately SEPARATE fixtures so
neither could mask the other — rather than discovering the collision afterwards. That is the
lesson working as prevention instead of as diagnosis.

It also disclosed one branch that is deliberately NOT load-bearing: the internal
`parse_result(payload, request)` re-validation at the end of both implementations. No test goes
red if deleted, because every test independently re-runs the D09 validator on the returned payload
anyway — which is the literal acceptance requirement. Naming a redundant guard beats omitting it
from the table and letting a later audit think the report was complete.

Carry-forward:
- Zero production callers, same as D11. The chain to a coordinator is D13, then D20/D23.
- `DEFAULT_RULES` ships EMPTY on purpose. No domain recovery heuristic is defined anywhere yet —
  that is D14-D19's work — and inventing one here would be candidate data changing the improvement
  procedure, which GUARDRAILS forbids. An empty table means the rules provider abstains wholesale,
  which is exactly what acceptance asks for. Flag it if a reviewer expected a shipped heuristic.
- `store_dir` is ALWAYS caller-supplied; the module never resolves a location, never reads an env
  var and never imports `runtime_data`. A later task wanting a real per-user default should call
  `runtime_data.store_path(...)` itself and pass the result in. Keeping the module ignorant of
  where its store lives also keeps a second file from containing the reserved store-name substring
  that the evaluation-store sweep matches.
- The replay store does not defend against someone with the user's own privileges hand-editing a
  record into a self-consistent forged digest — the same non-guarantee every hash in this kit
  already carries. A digest identifies content; it does not protect against a rewrite by someone
  who could write the file in the first place.
outcome: D12 model=sonnet attempts=1 result=pass review=revised run=2026-09-16-aa6e

## D13 — Legacy policy selection (opus, depends D02, D12) — Phase 3 complete

`bin/decision_policy.py` 500 -> 1240 lines; D11's half is byte-identical, verified by diffing the
first 500 lines against 998d433. New `tests/test_decision_policy.py:LegacySelectionTests`, 86
tests. Suite 4541 -> 4627. No version constant, deliberately: `ActionSelection` is an in-memory
return value feeding `build_record`, which already carries `CONTRACT_VERSION`; nothing here is
persisted, so there is no stored shape to version. If D23 persists a selection, that is when it
earns one.

**The D02 golden trap held.** I pinned `tests/test_decision_legacy.py` by checksum BEFORE dispatch
and told the implementer the pin existed. md5 is `8404232d...` before and after and
`git diff --numstat` on it is empty. The combined verify moved 1 -> 0 without a golden changing.

**The seam shape, corrected again — and my brief was the thing that was wrong.** I told D13 that
`routing_policy.py` has three direct loaders and implied all three were deciders. Reading shows
they are not three of a kind: `codex_policy.py` decides and `codex_execute.py` dispatches under it
(the only place a routing decision precedes a real dispatch); `workflow_eval.py:579` (`route_stage`)
DOES call `rp.decide`, but for offline variant comparison and it spends nothing; and
`release_gate.py:1004` merely loads the module to read a version constant off it — not a decision
seam at all. Claude and Copilot reach routing by neither path: their seam is `resolve_model` plus
`escalation_ladder` from their own pricing files, and Cursor has no ladder at all
(`cursor_execute.py:157` is `model or task.get("model")`). So there are TWO seam shapes, not four,
and two adapters wrap exactly those. Neither is wired to anything, and
`test_nothing_in_this_repository_calls_the_selection_or_either_seam` sweeps `bin/*.py` and asserts
the caller list is empty, so the day someone wires it that test is the signal.

**"A high-confidence result never overrides a hard denial" is structural, and I proved it myself.**
`_admissible(action, facts)` has exactly two parameters — there is no argument through which a
probability, a calibrated number or a vendor confidence could arrive; a test pins the parameter
list, so adding `result=None` trips it. I ran the behaviour directly: raw 1.0, calibrated 1.0 and
vendor_confidence 1.0 recommending a DENIED action leaves `selected` at the baseline with reason
`advice-inadmissible`, and the rejection carries the denial's own reason (`excluded`), not a
generic one. Control: the identical answer with vendor_confidence 0.0 behaves identically, so
confidence is unread in BOTH directions rather than merely capped.

`denial_reasons()` is derived by SUBTRACTION — `routing_policy.FILTERS` minus `ranked-lower` — so
a filter added to the router is hard here automatically. That fails closed rather than needing
someone to remember. A test patches `rp.FILTERS` with an invented filter and asserts it lands on
the denial side with no edit to this module.

80 mutations, 0 survivors. Three survived the first correct run and all three were examined:
`_mode`'s vocabulary check was masked by an identical check in `__post_init__` (fixed by
validating the caller's own argument BEFORE the state, which is also the better order); `_in_force`'s
source check survived only because the fixture lacked a digest, and with a proper fixture its
deletion lets a resolution claiming an activation read as in-force and SUCCEED SILENTLY — the
dangerous case; and `tuple(dict.fromkeys(codes))` genuinely proved nothing and was REMOVED rather
than disclosed, because de-duplicating would have silenced the `duplicate-entry` guard beneath it.
**A guard that hides another guard is worse than no guard** — add that to the standing instruction.

**The implementer's mutation harness caught a defect in ITSELF, which is the control lesson again.**
Its first run had all 80 mutants die with the same `SyntaxError` and ZERO failing test names —
which by exit code alone reads as 80 guards caught. Cause: it passed a restricted `PATH`, picked up
system python 3.9 instead of the repo's 3.12, and the run proved nothing. It ran the unmutated
control first, saw the control was also broken, and discarded the run. This is the same discipline
I failed on D11.

Two defects the tests found in its own code, same root cause: `selection_state` COERCED its
arguments before validating them. `dict(denials or {})` on a list raised a bare `ValueError`
instead of a contract refusal, and `list(reserved)` on a model-id string silently became a list of
its letters. The coercion answered the question before the contract could. **`runtime_facts` in
D11 has the same latent shape** (`dict(components)`, `list(capabilities)` before `_runtime` runs).
Out of D13's scope and NOT fixed — carry it to whoever touches D11 next.

Vocabulary: `SELECTION_REASONS` (20 codes) is disjoint from D11's `RESOLUTION_REASONS`, asserted by
test. One deliberate exception on the record: `legacy` appears in both `SELECTION_MODES` and
`RESOLUTION_SOURCES`, and the test asserts the intersection is EXACTLY `["legacy"]` rather than
forcing them apart — it names one fact, the frozen existing behaviour, and two spellings would be
two things to keep in step for no gain. The fourth coordinator check was renamed `budget` ->
`budget_admission` because `budget` is in `BANNED_FIELDS` and a check outcome spelled that way
would collide with the ban.

Carry-forward: zero production callers (the chain is D20/D23); `select_action` requires a PARSED
result and refuses a payload dict, so a caller holding `decision_provider.evaluate()` output must
run `parse_result` first — name this in the D20/D23 wiring; and `ActionSelection.recommended` is
NOT the field `DecisionRecord` carries under that name — the record reports what the provider said,
always, while this is narrower (the advice the selection was entitled to consider, `None` when the
result answered a different world). They diverge on a stale result. Documented in the dataclass,
but the name collision is a trap.

### The intermittent suite failure — second sighting, name STILL lost, and how to catch it

My first full-suite run at this tree reported `FAILED (errors=1, skipped=2)`. **I lost the test
name because I piped the run through `grep` for the summary line.** Four consecutive runs since
are green (one re-run plus three captured to files), so the tree is green and this is a
green-boundary commit, but the failure is real and this is the SECOND sighting — D09's implementer
saw one and also could not name it.

What this does and does not establish: D09's sighting happened when D13's code did not exist, so
D13 did not cause it. It is NOT attributed to the PLAN's known unreproduced scheduler/TASKS
atomic-write race, because there is still no evidence for that — only the absence of another
candidate, which is not evidence.

**Standing instruction, since this has now cost two chances:** never pipe a full-suite run through
`grep` when the point is to catch a failure. Redirect the whole run to a file
(`python3 -m unittest discover -s tests > run.log 2>&1`) and grep the FILE. A summary line is
worth nothing without the traceback above it, and the traceback is what both sightings lost.
outcome: D13 model=opus attempts=1 result=pass review=clean run=2026-09-16-aa6e

### D13 verification — ACCEPT, and it found a real defect in D11's shipped code

The verifier ran its control FIRST inside the temp tree (111/111 before mutating), redirected the
full suite to a file rather than piping it, and went well past my own confidence-vs-denial check:
a bundle whose `parameters` name the DENIED action, both modes, all eight denial reasons, and the
inverse trap where the baseline itself is denied and maximally-confident advice recommends exactly
it. Nothing moved `selected` off baseline or None. A literal `force_action` bundle parameter is
refused two layers below D13, by D09's closed parameter vocabulary.

It also confirmed structurally why `ranked-lower` being soft cannot be exploited:
`routing_policy`'s filter loop is an if/elif chain and appends `ranked-lower` ONLY to candidates
whose reasons list is already empty, so a candidate can never carry a hard filter and a ranking at
once. The ambiguity `state_from_routing` would have had to arbitrate cannot occur at the source.

Of its 12 mutations, 10 real deletions were caught, 2 test-validity probes were caught, and one
was the deliberate reinstatement of the removed `dict.fromkeys` de-dup: 0 failures, confirming the
removal was correct rather than a coverage hole. The `duplicate-entry` guard it would have masked
is exercised directly by a test that constructs `ActionSelection` and bypasses `select_action`
entirely, so whether `select_action` de-dups internally is irrelevant to that guard's coverage.

**D11's `runtime_facts` coercion defect: CONFIRMED EXPLOITABLE in shipped code, and now fixed.**
`runtime_facts(capabilities="codex-native-dispatch")` returned twenty-one single-character
capabilities instead of refusing. I reproduced it myself — after three failed probes of my own
(missing required args, then an invalid `intended_use`) which is worth recording, since each near
miss looked like the defect not existing.

The gap was precise and instructive: `_runtime` ALREADY type-checks `capabilities`, `providers`
and `components`, and a test already asserted `_runtime(capabilities="dispatch")` is refused. The
guard was never broken. But `runtime_facts` — the caller-facing wrapper — wrote
`list(capabilities)` and `dict(components)` BEFORE handing over, so the tested guard was
unreachable through the public door. **A validator can be correct, and tested, and still bypassed
by a convenience wrapper that coerces first.** Testing the validator is not testing the surface
callers actually use.

Fixed by handing the arguments over uncoerced; `_runtime` already makes its own defensive copies
from the values it validated, so coercing first could only ever hide a caller's mistake. The fix
is strictly a deletion. New test goes through `runtime_facts`, not `_runtime`, because that is
where the coercion was. Mutation-proven: control green, restoring the coercion fails 3 subtests.
Suite 4627 -> 4628.

### D12 verification — REVISE. The "33 mutations, 0 survivors" claim did NOT hold up

The verifier disclosed that its OWN first batch of 15 mutations was worthless: a hand-built `PATH`
resolved `python3` to a pre-3.10 interpreter, so every run failed INCLUDING the unmutated control.
It discarded the batch and redid it. That is the third time this exact trap has appeared in this
kit — D13's implementer hit it, I hit a variant of it on D11 — and every time the unmutated
control run is what exposed it. **A mutation batch without a green control is not evidence.**

Redone correctly, two of fourteen branches were deletable with all 38 tests green:

1. `_evaluate_rules`'s invented-category guard is masked by D09's own `_answer()`, which enforces
   the identical rule and is reached through D12's internal self-check. The test asserts only the
   error code, which D09 supplies for free, so it proves nothing about D12's own branch. Low
   severity: the outcome is identical either way and it is genuine defense-in-depth. Left in place
   and now named as redundant rather than removed, matching how D12 already disclosed its
   self-check.
2. **`record_result`'s anti-laundering guard was deletable with the suite green** — the serious
   one, because it contradicts the headline of my own commit 998d433 ("never let a replay pass as
   a fresh observation"). The only test re-recorded under the SAME identity already stored, so
   create-once fired first and masked the deletion entirely.

I reproduced both halves myself. On shipped code the cross-identity case IS refused, so the
product was always correct — the defect was purely that no test could tell. With the guard
removed, recording a replayed result under a NEW identity (same request, different `bundle_sha`)
SUCCEEDS, and a later replay of that identity returns a confident answer for a decision that was
never evaluated. Create-once cannot catch it, because nothing exists under that key yet.

Fixed by extending the existing test with the new-identity case. Mutation-proven: control green,
guard removed fails 1. Before the fix it failed 0.

**The pattern, stated once more because it has now bitten at three different layers.** A guard can
be masked by a sibling check (D10), by a check in a DIFFERENT MODULE reached through a self-check
(D12's invented-category), or by an earlier guard on the same call path that the test's own fixture
happens to trigger first (D12's anti-laundering). Non-emptiness does not detect any of them. Only
deleting the branch does — and only against a control you have proven green.

### A real design finding for D20/D23 — replay as keyed will almost never hit

`replay_key` is `request.sha()` plus provider/model/bundle_sha/calibrator. But
`DecisionRequest.sha()` digests the WHOLE request, so it also folds in `correlation_id`, `run`,
`task` and `attempt` — none of which the shared PLAN lists among replay-identity components. I
verified directly: two requests identical in every PLAN-listed respect (same state digest, same
questions, same alternatives, same eligibility) produce DIFFERENT keys when only `correlation_id`
differs, and likewise for `run`, `attempt` and `task`.

A correlation id is ordinarily fresh per call. So replay hits only when a caller re-asks with the
very same request object, never when the same SITUATION recurs — which is what a cache is for.

This is conservative, not wrong: a narrower key can only miss, never serve a stored answer for a
situation it did not answer. No safety issue. But a coordinator wiring this expecting a cache will
find it abstains almost always. Making replay hit across recurring situations means keying on a
narrower digest than `request.sha()`, which changes what identity MEANS — an architect decision,
not a silent edit. Both docstrings in `bin/decision_provider.py` described `sha()`'s coverage while
omitting these four fields; that false description is corrected, and the limitation is now stated
where a wiring task will read it.
defect: D12 kind=unspecified-path replay_key inherits correlation_id/run/task/attempt from DecisionRequest.sha(); the shared PLAN does not list them as replay-identity components, so replay rarely hits. Conservative, not unsafe. Needs an architect decision before D20/D23 wire a coordinator.

## Phase 3 review — accepted with findings; F1 and F2 closed in-phase

Nine findings, none reversing a `done`. The reviewer ran its control FIRST in BOTH temp trees and
used two of them deliberately: a `git archive` extract has no `.git`, and eight git-dependent
tests fail there for reasons unrelated to any mutation — so it also made a `git clone` at the
commit under test. That is the "temp tree differed in more than one way" trap I fell into on D11,
avoided by construction. 55 single-branch deletions, subprocesses inheriting `sys.executable`
rather than a hand-built PATH.

It ran the phase end-to-end across two different module loaders and it composes: request parsed ->
`evaluate(mode="rules")` -> `parse_result` -> `runtime_facts` + `resolve_bundle` -> `select_action`
-> `build_record` -> `decision_ref`. Authority containment holds under COMPOSITION, not just per
task: bundle parameters never reach selection, proposal diffs are inert, answer distributions are
unreadable by construction, a replayed `recommended` is re-validated against the current request's
alternatives, and reason vocabularies are closed at construction.

### F1 (HIGH, closed) — and I was fooled by the same fixture the tests were

Four of the six freshness nulls on a replay hit (`observed_provider`, `dispatched_model`,
`observed_model`, `usage`) were deletable with the ENTIRE 4629-test suite green. Cause: the
`result_for` fixture already set exactly those four to `None`, so four of the six `assertIsNone`
lines — which read as an exhaustive proof — could not fail.

**I verified this property myself earlier in this run and reported it as holding.** I printed all
six fields coming back `None` and concluded the unknown-not-zero guardrail was satisfied. I used
the default fixture, where four were already `None`, so my check could not have failed either. The
reviewer's finding is as much about my verification as about the tests: **a check performed with
the same fixture the tests use inherits the same blind spot.** When re-deriving a property, build
the input so that every field under test carries a value the code must actively change.

`usage` is the one with consequences: a replay reporting the original call's billed dollars
double-counts real spend, against the rule that missing usage is unknown, never inherited.
Confirmed shipped code is CORRECT — with a fully populated source record all six still come back
`None`. The defect was purely that no test could tell.

Closed with a test recording a source result carrying real values in all six, asserting in-test
that the SOURCE carries each one before asserting the replay nulls it. Mutation-proven per field:
all six now fail on deletion; before, four left the whole suite green.

### F2 (MEDIUM, closed) — a vacuous test reintroduced, of the class D09 fixed four of

`test_the_attempt_event_kinds_are_not_appended_from_this_module` had its `assertNotIn` nested
inside four `if`s over an AST walk and executed ZERO assertions against the module. Rewritten as
a text check like its own neighbour two lines below, which can always fail; proven non-vacuous by
adding a kind literal as a comment and watching it go red. The product was never exposed —
`test_decision_provenance.py` sweeps every `bin/*.py` for the same literals and is non-vacuous —
but D09's standing instruction says a new structural check must expect auditing, and D12 added one
that had not been.

### F3 (MEDIUM, OPEN — needs an architect decision, do NOT silently edit)

**A refused decision cannot be recorded.** `ActionSelection` sets `selected=None` for its six
refusal reasons, and `baseline` may be `None`. `parse_record` requires both to be non-null labels
drawn from `request.alternatives`, so `build_record` raises `[wrong-type] record.selected must be
a string, got NoneType`. The outcome that matters most for audit — the coordinator refused to act,
and here is the complete reason — has no representation in the object the shared PLAN says carries
"reason codes, rejected alternatives". Secondary wrinkle: on a whole-selection refusal every
alternative including the untouched baseline is listed in `rejected` with reason `not-selected`,
which is not why it was set aside.

Nothing is broken today (zero callers) but D18/D20/D23 hit it immediately. Two legitimate
resolutions: make `selected`/`baseline` nullable, which is a `CONTRACT_VERSION` bump and exactly
what that constant exists for; or record deliberately that a refusal produces no `DecisionRecord`
and say where it IS recorded instead. That is a scope decision, not an implementer's call.

### F4 (corrections to my own records)

"Zero production callers" is true of BEHAVIOUR and false of IMPORTS. `bin/release_gate.py:153-156`
loads and executes `bin/decision_contract.py` and `bin/decision_provider.py` at check/build time
via `spec.loader.exec_module`. Proven by coupling, not inferred: bumping each of the four version
constants moves `release_gate check` from exit 0 to exit 3, four times out of four. Consequence
for Phase 4: **an import-time error in either module breaks the release gate.**
`bin/decision_policy.py` genuinely has zero callers of any kind.

Also stale: D11's note said "the only two matches outside its own file are comments in
`decision_contract.py`". There are three now — D12 added `bin/decision_provider.py:453`. True when
written, wrong as a present-tense claim. Carry-forward notes age; date them or phrase them as of
a commit.

### F5-F9 — carried to Phase 4/5, not fixed here

F5: the rules provider sets `dispatched_provider` to the provider on the `ok` path and `None` on
both abstain paths — same local computation, two different claims about whether anything was
dispatched, and no test pins either. D14's coverage/abstention joins and D19's resource accounting
both key off these slots.
F6: `DecisionResult.note` is provider-controlled free text, bounded at 4000 chars but never passed
through `bin/redact.py`, and it is persisted verbatim into the replay store. Harmless today (the
only writers are this module's own constants); D20's live provider is the first real writer, and
D14-D19 read these records.
F7: `SENSITIVITIES` and `PRIVACY_SCOPES` are each validated as vocabularies and never compared to
each other, so nothing prevents a `restricted` question riding inside a `vendor-eligible` request.
F8: the stale-admission rule is spelled in both `decision_contract` and `decision_policy` with no
test pinning them equivalent — unlike the good precedent already set for
`LEGACY_PREFERENCE_VERSION == workflow_eval.POLICY_VERSION`.
F9: the replay store is read with bare `json.loads`, not the contract's duplicate-key-safe
`loads`, in a module whose sibling made duplicate keys a refusal.

### Two Phase 4/5 tripwires nobody had written down

**A real replay store has no home.** `replay` is not in `runtime_data.STORES` and there is no
`/replay/` in `.gitignore`. `store_path` does not validate the name, so passing one works — but
`runtime_data where/migrate/forget` iterate `STORES` only, so the store would be invisible to the
user's own inspection and deletion paths, and `legacy_path` means a `replay/` directory in the
repo root would become the store AND BE TRACKED BY GIT. That breaks the invariant that every local
store is personal data living outside the plugin tree.

**Label values are stricter in the workbench than in the bundle.** `workflow_eval.build_proposal`
refuses a `workflow` outside `WORKFLOWS` and a `policy` outside `POLICIES`; `DIFF_PARAMETERS`'
`routing.default_workflow`/`routing.default_policy` accept any label. Whoever bridges them must
apply the workbench's vocabulary.

Also for D20/D23: `_read_record` RAISES on a version mismatch rather than returning a miss, so
bumping `REPLAY_VERSION` turns an existing store into an error-throwing store rather than a cold
cache. Honest over silent, but a coordinator expecting "a miss abstains" will not get it.
reviewer: P3 model=opus findings=9 confirmed=9 result=accepted
defect: D13 kind=contradictory-acceptance a refused ActionSelection has selected=None and baseline may be None, but parse_record requires both non-null, so build_record raises and a refusal cannot be recorded. Needs an architect decision before D18/D20/D23.

## Phase 4 — Recovery evidence

## D14 — Read-only joins (opus, depends D05, D06, D10)

New `bin/decision_eval.py` (991 lines) and `tests/test_decision_eval.py:PredictionTimeJoinTests`
(55 tests), plus a `JOIN_VERSION` row in `release_gate.VERSION_SOURCES`. Suite 4629 -> 4684.

**Read-only proven BY CONSTRUCTION, which is the right shape for this acceptance term.** Not
"does not write" but "cannot": imports are exactly `datetime, importlib, pathlib, re, types` — no
`os`, `json`, `shutil`, `subprocess`, `tempfile` — there is no write-shaped call anywhere, and NO
PUBLIC FUNCTION TAKES A DIR, PATH, FILE, STORE OR ROOT PARAMETER. I verified all three by AST
myself. A mutation injecting `trial["adjudication"] = ...` — which is what `workflow_eval.build_card`
actually does — is caught by a byte-identity check on the inputs after a join.

**Future exclusion is a UTC comparison, not a lexical one, and I checked the cases that
distinguish them.** `09:30-04:00` against `12:00Z` is 13:30 UTC and places AFTER, where a string
compare says before; `14:30+04:00` is 10:30 UTC and places BEFORE, where a string compare says
after. Both correct. This is the one that matters: a lexical comparison leaks a post-prediction
fact into the feature set, which is label leakage, and every downstream metric would look better
than reality. A zoneless stamp is `unknown-time` rather than assumed local, and with
`prediction_at=None` NOTHING is a feature, because "before" has no meaning without an instant.

**The causal fence is structural.** `RELATIONS` is `('preceded', 'co-occurred', 'followed')` —
there is no causal member to set. Every recovery pairing carries `relation: "followed"`,
`causal_claim: None` and `NO_CAUSAL_CLAIM`, and `assert_no_causal_claim` sweeps emitted rows using
D09's own punctuation-reduction idiom, so `caused_by`, `c.a.u.s.e.d`, `due-to` and
`root.cause.causedby` are all caught. I confirmed all four.

50 mutations, control first, zero survivors. **Three survived the first batch and one is a variant
not seen before in this kit: two `_copy` calls MUTUALLY MASKING each other** because a second copy
one level out made either one individually deletable. The fix was to remove the outer copy and
keep exactly one at the point it is observable — not to keep both. Same family as D13's "a guard
that hides another guard is worse than no guard."

**A FIFTH repo-wide sweep exists that no carry-forward had listed.**
`tests/test_decision_policy.py:1035` asserts no `bin/*.py` except `decision_policy.py` contains
the strings `select_action`, `state_from_routing`, `state_from_ladder` or `selection_state` —
INCLUDING IN COMMENTS, same text-match shape as the `"evals"` trap. `decision_eval` is clean
(verified). **D17 will turn this red deliberately when it wires a driver seam — that is the
designed signal, not a break.**

Carry-forward handled rather than ignored:
- F3 NOT resolved, as instructed. `join_row(record=None, refusal=...)` yields an unresolved +
  censored row with `decision.record` stays `None` and the reasons validated against
  `decision_policy.REFUSAL_REASONS`, so no record shape is invented. The open architect decision
  stands.
- F6 handled: `DecisionResult.note` is deliberately NOT carried. `decision.note` is always `None`
  and `note_withheld` states why. A test asserts the note text is absent from `json.dumps(row)`.
- The `attempt_history._duration` private-reach smell was NOT extended; `decision_eval` reaches
  only `RECORD_FIELDS` and `DURATION_BASES`, pinned by AST test. **The public seam it wishes
  existed: `attempt_history.duration(basis, seconds, source)` and `cost(...)` constructors.** That
  would remove both the contract module's smell and this module's literal fixture. Worth a task.
- `duration_by_basis` GROUPS and never totals; nothing in the module sums anything.

Limitations stated rather than found later:
- **`prediction_at` is caller-supplied and may be None, because no `DecisionRecord` carries the
  instant a decision was taken** — the record versions WHAT was decided, not WHEN. It refused to
  derive it from the dispatch event's `ts`, because that instant is after the decision and would
  silently place the decision's own consequences before it. Fixing properly means a
  `CONTRACT_VERSION` bump to record the decision instant.
- "The outcome" is a DEFINED choice, not a discovered fact: the last attempt fact after the
  prediction for that run/task, described as what followed and never as what the decision produced.
- `_history_record` proves SHAPE, not ORIGIN — a hand-built dict using only `RECORD_FIELDS` names
  is accepted.
- `trial_facts`' per-fact `_copy(ref)` is depth, not a proven guard; no test can distinguish its
  deletion today because a ref is a flat dict of scalars. Reported rather than claimed as enforced.
- Zero production callers. `release_gate` IMPORTS the module to read its version and calls nothing.

## D15 — Calibration reports (sonnet, depends D14)

Calibration reporting appended to `bin/decision_eval.py` (991 -> 1447) plus
`CalibrationReportingTests` (42 tests) beside D14's class, which is AST-identical at 58 methods.
New `CALIBRATION_VERSION` registered separately. Suite 4684 -> 4726.

**"No private default fitting" is structural, and the precise claim is worth stating carefully.**
`calibration_artifact` — the only object that could carry fitted parameters — accepts ONLY
identity: target, provider, domain, dataset, method, fit_partition, sample_count, model,
fitted_at, note. Every one is a label, a count or an instant, and the signature is keyword-only,
so I confirmed that `observations`, `predictions`, `labels`, `pairs` and `samples` are all
`TypeError`. There is no parameter a fit could be computed from.

Do NOT overclaim this as "nothing sees the data": `calibration_report` necessarily receives rows
carrying both distributions and resolved labels, because that is what computing Brier or log loss
requires. The fence is that nothing converts them into parameters, and the artifact that would
hold parameters cannot be built from them. What would have to be added for fitting to exist: a
function taking (predicted, actual) batches and returning parameters. That is optional task O03
and does not exist anywhere in the module.

**The three-way metric status is the honesty rule where it matters most.**
`METRIC_STATUSES = ('computed', 'not-applicable', 'insufficient-evidence')`, floor 20. I verified
all three: 3 rows gives `insufficient-evidence` with `value=None` and `n=3` still visible; 40 rows
gives `computed`; rows with no distribution in the requested field give `not-applicable` with
`n=0`, genuinely distinct from sparse. A `0.0` Brier score reads as PERFECT CALIBRATION, which is
the most flattering possible misreading of "we had no data" — so `None` rather than 0 is
load-bearing here in a way it is not for most fields.

Arithmetic checked independently, not taken from the report: Brier 0.08 is exactly
(0.8-1)^2 + (0.2-0)^2, and log loss 0.22314355131420965 is -ln(0.8) to ~1e-16.

**It implemented natural log FROM SCRATCH rather than importing `math`, because D14's import-pin
test forbids new imports and it refused to modify D14's test.** That is respecting a fence at real
cost, and a hand-rolled log is exactly the kind of thing that produces plausible wrong numbers, so
I checked it: worst absolute error 8.9e-16 (machine epsilon) across 2013 samples from 1e-12 to
1.0. Effectively exact in double precision.

Partition leakage is refused: a calibrated report must declare its own `report_partition` and is
refused when that equals the artifact's `fit_partition` — validating a calibrator on the material
it was fit on is the fit read back, not held-out evidence. Same principle as D06's held-out
manifest.

23 mutations, control first, all red. Guards proven include: field-must-be-raw-or-calibrated;
artifact-cannot-cite-raw; artifact-target-mismatch; partition-leakage; the never-fall-back-to-raw
guard; brier not-applicable-on-empty vs sparse-insufficient as SEPARATE branches; log-loss floor
clipping; per-threshold sparsity; and the causal-fence wiring proven by monkeypatch rather than by
the sweep function merely being present.

Limitation worth carrying: `fit_partition`/`report_partition` are caller-supplied STRINGS compared
for inequality, NOT validated against `workflow_eval.PARTITION_ROLES`' real vocabulary
(`development`/`calibration`/`promotion`/`audit`). That is a deliberate tradeoff — reaching that
vocabulary would have broken D14's sibling-reach pin, which allows only `RECORD_FIELDS` and
`DURATION_BASES`. So two misspelled-but-different labels pass the leakage check. A later task
wiring `decision_eval` to real partitions needs either a new sibling loader or a relaxation of
that pin, deliberately.

`vendor_confidence` is read by no metric, which is correct: the decision contract already
establishes it is not a probability of task success.

## D16 — Context candidates (opus, depends D13)

New `bin/decision_context.py` (793 lines) and
`tests/test_decision_context_repair.py:ContextCandidateTests` (85 tests), plus a
`CONTEXT_VERSION` row. Suite 4726 -> 4811.

**It declined to modify the seam, and it was right to — my brief overstated the requirement.**
I briefed this as "THIS TASK MODIFIES EXISTING FILES" and pinned `bin/graph_ground.py` and
`bin/graph_brief.py` by checksum. The brief says "Own the existing ... seam", which GRANTS the
right to change it and does not require it. Everything D16 needs was already on the seam's public
surface (`repo_state`, `load_graph_bytes`, `freshness` with its existing `dirty_now` /
`uncovered_changed`, `impact` with its existing hub marking, `search`), so it built beside the seam
and read it, the way `decision_eval` reads `attempt_history`. Putting a new privacy vocabulary
inside `graph_ground.py` would have added a second concern to a module whose regression suite I
had just declared immovable. Both seam files verified byte-identical to their pinned checksums;
all three regression guards green at 134 tests, unmodified. **Bounded adaptation, flagged
prominently rather than done quietly — and the flag is the part that made it acceptable.**

**Graphify invariant holds.** `graphify` appears exactly twice, as the fence written down
(mirroring the seam's own hygiene test), never in an argv position. No `shutil.which`, no
`uv tool install`, no `pip install`, no `subprocess`. Every test uses a synthetic `graph.json` in
a temp dir with a canned git. `/graphify-out/` still gitignored at line 43.

**Determinism is proven the only way it can be.** Set-iteration order only shows up across
PROCESSES, so the test spawns child interpreters under `PYTHONHASHSEED` 0/1/12345, asserts
`returncode == 0` AND non-empty stdout BEFORE comparing — otherwise the comparison is satisfied by
two identical empty strings. Plus byte-identity across repeated builds, across six seeded shuffles
of node and link order, and a walk refusing any `set`/`frozenset` in the manifest. The ordering
test additionally asserts more than one kind is present so it cannot pass vacuously.

60 mutants, control first, zero survivors. **Seven survived the first batch and EVERY ROOT CAUSE
WAS THE FIXTURE, not the code** — the clearest demonstration yet of refinement 2. The instructive
ones:
- The total-order tiebreaker survived because no two rows were ever TIED: every fixture node
  differed in symbol or path, so the sort was already total. Fixed by adding two nodes sharing a
  file, location and label but reached from different parents — the only shape where input order
  decides the survivor.
- The sort ITSELF survived because no test asserted an ORDER. Byte-identity is satisfied by any
  deterministic order, so a mutant sorting by path instead of by kind was invisible. **Determinism
  and correct ordering are different properties and need different tests.**
- The fence's dotted-key branch survived because every key tested was already caught whole —
  `_alnum("depends.on")` is `"dependson"`, itself a banned token — so the `.split(".")` branch
  never ran. Fixed with `context.depends`, `graph.requires`, `edge.blocks`, whose whole spellings
  are innocent.
- The reference version check survived because the payload had no digest, so the sha check refused
  first with the same code. Same masking shape as D12's anti-laundering guard.
- One (`M27`, bare-string refusal) is GENUINELY redundant — the list/tuple check one line below
  refuses a `str` with the same code. Kept because it exists to SAY WHY ("a bare string iterates
  one character at a time") and the test pins that MESSAGE rather than the code. Reported as a
  diagnostic pinned by its words, not claimed as a second refusal.

The dependency fence is three-layered: no vocabulary member is dependency-spelled and every
candidate carries `authority: None`; an extractor's own word rides under `edge_label` beside
`edge_label_note` and a test rewrites every fixture edge's relation to literally `depends_on` and
asserts it appears as a VALUE and never a key; and `assert_no_dependency_claim` sweeps 26 tokens
including `safe_to_parallel` and `parallel_write`, proven WIRED by a recorder that sees a body with
no `sha256` yet (so the digest covers a swept body) and by a raiser that kills the build.

Limitations stated rather than found later:
- **The privacy PREVENTION layer covers prefixes only, and it refused to write the sentence that
  hides this.** A credential-shaped suffix or dotted path cannot be expressed as an exclude, so the
  bounded scan has already READ such a file by the time its path is judged. What IS guaranteed:
  neither the path nor any byte reaches the manifest, asserted against the whole serialised
  manifest rather than the field meant to hold it. The module docstring says this in those words.
- `kind-not-in-graph` will fire on most real runs, because a graph of code symbols does not index
  configuration — so the scan usually runs. Named honestly rather than folded into "graph not
  fresh".
- `excluded.duplicates` counts two different collapses (a scan hit in a file the graph named, and
  two indistinguishable graph rows); telling them apart needs two counters.
- The dependency fence sweeps KEYS only, deliberately: a graph whose own relation vocabulary
  contains `depends` puts that string in `edge_label` as a VALUE and is not refused, because
  refusing it would let a third-party extractor's word break a manifest.
- `M59` is killed structurally (AST sibling-reach pin) rather than behaviourally, because the
  fixture has no second store directory whose fate would differ.
- Zero production callers. D17 is what wires it.

## D17 — Context-repair policy (opus, depends D07, D16)

`bin/decision_policy.py` 1249 -> 1858, a third section after D13's, plus two stdlib imports.
D11's and D13's halves byte-identical. `ContextRepairPolicyTests`, 49 tests, beside D16's class
which is untouched. Suite 4811 -> 4860. No version constant, following D13: nothing here is
persisted.

**The fifth sweep did NOT go red, because it did not wire a driver — and it flagged the brief
tension rather than resolving it quietly.** The brief says "extend `bin/decision_policy.py` and
the existing driver recovery seam". It read "the driver recovery seam" as the seam representation
D13 already built INSIDE that file — the `(baseline, ladder)` pair `state_from_ladder` wraps —
whose ladder shape `plan_context_repair` carries. No driver was modified, and it wrote its OWN
equivalent sweep (`test_nothing_in_this_repository_plans_a_context_repair`) carrying the same
"when this list stops being empty, that is the signal" docstring. If the architect meant a driver
edit, that is a scope decision and would deliberately turn the sweep red. Second time in Phase 4
an implementer has correctly declined to widen scope on an ambiguous "own/extend the seam" phrase.

**"No default" is structural in the strongest available sense: `plan_context_repair` has TEN
required parameters and ZERO with defaults.** Nothing is permissive by omission — every fact is
stated or the call fails — and no parameter is spelled `enable`/`allow`/`force`/`on`. I confirmed
both by signature inspection. Only a `BundleResolution` whose parameters carry
`recovery.contract_context_package` as LITERALLY `True` (`is True`, not truthy) puts a repair in
force, proven against `1`, `"yes"`, `[1]`, `1.0` with a `True` control showing the fake shape is
otherwise accepted.

**Five things would have to change for a repair to actually run, and I verified the strongest one
myself.** `kit_contract.OPERATION_CAPS["retry"]` draws down `('max-dispatches', 'max-model-calls')`,
and **NO KIT IN THIS REPOSITORY DECLARES `max-model-calls`** — only `aesop-fold` and `docs-site`
declare a budget line at all, and neither includes that cap; `decision-improvement-v1` declares
none. So even with a pinned, approved bundle, EVERY kit refuses with `dispatch-cap-undeclared`.
The other four: nothing calls `plan_context_repair`; no tracked JSON or TOML sets that parameter
true (swept, and proven non-vacuous by planting one in the mutation tree); the bundle must survive
D11's resolver including a verified capability; and a coordinator would have to mint a SECOND
admission grant distinct from the failed attempt's and dispatch under it, which no path does.

`REPAIR_REASONS` is a third closed vocabulary of 17 codes, verified disjoint from both
`SELECTION_REASONS` and `RESOLUTION_REASONS`. Caps are named `dispatch-cap-*` rather than
`budget-*`, following D13's `budget_admission` precedent, because `budget` is in `BANNED_FIELDS`.
`_admissible(action, facts)`'s pinned parameter list is untouched — that pin is what makes
"confidence cannot bypass a denial" structural.

**D16's forward fence is now wired, with a subtlety worth keeping.** `assert_no_dependency_claim`
is handed a PLAIN DICT, because a `MappingProxyType` is not a `dict` and a sweep given one would
walk nothing and pass on every input. The maps are frozen only AFTER the sweep. That is the
vacuity pattern appearing in a new disguise — not an empty collection, but a type the walker
silently skips.

59 mutations, control first, zero survivors. Both stub controls are real, which is what stops the
refusal tests being vacuous: a planner stubbed to always REFUSE fails 16 of 49; one stubbed to
always ADMIT fails 25 of 49. One survivor in the first batch, fixture-caused again: `_strings`'
per-item check survived because every list passed contained well-formed strings, so a different
guard refused first with a different code.

Open questions and limitations, stated rather than left to be found:
- **`verification` is the ONLY repairable class, which excludes ledger class `model` too.** That
  reads the brief's "excluding ... model failures" literally and matches the shared PLAN's "do not
  change model and context at once". **If the architect meant only UNAVAILABLE-model (ledger class
  `config`), then `model` belongs in `REPAIRABLE_FAILURE_CLASSES`** — a one-tuple change, flagged
  rather than assumed.
- The duplicate guard is exactly as good as a coordinator's record-keeping: `repairs` is
  caller-supplied and nothing in the repo records a repair id. It cannot find a repair nobody
  recorded.
- `_manifest` reads D16's manifest keys directly (`status`, `candidates`,
  `freshness.revision.now`) because D16 exposes no accessor. A rename there breaks this at RUN
  time, not import time.
- `_failed_attempt` validates against `attempt_history.RECORD_FIELDS` — the same tuple
  `decision_eval._history_record` uses. **One authority, two implementations, nothing pinning them
  equivalent: the Phase 3 review's F8 shape, now at a second site.**
- `MAX_REASON_CODES` is deliberately NOT applied to a plan's reasons, because all 16 refusals can
  fire at once and truncating to a record's ceiling would hide one. A plan is not a
  `DecisionRecord` — which is also why it has no version constant. If D18/D20/D23 persist a plan,
  that question lands alongside the still-open F3.
- `_no_dependency_claim` translates only the `authority-field` code across the loader boundary and
  re-raises anything else untouched; both branches pinned. If D16's sweep ever raises a different
  code, a caller catching this module's `ContractError` would miss it.

## D18 — Three-arm protocol (opus)

Generates an experiment SPECIFICATION and runs nothing. The architect question — whether to wire
D08's gate — was answered by NOT wiring it: `CONFINED_DISPATCH_WIRED = False` in
`bin/workflow_eval.py`, a blocker derived from code rather than from anything a caller supplies.
That was the right call. D08's gate applies no confinement and ledgers nothing, so wiring it
as-is would have produced a real, unconfined, unledgered dispatch under an envelope saying the
profile is enforced.

- The flag is pinned in BOTH directions, and I killed mutants each way in my own temp tree
  (control unmutated first): flipping the flag alone dies; making the gate genuinely call
  `ep.wrap_argv`, `ep.ProtectedProfile` or `attempt_ledger.append` without flipping it also dies.
  Whoever wires a live protected trial flips it in the same edit that adds both halves.
- **`require_runnable` trusted the dict it was handed** — caught in my verification, not by the
  suite. It read `spec["content"]["blockers"]` without re-deriving the content digest, so a
  fabricated `{"sha": ..., "content": {"blockers": []}}` discharged every precondition, including
  the code-derived one, without touching the flag. Fixed: `content` is re-hashed with the same
  `_sha(_canonical(content))` `build_trial_protocol` uses, and a mismatch is refused before a
  blocker is read. **The general lesson for D19–D34: an enforcement point must consult the thing
  it enforces.** A guard can be genuine, derived and mutation-proven and still be discharged at
  the door.
- A forged spec gets NO code in `PROTOCOL_BLOCKERS`. That vocabulary is closed and means "a
  precondition a live run must satisfy"; a fabricated input is not an unsatisfied precondition.
- Limit, stated not glossed: content addressing detects ALTERATION, not authorship. Emptying the
  blockers AND recomputing the sha is not caught. No test pins that weakness as expected
  behaviour, deliberately.
- Phase 2 F5 is CLOSED: `manifest_summary` now carries `NOT_ENFORCEMENT_LABEL`, so `results.json`
  gets the disclaimer beside its partition counts. This changes D06's function — the one
  non-additive line in the file.
- Phase 2 F4 is closed at the NAMING level only: `live_requirements` lists `held-out-evidence` and
  `protected-profile-certified` side by side with reciprocal `pairs_with`, and satisfying either
  alone leaves the other blocking. They still never compose in a live path, because there is none.
- D06's product finding is honoured, not assumed away: an empty held-out partition yields
  `no-held-out-evidence`, whose detail names the no-`gh` → fix-commit-message → contagious
  quarantine chain. The fixture builds that case through `build_manifest` itself.
- **Zero production callers** for all 14 new public symbols; `release_gate` reads
  `TRIAL_PROTOCOL_VERSION` and calls nothing. The suite says the unit works, not that anything
  invokes it — D14's and D17's disclosure, again.
- `arm_accounting` proves SHAPE, not ORIGIN: its records are caller-supplied, which is why
  `initial_attempt_reused` is required rather than inferred.

Two traps worth carrying forward, both mine:

- **Prose describing a guard satisfies a text scan looking for it.** My own verification asserted
  the deleted guard was absent by scanning the function body for `_sha(_canonical(` — and matched
  the docstring paragraph explaining the check. D08's gate docstring likewise already contains
  `wrap_argv`, `ProtectedProfile` and `ProtectedLayout` in its "What it does NOT do" section, so
  any future pin on those must be AST-based or it is vacuous from birth.
- **Inspect the mutant, never trust its exit code.** My first deletion attempt kept the guard it
  meant to remove and "survived"; the second, verified absent, killed 11 tests + 4 errors. Fourth
  invalidated mutation run in this kit, all from a tree or edit not being what I assumed.

Process: doc-drift tests compare against the real committed tree, so a suite run concurrent with
any other run produces phantom failures in `test_docs_build_cli` / `test_docs_site` /
`test_codex_discovery_docs`. Seen again here. Runs stay sequential.
outcome: D18 model=opus attempts=2 result=pass review=revised run=2026-09-16-aa6e

## D19 — Outcomes and stopping (sonnet)

`recovery_report` in `bin/decision_eval.py`, with `RecoveryReportTests` in D18's test file.
Five acceptance terms, each mutation-proven by deleting the guard and watching exactly the
matching test go red.

- **F8 was answered better than the two options I offered, and this is the pattern to reuse.**
  D18's `arm_accounting` already enforced "zero ratio undefined" and "bases separate". Rather
  than calling it across the module boundary (which `decision_eval` never does for any sibling)
  or writing a second implementation pinned equivalent, `resource_evidence` takes an
  `arm_accounting` result as an ARGUMENT, relays every field verbatim, and REFUSES to relay
  evidence violating either invariant. There is no second computation, so there is nothing to
  diverge — verified: the only `cost_per_accepted_usd` mentions in the module are a key name and
  the refusal, with no arithmetic. **Relay-and-refuse beats both reuse and equivalence-pinning
  where a module must not reach for a sibling.**
- The guards have only ever fired against hand-forged dicts, because the real `arm_accounting`
  never produces a violation. That is a defensive relay guard, not a masked one; the forged
  tests prove reachability and deleting the call turns them red.
- **`operator_plan` claimed more than its scope, and I sent it back.** With its six declarations
  supplied it reported `plan-complete` / `blocks_promotion: False` while `primary_endpoint`,
  `sample_size` and `independent_evaluation` were undeclared and unmentioned. Now it carries
  `not_covered` naming those three with owner `workflow_eval.live_requirements`, a `scope_note`
  present unconditionally, and the two fields renamed to `own-declarations-complete` /
  `blocks_promotion_on_these_fields`. The old key is gone, not shadowed.
- The drift pin is the part that mattered: `shared | uncovered == set(OPERATOR_DECLARATIONS)`
  and `shared & uncovered == set()`. **My fix brief named only two uncovered fields; the exact
  partition found the third.** A test written to my list would have been complete by
  construction and wrong.
- `RECOVERY_REPORT_VERSION` is a NEW constant with its own `VERSION_SOURCES` row;
  `JOIN_VERSION` and `CALIBRATION_VERSION` untouched at `/1`. No envelope was bumped.
- Adding the `VERSION_SOURCES` row staled `docs/RELEASE.md`, and regenerating that staled
  `docs-site/deep-dives/release.md`. Both fixed by their OWN generators, never by hand. That
  two-step chain will fire for every future task that registers a version.

**This is the THIRD instance of the Phase 2 F4 shape** — held-out vs isolation, then D18's
`live_requirements`, now `operator_plan`. Each half is individually rigorous; the composition is
what keeps going missing, and the tell is always a verdict field whose NAME is broader than the
check behind it. Carry that to Phase 4 review as one pattern, not three findings.

Left open, volunteered rather than found: no production path calls any of D19's functions;
"caps" (resource ceilings) is not surfaced in the report though the brief's first sentence names
it; `quality_regression` is untested for both-sides-insufficient-evidence; `candidate_tally` and
`slice_coverage` accept caller-assembled data with no manifest-backed origin, so they prove
counting logic, not that the counted data came from anywhere real.

Process: **concurrent full-suite runs get one KILLED for memory, and a killed run looks like a
clean one if you only grep for FAIL lines.** A subagent's own background suite collided with
mine here. Read the exit status and the `Ran`/`OK` line; the serial rule covers subagents'
background work too.
outcome: D19 model=sonnet attempts=2 result=pass review=revised run=2026-09-16-aa6e

## Phase 4 independent verification (D14–D17, owed since they were marked done)

Four verifiers ran adversarially against committed HEAD, each constrained to targeted modules.

**D17 — ACCEPT.** 49 tests, all load-bearing under the verifier's own mutations: the
`REPAIRABLE_FAILURE_CLASSES` membership check (7 failures when neutered, and `model`/
`environment`/`permission` each produce `failure-class-excluded` ALONE, so it is not riding behind
another guard), `_repair_in_force`'s `is True` identity check, the dispatch-cap guard, and the
duplicate-repair guard. All ten defaultless parameters are genuinely consulted.

**KIT-LEVEL FINDING, confirmed by me directly — two of the seven failure classes have no
producer.** `attempt_ledger.CLASSES` declares `model` and `verification`, but `classify_dispatch`
can only return `infrastructure`, `None`, `auth`, `config`, `permission`, `unknown`. It never
returns either of the two that `RECOVERY` maps to `escalate`. The verifier reproduced the end to
end case with a REAL ledger — a dispatch that succeeds and whose verify fails projects
`result=verify-failed, failure_class=None` — and fed it to `plan_context_repair`, which refuses
with `failure-class-unestablished`. **So D17 gates exclusively on a value nothing in this
repository can currently emit.** That is a sixth and more fundamental reason "cannot run today at
all" holds, beyond the five already recorded. Not a D17 defect: D17 correctly consumes what
`attempt_history` projects and classifies nothing itself. **It lands on D23, D24 and the D30
handoff — a repairable class with no producer must be stated as a live gap, not implied to work.**

**Open question from D17 — CLOSED: leave `model` OUT of `REPAIRABLE_FAILURE_CLASSES`.** A context
repair hands back interfaces/consumers/config and retries on the SAME model, which only answers a
failure that produced a genuine checkable attempt falling short for a missing-information reason.
A `model`-class failure is a failure to produce a valid attempt at all; handing it a context
package changes context and spends the single permitted repair on something context cannot fix,
foreclosing it from a later genuine verification failure on the same task. The shared PLAN's own
rule — do not change model and context at once — points the same way. Note the distinction is not
observable today anyway, per the finding above.

**D16 — one CONFIRMED gap, being fixed.** `assert_no_dependency_claim` walks only concrete
`dict`/`list`/`tuple`, so it silently passes on `MappingProxyType` (top level AND nested),
namedtuple, dataclass, generator and set — each carrying a real `depends_on` key. I reproduced all
six against the unmutated module with plain-dict controls refusing correctly. Not live-exploitable
today because both callers hand it a fresh plain dict, and D17 deliberately sweeps BEFORE freezing
— but the hazard is already shaping other code as a caller-side workaround, and the module
docstring states the fence categorically. Bounded candidates, the closed `CANDIDATE_KINDS`
vocabulary, the privacy/redaction layer and the keys-only design (a `relation` VALUE of
`depends_on` is deliberately allowed) all verified sound.

**D14 — ACCEPT with one gap queued for fix.** Future exclusion survives lexically misleading UTC
offsets; feature-into-label leakage is genuinely blocked (`resolve_label` never reads
`features["at_prediction"]`); the `_copy` fix for the earlier mutual-masking pair is confirmed
load-bearing. Two findings: (a) `join_row`'s closing `assert_no_causal_claim(row)` is decorative —
deleting it kills nothing, because nothing `join_row` builds can trigger it; disclosed in-source
as forward insurance and the function itself is well tested, but one test pinning the return path
converts decoration into an invariant. (b) **`actions.outcome` is populated when no action was
taken.** I reproduced it: a refused decision gives `actions.taken=None` while `actions.outcome` is
a full `pass` record built from what merely FOLLOWED — in the same object where every alternative
correctly reports `outcome: None` and `recovery.intervention` is correctly `None`. That internal
inconsistency is what makes it a defect rather than a design choice.

**D15 — REVISE, two CONFIRMED findings, being fixed.** (a) `_reliability_bins` is the only metric
helper taking no sample floor — its four neighbours all take `min_n` — so on the SAME n=1 evidence
where `classification` and `brier` correctly say `insufficient-evidence`, a bin reports
`empirical_accuracy: 1.0`. (b) `_validated_artifact`, the path every real caller uses, checks an
artifact's field set and version stamp but never its VALUES: I confirmed it accepts
`sample_count=-999`, blank provider and `fitted_at="not a timestamp at all"` verbatim, while
`calibration_artifact` refuses exactly those. Shape enforced, content not, on the path that
matters.

**TWO SCOPING ERRORS IN MY OWN BRIEFS, both caught by verifiers who refused to scope-creep.** I
attributed `_ln`/`METRIC_STATUSES`/`MIN_METRIC_SAMPLES` to D14 (they are D15's; the file was 991
lines at D14 and ended at `join`) and `MAX_FALLBACK_DEPTH` to D17 (it landed in `e2cc9d6`, a task
earlier). Cause: carrying a constants list forward in a summary and attributing entries to
whichever task is being briefed. **Verify a constant's owning commit with `git log -S` before
putting it in a brief.** No coverage was lost either time, but a verifier that obliged instead of
objecting would have spent its budget on the wrong module.

### Phase 4 verification fixes — all three landed, suite 4983 OK

**D16 fence hardened.** The sweep now descends `Mapping`/`Sequence`/`Set`, accepts JSON scalars,
and REFUSES what it cannot inspect rather than passing it. I re-probed all twelve behaviours: the
six silent passes now refuse, and every deliberate allowance still accepts. Two decisions worth
keeping:
- A namedtuple is REFUSED rather than unpacked via `_fields`, because `json.dumps` emits it as an
  array and drops the field names — accepting it would certify names that vanish from the
  artifact's own bytes.
- **The fixer found a case I had not specified: `dict.items()` is a `Set`**, so a naive
  descend-Set rule walks a `MappingView` and reads a real `depends_on` KEY as a string in value
  position. `{"retry": {"depends_on": "x"}.items()}` was accepted before and refuses now.
- `{("depends_on", "x")}` is STILL accepted, correctly: a set cannot contain a mapping (nothing
  hashable is one), so that is a value, the same allowance as `relation: "depends_on"`. Proof the
  set is nonetheless genuinely descended: a set CONTAINING a namedtuple now refuses. "We do not
  walk it" and "we walk it and it is legitimately fine" look identical from a green test; only the
  second is a fence.
- D17's sweep-before-freeze at `bin/decision_policy.py:~1848` is no longer load-bearing, since the
  sweep handles a `MappingProxyType` directly. Harmless, left in place; its NOTES entry now
  describes a hazard that is gone.

**D15 fixed.** The floor is threaded into `_reliability_bins` the way its four neighbours take it;
a sparse occupied bin carries an existing `METRIC_STATUSES` value with `n` and `mean_confidence`
still visible and the outcome-estimated quantities nulled. `_assert_artifact_values` is ONE
helper called by both the constructor and the consumption path — no second implementation, so
nothing to drift. M6/M7 killed the asymmetry in both directions.
- **Accepted judgement call: the bin floor is now 20 PER BIN across 10 bins**, so even 200
  well-spread rows leave most bins `insufficient-evidence`. Strict, but the honest reading for a
  module whose job is refusing to invent numbers, and the status is visible rather than silent. A
  smaller bin-specific floor is a DESIGN decision for the architect, not a bug fix.
- **Accepted: `mean_confidence` survives a sparse bin** — it re-reports what the predictions said
  rather than estimating from outcomes, the analogue of `successes` surviving an
  `insufficient-evidence` rate.

**D14 fixed — and the "decorative guard" verdict was WRONG, which is the lesson.** When
`actions.taken is None`, `actions.outcome` is now null with a `why` note in the alternatives' own
idiom; `outcome_evidence` still carries the raw fact, asserted rather than assumed. But the second
finding inverted: `assert_no_causal_claim` in `join_row` is NOT decoration. `_envelope` copies
`holdout.manifest_ref` into the row VERBATIM with no shape validation, so a causal key reaches a
row today by that route, and `join_row`'s call is the only thing refusing it. M1 confirms the new
test kills that mutation and nothing else does.
- **A guard that survives its own deletion means EITHER it is decoration OR the tests never found
  its input route.** I collapsed those two into one conclusion and would have accepted a real
  guard as ornamental. Look for the route before calling it decoration.
- **`JOIN_VERSION` deliberately NOT bumped.** It appears outside `decision_eval.py` only in
  `release_gate.py`'s registry (a string read) and in tests; nothing persists a join document and
  nothing outside this kit reads one, so a bump would strand no reader while churning every
  fixture pinning the stamp. The repo rule cuts the same way — bumping an envelope constant is
  what discards data. **Honest caveat for D30: `polytropos.decision-join/1` now denotes a row
  shape different from before (`actions.outcome` narrowed, `actions.why` added). Nothing consumed
  the old shape, so nothing is stranded, but a release must state that `/1` covers both.**
outcome: D14 model=opus attempts=2 result=pass review=revised run=2026-09-16-aa6e
outcome: D15 model=sonnet attempts=2 result=pass review=revised run=2026-09-16-aa6e
outcome: D16 model=opus attempts=2 result=pass review=revised run=2026-09-16-aa6e
outcome: D17 model=opus attempts=1 result=pass review=clean run=2026-09-16-aa6e

## Phase 5 red preconditions — captured at 559a51b, before any Phase 5 task started

Evidence that cannot be obtained once the work exists, so it is taken up front (as it was for
Phases 3 and 4). Every Phase 5 verify command exits 1 at this commit, and all three test files it
names are absent from the tree:

    D20  test_decision_workbench.WorkflowEvalOwnershipTests    exit=1
    D21  test_decision_workbench.BoundedProposalTests          exit=1
    D22  test_decision_approval.ExactApprovalTests             exit=1
    D23  test_decision_activation.ProtectedActivationGateTests exit=1
    D24  test_decision_activation.PolicyEvidenceReportTests    exit=1

    tests/test_decision_workbench.py   No such file
    tests/test_decision_approval.py    No such file
    tests/test_decision_activation.py  No such file

Pins at the phase boundary: `bin/workflow_eval.py` 4275 lines
`3653a08bb4a9ed9a1784336173d4bc42`, `bin/decision_policy.py`
`5768addb61293c3670adb0e229e2384f`, `bin/kit_contract.py`
`8644823d02e36f973ac3522ff51a3149`.

**PLAN.md's fence for this phase, re-read from disk at the boundary: "Shared-module changes run
sequentially; phase review precedes the next phase."** All five of D20–D24 extend
`bin/workflow_eval.py`, so none of them may be dispatched in parallel with another — this is the
one phase where the kit explicitly forbids the fan-out the loop otherwise allows.

Carry into Phase 5, from D19's answer to the F8 shape: when a task must honour an invariant that
another owner already computes, prefer **relay-and-refuse** — take the other owner's result as an
argument, relay it verbatim, and refuse to relay what violates the invariant — over either
reaching across for a function call or writing a second implementation pinned equivalent. It
leaves nothing to drift. D20–D24 will face this question repeatedly against `workflow_eval`.

## Phase 4 review — adjudicated

**The "one pattern, three instances" reading I carried was WRONG, and the correction is
load-bearing because the two shapes need opposite fixes.**

- **Shape A — the name is broader than the check.** Tell: a field, docstring or vocabulary
  promises categorically what the code inspects partially. Fix: scope the name, pin the scope with
  an exact-partition test. D19's `operator_plan` is this and was fixed correctly.
- **Shape B — the enforcement point is not on the path, and the evidence it consults is
  unauthenticated.** Tell: "zero production callers" plus a sibling entry point that bypasses.
  **Fix: a call site and a re-derivation, never a name.** Phase 2's F4 is this. D18's
  `live_requirements` is this.

Merging them is what made a Shape B defect look like it was closed by renaming. F4 was never
"closed at the naming level"; it was RELOCATED to a checkpoint that is off the path and thin.

**F1 HIGH — CONFIRMED by me, fixing now.** Four of five live-run preconditions are discharged by
unauthenticated caller dicts. My AST check: `trial_cohort`, `_certification_evidence`,
`live_requirements`, `build_trial_protocol` and `require_runnable` call NONE of
`verify_manifest` / `require_held_out` / `manifest_digest` — all three of which are defined **in
that same module**. The `held-out-evidence` row names `workflow_eval.require_held_out (D06)` as
its owner, reports `satisfied: True`, and never calls it. `trial_cohort` sets `frozen: True`
because a `manifest` argument was PASSED, not because anything is frozen. A forged manifest with
`sha = "0"*64` is accepted and its declared sha is never compared to its derived one.
**This corrects my own sign-off.** I accepted D18's "emptying blockers AND recomputing sha is not
caught" as a properly disclosed limit. True but misframed: content addressing is not the weak
link, because `build_trial_protocol` computes a CORRECT digest over forged inputs. The
unauthenticated evidence sits inside the digest. Keep the digest check; add the consultation.

**F2 HIGH — CONFIRMED by me, queued behind F1 (same test file).** Two halves. (a) D19's
`recovery_report` closing `assert_no_causal_claim` is unpinned: replacing it with `return report`
leaves 804 tests green, yet it IS load-bearing — `full_task_study`, `comparisons` and `slices`
are copied verbatim from caller arguments and this call is the only refusal. Same inversion the
D14 verifier hit. (b) **`CAUSAL_TOKENS` misses the ordinary spellings.** My probe: REFUSED
`caused_by`, `because`, `due-to`, `explains`, `therefore`; **ACCEPTED `cause`, `root_cause`,
`rootcause`, `led_to`, `resulted_in`, `triggered_by`, `effect_of`, `attributable_to`**. The list
has `caused`/`causedby`/`causes`/`causal` but not the base `cause`. D14's four demonstration
spellings each happened to contain a listed token, which is exactly why the hole stayed invisible.
Compare D16's `DEPENDENCY_TOKENS`, which does carry base forms.

**F4 MEDIUM — AMENDS the Phase 5 carry-forward I wrote above. Relay-and-refuse is still the right
precedent, but ONLY with two conditions it currently lacks:**
1. **an exact-partition or equality test against the owner's own constant** — D19 already proved
   this works, and that exact test is what found the third uncovered field my fix brief had
   missed. D19 simply did not apply its own template to `RESOURCE_BASES`,
   `ACCOUNTING_EVIDENCE_KEYS` and `ACCOUNTING_SCOPE_KEYS`, which are hand-copied and pinned to
   nothing;
2. **closure — an undeclared key or basis must be REFUSED, not silently dropped.** The relay is a
   whitelist projection, so unknown fields vanish and the drift direction is silent
   UNDER-REPORTING of resources. An undeclared sixth basis carrying `usd` relays without refusal,
   straight through the guard that exists to stop exactly that.
Without both, D20–D23 reproduce this five more times against `workflow_eval`.
The review also qualified my question 4a correctly: `resource_evidence`'s relay guards are
legitimately defensive rather than masked (the condition is unreachable from real output BY
CONSTRUCTION, which is what makes it a defensive invariant assertion), but the honest label is
**"checks presence, not closure"** — not "proven".

**F6 MEDIUM — MY ERROR, fixed.** I appended new `outcome:` lines for D14–D17 instead of updating
them in place, which is what Phases 1–3 did. Verdicts read correctly (last-wins) but
`count_plan_budget_usage` sums every line: **31 dispatches reported against 27 real**. Four
phantom dispatches. `kit_contract`'s own docstring states the invariant, citing Phase 1's F2:
*nothing may write a line the reader has to ignore.* Nothing refuses today only because this kit
declares no budget — and D17's finding is that no kit in this repo declares `max-model-calls`.
Collapsed to one line per task; now 27, no duplicates, every verdict preserved.

### Adjudications, recorded rather than deferred again

**F3 (a refused decision cannot be recorded) — RESOLVED: record the decision, do NOT bump
`CONTRACT_VERSION`.** Every Phase 4 consumer already handles `record=None` correctly —
`join_row` emits `refusal-has-no-record` into both `censoring` and `unresolved`, and `_refusal`
validates reasons and refuses an empty list. Making `selected` nullable turns that tested path
into dead code. **There is no persisted `DecisionRecord` store anywhere**, so the honest answer
to "where IS a refusal recorded" is: in the attempt ledger's event, in the unresolved+censored
join row, and nowhere durable yet — and that sentence is the artifact the plan needed, not a
nullable field. If D20 or D23 genuinely needs to persist a refusal, bump IN THAT TASK with both
doc mirrors in the same commit (Phase 3's F4 proved that coupling four times out of four).

**D17's `model` class — moot as posed; the real finding is worse.** `classify_dispatch` has
exactly six returns: `auth`, `config`, `infrastructure`, `permission`, `unknown`, `None`. Never
`verification`, never `model`. So the tuple change is unobservable. But `failure_class ==
"verification"` reaches a record by exactly ONE route: `attempt_history.py:296`,
`failure_class or pairs.get("failure")`, where `pairs["failure"]` is the driver's **NOTES prose
outcome-line string** written from `rc != 0`. **So the only records that can ever trigger a repair
come from the NOTES projection (`source="notes"`), not from a trusted ledger event** — and D17's
header sentence claiming the trigger is written by `classify_dispatch` is false for the only class
it accepts. Leave the tuple; correct the sentence; and adjudicate whether a NOTES-derived class
satisfies the shared PLAN's "determined from trusted events and never by a semantic guess",
because today it is the only thing that can satisfy the trigger at all.

**The replay store still has no home — now a NAMED PHASE 5 PRECONDITION, not a carry-forward.**
`runtime_data.STORES` has no `replay`, and `.gitignore` carries no `/replay/`. A `replay/`
directory created in the repo root would become the store AND be tracked by git, against the
invariant that every local store is personal data living outside the plugin tree. D20 is the
first plausible writer.

**F8 — yes, the uncalled modules are a phase finding, and here is the measurement.** Five modules,
**69 public symbols, 7382 lines**, referenced in `bin/` only by each other and by `release_gate`
(which reads version strings and calls nothing). None has a `__main__`, so none has `--help` or
`--demo`. 11 of 66 `bin/` modules lack `__main__`, so being a library is not unprecedented — but
every other one has a production consumer that invokes it (`safe_paths` <- 16 modules,
`codex_policy` <- 7, `journal_sources` <- 5). These five have **zero in-edges from the running
system**. Phase 5 adds to the island and D28–D30 are release checks over a feature set nothing
exercises. **Phase 5 gate: one task produces a traced production path, or at minimum a `--demo`
for `decision_eval`/`decision_context`; failing that, the plan records that V1 ships these as an
offline library and names what D28–D30 exercise instead.**

**F9 — `JOIN_VERSION` non-bump RATIFIED**, with the release note already written into `559a51b`'s
body: `/1` now denotes two row shapes inside one kit run and a release must say so.
**F10 — `caps` is a brief/acceptance mismatch, not an acceptance failure.** One relayed field
beside `resources`; housekeeping.

**Standing rule, new: a shared scratchpad is not safe while agents run in parallel.** A parallel
agent overwrote a generic `scratchpad/mutate.py` and deleted `scratchpad/mut/` mid-run, which
invalidated one of the reviewer's sweeps. Every agent gets a UNIQUELY NAMED scratchpad
subdirectory from now on.

**Housekeeping deferred to the next green boundary:** F3's untested closed-vocabulary refusals
(11 survivors in D18's section, 16 in D19's, 0 in D17's — D17's `review=clean` is earned), F5's
bare `complete` key, F10's cap field.
reviewer: P4 model=opus findings=10 confirmed=8 result=accepted

### Phase 4 review findings — closed before Phase 5, suite 5009 OK

**F1 closed.** `trial_cohort` now calls `verify_manifest`; `_certification_evidence` now calls
`exec_policy.certify_profile` over a sentinel REPORT (the seam renamed `certification=` →
`sentinel_report=`). My check: a manifest with only its declared sha tampered now yields
`verified: False, frozen: False, item_count: 0` with a `digest` finding, while the honest one
still gives `frozen: True` and 6 items — refused without being over-broad. `frozen` now means "an
immutable manifest was supplied AND it verifies"; it used to mean "a `manifest` argument was
passed". New closed code `manifest-unverified`, deliberately distinct from `no-held-out-evidence`.
`CONFINED_DISPATCH_WIRED` still `False`.
**Honest residual, made machine-checkable rather than prose:** every requirement row now carries
`re_derived_by`, naming the function that re-derived it or `None`. `whole-task-study` and
`operator-declarations` are `None` — they remain caller assertions, and nothing offline can
re-derive that a run happened. The sentinel report itself is still unauthenticated; a fabricated
report consistent across backends, denial signals and control legs still certifies.

**F2 closed, and BOTH halves were needed.** All three caller-supplied routes into
`recovery_report` are pinned. Seven tokens added — `cause`, `rootcause`, `ledto`, `resultedin`,
`triggeredby`, `effectof`, `attributableto`. **The claim was narrowed in three places**, because
widening a list under a categorical claim just moves the line. `causation`, `causality`,
`proximate_cause` and `why_it_passed` are still uncaught and are now DISCLOSED and demonstrated
by a test rather than promised away — the redaction idiom: shape-matching cannot prove absence.
Causal words in VALUES still pass, as designed.

**F4 closed — and my description of it was wrong in a way worth keeping.** I said the drift was
silent UNDER-reporting. That holds for the projected fields, but `totals` is `_copy`'d WHOLESALE,
so an undeclared sixth basis carrying `usd: 12.5` came through INTACT, past the priced-usd sweep,
into the report. **Two opposite drift directions in one function.** So the Phase 5 rule is not
"projections under-report" — it is **any relay that does not check closure is asserting
completeness it did not check**, and which way it lies depends on whether the field was projected
or copied. Closure now refuses unknown keys and unknown bases (`unknown-field`); the three
mirrored vocabularies are pinned against the owner — `RESOURCE_BASES == wf.BASES`, and the two
field sets against `arm_accounting`'s real output, which is stronger than a constant because a
constant can drift from the literal it describes.

**F5 closed:** `complete` → `own_declarations_complete`, gone rather than shadowed. There were
FOUR assertion sites, not the three I named.

**THE PHASE 5 TEMPLATE IS THREE PARTS, NOT ONE.** `empty_totals()` carries a sixth key `note`
that is not a basis, so a naive `set(totals) - set(RESOURCE_BASES)` closure check would have
refused every well-formed accounting. **Only the positive control catches an over-broad guard.**
So D20–D24 inherit: (1) relay-and-refuse, (2) pinned to the owner by exact partition, (3) with a
positive control that provably bites. Here the positive control is killed by 7 of 12 mutants.

**My briefs were corrected SIX times across these fixes**, every time because the brief said
verify rather than assume:
1. I claimed adding `cause` would catch `root_cause` "via the existing normalisation". FALSE —
   `_is_causal_key` matches a WHOLE reduced key or dotted segment, never a substring, so
   `rootcause` needed its own token. The most likely real-world spelling would still be accepted.
2. I relayed the review's claim that `slices` was a second, separate hole. It is ONE vocabulary
   hole reachable by three routes; the review had probed `slices` with a base form and the others
   with `caused_by`.
3. Three assertion sites for the rename; there were four.
4. The drift direction was both ways, not one (above).
5. `workflow_eval` declares no constant for two of the three field sets.
6. `empty_totals()`'s non-basis `note` key (above).

**And my own probes were shallow FIVE times in one sitting** — passing a `where=` argument
`resource_evidence` does not take, hand-rolling an accounting missing required fields, a string
where an arm dict belongs, `_record()` without its two positional arguments. Every failure was a
real guard refusing my guess. **Build the input with the real generator; a hand-rolled input
tests your guess about the shape, a generated one tests the code.**

**Still open, carried to Phase 5:** scope NAMES in the relay are not closed (an invented scope
label relays, though every block under it still passes all three closure checks and both
invariant guards, so no unvouched figure gets in); `calibration_report` has no adversarial input
route today, so its label test records the call site rather than proving it end-to-end; and
nothing calls `resource_evidence` or `recovery_report` in production, so "the relay refuses" is
forward work, not an operational property.

## D20 — Existing owner (opus) — Phase 5 task 1 of 5

Extends `build_proposal`/`review_proposal`/`apply_proposal`/`rollback_policy` with a
bundle/manifest reference block. 21 tests, 21 mutants killed, 0 survivors, 0 inert.

**It improved on the pattern I briefed, and D21–D24 should copy THIS, not my version.** I asked
for a mirror of the owner's field set pinned by exact partition. It kept **no mirror at all**:
`fields = set(ledger.REF_FIELDS)`, read from the owner at call time, with the version read from
each slot's owner (`decision_contract.BUNDLE_VERSION` for `bundle`, `MANIFEST_VERSION` for
`manifest`). A partition test proves two lists agree today; reading the owner means there is only
one list. That is the strongest available answer to this kit's recurring "one authority, two
implementations" defect. A test patches `al.REF_FIELDS` and `dc.BUNDLE_VERSION` and asserts the
relay follows, so the read is pinned as a read.

**Closure landed right on first contact, and the contrast is the proof.** My probe:
`read_ref` alone DROPS an unknown key; the relay REFUSES it. The owner function silently narrows,
the relay does not — exactly the F4 distinction it took a phase review to surface. `_policy_ref`
is the writer and refuses; `read_policy_refs` is the reader and DEGRADES (`recorded: False`,
`unreadable: [slot]`). Two jobs, deliberately not one function.

- **It declined the Shape A trap the brief warned about.** `review_proposal` records
  `authority: "name-only"` with a label stating the reviewer is a string the command was handed
  and that this is not authentication. It could have written a field called `approved`.
- `POLICY_REFS_VERSION` is NEW, on the referenced object. `PROPOSAL_VERSION`, `POLICY_VERSION`,
  `EVAL_VERSION`, `MANIFEST_VERSION` all untouched at `/1` — `read_proposal` refuses any `v` that
  is not current, so a bump would discard stored records rather than migrate them.
- **No `replay/` store created**, and the absence is asserted in a test rather than claimed.
- Production path traced by reading the chain: `propose --manifest ID` → `read_manifest` →
  `manifest_ref` → `build_proposal` exists and is driven end-to-end through `main([...])`.
  `build_proposal(bundle_ref=...)` has NO caller — there is no bundle store in this repo, so it
  is a library seam for D21/D22/D23.

**Shape, not origin, stated plainly:** `_policy_ref` proves a reference is a complete well-formed
pointer naming the right contract. It opens nothing, so it proves nothing about whether the target
exists, still digests to that sha, or was approved. The `--manifest` CLI path DOES re-derive the
digest at the moment the pointer is taken (`read_manifest` refuses a rewritten file, mutation-
proven); nothing re-checks it later, and the library entry point cannot tell a real reference from
a well-formed hand-typed one. **`bundle_ref` has no origin evidence at all** — D22/D23 inherit
that, and a bundle store is an architect decision.

**MY ERROR, and it is a SECOND entrance to a chain already in this ledger.** I appended the D20
correction to `docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md` — right convention, right
content — and did not run `docs_build.py build`. Four tests went red and `docs_build check` exited
1. The chain already recorded here fires when a `VERSION_SOURCES` row is registered; it *also*
fires when any `docs/*.md` SOURCE is edited directly. **The same four test names
(`test_codex_discovery_docs`, `test_docs_build_cli` x2, `test_docs_site`) had been caused three
times by concurrent suite runs.** Nothing was racing this time. A symptom I had learned to
attribute to one cause has two, and only checking `ps` for a competing run before diagnosing kept
me from the wrong fix. Regenerated through the owning generator, never hand-edited.

**Left for my call, flagged rather than acted on:** `tests/test_decision_policy_bundle.py`'s
`preference_payload()` (D11's file) is now a slightly older snapshot lacking `refs` and the
authority label. Nothing fails — `describe_legacy_preferences` ignores unknown keys and
`parse_bundle` still refuses the shape by name — and it remains an accurate HISTORICAL file, which
is exactly what D20's migration test uses it as. Left as is.
outcome: D20 model=opus attempts=1 result=pass review=pending run=2026-09-16-aa6e

## D21 — Bounded drafts (opus) — Phase 5 task 2 of 5

`bin/improvement_loop.py`, 451 lines, a bounded orchestrator. 32 tests; 24 mutants killed,
1 deliberately INERT (a comment-only mutation, included so the harness's own "did this change
anything?" check is not itself vacuous), 0 survivors.

**"Not a persistence owner" proven structurally, by me.** An AST sweep of the new module finds
ZERO write primitives (`open`/`write_text`/`mkdir`/`dump`/`rename`/`unlink`/...), zero
subprocess-shaped calls, no `Path.home`, and imports of exactly `argparse`, `importlib`, `json`,
`pathlib`, `sys`. `workflow_eval` remains the one writer. This was the task most able to falsify
that invariant retroactively for D08, D18 and D20, and it does not.

**A NEW VARIANT OF THE MASKING PATTERN — worth adding to the catalogue.** The three draft guards
were built as a **tuple**, so all three expressions evaluated EAGERLY and `_draft_assurance`
raised about a value `_draft_vocabulary` had already refused. Every test still passed, because a
refusal did occur every time — just from the wrong guard. **Masking through evaluation order
rather than control flow.** It would have made the `assurance` refusal untestable in isolation
while looking healthy. Caught by the positive control, fixed to lazy, and pinned by a mutant that
reverts laziness and dies. Previous variants were all about which check runs first; this one is
about which checks run AT ALL when you meant only one to.

- **No version constant, and that is the reasoned answer rather than the rote one.** A draft is
  not a stored record, so nothing in the section versions anything; an AST test over module-level
  assigns inside the section bounds fails if a `*_VERSION` reappears. No `VERSION_SOURCES` row, so
  the RELEASE/docs-site chain never fired.
- **D20's no-mirror discipline propagated, which is what Phase 5 was supposed to do.**
  `draft_partitions()` derives from `PARTITION_ROLES` (held-out AND not single-use →
  `("promotion",)`), `draft_ceiling()` from `len(decision_contract.DIFF_PARAMETERS)`,
  `baseline_workflow()` from `kit_contract.DEFAULT_WORKFLOW`, `label_vocabulary()` from this
  module's own tuples. Each proved to follow its owner by PATCHING the owner.
- `PROPOSER_WIRED = False`, the `CONFINED_DISPATCH_WIRED` precedent; no runner parameter anywhere.
- `DRAFT_REFUSALS` is exactly the five acceptance terms, and
  `test_each_of_the_five_refusals_is_reachable_with_the_other_four_satisfied` asserts the refusal
  SET equals `[reason]` from an admissible draft with exactly one thing wrong, plus
  `examined == len(drafts)` so an empty batch cannot stand in.
- **No-candidate is observably distinct from all-rejected**: the CLI exits 0 for no candidate and
  3 for all rejected.
- Where "own workflow_eval validation" was ambiguous it resolved it from D11's own comment — the
  VALUES a label parameter may take are the owning surface's vocabulary — and said so rather than
  improvising.

**Shape, not origin, restated:** `validate_draft` vouches for a candidate's shape and its values'
vocabulary. It opens nothing — not the manifest a candidate cites, not the parent bundle, not the
attempt references. Only `prepare_evaluation` opens anything, through `read_manifest` (re-derives
the digest, refuses a rewrite) and `require_held_out`. `in_force` is the caller's statement about
the parent bundle and nothing proves that payload is the bundle the candidate's `parent` ref pins
— **the same no-bundle-store gap D20 recorded**, now load-bearing in a second place.

**Audit-blindness is a REFUSAL, not a boundary** — enforced at `_draft_hidden` on the candidate
and `prepare_evaluation` on the reader. Nothing here claims an OS boundary.

**Judgement call flagged rather than buried:** `reviewed → kit` is refused as an assurance
reduction, because `WORKFLOW_STAGES["kit"]` carries no `review` stage. Conservative, possibly
stricter than intended, a one-line consequence of "never drop a stage". Strict-and-flagged beats
permissive-and-silent, but it is the architect's call if it bites.

Production path traced by reading the chain: `improvement_loop.py {evidence|draft|demo}` → `main`
→ `run_draft` → `workflow_eval.validate_draft_batch`. **Nothing else in the repository invokes
it** — no skill, no driver, no generated doc.

Nothing in my brief was wrong this time; the agent confirmed each stated fact independently
(including that `read_ref` does silently drop unknown keys) rather than building on it.
outcome: D21 model=opus attempts=1 result=pass review=pending run=2026-09-16-aa6e

## D22 — Exact approval (opus) — Phase 5 task 3 of 5

Six-state lifecycle, four bound hashes, 37 tests. 41 mutants killed, 0 survivors, 1 deliberately
INERT (comment-only, so the harness's own AST-equality check is not vacuous).

**"Hashes not isolation" is ENFORCED, not stated — verified structurally by me:**

    "satisfied": bool(CONFINED_DISPATCH_WIRED), "evidence": None,
    "re_derived_by": "workflow_eval.CONFINED_DISPATCH_WIRED",
    "eligible": all(row["satisfied"] for row in rows),

`eligible` is a conjunction over rows and one row reads the flag directly, so a granted,
exactly-bound, still-holding approval with four correct hashes returns `eligible: False` BY
CONSTRUCTION. Each row names what re-derived it (D18's precedent). A hand-written
`{"certified": True}` report is refused because the verdict is `exec_policy.certify_profile`'s
through D18's own `_certification_evidence`.

**It did NOT undo D20's honesty.** `authority` is D20's `REVIEW_AUTHORITY` READ AT CALL TIME
(mutation-proven: replacing it with the literal `"name-only"` kills a test that patches the
constant). Binding is labelled integrity and explicitly not authority. The residual is
machine-readable and UNCONDITIONAL: every record and every binding row carries `APPROVAL_UNPROVEN
= ("actor-not-authenticated", "isolation-not-demonstrated", "origin-not-dereferenced")`, and
nothing in the section can discharge one — so none is ever dropped because another check passed.
Each binding row's `establishes` is the single code `content-identity`; a mutant changing it to
`"approved-and-verified"` dies.

**THREE FINDINGS ABOUT ITS OWN WORK, all caught by mutation — this is the standard to hold:**
1. **A mutant survived because the test only ever EMPTIED a list**, so an implementation accepting
   any INTERSECTION passed a check meant to require COVERAGE. The partial-overlap case (a
   candidate claiming two task classes, approved for one) is the case a coverage check actually
   gets wrong, and nothing tested it.
2. **A test was vacuous for a subtle reason worth keeping.** `CandidateProposal.to_payload()`
   round-trips the admitted fields and `decision_contract._canonical` / `workflow_eval._canonical`
   serialise IDENTICALLY, so a byte-digest of the payload agrees with the contract's digest for
   every payload the contract admits. Asserting equality proved nothing. Fixed by patching
   `dc.CandidateProposal.sha` and watching the binding follow — the read pinned as a read.
3. **It introduced this kit's masking pattern itself.** A create-once guard in `write_approval`
   made a version test pass for the wrong reason: the version-mutated record had the same id, so
   create-once raised first and the version check was never reached.

**A LIMIT ON MY OWN MANDATED TECHNIQUE — record this honestly.** Its harness was comparing
`"Ran N tests in T.Ts"` INCLUDING the elapsed time, so the collected-count check could never be
true. I have required that check in every brief since Phase 4 without saying how to extract the
count. **This does not invalidate any mutation kill** — those are real, a named test failed — but
it means the specific guarantee "a mutant that broke collection was distinguishable from one that
killed a test" cannot be assumed live in the earlier sweeps. Future briefs must say: parse the
integer, not the line.

**Judgement calls, flagged:**
- `decide_approval` evaluates all four gates EAGERLY — deliberately the opposite of D21's lazy
  guards — because the caller is owed the whole reason. Each gate is total over the case it is
  handed, so D21's failure mode cannot recur; argued in the section note and a
  `gates-short-circuit-after-the-first` mutant dies. **Laziness is not the rule; matching the
  evaluation strategy to whether the guards are total is.**
- `insufficient-evidence` is reserved for the refusal set being exactly `{"partial"}`; thin
  evidence plus anything else is `rejected` with both named.
- An illegal transition RAISES rather than producing a refused record; `reject` is reachable from
  any non-terminal state, `accept` only from `evaluated`.
- `write_approval` uses the plain `write_text` its neighbour `write_proposal` already uses rather
  than `safe_paths` — I verified the precedent is real (`write_proposal` at HEAD does
  `path.write_text`). This module already has two patterns: `safe_paths` for the evals store,
  plain writes for the prefs store. Following the neighbour beats adding a third.
- **The one unstated thing in my brief** was which objects `evaluation` and `source` name. It
  resolved evaluation → the eval manifest, source → the run envelope, and wrote the mapping into
  the section header rather than leaving it to be inferred.

**Shape not origin, and a NEW gap:** the library entry point opens nothing, so
`origin-not-dereferenced` is unconditional; the CLI path opens the manifest and envelope, but
**the candidate payload is a document somebody handed in on BOTH paths**, so origin is never
established for the thing being approved. The residual is deliberately not made conditional on
the entry point, because the record cannot tell which one produced it. **Nothing pins the
envelope before the approval does** — the candidate pins its manifest (which is what makes the
`stale` gate possible) but pins no run, so the approval record is the FIRST thing to pin the
envelope and the `stale` gate cannot catch an envelope swapped between the run and the approval.
The no-bundle-store gap is now load-bearing in a THIRD place.

`APPROVAL_VERSION` new; all five existing constants verified still at `/1`. No new store —
approvals live under the prefs directory D20 already owns. `approval_holds` and
`promotion_eligibility` have NO production caller; they are library seams for D23.
outcome: D22 model=opus attempts=1 result=pass review=pending run=2026-09-16-aa6e

## D23 — Protected activation (opus) — Phase 5 task 4 of 5

The transition that WOULD be taken, and it machine-refuses. 51 tests; 38 mutants, 38 killed,
0 survivors, 0 inert. `CONFINED_DISPATCH_WIRED` still `False` and untouched.

**The refusal is re-derived at THREE points, so a stored document never beats the state the repo
is actually in:** `activation_entry` (after the `permitted` check, so a hand-built verdict with
`permitted: True` is refused too), `validate_entry`'s writer path (a hand-written canary entry
refused before a file exists), and `runtime_activation` (a canary pointer that somehow exists
resolves every run to LEGACY). `activation_decision` relays `promotion_eligibility`'s rows WHOLE
and adds two of its own, so activation is a superset of promotion eligibility and cannot be laxer.

**The load-bearing test, and its shape is the whole lesson.** I read it rather than trusting the
summary. `test_every_named_gate_is_satisfiable_and_the_transition_still_refuses` asserts all four
named gates ARE individually satisfiable, and that the transition refuses anyway with
`blockers == ["confining-dispatch-unwired"]`, the row naming
`workflow_eval.CONFINED_DISPATCH_WIRED` as what re-derived it. **Without it, every refusal test in
the file could be satisfied by a gate that refuses everything.** Its docstring says so. That is
the positive-control discipline at its most valuable — the point where a suite full of green
refusals would otherwise prove nothing at all.

**Mechanics, not safety — carried as a CODE, not prose.** Every decision, entry and report carries
`fixture-proves-mechanics-not-safety` unconditionally, alongside `pointer-store-not-authenticated`
and `gate-block-not-re-derived-in-full`. A fixture that makes a gate pass proves the gate READS
what it claims to read; it certifies no host, no isolation, no model. The read-only CLI prints
this to the operator in plain language — the honesty standard applied outward, not only in tests.

- **CAS with no window at all**: `swap_activation(expected=N)` writes `gen-(N+1)` via
  `safe_paths.confined_create_bytes` (`O_EXCL`) and deliberately does NOT re-read the directory
  first, so a stale expectation fails on the kernel's answer rather than on a comparison with its
  own race window. Proven with a real `ThreadPoolExecutor`: eight concurrent swaps, one winner.
- **`pinned_bundle`'s SIGNATURE is the guarantee** — `(pin, bundles, runtime)`, no prefs dir,
  store, scope or pointer parameter, so there is no expression through which a run could re-read a
  pointer mid-flight. Pinned by `inspect.signature` and a source sweep.
- **`select_action` still refuses `canary`/`active` by name** — D13 was not weakened.
- No new store: generations live beside D20's proposals and D22's approvals under the prefs
  directory. `ACTIVATION_VERSION` new; **seven existing constants verified unmoved**.
- **`bin/kit_contract.py` change is pass-through ONLY**: `start_task_lifecycle` gains
  `policy_ref`/`decision_ref` and hands them to `TaskRun`, which has accepted both since step 16
  with no caller able to reach them. No contract logic added, moved or duplicated.
- **The driver seam is wired but UNFED.** All four `*_execute.py` call `start_task_lifecycle`, but
  `grep -n policy_ref` across them returns nothing, so the pin is `None` on every real run today
  and every attempt records it as unknown — the honest state, not a placeholder, and pinned by a
  test.
- **There is deliberately NO CLI command that activates anything**, asserted by a test that no
  subcommand named `activate`/`canary`/`promote`/`rollback-activation` exists. I confirmed the
  surface myself.

**MY BRIEF WAS WRONG AGAIN — eighth correction today.** I wrote "six version constants live in
`workflow_eval`"; there are seven. I omitted `TRIAL_PROTOCOL_VERSION`.

**Three self-corrections worth the standard they set:**
1. It found a FALSE CLAIM IN ITS OWN DRAFT and fixed it: it had written `manifest_currency` is
   "the first function in this module to ask both the document and the store". It is not —
   `require_held_out` already calls `verify_manifest`. The separate call is still load-bearing for
   a narrower reason the code now states: `require_held_out` merges everything into ONE blocker
   sentence, and D18's rule is that `manifest-unverified` and `no-held-out-evidence` are
   deliberately TWO codes and never one. Asking the document question first is what makes a forged
   manifest report AS a forgery.
2. It removed a rotting count from its own text ("for the fourth time in this kit").
3. **It DECLINED to confirm my claim about D22's harness**, because that harness is not in the
   tree — and followed the instruction anyway. Refusing to nod along to an unverifiable premise is
   rarer than agreement and is exactly the behaviour these briefs ask for.

**A survivor that exposed a fixture blind spot:** `rollback_entry` setting `bundle_ref` to the
fallback SURVIVED, because every rollback fixture resolved to legacy (`bundle_ref` None), so the
mutation was a no-op. Fixed by a fixture that genuinely selects an approved bundle.

**OPEN ARCHITECT QUESTION, raised by the implementer and NOT invented by it:** the whole-task
study is not a gate. `live_requirements` demands one before general rollout; the brief named
exactly four gates and it correctly declined to add a fifth. **This belongs in D24 and the D30
handoff before anything could ever move to `active`.**

Shape not origin: the gate is handed documents. `require_held_out` genuinely opens the evals
store, but the approval record, candidate, sentinel report and declarations are all caller-
supplied — D22's `origin-not-dereferenced` applies one layer up. Several tests patch the flag to
`True` inside a `wired()` context manager, because otherwise the pointer mechanics are unreachable
and would be code nobody has shown to work; every such test restores it and then asserts the same
pointer reads as legacy in the world as it is.
outcome: D23 model=opus attempts=1 result=pass review=pending run=2026-09-16-aa6e
