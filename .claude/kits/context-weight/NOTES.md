# NOTES — context-weight

Execute-owned. Cross-task learnings + machine-readable ledgers.

## Run 1 — 2026-07-25

Plugin was refreshed to 0.2.0 immediately before this run (see the `plugin-refresh` branch and
commit `c99c658`). Verified LOADED, not merely on disk: this session's `execute` skill reads the
kit's `GUARDRAILS.md` at setup, which only 0.2.0 does. The prior run attempt was aborted after
discovering the installed plugin was 18 days / 22 commits stale — architect still said "append to
CLAUDE.md", pricing had no `claude-opus-5`.

Dispatch: kit agents (`context-weight-*`) exist on disk but were written after this session's
agent registry loaded, so dispatch used the Agent tool directly with each task's `model` pin —
the sanctioned fallback. Model routing unaffected.

### Learnings

- **T1 verification method — `grep -c 'Path.home()'` gives FALSE POSITIVES; use the AST.** The
  guardrail requires ZERO `Path.home()` in `tests/test_context_weight.py`. A grep returns 1 — but
  that occurrence is inside the module docstring, in the sentence *documenting* the zero-count
  contract. An `ast.walk` looking for `Call(func=Attribute(value=Name('Path'), attr='home'))`
  returns the true answer: **0 calls**. Every later task with the same guardrail (T3, T4, T12)
  must be checked the same way, or a correct implementation gets reported as a defect.
- **The engine's 3 `Path.home()` calls are sanctioned and should NOT be "fixed".** Lines 136/137
  are module-level `DEFAULT_CODEX_HOME`/`DEFAULT_COPILOT_HOME`; line 131 sits inside
  `_default_projects_dir()`, which is called exactly once at line 135 to set the module-level
  `DEFAULT_PROJECTS_DIR` — mirroring `session_cost._default_projects_dir()` per the brief. An AST
  "is it at module level" check flags 131 as nested and reads as a violation; it isn't. All three
  resolve at import to compute `DEFAULT_*`, never on a runtime path a test exercises.
- **T1 measured facts** (useful to T7's demo pins): fixture weights `[10000, 20000, 30000, 8000]`
  → avg 17,000, peak 30,000, total 68,000; exactly one inferred drop at index 3; sidechain
  `{calls: 1, weight: 5000}`; carry cost `$<redacted> of $<redacted> (92%)`. Suite 1022 → **1041** (+19).

outcome: T1 model=sonnet attempts=1 result=pass review=none
agent: T1 id=a0ac6c4b818a25f1a role=implementer model=sonnet

- **T12 proved itself on a live case, and distinguishes the CAUSE.** Run right after T1/T12
  landed it reports `status: DRIFTED`, exit 3 — correctly: the repo now has
  `bin/context_weight.py` and `bin/plugin_staleness.py` that the installed 0.2.0 snapshot lacks.
  Crucially it does NOT blame the version (`version: repo 0.2.0 vs installed 0.2.0 — match`) and
  names the two missing files instead. That distinction is what would have made this morning's
  18-day staleness obvious in seconds. Imports are argparse/json/os/pathlib/sys only — no
  subprocess, no network; `Path.home()` calls: 0 (uses `os.path.expanduser`, matching
  `statusline.py` precedent).
- **T12's brief carried a self-contradictory verify.** It required PRINTING a remedy containing
  `claude plugin update`, then grepped the source to prove `claude plugin update` was absent. The
  implementer split the literal across two halves to satisfy both. Verified what matters — the
  printed OUTPUT is byte-exact against the pinned remedy. Not a dodge, but if a later task
  inherits a "must print X" + "grep proves not-X" pair, resolve it in the brief rather than in
  the source.
- **T2 attribution is honest (D4 confirmed in real output).** Ranked Bash 5,000 est. / Read
  2,000 est. against 20,000 measured growth, with an explicit `unattributed growth 13,000 est.`
  row rather than distributing the gap to make the table balance, plus a plain sentence naming
  what is structurally unmeasurable. Zero `$` inside the attribution section; dollars appear only
  on the carry-cost line from measured usage, per D5.

### Orchestrator method notes — three of my verification checks produced FALSE findings

Each time the implementer was right and my instrument was wrong. Later tasks (T3, T4) and the
phase reviewers face the same guardrails, so use these instruments:

1. **`Path.home()` count → use AST, not grep.** `grep -c` counts prose; the file's own docstring
   documents the zero-count contract. `ast.walk` for `Call(func=Attribute(value=Name('Path'),
   attr='home'))` gives the true count.
2. **Exit codes → never read `$?` after a pipe.** `cmd | tail` yields tail's status. Redirect to a
   file and capture `$?`, or use `PIPESTATUS`.
3. **Section-scoped content checks → bound the section.** Splitting on a heading and taking the
   remainder sweeps in every later section; regex to the NEXT heading (`(?=^##+ |\Z)`).

outcome: T2 model=sonnet attempts=1 result=pass review=none
outcome: T12 model=sonnet attempts=1 result=pass review=none
agent: T2 id=a0ac6c4b818a25f1a role=implementer model=sonnet
agent: T12 id=af7c9ff5cfed90657 role=implementer model=sonnet
warm-cluster: T1,T2 served by one sonnet sidekick (id a0ac6c4b818a25f1a) — 2 tasks, cap 4

- **Phase 1 review (opus): CLEAN** on all six axes — no implementation drift in T1/T2/T12. It
  produced three ACTIONS, all applied before Phase 2 continued:
  1. **D4 was leaving measured mass in the unknown bucket.** Decomposing `unattributed growth`
     on three real transcripts: assistant output is 83% of the gap on a 35-call session and 57%
     on a 298-call one. Every assistant reply (text + thinking + tool_use JSON) is re-submitted
     next call, so it IS growth — and it is already an exact `output_tokens` count, needing no
     `est.`. D4 sized only user-side additions. → **T13 added** (assistant-output row labeled
     `measured`, both it and `unattributed` ranked inline by size, corrected explanation line).
     The old pinned line claiming thinking is "not measurable" was wrong; T2's implementer had
     no latitude since it was pinned verbatim in the brief.
  2. **T9 check 8 would have FAILED correct work** — it used the exact `grep -c "Path.home()"`
     this file already proved wrong. → replaced with the AST check.
  3. **PLAN + T9 check 6 never sanctioned T12's two files** (added mid-flight by the
     orchestrator, acceptance criteria not amended) → both updated. This is the standing cost of
     an orchestrator-added task: amend the acceptance criteria in the same breath.
  Deferred, recorded not fixed: placeholder paths ignore `--json` (T7 must make `demo --json`
  round-trip); `find_main_transcript` can select a sidechain-only transcript and render a
  confusing `0 call(s)` card (T5/T9 could add a one-line note); `user` records with string
  content and `image` blocks are unsized — both inflate `unattributed` honestly, no violation.
- **T3 held the D3 ladder under real temptation.** `attribute_growth` was already written and
  passing, but Codex got a byte-share by RECORD TYPE plus the verbatim
  `provenance not recorded in these logs …` line instead of a fabricated tool ranking. Verified
  structurally, not by grep: an AST call-graph walk shows `attribute_growth` is UNREACHABLE from
  `_cmd_session_codex`, `codex_curve`, `codex_byte_share`, and `build_codex_session_card`. The
  implementer also self-checked with the AST instrument from this file rather than grep.

outcome: T3 model=sonnet attempts=1 result=pass review=clean
agent: T3 id=a13766fb716a353eb role=implementer model=sonnet

- **PRE-T13 BASELINE captured by the orchestrator (independent of the reviewer).** T13's
  acceptance rests on the reviewer's decomposition, so the same split was measured directly
  before T13 runs — it reproduces the reviewer's figures, which makes the finding two
  independent measurements rather than one claim:

  | session | calls | measured growth | attributed | unattributed | unknown % |
  |---|---:|---:|---:|---:|---:|
  | fc6c2eb3 | 312 | 845,335 | 325,448 | 519,887 | **61.5%** |
  | d32caae9 | 35 | 37,942 | 12,787 | 25,155 | **66.3%** |
  | b5972836 | 9 | 3,123 | 3,279 | 0 | 0.0% (overshoot flag fired) |
  | 49814f35 | 3 | 339 | 3,481 | 0 | 0.0% (overshoot) |

  Aggregate pre-T13 unknown share: **61.5%** (545,042 of 886,739). Reviewer independently
  reported 61% / 66% on the two large sessions — match. AFTER T13 lands, re-run the same
  measurement on the SAME session ids and require a material drop (brief predicts ~61% → ~26%
  on the 312-call profile). If the drop does not materialize, T13 has not done what it claims,
  regardless of what its tests assert.

  Command to reproduce (read-only):
  `python3 bin/context_weight.py session --harness claude --session <id> --no-subagents --json`
  then read `attribution.measured_growth` / `.attributed_total` / `.unattributed`.

- **Parallelism note:** after T3, the remaining graph is effectively SERIAL. T10 and T13 are
  dependency-ready (both depend only on T2) but every remaining task except T8/T11 edits
  `bin/context_weight.py` + `tests/test_context_weight.py`, so dependency-ready is not the same
  as safe-to-dispatch. Only T12 was ever genuinely parallel (disjoint files). Do not fan out
  T10/T13 alongside a running task on the shared pair.

- **T4 completed the ladder, and it is genuinely three different fidelities — not three
  variants of one card.** Copilot renders `growth curve: not available — Copilot events do not
  record per-turn input/cache token splits`, a session-average weight, per-model output turns,
  and a carry cost. No sparkline glyph appears anywhere in its output. This was the sharpest
  temptation in the kit: `codex_curve` (written one task earlier) would happily plot Copilot's
  per-turn OUTPUT events as a curve and it would look like a feature — but output tokens are
  not context weight, and Copilot records no per-turn input/cache split at all. Verified
  structurally: AST call-graph shows ZERO reachability from `_cmd_session_copilot`,
  `copilot_session_card`, `render_copilot_session_markdown`, or `build_copilot_session_json` to
  `codex_curve` / `attribute_growth` / `codex_byte_share` / `detect_drops`.
- **Sequencing decision: T13 runs BEFORE T5, deviating from phase order.** T5 (`overview`)
  aggregates attribution across sessions and T7 pins demo numbers derived from it. Running
  either before the fix would bake the 61.5% unknown split into cross-session figures and force
  a re-pin later. Fix the foundation, then aggregate.

outcome: T4 model=sonnet attempts=1 result=pass review=none
agent: T4 id=a8fefe36100444fe8 role=implementer model=sonnet

- **T13 delivered, verified against the recorded baseline — not against its own tests.** Its unit
  tests assert on a synthetic fixture and would pass whether or not real sessions improved, so
  the acceptance test was a re-measurement of the two baseline session ids:

  | session | unknown before | after | Δ |
  |---|---:|---:|---:|
  | d32caae9 (stable, 35 calls) | 66.3% | **11.4%** | −54.9pp |
  | fc6c2eb3 (live, 322 calls)  | 61.5% | **26.3%** | −35.2pp |

  Orchestrator re-measured both independently; figures match the implementer's report. The
  stable session is the stronger evidence — `fc6c2eb3` is this live conversation and grows while
  the kit runs (312 → 322 calls between baseline and re-measure), so its growth denominator
  moves. Qualitative checks that a cosmetic "fix" would have failed: the row reads
  `assistant output (measured) | 20,836 measured` (NOT `est.` — running it through
  `EST_CHARS_PER_TOKEN` for symmetry with the other rows would have silently undone the point),
  it ranks **#1 inline** with `unattributed` positioned below it by magnitude, and the old
  "thinking … not measurable" line is gone repo-wide.
- **Orchestrator instrument errors this run: 4, all mine, none masking a real defect.** grep-vs-AST
  for `Path.home()`; `$?` read after a pipe; section-bounding regex that swept in later sections;
  and twice a `^##+ .*heading.*$` regex that silently matched nothing and returned an EMPTY
  section — which reads as "the feature is missing" rather than "my check failed". Lesson for the
  remaining tasks and for T9: when a content check returns empty/zero, first prove the anchor
  exists, then judge the content. An empty match is not evidence of absence.

outcome: T13 model=sonnet attempts=1 result=pass review=none
agent: T13 id=adc1b05fe9c914696 role=implementer model=sonnet

- **Caught a stale downstream pin BEFORE it blocked a task.** T13 changed the fixture's
  `unattributed` from 13000 → 12250 (subtracting the 750 measured assistant output), but T7's
  brief — written by the architect before T13 existed — still pinned `unattributed 13000` and
  never mentioned the new `assistant output (measured)` row. T7 would have failed its own
  acceptance, or worse, its implementer would have "fixed" the engine to match a stale pin.
  Corrected T7 to `12250` + the measured row ranked #1. Also annotated T2's brief (done) as
  SUPERSEDED rather than editing its historical text, so a later reviewer checking T2 against
  its brief does not flag a mismatch. Verified the true post-T13 fixture values empirically
  before patching: measured_growth 20000, attributed 7000, assistant_output_measured 750,
  unattributed 12250.
  **Pattern, third instance this run:** a mid-flight change invalidates downstream pinned
  criteria (T9's stale grep, T12's unsanctioned paths, now T7's attribution pins). Whenever a
  task changes a number the architect pinned elsewhere, grep the whole TASKS.md for that number
  in the same breath.

- **T5 aggregated WITHOUT flattening the ladder — the hazard this task carried.** Each harness
  gets its own section with DIFFERENT columns (Claude: calls/avg/peak/total/compactions/
  sidechain; Codex: points/avg/peak/kind; Copilot: turns/session-average only) and its OWN carry
  cost in its own unit — $ / relative-burn proxy / $+AIC — never summed. Adding them would
  produce a figure with no meaning, and an "overview" page is exactly where that temptation
  peaks. Verified structurally: top-level JSON keys are exactly
  `{schema_version, days, harness_filter, sections}` with no sibling combined field, and both
  pinned honesty lines (Codex no-provenance, Copilot no-curve) survive into the aggregate view —
  the place they are easiest to drop for a tidier layout.
- **Reviewer's deferred sidechain finding is fixed here:** a wholly-sidechain transcript now
  reports `all N call(s) in this transcript are sidechain (subagent) — 0 main call(s), not a
  session with no activity` instead of a silent `0 call(s)` beside a large sidechain figure.
- **Honest fixture note from the implementer (kept, not "fixed"):** `_copilot_fixture_lines`
  carries fixed `2026-06-30` timestamps, so the default `--days 7` window correctly EXCLUDES it
  (Copilot filters by event `last_seen`, mirroring `copilot_usage.py`, not by file mtime). Its
  pinned tests therefore use `--days 400`, and the real `--days`-filtering proof uses Claude
  transcripts with controlled mtimes. Widening the default to make a test pass would have been
  the wrong fix.

outcome: T5 model=sonnet attempts=1 result=pass review=none
agent: T5 id=ab826c598ac400ca4 role=implementer model=sonnet

- **PLAN's "Done looks like" — the task-independent half is ALREADY satisfied** (pre-verified
  mid-run so T9 has no surprises):

  | criterion | state |
  |---|---|
  | `python3 bin/sync_pricing_refs.py --check` | exit 0 ✓ |
  | CLAUDE.md ≤ 16,000 bytes | 10,668 ✓ |
  | off-limits files unmodified (`cost_report`/`session_cost`/`codex_usage`/`copilot_usage`/`data`/`skills/route`/`skills/fable-check`) | `git diff --quiet` exit 0 ✓ |
  | `git status` shows only sanctioned paths | 8 untracked, all sanctioned ✓ |

  Remaining done-criteria all depend on T7: `demo` printing four cards with the D11 pins, and
  `demo --json` round-tripping.
- **The Phase-1 reviewer's `--json` warning is real but ALREADY COVERED by the briefs** — checked
  rather than assumed. Confirmed live that `audit --json` and `demo --json` currently emit the
  unparseable placeholder text (`` `demo` lands in a later task. ``). T6's interface pins
  `audit [--json]` and T7's Tests section explicitly requires
  `main(["demo", "--json"])` + a `json.loads` round-trip assertion, so both resolve as those
  tasks land. **No brief amendment needed** — unlike the three stale-pin defects, the plan had
  this one. Recording the negative result so it is not re-investigated.

- **T6 needed one follow-up — the BRIEF under-specified against D10, the work matched the brief.**
  As delivered, the reframe printed only with `--session`, because the *percentage* needs a real
  avg weight to divide by (correct reasoning, and the brief pinned only that case). But the
  DEFAULT invocation is what users run, and bare `audit` rendered `CLAUDE.md · 53% of budget`
  with no counter-message — inviting exactly the conclusion this kit refutes. D10 says the audit
  "itself PRINTS the reframe" unconditionally. Fixed by adding a QUALITATIVE fallback in the same
  prominent slot (above `budget:`, before the first `##` section):
  `resident surfaces are typically a low single-digit % of per-call weight — the working set, not
  config, is the lever. Run with --session <id> to compute this against a real session.`
  Critically it **fabricates no number** — filling the slot with a plausible-looking percentage
  would have been the easy fix and a direct violation of the honesty discipline every other rung
  holds. Numeric path unchanged and still conditional. Suite 1149, no test-count drift (one test
  replaced, not added).
  Scored **retry-pass**, not pass: T6's own acceptance criteria were met on the first dispatch,
  but a stricter reading of D10 was not. Recording it as a clean first-try would corrupt the
  routing data the next kit's pins are drawn from.
- **Pattern, 5th instance: a brief pinning only the interesting case leaves the DEFAULT path
  unspecified.** (Others: T9's disproven grep, T12's unsanctioned paths, T7's stale `13000`,
  and — checked, no defect — `demo --json`.) For the next architect pass: when a brief pins a
  test case for a flag-enabled path, pin the flag-absent path too, or state that it is
  deliberately unspecified.

outcome: T6 model=sonnet attempts=2 result=retry-pass review=none
agent: T6 id=a4e95eedf256ac75a role=implementer model=sonnet

- **Closed the loop the kit left open: T9 now runs the staleness guard it ships.** The kit
  CREATES exactly the condition `bin/plugin_staleness.py` detects — it adds
  `bin/context_weight.py`, `bin/plugin_staleness.py`, `skills/context-weight/SKILL.md`,
  `docs/CONTEXT-WEIGHT.md` and edits `CLAUDE.md`, none of which exist in the installed 0.2.0
  snapshot — yet T9's close-out never invoked it. Shipping the guard and not using it would have
  left the new `context-weight` skill silently un-invocable, which is the same failure that
  aborted this kit's FIRST run attempt (18-day-stale install).
  Added T9 check 9 with an unusual assertion: **exit 3 (DRIFTED) is the PASSING result.** An
  `in sync` report there would mean the guard is broken, since the drift is certain by
  construction. The check also requires confirming the report names the new files under
  `missing` and does NOT blame the version — repo and installed both read `0.2.0`, because
  content changed and the version string did not. That is precisely the trap that let the
  pre-run install rot for 18 days while `claude plugin update` reported "already at the latest
  version". T9 must SURFACE the printed remedy, not run it.
- Live routing after T6's retry: sonnet first-try 7/8, `--live` recommends no re-route,
  auto-upgrade budget 0/2 used. The single retry was a brief gap, not a model failure, so the
  threshold correctly did not trip.

- **OPEN QUESTION for the Phase-3 reviewer (deliberately NOT actioned by the orchestrator).**
  `watch` (T10) will be the kit's most actionable command — it is the direct answer to the user's
  motivating question, "at 700K of context, what do I do?" — but it will appear in NO cheatsheet:
  T8 pins exactly two CLAUDE.md run-lines (`demo`, `session`), T10 says nothing about CLAUDE.md,
  and T11 explicitly forbids touching it. Discoverability gap, not a correctness defect.
  Not actioned because (a) GUARDRAILS/standing-rules state the ONLY sanctioned existing-file edit
  in this kit is "CLAUDE.md's two pinned run-lines (T8)", so a third line would require amending
  a fence in order to cross it; (b) T11 already requires `watch` to be cited with a runnable
  command inside `skills/context-weight/SKILL.md`, which is where progressive disclosure says
  task-specific guidance belongs (the context-rules lesson: CLAUDE.md holds always-on invariants,
  skills load on demand); (c) the orchestrator has already amended this kit five times and this
  is a preference rather than something that would fail or mislead.
  Reviewer should decide: leave as-is (skill-only), or sanction a third run-line for `watch`.

- **T7 caught an error in the ORCHESTRATOR's own brief correction — and refused to reconcile it.**
  When correcting T7's stale pins earlier, the orchestrator wrote `assistant output (measured)
  750 measured` "ranked #1 inline", over-generalizing from T13's REAL sessions where assistant
  output genuinely IS the largest contributor (309,755 tokens on the live session). In the
  SYNTHETIC demo fixture it is only 750, behind Bash 5,000 and Read 2,000 — so rank 3 is the
  correct output of sort-by-magnitude. Rendered order: `unattributed 12,250 (—)` first by
  magnitude, then Bash 5,000 (1), Read 2,000 (2), assistant output 750 (3).
  Had the implementer obeyed the brief it would have had to inflate the fixture or special-case
  the sort, encoding a fiction into the kit's flagship demonstration. It did neither and reported
  the conflict, exactly as instructed ("do not fix the engine to match a pin, and do not silently
  re-pin to match the engine"). Brief corrected; engine and fixture untouched.
  **Lesson: a pin derived from real-world behavior does not transfer to a synthetic fixture.**
  T13's "ranked inline by size" is the general mechanism; "#1" was an accident of which data it
  was observed on.

outcome: T7 model=sonnet attempts=1 result=pass review=clean
agent: T7 id=abcb623df5e8632ef role=implementer model=sonnet

## Phase 2-3 review (opus): **DRIFT** — and one finding is a FALSE CLAIM IN THIS FILE

All six mechanical axes passed (D3 ladder proven unreachable-by-AST with a positive control; no
cross-harness merge; T13 attribution honest; audit dollar-free with both reframes prominent; demo
fully synthetic and byte-identical under `HOME=/nonexistent`; parsers unmodified; `Path.home()`
call count 0 in both test files). Three drift findings:

1. **CORRECTION TO AN EARLIER ENTRY IN THIS FILE.** The entry above claiming "a wholly-sidechain
   transcript now reports `all N call(s) … not a session with no activity`" is **WRONG about
   where**. That note exists only at `bin/context_weight.py:1240`, inside
   `build_claude_overview_section()` — the `overview` path. The Phase-1 finding was about
   `find_main_transcript`, which only `session` uses. **`session` still has no such guard.**
   Confirmed structurally by AST (the string's enclosing function is `build_claude_overview_section`).
   *Partial correction to the reviewer in turn:* its frequency claim ("70% of transcripts, 19/27")
   is environment-specific — it ran AS A SUBAGENT, so `find_main_transcript` picked its own
   all-sidechain `agent-*.jsonl`. In the main session there are **0 agent-*.jsonl of 8**, and bare
   `session` correctly picks a real 374-call transcript. So the defect is real but rarer than
   stated; it bites subagents and anyone whose newest transcript is sidechain-only.
   → folded into T10 (below), which is the next task touching this surface.
2. **PLAN.md D4 still carried the claim T13 disproved** ("system overhead, thinking, schemas — not
   measurable"). PLAN is declared binding and **T8/T11 write the guide and docs FROM IT** — this
   would have propagated the corrected-then-uncorrected claim into shipped user-facing docs.
   FIXED: D4 now states the corrected version with an `[AMENDED BY T13]` note.
3. **T2's brief pinned the superseded PROSE unannotated** — the stale *number* three lines below
   was marked SUPERSEDED in the same pass, the stale *text* was not. FIXED.

**Reviewer's ruling on the `watch` run-line: LEAVE SKILL-ONLY**, and its reason is better than
mine. Mine was procedural (crossing a fence needs amending it). Its reason is substantive:
**CLAUDE.md is itself a resident surface, re-submitted on every call in every future session.
Spending permanent resident tokens to advertise the command whose purpose is to reduce resident
mass is self-refuting** — and a kit that violates its own thesis in its own wiring loses the
authority to tell users not to. **Condition it attached (in T11's existing scope, not a fence
amendment): skill-only only works if the skill FIRES, so T11's frontmatter `description` must
carry the motivating trigger ("my context is huge", "should I compact") rather than a feature
summary — otherwise "cited in the skill" means invisible.**

**Reviewer on the orchestrator (asked to rule against me): "more coherent in code, more patchwork
in its own record."** Credited T13 (verified against a pre-recorded real-session baseline — called
the strongest verification used in the run), the T7 stale-pin catch, the T6 D10 follow-up, and the
T9 grep→AST fix. Against: the "ranked #1" amendment WAS itself a hazard (caught by the implementer,
not me), and **amendment discipline was one-sided — TASKS.md maintained six times, PLAN.md zero**,
which is exactly what produced findings 2 and 3. Both were documentation, both positioned to
propagate into T8/T11. Standing rule going forward: **when amending a brief, check whether PLAN.md
says the same thing.**

## T8 — done

`skills/context-weight/SKILL.md` + `docs/CONTEXT-WEIGHT.md` + 2 CLAUDE.md run-lines.
Verified: suite 1152 (unchanged — T8 ships docs, not code); CLAUDE.md 10,668 → 11,108 B
(`git diff --numstat` = exactly `2 0 CLAUDE.md`, ceiling 16,000); the unsupported `40%`
metric is cited **zero** times; `watch` referenced as where the live threshold arrives.

D12 (every practice cites a metric the tool reports) forced an honest call on practice #3:
PLAN's version cited "~40% of the window," which nothing measures. T8 scoped the practice to
what `session` prints today and deferred the live threshold to `watch`, rather than citing a
number the tool cannot produce. Named the gap instead of filling it.

**ORCHESTRATOR INSTRUMENT ERROR #5** (same shape as #4). My content grep flagged
`docs/CONTEXT-WEIGHT.md:65` as carrying the OLD "thinking … not measurable" claim. It does —
inside a quotation whose very next clause is "That was wrong about thinking". The doc quotes
the old claim IN ORDER TO CORRECT IT; line 70 carries the corrected engine text. Identical to
the `Path.home()` false positive: **a file that documents a contract will contain the string
that contract forbids.** SKILL.md showed "neither phrasing" for the same reason — it explains
the idea in its own words (line 49) instead of reciting the engine's sentence.
Standing rule, now twice-earned: **never judge a doc by substring presence — check what the
surrounding sentence DOES with the string.** I built `kitcheck.py` to stop exactly this, used
it for the AST checks, then hand-rolled the content check anyway.

outcome: T8 model=sonnet attempts=1 result=pass review=clean
agent: T8 id=agent_t8_impl role=implementer model=sonnet

## T10 — open seam found BEFORE dispatch review (PLAN vs TASKS)

Applying the standing rule from the Phase 2-3 review ("when amending a brief, check whether
PLAN.md says the same thing"), I checked PLAN D15 + the pinned interface against T10's brief and
found the two in tension:

- **PLAN.md:310** — "`watch --harness` is **NOT offered**", and the pinned signature
  (`PLAN.md:306`) lists only `[--session] [--window-tokens] [--projects-dir] [--tasks-dir] [--json]`.
- **TASKS T10** — "a Codex/Copilot **invocation** must exit 0 with the pinned line ...".

Both can hold only under one reading: `--harness` exists on `watch` as a **refusal-only**
argument — accepted, never functional, exits 0 with the honest explanation. If it is truly absent,
argparse exits **2** with "unrecognized arguments", which violates the exit-0 requirement and
gives the user no explanation of the fidelity ladder. Flagged to the implementer at dispatch
rather than resolved by fiat; the verifier judges the choice.

This is the SAME failure shape as findings 2 and 3: a decision recorded in one document and
amended in the other. Caught pre-dispatch this time instead of post-implementation.

## SEAM DEFECT #7 — T9's check 8 pointed at a script that did not exist (repaired pre-dispatch)

T9's brief invokes `.claude/kits/context-weight/_home_check.py` for the AST-based `Path.home()`
guardrail. **That file was never created by any task.** T9 is pinned to **haiku** and instructed
"change NOTHING unless a check fails" — it would have hit `No such file or directory` and either
blocked on a phantom failure, or taken the brief's "or inline: parse with `ast`..." fallback and
improvised an AST parser. A mechanical model hand-rolling the exact instrument that produced FIVE
false findings for me this run is the worst available outcome.

Wrote the helper (kit-local, read-only, `.claude/kits/context-weight/` is already a sanctioned
path in check 6). It counts only `Call(func=Attribute(value=Name("Path"), attr="home"))`, takes
`--expect N` for the engine's sanctioned 3, exits 2 on missing/unparseable input, and its
docstring records WHY grep is wrong here. Validated against both invocation forms in the brief:

    tests/test_context_weight.py:   0 call(s), expected 0 — ok
    tests/test_plugin_staleness.py: 0 call(s), expected 0 — ok
    bin/context_weight.py:          3 call(s), expected 3 — ok at line(s) 191, 196, 197
    grep -c 'Path.home()' tests/test_context_weight.py -> 2   (BOTH matches are prose)

Note the engine's sanctioned calls have MOVED — the brief and earlier notes say ~148/153/154;
T13's additions shifted them to **191/196/197**. Count unchanged at 3, so the guardrail holds;
recorded because line numbers in briefs age and the next reader should not treat the shift as drift.

The helper generalizes past this kit: it is the correct form of a check every future kit with a
`Path.home()` fence will otherwise hand-roll.

## Pre-T10 baseline (recorded BEFORE the implementer returned — makes its claims falsifiable)

Same technique the Phase 2-3 review credited as the run's strongest verification (used for T13).
State of `python3 bin/context_weight.py session` on the real transcript, before T10 lands:

    "% of window" / "percent of window" present ....... 0   (review finding 2 CONFIRMED)
    "avoidable" mass line present .................... 0   (review finding 3 CONFIRMED)
    "sidechain" note on the session path ............. 0   (review finding 1 CONFIRMED)
    `context_weight.py watch` ................. exit 2     (subcommand absent, as expected)
    widest output line ........................ 1238 chars

All three review findings independently reproduced against real output rather than taken on the
reviewer's word. T10 must move all four numbers or its claim of done is false.

**Finding 4 was UNDERSTATED, not overstated.** The review said the sparkline runs "373 chars at
373 calls"; the real line is **1,238 characters** (line 7, `growth curve: ▁▁▁...`). The next
widest line in the whole card is 147. So the curve is ~8× wider than any other element and wraps
roughly a dozen times in an 80-col terminal — the plateau shape that D12 practice #3 tells users
to read is not merely degraded, it is unreadable. The ~60-char downsample target stands, and the
gap to close is 1238→60, not 373→60.

Notable given this run's pattern: every earlier discrepancy I chased ended with the implementer
right and my instrument wrong (5×). This is the first where checking the reviewer's number found
the REPORTED figure too generous. Direction of error is not predictable — which is the argument
for measuring rather than trusting, in both directions.

## The kit is now the heaviest thing in the repo it was built to lighten

Measured while T10's implementer was still reading (its target files were untouched at 07:34,
last written 00:03 — a 102 KB engine takes a while to ingest before the first edit). Sizes use
the engine's own `EST_CHARS_PER_TOKEN = 4`, so the methodology matches what the tool reports;
figures are `est.` and deliberately NOT priced (D5/D9).

    bin/context_weight.py ............ 102,300 B ~ 25,575 est. tokens
    tests/test_context_weight.py ...... 81,663 B ~ 20,415 est. tokens
    .claude/kits/.../TASKS.md ......... 49,819 B ~ 12,454 est. tokens
    .claude/kits/.../NOTES.md ......... 32,494 B ~  8,123 est. tokens
    .claude/kits/.../PLAN.md .......... 26,339 B ~  6,584 est. tokens
    ------------------------------------------------------------------
    kit total ....................... 294,833 B ~ 73,708 est. tokens

**Every implementer dispatched at the engine must ingest ~25,575 est. tokens before it can
change one line.** That is the single largest per-dispatch cost in the run, it is paid cold on
every fresh fan-out, and it is the strongest justification the run produced for the warm-sidekick
mode the execute skill offers — a cluster reads it once, a fan-out reads it N times.

This is the same self-refutation the Phase 2-3 reviewer caught on the CLAUDE.md run-line
("spending permanent resident tokens to advertise the command whose purpose is to reduce resident
mass"), showing up a second time at the artifact level rather than the wiring level. The reviewer
was right that the principle generalizes; it generalizes further than either of us applied it.

Honest framing for the end-of-run report and for T11's "what this skill CANNOT do": the kit does
not reduce context — **it measures context, and measurement has mass.** A user installing this
pays resident tokens for the skill in order to learn where their resident tokens go. That trade
can be worth it, but the guide must state it rather than let the reader assume the tool is free.
Do NOT let this become a claim that the kit is self-defeating: the engine and tests are on-disk
files read on demand, not resident surfaces, and only the SKILL.md fraction is ever resident.
The distinction between on-demand mass and resident mass is the kit's own core teaching — apply
it here too.

## CORRECTION to the pre-T10 baseline — two of my numbers were wrong (errors #6 and #7)

**LIVE REPRODUCTION of review finding 1, unplanned.** Running `session` while the T10 implementer
was working returned:

    # Context weight — session agent-a49523d4cfd5e71c9 (claude)
    Scanned 1 file(s), 0 call(s).
    avg weight 0 · peak weight 0 · total submitted 0
    | 1 | assistant output (measured) |  | 0 measured |

`find_main_transcript` picked the **subagent I had just dispatched**. Zero-valued rows labeled
"measured", presented as fact. This is no longer a reviewer's reconstruction — it is reproducible
on demand: dispatch any subagent, run `session`, get a card describing the subagent instead of the
session. **Dispatching a subagent CAUSES the bug for anyone running `session` concurrently**, so
during kit execution — when this tool is most likely to be used — it is close to the common case.

**ERROR #6 — the sparkline is ~422 chars, not 1,238.** I measured with `awk '{print length}'`,
which counts BYTES in this locale; the sparkline blocks (▁▃▄) are 3-byte UTF-8. 1,238 bytes ÷ ~3
≈ 408 curve chars + the `growth curve: ` prefix. The real session has 408 calls, so the curve is
~408 chars — almost exactly the review's "373 chars at 373 calls". **My claim that the review
UNDERSTATED finding 4 was wrong; the review was accurate.** The ~60-char downsample target is
unchanged and still correct — 422 ≫ 60 — but the gap is 422→60, not 1238→60.
First error this run in the OVERSTATING direction; the previous five all invented failures.
Rule earned: for terminal-width claims, count CHARACTERS in Python, never `awk length` on UTF-8.

**ERROR #7 — my frequency caveat in T10's brief is false.** I wrote "0 of 8 transcripts are
`agent-*.jsonl` in the main session, so this is rarer than the review's 70%". I globbed the
PROJECTS dir; subagent transcripts live in the session's TASKS dir, which is where `session` just
found one. I corrected the reviewer using a check that looked in the wrong directory, and the
reviewer's figure was closer to reality than my correction to it. The brief's code requirement is
unaffected (add the note either way), so T10 was NOT re-dispatched — only the emphasis was wrong.

**The baseline's structural rows still stand** — `% of window`, `avoidable`, and `sidechain` were
absent because the engine never emits them, which no measurement window changes. Only the WIDTH
number was volatile, and it was volatile for a second reason beyond my byte/char error: `session`
reads whichever transcript is newest, so its output is a moving target while any agent is running.

**Verification upgrade this unlocks:** T10's sidechain fix can now be verified END-TO-END against
a real reproduction — dispatch an agent, run `session`, confirm the note appears — instead of only
against a synthetic fixture. Use that as the acceptance evidence.

## Follow-ups after this kit closes (user-confirmed 2026-07-25)

1. **Bump `.claude-plugin/plugin.json` version + refresh the install.** MUST come AFTER T9 —
   check 9 requires repo and installed to BOTH read `0.2.0` (content drifted, version string did
   not, which is the trap it exists to detect). Bumping early destroys the condition under test.
2. **Build the `bench-routing` skill** — user confirmed as the next feature after this kit.
   Point it at GitHub repos matching the user's real use cases; harvest tasks from closed
   PRs/issues (the merged diff is ground truth); replay each across haiku/sonnet/opus/fable;
   score first-try pass, retries, dollars. Reuse `bin/routing_scorecard.py` as the reporting
   layer — it already computes first-try rate, model mix, and the all-frontier counterfactual,
   but only retrospectively over kits already run (small sample, self-selected). Repo-derived
   tasks make it PREDICTIVE, which is what sets the `model:` pin architect writes into every
   future kit.
   Known hazard to scope BEFORE building: a merged diff is *a* correct answer, not *the* correct
   answer — scoring needs a judge model, and the judge is itself a cost that must be priced from
   `data/pricing.json` like everything else here. Cheap v1: one repo, ~20 merged PRs, two models.

## T10 — done (retry-pass, revised)

`watch` + `classify_prunable` + all four Phase 2-3 review additions. Suite **1152 → 1177** (+25).

Verified against the pre-recorded baseline (every number moved):

    watch ................ exit 2 -> exit 0
    % of window .......... absent -> "peak 99% of window (993,900 of 1,000,000 tokens)"
    avoidable mass ....... absent -> present, window-scale
    growth curve ......... ~422 chars -> 74 chars
    sidechain guard ...... absent -> fires correctly (forced end-to-end, below)
    classify_prunable .... absent -> defined, PURE by AST (no I/O, no globals)
    refusal line ......... byte-exact IN OUTPUT, exit 0
    Path.home() .......... engine 3 sanctioned / tests 0

**Sidechain guard verified END-TO-END against the live reproduction**, not a fixture: pointed
`session` at the T10 implementer's own transcript and got
`all 459 call(s) in this transcript are sidechain (subagent) — 0 main call(s), not a session with
no activity`. Covered by `test_sidechain_only_transcript_gets_a_note_not_a_silent_zero`.

**REAL DEFECT found and fixed on retry — units mismatch in review addition 3.** Shipped as
`avoidable ... 73,267 est. of 260,544,829 (0%)`: numerator window-scale, denominator
`total_submitted` (cumulative across 408 calls, ~260x the window). It rounded to **0%** — re-creating
the "nothing to do" reading the line existed to eliminate, more strongly than omitting the line.
Fixed to the peak-call weight: `74,160 est. of 993,900 (7%)`. Found by checking the OUTPUT against
the brief's own spec example (`34,333 of 905,000 (4%)`), not by any test — the verify command
passed the whole time. **Presence-checking verify commands cannot catch a wrong denominator.**

**The regression test was MUTATION-TESTED, not trusted.** Reverting the denominator in the real
file made it fail `AssertionError: 565000 != 5000`; file restored byte-identical (SHA-256 verified
before/after). A passing test is not evidence a test can fail — this is the first time this run
that a test was proven capable of catching the bug it claims to cover. Adopt for future kits.

**Out-of-brief change ACCEPTED:** `"totalNanoAiu": 1000000` -> `1_000_000` in T4's synthetic fixture,
to clear a false-positive collision with the verify's `! grep '1000000'`. Proven inert — identical
runtime value, identical serialized JSON, T4's pinned 17,000/8,000/21,000 and 10%/6%/4% all intact.
Disclosed rather than buried. Noting the shape for the record though: this is code bending to fit a
check, and the cleaner fix was to narrow the grep. Harmless here; would not be harmless in general.

**ORCHESTRATOR INSTRUMENT ERRORS #7 AND #8** (running total: 8).
 #7 — flagged the sidechain note "missing" using an UNCONDITIONAL check on a CONDITIONAL feature;
      absent on a main transcript is CORRECT. Same shape as #4.
      Also flagged the refusal line by searching SOURCE (it wraps across lines) instead of OUTPUT.
 #8 — the mutation harness itself was wrong first: PYTHONPATH cannot override the test's
      `spec_from_file_location(name, BIN_DIR / ...)` absolute-path load, so the "mutated" run
      silently tested the REAL engine and passed. Nearly recorded as "the test is weak."
Tally: my checks have now produced 8 false findings against 1 real defect found. The real one came
from reading OUTPUT against the spec; nearly all the false ones came from grepping SOURCE.
**Standing rule for the rest of this kit: verify behavior at the interface, not by inspecting source.**

outcome: T10 model=sonnet attempts=2 result=retry-pass review=revised
agent: T10 id=a49523d4cfd5e71c9 role=implementer model=sonnet

## SEAM DEFECTS #8 AND #9 — both inside T11's own acceptance, caught pre-dispatch

**#8 — the acceptance contradicted the reviewer's condition it was supposed to enforce.**
Acceptance said "SKILL.md frontmatter byte-unchanged from T8". The reviewer's condition (recorded
in the same task) requires REWRITING `description`, which IS frontmatter. Unsatisfiable as written.
T8's shipped description opens `Measure what fills the context window each turn — per-call token
weight, growth curve, ranked contributors...` — a feature summary, exactly the shape the condition
forbids. Resolved in favor of the reviewer's condition (later, substantive); the byte-unchanged
clause was the stale half. Amended acceptance now pins `name:`/`allowed-tools:` unchanged and
requires `description:` to carry >=2 of the motivating user-phrasings within the ~2-sentence cap.

**#9 — the guard protecting that frontmatter COULD NEVER FAIL.** The verify ran
`! git diff -- skills/context-weight/SKILL.md | grep -qE '^[-+](name:|description:)'`.
`skills/context-weight/` is UNTRACKED (`?? skills/context-weight/` in git status), so `git diff`
on that path emits NOTHING, `grep -q` exits 1, and the leading `!` inverts it to PASS —
unconditionally, forever. Verified empirically before amending, not assumed. It would have waved
through any frontmatter edit including the exact one it existed to forbid.

Same family as the T9 grep defect and the T13 fixture-delegation issue: **a check that cannot fail
is not a check.** Replaced with a Python frontmatter assertion that works on an untracked file and
FAILS LOUDLY on a missing trigger, a changed `name:`/`allowed-tools:`, or an over-long description.

Standing rule earned (generalizes past this kit): **any verify clause built on `git diff` is
vacuous for files this kit CREATES — they are untracked until commit.** Kits that ship new files
must assert on file CONTENT, never on a diff. Worth carrying into the architect skill's guidance.

Swept the rest of TASKS.md for the same `git diff --`-on-untracked pattern: no other occurrence.
PLAN.md checked per the standing amendment rule — its line 119 ("never touch existing skills'
frontmatter") governs PRE-EXISTING skills, not this kit's own new one, and line 342's ~2-sentence
tripwire agrees with the amendment. No PLAN change needed.

## T11 — done (first try, clean)

Guide-skill sections + `docs/CONTEXT-WEIGHT.md` live-threshold section. Suite 1177, unchanged
(docs task). Verified at the INTERFACE per the standing rule, not by grepping source:

    frontmatter ..... name/allowed-tools unchanged; description carries ALL FOUR triggers
                      ("context is huge", "700K", "should I compact", "cache reads"), ONE sentence
    ordering ........ "What this skill cannot do" at line 9 — first body section, before the
                      reframe (30) and well before the practices (121)
    levers .......... PREVENT (47) > PRUNE (51) > MEASURE (54), correct priority
    checkpoint ...... line 161, names NOTES.md and tasks/todo.md concretely
    commands ........ ALL FOUR cited commands EXECUTED: session/overview/audit/watch, every exit 0
    files ........... mtimes prove only SKILL.md (08:47:41) + docs (08:47:55) touched; engine
                      and tests untouched since T10; CLAUDE.md untouched since T8

**Used mtimes, not `git status`, to prove which files were touched** — the direct application of
seam defect #9. `git status` cannot show WHICH untracked file changed, only that untracked files
exist, so it would have been the same vacuous check all over again. Instrument chosen to fit the
tracking state of the artifact.

**The implementer corrected the orchestrator, and was right.** I supplied `bin/context_weight.py
~= 25,575 est. tokens` as writing material; T10's additions had since grown it to **32,453 est.
tokens**. My figure was accurate WHEN MEASURED and stale by the time it reached the writer. Rather
than print either number it wrote a reproducible command into the skill (`wc -c
bin/context_weight.py`, chars/4, "check it yourself, the number drifts as the engine grows"). That
is the better artifact: the same run has now been bitten by stale pinned numbers in T7's brief,
PLAN D4, T9's line numbers, T10's frequency caveat, and here. **Pinned numbers age; commands do not.**
Carry into architect: prefer a runnable command over a literal wherever a doc must cite a measurement.

It also cleared a claim of T8's that T10 made stale ("a live threshold check is not shipped yet")
without being asked — the amendment discipline the Phase 2-3 review demanded, applied by an
implementer to a file it did not write.

The "measurement has mass" honesty point landed with the on-demand vs resident distinction intact
(SKILL.md:14-18), so the kit states its own cost rather than hiding it.

outcome: T11 model=sonnet attempts=1 result=pass review=clean
agent: T11 id=a97ab6aadb7223c26 role=implementer model=sonnet

## T9 — done (first try, clean). KIT COMPLETE: 13/13.

Final sweep on **haiku** — the run's only haiku task — 9 of 9 checks passed, all output shown.
Independently re-ran checks 4, 5, 7 and the suite myself; every figure matched its report.

    suite ......................... 1177 tests, OK (baseline 1022, +155)
    demo .......................... exit 0, four cards, pinned 17,000/8,000/21,000 + 10%/6%/4%
    demo --json ................... round-trips through json.loads
    sync_pricing_refs --check ..... exit 0
    CLAUDE.md ..................... 11,108 B (ceiling 16,000)
    reuse-only surfaces ........... clean (cost_report, session_cost, codex_usage,
                                    copilot_usage, data, skills/route, skills/fable-check)
    Path.home() ................... engine 3 sanctioned (229/234/235) / both test files 0
    plugin_staleness .............. exit 3 = DRIFTED = PASSING

**Check 9 behaved exactly as designed, and its report is the proof the guard works:**
`version: repo 0.2.0 vs installed 0.2.0 — match` beside `git HEAD ... MISMATCH`, with
`missing bin/context_weight.py`, `missing bin/plugin_staleness.py`,
`missing skills/context-weight/SKILL.md`, `DIFFERS CLAUDE.md`. Content drifted while the
version string did not — precisely the trap that left the pre-run install 18 days stale. An
`in sync` here would have meant the guard was broken.

**Orchestrator caveat on check 6 (not a failure, a known blind spot).** `git status --porcelain`
collapses an untracked DIRECTORY to a single `??` line, so a stray file inside
`.claude/kits/context-weight/` or `skills/context-weight/` would never appear. Same family as
seam defect #9. Expanded both dirs with `find` — the only file beyond the kit's own artifacts is
`_home_check.py`, which the orchestrator wrote to repair T9's missing-helper defect. Clean.
Carry into architect: **for kits that ship new files, sanctioned-path checks must enumerate files,
not trust `git status` to expand directories.**

**PLAN's overall DONE check: ALL GREEN** (suite, demo exit 0, demo --json round-trip,
sync_pricing_refs exit 0, CLAUDE.md under ceiling, reuse-only surfaces clean, all six
deliverables present).

outcome: T9 model=haiku attempts=1 result=pass review=clean
agent: T9 id=aa3662799288feb13 role=implementer model=haiku

## DEFECT in the execute skill's own session-id recipe (found at close-out)

`skills/execute/SKILL.md` resolves the run's session id with
`ls -t "$HOME/.claude/projects/$(pwd | sed 's|[^A-Za-z0-9]|-|g')"/*.jsonl | head -1`.
That assumes the session's project slug matches the CURRENT working directory. It does not when
the session STARTED somewhere else — this run began at `~` and later worked in
`.../reposV2/polytropos`, so the recipe looked in
`-path-to-polytropos` and returned
`a1a5c610-...` — a **1,343-byte transcript from 22:37 yesterday, belonging to a different session**.

**It did not fail; it returned a confidently wrong id.** The skill's guard says "if the lookup
finds nothing, or a concurrent session makes it ambiguous, skip — never record a guessed id", but
this failure mode produces a plausible, non-empty, WRONG answer that trips no guard at all. Silent
wrong beats loud missing every time in how bad it is: the cross-kit routing history would have
attributed this entire 13-task run to an unrelated 1.3 KB session.

Correct id resolved by mtime instead: `fc6c2eb3-...` — 7,343,983 B, mtime 08:54:26 against a
wall clock of 08:54:30, i.e. still being written. Next candidate was 22:43 YESTERDAY. Unambiguous.

**Fix to carry into `skills/execute/SKILL.md` (out of this kit's scope — do NOT edit it here;
that file is a fenced non-target):** resolve the transcript by RECENCY OF WRITE across the
projects dirs, or sanity-check the candidate (a live session's transcript has an mtime within
minutes of now and is not a few kilobytes), rather than trusting a pwd-derived slug.
