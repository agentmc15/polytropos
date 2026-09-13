# The four oracles, the constructed substrate behind `solved`, and the full-patch diagnostic

Detail moved out of `skills/repo-bench/SKILL.md` by roadmap step 22 so the entry point carries the spend law and the relay requirements; the text below is unchanged.

## The four oracles, and the one word that means anything

Every task × candidate cell is graded on four independent, independently-labelled axes. They
are never blended into one score:

1. **Tests (objective).** The repo's test command runs against a substrate the engine
   CONSTRUCTS (see the next section) — never against the candidate's own tree, and never in
   the sandbox the candidate worked in. `solved` means this oracle passed. **`solved` means
   tests passed and nothing else, ever.** A judge grade or a structural-similarity score can
   never earn a `solved` label, no matter how convincing. When this oracle isn't available for
   a task (no test coverage in the fix, general mode with no red-validated coverage, or a
   candidate patch that would not apply) the cell renders `n/a` — never a zero, never a
   silently dropped row, and never a `False` the engine did not measure.
2. **Structural similarity.** Files-touched overlap, hunk overlap, and a LOC-delta ratio
   against the reference patch. Reported as **similarity — NOT a correctness verdict**: a
   candidate can score high on similarity while being wrong, or low while being right by a
   different route. Never present a similarity number as if it answered "did the candidate
   solve it." This oracle usually has numbers, but it is **not** unconditionally available:
   when the reference patch parses to nothing to compare against (a tests-only fix commit, a
   binary-only change, a diff the tool could not parse) the engine marks it unavailable and
   the cell renders `n/a`. Read that `n/a` as "there was no reference to be similar to," not
   as a zero and not as a low score.
3. **LLM judge (subjective, priced).** The judge model is the strongest tier in
   `data/pricing.json` that is NOT itself a candidate in the run — a judge that is also a
   candidate is a hard refusal. The judge sees the reference and candidate patches as blind,
   randomized `Patch A` / `Patch B` slots so its grade can't just follow "which one do I
   recognize." An unparseable judge response degrades to a labelled `n/a (unparseable)`, never
   a guessed score.
4. **Cost & latency.** Wall-clock per dispatch and dollars priced from token counts via
   `data/pricing.json` — this axis, not raw capability, is what separates a "daily driver"
   pick from a "strong tier" pick. A cell that was never dispatched, or one whose usage could
   not be priced, renders `n/a` here too rather than `$0.0000`.

A task's reference patch (and its sizing) has the fix commit's own test hunks stripped before
similarity scoring and judging — otherwise a correct candidate is compared against changes it
was structurally never allowed to make, which would depress its similarity score and hand the
judge a tell.


## What the tests oracle actually grades — and the false negative that buys

`solved` is the only word in this tool that means correctness, so the tree it is measured on is
not one the candidate can rig. The engine does not grade the candidate's tree at all — not even
a cleaned-up copy of it. It **constructs** a fresh substrate from three pieces, and that
construction is the whole guarantee:

> the grade result is a function of **(the task's base state, the candidate's IN-SCOPE patch,
> the reference test blobs)** and nothing else.

- **the task's base state** — a history-free extraction of the base commit through the
  read-only git path, plus the mined mutation in general mode;
- **the candidate's in-scope hunks only** — the slice of its patch whose paths the *reference
  patch* touched. The reference patch is mined from the repo's own history and no candidate can
  write it, so it is what defines "in scope";
- **the withheld test blobs**, written last.

Nothing the candidate wrote outside that scope is present, because it was never applied. That
is why rewriting `run_tests.py`, planting a `conftest.py`, a `Makefile`, a `tox.ini`, a
`setup.py`, a root `sitecustomize.py` or a dotfile cannot buy a `solved` — and why no list of
such filenames appears anywhere in the engine. A name-based rule can never enumerate what a
`--test-cmd` will actually execute; a construction never has to.

**This has a real cost and you must relay it rather than smooth it over.** A candidate that
genuinely fixes the bug in a file the reference patch did not touch — a legitimate alternative
route — has that work left out of the substrate, and its cell reads `not solved`. That is a
**false negative**. It is deliberately visible: the out-of-scope paths are recorded on the cell,
listed in the measurement table's `out-of-scope (excluded)` column, and called out per candidate
in the verdict as possible false negatives. When you see them, say so — report the cell as
"out of scope, not necessarily wrong," and do not present that candidate's `solved` count as a
clean capability reading. The asymmetry is intentional: a visible false negative costs the user
one investigation, while an invisible false positive would silently re-route their real work.

One honest limit on the *reporting* side, which does not touch the guarantee: that recorded
path list is read from the candidate's captured patch, so a change git never recorded (a file
the candidate added to `.gitignore` first, a pure rename) can be missing from it. The substrate
excludes such a change either way — the list is evidence, not the fence. Never read a short
out-of-scope list as proof that a candidate stayed in scope.

### The full-patch diagnostic — how big is that false negative?

The first completed live run made the cost measurable for the first time: **9 of 14 cells** read
`not solved` *with* work reverted from outside the reference patch's scope, including plausible,
genuinely-fixing edits to a different source file. So the absolute `solved` rates understate
every candidate — and nothing in the output said by how much.

The **full-patch diagnostic** bounds it. On exactly the false-negative suspects — the tests
oracle was available, the in-scope grade read `not solved`, *and* the candidate made recorded
out-of-scope changes — the engine grades a **second** substrate: the same base state, the
candidate's **entire** patch (its test-file edits are still restored from base — that law does
not bend), the same reference test blobs. It runs `--test-cmd` once more per such cell. **No
model is dispatched**, so it spends no `--max-usd` dollars; it costs toolchain time.

**It is forgeable by construction, and that is not a flaw to be fixed — it is the price of the
question.** The diagnostic substrate contains whatever the candidate wrote outside scope,
including the file `--test-cmd` actually executes. A pass there can mean "a correct fix that
lived in another file" *or* "the harness was rewritten," and this substrate cannot tell them
apart. So it feeds **nothing**: not `solved`, not the capability order, not the evidence floor,
not the tier map, not the daily-driver pick, not `apply`.

**Read it as a bound, never as a score.** The verdict prints, per candidate:

> `false-negative bound: N of the M not-solved cells pass with the full patch applied — solved
> lies in [lower, upper] of objective_n; the upper bound is DIAGNOSTIC (forgeable), the lower
> bound is routing-grade`

The **interval is the honest answer**. Quoting the upper bound alone is quoting a forgeable
number; quoting the lower bound alone is quoting a number you now know is an undercount. Say
both. The measurement table's `full-patch DIAGNOSTIC` column shows `-` (not run), `still fails`,
`PASSES — possible false negative`, or `n/a`, and every passing diagnostic lists the
out-of-scope paths that were applied **verbatim** — so if the candidate rewrote `run_tests.py`,
you will see `run_tests.py` sitting right there. The tool deliberately does **not** classify
those paths as "harness-adjacent" or "innocent"; naming a class of dangerous filenames is
exactly the enumeration mistake this whole grading design exists to avoid. Look at the list
yourself and say what you see.

Two readings that would be wrong:

- **A degenerate interval is not proof of no false negatives.** When the diagnostic did not run
  — `--no-full-patch-check`, an envelope written before the feature existed, or no suspect cells
  — `upper == lower`, and the card says how many cells actually got a reading. Nobody looked is
  not the same as nothing there.
- **A passing diagnostic is not a `solved`.** It never becomes one, in any column, and a run
  whose every diagnostic passed still ranks, tiers, floors and picks exactly as it would with
  the feature switched off.

`--no-full-patch-check` (on `run`) disables it entirely and restores the pre-feature cost
profile. It is off-by-default-on — the diagnostic is the honest default, because an unbounded
false-negative rate is a worse number than a bounded one.
