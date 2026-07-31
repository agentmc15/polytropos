# copilot-measure-parity — execution notes

## Run 1 (2026-07-25) — autonomy: advisory (no PLAN.md dial, none given at invocation)

### Dispatch-mode correction (recorded before the first dispatch)

TASKS.md marks T1 and T3 `independent: yes` and its preamble calls the two pairs
"independent of each other" — but BOTH tasks append a line to the SAME `skills:` block in
`copilot/aesop.yaml`, and both run `python3 bin/copilot_docs.py build` plus the full suite.
Parallel dispatch would race on one file and interleave two docs builds. The two warm
clusters therefore run SERIALLY: T1 → T2 (context-weight), then T3 → T4 (bench-routing).

Confirmed against repo reality before dispatching anything, so it is logged as a kit-level
architect brief defect. New kind coined — no existing kind (`stale-pin`,
`tautological-verify`, `missing-helper`, `unspecified-path`, `contradictory-acceptance`,
`stale-plan-decision`) describes an independence marking that contradicts a shared write
target.

defect: - kind=unsafe-parallel-marking

Lesson for the next kit: a task's `independent:` marking must account for EVERY file it
writes, manifests and generated-doc outputs included — not just its primary subject file.

### T1 stop-and-report — frozen file the deliverable must touch (confirmed)

The T1 implementer stopped instead of improvising, correctly. Its claim, verified by the
orchestrator against repo reality: `tests/test_copilot_docs_content.py` pins
`EXPECTED_SKILLS`/`EXPECTED_AGENTS` as hardcoded rosters, so the FIRST skill this kit adds
fails `test_discovered_skills_match_skills_md_headings_exactly` — while PLAN.md's scope and
GUARDRAILS.md froze that file. The kit's own deliverable could not satisfy its own
"full suite green" acceptance.

Adjudication: the test's live legs (discovery, docs headings) already agree once the builder
runs; the hardcoded set is a deliberate tripwire forcing acknowledgment of roster changes, so
updating it IS the sanctioned acknowledgment — NOT a workaround, and NOT a reason to derive
the constants (that would delete the tripwire the copilot-docs kit built on purpose).
PLAN.md gained D8, GUARDRAILS.md narrowed its freeze to "everything in that file except those
two constants", and T1–T4 each gained the lockstep roster-constant edit.

defect: - kind=unspecified-path

Lesson for the next kit: before freezing a file set, grep the suite for HARDCODED rosters of
the thing the kit adds — a set-equality test against a literal is invisible to a scope review
that only looks at the files the kit means to write.

### T1 second stop-and-report — a guardrail that misstated repo reality (confirmed)

Same implementer, same rule, second distinct discrepancy — and again correct. After the D8
amendment landed, two more coverage tests failed: the docs guide has no `## context-weight`
section.

Verified by the orchestrator: `copilot-docs/SKILLS.md` and `AGENTS.md` are NOT generated
output. Each is a hand-authored guide carrying ONE builder-spliced inventory block; the
per-surface `## <name>` prose sections below it are authored source the builder never writes
(manifest: `authoring.mode: estimated`, `tier: strong`). GUARDRAILS.md's original rule —
"Docs regeneration is builder-only; never hand-edit anything under `copilot-docs/`" — was
factually wrong about how that directory works, and it fenced off the very content the kit
had to produce.

Adjudication: PLAN.md gained D9, GUARDRAILS.md's docs rule was REPLACED (authored prose is
source and must be authored; generated blocks between markers and pure artifacts stay
builder-only), and T1–T4 each gained their authored guide section with the exact subsection
grammar the coverage tests require.

defect: - kind=stale-plan-decision

Lesson for the next kit: "generated directory" is a claim to VERIFY, not assume. A doc that
mixes spliced generated blocks with authored prose looks generated from the outside; check
for BEGIN/END markers and the manifest's `authoring` mode before writing a freeze rule over
a whole directory.

### Ledger note on T1's attempt count

T1 took three implementer dispatches (one spawn, two continuations), so its `outcome:` line
records `attempts=3 result=retry-pass` — the honest dispatch record. The implementer did NOT
fail: both re-dispatches were brief amendments after it correctly stopped on defects in MY
briefs, recorded above as `defect:` lines. The two ledgers split the question deliberately —
`outcome:` records what the dispatches did, `defect:` records whose fault it was. Reading the
sonnet tier's first-try rate for this kit without reading its defect lines would blame the
executor for the architect's misses.

### Ledger

outcome: T1 model=sonnet attempts=3 result=retry-pass review=clean
agent: T1 id=a78ffd925fd3847da role=implementer model=sonnet
agent: T1 id=afc4a87131fc10197 role=verifier model=haiku findings=0 confirmed=0 result=accepted
outcome: T2 model=sonnet attempts=1 result=pass review=clean
agent: T2 id=a78ffd925fd3847da role=implementer model=sonnet
agent: T2 id=aa0d24f4f62da4a69 role=verifier model=haiku findings=0 confirmed=0 result=accepted

outcome: T3 model=sonnet attempts=1 result=pass review=clean
agent: T3 id=ac468bf1c5c1540f9 role=implementer model=sonnet
agent: T3 id=ae622b7d8e775360f role=verifier model=haiku findings=0 confirmed=0 result=accepted

outcome: T4 model=sonnet attempts=1 result=pass review=clean
agent: T4 id=ac468bf1c5c1540f9 role=implementer model=sonnet
agent: T4 id=a577315435e578763 role=verifier model=haiku findings=0 confirmed=0 result=accepted

T3 opened the second cluster on a FRESH implementer (new subject: bench-routing) and passed
first try — the amended rules were carried by the BRIEFS at that point, not by agent context,
which is the sign the amendments landed in the kit rather than only in one agent's head.

T2 is the warm cluster's second task and its first clean pass — the same agent that had been
corrected twice on T1 needed no correction here, having carried both amendments (D8, D9) in
context rather than rediscovering them. Warmth earned its keep on this cluster.

### Phase 1 review — 8 findings, 7 confirmed

The opus phase reviewer found real defects that THREE per-task verifiers (all haiku, all
returning findings=0) had passed. Verified each myself before adjudicating:

- **F1 CONFIRMED (blocking).** `bench-routing.agent.md` states the D3 rule correctly, then its
  presentation section instructs the opposite: "implementer gets the measured-outcome check
  from the Claude-harness ledger". On the Copilot side that is a category error — the ledger's
  implementer evidence is about Claude tiers, while `roles --harness copilot` picks a
  different vendor's model entirely. Implementer drift (the brief never authorized a
  carve-out), so T4 is `review=revised`.
- **F2 CONFIRMED (blocking).** Both context-weight surfaces claim figures are "never priced",
  but `context_weight.py session --harness copilot` prints
  `context carry cost: $<redacted> (3,595.63 AIC)` with its mandatory
  `API-equivalent dollars — an estimate, not a bill.` label. The files contradict the very
  command they teach. Root cause is MY brief, which pinned the never-priced wording.
- **F3 NOT confirmed** — stale read. T4 was already `done` with its ledger line by the time I
  adjudicated; the reviewer read the file mid-run. No artifact, so not counted.
- **F4 CONFIRMED.** `UNAVAILABLE` never appears in the text output (`grep -c` = 0); it is a
  `--json`-only label, and the text card prints `20/27 benchmark entries dispatchable`. I
  pinned that anchor in the brief, so the brief taught a string users never see.
- **F5, F6, F7, F8 CONFIRMED** — compare's missing no-`--harness` note in the skill; the
  authored "Skills versus agents at a glance" table in AGENTS.md never extended (D9 named the
  `## <name>` sections and missed the table); the resident `copilot-instructions.md` roster
  prose now false by omission (correctly out of scope — follow-up, not an unsanctioned edit);
  pattern divergences.

reviewer: P1 model=opus findings=8 confirmed=7 result=accepted
defect: T1 kind=stale-plan-decision
defect: T3 kind=stale-plan-decision
defect: - kind=unspecified-path

**Verifier precision, recorded honestly:** three haiku verifiers each returned findings=0 over
material carrying seven real defects. They were rigorous on the checks they were GIVEN
(re-running commands, greping frozen paths, mutation-testing) but did not compare the files'
honesty claims against live engine output unprompted. The phase reviewer did, because its
brief told it to run the engines. Lesson: a verifier finds what its brief points at — the
adversarial value comes from the instruction to re-derive, not from the fresh context alone.

### Ledger — corrected after the phase review

The Phase 1 review required real changes to the products of T1–T4, so their `review=` field is
corrected from `clean` to `revised` here. The scorecard takes the LAST line per task id, so
these supersede the earlier lines; the originals are left in place as the record of what was
believed at the time.

outcome: T1 model=sonnet attempts=3 result=retry-pass review=revised
outcome: T2 model=sonnet attempts=1 result=pass review=revised
outcome: T3 model=sonnet attempts=1 result=pass review=revised
outcome: T4 model=sonnet attempts=1 result=pass review=revised
outcome: T5 model=sonnet attempts=1 result=pass review=clean
outcome: T6 model=haiku attempts=1 result=pass review=clean
outcome: T7 model=sonnet attempts=1 result=pass review=clean
agent: T5 id=a7baa01e218aebd90 role=implementer model=sonnet
agent: T5 id=a652dfa9d24cadb8c role=verifier model=haiku findings=0 confirmed=0 result=accepted
agent: T6 id=af3780b43aecc3aeb role=implementer model=haiku
agent: T7 id=adf6abd97c6f0e419 role=implementer model=sonnet

T7 also reported a discrepancy in its own brief rather than papering over it: my brief claimed
`--json` carries an uppercase `UNAVAILABLE` key; the engine actually emits a lowercase
`unavailable` list. It worded the fix to the engine's reality and said so. That is the third
time in this run an implementer chose reporting over improvising.

defect: T7 kind=stale-plan-decision

### Final review + T8 — the fabricated test anchor

The final review confirmed all six T7 fixes real and truthful (it also checked the F2 fix was
not an OVER-correction — `est.` genuinely does hold for the attribution and audit figures it
now claims). It found two residual items, both traceable to my briefs:

- The F4 fix reached the two bundle files but NOT the two authored docs sections T7's brief
  said "BOTH bench-routing files" and never named the docs — so the published guide
  contradicted the skill it documents, on the surface a user actually reads.
- **A test pinning a fiction.** T5's `UNAVAILABLE` anchor pins an uppercase literal that
  appears in ZERO engine output (`roles --harness copilot --json | grep -c UNAVAILABLE` = 0;
  the real key is the lowercase `unavailable`). T7 had to bend a sentence around it, so the
  bad anchor propagated a false clause instead of catching one. T8 repinned the assertion to
  the real key, dropped the clause from both bundle files, and corrected both docs sections.
  Mutation-tested afterwards: the repinned assertion still fails when the anchor is removed.

outcome: T8 model=sonnet attempts=1 result=pass review=clean
agent: T8 id=a3af859f63c9f6047 role=implementer model=sonnet
reviewer: P2 model=opus findings=2 confirmed=2 result=accepted
defect: T5 kind=stale-plan-decision

Lesson, and the sharpest one of this run: **a verify anchor is a claim about reality and must
be checked against the engine before it is pinned.** A test asserting a string the system never
emits is worse than no test — it passes forever, and it forces every later edit to preserve a
falsehood to keep the suite green. Check anchors against live output at ARCHITECT time.

### T9 — the deferred follow-up, closed

PLAN.md D10 narrowly unfroze the two roster sentences in `copilot/.github/copilot-instructions.md`
and their `aesop.yaml` mirror. Scoping it first showed the risk was lower than assumed when it
was deferred: `DoctrineSentenceSyncTests` requires ONE doctrine sentence verbatim in both files,
not byte-equality of the block, and `test_context_weight.py` sizes synthetic fixtures rather than
the real file.

Verified after landing: doctrine sentence intact in both; both roster sentences byte-identical
between the two files; resident surface grew 1928 -> 2132 chars (+204, ~51 tokens per call) for
two new capabilities — proportionate, which matters because this file is resubmitted on EVERY
Copilot call and this same kit ships the skill that teaches keeping resident surfaces lean.

outcome: T9 model=sonnet attempts=1 result=pass review=clean
agent: T9 id=ad93f54d1451f6c06 role=implementer model=sonnet

### Follow-up beyond this kit (CLOSED)

`copilot/.github/copilot-instructions.md` (and its mirrored `instructions.blocks` in
`copilot/aesop.yaml`) still enumerate the pre-parity roster — "four ported agents complete the
optimizer surface" and a `/route, /usage, /journal, /frontier-check, /escalate, /effort,
/architect, /execute` list omitting both new names. That prose is resident in every Copilot
call, so it is false-by-omission on the most-read surface in the bundle. GUARDRAILS froze the
file and this kit never sanctioned it, so the implementers were right to leave it. It needs its
own small kit or task — NOT an unsanctioned edit.

### Warm clusters

- T1 → T2 served by one warm implementer (shared subject: the context-weight surfaces).
- T3 → T4 to be served by a second warm implementer (shared subject: bench-routing).
- Verification is never warmed — each verifier is a fresh spawn.

