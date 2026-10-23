# sdd-docs-refresh — execution notes

Run `2026-10-23-af89`, interactive executor on Opus, autonomy advisory.

## T1
- INVENTORY.md: 61 stale rows (7 deferred with reasons). Extra finding beyond the brief:
  `skills/cost-report/SKILL.md:24` claims "Sonnet 5 intro pricing applied by date" but no
  pricing.json row carries `intro_pricing` (the engine still honours the field) — T2 owns it.
- `skills/architect/SKILL.md:3` and `:10` ("Get onto Fable 5") are roster claims, not the
  protected slogan; no test pins them — T2 should re-grep before editing.
- Row 50 (how-it-works.html "measured on this machine") is deferred with a reviewer-decides
  note; T5/T11 decide it consciously.
- Acceptance "git status shows exactly one new path" cannot hold literally: the kit dir and
  agent files were already untracked before T1.

outcome: T1 model=sonnet attempts=1 result=pass review=clean run=2026-10-23-af89
agent: T1 id=a43297397dbccd3b9 role=implementer model=sonnet
agent: T1 id=ab43906b9a2adf4f9 role=verifier model=sonnet findings=3 confirmed=1 result=accepted
defect: T1 kind=contradictory-acceptance

## Phase 1 review (opus): FIX-FIRST, 13 findings, all adjudicated real
- Inventory under-covered fable-check behavior claims (security/cyber, 30-day retention, effort
  sweep — none stated by `skills/fable-check/SKILL.md`), one more refusal-fallback site
  (GUIDE Example 9), REFERENCE.md:108 verifier=haiku, several HTML example/verifier sites, and
  had deferrals (rows 10/19/58, 50, 61) that should be fixes. Sent back to the implementer.
- T5 brief premise "the engine has no intro windows" is false: `bin/cost_report.py:60-64`
  still applies `intro_pricing`. T5's implementer must be told; the deferral of that row stands.
- T11's verify accepts `deferred: ` but T1's brief prescribed `defer:` — T11 must rewrite every
  deferral row to `deferred: <reason>`.
- REFERENCE.md:108 is a deliberate Claude-only exception to PLAN D4's "REFERENCE.md do not touch"
  (consequence of D3); T4 fixes it, T11 notes it.

defect: T5 kind=stale-pin
defect: T11 kind=contradictory-acceptance
defect: - kind=stale-plan-decision
- Inventory revised (76 rows; 2 deferred). Row 21 kept as "DUPLICATE of row 15" to avoid renumbering.

agent: T1 id=ad311f3fcccfc36de role=implementer model=sonnet
outcome: T1 model=sonnet attempts=2 result=pass review=revised run=2026-10-23-af89
reviewer: P1 model=opus findings=13 confirmed=13 result=accepted

## T2
- Skills refreshed; architect body ~2300 words; shared kit contract re-checked unchanged.
- Brief item 4 named a cost-report "roster list" that line 24 never had; implementer used
  INVENTORY row 32's wording (an `intro_pricing`-window clause). `ManifestDescriptionTests` stays
  red until T3 by design.
- `pricing.json` `models` is an id-keyed dict (not a list); the test handles both.

agent: T2 id=a3b48cc7152a7d454 role=implementer model=sonnet
outcome: T2 model=sonnet attempts=1 result=pass review=clean run=2026-10-23-af89
agent: T2 id=ae9c342823ff67315 role=verifier model=sonnet findings=7 confirmed=1 result=accepted
defect: T2 kind=stale-pin

## T3
- Manifest descriptions now tier words; the trailing "use Fable 5 optimally" also became "the
  frontier tier" (required by the brief's own no-display-name acceptance). Mechanical task —
  orchestrator verify plus diff read, no verifier dispatch.

agent: T3 id=afe39ffc631ae6d00 role=implementer model=haiku
outcome: T3 model=haiku attempts=1 result=pass review=none run=2026-10-23-af89

## T4
- Markdown docs current; REFERENCE.md:108 verifier=sonnet (the sanctioned exception).
- T4's verify clause `grep ... | grep -qi "skill .*fall"` false-positives on accurate prose
  ("The skill states no refusal fallback"); implementer reworded to "Nothing in `/escalate`
  handles a refused hop" — verifier confirmed still accurate. Watch for the same in T5.
- Implementer added an extra guard, `test_no_stale_snapshot_date_survives`.

agent: T4 id=a7fb9c030ee0e39fa role=implementer model=sonnet
outcome: T4 model=sonnet attempts=1 result=pass review=clean run=2026-10-23-af89
agent: T4 id=a06f5f6ca6cd9dd6c role=verifier model=sonnet findings=0 confirmed=0 result=accepted
defect: T4 kind=contradictory-acceptance

## T5
- Served warm by the T4 implementer (same agent id). Also removed guide.html:313 "11 kits …
  32/32" clause (not inventoried; verifier judged it in D7 scope). The T5 ban grep matches
  `32 of 32` but not `32/32` — a gap, not a defect worth a line.

agent: T5 id=a7fb9c030ee0e39fa role=implementer model=sonnet
outcome: T5 model=sonnet attempts=1 result=pass review=clean run=2026-10-23-af89
agent: T5 id=a113c61af85315a72 role=verifier model=sonnet findings=0 confirmed=0 result=accepted

## T6 — first attempt stopped red (correctly)
- `bin/copilot_docs.py check` exit 1 (drift on README/COSTS/WORKFLOWS source sets) and the full
  suite's one failure `test_copilot_docs_content.HtmlParityAccessibilityTests.test_in_process_check_reports_no_drift_and_is_read_only`
  — same cause. HEAD's tree checks clean, so this kit's Claude-side doc edits caused it.
- A rebuild in a temp copy changes ONLY three `sources_sha256` fields in
  `copilot-docs/aic-report.json` — provenance hashes of shared sources, no Copilot content.
- Plan conflict: PLAN/GUARDRAILS fence `copilot-docs/` read-only and T6's verify diffs it, but
  the repo invariant requires generated docs rebuilt and PLAN done-criterion 2 requires
  `copilot_docs.py check` exit 0. GUARDRAILS says CLAUDE.md invariants win. The USER chose
  (2026-10-23): rebuild, commit the hash-only change, exempt that one path from T6's verify.
  T10/T11 inherit the same exemption if their edits re-drift it.

agent: T6 id=a31b258add64347d6 role=implementer model=sonnet
defect: T6 kind=stale-plan-decision
