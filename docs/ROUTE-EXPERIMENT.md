# The route experiment — which Copilot route is best?

`bin/route_experiment.py` · definition: `experiments/route-arms/` · store: `routeruns/`

## The question

Is it better to split a task across models, with a planner, a cheap max-effort worker and a
frontier reviewer, or to hand the whole task to one frontier model? This experiment answers that
for **whole routes, not single models**. It measures cost in AIC, correctness, code quality, test
strength, complexity and discipline, and then applies a decision rule that was fixed before any
live trial ran.

## Arms

The arms are defined in `experiments/route-arms/experiment.json` (models, efforts). Model ids
are validated against `data/pricing.copilot.json`.

| Arm | Shape | Planner | Test-author / implementer / verifier | Reviewer |
|---|---|---|---|---|
| A1 | pipeline | Opus 5.5 (high) | Luna 6 (max) | Opus 5.5 (high) |
| A2 | pipeline | Sol 6 (high) | Luna 6 (max) | Opus 5.5 (high) |
| A3 | one-shot | Sol 6 (high), one dispatch | — | — |
| A4 | one-shot | Opus 5.5 (high), one dispatch | — | — |

**Pipeline flow:**

```
planner (read-only) → test-author → implementer → verifier (read-only)
  └ verifier FAIL  → 1 rework + re-verify
→ reviewer (read-only)
  └ reviewer REJECT → 1 rework + re-verify (no second review)
```

**Post-hoc extension arms** sit in `experiments/route-arms/extensions/`, one file per arm with a
stated reason. They stay outside `experiment.json`, so the preregistered digest never moves.

| Arm | Shape | Model | Added |
|---|---|---|---|
| A5 | one-shot | Luna 6 (max), one dispatch | after the A1–A4 run, on request |

A run takes an extension arm only on `run --extend-arms A5`. That records the arm, its file
digest, when it was added and how many trials preceded it in `run.json`. Resuming under a
changed or missing extension file is refused.

An extension arm is **never judged**. Re-judging a group with an extra candidate would
overwrite the judgments the preregistered decision rests on. The report therefore keeps the
preregistered view (A1–A4, with judge quality) as the decision. It then adds a **post-hoc
view** over every arm. In that view, judge quality is left out for every arm whenever it covers
only some of them, and the remaining weights renormalise. That way no arm is ranked on a
component another arm was never scored on.

A pipeline trial makes at most 9 dispatches; a one-shot trial makes exactly 1. Each stage sees
the previous stages' output, and verdicts are parsed from a fixed `VERDICT=` line.

## Tasks

There are three small, rollback-safe tasks in this repo. Each has a hidden oracle and a
reference patch.

| Task | Kind | Oracle on base → reference | Regression modules |
|---|---|---|---|
| T1-statusline-rollover | bug fix (`fmt_tokens` K→M rollover) | 6/10 → 10/10 | test_statusline |
| T2-est-multi-model | small feature (`est` takes a model list) | 7/13 → 13/13 | test_copilot_pricing, _usage, _statusline, test_journal_advisor |
| T3-redact-single-walk | behaviour-preserving refactor | 7/9 → 9/9 | test_privacy_primitives, test_journal_collect, test_context_weight, test_training_data |

`python3 bin/route_experiment.py validate` re-proves the table on demand. It checks that the
oracle is red on base and green on the reference patch, and that regression is green on both.

**Rollback.** Every trial runs in a history-free extraction of the pinned `base_commit`,
created by `repo_bench.make_sandbox`. The trial never touches the working tree; to roll back,
discard the sandbox.

**Hidden oracle.** The oracle is never placed in the candidate's tree. It is copied into a
separate grading sandbox afterwards.

## What is measured, per trial

| Family | Metric | Source |
|---|---|---|
| Cost | AIC per dispatch/role/trial, tokens by kind (input, cache read/write, output, reasoning), premium requests, wall time, dispatch count, reworks | each session's own `session.shutdown` `modelMetrics`, priced from the pricing file; Copilot's reported AIU is shown beside it as a cross-check and never summed with it |
| Correctness | oracle pass share; solved = oracle 100% **and** regression green | hidden oracle + regression modules |
| Test strength | mutation score: share of oracle-killable AST mutants (in the touched functions) that the candidate's own tests kill | `mutants()`, run with `python -B` so stale bytecode can't mask a mutant |
| Complexity | ΔSLOC, ΔMcCabe CC, Δcognitive (approx.), max nesting, Halstead volume, maintainability index, max touched-function CC/length, diff and test lines, compared against the reference patch | stdlib `ast` |
| Discipline | out-of-scope files, task guardrails (`subprocess`, hardcoded ids…), read-only stage wrote, new unused imports, TODOs, parse errors, patch doesn't apply | diff + fence records |
| Quality | two blind judges from different vendors (GPT-6 Astra, Claude Fable 5.1). Each scores all four arms' diffs for one task×repeat side by side, under shuffled labels, 1–10 on correctness/readability/design/tests/scope/overall | `judge` stage, shell denied |
| Gate accuracy (pipelines) | whether each verifier/reviewer verdict was correct, judged on the patch that gate actually saw; incorrect acceptances/rejections | oracle re-run per verdict |

## The composite and the decision rule

Everything below is data under `scoring` in `experiment.json`. `run` pins that file's digest
and refuses to resume under a changed definition.

**Quality Score (QS, 0–100) per trial:**

```
QS = 100 × gate × Σ wᵢ·cᵢ / Σ wᵢ          (over the components that exist)
     correctness .40 · judge quality .25 · test strength .15 · simplicity .10 · discipline .10
gate        = 1, or 0.5 if regression is red
simplicity  = 1 − ½·excess LOC/max(10, ref LOC) − ½·excess ΔCC/max(3, |ref ΔCC|)   (clamped 0..1)
discipline  = 1 − 0.25 × violations
```

**Decision:**

1. **Eligible** arms have a solve rate of at least 2/3.
2. The **leader** is the eligible arm with the highest mean QS.
3. Another arm is **tied** with the leader if the paired (task, repeat) QS gap is 5 points or
   less, or if its 95% paired bootstrap CI contains 0.
4. The **winner** is the cheapest tied arm by mean AIC per trial.

The report also shows:

- A cost/quality Pareto front.
- QS per AIC.
- AIC per solve.
- Wilson CIs on solve rates.
- A task-stratified bootstrap CI on each arm's mean QS.
- Judge agreement: Spearman correlation and mean absolute gap.

## Design controls

- **Paired and counterbalanced.** There are 3 tasks × 4 arms × 3 repeats = 36 trials. Arm
  order rotates per task and repeat, and every arm solves every task from the same base.
- **Hermetic dispatch.** Each dispatch sets its own `--session-id`, so cost attribution is
  exact. The following are excluded:
  - subagent and skill delegation (the arm's model mix is exactly what it claims);
  - `session_store_sql` (this repo's own sessions wrote the oracles);
  - memory writes;
  - web tools.

  Read-only stages deny the write tool, and judges also deny the shell. After each dispatch,
  the session log is scanned read-only for experiment paths and nested CLI launches. A hit marks
  the trial `contaminated` and excludes it.

  A nested launch means a shell command that RUNS `copilot -p` or a polytropos dispatcher.
  Naming one as data, such as a file passed to `grep`, does not count. `rescan --run ID`
  re-applies the current classifier to the saved logs offline and records an audit entry for
  each verdict it changes.
- **Money.** `run` and `judge` spend only behind both `--live` and an explicit `--max-aic`. The
  ceiling is re-checked before every dispatch against measured spend plus an estimate of the
  next dispatch. If a session log can't be read, that dispatch is charged its estimate and
  labelled unmeasured, never charged as zero. The ceiling stops the next dispatch; it is not a
  provider-side guarantee.
- **Crash safety.** Every dispatch goes through `attempt_ledger`. Re-running `run --run-id ID`
  resumes: it skips completed, timed-out and contaminated trials and never replays a dispatch.
  A trial that failed to dispatch is re-run on resume. Its failed attempts stay in the record
  as `prior_attempts` and still count against the ceiling. The report lists them separately,
  outside every arm's per-trial AIC, because an outage is not a property of the route. Three
  dispatch-failed trials in a row stop the run with exit code 5.

## Threats to validity

- **Small n.** There are 9 trials per arm. Expect wide CIs; a "tie" is the honest outcome
  when the data can't separate arms, and the rule then prefers the cheaper route.
- **Three small Python tasks** don't represent large or multi-file work. The result is
  scoped to tasks of this size.
- **Judge bias.** Judges are cross-vendor and blind, but they can still infer style. Judge
  quality is 25% of QS, and the report shows the other components separately.
- **Cognitive complexity is an approximation** of SonarSource's definition, implemented with
  stdlib `ast`. It is comparable across arms, but not with external tools.
- **Regression scope.** macOS `sandbox-exec` cannot nest, so modules that drive the kit
  drivers can't run inside the enforced verify boundary. Each task therefore runs a curated,
  task-relevant regression list. `grade --full-regression` (trusted-host only) re-grades
  offline against the full suite.
- **Extension arms are post hoc.** They run after the preregistered trials, on a different
  day, so model or service drift between the two sessions is uncontrolled. They also lack judge
  quality. Treat their post-hoc ranking as directional evidence, not a preregistered result.
- **Pre-dispatch estimates** use `task_profiles` token counts and exclude cache writes. Only
  measured AIC goes into the result. The CLI flags for tool exclusion/denial are verified at
  the first live dispatch.

## Version 2 (`experiments/route-arms-v2/`)

Version 2 fixes v1's weaknesses: small n, easy tasks, effort confounds and estimate-charged
outage spend. The v1 definition, its digest and its report are unchanged.

- **Harder tasks, sized for power.** Six new tasks (T4–T9) cover features, a refactor, a
  multi-defect bugfix and an algorithmic change. Each has 25 or more oracle tests and a
  `naive.patch`, a plausible but incomplete fix that `validate` requires to score strictly
  between 0 and 1. Three repeats give 18 paired attempts per arm. From v1's paired-gap spread,
  that is enough to detect a gap of about 2–3 QS at 80% power. `equivalence_margin` is 3 to
  match.
- **Two more route shapes.** `reviewed` is a one-shot followed by a reviewer gate; each reject
  buys one solo rework and a re-review. A `pipeline` may leave out its reviewer. These shapes
  test whether a cheap implementer plus an expensive gate beats either alone.
- **Effort-matched arms.** v1 ran Luna at `max` and Sol and Opus at `high`. A8 and A9 are Sol
  and Opus one-shots at `max`.
- **Time tie-break.** Among tied arms whose mean AIC is within `cost_tie_pct` % of the
  cheapest, the arm with the lowest median wall time wins.
- **Outage honesty.** The report shows each arm's AIC median and p90, wall-time median and
  p90, models/effort, and the share of its AIC charged at estimate. An arm above
  `max_estimate_share` is flagged. `rescan` re-measures an estimate-charged dispatch when its
  session log now carries usage, and records an audit entry under `remeasures`.
- **Sensitivity.** The report states the smallest QS gap the run could detect, and how many
  paired attempts a 2-, 3- or 5-point gap would need.

- **Rubric-and-rank judges.** With `scoring.quality_mode` `rubric_rank`, each judge fills the
  task's rubric checklist for every blinded candidate and ranks them all. Judge quality is half
  the checklist share and half the normalised rank. Agreement is measured with Kendall's W
  across judges. If the mean W falls below `judge_min_agreement`, judge quality is dropped for
  every arm and the report says so.
- **Judge consistency.** `judging.consistency_fraction` re-judges a deterministic sample of
  groups under a fresh label shuffle. The report gives the retest rank correlation and how
  often the top pick held. Retests never enter QS.
- **Stronger mutants.** `scoring.mutation_operators` `v2` adds boolean flips, string
  blanking, min/max and any/all swaps, augmented-assignment operator swaps, negated
  `if`/`while` tests and dropped unary minus to v1's operators.
- **Fairer simplicity.** `scoring.simplicity_basis` `median` measures size against the median
  of the reference and every solved candidate, not the reference alone. A task's
  `allowed_generated` paths count as in scope but never as size.
- **Gate probe.** `probe` shows every distinct verifier and reviewer stage a known-bad
  (`naive.patch`) and a known-good (reference) patch in a fresh sandbox, never the oracle. It
  reports each gate's sensitivity and specificity. The probe is a separate spend and never
  enters QS. `plan` prints its estimate when the definition has a `probe` block.

The new report sections render only when `scoring.extended_report` is true or the run holds
ranked judges or probes, so v1 reports stay byte-identical.

## How to run

```bash
python3 bin/route_experiment.py validate            # oracles red→green; offline
python3 bin/route_experiment.py plan                # matrix + AIC estimate; spends nothing
python3 bin/route_experiment.py run --dry-run       # every first-dispatch argv; spawns nothing
python3 bin/route_experiment.py demo                # whole pipeline on a stub CLI; offline

python3 bin/route_experiment.py run --live --max-aic 4000          # SPENDS: 36 trials
python3 bin/route_experiment.py judge --run ID --live --max-aic N  # SPENDS: 18 judge dispatches
python3 bin/route_experiment.py probe --run ID --dry-run           # gate-probe matrix + estimate; spawns nothing
python3 bin/route_experiment.py probe --run ID --live --max-aic N  # SPENDS: gate sensitivity/specificity
python3 bin/route_experiment.py rescan --run ID                    # re-classify contamination; offline
python3 bin/route_experiment.py run --run-id ID --extend-arms A5 --live --max-aic N  # SPENDS: post-hoc arm
python3 bin/route_experiment.py report --run ID [--json]           # scorecard + decision
```

The cost estimate comes from `plan`, which is computed from `data/pricing.copilot.json`. A
snapshot at `cached_date` 2026-09-24: about 1,020–1,070 AIC for trials plus about 540 AIC for
judges, against the preregistered 4,000 ceiling. Rerun `plan` for current figures.
