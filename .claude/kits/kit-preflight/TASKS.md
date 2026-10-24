# kit-preflight — tasks

Dispatch preamble. Read `PLAN.md` (D1–D16, the out-of-scope fence) and `GUARDRAILS.md` before
any task. Every verify command runs from the repo root
`/Users/michaelcave/Developer/reposV2/polytropos`. Tasks are strictly serial in id order (each
depends on the previous); no task is marked independent. Warm-cluster candidates (serial chain,
same primary file, same pin): **T7 → T8** would share `bin/kit_contract.py` but differ in pin
(sonnet → opus), so T8 is a fresh dispatch; **T10 → T11** share `skills/execute/SKILL.md` and
differ in pin (opus → sonnet), so T11 is fresh too. Every task is a cold spawn. Statuses:
pending | in-progress | done | blocked. The verifier agent is `kit-preflight-verifier`
(sonnet); the reviewer `kit-preflight-reviewer` (opus) runs at each phase end. The declared
roles `test-author` and `red-team` (`kit-preflight-test-author`, `kit-preflight-red-team`) are
dispatched on T4, T5, T7 and T8 only (PLAN D16).

Test invocation: this repo's tests load ONLY through `python3 -m unittest discover -s tests`
(optionally `-p '<file>.py'` and `-k <Class>`); the `python3 -m unittest tests.test_x` form
fails to import. Never pipe a unittest run into `tail` inside a verify command — the pipe hides
its exit status. Every new test uses a temp directory for its fixture kit and a temp
`--attempt-store`; nothing under `.claude/kits/` or the real data root is ever read as a
fixture or written.

Conventions that bind every task here (detail in `GUARDRAILS.md`): everything new lives in
`bin/kit_contract.py` or `bin/routing_scorecard.py` and is re-exported by drivers, never copied;
no code path in `analyze` can execute anything; `drift` and `accept` write only to the attempt
ledger outside the tree; committed NOTES.md files are never edited; the real
`claude`/`codex`/`copilot`/`agent`/`gh` CLI is never invoked; `CLAUDE.md` is not edited;
generated pages are rebuilt, never edited; stdlib only.

## Phase 1 — The defect vocabulary (C)

### T1 — Canonical defect kinds, folds, exclusions and `when=` in the scorecard
- id: T1
- title: Add the sanctioned defect vocabulary, read-time folding, the pre-run count and lessons_promote parity
- status: pending
- model: sonnet
- depends: (none)
- evidence: red-green

**Brief.** PLAN D9, D10, D11. Files: `bin/routing_scorecard.py`, `bin/lessons_promote.py`,
new `tests/test_defect_vocabulary.py`.

1. In `bin/routing_scorecard.py`, near `DEFECT_RE` (around line 226), add module constants:
   - `DEFECT_KINDS`: an ordered mapping (a tuple of `(kind, definition)` pairs or a dict
     preserving insertion order) of the NINE sanctioned kinds, in the order and with the exact
     one-line definitions written in PLAN D10 (`stale-pin`, `tautological-verify`,
     `unrunnable-verify`, `missing-helper`, `unspecified-path`, `contradictory-acceptance`,
     `stale-plan-decision`, `false-zero-spec`, `underivable-requirement`). The definition
     strings must be byte-identical to D10's text after the em dash, because T2 copies them
     into `ledger.md` and a test compares the two.
   - `DEFECT_FOLDS = {"incomplete-acceptance": "underivable-requirement", "process-guardrail":
     "stale-plan-decision", "unsafe-parallel-marking": "contradictory-acceptance"}`.
   - `DEFECT_EXCLUDED = ("verifier-destructive-restore",)`.
   - `DEFECT_WHEN = ("pre-run",)` — the only sanctioned value of the optional `when=` pair.
2. Add `canonical_defect_kind(kind) -> (canonical, note)` exactly as D9 specifies: sanctioned
   → `(kind, None)`; fold key → `(DEFECT_FOLDS[kind], "folded")`; excluded → `(None,
   "excluded")`; anything else → `(kind, "unsanctioned")`. Pure function, no I/O.
3. `parse_defects`: grammar unchanged; event dict stays exactly `{"task", "kind"}` UNLESS the
   line carries `when=`: then add `"when": value` when the value is in `DEFECT_WHEN`, and
   otherwise append a note `defect <tid> <kind>: unknown when=<value>, ignored` and omit the
   key. The dedupe key stays `(tid, kind)` on the RAW kind. Do not canonicalize here.
4. In the architect aggregation (the loop that builds `by_kind` around line 2155): count
   canonical kinds; skip excluded (they are not architect defects); add keys `folded`
   (`{raw: {"into": canonical, "count": n}}`), `unsanctioned` (`{kind: n}`), `excluded`
   (`{kind: n}`), and `pre_run` (number of counted defects whose event carries
   `when == "pre-run"`). `defects` (the grand total) counts only non-excluded defects.
   `kits_recording`/`by_kit` keep counting every recorded defect event as before (a kit that
   recorded only an excluded kind still "recorded"), so the existing tests on them hold.
5. In the card render (around line 2933): after the `kinds:` line, add `folded: raw→canonical
   n, …`, `unsanctioned: kind n, …`, `excluded: kind n, …` lines ONLY when their mapping is
   non-empty, and always `caught pre-run: <n>` when `arch["defects"] > 0`. Keep the existing
   "floor" sentence verbatim.
6. `bin/lessons_promote.py::collect_defect_evidence`: it receives `parse_defects` as a
   parameter; add a second optional parameter `canonical=None` and, when the caller passes
   `scorecard.canonical_defect_kind` (do so at the one call site around line 488), map each
   event's kind through it, dropping excluded events and recording a note
   `<kit>: defect <task> <raw> folded into <canonical>` for folds. Its docstring's "exact
   tokens, no fuzzy matching" rule stands — say in one sentence that a fold table is an exact
   map.
7. New `tests/test_defect_vocabulary.py` (stdlib `unittest`, loads the two modules by
   `importlib.util.spec_from_file_location` as the sibling tests do; see
   `tests/test_role_ledger.py` for the idiom). Cover: every `DEFECT_FOLDS` value and every
   `DEFECT_KINDS` key is sanctioned and no fold key or excluded kind is; `canonical_defect_kind`
   on all four classes; `parse_defects` on a line with `when=pre-run` (event has `when`), with
   `when=later` (no key, one note), without `when=` (event is exactly `{"task","kind"}`); an
   aggregation over a fixture NOTES text holding `stale-pin`, `incomplete-acceptance`,
   `verifier-destructive-restore`, `stale-pin-2` and one `when=pre-run` line — assert `by_kind`,
   `folded`, `unsanctioned`, `excluded`, `pre_run`, and that the rendered card contains
   `folded:`, `unsanctioned:`, `excluded:`, `caught pre-run: 1`; `collect_defect_evidence` with
   and without `canonical` on a temp kits dir; and a guard that `git diff --quiet --
   .claude/kits` holds after the module import (the module never writes). Use whatever
   aggregation entry point the scorecard exposes for a records list (read the module; the
   function that builds `roles["architect"]` is documented around line 2043) — do not call
   the real `.claude/kits` scan.

Gotcha: `tests/test_role_ledger.py` lines ~525–570 and `tests/test_routing_history.py` ~782
assert exact event dicts and exact `by_kind` on sanctioned kinds; both must stay green
unchanged. Never edit those tests.

**Acceptance.** The four constants and `canonical_defect_kind` exist with D10's wording; the
`--history` card over the committed kits renders a `folded:` line naming the three folds, an
`excluded:` line naming `verifier-destructive-restore`, no `unsanctioned:` line unless a
committed NOTES.md carries a kind outside the list (report what you see — do not edit any
NOTES.md to make it clean), and `caught pre-run: 0`; `python3 bin/lessons_promote.py --help`
still works and its demo/dry path (read its `--help`) clusters folded kinds together; the new
test file is red before the change (import of `canonical_defect_kind` fails) and green after;
`git diff --stat -- .claude/kits` is empty.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_defect_vocabulary.py' -q && python3 -m unittest discover -s tests -p 'test_role_ledger.py' -q && python3 -m unittest discover -s tests -p 'test_routing_history.py' -q && python3 -m unittest discover -s tests -p 'test_routing_scorecard.py' -q && python3 -m unittest discover -s tests -p 'test_lessons_promote.py' -q && python3 bin/routing_scorecard.py --history | grep -q 'folded:' && git diff --quiet -- .claude/kits
```

### T2 — Document the vocabulary and `when=pre-run` everywhere the kinds are enumerated
- id: T2
- title: Update ledger.md, routing-evidence.md, SPEC-DRIVEN.md and the guide's Part 4 to the sanctioned list, then rebuild the docs site
- status: pending
- model: sonnet
- depends: T1
- evidence: red-green

**Brief.** PLAN C1, C3, D10, D11. Files: `skills/execute/references/ledger.md`,
`skills/architect/references/routing-evidence.md`, `docs/SPEC-DRIVEN.md`,
`docs/sdd/guide.md`, generated `docs-site/**` via `python3 bin/docs_build.py build`; extend
`tests/test_defect_vocabulary.py` (created by T1) with the doc-parity tests below.

1. `ledger.md`, section "Role ledger — reviewer verdicts and brief defects": replace the
   sentence beginning "The kinds: `stale-pin`, …" with a list of the NINE kinds, each as
   "`<kind>` — <definition>" using D10's definitions verbatim; add one sentence naming the three
   folds and the exclusion ("`verifier-destructive-restore` is a verifier incident, recorded in
   prose, never as a `defect:` line"); keep the existing sentences about reuse, coining only
   when none fits, repeats and suffixes verbatim (test-pinned; `grep -rF` a phrase across
   `tests/` before touching any line). Then add the `when=` pair: the grammar line becomes
   `defect: <task-id> kind=<kebab-case-token> [when=pre-run]` and one paragraph states D11
   (set only on defects confirmed before the first dispatch — by the P0 spec review or by
   `analyze`'s findings; absent means confirmed mid-run; any other value is noted and ignored;
   a NOTES.md line format inside an existing family, not a task field). Do NOT change the
   "SIX machine-read line families" count — `when=` is a pair, not a family.
2. `routing-evidence.md`: where it tells the architect to read recurring defect kinds, point at
   `ledger.md`'s sanctioned list by name and add one sentence: before the first dispatch
   execute runs `python3 bin/kit_contract.py analyze --kit <dir>` (static: paths a brief names,
   verify parseability and runnability) and a P0 spec review, so a brief defect of those kinds
   is now caught before any dispatch and recorded `when=pre-run` — write briefs that pass it.
   Do not touch any other sentence; `tests/test_architect_approval_pause.py` and
   `tests/test_skill_entrypoints.py` read the architect SKILL.md, which you do not edit.
3. `docs/SPEC-DRIVEN.md` (~lines 99–104): the sentence "The kinds include `stale-pin`, …" now
   says the kinds are the nine sanctioned in `skills/execute/references/ledger.md`, names them,
   and says coined synonyms are folded at read time by `bin/routing_scorecard.py` and shown as
   folded or unsanctioned on the card. Nothing else in the file changes in this task (T12 adds
   the `analyze`/`accept`/`drift` paragraph).
4. `docs/sdd/guide.md` Part 4, section "What its own ledger says": the sentence "The same card
   showed several kinds outside the sanctioned vocabulary, coined mid-run, which splits
   recurring problems across synonyms." gains a following sentence: as of this kit the
   vocabulary is nine sanctioned kinds with definitions, coined kinds are folded or flagged
   `unsanctioned` on the card, and nothing in a committed NOTES.md was rewritten. Keep the "Run
   it" and roadmap table untouched here (T12 updates "None is built"). The section headings
   listed in `tests/test_sdd_docs.py` must remain byte-identical.
5. Run `python3 bin/docs_build.py build`; stage the regenerated pages with the sources.
6. Tests, appended to `tests/test_defect_vocabulary.py`: (a) every key of `DEFECT_KINDS`
   appears in `ledger.md` as "`<kind>` — <definition>" with the definition byte-identical to
   the module's; (b) `ledger.md` contains `when=pre-run`; (c) each of the four docs above
   names all nine kinds; (d) a synthetic negative: a copy of `ledger.md` in a temp dir with one
   definition altered fails the same comparison function.

**Acceptance.** The four documents enumerate the same nine kinds with one wording;
`ledger.md` carries the `when=` grammar; `python3 bin/docs_build.py check` exits 0;
`tests/test_skill_entrypoints.py`, `tests/test_docs_skill_dispositions.py`,
`tests/test_sdd_docs.py`, `tests/test_role_ledger.py` all pass; the parity tests were red
before this task's edits (the docs lacked `unrunnable-verify`).

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_defect_vocabulary.py' -q && python3 -m unittest discover -s tests -p 'test_skill_entrypoints.py' -q && python3 -m unittest discover -s tests -p 'test_docs_skill_dispositions.py' -q && python3 -m unittest discover -s tests -p 'test_sdd_docs.py' -q && python3 -m unittest discover -s tests -p 'test_docs_build.py' -q && python3 bin/docs_build.py check && grep -q 'unrunnable-verify' skills/execute/references/ledger.md skills/architect/references/routing-evidence.md docs/SPEC-DRIVEN.md docs/sdd/guide.md
```

### T3 — Commit Phase 1 at a green boundary
- id: T3
- title: Commit the vocabulary change on feat/route-experiment in the user's convention
- status: pending
- model: haiku
- depends: T2
- evidence: red-green

**Brief.** PLAN D15. Run the full suite once (`python3 -m unittest discover -s tests -q`, from
the repo root, reading the real exit status — never through a pipe) and `python3
bin/docs_build.py check`; both must be green before you stage anything. Stage by name:
`bin/routing_scorecard.py`, `bin/lessons_promote.py`, `tests/test_defect_vocabulary.py`,
`skills/execute/references/ledger.md`, `skills/architect/references/routing-evidence.md`,
`docs/SPEC-DRIVEN.md`, `docs/sdd/guide.md`, and the regenerated files under `docs-site/` that
`git status --porcelain -- docs-site` lists. Do NOT stage `.claude/kits/kit-preflight/` or
`.claude/agents/kit-preflight-*.md` (the orchestrator commits kit state separately). Never
`git add -A`. Commit on `feat/route-experiment` (confirm with `git branch --show-current`),
never on `main`, never push. Subject in the form `feat(ledger): sanction nine defect kinds and
fold coined synonyms at read time, history untouched` (or a better one in the same convention,
≤ 80 chars, imperative, lowercase after the colon, no period). Body: prose paragraphs wrapped at
80 columns — why the old state was wrong (coined kinds split recurrence; the six had no
definitions), what proves the new one (`tests/test_defect_vocabulary.py`, naming what it
asserts and that the negative fixture trips), what was deliberately not done (no NOTES.md
rewritten; `verifier-destructive-restore` excluded, not folded). No test counts. End with the
attribution trailer the session mandates and nothing else.

**Acceptance.** `git log -1 --format=%s` matches `^(feat|fix|docs|refactor|test|chore)\(` and
ends without a period; the body has at least two prose paragraphs; `git diff --quiet -- bin
tests skills docs docs-site` holds (sources clean); `git log origin/feat/route-experiment..HEAD`
lists the commit (or the branch has no upstream — either is fine; a pushed commit is a FAIL);
the branch is `feat/route-experiment`.

**Verify.**
```bash
test "$(git branch --show-current)" = feat/route-experiment && git log -1 --format=%s | grep -qE '^(feat|fix|docs|refactor|test|chore)\([a-z-]+\): [^A-Z].*[^.]$' && git diff --quiet -- bin tests skills docs docs-site
```

## Phase 2 — The static spec check (A, machine half)

### T4 — `kit_contract.py analyze`: paths, verify parseability and runnability, without running anything
- id: T4
- title: Implement analyze_kit and the analyze subcommand with the D3 heuristics and their tests
- status: pending
- model: opus
- depends: T3
- evidence: red-green

**Brief.** PLAN A1, A2, D2, D3. Files: `bin/kit_contract.py`, new `tests/test_kit_analyze.py`.

Add to `bin/kit_contract.py`, in a new section after the freshness section (before the CLI):

- `ANALYZE_FINDINGS = ("verify-unparseable", "verify-missing-executable",
  "verify-missing-path", "brief-missing-path")` and `PATH_STATES = ("exists", "created-by",
  "missing")`.
- `brief_paths(task_block_text)`, `verify_tokens(verify_text)`, `classify_path(path, repo_root,
  task_id, creators)`, and `analyze_kit(kit_dir, tasks, strict=False, repo_root=None) -> dict`.
  Implement the extraction, skipping, resolution and classification rules EXACTLY as PLAN D3
  states them — D3 is the specification; where D3 is silent, do the conservative thing (do not
  check the token) and say so in a comment. The repo root defaults to
  `_al().kit_repo_root(kit_dir)` (the attempt ledger already exposes it). "Created-by"
  resolution needs each task's block text: `parse_tasks` keeps only `brief`; add a private
  helper that re-splits the TASKS.md text into `{id: block_text}` the same way `parse_tasks`
  does (heading to heading), without changing `parse_tasks` or its output shape (the
  `test_the_dialect_parses_with_no_field_dropped` test pins it). Upstream is transitive over
  `depends`; "self" counts for verify paths, not for brief paths.
- The result dict: `{"v": CONTRACT_VERSION, "kit": <dir name>, "strict": bool, "exit": 0|3,
  "findings": [{"task", "kind", "detail"}], "paths": {task: [{"path", "state", "by"}]},
  "verify": {task: {"parseable": bool, "hint": str|None, "executables": [{"word","state"}],
  "paths": [{"path","state","by"}]}}}`. Exit 3 when any finding's kind is one of the first three,
  or `strict` and any `brief-missing-path`.
- `render_analyze(result)` → text: one line per finding `analyze: <task> <kind> -- <detail>`,
  then per-task path summaries for non-`exists` states (`analyze: <task> path <p> created-by
  <id>`), then `analyze: sound` or `analyze: <n> finding(s)`. Keep it terse: an executor pastes
  this into its context.
- `exit_if_unsound_kit(kit_dir, tasks, out=sys.stderr)`: runs `analyze_kit` non-strict, prints
  `render_analyze` to `out`, and `sys.exit(3)` when `result["exit"] == 3`. T5 wires it into
  the drivers; here it only exists and is tested.
- CLI: `analyze --kit DIR [--strict] [--json]`. Order of operations: `parse_tasks`,
  `exit_if_invalid_graph` (exit 2 on an invalid graph — reuse, never a second validator), then
  `analyze_kit`; print JSON or text; return `result["exit"]`. Add `analyze` to the parser's
  description sentence. Update the module docstring's subcommand list if it has one.
- The parseability hint: when `_extract_verify` returns `None`, lazily import
  `bin/kit_verify_hook.py` (sibling-file idiom already used for `_al()`/`_ep()`; name it
  `_kvh()`) and call its `_task_verify_cmd(text, task_id)`; a non-None result yields the hint
  text in D3. Never call anything else from that module.

Static by construction: `analyze_kit` has no runner parameter and must import nothing that
spawns. Test it the way D2 says: monkeypatch `kit_contract._pr` to a callable that raises and
`subprocess.run`/`subprocess.Popen` to raise, then call `analyze_kit` on every fixture and
assert it returns.

Tests, new `tests/test_kit_analyze.py` (stdlib, temp dirs; reuse the `_kit_text` idea from
`tests/test_kit_graph.py` but write briefs with backticked paths and real verify text). Fixture
kit under `<tmp>/.claude/kits/fx/TASKS.md` with files created under `<tmp>` so `kit_repo_root`
resolves to `<tmp>`. (Fixture-only paths below are written without backticks on purpose, so
this kit's own `analyze` does not list them.) Cases: (1) sound kit → exit 0, no findings,
every path `exists`; (2) a verify naming a script absent from the temp root (say
bin/missing.py) → `verify-missing-path`, exit 3; (3) a verify whose first word is
no-such-binary-xyz → `verify-missing-executable`; (4) a `Verify:` + bare-fence block →
`verify-unparseable` with the hint; (5) T2's verify names tests/test_new.py, which T1's brief
says it creates ("new " before the backticked path in the FIXTURE), and T2 depends on T1 →
state `created-by` with `by == "T1"`, exit 0; (6) a brief naming docs/nowhere.md →
`brief-missing-path`, exit 0 non-strict and 3 with `strict=True`; (7) heredoc body and `$(…)`
content are not tokenized (a verify with `python3 - <<'PY'` whose body mentions fake/path.py,
and `cd "$(git rev-parse --show-toplevel)"`, both sound); (8) `-m unittest tests.test_x` maps
to tests/test_x.py; `discover -s tests -p 'test_x.py'` maps to the same; (9) a task's own verify naming
the file its own brief says it creates is `created-by` self; (10) mutation: delete the file
from case 1 → exit flips to 3 (`verify-missing-path`); (11) the never-runs assertion above;
(12) the kit dir's bytes and `os.listdir` are unchanged after every call; (13) CLI: `--json`
parses and `exit` matches the process return; an invalid graph returns 2 before any analysis.

**Acceptance.** `python3 bin/kit_contract.py analyze --kit .claude/kits/kit-preflight` exits 0
on this kit (R8: if it does not, report the finding verbatim and stop — the brief that caused it
is a kit defect to record, not a heuristic to loosen); `analyze --kit .claude/kits/
sdd-docs-refresh` exits 3 with `verify-unparseable` and the dialect hint on every task;
`python3 bin/kit_contract.py --help` lists `analyze`; `tests/test_kit_analyze.py` is red before
(no `analyze_kit`) and green after; `tests/test_kit_contract.py` and `tests/test_kit_graph.py`
stay green; `git status --porcelain` shows only `bin/kit_contract.py` and the new test file.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_kit_analyze.py' -q && python3 -m unittest discover -s tests -p 'test_kit_contract.py' -q && python3 -m unittest discover -s tests -p 'test_kit_graph.py' -q && python3 bin/kit_contract.py analyze --kit .claude/kits/kit-preflight && git diff --quiet -- .claude/kits
```

### T5 — Every headless driver runs `analyze` before its first dispatch and fails closed
- id: T5
- title: Call exit_if_unsound_kit after roster_for_run in the four drivers, with fixture-safe tests
- status: pending
- model: sonnet
- depends: T4
- evidence: red-green

**Brief.** PLAN D5, R1. Files: `bin/claude_execute.py`, `bin/copilot_execute.py`,
`bin/codex_execute.py`, `bin/cursor_execute.py`; extend `tests/test_kit_analyze.py` (created by
T4) with a `DriverPreflightTests` class.

1. In each driver, add the re-export line beside its other `_CONTRACT.` re-exports:
   `exit_if_unsound_kit = _CONTRACT.exit_if_unsound_kit`.
2. In each driver's `cmd_run`, immediately after the `roster_for_run(...)` call (claude
   ~line 879, copilot ~1035, codex ~1435, cursor ~208 — anchors, re-grep for
   `roster_for_run(plan_text`), insert `exit_if_unsound_kit(kit, tasks)` — before any
   `--dry-run` branch, claim, preamble, or ledger open. Codex's `cmd_run` has already selected
   `task` by then; that is fine — the check is kit-wide and still precedes dispatch. Add a
   three-line comment stating PLAN D5: static, free, fail closed, no opt-out, brief-path
   findings never fail a run.
3. `tests/test_kit_analyze.py::DriverPreflightTests`: for each of the four drivers, build a
   fixture kit in a temp dir whose single pending task's verify names a missing script, and run
   the driver's `run` entry with `--dry-run` (every driver spawns nothing under it) in a
   subprocess with a temp HOME and temp `--attempt-store` where the driver accepts one (read
   each driver's `--help`; copy the invocation shape from that driver's own test file, e.g.
   `tests/test_claude_execute.py`); assert return code 3 and `verify-missing-path` in stderr,
   and that no file under the kit dir changed. Add the positive twin: the same fixture with the
   script present under the temp root returns the driver's normal dry-run code.
4. R1: run the four driver test files. A failure whose message is `verify-missing-path` or
   `verify-missing-executable` means a FIXTURE names a path it never created: fix the fixture
   (create the file under the temp root, or use a path-free command such as `true`) — never
   the heuristic. If more than five fixtures need it, stop and report with the list.

Gotcha: `tests/test_kit_contract.py::test_no_driver_redefines_a_name_the_contract_owns` — the
re-export is an assignment, not a `def`; do not define a local function.

**Acceptance.** `grep -n "exit_if_unsound_kit(kit, tasks)" bin/claude_execute.py
bin/copilot_execute.py bin/codex_execute.py bin/cursor_execute.py` shows exactly one hit per
driver, each within 12 lines after `roster_for_run(`; the new tests are red before (the drivers
dry-run successfully on an unsound kit) and green after; all four driver test files pass;
`tests/test_kit_contract.py` passes; `git status --porcelain` shows only the four drivers and
the test file (plus any fixture-only edits inside `tests/test_*_execute.py`, each named in your
report).

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_kit_analyze.py' -q && python3 -m unittest discover -s tests -p 'test_kit_contract.py' -q && python3 -m unittest discover -s tests -p 'test_claude_execute.py' -q && python3 -m unittest discover -s tests -p 'test_copilot_execute.py' -q && python3 -m unittest discover -s tests -p 'test_codex_execute.py' -q && python3 -m unittest discover -s tests -p 'test_cursor_execute.py' -q && test "$(grep -l 'exit_if_unsound_kit(kit, tasks)' bin/claude_execute.py bin/copilot_execute.py bin/codex_execute.py bin/cursor_execute.py | wc -l | tr -d ' ')" = 4
```

### T6 — Commit Phase 2 at a green boundary
- id: T6
- title: Commit analyze and the driver preflight on feat/route-experiment
- status: pending
- model: haiku
- depends: T5
- evidence: red-green

**Brief.** PLAN D15. Same procedure as T3: full suite green from the repo root (real exit
status, no pipe), `python3 bin/docs_build.py check` exit 0 (no docs changed in this phase, so
it should be a no-op — if it reports drift, stop and report), stage by name
(`bin/kit_contract.py`, the four `bin/*_execute.py`, `tests/test_kit_analyze.py`, any
`tests/test_*_execute.py` fixture edit T5 reported), never `.claude/kits/kit-preflight/` or the
kit agents, never `git add -A`, branch `feat/route-experiment`, never push. Subject e.g.
`feat(kits): analyze a kit's paths and verify commands statically before any dispatch`. Body per
the convention: why (the ledger's most frequent kinds were caught after dispatches were spent;
cite that `python3 bin/routing_scorecard.py --history` prints the current kinds — never type
counts), what proves it (`tests/test_kit_analyze.py`: the never-runs assertion, the mutation
flip, the driver fail-closed cases), and the deliberate limits (brief paths are advice unless
`--strict`; line anchors are not checked; the other verify dialect is reported, not read). End
with the mandated trailer.

**Acceptance.** As T3: subject in convention, prose body, sources clean after the commit,
branch `feat/route-experiment`, nothing pushed.

**Verify.**
```bash
test "$(git branch --show-current)" = feat/route-experiment && git log -1 --format=%s | grep -qE '^(feat|fix|docs|refactor|test|chore)\([a-z-]+\): [^A-Z].*[^.]$' && git diff --quiet -- bin tests skills docs docs-site
```

## Phase 3 — Acceptance and drift (B, machine half)

### T7 — `kit_contract.py accept`: the interactive loop's acceptance projection
- id: T7
- title: Implement accept_task over TaskRun.project with its ordering rule, refusals and tests
- status: pending
- model: sonnet
- depends: T6
- evidence: red-green

**Brief.** PLAN B1, D6, R10. Files: `bin/kit_contract.py`, new `tests/test_kit_evidence.py`.

1. `accept_task(kit_dir, task, run_id, actor="interactive", store=None, workspace=None,
   note="") -> dict` in `bin/kit_contract.py`, beside `refresh_task`. Steps, in order:
   (a) `task["status"] != "done"` → raise `ValueError("task <id> is <status>, not done; accept
   records an acceptance and there is none")`; (b) read `<kit_dir>/NOTES.md` (absent → empty)
   and `result = recorded_outcome_result(notes_text, task["id"])` (it exists at ~line 1458 —
   read it to learn its return shape); if it is not one of `pass`, `retry-pass`,
   `escalated-pass` → raise `ValueError("no passing outcome: line for <id> in NOTES.md; write
   the outcome line first — accept records what the ledger already states")`; (c)
   `workspace = Path(workspace) if workspace else _al().kit_repo_root(kit_dir)`; (d) `ledger =
   open_ledger(kit_dir, store=store)`; `lifecycle = TaskRun(ledger, run_id, task,
   workspace=workspace, actor=actor)`; `lifecycle.project("done", result=result,
   outcome_line=True, note=note)` — no `begin()`, no `end()` (D6: a projection takes no claim);
   (e) return `{"id", "artifact": ledger.latest_artifact(id), "upstream": {dep:
   ledger.latest_artifact(dep)}, "acceptance_ref": <the ref the projection wrote, read back
   from ledger.latest_acceptance(id)>, "result": result}`.
2. CLI: `accept --kit DIR --task ID --run RUN_ID [--attempt-store S] [--note TEXT]`. Exactly
   those five options; the test asserts `--artifact`, `--upstream`, `--at`, `--from-notes` are
   each rejected by argparse (exit 2). Validate `--run` against the run-id shape
   `generate_run_id` produces (`<UTC-date>-<4 hex>`; read it and reuse its regex or format).
   Print one line: `accept: <id> result=<result> artifact=<first 12 hex|unknown> upstream=
   <dep>:<first 12 hex|unknown>,…` (or `upstream=none`). `ValueError` → message on stderr,
   exit 2. `parse_tasks` + `exit_if_invalid_graph` first, as the other subcommands do.
3. Tests, new `tests/test_kit_evidence.py` (temp kit under `<tmp>/.claude/kits/fx`, a real
   `git init` in `<tmp>` with one commit so `workspace_fingerprint` returns a hex digest; temp
   `--attempt-store`): (1) a done task with an `outcome: T1 … result=pass` line → `accept`
   exits 0, `freshness` on a dependant done task with its own accepted line reads `fresh`;
   (2) mutation: append a file in `<tmp>`, re-`accept` T1 → `freshness` reads T2 `stale`;
   (3) T1 not done → exit 2 with "not done"; (4) done but no outcome line → exit 2 with "write
   the outcome line first"; (5) the four forbidden flags each exit 2; (6) the kit dir's bytes
   are unchanged after every call (NOTES.md and TASKS.md are read, never written); (7) the
   ledger file lives under the temp store, and nothing was written under `<tmp>/.claude`;
   (8) `python3 bin/kit_contract.py freshness --kit .claude/kits/sdd-docs-refresh` still prints
   `unknown` for every task with upstream (a live-tree read-only check that no backfill
   happened; it spends nothing and writes nothing).

Gotcha: `TaskRun.__init__` defaults `workspace` to `Path.cwd()`; always pass the repo root.
`recorded_outcome_result` may return something other than a bare string — read it.

**Acceptance.** `python3 bin/kit_contract.py --help` lists `accept`; the test file is red
before (no `accept_task`) and green after; `tests/test_kit_contract.py`,
`tests/test_attempt_ledger.py` pass; `git status --porcelain` shows only `bin/kit_contract.py`
and the new test file; nothing under the real data root (`python3 bin/runtime_data.py where`)
changed — do not run `accept` against any committed kit.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_kit_evidence.py' -q && python3 -m unittest discover -s tests -p 'test_kit_contract.py' -q && python3 -m unittest discover -s tests -p 'test_attempt_ledger.py' -q && python3 bin/kit_contract.py --help | grep -q 'accept' && git diff --quiet -- .claude/kits
```

### T8 — `kit_contract.py drift`: re-run finished kits' checks read-only and report drift, not failure
- id: T8
- title: Implement drift_kit with the D7 states, dedupe, criteria comparison, ledger event and tests
- status: pending
- model: opus
- depends: T7
- evidence: red-green

**Brief.** PLAN B3, D7, D8, R6, R9. Files: `bin/kit_contract.py`; extend
`tests/test_kit_evidence.py` (created by T7) with a `DriftTests` class.

1. `DRIFT_STATES = ("holds", "drifted", "unrunnable")`, `ACCEPTANCE_STATES = ("unchanged",
   "changed", "unknown")`, and `drift_kit(kit_dir, tasks, runner, store=None, workspace=None,
   run_id=None, record=True, confinement=None) -> dict` implementing D7 exactly: done tasks
   only; the static verify check from `analyze_kit` first (reuse its per-task `verify` entry —
   call `analyze_kit` once and read `result["verify"][tid]`; do not re-implement the
   heuristics) → `unrunnable` when unparseable or any executable/path is `missing`; otherwise
   run the stripped verify text through `runner(cmd) -> (rc, output)` ONCE per distinct text
   (dict keyed by the stripped text; later tasks get `shared_with`); `holds`/`drifted` by rc;
   `acceptance` from the ledger's latest acceptance `acceptance_ref` (use
   `_al().read_ref` on the stored value and compare its `sha` to
   `acceptance_identity(task)` — read both helpers; `unknown` when either side is missing);
   when `record`, `ledger.append("evidence.drift", run=run_id, task=tid, state=…, rc=…,
   acceptance=…, verify_sha=_sha-of-stripped-text, confinement=confinement,
   shared_with=[…])` — the output text is NEVER stored. Return `{"v", "kit", "confinement",
   "tasks": {tid: {...}}, "exit": 0|3}`; `exit` is 3 when any state is `drifted` or
   `unrunnable`, else 0. No call to `project_status`, `set_status`, `append_run_note`,
   `finish_task_projection`, or any write under the kit dir — the test greps the function body
   for those names and asserts none appear.
2. `render_drift(result)`: first line `drift: <kit> confinement=<value>`; one line per task
   `drift: <tid> <state> acceptance=<a> [shared-with <ids>]`; last line `drift: <n> hold, <n>
   drifted, <n> unrunnable`.
3. CLI: `drift (--kit DIR | --all) [--kits-dir .claude/kits] [--attempt-store S] [--exec-mode
   enforced|trusted-host] [--json] [--no-record]`. Runner: `_ep().verify_runner(repo_root,
   mode=args.exec_mode, on_result=cb)` where `cb` captures `result["confinement"]` (read
   `exec_policy.verify_runner`'s `on_result`); `repo_root = _al().kit_repo_root(kit)`;
   `run_id = generate_run_id()`. `--all`: every `<kits-dir>/*/TASKS.md`, one section per kit;
   a `ValueError` from `parse_tasks` (a kit in a dialect without `- status:`) prints `kit:
   <slug> unparseable -- <reason>` and continues. Return code: 0 when every kit's `exit` is 0,
   else 3 — never 1. `--kit` with an invalid graph: exit 2 via `exit_if_invalid_graph`.
4. Tests (`DriftTests`, injected runner, temp kit + temp store, same git-initialised temp root
   as T7's tests): (1) three done tasks, two sharing one verify text, runner returns rc 0 →
   every `holds`, runner called exactly twice, `shared_with` set on the second; (2) runner
   returns rc 1 for one text → that task `drifted`, exit 3; (3) a done task whose verify names
   a missing script → `unrunnable`, runner never called for it; (4) a pending task is absent
   from `tasks`; (5) acceptance: after an `accept`, `unchanged`; edit the fixture TASKS.md's
   acceptance text (in the temp kit — it is a fixture) and re-run → `changed`; with no
   acceptance recorded → `unknown`; (6) the ledger holds one `evidence.drift` event per
   checked task with no `output` key; `--no-record` writes none; (7) kit dir bytes and `git
   status --porcelain` in the temp root are unchanged after every run, and TASKS.md statuses
   are untouched; (8) the CLI never returns 1: with the runner forced to fail through an
   injected `verify_runner` factory (monkeypatch `kit_contract._ep` to return an object whose
   `verify_runner` yields a failing runner and never touches a sandbox), the process-level
   return is 3; (9) `--all` over a temp kits dir containing one sound kit and one TASKS.md in
   the `- Verify:` dialect without `- status:` lines → the second is reported `unparseable` and
   the run completes; (10) R9: `tests/test_attempt_history.py` and `tests/test_attempt_ledger.py`
   still pass with an `evidence.drift` event present in a fixture ledger (add one small case
   to `DriftTests` that runs `attempt_history`'s join over the temp store if its API allows;
   otherwise record in your report that you ran its test file).
5. Do not run `drift` against any committed kit in this task (that is T13's self-check, on the
   finished tree, under a host where `python3 bin/exec_policy.py check` exits 0).

**Acceptance.** `--help` lists `drift`; `DriftTests` red before (no `drift_kit`) and green
after; the grep-the-body test proves no status-writing helper is referenced; `tests/
test_kit_contract.py`, `tests/test_attempt_history.py`, `tests/test_attempt_ledger.py`,
`tests/test_exec_policy.py` pass; `git status --porcelain` shows only `bin/kit_contract.py` and
`tests/test_kit_evidence.py`.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_kit_evidence.py' -q && python3 -m unittest discover -s tests -p 'test_kit_contract.py' -q && python3 -m unittest discover -s tests -p 'test_attempt_history.py' -q && python3 -m unittest discover -s tests -p 'test_attempt_ledger.py' -q && python3 -m unittest discover -s tests -p 'test_exec_policy.py' -q && python3 bin/kit_contract.py --help | grep -q 'drift' && git diff --quiet -- .claude/kits
```

### T9 — Commit Phase 3 at a green boundary
- id: T9
- title: Commit accept and drift on feat/route-experiment
- status: pending
- model: haiku
- depends: T8
- evidence: red-green

**Brief.** PLAN D15. Same procedure as T3 and T6: full suite green (real exit status),
`docs_build.py check` exit 0, stage by name (`bin/kit_contract.py`,
`tests/test_kit_evidence.py`), never the kit dir or agents, never `git add -A`, branch
`feat/route-experiment`, never push. Subject e.g. `feat(kits): record interactive acceptances
and survey finished kits for drift without marking them failed`. Body: why (the interactive
loop recorded nothing, so `freshness` read every task `unknown`; nothing re-checked a kit after
it shipped), what proves it (`tests/test_kit_evidence.py`: the fresh→stale flip, the
never-1 exit, the no-status-write grep, the no-backfill flag refusals), and the deliberate
limits (`drift` reports; the operator decides what is superseded; finished kits stay
`unknown` by design). End with the mandated trailer.

**Acceptance.** As T3.

**Verify.**
```bash
test "$(git branch --show-current)" = feat/route-experiment && git log -1 --format=%s | grep -qE '^(feat|fix|docs|refactor|test|chore)\([a-z-]+\): [^A-Z].*[^.]$' && git diff --quiet -- bin tests skills docs docs-site
```

## Phase 4 — The interactive loop and the documents

### T10 — The execute skill runs `analyze` and a P0 spec review before the first dispatch
- id: T10
- title: Add the pre-dispatch analyze step and the spec-review reference to the execute skill, with a skill-text test
- status: pending
- model: opus
- depends: T9
- evidence: red-green

**Brief.** PLAN A3, A4, D4, D11, D12, R2. Files: `skills/execute/SKILL.md`, new
`skills/execute/references/spec-review.md`, new `tests/test_execute_preflight.py`, generated
`docs-site/**` via `python3 bin/docs_build.py build`.

1. `skills/execute/SKILL.md`, section "The loop", the paragraph that begins "Before the first
   dispatch, run `python3 ${CLAUDE_PLUGIN_ROOT}/bin/kit_contract.py graph …`": after the roster
   sentence, append (≤ 120 words): run `python3 ${CLAUDE_PLUGIN_ROOT}/bin/kit_contract.py
   analyze --kit .claude/kits/<slug>`; exit 3 names a verify command that cannot run or a path
   no task creates — fix TASKS.md, or record the `defect:` (with `when=pre-run`) and stop; exit
   0 may still list brief paths it could not find — read them. Then, when NOTES.md holds no
   `reviewer: P0` line yet, dispatch the spec review per `references/spec-review.md` and
   adjudicate it before step 1 of the first task. Keep every existing sentence of that
   paragraph verbatim (test-pinned; `grep -rF` before touching any line).
2. New `skills/execute/references/spec-review.md` — the whole of D4 made operational, for the
   orchestrator: when it runs (once per kit, before the first dispatch, only when no
   `reviewer: P0` line exists); who runs it (the kit's `<slug>-reviewer` agent, model opus,
   read-only tools; fall back to the Agent tool on opus when the kit has none, and say so);
   the prompt to pass VERBATIM (a fenced block: read PLAN.md's Goal/"done" and Constraints,
   GUARDRAILS.md, and every TASKS.md task's acceptance and verify; return only findings of two
   sorts — acceptance clauses that cannot all hold, across a task or between a task and a fence
   or between a verify and its acceptance; and "done" items no task's acceptance covers — each
   with file:line and the defect kind from `ledger.md`'s sanctioned list; no style remarks, no
   design opinions; count findings as distinct claims); adjudication (confirmed only when it
   produces a TASKS.md/PLAN.md edit or a stop-and-report); recording (`reviewer: P0 model=opus
   findings=<n> confirmed=<n> result=<accepted|revised|blocked>` and one `defect: <id>
   kind=<kind> when=pre-run` per confirmed defect — backtick the tokens when quoting them in
   prose); and what to do with a confirmed finding (fix TASKS.md if the fix is unambiguous,
   else stop and report to the user before any dispatch). Also state how `analyze`'s own
   findings become ledger lines: a confirmed `verify-missing-path`/`verify-missing-executable`/
   `verify-unparseable` is `kind=unrunnable-verify when=pre-run`; a confirmed
   `brief-missing-path` is `kind=unspecified-path when=pre-run`.
3. "References — read when" list: add `- references/spec-review.md — read when a kit has no
   reviewer: P0 line yet: the pre-dispatch spec review's prompt, adjudication, and recording.`
   (the test requires the literal words "read when" on the line).
4. Measure the body with the same split `tests/test_docs_skill_dispositions.py` uses and keep
   it ≤ 3200 words — move words into the reference, never raise the ceiling.
5. New `tests/test_execute_preflight.py` (style of `tests/test_architect_approval_pause.py`):
   (a) SKILL.md names `kit_contract.py analyze` between "Before the first dispatch" and "For
   each task in order"; (b) it names `references/spec-review.md` with "read when"; (c) it
   mentions `reviewer: P0`; (d) the reference exists, contains a fenced prompt, names
   `PLAN.md`, `TASKS.md`, `contradictory-acceptance`, `when=pre-run`, and the two `analyze`
   mappings above; (e) the reference does not mention `docs-site`. Do not pre-write T11's
   `accept` assertion — T11 adds it.
6. `python3 bin/docs_build.py build`; stage sources and generated pages together.

**Acceptance.** The new test is red before (no reference file) and green after;
`tests/test_skill_entrypoints.py`, `tests/test_docs_skill_dispositions.py`,
`tests/test_docs_build.py` pass; `python3 bin/docs_build.py check` exits 0; the string
`docs-site` appears in no SKILL.md or reference; `git status --porcelain` lists only
`skills/execute/SKILL.md`, the new reference, the new test, and generated `docs-site/` pages.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_execute_preflight.py' -q && python3 -m unittest discover -s tests -p 'test_skill_entrypoints.py' -q && python3 -m unittest discover -s tests -p 'test_docs_skill_dispositions.py' -q && python3 bin/docs_build.py check && test -f skills/execute/references/spec-review.md && ! grep -rq 'docs-site' skills/execute/SKILL.md skills/execute/references/spec-review.md
```

### T11 — The execute skill records each acceptance with `accept` after the outcome line
- id: T11
- title: Add the one-call accept step to step 4 of the loop, pinned by test
- status: pending
- model: sonnet
- depends: T10
- evidence: red-green

**Brief.** PLAN B2, D6, R2, R10. Files: `skills/execute/SKILL.md`, `tests/test_execute_preflight.py`
(created by T10), generated `docs-site/**`.

1. In "The loop", step 4 ("**On pass**: mark `done`, note anything learned …, and append the
   task's `outcome:` line …"): append one sentence after the outcome-line clause: then record
   the acceptance for freshness with ONE call, `python3 ${CLAUDE_PLUGIN_ROOT}/bin/kit_contract.py
   accept --kit .claude/kits/<slug> --task <id> --run <run-id>` (the same `run=` id you stamp on
   the outcome line) — it reads that line, writes the artifact versions outside the tree, and
   exits 2 with the reason if the line is missing; keep only its one output line. Keep the
   existing step-4 wording verbatim (test-pinned).
2. If the lean-driver section lists what the orchestrator touches directly, add `accept` as a
   kit-state command there in ≤ 15 words; otherwise do not.
3. `tests/test_execute_preflight.py`: add assertions that step 4 names `kit_contract.py
   accept`, that `--run` appears in that sentence, and that it appears AFTER the `outcome:`
   clause within step 4's text.
4. Re-measure the body ≤ 3200 words; `python3 bin/docs_build.py build`; stage together.

**Acceptance.** The added assertions are red before and green after; `tests/
test_skill_entrypoints.py` and `tests/test_docs_skill_dispositions.py` pass; `docs_build.py
check` exits 0; the skill's pinned sentences are unchanged (`python3 -m unittest discover -s
tests -p 'test_role_ledger.py' -q` and `-p 'test_reroute_live.py'` pass, as both read the skill
text).

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_execute_preflight.py' -q && python3 -m unittest discover -s tests -p 'test_skill_entrypoints.py' -q && python3 -m unittest discover -s tests -p 'test_docs_skill_dispositions.py' -q && python3 -m unittest discover -s tests -p 'test_role_ledger.py' -q && python3 -m unittest discover -s tests -p 'test_reroute_live.py' -q && python3 bin/docs_build.py check && grep -q 'kit_contract.py accept' skills/execute/SKILL.md
```

### T12 — Documents tell the truth about the loop: GRAPH-ENGINEERING, the guide, SPEC-DRIVEN, the command lists
- id: T12
- title: Correct the kit_verify_hook claim, update the guide's roadmap and P8 row, add the three subcommands to the docs, rebuild mirrors
- status: pending
- model: sonnet
- depends: T11
- evidence: red-green

**Brief.** PLAN C3, D8, D13, R5, R7, and the user's approved addition on
`docs/GRAPH-ENGINEERING.md`. Files: `docs/GRAPH-ENGINEERING.md`, `docs/sdd/guide.md`,
`docs/SPEC-DRIVEN.md`, `docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`, `docs/REFERENCE.md`; generated
`docs-site/**` (`docs_build.py build`), `docs/RELEASE.md`'s block only if `python3
bin/release_gate.py check` reports drift (then `build`); extend `tests/test_sdd_docs.py` with
the one assertion in step 6 ONLY if that file already has a class for Part 4 content —
otherwise add it to `tests/test_execute_preflight.py`. Do NOT edit `CLAUDE.md` (R5: it sits at
its byte ceiling).

1. `docs/GRAPH-ENGINEERING.md` ~line 42 ("Edit is how this repo's own `skills/execute/SKILL.md`
   and every driver actually flip a single `- status:` line") and the module docstring it
   paraphrases in `bin/kit_verify_hook.py` (~line 50): the skill flips status with the Edit tool
   but does NOT call `kit_verify_hook.py`'s `record`/`precheck` — only the drivers do. Reword
   the doc sentence to say exactly that, and add that since kit `kit-preflight` the interactive
   loop's per-task CLI calls are `kit_contract.py analyze` (once, pre-dispatch) and
   `kit_contract.py accept` (per accepted task); the hook itself stays unwired for interactive
   runs (a `~/.claude` settings change, out of scope). Correct the docstring's sentence the same
   way in `bin/kit_verify_hook.py` — comment text only, no code; its tests must stay green.
2. `docs/sdd/guide.md`: (a) Part 4 "Roadmap": the sentence "Each item would be its own kit,
   approved through the architect's approval pause. None is built." becomes: A, B and C were
   built together as kit `kit-preflight` (see `.claude/kits/kit-preflight/PLAN.md`); D–H are
   not built. Mark rows A, B, C in the table as built (e.g. append " — built (`kit-preflight`)"
   to the Improvement cell; the test `test_every_roadmap_item_names_its_evidence` reads
   column 3, so keep the evidence cells intact). (b) Part 2 lifecycle table, row "Analyze":
   now also `bin/kit_contract.py analyze` (paths, verify parseability and runnability, static)
   and the P0 spec review (contradictory acceptance, uncovered goals) before the first
   dispatch. (c) Principle table row P8: "After a kit ends, nothing re-checks it" becomes:
   `kit_contract.py accept` records interactive acceptances, `drift` re-runs a finished kit's
   checks read-only and reports drift; rating stays the author's call but must not claim more
   than the code does — "Partial → Strong for detection; nothing updates a spec automatically"
   is accurate. (d) The sentence in "What its own ledger says" about the interactive loop
   recording nothing: now says it records acceptances through `accept` since this kit, and
   kits finished earlier stay `unknown` by design. (e) Part 3 table: add rows for `analyze`,
   `accept`, `drift` in the style of the `kit_contract.py graph` row. (f) "Run it": add the
   three commands. Section headings byte-identical (`tests/test_sdd_docs.py`).
3. `docs/SPEC-DRIVEN.md`: after the paragraph on `graph`/`freshness`/`refresh` (~lines 91–97),
   add one paragraph naming `analyze` (static; what it checks; exit 0/3/2), `accept` (the
   interactive loop's acceptance record, outside the tree), and `drift` (read-only re-check;
   drift, not failure; `evidence.drift` event; never exit 1), each no stronger than
   `python3 bin/kit_contract.py --help` states.
4. `docs/GUIDE.md` (~lines 186–190) and `docs/HOW-IT-WORKS.md` (~198–201) command lists: add
   the three commands with one-line comments in the existing column style. `docs/REFERENCE.md`
   ~line 387 (the `bin/kit_contract.py` table row): append "pre-run `analyze`, interactive
   `accept`, read-only `drift`" to its description if the row enumerates subcommands; else
   leave it.
5. Run `python3 bin/docs_build.py build`, `python3 bin/release_gate.py check` (build only on
   drift), `python3 bin/copilot_docs.py check` (it mirrors Copilot sources you did not touch;
   if it reports drift, stop and report — do not build).
6. One test assertion: `docs/sdd/guide.md` no longer contains "None is built." and does contain
   "kit-preflight".

**Acceptance.** The six docs state only what the code does (every command named exists in
`python3 bin/kit_contract.py --help`); `docs_build.py check`, `release_gate.py check`,
`copilot_docs.py check` exit 0; `tests/test_sdd_docs.py`, `tests/test_kit_verify_hook.py`,
`tests/test_spec_driven_pitch.py`, `tests/test_docs_build.py` pass; the new assertion was red
before; no number that rots was typed (grep your diff for `[0-9]+ (kits|tasks|tests)` and `%`).

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_sdd_docs.py' -q && python3 -m unittest discover -s tests -p 'test_execute_preflight.py' -q && python3 -m unittest discover -s tests -p 'test_kit_verify_hook.py' -q && python3 -m unittest discover -s tests -p 'test_docs_build.py' -q && python3 bin/docs_build.py check && python3 bin/release_gate.py check && python3 bin/copilot_docs.py check && ! grep -q 'None is built\.' docs/sdd/guide.md && grep -q 'kit-preflight' docs/sdd/guide.md
```

### T13 — Closeout: the whole-kit done check, self-analyze, commit, self-drift
- id: T13
- title: Run the kit's own done check end to end, commit Phase 4, and survey this kit for drift
- status: pending
- model: sonnet
- depends: T12
- evidence: red-green

**Brief.** PLAN "Whole-kit done", D7, D15, R6, R8. No new files. In this order, from the repo
root, reading real exit statuses (never through a pipe):

1. `python3 -m unittest discover -s tests -q` — green, or stop and report which test and why.
2. `python3 bin/docs_build.py check && python3 bin/copilot_docs.py check && python3
   bin/release_gate.py check` — all exit 0.
3. `python3 bin/kit_contract.py analyze --kit .claude/kits/kit-preflight` — exit 0. If 3, the
   finding is a kit defect (R8): record it in your report verbatim with the task id and stop;
   do not edit TASKS.md yourself (the orchestrator records the `defect:` line and decides).
4. `python3 bin/exec_policy.py check` — exit 0 (an OS boundary exists here). If 3, stop and
   report: the self-drift cannot run `enforced` on this host and `trusted-host` is not yours
   to choose.
5. Commit Phase 4 per D15: stage by name (`skills/execute/SKILL.md`,
   `skills/execute/references/spec-review.md`, `tests/test_execute_preflight.py`,
   `docs/GRAPH-ENGINEERING.md`, `bin/kit_verify_hook.py`, `docs/sdd/guide.md`,
   `docs/SPEC-DRIVEN.md`, `docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`, `docs/REFERENCE.md`,
   `tests/test_sdd_docs.py` if T12 touched it, `docs/RELEASE.md` if regenerated, and the
   generated `docs-site/` pages). Never the kit dir or agents, never `git add -A`, branch
   `feat/route-experiment`, never push. Subject e.g. `feat(execute): check the spec before the
   first dispatch and record each acceptance, so freshness and drift work interactively`. Body
   per the convention, including what is deliberately unfinished (the hook stays unwired; the
   orchestrator's final status flip of this task is committed after this commit by the user).
6. `python3 bin/kit_contract.py drift --kit .claude/kits/kit-preflight` — every done task
   `holds` (exit 0). T13 itself is `in-progress` at this moment and is not surveyed. If any
   task reads `drifted` or `unrunnable`, report which and why; do not re-run the task.
7. Report the output tails of steps 1–6 faithfully.

**Acceptance.** Steps 1–6 all succeeded in your own run with the outputs pasted; the commit
exists on `feat/route-experiment` with sources clean; the self-drift's last line reads `drift:
<n> hold, 0 drifted, 0 unrunnable` with `confinement=` naming an OS backend, not
`trusted-host`.

**Verify.**
```bash
python3 -m unittest discover -s tests -q && python3 bin/docs_build.py check && python3 bin/copilot_docs.py check && python3 bin/release_gate.py check && python3 bin/kit_contract.py analyze --kit .claude/kits/kit-preflight && git diff --quiet -- bin tests skills docs docs-site && python3 bin/kit_contract.py drift --kit .claude/kits/kit-preflight | grep -qE 'drift: [0-9]+ hold, 0 drifted, 0 unrunnable'
```
