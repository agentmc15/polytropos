# NOTES — aesop-bridge execution

Cross-task learnings maintained by the execute orchestrator. Read before dispatching later tasks.

## Preconditions confirmed at run start (2026-07-01)
- harden-plugin kit is complete (all 8 tasks done, final review PROCEED) — T3's anchor sentences
  (harden-plugin T6's output) are in place in skills/route/SKILL.md and skills/fable-check/SKILL.md.
- Suite baseline: 28 tests green (`python3 -m unittest discover -s tests`).
- `grep -rE '\$[0-9]' skills/` is empty — keep it that way (harden-plugin done-definition
  gate; do not introduce `$<digit>` literals in any skill file).

## Progress
- **T1 — done** (sonnet). `bin/sync_pricing_refs.py` + both mirrors created; adversarially
  verified PASS (byte-copy mechanism confirmed at source level, root param exercised in temp
  trees, --check exit codes correct, real mirrors never corrupted during testing).
- **T2 — done** (sonnet). `tests/test_pricing_refs.py`, 5 tests, suite now 33 green. Implementer
  correctly stopped on a verify failure and diagnosed it: **dotted-module invocations
  (`python3 -m unittest tests.<module>`) do not work on this machine** — a pre-existing
  site-packages package named `tests` (Polymarket, has `__init__.py`) shadows the repo's
  namespace-style `tests/` dir under PEP 420. Repo tests themselves are fine.

- **T3 — done** (sonnet). Three-step pricing ladder in both portable skills; anchors
  (harden-plugin T6 output) confirmed present before editing, replaced exactly once each;
  `$`-grep gate still clean. Verifier confirmed replacements verbatim, old anchors gone,
  mirrors byte-match.
- **T4 — done** (sonnet). Mirror rule appended to CLAUDE.md first invariant bullet; README
  "Updating prices" gained the sync-script step. NOTE: CLAUDE.md's anchor sentence wraps
  mid-phrase across lines ("...its field\nname (e.g. ...)") — quote-with-line-breaks when
  editing that bullet.

- **Phase 1 review — CLEAN** (reviewer reproduced the site-packages collision and approved the
  T2/T8 verify amendments).
- **T5 — done** (opus). `**Aesop-managed target?**` paragraph appended to architect's
  `### Harness guardrails`; kit-contract markers re-checked in both skills.
- **T6 — done** (sonnet). Setup item 3 appended to execute's `## Setup`, wording consistent
  with T5's paragraph (same detection rule + manifest destination); contract intact.

- **Phase 2 review — CLEAN** (append-only confirmed character-for-character; contract intact;
  D6 fidelity checked, no overclaim).
- **T7 — done** (sonnet). `bin/aesop_bridge.py`: tier_map/est_tick/check_budget pure functions +
  tiers/est-tick/check-budget CLI. Current tier mapping (computed): frontier→claude-fable-5,
  strong→claude-opus-4-8, mid→claude-sonnet-5, cheap→claude-haiku-4-5. No hardcoded
  prices/model-ids in source.
- **T8 — done** (sonnet). `tests/test_aesop_bridge.py`, 11 tests with synthetic fixture
  (fake round numbers, explicit `today=` everywhere — no wall-clock dependence). Suite: 44 green.

- **Phase 3 review — CLEAN** (formula/boundary fidelity verified at source level; no hardcoded
  prices/model-ids; suite 44 green).
- **T9 — done** (opus). `docs/AESOP-INTEGRATION.md` (195 lines): five required sections, all
  aesop claims pinned to `5506617`, no live prices as facts; grounded in real bridge-CLI runs.
- **T10 — done** (sonnet). README cross-link paragraph after the architecture-guide line.
- **PLAN.md overall done-check — PASS** (orchestrator, 2026-07-01): 44 tests green,
  `sync_pricing_refs.py --check` ok, ladder in both portable skills, tiers-mapping values all in
  pricing.json, doc present, aesop-awareness text in both architect+execute with contract intact,
  pricing.json untouched, `$`-grep clean.

## ⚠️ Standing rule for later tasks (T8 especially)
Never use `python3 -m unittest tests.<module>` in this repo/environment. Use
`python3 -m unittest discover -s tests [-p '<file>.py']` — the T2 and T8 verify commands in
TASKS.md were amended accordingly during execution (orchestrator edit, both re-verified).
