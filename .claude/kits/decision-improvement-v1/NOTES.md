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

## D24 — Policy evidence report (sonnet) — Phase 5 task 5 of 5, phase COMPLETE

Projects lineage/scope/interventions/resource bases/quality/monitoring/defect windows without ever
calling mechanics performance. 43 tests. `POLICY_EVIDENCE_VERSION` new (9th constant; it recounted
`dir(we)` itself rather than trusting my number — I had miscounted twice).

**`POLICY_EVIDENCE_UNPROVEN = ("mechanics-not-performance", "no-live-outcome-observed",
"monitoring-not-authority")` is unconditional on every assembled report**, mirroring D22/D23's
pattern. Every figure a caller could feed this today is synthetic-fixture evidence or an explicit
`unknown`, because `CONFINED_DISPATCH_WIRED` is still `False`.

**THE EXCHANGE WORTH REMEMBERING — I flagged on a pattern match; the agent PROVED the gap before
closing it.** I noted `scope_visibility` was "a direct relay, not separately mutation-killed" and
said direct relays are where D19's closure defect lived. Rather than take my word or defensively
add a test, it mutated the function to silently drop `task_classes` from the relayed scope, ran
all 42 tests, and **every one passed**. The hole was real and demonstrated. It then added a
whole-object equality test, reapplied the identical mutation, and confirmed the new test is the
ONLY failure among 43. **A test added on suspicion tells you nothing about whether it was needed;
a test added after the gap is demonstrated tells you exactly what it catches.**

**Fix I sent, and why it mattered:** `test_policy_evidence_report_never_claims_a_gain` excluded
the WHOLE `labels` key from its sweep. The reasoning was sound — a disclaimer must name the thing
it disclaims, as `assert_no_causal_claim` sweeps keys and never disclaiming prose — but **the
exclusion was written wider than its reason**. Safe today (I verified labels held only the three
disclaimer constants); tomorrow a gain-claiming label passes the guard on this task's single most
important property. This is the kit's signature defect wearing test clothing. Now narrowed to the
three KNOWN constants read off the constants themselves, with nested `labels` lists swept too —
**and it asserts the POSITIVE**: it plants "a 12% win rate improvement over baseline" as a fourth
label and asserts `winrate` is found. A fix to a test that does not change what the test catches
is decoration.

- **It found its own bug**: `present = resources is not None` is `True` for a valid but EMPTY
  accounting list; fixed to `bool(accountings)`.
- **It disambiguated a naming collision that is D22's, rather than silently picking one.** D22's
  binding slot spelled `evaluation` is the manifest; this report's `evaluation` is the run (D22's
  `source` binding). `LINEAGE_NAMING_NOTE` states it on the record.
- `monitor_proposal` never calls `rollback_entry`/`swap_activation`/`decide_approval` — proven by
  patching all four with the file's own `_RaisingSeam` and confirming the right proposal still
  returns. Monitoring can propose; it cannot grant.
- Reads at call time, proven by patching the owner: `decision_eval.HUMAN_LABEL_SOURCES`,
  `de.RESOURCE_BASES`. A hardcoded 5-tuple copy dies when the owner grows a sixth basis.
- `routing_scorecard.py` gained ONE function, additive-only fence intact, 125 tests including its
  golden/demo byte-stability tests still green.

**Stated limitations, volunteered:** no production path invokes any of it and no CLI verb was
added (the brief required none; D23's `activation` precedent does not oblige one). **The
escaped-defect and monitor-observation record shapes are NEW vocabulary this task introduced, not
relayed from an owner** — no D01–D23 task defined either, so those inputs are hand-built by
necessity; it drew that distinction rather than letting them read as relays. Several branches are
proven by direct example rather than a mutation kill, and it said so rather than implying a
systematic sweep it did not run.

**MY FALSE ALARM, caught before reporting it:** I ran `routing_scorecard.py demo` and got exit 1.
The documented form is `--demo`, which exits 0. The bare form exits 1 **at HEAD too**, so my
invocation was wrong, not D24's change. Third near-miss today from a wrong invocation (the `where=`
parameter, hand-rolled fixtures, this). **Check the failing form against HEAD before calling
anything a regression.**
outcome: D24 model=sonnet attempts=2 result=pass review=revised run=2026-09-16-aa6e

## Phase 5 review — ACCEPT WITH FINDINGS, all five closed before Phase 6

The review earned its keep by **beating the test I trusted most.** 22 of its 24 planted mutants
died; the chain could not be made to activate, dispatch, or claim a live outcome. But the fifth
link broke in three ways this kit has a catalogue for.

**F2 (HIGH, I reproduced it) — the gate named `exact-approval` was satisfied by a record that
bound nothing.** `approval_ok = granted and (holds is None or holds["holds"])`, and `case` defaults
to `None`, so `{"state":"approved","granted":True,"bindings":None}` gave
`exact-approval satisfied=True, re_derived_by=None`. **This is the SAME defect I personally closed
in Phase 4 for `trial_cohort`** — satisfied because an argument was PASSED, not because anything
was checked — reappearing one function away, in the gate that consumes what I fixed. The file even
states the rule, in `manifest_currency`: *"an unmade check is not a passed one."* D23 applied it to
its own gate; D22 never applied it to the one D23 relays.
The reviewer then **beat D23's load-bearing test** with it: same fixtures, hand-built approval, no
case, inside `wired()` → `permitted: True`, `blockers: []`, a minted entry, a written generation,
`runtime_activation` reporting canary. **The only thing refusing today was
`CONFINED_DISPATCH_WIRED`, and D18's note says that flag gets flipped in the same edit that adds a
confining runner.** Closed: `granted and holds is not None and holds["holds"]`, new closed
vocabulary `PROMOTION_APPROVAL_BLOCKERS`. Verified: the forged record now yields
`satisfied=False, blocker=exact-approval-not-re-derived`, and D23's control still passes because it
supplies a real case.

**F1 (HIGH, I reproduced it) — `quality_evidence` read the wrong nesting level.** `resolved`,
`scoreable`, `abstained` live under `coverage`; it read them at top level, so all three were always
`None` while `status` said `"reported"` and `present` was `True` — and
`render_policy_evidence_markdown` printed `resolved=n/a` to an operator. **Known evidence rendered
as unknown, on a report whose contract is "unknown visible."** 43 tests missed it because the
assertion checked KEY PRESENCE, and the key is always present since the dict literal writes it.
Verified fixed: 25/25/0. The renderer needed no change — it was rendering what it was given.

**F5 (MEDIUM) — my open question answered against my instinct: THE NEIGHBOUR IS THE BUG.** A
demonstrated traversal: `write_approval` returned `.../approvals/../../OUTSIDE/pwned.json` and the
file existed outside the prefs root. Same for the proposal pair. The decisive evidence is inside
Phase 5: **D23's `swap_activation` writes to the SAME store through `safe_paths.validate_id` one
commit later**, saying *"text that becomes a filename is text that can name a path."* Two opposite
answers to one concern, one commit apart — following the neighbour added a third state, it did not
avoid one. Closed with `validate_id` on six functions, before the `mkdir`, so a refused id creates
nothing.

**F4 (MEDIUM) — Phase 4's F4 reproduced exactly**, in `resource_basis_report`: one-directional
closure plus a wholesale `_frozen` copy, so an undeclared sixth basis carrying `usd: 12.5` arrived
intact on a report whose `bases` field says five. The docstring NAMED bidirectional checking as its
reason and checked one direction.

**F3 (MEDIUM-HIGH) — "no gain claim" had no product-side enforcement.** Caller `notes` went
straight onto the report; the injected claim rendered as a blockquote directly above the disclaimer
denying it. **A capability claim whose only enforcement is a test over one fixture is not
enforcement.** Now `assert_no_gain_claim` in the product, with the limit disclosed the way D19
disclosed `causation`/`causality`.

### Two places the implementer improved on MY brief

1. **I said exempt the three disclaimer constants from the gain sweep. It measured which actually
   contain a gain token — only `MECHANICS_NOT_PERFORMANCE_LABEL` does — and exempted ONLY that
   one**, pinning the other two as inert so a claim landing in either refuses loudly rather than
   riding an exemption it never needed. That applies my own principle more strictly than I stated
   it.
2. **`roi` as a substring collides with ordinary prose**: `"zero identity"` → `"zeroidentity"`
   contains `roi`. The EXISTING test listed it as a substring and passed only because no such
   phrase was in the document. Now word-anchored; verified `[]` for that phrase and `['roi']` for
   "the ROI was 3x".

### A SECOND LIMIT ON MY OWN MANDATED TECHNIQUE — record this

Its harness first reported two F5 mutants as SURVIVING. They do not survive: **the rsync'd temp
tree carried `__pycache__` and importlib served PRE-MUTATION BYTECODE**, so the mutation was
applied to source that never ran. Cleared cache plus `python3 -B` turned both red.

**Several agents this run built temp trees by copying `bin/` and `tests/`, and I never specified
clearing `__pycache__` or `-B`.** A stale-bytecode mutant is indistinguishable from a real
survivor. Unlike the `Ran N tests` line issue — which only weakened a secondary check — this one
can invert the verdict on a guard. **The kills that named a specific failing test remain sound
(positive evidence). What I cannot claim retroactively is that every reported SURVIVOR in earlier
sweeps was a real survivor.** Both limits have the same cause: I specified WHAT to check without
specifying HOW, and that gap is where a check goes quietly inert. Standing brief now says: parse
the integer, and run `-B` on a cache-cleared tree.

### Adjudications

- **Whole-task study as an activation gate: YES, but conditional on `target_state == "active"`,
  not a fifth unconditional gate.** The review compared both lists: four of five live requirements
  have activation counterparts (two strictly stronger), and `whole-task-study` is the only one with
  none. The shared PLAN scopes it to "before general rollout", and `RUNNING_STATES` already
  separates bounded `canary` from `active`. D23's implementer was right to decline inventing it.
  **Now an architect decision before D30's matrix claims what `active` requires** — and note it
  will be a caller assertion whichever task takes it, since nothing offline can re-derive that a
  study ran.
- **`classify_dispatch`: untouched by Phase 5, neither better nor worse.** But the review found an
  adjacent pre-existing D14 overclaim: `decision_eval.py:528` sets
  `"failure_class_basis": "trusted-event" if cls else None` unconditionally, so a class that
  arrived via the NOTES prose projection is labelled `trusted-event`. **The field whose whole job
  is to name trustworthiness overclaims.** Folds into whichever task takes the D17 trigger
  question.
- **No-bundle-store gap: a D30 disclosure, not a Phase 6 blocker — and it is load-bearing in FIVE
  places, not three.** Add D23's `activation_entry(bundle_ref=...)` and `rollback_entry`'s
  `resolution`. D30's matrix cannot claim canary/active "unavailable absent D23 evidence" without
  also saying the bundle a pointer would name has no store and no origin evidence.

**Two F5 guards survive by construction and say so in their own source**: `review_proposal` and
`apply_proposal` both call `read_proposal` first, which validates, so their mutants are unkillable.
Documented as deliberate defence in depth with no mutation kill claimed — a function composing a
path from a caller's string should not depend on a neighbour having checked it.

**Behaviour changes callers should know:** `policy_evidence_report` and `resource_basis_report` now
RAISE where they previously returned. `quality_evidence` blocks gained `coverage`/`coverage_reason`
(additive).

**Artefact for future temp-tree sweeps:** `tests/test_release_gate.py` has three cases that read
the real checkout's git revision and fail in a `git archive` tree for reasons that are not the
code's. Exclude that module rather than reading its failure as a finding.
reviewer: P5 model=opus findings=10 confirmed=10 result=accepted

## D25 — Harness assessment skill (opus) — Phase 6 task 1 of 3

Stages `assess-improvement` from the prototype into `skills/` and the Cursor bundle. 23 tests;
28 mutants killed, 0 survivors, plus a second battery of 7 against the existing test files it
edited — all killed.

**ARCHITECT-VISIBLE SCOPE DECISION: the card ships on Claude and Cursor ONLY, not Copilot or
Codex.** Reasoning verified and sound: adding it to those two means editing FROZEN ROSTERS in test
files D25 does not own — `ORIGINAL_SKILLS` in `test_copilot_bundle_adversarial.py` pins 13 names
in exact order; `EXPECTED_SKILL_STEMS` in `test_codex_bundle.py` pins an exact set — and neither
file is in D25's verify command, which says the task author did not expect them to move. The
acceptance is satisfied literally: it says **"Codex plugin valid"**, not "Codex includes skill".
**D27's assessment and D30's release matrix must describe this as a TWO-harness capability**, and
`primitives/harness-capabilities.json` records a capability as relied-on only when verified.

**`bin/harness_select.py` is BYTE-IDENTICAL — the installer needed no change.** `install --harness
cursor` delegates wholly to `cursor_adapter.plan_install`/`apply_install`, so a `BUNDLE` addition
flows through untouched; `install --harness claude-code` writes nothing because the plugin at the
repo root IS the install. The brief named that file as in-scope; discovery said do not touch it.
**That is the "only where actual discovery requires it" instruction working as intended**, and it
also did not touch `.claude-plugin/plugin.json` (carries no skills roster — `skills/` IS the
roster, pinned by a test asserting the manifest's key set) or `.codex-plugin/plugin.json`
(`"skills": "./codex/skills/"` is a DIRECTORY, so discovery grows with the tree and a new card is
never a manifest edit).

**It found a brief-vs-reality conflict in the card itself and pinned the divergence rather than
hiding it.** `test_skill_entrypoints.py` requires every Claude SKILL.md description to name a
trigger ("use when" / "when the user" / ...). The prototype's said "Use for read-only improvement
planning" — no trigger — so a verbatim copy fails a suite that is NOT in D25's verify command.
It rewrote the description line only and pinned it:
`test_the_claude_card_is_the_prototype_body_verbatim` asserts the BODY is byte-identical, `name`
identical, description deliberately NOT, and the new description names a trigger. The prototype is
left untouched as the record of what was staged.

**Eight files outside the brief's named list were forced by live-tree guards**, each fixed at the
CLAIM rather than by re-arming a literal:
- `tests/test_docs_build_adversarial.py`: `len(baseline) == 75` → an exact set partition. **This
  is a strengthening I verified in the diff** — it catches a page silently dropping while another
  appears, which a count cannot — and the absolute page-set size stays pinned in
  `test_docs_build_cli.RealTreeIdempotenceTests`, so no absolute pin was lost.
- `tests/test_docs_audit.py`: `test_exactly_39_entries` derived from `skill_inventory()` instead,
  **plus a guard that did not exist**: `_entries()` builds a dict, so two headers for one skill
  silently collapsed and passed.
- `tests/test_cursor_adapter.py`: `"wrote 3 file(s)"` → `f"wrote {len(ca.BUNDLE)} file(s)"`.
- The rest are tripwire bumps, commented as tripwires rather than dressed up as derivations.

**`.claude/kits/docs-site/AUDIT.md` — another kit's file, edited correctly.** The guard
(`test_roster_is_exactly_the_live_skill_inventory`) is DESIGNED to fire when a skill lands. The
entry is labeled honestly rather than backdated: *"unchanged, and unreviewed by this pass… no D1
three-way reading was ever performed on it, so `keep` here means unchanged."* The summary moved
33→34 because the consistency test recounts verdicts, with an added line stating the REVIEWED
shape of that pass was 33/3/3, and readers are told to re-derive from `skill_inventory()` rather
than trust the now-stale Method arithmetic. **It did not rewrite a record of what that pass
measured.**

**MY COUNT WAS WRONG AGAIN — ninth correction today.** I said the four pre-existing suites collect
175; they collect 174. It measured properly rather than asserting: stashed its work under a unique
tag, re-ran, restored by SHA, dropped the entry, verified the tree.

**Stated limitations:** everything here is STRUCTURAL — no test asserts a model follows the card's
prose, and D26 owns fixture-level behaviour. The no-fit vocabulary test proves the vocabulary is
present and closed, never that a model emits `no-fit`. The Codex "roster" in its test is a
directory listing, so that side CANNOT disagree with the tree — said out loud rather than dressed
up as agreement. No site fragment was written (unreviewed public prose for no acceptance gain) so
the card's page has no "In practice" section. The `.cursor/`-absent assertion is conditional on
the pre-existing state, so it stays correct for a developer who has legitimately installed the
bundle into this checkout.
outcome: D25 model=opus attempts=1 result=pass review=pending run=2026-09-16-aa6e

## D26 — Assessment fixtures (opus) — Phase 6 task 2 of 3

35-case corpus plus a structural checker. 32 tests; 18 mutants, 0 survivors. All four pins
byte-identical — the card needed no change.

**"No assertion in this task is about a model. Not one."** It audited every test name for the
defect I warned about and **RENAMED FOUR** that read as behaviour claims — `…produces not
applicable…`, `…concludes no supported intervention…`, `…is findable twice over…`, and
`…states none of its contents` (a test cannot prove a statement leaks nothing, and the docstring
now says so). I verified independently: no test name claims model behaviour; the only matches are
`no_model_pin`, "the oracle records", and one that explicitly DISCLAIMS observing a model.

**It reused the product's gain authority rather than copying it, and then pinned that it cannot be
copied.** `we.assert_no_gain_claim` is called 6 times, and `inspect.getsource` asserts the
checker's own source contains NONE of `we.GAIN_TOKENS`. I confirmed: zero literal copies in the
test file. That is stronger than reuse — it makes the second implementation impossible to add
quietly.

**Every rule the checker enforces is parsed out of the shipped card/template AT CALL TIME** —
evidence statuses, permitted assessments/recommendations/decisions, ranking basis, the four
surfaces. None is a literal in D26's section; D25's `SkillPackagingTests` pins those same sets to
literals. **D25 is the guard, D26 is the consumer** — the no-mirror discipline applied across a
task boundary.

**TWO SELF-CAUGHT NEAR-MISSES, and the first is a NEW variant for the catalogue:**
1. **A no-op mutant SURVIVED and exposed real missing coverage.** Its determinism mutant returned
   `[next(iter(findings))]` and passed, because **every case carried exactly ONE finding, so
   `sorted()` pinned nothing at all.** Not a check behind a check — **a check over data too
   simple to exercise it.** The guard was real, the test was real, the FIXTURE made the assertion
   vacuous. Fixed by adding a two-finding case, pinning it by name as the only multi-finding one,
   and re-mutating with `sorted(..., reverse=True)`.
2. **Its harness produced a fake "4 persistent failures"** because `restore()` reverted the test
   file and card but not the FIXTURE files, so a fixture-editing mutant contaminated the next
   run's baseline. Same family as today's `__pycache__` stale-bytecode trap: **the harness lied,
   not the code.**

**It applied the D24 lesson back at me, unprompted.** Hidden-answer handling bans every finding
code and conclusion token from `sources.json`, but **deliberately does NOT ban
`unknown`/`unverified`** — those are evidence states a repository legitimately records about
itself, and banning them would be *"an exclusion wider than its reason"*. That is the exact
principle I had to send back to D24.

**MY BRIEF WAS WRONG A TENTH TIME, precisely.** I said D25 made "a one-harness asymmetry"
concrete because the card ships on Claude and Cursor. **Two harnesses is not one**, so it does not
model the fixture the brief requires. It built that synthetically and instead tied the corpus to
repo reality where safe: every fixture's harness key set is pinned equal to D25's
`HARNESS_SKILL_ROOTS`, so a fixture cannot invent a fifth harness or drop one, while support
VALUES stay synthetic. I had conflated "asymmetric across harnesses" with "supported by exactly
one."

- The contradiction is **DERIVED** (two observations on one subject asserting different things);
  the sources never say a contradiction exists. Three reports over one byte-identical source:
  carried → accepted, dropped → `contradiction-unreported`, settled → `contradiction-silently-
  resolved`, invented → `contradiction-fabricated`.
- No-home/network/CLI is proven with 13 armed seams AND a control that fires each one, with
  `PROBES` pinned equal to `FORBIDDEN_SEAMS` by name and each seam asserted replaced BEFORE its
  probe fires — so an arming failure cannot let a real call through.
- Exactness throughout, per the D19 template: `accepted | refused ==` every case with empty
  intersection; oracle key set == case set; corpus finding union == `FINDING_CODES` in BOTH
  directions.
- **The qualitative item done literally**: `QUALITATIVE-OBSERVATION.md` carries `Status:
  qualitative`, the cases inspected, and "No model was run, dispatched or observed". Two tests
  keep it a note and not an oracle — bounded to a STRICT subset of case ids, containing no finding
  code and neither verdict key, and it passes `assert_no_gain_claim`.

**Stated limitations:** `review_assessment` has NO production caller — it is a test-module checker
over a test corpus, and making it reachable from an engine would need a deliberate move into
`bin/` with its own ownership decision, which it declined to make. **The oracle is authored, like
the corpus** — what carries weight instead is call-time-derived rules, byte-identical-sibling
differentials (8 source documents, every multi-case group containing both an accept and a
refusal), and the two-directional code partition. The fixture path guard would fail benignly if
someone later created a top-level dir colliding with a synthetic tree name (it already hit and
fixed one real collision: `docs/RELEASE.md`).
outcome: D26 model=opus attempts=1 result=pass review=pending run=2026-09-16-aa6e

## D27 — Whole-repo assessment (opus) — Phase 6 task 3 of 3, phase COMPLETE

`docs/ASSESSMENTS/polytropos-decision-improvement-v1.{md,json}` — 21 findings, 49 evidence rows
across 28 files, 7 surfaces. Verify exit 0 read UNPIPED. All three pins byte-identical: D27
changed no engine, no card, no test.

**CORRECTION TO A FACT I CARRIED SINCE PHASE 4 AND REPEATED IN FOUR BRIEFS.** I have been asserting
that five decision modules are "referenced in `bin/` only by each other and by `release_gate`".
**That is FALSE at this HEAD and I never re-measured after the task that changed it.** D21's
`bin/improvement_loop.py` gave two of them a runnable entry point. I verified by instrumenting the
sibling loader — my first attempt found nothing because `improvement_loop` loads siblings through
its OWN `_sibling` (`spec_from_file_location` makes a FRESH module object), so my wrappers were on
the `sys.modules` instance, a different object:

    improvement_loop.py demo reaches:  decision_policy.bundle_ref
      + workflow_eval.{baseline_workflow, draft_budget, draft_ceiling, draft_key,
        draft_partitions, label_vocabulary, validate_draft, validate_draft_batch, workflow_stages}

The agent traced three decision-module functions (`decision_contract.parse_bundle`,
`parse_proposal`, `decision_policy.bundle_ref`); my single-loader wrap caught one of the three, the
other two going through `workflow_eval`'s own loader. **The honest residual: ~3 exercised symbols
out of ~70, and NONE of `workflow_eval`'s five offline verbs (`demo`, `activation`, `policy`,
`approvals`, `list`) loads a decision module at all** — traced against temp dirs. Also corrected:
**70** public symbols not 69, and there is a **SIXTH** module, `improvement_loop.py` (12 symbols,
the only one with a `__main__`). **D30's handoff must use these figures, not Phase 4's.**

**THE GAIN SWEEP REFUSES ITS OWN REPORT, and the cause is wider than this kit.** The checkout
directory is named `polytropos-decision-improvement-plan`, so **any absolute path quoted from this
worktree trips the token `improvement`.** Measured on the final document: 945 strings swept, 42
carry a token, 37 inside identifiers, 5 as bare words, 1 distinct token. All five bare occurrences
name the body of work or a quoted search pattern; none claims performance. Cross-checked by a
second sweeper that keeps no copy of the vocabulary, asserted via `inspect.getsource` — D26's
method. **Anything that sweeps paths in this checkout will hit this.**

**New material the kit's record did not have:**
- **`bin/docs_build.py:_HARNESS_SKILL_ROOTS` has THREE harnesses** (claude, copilot, codex) —
  **Cursor is absent**, so the card PUBLISHES as Claude-only while it SHIPS on two. D25's
  two-harness fact was half the story: packaging and publication disagree.
- **`primitives/harness-capabilities.json` → `claude-code.capabilities.confined_dispatch` is
  `verified: "unsupported"`**, source "measured on macOS", because subscription credentials live in
  a keychain the profile blocks. The report links this to the activation blocker **without merging
  them** — conflating a host limitation with a design decision would misread both. **31 of 57
  capability rows across 5 harness entries are `verified: unknown`.**
- **Cursor's `skill_files` is `verified: "unknown"`** — the very install surface shipping the card
  is unverified.
- **Two unrelated things share the word "rollback"**: `rollback_policy` (CLI-reachable, policy
  files) and `rollback_entry` (reachable from nothing). Flagged before either reaches an operator.
- `bin/decision_eval.py:528`'s `"failure_class_basis": "trusted-event" if cls else None` overclaim
  is still open at this HEAD (its F03).

**Three defects of its own, caught and fixed:** it nearly reported four red gates because `bin/$c`
in zsh does not word-split an unquoted expansion (**the same class of error I have made three times
today**); `.strip()` on `git status --porcelain` ate the leading dot of `.claude/...`; and its first
draft claimed "every occurrence is an identifier" when 5 were bare words, then said "three kinds"
when only two occur.

**No generator needed rebuilding**, and it verified why rather than assuming: `docs_build`
enumerates `(root/"docs").glob("*.md")` — NON-recursive — and `copilot_docs`' recursive walk is
rooted at `copilot-docs/`, so a file under `docs/ASSESSMENTS/` is invisible to both. The six census
pins use the same non-recursive glob.

**What it could not assess, stated:** whether any model follows the card (it added no such
assertion); whether a confined dispatch would work (no such path exists to run); whether non-Claude
hosts discover what the bundles install (those rows are `unknown` and stay `unknown`); and whether
the 3-of-70 fraction is stable, since it was measured on one command path and a verb behind absent
state may reach further once that state exists.
outcome: D27 model=opus attempts=1 result=pass review=pending run=2026-09-16-aa6e

## D31 — Decision-time snapshots (opus) — Phase 7 task 1 of 4

`bin/training_data.py` (1430 lines) + 66 tests. 38 mutants, 38 caught, 0 survivors.

**COLLECTION SHIPS OFF, AND I VERIFIED NOTHING WAS COLLECTED.** Three independent locks, all shut:
`COLLECTION_ENABLED = False`, `CAPTURE_WIRED = False` (different facts, both re-derived at call
time — `enabled=None` reads the constant INSIDE the body, never as a default-argument value), and
`collection_scope`'s `eligibility` **defaults to `"unknown"`**, which cannot persist anything. An
operator must do all three, and flipping the constant alone still collects nothing because there is
**no call site**. My own check, via `runtime_data.store_path("training", repo_root)`:

    training store path: .../polytropos-decision-improvement-plan-9f697583/training
    EXISTS: False
    stores actually present in the per-checkout root: ['journal']   <- pre-existing, not this run

`/training/` is root-anchored at `.gitignore:29` and `git log --all --diff-filter=A -- training/`
is empty: never tracked.

**THE STORE DECISION IS BETTER REASONED THAN MY BRIEF.** I offered "add a `STORES` row" or "reuse
an existing store". It rejected reuse **on the invariant's own words — "written by its own engine
ONLY"** — because `evals` belongs to `workflow_eval` and `prefs` to `copilot_prefs`/`workflow_eval`,
so a new engine writing into either breaks the one-writer rule D22/D23 respected by staying inside
the module that already owned their directory. **Registering it properly bought four things I had
not considered:** `release_gate packaging` now checks its ignore rule (`| training/ | present |` in
`docs/RELEASE.md`); `tests/test_privacy_layout.py` covers it automatically because that test's list
IS `STORES`; `runtime_data where/migrate/export/forget` see it; and **materially,
`decision_context.store_prefixes()` now automatically excludes training snapshots from ever being
offered as repair context.** An unregistered training store could have been read back into a
model's context by D16's candidate proposer. **That consequence only appears if you register
through the authority instead of resolving a path yourself.**

**TWO MUTANTS SURVIVED ITS FIRST BATTERY AND BOTH FOUND REAL GAPS** — it looked for the route
first, as instructed, and both times there was one:
1. A zoneless instant was accepted; the entry-level test passed because `_entry`'s placement check
   catches an unreadable stamp a SECOND time. The uncovered route was **`captured_at`, which has no
   second line of defence** — it feeds the file name and the expiry date. The new test also asserts
   the message NAMES the field, so one route cannot be satisfied by the other's refusal.
2. **A genuinely vacuous test**: `assertRaises(Exception)` on a path that raised earlier for an
   unrelated reason. It hid that `read_snapshots(store, captured_at)` takes the date RAW, and
   `safe_parts` refuses `..` and absolute paths but accepts `a/b/c` (creating nested dirs) and a
   leading dot (a hidden file). Fixed by asserting `SafePathError` specifically and moving the
   validation ABOVE the `is_dir()` short-circuit, so the argument is wrong whether or not the store
   exists yet.

**One branch is deliberately unreachable and NAMED rather than shipped as a guard no test reaches**:
`persist`'s `duplicate-entry` refusal needs a 64-bit digest collision, since `assert_intact` proves
the id is derived. The test reaches it by patching `_sha` into a colliding hash, and the docstring
says which of the two refusals actually bites on a tampered store.

**MY BRIEF WAS WRONG AN ELEVENTH TIME.** I said `classify_dispatch` returns six of the seven
classes. It returns **FIVE** — `infrastructure`, `auth`, `config`, `permission`, `unknown` — plus
`None` for a zero exit, which is not a class. I had counted `None`. My load-bearing claim (it never
returns `verification` or `model`) was correct. `NOT_PRODUCED_BY_DISPATCH = ("model",
"verification")` records it and a test re-derives it TWO ways: by CALLING the function over a
7-case matrix (observed set == `set(CLASSES) - NOT_PRODUCED_BY_DISPATCH`) and by READING its source
for those returns — because calling alone would only prove the fixture missed them, and reading
alone would not prove the other five are reachable.

- **"Not general transcript logging" enforced as ceilings, not prose**: 16 KiB per record, 2000
  chars per field, at most 8 entries per field. A decision needing more evidence is REFUSED rather
  than logged.
- Redaction goes through `bin/redact.py`, reports KIND and COUNT never value, and
  `REDACTION_LIMIT_NOTE` rides on every record saying shape-matching cannot prove absence. **No
  sentence anywhere claims no secret can get through.**
- The taxonomy is pinned by **exact partition** against `attempt_ledger.CLASSES` read at call time,
  patched BOTH ways in the test; an AST sweep asserts no owner vocabulary is copied in as a
  constant, with a `> 50` non-vacuity floor.
- `docs/PRIVACY.md`'s two hand-kept store lists updated in the same edit, both mirrors rebuilt
  through their generators. It ran `git check-ignore -v` and `git log --diff-filter=A` BEFORE
  writing the sentence claiming the store never existed, rather than inheriting the older
  "verified for all eight" wording.

**Production callers: NONE**, and pinned as an exact set — `test_no_production_path_calls_the_
capture_hook` asserts the modules naming `training_data` are exactly `{release_gate.py}`, which
reads only two version constants and is asserted to contain no `capture_hook`/`collection_scope`/
`persist(`/`snapshot(` call. Mutating the `VERSION_SOURCES` rows away trips that exact-set
assertion, so a second importer cannot appear silently.

**Deliberately D32–D34's, not D31's:** label lifecycle (`attach_label` returns
`status: "unadjudicated"` and nothing can advance it; `expires_on` is computed and recorded but
nothing acts on it), export/manifests/grouping/splits, the readiness report, and
`REVIEW_ONLY_CLASSES` (`missing-context`, `implementation-error`, `multiple-causes`) which are
asserted unreachable from any operational signal by design.
outcome: D31 model=opus attempts=1 result=pass review=pass run=2026-09-16-aa6e

## D32 — Reviewed labels and eligibility lifecycle (opus) — Phase 7 task 2 of 4

68 tests (module now 134 with D31's 66). 30 mutants, 0 survivors. Three pins byte-identical;
`runtime_data.py` needed no change because D31 already registered `training`.

**"Without claiming model unlearning" is enforced in DATA, not prose — verified:**

    derived-dataset    : invalidated
    export-manifest    : invalidated
    readiness-report   : invalidated
    trained-checkpoint : identified-only        <- named, never unlearned

`REVOCATION_UNREACHED = ('trained-weights-not-unlearned', 'exported-copies-not-recalled',
'downstream-artifacts-not-rebuilt', 'byte-erasure-not-proven')` rides on EVERY `revoke()` record
whether it names four dependents or none, and what revocation DOES reach is separately coded.
`assert_no_unlearning_claim` refuses a dependent payload whose keys would claim otherwise
(`unlearned`, `weights_purged`, `scrubbedFromWeights`, `model-forgot`), matched as whole words after
splitting on punctuation AND camelCase humps — **and its docstring says a spelling list is not a
decision procedure and that a claim in a VALUE is not caught.**

**IT REMOVED TWO OF ITS OWN GUARDS FOR BEING DECORATION, BEFORE ANY MUTATION FOUND THEM.** This is
the first time in the run an agent applied the standing rule prospectively rather than as a
post-mortem. `attach_action` originally swept its payload with `assert_no_input_field` and
`decision_eval.assert_no_causal_claim` — but every parameter is keyword-only and lands in a named
field, so **there is no caller-keyed object for a sweep to inspect** and both would have survived
deletion. Replaced with the closed schema plus a test pinning the exact 16-key set against both
predicates.

**It also caught the masking pattern IN DESIGN.** In `revoke`, the sweeps had to move BEFORE
`_dependents`, because `_closed` would answer `unknown-field` first and the sweep would never see a
nested `{"ref": {"id": "c", "scrubbedFromWeights": true}}` — `attempt_ledger.read_ref` ignores
extra keys. Same shape as every masking instance this kit has found, spotted before shipping.

**MY BRIEF WAS WRONG A TWELFTH TIME, and the correction is the most interesting one yet.** I said
`LABEL_STATUSES` does not exist. **It exists in `decision_eval`** as
`("resolved","disputed","missing","censored")`; my claim was true of `training_data` only. It then
**DECLINED to map onto it**, correctly: the surjective map would force `unresolved` onto `missing`
or `censored`, and *"somebody reviewed it and could not tell"* is neither "no label" nor "not yet
knowable from a joined fact". **Reusing a vocabulary that NEARLY fits is how two different facts
become one.** `LABEL_VOCABULARY_NOTE` states why they are apart, and a test asserts
`UNSUPPORTED_REASONS ∩ decision_eval.METRIC_STATUSES == set()` so `insufficient-evidence` is not
borrowed either (the D15 point).

**Two first-sweep survivors, both real gaps:**
1. `label_state([])["target"]["eligible"] = True` survived — the empty-history test asserted
   `status` and `reason` but never the eligibility VALUE, and `export_eligibility` keys off
   `status`, so **nothing read the field D33 will read.** Fixed by asserting the whole `target` dict.
2. Replacing the `EXPORT_REFUSALS` self-check with `[]` survived — nothing made the function emit a
   code outside its own vocabulary. Fixed by shrinking `EXPORT_REFUSALS` under `mock.patch.object`
   and asserting the decision refuses to answer in a vocabulary it does not name.

**The three origins are three slots**, not one field with a flag: `operational_observation` (copied
off the snapshot, NEVER from the caller), `provider_suggestion` (caller's, `adjudicated: False`,
supports nothing), and `cause`/`contributing` (only what review evidence supported).
`assert_no_adjudicated_field` refuses a claim or suggestion arriving under an adjudicated field name.

**Owner pins, both patched both ways:** `EVIDENCE_ADMISSIBILITY` against
`decision_eval.LABEL_SOURCES` plus a third check that every `HUMAN_LABEL_SOURCES` member weighs as
`review`; and `RESULT_TO_ACTION_OUTCOME` against
`RECOVERED_RESULTS + FAILED_RESULTS + CENSORING_BY_RESULT` in THREE directions, so **a censored
result read as a failure refuses.**

**GAP TO CARRY INTO D33:** `attach_action` accepts an `ACTION_OUTCOMES` member DIRECTLY, so the
censored→unknown rule only bites for a caller routing through `action_outcome()`. A caller can
still declare `outcome="failure"` for an open attempt — the caller asserting, not the module
inferring, consistent with D31's posture. **D33 exports these records, so it must know which field
is derived and which is declared.** The named fix if wanted: an `outcome_basis` field
(`attempt-result` vs `declared`), or taking `result=` instead of `outcome=`.
Also: `export_eligibility` without `store_dir` yields `label-not-checked` +
`revocation-not-checked` rather than an all-clear, and `EXPORT_NOT_ESTABLISHED` carries
`enforcement-not-provided` unconditionally — **it decides, it does not prevent.**

Locks verified still shut and **no training store created even after `training_data.py demo` ran**:
`exists: False`, root contains only the pre-existing `journal`. No production caller —
`release_gate` remains the only `bin/` module naming `training_data`, reading version constants
only, still pinned as an exact set by D31's test.
outcome: D32 model=opus attempts=1 result=pass review=pass run=2026-09-16-aa6e

## D33 — Grouped dataset splits and reproducible exports (opus) — Phase 7 task 3 of 4

52 tests (module 186). **44 mutants, 44 caught, 0 survivors.** Three pins byte-identical.

**PREVENTS, not decides — the question I asked, answered in the signature.** `store_dir` is
REQUIRED on `build_dataset`, so D32's `label-not-checked` / `revocation-not-checked` cannot arise
through this path at all (asserted: those two codes never appear in a D33 exclusion). A record with
a non-empty refusal list never reaches a payload line. What it still does not prevent is a process
reading the store directly — that stays the store's `0700`/`0600` and `exec_policy`, carried
machine-readably on every manifest as `access-not-enforced`.

**IT DELETED FOUR OF ITS OWN GUARDS — the bar keeps rising** (D32 deleted two, itself a first):
a `label["current"] is None` branch the `head is None` lookup already covered; a line-count check
made unreachable by the file digest; a second `sorted()` duplicating an ordering decision made
elsewhere; and **it found an existing assertion PASSING FOR THE WRONG REASON** — `dataset_integrity`
fired before the content compare it was meant to test. That is the masking pattern inside its own
tests, found by mutation rather than reading.

**Reuse of D06 is total: `development` is the ONLY partition name spelled as a literal in the
module** (I verified — `constants & set(we.PARTITIONS) == {TRAINABLE_PARTITION}`). Everything else
is read at call time from `PARTITION_ROLES`/`PARTITIONS`, and the two non-obvious inadmissible
placements are derived by **asking `decision_eval.placement`** rather than spelling
`"after-prediction"`, which would have tripped D31's own owner-vocabulary sweep.
`require_held_out` is deliberately NOT called — it refuses `development` by design — and the
substitute rule compares against `PARTITION_ROLES[TRAINABLE_PARTITION]["purpose"]`, stated in the
module rather than left implicit.

**Two ways it declined to overstep, both worth keeping as precedent:**
1. **It edited another task's test and REPORTED it.** D32 pins an exact COUNT of
   `confined_read_bytes` call sites; D33 legitimately adds four, so it bumped `2 → 6` with a comment
   naming each — then added the **count-free form** in its own class, pinning the `safe_paths`
   surface as an exact five names rather than a number that rots.
2. **When its work collided with D06's test, it fixed ITS OWN side.**
   `test_the_evals_store_has_exactly_one_engine_naming_it` allows only two files to contain the
   literal `"evals"`; its demo had named a temp dir that. It renamed the demo dir rather than
   widening a store-ownership guard. The easier choice would have quietly weakened D06.

**It declined the scope expansion I offered.** I said `outcome_basis` was in scope if needed for
honest export. It answered that **D33 exports no action records at all** — only the adjudicated
cause — so the field would have no reader, and then **PINNED THE ABSENCE**:
`test_no_action_record_reaches_either_file` asserts the action's text, digest and outcome appear in
neither file and that no `action`/`outcome`/`taken` name exists in either schema. **A later outcome
field fails there rather than shipping as a measurement.** If the outcome is ever wanted,
`attach_action` needs the basis first — named unfinished, not done.

**SCOPE DECISION SURFACED RATHER THAN TAKEN, and D34 must carry it:** the draw is **NOT** recorded
in `workflow_eval`'s exposure log, because that would mean writing another engine's store. Every
manifest carries `exposure-not-recorded-in-the-eval-store` and names the remedy
(`workflow_eval.record_exposure`, called by the operator). **The runbook has to include that step or
an operator exports without recording exposure.**

- Determinism proven with enough shape to matter (D26's trap avoided): 3 groups, 4 included, 4
  distinct exclusion codes, exported in REVERSED order, compared byte for byte — plus two child
  interpreters under two different `PYTHONHASHSEED`s.
- Future-answer leakage: the forged record's **three digests are all correct** (D18's lesson), so
  only export-time re-derived placement can refuse it.
- Audit/payload separation is proven LOSSLESS with intersection == `{"example_id"}`, and
  `audit-identity-in-payload` searches only content-derived identifiers — **the reviewer id and the
  partition name are deliberately NOT searched**, because a decision really can have been shown the
  word "development", so the schema and not a search is what keeps those out.
- 16 stdlib seams + 8 `workflow_eval` writers armed, probe list asserted equal to the forbidden
  list by name, with a control that fires each.
- Honest limits: `_dataset_id`'s `validate_id` CANNOT fire (the `ds-[0-9a-f]{16}` regex is narrower
  than `SAFE_ID_RE`) and says so; the manifest digest establishes nothing was altered after export,
  **never that the inputs were real**; `MAX_DATASET_EXAMPLES = 2_000` refuses rather than trims;
  no minimum sample count is asserted anywhere (`training-sufficiency-not-established`).

**Process note: the full suite was KILLED for memory once here, with ZERO competing runs** — the
suite is now 5454 tests and the machine is tight. Unlike the earlier kill this was not a collision;
I checked `ps` first. Re-ran clean.
outcome: D33 model=opus attempts=1 result=pass review=revised run=2026-09-16-aa6e

## D34 — Collection readiness and operator runbook (opus) — Phase 7 task 4 of 4, phase COMPLETE

38 tests (module 224). 32 mutants, 32 caught, 0 survivors. `workflow_eval.py` byte-identical; the
four Phase 7 version constants unmoved; `READINESS_VERSION` new and registered.

**THE REPORT SAYS NOTHING IS READY, and I verified it: 11 gates, 0 met, 4 unmet, 7 unknown.**

    unmet   : collection-switched-on, capture-wired-to-a-caller, records-captured,
              collection-target-chosen
    unknown : the other seven

**`unknown` is deliberately NOT `unmet`** — it means the report could not SEE the thing (no dataset
offered, no exposure log given, no scope passed). That is the unknown-is-not-zero discipline applied
to a report. **`collection-target-chosen` is ALWAYS unmet**, not because anything is broken but
because nobody has run a pilot, and **a number chosen to close it would be the arbitrary threshold
the acceptance forbids.**

Ten codes ride on every report unconditionally, including D33's five **read from that tuple rather
than respelled**: `synthetic-fixtures-are-not-readiness`,
`readiness-is-a-report-not-an-authorization`, `exposure-not-recorded-in-the-eval-store`,
`digest-identifies-content-not-provenance`, `training-sufficiency-not-established`,
`label-agreement-counted-not-calibrated`, `sampling-bias-not-estimable`,
`checkpoint-link-is-a-forward-declaration`, `no-transfer-and-no-training-performed`,
`access-not-enforced`. **The acceptance term is machine-readable, not prose.**

**D33's obligation IS carried.** `runbook()` names `workflow_eval.record_exposure` (verified), while
**AST proves `training_data.py` never CALLS it** (`record_exposure` absent from the called set,
`exposure_state` present). The operator's step is documented precisely because the module refuses to
take it. **`runbook()` REFUSES unless its steps exactly cover `READINESS_GATES`** — a gate cannot
exist without a step telling an operator how to close it. And the gate is DERIVED, not advice: the
report reads `workflow_eval.exposure_state`, reports `unmet` naming the drawn items, and flips to
`met` only after the test calls `we.record_exposure` itself — and **recording it does not discharge
the unconditional code**, because this module still wrote nothing there.

**THE GAIN-SWEEP SOLUTION IS THE BEST ANSWER TO THAT PROBLEM YET.** I warned it to expect a refusal
(this checkout's path contains `improvement`) and not to widen the exemption. It did neither — it
**separated the swept artifact from the unswept one**: the report carries the store's NAME
(`"store": "training"`) and never its path, so it sweeps clean; the CLI payload embeds the resolved
path and is **deliberately not swept**, with its docstring saying why. The document carries exactly
ONE gain token in 279 lines, inside an inline-code span naming a repository path, and the test hands
the PROSE (code spans, fences and listings removed) to the product's own authority — with a control
injecting "a measured improvement" that confirms the sweep bites. `readiness_report` CALLS
`assert_no_gain_claim` as its last act, so a scope whose declared purpose reads as a performance
claim refuses.

**One guard deleted for being unreachable** (D32 deleted 2, D33 4, D34 1) — `_one_of` on the gate
name and state both survived, because `readiness_gates()` already checks `GATE_REMEDIES` is an exact
partition of `READINESS_GATES`, so a bad name trips THAT first. Removed, with the docstring naming
what actually enforces it and stating plainly that `remedies[name]` is ordinary indexing, not a
guard.

**A near-miss in its own fixtures, caught:** a disputed-label test **passed for the wrong reason** —
as "one supported head plus one unsupported" rather than two competing supported causes — because it
used `tests-oracle` evidence for a `REVIEW_ONLY_CLASS`, which cannot be supported that way. The
corroboration test failed honestly; the disputed one passed dishonestly. Both rebuilt with a second
independent human reader.

**Two consequences my brief did not name, both reported rather than done quietly:**
1. **`mkdocs.yml` needed a hand nav line** — `deep-dives/` is generator-owned but the nav is
   hand-kept, and `test_docs_site` fails both directions without it.
2. **Three hand-kept count tripwires in other tasks' test files moved** (`test_docs_build_adversarial`,
   `test_docs_build_cli`, `test_primitives_doc_adversarial`), each with a dated comment in the
   existing precedent format — D33's "edited another task's test and REPORTED it" convention.

**CORRECTIONS TO MY BRIEF: NONE. Twelve factual claims checked, twelve held** — the red exit status,
the 186, three md5 pins, the three locks plus the missing call site, decides-vs-prevents, the ceiling
with no floor, the declared-not-derived action outcome, D33's zero action records, the retention
rules, the revocation reach table, the `docs/*.md` non-recursive glob, and the `improvement` token in
this worktree's path. **First fully-correct brief of the run.**

**Limits:** everything is synthetic and that is now a CODE on every report, not only a sentence. No
production path calls `readiness_report` either. The exposure gate establishes an entry exists under
the trainable purpose for each drawn item, **never that the entry describes this export**. `records`
are passed IN rather than enumerated — there is no "read every capture date" function, and adding one
would add a path seam to a module whose `safe_paths` surface is pinned at exactly five names.
Label "agreement" is a count of live heads reaching the same target, **not an inter-rater statistic
and not corrected for chance**.
outcome: D34 model=opus attempts=1 result=pass review=revised run=2026-09-16-aa6e

## Phase 7 review — ACCEPT WITH FINDINGS, all seven closed

**The collection lock could NOT be broken, and that is a result.** The reviewer attacked with a
C-level `sys.addaudithook` trap — which fires inside CPython regardless of what the module imported,
strictly harder to defeat than the 16 patched seams D33 armed — across `status`, `taxonomy`,
`readiness`, `demo` and four `capture_hook` shapes. **Zero post-import file-write, mkdir, socket or
subprocess events with collection off.** Not "no writes outside temp" — no events at all. `demo`
produced 39, all under a `mkdtemp` root, all removed by its `finally`. **The D18 hand-built-document
route does not exist here**: `persist` re-derives `assert_intact` AND re-checks eligibility, so a
record with correct digests still cannot persist with a non-`approved` block.

**F1 (HIGH) — a sentence outran its code, in the PRIVACY layer.** `redact()` is called in exactly
TWO places in 4662 lines (I verified by AST) while the module header and the readiness doc both said
*"Every free-text entry goes through `bin/redact.py` before it is persisted."* False for the
QuestionSpec wording — which is copied verbatim into `payload.jsonl`, **the model's input file**. A
credential shape reaches the export while `record["redaction"]["redactions"]` reports `{}`. **The
test that should have caught it generalised past its fixture**: named
`..._never_reaches_the_record_or_the_disk`, it only ever put the token in one field — and
`release_gate.py` cited it as evidence for a guarantee row.
**Closed by narrowing, and the reason the other closure is unavailable is solid:**
`QuestionSpec.digest()` is over the COMPLETE wording, so redacting inside `_question` would store a
payload its own digest no longer identifies, and `questions_digest` pins whole sets the same way.
Both sentences now say "input entries and the revocation reason"; every record carries
`REDACTED_FIELDS` (2) and `NOT_REDACTED_FIELDS` (10) so a reader of an empty `{}` knows its scope;
the test is renamed to name its field; the release-gate row no longer reads as whole-record
coverage. **It also named the option I did not offer** — refusing a credential shape at capture —
and left it undone rather than pretending the choice was binary.

**F2 (HIGH) — the late-evidence defence measured against an unchecked instant.** Nothing compared
`prediction_at` to `captured_at`. A record captured at 10:00:05Z declaring its decision at 23:00:00Z
was accepted, filed and exported — and the reviewer got "the patch that fixed it" into decision-time
input **through the sanctioned API alone, no digest forging.** Closed in `snapshot()` reusing the
same `placement` primitive every entry uses, AND re-derived at export as the new exclusion code
`captured-before-the-decision`. I verified: the impossible ordering refuses, and **both controls
still stand** — same instant and captured-a-year-after both accepted, so it is not over-broad.

**F3 (MEDIUM) — the mirror of a gap D32 named and did not connect.** `adjudicate`'s `no-failure`
branch checks `from_operational is not None`, but that value is the SNAPSHOT CALLER'S argument with
no cross-check against `attempt_ref` — so a failed attempt is exported as a negative example by
OMITTING ONE ARGUMENT. Same shape as `attach_action`'s `outcome_basis`, one field over.
**`operational_class_basis` now defaults to `"declared"` — the WEAKER value — so unstated provenance
can never pass as a ledger reading.** The opposite default would have made every existing caller
silently claim ledger authority. D32's sentence is corrected IN PLACE: *"'Copied off the snapshot,
never from the caller' was true here and false one step earlier."*

**F4 (MEDIUM) — the one decorative guard that shipped, and it shipped in the honesty report.**
`grouped-partition-assigned` survived replacement by the constant `"met"`, appeared in ZERO tests,
and was structurally unable to read `unmet` (its lists are computed over examples that `build_dataset`
already excluded). Worse: `build_dataset([])` produced a valid empty dataset that flipped BOTH it and
`exposure-recorded-in-the-eval-store` to `met` — the gate naming this phase's own live hazard.
**Kept and made able to fail rather than deleted**, because deleting would also remove its runbook
step and remedy row, and the gate is what a reader looks for. Now derived from the manifest's own
`excluded_by_code`, both gates `unknown` on an empty draw, and **`readiness_gates()` refuses if a
watched code is not one an export can emit** — otherwise renaming a code leaves the gate watching a
name that can never appear, *the same decoration one indirection further along.*

**F5 (MEDIUM) — a model's verdict satisfied the "independent reader" rule.**
`decision_eval` produces `review-verdict` for any trial acceptance not by `kit-check`, i.e. an
agent's. `_supports_a_cause` asked only `tally["review"] == 0` and never consulted
`HUMAN_LABEL_SOURCES`, which was already computed. Now a review-only class needs a human reader,
read from the owner AT CALL TIME. **Two adjacent gaps deliberately NOT taken and named for D30**:
`ambiguity`'s top-level check still gates on any review weight, and `_reviewer` still admits
`review-verdict` as the filing reviewer — an agent's verdict may FILE an adjudication, it cannot by
itself ESTABLISH a review-only cause, and both facts ride on the record.

**F6/F7/F10 closed**: four ceilings pinned BY VALUE beside the doc that quotes them (and it corrected
the review — `MAX_FIELD_CHARS` did NOT survive mutation, so only two of four were value-free);
`MAX_DATASET_EXAMPLES` now states its basis as a chosen bound with an explicit denial that it is a
sufficiency threshold; the two `_closed` drift guards keep a comment saying they guard drift not
arrival, proven by running both deletions (236 OK) and the control (46 errors); and
`test_the_training_store_has_exactly_one_engine_naming_it` is the analogue D31 leaned on.

**THE INTERMITTENT SUITE FAILURE, SIGHTING THREE — and the reviewer lost it to a pipe again**,
the exact mistake the standing rule at this file forbids, written after sighting two cost the same
thing. **But it added the only new information in three sightings: this was `failures=1` where
sighting two was `errors=1`.** An assertion failed rather than an exception escaping — either a
second flake or a narrowing of the first. Four subsequent runs green.

### What D28–D30 must NOT claim (adjudicated, carry verbatim)

- **D28**: no `harness-capabilities.json` row or matrix cell presenting training-data collection as
  available or verified on ANY harness — it has no call site anywhere and `unknown` still means no.
  No dataset, manifest or store enters packaging; `| training/ | present |` as an ignore rule is the
  correct and only claim. **Five `VERSION_SOURCES` rows are stored-object schemas with ZERO stored
  objects**; a matrix counting schema versions as shipped surface must say so.
- **D29**: the 224 (now 236) Phase 7 tests are NOT evidence that collection works — every one
  constructs its own record. **No migration has ever been exercised against a stored record, because
  no record has ever been stored.** The private store does not ENFORCE access. The exposure
  obligation is *unavailable/operator-owned*, not passed.
- **D30**: never state or imply revocation removes anything from a model. **"0 examples collected"
  is the absence of a call site, not a gate met or a privacy achievement.** The named-unfinished
  register is now FOUR items, not two: `attach_action`'s `outcome_basis`; the operator's exposure
  step 10; no collection target (pilot not run); **and F3's `operational_class` basis pair.** Plus
  F5's two adjacent gaps and F1's disclosed question-wording exposure.

**Residual hazard, stated asymmetrically because it is asymmetric**: the TRAINING side is protected
— `build_dataset` reads the exposure log and emits `item-exposed-elsewhere`/`item-retired`, both
mutation-caught. **The EVALUATION side — the next held-out draw — has nothing to read, because
nobody wrote the entry.** That is where the spend happens and it is the one direction no code in
this repository closes. Keep the design (writing another engine's store would break the one-writer
rule D31 invoked); **D30 records it as an OPEN OPERATOR OBLIGATION, never as a closed gate.**

**Store-prefix precision for D30**: `decision_context.store_prefixes()` reads `runtime_data.STORES`,
so `training/` is in the prefix set — but prefixes are repo-relative and the scan is rooted at the
repo, so the prefix is load-bearing only for a LEGACY IN-TREE store; for the default out-of-tree
store the protection is scan confinement. D31's claim is true and the consequence real, but it is
not the only mechanism.
reviewer: P7 model=opus findings=10 confirmed=10 result=accepted

## Phase 8 — independent verification of the Phase 7 tasks

**D31 verified (sonnet, read-only, `SnapshotTests` only): 72 tests, exit 0. `review=pass`.**

One correction the verifier earned, and it lands on my own prose: I have been describing D31 as
"three locks that are all shut" (it is c12170b's subject line). Two of the three are runtime gates
and one is not. `COLLECTION_ENABLED` is branched on in `collection_state()`; the
`eligibility="unknown"` default is re-checked independently in `collection_state()`, `snapshot()`
and `persist()` — triply fail-closed. **`CAPTURE_WIRED` is never branched on anywhere.** Every one
of its ~13 occurrences only populates a report field (`"wired": bool(CAPTURE_WIRED)`) or a
readiness-gate label. Nothing inside `capture_hook` refuses because of it.

What actually enforces "nothing calls this" is structural, not a branch:
`test_no_production_path_calls_the_capture_hook` scans every `bin/*.py` for `training_data`,
finds only `release_gate.py`, and greps that file to confirm it never reaches
`capture_hook`/`collection_scope`/`persist(`/`snapshot(`. The verifier re-derived that
independently across the whole repo rather than trusting the test's own scan, and confirmed
`release_gate.py` reads five version constants and nothing else. **No call site — confirmed, and
that is the correct answer, not a gap.**

This is disclosed, not hidden: `NOT_WIRED_LABEL` says in the module itself that a green test proves
the seam works and does not prove anything invokes it. So it is not a defect. But "three locks"
overstates the mechanism by one, and the carry-forward wording should be **two runtime gates plus
one externally-verified structural fact.**

Two things the verifier checked that this kit has been burned on before, both clean:
- **Positive controls exist and bite.** `test_the_switch_is_re_derived_at_call_time_not_captured_at_import`
  flips `COLLECTION_ENABLED` True and proves the build callable IS invoked (`build.calls == 1`),
  paired against the never-called test. Redaction has its own control pair: a credential shape
  produces `{"anthropic-key": 1}`, clean text produces `{}`. This module does NOT carry the D23 /
  Phase-5 "satisfiable by a function that refuses everything" defect.
- **The redaction claim is narrower than it sounds, and says so.** `test_the_redaction_claim_names_exactly_the_two_fields_that_are_redacted`
  walks the AST, asserts exactly 2 `redact(` call sites (`_entry`, `revoke`), pins
  `REDACTED_FIELDS`, and greps both the module docstring and `docs/TRAINING-DATA-READINESS.md` to
  confirm the old overclaiming sentence is gone. `test_a_credential_shape_in_the_question_wording_is_not_redacted_and_the_record_says_so`
  then proves the gap is REAL: a synthetic token in the question wording reaches `_payload_line`
  unredacted, with the field named in `not_redacted`. A disclosed hole with a test that proves the
  hole is the honest form.

Masking sweep found none. Worth keeping: `test_a_record_whose_eligibility_is_not_approved_cannot_be_persisted`
tampers `eligibility.status` and then **recomputes `content_sha`** so the digest guard passes
cleanly — isolating `persist()`'s own eligibility re-check instead of re-tripping `assert_intact`.
That is the right way to defeat the masking pattern in a test, and the first instance in this kit
of a test that was already built to do it.

**D34 verified (sonnet, read-only, `ReadinessTests` only): 41 tests, exit 0. `review=pass`.**

**A correction to a claim I have put in every brief since D34 landed.** I have been carrying
"readiness = 11 gates, 0 met, 4 unmet, 7 unknown" as a property of the readiness report. It is not.
It is a property of ONE INPUT SHAPE — the pristine empty store. The verifier re-derived the tally
live from `readiness_report` with `records=[]` and got exactly 0/4/7, confirming the figure; then
ran the two other shapes the suite itself uses and found **6 of 11 `met` after a capture→adjudicate
walk, and 8 of 11 `met` after an export.** That is correct behaviour — a real walk should close the
mechanical gates while `capture-wired-to-a-caller`, `exposure-recorded-in-the-eval-store` and
`collection-target-chosen` stay open — but "0 met" describes an empty store, not the mechanism.

**This matters for D30.** "Nothing is ready to train" is NOT enforced by the gate tally, and D30
must not cite the tally as if it were. What is enforced is `readiness_codes()` — ten codes, five
inherited from D33 and five owned by D34 (`synthetic-fixtures-are-not-readiness`,
`label-agreement-counted-not-calibrated`, `sampling-bias-not-estimable`,
`checkpoint-link-is-a-forward-declaration`, `readiness-is-a-report-not-an-authorization`) — which
`test_every_report_carries_the_codes_that_deny_readiness_unconditionally` asserts ride on all three
computed report shapes, including the 8-of-11-met one. **The denial is unconditional; the tally is
not.** Cite the codes.

Clean on the checks this kit keeps failing: the doc never hand-types the tally (zero grep hits), so
there is no reconstructed-from-prose record; no softening language anywhere near gate text (the
phrasing is "unknown is NOT unmet — it means this report could not SEE the thing"); and
`docs/TRAINING-DATA-READINESS.md` is confirmed hand-authored SOURCE with its generated mirror at
`docs-site/deep-dives/training-data-readiness.md`, matching the repo pattern.

**Positive control — the check I asked for specifically, and it mostly holds.** 10 of 11 gates are
driven to `met` by real fixtures; six have a dedicated named `assertEqual(..., "met")`. So the
readiness function is NOT vacuously satisfiable by an always-unmet implementation — it does not
carry the D23 defect. Two named gaps remain, both real, neither blocking:

- **(a) Nothing pins the canonical {met:0, unmet:4, unknown:7} empty-store split.**
  `test_every_gate_state_is_reached_and_no_report_invents_a_gate_or_a_state` asserts only that the
  gates sum to 11 and that all three states appear SOMEWHERE across three shapes. The split could
  drift to 1/3/7 and nothing would fail.
- **(b) `capture-wired-to-a-caller` has zero positive control** — `bin/training_data.py:4385-4386`.
  No test anywhere patches `CAPTURE_WIRED` True to prove the gate's `met` arm fires. This is the
  one gate whose `met` branch is never executed in the suite.

**(b) converges with what the D31 verifier found independently**: `CAPTURE_WIRED` is never branched
on in production either. So the constant is pinned `False` in seven places, reflected into a gate,
and its `True` path is executed nowhere in the repository. Two verifiers reached that from opposite
directions without seeing each other's work. Both gaps are test-only and cheap; closing them is
queued for this phase rather than deferred.

Also worth keeping: `test_the_grouping_gate_is_derived_from_the_exclusions_and_can_actually_read_unmet`
is the in-source record of the `grouped-partition-assigned` defect review caught — the gate used to
be a decorative constant computed over an always-empty list. Its companion,
`test_every_code_the_grouping_gate_watches_is_one_an_export_can_emit`, mutation-tests a renamed
exclusion code and catches it, closing the "watches a code nothing produces" route by name.

**D32 verified (sonnet, read-only, `LabelEligibilityTests` only): 70 tests, exit 0. `review=pass`.**
Clean on all six attacks — the only one of the four Phase 7 tasks with no gap named against it.

Three findings that correct or sharpen the kit's own standing rules:

- **`REVOCATION_REACH` is the BEST form, not a mirror needing the D19/D20 treatment.** I briefed
  this as a mirror to be pinned by exact partition against its owner. It is not a mirror at all:
  `DOWNSTREAM_KINDS` and `REVOCATION_REACH` are both OWNED inside `training_data.py`, so there is
  no second copy of anyone else's vocabulary — which is exactly D20's "keep no mirror" ideal.
  Closure is nonetheless enforced at CALL time, not import: `_dependents()` calls
  `_assert_partition(REVOCATION_REACH, DOWNSTREAM_KINDS, REACH_LEVELS)` on every `revoke()`, and
  that helper computes BOTH `missing = owner - mapping` and `extra = mapping - owner`, raising
  `unknown-value` on either. Both directions are proven live: adding a fifth kind
  (`fine-tuned-adapter`) makes `revoke()` refuse rather than silently drop it, and corrupting the
  checkpoint row to `"erased"` also refuses. Real closure, not an "at least covers" check.

- **`trained-checkpoint: identified-only` is enforced behaviourally, not by table self-assertion.**
  Four named dependents split 3-vs-1 drive the bucketing logic, and `checkpoint-1` lands only in
  `identified`, never in `invalidated`. Note the 3-vs-1 split also means this is NOT the D26
  one-element-list trap — ordering and bucketing are both actually exercised. Stronger still,
  `assert_no_unlearning_claim` REFUSES an adversarial caller attaching `unlearned: True` /
  `weights_purged` / `scrubbedFromWeights`, and the string sweep guards itself with
  `assertGreater(checked, 1)` so it cannot pass by finding nothing.

- **`MappingProxyType` count in `training_data.py` is zero.** The file avoids the exact bug class
  this kit hit earlier (a proxy handed to a walker expecting `dict`). The "cannot rewrite its
  input" property is structural: `adjudicate()` never assigns into `record`, builds a fresh `entry`
  carrying only `example_id`/`input_sha` pointers, and uses exactly ONE defensive `_copy` at the
  single boundary where a caller-owned mutable (`claim`) crosses in — no second copy to mask it,
  and `_copy`'s own docstring cites the D14 two-copies lesson.

`OPERATIONAL_CLASS_BASES` is not decoration: flipping only `operational_class_basis` from
`declared` to `ledger` on otherwise identical fixture data flips refuse → resolve. The weaker
default was chosen deliberately at F3 so unstated provenance can never pass as a ledger reading.

Ordering hazard confirmed handled: `revoke()` runs `assert_no_input_field` and
`assert_no_unlearning_claim` BEFORE `_dependents()`/`_closed()`, because `_closed` would raise
`unknown-field` first and hide a nested `{"ref":{"scrubbedFromWeights":true}}`. That is the
evaluation-order trap from D21 caught in design rather than at review.

**D33 verified (sonnet, read-only, `DatasetExportTests` only): 53 tests, exit 0. Verdict REVISE —
one confirmed surviving mutant. `review=` stays `pending` until the gap is closed.**

**The finding, and it contradicts a claim in this very ledger.** `bin/training_data.py:3522-3526`,
inside `build_dataset`, bounds the exported payload/audit LINE against `MAX_RECORD_BYTES`:

      for what, line in (("payload", payload), ("audit_metadata", audit)):
          size = len((canonical(line) + "\n").encode("utf-8"))
          if size > MAX_RECORD_BYTES:
              raise _refuse("bounds-exceeded", f"refusing a {size}-byte {what} line for {eid}")

The verifier rsync'd the tree to scratch, replaced that whole block with a no-op, and reran all 53
`DatasetExportTests`: **OK, zero failures.** Nothing exercises it in either direction — no fixture
produces an oversized line and nothing patches the ceiling down the way
`test_an_export_past_its_ceiling_refuses_rather_than_trimming` does for `MAX_DATASET_EXAMPLES`.

**This ledger records "44 mutants, 44 caught, 0 survivors" for D33. That claim is now known
incomplete** — either the sweep never generated this line or the tree it mutated was not the tree
that ships. A mutation count is only as good as its operator set, and a clean sweep is not proof
that every branch was in it. Do not quote the 44 figure again without saying what it covered.

Why this is NOT dead code, which is the part that makes it worth fixing rather than deleting: it is
a **fourth distinct reuse** of `MAX_RECORD_BYTES`, separate from D31's whole-snapshot check (1107)
and D32's lifecycle-record check (~1921). `AUDIT_FIELDS` folds a full `label` audit from a
SEPARATELY 16KB-bounded lifecycle record into the audit line, so a near-ceiling snapshot plus a
near-ceiling adjudication can plausibly exceed the ceiling. The verifier confirmed reachability by
patching the constant down in a live session: `bounds-exceeded: refusing a 671-byte payload line`.
So this is the standing rule's FIRST branch, not the second — a live guard no test routes to, not
decoration. Keep it, cover it.

Everything else held under direct attack, including two mutations the verifier ran itself:
- Deleting the `verify_manifest` findings raise (~3379-3389) made
  `test_a_group_split_across_partitions_refuses_the_whole_export` fail cleanly — load-bearing, not
  masked. The test also calls `verify_manifest(forged)` directly to confirm `group-split` is the
  ONLY finding, ruling out a digest mismatch doing the refusing instead.
- Deleting `build_dataset`'s `if store_dir is None: raise` made the required-store test fail — and
  revealed the failure mode is a silent degrade to *excluded*, not a refusal, which is exactly why
  that guard has to be explicit.
- **The one-element-list trap is avoided ON PURPOSE and cites D26 by name**: `_pool()`'s own
  comment says "the uneven sizes are what makes the determinism assertions non-vacuous: with one
  group of one item, `sorted()` pins nothing." A defect this kit shipped once is now a documented
  fixture constraint.
- "Byte for byte" is real: `dataset["bytes"]` compared directly, `Path.read_bytes()` off disk, and
  a cross-process digest test spawning children under `PYTHONHASHSEED=0` and `424242`.
- `store_dir` confirmed to have no default by `ast.parse` of the signature — no import, no
  execution — and no wrapper supplies one.

**Three test-only gaps now dispatched together** (one implementer, `tests/test_training_data.py`
only): D33's uncovered line-size ceiling above; D34's `capture-wired-to-a-caller` `met` arm, the
only one of 11 gates with no positive control; and a pin on the canonical empty-store tally
{met:0, unmet:4, unknown:7} INCLUDING set membership, since a count alone lets one gate swap sides
with another unnoticed. The `CAPTURE_WIRED` test carries an explicit honesty fence: it proves the
ternary's arm is reachable when the constant is patched, and must never read as evidence a caller
exists — the structural test is what proves that, and the two are to be read together.

**Three gaps closed (opus, `tests/test_training_data.py` only, +136 lines, 3 tests, 0 deletions).**
`bin/training_data.py` byte-identical before and after (sha `4943e44b…` both times) — no production
change was needed. D33 and D34 move to `review=revised`.

Each test was mutation-proven, and two of the three proofs produced a stronger result than asked:

- **Gap 1, D33's line-size ceiling.** The mutant is printed verbatim in the agent's report; the
  file sha moved `4943e44…` → `7ec5e8c4…`, so it was not a no-op — the failure mode that has
  invalidated four runs in this kit. Under the mutant the new test went RED on both subtests, and
  **the export SUCCEEDED OUTRIGHT** — which is the empirical answer to "does another
  `MAX_RECORD_BYTES` site refuse first": none does. `persist`/`persist_lifecycle` run inside
  `self.resolve(...)` BEFORE the patch context is entered, and `snapshot`'s own check runs at
  fixture construction, earlier still. `build_dataset` reaches only line 3524. Masking ruled out by
  measurement, not by argument. Running the whole class against the mutant gave 54 tests,
  **failures=2, both new** — confirming every pre-existing test stays green when the block is
  deleted, exactly as the verifier found.
  The assertion pins the message phrasing `f"{size}-byte {what} line for {eid}"`, which the other
  three call sites do not use ("the record serializes to N bytes…", "refusing a N-byte snapshot
  line", "refusing a N-byte {kind} line"), so it cannot pass against any of them. Sizes were
  MEASURED off a control export (payload 671, audit 7261, ceiling 16384), not typed.

- **Gap 2, `capture-wired-to-a-caller`.** Mutating the ternary to a constant `"unmet"` and running
  the WHOLE module gave **239 tests, exactly one failure — the new one.** That is direct proof the
  `met` arm had zero coverage before, not an inference from a grep.
  The agent re-derived the "never branched on in production" claim by AST rather than trusting my
  brief, and **sharpened it**: `CAPTURE_WIRED` has exactly 7 Load sites, and the only branching
  node whose TEST names it is the `IfExp` at 4385 — the gate ternary itself. The `If` at 3840 looks
  like a branch on it but its test is `state["collecting"]`; the constant merely sits in the body.
  So the honest count is seven loads, one of which is a branch, and that branch is the gate.
  The test's name and docstring carry the fence explicitly — it proves the ternary has a reachable
  arm and is "NOT evidence that capture is wired, and it must never be cited as any" — and it names
  `test_no_production_path_calls_the_capture_hook` as the actual enforcement so the two are read
  together. It also asserts `not_established` still equals `readiness_codes()` under the patch:
  **closing this gate establishes nothing.**

- **Gap 3, the empty-store tally.** Re-derived independently before any assertion was written and
  matched: 0 met / 4 unmet / 7 unknown, with the membership I carried. The non-empty shapes were
  re-derived too and my brief was slightly loose — after `walked()` it is **met 6 / unmet 2 /
  unknown 3**, and with a dataset **met 8 / unmet 3 / unknown 0**. "6-of-11 and 8-of-11 met" was
  right; I had not stated the other two columns.
  Two mutants prove the pin bites where the old test does not. (1) Tally-changing: one gate flipped
  `unmet`→`unknown`. New test RED, `test_every_gate_state_is_reached_…` **GREEN** — the predicted
  drift. (2) Membership-only, two coordinated edits that keep the tally at 0/4/7 while two gates
  swap sides. New test RED, the old test **GREEN again**. So the membership assertions bite
  independently of the count, which is why a bare count was not enough.

**Suite: 5530 green, exit 0 (module: 239, exit 0).** Delta accounted: 5504 + 3 new + 23 collected
from D28's `tests/test_decision_release_matrix.py`, already on disk and picked up by `discover`.
**I am NOT treating 5530 as the boundary figure** — that run overlapped D28's mutation windows on
the tracked tree (below), so it will be re-run clean before I commit.

**Method hazard, carried forward as a kit rule.** D28's mutation harness is rooted at the
REPOSITORY, not an rsync'd copy: it mutates tracked source in place and restores afterwards. The
tree is currently clean (`bin/training_data.py` matches its pin; only D28's own `bin/release_gate.py`
is modified under `bin/`), so nothing leaked. But it is unsafe twice over — a concurrent suite run
that overlaps a mutation window is meaningless in both directions, and **a false SURVIVOR is the
dangerous one**, since it reads as "this guard is decoration" and invites deleting a live guard;
and a process killed inside the window leaves the repo silently mutated, which is not hypothetical
here because D28's first dispatch died to a 600s stall watchdog. D28 has been warned to re-run any
survivor it concluded, on a copy.

## D28 — Jev-free matrix

outcome: D28 model=opus attempts=2 result=pass review=pending run=2026-09-16-aa6e

`attempts=2`: the first dispatch died to a 600s stall watchdog having written nothing, so the brief
was re-sent unchanged. Nothing needed undoing — the pins were byte-identical across the failure.

**My own evidence, run from the repo root, unpiped, exit status read directly:** verify
`test_decision_release_matrix.JevFreeMatrixTests` **23 tests, exit 0**; full suite **5530, exit 0,
zero FAIL/ERROR lines**, with no mutation window overlapping it this time; `release_gate check`,
`docs_build check`, `copilot_docs check`, `sync_codex_surfaces check`, `sync_pricing_refs --check`
and the new `release_gate decision` all exit 0.

**I misread four gates as exit 2 first.** The shell here is zsh, which does NOT word-split an
unquoted variable, so `for g in "bin/x.py check"; python3 $g` passed the whole string as one
filename and python exited 2 on a missing file. The gates were green all along. **This is the
second time in this kit I have reported a false gate failure** — the first was calling
`routing_scorecard.py demo` when the documented form is `--demo`. Both times the rule that saved it
was the same: look at the actual output before calling it a regression.

**I also recorded a method hazard that was not real, and it is corrected here.** I wrote that D28's
mutation harness was rooted at the repository and mutating tracked source in place. It was not: the
harness built a tar copy under the scratchpad, `git init`-ed it so `git ls-files` works, ran the
unmutated control there, and `sed`-ed `ROOT` to the mirror BEFORE the first execution — the run's
own first line printed the mirror path. What the concurrent agent saw on disk was an unedited draft
that never ran. The pins held across the whole window. The general rule stands and D28 tightened
its harness anyway (it now REFUSES to start if `ROOT` resolves inside the repo), but the specific
accusation was wrong and the ledger should not carry it as fact.

**Mutation result: control exit=0 at N=23, twelve mutants, all RED, zero survivors.** One did
survive the first pass — `known_blocker=True` left the live-gate test green. Per the standing rule
the agent checked for the INPUT ROUTE before concluding decoration, and found it: the check only
differs when a gate names a blocker no owner declares, and every blocker in the table is a known
one, so the real tree can never exercise it. **It fixed the TEST, not the guard** — feeding in a
gate carrying `a-blocker-nobody-declares` and following the finding through to `run_check`'s exit 3.
That is the standing rule's first branch resolving correctly for the second time today (D33's
line-size ceiling was the other), and nothing was deleted as decoration.

**The seven adjudicated constraints, each verified by me rather than accepted:**

1. **No training capability row exists anywhere.** I walked the registry myself: zero rows whose
   path matches `train|capture|collect|dataset`. The mutation that adds one goes red.
2. **No `unknown` reduced by asserting.** I re-derived the census: **23 supported / 3 unsupported /
   36 unknown**. The 31 became 36 via exactly the five new `adaptive_decisions` rows, every one
   `verified: unknown` with `verified_on: null`. Supported and unsupported are UNCHANGED at 23 and
   3 — no existing row moved.
3. **Packaging untouched**; `| training/ | present |` remains the only training claim, and the
   generated prose spells out that it means the store's ignore rule is present, never a record.
4. **No `VERSION_SOURCES` row registered and no constant bumped** — so nothing new reads as a
   stored object.
5. **`canary`/`active` unavailable, machine-derived.** The cell is computed from
   `workflow_eval.CONFINED_DISPATCH_WIRED`; flipping the constant moves it, which is the test.
   D23's refusal is cited by name, never routed around.
6. **Cursor's two claims kept apart** in two separate columns: the adaptive profile `unsupported`
   pending independent proof, beside Cursor's six dated `verified: supported` rows with their
   client version. `bin/cursor_adapter.py` and `bin/cursor_execute.py` untouched.
7. **Host limitation and design decision linked, not merged.** `confined_dispatch` is measured,
   dated 2026-09-06, macOS — and I confirmed it is the ONLY harness carrying such a row. It rides
   in the OS/Enforcement columns; `CONFINED_DISPATCH_WIRED` rides in Decision mode and reaches all
   five. A test asserts exactly that asymmetry.

**Limitations left in place deliberately, and they belong in D30's handoff:**
- The AST scan is **per-file over two named lists, not transitive** — a module reached only through
  `_sibling()` at call time is not walked unless listed. The behavioural test covers the transitive
  case only for the paths it actually exercises (startup, rules, replay, rollback).
- **The OS column is empty for codex, copilot, cursor and stub.** That is the honest state; Claude's
  macOS evidence was deliberately not allowed to read across to another harness.
- Baseline conformance **reuses D02's frozen goldens** rather than adding per-adapter tests — the
  one-authority choice. The new work is the per-adapter separation and id resolution.
- `adaptive_decisions` derives `effective: unsupported` from `implemented: unsupported` (a design
  fact — the modes are refused by name) while `verified` stays `unknown` because nobody ran
  anything. Each row's note states that distinction.
