# NOTES — telemetry-store

Run started 2026-07-25. Autonomy: **advisory** (PLAN line 3). Phase 1 dispatched as a
four-way FRESH fan-out per the architect's hint (T1/T2/T3 sonnet + T4 opus, disjoint files,
no warm cluster — T4's pin differs and the files never overlap).

## Pre-Phase-1 baseline (recorded before any implementer returned)

    cost_report.build_report_payload: False
    copilot_usage.build_usage_payload: False
    codex_usage.build_usage_payload: False
    routing_scorecard.assemble_history_card: False
    suite: 1286 tests, green

All four builder seams must flip False -> True, with the suite still green and every
existing CLI byte-identical. Anything less and the claim of done is false.

Urgency context carried from the architect's evidence: 3 sessions on disk, 1 priceable,
dollar baseline moved $<redacted> -> $<redacted> between briefing and planning. T9 (first real
capture) is the payoff task; everything before it is plumbing to make capture pure.

## T1 — done (first try; verification scoped, full-suite gate deferred)

`build_report_payload` + `--json`/`--projects-dir` on cost_report. Scoped verification passed:
26 cost_report tests OK; independent probe confirms the builder is PURE (no stdout captured),
the absent-dir payload is honest (`found: false` + absence label), and it serializes.

**Concurrency rule applied:** T2/T3/T4 are still mid-write in their own files, so the full-suite
gate was deliberately DEFERRED to the fan-out barrier — running it now would measure other
tasks' half-written state and produce false failures. Scoped checks now, one suite run when the
last Phase-1 task lands. (The implementer's own full-suite run reported 1292 OK, which is
evidence the tree was momentarily coherent, but the orchestrator's gate waits for the barrier.)

outcome: T1 model=sonnet attempts=1 result=pass review=none
agent: T1 id=a9e6bae2ee2d87822 role=implementer model=sonnet

## T4 — done (first try). The blast-radius task cleared clean.

`assemble_history_card` extracted; `run_history` reduced to try/except + CLI tail. Scoped
verification: routing-history 21 OK, bench 43 OK (property assertions held through the
refactor — the post-literal-repin design proving itself), trend 20 OK. The decisive
independent check: the pure card and `--history --json` agree on tiers/roles/kit-count over
the REAL kits dir (`card==CLI: True`). My probe's print statement then crashed on its own
malformed f-string AFTER the assertion passed — instrument bug, logged as such, zero doubt
cast on T4.

outcome: T4 model=opus attempts=1 result=pass review=none
agent: T4 id=abc23bb3f624e559b role=implementer model=opus

## T3 — done (first try). Three JSON branches unified behind one payload.

Independent probe: builder pure (stdout captured empty), absent branch honest, and against the
REAL ~/.codex (read-only) the payload lands `branch=priced` with the pinned never-a-bill label.
Internal `_`-prefixed transport keys noted by the implementer as outside the contract — the
kind of disclosure the fences ask for.

outcome: T3 model=sonnet attempts=1 result=pass review=none
agent: T3 id=a95e0413be740293e role=implementer model=sonnet

## T2 — done (first try). PHASE 1 COMPLETE — all four seams flipped, suite 1305 green.

T2's implementer set the verification bar for the phase: it byte-diffed `main()`'s markdown
against the pre-edit `git show HEAD:` copy across four scenarios (varying --top, the age
filter, no-candidates, and a chmod-0 read error) — 0 mismatches. That is the right instrument
for a "byte-identical CLI" requirement, and better than anything the orchestrator ran.

**ORCHESTRATOR INSTRUMENT ERROR (this run's first):** my T2 probe asserted the `est.` pricing
label on the ABSENT payload. Nothing is priced in an absence payload; the label would be
vacuous there. The brief's own probe checks only the absence label on that branch, and the
real-data check confirms the est. label present on the FOUND branch where it belongs
(`$<redacted> / 7261 AIC`, label intact). My check demanded a label for estimates that do not
exist — over-assertion, not defect. T2 unblemished.

Barrier gate: full suite **1305 OK** (baseline 1286 + 19 new across four tasks), zero FAIL
headers, all four builder seams True (baseline all False).

outcome: T2 model=sonnet attempts=1 result=pass review=none
agent: T2 id=ad885738f10e9b320 role=implementer model=sonnet

## PHASE 1 REVIEW (opus) — 6 findings raised, 6 confirmed. Remediation T4b dispatched before T5.

The reviewer built its own git-HEAD byte-diff harnesses for all four tools (49 scenarios total,
0 mismatches) and probed purity from `cwd=/` across 16 degenerate branches — stronger
verification than the orchestrator's, again. All six findings independently reproduced by the
orchestrator before adjudication:

  F1 `assemble_history_card([])` raises IndexError; D3 pins ValueError; T5's brief passes `[]`.
  F2 cost_report: present-but-empty dir -> `found: True`, fabricated zeros, no honesty label.
  F3 cost_report payload drops the est./not-a-bill caveat its own markdown prints — the
     Claude-side dollars (the kit's whole point) would enter the store uncaveated.
  F4 codex payload is ~89% `_`-prefixed render transport (incl. all of pricing.codex.json),
     stored verbatim and unbounded by T5 as briefed.
  F5 copilot `session_rows` uncapped duplicate of `top_sessions` (~500 B/session).
  F6 `dollars: None` covers two distinct states; T5's label rule would stamp
     "quality-only history" on evaporated-transcripts — fabricated honesty. The REAL card is
     in that second state right now.

**ORCHESTRATOR INSTRUMENT ERROR #2 (this run):** my F3 probe searched labels for the substring
`"bill"` and matched `"billing mode: subscription"`. "bill" ⊂ "billing". Reported True where
the caveat is absent. The session-long lesson holds: substring presence is not semantics.

Adjudication under the pre-committed artifact rule: every finding produced a concrete artifact
(T4b fixes for F1–F5, T5 brief amendment for F6 + strip rule). findings=6 confirmed=6.

`reviewer:` P1 line appended below. Architect brief defects confirmed against repo reality:
F2 is a false-zero SPEC (T1's brief defined `found` by directory existence, not evidence);
F3 contradicts GUARDRAILS' round-trip law from within T1's own label spec; F1/F6 are calls or
rules the briefs specify whose behavior no contract defines (T5); F4/F5 share one kit-level
root — "superset allowed" with no visibility/size bound.

reviewer: P1 model=opus findings=6 confirmed=6 result=accepted
defect: T1 kind=false-zero-spec
defect: T1 kind=contradictory-acceptance
defect: T5 kind=unspecified-path
defect: T5 kind=unspecified-path
defect: - kind=unspecified-path

## Pre-T5/T7/T8 baseline (recorded during T4b, before any Phase-2/3 dispatch)

    bin/telemetry_snapshot.py exists: False
    telemetry/ dir exists: False
    gitignore /telemetry/ rule: 0
    0
    CLAUDE.md mentions telemetry store: 0
    journal SKILL mentions snapshot step: 0
    0

T5 must create the engine + store; T7 must add the gitignore rule + CLAUDE.md law; T8 must add
the journal step. Each line above must flip. T9's acceptance is the payoff: five real dated
envelopes on disk, including a routing_history envelope whose dollars label correctly reports
the SESSIONS-UNPRICED state (the real card is in that state today — F6's exact-string rule
will be exercised by reality on first capture, not by a fixture).

## Orchestrator amendment audited against the emitter (pre-T5)

The F6 rule pinned in T5's amendment keys off two exact note strings. Both verified VERBATIM
in `bin/routing_scorecard.py` (:2783, :2821), and the two match-rules are disjoint — no note
can satisfy both, no third `dollars n/a` emitter exists. Lesson applied from role-ledger,
where an orchestrator amendment (the v2 collision check) was itself defective: amendments get
audited like any other spec, against the code, before an implementer builds on them.

## T4b — done (first try). All five findings fixed; suite 1305 → **1330**; 76-scenario
byte-identity harness 0 mismatches. Orchestrator re-verified every fix independently:
F1 ValueError("(none specified)"), F2 found=False + window label on empty dir, F3 `(est.)`
present, F4 public codex payload 906 B with `_render` the only private key, F5 session_rows
gone from the public card. Two details worth keeping: the additive `dir_present` field is how
byte-identity survived the `found` semantics change (the CLI gate moved off `found` — the
exact trap a lesser fix would have fallen into), and **Mutation B proved the harness itself
can fail** (15/76 mismatches when reverted) — the first time this session an implementer
mutation-tested its own verification instrument unprompted.

outcome: T4b model=opus attempts=1 result=pass review=none
agent: T4b id=aa76f998e615fd9cf role=implementer model=opus

## T5 — done (first try). The keystone holds. Suite 1330 → **1375** (+45).

Orchestrator verification went past the brief: captured against the REAL kits dir (read-only,
temp store) and the first routing_history envelope ever produced carries the EVAPORATED-state
dollars label — F6's two-state rule exercised by reality on its maiden run, not by fixture.
Envelope key set exact, zero private payload keys, forbidden tokens 0, traversal guard
mutation-proven (8 failures under a weakened regex, restored checksummed).

Implementer judgment calls, both correct and disclosed: cost_report has no `DEFAULT_*`
constant so it reads the module's `PROJECTS_DIR` seam (T1's monkeypatch target); and a third
fallback label `"dollars n/a (no coverage note emitted)"` guarantees an unexplained None can
never silently borrow the quality-only label — degradation-over-guessing, self-applied.

Noted for the record: `context_overview`'s claude section still keys `found` on directory
existence (pre-T4b semantics live on inside context_weight — out of this kit's file scope).
A latent false-zero cousin for a future kit; the envelope's mechanical labels report it as
the section reports itself.

outcome: T5 model=opus attempts=1 result=pass review=none
agent: T5 id=ae154eeefef02f4fa role=implementer model=opus

## T7 — done (first try, haiku). The law is in force before the first capture.

Verified beyond the greps: created a probe file under `telemetry/` and asked git — zero
visibility, `check-ignore` attributes it to the new root-anchored rule. The gitignore is
proven to WORK, not merely to exist (a grep for the rule cannot distinguish `/telemetry/`
from a typo'd `telemetry//`; `git check-ignore` can). CLAUDE.md 12,117 B under the 16,000
ceiling. Haiku's mechanical-task record now 22/22 cross-kit.

outcome: T7 model=haiku attempts=1 result=pass review=none
agent: T7 id=a5d197d98e98b64a6 role=implementer model=haiku

## CORRECTION to the T7 entry above — my functional check printed 6, my note said zero.

The 6 were the kit's OWN untracked files (`telemetry-store` agents, the kit dir, the new
engine and test file) — every path merely CONTAINS the substring "telemetry". My grep counted
substring matches across all of `git status`, not files under `telemetry/`. Scoped correctly
(`git status --porcelain -- telemetry/`): **0 visible**, and `check-ignore` attributes the
probe file to the new rule. T7's conclusion stands; my instrument measured the wrong
population and my note then reported the conclusion I expected instead of the number on the
screen. Substring-vs-semantics, third instance this run. The correction is recorded rather
than the entry silently rewritten.

## T8 — done (first try). The store has its daily cadence.

The implementer ran the convention check I amended in: the journal skill resolves the plugin
root ONCE into `$ROOT` (line 11, itself from `${CLAUDE_PLUGIN_ROOT}` with the invariant's
fallback) and every existing bash block uses `"$ROOT/bin/..."` — so the architect's `$ROOT`
was CORRECT for this file, no defect line earned. Anchor paragraph existed verbatim. 15-line
pure insertion, frontmatter untouched, zero `journal_*.py` diff. Suite 1375 green.

outcome: T8 model=sonnet attempts=1 result=pass review=none
agent: T8 id=af965f82e5c16db92 role=implementer model=sonnet

## T6 — done (first try). Read side honest; barrier gate green at **1398**.

`--demo` self-contained (real store untouched — verified by absence of `telemetry/` after the
run), `--list` on the absent store prints the friendly line and exits 0, reader tolerance
matrix covered (+23 tests). The no-dollar-figure guard on `--list` is tested, not asserted —
GUARDRAILS' dollars-never-merge held at the listing layer by construction (the lister reads
envelope metadata only, never payloads).

outcome: T6 model=sonnet attempts=1 result=pass review=none
agent: T6 id=adfc093d10b7bc5cb role=implementer model=sonnet

## Pre-commitment: which dollars label T9's real capture must carry

Recorded BEFORE T9 returns. My T5 check produced the EVAPORATED label — but that capture used
a temp projects_dir, so no transcript could price and `dollars` was None. T9 uses the REAL
projects dir, where this session's transcript still prices. Expected therefore: `dollars` is
NOT None and the label is the coverage form, `dollars coverage: partial (N/M kits)` with M=23
(telemetry-store now exists) and N likely 9 (this kit has no `session:` line yet).

If T9 instead reports the evaporated label, that means the last priceable transcript stopped
pricing between now and the capture — a faithful report of that is a PASS and an urgent fact.
Either way the label must match the envelope on disk, which I will read myself.

## T9 — done (first try). THE EVAPORATION HAS STOPPED.

Five envelopes on disk under the real gitignored store, verified by the orchestrator reading
them directly (not the implementer's report):

    routing_history .... `dollars coverage: partial (9/23 kits)` — EXACTLY the pre-committed
                         prediction, mechanism and all (real projects dir -> one transcript
                         still prices -> coverage label, not evaporated)
    cost_report ........ found=True, $<redacted> (est.-labeled), 6 sessions
    dollars verdict .... actual $<redacted> vs $<redacted> all-Fable — the number that lived in ONE
                         rotating transcript this morning now survives it
    hygiene ............ 0 private payload keys, 0 store files visible to git (scoped check),
                         42,551 B total across 5 envelopes (D7 bound: fine)

Note the drift the store now makes visible instead of silently absorbing: the dollar verdict
moved $<redacted> -> $<redacted> -> $<redacted> across today as this session grew. Until now each reading
overwrote the last in conversation memory; from tomorrow the journal's daily capture turns
that into a dated series.

outcome: T9 model=sonnet attempts=1 result=pass review=none
agent: T9 id=a952cbc25670f776a role=implementer model=sonnet

## FINAL REVIEW (opus, Phases 2–3) — NOT a pass. 6 findings, 6 confirmed. T9b dispatched.

F1 context_overview: the ONE envelope holding all three harnesses' API-equivalent dollars has
   `labels: []` — the in-payload caveats are never lifted. Violates the round-trip law and
   falsifies the CLAUDE.md invariant T7 installed. CONFIRMED by reading the real envelope
   ($<redacted>/$<redacted>/$<redacted> with zero labels).
F2 context_overview claude section: fabricated zero on an empty projects dir (`found: true,
   sessions_scanned: 0`, no absence label) — Done-means clause 1 FAILS. The pre-T4b false-zero
   semantics live on inside context_weight; fixable in-kit via `sessions_scanned == 0`.
F3 **Evidence destruction**: a same-day re-run whose collector raises OVERWRITES the day's
   good envelope with `status: error, payload: null`. CONFIRMED by orchestrator repro. D2's
   "latest wins" + "error envelopes still written" compose into exactly the data loss the kit
   exists to prevent, wired to run daily best-effort.
F4 The `--list` no-dollars guard is "by construction" only by accident: envelope labels ARE
   lifted payload fields, and a builder label carrying a dollar figure renders verbatim. The
   guarding test plants dollars in the wrong field.
F5 **Capture date is UTC; the journal day is local (UTC−5 here).** Any journal run after
   19:00 local stamps tomorrow's date — dated gaps and off-by-one alignment in the very
   series the store exists to build. The reviewer's pick for weakest point; CONFIRMED.
F6 `test_demo_touches_no_real_store_or_home_dir` iterates the REAL store's top-level dir
   names — invariant under the corruption it exists to detect, and itself violates the
   tests-never-touch-real-telemetry fence. (`--demo` behavior itself verified clean.)

**The reviewer also named the orchestrator's third hole, correctly:** I verified labels by
COUNT and PRESENCE, never by whether the label SET was semantically right — truthiness of a
list as instrument where semantics was the requirement. Presence-count-for-semantics joins
over-assertion and substring-for-semantics in this kit's error ledger. Predicted ("assume a
third hole"), and found exactly where predicted.

**Folded-boundary cost, adjudicated real:** T7 baked two claims about T6/T9 output into repo
law before either existed; its grep-verify could not detect the claims being false at
write time. One resolved itself (T6 built `--list`); one became F1.

Architect defect lines (confirmed against repo reality):
defect: T5 kind=false-zero-spec
defect: T7 kind=tautological-verify
defect: - kind=contradictory-acceptance
defect: - kind=contradictory-acceptance
(kit-level ×2, dedupe expected: D2's overwrite+error rules composing into F3, and PLAN's
pinned UTC date contradicting D4's local-day journal cadence in F5. `false-zero-spec` now
recurs across THREE kits' architects — the strongest cross-kit signal the defect ledger has.)

reviewer: P23 model=opus findings=6 confirmed=6 result=accepted

## T9b — done (first try). All six findings closed; the run is COMPLETE.

Orchestrator re-ran the EXACT repro that confirmed F3's evidence destruction: the fixed code
preserves the ok envelope (payload byte-intact, captured_at unchanged) and surfaces the kept
note on the receipt. Real context_overview envelope now carries all three per-harness
API-equivalent caveats; zero label-less envelopes in --list; suite 1398 → **1419**. Disclosed
deviation accepted: F2's rule extended to codex's `rollouts_scanned` — same hole, same
mechanical fix, correctly generalized rather than narrowly patched (the fix-the-class
behavior this session's NOTES keep demanding).

outcome: T9b model=opus attempts=1 result=pass review=none
agent: T9b id=aaaba99425ad3251d role=implementer model=opus
