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
