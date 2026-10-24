# kit-preflight — kit-scoped guardrails

These fences bind every task, verifier run, reviewer pass, test-author and red-team dispatch of
this kit. They are kit-scoped law; the repo `CLAUDE.md` Invariants stay the always-on rules and
win on any conflict. PLAN.md's "Constraints and out of scope" is the approved spec; this file is
how to honor it while working.

## Nothing in this kit executes, spends, or writes where it should not

- `analyze_kit` has NO runner parameter and imports nothing that spawns; it never calls
  `proc_runner`, `subprocess`, `exec_policy`, or a harness CLI. A test proves it by making every
  one of those raise. If you find yourself wanting to "just run the verify to see" inside
  `analyze`, that is `drift`'s job, not `analyze`'s.
- `drift` runs verify commands ONLY through `exec_policy.verify_runner` (`enforced` default;
  `trusted-host` named in the report's first line). It never calls `project_status`,
  `set_status`, `append_run_note`, `finish_task_projection`, or writes under a kit dir; its one
  write is the `evidence.drift` ledger event outside the tree, with no output text in it.
- `accept` takes no claim, writes nothing in the tree, and records only what the current tree
  and the kit's own `outcome:` line already say. There is no `--artifact`, `--upstream`,
  `--at`, or `--from-notes` flag, and none may be added: a stored record is never backdated or
  reconstructed from prose. Kits finished before this kit stay `unknown` in `freshness` —
  that is correct; never "fix" it.
- Never invoke the real `claude`/`codex`/`copilot`/`agent`/`gh` CLI from any task, test, or
  verify command — `--dry-run` is the only sanctioned driver smoke and spawns nothing. Never
  read or write `~/.claude`, `~/.codex`, `~/.copilot`, or the real attempts store
  (`python3 bin/runtime_data.py where`); every test uses a temp fixture kit under
  `<tmp>/.claude/kits/<slug>` and a temp `--attempt-store`. Do not run `accept` or `drift`
  against any committed kit except T13's self-drift on the finished tree.

## One contract, one home

- New Python goes into `bin/kit_contract.py` (analyze/accept/drift) or
  `bin/routing_scorecard.py` (the vocabulary) and is RE-EXPORTED by drivers
  (`name = _CONTRACT.name`), never defined in a driver. `tests/test_kit_contract.py` fails on a
  redefinition or a shared body; do not edit that test to pass.
- The defect fold is a read-time view. `parse_defects` keeps its grammar and event shape
  (`{"task","kind"}`, plus `when` only when the pair is present); canonicalization is
  `canonical_defect_kind`, used by BOTH the scorecard aggregate and `lessons_promote`. No
  committed NOTES.md is ever edited — `git diff --quiet -- .claude/kits` is in verify commands
  for a reason. `verifier-destructive-restore` is excluded, never folded.
- D3's heuristics are the specification for `analyze`. Where a fixture or a committed kit
  trips them, fix the fixture or record the kit's defect; never loosen a rule to make a kit
  pass, and never widen `_extract_verify` (the drivers execute what it returns).
- No new task field, no new PLAN.md line family, no new roster token. `reviewer: P0` is an
  existing family with a new phase label; `when=pre-run` is an optional pair on an existing
  line; `evidence.drift` is a ledger event kind, not a NOTES.md line.

## Skills are runtime behavior, and much of their text is test-pinned

- Additive-first. Before deleting or rewording ANY existing line of `skills/execute/SKILL.md`,
  `skills/execute/references/ledger.md`, or `skills/architect/references/routing-evidence.md`,
  run `grep -rF '<a distinctive 6+ word phrase of it>' tests/`. A hit means keep it verbatim.
  Never edit an asserting test to license a skill edit.
- `skills/execute/SKILL.md` stays ≤ 3200 words of body (`tests/test_docs_skill_dispositions.py`);
  detail belongs in `references/spec-review.md`. `skills/architect/SKILL.md` is NOT edited by
  this kit (only its `references/routing-evidence.md` is). The string `docs-site` never appears
  in a SKILL.md or a reference. No model id, price, ratio, date, or count that rots is typed into
  a skill, reference, agent, or doc — name the command that prints it.
- The architect and execute skills share one kit contract (layout, task fields, status
  vocabulary, phase headings, `depends:`/`independent:`, model-field override). Nothing in this
  kit changes it; if an edit seems to need to, stop and report.

## Generated content is rebuilt, never edited

- `docs-site/**` only via `python3 bin/docs_build.py build` (run it in the same task as any
  edit under `skills/` or `docs/*.md`; stage sources and output together); the marked block of
  `docs/RELEASE.md` only via `python3 bin/release_gate.py build`, and only when `check` reports
  drift; `copilot-docs/**` only via `bin/copilot_docs.py build` — this kit touches no Copilot
  source, so if its `check` reports drift, stop and report rather than build.
- `CLAUDE.md` is at its 16000-byte ceiling and is not edited in this kit. Command lists live in
  `docs/GUIDE.md` and `docs/HOW-IT-WORKS.md`.
- Nothing under `copilot/`, `codex/`, `cursor/`, `primitives/`, `data/`, `.github/`, or
  `SECURITY.md` changes.

## Proving and reporting

- Every task's verify command runs from the repo root, unpiped where the exit status matters;
  tests load only through `python3 -m unittest discover -s tests -p '<file>.py'`.
- Red-green is real: run the task's verify BEFORE the work and say in your report that it
  failed and why. A check that already passed is a `tautological-verify` defect to record, not
  a convenience.
- Proving a guard fires: never mutate a tracked file in place. Copy to a temp dir and mutate the
  copy, or use the test file's own negative fixture. If the tree is touched anyway, restore it
  byte-for-byte and say so. Close every report with `git status --porcelain`.
- Commits happen only in T3, T6, T9, and T13, on `feat/route-experiment`, staged by name, in the
  user's convention with the session's mandated trailer; never `main`, never push, never
  `git add -A`, never the kit dir or the kit agents (the orchestrator commits kit state).
