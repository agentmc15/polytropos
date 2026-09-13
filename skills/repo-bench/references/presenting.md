# Presenting the results

Detail moved out of `skills/repo-bench/SKILL.md` by roadmap step 22 so the entry point carries the spend law and the relay requirements; the text below is unchanged.

1. **Never present a plan's dollar total, or any `estimated`/`mixed`-basis figure, as a bill.**
   Every dollar in this tool's output carries a basis — `spend basis: actual` (priced from
   harness-reported token counts), `spend basis: estimated` (no usable usage was extractable,
   so the number comes from the plan's own per-task estimate), or `spend basis: mixed` (some
   cells actual, some estimated) — and that basis must travel with the number whenever you
   relay it. Usage extraction itself is a best-effort, never-live-verified assumption about the
   dispatch harness's JSON output shape; when it fails to parse a real dispatch's usage, the
   number silently degrades to the estimated basis rather than producing a wrong number — so
   `spend basis: estimated` on a `run` output can mean either "no usage was ever recorded" or
   "a parse attempt happened and came up empty," and either way the number is a plan-derived
   estimate, not a measurement of what was actually spent.
2. **Quote the honesty labels verbatim, don't paraphrase them away.** `similarity … NOT a
   correctness verdict`, `BELOW EVIDENCE FLOOR`, `partial (cost-ceiling)`, `DISAGREEMENT —
   signal, not error`, and `n/a (unparseable)` all mean something specific and precise; a
   friendlier rewrite loses the precision the labels exist to protect.
3. **State per-verdict oracle coverage.** Say how many cells were objectively scored (tests
   available) out of how many total; call out any candidate whose `solved` cells came
   alongside test-file edits of its own — that isn't proof of gaming, but it must stay visible
   rather than folded silently into a clean-looking number — and call out any `not solved`
   cell that carries reverted out-of-scope paths, which may be a false negative rather than a
   failure (see the tests-oracle section above).
   **Always relay the false-negative bound as an interval** — `solved lies in [lower, upper]` —
   with the lower bound labelled routing-grade and the upper bound labelled diagnostic and
   forgeable. Quoting either end alone misrepresents the run: the lower end alone is a number
   you know understates the candidate, and the upper end alone is a number a rewritten test
   harness could have produced. If a diagnostic passed, name the applied out-of-scope paths it
   listed and let the reader judge them; do not summarise them as "harmless" or "suspicious".
4. **Test-path detection is a naive substring match**, not a glob or path-segment match — a
   file whose path merely *contains* one of the test markers (for example something like
   `latest/foo.py` or `contest_data.py`) can be incidentally treated as a test file, which
   means it gets stripped out of what the candidate is graded against and its content withheld
   from the candidate's sandbox. This is a real, known limitation of the current tool, not a
   hypothetical: if a repo's own layout uses path segments or filenames that happen to contain
   a test marker as a substring, its measurement can be subtly off in ways that won't show up
   as an error. There is no dedicated CLI flag for this today — flag it as a caveat on the
   verdict for any repo whose layout looks like it could trip this, and say so plainly rather
   than presenting the affected cells' coverage as clean.
