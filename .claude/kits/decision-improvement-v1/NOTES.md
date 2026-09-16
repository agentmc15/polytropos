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
