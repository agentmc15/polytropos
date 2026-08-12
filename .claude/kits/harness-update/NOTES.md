# harness-update — execution notes

Execute-owned ledger. Machine-read line families: `outcome:`, `agent:`, `reroute:`,
`session:`, `reviewer:`, `defect:` (always backticked in prose here).

Run 2026-08-11-b41f — interactive execute loop, autonomy=advisory, no budget dial.
Warm cluster planned: T1→T2→T3→T5 on one continued sonnet implementer (same primary file).
T4 dispatched fresh in parallel (disjoint files).

## Cross-task learnings

- T1: engine counts `SHA STALE` as drift (exit 3) — a documented, deliberate widening of
  plugin_staleness's own exit-0 treatment; the deviation lives in both docstrings. Later
  tasks keep it.
- Mid-run observation: editing docs/COPILOT-HARNESS.md (T4) makes
  tests/test_copilot_docs_content.py's freshness check fail until the copilot-docs
  generator is re-run — confirmed by T4; resolved by running `bin/copilot_docs.py`
  (sanctioned generator; only sources_sha256 hashes changed in aic-report.json).
  Brief contradiction logged as `defect:` T4 contradictory-acceptance.
- T2: `harness_select._resolved_bytes` resolves the repo root (symlink-real) before
  substitution, but `install_copilot` substitutes the UNRESOLVED `str(repo_root)` — on
  macOS `/var`→`/private/var` temp paths they diverge. T2 matched install_copilot's own
  mechanism (module-is-authoritative rule); T6's apply must compare/dispatch through the
  same unresolved form or fixtures will spuriously `differ`.
- T3: doctor_codex plans a full install against a NONEXISTENT home — the engine pre-checks
  home existence so absence maps to "not installed", never an all-install drift plan. The
  "skip" state exists only inside apply_codex_plan's defensive filter, never emitted by
  doctor. (Both verified by T3's verifier against harness_select source.) T6: keep the
  same pre-check before any apply path targets a home.
- P1 review (opus, PASS): 4 confirmed of 9 — T4 fence ratified in TASKS.md (generator runs
  in scope, hand-edits stay banned); stale "2026-07-25 refresh" clause in
  docs/COPILOT-HARNESS.md fixed + copilot-docs rebuilt; T6 must add a coupling assertion
  binding the comparator's unresolved-path substitution to install_copilot's actual writes
  (symlinked-root fixture) — the one forked line is the risk; T7 skill must warn that
  check's --json embeds absolute home paths (install_path, codex destinations) — scrub
  before pasting outward. Accepted deviations, no change: ASCII "--" where PLAN D7 wrote
  em dashes (labels' substrings intact); unknown-claude-status fallthrough renders "in
  sync" (unreachable today); demo's second codex roster copy (rot fails loudly — do NOT
  add a third); SHA STALE = drift stays (brief-sanctioned, disclosed in-card).
- T6 ratified scope calls: build_demo_tree() root is .resolve()d (REQUIRED — legacy
  install_codex substitutes the unresolved root, doctor_codex the resolved one; an
  unresolved temp root can never round-trip green; the real repo root is already
  resolved); demo extended to apply --dry-run / apply / post-apply check per PLAN done
  bullet 3, final card deliberately keeps data drift (docs-label staleness is the class
  apply refuses to auto-fix, stated in-card). sync_codex_surfaces build returns the
  previously-stale names, NOT the full rewrite set — apply labels it accordingly.
- P2 review (opus, BLOCKED then remediated): install_codex's prompts loop is UNCONDITIONAL
  overwrite (harness_select.py:238-246) — only AGENTS.md and skill dirs are no-clobber.
  PLAN D3(b) had asserted no-clobber wholesale (architect `defect:` kit-level
  stale-plan-decision); GUARDRAILS + PLAN amended to per-channel truth: prompts =
  plugin-generated mirrors, overwrite-in-place, every differing rewrite listed; the
  "preserved" note only when something was preserved. Also confirmed: apply's codex writer
  cannot reach project-scope agent TOMLs or the modern plugin component (report must name
  the coverage limit, never claim completion over unreachable drift); claude remedy must
  be framed conditionally (apply makes no freshness determination). T6 verifier's clean
  verdict was overturned by the phase review (its skip-differs probe only exercised
  AGENTS.md; `_seed_repairable_drift` only deleted prompts — the overwrite path was
  invisible to the suite). Lesson: an adversarial verifier inherits the brief's blind
  spots — the reviewer's value was reading the REUSED module's write loop, not the new code.
- P2 re-review (opus, PASS; mutation-tested on a scratch copy — all five injected defects
  caught): 7 of 9 findings actioned — T7 brief's stale wholesale-no-clobber wording fixed
  + envelope-divergence and both-subcommands scrub warnings added to T7; T8's cosmetic
  item had named the WRONG argparse location (`defect:` T8 unspecified-path — it is the
  apply subparser's own help=, not --codex-home's); PLAN out-of-scope line de-staled.
  Two open notes, future work, not blocking: the AST write-guard nets only functions with
  "apply" in the name (helpers like _codex_prompt_overwrites sit outside it, read-only
  today); the CODEX pre-scan has no symlinked-root coupling test (copilot side has one;
  manually probed correct today). The reviewer's finding-1 empirical probe: hand-edited
  prompt → rewritten AND labeled, preserved appears only for AGENTS.md/skills.
- T8: the brief claimed its KIT_SENTINELS substring existed "verbatim" in GUARDRAILS.md —
  false, the phrase was line-wrapped (`defect:` T8 stale-pin). The haiku implementer
  adapted with an embedded "\n  " sentinel (worked, but brittle against reflow and
  style-divergent); orchestrator revised: GUARDRAILS bullet reflowed so the phrase is
  contiguous, sentinel now the clean single-line form. Layout test + full suite green
  after (2538 OK). Lesson for sentinel briefs: quote the anchor from the file bytes, not
  from memory of what was written — wrapping is part of the bytes.
- P3 review (opus, PASS; whole-kit close: "complete and safe to hand over"): 4 of 6
  findings actioned in skills/update/SKILL.md + this file — scrub warning extended to the
  HUMAN apply card (it lists destination paths; check's card is path-free); conflict /
  managed-update / apply-error glosses added to "Reading the card"; a clause reconciling
  the shipped skill with CLAUDE.md's always-on ~/.claude invariant (explicit user
  go-ahead = the sanctioned path, engine still never runs it). F2 recorded: the CLAUDE.md
  invariant bullet as landed carries one extra accurate sentence (per-channel codex
  semantics) beyond the stored T8 brief's "verbatim" block — the deviation originated in
  the ORCHESTRATOR'S dispatch text, which post-P2 corrected the bullet while TASKS.md kept
  the shorter form; accurate, budget-safe (13,881 B), kept. Not actioned (already logged
  or cosmetic): GUARDRAILS reflow disclosure stands; AST-guard naming net remains future
  work. Real-machine close: check exit 3 (claude sha-stale + codex conflicts — true
  drift), apply --dry-run honest, demo exit 0, 2538 tests OK.

## Ledger

agent: T1 id=ab18b9f9744f6e969 role=implementer model=sonnet
agent: T1 id=a338f3444b1cbc00b role=verifier model=sonnet findings=0 confirmed=0 result=accepted
defect: T4 kind=contradictory-acceptance
agent: T4 id=ab1a20ba25323dca0 role=implementer model=sonnet
agent: T4 id=a9a477b03aecc2d73 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T4 model=sonnet attempts=1 result=pass review=clean run=2026-08-11-b41f
agent: T2 id=ab18b9f9744f6e969 role=implementer model=sonnet
agent: T2 id=abf29a926d1148bdc role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T2 model=sonnet attempts=1 result=pass review=clean run=2026-08-11-b41f
agent: T3 id=ab18b9f9744f6e969 role=implementer model=sonnet
agent: T3 id=a4df31bc4e7151dbf role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T3 model=sonnet attempts=1 result=pass review=clean run=2026-08-11-b41f
agent: T5 id=ab18b9f9744f6e969 role=implementer model=sonnet
agent: T5 id=ac9038c9717d96f27 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T5 model=sonnet attempts=1 result=pass review=clean run=2026-08-11-b41f
reviewer: P1 model=opus findings=9 confirmed=4 result=accepted
agent: T6 id=a9dd0f377597123bc role=implementer model=opus
agent: T6 id=a767b87243542905a role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T6 model=opus attempts=1 result=pass review=clean run=2026-08-11-b41f
reviewer: P2 model=opus findings=5 confirmed=5 result=accepted
defect: - kind=stale-plan-decision
agent: T6 id=a767b87243542905a role=verifier model=sonnet findings=0 confirmed=0 result=revised
agent: T6 id=a9dd0f377597123bc role=implementer model=opus
agent: T6 id=afb6aa117f3e7a909 role=verifier model=sonnet findings=1 confirmed=1 result=accepted
outcome: T6 model=opus attempts=2 result=retry-pass review=revised run=2026-08-11-b41f
reviewer: P2 model=opus findings=9 confirmed=7 result=accepted
defect: T8 kind=unspecified-path
agent: T7 id=a28913eb5b7c2cb43 role=implementer model=sonnet
agent: T7 id=adabb0b75f7eacd45 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
outcome: T7 model=sonnet attempts=1 result=pass review=clean run=2026-08-11-b41f
agent: T8 id=a610c58efc30c620a role=implementer model=haiku
defect: T8 kind=stale-pin
outcome: T8 model=haiku attempts=1 result=pass review=revised run=2026-08-11-b41f
reviewer: P3 model=opus findings=6 confirmed=4 result=accepted
session: abf847f3-aa57-4b8d-a3b9-394a063e8762
outcome: T1 model=sonnet attempts=1 result=pass review=clean run=2026-08-11-b41f
