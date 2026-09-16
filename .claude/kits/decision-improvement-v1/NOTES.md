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
- **Drift hazard, unfixed by design**: `kit_contract.parse_plan_routing` (line 835) validates a
  PLAN.md `routing:` line against its own `PLAN_ROUTING_KEYS` tuple, independent of
  `routing_policy`'s `POLICIES`/`PREFERENCES`. The two vocabularies can drift with nothing
  failing.

`outcome: D01 model=opus attempts=2 result=retry-pass review=revised run=2026-09-16-aa6e`
`agent: D01 id=a4a14bf role=implementer model=opus`
`agent: D01 id=ab236ea role=verifier model=sonnet findings=3 confirmed=3 result=revised`
`defect: D01 kind=contradictory-acceptance`
