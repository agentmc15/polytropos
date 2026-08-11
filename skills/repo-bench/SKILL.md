---
name: repo-bench
description: Benchmark candidate Claude models on a chosen repo's own real work — mines issue-fix pairs or generates red-validated mutation-repair tasks, dispatches candidates in leak-proof sandboxes, grades with four independent oracles, and renders a re-tiered strong/mid/weak map plus a daily-driver pick. Use when the user asks to "benchmark models on my repo", "which model should implement/review in this repo", "re-tier / re-classify models for this project", "find a daily driver model", or "measure model X on our codebase". The default invocation is ALWAYS a priced plan that spends nothing — never a live spend — until the user explicitly confirms a cost ceiling.
allowed-tools: Bash, Read
---

# Repo bench

Run the engine that ships with this plugin. Use the `${CLAUDE_PLUGIN_ROOT}` env var Claude Code
sets for plugin-executed content; if it is unset, fall back to resolving
`../../bin/repo_bench.py` relative to this SKILL.md to an absolute path before shelling out.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_bench.py" plan --repo <path> --models <ids-or-tiers>
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_bench.py" run --repo <path> --models <ids-or-tiers> --live --max-usd <ceiling>
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_bench.py" verdict --run <run-id>
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_bench.py" apply --run <run-id>
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_bench.py" list
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_bench.py" demo
```

## Plan-first law — the one rule that overrides every other instinct

`plan` mines the repo, resolves candidates, and prints the exact models × tasks matrix priced
from `data/pricing.json` at run time (candidate dispatches AND judge grades, one total) — then
stops. It spends nothing. `run` without BOTH `--live` and `--max-usd` refuses structurally,
prints the same plan, and exits non-zero.

**NEVER add `--live` yourself.** When this skill is invoked, always run `plan` first, present
the plan and its total to the user exactly as printed, and only construct a `run --live
--max-usd <ceiling>` command after the user has explicitly confirmed a ceiling in THIS
conversation. A ceiling from a previous session, a guess at "what seems reasonable," or the
user simply asking a benchmarking question does not count as that confirmation. During a live
run the ceiling is re-checked before every single dispatch — candidate or judge — so a run that
hits it stops cleanly mid-matrix rather than overspending; the remaining cells are marked
skipped and the results are labelled `partial (cost-ceiling)`, never silently completed.

### Size the ceiling against calibration, not against the raw estimate

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

## The two acquisition modes

- **Issue-replay** engages when the target's `git log` yields enough fix commits that
  reference an issue (`fixes/closes/resolves #N`, or a squash-merge `(#N)` subject) to clear
  the evidence floor below. Each pair becomes a task: the commit before the fix is the base,
  the fix diff is the reference patch (never shown to the candidate), and the problem
  statement is the issue title/body when available, else the commit message — labelled
  `statement from commit message (weaker than issue text)` when it falls back.
- **General (mutation-repair)** is the fallback: a deterministic textual mutation (comparison
  flip, boolean negation, off-by-one, and/or swap) is applied to the repo and validated RED —
  the caller's `--test-cmd` must actually fail with the mutation in place, at zero model cost —
  before the task is admitted. The candidate is told the tests fail and must find and fix it;
  the reverse-mutation diff is the reference patch. This mode requires `--test-cmd`.

`--mode auto` (the default) prefers issue-replay and falls back honestly to general; the plan
card states which mode was chosen and why, including how many mined pairs actually carry a
usable tests oracle — an issue-replay pair can mine cleanly and still have no test coverage to
score it, so "enough pairs" and "enough *scorable* pairs" are not the same claim. `--mode` can
force either mode explicitly.

### `--with-gh` — real issue text instead of the commit message

Issue-replay's default statement is the fix commit's own subject+body, labelled
`statement from commit message (weaker than issue text)`. That label matters most on repos
that squash-merge PR descriptions into the merge commit: a PR description usually describes
the CURE, not the bug (it can even name a private helper the fix itself introduces), while the
issue body describes the actual bug the candidate needs to find. `--with-gh` (opt-in, accepted
by both `plan` and `run`) calls `gh api repos/<owner>/<name>/issues/<N>` once per
issue-referencing task and, when it succeeds AND the number is a genuine issue, uses the real
issue text — `statement_source` becomes `issue` and the weaker-statement label drops.

**GitHub shares ONE number namespace between issues and pull requests, and a squash-merge
`(#N)` subject is usually a PR number, not an issue number.** `gh issue view` cannot tell the
two apart — it resolves a PR number happily and returns the PR's own description, which is a
WORSE leak than the commit message: a PR description explains the fix in detail (it can name
symbols the fix introduces that the bug report never mentions), so blindly using it made
enrichment more confident and less trustworthy at the same time. `--with-gh` therefore never
calls `gh issue view`. It calls `gh api repos/<owner>/<name>/issues/<N>` — the same underlying
GitHub object as raw JSON — and inspects the payload for a `pull_request` key, which GitHub's
REST API sets if and only if the number is a pull request. **When that key is present, the PR
body (and its title) are never used**, full stop; mining falls back to the commit-message
statement with the existing weaker-statement label plus a note identifying the number as a
pull request. `statement_source: issue` therefore always means a genuine issue was used — it
is the field a reader relies on to weigh a verdict, so it must never overstate.

Requirements: `gh` installed and authenticated (`gh auth login`) locally — it is never invoked
by any test, `demo`, or this skill's own smokes, and one real network call is made per
issue-referencing task, so `--with-gh` is a `plan`-time decision, not something to add reflexively.
It does not help every repo: when a squash-merge subject's `(#N)` is a pull-request number with
no underlying issue at all, there is no issue text to fetch either way, and `--with-gh` cannot
invent one. Every real-world failure — `gh` missing from PATH, not authenticated, the number
resolving to a pull request, the issue not found/private/rate-limited, an unparseable response
— degrades to the same commit-message statement and label, plus a note naming what specifically
happened; a task's statement is never left empty or invented. The plan card surfaces the
outcome as `gh enrichment: N/M task(s) used real issue text`, and — because PRs are the
dominant reason enrichment falls short on squash-merge repos — adds `(K were pull requests)`
whenever any were, e.g. `gh enrichment: 3/10 task(s) used real issue text (7 were pull
requests)`. **Read this number before trusting a verdict on a repo benchmarked with
`--with-gh`**: a low ratio dominated by pull requests means most statements are still commit
messages, weaker evidence than the label alone might suggest.

**`--with-gh` REQUIRES `--gh-repo OWNER/NAME`.** `gh api repos/<owner>/<name>/issues/<N>` with
no explicit owner/name resolves `{owner}`/`{repo}` placeholders from the CURRENT WORKING
DIRECTORY, not from `--repo`/the target being benchmarked — the normal case is running this
tool from the plugin repo against a target elsewhere, so an unset `--gh-repo` makes every
lookup silently query the wrong project. That failure mode is uniquely dangerous here: it does
not error loudly, it degrades to the same commit-message fallback every other `gh` failure
uses, so a wrong-repo run reports something that reads exactly like a real measurement (e.g. a
confident `gh enrichment: 0/10`) while having measured nothing. So `--with-gh` without
`--gh-repo` REFUSES (exit 2) rather than degrading — the one place in this tool where a loud
refusal beats an honest-looking label, because the label would not actually be distinguishable
from a correct result. `--gh-repo` is never inferred from the target's `origin` remote:
`remote`/`config` are not in the read-only git allowlist this tool holds targets to, and
inference would be wrong for a fork anyway — a fork's issues live in the upstream repo, not at
the fork's own remote. Pass the repo you actually want `gh` to query, explicitly, every time.

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

## Targets that must build or install first — `--setup-cmd` and `--setup-key`

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

## The evidence floor

A candidate needs a structural minimum number of objectively-scored (tests-oracle-available)
tasks before its measurement is routing-grade — the same floor precedent as the passive ledger,
pinned higher because an active re-tiering decision changes routing for every future kit.
Below that floor, `verdict` still prints the raw measurement table, but the card, the envelope,
and `verdict.md` all carry **`BELOW EVIDENCE FLOOR`** stamped at the top — present it exactly
that way, never softened into something like "limited data" or "preliminary results." A
below-floor verdict is not a weaker verdict to be reported with hedges; it is explicitly
labelled as not a routing-grade verdict at all. `--min-tasks` can only RAISE the floor for a
given run, never lower it, and `apply` hard-refuses a below-floor verdict outright.

## The three legs — never average them

The repo already has two other legs of routing evidence: a PUBLISHED prior
(`bin/bench_routing.py` over the benchmark index) and OBSERVED outcomes
(`bin/routing_scorecard.py` over kits this repo has actually run). `repo_bench` is the third
leg: MEASURED-ON-DEMAND, on this specific repo's own work. `verdict` prints all three side by
side per candidate — published index (when the model appears in the benchmark data), observed
first-try rate (when the target repo's own kit ledger evidences it, `no ledger evidence`
otherwise), and this run's measured result.

**Lead with the measured verdict** when presenting results — it is the most specific evidence,
gathered on this repo, for this task shape. Show the published prior and the ledger beside it
for context. When the legs disagree — for example, this run's measured ranking inverts the
published index's order — the card prints **`DISAGREEMENT — signal, not error`**. Repeat that
framing verbatim when you relay it: a disagreement between legs is something to investigate and
mention, never something to average away or silently resolve toward whichever leg looks more
authoritative.

## Apply is a separate, explicit action

`run` measures; `verdict` renders; **`apply` is the only thing that ever changes routing, and
it is always its own explicit user action.** Never chain `run` straight into `apply`, and never
run `apply` on the user's behalf without them having seen the verdict first — `apply` prints
exactly what it is about to write (old tiers, new tiers, source run) as its own confirmation,
and there is no `--yes` flag because running the command IS the opt-in. `apply` also refuses:
when the named run has no verdict recorded yet, when the verdict is below the evidence floor,
or when any tier/daily-driver model id in the verdict is no longer present in the current
`data/pricing.json` (stale evidence — the benchmark must be re-run, not silently reapplied).

A successful `apply` writes a gitignored `prefs/repo-bench.json` with this schema:
`schema_version`, `applied_at`, `source_run`, `repo`, `tiers` (`strong`/`mid`/`weak`, each a
model id or `None`), `daily_driver` (a model id or `None`), and `labels` (carried over from the
verdict card — a below-floor verdict never reaches this file, so `labels` here never includes
the below-floor stamp). Consumption is pull-only: nothing in this plugin auto-reads this file
or auto-applies a routing change; a router that wants to use it has to go check for it.

## The tests-as-oracle exposure

Running a target repo's test suite executes arbitrary code from that repo. This kit treats that
as the same trust a user already extends when running their own tests — never more. It runs
ONLY inside a sandbox or scratch copy under the run's own working area, with its cwd there, and
only when the user explicitly supplied `--test-cmd`. `repo_bench` never invents a test command
and never runs one against this plugin repo itself. Only benchmark repos whose test suite you
would run by hand — no sandboxing theater is claimed beyond that; the honest statement of scope
IS the fence.

## What "read-only target, mutation only under the run" actually covers — and its two carve-outs

The target repo is read-only by construction: every touch to it goes through one allowlisted,
read-only git choke point, and candidate work happens in tree-extraction sandboxes with no
history the candidate could mine for the answer. That guarantee is real, but it applies to
`run`'s candidate sandboxes specifically — it has two carve-outs worth knowing before you tell
a user "nothing is written outside the run":

- **`plan` has no run directory at all.** Mining for `plan` happens through a system temp
  directory, not under any run's own working area, because a plan-only invocation never creates
  a run in the first place. That temp directory is still local and disposable, but it is not
  "under the run dir" — there is no run dir yet.
- **The judge's dispatch runs from a system temp directory on purpose.** This is a leak fix,
  not an oversight, and the reason is stronger than "stray clues": the run directory holds
  `tasks/<id>.json`, which carries the reference patch and the withheld test blobs — literally
  the answer to "which of these two slots is the reference." A judge whose cwd sat inside the
  run tree could read it out of its own ancestry and the blind `Patch A`/`Patch B` design
  would be decoration. Two things enforce it: the judge's cwd is outside the run dir entirely,
  and the run's task/dispatch records are not written to disk at all until every dispatch,
  candidate and judge alike, has already returned.

## Subcommands

- **`plan`** — `--repo`, `--models` (comma-separated ids or tier words, required), `--mode
  auto|issue-replay|general` (default `auto`), `--limit` (max tasks to mine), `--test-cmd`
  (required for general mode), `--setup-cmd` (build/install step run once per grade template —
  see above; never run by `plan` itself), `--setup-key` (repeatable path whose content keys those
  templates), `--judge` (override the default judge selection), `--commit`
  (base commit; defaults to the repo's current HEAD), `--exclude-subject` (repeatable regex,
  drop matching commit subjects from mining), `--with-gh` (opt-in `gh api` issue-vs-PR-aware
  statement enrichment — see above), `--gh-repo OWNER/NAME` (REQUIRED with `--with-gh`; refuses
  otherwise — see above), `--store-dir` (read-only source for the calibration line above —
  point it at the store your `run`s write to; omitted means the plan card's `## calibration`
  section reports no data rather than reading a default location), `--json`. Prices the whole
  matrix and stops — no `--live`, no spend, ever, on this subcommand.
- **`run`** — same mining flags as `plan` (including `--exclude-subject`, `--with-gh`,
  `--gh-repo`, `--setup-cmd` and `--setup-key`), plus
  `--store-dir` (where the run lands; defaults to a `benchruns/` store), `--live` and
  `--max-usd` (BOTH required to spend anything), `--claude-bin` (the dispatch binary — point it
  at a stub in any test context), `--keep-work` (keep the per-cell sandboxes instead of
  deleting them after grading, useful for inspecting a run by hand), `--no-full-patch-check`
  (switch off the full-patch diagnostic described above — it is on by default, dispatches no
  model, and costs one extra `--test-cmd` run per false-negative-suspect cell). Without
  `--live --max-usd` it prints the plan and refuses with a non-zero exit.
- **`verdict`** — `--run` (required), `--store-dir`, `--goal tiers|daily-driver|both` (default
  `both`), `--min-tasks` (raise the evidence floor for this render only), `--benchmarks`
  (override the published-index file for the D10 published leg), `--kits-dir` (override the
  observed-ledger source; defaults to the target repo's own `.claude/kits` when present),
  `--json`. Renders the tier map and/or daily-driver pick, the per-oracle measurement table,
  and the three-legs comparison — including the below-floor stamp when it applies.
- **`apply`** — `--run` (required), `--store-dir`, `--prefs-path` (override the default
  gitignored prefs location). Reads the named run's verdict, prints exactly what it will write,
  and writes it — or refuses per the rules above.
- **`list`** — `--store-dir`, `--prefs-path`, `--json`. Enumerates the store tolerantly: a
  missing store prints a friendly line, a rogue or malformed run directory gets a note instead
  of a crash, and no dollar figure is invented for a run with no recorded spend (shown as
  `n/a`). Shows, per run: id, repo, mode, candidates, spend and its basis, whether a verdict
  exists, whether it's below-floor, and whether it's the run currently applied to prefs.
- **`demo`** — a fully synthetic end-to-end smoke: fixture git repos, stub dispatch, both
  acquisition modes (issue-replay and general/mutation-repair, each run end to end), all four
  oracles, a rendered verdict including a below-floor example, and a demonstration that
  rewriting the test harness cannot earn `solved` — no network, no real CLI, nothing written
  outside a temp directory. Use this to sanity-check the tool itself, or to show a user what
  the output actually looks like before running anything real.

## Presenting the results

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
