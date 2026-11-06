# Context travel: critique reconciliation

Date: 2026-11-01

## Conclusion and scope

The user chose to **keep the original phase order** on 2026-11-01:
CT1 -> CT2 -> CT3 -> CT4 -> CT5 -> CT6. The pilot sequence reviewed below is not
adopted. Its useful privacy, identity, rendering and evaluation corrections feed
the original milestones; all six surfaces and all providers remain on the roadmap.

The separate `kit/context-travel` draft makes a useful sequencing proposal:
freeze evaluation fixtures early, demonstrate one complete producer-to-consumer
handoff, then expand integrations. This remains a reviewed alternative, while the
original context-travel roadmap and its cost/quality evaluation remain active.
The draft is not ready for implementation as written: the reader boundary,
evidence binding, render overflow behavior, and evaluation API need corrections.

This is a code-inspected review of a draft, not an implementation, test result,
merge authorization, or acceptance of another conversation's reported approvals.
The user supplied the branch name so the critique could be read, then declined
the proposed pilot resequencing. The sequence below is retained as a historical
review recommendation, not an executable replacement kit.
No document on the separate branch has been edited, merged, or cherry-picked.

CT1 remains complete at `d2dec5b4b1af321e0991cd44eef557c0c9346155` on
`codex/context-travel-ct1`. Its independent review and successful 6,489-test
offline run are recorded in NOTES.md. The review did not establish a CT1 defect.
No CT2 or later implementation was started during this reconciliation.

## Sources and snapshot

The source checkout is on local branch `kit/context-travel`, based on
`7671894d2ac9e43f1a6c808d5b31477a107b119e`. The reviewed kit files were uncommitted.
The branch's HEAD alone therefore does not identify the critique. References
prefixed **Draft** below mean these files in that separate checkout; **Code**
means existing repository code inspected against the same baseline.

| Draft file | SHA-256 of reviewed bytes |
| --- | --- |
| `.claude/kits/context-travel/PLAN.md` | `2368457f21793492fcad4255368d88b91a7f649905f817e49efb1de09e7070aa` |
| `.claude/kits/context-travel/TASKS.md` | `20cc9b95e768855d89fdbf0fd2df35a653fb159ef06bc559603e0c33399c26b8` |
| `.claude/kits/context-travel/GUARDRAILS.md` | `af914a1c61d363e901ab81948bfc113bfabecc98395b77c1c0cd0b7d4ba83e17` |

If these files change, re-review the changed sections. The untracked agent drafts
were inventoried but not executed or adopted. Claims in the draft about historical
routing performance or approval in another conversation were not independently
verified; no personal history store was read to substantiate them.

## What to retain

- Design and freeze fixtures and labels before implementing the producer. Add
  independent negative cases and held-out cases, rather than only pinning an
  implementation author's expected outputs.
- Prove one complete handoff early, including the consumer receiving the briefing
  and a verifier retrieving the same artifact. Unit-level contract correctness
  alone does not demonstrate this integration.
- Reuse the kit, graph, privacy, provenance and routing authorities. Add narrow
  read seams where needed instead of duplicating their semantics.
- Keep the new behavior opt-in and prove the existing path remains unchanged.
- Preserve `PROVENANCE_REFS`; record a briefing reference separately rather than
  changing the CT1 schema indirectly through a shared constant.
- Keep stub evidence distinct from installed-client evidence. Capability
  verification remains unknown; an offline comparison cannot establish savings,
  meaningful user outcomes, or reliable live operation.

## Corrections required before the affected work

### 1. Cover every source read, including graph freshness

**Draft:** PLAN.md:153 and TASKS.md:345 propose replacing the original reader task
with an eligibility predicate before `graph_ground.search` opens a source file.
That closes a real scan-path gap, but it is not the whole reader boundary.

**Code-inspected evidence:** `decision_context.py:543` calls graph freshness before
the fallback scan. `graph_ground.py:406` fingerprints graph source files through
the read path at `graph_ground.py:256`, without the proposed predicate. The draft's
sentinel fixture explicitly has no graph and cannot catch this earlier access.
`graph_ground.py:659` reads bytes before checking their size. Graph loading at
`graph_ground.py:210` reads the graph and then reloads it for parsing.

**Correction:** apply the same pre-read policy to selected graph bytes, sidecars,
fingerprinted sources, scan candidates, and evidence files, or report the affected
source unavailable. Add graph-present as well as graph-absent denied-read fixtures.
Bound aggregate physical reads, including retries, before access; distinguish
output/candidate limits from bytes actually read. Retain explicit handling for
symlink roots/ancestors/leaves, special files, source mutation, and incomplete
coverage. Do not report the original CT2 acceptance complete after fixing only
search eligibility.

### 2. Require explicit evidence access and subject binding

**Draft:** TASKS.md:232 makes `--attempt-store` optional and calls
`kit_contract.open_ledger(kit_dir, store=...)`; TASKS.md:306 repeats this for preview.

**Code-inspected evidence:** `kit_contract.py:1815`, `attempt_ledger.py:313`, and
`runtime_data.py:95` allow omitted store selection to resolve a personal default.
`attempt_ledger.py:379` reads ledger events without an aggregate byte ceiling.
Existing ledger namespaces derived from kit basenames do not prove repository
and relative-kit identity across reused stores.

**Correction:** require an explicitly supplied, authorized evidence binding, or
represent evidence as absent/unavailable. No fallback to a personal store, including
preview and CLI paths. Validate repository ID, relative kit path, task and evidence
applicability before joining records; preserve legacy unknowns. Include duplicate
kit names across repositories and across both kit layouts in the fixture cohort.
Using a bare `artifact:T1` or `attempt:<id>` inside a properly validated subject
is possible; the bare reference alone does not establish that subject.

### 3. Correct repository-root and parsing assumptions

**Draft:** TASKS.md:188 extracts acceptance from a task block and defaults the root
through `attempt_ledger.kit_repo_root` for both kit layouts.

**Code-inspected evidence:** `attempt_ledger.py:300` recognizes the Claude kit
layout, not the promised native `tasks/kits` layout. `kit_contract.parse_tasks`
already returns parsed acceptance (`kit_contract.py:111`, `:195`); it does not
return the raw task block assumed by the proposed producer and source extraction.

**Correction:** pass and validate an explicit repository root, derive the kit path
only after containment checks, and consume the parser's acceptance field. If raw
brief-path extraction is needed, specify one additive seam owned by
`kit_contract`; do not create a second task parser. Test both layouts independently.

### 4. Define refusal when mandatory rendered content exceeds its budget

**Draft:** PLAN.md:204 and TASKS.md:214 keep all criteria within the existing render
budget by dropping only optional evidence.

**Code-inspected evidence:** CT1 permits several criteria whose combined text
exceeds `attempt_ledger.CONTEXT_CHARS`, while still fitting the CT1 object limit.
Dropping every evidence entry cannot make such mandatory content fit.

**Correction:** calculate mandatory rendered size first, including the identity
header, criteria and required limitations. If it cannot fit, return an explicit
refusal or a separately specified bounded reference handoff. Never overflow the
budget or silently omit criteria. Add a negative fixture that is valid under CT1
but cannot fit the render limit.

### 5. Repair the evaluation API and preserve the real comparison

**Draft:** TASKS.md:612 calls `workflow_eval.pin_trial_inputs` with a fixture digest
as `checkpoint` and an identity as `acceptance`.

**Code-inspected evidence:** `workflow_eval.py:2277` expects structured checkpoint
and acceptance mappings, including checkpoint fields such as item/group and an
acceptance command/digest. Those draft arguments do not satisfy the current API.

**Correction:** define the mappings from independently constructed fixture facts,
then test the adapter against the existing protocol. If that protocol measures a
different experiment, use a small distinct schema instead of inventing placeholder
facts to satisfy it. Keep unknown observations unknown.

The draft's no-briefing / briefing / briefing-with-sources arms are a useful
component comparison. They are not the original CT6 comparison of ordinary
discovery, a conventional static briefing, and maintained context travel at
matched quality. A recorder stub observes prompt delivery, not agent task success
or cost per accepted outcome. Retain the latter comparison as a separate gate,
with held-out cohorts, maintenance cost, baseline/control parity, and independently
accepted outcomes. Freeze labels early, but permit documented correction of a
demonstrably wrong oracle through independent review and a new evaluation version;
a label pin is not proof that the label is true.

Instrument all relevant read paths, not only calls that happen to use one patched
helper. A zero read count from an uninstrumented path must be unknown. Count
forbidden read attempts as well as forbidden strings in the final output.

### 6. Keep applicability and privacy claims within the evidence

**Draft:** PLAN.md:189 uses a workspace fingerprint as source-state identity;
TASKS.md:214 claims no absolute path, hostname or username can appear in rendering.

**Code-inspected evidence:** `attempt_ledger.workspace_fingerprint`
(`attempt_ledger.py:868`) invokes its own Git probe; injecting Git into
`graph_ground.repo_state` does not inject that call. Its untracked-file coverage
uses metadata rather than a complete content digest. CT1's text redaction catches
credential shapes; it does not promise removal of arbitrary usernames, hostnames
or filesystem paths from free text or explicit identifiers.

**Correction:** describe fingerprint coverage and omitted state explicitly. Provide
an injectable or precomputed observation path for offline tests, and leave unknown
state unknown. Specify the actual export policy and test representative sensitive
inputs; remove universal privacy claims not established by that policy.

Draft TASKS.md:419 also sets `supplied=seeds`. In `decision_context.py:488`, supplied
paths mean context already shown to the consumer. A path mentioned in a brief is
not proof its contents were shown. Preserve that distinction. Source references
with `sha=None` support navigation; they do not identify the bytes of a file.

### 7. Preserve task identity and the broader product scope

The two documents reuse CT2 through CT5 for different work. For example, original
CT2 means readers while draft CT2 means producer and storage. This is exactly the
kind of ambiguity context travel must avoid.

**Correction:** keep original CT1–CT6 IDs and acceptance obligations stable. Name
pilot tasks separately and link them to the original milestones. Choose one active
execution kit/status authority before dispatch; the other document becomes a
proposal or a linked historical record, not a second competing status table.

The original goal still includes Codex desktop/CLI, Claude desktop/CLI, Copilot
desktop/CLI, GitHub, GitLab, Bitbucket, Azure DevOps, plain Git, multiple repositories,
and monorepos. A first CLI pilot may defer their implementations and all provider
work. It does not remove them from the roadmap or prove their compatibility.
Native-first provider ownership and portable plans/evidence remain design goals.

### 8. Keep the user's instructions above draft execution instructions

Draft PLAN.md:11 reports approval in another conversation; that is background,
not independently verified authorization here. Its merge precondition does not
authorize a merge. The completed CT1 branch already contains the contract, so no
merge is needed to assess the proposal in this isolated workspace.

Draft GUARDRAILS.md:94 requests a mandated session trailer. The user's global
instructions prohibit AI attribution and assistant/session trailers. Follow the
user's anonymous commit convention. Do not install the draft agents, inherit
Claude-specific routing pins into Codex, or run the draft's store/history checks.
Each harness retains its own policy and pricing authority.

## Reviewed pilot alternative and mapping (not adopted)

This mapping adds a pilot beneath the original milestones; it does not rename
them or mark them complete. Proposed pilot IDs have not been dispatched.

| Order | Proposed pilot task | Original milestone contribution | Required evidence |
| --- | --- | --- | --- |
| 0 | Existing CT1 | CT1 complete | Retain reviewed contract and recorded checks |
| 1 | P1: fixture and observation contract | Early part of CT6 | Independent labels; both kit layouts; duplicate subjects; denied reads; missing/corrupt/stale evidence; honest unknown metrics |
| 2 | P2: minimum explicit read boundary | CT2 | Confined bounded reads, explicit store selection/absence, graph-present denials, mutation and identity fixtures |
| 3 | P3: one task briefing producer and CLI | Part of CT3/CT4 | Correlation, source coverage, render-overflow refusal, validated immutable-reference handoff |
| 4 | P4: first driver consumer with stubs | Part of CT5 | Prompt and reference delivery, unchanged opt-out behavior, temp stores, no live compatibility claim |
| 5 | P5: source composition and verifier retrieval | CT2/CT3/CT5 integration | Same artifact retrieved, eligibility enforced across reads, navigation/content distinction, no false freshness |
| 6 | P6: offline component comparison | Partial CT6 | Frozen cohort, all reads observed or marked unknown, denominators, explicit non-live verdict |
| 7 | Later promotion | Remaining CT3–CT6 and later phases | Read-only lifecycle queries, remaining surfaces, general comparison, incremental scale and providers under their own gates |

Claude Code CLI is a reasonable first consumer because the existing driver has a
stub-dispatch seam and relevant verification behavior. A count of kit directories
does not establish that it is the most exercised driver. Codex CLI can follow using
the same producer; either order must leave the other surfaces visible as pending.

## Actions taken and verification limits

- Read local branch/worktree metadata and the three draft kit files; did not fetch
  remote content or access GitHub.
- Used two bounded read-only reviews: one for reader/store integration and one for
  evaluation, contracts and scope. Findings above were reconciled by the coordinator.
- Used the central Codex policy's read-only verifier preview. This was not a live
  driver invocation or a measured usage record.
- Authored this document and linked it from the complete implementation report.
  Executable task status and CT1 source code are unchanged.
- Did not run the draft, its verify commands, fixtures, history checks or agents.
  API and boundary findings are code-inspected, not newly reproduced runtime tests.
- CT1's earlier full-suite result remains attached to unchanged implementation
  bytes; it is not evidence for the draft producer, reader changes or evaluation.
- Independent document review passed after correcting one source-line citation.
  Both documentation generators ran and their checks passed, producing no
  generated-content changes. The reviewed draft hashes were rechecked unchanged.
  The full unit suite was not repeated for this planning-document-only change.

All implementation remains in the isolated worktree. No live runs, installations,
GitHub changes, merges, pushes, or deployments are authorized or performed here.
