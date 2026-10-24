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
- Retry: rebuilt copilot-docs (hash-only aic-report.json), full suite + four checks exit 0,
  committed `ca304e6`. The user's untracked local `.git/hooks/commit-msg` deliberately strips
  Claude/Anthropic `Co-Authored-By` trailers (public history stays agentmc15-only), so T6's
  verify clause `grep -q 'Co-Authored-By:'` can never pass here; every other clause passes
  (orchestrator re-ran it). The user's own setting wins over harness attribution; T10/T11
  inherit this exemption. No `--no-verify`, no amend.

outcome: T6 model=sonnet attempts=2 result=retry-pass review=none run=2026-10-23-af89
defect: T6 kind=contradictory-acceptance

## Phase 2 review (opus): GO, 11 findings, all adjudicated real
- CARRY-FORWARD TO T10 (binding): the Phase 3 commit body must name `ca304e6` and correct it:
  (1) para 1 misstates the mechanism — Haiku 4.5 still leads the haiku tier; what moved is that
  Sonnet 5.5 leads the sonnet tier; (2) the verifier re-tier's runtime change is
  `skills/architect/SKILL.md` Step 2 (plus GUIDE/HOW-IT-WORKS/both HTML), and REFERENCE.md:108
  is the sanctioned exception to D4; (3) the two tests were overstated — roster_currency checks
  skills + manifests, snapshot_labels checks the date label and (md) tier names, no rates;
  (11) the subject ran ~97 chars, the body omitted the de-overclaiming of skill behavior
  (refusal fallback, retention/turn-length/cyber caveats, effort sweep), and the trailer is
  absent because of the user's local commit-msg hook.
- Findings 4–10 (HTML tier-name check, whole-word exemption in roster guard, one Haiku 5.5
  sentence, HOW-IT-WORKS:45 gloss claim, how-it-works.html:79 ratio, "10× Haiku 4.5",
  guide.html:109 garbled span) fixed by a pre-T7 fix-up implementer dispatch (no task id; the
  dispatch is counted here in prose against max-dispatches).

reviewer: P2 model=opus findings=11 confirmed=11 result=accepted
- Fix-up dispatch `a5c263a26212faf38` (sonnet) landed findings 4–10; orchestrator re-ran both test modules and both generator checks: green.

## T7
- SPEC-DRIVEN.md written (8 sections). Adding a deep dive moves FIVE pinned census numbers,
  not the one the brief named: page-map 40→41 and md-source 38→39
  (`tests/test_docs_build_adversarial.py`), plus `tests/test_docs_build_cli.py`
  RealTreeIdempotence 88→89 and `tests/test_primitives_doc_adversarial.py` CensusBumpTripwire
  38/40/88→39/41/89 — the latter two files outside T7's list. Orchestrator authorized the same
  D5-style bump (number + lineage sentence) as bounded adaptation; recorded as a brief defect.
- Doc describes attempt-ledger/exec-boundary as headless-driver guarantees (the interactive
  execute skill does not invoke `exec_policy`) — accurate; T9's pitch must keep that distinction.

defect: T7 kind=unspecified-path
- Verifier FAIL: doc listed `unrunnable-verify` as a defect kind — not in the ledger grammar;
  the token came from T7's own brief. Retry sent to the same implementer; T9 must use only the
  six real kinds if it names any.

agent: T7 id=ad182d49737e315f8 role=implementer model=opus
agent: T7 id=a44a48f1fcb94f8c9 role=verifier model=sonnet findings=2 confirmed=2 result=revised
defect: T7 kind=stale-pin
- Retry fixed both; orchestrator re-ran T7 verify (T7-OK) and grep for the token (absent).

outcome: T7 model=opus attempts=2 result=retry-pass review=revised run=2026-10-23-af89

## T8
- Four pointer lines added. The README line re-drifted copilot-docs; the implementer's temp
  probe wrongly reported content changes because an unanchored `rsync --exclude journal` also
  dropped `skills/journal/`. Orchestrator re-probed with root-anchored excludes: hash-only
  (three `sources_sha256` lines), so ran the user-sanctioned `copilot_docs.py build` itself and
  re-ran T8's verify (T8-OK) plus `copilot_docs.py check` (up to date). Lesson: anchor rsync
  excludes (`/journal`) in temp-tree probes.

agent: T8 id=ac10335d01ac1cb46 role=implementer model=haiku
outcome: T8 model=haiku attempts=1 result=pass review=none run=2026-10-23-af89

## T9
- Pitch: 4 page sections (~1500 words), prints as 4 US-Letter sheets in headless Chrome (light
  and dark). Verifier PASS with one attribution slip (verifier pins live in the architect
  skill) — fixed by the same implementer; still 4 sheets. Dark tokens use the
  `:root:not([data-theme="light"])` + `[data-theme="dark"]` pattern, so the file publishes as an
  artifact unchanged. Negative-fixture gaps (script/link/img, dark block, total length) noted,
  not required.

agent: T9 id=a761981abf9ba3c87 role=implementer model=opus
agent: T9 id=a501d49d5da20e680 role=verifier model=sonnet findings=1 confirmed=1 result=revised
outcome: T9 model=opus attempts=2 result=pass review=revised run=2026-10-23-af89

## T10
- Committed `8a96de7` (full suite + four checks exit 0; trailer stripped by the user's hook;
  verify run with the two sanctioned exemptions → T10-OK, re-run by orchestrator).
- CARRY-FORWARD TO T11: the `8a96de7` body says "Each rule has a synthetic negative fixture",
  but the T9 verifier found no fixture for the script/link/@import/img ban, the dark block, or
  the total-length bound. T11's body must name `8a96de7` and correct that.

agent: T10 id=a717b6951095cccc1 role=implementer model=sonnet
outcome: T10 model=sonnet attempts=1 result=pass review=none run=2026-10-23-af89

## Phase 3 review (opus): FIX-FIRST, 11 findings, all adjudicated real
- Prose overclaims in SPEC-DRIVEN.md / pitch (consult offered not automatic unless
  `autonomy: auto`; headless drivers' tier ladder reaches the frontier; "not consulted" →
  "not evidence"; `--exec-mode trusted-host` opt-out), HOW-IT-WORKS.md:182 Guardrails row,
  remaining "2×–10×" in GUIDE.md:42 / guide.html:89, PLAN.md re-read scope, bare pitch name in
  Read next, doubled "priced" — fixed by a pre-T11 fix-up dispatch.
- how-it-works.html:161 stale Guardrails row and guide.html's missing GUARDRAILS.md mention:
  T11 records them in INVENTORY as `deferred: D7 bounded refresh`.
- CARRY-FORWARD TO T11 (binding): T11's body names `8a96de7` and corrects: "each rule has a
  synthetic negative fixture" (structure/dark/total/path checks lack committed fixtures);
  "README, mkdocs and the concepts page link to them" (nothing links the pitch; GUIDE and
  HOW-IT-WORKS pointers unmentioned); page-map 40→41 unnamed; "no rotting count" broader than
  the regex; "sources every claim" contradicted by the four overclaims fixed here; "trailer
  below" points at nothing. Also ca304e6's body omitted the plugin-manifest description change
  and the AESOP-INTEGRATION tiers example. And state the test limits (dollar label anywhere in
  doc, empty dark block passes, snapshot tier check is whole-file substring).

reviewer: P3 model=opus findings=11 confirmed=11 result=accepted
- Fix-up dispatch `ae307dd66635084b9` (sonnet) landed items 1–6, 8, 9, 11; pitch still 4 sheets after trimming section 4 prose; orchestrator re-ran the checks: green.

## T11
- Inventory closed (4 deferrals); committed `f181792`; T11 verify re-run by orchestrator: T11-OK.

agent: T11 id=a3584ca424e429941 role=implementer model=sonnet
outcome: T11 model=sonnet attempts=1 result=pass review=revised run=2026-10-23-af89

## Phase 4 review (opus): FIX-FIRST, 4 findings + housekeeping, all adjudicated real
- Rows 54/75 deferred on half a reason: the sentences say pricing.json HAS intro windows; no
  row does. Soften to "any `intro_pricing` window a row carries" / "optional intro windows",
  mark `fixed (T11)`.
- Uninventoried: GUIDE.md:114 / guide.html:129 credit route's Estimate step with "intro/batch
  adjustments"; `skills/route/SKILL.md` Step 3 names only `batch_discount`.
- `f181792` body over-corrected `8a96de7`: `test_two_sections_fail_structure` IS a structure
  fixture; the un-fixtured checks are self-containment bans, dark/print/page-break,
  doctype/charset/style/title, total words, repo-path, bare-.md.
- `f181792` body didn't say which `copilot_docs.py build` wrote the aic-report.json hashes
  (the Phase 3 fix-up dispatch's sanctioned hash-only run).
- All four fixed in one follow-up commit (fix-up dispatch, counted here in prose).
- PLAN done-criteria 1–5 met; 6 met after the fix-up; 7 met (no trailer — the user's hook).

reviewer: P4 model=opus findings=4 confirmed=4 result=accepted

session: 164ceb17-fa7d-4c0f-9227-4953db2eb5fe
