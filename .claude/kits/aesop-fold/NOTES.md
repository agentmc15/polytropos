# aesop-fold — execution notes

## Run baseline (recorded before the first dispatch — PLAN R1 / GUARDRAILS)

- Suite: `python3 -m unittest discover -s tests` -> **Ran 3034 tests in 134.742s - OK (skipped=2)**.
  Fully clean on this run: zero real `FAIL:`/`ERROR:` lines. Strings in the output that resemble
  failures (`FAILED next_day`, the `kit-verify-hook` advisory, argparse usage text) are fixture
  output from tests exercising error paths, not suite failures. "Green" for this kit = no NEW
  failure or error against this 3034/OK baseline.
- Interpreter: Python 3.12.7 - satisfies the 3.11 floor (PLAN D2).
- aesop `git status --porcelain`: empty (clean). Kit-pinned aesop HEAD
  `9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8`.
- Dials read at Setup: autonomy advisory; budget max-dispatches=24 max-escalations=2
  max-consults=2; roles test-author.

### Divergence from PLAN R1 - the working tree is CLEAN

polytropos `git status --porcelain` at run start showed ONLY the untracked kit artifacts
(`.claude/kits/aesop-fold/` and the four `.claude/agents/aesop-fold-*.md`). PLAN R1 describes
uncommitted modifications to `README.md`, `SETUP.md`, `bin/harness_select.py`,
`bin/harness_update.py`, `codex/AGENTS.md`, `docs/CODEX-HARNESS.md`, two `docs-site/` Codex
pages and two Codex tests. **None of those are modified now** - the user confirmed they committed that work in Codex
between architect time and run start, so R1's snapshot is simply superseded, not lost work.
R1's tripwire still applies and
simply finds nothing; briefs that anticipate a dirty `SETUP.md` or `README.md` (T2 notably)
should proceed normally and report the file as clean. Not recorded as an architect defect: R1 is
an explicitly time-stamped observation ("at architect time"), not a false claim about now.

## Task log

### T2 — Python floor 3.8 -> 3.11 (sonnet)

Orchestrator-run verify: PASS (exit 0). `SETUP.md` diff is exactly the pinned row; no other line
changed. Full suite 3038 tests OK (skipped=2) = baseline 3034 + 4 new. aesop tree clean.
Learning for later tasks: `bin/harness_select.py`'s `try: import tomllib / except ImportError`
fallback is now dead code under the 3.11 floor - left in place deliberately (out of scope,
GUARDRAILS); do not "tidy" it in a later task. New code imports `tomllib` unconditionally.
agent: T2 id=a6a01294b86b1142b role=implementer model=sonnet

### T1 — independent re-verification of the evaluation table (opus)

Orchestrator-run verify: PASS (exit 0). 19 sections, 19 verdict lines, Summary present, aesop
clean. Observed aesop HEAD matched the kit-pinned SHA exactly, so the table was checked against
the same tree the architect read. All 29 cited `wc -l` counts matched with delta 0; the vendored
schema sha256 matched the pin byte-for-byte.

Result: 17 confirmed / 2 contradicted (E5, E8). Both contradictions are errors in the table's
SOURCE-CITATION column, not in the verdicts - E5's *fold now* and E8's *drop* both still follow
from the evidence. Adjudicated as real (each produced a correction in EVALUATION.md):

- E5: PLAN cites `compile --verbose` for the native/fallback capability listing. That path
  iterates `capabilities().fallback` only; the real listing is `doctor --matrix`
  (`doctor.ts:180-186`). Downstream effect - CORRECTED by the Phase 1 review; my first statement
  of it was wrong. `plan` is a port of NEITHER command. Modeling it on `doctor --matrix` would
  BREAK D7: `doctor.ts:181` maps over `manifest.harnesses` and reports only DECLARED harnesses,
  while `plan ... --harness cursor` must work on a manifest declaring only copilot. `plan` renders
  `primitives/harness-matrix.json` and its shape is a superset of doctor's. T5's brief amended.
- E8: PLAN enumerates four doctor dynamic checks; two do not exist. There is no MCP handshake
  (`doctor.ts:109` defers it to "Phase 5"; it is a `command -v` PATH lookup) and no
  harness-version freshness check at all.

defect: - kind=stale-pin
defect: - kind=stale-plan-decision

One `note:` dissent recorded at E19: its "polytropos state" cell names `bin/primitives.py`, which
does not exist at HEAD - it is the artifact this kit builds. Confirmed rather than contradicted
because E4/E5 make the intent unambiguous; flagged for anyone scanning that column alone.

FINDING ABOUT AESOP, surfaced for the keep/kill decision (not this kit's work): aesop's own
`docs/03-harness-matrix.md` promises a 90-day harness-version freshness check that `doctor.ts`
never implements. A doc-vs-code gap in aesop itself.

Orchestrator note on concurrency (not a defect in either task): T1 correctly reported that
`SETUP.md` and `tests/test_python_floor.py` appeared in the tree mid-run and correctly declined
to claim them, verifying by mtime and content that they were T2's. My "tree is CLEAN" briefing
line was true at run start and became stale while both ran. TASKS.md's parallel-safety claim
held - the two tasks' file sets were genuinely disjoint. Future parallel dispatches should say
"clean apart from the kit artifacts AND whatever your sibling task is writing".

agent: T1 id=aaa203e70ce6a4b8d role=implementer model=opus

T1 verifier (fresh context, adversarial): **PASS, zero findings** - an honest clean verdict, not
a rubber stamp. It independently re-read `compile.ts:110-114` (confirmed fallback-only) and all
205 lines of `doctor.ts` (confirmed no MCP handshake, no freshness check anywhere), so BOTH
contradictions are themselves correct. It also re-ran `wc -l` on all ~30 cited aesop files - every
count matches with delta 0 - and spot-verified E1, E11, E12, E13, E17 against source. Header SHAs
for both repos verified against live `rev-parse`. No fabricated evidence found in any section.

agent: T1 id=ab0a0c2b5446b9acf role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T1 model=opus attempts=1 result=pass review=clean run=2026-09-04-c3f1

T2 test-author (declared role, hook: after implementer, before verifier): **zero defects found**,
but the dispatch was not empty - it added `tests/test_python_floor_adversarial.py` (13 tests) and
MUTATION-VALIDATED each one: it broke the exclusion list, one regex branch, and the self-exclusion
check in temp copies and confirmed the matching test caught each regression. So the "no gap" result
is evidence, not a shrug. Notably it proved the sweep's twelve roots are each walked recursively
(planting two levels deep under all 9 dir roots + the 3 file roots), that all four regex
alternatives fire independently, and that the self-exclusion is by PATH rather than by the
original's careful escaping.
Self-referential hazard it handled correctly: its own file lives under the swept `tests/` root, so
it builds every planted stale-floor string by runtime concatenation - no contiguous literal in its
source - and verified the real regex finds zero matches in its own text.
Suite baseline moves 3038 -> **3051** (13 new). Still OK (skipped=2).

agent: T2 id=ac354b84e78fe13db role=test-author model=sonnet findings=0 confirmed=0 marginal=0 result=accepted

T2 verifier (fresh context, adversarial): **PASS, zero findings.** `git diff --numstat -- SETUP.md`
= `1 1` (exactly one line in, one out) - the acceptance criterion most likely to be quietly
violated held. It proved the sweep is a real tripwire by its OWN mutation: planted `Python 3.8`
four dirs deep under `docs/` and `3.8+` five dirs deep under `skills/`, both caught, temp dirs
removed. So the real tree's pass is genuine, not a silent no-op walk. It also empirically ran the
real `STALE_FLOOR_RE` against the adversarial file's source: 0 matches, confirming the runtime
concatenation works rather than taking the docstring's word. Full suite 3051 OK (skipped=2).

agent: T2 id=aa037820b6df71496 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T2 model=sonnet attempts=1 result=pass review=clean run=2026-09-04-c3f1

## Phase 1 review (opus) — ACCEPTED with one pre-Phase-2 fix, now applied

Reviewer raised 2 findings; 1 confirmed and acted on, 1 acknowledged with no action.

- **F1 (CONFIRMED, fixed).** `TASKS.md` T5's *Why* inherited PLAN E5's proven-stale
  `compile --verbose` citation, and my own NOTES consequence statement was ALSO wrong in the
  direction that matters. `doctor.ts:181` maps over `manifest.harnesses`, so `doctor --matrix`
  reports only DECLARED harnesses; an implementer told to "model plan on doctor's matrix output"
  would build an engine that cannot preview Cursor - breaking the one thing D7 exists for, and a
  definition-of-done line. Correct statement: `plan` ports NEITHER command; it renders
  `primitives/harness-matrix.json` and is a superset of doctor's shape. Both T5's brief and the
  NOTES line are amended. Reviewer confirmed the SPEC (harness-selection rule, nine-entry output)
  was already right - only the rationale was stale, so no Phase 2 task would have built the wrong
  engine, but a reader resolving the contradiction toward the *Why* could have.
- **F2 (endorsement, not a defect).** Leaving PLAN's Evaluation table uncorrected is the RIGHT
  call: D10 designs the table as the architect's CLAIM and EVALUATION.md as the RECORD, and
  rewriting the cells would erase the only visible product of the maker/checker split. No action.
- **F3 (acknowledged, NOT confirmed - no artifact).** E19 is arguably `contradicted` rather than
  `confirmed`+note, since its polytropos-state cell names `bin/primitives.py` which does not exist
  at HEAD. Headline would read 16/3 instead of 17/2. Consequence zero (E19's verdict is *drop*,
  nothing is built from it) and T1 disclosed the gap openly. Reviewer explicitly does not
  recommend reopening. Recorded for the user's awareness, not acted on.

Reviewer also verified Phase 2's foundation unprompted: all six aesop `capabilities()` bodies
match T3's pinned bullets exactly, `HookSpec.event` matches T3's enum, `SECRET_PATTERNS`
(`doctor.ts:45-50`) matches T4's four regexes verbatim, and every schema path T4 reads resolves.
No stale pin waiting in Phase 2 beyond the one fixed above.

defect: T5 kind=stale-pin
reviewer: P1 model=opus findings=2 confirmed=1 result=accepted

### T3 — primitive model + harness matrix + vendored schema (sonnet)

Orchestrator-run verify: PASS (exit 0). Schema copy confirmed byte-identical to aesop's by
`diff -q`, not just by hash. 18 new structural tests; suite 3051 -> **3069**, OK (skipped=2).

Implementer did the source re-verification the dispatch demanded: opened `src/types.ts` and all
six `src/emitters/*.ts` plus `shared.ts` and `compile.ts`, and confirmed every `capabilities()`
body matches the brief's six bullets exactly - **no discrepancy**. So PLAN's capability bullets
are sound (unlike its E5 citation), independently confirmed twice now (Phase 1 reviewer + here).

Self-caught violation worth recording as a POSITIVE: while transcribing `notes` it initially
carried emitter comment dates ("(May 2026)", "pinned July 2026") into `harness-matrix.json`,
which breaks the acceptance line "no dates other than the provenance note". It caught this in its
own hygiene sweep and rewrote the three values to keep substance without dates. Not a defect -
the implementer's own check worked.

Cursor column (the deliverable for the later Cursor kit) reads: goal_mode ralph; native
instructions/mcp/state; fallback skill/agent/command/hook/permissions/loop; targets pinned
(`.cursor/rules/skill-<name>.mdc`, `.aesop/roles/<name>.md`, `.aesop/prompts/<name>.md`,
`.cursor/mcp.json`); hook and permissions emit nothing (`target: []`).

agent: T3 id=ad2c252145fec6f04 role=implementer model=sonnet

T3 test-author: **2 findings, both confirmed, both marginal** - the roster's first real catch.

- **F1 (confirmed, marginal, closed).** T3's acceptance line "no prices, model ids, dates, or home
  paths anywhere" was **genuinely unenforced**. Proven by mutation: planting a home path, `$12.50`,
  `claude-3-5-sonnet`, and `2025-01-15` into temp copies of `model.json`/`harness-matrix.json` left
  the ENTIRE 3069-test suite green. Now closed by `DataHygieneTests` +
  `MutationProbeConfirmsHygieneGapTests` (the latter is a permanent record that the gap was real,
  not hypothetical). It reused this repo's OWN established patterns
  (`test_docs_fragment_content.py`'s `_DOLLAR_RE`/`_VERSIONED_MODEL_RE`,
  `test_docs_skill_dispositions.py`'s ISO-date regex) instead of inventing new ones. This matters
  because the T3 implementer caught itself committing exactly this violation by hand and fixed it -
  with no test, the next edit reintroduces it silently.
- **F2 (confirmed, marginal).** ARCHITECT DEFECT: the same acceptance line is UNSATISFIABLE as
  literally written. It says "anywhere in the three files", but the third file
  (`primitives/aesop.schema.v1.json`) is a byte-identical vendored copy that already contains an
  ISO date in its own content, and D5 forbids editing it. Correct resolution, taken: scope hygiene
  enforcement to the two files this kit AUTHORS, and document the contradiction rather than
  silently excluding the schema. Escalated rather than resolved silently - correct behavior.

Probes 1-6 all confirmed the existing pins are real tripwires (four cell flips across four
harnesses incl. a goal_mode flip; the named cursor test isolates correctly and does NOT over-fire
on a non-cursor change; sha256 catches a one-byte schema edit; missing cell / 7th harness / dropped
primitive each caught; bogus enum tokens caught; absolute path in `target` caught).

Suite 3069 -> **3092** (23 new). Still OK (skipped=2).

defect: T3 kind=contradictory-acceptance
agent: T3 id=ad3052e1b5a4fbf02 role=test-author model=sonnet findings=2 confirmed=2 marginal=2 result=accepted

T3 verifier: **PASS, zero defects.** It re-derived `capabilities()` from all six emitters itself
(not the brief, not the matrix) - every cell matches, and every fallback `notes` string is a
BYTE-VERBATIM transcription of the emitter's own fallback literal (spot-proved character-for-
character on `copilot.ts:75`). It also went beyond the two columns asked for and traced EVERY
target path in all six harnesses to a real `path:` string or a confirmed core-emitted file
(`AGENTS.md` at `compile.ts:92`, `.aesop/goals/*` at `compile.ts:98-99`). Schema byte-identical by
`diff` (exit 0), not just by hash. The `authored_as` inline/referenced split confirmed
source-grounded: inline types are embedded data in `Manifest`, referenced ones are
`PrimitiveRef`/`AgentRef` (name + overrides only) - a defensible split, not a guess. Defaults
verified against `registry.ts:137-165`. Suite 3092 OK.
Its one non-defect observation: `source.verified` = "aesop's own pin: June-July 2026" is a coarse
date outside the ISO regex, but it is lifted verbatim from the brief's own JSON template and sits
inside the `source` provenance block the acceptance line exempts. Agreed - not a defect.

agent: T3 id=a37a36211f9dcf446 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T3 model=sonnet attempts=1 result=pass review=clean run=2026-09-04-c3f1

Warm cluster note: T4 and T5 are served by ONE continued implementer (same primary files
`bin/primitives.py` + `tests/test_primitives.py`, same sonnet pin) - both tasks' agent lines carry
the SAME agent id by design.

### Pre-dispatch pin audit — T6..T9 (orchestrator, while T4 ran)

Two stale pins had already cost this kit (PLAN E5 citation; T5's inherited *Why*), so every
checkable anchor in the remaining briefs was verified against repo reality BEFORE dispatch rather
than discovered mid-task. **All hold - no third stale pin.**

- T6: `_extract_yaml_list_block` present (5 refs) and used ONLY in `tests/test_copilot_bundle.py`,
  so deleting it is safe; 86 `def test_` methods today (acceptance needs >= 87 after);
  `copilot/aesop.yaml` really carries 12 agents + 13 skills as the brief states.
- T7: every rename anchor exists verbatim - `docs/COPILOT-PARITY.md` has exactly the 2 occurrences
  claimed; `docs/COPILOT-HARNESS.md:16` is the pinned bullet; `docs/HOW-IT-WORKS.md:89` is the tree
  line; `copilot-docs/manifest.json:20` is the bundle entry.
- T8: `mkdocs.yml:112-113` has `Deep dives:` with `deep-dives/index.md` first, as the brief assumes;
  both cross-referenced docs (`ROUTING-HISTORY.md`, `ROLE-EXPERIMENT.md`) exist; the
  `spec_from_file_location` `_load` idiom exists in `tests/test_harness_select.py`.
  Checked one risk the brief raises implicitly: nav ordering is NOT test-enforced
  (`tests/test_docs_site.py` compares nav tokens as a SET, line 139; its `sorted()` calls are for
  error messages and file iteration only). So the brief's "AI sorts first" claim is cosmetic - it
  is true under ASCII but false case-insensitively, and either way nothing fails on it.
- T9: `CLAUDE.md` is **exactly 15568 bytes**, matching PLAN R5's figure to the byte, and the anchor
  line `python3 bin/docs_build.py check` is at line 103. The pinned insert is 160 bytes ->
  **15728 of 16000, 272 bytes headroom**. Safe.

### T4 — bin/primitives.py: tomllib loader + schema-driven validator (sonnet, warm cluster head)

Orchestrator-run verify: PASS (exit 0). Engine exercised live: `model` prints all nine primitives
with full semantics; `check tests/fixtures/primitives/full.toml` -> `ok:` exit 0. 63 new tests;
suite -> **3155**, OK (skipped=2).

**ARCHITECT DEFECT the implementer caught, independently reproduced by me.** The brief's
illustrative TOML dialect ordering (`[project]`, `[project.commands]`, `[project.models.judge]`,
THEN `harnesses = [...]`, `[pathway]`, `registries = [...]`) is invalid: in TOML a bare `key =
value` after any `[table]` header nests under that table. Proof:
`[project]\nname="x"\nharnesses=["copilot"]` parses to `{'project': {'name':'x', 'harnesses':
[...]}}` - `harnesses` silently lands INSIDE project. Critically this raises NO error (unlike R2's
"cannot declare twice"), so it is a silent-corruption risk, not a syntax error: a manifest written
to the brief's order would parse clean and validate wrong. Resolved correctly by placing
`version`, `harnesses`, `registries` as bare ROOT keys before the first `[table]` header, in every
fixture and in the module docstring. R2's own separate guidance (plain `[primitives]` keys before
`[primitives.*]` subtables) was correct and is respected. This ordering rule is now load-bearing
for T6, which converts the real manifest - the corrected rule is documented in the module docstring
where T6 will read it.

Note for the verifier to judge: module is **542 lines against the "~450" soft target** (+20%).
Implementer justified it (seven independently-coded rule categories; it already collapsed 12
schema accessors into one `_schema_get` walker and trimmed defensive branches). Acceptance says
"~450", explicitly approximate.
Design fact for T5: all enums/patterns flow through ONE chokepoint `_schema_get(schema, *path)` -
nothing retyped as a Python literal, proven by a test that removes `cursor` from a temp copy of the
schema's harness enum and confirms the finding follows.

defect: T4 kind=stale-plan-decision
agent: T4 id=acf3fd94560a5c648 role=implementer model=sonnet

T4 test-author: **2 findings, suite RED (2 failures) - the roster's first genuine BUG catch.**

- **F1 (CONFIRMED, real defect, independently reproduced by me).** `unsafe-name` co-fires on an
  EMPTY `project.name`. Rule 6 is scoped to names containing `/ \ .. NUL` or equal to `.`; an empty
  string matches none. But `validate()` returns BOTH `schema` ("missing or empty") and
  `unsafe-name` ("not a safe name: ''"). Root cause, confirmed at my end:
  `os.path.normpath("") == "."` in Python, so a normalize-then-compare-to-"." safety check
  misclassifies empty as unsafe. One defect reporting as two unrelated findings - exactly the
  cross-firing the dispatch asked it to probe, in the mirror direction. -> RETRY with evidence.
- **F2 (raised earlier by the implementer itself, so NOT marginal).** 542 lines vs the `~450`
  acceptance target; the test-author encoded a hard <=500 assertion against a soft "~" target.
  Orchestrator adjudication: attempt an honest trim; if the module cannot get under 500 without
  hurting correctness or readability, align the TEST threshold to reality with a recorded reason -
  a hard assertion on an explicitly approximate target is the wrong instrument, but deleting a
  failing test to go green is not acceptable either.

Verified-correct (not findings), each by real mutation rather than by reading the code: enums
genuinely read from the vendored schema (removed `cursor` / added a bogus tier in a temp copy;
behavior flipped BOTH ways); `stops` never silently defaulted (all 10 sub-cases return exactly
{stops}, and `validate()` does not inject 40/3/25 into the manifest); exit codes 0/1/2 distinct
with argparse's native 2 correctly remapped to 1; `--json` always exactly {manifest, ok, findings};
`env-value`/`secret` near-misses behave (`API_KEY` silent, `API_KEY=` and `${API_KEY}` fire;
`${VAR}` correctly does NOT trip the secret lookahead); output byte-stable across runs.

agent: T4 id=ae80ba7f3c09a0280 role=test-author model=sonnet

T4 RETRY (same warm agent): both failures resolved, suite back to **3243, 0 failures**.

- F1 fixed at the real root cause, which was NOT my hypothesis. I guessed
  `os.path.normpath("") == "."`; the module never calls `normpath`. Actual cause: `_is_safe_name`
  listed `""` alongside `"."` in its disallowed tuple, so emptiness was judged by rule 6's code
  path when it is rule 1's job. Fix removes `""` from that set. Because `_check_unsafe_names` is
  the single call site for all six name types plus `project.name`, the one fix applies everywhere -
  no special-casing, as instructed. Orchestrator re-verified the neighbours, not just the reported
  case: empty -> [schema] only; `"."`, `"a/b"`, `".."` -> [unsafe-name] each, still caught.
  LESSON: my confident root-cause attribution was wrong while the symptom description was right.
  Hand implementers the EVIDENCE and let them find the cause; a stated mechanism can mislead.
- F2: honest trim first (4 genuine dedups - merged the near-identical primitive/agent ref-list
  checkers, factored a twice-repeated positive-int guard, unified three name loops into one,
  hoisted duplicate `--json` registration), **542 -> 529**. Branch 3 then applied: threshold moved
  500 -> 540 with a comment recording that `~450` is explicitly approximate, what was deduped, and
  the final count. No test deleted or skipped.

agent: T4 id=ae80ba7f3c09a0280 role=test-author model=sonnet findings=2 confirmed=2 marginal=1 result=accepted

T4 verifier: **PASS, zero defects**, and it RULED on the threshold question rather than only
measuring it. It read all four dedups in place and confirmed they are real multi-site
consolidations (`_check_ref_list` backs 4 call sites via an `_agent_enum_findings` callback;
`_is_positive_int` is loop-driven; `_check_unsafe_names` is one loop over six keys; `build_parser`
hoists `--json` over three subparsers). It actively looked for gaming - no semicolon-joined
statements, longest lines normal descriptive code, ~12% blank-line ratio, docstring intact at 31
substantive lines - and noted the new threshold (540) sits 11 lines ABOVE the measured 529 rather
than pinned tight. **Ruling: legitimate engineering correcting an overly strict self-imposed
assertion** (the 500 was the test-author's own invention, never in the brief). Nothing deleted or
skipped. I accept this ruling.
Regression probes: 20 fresh self-built mutations across ALL seven name sites - `unsafe-name` fires
20/20. Correctly observed that on schema-pattern-constrained sites a bare `/` legitimately
co-fires `schema` too (the pattern already forbids it) - expected double coverage, not a bug.
The boolean trap holds: `max_iterations = true` / `no_progress_after = true` still yield
[stops], because `_is_positive_int` excludes `bool` before the `int` check
(`isinstance(True, int)` is True in Python). All 10 stops sub-cases pass; nothing defaulted.
Enums re-proved live by temp-copy schema mutation. Fence sweep clean: no cursor dir, no TOML
writer (`.dump`/`open(...,"w")` absent - read-only as designed), no pricing reference.
Suite 3243 OK (skipped=2).

agent: T4 id=a904b2d72b5a3a291 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T4 model=sonnet attempts=2 result=retry-pass review=revised run=2026-09-04-c3f1

### T5 — `plan` subcommand + `matrix --markdown` (sonnet, warm cluster tail)

Orchestrator-run verify: PASS (exit 0). Suite 3243 -> **3257** (+14). Module 529 -> **640 lines**,
size assertion raised 540 -> 660 with the comment extended (sanctioned in the dispatch; the T4
verifier already ruled this instrument legitimate).

**ARCHITECT DEFECT, confirmed by me.** The brief's illustrative markdown fence shows an UNSPACED
separator `|---|---|`, but its own verify command asserts `grep -c '^| '` equals 11. An unspaced
separator row starts `|-`, not `| `, so the brief's own pinned format fails the brief's own verify
command (proved: a 3-line sample with an unspaced separator matches only 2). The implementer used
the spaced form `| --- | --- |`, which satisfies the machine check and renders identically in GFM.
Correct resolution, and it reported the deviation rather than hiding it.

Design facts for T8 (which embeds this output and drift-tests it):
- `render_matrix_markdown(matrix) -> str` is a top-level importable PURE function, as T8's brief
  requires ("calls the pure function, not the CLI"). Column order and the goal-mode line are both
  derived live from `matrix["harnesses"]` key order, never hardcoded.
- T8 must embed the SPACED separator form byte-for-byte, since the drift test compares to this
  renderer's output.
- The markdown test pins against `_reference_markdown_table`, a second independently-written
  renderer (different loop structure, no call into the real one), so a shared bug cannot pass.

`plan` honors D7: it resolves `--harness` from the MATRIX, not from `manifest["harnesses"]`, so
`plan copilot/aesop.toml --harness cursor` works on a manifest declaring only copilot. It runs
`validate()` first and a lone `secret` finding still blocks with exit 2 and no plan output.

defect: T5 kind=contradictory-acceptance
agent: T5 id=acf3fd94560a5c648 role=implementer model=sonnet

### Phase-boundary hold + T6 input pre-check (orchestrator)

Holding at the Phase 2/3 boundary deliberately. T6 is technically unblocked (`depends: T4`, done),
but the loop reviews each phase against PLAN.md BEFORE the next opens; crossing early is how drift
compounds. Phase 3 waits for T5's verifier and the P2 review.

Pre-checked T6's inputs while T5's test-author ran:
- `bin/primitives.py`'s docstring DOES carry the corrected TOML ordering rule, explicitly labelled
  "also the T6 conversion target" - bare `version`/`harnesses`/`registries` before the first
  `[table]` header. It adds a constraint I had not recorded: **a table cannot be reopened, so a
  non-empty `mcp`/`loops` is populated only via its array-of-tables form.**
  **CORRECTED by the Phase 2 review — this line was wrong.** `copilot/aesop.yaml` has NO `mcp`
  key and NO `loops` key at all; they are ABSENT, not empty arrays. A 1:1 conversion writes
  NEITHER, so the array-of-tables constraint is moot for T6. My error was carried into the T6
  briefing and is now fixed in the brief itself. (Third time I have stated an unverified
  specific as fact in a dispatch — see also the `normpath` root-cause guess on T4 and the
  phantom permissions table on T5.)
- The doctrine sentence T6's verify greps for is still present in `copilot/aesop.yaml` (2
  occurrences: the instruction block and the invariants list).
- Engine already validates an aesop-shaped manifest end to end: `check
  tests/fixtures/primitives/aesop_self.toml` -> `ok:` exit 0.
- **D7 proven live**, not just tested: `plan tests/fixtures/primitives/minimal.toml --harness
  cursor` returns a full nine-entry cursor plan from a manifest that does not declare cursor.
  The `declared` x `support` cross is the Cursor-cost answer: declared+fallback = work a port must
  do; "—"+fallback = work skippable because the primitive is unused.

T5 test-author: **0 implementation defects**, 33 tests added, suite 3257 -> **3290** OK.

The probe that mattered came back correct: `_is_declared` uses `primitives.get(key)` TRUTHINESS,
not `key in primitives`. Its own words - "an `in`-based implementation would have failed my
empty-vs-absent pair". That distinction (`skills = []` present-but-empty vs no `skills` key) is
where a plausible implementation silently diverges, and both readings pass a naive test. It also
proved `render_matrix_markdown` reads ONLY its argument by feeding it a fabricated matrix with a
fake harness id and reversed primitive order, and proved the goal-mode line is derived by mutating
goal_mode / a cell's support / harness key order in memory and watching the output follow.
D7 re-proven independently: it built its OWN copilot-only fixture and confirmed `--harness cursor`
never falls back to `manifest["harnesses"]`, while the `None` branch still does.
Validate-first gate confirmed both ways: a secret-only AND a verify-loop-only fixture each exit 2
with ZERO `##` plan output (not "findings then plan anyway").
`check` regression surface after T5's refactor is intact: 0/1/2 exit codes, `error:` prefix,
`--json` exactly three keys on both clean and dirty manifests.

It independently surfaced the markdown separator contradiction already recorded above (the brief's
illustrative `|---|` vs its own `grep -c '^| '` = 11). Not marginal - the implementer raised it
first - but it resolved it the same way and left a comment so a future reader is not confused by
the mismatch between the brief's two halves. Both of its own false starts were self-inflicted TOML
ordering mistakes (bare key after a table header), caught before any assertion was weakened - the
very trap T4's docstring now documents for T6.

agent: T5 id=a898d090ffda0add5 role=test-author model=sonnet findings=1 confirmed=1 marginal=0 result=accepted

T5 verifier: **PASS**, 1 real finding (non-blocking), plus it caught an error in MY brief.

- **F1 (CONFIRMED, marginal, NOT yet fixed - referred to the P2 reviewer).** `plan --json` on an
  INVALID manifest prints plain-text finding lines, not JSON, while `check --json` stays
  JSON-shaped (`{"manifest","ok":false,"findings":[...]}`) on the same input. Reproduced by me
  verbatim. It is not malformed JSON - it is no JSON at all, so a consumer parsing `plan --json`
  breaks on exactly the input it most needs to handle. Outside T5's stated acceptance (the brief
  says only "findings -> print them and exit 2", format unspecified), and no test covers it.
  Referred to the Phase 2 review as an explicit decision rather than fixed unilaterally: fixing is
  small but is scope the task did not ask for.
- **Ruling on the 540->660 raise: justified, no padding.** It regex-scanned every `def` and
  confirmed `_load_manifest_for_cli` and `_print_findings` each have exactly TWO call sites
  (`cmd_check` + `cmd_plan`) - the implementer's "shared for consistency" claim is true, not a
  cover for a one-call-site helper. It itemized the ~111-line growth function by function and
  found nothing duplicated or orphaned.
- T4 regression surface re-proved on its OWN fresh manifests: all seven codes independently fire;
  `stops` still rejects `max_iterations = true`; argparse usage errors still remapped to 1;
  `check --json` still exactly three keys.
- Markdown confirmed byte-identical between the pure function and the CLI, separator spaced, 11
  pipe-lines, LF-only, single trailing newline (hexdump-checked). That is what T8 must embed.

ORCHESTRATOR ERROR the verifier caught: my dispatch brief asserted `copilot/aesop.yaml` contains a
permissions table. It does not (`grep -c permissions` -> 0). The verifier checked rather than
inheriting the claim, and correctly noted the code behaves right either way (absent -> declared
false). Same class of mistake as my `normpath` root-cause guess on T4: I stated an unverified
specific as fact in a dispatch. Verified counts that DO hold: 12 agents, 13 skills.

agent: T5 id=a9e7fc91cd91ab914 role=verifier model=sonnet findings=1 confirmed=1 result=accepted
outcome: T5 model=sonnet attempts=1 result=pass review=clean run=2026-09-04-c3f1

## Phase 2 review (opus) — ACCEPTED, 3 blocking brief defects caught BEFORE Phase 3

The phase boundary earned itself here: all three blocking findings are in the BRIEFS, not the
code, and all three would have cost a task.

- **F1 (CONFIRMED, fixed) — T6's brief carried the very ordering T4's defect corrected.** It listed
  conversion values in YAML source order, which the reviewer EXECUTED in a temp dir: `harnesses`
  failed loudly (`missing required key`), but `invariants` landed under `[project.commands]` and
  `registries` under `[pathway]` SILENTLY. No test asserts on `invariants`, so an implementer who
  fixed only the loud error would have shipped a manifest with `project.invariants` gone. Root
  cause of the miss is mine: NOTES said "the corrected rule is documented in the docstring where T6
  will read it" - an assumption about implementer behavior, not an instruction. T6's brief now
  carries the corrected order inline AND points at the docstring as authoritative.
- **F2 (CONFIRMED, fixed) — `mcp`/`loops` are ABSENT, not empty.** My pre-check line said "empty
  arrays" and I carried it into the briefing. T6 must write NEITHER key. Corrected above and in the
  brief, with an explicit "do not helpfully add `mcp = []`" instruction.
- **F3 (CONFIRMED, fixed) — T7's acceptance contradicted PLAN.** It said no `copilot/aesop.yaml`
  string may remain "in the six named source files", but `docs/AESOP-COMPILE-PROPOSAL.md` is one of
  those six, legitimately contains 5 occurrences, and PLAN says its body stays as history. Read
  literally, an implementer rewrites a historical document. T7's VERIFY command was always correct
  (it greps only the four rename files); only the prose overreached. Narrowed.
- **Q2 DECISION — fix `plan --json` now, as a logged task, not an ad-hoc edit.** Reviewer's
  reasoning accepted: it is a trap rather than a cosmetic gap (a consumer cannot distinguish
  "invalid manifest" from "engine crashed"), T8 is about to document this surface, and "touch only
  what the task requires" governs an implementer inside a task - the orchestrator opening a scoped
  task is the sanctioned mechanism. Landed as **T5b** with the exact gate the reviewer specified,
  including its instruction NOT to add `"ok": true` to the success payload (an existing test pins
  that key set).
- Non-blocking, recorded: engine is 640 lines vs PLAN's "~450" (+42%), disclosed at every step and
  twice audited for padding - **the threshold must not be raised again**; T8/T9 add no engine code
  and T5b is ~4 lines. Also caught a stale in-kit comment T7's fence would have missed
  (`tests/test_primitives_plan_adversarial.py:132`), now added to T7's edit list.

**It also proved T6's acceptance is ACHIEVABLE** rather than leaving it to chance: it built a
faithful `copilot/aesop.toml` in a temp dir and ran the engine -> `ok:` exit 0, with agents==12,
skills==13, invariants==4, doctrine sentence present. And it walked each of the seven rules to show
why none fires - notably `secret`, where the only trigger word in the file is `token` inside
`profile: token-lean`, which cannot match the literal-credential regex (PLAN R9 satisfied with no
comment rewording needed).

Ledger verified by the reviewer against the SKILL.md grammar: 5 outcomes, 15 agent lines, 6
defects, 1 reviewer line, zero malformed or quoted. attempts sum 6/24, escalations 1/2, consults
0/2.

defect: T5 kind=incomplete-acceptance
defect: T6 kind=stale-plan-decision
defect: T7 kind=contradictory-acceptance
reviewer: P2 model=opus findings=5 confirmed=5 result=accepted

### T5b — `plan --json` JSON error path (sonnet, warm cluster; from the P2 review's Q2 ruling)

Orchestrator-run verify: PASS. Confirmed directly that the two failure objects are now
byte-identical between `check --json` and `plan --json` (same keys, same values, both exit 2), and
that the SUCCESS payload is untouched at `['harnesses', 'manifest']` - the reviewer's explicit
instruction not to widen it by adding `"ok": true` was honored, so the existing key-set assertion
still holds. 640 -> 643 lines, under the 660 ceiling; threshold NOT raised, as directed. Suite
3290 -> **3291** (+1, exactly the new test).

Roster note: **test-author and verifier both deliberately SKIPPED for T5b**, recorded honestly as
`review=none` rather than dressed up. Rationale: a 4-line change whose exact final form was
specified by the opus reviewer, whose test assertion was pinned in the brief, and whose full
contract I verified myself three ways (verify command, direct failure-shape comparison against
`check --json`, and success-payload key check). The loop sanctions skipping the verifier for
trivial tasks; padding the roster here would inflate the role measurement without buying evidence.

outcome: T5b model=sonnet attempts=1 result=pass review=none run=2026-09-04-c3f1

### Cross-task defect caught mid-flight: T6's done-bar is unsatisfiable inside its own fence

Found by an orchestrator pre-flight while T6 was running (I was baselining the two doc gates T7
must satisfy, and caught the repo mid-conversion).

**The problem.** `copilot-docs/manifest.json:20` lists `"copilot/aesop.yaml"` as a doc source, and
`bin/copilot_docs.py detect_drift()` hashes every source file. The moment T6 renames the manifest,
that raises `FileNotFoundError` - and it is reached by a REAL test against the REAL repo root:
`tests/test_copilot_docs_content.py:515`
(`HtmlParityAccessibilityTests.test_in_process_check_reports_no_drift_and_is_read_only`).
`python3 bin/copilot_docs.py check` fails for the same reason.

**Why it is an architect defect, not an implementer one.** GUARDRAILS' "always run before claiming
done" requires the FULL suite green with no new failure, but T6's scope fence says "Nothing else
(T7 handles every other reference)" and `copilot-docs/manifest.json` is explicitly on T7's edit
list. T6 therefore cannot satisfy its own done-bar without violating its own fence. The two tasks
are correctly ordered (`T7 depends: T6`), so the repo is simply transiently red between them - but
nothing in either brief SAYS so, which is exactly how an implementer gets pushed into either
breaking its fence or reporting a false failure.

**Action taken:** messaged T6 mid-run with an amended done-bar - the suite may show failures whose
traceback bottoms out in that `FileNotFoundError`, and only those; every other failure is still
its own; report the list explicitly for handoff to T7; touch `copilot-docs/manifest.json` under no
circumstances; skip/weaken nothing.

Note for T7: it inherits a red `copilot_docs.py check` and MUST leave it green. Its brief already
requires `copilot_docs.py check` exit 0 and already lists `manifest.json` - so T7 is the fix, and
its own acceptance will catch it if the update is missed. `docs_build.py check` was verified clean
BEFORE T6 started, so any docs-site drift T7 sees is T7's own.

defect: T6 kind=contradictory-acceptance

### T6 — copilot/aesop.yaml -> copilot/aesop.toml (sonnet)

Orchestrator-run verify: PASS (exit 0), `ok: copilot/aesop.toml`. Test methods 86 -> 87, every
original name preserved. `_extract_yaml_list_block` gone repo-wide.

**Independent equivalence check by me against the git blob** (`git show HEAD:copilot/aesop.yaml`),
not against the implementer's report: agents 12/12 identical AND ordered; skills 13/13 identical
AND ordered; invariants 4/4 byte-identical. Structure proves the corrected ordering held -
`{'version': 1, 'harnesses': ['copilot'], 'registries': ['builtin']}` are all at ROOT, and
`project` keys are `['commands','invariants','name','stack']` with `invariants` at PROJECT level.
Those are exactly the two silent losses the P2 review predicted from source order (`registries`
swallowed by `[pathway]`, `invariants` swallowed by `[project.commands]`). Neither `mcp` nor
`loops` was added. `state.dir = "tasks/"`, `pathway.profile = "token-lean"`. The user's four
project invariants survived the conversion.

The mid-flight intervention worked as intended: it left `copilot-docs/manifest.json` untouched
(confirmed empty on `git status --porcelain` for that path) and reported the expected failures
explicitly instead of hiding or "fixing" them.

**Handoff to T7 - the transient red is TWO tests, not one.** I had identified only
`HtmlParityAccessibilityTests.test_in_process_check_reports_no_drift_and_is_read_only`; T6 found a
second with an identical traceback bottom:
`SafetyStaticScopeTests.test_check_leaves_docs_root_byte_identical`. Both end in
`FileNotFoundError: .../copilot/aesop.yaml` via `detect_drift`/`build_aic_report` ->
`_doc_source_hash` -> `source_set_hash` -> `hash_file_bytes`. Suite is 3292 with errors=2,
skipped=2 unchanged; no other failure anywhere. T7 must return BOTH to green by updating
`copilot-docs/manifest.json:20`.

Working tree now carries a real staged rename (`RM copilot/aesop.yaml -> copilot/aesop.toml`) plus
`M tests/test_copilot_bundle.py`. `git mv` staging is expected and instructed; nothing else staged,
no commit, no push.

agent: T6 id=a1779036904fb55a2 role=implementer model=sonnet

T6 test-author: **0 defects**, 37 tests added, suite 3292 -> **3329** (errors still the same 2).

It diffed every leaf against the pre-conversion YAML TWO independent ways (a dedent-based
literal-block extractor and a generic `key:`/`- item` list extractor), both hand-rolled - no YAML
library. All matched byte-for-byte including the em-dash, the backticks, `${CLAUDE_PLUGIN_ROOT}`
and `{{POLYTROPOS_ROOT}}` inside the invariants. It confirmed the nesting trap did not fire in the
RAW TEXT too, not just the parsed shape: the three bare root keys physically sit at lines 13-15,
before `[project]` at line 17.
Header comments: all 10 original `#` lines survive in order; the `aesop compile` doctrine sentence
is byte-verbatim (it wraps across two comment lines and reconstructs exactly); `aesop.yaml` appears
nowhere else in the file; the trailing YAML comment on the `test` command line survived.
Method preservation proven by AST, not grep: the original 86 `Class.method` pairs are a strict
SUBSET of the current 87 - nothing deleted or renamed - and the addition is
`ManifestSanityTests.test_no_yaml_manifest_remains`.

**A durability decision worth keeping.** It pinned the 86 original method names as a FROZEN
hardcoded set rather than reading `git show HEAD:` dynamically, reasoning that HEAD will move once
T6 is committed and a dynamic comparison would silently become vacuous. That is the right call and
the kind of thing that usually gets noticed only after it has quietly stopped testing anything.
Its `NestingTrapRegressionTests` now permanently pins the two silent losses (root keys at root,
`invariants` at project level), so a future hand-edit of this manifest fails loudly instead of
quietly dropping the user's invariants.
It also caught and fixed its own authoring bug (joining header lines with `\n` instead of `" "`,
which broke the wrapped-sentence search) - not a T6 defect.

agent: T6 id=a4034a6a0204dae01 role=test-author model=sonnet findings=0 confirmed=0 marginal=0 result=accepted

### T7 pre-flight (orchestrator, while T6's verifier ran)

All anchors verified against the post-T6 tree:
- Both status-blockquote targets have `# H1` on line 1 and a blank line 2, so T7's pinned
  "immediately after the H1 line and a blank line" insertion point is valid (insert at line 3).
- The fix that un-reds the two erroring tests is ONE line: `copilot-docs/manifest.json`, inside
  the `bundle` array, `"copilot/aesop.yaml"` -> `"copilot/aesop.toml"`. Nothing else in that file
  references the manifest.
- `docs_build.py check` re-confirmed exit 0 AFTER T6 (T6 touched no docs), so any docs-site drift
  T7 encounters is genuinely its own, not inherited. Baseline established twice now, before and
  after the rename.
- Note for whoever reads the result: `docs/AESOP-COMPILE-PROPOSAL.md` will end up carrying TWO
  status blockquotes - the pre-existing "Status update (2026-07-02)" partway down (recording that
  the .agent.md extension half shipped as aesop PR #1) and T7's new superseded note at the top.
  That is correct; both are history and neither invalidates the other.

T6 verifier: **FAIL on the literal gate — and correct to call it that**, though T6's own work is
sound. It confirmed every acceptance bullet and every probe clean, then found the verify command
itself cannot pass.

**The self-defeating gate.** T6's verify contains `! grep -rq '_extract_yaml_list_block' tests bin`.
The only two matches repo-wide are in `tests/test_copilot_bundle_adversarial.py` - line 595 (a
method NAME, `test_extract_yaml_list_block_helper_is_gone`) and line 597 (`assertNotIn(
"_extract_yaml_list_block", source)`) - a file the TEST-AUTHOR added AFTER the implementer ran, and
which exists precisely to assert the helper's absence. `tests/test_copilot_bundle.py` has zero
occurrences: the helper really is gone. So a test proving the thing is absent is what makes the
grep proving it absent fail. My earlier "Orchestrator-run verify: PASS" for T6 was genuine - it ran
BEFORE the test-author's file existed. The verifier caught a state neither of us had seen.

ARCHITECT DEFECT: any negative-assertion test defeats a bare repo-wide grep gate. Recording as
`unrunnable-verify` because the command as written cannot pass in the presence of the very test
that proves its condition.

**Fix chosen: make the adversarial test construct the string non-literally, NOT weaken the grep.**
Rejected the alternative (exclude `*_adversarial.py` from the grep) because exclusions accumulate
and a genuinely repo-wide gate is worth keeping. This kit already set the precedent: T2's
test-author hit the identical problem - its file lived under the swept `tests/` root and would have
tripped the real stale-floor sweep - and solved it by runtime string concatenation. The T6
test-author did not carry that lesson across. Same fix applies here, to both the method name and
the assertion.

defect: T6 kind=unrunnable-verify
agent: T6 id=a4bf2fc4e66bfbddb role=verifier model=sonnet findings=1 confirmed=1 result=accepted

**Second defect in the same file, found by an orchestrator forward-risk sweep — and it is the
worse of the two: tests that pass NOW and break the moment T6 is committed.**

`tests/test_copilot_bundle_adversarial.py` line ~150: `_OriginalYaml.text()` calls
`_git_show_head("copilot/aesop.yaml")`. That resolves today ONLY because T6's rename is STAGED and
not committed, so HEAD still carries the old path. On commit, HEAD holds `copilot/aesop.toml` and
the `.yaml` blob is unreachable - every test in `ValueParityAgainstOriginalYamlTests` errors.
Verified both directions: `git show HEAD:copilot/aesop.yaml` succeeds now,
`git show HEAD:copilot/aesop.toml` does not.

The sharp part: this same agent got the identical hazard RIGHT ~200 lines earlier, freezing the 86
method names as a hardcoded set precisely because "HEAD will move once T6 is committed and a
dynamic comparison would become meaningless" - then did not carry that reasoning to the YAML
content read. Correct instinct, applied once, not generalized.

Fix directed: freeze the extracted leaf values as module constants and drop the git dependency
entirely, keeping the ongoing regression value (a later edit dropping an agent or corrupting an
invariant still fails) without depending on a ref that is about to change. Required a mutation
proof that the frozen constants are a real tripwire, not decoration.

Also audited EVERY remaining verify command in the kit for the self-defeating-gate pattern:
**T6's is the only repo-wide negative grep** (`! grep -rq ... tests bin`). T1-T5b and T7-T9 all
scope their greps to named files, so no other task can hit it. The defect is isolated.

defect: T6 kind=stale-pin

Both T6 test-author defects fixed and re-verified by me. T6 verify now exits 0. No runtime git
dependency remains (`subprocess`, `_git_show_head`, `_OriginalYaml` all gone); 13 frozen
`ORIGINAL_*` constants replace them, with a "WHY FROZEN" comment recording that the parity was
proven against `git show HEAD:copilot/aesop.yaml` during T6 and preserved as a regression guard
once that blob leaves HEAD. Grep gate clean repo-wide. Tripwire re-proved by mutation: removing
`"route"` from a temp copy's agents array fails `test_agents_same_12_names_same_order`.
It also deleted `PreconditionTests.test_original_yaml_readable_from_git_history` outright - correct,
since that test asserted only the git-history readability the file no longer depends on. Suite is
therefore **3328**, not 3329 (37 -> 36 tests in that file); errors still the same 2 transients.

T6 recorded as `review=revised`: the implementer's own work was never revised, but changes WERE
required after it claimed done - in a sibling roster artifact rather than its own files. `attempts`
stays 1 because no second implementer dispatch happened.

outcome: T6 model=sonnet attempts=1 result=pass review=revised run=2026-09-04-c3f1

### T7 — reference sweep, superseded notes, rebuilds (sonnet)

Orchestrator-run verify: PASS (exit 0) - `docs-site pages are up to date` / `up to date`.
**Full suite back to 3328, OK (skipped=2), ZERO errors** - the T6->T7 transient breakage is closed.
`test_copilot_docs_content.py` alone: 41 tests OK, both previously-erroring tests green.

It followed the sequencing instruction: `copilot-docs/manifest.json` edited FIRST and the two
inherited errors confirmed green before touching anything else, isolating its own work from the
inherited breakage. No `stale-pin` hit - every anchor was present verbatim, as my pre-flight
predicted.

Rebuilds: `docs_build.py build` wrote 5 pages (exactly the 5 `check` had flagged stale);
`copilot_docs.py build` wrote 20 artifacts of which only `copilot-docs/aic-report.json` changed
content (the rest byte-identical rewrites), because the manifest rename changed the source-set hash
for 7 documents.

**Historical records preserved, verified by me**: `docs/AESOP-COMPILE-PROPOSAL.md` still holds
exactly **5** occurrences of `copilot/aesop.yaml` in its body and now carries **2** status
blockquotes - the new superseded note at the top and the pre-existing 2026-07-02 note recording
that the `.agent.md` extension half shipped upstream as aesop PR #1. That is exactly what the
Phase 2 review's F3 correction was protecting; the un-narrowed acceptance would have deleted those
5 occurrences.
`docs/AESOP-INTEGRATION.md`'s generic root-`aesop.yaml` references (lines 24, 55, 157, 161) were
correctly left alone - those name aesop's own concept, not this repo's file.

Roster note: **test-author deliberately SKIPPED for T7**, recorded honestly. T7 adds no code and no
tests; it is a text sweep whose acceptance is already grep-based and whose real risk (a missed
reference, or a damaged historical record) is a verifier question, not a test-authoring one.
Same call as T1 and T5b - the roster is measured, not padded.

agent: T7 id=a4ba0c0ac195e3384 role=implementer model=sonnet

T7 verifier: **PASS**, 1 finding - real, but NOT a T7 defect and deliberately not fixed.

- **F1 (confirmed, surfaced to the user, NOT actioned).** `docs/how-it-works.html:135` still reads
  `the Copilot CLI harness bundle (aesop.yaml + .github/)` - the exact stale claim T7 fixed in the
  `.md` sibling. It is a live, publicly-visible page. But it is OUT of T7's declared scope and
  covered by a pre-existing documented policy from the docs-site kit:
  `.claude/kits/docs-site/PLAN.md` D6 leaves `docs/guide.html` and `docs/how-it-works.html`
  "as-is - repo-local styled conveniences, not mirrored... whether to eventually retire them is
  deliberately left to the user, post-launch", encoded in `bin/docs_build.py` as
  `_UNMIRRORED_HTML_TARGETS`. Fixing it would be scope creep into a file the USER decided is
  unmaintained. Recorded for the user's decision, not patched. **This is the only genuinely live,
  currently-wrong reference anywhere in the repo.**
- Everything else in its whole-repo sweep classified correctly as historical/out-of-scope: the 5
  legitimate body occurrences in `AESOP-COMPILE-PROPOSAL.md` and its docs-site mirror; every other
  kit under `.claude/kits/*` and `tasks/kits/*` (dozens of hits, correctly frozen); T6's frozen
  pre-conversion fixtures (which describe the old file precisely so they can assert it is gone);
  and generic root-`aesop.yaml` references in GUIDE/README/skills.
- Historical record verified intact by `git diff`: `AESOP-COMPILE-PROPOSAL.md` is a clean 2-line
  insert, body still exactly 5 occurrences, and the pre-existing 2026-07-02 PR-#1 note has ZERO
  lines touched. Nothing under any other kit changed.
- Both blockquotes byte-exact: it extracted the pinned text from TASKS.md programmatically
  (unescaping the backticks) and compared character-for-character - 520 and 488 chars, identical,
  each appearing exactly once, each at line index 2 after H1 + blank.
- `copilot_docs.py build` did not overreach: `git diff --stat -- copilot-docs/` is only
  `manifest.json` (1 line) and `aic-report.json` (14 lines, all `sources_sha256` recomputations).
  No bytes/words/title/model-id/price field changed anywhere.
- Generated pages proven regenerated rather than hand-edited by reading `check_site()` itself -
  it byte-compares freshly-computed `expected_pages()` against disk, so its "up to date" IS the
  proof; no mutation probe needed.

agent: T7 id=a9a9bcf383d0f42b1 role=verifier model=sonnet findings=1 confirmed=1 marginal=1 result=accepted
outcome: T7 model=sonnet attempts=1 result=pass review=clean run=2026-09-04-c3f1

## Phase 3 review (opus) — ACCEPTED; T8 blocked as written, now amended

Phase 3 itself: every definition-of-done line re-derived independently (not taken from the
verifiers). Full value equivalence against the git blob recomputed with the reviewer's own
extractor; **test contract proven un-weakened by AST rather than grep** - per-method assert-call
counts show 0 decreased and 1 increased (`test_doctrine_sentence_in_manifest` 1 -> 2, exactly the
brief's "keep the raw-text assert AND add the parsed-content assert"), totals 130 -> 132.

**Two BLOCKING T8 defects, both proven empirically, both now fixed in the brief:**

- **C1 - T8's fence was unsatisfiable against the green-suite bar, same class as the T6 trap.**
  `tests/test_docs_build_adversarial.py` hardcodes the doc census in four assertions (lines 750,
  778, 949, 956). The reviewer copied `docs/` to a temp tree, added a stub `PRIMITIVES.md`, and ran
  the real `docs_build` functions: md sources 24 -> 25, page_map 26 -> 27, expected_pages 68 -> 69.
  So creating the doc breaks four currently-green tests, while T8's brief said "Nothing else".
  Amended: that file is now explicitly in scope with the exact bumps, plus the instruction NOT to
  replace the counts with a glob - they are deliberate tripwires making a new doc a conscious act.
- **C2 - a `docs/`-prefixed link would have shipped a silent 404 to the public site.** The reviewer
  ran the real `render_deep_dive_page` on all three plausible link forms: bare sibling and `./`
  both mirror correctly; `[x](docs/ROUTING-HISTORY.md)` mirrors to
  `.../blob/main/docs/docs/ROUTING-HISTORY.md` - doubled path, 404 - and
  `tests/test_docs_site.py`'s link check SKIPS `https://` targets, so it ships green. Amended to
  pin the bare sibling form, with `! grep -q '](docs/' docs/PRIMITIVES.md` added to the verify.
- **C4 (non-blocking, also applied).** `render_matrix_markdown` returns WITHOUT a trailing newline
  (the CLI's `print` adds it), so T8's byte-comparison fails on a naive line slice. Verified myself.
  Brief now says compare `region.strip("\n")` against
  `render_matrix_markdown(load_matrix()).strip("\n")`.

**C3 - the stale HTML: ruling is LEAVE IT, and my earlier framing was wrong.** I called
`docs/how-it-works.html` "live and publicly visible". It is not: `mkdocs.yml:6` sets
`docs_dir: docs-site`, the file is in `_UNMIRRORED_HTML_TARGETS`, and `docs-site/how-it-works.html`
does not exist - confirmed by me. Its only exposure is a `README.md:11` link as a repo-local styled
convenience. The reviewer's stronger argument: a one-line patch would make the page LOOK maintained
while its `bin/` tree still lists 16 of the repo's 41 scripts (25 missing, including this kit's own
`primitives.py`); and the sibling `docs/guide.html` carries SEVEN aesop references describing
`aesop compile` as this repo's live guardrail workflow - far more misleading than a tree label.
Fixing the small one behind the large one is a net loss in reader trust. Surfaced to the user as a
standing decision with three options (retire + repoint README:11, redirect to the published site,
or commission a refresh kit); a spot-patch is explicitly not recommended.

**C6 - defect count correction: 12, not 13.** I miscounted. The reviewer parsed the ledger: 8
`outcome:`, 20 `agent:`, **12 `defect:`**, 2 `reviewer:`, zero malformed or quoted. The candidate
I had loosely counted was my own dispatch error (the phantom permissions table) - but that is an
ORCHESTRATOR error, not an architect one, and the `defect:` family measures the architect. It stays
prose, correctly. Attempts 9/24, escalations 1/2, consults 0/2.

reviewer: P3 model=opus findings=5 confirmed=5 result=accepted

### T8 — docs/PRIMITIVES.md, nav, drift test, site rebuild (sonnet)

Orchestrator-run verify: PASS (exit 0). Embedded matrix confirmed **byte-identical** to
`render_matrix_markdown(load_matrix())` by my own comparison (13-line region, stripped compare) -
so the published table cannot drift from `primitives/harness-matrix.json`. Doc is 148 lines /
846 words of prose, inside the pinned 500-900 band. Suite 3328 -> **3331** (+3), OK (skipped=2).

**A SECOND census tripwire the Phase 3 review missed, found by the implementer via the full
suite.** The review's C1 identified `tests/test_docs_build_adversarial.py` (four assertions) but
not `tests/test_docs_build_cli.py:304`
(`RealTreeIdempotenceTests.test_build_twice_on_the_full_real_roster`), which independently pinned
`expected_count == 68` from the earlier docs-site kit. Adding `docs/PRIMITIVES.md` broke it. So my
amendment - which said "Nothing else beyond these files" - was itself incomplete, and T8 faced the
same unsatisfiable-fence shape a second time. The implementer bumped it to 69 with its docstring
arithmetic and **flagged the out-of-scope edit explicitly rather than hiding it**, which is exactly
the behavior the fence discipline is meant to produce.

ARCHITECT DEFECT recorded for the incomplete amendment. Lesson for the next kit: when a repo pins
a census in ANY test, grep for every pinned count before declaring the file list - one review pass
found one of two.

It also renamed two test methods so their names match their bumped assertions
(`..._26_entries` -> `..._27_entries`, `..._26th_mirror_page` -> `..._27th_mirror_page`) and
flagged that as beyond the literal brief. Correct call: a method named for a number its own
assertion no longer uses is a future misreading waiting to happen.

`docs_build.py build` wrote 2 / unchanged 67: the new `docs-site/deep-dives/primitives.md` and one
alphabetically-sorted row added to `docs-site/deep-dives/index.md`.

defect: T8 kind=contradictory-acceptance
agent: T8 id=a9c0a6dd474ae5372 role=implementer model=sonnet

T8 test-author: **1 finding (confirmed, marginal), 5 confirmations**, 16 tests added, suite
3331 -> **3347** OK.

The critical confirmation: **the drift test fails in BOTH directions.** It copied the real,
unmodified `tests/test_primitives_doc.py` into a temp tree and ran it against three states -
unmutated (passes), doc-side mutation (flipped a `fallback`->`native` inside the marker region:
fails), and DATA-side mutation (flipped `harness-matrix.json`'s `cursor.skill.support`: fails).
That two-way property is the whole value of T8: the published table cannot drift from the data,
and the data cannot move without the doc going red.
Also proved the model-order check is a real ordering comparison (swapping two table rows fails it),
not a set/membership check that would pass on any permutation; and that marker extraction fails
LOUDLY on all three malformed-doc states (missing begin, missing end, empty region) rather than
silently passing.

- **F1 (CONFIRMED, marginal, closed).** T8's own hygiene acceptance - no `$`+digit, no `](docs/`,
  no absolute/home paths, no dates beyond the provenance commit - was enforced ONLY by the bash
  `Verify:` block in TASKS.md, i.e. by nothing that `python3 -m unittest discover` runs. So it held
  for this run and would silently stop holding forever after. Closed with `DocHygieneAcceptanceTests`.
  Same shape as the T3 data-hygiene gap this role found earlier: an acceptance line asserted once
  by hand and never encoded.

Factual cross-checks it ran that I would otherwise have had to trust: section 8's fold/defer/drop
summary matches PLAN's evaluation table exactly (fold E1-E5; defer E6, E17; drop E7-E10, E14-E16,
E19); section 6's seven finding codes match the codes `bin/primitives.py` actually raises, verified
by regex-extracting its `_finding(...)` calls and now enforced by a test; section 5's TOML excerpt
is verbatim `copilot/aesop.toml` content, not invented, also now enforced.

agent: T8 id=aad68328dc8f8d2ab role=test-author model=sonnet findings=1 confirmed=1 marginal=1 result=accepted

### T9 — one run line in CLAUDE.md (haiku)

Orchestrator-run verify: PASS (exit 0). **15568 -> 15728 bytes, exactly the predicted figure**,
272 under the 16000 ceiling. `git diff --numstat -- CLAUDE.md` = `1 0` (one insertion, zero
deletions), line at 104 directly under the `docs_build.py check` anchor and still inside the fence.
Suite 3347, OK (skipped=2).

The only haiku task in this kit, and the pre-flight byte arithmetic I ran during a Phase-3 wait
predicted the outcome to the byte. That is the value of pinning a numeric acceptance the executor
can check itself rather than a vague "keep it short".

Roster note: **test-author and verifier both SKIPPED for T9**, recorded honestly as `review=none`.
A single verbatim line insert with exact byte math, whose full contract I verified myself (count,
ceiling, numstat, placement, layout test). Same call as T1 and T5b - the roster is measured, not
padded, and inflating it would corrupt the `--roles` evidence this kit exists to generate.

outcome: T9 model=haiku attempts=1 result=pass review=none run=2026-09-04-c3f1

T8 verifier: **PASS, zero findings.** It answered the question I actually asked - is the document
TRUE - by re-deriving every claim rather than re-reading it:
- aesop HEAD really is `9c4108ee...`, and the vendored schema diffs byte-identical against
  `git -C aesop show <that commit>:schemas/aesop.schema.json`, sha256 matching the pin.
- All nine table rows' id/order/`manifest_key`/`authored_as` diffed programmatically against
  `primitives/model.json`.
- The embedded matrix re-extracted by locating the markers ITSELF (not trusting the drift test) and
  compared byte-for-byte to a fresh `matrix --markdown` run.
- Section 6 verified by RUNNING the CLI across five scenarios - valid (0), missing file (1),
  malformed TOML (1), unknown `--harness` (2), induced schema violation via temp copy (2) - rather
  than reading the exit codes off the page. All seven finding codes confirmed present in that exact
  order, each one-line description checked against its check function's real behavior, and the
  "four known committed-credential shapes" claim confirmed against `SECRET_PATTERNS` (4 entries).
- Section 8 cross-checked against BOTH PLAN's Evaluation net line and EVALUATION.md's 19
  `verdict-check:` rows, confirming the doc's account maps 1:1 with no omission or overstatement -
  including that E5/E8's `contradicted` flags are citation-only and leave their verdicts intact.
- Census bumps: recomputed all three real counts independently (25/27/69), diffed both files
  against `git show HEAD:`, confirmed the only changes are the five bumps, their docstrings, and
  two method renames consistent with their own assertions.
- Cross-doc links confirmed to mirror as relative `routing-history.md`/`role-experiment.md` with
  both targets existing - no doubled `blob/main/docs/docs/...` path. C2's amendment held.

**Honesty note worth recording.** One probe - injecting drift into `docs-site/deep-dives/
primitives.md` to prove `docs_build.py check` catches it - was blocked pre-execution by the
harness's own action classifier. It did NOT retry or work around the block; it said so plainly,
fell back to reading `check_site()` (which uses `read_bytes() != payload`, a real byte comparison
at `bin/docs_build.py:872-898`), and labeled that one claim as resting on code reading plus the
passing check rather than a live drift injection. A verifier distinguishing "I proved this" from
"I read the code and it should hold" is exactly the behavior that makes the role worth its cost.

agent: T8 id=a76bfd8ec0aebcc12 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T8 model=sonnet attempts=1 result=pass review=clean run=2026-09-04-c3f1

## Phase 4 review (opus) — KIT ACCEPTED; all ten definition-of-done lines held

Every done-bar line re-derived independently, not taken from reports. Highlights: suite 3034 ->
**3347** (+313), zero failures; schema sha256 confirmed by hashing `git show <pinned commit>:
schemas/aesop.schema.json` and matching; the 86 original `test_copilot_bundle.py` methods proven
all-present by sorted name diff with exactly one addition; the marker region compared byte-for-byte
against a fresh `render_matrix_markdown` call; two finding codes proven live on temp copies
(`version = 2` -> exit 2 `schema`; `project.name = "../evil"` -> exit 2 `unsafe-name`); cursor
column diffed against `cursor.ts` `capabilities()` with the fallback notes confirmed VERBATIM.

### F1 — ACTED ON: 24 real home paths would have entered a deliberately-scrubbed public repo

`docs/PRIVACY.md` states this repo IS the public snapshot, created with "absolute home paths
generalized to `/path/to/polytropos`". a `git grep` for the real home prefix over the tracked tree
returns ZERO files - the scrub held across every prior kit. This kit's records reintroduced 24
occurrences across 7 uncommitted-but-committable files (TASKS 8, PLAN 4, GUARDRAILS 2, and 3+3+3+1
across the four agents). None gitignored; other kits' equivalents are tracked, so `git add -A`
would have committed them, and NOTHING would have caught it: `tests/test_privacy_layout.py` guards
only the gitignored stores, and PRIVACY.md's home-path item was a one-time pre-flip checklist step,
not a recurring test.
Root cause is precise and worth keeping: the kit applied home-path hygiene to its CODE (PLAN R8
banned home paths in fixtures; every verify block correctly used `$(git rev-parse --show-toplevel)`)
and skipped it on its own PROSE, where the sibling-repo path had no repo-relative form.
**Scrubbed all 24 to `/path/to/aesop` / `/path/to/polytropos`; verified zero remain repo-wide.**
Same shape as the silent-404 and the commit-fragile git read: green today, wrong on ship.

### Recorded, not acted on (each is a user decision or a later kit's work)

- **F2** - eight LIVE `.claude/agents/*.md` from other kits still instruct against `copilot/aesop.yaml`
  (harness-parity, copilot-model-prefs, copilot-measure-parity, copilot-skills-parity, docs-site).
  The fence was right to leave them - rewriting historical kit records would falsify the run log -
  but unlike `tasks/kits/*` these are live definitions, so a future harness-parity dispatch will
  look for a dead path. Hand to whichever kit next touches those agents.
- **F3** - `primitives/harness-matrix.json` carries aesop's roadmap language verbatim
  ("git pre-commit wrapper lands in Phase 6"). "Phase 6" names nothing in polytropos. It never
  reaches the human doc or text output, but `matrix --harness cursor --json` prints it. Verbatim
  fidelity is the fold's whole value, so the fix is a provenance line in the data, never a rewrite.
- **F4** - `docs/PRIMITIVES.md` says the cursor column is pinned to aesop's research but not WHEN.
  aesop's own matrix header says "Verified June 2026". One clause would stop a reader treating a
  months-old snapshot as current fact about Cursor. Worth adding before any Cursor work starts.
- **Engine size**: 643 lines vs D1's "~450" soft target (+43%), disclosed at every step and audited
  twice for padding. Recorded as-is rather than rounded to the plan.
- **D10 calibration**: T1 ran on opus and the ledger says so, but the ARCHITECT's model is not
  recorded, so "checked by a different model" is asserted by process, not evidenced. And the repo's
  own `judge-family` rule - which this very engine enforces - sets a higher bar than D10 met: opus
  checking a Claude-family architect is a different model, not a different family.

### Ledger honesty (the reviewer's own audit)

10 `outcome:`, 23 `agent:`, 13 `defect:`, 3 `reviewer:`; zero quoted, zero malformed. It confirmed
the ledger does NOT flatter the run: all ten tasks passed, yet the record carries 13 architect
defects, 12 confirmed reviewer findings, a `reviewer: P1 findings=2 confirmed=1` line preserving an
UNCONFIRMED finding rather than rounding it up, and three explicit self-corrections. It named the
T8 verifier's blocked-probe disclosure as the single best signal in the file.
One imprecision it caught in my own prose: T9's note says the skip was the "same call as T1 and
T5b" - T5b matches, T1 does not (T1 ran a verifier and recorded `review=clean`, skipping only the
test-author). The `outcome:` lines are correct; the sentence over-generalized.

reviewer: P4 model=opus findings=5 confirmed=5 result=accepted

## End of run

All 10 tasks `done`, zero blocked, zero remaining. Suite **3347, OK (skipped=2)** — up from the
3034 baseline recorded before the first dispatch (+313 tests). Budget used: 11 of 24 dispatches,
1 of 2 escalations (T4's retry), 0 of 2 consults — no Fable consult was ever needed.

Note for the user (not a defect): `docs/PRIVACY.md` line 3 says the public snapshot was created
with `session:` transcript ids redacted, yet five kits since (docs-site, graphify-skill,
harness-update, repo-bench, role-roster) carry tracked `session:` lines, and line 33 keeps them
deliberately for per-kit dollar attribution. Recording one here follows that established practice;
the snapshot paragraph reads as history rather than an ongoing rule. Worth a clarifying word in
PRIVACY.md if the tension is unintended.

session: 7c7ad868-93a9-4252-a524-33b0b673954d
