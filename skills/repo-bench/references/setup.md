# Targets that must build or install first — `--setup-cmd` and `--setup-key`

Detail moved out of `skills/repo-bench/SKILL.md` by roadmap step 22 so the entry point carries the spend law and the relay requirements; the text below is unchanged.

Sandboxes are history-free tree extractions, so they contain the repo's source and nothing
else: no `node_modules`, no virtualenv, no compiled output. On a target whose tests cannot run
until something is installed or built, every grading would otherwise fail for a reason that has
nothing to do with any candidate's work. `--setup-cmd CMD` (accepted by both `plan` and `run`)
is that missing step: a command run inside a sandbox *before* `--test-cmd`, through the same
injectable runner seam `--test-cmd` uses. Reach for it on any target with an install or compile
step — a JS/TS repo needing a lockfile install, a Python repo needing an editable install, a
compiled project needing a build. Without such a step, don't pass it; there is no default and
the tool never invents one.

**It runs once per prepared template, not once per grading.** Running the install per grading
would mean roughly one install per task × candidate — worse than the problem it solves. So the
engine builds a *template*: a sandbox made from the task's own base state, with `--setup-cmd`
run in it exactly once, and every grade substrate is then handed that template's captured
artifacts. The construction the `solved` guarantee rests on is unchanged, just restated with the
template in it:

> the grade substrate is **(the task's base state + the setup artifacts) + the candidate's
> IN-SCOPE patch + the reference test blobs** — and nothing else.

**No candidate tree, patch, or path is ever an input to preparing a template** — that is the
guarantee, and it is the one to relay. (It is deliberately *not* phrased as "the template is
built first": templates are prepared lazily, inside grading, which happens after the first
candidate of that task has already been dispatched. A timing claim would be false; the data-flow
claim is true and is what the construction rests on.) Setup never runs inside a candidate's
sandbox — which has a consequence worth stating when you present results: a candidate on such a
target **cannot run the tests itself** while it works, so it is being measured on a repair it
could not verify locally. That is a real handicap the measurement carries, not a bug, and it
belongs beside the numbers.

The captured artifacts are held **outside the run directory**, in a private temporary directory
deleted when the run ends, and each one is content-hashed when captured and re-verified before
every single overlay; a store whose bytes changed renders the tests oracle `n/a` with a note and
labels the run, never a failure. (Only the *setup command itself* runs under the run's working
area — the inert captured bytes do not, because a candidate's own sandbox is under the run
directory too, and a shared store kept there would be reachable from it for the whole run.) Two
independent mechanisms, because a store that a candidate could rewrite is a `solved` a candidate
can forge without touching its own sandbox at all.

`--setup-key PATH` (repeatable) controls how templates are shared. By default each distinct base
commit gets its own template, which on an issue-replay run means one install per task. Point it
at the file that actually determines the dependency set — `--setup-key package-lock.json`,
`--setup-key requirements.txt` — and tasks whose keyed content is identical share ONE template
even though their base commits differ, which is usually the difference between one install and
ten. **Read the template accounting the run prints and the envelope records** (`N template(s)
prepared, reused across M grading(s)`): a cache that silently misses looks exactly like no cache,
and that line is how you tell them apart. General (mutation-repair) mode is the exception —
tasks there share a base commit but each carries a different injected bug, so they never share a
template regardless of `--setup-key`; that costs one preparation per task and is deliberate.

**`--setup-key` is sound for an install and unsound for a build, and the engine now decides that
itself rather than trusting you to.** A dependency install is a function of the manifest you
keyed on; a compile is a function of the *source*, which differs between two tasks' base commits
by construction — so sharing one template across them would grade task B against task A's
compiled output. Before any artifact crosses a base commit the engine refuses outright if the
setup step rewrote a path that exists at either base (build output, not an install artifact),
and otherwise prepares the template once more at the second base and compares the artifacts
byte for byte: identical means the key is reused for the rest of the run (one extra preparation
in total), different means sharing is refused for the rest of the run and every task gets its
own. Both outcomes are recorded in the envelope's `setup.sharing_notes` — read them, and report a
refusal as what it is: the run cost more installs *because* keyed sharing would not have been
sound. Verification is evidence that this setup output was reproducible across two base commits,
not a proof that it always is. A `--setup-key` path that does not exist at a task's base commit
keys nothing, so that task falls back to its base commit and the run is labelled — check the
spelling when you see that label.

Three honesty rules ride with this and must not be smoothed over when you relay results:

- **A setup failure makes the tests oracle UNAVAILABLE, never failed.** If `--setup-cmd` exits
  non-zero, every grading depending on that template records `available: false` with a note
  naming the exit code, and `passed` stays `null` — the cell renders `n/a`, the run is labelled
  `partial (setup failed)`, and no candidate is marked wrong. A broken toolchain reading as "the
  model didn't solve it" would produce a confident, entirely fictional verdict. If you see that
  label, say the toolchain failed; never report those cells as failures.
- **Setup time is not model latency.** Template preparation is recorded as its own per-run
  `setup_seconds` and never enters any cell's `wall_seconds`. Oracle (d) is what the daily-driver
  pick reads, so folding a target's build time into it would blame whichever model happened to be
  graded first for the toolchain's slowness.
- **Artifacts that failed verification are absence too.** If the envelope carries
  `partial (setup artifacts failed verification)` or a non-empty `setup.artifacts_tampered`, the
  affected cells render `n/a` and `passed` stays `null` — say the artifacts could not be trusted,
  and never present those cells as failures or fold them into a candidate's `solved` count.

`--setup-cmd` carries exactly the same exposure as `--test-cmd` and the same fence: **it runs
arbitrary commands, so only benchmark repos whose build you would run by hand.** It is opt-in,
never inferred, never run by `plan` (which spends and runs nothing), never run without
`--test-cmd` (there would be no tests oracle to make runnable), and the command itself executes
only inside the run's own working area, which is swept with the rest of it unless `--keep-work`
(its captured artifacts live outside the run dir, as above, and are deleted either way).
