# Size the ceiling against calibration, not against the raw estimate

Detail moved out of `skills/repo-bench/SKILL.md` by roadmap step 22 so the entry point carries the spend law and the relay requirements; the text below is unchanged.

`task_profiles` prices a GENERIC dispatch — it has no idea whether the candidate is about to
run a real agentic session against a large, unfamiliar codebase. The kit's first live run (a
10-task matrix against a large TypeScript codebase, `.claude/kits/repo-bench/NOTES.md`) planned
at $17.22 and would have cost $100-200 at its measured rate: on `size=S` cells, haiku ran 8.7x
over its estimate, sonnet 10.6x, opus 11.9x — three cells, one run. The ceiling caught it
exactly as designed (it stopped around cell 12 of 30), but a user reading only the plan total
has no way to know the number is off by an order of magnitude.

`plan` therefore prints a `## calibration` section, sourced from a `--store-dir`'s own
recorded `usd_basis: "actual"` cells (pass the same store your `run`s write to — omit it and
`plan` reports the honest "no calibration data" line rather than silently guessing; unlike
`run`/`list`/`verdict`/`apply`, `plan` never falls back to the default `benchruns/` store on
its own). It reports a MEDIAN ratio with its sample size, broken down by size profile and by
model wherever there is enough data to break it down — a ratio measured on three `size=S`
cells is never presented as if it applies to `size=L`, and a thin sample is shown as thin, not
padded into false confidence. **The matrix and total above the calibration section are NEVER
adjusted by it** — `task_profiles` estimates stay exactly what they say; the calibration line
stands beside them so a ceiling can be sized against measured reality instead of a number that
has measured ~10x low on real agentic work. When relaying a plan to a user, quote the
calibration line (or its absence) exactly as printed, the same rule as every other honesty
label in this skill.
