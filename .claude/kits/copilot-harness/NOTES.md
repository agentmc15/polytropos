# NOTES — copilot-harness execution

Cross-task learnings maintained by the execute orchestrator. Read before dispatching later tasks.

## Standing rules (from PLAN.md / TASKS.md)
- Never write outside the repo — including `~/.copilot` (installs use `--copilot-home <tmpdir>` only).
- Never run node/npm/`aesop compile`; stdlib-only Python.
- Never touch `data/pricing.json`, `.claude-plugin/`, `skills/`, or the completed kits.
- Verify with `python3 -m unittest discover -s tests [-p '<file>.py']` — the dotted-module form
  is broken on this machine (site-packages `tests` shadows the repo dir under PEP 420).
- Baseline suite at run start: 44 tests green.

## Progress
- **T1 — done** (haiku). `data/pricing.copilot.json` pinned JSON, 19 models (2 frontier/4 strong/
  6 mid/7 cheap), AIC unit as data. Independently verified.
- **T2 — done** (sonnet). `bin/copilot_pricing.py`: effective_rates/est_cost/plan_runway/
  models_table + est/models/runway CLI. Long-context whole-estimate rule, cache-write excluded,
  AIC from `billing_unit.usd_per_credit`, unknowns exit 2. Independently verified.
- **T3 — done** (sonnet). `tests/test_copilot_pricing.py`, 21 tests (synthetic fixture with
  usd_per_credit 0.5 to prove derivation). Suite: 65 green. Independently verified.

Phase 2 note: T4 (haiku) and T5 (opus) are both independent with deps satisfied → dispatch in
parallel. T6 depends on T1+T4+T5.
- **T4 — done** (haiku). `copilot/aesop.yaml` pinned manifest. Independently verified.
- **T5 — done** (opus). `copilot/.github/agents/route.agent.md` (69 lines) + `copilot-instructions.md`
  (12 lines); five action mechanisms, `{{POLYTROPOS_ROOT}}` placeholder, no absolute paths
  or price literals, `model: claude-sonnet-5` pin is a live pricing key. Independently verified.
- **T6 — done** (sonnet). `tests/test_copilot_bundle.py`, 10 tests enforcing manifest↔bundle
  consistency (the `aesop compile` stand-in). Suite: 75 green. Independently verified.

Phase 3 note: T7 (harness_select.py) → T8 (its tests) are serial. Standing rule for T7/T8:
installs go to `--copilot-home <tmpdir>` ONLY; never the real `~/.copilot`.
- **T7 — done** (sonnet). `bin/harness_select.py`: detect() + install_copilot() + CLI. Placeholder
  → absolute repo root at install; claude-code writes nothing (marketplace message). Independently
  verified into a temp home; real `~/.copilot/agents` confirmed absent (nothing written there).
  Suite: 75 green. NOTE for future subagents: on this machine `cd` into the repo can hit a
  Desktop/desktop case quirk — resolve paths via `Path(__file__).resolve()` rather than `$PWD`.
- The user HAS a real `~/.copilot` (their live Copilot install) — T8 must keep every install in a
  `tempfile.TemporaryDirectory`; never read/write the real `~/.copilot`.
- **T8 — done** (sonnet). `tests/test_harness_select.py`, 8 tests (all installs in temp dirs).
  Suite: 83 green. Real `~/.copilot/agents` confirmed absent. Independently verified.

Phase 4 note: T9 (docs + README, sonnet) and T10 (CLAUDE.md invariants, haiku) are both
independent with deps satisfied → dispatch in parallel. They touch different files
(T9: docs/COPILOT-HARNESS.md + README.md; T10: CLAUDE.md).
- **Phase 3 review — CLEAN** (reviewer thoroughly confirmed the real `~/.copilot` fence held).
- **T9 — done** (sonnet). `docs/COPILOT-HARNESS.md` (143 lines, six H2 headings, 19-model AIC
  snapshot table labeled to cached_date 2026-07-01, aesop pin 5506617) + README cross-link
  paragraph after the Aesop-integration line. Independently verified. (Post-review fix: corrected
  prose that wrongly named gpt-5.3-codex as long-context; the three long-context models are
  gpt-5.5, gpt-5.4, gemini-3.1-pro.)
- **T10 — done** (haiku). CLAUDE.md: Copilot-side invariant bullet + the copilot_pricing.py
  how-to line. Independently verified. Suite: 83 green.
