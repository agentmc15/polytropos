# NOTES — repo-bench

Execute-owned. Cross-task learnings plus the machine-read ledger lines.

## Run log

Run id for this session's lines: `2026-07-31-63c6`.

Warm clusters this run: T2 → T3 served by ONE warm sonnet implementer (same file
`bin/repo_bench.py`, same pin) — both tasks carry the same agent id by design.

## Learnings for later tasks

- T1 widened two signatures beyond the brief, both backward-compatible with the calls the
  briefs make: `git_sandbox(sandbox, *args, git_runner=None)` and
  `capture_patch(sandbox, init_commit=None, git_runner=None)`. `capture_patch(sandbox)` still
  works — T5 can call it exactly as its brief writes it.
- T1 added `SANDBOX_GIT_CONFIG` (pinned identity + `init.defaultBranch=bench`) so no code path
  depends on the ambient branch name — R3's portability tripwire is already handled for
  sandbox-side git; fixture repos in tests still need their own `-c user.name`/`user.email`.
- `capture_patch` derives the baseline via `rev-list --max-parents=0 HEAD`, so a candidate
  that makes its own commits cannot move the diff baseline. Relevant to T5's dispatch loop.
- `_load` (importlib) is in place and `claude_execute` is lazy-loaded via `_ce()`; T4/T5/T8
  should reuse that accessor rather than re-importing.
- The full suite prints unrelated stderr from other kits' error-path tests
  (`kit-verify-hook: …`, `FAILED next_day`, `unknown role 'bogus'`). Pre-existing and not a
  repo-bench signal — the suite result line is what counts.

## Phase 1 review — findings carried FORWARD (binding on later tasks)

The P1 reviewer raised 11 findings; the orchestrator adjudicated all 11 as real. F1, F2, F3,
F4, F6, F7, F10, F11a are fixed in T3R. These four are NOT code changes in Phase 1 — they are
binding constraints on later tasks, recorded here because the task briefs do not carry them:

- **F5 (T6 + T7, measurement validity).** An issue-replay `reference_patch` is the FULL
  `git diff base..fix`, so it contains the fix commit's test hunks — files the candidate
  structurally cannot produce, because those blobs are deliberately withheld from its sandbox.
  Two consequences: `oracle_structural` will systematically depress `files_jaccard` /
  `hunk_overlap` for CORRECT candidates, and the judge sees one patch that adds tests and one
  that never does — a reliable tell that partially defeats D6's blind `Patch A`/`Patch B`
  slots. T6/T7 must strip test-pattern paths from the reference before similarity scoring and
  before judging, OR label the bias explicitly in the result. Do NOT change what T2 mines —
  the blobs are needed for the tests oracle.
- **F8 (T4, honesty label).** `mine_general_tasks` stops at `limit * 4` examined sites. Green
  discards get a note, but exhausting the bound with fewer than `limit` tasks emits nothing
  saying coverage was truncated. D8's partial-coverage labels apply — T4's plan card must say
  so when it happens.
- **F9 (T4, decision quality).** `choose_mode` counts issue pairs, not objectively-SCORABLE
  pairs. Issue pairs may carry `oracle_tests_available: False`; general tasks are always True.
  So `auto` can pick issue-replay with 5 unscorable pairs over a general fallback that would
  have cleared the D7 floor — a guaranteed below-floor verdict. T4's plan card must print the
  oracle-available count inside the mode `reason`.
- **F11b (T4 + T5, D11 accuracy).** `mine_general_tasks(scratch_dir=None)` puts scratch
  sandboxes in a SYSTEM temp dir, but D3/D11 claim all mutation happens under the run dir.
  T4/T5 must pass `scratch_dir=<run-dir>/work` or the D11 honesty claim is inaccurate.

## T3R — a defective verify clause, and why it carries no `defect:` line

T3R's brief was authored by EXECUTE, not the architect, and its verify probe shipped with a
broken clause: the stub test-runner keyed redness on `'big'`, a string no operator in
`MUTATION_OPERATORS` can remove, so every mutation read as green, zero general tasks were
admitted, and the clause failed against a CORRECT module. The implementer verified that
against the pre-T3R module before changing anything and stopped to report it rather than
weakening red-validation to force a pass — the right call, since red-validation is T3
acceptance law. The orchestrator fixed the one line (now keyed on the mutated operator text)
and re-ran the block itself, green.

No `defect:` line is recorded for this. That ledger measures the ARCHITECT's briefs; T3R's
brief is execute's own, and attributing its flaw to the architect would corrupt the very
signal the next kit is supposed to read.

## T4 — a spend-gate bypass, and the guard T5 must reuse

T4's first dispatch passed every test and its own verify block, and still shipped a real
ceiling bypass: `--max-usd nan` parses cleanly through argparse, satisfies the structural
"ceiling is not None" check, and then defeats `grand_total > max_usd` outright, because
`x > nan` is False for every x under IEEE-754. Reproduced live — a $0.165 plan accepted
against a `nan` ceiling, run dir written, exit 0.

The fix is `validate_ceiling(max_usd)` (`bin/repo_bench.py`), called from `cmd_run` BEFORE
the run dir is created and before both the structural check and the comparison. It rejects
non-finite and negative values through the same exit-2 refusal path; `None` passes through
so the structural check stays the thing that refuses a missing flag.

**T5 MUST call `validate_ceiling` for its per-dispatch re-check rather than re-deriving the
test.** PLAN D1 requires the ceiling to be re-checked before EVERY dispatch, judge grades
included; a ceiling checked in two places is a ceiling that will eventually be checked two
different ways, and this defect is the proof. The helper is named and importable for exactly
that reason.

Also recorded as an architect defect: PLAN's "Done means" clause 6 requires that "no existing
test changes", but the kit's own sequence guarantees one — T4 implements `plan`/`run`, which
makes T1's `test_unimplemented_subcommands_exit_2` assertion false by construction. The
implementer correctly narrowed it and added broader replacement coverage.

## Phase 2 review — findings carried FORWARD (binding on later tasks)

11 findings, all 11 adjudicated real. F1, F2, F3, F4, F6, F7, F8, F9 are fixed in T5R; F10 is
fixed by pulling T10 forward. These three are binding constraints on later tasks:

- **P2-F5 (T7, spend accounting).** `grade_cells(cells, **kwargs)` is called as
  `grade_cells(cells)` — it receives NO `spent_usd`, `max_usd`, `pricing`, or `run_path`, and
  it sits after `spent_usd` accumulation and immediately before `_spend_basis(cells)`. If T7
  fills the seam in that shape, judge dispatches run OUTSIDE `would_exceed_ceiling`, judge
  dollars never enter `spend.spent_usd`, and the envelope basis is derived from candidate
  cells only — three separate under-counts. **T7 must change `grade_cells` to take and return
  spend state, and every judge grade must pass through the same ceiling check as a candidate
  dispatch.** Today's numbers are structurally safe only because the pre-run gate reserves
  `judge_total` inside `grand_total`; that reservation is not a substitute for the check.
- **P1-F5 + Nit (T6).** The reference patch still contains the fix commit's test hunks. Strip
  test-pattern paths at the GRADING boundary (structural similarity and judge), and apply the
  same strip to `size_profile` sizing — otherwise candidates are priced for LOC they
  structurally cannot produce, and the judge gets a tell. Do NOT change what T2 mines.
- **T6-informational (T11, skill text) — test-path detection is substring-based.**
  `DEFAULT_TEST_PATTERNS` matches by naive substring, so `latest/foo.py` or
  `contest_data.py` would incidentally be treated as a test path — stripped from the
  reference at the grading/sizing boundary, and (at mining) have its blob withheld from the
  candidate's sandbox. Pre-existing from T2, deliberately loose by design ("never a glob
  engine"), and judged out of T6's scope. Not worth a remediation task, but it IS a real
  limitation: T11 must disclose that test-path detection is substring-based and that
  `--test-patterns` (or equivalent) is the escape hatch for a repo whose layout trips it.
- **T7-informational (T8, one-line test strengthening).** An aborted run must not spend on
  judge grading — `cmd_run`'s `finally` gates `grade_cells` on `completed`. The property is
  enforced in code and was proven by mutation (removing the gate makes an aborted run dispatch
  a grade and spend), but it is only asserted INDIRECTLY, via
  `EnvelopeAlwaysWrittenTests.test_a_mid_loop_exception_still_writes_a_labelled_envelope`.
  T8 already extends the tests — add the direct assertion that an aborted run's envelope
  carries `grades: []`.
- **T7R carry-forward (T8, cell shape).** Cells now carry `candidate_touched_tests` (list, or
  `None` on a skipped cell) — a candidate that edited tests is not proof of gaming, but a
  `solved` earned alongside test edits must be VISIBLE in the verdict. `oracle_structural` can
  now be `available: False` with all-`None` metrics and must render `n/a`. Grades carry a
  second skip reason, `empty-reference`, which is NOT a budget casualty and must not be
  counted as one. New envelope labels exist: `GRADING_FAILED_LABEL`, `STORE_WRITE_FAILED_LABEL`.
  A demoted tests record now carries `rc: None` (the stale `rc: 0` is gone; still never read
  `rc` as a signal).
- **T7R-informational (T8, two one-line test additions).** Two behaviors are correct in code
  and proven by hand, but not asserted by any test: (a) an aborted run's envelope carries
  `grades: []`; (b) the store-write guard — a failing `tasks/*.json` write must still leave a
  labelled envelope carrying `STORE_WRITE_FAILED_LABEL`. The orchestrator and the T7R verifier
  each confirmed both manually. T8 already extends the tests; add both assertions.
- **Audit limitation worth knowing.** This repo has a single commit and the whole kit plus
  `bin/repo_bench.py` / `tests/test_repo_bench.py` are UNTRACKED working-tree content, so no
  verifier can diff a task's changes against a prior state. Judgements about "was this
  pre-existing test weakened or forced" are therefore made from current-state evidence and
  reasoning, not from a diff. Reviewers should say so rather than implying diff-backed
  confidence.
- **A carry-forward gap execute owns.** T3R's F7 fix added a test forbidding the literal
  `PLUGIN_ROOT / "data"` in this module. T8's architect-written brief then specified the
  benchmarks default as exactly `PLUGIN_ROOT/"data"/"benchmarks.aa.json"`. The remediation made
  a later brief unimplementable as written, and NOTES never recorded it — that is execute's
  carry-forward failure, not an architect defect, so no `defect:` line. T8's implementer
  resolved it correctly by reusing `bench_routing.DEFAULT_BENCHMARKS_PATH` (same resolved
  path, strictly more D10 reuse, existing test untouched). **Lesson for the rest of the run:
  when a remediation forbids something, check what LATER briefs already assume.**
- **P2-F11 (T11, skill text).** `cmd_plan` mines through a SYSTEM temp dir (there is no run
  dir on the plan path), so D11's "all mutation happens under the run dir" is accurate for
  `run` but not for `plan`. T11 must not repeat that sentence unqualified.

## The leak chain, and what it cost to actually close

Worth reading before Phase 3, because the pattern recurs: **every leak found in this kit
passed its own tests.**

- F1 (ancestor dirs): the guard test checked inside the cell directory while
  `reference_patch` and `test_blobs` sat one `../` away in `tasks/<id>.json`.
- The sandbox-history leak: T1 PROVED and tested "sandbox has exactly one commit" — then T5's
  `prepare_cell_sandbox` added a second commit, and T1's proof silently stopped being true
  because the test guarded the moment, not the invariant.
- `--amend` alone did NOT close it. The reflog still held the pre-amend commit
  (`git diff HEAD@{1} HEAD` = the answer) and the clean blob survived as a dangling object
  (`cat-file --batch-all-objects`). Closing it needed three legs: amend +
  `core.logAllRefUpdates=false` + `git prune --expire=now`.

**A correction execute owns:** T5R2's brief probe asserted the MUTATED line never appears in
`git log -p`. No correct implementation can satisfy that — `log.showRoot` defaults true, so
the root commit renders as a whole-tree creation diff, and the mutated tree IS the candidate's
legitimate base state. The implementer flagged it, resolved it with a
`log.showRoot=false` sandbox config key, and stated plainly that the key closes NO leak on its
own. That adjudication is accepted: the key stays (harmless, and coherent beside
`core.logAllRefUpdates=false`, which closes a real one), and the PROBE was corrected to assert
the real property — that the ORIGINAL, pre-mutation content is unrecoverable from log, reflog,
all objects, and fsck, while the mutated line remains present in the worktree by design.
Orchestrator-verified clean on all four channels. As with T3R, no `defect:` line: the
defective clause was execute's own brief, not the architect's.

## Phase 3 review — the two lessons worth carrying

1. **"Designed to see it" is not "allowed to know which is which."** T7's test excluded the
   judge's cwd from the ancestry hunt because the judge is DESIGNED to see both patches. True
   — and irrelevant. Seeing both patches is grading; knowing which is the reference is the
   bias control D6 exists to protect. The T7 verifier accepted that reasoning too. When a
   fence is narrowed on a rationale, check the rationale against what the fence PROTECTS, not
   against what the code does.
2. **The leak work protected the answer and forgot the oracle.** Three remediation tasks kept
   `reference_patch` away from the candidate. Meanwhile `solved` — the one objective signal,
   the only thing D5 lets produce a correctness verdict — was computed from a copy of a tree
   the candidate can write to. R6's tripwire was watching for (b)/(c) being promoted into
   "solved"; the real inflation vector was a forgeable (a).

Carried to T8 (verdict), from the review's "what T8 inherits" section — the cell shape makes
blending hard, which is right, but three traps come with it:
- Judge grades live in a SIBLING top-level `grades` list joined on `(task_id,
  candidate_model)`; there is no `oracles["judge"]` key, so an ABSENT grade must be
  synthesized as `n/a` rather than skipped.
- A skipped cell collapses all four oracles into one `"oracles": None` sentinel — T8 must
  expand that into four labelled `n/a`s, not one blank.
- Oracle (d) is bare cell scalars (`wall_seconds`/`usd`/`usd_basis`) OUTSIDE `oracles`; its
  `None`s are the kind a renderer prints as `0.00`.
- A demoted tests record keeps `"rc": 0` from the pre-demotion run beside `"passed": null` —
  never read `rc` as a signal.
- Judge grading is a POST-LOOP pass, so budget is consumed candidate-first: an overspending
  run drops 100% of judge grades rather than a proportional slice. Worth a line in the
  verdict when it happens.

## A miss the orchestrator owns, recorded because the shape recurs

While probing T9 by hand, the orchestrator fed `apply_verdict` a verdict card using the PREFS
payload schema (`tiers` / `daily_driver` as a bare id) instead of the VERDICT card schema
(`tier_map.slots` / `daily_driver.pick`). The staleness guard did not fire, and the
orchestrator concluded "my probe was wrong" — which it was, about the schema — and moved on.

The T9 verifier then found the real defect underneath: `tier_map.get("slots") or {}` means a
differently-shaped card yields ZERO ids to check, and zero ids read as a PASS. The orchestrator
had the defect in hand and explained it away, because the wrong-fixture explanation was
sufficient and arrived first.

**The lesson, which is the same one the phase reviews keep teaching:** when a guard does not
fire, "my input was malformed" and "the guard fails open on malformed input" are the SAME
observation. Finding the first explanation does not discharge the second. The same run's
T9 defect #1 was the identical shape — `verdict.get("below_floor")` treating an absent key
as `False`, so a card that never declared itself above the floor was applied.

## Phase 4 review — the kit was NOT complete, and why

9 findings, all 9 adjudicated real. The blocking one is F1, and it is the third instance of a
single recurring shape:

- Phase 2 protected the ANSWER (`reference_patch`) from the candidate.
- Phase 3 found the ORACLE (`solved`) was computed from a tree the candidate could write, and
  T7R restored every path matching `DEFAULT_TEST_PATTERNS`.
- Phase 4 found the TEST HARNESS is not a test-pattern path. `conftest.py`, `run_tests.py`,
  `Makefile`, `tox.ini`, `pytest.ini`, `setup.py`, `noxfile.py` all return False from
  `_matches_test_pattern`. A stub candidate that touched no module and no test-pattern file,
  and merely rewrote `run_tests.py` to `sys.exit(0)`, earned 6/6 `solved`, cleared the D7
  floor, and was APPLIED to a prefs file. `candidate_touched_tests` stayed empty.

Each fix was correct for the layer it was aimed at, and each left the next layer out
untouched. The generalisation worth carrying into the next kit: **whenever you restore "the
oracle" from a trusted source, enumerate what the oracle actually CONSISTS of at run time —
not what it is named.** A pattern list describes names; `--test-cmd` describes behavior.

**The invariant that was never written down — and is the actual root cause of all three:**

    the grade result is a function of
        (base tree, the candidate's IN-SCOPE patch, the reference test blobs)
    and nothing else.

Every one of the three fixes was a CASE ("a candidate can do X, so block X"). None stated the
rule, so each time a new X appeared, the rule had to be rediscovered from a fresh forgery.
Stated as above, the harness question answers itself — and so does the next one nobody has
thought of yet.

T12R therefore builds the grade substrate as a WHITELIST (construct from base + in-scope hunks
+ reference blobs) rather than a blacklist (take the candidate's tree, revert the bad parts),
and proves the CONSTRUCTION with a property test rather than proving outcomes with more case
tests. Nothing adversarial has to be anticipated, because nothing outside the scope is ever
applied.

**PLAN D5 and GUARDRAILS never stated this invariant** — that is an architect-level gap, and
the reason four reviews found four instances of one missing rule. A future kit touching this
code should carry the invariant as a PLAN decision or a GUARDRAILS fence, not as prose here.

**How T12R implemented it, and the three judgment calls it stated rather than buried:**
`oracle_tests`'s second parameter is now the candidate's captured PATCH, not its sandbox path
— the candidate's tree is not an input at all, which makes the invariant legible at the call
site instead of only honored inside the function. The blacklist helpers were deleted, not left
unused. Substrate = `prepare_cell_sandbox` (base + mined `setup_patch`) → `git apply` of the
in-scope slice only → `test_blobs` written last. The three calls:
  (a) the mined `setup_patch` counts as trusted base state — necessary, because in general
      mode the literal base tree is GREEN (the bug lives in `setup_patch`), so a literal reading
      would mark every general-mode candidate solved. It is a mining artifact no candidate can
      write.
  (b) `target_repo=None` now REFUSES to grade rather than falling back to a cleaned candidate
      tree — that fallback IS the forgeable grade, so there is deliberately no fallback.
  (c) an unappliable in-scope slice refuses rather than grading an unpatched substrate, which
      would report a `not solved` nobody measured.

Orchestrator-verified end to end: with `run_tests.py` confirmed NOT to match any test pattern,
the forgery (rewrite the harness, fix nothing) reads `passed=False`, and a genuine in-scope fix
still reads `passed=True`. The fix did not have to anticipate `run_tests.py` — that is the
difference between an invariant and a longer list.

**Residual risk that cannot be engineered away, and must be documented rather than claimed
away:** the candidate's IN-SCOPE file is still executed by the tests, so a candidate could
write a module that subverts the runner on import. Real sandboxing is out of scope and PLAN
D11 explicitly refuses to claim sandboxing theater. The honest reading of `solved` is: "the
reference tests passed against a substrate containing only the candidate's in-scope changes"
— strong, but not proof against adversarial code execution.

## Post-completion: what the first REAL `plan` revealed (no spend)

Ran `plan --repo . --models haiku,sonnet,opus --test-cmd "python3 -m unittest discover -s
tests -q" --limit 3` against polytropos itself. Result: **0 tasks, $0.00**, and two honest
labels fired correctly (issue-replay found 0 pairs on a 1-commit snapshot; general mode
reported partial coverage). The tool refused to invent work — right behavior.

But the 12 examined sites were **all the same operator** (`and-to-or`), all green:

    note: mutation discarded (green, not a discriminating bug): site 1 (and-to-or)
    ... sites 2-12, every one (and-to-or)

**The limitation, worth a fix in a future kit:** `MUTATION_OPERATORS` is an ORDERED tuple with
first-match-wins per site, and `mine_general_tasks` walks files in a fixed order under a
bounded scan (`limit * 4`). So a repo whose early-scanned files are dense in one operator
burns the entire budget on that operator and never reaches `==`→`!=`, off-by-one, or the
others — and never reaches later files at all. Twelve consecutive greens is the signature of a
scan stuck in one seam, not of a well-tested codebase.

Every general-mode TEST uses a small fixture where the first operator hit is the intended one,
so no test could surface this. It took a real repo. Candidate fixes: round-robin or shuffle
across operators, cap sites per (file, operator) pair, or scan breadth-first across files
before depth-first within one. Any of them wants the bounded-scan note to also say WHICH
operators/files were reached, so "0 tasks" is distinguishable from "0 tasks after looking at
one seam".

## Post-completion: a FIFTH leak channel, found by target research (not yet fixed)

Researching real benchmark targets surfaced a leak the whole kit missed, in the same family as
the other four and one ring further out again.

`mine_issue_tasks` builds `statement` from the commit subject + body when `use_gh` is off
(the default), labelled `statement from commit message (weaker than issue text)`. On repos
that squash-merge with the PR description in the body, **that body frequently describes the
FIX, not the bug.** Measured examples:

- pyright #11541 — "add a regression sample for `class A: get_class = lambda: __class__`"
- black #5241 — "`can_omit_invisible_parens` now returns false when…"

Average commit-message length for fix+test commits, from a 300-commit sample per repo:
markitdown 1056 chars, black 974, pyright 917, tox 891, attrs 505, scrapy 472, langchain 397
(rich bodies — LEAK-PRONE); pydantic 101, click 79, requests 74, autogen 158, fastapi 167
(title-only — no leak, but the model gets a one-line title as its entire problem statement).

Every leak fence in this kit guards `reference_patch` and `test_blobs`. The STATEMENT is a
third channel into the same place, and `build_prompt` deliberately includes it — it has to,
it is the task. So this is not a fence bug; it is an unmodelled property of the source data.

Share of fix+test commits carrying a REAL issue link (`Fixes #N` / issues URL) rather than
just a PR number: pyright 12/25 (best), tox 3/21, attrs 3/6, click 2/10, black 1/8,
scrapy 1/9; pydantic, fastapi, langchain, requests, autogen all 0/N. Note `(#N)` in a squash
subject is usually a PR number, not an issue number — the miner cannot tell them apart.

Candidate mitigations for a future kit, none implemented: (a) detect fix-describing statements
(they name identifiers that appear in the reference patch) and either drop the task or strip
to the subject line, with a label; (b) prefer the `--with-gh` issue-text path on repos whose
bodies are long, and record `statement_source` in the verdict so a reader can weigh it;
(c) at minimum, LABEL a task whose statement shares identifiers with its own reference patch —
same "evidence, not guarantee" posture used for `candidate_modified_out_of_scope`.

## T17 — the leak direction the BRIEF created, and the design deviation that was right

Two things worth carrying forward, both from the implementer rather than the orchestrator.

**1. A safety argument that only runs one direction is half an argument.** T17's brief argued
the prepared template is safe because nothing a candidate wrote can reach it. True — and
irrelevant to the actual hazard. The brief ALSO specified (item 6) that templates live under
`<run-dir>/work/`, one `../` from a candidate's cwd. In general mode the candidate's sandbox is
base + the injected `setup_patch`, so a template built from the PRISTINE base is a brand-new
answer key: `diff ../templates/<key>/build/calc.py ./calc.py` is the bug. The orchestrator
wrote the leak into the brief while arguing the feature was safe.

Closed three ways, all structural: the template's build tree is built by
`prepare_cell_sandbox` (so it carries the task's own `setup_patch` and is byte-identical to the
state the candidate starts in); the cache key includes that setup patch (so general-mode tasks
sharing a base commit but carrying different injected bugs never share a template); and the
build tree is deleted the moment its artifacts are captured. Stated cost, not buried: general
mode gets one preparation per task and `--setup-key` cannot collapse it — collapsing is an
issue-replay feature.

**The generalisable rule:** when adding an input to the grading substrate, check BOTH
directions — can the candidate influence this, AND can this tell the candidate anything. Every
leak in this kit was found in the second direction after the first was argued.

**2. The brief's caching design was unsound and the implementer said so.** It specified that
grade substrates COPY the prepared template tree. That breaks the moment `--setup-key` works:
two tasks share a key while having DIFFERENT base commits, so copying task A's tree as task B's
substrate grades B against A's source. The implementer stored only the setup ARTIFACTS
(snapshot diff across the setup command, collapsed at directory granularity so `npm ci` yields
one `node_modules` entry) and overlays them on each task's own base. Re-extraction is a
`git archive` that happens anyway; the install — the expensive part — still runs once per
template. Correctness kept, acceptance still met.

**3. A product consequence, documented rather than left implicit.** Setup never runs in a
candidate's sandbox (the brief forbade it, correctly — it is a leak channel). So on a target
needing an install step, the candidate CANNOT run the tests while it works. That is a real
handicap the measurement carries, and it is now stated in the skill beside the flag.

## The sixth ring, and the two questions that would have caught all of them

T17 shipped a WORKING FORGERY. A candidate that changed nothing in its own sandbox could write
`../templates/<key>/artifacts/vendor/dep.py`; `overlay` copied those bytes into its grade
substrate; the cell read `passed=True` with `candidate_modified_out_of_scope` and
`candidate_touched_tests` both EMPTY — no trace in the patch, counting toward the D7 floor,
eligible for `apply`.

**Why it survived:** T17 was the only task in this kit that added a new input to the grading
substrate, and it was the one task that received no independent review — five post-completion
tasks were verified only by their own tests and the orchestrator's probes, after four phase
reviews had each found something per-task checks missed. It was caught by the review that
should have run before it shipped.

**The false claim did the real damage.** "A template is built before any candidate for that
task has been dispatched" appeared twice in the engine and once in the skill, and was untrue —
templates are prepared lazily inside grading, which runs after dispatch. That sentence made the
leak look impossible to every reader including the orchestrator, who wrote a brief arguing the
feature was safe while specifying (item 6) the directory layout that made it unsafe. A safety
claim that is not true is worse than no claim, because it stops people looking.

**The generalisation — two questions, not one.** Every previous ring was found by asking
*can a candidate influence this input?* (construction). T17's implementer asked exactly that,
answered it correctly, and closed the construction-side leak it found. The hazard was the other
question: *for how long does this input sit somewhere a candidate can reach?* (lifetime). Ask
BOTH of every input to the grade substrate:

    construction — can a candidate influence what goes into this?
    lifetime     — how long does it sit where a candidate can reach it, and is it writable?

**Fixed twice, independently** (because five prior single fixes were each one ring short): the
artifact store moved OUT of the run dir into a 0700 `mkdtemp` whose name appears in no
candidate-readable file (the T7R judge-cwd carve-out precedent — the setup command still
executes under `work/`, only the inert store leaves), AND every artifact is content-hashed at
capture and re-verified before every overlay, with a mismatch rendering `available: False` /
`passed: None` plus a labelled envelope. `demo` part 5 now proves both, including a raid that
sweeps `../` and `../..` and finds 0 even under `--keep-work`.

`--setup-key`'s cross-base sharing was made STRUCTURAL rather than documented away: an artifact
path tracked at either base is refused outright, and otherwise the template is re-prepared at
the second base and digests compared before sharing. Stated residual, not buried: that is
evidence across two bases, not proof for a third.

## Known gap, hand-verified, not blocking

The build tree at `work/templates/<key>/build` is deleted unconditionally at the end of
`_prepare` — including on the setup-FAILURE path, which the T17R verifier confirmed by hand
(setup rc=7 leaves neither the build dir nor the key dir behind). That failure-path deletion
has no dedicated test. Trivial to add; recorded here so it is a known gap rather than an
assumed one.

## First LIVE run — what real dispatches taught (run 2026-08-05-515a, $5.70 actual)

First run with real money, against microsoft/pyright. It aborted after 3 cells because the
TARGET REPO was destroyed mid-run — `/private/tmp` reaping deleted every loose file in its
`.git` (HEAD, config, index, packed-refs) at midnight while leaving every directory, five days
after the clone. **Not the tool:** `git_target` still refused every write verb, and no dispatch
record referenced the target path. Operational lesson: never park a benchmark target in
`/private/tmp` for a multi-day workflow.

**The tool behaved correctly under a failure nobody designed for.** It raised, and the T5R/F6
`try/finally` still wrote a labelled envelope rather than losing it:
`partial (aborted) — the dispatch loop raised before completing; cells that never ran are
absent from this envelope entirely, not recorded as skipped`, with `spent_usd: 5.70`,
`basis: actual`.

**THE FINDING WORTH ACTING ON — `task_profiles` under-predicts real agentic spend by ~10x.**
Measured on `issue-11570` (size=S), all three candidates:

    model    tests        actual     estimated   ratio   wall
    haiku    not solved   $0.52      $0.06       8.7x    420s
    sonnet   SOLVED       $1.28      $0.12       10.6x   644s
    opus     not solved   $3.58      $0.30       11.9x   550s

The full 10-task matrix was planned at $17.22; at these rates it would have cost **$100-200**.
The $25 ceiling would have stopped it around cell 12 of 30 — the gate works, and it is the
only thing standing between a user and a 10x surprise. The `planned estimate from
task_profiles — not a bill` label is doing real work and must never be softened. A future kit
should either calibrate `task_profiles` against recorded actuals (the run store now holds
them) or make `plan` state the historical estimate-vs-actual ratio beside its total.

**Two mechanisms confirmed on live work rather than fixtures:**
- T12R's whitelist caught a real candidate wandering: haiku modified `package.json` and
  `package-lock.json`, both outside the reference patch's scope — recorded in
  `candidate_modified_out_of_scope` and excluded from the grade substrate.
- All three candidates edited a test sample file (`matchLiteral1.py`/`matchLiteral2.py`),
  flagged in `candidate_touched_tests`; the restored reference test surface meant none of it
  could earn a pass. Sonnet still solved it legitimately; haiku and opus did not. **n=1 — this
  says nothing about the models and must not be quoted as if it does.**

Also observed: `--setup-key package-lock.json` did NOT collapse — pyright's lockfile is at
`packages/pyright-internal/package-lock.json`, not the root — so F7's absent-path label fired
correctly and the run keyed on base commit instead (2 templates, 5 gradings served, 13.7s of
setup). The label is what made that visible rather than silent.

## T19 — the last two recorded gaps, closed

Both were recorded in NOTES as known-but-unfixed; neither was a defect in shipped behavior.

- **Failure-path deletion now has a test.** `work/templates/<key>/build` was already deleted
  when `--setup-cmd` fails — a verifier confirmed it by hand — but the `rmtree` sits OUTSIDE
  the `if record['ok']:` block and nothing would have caught an edit moving it inside, which
  would leave a failed template's tree under the run dir, one `../` from a candidate. Hand
  verification is not coverage.
- **F8's exclusion count is honest without reordering the check.** T17R's implementer
  declined to reorder because T13's tests and the count's meaning both depend on the current
  order; T19 kept that and gated the NOTE append on a `quota_met` flag instead. Orchestrator
  probed BOTH branches, which is the real risk surface of a flag approach: with the fix
  commit newest, `--limit 1` reports 0 exclusions (none were needed); with three bumps newest
  and the fix beneath, `--limit 1` still reports all 3, because the walk had to pass them.
  Suppressing pre-quota exclusions would have been the silent-shrinkage failure T13 exists to
  prevent.

T19 carries `review=none`: no independent verifier ran, only orchestrator probes covering
both branches. Recorded as it happened rather than as `clean` — the same correction made to
T17R's line earlier, and the distinction that separates a checked claim from an asserted one.

## Ledger

Read the T2 outcome with this context: its implementer dispatch STALLED on a harness
watchdog (no progress for 600s) partway through running its own verify block. The
implementation had already landed and the orchestrator re-ran the whole verify block itself,
green. So T2 is recorded `result=pass attempts=1` — the work passed on its first dispatch and
no retry was ever made. The stall was an infrastructure event, NOT a signal about the sonnet
tier, and deliberately carries no `failure=` class (that vocabulary is for blocked/escalated
outcomes only). The warm T2 → T3 cluster died with the agent; T3 was dispatched fresh.

agent: T1 id=a7b03b45c4f9b70ed role=implementer model=opus
agent: T1 id=af27c81585f3fac8f role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T1 model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T2 id=af58c5760f6fba5f3 role=implementer model=sonnet
agent: T2 id=ad5b751968ca1a6ec role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T2 model=sonnet attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T3 id=afa0032d132f1ba96 role=implementer model=sonnet
agent: T3 id=a4b063a919298acaa role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T3 model=sonnet attempts=1 result=pass review=clean run=2026-07-31-63c6
reviewer: P1 model=opus findings=11 confirmed=11 result=accepted
defect: T3 kind=underivable-requirement
agent: T3R id=ad1e851fb0a448b0b role=implementer model=opus
agent: T3R id=a38aacaa6471a13ff role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T3R model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T4 id=a071c51d68a217ec7 role=implementer model=sonnet
agent: T4 id=a1369daea9d63d093 role=verifier model=sonnet findings=1 confirmed=1 result=accepted
agent: T4 id=a92fa9ab221117871 role=implementer model=sonnet
agent: T4 id=a10bdfb5427c085be role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T4 model=sonnet attempts=2 result=retry-pass review=revised run=2026-07-31-63c6
defect: - kind=contradictory-acceptance
agent: T5 id=ad9c8c5c66f447c44 role=implementer model=opus
agent: T5 id=abe8f093bc112d548 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T5 model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
reviewer: P2 model=opus findings=11 confirmed=11 result=accepted
defect: T5 kind=contradictory-acceptance
agent: T5R id=a06353ade20a7270c role=implementer model=opus
agent: T5R id=a807723a6b5363a89 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T5R model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T5R2 id=ac38c02a3c6862a10 role=implementer model=opus
agent: T5R2 id=a807723a6b5363a89 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T5R2 model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T6 id=a739d44c2dba84e24 role=implementer model=sonnet
agent: T6 id=a3496eb9223074d97 role=verifier model=sonnet findings=1 confirmed=1 result=accepted
outcome: T6 model=sonnet attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T7 id=a8f78b73b0d6bd854 role=implementer model=sonnet
agent: T7 id=a1acf093de249de60 role=verifier model=sonnet findings=1 confirmed=1 result=accepted
outcome: T7 model=sonnet attempts=1 result=pass review=clean run=2026-07-31-63c6
reviewer: P3 model=opus findings=6 confirmed=6 result=accepted
agent: T7R id=a0b3d77b7a97bd5fb role=implementer model=opus
agent: T7R id=a6f3add7266b2e7ff role=verifier model=sonnet findings=1 confirmed=1 result=accepted
outcome: T7R model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T8 id=ac0e370ad66fe05be role=implementer model=opus
agent: T8 id=a6078fd25abf48d5e role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T8 model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T10 id=adba3a04dd9b0a25b role=implementer model=haiku
outcome: T10 model=haiku attempts=1 result=pass review=none run=2026-07-31-63c6
agent: T11 id=afc2997410ebe4d15 role=implementer model=sonnet
outcome: T11 model=sonnet attempts=1 result=pass review=none run=2026-07-31-63c6
agent: T12 id=a027a00f6fdcc23da role=implementer model=haiku
outcome: T12 model=haiku attempts=1 result=pass review=none run=2026-07-31-63c6
agent: T9 id=a1a553e2191d8d2e5 role=implementer model=sonnet
agent: T9 id=a8c9e759960be9e1d role=verifier model=sonnet findings=2 confirmed=2 result=accepted
agent: T9 id=ae3bb7c7116f11c2d role=implementer model=sonnet
outcome: T9 model=sonnet attempts=2 result=retry-pass review=revised run=2026-07-31-63c6
reviewer: P4 model=opus findings=9 confirmed=9 result=accepted
agent: T12R id=a6994f25405f3d561 role=implementer model=opus
agent: T12R id=a989757818e2d1eb6 role=verifier model=sonnet findings=1 confirmed=1 result=accepted
outcome: T12R model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T13 id=ac982418b05a10f07 role=implementer model=sonnet
outcome: T13 model=sonnet attempts=1 result=pass review=none run=2026-07-31-63c6
agent: T14 id=a00b7a57f47df8365 role=implementer model=sonnet
outcome: T14 model=sonnet attempts=1 result=pass review=none run=2026-07-31-63c6
agent: T15 id=a7949565e670e9946 role=implementer model=sonnet
outcome: T15 model=sonnet attempts=1 result=pass review=none run=2026-07-31-63c6
agent: T16 id=a293b9f5dad3fa0bf role=implementer model=sonnet
outcome: T16 model=sonnet attempts=1 result=pass review=none run=2026-07-31-63c6
agent: T17 id=ad62b071377b21b69 role=implementer model=opus
outcome: T17 model=opus attempts=1 result=pass review=none run=2026-07-31-63c6
reviewer: P5 model=opus findings=9 confirmed=9 result=accepted
agent: T17R id=a96e99d2bf0e1eed6 role=implementer model=opus
agent: T17R id=aab7ebc1857af639f role=verifier model=sonnet findings=1 confirmed=1 result=accepted
outcome: T17R model=opus attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T18 id=ad19f196ccc394460 role=implementer model=sonnet
agent: T18 id=aee41aa50575282f5 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T18 model=sonnet attempts=1 result=pass review=clean run=2026-07-31-63c6
agent: T19 id=a6b52d95693e6af6f role=implementer model=sonnet
outcome: T19 model=sonnet attempts=1 result=pass review=none run=2026-07-31-63c6
session: abf847f3-aa57-4b8d-a3b9-394a063e8762
