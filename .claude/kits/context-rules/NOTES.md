# NOTES — context-rules

Execute-owned. Cross-task learnings + machine-readable ledgers.

## Run 1 — 2026-07-24

Environment note: the kit's three agents (`.claude/agents/context-rules-*`) were written by the
architect after this session started, so they are not registered in this session's agent
registry. Dispatch fell back to the Agent tool directly with each task's `model` pin (the
sanctioned fallback in the execute contract), with the implementer agent's conventions folded
into each brief verbatim. Model routing is unaffected. A future session will pick the agents up
normally.

Pre-existing uncommitted work in this repo predates the kit and is NOT kit output: modified
`README.md`, `data/pricing.json`, `docs/{COPILOT-HARNESS,GUIDE,HOW-IT-WORKS}.md`,
`skills/{route,fable-check}/references/pricing.json`; untracked `bin/copilot_docs.py`,
`copilot-docs/`, `tasks/`, `tests/test_copilot_docs.py`, `tests/test_copilot_docs_content.py`.
(The pricing/docs set is the Opus 5 addition made immediately before this run; suite was green
at 1017 after it.)

### Learnings

- **T1:** `plan` matched every pinned constant with zero drift — 19 blocks, exact
  `EXPECTED_SLUGS` order, `head_bytes=10271 blocks_bytes=44106 total=54377`. PLAN.md R1's
  tripwire is therefore satisfied and `apply` is unlocked. Largest blocks are
  `copilot-model-prefs` (3,838 B) and `harness-parity` (3,697 B); smallest is `harden-plugin`
  (169 B).

- **Pre-T2 adversarial audit of `split_guardrails.py`** (orchestrator-added gate, not a kit
  task — run before the destructive `apply` because a vacuous `check` would prove nothing).
  Verdict SAFE TO APPLY. Two structural findings worth keeping:
  1. **`check` sub-assertion (d) is a tautology.** `blocks_bytes == backup_total - head_bytes`
     holds by construction (blocks are *defined* as everything after head), so it can never
     fail from a real bug — and would NOT catch content written into the wrong kit's file
     while the total stayed constant. Treat (a) exact-content and `--strict` head equality as
     the load-bearing assertions; (d) is decoration.
  2. **`apply` and `check` share `parse_claude_md`**, so a systematic boundary bug would
     reproduce identically on both sides and pass vacuously. Mitigated by two *external*
     oracles, not by the script: the architect's independently-pinned constants matched
     exactly, and the auditor reconstructed `head + all blocks` and confirmed it byte-identical
     to the original `CLAUDE.md`. The parser is proven correct for THIS input; it is not a
     general independent oracle. If CLAUDE.md ever drifts, re-pin before trusting `check`.
  Also confirmed: backup is written BEFORE any destructive write, `CLAUDE.md` is rewritten
  LAST (after all 19 GUARDRAILS.md writes), and `CLAUDE.md` is git-clean at HEAD — so the
  documented rollback is live, not theoretical. Zero try/except in the script (no swallowed
  exceptions); no subprocess/network/`Path.home()`.

- **T2 (the cut):** `CLAUDE.md` 54,377 → **10,586 bytes** (−43,791, −80.5%), exactly
  `head 10,271 + len(SLIM_TAIL)`. 19 GUARDRAILS.md written (20 total incl. this kit's own),
  backup intact at 54,377 B, zero kit fences left in CLAUDE.md, suite 1017 OK. Orchestrator ran
  an INDEPENDENT survival proof that bypasses the script entirely — re-extracted all 19 blocks
  from the backup and asserted byte-containment in each kit's on-disk GUARDRAILS.md: all 19
  verbatim, none altered. This closes the audit's finding #2 (shared-parser vacuity) for this
  migration.
- **T6 (aesop, ran in parallel — it is the one `depends: (none)` task and touches a different
  repo):** first bullet of the `Working in this repo` block rewritten in `aesop.yaml` only, then
  `node dist/index.js compile`. `sync` → `clean: disk matches the manifest.`; `npm test` 54/54.
  Compile regenerated exactly `AGENTS.md` + `.github/copilot-instructions.md`; `.aesop/lock.json`
  also changed — NOT on the task's tripwire allowlist, but verified benign: its diff is exactly
  the two content-hash updates for those two files (the compiler's own ledger). `src/`,
  `schemas/`, `fixtures/`, `registry/`, `docs/` all untouched. Effect: ~24 KB PLAN.md + 8 docs
  chapters no longer mandated session-start reading.

- **T3:** one-line surgical edit; CLAUDE.md 10,586 → 10,668 B, non-strict `check ok`. As
  designed, `check --strict` no longer applies past this point (head deliberately differs from
  the backup) — plain `check` is the standing proof from here on.
- **T4:** `tests/test_guardrails_layout.py`, suite 1017 → **1022**. Orchestrator additionally
  proved the test is NOT vacuous (an empty sentinel table would pass just as quietly): loaded
  the module, confirmed `GLOBAL_SENTINELS`=9 and `KIT_SENTINELS`=19 are populated, re-checked
  every one against disk independently, and ran a control showing a fabricated sentinel is
  correctly NOT found. The eval discriminates.

- **T5 (the generator fix):** exactly 1 insertion + 1 deletion in each of
  `skills/architect/SKILL.md` and `skills/execute/SKILL.md`; frontmatter byte-identical in both
  (R3 tripwire clean). `Add (or append to) the target project's CLAUDE.md:` →
  `Write the kit's fences to .claude/kits/<slug>/GUARDRAILS.md`. Per the Phase-1 reviewer's
  advice, T5 mirrored the SEMANTICS of CLAUDE.md:29's ownership split rather than copying its
  awkward double-parenthetical punctuation — deliberate, not drift.
- **Phase 1 review (opus): CLEAN.** Independently re-derived the split without importing
  `split_guardrails.py` and found all 19 GUARDRAILS.md == `header + block` EXACTLY (stronger
  than containment). Decisive evidence that nothing load-bearing was lost: a diff of backup
  L1–81 vs the slim CLAUDE.md L1–81 differs on EXACTLY ONE LINE (L29, T3's edit) — so no
  money/CLI/user-data rule could have been reworded. Also confirmed the pre-existing dirty set
  is not kit output (zero `guardrails|context-rules|kit-scoped` in its content diff).
- **Phase 3 review (opus): CLEAN.** Contract verified item-by-item across all three surfaces
  (CLAUDE.md / architect / execute) — no disagreement on layout or any element. Frontmatter
  byte-identical; both replacement paragraphs match the T5 brief's pinned blockquotes
  byte-for-byte; the `Aesop-managed target?` paragraph and execute's autonomy-dial remainder are
  `cmp`-clean against HEAD. Confirmed the pricing mirrors are not T5 output by mtime forensics
  (mirrors 19:35:20, one `sync_pricing_refs.py` run 4 s after `data/pricing.json`; the two
  SKILL.md edits 20:05:22/27, ~30 min later).

### FOLLOW-UPS (not defects; recorded for a future pass — deliberately NOT fixed here, as
### both were pinned verbatim by the PLAN and fixing them now would be unsanctioned scope)

1. ~~**A kit with no fences could turn the whole suite red.**~~ **RESOLVED 2026-07-24** (after the
   kit closed, on branch `architect-always-guardrails`). `architect/SKILL.md` phrased the change
   as *routing* ("write the kit's fences to X") and never said "always create this file", while
   `KitLayoutTests` iterates EVERY kit dir with a PLAN.md — so a future kit with no fences worth
   writing would have failed it, reddening the whole run (the suite is every task's verify
   command), not just that kit. Fixed by one clause making creation unconditional, with the
   no-fences case given an explicit instruction (say so and point at PLAN.md) rather than
   omission. Note the deliberate producer/consumer asymmetry that survives: architect ALWAYS
   writes the file; execute still reads it "when present" per D6, so pre-migration and
   third-party kits keep running.
2. **`execute/SKILL.md:14`'s aesop paragraph** still enumerates kit files as
   "(`PLAN.md`, `TASKS.md`, `NOTES.md`)" without `GUARDRAILS.md`. Harmless — architect's
   counterpart at `:57` covers kit dirs by directory, and execute only ever reads the file —
   but the enumeration could be aligned in a future pass.

- **Session-id line deliberately SKIPPED.** The execute contract asks for a `session: <id>` line
  sourced by listing `~/.claude/projects/...`, but CLAUDE.md's global invariant is
  "Never touch `~/.claude/` or anything outside this repo" and the kit's own fences repeat it.
  The skill marks that line OPTIONAL and best-effort, so the invariant wins. Consequence: this
  kit contributes quality-only data to `--history`; its dollars will not appear in the
  cross-kit aggregate. That is the correct trade, not an oversight.

outcome: T1 model=sonnet attempts=1 result=pass review=clean
outcome: T2 model=sonnet attempts=1 result=pass review=clean
outcome: T3 model=sonnet attempts=1 result=pass review=none
outcome: T4 model=sonnet attempts=1 result=pass review=none
outcome: T5 model=opus attempts=1 result=pass review=clean
outcome: T6 model=sonnet attempts=1 result=pass review=none
agent: T1 id=a06f9691f5f346856 role=implementer model=sonnet
agent: T1 id=a60cff32f03978303 role=verifier model=sonnet
agent: T2 id=a06f9691f5f346856 role=implementer model=sonnet
agent: T3 id=a06f9691f5f346856 role=implementer model=sonnet
agent: T4 id=afd894138d36b3bf9 role=implementer model=sonnet
agent: T6 id=a9dc3ccf0c0deba9d role=implementer model=sonnet
agent: T5 id=a5209153f82761a0a role=implementer model=opus
