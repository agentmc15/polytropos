# `regrade` — the same law, for a judge column a ceiling stranded

Detail moved out of `skills/repo-bench/SKILL.md` by roadmap step 22 so the entry point carries the spend law and the relay requirements; the text below is unchanged.

Judge grading is a POST-LOOP pass, so budget is consumed candidate-first: a run that crosses its
ceiling during grading has already dispatched (and paid for) every candidate cell and simply
stops buying judge grades. The envelope records those as `skipped: cost-ceiling` and stays
labelled `partial (cost-ceiling)`. **That is the signal to reach for `regrade`** — a verdict
whose judge column is mostly `n/a (skipped: cost-ceiling)` is a run missing one of its four
oracles, not a run that measured nothing there.

`regrade --run <id>` re-dispatches ONLY those stranded grades. It **spends**, so it carries
exactly the same law as `run`: never add `--live` yourself, always show the user what it will
cost first (the command prints the pending count, the per-grade estimate and the total before it
dispatches anything), and only construct the `--live --max-usd <ceiling>` form after the user has
confirmed a ceiling in THIS conversation. The ceiling is a **fresh** budget for this invocation
starting at $0.00 — never a continuation of the stopped run's arithmetic — and it is re-checked
before every single grade, so a regrade that runs out stops cleanly, says so, and stays resumable
by another one.

What it deliberately does NOT do: re-dispatch candidate cells (their work is done, and a cell the
ceiling cut is not finishable — `regrade` names those rather than pretending), touch a grade that
completed, or re-dispatch an `empty-reference` skip (that is a design refusal, not a budget
casualty — its reference strips to nothing, so one blind slot would render empty and deanonymise
the pair). Every judge discipline is unchanged: slots re-randomized per grade, the reference
stripped of its test hunks, `judge == candidate` refused, unparseable output recorded as such.

Two things to relay honestly afterwards. **Spend is reported per invocation**, one line each with
its own basis, and there is deliberately no combined total — a run priced `actual` plus a regrade
priced `estimated` has no single basis, and every dollar this tool prints must carry one. And a
**verdict rendered before the regrade is stamped `STALE VERDICT`** and `apply` refuses it: judge
grades break capability ties, so re-run `verdict --run <id>` before quoting or applying anything.
The `partial (cost-ceiling)` label comes off only when no cost-ceiling skip remains anywhere,
cells included — a run whose CELLS were also cut stays partial no matter how many grades a
regrade finishes.
