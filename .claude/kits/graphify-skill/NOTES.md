# graphify-skill — execution notes

Execute-owned ledger. Machine-read line families: `outcome:`, `agent:`, `reroute:`,
`session:`, `reviewer:`, `defect:` (always backticked in prose here).

Run 2026-08-12-e7c3 — interactive execute loop, autonomy=advisory, no budget dial.
Warm cluster planned: T1→T2 on one continued sonnet implementer (same primary file).
T3 waits on T1; T4/T5 independent of each other after T3.

## Cross-task learnings

- Kit was architected from a same-day hands-on eval (graphifyy 0.9.41; evidence in
  PLAN.md). The eval graph of this repo lives in the session scratchpad, NOT in the repo —
  tests never depend on it.
- P1 review (opus, PASS; mutation-tested the guards on copies — all fired): 6 of 8
  findings actioned. Remediation before T3: (F1) UnicodeDecodeError escapes load_graph as
  a traceback on non-UTF-8 graphs — reachable, since graphify embeds source snippets in
  link `context`; (F2) the tests-excluded hub label overclaimed ("all top-8" vs the real
  graph's 4/8 — architect `defect:` T1 stale-pin; corrected string ratified in TASKS.md);
  (N8) `--top -1` slice artifact. For T3's skill wording: the tests/ exclusion is a
  top-level-prefix match only (test/, spec/, src/tests/ get no benefit — say so); the
  cross-file ratio counts `relation=="calls"` only (indirect_call excluded — do not claim
  it covers all call-like edges). Acknowledged, no change: source_file-less nodes (e.g.
  builtin exceptions) can rank in the excluded hub list; the `(none)` directory bucket
  conflates root-level files with unattributed nodes. PLAN Evidence edge-count annotated
  (12,742 CLI banner vs 12,000 in-file post-dedup — both true, different stages).
  Real-graph proof point for the record: 52-line card from an 8.2MB graph (~4,600×
  reduction), warning fired at 1/4098 cross-file calls, EXTRACTED/INFERRED 11802/198.
- P2 review (opus, PASS; kit closes green): 4 of 6 findings actioned in a final
  remediation — (F1) the deny list named a PHANTOM surface ("the MCP server" does not
  exist in graphifyy 0.9.41's measured --help) while omitting the three biggest real
  ones: `extract` (headless LLM extraction, auto-detects API keys — the largest
  spend/network surface), `global` (writes ~/.graphify), and per-platform `install`
  commands (`claude install` etc. — rewrite CLAUDE.md, install hooks); fixed in both
  SKILL.md and the permanent CLAUDE.md invariant. The closed allowlist framing kept this
  non-blocking — nothing was reachable — but deny-list wording must trace to measured
  bytes, the same law as strength claims. (F2) both verbatim honesty strings were pinned
  via the engine's own constants — self-referential; mutation on a copy gutted the 54%
  clause with all 36 tests green. Fixed: literal pins in tests. (F4) one skill claim
  widened past Evidence (query surfaces doc-manifest nodes too, not only test helpers) —
  reworded. (F5) allowlisted reads write into graphify-out/ (explain updates a cache
  stamp; tree emits GRAPH_TREE.html) — named in the skill's hygiene section. Acknowledged,
  no change: T5's numstat verify is vacuous post-commit (grep conjunct still bites);
  CLAUDE.md headroom 1,529 B. Reviewer disclosure, adjudicated as justified: it invoked
  the real graphify binary (--help/--version/one explain on the scratchpad eval graph) to
  measure the CLI surface — local-only, zero network/spend, outside every test/verify
  path; that measurement is what caught F1, and vendor docs had already proven wrong once
  (no `extract` in the docs' sense either). The sentinel's purpose (no spend, no network,
  no CI invocation) was not touched.

## Ledger

agent: T1 id=a9063d9b399cedb6e role=implementer model=sonnet
agent: T1 id=a1d49148b268a2317 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T1 model=sonnet attempts=1 result=pass review=clean run=2026-08-12-e7c3
agent: T2 id=a9063d9b399cedb6e role=implementer model=sonnet
agent: T2 id=a66513bcf84196d1d role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T2 model=sonnet attempts=1 result=pass review=clean run=2026-08-12-e7c3
reviewer: P1 model=opus findings=8 confirmed=6 result=accepted
defect: T1 kind=stale-pin
agent: T1 id=a9063d9b399cedb6e role=implementer model=sonnet
agent: T1 id=a104c5bd87a1d5d8a role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T1 model=sonnet attempts=2 result=retry-pass review=revised run=2026-08-12-e7c3
agent: T3 id=a633429a7de5694cd role=implementer model=sonnet
agent: T3 id=a5cd362744f53a02e role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T3 model=sonnet attempts=1 result=pass review=clean run=2026-08-12-e7c3
agent: T4 id=a3f836dd7270de8e0 role=implementer model=haiku
outcome: T4 model=haiku attempts=1 result=pass review=none run=2026-08-12-e7c3
agent: T5 id=aee4334950187c248 role=implementer model=sonnet
agent: T5 id=a1b9168530d5287d2 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T5 model=sonnet attempts=1 result=pass review=clean run=2026-08-12-e7c3
reviewer: P2 model=opus findings=6 confirmed=4 result=accepted
agent: T3 id=a731fa72280ae5eaa role=implementer model=sonnet
outcome: T3 model=sonnet attempts=2 result=retry-pass review=revised run=2026-08-12-e7c3
outcome: T4 model=haiku attempts=2 result=retry-pass review=revised run=2026-08-12-e7c3
session: abf847f3-aa57-4b8d-a3b9-394a063e8762
