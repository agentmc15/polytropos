# kit-preflight — execution notes

Run `run=2026-10-24-93ee`, interactive (`/polytropos:execute kit-preflight`), plugin 0.6.10, branch `feat/route-experiment` at 98d1a67. Dials: autonomy advisory; budget max-dispatches=40 max-escalations=3 max-consults=3; roles test-author + red-team, dispatched on T4, T5, T7 and T8 only (PLAN D16) and on no docs, skill or commit task.

Setup: `kit_contract.py graph` exit 0 (ready, frontier T1); `roster` exit 0 (workflow=extended). The installed execute skill predates this kit's A3, so this run has no P0 spec review; that loop step is what T10 builds.

## Task notes

- T1 pre-work: verify's first clause exit 5 (NO TESTS RAN; the test file does not exist) — red as required.
agent: T1 id=af5875d465df3bef0 role=implementer model=sonnet
- T1: the verify's last clause `git diff --quiet -- .claude/kits` cannot pass while the loop keeps this kit's TASKS.md current; the orchestrator judges it as `git diff --quiet -- .claude/kits ':!.claude/kits/kit-preflight'` (same intent: no other kit's committed files change). Every later task whose verify carries the clause is judged the same way.
- T1: brief steps 4–5 (new architect keys always present; `caught pre-run` always rendered when defects > 0) conflict with the Gotcha's "existing tests stay green unchanged" — exact key-set and byte-exact golden tests. Implementer rendered the keys and line only when non-empty; acceptance (`caught pre-run: 0` on the committed card) still holds. Bounded adaptation.
defect: T1 kind=contradictory-acceptance
agent: T1 id=adabfb0bfde5d0646 role=verifier model=sonnet findings=5 confirmed=3 result=accepted
outcome: T1 model=sonnet attempts=2 result=pass review=revised run=2026-10-24-93ee
- T1 done: verify passed on the first dispatch; the second dispatch applied the verifier's two cosmetic fixes (comment path, duplicate test constant/dead helper). Card on committed kits: folded 3, excluded 1, no unsanctioned, `caught pre-run: 0`. Later tasks must not assume the `caught pre-run` line renders on a card with only sanctioned kinds.
- T2 pre-work: the verify's last clause (`grep -q 'unrunnable-verify'` across the four docs) exit 1 — red as required.
agent: T2 id=a345221e9560e719b role=implementer model=sonnet
agent: T2 id=a79d53a7fc3362294 role=verifier model=sonnet findings=2 confirmed=2 result=accepted
- T2: the brief mandates present-tense text in `skills/architect/references/routing-evidence.md` (execute "runs" `analyze` and a P0 review) and in ledger.md's `when=pre-run` paragraph, but T3 commits Phase 1 before T4 (`analyze`) and T10 (P0 review) exist. Kept the mandated wording (no scope change); T3's commit body must say that sentence is ahead of the code until T4 and T10 land. The plugin installs only from main, so no session reads it before the kit is merged.
defect: T2 kind=contradictory-acceptance
outcome: T2 model=sonnet attempts=2 result=pass review=revised run=2026-10-24-93ee
- T2 done: verify passed on the first dispatch; the second moved the test file's `__main__` block below the parity tests (verifier finding).
- T3 pre-work: `git diff --quiet -- bin tests skills docs docs-site` exit 1 (Phase 1 sources dirty) — red as required. The brief's staging list omits `docs/sdd/guide.html` (the guide's generated twin), without which the verify's `docs` clause cannot hold; added as an orchestrator note at dispatch.
defect: T3 kind=unspecified-path
agent: T3 id=a2914c79c58755a22 role=implementer model=haiku
outcome: T3 model=haiku attempts=1 result=pass review=none run=2026-10-24-93ee
- T3 done: Phase 1 committed as 6613705 (full suite and docs_build check green before staging; the body carries the "ahead of the code" note for routing-evidence.md). The user's commit-msg hook strips the trailer, as before.

## Phase 1 review (opus) — FIX-FIRST, adjudicated

reviewer: P1 model=opus findings=12 confirmed=5 result=accepted
- Finding 1 (blocking before T4): D3 split on `|`/`&&`/`;` before honoring quotes and path-checked `test` operands, so this kit's own commit-task verifies (quoted `feat|fix|…` regex; `= feat/route-experiment`) would read as missing executables/path and T4's "analyze exits 0 on this kit" could not hold. The user chose to correct D3 (quote-aware `shlex` with `punctuation_chars`; `test`/`[` operands not path-checked); PLAN D3 carries a dated amendment note; T4 gains test case (11a) for it.
defect: T4 kind=contradictory-acceptance
- Finding 2: T1/T4/T7/T8 verify ended with the literal `git diff --quiet -- .claude/kits`, which T13's `drift` would re-run on a tree whose kit-preflight TASKS.md is dirty. All four now end with `test -z "$(git diff --name-only -- .claude/kits | grep -v '^.claude/kits/kit-preflight/')"` (user-approved; same intent; passes the amended D3 because `$(…)` is dropped before tokenizing). GUARDRAILS' sentence about the clause updated to match.
defect: T13 kind=contradictory-acceptance
- Finding 3 → T6: 6613705's body overclaims — `--roles` never calls `role_quality_stats` or renders defect kinds; the tests do not compare lessons_promote with the scorecard aggregate; the write guard re-imports routing_scorecard, not lessons_promote. T6's commit body corrects 6613705 by name.
- Finding 9 → T12: `docs/SPEC-DRIVEN.md` "coined synonyms are folded" overstates (only three named synonyms fold; new ones are flagged unsanctioned), and ledger.md names the folds without their targets. T12 fixes both sentences.
- Finding 11 → T10: no task adds A4's fixture test that a `reviewer: P0` line counts as a review event and `when=pre-run` defects count as caught pre-run. T10 adds one fixture-NOTES test.
- Not acted on, carried as follow-ups for a later kit: (4) no test pins `lessons_promote.main()` passing the canonical hook; (7) fold + raw-kind dedupe can count one canonical kind twice in one task (no committed kit has such a pair); (8) lessons_promote docstring "Used ONLY for its parse_defects" is stale. Informational: (5) T1's conditional keys judged correct — so docs must not say `caught pre-run` always renders, and `--json` readers use `.get('pre_run', 0)`; (6) the ahead-of-code sentences become true only after T10, so the branch must not be merged before T10; (10) `by_kit` counts the excluded event by design; (12) T4: only a dotted module after `-m` maps to a path.
