# kit-preflight — check the spec before the run, record what freshness needs, settle the defect vocabulary

autonomy: advisory
budget: max-dispatches=40 max-escalations=3 max-consults=3
roles: test-author red-team

Written 2026-10-24 on branch `feat/route-experiment` at HEAD `1cd9e62` ("Merge release/0.6.10").
Roadmap items A + B + C of `docs/sdd/guide.md` Part 4, built as one kit. The spec half below
(Goal; Constraints and out of scope) was approved by the user in this conversation, as drafted,
with the architect's recommendation taken on every open question; the design half (D1–D16)
follows from those decisions. `workflow: extended` is implied by the `roles:` line (D16).

## Goal

Close the three gaps `docs/sdd/guide.md` Part 4 ranks first, so that a kit is checked against
itself **before the first dispatch spends anything** (A), an interactively executed kit leaves
the evidence `kit_contract.py freshness` needs and any finished kit can be re-checked against
today's tree **without being marked failed** (B), and the brief-defect ledger stops splitting one
recurring problem across coined synonyms (C) — all inside the existing kit contract, with no new
task field and no new roster role.

**Done means every line below holds, each with the named enforcement:**

A — pre-run spec check
- A1. `python3 bin/kit_contract.py analyze --kit <dir>` exists. It is static: it **never
  executes a verify command, never spawns a CLI, never writes** — proven by a test whose
  injected runner asserts it was never called and whose fixture kit is byte-identical afterwards
  (`git status --porcelain` empty, TASKS.md bytes unchanged). Exit 0 = sound, 3 = findings, 2 =
  invalid graph (reusing `graph`'s verdict, never a second validator).
- A2. For every task it reports, machine-readably (`--json`) and as text: (i) each
  repo-relative path the brief names in backticks, classified `exists | created-by-<task-id> |
  missing` — "created-by" is a disclosed resolution, never a silent pass; (ii) the verify
  block's **parseability** in the one dialect `kit_contract._extract_verify` accepts (missing
  `**Verify.**` fence = finding); (iii) **runnability without running**: the command's first
  word resolves on `PATH`, and every path-shaped argument under the repo (`bin/x.py`,
  `tests/test_y.py`, `-m unittest tests.test_y` → `tests/test_y.py`) exists or is created by a
  task this kit declares before it in dependency order. Proven red→green on a temp fixture kit
  with one missing script, one unparseable verify, one verify naming a file a later task
  creates; mutation-proven: deleting the fixture file flips exit 0 → 3.
- A3. The interactive execute skill (`skills/execute/SKILL.md`) runs `analyze` right after
  `graph` and `roster`, before the first dispatch, and then dispatches ONE fresh-context **spec
  review** — PLAN.md against TASKS.md for contradictory acceptance and goals no task covers —
  recorded as a `reviewer: P0 …` line (existing family, phase token `P0`), with each confirmed
  finding written as a `defect:` line **before any `outcome:` line exists for the run**. No new
  roster token, no new agent file: the kit's existing `<slug>-reviewer` agent (opus, read-only
  tools) runs it with a prompt kept in a new read-when reference
  `skills/execute/references/spec-review.md`. Pinned by a skill-text test in the style of
  `tests/test_architect_approval_pause.py`; `tests/test_skill_entrypoints.py` (every reference
  has a "read when") stays green.
- A4. `bin/routing_scorecard.py` counts a `reviewer: P0` line as a review event and the
  `--history` card says how many defects were caught pre-run (the optional `when=pre-run` pair
  on `defect:` lines, D11); fixture-NOTES test proves it.

B — freshness for interactive kits, then drift
- B1. `python3 bin/kit_contract.py accept --kit <dir> --task <id> --run <run-id>
  [--attempt-store]` appends the same `task.projected` acceptance the headless drivers'
  `TaskRun.project` writes — workspace fingerprint, each dependency's latest artifact,
  `acceptance_ref` from `acceptance_identity` — to the attempt ledger **outside the tree**
  (`bin/runtime_data.py` `attempts` store). Implemented by calling the existing `TaskRun` path,
  never a second copy (`tests/test_kit_contract.py`'s duplicate-implementation guard must stay
  green). It refuses a task that is not `done` and refuses to backfill: no flag reconstructs an
  acceptance from NOTES.md prose or git history.
- B2. `skills/execute/SKILL.md` step 4 ("On pass") calls `accept` once per accepted task —
  exactly one bash call, one line of output, so the lean-driver cost is one tool call per task.
  Proven by driving a temp fixture kit through the CLI with a temp `--attempt-store`:
  `freshness` then reads `fresh`, and re-accepting an upstream task on a changed tree flips its
  dependant to `stale` (mutation-proven). Already-finished kits (e.g. `sdd-docs-refresh`) keep
  reading `unknown` — that is the correct, unchanged answer.
- B3. `python3 bin/kit_contract.py drift --kit <dir> [--all] [--attempt-store] [--exec-mode
  enforced|trusted-host] [--json]` re-runs each **done** task's verify command against the
  current tree through `bin/exec_policy.verify_runner` (`enforced` default; `trusted-host` is
  the only opt-out and the report names it) and reports per task `holds | drifted | unrunnable
  | unknown` plus, where a ledger acceptance exists, whether the acceptance identity changed
  since (`criteria-changed`). It **never changes a status, never writes TASKS.md/NOTES.md, never
  dispatches**; exit 0 = nothing drifted, 3 = drift observed, **never 1** — drift is a report,
  not a failure. Identical verify commands across tasks run once. Proven with an injected runner
  on a fixture kit (tree byte-identical after; runner called once per distinct command; a
  failing runner yields `drifted`, a missing script yields `unrunnable`). Per the approved
  decision on Q2, `drift` appends one `evidence.drift` event per checked task to the attempt
  ledger (outside the tree) and nothing anywhere in the tree.

C — the defect vocabulary
- C1. `skills/execute/references/ledger.md` lists the sanctioned kinds **each with a one-line
  definition**: the original six plus the recurring coined ones `unrunnable-verify`,
  `false-zero-spec`, `underivable-requirement`. Singletons are mapped: `incomplete-acceptance →
  underivable-requirement`, `process-guardrail → stale-plan-decision`, `unsafe-parallel-marking
  → contradictory-acceptance` (an `independent:` mark that contradicts the brief's own file
  overlap), and `verifier-destructive-restore` is **excluded** as not an architect brief defect
  (it is a verifier incident), surfaced as a note, never counted.
- C2. The mapping lives in ONE table in `bin/routing_scorecard.py` (the module that owns
  `parse_defects`), applied at read time; the event keeps the raw kind;
  `bin/lessons_promote.py` clusters on the canonical kind through that same module (one place,
  two consumers). The `--history` card renders canonical counts with a "(folded: X n, Y m)"
  note and flags any kind outside the sanctioned list as `unsanctioned` — so future coinage is
  visible at the next card rather than silently splitting. **No committed NOTES.md changes** —
  proven by asserting `git diff --stat -- .claude/kits` is empty after the suite and by fixture
  tests on raw lines.
- C3. Every tracked enumeration of the kinds agrees: `ledger.md`,
  `skills/architect/references/routing-evidence.md`, `docs/SPEC-DRIVEN.md`, `docs/sdd/guide.md`
  Part 4 (its "None is built" and "several kinds outside the sanctioned vocabulary" sentences
  updated in the same edit), with `docs_build.py build` run and `check` green.

Whole-kit "done": `python3 -m unittest discover -s tests -v` green from the repo root;
`python3 bin/docs_build.py check`, `python3 bin/copilot_docs.py check`,
`python3 bin/release_gate.py check` all exit 0; `python3 bin/kit_contract.py analyze --kit
.claude/kits/kit-preflight` exits 0 on this kit itself; and `python3 bin/kit_contract.py drift
--kit .claude/kits/kit-preflight` reports every task `holds` on the finishing tree. Also in
scope by approval: `docs/GRAPH-ENGINEERING.md`'s claim that `skills/execute/SKILL.md` flips a
task's status through `kit_verify_hook.py` is corrected to what the skill actually does (T12).

## Constraints and out of scope

- **No contract change.** No new task field, no new TASKS.md grammar, no new roster token (the
  seven optional roles stay seven), no new PLAN.md line family. Requirement ids / `covers:`
  (roadmap F) are out; A's "uncovered goals" check is the P0 reviewer's judgment, not a machine
  join. No `superseded:` line family (Q6, declined for v1).
- **A spends nothing and mutates nothing.** The only model dispatch A introduces is the P0 spec
  review, made by the interactive skill through the Agent tool — never from a `bin/` script, a
  test, or a verify command. The real `claude`/`codex`/`copilot`/`agent` CLIs are never invoked
  anywhere.
- **B records forward only.** `accept` writes only what the current tree and ledger say now;
  nothing backdates or reconstructs acceptances for kits already finished (CLAUDE.md: a stored
  record is never reconstructed from prose). `drift` writes nothing in the tree and nothing to a
  kit dir; its one write is the `evidence.drift` ledger event outside the tree.
- **Verify commands run only under `bin/exec_policy.py`**, `enforced` by default;
  `trusted-host` is the sole, self-reporting opt-out. Tests inject the runner and never run a
  real verify.
- **C never edits history.** Committed NOTES.md lines are untouched; the fold is a read-time
  view in one module; raw kinds stay inspectable.
- **One kit contract.** Everything new in Python lands in `bin/kit_contract.py` (or
  `routing_scorecard.py` for C) and is re-exported, never duplicated into a driver. Headless
  drivers pick up only what the shared CLI gives them: per the approved decision on Q4, all
  four call the static `analyze` through one shared helper before their first dispatch and fail
  closed on exit 3; none runs the P0 review.
- **Non-Claude bundles (`copilot/`, `codex/`, `cursor/`) are not edited by hand**; only
  generators' regenerated mirrors may change. Capability rows in
  `primitives/harness-capabilities.json` are not flipped from `unknown` by this kit.
- **Stdlib-only Python; temp fixture kits and temp `--attempt-store` in every test; never the
  real store, never `~/.claude`.** The PostToolUse `kit_verify_hook` stays unwired (wiring it
  is a `~/.claude` settings change).
- **No rotting numbers in skills or docs**: defect counts live only in the `--history` card.
- **Architect/execute stay in sync**: the architect skill changes only in
  `references/routing-evidence.md` (point at the sanctioned list and say `analyze` exists to
  write briefs against); `SKILL.md` Step 2's task-field contract text is untouched.
- Out of scope: roadmap D, E, F, G, H; any routing or pricing change; wiring `analyze` into
  `kit_scheduler.py`; a dashboard panel for drift; renaming or deprecating `refresh`.

## Architecture and key decisions

**D1 — One module each, re-exported, never copied.** `analyze`, `accept`, and `drift` are
functions in `bin/kit_contract.py` (`analyze_kit`, `exit_if_unsound_kit`, `accept_task`,
`drift_kit`) plus three subparsers on its existing `_cli`. The defect vocabulary (`DEFECT_KINDS`,
`DEFECT_FOLDS`, `DEFECT_EXCLUDED`, `canonical_defect_kind`) lives in `bin/routing_scorecard.py`
because that module owns `parse_defects` and `lessons_promote.py` already lazy-imports it for
exactly that parser. `tests/test_kit_contract.py` fails if a driver redefines a name the
contract owns or two drivers share a body ≥ 85% identical over 8+ lines — so the driver change
(D5) is a one-line call per driver, nothing more.

**D2 — `analyze` is static by construction, not by discipline.** `analyze_kit(kit_dir, tasks,
strict=False)` takes no runner argument at all; there is no code path that could execute a
verify command, and the test proves it by monkeypatching `kit_contract._pr` and
`subprocess.run`/`subprocess.Popen` to raise and asserting `analyze` still returns. Its
repo root is `attempt_ledger.kit_repo_root(kit_dir)` (the directory holding
`.claude/kits/<slug>`, or the kit's parent for a fixture elsewhere), so a fixture kit in a temp
dir resolves paths against the temp dir, never against this repo.

**D3 — The path and verify heuristics, pinned.** Brief paths: in the text of a task block
before `**Verify.**`, every single-backticked span with no whitespace that contains `/` or ends
with one of `.py .md .json .toml .yml .yaml .txt .html .sh .css .js`; skip a span that starts
with `-`, `$`, `~`, `<`, `{`, or `http`, or that contains any of `* ? [ ] { } ( ) < > ::`; strip
trailing `.,:;` and a `:<digits>` line suffix (`bin/x.py:42` → `bin/x.py`). Classification:
`exists` when the path (absolute, or relative to the repo root) exists; else
`created-by-<id>` when that same path appears, in this task or any task upstream of it
(transitively), preceded within 40 characters by one of `new`, `create`, `creates`, `add`,
`adds`, `write`, `writes` (case-insensitive); else `missing`. Verify runnability: first drop
heredoc bodies (from a line containing `<<'TAG'`, `<<"TAG"`, or `<<TAG` through the line that
is exactly `TAG`) and `$(…)` substitutions; split the rest on newlines, then tokenize each
line with `shlex.shlex(line, posix=True, punctuation_chars=True)` and `whitespace_split=True`,
so `&&`, `||`, `;` and `|` separate simple commands only where they stand OUTSIDE quotes (on
`ValueError` fall back to whitespace split). The first word: a token containing `=` before any
`/` is an assignment, skip; a token in `{cd test [ ! echo printf export set true false exit for
do done if then else elif fi while until read}` is a builtin, skip — and the operands of `test`
and `[` are values being compared, not files being read, so they are never path-checked; a
token containing `/` is a path and must exist (absolute or
repo-relative); anything else must resolve via `shutil.which` → otherwise
`verify-missing-executable`. Arguments: after `-m` a dotted module (`tests.test_x`) maps to
`tests/test_x.py`; after `-p` following a `discover`, a glob-free pattern maps to
`<-s value or tests>/<pattern>`; any other argument that contains `/`, has no glob
characters, and does not start with `-`, `$`, `~`, or `http` is checked for existence;
everything after a `>` or `>>` token in a simple command is output and skipped; a token with
a component starting with `$` is skipped. Classification for verify paths is the same three
states, with `created-by` including the task **itself** (a task may verify the test file it
creates); `missing` is the finding `verify-missing-path`. A verify block that
`_extract_verify` returns `None` for is `verify-unparseable`, with the hint "uses a dialect
(`Verify:` or a bare fence) that `kit_contract` does not read" when
`kit_verify_hook._task_verify_cmd` would have parsed it. Finding kinds are exactly
`ANALYZE_FINDINGS = ("verify-unparseable", "verify-missing-executable", "verify-missing-path",
"brief-missing-path")`. Exit: 2 invalid graph; 3 when any of the first three occur, or when
`strict` and a `brief-missing-path` occurs; else 0 — with the brief findings still printed.
Why this strictness split (approved Q1): briefs legitimately name files a task will create and
the created-by heuristic will sometimes miss, so a brief path is advice; a verify path is the
run's proof and must be there.

*D3 amended 2026-10-24, before T4, by the user's decision after the Phase 1 review.* The first
version split on `|`/`&&`/`;` before honoring quotes and path-checked every `/`-bearing operand.
Read literally, it made this kit's own commit-task verifies (a quoted `'^(feat|fix|docs|…)'`
regex, and `test … = feat/route-experiment`) report missing executables and a missing path, so
T4's own acceptance could not hold. The amendment makes the reading quote-aware and exempts
`test`/`[` operands. It does not narrow what counts as a missing script, executable or path.

**D4 — The spec review is a `P0` phase review, not a role.** Adding a roster token is a
contract change in three places; a phase review with token `P0` is already in grammar
(`parse_reviewers` takes a free-form phase label). The interactive loop dispatches the kit's
`<slug>-reviewer` agent once per kit — only when NOTES.md carries no `reviewer: P0` line yet,
so a resumed kit does not re-review — with the prompt in
`skills/execute/references/spec-review.md`: read PLAN.md's Goal and "done" list, Constraints,
and every task's acceptance and verify; return findings of exactly two sorts — acceptance
clauses that cannot all hold (across a task, between a task and the fences, between a verify
and its acceptance) and "done" items no task's acceptance covers — each cited to file:line, in
the defect vocabulary. The orchestrator adjudicates, appends `reviewer: P0 model=opus
findings=<n> confirmed=<n> result=…` and one `defect: <id> kind=<kind> when=pre-run` per
confirmed defect, and fixes TASKS.md (or stops and reports) before dispatching. Opus because the
card's reviewer precision on opus is the highest measured of any role (read `python3
bin/routing_scorecard.py --history`; do not type the number into any file).

**D5 — The drivers' seat for `analyze`.** `exit_if_unsound_kit(kit_dir, tasks, out=sys.stderr)`
runs `analyze_kit(..., strict=False)`, prints every finding, and `sys.exit(3)` when the exit
would be 3 (invalid graph is already `exit_if_invalid_graph`'s job; the helper leaves it to the
existing call). Each of `bin/claude_execute.py`, `bin/copilot_execute.py`,
`bin/codex_execute.py`, `bin/cursor_execute.py` calls it in `cmd_run` immediately after its
`roster_for_run(...)` line — before any `--dry-run` branch, any claim, any preamble — so a
preview refuses the same way a run would. No opt-out flag: the check is static and free, and a
kit whose verify cannot run is a kit no dispatch can prove. Brief-path findings are printed and
never fail a driver run.

**D6 — `accept` is a projection, not an attempt.** `accept_task(kit_dir, task, run_id,
actor="interactive", store=None, workspace=None, note="")`: requires `task["status"] == "done"`;
reads the kit's NOTES.md and requires `recorded_outcome_result(notes_text, task_id)` to be a
pass value (`pass`, `retry-pass`, `escalated-pass`) — the `outcome:` line is written FIRST by
the loop, and `accept` records the acceptance that line already states, so nothing here is
hand-authored; opens the ledger with `open_ledger`, builds a `TaskRun(ledger, run_id, task,
workspace=repo_root, actor=actor)` and calls `project("done", result=<that result>,
outcome_line=True, note=note)` — no `begin()` (no claim is taken; a projection is not a
dispatch) and no `end()`. The CLI has exactly `--kit --task --run --attempt-store --note`; there
is deliberately no `--artifact`, `--upstream`, `--at`, or `--from-notes` argument, and the test
asserts the parser rejects each. Exit 0 with one line `accept: <id> artifact=<12 hex> upstream=
<dep>:<12 hex|unknown>,…`; exit 2 on refusal with the reason.

**D7 — `drift` semantics.** `drift_kit(kit_dir, tasks, runner, store=None, workspace=None,
run_id=None, record=True, confinement=None)` considers only `done` tasks. For each: the static
verify check from D3 first — `verify-unparseable` / `verify-missing-*` → state `unrunnable`,
nothing run; otherwise run the verify text through `runner` once per distinct stripped command
(later tasks with the same text reuse the result and list `shared-with`), rc 0 → `holds`,
rc ≠ 0 → `drifted`. Beside the state, `acceptance` is `unchanged` when the ledger's latest
acceptance carries an `acceptance_ref` whose `sha` equals `acceptance_identity(task)["sha"]`
now, `changed` when it differs, `unknown` when no acceptance or no ref is recorded. When
`record` is true, append `evidence.drift` to the kit's ledger with `run`, `task`, `state`,
`rc`, `acceptance`, `verify_sha`, `confinement`, `shared_with` (nothing else — no output text,
which may hold paths and is bounded elsewhere). Exit code of the CLI: 0 when every checked task
`holds`; 3 when any is `drifted` or `unrunnable`; never 1. The CLI's runner is
`exec_policy.verify_runner(repo_root, mode=args.exec_mode, on_result=<capture confinement>)`
with `repo_root = kit_repo_root(kit)`; the text report's first line is `drift: <slug>
confinement=<backend|trusted-host>` so a trusted-host run can never read as enforced. `--all`
walks every `<kits-dir>/*/TASKS.md` (default `.claude/kits`), one section per kit, and a kit
whose TASKS.md fails to parse is reported as `kit: <slug> unparseable -- <reason>` and skipped.
Nothing in `drift` calls `project_status`, `set_status`, `append_run_note`, or writes under the
kit dir; the test asserts the kit dir's bytes and `git status --porcelain` are unchanged.

**D8 — Why `refresh` stays as is.** `refresh` re-binds ONE stale task's evidence and projects
`blocked` on failure — it mutates kit state on purpose, under an operator's explicit task
argument. `drift` is the read-only survey that tells the operator which task to `refresh`. The
two are complementary and neither is renamed.

**D9 — The vocabulary fold is a read-time view.** `parse_defects` keeps its grammar and its
event shape (`{"task", "kind"}`; a `when` key is added only when the pair is present, so every
existing test asserting exact event dicts still holds). Canonicalization is a separate step:
`canonical_defect_kind(kind) -> (canonical, note)` where `note` is `None` for a sanctioned
kind, `"folded"` for a `DEFECT_FOLDS` key, `"excluded"` for a `DEFECT_EXCLUDED` member
(canonical is `None`), and `"unsanctioned"` otherwise (canonical is the raw kind). The
architect aggregate (`by_kind`) counts canonical kinds, drops excluded ones, and carries three
new keys: `folded` (`{raw: {"into": canonical, "count": n}}`), `unsanctioned` (`{kind: n}`),
`excluded` (`{kind: n}`), plus `pre_run` (count of defects carrying `when=pre-run`). The card
renders `kinds:` from canonical counts, then `folded:`, `unsanctioned:`, `excluded:` lines only
when non-empty, and `caught pre-run: n`. `lessons_promote.collect_defect_evidence` maps each
event's kind through `canonical_defect_kind` and drops excluded ones, so both consumers
cluster identically; its "exact tokens, no fuzzy matching" rule is preserved — a fold table is
an exact map, not a similarity.

**D10 — The sanctioned kinds and their definitions** (copied verbatim into `ledger.md` by T2
and into the `DEFECT_KINDS` mapping by T1 — one wording, two homes, test-compared):

- `stale-pin` — the brief anchors on a file, line, phrase or identifier that no longer exists
  where the brief says it does.
- `tautological-verify` — the verify command passes before the work is done, so a later pass
  proves nothing.
- `unrunnable-verify` — the verify command cannot execute as written: unparseable, a missing
  script or path, a wrong invocation form.
- `missing-helper` — the brief relies on a helper, fixture or flag that no task in the kit
  creates and the tree does not have.
- `unspecified-path` — the brief leaves a destination, file or location to the implementer's
  guess.
- `contradictory-acceptance` — two acceptance clauses, or an acceptance and its verify or a
  fence, cannot all hold at once.
- `stale-plan-decision` — a PLAN.md decision the tree already contradicts when the task runs
  (kit-level; task token `-`).
- `false-zero-spec` — the brief asserts something is absent, zero or never the case that the
  tree shows is present.
- `underivable-requirement` — an acceptance that cannot be derived from the brief plus the
  tree: no stated source, no measurable form, or a criterion left incomplete.

Folds: `incomplete-acceptance → underivable-requirement`, `process-guardrail →
stale-plan-decision`, `unsafe-parallel-marking → contradictory-acceptance`. Excluded:
`verifier-destructive-restore` (a verifier incident, not a brief defect; it stays in NOTES.md
prose and the card notes it was seen).

**D11 — `when=pre-run`.** One optional pair on `defect:` lines, value exactly `pre-run`, set
only on defects confirmed by the P0 review (or by `analyze`'s findings adjudicated before the
first dispatch). Absent means today's behavior (confirmed mid-run). Any other value is noted
and ignored. This is a NOTES.md line-format addition inside an existing family — not a task
field — stated in `ledger.md` beside `run=`/`parent=`/`failure=`.

**D12 — The execute skill stays under its ceiling.** `tests/test_docs_skill_dispositions.py`
caps `skills/execute/SKILL.md` at 3200 words of body (it is near 2700 today — measure, do not
assume). The SKILL.md gains only the loop changes: one sentence block after the roster check
(run `analyze`, then the P0 review per `references/spec-review.md`), one sentence in step 4
(call `accept` after the `outcome:` line), and one read-when line for the new reference. All
prompt text, recording detail and adjudication rules go into `spec-review.md`.
`tests/test_skill_entrypoints.py` requires the reference to be listed with "read when" and
forbids "read all references".

**D13 — Scope is Claude-interactive-first, shared code is harness-neutral.** The recording gap
is interactive-only (drivers already project acceptances); `analyze` and `drift` are plain CLI
over the shared contract, so Codex, Copilot and Cursor users get them without any bundle edit.
The drivers' `analyze` call (D5) is the one driver-side change. No file under `copilot/`,
`codex/`, `cursor/`, `copilot-docs/` is hand-edited; the only changes there, if any, are
generator output from `bin/copilot_docs.py build` and `bin/sync_codex_surfaces.py` when their
checks report drift because a source they mirror changed — run the check first, build only on
drift, and name it in NOTES.md.

**D14 — Model pins, from the card.** Run `python3 bin/routing_scorecard.py --history` and
`--roles` before executing; the architect read them on 2026-10-24 and pinned: **opus** for the
three tasks whose shape is new engine logic with many edge rules (T4 `analyze`, T8 `drift`) and
for the one task whose product is a prompt every future kit will run (T10 spec review) —
opus and sonnet show the same first-try rate on the card, so the pin buys judgment on the
heuristics, not pass rate; **sonnet** for wrappers, wiring, docs, and skill edits (T1, T2, T5,
T7, T11, T12, T13); **haiku** for the three commit tasks (T3, T6, T9), which are mechanical.
Verifier on sonnet (the repo re-tiered it there in the previous kit on the card's precision
evidence); reviewer on opus.

**D15 — Commits.** Each phase ends in a commit task on `feat/route-experiment` in the user's
convention (global CLAUDE.md: `type(scope): outcome`, prose body, honesty rules, the trailer the
session mandates). Never push, never `main`, never `git add -A` — stage named paths. The
orchestrator's final status flip of the last task lands after T13's commit; the user commits
it or asks for it.

**D16 — Roles declared: `test-author` and `red-team`, dispatched on the engine tasks.** The
`--roles` card on 2026-10-24 showed test-author and red-team with the highest marginal-catch
rates of any role on small samples (read the card; it says "insufficient sample" where it
cannot support a number). This kit's value concentrates in four engine tasks whose acceptance
is machine-checkable and whose failure modes are edge inputs (heredocs, dialects, missing
stores): T4, T5, T7, T8. Execute dispatches both roles on exactly those four tasks (test-author
after the implementer, red-team after verify passes) and dispatches neither on docs, skill or
commit tasks — say so in NOTES.md once, at Setup. The roster grammar records what ran; a role
not dispatched on a task is simply a task without that `agent:` line. Agents
`.claude/agents/kit-preflight-test-author.md` and `kit-preflight-red-team.md` are instantiated
from the templates unchanged in model and tools.

## Risks and tripwires

- **R1 — Driver fixtures that `analyze` now refuses.** `tests/test_{claude,copilot,codex,
  cursor}_execute.py` build temp kits whose verify commands may name files that do not exist
  in the temp tree. After T5, run those four files; a failure whose message is
  `verify-missing-path`/`verify-missing-executable` is a fixture naming a path it never
  created — fix the FIXTURE (create the file, or make the command path-free such as `true`),
  never the heuristic. If more than five fixtures need this, stop and report: the heuristic
  may be broader than D3 states.
- **R2 — Word ceiling.** After T10 and T11 run `python3 -m unittest discover -s tests -p
  'test_docs_skill_dispositions.py' -q`; if red, move words into `spec-review.md`, never
  raise the ceiling.
- **R3 — Exact-event-dict tests.** `tests/test_role_ledger.py` asserts `parse_defects` events
  equal `{"task","kind"}` exactly; add `when` only when present (D9). `stale-pin-2` must still
  parse as its own raw kind (it becomes `unsanctioned` at read time, which is the point).
- **R4 — The other verify dialect.** Many committed kits (e.g. `sdd-docs-refresh`) use
  `Verify:` + a bare fence, which `_extract_verify` cannot read. `analyze` on them exits 3 with
  `verify-unparseable` and the hint; `drift --all` reports their tasks `unrunnable` and goes on.
  That is correct and expected — do not widen `_extract_verify` (the drivers execute what it
  returns; widening it is a different kit).
- **R5 — `CLAUDE.md` is at its 16000-byte ceiling** (`tests/test_guardrails_layout.py`). Do
  not edit it in this kit; command lists go in `docs/GUIDE.md` and `docs/HOW-IT-WORKS.md`.
- **R6 — Sandbox availability.** `enforced` mode needs `sandbox-exec` (Darwin). Tests inject
  the runner and never call `exec_policy.run_confined`; only T13's self-check runs `drift`
  for real, and `python3 bin/exec_policy.py check` must exit 0 on that host first.
- **R7 — Generated mirrors.** Any edit under `skills/` or `docs/*.md` changes `docs-site/`;
  run `python3 bin/docs_build.py build` in the same task and stage both. `release_gate.py
  check` and `copilot_docs.py check` likewise.
- **R8 — This kit must pass its own `analyze`.** Every brief here says "new `path`" for a
  file a task creates, and every verify names only files that exist or that the task itself
  or an upstream task creates. If T13's self-check exits 3, the finding names either a brief
  that violated that rule (fix the brief and record `defect: … kind=unspecified-path`) or a
  heuristic gap (record it; do not loosen D3 to pass).
- **R9 — The `evidence.drift` event and `attempt_history.py`.** `attempt_history` joins
  ledger events by kind; an unknown kind must be ignored, not crash. T8 runs
  `tests/test_attempt_history.py` and `tests/test_attempt_ledger.py` after adding the event.
- **R10 — `accept` ordering.** If the orchestrator calls `accept` before writing the
  `outcome:` line, it exits 2 with "no outcome line" — that is the designed order, not a bug.
