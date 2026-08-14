# role-roster — a 3→10 role system, measured for marginal value

autonomy: advisory

## Goal

Make the kit execution loop's role roster configurable from today's trio (implementer /
verifier / reviewer) up to ten roles — adding scout, test-author, second-verifier,
red-team, security-auditor, docs-editor, and synthesizer as OPTIONAL, per-kit declared
roles — and instrument the ledger + scorecard so the question "does each extra role pay?"
is answered by measurement (marginal catches vs measured cost), never by vibes. "Done":

- A kit's PLAN.md may carry a `roles:` line (a PLAN.md line family exactly like
  `autonomy:`/`budget:` — never a task field); absent = the trio, today's behavior, so
  every existing kit and ledger stays valid.
- Seven generic role templates exist for the architect to instantiate as kit-prefixed
  agents; the architect and execute skills specify declaration, hook points, and
  recording; the shared kit contract is unchanged and rechecked in both files.
- `agent:` ledger lines accept the seven new role tokens plus an optional `marginal=`
  field (confirmed findings no earlier layer caught, orchestrator-adjudicated exactly
  like `confirmed=`).
- `python3 bin/routing_scorecard.py --roles` (and `--demo --roles`) renders the per-role
  value table: dispatches, findings, confirmed, marginal, precision, marginal rate,
  dollars where transcripts price, roster tier per kit — with "insufficient sample"
  honesty below the floor. All four existing byte-goldens and all three 9-key card locks
  pass unchanged.
- Full suite green.

## Why this design (measurement method)

User chose marginal-catch instrumentation on real kits over paid A/B replay. The unit of
evidence: when a role's findings are adjudicated, the orchestrator also adjudicates how
many confirmed findings were NEW — caught by no earlier pipeline layer on that task or
phase. This week supplied the proof-of-concept three times over: the P2 harness-update
reviewer's codex-prompts catch and both graphify-skill review catches were marginal
catches over clean verifier passes. Cost per role comes from the `--by-task` transcript
pricing machinery that already exists. Roster size per kit is DERIVED from observed role
tokens — zero new line families.

## The ten roles

| # | role token | hook point | default model | writes? |
|---|---|---|---|---|
| 1 | implementer | per task (exists) | task pin | yes |
| 2 | verifier | post-implementer (exists) | sonnet | read-only pinned |
| 3 | reviewer | phase end (exists; `reviewer:` family) | opus | read-only pinned |
| 4 | scout | pre-implementer grounding, per task when declared | haiku | read-only pinned |
| 5 | test-author | post-implementer, pre-verifier: writes adversarial tests from the BRIEF, not the implementation | sonnet | yes (tests only) |
| 6 | second-verifier | parallel with verifier, different lens | sonnet | read-only pinned |
| 7 | red-team | post-verify, pre-done: actively try to BREAK it | sonnet | read-only pinned |
| 8 | security-auditor | phase end, parallel with reviewer: leak/injection/fence lens | sonnet | read-only pinned |
| 9 | docs-editor | phase end, post-review-adjudication: docs/comments vs changed behavior | haiku | yes (docs only) |
| 10 | synthesizer | end of run: distill NOTES learnings | haiku | yes (NOTES prose only) |

Roster tiers, so "3 to 10 and everything in between" is comparable across kits:
**R3** = trio (absent `roles:` line). **R5** = +test-author +red-team. **R7** = +scout
+second-verifier. **R10** = +security-auditor +docs-editor +synthesizer. A kit may
declare any subset — tiers are the recommended comparison ladder, not a constraint; the
scorecard labels each kit R<n> by distinct roles observed.

## Constraints and out-of-scope

- **Out of scope:** the headless drivers (`bin/*_execute.py` never write `agent:` lines
  today, so extended roles simply do not appear in driver runs — a future kit may add
  ledger emission there; this one changes zero driver code); copilot/codex bundle parity
  (Claude-side first); any auto-application of roster recommendations (evidence advises,
  the human decides — same law as re-routing); the paid A/B replay harness (user chose
  against); retro-fitting `marginal=` onto ledgers already written (absence means
  unmeasured, never zero).
- Task-field contract unchanged, absolutely: `roles:` is a PLAN.md line family; no new
  task fields, no status vocabulary change, no phase-heading change.
- Stdlib-only, unittest only, no real-CLI invocation, temp fixtures only.
- CLAUDE.md stays ≤ 16,000 bytes (currently 14,511).

## Architecture & key decisions

- **D1 — Extend `AGENT_ROLES`, as a documented supersession.** The role-ledger kit's own
  D1 pinned `AGENT_ROLES = ("implementer", "verifier", "escalation")` with
  `tests/test_role_ledger.py:59` (`test_agent_roles_untouched`, comment "D1 must not
  extend AGENT_ROLES"). This kit supersedes that decision deliberately: the tuple grows
  to ten tokens (trio + escalation + the seven), and the fence test is REPLACED by
  `test_agent_roles_extended_exactly` pinning the new tuple with a comment naming this
  kit and the supersession. *Why extension beats a new line family:* `--by-task`'s JSON
  buckets are already dynamic (`roles.setdefault(e["role"], ...)`), so dollars-per-role
  flows free; a parallel family would duplicate the whole agent-parsing/cost pipeline.
  *Why it is safe:* old ledgers contain no new tokens — parsing of every existing line
  is byte-identical, and the `chef` out-of-vocab probe still drops (chef is not in the
  extended set), so the four byte-goldens hold.
- **D2 — `marginal=` rides the existing `agent:` line.** Optional; meaningful only
  alongside `findings=`/`confirmed=`; constraint `0 ≤ marginal ≤ confirmed`; violations
  degrade `marginal` to None with a note while the line survives (mirroring the
  findings/confirmed degradation semantics). Adjudicated by the orchestrator at the
  moment findings are adjudicated: a confirmed finding is MARGINAL iff no earlier
  pipeline layer on that task (or phase, for phase-scoped roles) raised it.
  [AMENDED at P1 review — the original sentence pointed at "the table above", whose
  numbering is NOT the pipeline order; kit-level `defect:` stale-plan-decision logged.]
  The canonical pipeline order, authoritative here and restated verbatim in execute's
  skill by T5:
  scout → implementer → test-author → verifier → second-verifier → red-team → reviewer →
  security-auditor → docs-editor → synthesizer.
  Parallel-pair tiebreaks, stated once: a finding raised by both verifier and
  second-verifier is the VERIFIER's (not marginal for second-verifier); one raised by
  both reviewer and security-auditor is the REVIEWER's (not marginal for
  security-auditor). A finding is never counted marginal twice.
- **D3 — Measurement is a NEW view, never a mutation of locked surfaces.**
  `--roles` is its own render (and its own card JSON) — nothing is added to the 9-key
  history card, `role_quality_stats`' 4-key return, or the `--history` markdown, so
  `tests/test_routing_history.py:666`, `test_crossrepo_trend.py:390`,
  `test_role_ledger.py:642`, and all four byte-goldens pass untouched. The `--by-task`
  markdown gains one ADDITIVE rendering: when a task row carries dollars in a
  non-trio role, an indented per-role extras line prints under the row (the three-column
  table is unchanged; JSON was already dynamic). *Why:* the reviewer-precedent
  (`## Role quality` updated goldens) is available but unnecessary — a separate view has
  zero blast radius.
- **D4 — Honesty rules of the `--roles` card.** Per role: dispatches, findings,
  confirmed, marginal, precision (None-not-zero when unmeasured), marginal rate, dollars
  only where transcripts actually priced (basis labeled, never summed across bases), and
  "insufficient sample" below MIN_ROLE_DISPATCHES = 5.
  [AMENDED at P1 review:] the marginal CELL renders "n/a" when zero dispatches carry a
  measured `marginal=` (never a fabricated 0), and the marginal RATE's denominator is
  MEASURED dispatches only (marginal ÷ marginal-measured), with the unmeasured count
  beside it — a rate diluted by unmeasured dispatches understates a role's evidence.
  Aggregate cost-per-marginal renders only when every contributing record is priced on
  one basis (single-record today; a multi-kit mix of priced and unpriced records renders
  n/a with a note, never a blended figure). The card's legend names the structurally
  unmeasurable cells: phase/run-scoped roles (security-auditor, docs-editor, synthesizer)
  can carry no per-task dollars under the never-split law, and the indirect-value roles
  (scout, docs-editor, synthesizer) produce no adjudicable findings by design — their
  rows are dispatch-cost only, which the legend says in words.
  Cost-per-marginal-catch renders only when BOTH sides are measured. A role with zero
  recorded dispatches is absent, not zero. Escalation is excluded from the value table
  (it delivers fixes, not verdicts — existing law). Legacy verifier/reviewer lines
  without `marginal=` count as "marginal unmeasured", never as marginal=0.
- **D5 — Roster derivation, not declaration-tracking.** A kit's roster = distinct role
  tokens observed in its ledger (`agent:` roles + `reviewer:` family presence + implicit
  implementer from outcomes). The scorecard labels it R<n>. *Why:* zero new grammar, and
  it measures what actually RAN, not what PLAN.md promised.
- **D6 — Templates live in `skills/architect/references/roles/`.** Seven files, one per
  new role, each a complete agent-file skeleton with `<slug>` placeholders: frontmatter
  (name/description/model default/tools pin per the table), the role's mission, its hook
  point, its recording contract (what its findings mean, what the orchestrator will
  adjudicate), and — for every read-only role — the damage-restore practice paragraph
  verbatim from the architect skill's tools-pinning law. Write-capable roles
  (test-author, docs-editor, synthesizer) get scoped write missions instead of pins,
  stated as: touch ONLY <tests/docs/NOTES prose>; anything else is your defect.
  *Why references/:* `.claude/agents/` has zero test coverage but is the live-install
  surface — templates are architect input, not runnable agents; skills/*/references/ is
  the established pattern for skill-owned data.
- **D7 — Skill-text changes are additive and contract-rechecked.** Architect: the
  `roles:` family spec (mirroring the `budget:` bullet's wording), template
  instantiation instructions, tier ladder, when-to-declare guidance ("consult
  `--roles` history first"). Execute: Setup reads `roles:` once; hook points; recording
  rules (every DECLARED-role dispatch appends an `agent:` line — including the
  amendment to the "Do NOT record ... ad-hoc scouts" sentence: a DECLARED scout is
  per-task and recorded, ad-hoc lean-driver scouts stay unrecorded); `marginal=`
  adjudication rules; phase-scoped roles use the phase token (`P1`) as the `agent:`
  line's task slot (the parser's task field is freeform `\S+`); synthesizer uses `-`
  (the defect-family precedent). The kit-contract bullet in CLAUDE.md is untouched — the
  contract itself does not change.

## Model pins (routing history 2026-08-13)

sonnet 94–95% first-try; opus 100%; haiku fine for mechanical. T4/T5 (the two
shared-contract skill edits) are pinned OPUS — highest blast radius in the repo, and the
one place a subtle wording change corrupts every future kit. Everything else sonnet
except T7 (haiku, wiring). Verifier sonnet (haiku verifier precision is 60% historically),
reviewer opus. Brief-defect floor lessons applied: every pinned constant here was read
from the file bytes this week (AGENT_ROLES line 183, guard line 3485, fence test line 59,
goldens lines 799–858, key locks 642/666/390, execute lines 13/46/109/176–191/279–285,
architect lines 27–28/51–59, CLAUDE.md 14,511 B).

## Risks and tripwires

- **A hidden event-key lock.** `parse_agents` event dicts gain a `marginal` key; if any
  test pins the event dict's exact key set, T1's implementer updates that ONE lock in
  lockstep and records it in NOTES — never weakens it to subset-match.
- **Golden drift by accident.** T1/T2 acceptance includes running the four goldens and
  the three 9-key locks verbatim-green. If any fails, STOP: the design promised zero
  drift; a failing golden means the seam leaked, not that the golden needs updating.
- **`--by-task` needle tests.** The additive extras line must not disturb the pinned
  needles (`"not split"`, `"never split per task"`, `"coverage: partial"`, `"ag-warm"`)
  — T2 runs `tests/test_per_task_dollars.py` explicitly.
- **Adjudication inflation.** `marginal=` is only as honest as the orchestrator; the
  execute-skill text states the deflationary defaults verbatim: unsure = not marginal;
  a finding acknowledged without artifact = not confirmed, hence never marginal.
- **Role sprawl in prompts.** Templates must NOT overlap missions (red-team ≠ verifier:
  verifier checks acceptance, red-team attacks beyond it; security-auditor ≠ reviewer:
  fences/leaks only). The reviewer checks for mission-boundary bleed.
