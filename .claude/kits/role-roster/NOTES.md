# role-roster — execution notes

Execute-owned ledger. Machine-read line families: `outcome:`, `agent:`, `reroute:`,
`session:`, `reviewer:`, `defect:` (always backticked in prose here).

Run 2026-08-13-f3a9 — interactive execute loop, autonomy=advisory, no budget dial.
Warm cluster planned: T1→T2 on one continued sonnet implementer (bin/routing_scorecard.py).
T3 dispatched fresh in parallel (disjoint files). T4→T5 are FRESH opus dispatches each
(contract edits get fresh eyes, deliberately no warm cluster).

## Cross-task learnings

- Kit authored against byte-verified anchors (AGENT_ROLES line ~183, fence test
  test_role_ledger.py:59, goldens/locks enumerated in PLAN). One authoring-time sentinel
  case mismatch caught and fixed before dispatch (capital-E "Extended" — quoted from
  GUARDRAILS bytes).
- P1 review (opus, PASS; six mutants on copies all caught; HEAD-build byte comparisons):
  8 of 11 findings actioned. PLAN D2's pipeline-order sentence contradicted its own
  table (kit-level `defect:` stale-plan-decision) — canonical order + parallel-pair
  tiebreaks now written out in PLAN and embedded verbatim in T5's brief; T5's amendment
  scope extended to BOTH halves of the ad-hoc-scouts sentence (phase-reviewer rationale
  included). PLAN D4 amended: marginal cell n/a when zero measured (never fabricated 0);
  marginal rate over MEASURED dispatches only; aggregate cost-per-marginal single-basis
  or n/a (the current fold mixes priced/unpriced kits — CLI-unreachable today but the
  docstring claim was false); card legend must name the structurally-unmeasurable cells
  (phase-role dollars under never-split; indirect-value roles with no findings). T2R
  remediation carries the card changes under a SANCTIONED deliberate golden update (the
  roles view's own goldens only — the four prior goldens stay untouched). T6 brief now
  mandates the four structural limits (phase-role dollars, measured-denominator reading,
  order-dependence — a late role's low marginal never proves it worthless, no-findings
  roles judged qualitatively). Not actioned: F8 (deflationary language already lands via
  T5+templates), F9 (parser tolerances consistent with family), F11 (shifted line number
  only). Dogfood note: from here this kit's own verifier `agent:` lines carry
  `marginal=` where adjudicated.
- T5 verifier's one finding (tiebreak sentence paraphrased with articles vs the brief's
  "verbatim") adjudicated NOT confirmed: substance byte-equivalent in rule content,
  natural prose not parsed grammar, no behavioral difference at adjudication time. The
  "verbatim" law binds the deflationary defaults and the canonical order chain (both ARE
  byte-verbatim) — articles in the tiebreak prose are below the law's floor.
- P2 closing review (opus, whole-kit PASS; 8 mutants on copies all caught; leak scan
  stated zero): 6 of 9 findings actioned. Remediated in the closing round: (F1) execute's
  pre-existing "findings/confirmed meaningful only for role=verifier" clause became false
  post-T5 — self-contradiction in the shared contract file, amended; (F3) consequence
  rules for extended-role catches did not exist (red-team breaks a verified task → what?)
  — pinned; (F5) Setup and End-of-run enumerations extended to name roles:/--roles
  alongside their sibling dials; (F6) test-author structurally depresses per-tier
  first-try rates (its findings feed step-5 retries) — caveat added to the roles section
  and ROLE-EXPERIMENT's honest limits; (F2) the marginal-rate cell is catches per
  measured dispatch and can exceed 100% — legend + doc disclosure added (sanctioned
  roles-view golden update only); (F7) GUARDRAILS fence text said one sanctioned
  amendment where the corrected brief always named two — fixed by the architect.
  Recorded as named future work, not actioned now: (F4) the seven templates are
  polytropos-specific (/path/to/polytropos + repo-specific auditor fences) and their
  frontmatter contract has no standing test — a future kit should generalize the
  templates for non-polytropos targets and pin the frontmatter contract; until then,
  declaring roles: on a non-polytropos target requires hand-adapting the instantiated
  agents. Notes, no change: (F8) --demo --roles --session silently ignores the session
  flag; (F9) insufficient-sample keys on dispatches not measured-dispatches (mitigated by
  the adjacent unmeasured column and doc limit #2).

## Ledger

agent: T1 id=a8e9cf4d3eab00504 role=implementer model=sonnet
agent: T1 id=a8aca3409184eeba6 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T1 model=sonnet attempts=1 result=pass review=clean run=2026-08-13-f3a9
agent: T2 id=a8e9cf4d3eab00504 role=implementer model=sonnet
agent: T2 id=a9604f8387371ea85 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T2 model=sonnet attempts=1 result=pass review=clean run=2026-08-13-f3a9
reviewer: P1 model=opus findings=11 confirmed=8 result=accepted
defect: - kind=stale-plan-decision
agent: T2 id=aa1524e38993c54fc role=implementer model=sonnet
agent: T2 id=ada5b8e8572596e8c role=verifier model=sonnet findings=0 confirmed=0 marginal=0 result=accepted
outcome: T2 model=sonnet attempts=2 result=retry-pass review=revised run=2026-08-13-f3a9
agent: T4 id=a3a781c732342772c role=implementer model=opus
agent: T4 id=aba7313d82062ee37 role=verifier model=sonnet findings=0 confirmed=0 marginal=0 result=accepted
outcome: T4 model=opus attempts=1 result=pass review=clean run=2026-08-13-f3a9
agent: T5 id=a35965ad55ce263b4 role=implementer model=opus
agent: T5 id=acffa5acea5482482 role=verifier model=sonnet findings=1 confirmed=0 marginal=0 result=accepted
outcome: T5 model=opus attempts=1 result=pass review=clean run=2026-08-13-f3a9
agent: T6 id=a97ce223359c329ba role=implementer model=sonnet
agent: T6 id=a5ae6113ac0d8d759 role=verifier model=sonnet findings=0 confirmed=0 marginal=0 result=accepted
outcome: T6 model=sonnet attempts=1 result=pass review=clean run=2026-08-13-f3a9
agent: T7 id=a4a493b5a060cbdf4 role=implementer model=haiku
outcome: T7 model=haiku attempts=1 result=pass review=none run=2026-08-13-f3a9
reviewer: P2 model=opus findings=9 confirmed=6 result=accepted
agent: T5 id=af2254edd81660993 role=implementer model=opus
outcome: T5 model=opus attempts=2 result=retry-pass review=revised run=2026-08-13-f3a9
agent: T2 id=a43d4cbe247710da9 role=implementer model=sonnet
outcome: T2 model=sonnet attempts=3 result=retry-pass review=revised run=2026-08-13-f3a9
session: abf847f3-aa57-4b8d-a3b9-394a063e8762
agent: T3 id=a992896f15f01c728 role=implementer model=sonnet
agent: T3 id=ad683912f461e4dc6 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T3 model=sonnet attempts=1 result=pass review=clean run=2026-08-13-f3a9
