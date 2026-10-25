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
  invalid graph (reusing `graph`'s verdict, never a second validator). *Amended 2026-10-24
  (D3's seventh amendment, user-approved during T4): non-strict exit 3 means a
  `verify-unparseable`; every other finding gives exit 3 only under `--strict`.*
- A2. For every task it reports, machine-readably (`--json`) and as text: (i) each
  repo-relative path the brief names in backticks, classified `exists | created-by-<task-id> |
  missing` — "created-by" is a disclosed resolution, never a silent pass; (ii) the verify
  block's **parseability** in the one dialect `kit_contract._extract_verify` accepts (missing
  `**Verify.**` fence = finding); (iii) **runnability without running**: the command's first
  word resolves on `PATH`, and every path-shaped argument under the repo (`bin/x.py`,
  `tests/test_y.py`, `-m unittest tests.test_y` → `tests/test_y.py`) exists or is created by a
  task this kit declares before it in dependency order. Proven red→green on a temp fixture kit
  with one missing script, one unparseable verify, one verify naming a file a later task
  creates; mutation-proven: deleting the fixture file flips exit 0 → 3. *Amended 2026-10-24
  (D3's seventh amendment): the flip holds under `--strict`; without it, the deletion adds a
  `verify-missing-path` warning and the exit stays 0.*
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
  closed on exit 3; none runs the P0 review. *Amended 2026-10-24: the gate fails closed only for
  a `verify-unparseable` on a task still to run or on the `--task` target (D3's seventh
  amendment, D5's amendment during T5).*
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

*D3 amended a second time 2026-10-24, during T4, by the user's decision on the implementer's
survey.* Read against every committed kit, D3 still refused ordinary verifies. Under D5 a
refusal has no opt-out, and D17(a) promises that a spike passes, so five more rules apply.
(1) `[[`, `source`, `.` and `:` join the builtin first words, and the operands of `[[` are
values, like those of `test` and `[`. (2) An argument written with quotes in the verify source
is a value and is never path-checked. This covers grep patterns such as `'/dashboard/'` and the
code after `python3 -c`. The `-m` and `-p` mappings above still read quoted values. (3) An
argument word with `=` before any `/` (`MODE=a/b`) is a value, by the same rule as a first-word
assignment. (4) A token with `:` before its first `/` (`HEAD:docs/x.md`) is a git object name,
not a path. (5) A path that an earlier simple command in the same verify writes counts as
`created-by` the task itself. "Writes" means the target of a `>` or `>>`, or an operand of
`tee`, `touch` or `mkdir`. This amendment does narrow D3: a script path passed in quotes
(`python3 "bin/x.py"`) is no longer checked. The first word, unquoted arguments, and the
`-m`/`-p` mappings still are. The user chose this trade. A false refusal blocks every driver
with no way around it, while a missed quoted path still fails when the verify runs.

*D3 amended a third time 2026-10-24, during T4, by the user's decision on the red-team's
findings ("block only on what can't start").* Even after the second amendment, the generic rule
"any argument containing `/` must exist" refused runnable verifies: git refs (`origin/main`),
`sed s/a/b/`, output and fixture-dir arguments, relative paths after `cd`, `trap`, `case`, and
the commonest spike shape, "Implement `spike/run.py`" with `python3 spike/run.py`. A refusal has
no opt-out under D5, so a path finding now blocks only where a missing path stops the verify
from starting.
(1) **Blocking positions.** `verify-missing-path` and `verify-missing-executable` arise only in
these places:
  - the command word of a simple command (a missing tool, or a missing path such as `./bin/x.sh`);
  - the script operand of an interpreter (`python`, `python3`, `bash`, `sh`, `zsh`, `node`, `ruby`,
    `perl`). This is the first argument not starting with `-`, unless `-c`, `-m` or `-` comes
    first. It is checked when it contains `/` or ends in `.py .sh .js .mjs .rb .pl`;
  - the `-m` and `discover -s/-p` test mappings. A dotted module maps only when its first segment
    is a directory under the repo root, so stdlib modules such as `json.tool` are never mapped;
  - the operand of a literal `cd`.

  Every other argument is still resolved and recorded in `verify.paths` with its state. A
  `missing` one prints a path summary line and is never a finding.
(2) **Builtins.** Every bash builtin and reserved word counts as a builtin first word (`trap`,
`exec`, `eval`, `local`, `declare`, `return`, `shift`, `unset`, `case`, `esac`, `function`,
`select`, `time`, `pushd`, `popd` and the rest of bash's list). A `((…))` command is not
checked. Lines from `case` through `esac` are not checked. A function the verify defines
(`f() {` or `function f`) is defined for later command words.
(3) **Inside `[[ … ]]`.** `&&`, `||`, `<` and `>` are test operators, not separators or
redirects. Nothing inside the brackets is checked.
(4) **Paths after `cd`.** After a literal `cd D`, later relative paths resolve against `D`. After
a dynamic `cd` (one carrying `$` or a substitution) or a bare `cd`/`cd -`, relative paths are not
checked for the rest of the verify. More writers count for rule 5 of the second amendment: the
last operand of `cp`, `mv`, `ln` and `install`, and the directory operand of `git init`,
`git clone` and `git worktree add`.
(5) **Creation claims.** A creation claim is read from the task block before its `**Verify.**`
marker only, meaning the brief and the acceptance. The verify's own words never claim to create
a path. The creation words are `new`, `create`, `add`, `write`, `implement`, `build`, `make`,
`generate`, `scaffold`, `author`, `draft`, `introduce`, `produce`, `save`, `emit`, `output`,
`put`, `extract`, `move`, `rename` and `split`, each with its `-s`/`-ed`/`-ing` forms and the
irregular `built`, `made` and `written`. The word must end within 80 characters before the path.

This amendment narrows D3 a great deal. A data argument such as `cat docs/nowhere.md` no longer
blocks, while a missing script, tool or `cd` target still does. It also tightens D3 in two
places: an interpreter's bare script name (`python3 zz.py`) is now checked, and the verify's own
words no longer clear a path.

*D3 and D5 amended a fourth time 2026-10-24, during T4, by the user's decision after the second
red-team round ("only sure things block").* The second round still found refusals of verifies
that start fine: `make && ./app`, a guarded `cd x || true`, spike briefs that say "Prototype",
`exec 2>&1`, and `arr=(a b c)`. Each red-team round over a static shell reader finds more, and
under D5 each one would refuse a kit. So exit 3 now means only what `analyze` knows for sure.
(1) **What blocks.** Non-strict exit 3 comes only from `verify-unparseable` (the drivers cannot
read the verify) and `verify-missing-executable` (a bare command word that is not on `PATH`,
not a builtin or reserved word, and not a function the verify defines). An unknown bare word does
not block after `source`, `.` or `eval` in the same verify, since the sourced text may define it.
It also does not block after an earlier command in the same verify carrying the word `install`,
since that step may put it on `PATH`.
(2) **What warns.** `verify-missing-path` keeps every position and rule above. Like
`brief-missing-path`, it is printed, it is never a driver refusal, and it gives exit 3 only
under `--strict`. The execute skill's P0 spec review (D4) reads these warnings and adjudicates
them, so a human or a reviewing model with judgement decides whether a missing script is a
defect.
(3) **Bugs fixed in the same pass.** These fall short of the plan text, so they are not
amendments:
  - a digit right before a redirect operator (`2>&1`, `3<file`) is a file-descriptor number, not
    a word;
  - a command made only of redirections is skipped;
  - `NAME=(…)` is an array assignment;
  - analysis time grows linearly with the verify's size.

What this gives up: a missing script, `cd` target or test module no longer stops a driver.
The 72 `cd /path/to/polytropos` placeholders in older kits become warnings, and so does
`python3 bin/missing.py`. They still fail when the verify runs. They now reach the P0 review
and the author's `--strict` run instead of a hard refusal.

*D3 amended a fifth time 2026-10-24, during T4, by the user's decision after the third red-team
round ("block only on simple verifies").* Once only `verify-missing-executable` could refuse a
kit, the third round's false refusals all came from one guess: is this word really an
undefined command? Functions defined inside `if`, nested, or with the brace on the next line;
`${x%%;*}`; a heredoc or `case` inside `$(…)`; and a verify that puts its own tool on PATH each
broke that guess.
(1) **Simple verifies.** A `verify-missing-executable` refuses only in a verify that uses none
of the following features, anywhere in its fence:
  - a function definition: the reserved word `function`, or a word followed by `(` `)`;
  - the reserved word `case`;
  - an unquoted `${`;
  - a command substitution (`$(…)` or backticks) that spans lines or contains `<<` or `case`;
  - an assignment to `PATH`, whether a prefix, plain, or `export`;
  - `source`, `.` or `eval`;
  - an install step: a command carrying the word `install`, or any command whose first word
    is a package manager (`npm`, `pnpm`, `yarn`, `bun`, `pip`, `pip3`, `uv`, `cargo`, `gem`,
    `brew`, `go`).

  This replaces the fourth amendment's narrower "after `source`/`.`/`eval`/`install`" scope.
  In a verify that uses any of these, the same finding is printed as a warning. It still gives
  exit 3 under `--strict`, and the P0 spec review still sees it.
(2) **Conformance fixes in the same pass.** These bring the code up to the plan text and are
not amendments:
  - a command word with `$` anywhere in it is dynamic and is not checked;
  - analysis stays linear in the size of the verify and of TASKS.md, including nested `{`
    groups and the per-task dialect hint.

What this gives up: a missing tool in a verify that defines functions, uses `case`, edits PATH
and so on warns instead of refusing. The verify still fails when it runs. False refusals are now
bounded by construction instead of by patching: the gate refuses only where the reader models
every construct in the verify.

*D3 and D5 amended a sixth time 2026-10-24, during T4, by the user's decision after the fourth
red-team round ("fix and close, with a stop rule").* About 560 verifies turned up two parse
bugs and one gap.
(1) **Tool guards.** Two more cases are not refusals:
  - A tool probe makes the verify non-simple. A tool probe is a command whose word is
    `command` (with `-v` or `-V`), `type`, `hash` or `which`.
  - An unknown command word that is the left operand of `||` is a warning. The author expects
    it may fail, and `x || exit 1` then warns instead of refusing.
(2) **The drivers check only what they will run.** `exit_if_unsound_kit` exits 3 only for a
refusing finding on a task whose status is not `done`. Findings on `done` tasks are still
printed. `analyze` itself still reports every task. So a finished task whose tool is now missing
never refuses a run of other pending tasks.
(3) **An empty verify.** A `**Verify.**` fence that is empty or only whitespace is
`verify-unparseable`. There is nothing to run, and `bin/codex_execute.py` already rejects it.
This tightens D3, and it is a sure thing.
(4) **Conformance fixes, not amendments.** `exec {fd}>file` and the other `{name}` redirections
are redirections, not command words. `[[ … ]]` and `(( … ))` keep their mode across newlines.
(5) **Stop rule for T4.** One last red-team pass runs. Only a traceback, a hang over 10 seconds,
an execution or write, or a non-strict exit 3 on a simple verify that bash would run reopens
T4. Every other finding is recorded in NOTES.md as a follow-up for a later kit, never as
another round.
(6) **Silent-case readings accepted under this amendment** (orchestrator, 2026-10-24). Each one
moves only toward warning. They are written here so the text matches the code:
  - heredoc delimiters are read as bash reads them;
  - `alias` and `enable` make a verify non-simple;
  - a bare `PATH` operand (`read PATH`, `printf -v PATH`) and an assignment to a computed name
    count as a PATH change;
  - any word containing `install` or `bootstrap` counts as an install step;
  - a tool probe inside a command substitution counts as a probe;
  - every command inside a group (`{ … }`, `( … )`, `if … fi`, a loop) that is the left operand
    of `||` counts as a left operand.

  The `install`/`bootstrap` reading is wider than the words "carrying the word `install`". It
  can turn a refusal into a warning in a verify that merely names such a file, and it was
  accepted knowing that.

*D3 and D5 amended a seventh time 2026-10-24, during T4, by the user's decision after the
final red-team pass reopened T4 ("only unparseable blocks").* Even a missing tool in a simple
verify is not a sure failure. Bash may never reach the word: `[ -n "$CI" ] && tool`, code
after `exit`, the right of `||`. Static reading cannot settle reachability, so this amendment
stops trying.
(1) **What blocks.** Non-strict exit 3, and with it every driver refusal, comes only from
`verify-unparseable`: `_extract_verify` returns None, or the fence is empty or whitespace.
That needs no guess, because the drivers cannot run what they cannot read.
(2) **What warns.** `verify-missing-executable` keeps every rule above, including the
simple-verify guard, whose features stay named in the finding's detail. Like
`verify-missing-path` and `brief-missing-path`, it is now printed, judged by the P0 spec review,
and gives exit 3 only under `--strict`.
(3) **The drivers' gate checks only what they will run.** `exit_if_unsound_kit` exits 3 only
for a `verify-unparseable` on a task whose status is `pending` or `in-progress`. `done` and
`blocked` tasks never refuse a run. Their findings are still printed.
(4) **Fixes in the same pass:**
  - created-by resolution is linear over a long `depends:` chain;
  - when the verify runs `shopt -s extglob`, `@(…)`, `+(…)`, `?(…)`, `*(…)` and `!(…)` are each
    one word, so a `|` inside one is not a pipe;
  - `analyze` exits quietly with its own code when stdout closes early (`| head`), with no
    traceback.

What this gives up: a missing tool no longer stops a driver before its first dispatch. The run
spends that task's dispatch and then fails its verify through the drivers' existing failure
path, and the P0 review and `--strict` see the warning first. The stop rule of the sixth
amendment carries over unchanged to the one red-team pass that follows.

*D5 amended 2026-10-24, during T5, by the user's decision on T5's red-team finding ("also check
the `--task` target").* The seventh amendment's status filter assumed that `done` and `blocked`
tasks never run. Two driver flags run them on purpose: `--task X --rerun` re-dispatches a `done`
task, and `--task X` is the drivers' sanctioned retry of a `blocked` one. With the filter, either
flag dispatched a task whose verify cannot be read. The fix keeps the sixth amendment's principle,
"the drivers check only what they will run", and checks what will actually run:
`exit_if_unsound_kit(kit_dir, tasks, out=None, selected=None)` exits 3 for a `verify-unparseable`
on any `pending` or `in-progress` task, and on the task whose id is `selected`, whatever that
task's status. Every driver calls it as `exit_if_unsound_kit(kit, tasks, selected=args.task)`.
Old `done` tasks still never refuse a normal run.

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
confirmed defect, and fixes TASKS.md (or stops and reports) before dispatching. *Amended
2026-10-24, after the Phase 2 review, by the user's decision ("feed them to the review").* The
orchestrator passes `analyze`'s text output into the P0 prompt. The reviewer gets a third sort
of finding: an `analyze` warning it judges a real defect, recorded as `kind=unrunnable-verify`
or `kind=unspecified-path` with `when=pre-run`. Only the interactive loop has this adjudicator.
The headless drivers and `workflow: direct` kits print the warnings, and nothing judges them.
The plan and the docs say so plainly. Opus because the
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
never fail a driver run. Since D3's fourth amendment, the same holds for verify-path findings,
and since its seventh amendment for missing executables too. Only a `verify-unparseable` on a
`pending` or `in-progress` task fails a driver run.

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

*D6 and B1 amended 2026-10-24, after the Phase 3 review, by the user's decision ("guard on run
and date").* The Phase 3 reviewer copied sdd-docs-refresh into a temp dir and ran `accept` on
its 11 done tasks. Each exited 0, and `freshness` went from `unknown` to `fresh`. That was
backfill with no flag at all, because `accept_task` took the task's latest passing `outcome:`
line from any run. `accept` now refuses unless that line carries `run=` equal to `--run`, and
the run id's date is today or yesterday in UTC, read from the clock when `accept` runs. Under
that rule, an old kit's lines cannot be accepted even by passing their old run id. A line
without `run=` is refused. The loop's order is unchanged: the outcome line first, then `accept`
with the same run id. What remains is a hand-authored outcome line carrying a fresh run id.
That is a fabricated record, which CLAUDE.md already forbids, and no tool can tell it from a
real one.

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

*D7 amended 2026-10-24, after the Phase 2 review, by the user's decision ("only
unparseable").* `unrunnable` means only that the task has a `verify-unparseable` finding, and
then nothing is run. Every other done task's verify is run and judged by its rc. Its
`verify-missing-*` findings ride along in that task's report as `warnings`, so a `drifted`
result caused by a missing tool is labelled as such. The state is never read from the
`verify.paths`/`executables` entry states, because those record non-blocking arguments
(`origin/main`, `s/a/b/`, an `--out` target) as `missing` without any finding. Running the
check is the ground truth, as in D3's seventh amendment.

*D7 and B1 amended 2026-10-24, during T8, by the user's decision ("parse acceptance now").*
T8's implementer found that `_parse_block` never reads a task's `**Acceptance.**` paragraph.
`_extract_brief` stops there, and the returned dict has no `acceptance` key, so
`acceptance_identity(task)` is None for every task parsed from TASKS.md. As a result no
`accept` and no driver projection ever recorded an `acceptance_ref`, and `drift` could only
report `acceptance=unknown`. The parser now carries `acceptance`: the text between
`**Acceptance.**` and `**Verify.**`, stripped, or `""` when the paragraph is absent. This is
no new field and no new grammar. Acceptance is already a named task field (CLAUDE.md's shared
contract, `TASK_FIELDS`, `to_contract`); the parser had been dropping it. One consequence:
every driver's `TaskRun.project` and `accept` now record an `acceptance_ref`, which is what
`acceptance_identity` was written for. Records written before this have none and read
`unknown`, and nothing is backfilled (B's forward-only rule).

*D7 amended again 2026-10-24, after T8's red-team, by the user's decision ("a skipped kit gives
3").* Under `--all`, a kit that is reported but not checked makes the exit 3. That covers a
TASKS.md that fails to parse, an invalid graph, and a slug the ledger refuses. The reasoning is
the same as for an `unrunnable` task one level down: a check that cannot run is not a hold.
`--kit` keeps its exit-2 refusals, and an empty kits dir still exits 0 with `no kit under`.

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

**D17 — Exploration stays cheap and unblocked** (added 2026-10-24 before T4, by the user's
decision: "make sure polytropos can still handle exploration well"). Three consequences, each
pinned in the task that owns it. (a) T4 proves that an exploration-shaped kit — verify commands
like `true` or `python3 -c …`, briefs that name files their tasks will create — passes
`analyze` with exit 0, so the drivers' fail-closed call (D5) cannot block a spike for being a
spike; D5's no-opt-out stance stands. (b) The P0 spec review (D4) is skipped when `kit_contract.py
roster` reports `workflow=direct`: that kit already opted out of independent review, and the
loop records that the P0 review was skipped and why. (c) The guide says how to explore before
writing a spec: Part 1 gains a vendor-neutral "explore first, then specify" sentence, and Part 2
names the polytropos paths for it (`/polytropos:route`, `/polytropos:escalate`, a `scout`,
`workflow: direct`) and how a finished spike becomes a spec.

## Risks and tripwires

- **R1 — Driver fixtures that `analyze` now refuses.** `tests/test_{claude,copilot,codex,
  cursor}_execute.py` build temp kits whose verify commands may name files that do not exist
  in the temp tree. After T5, run those four files. Since D3's seventh amendment, only a
  `verify-unparseable` on a pending or in-progress task fails a driver run. Such a failure is a
  fixture whose verify the drivers cannot read or whose fence is empty. Fix the FIXTURE, never
  the heuristic. Every other finding is a printed warning and fails no fixture. If more than five fixtures need this, stop and report: the heuristic
  may be broader than D3 states.
- **R2 — Word ceiling.** After T10 and T11 run `python3 -m unittest discover -s tests -p
  'test_docs_skill_dispositions.py' -q`; if red, move words into `spec-review.md`, never
  raise the ceiling.
- **R3 — Exact-event-dict tests.** `tests/test_role_ledger.py` asserts `parse_defects` events
  equal `{"task","kind"}` exactly; add `when` only when present (D9). `stale-pin-2` must still
  parse as its own raw kind (it becomes `unsanctioned` at read time, which is the point).
- **R4 — The other verify dialect.** Many committed kits (e.g. `sdd-docs-refresh`) use
  `Verify:` + a bare fence, which `_extract_verify` cannot read. `analyze` on them exits 3 with
  `verify-unparseable` on every task and no hint: D3 fires the hint only when
  `kit_verify_hook._task_verify_cmd` would parse the block, and that parser reads neither a plain
  `Verify:` line nor a bare fence (corrected 2026-10-24 during T4, by the user's decision; the
  first wording promised the hint). `drift --all` reports their tasks `unrunnable` and goes on.
  That is correct and expected — do not widen `_extract_verify` (the drivers execute what it
  returns; widening it is a different kit).
- **R5 — `CLAUDE.md` is at its 16000-byte ceiling** (`tests/test_guardrails_layout.py`). Do
  not edit it in this kit; command lists go in `docs/GUIDE.md` and `docs/HOW-IT-WORKS.md`.
- **R6 — Sandbox availability.** `enforced` mode needs `sandbox-exec` (Darwin). Tests inject
  the runner and never call `exec_policy.run_confined`; only T13's self-check runs `drift`
  for real, and `python3 bin/exec_policy.py check` must exit 0 on that host first.
  *Amended 2026-10-24, after the Phase 3 review, by the user's decision ("move drift to a
  step").* `exec_policy.py check` only finds the binary. In a shell that is already sandboxed,
  every confined verify returns rc 71 (`sandbox_apply: Operation not permitted`) and reads
  `drifted`. So T13 first runs `drift` on a harmless temp fixture and reads `--json` for rc
  71. The self-drift is no longer part of T13's verify, where it would nest a second `drift`
  inside the sandbox, which the macOS sandbox refuses to allow, and leave T13 `drifted` in every
  later self-drift. It is a numbered step instead, with its output recorded in NOTES.md.
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
