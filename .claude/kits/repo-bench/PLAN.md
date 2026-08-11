# PLAN — repo-bench: measure candidate models on a chosen repo's real work, then re-tier or pick a daily driver — on explicit user action only

autonomy: advisory

## Goal

The repo has three legs of routing evidence today: a PUBLISHED prior (`bin/bench_routing.py`
over the screenshot-transcribed Artificial Analysis index), and OBSERVED outcomes
(`bin/routing_scorecard.py` over kits already run — passive, free, but blind to models never
dispatched). This kit builds the third leg: MEASURED-ON-DEMAND. One new engine,
`bin/repo_bench.py`, plus one new skill, `skills/repo-bench/SKILL.md`, that point at ANY git
repo, select candidate Claude models, and measure them on that repo's own work — two
acquisition modes (issue-replay when the repo's history yields usable issue→fix pairs;
mutation-repair general benchmark otherwise), four layered grading oracles, and two verdict
shapes off the same run: a re-tiered strong/mid/weak map (≈ reviewer / implementer / verifier
for loop engineering) and a daily-driver pick for quick task resolution. Plan-first: the
default invocation prices the whole matrix from `data/pricing.json` and stops; real dispatch
requires `--live` plus an explicit `--max-usd` ceiling. Results land in a gitignored dated
store; routing only changes via a separate, explicit `apply` step.

**No task in this kit dispatches a real model, invokes `gh`, or runs a live benchmark.** Every
test and verify uses stub runners and fixture repos. The first live run is a user decision
taken after the kit lands, never a kit task.

## Done means (all checkable from the repo root)

1. `python3 bin/repo_bench.py demo` exits 0: fully synthetic end-to-end smoke — fixture git
   repo, stub dispatch runner, both acquisition modes exercised, all four oracles graded, a
   verdict rendered with its labels — no network, no real CLI, no real repo, nothing written
   outside a temp dir.
2. `python3 bin/repo_bench.py plan --repo <path> --models <ids>` prints the exact
   models×tasks matrix with a per-dispatch and total cost estimate derived at run time from
   `data/pricing.json` (judge grades included), then stops. `run` without BOTH `--live` and
   `--max-usd` refuses, prints the same plan, and exits non-zero — structurally, not
   politely.
3. A `run` against a target repo leaves that repo byte-identical: the engine touches a target
   only through a read-only git allowlist; all mutation happens in per-(task×candidate)
   sandboxes built by tree-extraction (no history), so the reference fix is unreachable by
   the candidate BY CONSTRUCTION. A test proves the target's worktree and refs are unchanged
   after a full stubbed run.
4. `verdict` refuses to emit a routing-grade tier map below the evidence floor (D7) and
   labels every oracle gap per task instead of silently reweighting; `apply` (separate,
   explicit) writes gitignored `prefs/repo-bench.json` and hard-refuses a below-floor
   verdict.
5. `.gitignore` carries root-anchored `/benchruns/`; CLAUDE.md carries the benchruns
   invariant bullet + run-lines and stays ≤ 16000 bytes (`tests/test_guardrails_layout.py`).
6. Full suite green: `python3 -m unittest discover -s tests -q` — every new test uses temp
   fixtures and injected runners; the count only grows and no existing test changes.

## Decisions (each with the why — executors follow these, not their own taste)

**D1 — Spend posture: plan-first; `run` requires `--live` AND `--max-usd`, enforced before
every dispatch.** The default `plan` does everything except spend: mines the task pack,
resolves candidates, prints the matrix priced per dispatch (candidate dispatches + judge
grades) and the total. `run` without both flags refuses with exit 2 after printing the plan —
a runaway benchmark must be structurally hard. During a live run the ceiling is re-checked
before EVERY dispatch (candidate or judge): projected spend = recorded spend so far + the
next dispatch's estimate; over the ceiling → stop cleanly, mark every remaining cell
`skipped: cost-ceiling`, label the results envelope `partial (cost-ceiling)`. Recorded spend
per completed dispatch uses harness-reported token counts priced locally when extractable,
else the plan estimate, and the envelope says which (`spend basis: actual|estimated|mixed`).
This mirrors the repo's `--demo`/`--dry-run` conventions and the budget-stop precedent
(`claude_execute`): a stop is stated plainly, never folded into a fluent summary.

**D2 — Claude-only, behind an injectable harness-adapter seam.** Claude is the only harness
with real per-token pricing, so scores can carry honest dollars. The adapter contract (a
plain dict/namespace: `name`, `build_argv(bin_, model_id, prompt)`, `extract_usage(output)`,
`pricing loader`) is the seam codex/copilot drop into later — it exists and is exercised by a
stub adapter in tests, but NO codex/copilot adapter is built here (out of scope). The Claude
adapter REUSES `bin/claude_execute.py` via the house importlib pattern
(`bench_routing._load`): `build_dispatch` + `PERMISSION_FLAG` for the argv shape,
`resolve_model` for tier-word→id resolution, `generate_run_id` for content-free run ids.
`repo_bench` defines its own default runner (it needs `cwd=<sandbox>`), but the argv shape is
never re-derived. Usage extraction appends `OUTPUT_FORMAT_ARGS = ("--output-format", "json")`
and parses token counts from the result JSON — best-effort, MEDIUM confidence, the
`PERMISSION_FLAG` precedent exactly: ONE module constant + one parse function; if reality
disagrees, the fix is a one-constant/one-function correction against the CLI docs, never a
redesign, and the degradation path (estimate + label) already covers a parse miss.

**D3 — Sandbox = tree extraction + fresh `git init`; the target repo is read-only by
construction.** Rejected: `git worktree` (shares refs and the object store with the user's
checkout — a candidate model running destructive git commands in a worktree can damage the
real repo) and plain `git clone` (the fix commit and origin refs ride along, so a candidate
could find the reference fix via `git log --all` — solution leak). Chosen: per
(task×candidate) sandbox built by `git archive <base-commit> | tar -x` into
`<run-dir>/work/...`, then `git init` + one initial commit. Properties: (a) the target repo
is only ever touched by an allowlisted set of read-only git commands (`archive`, `show`,
`log`, `rev-parse`, `diff`, `ls-tree`, `cat-file`, `status`) run with `-C <target>` — the
allowlist is a module constant and the single choke point for target access; (b) the
reference fix is UNREACHABLE in the sandbox — there is no history to mine; (c) the candidate
patch is captured as a git diff against the sandbox's initial commit (untracked files
included, robust to agent-made commits). Sandboxes live under the run dir (`work/`), deleted
after grading unless `--keep-work`.

**D4 — Two acquisition modes; auto prefers issue-replay, falls back honestly.**
*Issue-replay*: mine the target's `git log` OFFLINE for fix commits referencing issues
(`fixes/closes/resolves #N` and squash-merge `(#N)` subjects). Per pair: base = first parent,
reference patch = the fix diff, oracle-test availability = whether the fix touched files
matching the test-path patterns (configurable, sane defaults), and the fix commit's
test-file blobs are extracted AT MINING TIME (the sandbox has no history to fetch them from
later). The problem statement is the issue title/body when available — `gh issue view`
enrichment is OPTIONAL, behind a flag, through an injectable runner, and never invoked by any
test — else the commit subject+body, labeled `statement from commit message (weaker than
issue text)`. The prompt NEVER contains the reference patch; a test asserts no hunk line of
the reference appears in the prompt. *General (fallback)*: mutation-repair — deterministic
textual mutation operators (comparison flips, boolean negation, off-by-one, and/or swaps)
applied one per task and VALIDATED RED (the repo's `--test-cmd` must fail in a scratch
sandbox with the mutation, at zero model cost) before the task is admitted; the candidate is
told the tests fail and must find and fix the bug; the reverse-mutation diff is the reference
patch. Auto mode: issue-replay when it yields ≥ D7's floor of usable pairs, else general,
and the plan states which mode was chosen and why. General mode requires `--test-cmd`; a repo
with no runnable tests can still be issue-replayed but its verdict will be
judge/structural-only and labeled accordingly (D5/D7).

**D5 — Four oracles, layered, each independently labeled and independently degradable; the
combination rule is explicit and inspectable, never a blended scalar.**
(a) *tests-as-oracle* (objective): grade in a COPY of the post-dispatch sandbox — write the
fix commit's test blobs in, run `--test-cmd`, rc 0 = solved. Only for tasks whose fix touched
tests; additionally each such task is red-checked at base in a scratch copy (blobs in, tests
must fail) — a task green-at-base is labeled `not a discriminating oracle` and drops out of
objective coverage rather than inflating it. The test blobs are NEVER placed in the sandbox
the candidate works in (they encode the fix — that is the leak). In general mode the repo's
own visible tests are the oracle (red-validated at generation).
(b) *structural diff* (always available): files-touched overlap, hunk overlap, LOC-delta
ratio, out-of-scope file count vs the reference patch — reported as SIMILARITY, with that
word, never as correctness.
(c) *LLM judge* (subjective, priced): D6.
(d) *cost & latency* (always available): wall-clock per dispatch; dollars from token counts
priced via `data/pricing.json` at run time — this axis, not capability, is what separates
"daily driver" from "strong tier".
Combination: a task×candidate cell is `solved` iff oracle (a) passed; where (a) is
unavailable the cell is `unverified` and shows (b)+(c) beside that label. The verdict table
prints one column per oracle with explicit `n/a` cells; when an oracle is missing for a task
the verdict SAYS SO — no silent reweighting, no composite score anywhere.

**D6 — Judge bias controls.** The judge model defaults to the strongest-tier model in
`data/pricing.json` that is NOT a candidate (derived at run time, never a hardcoded id) and a
judge that is simultaneously a candidate in the same run is a HARD refusal (flag error, exit
2). Each grade presents the reference and candidate patches as blind randomized `Patch A` /
`Patch B` slots with the issue statement; the slot assignment is recorded per grade so the
result is auditable. Judge dispatches go through the same injectable runner seam and are part
of the priced matrix (D1). Judge output is parsed structurally; an unparseable grade degrades
to `judge: unparseable` + note, never a guessed score.

**D7 — Evidence floor: `MIN_EVIDENCE_TASKS = 5` objectively-scored tasks per candidate.**
`routing_scorecard.LIVE_MIN_SAMPLE` (3) is the floor for PASSIVE ledger rates; an ACTIVE
re-tiering decision changes routing for every future kit and demands more, so this kit pins
its own higher structural constant. Below the floor: `verdict` still prints the raw
measurement table but stamps `BELOW EVIDENCE FLOOR — not a routing-grade verdict` on the card,
the envelope, and verdict.md; `apply` hard-refuses (exit 2) — a 3-task benchmark can
never re-tier a model here, by construction. `--min-tasks` may RAISE the floor per run, never
lower it. The bench_routing `insufficient sample` idiom is the precedent for the wording.

**D8 — The store: gitignored `benchruns/<run-id>/` in THIS plugin repo, never in the
target.** Run id = `claude_execute.generate_run_id()` (`<UTC-date>-<4 hex>`, content-free) —
the date rides in the id, telemetry's dated-envelope spirit with a per-run granularity. Run
dir: `plan.json`, `tasks/<task-id>.json` (mined records incl. reference patch + test blobs),
`dispatches/` (per-cell record: argv model, wall-clock, usage, patch), `results.json` (ONE
self-describing envelope: `store_schema_version` 1, run metadata, per-cell oracle grades,
spend basis, honesty labels, notes), `verdict.md` (human-readable). `bin/repo_bench.py` is
the ONLY writer under `benchruns/`; envelopes are never hand-authored or backdated; absence,
partial coverage, and estimate-vs-actual labels ride inside every envelope (telemetry-store
law, applied here). `list` enumerates the store tolerantly (missing dir → friendly line,
rogue entries → note, never a crash).

**D9 — Report + OPT-IN apply; measurement never changes routing as a side effect.** `apply`
is its own subcommand: reads a named run's verdict, prints exactly what it will write, and
writes `prefs/repo-bench.json` (gitignored via the existing root-anchored `/prefs/` line —
the `copilot_prefs` precedent): `{schema_version: 1, applied_at, source_run, repo, tiers:
{strong, mid, weak}, daily_driver, labels}`. Refusals: no verdict in the run, below-floor
verdict (D7), or a tier-map model id no longer present in `data/pricing.json` (staleness).
Consumption is pull-only and advisory: `skills/repo-bench/SKILL.md` documents the schema and
`skills/route/SKILL.md` gains one short body-only paragraph telling the router to CHECK the
file and cite it when present — no engine auto-reads it, and nothing in architect/execute
changes in this kit.

**D10 — Three-legs non-duplication (the sharpest fence).** `bench_routing` = published prior;
`routing_scorecard` = observed ledger; `repo_bench` = measured-on-demand. `repo_bench`
re-implements NONE of: ledger parsing (reuse `routing_scorecard.scan_kits`/stats via
importlib when the target has `.claude/kits`), pricing math (reuse
`cost_report.match_model`/`rates_for` — the only local arithmetic is tokens × rate),
benchmark ranking (reuse `bench_routing.load_benchmarks`/`normalize_id` for the prior
lookup). The verdict prints a per-candidate three-legs line — published index (when the model
is in `data/benchmarks.aa.json`), observed first-try rate (when the target's ledger evidences
it, `no ledger evidence` otherwise), measured result — and when the legs disagree (e.g.
measured ranking inverts the published index order) it prints `DISAGREEMENT — signal, not
error` and lets all three stand. Never averaged, never reconciled into one number.

**D11 — The tests-as-oracle exposure, stated honestly and fenced.** Running a target repo's
test suite executes arbitrary code from that repo. This is the same trust the user already
extends by running their own tests, and it runs ONLY: inside a sandbox/scratch copy under the
run dir, with cwd there, when the user explicitly supplied `--test-cmd`. `repo_bench` never
invents a test command, never runs one against the plugin repo itself, and the skill says
plainly: only benchmark repos whose test suite you would run by hand. No sandboxing theater
is claimed — the honest statement is the fence.

## Constraints

- Python stdlib only; no pip, no pytest. `subprocess` to `git` is sanctioned (local,
  free, and for targets restricted to the D3 read-only allowlist); `subprocess` to
  `claude`/`gh` exists ONLY behind injectable runners that every test stubs.
- Never invoke the real `claude`, `copilot`, `codex`, or `gh` CLI from any test, verify
  command, or kit task. `demo` + `plan` + stubbed runners are the only sanctioned smokes.
- No hardcoded prices, price ratios, or real model ids in engine or skill — candidates,
  judge, tiers, and dollars all derive from `data/pricing.json` at run time. Structural
  constants sanctioned for this kit: `MIN_EVIDENCE_TASKS = 5`, `OUTPUT_FORMAT_ARGS`,
  the read-only-git allowlist, mutation-operator table, size→profile thresholds,
  store/prefs schema versions (1), oracle/status vocabularies.
- Target repos in tests are throwaway fixture repos built in temp dirs — never `~/`,
  never a real project, and the real `benchruns/`/`prefs/` are never touched by tests.
- Reuse, never fork: `bin/claude_execute.py`, `bin/cost_report.py`,
  `bin/routing_scorecard.py`, `bin/bench_routing.py` are imported via the house importlib
  pattern and NEVER edited by this kit.
- Do not commit or push.

## OUT OF SCOPE — executors must NOT

- Build codex/copilot adapters, or anything that reads `pricing.codex.json` /
  `pricing.copilot.json`.
- Run a live benchmark, dispatch any real model, or invoke `gh` — the kit produces the tool,
  not its first spend.
- Edit `bin/bench_routing.py`, `bin/routing_scorecard.py`, `bin/cost_report.py`,
  `bin/claude_execute.py`, `bin/session_cost.py`, their tests, any pricing file, any skill's
  YAML frontmatter, `skills/architect/SKILL.md`, `skills/execute/SKILL.md`, or any existing
  kit's files.
- Auto-apply a verdict, wire any engine to read `prefs/repo-bench.json` automatically, or
  bulk-inject the benchruns store into a session's context.
- Add network code beyond the injectable `gh` seam; no HTTP clients, no API tokens.
- Build HTML reports or dashboards.

## Risks and tripwires

- **R1 — Headless flag surface (usage extraction).** `OUTPUT_FORMAT_ARGS` and the result-JSON
  shape are best-effort, never live-verified (that spends tokens). Tripwire: if the parse
  fails on real output someday, the degradation path (estimate + `spend basis: estimated`
  label) already covers it — fix is one constant/function against the CLI docs, never a
  redesign, and NEVER a live invocation from a test.
- **R2 — Solution leak.** Any path that lets the candidate see the reference patch or the
  fix's test blobs (in the prompt, in the sandbox, via git history) invalidates the whole
  measurement. Tripwire: the leak tests in T2/T6 fail → stop, fix the leak; never weaken the
  assertion.
- **R3 — Git fixture portability.** Fixture repos in tests must pin identity via
  `-c user.name=t -c user.email=t@example.com` on every `commit`, and never depend on the
  default branch name (use explicit commits/`rev-parse HEAD`, not `main`/`master`).
  Tripwire: a test failing only on another machine's git config.
- **R4 — Reuse blast radius.** The four reused modules are untouchable; if a reuse seam
  seems to need a change in one of them, STOP and report — do not edit, do not vendor a
  copy.
- **R5 — CLAUDE.md byte ceiling.** 12099 bytes at kit-authoring time; the layout test fails
  at 16000. T10 adds ~0.8 KB of pinned text — writing more means stop and trim.
- **R6 — Oracle inflation.** The seductive failure is quietly promoting structural
  similarity or a judge grade into "solved" when tests are missing. The vocabulary is
  load-bearing: `solved` is oracle-(a)-only, forever. Tripwire: any rendering where a
  candidate's headline number mixes oracle classes.
