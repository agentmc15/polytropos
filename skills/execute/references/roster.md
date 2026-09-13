# Roles roster — optional extended roles, measured

Detail moved out of `skills/execute/SKILL.md` by roadmap step 22 so the entry point carries the mandatory loop; the text below is the binding grammar it points at, unchanged.

PLAN.md may declare an OPTIONAL `roles:` line — a PLAN.md line family exactly like `autonomy:` and `budget:`, **never a task field**, read once at Setup:

    `roles: <token> <token> ...`

Read it, and the optional `workflow:` line (`reviewed` = the trio, default; `extended` = trio + declared roles; `direct` = implementer and deterministic checks only, named on purpose, never beside `roles:`), through the shared grammar: `python3 ${CLAUDE_PLUGIN_ROOT}/bin/kit_contract.py roster --kit .claude/kits/<slug>` prints the roster and each contract (`--json`); a grammar error exits 2 before any dispatch. Headless drivers refuse or disclose a role they cannot sequence (`--roster-gap`); you sequence every declared role at the hooks below, and independent review stays binding unless the workflow is `direct`.

Tokens come from exactly seven: `scout`, `test-author`, `second-verifier`, `red-team`, `security-auditor`, `docs-editor`, `synthesizer` — the optional pipeline roles a kit adds beyond the standing trio (implementer / verifier / reviewer). Absent line = the trio, today's behavior everywhere: no extra dispatch, no extra ledger line, and every kit written before this dial existed runs exactly as it always has. Dispatch each declared role to the kit's `<slug>-<role>` agent (the architect instantiates one per declared role from its templates); if a declared role has no agent file, dispatch it with the Agent tool directly on the template's default model and say so in your report.

**Hook points, pinned.** A declared role runs at exactly one place in the loop, and nowhere else:

- `scout` — before a declared-roster task's implementer dispatch (step 2). You MAY skip it per task when the task needs no grounding; every dispatch you actually make is recorded.
- `test-author` — after the implementer claims done, before the verifier. Its failing tests are FINDINGS, not a verdict: hand them to the implementer as the retry evidence of step 5.
- `second-verifier` — in parallel with the verifier (step 3), carrying a stated different lens. Like the verifier it is always a fresh spawn, never warmed.
- `red-team` — after verify passes, before the task is marked `done` (step 4).
- `security-auditor` — phase end (step 6), in parallel with the reviewer.
- `docs-editor` — phase end, after the review's findings are adjudicated.
- `synthesizer` — end of run, before you write the report.

**Consequence rules — what a confirmed catch triggers.** Recording a catch is not the same as acting on one, so each finding-producing extended role has ONE pinned consequence:

- `test-author` — a failing test is FINDINGS, not a verdict: hand it to the implementer as step 5's retry evidence, exactly as its hook point above states.
- `red-team` — a confirmed break on a task that already PASSED verify is treated as a failed verify: feed it to the implementer as step 5's retry evidence, and a second failure blocks the task. A confirmed break is never recorded-and-shrugged into `done`.
- `security-auditor` — a confirmed fence violation at phase end is PHASE-BLOCKING, with the same standing as a blocking reviewer finding: fix it before the next phase's first dispatch.
- `docs-editor` — a confirmed drift rides the phase boundary: dispatch the fix, or fold it into the next task. It never blocks the run.

Stated once for all four: consequence rules change nothing about RECORDING. The `agent:` line is appended the moment the dispatch returns, whatever the catch does or does not trigger — the ledger records what ran and what it found, never what you decided to do about it.

**Recording — every declared-role dispatch appends an `agent:` line.** The seven role tokens join `implementer`/`verifier`/`escalation` in that family's `role=` vocabulary; no new line family exists for them, and NOTES.md's machine-read families stay the SIX named above. The task slot depends on the role's scope:

- per-task roles (`scout`, `test-author`, `second-verifier`, `red-team`) — the task id, exactly like an implementer or verifier line.
- phase-scoped roles (`security-auditor`, `docs-editor`) — the PHASE token (`P1`) in the task slot; the parser's task field is freeform. The never-split law above is unchanged for them: their per-phase transcripts still land in the breakdown's unattributed line, which is why their per-task dollars read n/a in the `--roles` card.
- `synthesizer` — the token `-` in the task slot (the `defect:` family's precedent for a kit-level record), because it is run-scoped.

`findings=`/`confirmed=` carry exactly the counting and adjudication rules already stated for the agent ledger: count the verdict's distinct claims as the verdict itself presented them, and a finding is confirmed only when it produced a concrete artifact. The roster adds ONE optional field to that same line:

    `agent: <task-id|phase|-> id=<agent-id> role=<role> model=<model> [findings=<n> confirmed=<n> marginal=<n>] [result=<accepted|revised|blocked>]`

- `marginal` (optional; meaningful only alongside `findings=`/`confirmed=`, and constrained `0 ≤ marginal ≤ confirmed`) — of the CONFIRMED findings, how many no EARLIER layer of the pipeline raised on that task (or on that phase, for phase-scoped roles). This is the number that answers "did this role pay?"; adjudicate it at the same moment you adjudicate `confirmed=`, and never revisit it afterwards.

**The canonical pipeline order**, written out in full here — this is what "earlier layer" means, and it is the only order `marginal=` is adjudicated against:

    scout → implementer → test-author → verifier → second-verifier → red-team → reviewer → security-auditor → docs-editor → synthesizer

Two pairs run in parallel, so state their tiebreaks the same way every time: a finding raised by both the verifier and the second-verifier is the VERIFIER's (not marginal for the second-verifier); a finding raised by both the reviewer and the security-auditor is the REVIEWER's (not marginal for the security-auditor). A finding is never counted marginal twice.

Deflationary defaults are the law of `marginal=`: unsure = not marginal; a finding with no artifact = not confirmed, hence never marginal. An absent `marginal=` means unmeasured, never zero — legacy lines carry none and the scorecard reads them as marginal-unmeasured — so never back-fill one onto an adjudication already made. And as with every ledger token, backtick `roles:`, `agent:`, `marginal=`, and the role tokens whenever you quote them in NOTES.md prose: an unbackticked line that starts with a family token parses as real data.

**The dial is measurement, not mandate.** Declared roles run in order to be MEASURED: `python3 bin/routing_scorecard.py --roles` renders the per-role value table — dispatches, findings, confirmed, marginal, precision, marginal rate over the dispatches where marginal was actually adjudicated, and dollars only where transcripts priced them — with "insufficient sample" below the evidence floor rather than a number the sample cannot support. Dropping a role that is not earning its marginal keep is the EXPECTED outcome of measuring it, not a failure of the run. That decision belongs to the human, BETWEEN kits: never add, drop, or substitute a role mid-run because the numbers look thin so far. Report what the roster measured at end of run, and let the next kit's PLAN.md act on it.

**A declared roster shifts `attempts=` — and that is not implementer regression.** Declaring `test-author` (and `red-team`, whose retry path is pinned above) structurally INCREASES `attempts=` on exactly the tasks whose defects those roles catch before `done`: a defect that would once have shipped now costs a retry instead. So per-tier first-try rates in `--history` will dip on R5+ kits at identical model quality — the dip is the roster working, not the implementer getting worse. Read those rates tier-vs-tier only across kits with the SAME roster, and never read a roster-driven dip as evidence for re-pinning a tier down.
